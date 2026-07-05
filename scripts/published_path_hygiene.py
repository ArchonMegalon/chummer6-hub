from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOOPBACK_URL_PATTERN = re.compile(r"https?://(?:127\.0\.0\.1|localhost|\[::1\]|::1)(?::\d+)?(?:[/?#][^\s\"']*)?")


def expand_portable_path(value: Any) -> Path:
    text = str(value or "").strip()
    if text == "~":
        return Path.home()
    if text.startswith("~/"):
        return Path.home() / text[2:]
    return Path(text)


def portable_path_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    home = Path.home()
    try:
        relative = path.relative_to(home)
    except ValueError:
        return str(path)
    suffix = relative.as_posix()
    return "~" if not suffix or suffix == "." else f"~/{suffix}"


def portable_command_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    home = Path.home()
    return text.replace(str(home) + "/", "~/")


def contains_loopback_url_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(LOOPBACK_URL_PATTERN.search(text))


def public_base_url_text(value: Any, *, fallback: str = "https://chummer.run") -> str:
    normalized_fallback = str(fallback or "").strip() or "https://chummer.run"
    text = str(value or "").strip()
    if not text:
        return normalized_fallback
    parsed = urlparse(text)
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme in {"http", "https"} and host in LOOPBACK_HOSTS:
        return normalized_fallback
    return text


def published_url_text(value: Any, *, public_base_url: str = "https://chummer.run") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized_public_base_url = public_base_url_text(public_base_url).rstrip("/")

    def replace_loopback_url(match: re.Match[str]) -> str:
        parsed = urlparse(match.group(0))
        suffix = parsed.path or ""
        if parsed.query:
            suffix += f"?{parsed.query}"
        if parsed.fragment:
            suffix += f"#{parsed.fragment}"
        return f"{normalized_public_base_url}{suffix}"

    return LOOPBACK_URL_PATTERN.sub(replace_loopback_url, text)


def published_command_text(value: Any, *, public_base_url: str = "https://chummer.run") -> str:
    text = portable_command_text(value)
    if not text:
        return ""
    return published_url_text(text, public_base_url=public_base_url)
