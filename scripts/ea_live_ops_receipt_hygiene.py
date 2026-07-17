from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunsplit


REDACTED_VALUE_MARKERS = (
    "token",
    "secret",
    "bearer",
    "password",
    "api_key",
    "client_secret",
    "access_token",
    "authorization",
    "cookie",
    "credential",
    "private_key",
    "session_id",
)
SAFE_SENSITIVE_KEY_SUFFIXES = ("_present", "_count", "_keys", "_sha256")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
SCRIPT_SUFFIXES = (".py", ".sh", ".ps1", ".bash", ".zsh", ".rb", ".js", ".cjs", ".mjs", ".ts")


def json_from_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
        for line in reversed(raw.splitlines()):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        if payload is None or not isinstance(payload, dict):
            return {}
    return dict(payload) if isinstance(payload, dict) else {}


def looks_like_secret_value(key: str, value: Any) -> bool:
    normalized_key = str(key or "").strip().lower()
    if not any(marker in normalized_key for marker in REDACTED_VALUE_MARKERS):
        return False
    if normalized_key.endswith(SAFE_SENSITIVE_KEY_SUFFIXES):
        return False
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return False


def contains_secretish_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if looks_like_secret_value(str(key), nested):
                return True
            if contains_secretish_key(nested):
                return True
        return False
    if isinstance(value, list):
        return any(contains_secretish_key(item) for item in value)
    return False


def _redact_local_path(path: str) -> str:
    parts = str(path or "").split("/")
    if len(parts) == 4 and parts[1] == "sessions" and parts[3] == "pair":
        parts[2] = "redacted"
    return "/".join(parts)


def _sensitive_name(value: Any) -> bool:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return any(marker in normalized for marker in REDACTED_VALUE_MARKERS)


def _public_http_url(text: str) -> str:
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return text

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    safe_query_pairs = [
        (key, value)
        for key, value in query_pairs
        if not _sensitive_name(key)
    ]
    fragment = parsed.fragment
    if any(_sensitive_name(key) for key, _ in parse_qsl(fragment, keep_blank_values=True)):
        fragment = ""

    has_credentials = parsed.username is not None or parsed.password is not None
    removed_sensitive_query = len(safe_query_pairs) != len(query_pairs)
    removed_sensitive_fragment = fragment != parsed.fragment
    if not (has_credentials or removed_sensitive_query or removed_sensitive_fragment):
        return text

    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            urlencode(safe_query_pairs, doseq=True),
            fragment,
        )
    )


def _looks_like_windows_absolute_path(text: str) -> bool:
    raw = str(text or "").strip()
    return (
        len(raw) >= 3
        and raw[0].isalpha()
        and raw[1] == ":"
        and raw[2] in {"/", "\\"}
    ) or raw.startswith("\\\\")


def _local_source_label(path_text: str) -> str:
    normalized = str(path_text or "").replace("\\", "/").rstrip("/")
    if not normalized:
        return "host-local-file:redacted"
    basename = normalized.split("/")[-1]
    if basename.lower().endswith(SCRIPT_SUFFIXES):
        return f"script:{basename}"
    if basename:
        return f"host-local-file:{basename}"
    return "host-local-file:redacted"


def _script_source_label(text: str) -> str:
    raw = str(text or "").strip()
    lowered = raw.lower()
    for suffix in SCRIPT_SUFFIXES:
        if not lowered.endswith(suffix):
            continue
        trimmed = raw[: -len(suffix)]
        token = trimmed.replace("\\", "/").split("/")[-1].split(".")[-1].strip()
        if token:
            return f"script:{token}{suffix}"
    return ""


def public_href(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme in {"http", "https"} and host in LOOPBACK_HOSTS:
        sanitized_path = _redact_local_path(parsed.path or "/")
        return f"host-local://{sanitized_path}{'#' + parsed.fragment if parsed.fragment else ''}"
    if parsed.scheme == "host-local":
        sanitized_path = _redact_local_path(parsed.path or "/")
        return f"host-local://{sanitized_path}{'#' + parsed.fragment if parsed.fragment else ''}"
    return _public_http_url(text)


def public_source_ref(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme == "script":
        return text
    if parsed.scheme == "file":
        return _local_source_label(parsed.path or "")
    if parsed.scheme in {"http", "https", "host-local"}:
        return public_href(text)
    if text.startswith("/") or _looks_like_windows_absolute_path(text):
        return _local_source_label(text)
    script_label = _script_source_label(text)
    if script_label:
        return script_label
    if ("/" in text or "\\" in text) and text.replace("\\", "/").rstrip("/").split("/")[-1].lower().endswith(
        SCRIPT_SUFFIXES
    ):
        return _local_source_label(text)
    return text


def stderr_summary(stderr: str) -> str:
    text = str(stderr or "").strip()
    if not text:
        return ""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"present len={len(text)} sha256={digest}"
