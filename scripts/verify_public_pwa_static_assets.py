#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import ipaddress
import json
import os
import re
import stat
import sys
import tempfile
import types
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    import fcntl
except ImportError:  # pragma: no cover - sealed descriptor mode is a POSIX deploy gate.
    fcntl = None  # type: ignore[assignment]


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = RUN_SERVICES_ROOT / "Chummer.Run.Api"
WWWROOT = API_ROOT / "wwwroot"
MIRROR_CONTRACT = API_ROOT / "play-pwa-mirrors.json"
CONTRACT_NAME = "chummer.public_play_install_assets.v2"
ASSET_DIGEST_INVENTORY_CONTRACT_NAME = "chummer.public_pwa_asset_digest_inventory.v1"
ASSET_DIGEST_INVENTORY_ALGORITHM = "sha256-canonical-json-v1"
MIRROR_CONTRACT_NAME = "play-install-mirror-v5"
INVENTORY_CONTRACT_NAME = "play-install-mirror-required-inventory-v2"
POLICY_ID = "chummer.public-play-pwa-mirror.v1"
EXPECTED_DEPLOYMENT_IDENTITY_CODE = "overlay_identity_bound"
MAX_TRUSTED_GENERATOR_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_RECEIPT_BYTES = 256 * 1024
MAX_TRUSTED_INPUT_MANIFEST_BYTES = 256 * 1024
MAX_JSON_INPUT_BYTES = 2 * 1024 * 1024
MAX_TEXT_INPUT_BYTES = 4 * 1024 * 1024
MAX_BINARY_INPUT_BYTES = 8 * 1024 * 1024
MAX_LIVE_JSON_BYTES = 256 * 1024
MAX_LIVE_MANIFEST_BYTES = 256 * 1024
MAX_LIVE_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_LIVE_TEXT_ASSET_BYTES = 8 * 1024 * 1024
MAX_LIVE_BINARY_ASSET_BYTES = 8 * 1024 * 1024
PUBLIC_ASSET_CACHE_CONTROL = "public, max-age=300, must-revalidate"
WORKER_CACHE_CONTROL = "no-cache, no-store, must-revalidate"
PRIVATE_CACHE_CONTROL = "private, no-store, max-age=0"
CDN_NO_STORE = "no-store, max-age=0"
INPUT_SNAPSHOT_CONTRACT = "chummer.public-pwa-proof-input-snapshot.v1"
_ACTIVE_TRUSTED_INPUT_SNAPSHOT: "TrustedInputSnapshot | None" = None
REQUIRED_INVENTORY_PATH = "Chummer.Run.Api/play-pwa-required-inventory.json"
REQUIRED_GENERATOR_DEPENDENCIES = {
    "generator_script": ("scripts/generate_public_play_worker_projection.py", "python", "text/x-python"),
    "projection_config": ("Chummer.Run.Api/play-worker-projection.json", "json", "application/json"),
    "projection_template": ("Chummer.Run.Api/service-worker.public-edge.template.js", "template", "application/javascript"),
    "required_inventory": (REQUIRED_INVENTORY_PATH, "json", "application/json"),
}
EXPECTED_ASSET_POLICY = (
    ("src/Chummer.Play.Web/wwwroot/mobile-install-shell.js", "wwwroot/mobile-install-shell.js", "exact", "install_shell", "application/javascript", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/mobile.css", "wwwroot/mobile.css", "exact", "install_styles", "text/css", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/manifest.webmanifest", "wwwroot/manifest.play.webmanifest", "exact", "base_manifest", "application/manifest+json", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/manifest.player.webmanifest", "wwwroot/manifest.player.webmanifest", "exact", "player_manifest", "application/manifest+json", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/manifest.gm.webmanifest", "wwwroot/manifest.gm.webmanifest", "exact", "gm_manifest", "application/manifest+json", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/manifest.observer.webmanifest", "wwwroot/manifest.observer.webmanifest", "exact", "observer_manifest", "application/manifest+json", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-192.png", "wwwroot/icons/icon-192.png", "exact", "icon_192_png", "image/png", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-512.png", "wwwroot/icons/icon-512.png", "exact", "icon_512_png", "image/png", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-192.svg", "wwwroot/icons/icon-192.svg", "exact", "icon_192_svg", "image/svg+xml", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/icons/icon-512.svg", "wwwroot/icons/icon-512.svg", "exact", "icon_512_svg", "image/svg+xml", "public, max-age=300, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/mobile/service-worker.js", "wwwroot/mobile/service-worker.js", "exact", "scoped_worker", "application/javascript", "no-cache, no-store, must-revalidate"),
    ("src/Chummer.Play.Web/wwwroot/service-worker.js", "wwwroot/service-worker.js", "transform", "root_worker", "application/javascript", "no-cache, no-store, must-revalidate"),
)
EXPECTED_DEPENDENCY_POLICY = tuple(
    (path, kind, role, content_type)
    for role, (path, kind, content_type) in REQUIRED_GENERATOR_DEPENDENCIES.items()
)
CONTENT_TYPES_BY_SUFFIX = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json",
}
EXPECTED_DESCRIPTION = (
    "Installable public Chummer Play shell. A signed-in identity and trusted table invitation are required for live sessions."
)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 "
    "ChummerPwaStaticAssetProof/2.0"
)

MANIFESTS = {
    "/manifest.webmanifest": {
        "id": "/mobile",
        "name": "Chummer Turn Companion",
        "short_name": "Chummer Play",
        "start_url": "/mobile/player",
        "shortcuts": {"/mobile/player", "/mobile/gm", "/mobile/observer"},
    },
    "/manifest.play.webmanifest": {
        "id": "/mobile",
        "name": "Chummer Turn Companion",
        "short_name": "Chummer Play",
        "start_url": "/mobile/player",
        "shortcuts": {"/mobile/player", "/mobile/gm", "/mobile/observer"},
    },
    "/manifest.player.webmanifest": {
        "id": "/mobile/player",
        "name": "Chummer Player Companion",
        "short_name": "Chummer Player",
        "start_url": "/mobile/player",
        "shortcuts": {"/mobile/player", "/mobile/gm"},
    },
    "/manifest.gm.webmanifest": {
        "id": "/mobile/gm",
        "name": "Chummer GM Companion",
        "short_name": "Chummer GM",
        "start_url": "/mobile/gm",
        "shortcuts": {"/mobile/gm", "/mobile/player"},
    },
    "/manifest.observer.webmanifest": {
        "id": "/mobile/observer",
        "name": "Chummer Observer Companion",
        "short_name": "Chummer Observer",
        "start_url": "/mobile/observer",
        "shortcuts": {"/mobile/observer", "/mobile/player"},
    },
}

LOCAL_ASSETS = {
    "/js/mobile-app-handoff.js": "javascript",
    "/mobile.css": "text/css",
    "/mobile-install-shell.js": "javascript",
    "/service-worker.js": "javascript",
    "/mobile/service-worker.js": "javascript",
    "/icons/icon-192.png": "image/png",
    "/icons/icon-512.png": "image/png",
    "/icons/icon-192.svg": "image/svg+xml",
    "/icons/icon-512.svg": "image/svg+xml",
    **{path: "manifest" for path in MANIFESTS},
}

LIVE_BOUND_ASSET_POLICY = (
    ("/js/mobile-app-handoff.js", "application/javascript", PUBLIC_ASSET_CACHE_CONTROL, False),
    ("/manifest.webmanifest", "application/manifest+json", PUBLIC_ASSET_CACHE_CONTROL, False),
    ("/mobile-install-shell.js", "application/javascript", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/mobile.css", "text/css", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/manifest.play.webmanifest", "application/manifest+json", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/manifest.player.webmanifest", "application/manifest+json", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/manifest.gm.webmanifest", "application/manifest+json", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/manifest.observer.webmanifest", "application/manifest+json", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/icons/icon-192.png", "image/png", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/icons/icon-512.png", "image/png", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/icons/icon-192.svg", "image/svg+xml", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/icons/icon-512.svg", "image/svg+xml", PUBLIC_ASSET_CACHE_CONTROL, True),
    ("/service-worker.js", "application/javascript", WORKER_CACHE_CONTROL, True),
    ("/mobile/service-worker.js", "application/javascript", WORKER_CACHE_CONTROL, True),
)

ROLE_DOCUMENTS = {
    "/mobile/player": ("player", "/manifest.player.webmanifest", "Chummer Player", "Keep your runner ready at the table.", "Runner readiness", "/mobile/player"),
    "/mobile/gm": ("gm", "/manifest.gm.webmanifest", "Chummer GM", "Stage the table without exposing Game Master controls.", "Scene pacing", "/mobile/gm"),
    "/mobile/observer": ("observer", "/manifest.observer.webmanifest", "Chummer Observer", "Follow the table without gaining control.", "Read-mostly return", "/mobile/observer"),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalized_media_type(value: object) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def asset_digest_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    canonical_rows = sorted(rows, key=lambda item: str(item.get("path") or ""))
    canonical = {
        "contractName": ASSET_DIGEST_INVENTORY_CONTRACT_NAME,
        "algorithm": ASSET_DIGEST_INVENTORY_ALGORITHM,
        "assets": canonical_rows,
    }
    digest = sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    return {
        **canonical,
        "assetCount": len(canonical_rows),
        "sha256": digest,
    }


def source_asset_digest_inventory(
    root: Path,
    failures: list[str],
) -> dict[str, Any]:
    root = lexical_path(root)
    api_root = root / "Chummer.Run.Api"
    rows: list[dict[str, Any]] = []
    mirror_bound_count = 0
    for path, content_type, cache_control, mirror_bound in LIVE_BOUND_ASSET_POLICY:
        relative_path = f"wwwroot/{path.lstrip('/')}"
        try:
            payload = read_regular_file_no_symlinks(
                api_root / relative_path,
                root=api_root,
                label=f"PWA asset digest inventory entry {path}",
                max_bytes=input_size_limit("run-services", f"Chummer.Run.Api/{relative_path}"),
            )
        except RuntimeError as exc:
            failures.append(f"asset inventory: {path} is unreadable: {exc}")
            payload = b""
        rows.append(
            {
                "path": path,
                "contentType": content_type,
                "cacheControl": cache_control,
                "mirrorBound": mirror_bound,
                "sha256": sha256(payload),
                "sizeBytes": len(payload),
            }
        )
        mirror_bound_count += int(mirror_bound)
    require(
        mirror_bound_count == len(EXPECTED_ASSET_POLICY) == 12,
        failures,
        "asset inventory: exactly 12 projected mirror assets must be bound",
    )
    require(
        len(rows) == len(LIVE_BOUND_ASSET_POLICY) == 14,
        failures,
        "asset inventory: exact live asset inventory must contain 14 assets",
    )
    return asset_digest_inventory(rows)


def verify_live_bound_asset(
    path: str,
    status: int,
    headers: dict[str, str],
    payload: bytes,
    expected: dict[str, Any],
    failures: list[str],
) -> dict[str, Any]:
    actual_media_type = normalized_media_type(headers.get("content-type"))
    actual_digest = sha256(payload)
    require(status == 200, failures, f"{path}: expected 200, got {status}")
    require(bool(payload), failures, f"{path}: empty response")
    require(
        actual_media_type == expected.get("contentType"),
        failures,
        f"{path}: live MIME differs from the preflight source inventory",
    )
    require(
        actual_digest == expected.get("sha256"),
        failures,
        f"{path}: live digest differs from the preflight source inventory",
    )
    require(
        len(payload) == expected.get("sizeBytes"),
        failures,
        f"{path}: live byte length differs from the preflight source inventory",
    )
    require(
        headers.get("x-content-type-options", "").strip().lower() == "nosniff",
        failures,
        f"{path}: X-Content-Type-Options must be exactly nosniff",
    )
    require(
        headers.get("cache-control", "").strip().lower()
        == str(expected.get("cacheControl") or "").strip().lower(),
        failures,
        f"{path}: Cache-Control differs from the sealed source inventory",
    )
    expected_is_bound = expected.get("mirrorBound") in {True, False}
    return {
        "path": path,
        "contentType": actual_media_type,
        "cacheControl": headers.get("cache-control", "").strip(),
        "nosniff": headers.get("x-content-type-options", "").strip().lower() == "nosniff",
        "mirrorBound": expected.get("mirrorBound") is True,
        "sha256": actual_digest,
        "sizeBytes": len(payload),
        "matchesExpected": expected_is_bound
        and status == 200
        and bool(payload)
        and actual_media_type == expected.get("contentType")
        and actual_digest == expected.get("sha256")
        and len(payload) == expected.get("sizeBytes")
        and headers.get("x-content-type-options", "").strip().lower() == "nosniff"
        and headers.get("cache-control", "").strip().lower()
        == str(expected.get("cacheControl") or "").strip().lower(),
    }


def strict_json_loads(payload: bytes | str, *, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
        return json.loads(text, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict JSON: {exc}") from exc


def lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def open_directory_no_symlinks(path: Path, *, label: str) -> int:
    absolute = lexical_path(path)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except (OSError, TypeError) as exc:
        os.close(descriptor)
        raise RuntimeError(f"{label} contains a symlink or non-directory component: {absolute}: {exc}") from exc


def require_directory_no_symlinks(path: Path, *, label: str) -> Path:
    absolute = lexical_path(path)
    descriptor = open_directory_no_symlinks(absolute, label=label)
    os.close(descriptor)
    return absolute


def read_regular_file_no_symlinks(path: Path, *, root: Path, label: str, max_bytes: int | None = None) -> bytes:
    absolute_root = lexical_path(root)
    absolute_path = lexical_path(path)
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as exc:
        raise RuntimeError(f"{label} escapes its declared root: {absolute_path}") from exc
    if not relative.parts:
        raise RuntimeError(f"{label} must name a file below its declared root")
    if _ACTIVE_TRUSTED_INPUT_SNAPSHOT is not None:
        payload = _ACTIVE_TRUSTED_INPUT_SNAPSHOT.read(absolute_path, label=label)
        if payload is not None:
            effective_limit = max_bytes if max_bytes is not None else MAX_BINARY_INPUT_BYTES
            if len(payload) > effective_limit:
                raise RuntimeError(f"{label} exceeds its maximum size")
            return payload

    absolute_root = require_directory_no_symlinks(absolute_root, label=f"{label} root")

    directory_descriptor = open_directory_no_symlinks(absolute_root, label=f"{label} root")
    try:
        for component in relative.parts[:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        file_descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_descriptor,
        )
        try:
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise RuntimeError(f"{label} is not a regular file: {absolute_path}")
            if max_bytes is not None and before.st_size > max_bytes:
                raise RuntimeError(f"{label} exceeds its maximum size")
            chunks: list[bytes] = []
            byte_count = 0
            effective_limit = max_bytes if max_bytes is not None else MAX_BINARY_INPUT_BYTES
            while True:
                chunk = os.read(file_descriptor, min(1024 * 1024, effective_limit + 1 - byte_count))
                if not chunk:
                    break
                chunks.append(chunk)
                byte_count += len(chunk)
                if byte_count > effective_limit:
                    raise RuntimeError(f"{label} exceeds its maximum size")
            after = os.fstat(file_descriptor)
            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            after_identity = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if before_identity != after_identity or byte_count != before.st_size:
                raise RuntimeError(f"{label} changed while it was read")
            return b"".join(chunks)
        finally:
            os.close(file_descriptor)
    except (OSError, TypeError) as exc:
        raise RuntimeError(f"{label} contains a symlink or unreadable component: {absolute_path}: {exc}") from exc
    finally:
        os.close(directory_descriptor)


def read_sealed_inherited_payload(
    descriptor: int,
    expected_sha256: str,
    *,
    label: str,
    max_bytes: int,
) -> bytes:
    if descriptor < 0:
        raise RuntimeError(f"{label} descriptor is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise RuntimeError(f"{label} expected digest is invalid")
    if fcntl is None:
        raise RuntimeError(f"{label} sealing support is unavailable")
    required_names = (
        "F_GET_SEALS",
        "F_SEAL_SEAL",
        "F_SEAL_SHRINK",
        "F_SEAL_GROW",
        "F_SEAL_WRITE",
    )
    if any(not hasattr(fcntl, name) for name in required_names):
        raise RuntimeError(f"{label} sealing support is unavailable")
    required_seals = int(
        fcntl.F_SEAL_SEAL
        | fcntl.F_SEAL_SHRINK
        | fcntl.F_SEAL_GROW
        | fcntl.F_SEAL_WRITE
    )
    try:
        metadata = os.fstat(descriptor)
        actual_seals = int(fcntl.fcntl(descriptor, fcntl.F_GET_SEALS))
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"{label} descriptor is not a regular file")
        if metadata.st_size > max_bytes:
            raise RuntimeError(f"{label} exceeds its maximum size")
        if actual_seals & required_seals != required_seals:
            raise RuntimeError(f"{label} descriptor is not fully sealed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        byte_count = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - byte_count))
            if not chunk:
                break
            chunks.append(chunk)
            byte_count += len(chunk)
            if byte_count > max_bytes:
                raise RuntimeError(f"{label} exceeds its maximum size")
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise RuntimeError(f"{label} descriptor is unreadable") from exc
    if len(payload) > max_bytes or len(payload) != metadata.st_size:
        raise RuntimeError(f"{label} exceeds its maximum size")
    if (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise RuntimeError(f"{label} changed while it was read")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RuntimeError(f"{label} digest does not match the sealed authority")
    os.lseek(descriptor, 0, os.SEEK_SET)
    return payload


def write_receipt_descriptor(descriptor: int, payload: bytes) -> None:
    if descriptor < 0:
        raise RuntimeError("output receipt descriptor is invalid")
    if len(payload) > MAX_OUTPUT_RECEIPT_BYTES:
        raise RuntimeError("output receipt exceeds its size limit")
    try:
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("output receipt descriptor write did not make progress")
            offset += written
        os.fsync(descriptor)
    except OSError as exc:
        raise RuntimeError("output receipt descriptor is unwritable") from exc


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def quoted_array(source: str, name: str) -> set[str]:
    match = re.search(rf"const\s+{re.escape(name)}\s*=\s*\[(.*?)\];", source, re.DOTALL)
    return set(re.findall(r'"([^"]+)"', match.group(1))) if match else set()


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def validate_clean_origin(value: str) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if (
        not raw
        or parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or any(ord(character) < 0x20 for character in raw)
    ):
        raise RuntimeError("base origin must be a clean query-free HTTP(S) origin")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("base origin has an invalid port") from exc
    hostname = parsed.hostname.lower()
    is_loopback = hostname == "localhost"
    try:
        is_loopback = is_loopback or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme.lower() == "http" and not is_loopback:
        raise RuntimeError("base origin must use HTTPS unless it is loopback")
    if not is_loopback and port not in {None, 443}:
        raise RuntimeError("public base origin must use the default HTTPS port")
    host = f"[{hostname}]" if ":" in hostname else hostname
    include_port = port is not None and not (
        parsed.scheme.lower() == "https" and port == 443
    )
    return f"{parsed.scheme.lower()}://{host}{f':{port}' if include_port else ''}"


def validate_clean_probe_path(value: str) -> str:
    raw = str(value or "")
    parsed = urlsplit(raw)
    if (
        not raw.startswith("/")
        or raw.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "\\" in raw
        or unquote(raw) != raw
        or any(ord(character) < 0x20 for character in raw)
    ):
        raise RuntimeError("probe path must be an absolute, query-free local path")
    return raw


def live_read_limit(path: str) -> int:
    if path == "/api/ready":
        return MAX_LIVE_JSON_BYTES
    if path.endswith(".webmanifest"):
        return MAX_LIVE_MANIFEST_BYTES
    if path in ROLE_DOCUMENTS or path == "/mobile/player":
        return MAX_LIVE_DOCUMENT_BYTES
    if path.endswith((".js", ".css", ".svg")):
        return MAX_LIVE_TEXT_ASSET_BYTES
    return MAX_LIVE_BINARY_ASSET_BYTES


def read_bounded_http_body(response: Any, *, path: str, limit: int) -> bytes:
    raw_length = str(response.headers.get("Content-Length") or "").strip()
    if raw_length:
        if not raw_length.isdigit() or int(raw_length) > limit:
            raise RuntimeError(f"{path}: response exceeds its byte limit")
    chunks: list[bytes] = []
    byte_count = 0
    while True:
        chunk = response.read(min(64 * 1024, limit + 1 - byte_count))
        if not chunk:
            break
        chunks.append(chunk)
        byte_count += len(chunk)
        if byte_count > limit:
            raise RuntimeError(f"{path}: response exceeds its byte limit")
    return b"".join(chunks)


def fetch(base_url: str, path: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    origin = validate_clean_origin(base_url)
    clean_path = validate_clean_probe_path(path)
    request = Request(
        origin + clean_path,
        headers={"User-Agent": BROWSER_USER_AGENT},
    )
    opener = build_opener(NoRedirectHandler())
    limit = live_read_limit(clean_path)
    try:
        with opener.open(request, timeout=timeout) as response:
            return (
                int(response.status),
                {key.lower(): value for key, value in response.headers.items()},
                read_bounded_http_body(response, path=clean_path, limit=limit),
            )
    except HTTPError as error:
        return (
            int(error.code),
            {key.lower(): value for key, value in error.headers.items()},
            read_bounded_http_body(error, path=clean_path, limit=limit),
        )
    except URLError as error:
        raise RuntimeError(f"{clean_path}: network request failed") from error


def verify_clean_mobile_player_shell(
    base_url: str,
    timeout_seconds: float,
    failures: list[str],
) -> dict[str, Any]:
    path = "/mobile/player"
    status, headers, payload = fetch(base_url, path, timeout_seconds)
    markup = payload.decode("utf-8", errors="replace")
    clean_final_route = status == 200
    require(status == 200, failures, f"{path}: signed-out shell expected 200, got {status}")
    require(
        normalized_media_type(headers.get("content-type")) == "text/html",
        failures,
        f"{path}: signed-out shell MIME must be text/html",
    )
    require(clean_final_route, failures, f"{path}: redirect or non-200 response rejected")
    require('data-play-surface="install-only"' in markup, failures, f"{path}: signed-out shell is not install-only")
    require('data-live-session="unavailable"' in markup, failures, f"{path}: signed-out shell exposes live-session authority")
    require('data-authority="none"' in markup, failures, f"{path}: signed-out shell does not declare no authority")
    private_key_findings = private_identity_key_findings(markup)
    require(
        not private_key_findings,
        failures,
        f"{path}: signed-out shell contains private identity keys ({', '.join(private_key_findings)})",
    )
    return {
        "path": path,
        "status": status,
        "contentType": normalized_media_type(headers.get("content-type")),
        "finalPath": path if clean_final_route else "",
        "redirectRejected": status != 200,
        "queryFree": True,
        "cleanFinalRoute": clean_final_route,
        "installOnly": 'data-play-surface="install-only"' in markup,
        "liveSessionUnavailable": 'data-live-session="unavailable"' in markup,
        "authorityNone": 'data-authority="none"' in markup,
        "privateIdentityAbsent": not private_key_findings,
        "privateIdentityKeyFindings": private_key_findings,
    }


PRIVATE_IDENTITY_KEYS = {
    "session",
    "sessionid",
    "device",
    "deviceid",
    "access",
    "accesstoken",
    "artifactaccess",
    "invite",
    "invitecode",
    "token",
    "authorization",
    "authority",
}


def decoded_identity_text(value: str) -> str:
    decoded = value
    for _ in range(4):
        expanded = html.unescape(unquote(decoded))
        expanded = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda match: chr(int(match.group(1), 16)),
            expanded,
        )
        expanded = expanded.replace('\\"', '"').replace("\\'", "'")
        if expanded == decoded:
            break
        decoded = expanded
    return decoded


def normalized_identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", decoded_identity_text(value).lower())


def private_identity_key(value: str) -> tuple[str, bool]:
    normalized = normalized_identity_key(value)
    if normalized.startswith("data") and normalized[4:] in PRIVATE_IDENTITY_KEYS:
        return normalized[4:], True
    return normalized, False


def private_identity_key_findings(markup: str) -> list[str]:
    decoded = decoded_identity_text(markup)
    findings: set[str] = set()

    def record(raw_key: str) -> None:
        key, _ = private_identity_key(raw_key)
        if key in PRIVATE_IDENTITY_KEYS:
            findings.add(key)

    assignment = re.compile(
        r"(?P<keyquote>['\"]?)(?P<key>[A-Za-z][A-Za-z0-9_-]{0,63})(?P=keyquote)\s*(?:=|:)\s*"
        r"(?P<quote>['\"]?)(?P<value>[^'\"\s&<>;,}]*)",
        re.IGNORECASE,
    )
    for match in assignment.finditer(decoded):
        raw_key = match.group("key")
        key, is_data_attribute = private_identity_key(raw_key)
        if key not in PRIVATE_IDENTITY_KEYS:
            continue
        value = normalized_identity_key(match.group("value"))
        fixed_no_authority_marker = (
            key == "authority"
            and value == "none"
            and is_data_attribute
            and raw_key.lower() == "data-authority"
        )
        if not fixed_no_authority_marker:
            findings.add(key)

    # Quoted sensitive key literals cover bracket access, header/query setters,
    # computed properties, and keys stored for later use. Exact-key matching
    # avoids treating ordinary prose such as "session setup" as identity data.
    quoted_key = re.compile(
        r"(?P<quote>['\"])(?P<key>[A-Za-z][A-Za-z0-9_-]{0,63})(?P=quote)",
        re.IGNORECASE,
    )
    for match in quoted_key.finditer(decoded):
        record(match.group("key"))

    # Cover unquoted computed access and setter arguments as well. Quoted forms
    # are already closed by the literal scan above.
    bare_bracket_or_setter_key = re.compile(
        r"(?:\[\s*|\b(?:append|delete|get|has|set|setAttribute|setRequestHeader)\s*\(\s*)"
        r"(?P<key>[A-Za-z][A-Za-z0-9_-]{0,63})(?=\s*(?:\]|[,)]))",
        re.IGNORECASE,
    )
    for match in bare_bracket_or_setter_key.finditer(decoded):
        record(match.group("key"))

    dotted_key = re.compile(
        r"(?:\.|\?\.)\s*(?P<key>[A-Za-z][A-Za-z0-9_-]{0,63})\b",
        re.IGNORECASE,
    )
    for match in dotted_key.finditer(decoded):
        record(match.group("key"))

    data_attribute = re.compile(
        r"\bdata-(?P<key>[A-Za-z][A-Za-z0-9_-]{0,63})\b",
        re.IGNORECASE,
    )
    for match in data_attribute.finditer(decoded):
        if (
            normalized_identity_key(match.group("key")) == "authority"
            and re.match(
                r"\s*=\s*(['\"])none\1",
                decoded[match.end():],
                re.IGNORECASE,
            )
        ):
            continue
        record(match.group("key"))

    destructuring = re.compile(r"\{(?P<body>[^{}\r\n]{1,1024})\}\s*=", re.IGNORECASE)
    destructured_identifier = re.compile(r"\b[A-Za-z][A-Za-z0-9_-]{0,63}\b")
    for destructuring_match in destructuring.finditer(decoded):
        for identifier in destructured_identifier.finditer(
            destructuring_match.group("body")
        ):
            record(identifier.group(0))
    return sorted(findings)


def require_private_response_headers(
    path: str,
    headers: dict[str, str],
    failures: list[str],
) -> None:
    require(
        headers.get("cache-control", "").strip().lower()
        == PRIVATE_CACHE_CONTROL,
        failures,
        f"{path}: Cache-Control must be exactly {PRIVATE_CACHE_CONTROL}",
    )
    for name in ("cdn-cache-control", "cloudflare-cdn-cache-control"):
        require(
            headers.get(name, "").strip().lower() == CDN_NO_STORE,
            failures,
            f"{path}: {name} must be exactly {CDN_NO_STORE}",
        )
    require(
        headers.get("surrogate-control", "").strip().lower() == "no-store",
        failures,
        f"{path}: Surrogate-Control must be exactly no-store",
    )
    require(
        headers.get("x-content-type-options", "").strip().lower() == "nosniff",
        failures,
        f"{path}: X-Content-Type-Options must be exactly nosniff",
    )


def verify_manifest(path: str, payload: bytes, failures: list[str]) -> dict[str, Any]:
    try:
        manifest = strict_json_loads(payload, label=path)
    except RuntimeError as error:
        failures.append(f"{path}: invalid manifest: {error}")
        return {"path": path, "valid": False}
    if not isinstance(manifest, dict):
        failures.append(f"{path}: manifest must be a JSON object")
        return {"path": path, "valid": False}

    expected = MANIFESTS[path]
    shortcuts = {
        str(item.get("url") or "")
        for item in manifest.get("shortcuts", [])
        if isinstance(item, dict)
    }
    icons = {
        str(item.get("src") or "")
        for item in manifest.get("icons", [])
        if isinstance(item, dict)
    }
    require(manifest.get("id") == expected["id"], failures, f"{path}: wrong id")
    require(manifest.get("name") == expected["name"], failures, f"{path}: wrong name")
    require(manifest.get("short_name") == expected["short_name"], failures, f"{path}: wrong short_name")
    require(manifest.get("start_url") == expected["start_url"], failures, f"{path}: wrong start_url")
    require("?" not in str(manifest.get("start_url") or ""), failures, f"{path}: start_url must be query-free")
    require(manifest.get("scope") == "/mobile/", failures, f"{path}: scope must be /mobile/")
    require(manifest.get("display") == "standalone", failures, f"{path}: display must be standalone")
    require(expected["shortcuts"] <= shortcuts, failures, f"{path}: role shortcuts drifted")
    require(
        {"/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon-192.svg", "/icons/icon-512.svg"} <= icons,
        failures,
        f"{path}: complete local icon set missing",
    )
    if path == "/manifest.play.webmanifest":
        require(manifest.get("description") == EXPECTED_DESCRIPTION, failures, f"{path}: public boundary description drifted")
    return {
        "path": path,
        "valid": True,
        "id": manifest.get("id"),
        "startUrl": manifest.get("start_url"),
        "display": manifest.get("display"),
        "shortcutCount": len(shortcuts),
        "iconCount": len(icons),
    }


def verify_worker(payload: bytes, failures: list[str]) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="replace")
    critical = quoted_array(text, "CRITICAL_SHELL_ASSETS")
    require('const CACHE_VERSION = "v19";' in text, failures, "worker: cache version must be v19")
    require(
        'const CACHE_CONTRACT = "run-api-projection-v2";' in text,
        failures,
        "worker: projection cache contract must be v2",
    )
    require("self.skipWaiting()" not in text, failures, "worker: activation must not force skipWaiting")
    require("self.clients.claim()" not in text, failures, "worker: activation must not force clients.claim")
    require("/manifest.play.webmanifest" in critical, failures, "worker: Play base manifest is not critical")
    for path in (
        "/mobile-install-shell.js",
        "/manifest.player.webmanifest",
        "/manifest.gm.webmanifest",
        "/manifest.observer.webmanifest",
        "/icons/icon-192.svg",
        "/icons/icon-512.svg",
    ):
        require(path in critical, failures, f"worker: missing critical local asset {path}")
    require("/mobile-turn-companion.js" not in text, failures, "worker: private companion script is public-edge cacheable")
    require("isExpectedPublicAssetResponse" in text, failures, "worker: response media-type validation missing")
    require("Promise.allSettled" not in text, failures, "worker: critical precache must be atomic")
    require('url.pathname.startsWith("/api/play/")' in text, failures, "worker: private API network-only boundary missing")
    return {
        "cacheVersion": "v19" if 'const CACHE_VERSION = "v19";' in text else "",
        "cacheContract": "run-api-projection-v2" if 'const CACHE_CONTRACT = "run-api-projection-v2";' in text else "",
        "passiveActivation": "self.skipWaiting()" not in text and "self.clients.claim()" not in text,
        "criticalAssets": sorted(critical),
        "privateApiNetworkOnly": 'url.pathname.startsWith("/api/play/")' in text,
    }


def normalized_relative_path(value: object) -> str | None:
    raw = str(value or "").strip()
    normalized = str(PurePosixPath(raw)) if raw else ""
    if (
        not raw
        or raw != normalized
        or raw.startswith("/")
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in PurePosixPath(raw).parts)
    ):
        return None
    return raw


def input_size_limit(root_name: str, relative_path: str) -> int:
    if root_name not in {"run-services", "play"}:
        raise RuntimeError("snapshot input root role is unsupported")
    if relative_path in {
        "scripts/verify_public_pwa_static_assets.py",
        "scripts/generate_public_play_worker_projection.py",
        "scripts/validate_public_pwa_proof_authority.py",
    }:
        return MAX_TRUSTED_GENERATOR_BYTES
    suffix = PurePosixPath(relative_path).suffix.lower()
    if suffix in {".json", ".webmanifest"}:
        return MAX_JSON_INPUT_BYTES
    if suffix == ".png":
        return MAX_BINARY_INPUT_BYTES
    return MAX_TEXT_INPUT_BYTES


class TrustedInputSnapshot:
    def __init__(
        self,
        *,
        run_root: Path,
        manifest_sha256: str,
        rows: list[dict[str, Any]],
        payloads: dict[tuple[str, str], bytes],
    ) -> None:
        self.run_root = lexical_path(run_root)
        self.play_root = lexical_path(self.run_root.parent / "chummer-play")
        self.manifest_sha256 = manifest_sha256
        self.rows = rows
        self.payloads = payloads

    def read(self, path: Path, *, label: str) -> bytes | None:
        absolute = lexical_path(path)
        for root_name, root in (
            ("run-services", self.run_root),
            ("play", self.play_root),
        ):
            try:
                relative = absolute.relative_to(root).as_posix()
            except ValueError:
                continue
            key = (root_name, relative)
            if key not in self.payloads:
                raise RuntimeError(
                    f"{label} is outside the closed trusted input snapshot: "
                    f"{root_name}:{relative}"
                )
            return self.payloads[key]
        return None

    def receipt(self) -> dict[str, Any]:
        checked = [
            {
                key: row[key]
                for key in (
                    "root",
                    "path",
                    "sha256",
                    "byteLength",
                    "fileIdentity",
                    "directoryTrace",
                )
            }
            for row in self.rows
        ]
        return {
            "status": "pass",
            "contractName": INPUT_SNAPSHOT_CONTRACT,
            "sha256": self.manifest_sha256,
            "checkedCount": len(checked),
            "checked": checked,
            "stable": True,
            "authorityMode": "sealed_inherited_file_descriptors",
        }


def load_trusted_input_snapshot(
    run_root: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    *,
    reserved_descriptors: set[int],
) -> TrustedInputSnapshot:
    if set(manifest) != {"contractName", "roots", "files"}:
        raise RuntimeError("trusted input manifest fields drifted from the closed contract")
    if manifest.get("contractName") != INPUT_SNAPSHOT_CONTRACT:
        raise RuntimeError("trusted input manifest contract is unsupported")
    rows_value = manifest.get("files")
    roots_value = manifest.get("roots")
    if not isinstance(roots_value, list) or len(roots_value) != 2:
        raise RuntimeError("trusted input manifest roots are invalid")
    expected_root_paths = {
        "run-services": str(lexical_path(run_root)),
        "play": str(lexical_path(run_root).parent / "chummer-play"),
    }
    root_roles: set[str] = set()
    for root_index, root_row in enumerate(roots_value):
        if (
            not isinstance(root_row, dict)
            or set(root_row) != {"role", "path", "identity", "pathTrace"}
        ):
            raise RuntimeError(f"trusted input root row {root_index} fields are invalid")
        role = str(root_row.get("role") or "")
        if role in root_roles or root_row.get("path") != expected_root_paths.get(role):
            raise RuntimeError(f"trusted input root row {root_index} path is invalid")
        identity = root_row.get("identity")
        path_trace = root_row.get("pathTrace")
        if (
            not isinstance(identity, list)
            or len(identity) != 7
            or any(not isinstance(value, int) for value in identity)
            or not isinstance(path_trace, list)
            or not path_trace
        ):
            raise RuntimeError(f"trusted input root row {root_index} identity is invalid")
        for trace_index, trace in enumerate(path_trace):
            if (
                not isinstance(trace, dict)
                or set(trace) != {"path", "identity"}
                or not isinstance(trace.get("path"), str)
                or not isinstance(trace.get("identity"), list)
                or len(trace["identity"]) != 7
                or any(not isinstance(value, int) for value in trace["identity"])
            ):
                raise RuntimeError(
                    f"trusted input root row {root_index} path trace {trace_index} is invalid"
                )
        root_roles.add(role)
    if root_roles != set(expected_root_paths):
        raise RuntimeError("trusted input manifest root roles drifted")
    if not isinstance(rows_value, list):
        raise RuntimeError("trusted input manifest files must be an array")
    expected = expected_input_snapshot_paths()
    if len(rows_value) != len(expected):
        raise RuntimeError("trusted input manifest exact input count drifted")
    payloads: dict[tuple[str, str], bytes] = {}
    rows: list[dict[str, Any]] = []
    descriptors: set[int] = set()
    actual: list[tuple[str, str]] = []
    for index, row in enumerate(rows_value):
        expected_fields = {
            "root",
            "path",
            "descriptor",
            "sha256",
            "byteLength",
            "fileIdentity",
            "directoryTrace",
        }
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise RuntimeError(f"trusted input row {index} fields are invalid")
        root_name = str(row.get("root") or "")
        relative_path = normalized_relative_path(row.get("path"))
        descriptor = row.get("descriptor")
        digest = str(row.get("sha256") or "").lower()
        byte_length = row.get("byteLength")
        file_identity = row.get("fileIdentity")
        directory_trace = row.get("directoryTrace")
        if root_name not in {"run-services", "play"} or relative_path is None:
            raise RuntimeError(f"trusted input row {index} root/path is invalid")
        key = (root_name, relative_path)
        if key in payloads:
            raise RuntimeError(f"trusted input row {index} is duplicated")
        if (
            not isinstance(descriptor, int)
            or descriptor < 0
            or descriptor in descriptors
            or descriptor in reserved_descriptors
        ):
            raise RuntimeError(f"trusted input row {index} descriptor is invalid")
        if (
            re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(byte_length, int)
            or byte_length < 0
            or byte_length > input_size_limit(root_name, relative_path)
        ):
            raise RuntimeError(f"trusted input row {index} identity is invalid")
        if (
            not isinstance(file_identity, list)
            or len(file_identity) != 7
            or any(not isinstance(value, int) for value in file_identity)
        ):
            raise RuntimeError(f"trusted input row {index} file identity is invalid")
        if not isinstance(directory_trace, list) or not directory_trace:
            raise RuntimeError(f"trusted input row {index} directory trace is invalid")
        for trace_index, trace in enumerate(directory_trace):
            if (
                not isinstance(trace, dict)
                or set(trace) != {"path", "identity"}
                or not isinstance(trace.get("path"), str)
                or not isinstance(trace.get("identity"), list)
                or len(trace["identity"]) != 7
                or any(not isinstance(value, int) for value in trace["identity"])
            ):
                raise RuntimeError(
                    f"trusted input row {index} directory trace {trace_index} is invalid"
                )
        payload = read_sealed_inherited_payload(
            descriptor,
            digest,
            label=f"trusted input {root_name}:{relative_path}",
            max_bytes=input_size_limit(root_name, relative_path),
        )
        if len(payload) != byte_length:
            raise RuntimeError(f"trusted input row {index} byte length drifted")
        descriptors.add(descriptor)
        actual.append(key)
        payloads[key] = payload
        rows.append(dict(row))
    if set(actual) != expected or len(actual) != len(expected):
        raise RuntimeError("trusted input manifest exact input path set drifted")
    return TrustedInputSnapshot(
        run_root=run_root,
        manifest_sha256=manifest_sha256,
        rows=rows,
        payloads=payloads,
    )


def expected_input_snapshot_paths() -> set[tuple[str, str]]:
    run_paths = {
        "scripts/verify_public_pwa_static_assets.py",
        "scripts/generate_public_play_worker_projection.py",
        "Chummer.Run.Api/public-pwa-proof-authority.json",
        "Chummer.Run.Api/Dockerfile",
        "scripts/validate_public_pwa_proof_authority.py",
        "Chummer.Run.Api/play-pwa-required-inventory.json",
        "Chummer.Run.Api/play-pwa-mirrors.json",
        "Chummer.Run.Api/play-worker-projection.json",
        "Chummer.Run.Api/service-worker.public-edge.template.js",
        "Chummer.Run.Api/Services/PublicPlayProxyGateway.cs",
        "docker-compose.public-edge.yml",
        "Chummer.Run.Api/wwwroot/js/mobile-app-handoff.js",
        "Chummer.Run.Api/wwwroot/manifest.webmanifest",
    }
    run_paths.update(f"Chummer.Run.Api/{projection}" for _, projection, *_ in EXPECTED_ASSET_POLICY)
    run_paths.update(path for path, *_ in EXPECTED_DEPENDENCY_POLICY)
    play_paths = {source for source, *_ in EXPECTED_ASSET_POLICY}
    return {("run-services", path) for path in run_paths} | {
        ("play", path) for path in play_paths
    }


def validate_input_snapshot(
    root: Path,
    snapshot: TrustedInputSnapshot | None,
    failures: list[str],
) -> dict[str, Any]:
    if snapshot is None:
        return {
            "status": "not_requested",
            "contractName": "",
            "sha256": "",
            "checkedCount": 0,
            "checked": [],
        }
    if snapshot.run_root != lexical_path(root):
        failures.append("snapshot: run-services root binding drifted")
        return {**snapshot.receipt(), "status": "fail"}
    return snapshot.receipt()


def inventory_rows(
    inventory: dict[str, Any],
    failures: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    require(
        inventory.get("contract") == INVENTORY_CONTRACT_NAME,
        failures,
        "mirror: required inventory contract must be v2",
    )
    require(
        inventory.get("policyId") == POLICY_ID,
        failures,
        "mirror: required inventory policy identity drifted",
    )
    require(
        inventory.get("sourceRepository") == "../chummer-play",
        failures,
        "mirror: required inventory must bind the sibling chummer-play source",
    )
    assets_value = inventory.get("assets")
    assets = assets_value if isinstance(assets_value, list) else []
    require(bool(assets), failures, "mirror: required inventory assets are missing")
    seen_sources: set[str] = set()
    seen_projections: set[str] = set()
    seen_roles: set[str] = set()
    valid_assets: list[dict[str, Any]] = []
    actual_asset_policy: list[tuple[str, str, str, str, str, str]] = []
    for index, item in enumerate(assets):
        if not isinstance(item, dict):
            failures.append(f"mirror: required inventory asset row {index} is not an object")
            continue
        source = normalized_relative_path(item.get("source"))
        projection = normalized_relative_path(item.get("projection"))
        role = str(item.get("role") or "").strip()
        kind = str(item.get("kind") or "").strip()
        content_type = str(item.get("contentType") or "").strip()
        cache_control = str(item.get("cacheControl") or "").strip()
        require(source is not None, failures, f"mirror: inventory source path is not normalized at row {index}")
        require(projection is not None, failures, f"mirror: inventory projection path is not normalized at row {index}")
        require(bool(role), failures, f"mirror: inventory role is missing at row {index}")
        require(kind in {"exact", "transform"}, failures, f"mirror: inventory kind is invalid at row {index}")
        expected_type = CONTENT_TYPES_BY_SUFFIX.get(PurePosixPath(projection or "").suffix)
        require(content_type == expected_type, failures, f"mirror: inventory MIME is invalid at row {index}")
        require(bool(cache_control), failures, f"mirror: inventory cache policy is missing at row {index}")
        if source is not None:
            require(source not in seen_sources, failures, f"mirror: duplicate inventory source {source}")
            seen_sources.add(source)
        if projection is not None:
            require(projection not in seen_projections, failures, f"mirror: duplicate inventory projection {projection}")
            seen_projections.add(projection)
        if role:
            require(role not in seen_roles, failures, f"mirror: duplicate inventory role {role}")
            seen_roles.add(role)
        if source is not None and projection is not None and role and kind in {"exact", "transform"}:
            valid_assets.append(item)
            actual_asset_policy.append((source, projection, kind, role, content_type, cache_control))
    require(
        sum(1 for item in valid_assets if item.get("kind") == "transform") == 1,
        failures,
        "mirror: required inventory must declare exactly one transform",
    )
    require(
        tuple(actual_asset_policy) == EXPECTED_ASSET_POLICY,
        failures,
        f"mirror: required inventory must exactly match {POLICY_ID} ({len(EXPECTED_ASSET_POLICY)} ordered assets)",
    )

    dependencies_value = inventory.get("generatorDependencies")
    dependencies = dependencies_value if isinstance(dependencies_value, list) else []
    require(
        len(dependencies) == len(REQUIRED_GENERATOR_DEPENDENCIES),
        failures,
        "mirror: required generator dependency inventory is incomplete",
    )
    seen_dependency_roles: set[str] = set()
    seen_dependency_paths: set[str] = set()
    valid_dependencies: list[dict[str, Any]] = []
    actual_dependency_policy: list[tuple[str, str, str, str]] = []
    for index, item in enumerate(dependencies):
        if not isinstance(item, dict):
            failures.append(f"mirror: required dependency row {index} is not an object")
            continue
        role = str(item.get("role") or "").strip()
        path = normalized_relative_path(item.get("path"))
        actual = (
            path,
            str(item.get("kind") or "").strip(),
            str(item.get("contentType") or "").strip(),
        )
        require(role not in seen_dependency_roles, failures, f"mirror: duplicate dependency role {role}")
        require(path is not None and path not in seen_dependency_paths, failures, f"mirror: duplicate or invalid dependency path at row {index}")
        require(
            role in REQUIRED_GENERATOR_DEPENDENCIES and actual == REQUIRED_GENERATOR_DEPENDENCIES.get(role),
            failures,
            f"mirror: required dependency metadata is invalid for {role or index}",
        )
        seen_dependency_roles.add(role)
        if path is not None:
            seen_dependency_paths.add(path)
        if role in REQUIRED_GENERATOR_DEPENDENCIES and actual == REQUIRED_GENERATOR_DEPENDENCIES[role]:
            valid_dependencies.append(item)
            actual_dependency_policy.append((str(path), actual[1], role, actual[2]))
    require(
        seen_dependency_roles == set(REQUIRED_GENERATOR_DEPENDENCIES),
        failures,
        "mirror: required generator dependency roles are incomplete",
    )
    require(
        tuple(actual_dependency_policy) == EXPECTED_DEPENDENCY_POLICY,
        failures,
        f"mirror: required inventory must exactly match {POLICY_ID} ({len(EXPECTED_DEPENDENCY_POLICY)} ordered dependencies)",
    )
    if tuple(actual_asset_policy) != EXPECTED_ASSET_POLICY:
        valid_assets = []
    if tuple(actual_dependency_policy) != EXPECTED_DEPENDENCY_POLICY:
        valid_dependencies = []
    return valid_assets, valid_dependencies


def require_closed_rows(
    declared_value: object,
    required_rows: list[dict[str, Any]],
    *,
    kind: str,
    failures: list[str],
) -> list[dict[str, Any]]:
    declared = declared_value if isinstance(declared_value, list) else []
    valid_declared = [item for item in declared if isinstance(item, dict)]
    require(len(valid_declared) == len(declared), failures, f"mirror: {kind} rows must be objects")
    declared_projections = [normalized_relative_path(item.get("projection")) for item in valid_declared]
    required_by_projection = {str(item["projection"]): item for item in required_rows}
    normalized_declared = [path for path in declared_projections if path is not None]
    duplicates = sorted({path for path in normalized_declared if normalized_declared.count(path) > 1})
    missing = sorted(set(required_by_projection) - set(normalized_declared))
    extra = sorted(set(normalized_declared) - set(required_by_projection))
    invalid_count = len(declared_projections) - len(normalized_declared)
    require(not duplicates, failures, f"mirror: duplicate {kind} rows: {', '.join(duplicates)}")
    require(not missing, failures, f"mirror: missing required {kind} rows: {', '.join(missing)}")
    require(not extra, failures, f"mirror: extra undeclared {kind} rows: {', '.join(extra)}")
    require(invalid_count == 0, failures, f"mirror: {kind} rows contain non-normalized paths")
    require(
        len(valid_declared) == len(required_rows),
        failures,
        f"mirror: {kind} row count does not match the required inventory",
    )
    metadata_fields = ("source", "projection", "kind", "role", "contentType", "cacheControl")
    for item in valid_declared:
        projection = normalized_relative_path(item.get("projection"))
        required = required_by_projection.get(projection or "")
        if required is None:
            continue
        for field in metadata_fields:
            require(
                item.get(field) == required.get(field),
                failures,
                f"mirror: {projection} {field} drifted from required inventory",
            )
    return valid_declared


def verify_mirror_closure(
    root: Path,
    failures: list[str],
    *,
    trusted_generator_path: Path | None = None,
    trusted_generator_payload: bytes | None = None,
    trusted_generator_sha256: str = "",
) -> dict[str, Any]:
    root = lexical_path(root)
    api_root = lexical_path(root / "Chummer.Run.Api")
    contract_path = api_root / "play-pwa-mirrors.json"
    inventory_path = root / REQUIRED_INVENTORY_PATH
    try:
        require_directory_no_symlinks(root, label="run-services root")
        require_directory_no_symlinks(api_root, label="Chummer.Run.Api root")
        contract_bytes = read_regular_file_no_symlinks(
            contract_path,
            root=api_root,
            label="mirror contract",
        )
        contract = strict_json_loads(contract_bytes, label="mirror contract")
        inventory_bytes = read_regular_file_no_symlinks(
            inventory_path,
            root=api_root,
            label="required inventory",
        )
        inventory = strict_json_loads(inventory_bytes, label="required inventory")
    except (OSError, RuntimeError) as exc:
        failures.append(f"mirror: contract or required inventory is unreadable: {exc}")
        return {"contract": "", "checked": [], "generator": {}, "generatorReceipt": {}}
    if not isinstance(contract, dict) or not isinstance(inventory, dict):
        failures.append("mirror: contract and required inventory must be JSON objects")
        return {"contract": "", "checked": [], "generator": {}, "generatorReceipt": {}}

    require(contract.get("contract") == MIRROR_CONTRACT_NAME, failures, "mirror: contract must be v5")
    require(contract.get("inventoryContract") == INVENTORY_CONTRACT_NAME, failures, "mirror: inventory contract binding drifted")
    require(contract.get("policyId") == POLICY_ID, failures, "mirror: policy identity binding drifted")
    require(contract.get("assetPolicyCount") == len(EXPECTED_ASSET_POLICY), failures, "mirror: exact asset policy count drifted")
    require(contract.get("dependencyPolicyCount") == len(EXPECTED_DEPENDENCY_POLICY), failures, "mirror: exact dependency policy count drifted")
    require(contract.get("inventoryPath") == REQUIRED_INVENTORY_PATH, failures, "mirror: inventory path binding drifted")
    inventory_digest = sha256(inventory_bytes)
    require(contract.get("inventorySha256") == inventory_digest, failures, "mirror: inventory digest binding drifted")
    required_assets, required_dependencies = inventory_rows(inventory, failures)
    source_repository_value = str(contract.get("sourceRepository") or "")
    require(source_repository_value == inventory.get("sourceRepository"), failures, "mirror: source repository drifted from required inventory")
    source_root = lexical_path(root / source_repository_value)
    expected_source_root = lexical_path(root.parent / "chummer-play")
    require(source_root == expected_source_root, failures, "mirror: source repository is not the sibling chummer-play checkout")
    source_root_valid = False
    try:
        require_directory_no_symlinks(expected_source_root, label="sibling chummer-play root")
    except RuntimeError as exc:
        failures.append(f"mirror: sibling source root is invalid: {exc}")
    else:
        source_root_valid = True

    exact_required = [item for item in required_assets if item.get("kind") == "exact"]
    transform_required = [item for item in required_assets if item.get("kind") == "transform"]
    assets = require_closed_rows(contract.get("assets"), exact_required, kind="exact asset", failures=failures)
    transforms = require_closed_rows(
        contract.get("executableTransforms"),
        transform_required,
        kind="transform",
        failures=failures,
    )
    checked: list[dict[str, Any]] = []
    for asset in assets:
        try:
            source = read_regular_file_no_symlinks(
                source_root / str(asset["source"]),
                root=expected_source_root,
                label=f"mirror source asset {asset.get('role')}",
            )
            projection = read_regular_file_no_symlinks(
                api_root / str(asset["projection"]),
                root=api_root,
                label=f"mirror projection asset {asset.get('role')}",
            )
        except (OSError, RuntimeError, KeyError) as exc:
            failures.append(f"mirror: exact asset is unreadable: {exc}")
            continue
        digest = sha256(projection)
        require(source == projection, failures, f"mirror: byte drift for {asset['projection']}")
        require(digest == asset["sha256"], failures, f"mirror: digest drift for {asset['projection']}")
        checked.append({"projection": asset["projection"], "sha256": digest, "kind": "exact"})
    require(len(transforms) == 1, failures, "mirror: root worker transform must be declared exactly once")
    for transform in transforms:
        try:
            source = read_regular_file_no_symlinks(
                source_root / str(transform["source"]),
                root=expected_source_root,
                label=f"mirror source transform {transform.get('role')}",
            )
            projection = read_regular_file_no_symlinks(
                api_root / str(transform["projection"]),
                root=api_root,
                label=f"mirror projection transform {transform.get('role')}",
            )
        except (OSError, RuntimeError, KeyError) as exc:
            failures.append(f"mirror: transformed asset is unreadable: {exc}")
            continue
        require(sha256(source) == transform["sourceSha256"], failures, "mirror: source worker digest drift")
        require(sha256(projection) == transform["projectionSha256"], failures, "mirror: projected worker digest drift")
        checked.append({"projection": transform["projection"], "sha256": sha256(projection), "kind": "transform"})

    generator = contract.get("generator") if isinstance(contract.get("generator"), dict) else {}
    require(
        generator.get("contract") == "play-root-worker-projection-generator-v1",
        failures,
        "mirror: deterministic worker generator contract missing",
    )
    declared_dependencies = generator.get("dependencies") if isinstance(generator.get("dependencies"), list) else []
    required_dependencies_by_role = {str(item["role"]): item for item in required_dependencies}
    declared_dependency_roles = [str(item.get("role") or "") for item in declared_dependencies if isinstance(item, dict)]
    duplicate_dependency_roles = sorted({role for role in declared_dependency_roles if declared_dependency_roles.count(role) > 1})
    missing_dependency_roles = sorted(set(required_dependencies_by_role) - set(declared_dependency_roles))
    extra_dependency_roles = sorted(set(declared_dependency_roles) - set(required_dependencies_by_role))
    require(not duplicate_dependency_roles, failures, f"mirror: duplicate generator dependencies: {', '.join(duplicate_dependency_roles)}")
    require(not missing_dependency_roles, failures, f"mirror: missing generator dependencies: {', '.join(missing_dependency_roles)}")
    require(not extra_dependency_roles, failures, f"mirror: extra generator dependencies: {', '.join(extra_dependency_roles)}")
    require(len(declared_dependencies) == len(required_dependencies), failures, "mirror: generator dependency count drifted")
    dependency_paths: dict[str, Path] = {}
    for item in declared_dependencies:
        if not isinstance(item, dict):
            failures.append("mirror: generator dependency rows must be objects")
            continue
        role = str(item.get("role") or "")
        required = required_dependencies_by_role.get(role)
        if required is None:
            continue
        for field in ("path", "kind", "role", "contentType"):
            require(item.get(field) == required.get(field), failures, f"mirror: generator dependency {role} {field} drifted")
        declared_path = normalized_relative_path(item.get("path"))
        if declared_path is None:
            failures.append(f"mirror: generator dependency {role} path is not normalized")
            continue
        path = lexical_path(root / declared_path)
        dependency_paths[role] = path
        try:
            dependency_bytes = read_regular_file_no_symlinks(
                path,
                root=root,
                label=f"generator dependency {role}",
            )
        except RuntimeError as exc:
            failures.append(f"mirror: generator dependency {role} invalid: {exc}")
        else:
            require(sha256(dependency_bytes) == str(item.get("sha256") or ""), failures, f"mirror: generator dependency {role} digest drift")

    flat_dependency_fields = {
        "script": ("generator_script", "scriptSha256"),
        "config": ("projection_config", "configSha256"),
        "template": ("projection_template", "templateSha256"),
        "inventory": ("required_inventory", "inventorySha256"),
    }
    for field, (role, digest_field) in flat_dependency_fields.items():
        required = required_dependencies_by_role.get(role, {})
        path = dependency_paths.get(role)
        require(generator.get(field) == required.get("path"), failures, f"mirror: generator {field} path binding drift")
        if path is not None:
            try:
                dependency_bytes = read_regular_file_no_symlinks(path, root=root, label=f"generator {field}")
            except RuntimeError:
                continue
            require(generator.get(digest_field) == sha256(dependency_bytes), failures, f"mirror: generator {field} digest binding drift")

    config_path = dependency_paths.get("projection_config")
    if config_path is not None:
        try:
            config_bytes = read_regular_file_no_symlinks(config_path, root=root, label="projection config")
            projection_config = strict_json_loads(config_bytes, label="projection config")
        except (OSError, RuntimeError) as exc:
            failures.append(f"mirror: projection config is unreadable: {exc}")
        else:
            require(projection_config.get("requiredInventory") == REQUIRED_INVENTORY_PATH, failures, "mirror: projection config inventory path drifted")
            require(projection_config.get("requiredInventorySha256") == inventory_digest, failures, "mirror: projection config inventory digest drifted")

    generator_receipt: dict[str, Any] = {}
    dependency_files_valid = set(dependency_paths) == set(REQUIRED_GENERATOR_DEPENDENCIES)
    if dependency_files_valid:
        try:
            dependency_payloads = {
                role: read_regular_file_no_symlinks(path, root=root, label=f"generator dependency {role}")
                for role, path in dependency_paths.items()
            }
        except RuntimeError:
            dependency_files_valid = False
            dependency_payloads = {}
    else:
        dependency_payloads = {}
    trusted_generator_digest = ""
    if dependency_files_valid:
        try:
            script_path = dependency_paths["generator_script"]
            generator_payload = dependency_payloads["generator_script"]
            if trusted_generator_path is not None and trusted_generator_payload is not None:
                raise RuntimeError("trusted generator path and sealed payload are mutually exclusive")
            if trusted_generator_payload is not None:
                trusted_generator_digest = sha256(trusted_generator_payload)
                require(
                    trusted_generator_digest == trusted_generator_sha256,
                    failures,
                    "mirror: sealed generator payload digest differs from its execution authority",
                )
                require(
                    trusted_generator_payload == generator_payload,
                    failures,
                    "mirror: sealed generator payload differs from pinned source generator",
                )
                if (
                    trusted_generator_digest != trusted_generator_sha256
                    or trusted_generator_payload != generator_payload
                ):
                    raise RuntimeError("sealed generator payload identity mismatch")
                generator_payload = trusted_generator_payload
            elif trusted_generator_path is not None:
                trusted_payload = read_regular_file_no_symlinks(
                    trusted_generator_path,
                    root=trusted_generator_path.parent,
                    label="trusted generator snapshot",
                )
                require(
                    trusted_payload == generator_payload,
                    failures,
                    "mirror: trusted generator snapshot differs from pinned source generator",
                )
                if trusted_payload != generator_payload:
                    raise RuntimeError("trusted generator snapshot identity mismatch")
                generator_payload = trusted_payload
                trusted_generator_digest = sha256(trusted_payload)
            module = types.ModuleType("verify_public_play_worker_projection_generator")
            module.__file__ = str(script_path)
            exec(compile(generator_payload, str(script_path), "exec"), module.__dict__)
            if _ACTIVE_TRUSTED_INPUT_SNAPSHOT is not None:
                def trusted_generator_reader(
                    path: Path,
                    root: Path,
                    label: str,
                ) -> bytes | None:
                    return _ACTIVE_TRUSTED_INPUT_SNAPSHOT.read(path, label=label)

                module.install_trusted_input_reader(
                    trusted_generator_reader,
                    roots=(
                        _ACTIVE_TRUSTED_INPUT_SNAPSHOT.run_root,
                        _ACTIVE_TRUSTED_INPUT_SNAPSHOT.play_root,
                    ),
                )
            with tempfile.TemporaryDirectory(prefix="chummer-worker-projection-verify-") as temp_dir:
                temp_root = Path(temp_dir)
                worker_output = temp_root / "service-worker.js"
                mirror_output = temp_root / "play-pwa-mirrors.json"
                generator_receipt = module.run(
                    root=root,
                    config_path=dependency_paths["projection_config"],
                    output_path=worker_output,
                    mirror_output_path=mirror_output,
                )
                require(
                    read_regular_file_no_symlinks(worker_output, root=temp_root, label="regenerated worker")
                    == read_regular_file_no_symlinks(api_root / "wwwroot/service-worker.js", root=api_root, label="committed worker"),
                    failures,
                    "mirror: committed worker differs from deterministic regeneration",
                )
                require(
                    read_regular_file_no_symlinks(mirror_output, root=temp_root, label="regenerated mirror")
                    == contract_bytes,
                    failures,
                    "mirror: committed mirror contract differs from deterministic regeneration",
                )
        except (OSError, RuntimeError, ValueError) as exc:
            failures.append(f"mirror: deterministic regeneration failed: {exc}")
    return {
        "contract": contract.get("contract"),
        "inventoryContract": inventory.get("contract"),
        "policyId": inventory.get("policyId"),
        "assetPolicyCount": len(required_assets),
        "dependencyPolicyCount": len(required_dependencies),
        "symlinkPolicy": "reject_all_components",
        "inventorySha256": inventory_digest,
        "sourceRepository": source_repository_value,
        "siblingPlaySourceValidated": source_root == expected_source_root and source_root_valid,
        "checked": checked,
        "generator": generator,
        "generatorReceipt": generator_receipt,
        "trustedGeneratorSha256": trusted_generator_digest,
    }


def _verify_source_impl(
    root: Path = RUN_SERVICES_ROOT,
    *,
    trusted_generator_path: Path | None = None,
    trusted_generator_payload: bytes | None = None,
    trusted_generator_sha256: str = "",
    trusted_input_snapshot: TrustedInputSnapshot | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    root = lexical_path(root)
    api_root = root / "Chummer.Run.Api"
    wwwroot = api_root / "wwwroot"
    snapshot_before = validate_input_snapshot(
        root,
        trusted_input_snapshot,
        failures,
    )
    asset_inventory = source_asset_digest_inventory(root, failures)

    def source_bytes(path: Path, *, file_root: Path, label: str) -> bytes:
        try:
            return read_regular_file_no_symlinks(
                path,
                root=file_root,
                label=label,
                max_bytes=input_size_limit(
                    "run-services",
                    lexical_path(path).relative_to(root).as_posix(),
                ),
            )
        except RuntimeError as exc:
            failures.append(f"source: {label} is invalid: {exc}")
            return b""

    manifests: list[dict[str, Any]] = []
    for path in MANIFESTS:
        file_path = wwwroot / path.lstrip("/")
        payload = source_bytes(file_path, file_root=api_root, label=f"manifest {path}")
        if payload:
            manifests.append(verify_manifest(path, payload, failures))
    for path in LOCAL_ASSETS:
        source_bytes(
            wwwroot / path.lstrip("/"),
            file_root=api_root,
            label=f"local asset {path}",
        )
    installer = source_bytes(
        wwwroot / "mobile-install-shell.js",
        file_root=api_root,
        label="mobile install shell",
    ).decode("utf-8", errors="replace")
    require(
        'register("/mobile/service-worker.js", { scope: "/mobile/" })' in installer,
        failures,
        "source: installer must register the nested worker at /mobile/ scope",
    )
    nested = source_bytes(
        wwwroot / "mobile" / "service-worker.js",
        file_root=api_root,
        label="nested service worker",
    ).decode("utf-8", errors="replace")
    require('importScripts("/service-worker.js")' in nested, failures, "source: nested worker must import the digest-closed root worker")
    worker = verify_worker(
        source_bytes(
            wwwroot / "service-worker.js",
            file_root=api_root,
            label="root service worker",
        ),
        failures,
    )
    mirror = verify_mirror_closure(
        root,
        failures,
        trusted_generator_path=trusted_generator_path,
        trusted_generator_payload=trusted_generator_payload,
        trusted_generator_sha256=trusted_generator_sha256,
    )
    compose = source_bytes(
        root / "docker-compose.public-edge.yml",
        file_root=root,
        label="public edge compose",
    ).decode("utf-8", errors="replace")
    require('profiles: ["play-private"]' in compose, failures, "compose: private Play profile missing")
    require(
        'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"' in compose,
        failures,
        "compose: public Play proxy must be literal false",
    )
    require(
        compose.count("CHUMMER_PUBLIC_PLAY_PROXY_ENABLED:") == 1,
        failures,
        "compose: public Play proxy must have exactly one declaration",
    )
    require(
        'CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "false"' in compose,
        failures,
        "compose: public Play live-session proxy must be literal false",
    )
    require(
        compose.count("CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED:") == 1,
        failures,
        "compose: public Play live-session proxy must have exactly one declaration",
    )
    require(
        "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED" not in compose,
        failures,
        "compose: public Play proxy must not be environment-overridable",
    )
    require(
        "${CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED" not in compose,
        failures,
        "compose: public Play live-session proxy must not be environment-overridable",
    )
    portal_parts = compose.split("  chummer-portal:", 1)
    require(len(portal_parts) == 2, failures, "compose: portal service is missing")
    portal_dependencies = portal_parts[1].split("    environment:", 1)[0] if len(portal_parts) == 2 else ""
    require("chummer-play-web:" not in portal_dependencies, failures, "compose: portal must not depend on private Play")
    gateway = source_bytes(
        api_root / "Services" / "PublicPlayProxyGateway.cs",
        file_root=api_root,
        label="public Play proxy gateway",
    ).decode("utf-8", errors="replace")
    require("Array.Empty<string>()" in gateway, failures, "gateway: public route set must be empty")
    require("IHttpClientFactory" not in gateway, failures, "gateway: outbound client must not exist")
    snapshot_after = validate_input_snapshot(
        root,
        trusted_input_snapshot,
        failures,
    )
    snapshot_stable = snapshot_before == snapshot_after
    require(snapshot_stable, failures, "snapshot: inputs changed during verification")
    return {
        "contractName": CONTRACT_NAME,
        "generatedAt": datetime.now(UTC).isoformat(),
        "mode": "source",
        "status": "pass" if not failures else "fail",
        "manifests": manifests,
        "worker": worker,
        "mirror": mirror,
        "assetDigestInventory": asset_inventory,
        "inputSnapshot": {
            "status": (
                "pass"
                if snapshot_stable and snapshot_before.get("status") == "pass"
                else snapshot_before.get("status")
            ),
            "contractName": snapshot_before.get("contractName", ""),
            "sha256": snapshot_before.get("sha256", ""),
            "checkedCount": snapshot_before.get("checkedCount", 0),
            "checked": snapshot_before.get("checked", []),
            "stable": snapshot_stable,
            "authorityMode": snapshot_before.get("authorityMode", ""),
        },
        "failures": failures,
    }


def verify_source(
    root: Path = RUN_SERVICES_ROOT,
    *,
    trusted_generator_path: Path | None = None,
    trusted_generator_payload: bytes | None = None,
    trusted_generator_sha256: str = "",
    trusted_input_snapshot: TrustedInputSnapshot | None = None,
) -> dict[str, Any]:
    global _ACTIVE_TRUSTED_INPUT_SNAPSHOT
    previous_snapshot = _ACTIVE_TRUSTED_INPUT_SNAPSHOT
    _ACTIVE_TRUSTED_INPUT_SNAPSHOT = trusted_input_snapshot
    try:
        return _verify_source_impl(
            root,
            trusted_generator_path=trusted_generator_path,
            trusted_generator_payload=trusted_generator_payload,
            trusted_generator_sha256=trusted_generator_sha256,
            trusted_input_snapshot=trusted_input_snapshot,
        )
    finally:
        _ACTIVE_TRUSTED_INPUT_SNAPSHOT = previous_snapshot


def verify_live_deployment_identity(
    base_url: str,
    timeout_seconds: float,
    expected_full_deployment_digest_sha256: str,
    failures: list[str],
) -> dict[str, Any]:
    expected_digest = str(expected_full_deployment_digest_sha256 or "").strip()
    require(
        re.fullmatch(r"[0-9a-f]{64}", expected_digest) is not None,
        failures,
        "/api/ready: expected full deployment digest must be lowercase SHA-256",
    )
    status, headers, payload = fetch(base_url, "/api/ready", timeout_seconds)
    require(status == 200, failures, f"/api/ready: expected 200, got {status}")
    require_private_response_headers("/api/ready", headers, failures)
    require(
        "json" in headers.get("content-type", "").lower(),
        failures,
        "/api/ready: wrong content type",
    )
    try:
        readiness = strict_json_loads(payload, label="/api/ready")
    except RuntimeError as error:
        failures.append(f"/api/ready: invalid readiness JSON: {error}")
        return {
            "status": status,
            "ready": False,
            "code": "",
            "sourceFingerprintSha256": "",
            "fullDeploymentDigestSha256": "",
            "matchesExpectedFullDeploymentDigest": False,
        }
    if not isinstance(readiness, dict):
        failures.append("/api/ready: readiness payload must be a JSON object")
        readiness = {}
    identity = readiness.get("deploymentIdentity")
    if not isinstance(identity, dict):
        failures.append("/api/ready: deployment identity is missing")
        identity = {}
    source_fingerprint_sha256 = str(
        identity.get("sourceFingerprintSha256") or ""
    ).strip()
    actual_digest = str(
        identity.get("fullDeploymentDigestSha256") or ""
    ).strip()
    require(
        readiness.get("ready") is True and readiness.get("status") == "ready",
        failures,
        "/api/ready: combined readiness is not ready",
    )
    require(
        identity.get("ready") is True
        and identity.get("code") == EXPECTED_DEPLOYMENT_IDENTITY_CODE,
        failures,
        "/api/ready: deployment identity is not bound",
    )
    require(
        re.fullmatch(r"[0-9a-f]{64}", source_fingerprint_sha256) is not None,
        failures,
        "/api/ready: source fingerprint is invalid",
    )
    require(
        re.fullmatch(r"[0-9a-f]{64}", actual_digest) is not None,
        failures,
        "/api/ready: full deployment digest is invalid",
    )
    require(
        bool(expected_digest) and actual_digest == expected_digest,
        failures,
        "/api/ready: full deployment digest does not match the expected deployment",
    )
    return {
        "status": status,
        "ready": identity.get("ready") is True,
        "code": str(identity.get("code") or ""),
        "sourceFingerprintSha256": source_fingerprint_sha256,
        "fullDeploymentDigestSha256": actual_digest,
        "matchesExpectedFullDeploymentDigest": bool(expected_digest)
        and actual_digest == expected_digest,
    }


def deployment_identity_is_stable(
    before: dict[str, Any],
    after: dict[str, Any],
) -> bool:
    return (
        before.get("sourceFingerprintSha256")
        == after.get("sourceFingerprintSha256")
        and before.get("fullDeploymentDigestSha256")
        == after.get("fullDeploymentDigestSha256")
        and before.get("code") == after.get("code")
        and before.get("ready") == after.get("ready")
    )


def verify_live(
    base_url: str,
    timeout_seconds: float,
    expected_full_deployment_digest_sha256: str,
    expected_asset_inventory_sha256: str,
) -> dict[str, Any]:
    failures: list[str] = []
    validate_clean_origin(base_url)
    sealed_inventory_digest = str(expected_asset_inventory_sha256 or "").strip()
    require(
        re.fullmatch(r"[0-9a-f]{64}", sealed_inventory_digest) is not None,
        failures,
        "asset inventory: sealed expected digest must be lowercase SHA-256",
    )
    expected_asset_inventory = source_asset_digest_inventory(
        RUN_SERVICES_ROOT,
        failures,
    )
    require(
        expected_asset_inventory.get("sha256") == sealed_inventory_digest,
        failures,
        "asset inventory: current source differs from the sealed preflight inventory",
    )
    expected_assets = {
        str(item.get("path") or ""): item
        for item in expected_asset_inventory.get("assets", [])
        if isinstance(item, dict)
    }
    readiness_before = verify_live_deployment_identity(
        base_url,
        timeout_seconds,
        expected_full_deployment_digest_sha256,
        failures,
    )
    manifests: list[dict[str, Any]] = []
    for path in MANIFESTS:
        status, headers, payload = fetch(base_url, path, timeout_seconds)
        require(status == 200, failures, f"{path}: expected 200, got {status}")
        require("manifest" in headers.get("content-type", "") or "json" in headers.get("content-type", ""), failures, f"{path}: wrong content type")
        manifests.append(verify_manifest(path, payload, failures))
    assets: list[dict[str, Any]] = []
    live_bound_rows: list[dict[str, Any]] = []
    for path in LOCAL_ASSETS:
        status, headers, payload = fetch(base_url, path, timeout_seconds)
        actual_media_type = normalized_media_type(headers.get("content-type"))
        exact_expected_media_type = CONTENT_TYPES_BY_SUFFIX.get(
            PurePosixPath(path).suffix,
            "",
        )
        require(status == 200, failures, f"{path}: expected 200, got {status}")
        require(bool(payload), failures, f"{path}: empty response")
        require(
            actual_media_type == exact_expected_media_type,
            failures,
            f"{path}: MIME must be exactly {exact_expected_media_type}",
        )
        if path.endswith("service-worker.js"):
            require("no-store" in headers.get("cache-control", "").lower(), failures, f"{path}: worker must be no-store")
            require(headers.get("x-content-type-options", "").lower() == "nosniff", failures, f"{path}: worker must be nosniff")
        actual_digest = sha256(payload)
        expected_asset = expected_assets.get(path)
        require(
            expected_asset is not None,
            failures,
            f"{path}: asset is outside the sealed expected inventory",
        )
        if expected_asset is not None:
            live_bound_rows.append(
                verify_live_bound_asset(
                    path,
                    status,
                    headers,
                    payload,
                    expected_asset,
                    failures,
                )
            )
        assets.append(
            {
                "path": path,
                "status": status,
                "contentType": actual_media_type,
                "sizeBytes": len(payload),
                "sha256": actual_digest,
                "expectedSha256": str((expected_asset or {}).get("sha256") or ""),
                "digestMatches": expected_asset is not None
                and actual_digest == expected_asset.get("sha256"),
            }
        )
    live_asset_inventory = asset_digest_inventory(
        [
            {
                key: row.get(key)
                for key in (
                    "path",
                    "contentType",
                    "cacheControl",
                    "mirrorBound",
                    "sha256",
                    "sizeBytes",
                )
            }
            for row in live_bound_rows
        ]
    )
    asset_inventory_matches = (
        live_asset_inventory.get("assetCount")
        == expected_asset_inventory.get("assetCount")
        == len(LIVE_BOUND_ASSET_POLICY)
        and live_asset_inventory.get("sha256")
        == expected_asset_inventory.get("sha256")
    )
    require(
        asset_inventory_matches,
        failures,
        "asset inventory: live PWA bundle does not match the preflight source inventory",
    )
    status, _, worker_payload = fetch(base_url, "/service-worker.js", timeout_seconds)
    require(status == 200, failures, "root worker unavailable")
    worker = verify_worker(worker_payload, failures)
    critical_assets = set(worker.get("criticalAssets") or [])
    compatibility_service_worker = {
        "ledger_stream_non_cacheable": worker.get("privateApiNetworkOnly") is True,
        "ledger_stream_precached": any(
            str(path).startswith("/api/play/") for path in critical_assets
        ),
        "worker_kind": "play",
        "cache_version": worker.get("cacheVersion"),
    }
    clean_mobile_player_shell = verify_clean_mobile_player_shell(
        base_url,
        timeout_seconds,
        failures,
    )
    documents: list[dict[str, Any]] = []
    for path, (role, manifest, title, purpose, capability, target) in ROLE_DOCUMENTS.items():
        status, headers, payload = fetch(base_url, path, timeout_seconds)
        markup = payload.decode("utf-8", errors="replace")
        require(status == 200, failures, f"{path}: expected 200, got {status}")
        require(f'data-install-role="{role}"' in markup, failures, f"{path}: wrong role shell")
        require(f'href="{manifest}"' in markup, failures, f"{path}: wrong manifest")
        require(title in markup, failures, f"{path}: wrong title/body")
        require(purpose in markup, failures, f"{path}: role purpose drifted")
        require(capability in markup, failures, f"{path}: role capability drifted")
        require(f'href="{target}"' in markup, failures, f"{path}: role open target drifted")
        require("data-mobile-app-inline-qr" in markup, failures, f"{path}: role QR missing")
        require(f'data-role-privacy-warning="{role}"' in markup, failures, f"{path}: privacy warning drifted")
        require(f'data-role-authority-warning="{role}"' in markup, failures, f"{path}: authority warning drifted")
        require('data-play-surface="install-only"' in markup, failures, f"{path}: not install-only")
        require("/_framework/blazor.web.js" not in markup, failures, f"{path}: Blazor boot leaked")
        require("mobile-turn-companion.js" not in markup, failures, f"{path}: private companion script leaked")
        require_private_response_headers(path, headers, failures)
        require("connect-src 'none'" in headers.get("content-security-policy", ""), failures, f"{path}: CSP permits network connections")
        require(headers.get("referrer-policy", "").lower() == "no-referrer", failures, f"{path}: referrer policy drift")
        require(headers.get("x-content-type-options", "").lower() == "nosniff", failures, f"{path}: nosniff missing")
        private_key_findings = private_identity_key_findings(markup)
        require(
            not private_key_findings,
            failures,
            f"{path}: private identity key material is present ({', '.join(private_key_findings)})",
        )
        documents.append(
            {
                "path": path,
                "role": role,
                "manifest": manifest,
                "target": target,
                "status": status,
                "privateIdentityKeysAbsent": not private_key_findings,
                "privateIdentityKeyFindings": private_key_findings,
            }
        )
    compatibility_role_names = {
        "/manifest.player.webmanifest": "Player",
        "/manifest.gm.webmanifest": "GameMaster",
        "/manifest.observer.webmanifest": "Observer",
    }
    role_manifests = [
        {
            "role": compatibility_role_names[manifest["path"]],
            "path": manifest["path"],
            "id": manifest.get("id"),
            "start_url": manifest.get("startUrl"),
            "display": manifest.get("display"),
        }
        for manifest in manifests
        if manifest.get("path") in compatibility_role_names
    ]
    readiness_after = verify_live_deployment_identity(
        base_url,
        timeout_seconds,
        expected_full_deployment_digest_sha256,
        failures,
    )
    readiness_stable = deployment_identity_is_stable(
        readiness_before,
        readiness_after,
    )
    require(
        readiness_stable,
        failures,
        "/api/ready: deployment identity changed during live verification",
    )
    final_source_inventory = source_asset_digest_inventory(
        RUN_SERVICES_ROOT,
        failures,
    )
    source_inventory_stable = (
        final_source_inventory.get("sha256")
        == expected_asset_inventory.get("sha256")
        == sealed_inventory_digest
    )
    require(
        source_inventory_stable,
        failures,
        "asset inventory: source changed during live verification",
    )
    return {
        "contractName": "chummer.public_pwa_static_assets.v1",
        "assetContractName": CONTRACT_NAME,
        "generatedAt": datetime.now(UTC).isoformat(),
        "mode": "live",
        "status": "pass" if not failures else "fail",
        "deploymentIdentity": {
            **readiness_after,
            "before": readiness_before,
            "after": readiness_after,
            "stable": readiness_stable,
        },
        "manifests": manifests,
        "role_manifests": role_manifests,
        "assets": assets,
        "assetDigestInventory": {
            "contractName": ASSET_DIGEST_INVENTORY_CONTRACT_NAME,
            "algorithm": ASSET_DIGEST_INVENTORY_ALGORITHM,
            "assetCount": len(LIVE_BOUND_ASSET_POLICY),
            "expectedSha256": expected_asset_inventory.get("sha256"),
            "sealedExpectedSha256": sealed_inventory_digest,
            "actualSha256": live_asset_inventory.get("sha256"),
            "matchesExpected": asset_inventory_matches
            and source_inventory_stable,
            "sourceStable": source_inventory_stable,
            "assets": live_bound_rows,
        },
        "worker": worker,
        "service_worker": compatibility_service_worker,
        "cleanMobilePlayerShell": clean_mobile_player_shell,
        "documents": documents,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the local install-only public Play PWA contract.")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--expected-full-deployment-digest-sha256", default="")
    parser.add_argument("--expected-asset-inventory-sha256", default="")
    parser.add_argument("--source-root", type=Path, default=RUN_SERVICES_ROOT)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--output", type=Path)
    output_group.add_argument("--output-fd", type=int)
    parser.add_argument("--trusted-generator", type=Path)
    parser.add_argument("--trusted-generator-fd", type=int)
    parser.add_argument("--trusted-generator-sha256", default="")
    parser.add_argument("--trusted-input-manifest-fd", type=int)
    parser.add_argument("--trusted-input-manifest-sha256", default="")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    args = parser.parse_args()
    if args.base_url and re.fullmatch(
        r"[0-9a-f]{64}",
        str(args.expected_full_deployment_digest_sha256 or "").strip(),
    ) is None:
        parser.error(
            "--base-url requires --expected-full-deployment-digest-sha256 as lowercase SHA-256"
        )
    if args.base_url and re.fullmatch(
        r"[0-9a-f]{64}",
        str(args.expected_asset_inventory_sha256 or "").strip(),
    ) is None:
        parser.error(
            "--base-url requires --expected-asset-inventory-sha256 as lowercase SHA-256"
        )
    if args.base_url:
        try:
            validate_clean_origin(args.base_url)
        except RuntimeError as exc:
            parser.error(str(exc))
    if args.trusted_generator is not None and args.trusted_generator_fd is not None:
        parser.error("--trusted-generator and --trusted-generator-fd are mutually exclusive")
    trusted_generator_payload: bytes | None = None
    trusted_input_snapshot: TrustedInputSnapshot | None = None
    manifest_error = ""
    if args.trusted_input_manifest_fd is not None:
        try:
            trusted_input_manifest_payload = read_sealed_inherited_payload(
                args.trusted_input_manifest_fd,
                str(args.trusted_input_manifest_sha256 or "").lower(),
                label="trusted input manifest",
                max_bytes=MAX_TRUSTED_INPUT_MANIFEST_BYTES,
            )
            parsed_manifest = strict_json_loads(
                trusted_input_manifest_payload,
                label="trusted input manifest",
            )
            if not isinstance(parsed_manifest, dict):
                raise RuntimeError("trusted input manifest must be a JSON object")
            reserved_descriptors = {
                value
                for value in (
                    args.trusted_input_manifest_fd,
                    args.trusted_generator_fd,
                    args.output_fd,
                )
                if isinstance(value, int) and value >= 0
            }
            trusted_input_snapshot = load_trusted_input_snapshot(
                args.source_root,
                parsed_manifest,
                str(args.trusted_input_manifest_sha256 or "").lower(),
                reserved_descriptors=reserved_descriptors,
            )
        except RuntimeError as exc:
            manifest_error = str(exc)
    elif args.trusted_input_manifest_sha256:
        parser.error("--trusted-input-manifest-sha256 requires --trusted-input-manifest-fd")

    if manifest_error:
        result = {
            "contractName": CONTRACT_NAME,
            "mode": "source",
            "status": "fail",
            "mirror": {},
            "inputSnapshot": {"status": "fail"},
            "failures": [f"snapshot: sealed input manifest authority failed: {manifest_error}"],
        }
    elif args.trusted_generator_fd is not None:
        try:
            trusted_generator_payload = read_sealed_inherited_payload(
                args.trusted_generator_fd,
                str(args.trusted_generator_sha256 or "").lower(),
                label="trusted generator",
                max_bytes=MAX_TRUSTED_GENERATOR_BYTES,
            )
        except RuntimeError as exc:
            result = {
                "contractName": CONTRACT_NAME,
                "mode": "source",
                "status": "fail",
                "mirror": {},
                "failures": [f"mirror: sealed generator authority failed: {exc}"],
            }
        else:
            result = verify_source(
                args.source_root,
                trusted_generator_payload=trusted_generator_payload,
                trusted_generator_sha256=str(args.trusted_generator_sha256 or "").lower(),
                trusted_input_snapshot=trusted_input_snapshot,
            )
    else:
        if args.trusted_generator_sha256:
            parser.error("--trusted-generator-sha256 requires --trusted-generator-fd")
        result = (
            verify_live(
                args.base_url,
                args.timeout_seconds,
                args.expected_full_deployment_digest_sha256,
                args.expected_asset_inventory_sha256,
            )
            if args.base_url
            else verify_source(
                args.source_root,
                trusted_generator_path=args.trusted_generator,
                trusted_input_snapshot=trusted_input_snapshot,
            )
        )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    rendered_bytes = rendered.encode("utf-8")
    if args.output_fd is not None:
        write_receipt_descriptor(args.output_fd, rendered_bytes)
    elif args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
