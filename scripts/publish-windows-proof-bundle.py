#!/usr/bin/env python3
"""Publish one isolated Windows proof bundle through the durable session API.

The uploader accepts only current-owner 0600 credential files, never places
credentials in argv or a curl config file, records recovery state durably before
irreversible calls, and never falls back to canonical release publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import ssl
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterator, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, HTTPHandler, Request, build_opener

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from windows_proof_evidence import (  # noqa: E402
    MANIFEST_SCHEMA,
    validate_governed_windows_evidence,
    validate_manifest_freshness,
)

MANIFEST_NAME = "WINDOWS_PROOF_MANIFEST.generated.json"
RECEIPT_SCHEMA = "chummer.windows-proof.upload-attempt/v1"
DEFAULT_SESSIONS_URL = "https://chummer.run/api/internal/windows-proof/upload-sessions"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SESSION_PATTERN = re.compile(r"^[0-9a-f]{32}$")
PORTABLE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,254}$")
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_CF_ACCESS_ENV_BYTES = 16 * 1024
DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024
DIRECT_LIMIT_BYTES = 8 * 1024 * 1024
CF_ACCESS_ENV_KEY_PATTERN = re.compile(
    r"^(?:(?P<prefix>[A-Z0-9_]+)_)?CF_ACCESS_CLIENT_(?P<field>ID|SECRET)$"
)
REQUIRED_KINDS = {
    "installer",
    "bootstrap_payload",
    "bootstrap_metadata",
    "signing_receipt",
    "startup_smoke_receipt",
    "visual_handoff",
    "build_provenance_receipt",
    "sbom",
}
KIND_PATH_RULES = {
    "installer": ("files/", "-installer.exe"),
    "bootstrap_payload": ("files/", "-payload.zip"),
    "bootstrap_metadata": ("files/", "-payload.zip.json"),
    "signing_receipt": ("signing/", ".receipt.json"),
    "startup_smoke_receipt": ("startup-smoke/", ".receipt.json"),
    "visual_handoff": ("proof/", "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"),
    "build_provenance_receipt": (
        "proof/build-provenance/v1/invocations/",
        ".avalonia.win-x64.installer.json",
    ),
    "sbom": ("proof/build-provenance/v1/sbom/", "desktop-avalonia.cdx.json"),
}
KIND_CONTENT_TYPES = {
    "installer": "application/vnd.microsoft.portable-executable",
    "bootstrap_payload": "application/zip",
    "bootstrap_metadata": "application/json",
    "signing_receipt": "application/json",
    "startup_smoke_receipt": "application/json",
    "visual_handoff": "application/json",
    "build_provenance_receipt": "application/json",
    "sbom": "application/vnd.cyclonedx+json",
}


class DuplicateJsonKey(ValueError):
    pass


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError, DuplicateJsonKey) as exc:
        fail(f"{label} is not a unique-key UTF-8 JSON object: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        fsync_directory(path.parent)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def ensure_regular_without_links(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        fail(f"{label} is missing or inaccessible: {exc}")
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        fail(f"{label} must be a non-symlink regular file: {path}")
    for parent in path.parents:
        if parent.is_symlink():
            fail(f"{label} must not traverse a symbolic link: {parent}")


def normalize_relative_path(value: Any) -> str:
    path = str(value or "").strip()
    if (
        not path
        or path.startswith("/")
        or path.endswith("/")
        or "\\" in path
        or ":" in path
        or any(ord(character) < 32 for character in path)
    ):
        fail("manifest contains a nonportable relativePath")
    segments = path.split("/")
    if len(segments) < 2 or any(
        segment in {"", ".", ".."} or not PORTABLE_SEGMENT.fullmatch(segment)
        for segment in segments
    ):
        fail("manifest contains a nonportable relativePath segment")
    return path


@dataclass(frozen=True)
class DeclaredFile:
    kind: str
    relative_path: str
    file_name: str
    size: int
    sha256: str
    path: Path


@dataclass(frozen=True)
class ValidatedBundle:
    root: Path
    manifest_path: Path
    manifest_bytes: bytes
    manifest: dict[str, Any]
    manifest_sha256: str
    candidate_version: str
    files: tuple[DeclaredFile, ...]
    inventory_digest: str


@dataclass(frozen=True, repr=False)
class CfAccessCredentials:
    client_id: str
    client_secret: str

    def request_headers(self) -> dict[str, str]:
        return {
            "CF-Access-Client-Id": self.client_id,
            "CF-Access-Client-Secret": self.client_secret,
        }


def validate_bundle(root: Path) -> ValidatedBundle:
    if root.is_symlink() or not root.is_dir():
        fail(f"bundle root must be a non-symlink directory: {root}")
    manifest_path = root / MANIFEST_NAME
    ensure_regular_without_links(manifest_path, "Windows proof manifest")
    manifest_bytes = manifest_path.read_bytes()
    if not 1 <= len(manifest_bytes) <= 1024 * 1024:
        fail("Windows proof manifest size is invalid")
    manifest = parse_json_bytes(manifest_bytes, "Windows proof manifest")
    expected_top_level = {
        "schemaVersion": MANIFEST_SCHEMA,
        "channel": "preview",
        "releaseScope": "proof_only",
        "supportabilityState": "review_required",
        "publicTrustPosture": "blocked",
        "cfAccessGated": True,
        "revoked": False,
    }
    for key, expected in expected_top_level.items():
        if manifest.get(key) != expected:
            fail(f"manifest.{key} must be {expected!r}")
    validate_manifest_freshness(manifest)
    candidate_version = str(manifest.get("candidateVersion") or "").strip()
    if not PORTABLE_SEGMENT.fullmatch(candidate_version) or ".." in candidate_version:
        fail("manifest candidateVersion is invalid")
    proof_policy = manifest.get("proofOnlyPolicy")
    if not isinstance(proof_policy, dict) or any(
        proof_policy.get(key) is not True
        for key in ("enabled", "unsignedPreviewAllowed", "nativeWindowsValidationRequired")
    ):
        fail("manifest proofOnlyPolicy is incomplete")
    signing = manifest.get("signing")
    if not isinstance(signing, dict) or signing.get("status") not in {"pass", "skipped_preview"}:
        fail("manifest signing evidence is invalid")
    smoke = manifest.get("compatibilitySmoke")
    if not isinstance(smoke, dict) or (
        smoke.get("status"), smoke.get("executionEnvironment"), smoke.get("nativeWindows")
    ) != ("pass", "wine_compatibility", False):
        fail("manifest compatibility smoke posture is invalid")
    handoff = manifest.get("nativeHostHandoff")
    if not isinstance(handoff, dict) or (
        handoff.get("status"), handoff.get("onlyBlocker"), handoff.get("onlyBlockerIsVisualProof")
    ) != ("ready_for_windows_host", "visual_proof", True):
        fail("manifest native-host handoff posture is invalid")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(REQUIRED_KINDS):
        fail("manifest must declare exactly the eight proof-only artifact roles")
    declared: list[DeclaredFile] = []
    kinds: set[str] = set()
    paths: set[str] = set()
    portable_paths: set[str] = set()
    for row in artifacts:
        if not isinstance(row, dict):
            fail("manifest artifact rows must be objects")
        kind = str(row.get("kind") or "")
        relative_path = normalize_relative_path(row.get("relativePath"))
        artifact_id = str(row.get("artifactId") or "")
        file_name = str(row.get("fileName") or "")
        content_type = str(row.get("contentType") or "")
        size = row.get("size")
        digest = str(row.get("sha256") or "")
        if kind not in REQUIRED_KINDS:
            fail("manifest artifact kind is not allowlisted")
        prefix, suffix = KIND_PATH_RULES[kind]
        if not relative_path.startswith(prefix) or not relative_path.endswith(suffix):
            fail(f"manifest path is not allowlisted for artifact kind {kind}")
        if (
            kind in kinds
            or artifact_id != "avalonia-win-x64-installer"
            or row.get("head") != "avalonia"
            or row.get("rid") != "win-x64"
            or content_type != KIND_CONTENT_TYPES[kind]
            or relative_path in paths
            or relative_path.casefold() in portable_paths
            or Path(relative_path).name != file_name
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or not SHA256_PATTERN.fullmatch(digest)
        ):
            fail("manifest artifact row is invalid or collides under portable comparison")
        kinds.add(kind)
        paths.add(relative_path)
        portable_paths.add(relative_path.casefold())
        path = root / Path(relative_path)
        ensure_regular_without_links(path, f"manifest artifact {relative_path}")
        if path.stat().st_size != size or sha256_file(path) != digest:
            fail(f"manifest artifact bytes do not match {relative_path}")
        declared.append(DeclaredFile(kind, relative_path, file_name, size, digest, path))
    if kinds != REQUIRED_KINDS:
        fail("manifest artifact kinds are not the exact proof-only eight-role set")

    by_kind = {item.kind: item for item in declared}
    governed_evidence = validate_governed_windows_evidence(
        version=candidate_version,
        installer_path=by_kind["installer"].path,
        provenance_path=by_kind["build_provenance_receipt"].path,
        sbom_path=by_kind["sbom"].path,
    )
    validate_manifest_freshness(manifest, not_before=governed_evidence.build_started_at)

    observed: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"bundle contains a symbolic link: {path}")
        if path.is_file():
            observed.add(path.relative_to(root).as_posix())
    expected_paths = paths | {MANIFEST_NAME}
    if observed != expected_paths:
        fail("bundle contains undeclared, missing, or stale files")

    inventory_hash = hashlib.sha256()
    for row in sorted(declared, key=lambda item: item.relative_path):
        inventory_hash.update(f"{row.relative_path}\0{row.size}\0{row.sha256}\n".encode())
    return ValidatedBundle(
        root,
        manifest_path,
        manifest_bytes,
        manifest,
        hashlib.sha256(manifest_bytes).hexdigest(),
        candidate_version,
        tuple(declared),
        inventory_hash.hexdigest(),
    )


def read_ticket(path: Path) -> str:
    ensure_regular_without_links(path, "Windows proof upload ticket file")
    metadata = path.stat()
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        fail("ticket file must be owned by the current user with exact mode 0600")
    if not 1 <= metadata.st_size <= 8192:
        fail("ticket file size is invalid")
    raw = path.read_bytes()
    if b"\0" in raw:
        fail("ticket file contains a NUL byte")
    try:
        value = raw.decode("utf-8").rstrip("\r\n")
    except UnicodeError as exc:
        fail(f"ticket file is not UTF-8: {exc}")
    if not value or "\r" in value or "\n" in value:
        fail("ticket file must contain exactly one non-empty line")
    return value


def read_current_owner_private_file(path: Path, label: str, max_bytes: int) -> bytes:
    """Read a bounded private file without following a final-component symlink."""

    ensure_regular_without_links(path, label)
    before = path.lstat()
    if before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600:
        fail(f"{label} must be owned by the current user with exact mode 0600")
    if not 1 <= before.st_size <= max_bytes:
        fail(f"{label} size is invalid")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"{label} could not be opened safely: {exc}")
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or not 1 <= opened.st_size <= max_bytes
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            fail(f"{label} changed or failed its private-file contract while opening")

        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            block = os.read(descriptor, min(8192, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(raw) != opened.st_size
            or after.st_size != opened.st_size
            or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            fail(f"{label} changed while it was being read")
        if len(raw) > max_bytes:
            fail(f"{label} size is invalid")
        return raw
    finally:
        os.close(descriptor)


def read_cf_access_env_file(path: Path) -> CfAccessCredentials:
    label = "Cloudflare Access credential file"
    raw = read_current_owner_private_file(path, label, MAX_CF_ACCESS_ENV_BYTES)
    if b"\0" in raw:
        fail(f"{label} contains a NUL byte")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        fail(f"{label} is not UTF-8: {exc}")
    if "\r" in text:
        fail(f"{label} must use LF line endings")
    if text.endswith("\n"):
        text = text[:-1]
    lines = text.split("\n")
    if len(lines) != 2 or any(not line or line.strip() != line for line in lines):
        fail(f"{label} must contain exactly two non-empty assignments")

    values: dict[str, str] = {}
    selected_prefix: str | None = None
    prefix_selected = False
    for line in lines:
        if "=" not in line:
            fail(f"{label} contains a malformed assignment")
        key, value = line.split("=", 1)
        match = CF_ACCESS_ENV_KEY_PATTERN.fullmatch(key)
        if match is None:
            fail(f"{label} contains an unexpected key")
        prefix = match.group("prefix")
        if prefix_selected and prefix != selected_prefix:
            fail(f"{label} mixes credential key prefixes")
        selected_prefix = prefix
        prefix_selected = True
        field = str(match.group("field"))
        if field in values:
            fail(f"{label} contains a duplicate key")
        if (
            not value
            or value.strip() != value
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        ):
            fail(f"{label} contains an empty or invalid value")
        values[field] = value
    if set(values) != {"ID", "SECRET"}:
        fail(f"{label} must contain each required key exactly once")
    return CfAccessCredentials(
        client_id=values["ID"],
        client_secret=values["SECRET"],
    )


class RejectRedirects(HTTPRedirectHandler):
    def http_error_301(self, req: Any, fp: Any, code: int, msg: str, headers: Any) -> None:
        raise HTTPError(req.full_url, code, "redirects are forbidden", headers, fp)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


class ProofHttpClient:
    def __init__(
        self,
        sessions_url: str,
        ticket: str,
        allow_http_loopback: bool = False,
        cf_access_credentials: CfAccessCredentials | None = None,
    ) -> None:
        self.sessions_url = validate_sessions_url(sessions_url, allow_http_loopback)
        self._ticket = ticket
        self._cf_access_credentials = cf_access_credentials
        credential_values = [ticket]
        if cf_access_credentials is not None:
            credential_values.extend(
                [cf_access_credentials.client_id, cf_access_credentials.client_secret]
            )
        self._credential_values = tuple(
            sorted((value for value in credential_values if value), key=len, reverse=True)
        )
        handlers: list[Any] = [RejectRedirects()]
        if urlsplit(self.sessions_url).scheme == "https":
            handlers.append(HTTPSHandler(context=ssl.create_default_context()))
        else:
            handlers.append(HTTPHandler())
        self.opener = build_opener(*handlers)

    def _redact(self, value: str) -> str:
        redacted = value
        for credential in self._credential_values:
            redacted = redacted.replace(credential, "[redacted]")
        return redacted

    def request_json(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        content_type: str | None = None,
        *,
        retry_idempotent: bool = False,
    ) -> dict[str, Any]:
        attempts = 4 if retry_idempotent else 1
        last_error: BaseException | None = None
        for attempt in range(attempts):
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {self._ticket}",
                "Cache-Control": "no-store",
            }
            if self._cf_access_credentials is not None:
                headers.update(self._cf_access_credentials.request_headers())
            if content_type:
                headers["Content-Type"] = content_type
            request = Request(url, data=body if body is not None else b"", headers=headers, method=method)
            try:
                with self.opener.open(request, timeout=90) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        fail("upload response exceeded the bounded response limit")
                    return parse_json_bytes(raw, "upload response")
            except HTTPError as exc:
                raw = exc.read(MAX_RESPONSE_BYTES + 1)
                detail = ""
                if len(raw) <= MAX_RESPONSE_BYTES:
                    try:
                        problem = parse_json_bytes(raw, "upload problem")
                        detail = self._redact(
                            str(problem.get("detail") or problem.get("title") or "")
                        )[:500]
                    except ValueError:
                        detail = ""
                if retry_idempotent and 500 <= exc.code < 600 and attempt + 1 < attempts:
                    time.sleep(1 + attempt)
                    continue
                fail(f"upload request failed with HTTP {exc.code}{': ' + detail if detail else ''}")
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if retry_idempotent and attempt + 1 < attempts:
                    time.sleep(1 + attempt)
                    continue
                raise RuntimeError("upload request transport outcome is unknown") from exc
        raise RuntimeError("upload request failed after retries") from last_error

    def multipart_file(
        self,
        url: str,
        fields: dict[str, str],
        field_name: str,
        file_name: str,
        data: bytes,
    ) -> dict[str, Any]:
        boundary = f"chummer-proof-{secrets.token_hex(16)}"
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                    value.encode(),
                    b"\r\n",
                ]
            )
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="{file_name}"\r\n'
                ).encode(),
                b"Content-Type: application/octet-stream\r\n\r\n",
                data,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        return self.request_json(
            "POST",
            url,
            b"".join(chunks),
            f"multipart/form-data; boundary={boundary}",
            retry_idempotent=True,
        )


def validate_sessions_url(value: str, allow_http_loopback: bool = False) -> str:
    parsed = urlsplit(value.strip())
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if (
        (parsed.scheme != "https" and not (allow_http_loopback and parsed.scheme == "http" and loopback))
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/api/internal/windows-proof/upload-sessions"
    ):
        fail("Windows proof sessions URL must be the exact HTTPS proof-session collection")
    return parsed.geturl().rstrip("/")


def resolve_session_url(sessions_url: str, candidate: Any, session_id: str, suffix: str) -> str:
    raw = str(candidate or "").strip() or f"{sessions_url}/{session_id}/{suffix}"
    resolved = urlsplit(urljoin(f"{sessions_url}/", raw))
    base = urlsplit(sessions_url)
    decoded = unquote(resolved.path)
    if (
        (resolved.scheme.lower(), (resolved.hostname or "").lower(), resolved.port)
        != (base.scheme.lower(), (base.hostname or "").lower(), base.port)
        or resolved.username is not None
        or resolved.password is not None
        or resolved.query
        or resolved.fragment
        or "\\" in resolved.path
        or any(segment in {".", ".."} for segment in decoded.split("/"))
        or decoded != f"{base.path.rstrip('/')}/{session_id}/{suffix}"
    ):
        fail("upload session response URL escaped its exact same-origin session route")
    return resolved.geturl()


def receipt_matches(receipt: dict[str, Any], bundle: ValidatedBundle, sessions_url: str) -> None:
    expected = {
        "schemaVersion": RECEIPT_SCHEMA,
        "candidateVersion": bundle.candidate_version,
        "manifestSha256": bundle.manifest_sha256,
        "inventoryDigest": bundle.inventory_digest,
        "sessionsUrl": sessions_url,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            fail(f"existing upload receipt {key} does not match this bundle")


def iter_text_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            yield from iter_text_values(key)
            yield from iter_text_values(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from iter_text_values(nested)


def ensure_receipt_contains_no_credentials(
    receipt: dict[str, Any], forbidden_values: tuple[str, ...]
) -> None:
    secrets_to_reject = tuple(value for value in forbidden_values if value)
    for text_value in iter_text_values(receipt):
        if any(secret in text_value for secret in secrets_to_reject):
            fail("upload recovery receipt contains credential material")


def transition(
    receipt_path: Path,
    receipt: dict[str, Any],
    state: str,
    *,
    forbidden_values: tuple[str, ...] = (),
    **updates: Any,
) -> None:
    candidate = dict(receipt)
    candidate.update(updates)
    candidate["state"] = state
    candidate["updatedAt"] = now_iso()
    ensure_receipt_contains_no_credentials(candidate, forbidden_values)
    atomic_json(receipt_path, candidate)
    receipt.clear()
    receipt.update(candidate)


def create_or_resume_session(
    client: ProofHttpClient,
    bundle: ValidatedBundle,
    receipt_path: Path,
    receipt: dict[str, Any],
    forbidden_values: tuple[str, ...],
) -> tuple[str, str, str, str, str]:
    session_id = str(receipt.get("sessionId") or "")
    if session_id:
        if not SESSION_PATTERN.fullmatch(session_id):
            fail("upload receipt contains an invalid sessionId")
        return (
            session_id,
            str(receipt["filesUrl"]),
            str(receipt["chunksUrl"]),
            str(receipt["completeUrl"]),
            str(receipt["reconcileUrl"]),
        )

    transition(
        receipt_path,
        receipt,
        "create_started",
        forbidden_values=forbidden_values,
    )
    response = client.request_json("POST", client.sessions_url)
    session_id = str(response.get("sessionId") or "")
    if not SESSION_PATTERN.fullmatch(session_id):
        fail("upload session response contains an invalid sessionId")
    files_url = resolve_session_url(client.sessions_url, response.get("filesUrl"), session_id, "files")
    chunks_url = resolve_session_url(client.sessions_url, response.get("chunksUrl"), session_id, "chunks")
    complete_url = resolve_session_url(client.sessions_url, response.get("completeUrl"), session_id, "complete")
    reconcile_url = resolve_session_url(client.sessions_url, response.get("reconcileUrl"), session_id, "reconcile")
    transition(
        receipt_path,
        receipt,
        "created",
        forbidden_values=forbidden_values,
        sessionId=session_id,
        filesUrl=files_url,
        chunksUrl=chunks_url,
        completeUrl=complete_url,
        reconcileUrl=reconcile_url,
        expiresAtUtc=response.get("expiresAtUtc"),
    )
    return session_id, files_url, chunks_url, complete_url, reconcile_url


def upload_file_direct(client: ProofHttpClient, url: str, path: str, source: Path) -> None:
    client.multipart_file(url, {"path": path}, "file", source.name, source.read_bytes())


def upload_file_chunked(
    client: ProofHttpClient,
    url: str,
    declared: DeclaredFile,
    chunk_bytes: int,
) -> None:
    total = math.ceil(declared.size / chunk_bytes)
    with declared.path.open("rb") as stream:
        for index in range(total):
            data = stream.read(chunk_bytes)
            if not data:
                fail("local artifact ended before its declared chunk count")
            client.multipart_file(
                url,
                {
                    "path": declared.relative_path,
                    "index": str(index),
                    "total": str(total),
                },
                "chunk",
                f"chunk-{index:04d}.bin",
                data,
            )
        if stream.read(1):
            fail("local artifact grew while it was being uploaded")


def validate_completion(result: dict[str, Any], bundle: ValidatedBundle, session_id: str) -> None:
    checks = {
        "sessionId": session_id,
        "candidateVersion": bundle.candidate_version,
        "manifestSha256": bundle.manifest_sha256,
    }
    for key, expected in checks.items():
        if result.get(key) != expected:
            fail(f"completion response {key} does not match the admitted bundle")
    generation = str(result.get("generationId") or "")
    inventory = str(result.get("inventoryDigest") or "")
    if not generation.startswith("sha256-") or not SHA256_PATTERN.fullmatch(inventory):
        fail("completion response generation or inventory digest is invalid")


def publish(args: argparse.Namespace) -> int:
    bundle = validate_bundle(args.bundle_root.absolute())
    sessions_url = validate_sessions_url(args.sessions_url, args.allow_http_loopback)
    receipt_path = (
        args.receipt.absolute()
        if args.receipt is not None
        else bundle.root.parent / f".{bundle.root.name}.upload-receipt.json"
    )
    if receipt_path == bundle.root or bundle.root in receipt_path.parents:
        fail("upload recovery receipt must live outside the immutable proof bundle")
    if args.dry_run:
        print(
            "windows_proof_upload:dry-run-ok "
            f"candidate={bundle.candidate_version} files={len(bundle.files) + 1} "
            f"bytes={sum(item.size for item in bundle.files) + len(bundle.manifest_bytes)} "
            f"manifestSha256={bundle.manifest_sha256}"
        )
        return 0

    ticket = read_ticket(args.ticket_file.absolute())
    cf_access_path = getattr(args, "cf_access_env_file", None)
    cf_access_credentials = (
        read_cf_access_env_file(cf_access_path.absolute())
        if cf_access_path is not None
        else None
    )
    if urlsplit(sessions_url).scheme == "https" and cf_access_credentials is None:
        fail("--cf-access-env-file is required for live HTTPS upload")
    forbidden_values = (ticket,)
    if cf_access_credentials is not None:
        forbidden_values += (
            cf_access_credentials.client_id,
            cf_access_credentials.client_secret,
        )

    existing: dict[str, Any] | None = None
    if receipt_path.exists():
        ensure_regular_without_links(receipt_path, "Windows proof upload recovery receipt")
        existing = parse_json_bytes(receipt_path.read_bytes(), "Windows proof upload recovery receipt")
        ensure_receipt_contains_no_credentials(existing, forbidden_values)
        receipt_matches(existing, bundle, sessions_url)
        if not args.reconcile:
            fail(f"upload receipt already exists in state {existing.get('state')}; use --reconcile, never a new upload")
    elif args.reconcile:
        fail("--reconcile requires an existing durable upload receipt")

    receipt = existing or {
        "schemaVersion": RECEIPT_SCHEMA,
        "candidateVersion": bundle.candidate_version,
        "manifestSha256": bundle.manifest_sha256,
        "inventoryDigest": bundle.inventory_digest,
        "sessionsUrl": sessions_url,
        "createdAt": now_iso(),
    }
    if existing is None:
        transition(
            receipt_path,
            receipt,
            "preflight",
            forbidden_values=forbidden_values,
        )

    client = ProofHttpClient(
        sessions_url,
        ticket,
        args.allow_http_loopback,
        cf_access_credentials,
    )
    session_id, files_url, chunks_url, complete_url, reconcile_url = create_or_resume_session(
        client,
        bundle,
        receipt_path,
        receipt,
        forbidden_values,
    )
    if receipt.get("state") not in {"request_started", "completed", "verified"}:
        transition(
            receipt_path,
            receipt,
            "uploading",
            forbidden_values=forbidden_values,
        )
        upload_file_direct(client, files_url, MANIFEST_NAME, bundle.manifest_path)
        for declared in bundle.files:
            if declared.size <= DIRECT_LIMIT_BYTES:
                upload_file_direct(client, files_url, declared.relative_path, declared.path)
            else:
                upload_file_chunked(client, chunks_url, declared, args.chunk_bytes)
        transition(
            receipt_path,
            receipt,
            "uploaded",
            forbidden_values=forbidden_values,
        )

    if receipt.get("state") in {"completed", "verified"}:
        result = receipt.get("completion")
        if not isinstance(result, dict):
            fail("completed receipt is missing its completion response")
        validate_completion(result, bundle, session_id)
        print(
            "windows_proof_upload:already-completed "
            f"candidate={bundle.candidate_version} generation={result['generationId']}"
        )
        return 0

    transition(
        receipt_path,
        receipt,
        "request_started",
        forbidden_values=forbidden_values,
    )
    endpoint = reconcile_url if args.reconcile else complete_url
    try:
        result = client.request_json("POST", endpoint)
    except RuntimeError:
        print(
            f"windows_proof_upload:completion-unknown receipt={receipt_path}; "
            "rerun only with --reconcile",
            file=sys.stderr,
        )
        raise
    validate_completion(result, bundle, session_id)
    transition(
        receipt_path,
        receipt,
        "completed",
        forbidden_values=forbidden_values,
        completion=result,
    )
    print(
        "windows_proof_upload:completed "
        f"candidate={bundle.candidate_version} generation={result['generationId']} "
        f"receipt={receipt_path}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_root", type=Path)
    parser.add_argument("--ticket-file", type=Path)
    parser.add_argument(
        "--cf-access-env-file",
        type=Path,
        help="current-owner 0600 file containing one Cloudflare Access credential pair",
    )
    parser.add_argument("--sessions-url", default=DEFAULT_SESSIONS_URL)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--allow-http-loopback", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.dry_run and args.ticket_file is None:
        parser.error("--ticket-file is required for live upload")
    if (
        not args.dry_run
        and urlsplit(args.sessions_url.strip()).scheme.lower() == "https"
        and args.cf_access_env_file is None
    ):
        parser.error("--cf-access-env-file is required for live HTTPS upload")
    if not 1024 * 1024 <= args.chunk_bytes <= 16 * 1024 * 1024:
        parser.error("--chunk-bytes must be between 1 MiB and 16 MiB")
    return args


def main() -> int:
    try:
        return publish(parse_args())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"windows_proof_upload:fail: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
