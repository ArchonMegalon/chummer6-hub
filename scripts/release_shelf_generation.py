#!/usr/bin/env python3
"""Stage, validate, and activate immutable public release shelf generations.

The layout implemented here is documented in docs/ATOMIC_RELEASE_SHELF_PUBLICATION.md.
The filesystem publisher uses ``activate-filesystem`` directly. Object-storage
publishers use ``prepare`` and upload the resulting generation before replacing the
single ``current.json`` authority pointer.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterator
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen


POINTER_SCHEMA = "chummer.release-shelf.current/v1"
ACTIVATION_CANDIDATE_SCHEMA = "chummer.release-shelf.activation-candidate/v1"
LAYOUT_MARKER = ".release-shelf-layout-v1"
CURRENT_POINTER = "current.json"
GENERATIONS_DIRECTORY = "generations"
PROMOTION_LOCK = ".release-shelf-promotion.lock"
ACTIVATION_STAGE_PREFIX = ".release-shelf-stage-"
WRITER_POLICY = ".release-shelf-writer-policy.json"
SERVER_WRITER_POLICY_SCHEMA = "chummer.release-shelf.writer-policy/v1"
SERVER_WRITER_POLICY_MODE = "server-journal-v1"
SIDECAR_WRITER_POLICY_MODE = "sidecar-readonly-v1"
CANONICAL_MANIFEST = "RELEASE_CHANNEL.generated.json"
COMPATIBILITY_MANIFEST = "releases.json"
PUBLICATION_SCOPE = "PUBLICATION_SCOPE.generated.json"
ACTIVATION_CANDIDATE = "activation-candidate.json"
SAFE_GENERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PORTABLE_INVENTORY_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,254}$")
COPYABLE_FILES = {
    CANONICAL_MANIFEST,
    COMPATIBILITY_MANIFEST,
    PUBLICATION_SCOPE,
    "aur-packages.json",
}
COPYABLE_DIRECTORIES = {
    "files",
    "install",
    "startup-smoke",
    "proof",
    "release-evidence",
}
VERSIONED_ROUTE_PREFIXES = (
    "/downloads/files/",
    "/downloads/proof/",
    "/downloads/startup-smoke/",
    "/downloads/release-evidence/",
)
ALLOWED_GENERATION_ROUTE_ROOTS = {
    CANONICAL_MANIFEST,
    COMPATIBILITY_MANIFEST,
    "files",
    "startup-smoke",
    "proof",
    "release-evidence",
}
PROOF_ROUTE_KEYS = frozenset({"proofRoutes", "proof_routes"})
SEALED_DIRECTORY_MODE = 0o555
SEALED_FILE_MODE = 0o444
PUBLIC_METADATA_FILE_MODE = 0o644
SHARED_DIRECTORY_MODE = 0o2770
SHARED_CONTROL_FILE_MODE = 0o660
PUBLIC_GENERATION_METADATA = {
    ACTIVATION_CANDIDATE,
    CANONICAL_MANIFEST,
    COMPATIBILITY_MANIFEST,
    PUBLICATION_SCOPE,
}


class ReleaseShelfError(RuntimeError):
    """Raised when a shelf or candidate fails closed."""


def _stage_intent_name(generation_id: str, activation_receipt_id: str) -> str:
    generation_id = validate_generation_id(generation_id)
    activation_receipt_id = validate_generation_id(activation_receipt_id)
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "activationReceiptId": activation_receipt_id,
                "generationId": generation_id,
            }
        )
    ).hexdigest()
    return f"{ACTIVATION_STAGE_PREFIX}{digest[:32]}"


class _PromotionLockLease:
    """Opaque proof that this process still owns the canonical shelf lock."""

    __slots__ = ("_handle", "_lock_path", "_identity")

    def __init__(self, handle: BinaryIO, lock_path: Path) -> None:
        self._handle = handle
        self._lock_path = lock_path
        metadata = os.fstat(handle.fileno())
        self._identity = (metadata.st_dev, metadata.st_ino)

    def validate_for(self, shelf_root: Path) -> None:
        expected = (shelf_root.resolve(strict=True) / PROMOTION_LOCK)
        if expected != self._lock_path:
            raise ReleaseShelfError(
                "promotion lock lease is bound to a different release shelf"
            )
        try:
            opened = os.fstat(self._handle.fileno())
            linked = self._lock_path.lstat()
        except (OSError, ValueError) as exc:
            raise ReleaseShelfError("promotion lock lease is no longer active") from exc
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(linked.st_mode)
            or (opened.st_dev, opened.st_ino) != self._identity
            or (linked.st_dev, linked.st_ino) != self._identity
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != SHARED_CONTROL_FILE_MODE
        ):
            raise ReleaseShelfError("promotion lock lease identity changed")


def refuse_server_managed_filesystem_shelf(shelf_root: Path) -> None:
    """Prevent this legacy Python writer from bypassing the server journal."""
    policy_path = shelf_root / WRITER_POLICY
    if not policy_path.exists():
        return
    if policy_path.is_symlink() or not policy_path.is_file():
        raise ReleaseShelfError("release shelf writer policy is not a regular file; refusing mutation")
    policy = read_json_object(policy_path, "release shelf writer policy")
    if set(policy) != {"schemaVersion", "mode"}:
        raise ReleaseShelfError("release shelf writer policy is malformed; refusing mutation")
    if (
        policy.get("schemaVersion") == SERVER_WRITER_POLICY_SCHEMA
        and policy.get("mode") == SERVER_WRITER_POLICY_MODE
    ):
        raise ReleaseShelfError(
            "release shelf is owned by the staged HTTP server journal; filesystem mutation is forbidden"
        )
    raise ReleaseShelfError("release shelf writer policy is unsupported; refusing mutation")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_generation_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"g-{stamp}-{uuid.uuid4().hex[:16]}"


def new_activation_receipt_id() -> str:
    return f"activation-{uuid.uuid4().hex}"


def validate_generation_id(value: str) -> str:
    token = str(value or "").strip()
    if not SAFE_GENERATION_ID.fullmatch(token) or token in {".", ".."} or ".." in token:
        raise ReleaseShelfError(
            "generation ID must be a traversal-safe opaque token containing only "
            "letters, numbers, '.', '_', or '-'"
        )
    return token


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    # Cross-language release-shelf v1 contract: compact UTF-8 JSON, object keys
    # sorted ordinally, array order preserved, and non-ASCII/HTML-sensitive
    # characters emitted literally. This matches System.Text.Json with
    # JavaScriptEncoder.UnsafeRelaxedJsonEscaping.
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ReleaseShelfError(f"{label} is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseShelfError(f"{label} is unreadable or malformed: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise ReleaseShelfError(f"{label} must be a JSON object: {path}")
    return payload


def write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    mode: int | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        if mode is not None:
            os.fchmod(handle.fileno(), mode)
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _normalize_timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    token = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _manifest_identity(
    payload: dict[str, Any], label: str, *, require_published_at: bool = True
) -> tuple[str, str, str]:
    version = str(payload.get("releaseVersion") or payload.get("version") or "").strip()
    channel = str(payload.get("channelId") or payload.get("channel") or "").strip()
    published_at = str(payload.get("publishedAt") or payload.get("generatedAt") or "").strip()
    if not version or not channel or (require_published_at and not published_at):
        raise ReleaseShelfError(
            f"{label} must expose release version, channel, and publication timestamp"
        )
    return version, channel, published_at


_OMIT_MANIFEST_VALUE = object()


def _artifact_routes(
    payload: dict[str, Any], generation_id: str
) -> dict[str, dict[str, str | None]]:
    routes: dict[str, dict[str, str | None]] = {}
    for collection_name in ("artifacts", "downloads"):
        rows = payload.get(collection_name) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            artifact_id = str(row.get("artifactId") or row.get("id") or "").strip()
            file_name = str(row.get("fileName") or "").strip()
            if not file_name:
                raw_url = str(row.get("downloadUrl") or row.get("url") or "").strip()
                file_name = Path(urlsplit(raw_url).path).name if raw_url else ""
            if not artifact_id or not file_name:
                continue
            if Path(file_name).name != file_name:
                raise ReleaseShelfError(
                    f"manifest contains unsafe artifact fileName for {artifact_id}: {file_name}"
                )
            if not PORTABLE_INVENTORY_SEGMENT.fullmatch(file_name):
                raise ReleaseShelfError(
                    f"manifest contains non-portable artifact fileName for {artifact_id}: {file_name}"
                )
            if not SAFE_GENERATION_ID.fullmatch(artifact_id) or ".." in artifact_id:
                raise ReleaseShelfError(
                    f"manifest contains unsafe artifactId: {artifact_id}"
                )
            access_class = str(
                row.get("installAccessClass") or row.get("install_access_class") or ""
            ).strip().lower()
            primary_route = (
                f"/downloads/g/{generation_id}/files/{file_name}"
                if access_class == "open_public"
                else f"/downloads/g/{generation_id}/install/{quote(artifact_id, safe='')}"
            )
            payload_name = str(row.get("payloadFileName") or "").strip() or None
            if payload_name is not None and (
                Path(payload_name).name != payload_name
                or not PORTABLE_INVENTORY_SEGMENT.fullmatch(payload_name)
            ):
                raise ReleaseShelfError(
                    f"manifest contains unsafe payloadFileName for {artifact_id}: {payload_name}"
                )
            route: dict[str, str | None] = {
                "artifact_id": artifact_id,
                "file_name": file_name,
                "payload_file_name": payload_name,
                "primary": primary_route,
                "payload": (
                    f"/downloads/g/{generation_id}/install/{quote(artifact_id, safe='')}/payload"
                    if payload_name is not None
                    else None
                ),
                "metadata": (
                    f"/downloads/g/{generation_id}/install/{quote(artifact_id, safe='')}/metadata"
                    if payload_name is not None
                    else None
                ),
            }
            prior = routes.get(artifact_id)
            if prior is not None and prior != route:
                raise ReleaseShelfError(
                    f"manifest artifactId maps to multiple files: {artifact_id}"
                )
            routes[artifact_id] = route
    return routes


def _project_artifact_download_urls(
    payload: dict[str, Any], artifact_routes: dict[str, dict[str, str | None]]
) -> None:
    for collection_name in ("artifacts", "downloads"):
        rows = payload.get(collection_name) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            artifact_id = str(row.get("artifactId") or row.get("id") or "").strip()
            route = artifact_routes.get(artifact_id)
            if route is None:
                continue
            if "downloadUrl" in row:
                row["downloadUrl"] = route["primary"]
            if "url" in row:
                row["url"] = route["primary"]
            if "payloadDownloadUrl" in row and route["payload"] is not None:
                row["payloadDownloadUrl"] = route["payload"]


def _release_path(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        if "/downloads/" in value:
            raise ReleaseShelfError(f"malformed release URL: {value}") from exc
        return None
    if value.startswith("/downloads/"):
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "\\" in value or "%" in value:
            raise ReleaseShelfError(
                f"release URL must be a canonical unencoded site path without query, fragment, or backslash: {value}"
            )
        return parsed.path
    if (parsed.scheme or parsed.netloc) and parsed.path.startswith("/downloads/"):
        raise ReleaseShelfError(
            f"release URL must be a plain canonical site path, not an absolute URL: {value}"
        )
    if "%" in value and unquote(value).startswith("/downloads/"):
        raise ReleaseShelfError(
            f"release URL cannot hide a download path behind percent encoding: {value}"
        )
    return None


def _bind_artifact_route(
    value: str,
    artifact_routes: dict[str, dict[str, str | None]],
) -> str | object:
    artifact_id = value
    role = "primary"
    for suffix, candidate_role in (("/payload", "payload"), ("/metadata", "metadata")):
        if artifact_id.endswith(suffix):
            artifact_id = artifact_id[: -len(suffix)]
            role = candidate_role
            break
    route = artifact_routes.get(artifact_id)
    if route is None or route.get(role) is None:
        return _OMIT_MANIFEST_VALUE
    return str(route[role])


def _bind_file_route(
    file_name: str,
    artifact_routes: dict[str, dict[str, str | None]],
) -> str:
    if PurePosixPath(file_name).name != file_name:
        raise ReleaseShelfError(f"manifest file URL has a noncanonical basename: {file_name}")
    matches: list[tuple[dict[str, str | None], str]] = []
    for route in artifact_routes.values():
        if route["file_name"] == file_name:
            matches.append((route, "primary"))
        if route["payload_file_name"] == file_name:
            matches.append((route, "payload"))
        if route["payload_file_name"] is not None and f'{route["payload_file_name"]}.json' == file_name:
            matches.append((route, "metadata"))
    if len(matches) != 1:
        raise ReleaseShelfError(f"manifest file URL references unknown or ambiguous bytes: {file_name}")
    route, role = matches[0]
    bound = route.get(role)
    if bound is None:
        raise ReleaseShelfError(f"manifest file URL references unavailable bytes: {file_name}")
    return str(bound)


def _rewrite_release_url(
    value: str,
    generation_id: str,
    artifact_routes: dict[str, dict[str, str | None]],
) -> str | object:
    path = _release_path(value)
    if path is None:
        return value
    generation_prefix = f"/downloads/g/{generation_id}/"
    relative: str
    if path.startswith("/downloads/g/"):
        remainder = path[len("/downloads/g/") :]
        prior_generation, separator, relative = remainder.partition("/")
        if not separator or not prior_generation or not relative:
            raise ReleaseShelfError(f"malformed generation-bound download URL: {value}")
    else:
        relative = path[len("/downloads/") :]

    if relative.startswith("files/"):
        return _bind_file_route(relative[len("files/") :], artifact_routes)
    for dispatch_root in ("install", "get", "file"):
        prefix = f"{dispatch_root}/"
        if relative.startswith(prefix):
            return _bind_artifact_route(relative[len(prefix) :], artifact_routes)
    if relative in (CANONICAL_MANIFEST, COMPATIBILITY_MANIFEST):
        return generation_prefix + relative
    if any(relative.startswith(f"{root}/") for root in ("proof", "startup-smoke", "release-evidence")):
        return generation_prefix + relative
    raise ReleaseShelfError(f"manifest retains an unsupported release URL: {value}")


def _rewrite_manifest_value(
    value: Any,
    generation_id: str,
    artifact_routes: dict[str, dict[str, str | None]],
    path: tuple[str, ...] = (),
) -> Any:
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, item in value.items():
            if key in PROOF_ROUTE_KEYS:
                if path == ("releaseProof",) and key == "proofRoutes":
                    rewritten[key] = copy.deepcopy(item)
                    continue
                if key == "proof_routes" or (path and path[-1] == "releaseProof"):
                    raise ReleaseShelfError(
                        "Registry generation projection rejects nested releaseProof.proofRoutes lookalikes and noncanonical aliases"
                    )
            projected = _rewrite_manifest_value(
                item, generation_id, artifact_routes, path + (key,)
            )
            if projected is not _OMIT_MANIFEST_VALUE:
                rewritten[key] = projected
        return rewritten
    if isinstance(value, list):
        rewritten_items = [
            _rewrite_manifest_value(item, generation_id, artifact_routes, path + ("[]",))
            for item in value
        ]
        return [item for item in rewritten_items if item is not _OMIT_MANIFEST_VALUE]
    if isinstance(value, str):
        return _rewrite_release_url(value, generation_id, artifact_routes)
    return value


def normalize_manifest(
    path: Path,
    generation_id: str,
    artifact_routes: dict[str, dict[str, str | None]] | None = None,
) -> dict[str, Any]:
    payload = read_json_object(path, path.name)
    artifact_routes = artifact_routes or _artifact_routes(payload, generation_id)
    for source_value in _walk_strings(payload):
        _rewrite_release_url(source_value, generation_id, artifact_routes)
    source = copy.deepcopy(payload)
    _project_artifact_download_urls(source, artifact_routes)
    normalized = _rewrite_manifest_value(
        source, generation_id, artifact_routes
    )
    assert isinstance(normalized, dict)
    normalized["generationId"] = generation_id
    path.write_bytes(canonical_json_bytes(normalized) + b"\n")
    return normalized


def project_manifest_pair(
    canonical_path: Path,
    compatibility_path: Path,
    generation_id: str,
) -> dict[str, Any]:
    """Atomically project both incoming manifests to one caller-declared generation.

    HTTP promotion uses the same normalization contract server-side. Projecting the
    pair before upload lets Registry authority bind the exact bytes that the server
    will seal, without copying the much larger artifact tree.
    """

    generation_id = validate_generation_id(generation_id)
    for path, label in (
        (canonical_path, CANONICAL_MANIFEST),
        (compatibility_path, COMPATIBILITY_MANIFEST),
    ):
        if path.is_symlink() or not path.is_file():
            raise ReleaseShelfError(f"{label} must be a regular non-symlink file: {path}")

    canonical_source = read_json_object(canonical_path, CANONICAL_MANIFEST)
    compatibility_source = read_json_object(
        compatibility_path, COMPATIBILITY_MANIFEST
    )
    canonical_identity = _manifest_identity(canonical_source, CANONICAL_MANIFEST)
    compatibility_identity = _manifest_identity(
        compatibility_source, COMPATIBILITY_MANIFEST
    )
    if canonical_identity[:2] != compatibility_identity[:2] or (
        canonical_identity[2]
        and compatibility_identity[2]
        and _normalize_timestamp(canonical_identity[2])
        != _normalize_timestamp(compatibility_identity[2])
    ):
        raise ReleaseShelfError(
            "canonical and compatibility manifests must expose the same release identity"
        )

    artifact_routes = _artifact_routes(compatibility_source, generation_id)
    temporary_paths: list[Path] = []
    try:
        projected: dict[str, tuple[Path, dict[str, Any]]] = {}
        for destination, label in (
            (canonical_path, CANONICAL_MANIFEST),
            (compatibility_path, COMPATIBILITY_MANIFEST),
        ):
            descriptor, raw_temporary = tempfile.mkstemp(
                prefix=f".{destination.name}.generation-",
                dir=destination.parent,
            )
            temporary = Path(raw_temporary)
            temporary_paths.append(temporary)
            try:
                os.fchmod(descriptor, 0o600)
            except Exception:
                os.close(descriptor)
                raise
            with os.fdopen(descriptor, "wb") as handle:
                source_payload = (
                    canonical_source
                    if label == CANONICAL_MANIFEST
                    else compatibility_source
                )
                handle.write(canonical_json_bytes(source_payload) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            normalized = normalize_manifest(
                temporary,
                generation_id,
                artifact_routes,
            )
            validate_manifest_routes(normalized, generation_id, label)
            projected[label] = (temporary, normalized)

        projected_canonical_identity = _manifest_identity(
            projected[CANONICAL_MANIFEST][1], CANONICAL_MANIFEST
        )
        projected_compatibility_identity = _manifest_identity(
            projected[COMPATIBILITY_MANIFEST][1], COMPATIBILITY_MANIFEST
        )
        if projected_canonical_identity != projected_compatibility_identity:
            raise ReleaseShelfError(
                "generation-projected manifests changed or contradicted release identity"
            )

        os.replace(projected[CANONICAL_MANIFEST][0], canonical_path)
        temporary_paths.remove(projected[CANONICAL_MANIFEST][0])
        os.replace(projected[COMPATIBILITY_MANIFEST][0], compatibility_path)
        temporary_paths.remove(projected[COMPATIBILITY_MANIFEST][0])
        for parent in {canonical_path.parent, compatibility_path.parent}:
            descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        return {
            "generationId": generation_id,
            "releaseVersion": projected_canonical_identity[0],
            "channel": projected_canonical_identity[1],
            "publishedAt": projected_canonical_identity[2],
            "canonicalManifestSha256": sha256_file(canonical_path),
            "compatibilityManifestSha256": sha256_file(compatibility_path),
        }
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)


def _walk_strings(value: Any, path: tuple[str, ...] = ()) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in PROOF_ROUTE_KEYS:
                if path == ("releaseProof",) and key == "proofRoutes":
                    continue
                if key == "proof_routes" or (path and path[-1] == "releaseProof"):
                    raise ReleaseShelfError(
                        "authoritative manifest contains a nested releaseProof.proofRoutes lookalike or noncanonical alias"
                    )
            yield from _walk_strings(item, path + (key,))
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item, path + ("[]",))
    elif isinstance(value, str):
        yield value


def validate_manifest_routes(payload: dict[str, Any], generation_id: str, label: str) -> None:
    if payload.get("generationId") != generation_id:
        raise ReleaseShelfError(f"{label} generationId mismatch")
    expected_prefix = f"/downloads/g/{generation_id}/"
    for value in _walk_strings(payload):
        path = _release_path(value)
        if path is None:
            continue
        if not path.startswith(expected_prefix):
            raise ReleaseShelfError(f"{label} retains non-generation download URL: {value}")
        relative_text = path[len(expected_prefix) :]
        relative = PurePosixPath(relative_text)
        if (
            not relative_text
            or not relative.parts
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ReleaseShelfError(f"{label} has unsafe generation URL: {value}")
        invalid_root_shape = relative.parts[0] not in ALLOWED_GENERATION_ROUTE_ROOTS
        if relative.parts[0] == "install":
            invalid_root_shape = len(relative.parts) not in (2, 3) or (
                len(relative.parts) == 3 and relative.parts[2] not in ("payload", "metadata")
            )
        elif relative.parts[0] in (CANONICAL_MANIFEST, COMPATIBILITY_MANIFEST):
            invalid_root_shape = len(relative.parts) != 1
        elif relative.parts[0] == "files":
            invalid_root_shape = len(relative.parts) != 2
        elif relative.parts[0] in ("proof", "startup-smoke", "release-evidence"):
            invalid_root_shape = len(relative.parts) < 2
        if invalid_root_shape:
            raise ReleaseShelfError(f"{label} has unsafe generation URL: {value}")


def _copy_without_symlinks(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ReleaseShelfError(f"candidate entries must not be symbolic links: {source}")
    if source.is_dir():
        for entry in source.rglob("*"):
            if entry.is_symlink():
                raise ReleaseShelfError(f"candidate entries must not be symbolic links: {entry}")
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def copy_candidate(source_root: Path, generation_root: Path) -> None:
    if not source_root.is_dir():
        raise ReleaseShelfError(f"candidate root is missing: {source_root}")
    if generation_root.exists():
        raise ReleaseShelfError(f"generation destination already exists: {generation_root}")
    generation_root.mkdir(parents=True)
    for name in sorted(COPYABLE_FILES):
        source = source_root / name
        if source.exists():
            if not source.is_file() or source.is_symlink():
                raise ReleaseShelfError(f"candidate file is invalid: {source}")
            _copy_without_symlinks(source, generation_root / name)
    for name in sorted(COPYABLE_DIRECTORIES):
        source = source_root / name
        if source.exists():
            if not source.is_dir() or source.is_symlink():
                raise ReleaseShelfError(f"candidate directory is invalid: {source}")
            _copy_without_symlinks(source, generation_root / name)
    for required in (CANONICAL_MANIFEST, COMPATIBILITY_MANIFEST):
        if not (generation_root / required).is_file():
            raise ReleaseShelfError(f"candidate is missing required manifest: {required}")
    if not (generation_root / "files").is_dir():
        raise ReleaseShelfError("candidate is missing required files directory")


def _normalize_public_generation_modes(generation_root: Path) -> None:
    """Seal one unpublished generation with the public runtime mode contract."""
    try:
        root_metadata = generation_root.lstat()
    except OSError as exc:
        raise ReleaseShelfError(
            f"generation root is unavailable: {generation_root}"
        ) from exc
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
    ):
        raise ReleaseShelfError(f"generation root is unsafe: {generation_root}")
    generation_root.chmod(SEALED_DIRECTORY_MODE)
    for path in sorted(generation_root.rglob("*"), key=lambda item: item.as_posix()):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ReleaseShelfError(
                f"generation entries must not be symbolic links: {path}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            path.chmod(SEALED_DIRECTORY_MODE)
        elif stat.S_ISREG(metadata.st_mode):
            relative = path.relative_to(generation_root).as_posix()
            path.chmod(
                PUBLIC_METADATA_FILE_MODE
                if relative in PUBLIC_GENERATION_METADATA
                else SEALED_FILE_MODE
            )
        else:
            raise ReleaseShelfError(f"generation contains a special entry: {path}")


def _verify_public_generation_modes(generation_root: Path) -> None:
    try:
        root_metadata = generation_root.lstat()
    except OSError as exc:
        raise ReleaseShelfError(
            f"generation root is unavailable: {generation_root}"
        ) from exc
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_IMODE(root_metadata.st_mode) != SEALED_DIRECTORY_MODE
    ):
        raise ReleaseShelfError(
            "generation root does not satisfy the public directory mode contract"
        )
    for path in sorted(generation_root.rglob("*"), key=lambda item: item.as_posix()):
        metadata = path.lstat()
        relative = path.relative_to(generation_root).as_posix()
        if stat.S_ISLNK(metadata.st_mode):
            raise ReleaseShelfError(
                f"generation entries must not be symbolic links: {relative}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            expected_mode = SEALED_DIRECTORY_MODE
        elif stat.S_ISREG(metadata.st_mode):
            expected_mode = (
                PUBLIC_METADATA_FILE_MODE
                if relative in PUBLIC_GENERATION_METADATA
                else SEALED_FILE_MODE
            )
        else:
            raise ReleaseShelfError(
                f"generation contains a special entry: {relative}"
            )
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise ReleaseShelfError(
                f"generation entry has non-public mode: {relative}"
            )


def _verify_artifact_row(row: dict[str, Any], files_root: Path, label: str) -> None:
    file_name = str(row.get("fileName") or "").strip()
    if not file_name:
        url = str(row.get("downloadUrl") or row.get("url") or "").strip()
        file_name = Path(urlsplit(url).path).name if url else ""
    if not file_name:
        return
    if Path(file_name).name != file_name:
        raise ReleaseShelfError(f"{label} contains unsafe artifact fileName: {file_name}")
    artifact_path = files_root / file_name
    if not artifact_path.is_file():
        raise ReleaseShelfError(f"{label} references missing artifact: {file_name}")
    expected_size = int(row.get("sizeBytes") or 0)
    if expected_size and artifact_path.stat().st_size != expected_size:
        raise ReleaseShelfError(f"{label} size mismatch for {file_name}")
    expected_sha = str(row.get("sha256") or "").strip().lower()
    if expected_sha and sha256_file(artifact_path) != expected_sha:
        raise ReleaseShelfError(f"{label} SHA-256 mismatch for {file_name}")
    payload_name = str(row.get("payloadFileName") or "").strip()
    if payload_name:
        if Path(payload_name).name != payload_name:
            raise ReleaseShelfError(f"{label} contains unsafe payloadFileName: {payload_name}")
        payload_path = files_root / payload_name
        if not payload_path.is_file():
            raise ReleaseShelfError(f"{label} references missing payload: {payload_name}")
        expected_payload_size = int(row.get("payloadSizeBytes") or 0)
        if expected_payload_size and payload_path.stat().st_size != expected_payload_size:
            raise ReleaseShelfError(f"{label} size mismatch for {payload_name}")
        expected_payload_sha = str(row.get("payloadSha256") or "").strip().lower()
        if expected_payload_sha and sha256_file(payload_path) != expected_payload_sha:
            raise ReleaseShelfError(f"{label} SHA-256 mismatch for {payload_name}")


def validate_manifest_artifacts(
    canonical: dict[str, Any], compatibility: dict[str, Any], generation_root: Path
) -> None:
    files_root = generation_root / "files"
    for label, rows in (
        (CANONICAL_MANIFEST, canonical.get("artifacts") or []),
        (COMPATIBILITY_MANIFEST, compatibility.get("downloads") or []),
    ):
        if not isinstance(rows, list):
            raise ReleaseShelfError(f"{label} artifact collection must be a list")
        for row in rows:
            if not isinstance(row, dict):
                raise ReleaseShelfError(f"{label} artifact rows must be objects")
            _verify_artifact_row(row, files_root, label)


def validate_files_are_manifest_bound(
    canonical: dict[str, Any], compatibility: dict[str, Any], generation_root: Path
) -> None:
    reference_keys = {
        "fileName",
        "payloadFileName",
        "payloadMetadataFileName",
        "sourceArchiveFileName",
        "pkgbuildFileName",
        "srcinfoFileName",
        "upstreamArtifactFileName",
    }
    referenced: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in reference_keys and isinstance(item, str) and item.strip():
                    file_name = item.strip()
                    if Path(file_name).name != file_name:
                        raise ReleaseShelfError(
                            f"manifest file reference must be one exact files/ basename: {file_name}"
                        )
                    referenced.add(file_name)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(canonical)
    collect(compatibility)
    aur_path = generation_root / "aur-packages.json"
    if aur_path.is_file():
        collect(read_json_object(aur_path, "aur-packages.json"))

    files_root = generation_root / "files"
    actual: set[str] = set()
    for path in sorted(files_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ReleaseShelfError(f"files/ entries must not be symbolic links: {path}")
        if path.is_file():
            actual.add(path.relative_to(files_root).as_posix())

    # Windows payload metadata is a contracted sibling of payloadFileName even in
    # older manifests that predate payloadMetadataFileName.
    for file_name in tuple(referenced):
        metadata_name = f"{file_name}.json"
        if metadata_name in actual:
            referenced.add(metadata_name)

    unreferenced = sorted(actual - referenced)
    missing = sorted(referenced - actual)
    if unreferenced:
        raise ReleaseShelfError(
            "generation files/ contains unreferenced bytes: " + ", ".join(unreferenced)
        )
    if missing:
        raise ReleaseShelfError(
            "generation manifests reference missing files/: " + ", ".join(missing)
        )


def build_inventory(generation_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    casefolded_paths: set[str] = set()
    for path in sorted(generation_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ReleaseShelfError(f"generation entries must not be symbolic links: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(generation_root).as_posix()
        if relative in {
            ACTIVATION_CANDIDATE,
            CANONICAL_MANIFEST,
            COMPATIBILITY_MANIFEST,
        }:
            continue
        if "\n" in relative or "\r" in relative or "\t" in relative:
            raise ReleaseShelfError(f"generation path contains unsafe control characters: {relative!r}")
        if any(
            not PORTABLE_INVENTORY_SEGMENT.fullmatch(segment)
            for segment in relative.split("/")
        ):
            raise ReleaseShelfError(
                f"generation inventory path is not portable ASCII: {relative!r}"
            )
        folded = relative.casefold()
        if folded in casefolded_paths:
            raise ReleaseShelfError(
                f"generation inventory contains a case-colliding path: {relative}"
            )
        casefolded_paths.add(folded)
        rows.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
            }
        )
    return rows


def inventory_digest(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def fsync_tree(root: Path) -> None:
    directories = [root]
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        elif path.is_dir():
            directories.append(path)
    for directory in reversed(directories):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def materialize_generation(
    candidate_root: Path,
    generation_root: Path,
    generation_id: str,
    *,
    activated_at: str | None = None,
    activation_receipt_id: str | None = None,
) -> dict[str, Any]:
    generation_id = validate_generation_id(generation_id)
    copy_candidate(candidate_root, generation_root)
    compatibility_source = read_json_object(
        generation_root / COMPATIBILITY_MANIFEST,
        COMPATIBILITY_MANIFEST,
    )
    artifact_routes = _artifact_routes(compatibility_source, generation_id)
    canonical = normalize_manifest(
        generation_root / CANONICAL_MANIFEST,
        generation_id,
        artifact_routes,
    )
    compatibility = normalize_manifest(
        generation_root / COMPATIBILITY_MANIFEST,
        generation_id,
        artifact_routes,
    )
    validate_manifest_routes(canonical, generation_id, CANONICAL_MANIFEST)
    validate_manifest_routes(compatibility, generation_id, COMPATIBILITY_MANIFEST)
    canonical_identity = _manifest_identity(canonical, CANONICAL_MANIFEST)
    compatibility_identity = _manifest_identity(
        compatibility, COMPATIBILITY_MANIFEST, require_published_at=False
    )
    if canonical_identity[:2] != compatibility_identity[:2] or (
        compatibility_identity[2]
        and _normalize_timestamp(canonical_identity[2])
        != _normalize_timestamp(compatibility_identity[2])
    ):
        raise ReleaseShelfError(
            "canonical and compatibility manifests must expose the same release identity"
        )
    validate_manifest_artifacts(canonical, compatibility, generation_root)
    validate_files_are_manifest_bound(canonical, compatibility, generation_root)
    inventory = build_inventory(generation_root)
    if not inventory:
        raise ReleaseShelfError("activation candidate inventory must not be empty")
    activated_at = str(activated_at or utc_now()).strip()
    activation_receipt_id = str(activation_receipt_id or new_activation_receipt_id()).strip()
    if not activated_at or not activation_receipt_id:
        raise ReleaseShelfError("activation timestamp and receipt ID are required")
    pointer: dict[str, Any] = {
        "schemaVersion": POINTER_SCHEMA,
        "generationId": generation_id,
        "releaseVersion": canonical_identity[0],
        "channel": canonical_identity[1],
        "publishedAt": canonical_identity[2],
        "manifests": {
            "canonical": {
                "path": f"/downloads/g/{generation_id}/{CANONICAL_MANIFEST}",
                "sha256": sha256_file(generation_root / CANONICAL_MANIFEST),
            },
            "compatibility": {
                "path": f"/downloads/g/{generation_id}/{COMPATIBILITY_MANIFEST}",
                "sha256": sha256_file(generation_root / COMPATIBILITY_MANIFEST),
            },
        },
        "inventoryDigest": f"sha256:{inventory_digest(inventory)}",
        "activatedAt": activated_at,
        "activationReceiptId": activation_receipt_id,
    }
    candidate_record = {
        "schemaVersion": ACTIVATION_CANDIDATE_SCHEMA,
        "generationId": generation_id,
        "releaseVersion": pointer["releaseVersion"],
        "channel": pointer["channel"],
        "publishedAt": pointer["publishedAt"],
        "manifests": copy.deepcopy(pointer["manifests"]),
        "inventoryDigest": pointer["inventoryDigest"],
        "inventory": inventory,
    }
    write_json(
        generation_root / ACTIVATION_CANDIDATE,
        candidate_record,
        mode=PUBLIC_METADATA_FILE_MODE,
    )
    _normalize_public_generation_modes(generation_root)
    verify_generation(generation_root, pointer)
    fsync_tree(generation_root)
    return pointer


def verify_generation(
    generation_root: Path,
    pointer: dict[str, Any],
    *,
    require_sealed_modes: bool = True,
) -> None:
    generation_id = validate_generation_id(str(pointer.get("generationId") or ""))
    if generation_root.name != generation_id:
        raise ReleaseShelfError(
            f"generation directory {generation_root.name!r} does not match pointer {generation_id!r}"
        )
    if pointer.get("schemaVersion") != POINTER_SCHEMA:
        raise ReleaseShelfError("unsupported release shelf pointer schemaVersion")
    if require_sealed_modes:
        _verify_public_generation_modes(generation_root)
    candidate = read_json_object(
        generation_root / ACTIVATION_CANDIDATE, "activation candidate"
    )
    if candidate.get("generationId") != generation_id:
        raise ReleaseShelfError("activation candidate generationId mismatch")
    if candidate.get("schemaVersion") != ACTIVATION_CANDIDATE_SCHEMA:
        raise ReleaseShelfError("unsupported activation candidate schemaVersion")
    for field in ("releaseVersion", "channel", "publishedAt", "inventoryDigest"):
        if candidate.get(field) != pointer.get(field):
            raise ReleaseShelfError(
                f"activation candidate {field} disagrees with pointer"
            )
    if candidate.get("manifests") != pointer.get("manifests"):
        raise ReleaseShelfError("activation candidate manifest bindings disagree with pointer")
    canonical = read_json_object(generation_root / CANONICAL_MANIFEST, CANONICAL_MANIFEST)
    compatibility = read_json_object(
        generation_root / COMPATIBILITY_MANIFEST, COMPATIBILITY_MANIFEST
    )
    for payload, label in (
        (canonical, CANONICAL_MANIFEST),
        (compatibility, COMPATIBILITY_MANIFEST),
    ):
        if payload.get("generationId") != generation_id:
            raise ReleaseShelfError(f"{label} generationId mismatch")
        validate_manifest_routes(payload, generation_id, label)
    validate_manifest_artifacts(canonical, compatibility, generation_root)
    canonical_identity = _manifest_identity(canonical, CANONICAL_MANIFEST)
    compatibility_identity = _manifest_identity(
        compatibility, COMPATIBILITY_MANIFEST, require_published_at=False
    )
    pointer_identity = (
        str(pointer.get("releaseVersion") or "").strip(),
        str(pointer.get("channel") or "").strip(),
        str(pointer.get("publishedAt") or "").strip(),
    )
    if canonical_identity[:2] != pointer_identity[:2] or _normalize_timestamp(
        canonical_identity[2]
    ) != _normalize_timestamp(pointer_identity[2]):
        raise ReleaseShelfError("canonical manifest release identity disagrees with pointer")
    if compatibility_identity[:2] != pointer_identity[:2] or (
        compatibility_identity[2]
        and _normalize_timestamp(compatibility_identity[2])
        != _normalize_timestamp(pointer_identity[2])
    ):
        raise ReleaseShelfError("compatibility manifest release identity disagrees with pointer")
    expected_manifests = pointer.get("manifests")
    if not isinstance(expected_manifests, dict) or set(expected_manifests) != {
        "canonical",
        "compatibility",
    }:
        raise ReleaseShelfError("pointer manifests must bind canonical and compatibility")
    for key, name in (
        ("canonical", CANONICAL_MANIFEST),
        ("compatibility", COMPATIBILITY_MANIFEST),
    ):
        binding = expected_manifests.get(key)
        if not isinstance(binding, dict):
            raise ReleaseShelfError(f"pointer {key} manifest binding is malformed")
        if binding.get("path") != f"/downloads/g/{generation_id}/{name}":
            raise ReleaseShelfError(f"pointer {key} manifest path is not generation-bound")
        if binding.get("sha256") != sha256_file(generation_root / name):
            raise ReleaseShelfError(f"pointer {key} manifest SHA-256 does not match generation bytes")
    inventory = build_inventory(generation_root)
    if candidate.get("inventory") != inventory:
        raise ReleaseShelfError("activation candidate inventory does not match generation bytes")
    actual_inventory_digest = inventory_digest(inventory)
    if pointer.get("inventoryDigest") != f"sha256:{actual_inventory_digest}":
        raise ReleaseShelfError("pointer inventoryDigest does not match generation bytes")
    if candidate.get("inventoryDigest") != f"sha256:{actual_inventory_digest}":
        raise ReleaseShelfError("activation candidate inventoryDigest does not match generation bytes")


def validate_pointer_payload(pointer: dict[str, Any]) -> dict[str, Any]:
    validate_generation_id(str(pointer.get("generationId") or ""))
    if pointer.get("schemaVersion") != POINTER_SCHEMA:
        raise ReleaseShelfError("unsupported release shelf pointer schemaVersion")
    for field in (
        "releaseVersion",
        "channel",
        "publishedAt",
        "activatedAt",
        "activationReceiptId",
    ):
        if not isinstance(pointer.get(field), str) or not str(pointer[field]).strip():
            raise ReleaseShelfError(f"release shelf pointer is missing {field}")
    inventory_binding = str(pointer.get("inventoryDigest") or "")
    if not inventory_binding.startswith("sha256:") or not SHA256_PATTERN.fullmatch(
        inventory_binding[len("sha256:") :]
    ):
        raise ReleaseShelfError("release shelf pointer inventoryDigest is malformed")
    generation_id = str(pointer["generationId"])
    manifests = pointer.get("manifests")
    if not isinstance(manifests, dict) or set(manifests) != {"canonical", "compatibility"}:
        raise ReleaseShelfError("release shelf pointer manifest bindings are malformed")
    for key, name in (
        ("canonical", CANONICAL_MANIFEST),
        ("compatibility", COMPATIBILITY_MANIFEST),
    ):
        binding = manifests.get(key)
        if not isinstance(binding, dict):
            raise ReleaseShelfError(f"release shelf pointer {key} binding is malformed")
        if binding.get("path") != f"/downloads/g/{generation_id}/{name}":
            raise ReleaseShelfError(f"release shelf pointer {key} path is not generation-bound")
        if not SHA256_PATTERN.fullmatch(str(binding.get("sha256") or "")):
            raise ReleaseShelfError(f"release shelf pointer {key} SHA-256 is malformed")
    return pointer


def load_pointer(path: Path) -> dict[str, Any]:
    return validate_pointer_payload(read_json_object(path, "release shelf pointer"))


def _load_public_pointer(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ReleaseShelfError("release shelf pointer is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != PUBLIC_METADATA_FILE_MODE
    ):
        raise ReleaseShelfError(
            "release shelf pointer does not satisfy the public file mode contract"
        )
    return load_pointer(path)


def resolve_shelf_root(shelf_root: Path) -> tuple[str, Path, dict[str, Any] | None]:
    marker_exists = (shelf_root / LAYOUT_MARKER).is_file()
    pointer_path = shelf_root / CURRENT_POINTER
    pointer_exists = pointer_path.is_file()
    if pointer_exists:
        pointer = _load_public_pointer(pointer_path)
        generation_id = str(pointer["generationId"])
        generation_root = shelf_root / GENERATIONS_DIRECTORY / generation_id
        if not generation_root.is_dir():
            raise ReleaseShelfError(f"current generation is missing: {generation_root}")
        verify_generation(generation_root, pointer)
        return "generation", generation_root, pointer
    if marker_exists:
        raise ReleaseShelfError(
            f"layout marker exists without a valid {CURRENT_POINTER}; refusing legacy fallback"
        )
    return "legacy", shelf_root, None


@contextlib.contextmanager
def promotion_lock(shelf_root: Path) -> Iterator[_PromotionLockLease]:
    shelf_root.mkdir(parents=True, exist_ok=True)
    shelf_root = shelf_root.resolve(strict=True)
    lock_path = shelf_root / PROMOTION_LOCK
    flags = (
        os.O_RDWR
        | os.O_APPEND
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(lock_path, flags, SHARED_CONTROL_FILE_MODE)
    with os.fdopen(descriptor, "a+b") as handle:
        os.fchmod(handle.fileno(), SHARED_CONTROL_FILE_MODE)
        opened = os.fstat(handle.fileno())
        linked = lock_path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(linked.st_mode)
            or (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != SHARED_CONTROL_FILE_MODE
        ):
            raise ReleaseShelfError("release shelf promotion lock is unsafe")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        lease = _PromotionLockLease(
            handle,
            lock_path,
        )
        try:
            yield lease
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        os.fchmod(descriptor, PUBLIC_METADATA_FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _atomic_write_layout_marker(marker: Path) -> None:
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{marker.name}.", dir=marker.parent)
    temp_path = Path(raw_temp)
    try:
        os.fchmod(descriptor, PUBLIC_METADATA_FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("v1\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, marker)
    finally:
        temp_path.unlink(missing_ok=True)


def _create_layout_marker(shelf_root: Path) -> None:
    _atomic_write_layout_marker(shelf_root / LAYOUT_MARKER)


def _require_layout_marker(
    shelf_root: Path,
    *,
    require_public_mode: bool = True,
) -> None:
    marker = shelf_root / LAYOUT_MARKER
    try:
        metadata = marker.lstat()
        body = marker.read_bytes()
    except OSError as exc:
        raise ReleaseShelfError("release shelf layout marker is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_nlink != 1
        or (
            require_public_mode
            and stat.S_IMODE(metadata.st_mode) != PUBLIC_METADATA_FILE_MODE
        )
        or body != b"v1\n"
    ):
        raise ReleaseShelfError("release shelf layout marker is invalid")


def _repair_authenticated_layout_modes(
    shelf_root: Path,
    pointer: dict[str, Any],
    *,
    publish_pointer: bool,
) -> None:
    """Repair only a byte-authenticated layout produced by the pre-mode writer."""
    generation_id = validate_generation_id(str(pointer.get("generationId") or ""))
    generation_root = shelf_root / GENERATIONS_DIRECTORY / generation_id
    verify_generation(
        generation_root,
        pointer,
        require_sealed_modes=False,
    )
    marker = shelf_root / LAYOUT_MARKER
    if marker.exists() or marker.is_symlink():
        _require_layout_marker(shelf_root, require_public_mode=False)
    _normalize_public_generation_modes(generation_root)
    shelf_root.chmod(SHARED_DIRECTORY_MODE)
    generations_root = shelf_root / GENERATIONS_DIRECTORY
    generations_root.chmod(SHARED_DIRECTORY_MODE)
    if marker.exists():
        _atomic_write_layout_marker(marker)
    if publish_pointer:
        _atomic_write_json(shelf_root / CURRENT_POINTER, pointer)
    verify_generation(generation_root, pointer)
    if marker.exists():
        _require_layout_marker(shelf_root)
    if publish_pointer:
        _load_public_pointer(shelf_root / CURRENT_POINTER)


def _tree_fingerprint(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise ReleaseShelfError(f"activation tree is unsafe: {root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ReleaseShelfError(
                f"activation tree contains a symbolic link: {relative}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            rows.append({"path": relative, "type": "directory"})
        elif stat.S_ISREG(metadata.st_mode):
            rows.append(
                {
                    "path": relative,
                    "type": "file",
                    "sha256": sha256_file(path),
                    "sizeBytes": metadata.st_size,
                }
            )
        else:
            raise ReleaseShelfError(
                f"activation tree contains a special entry: {relative}"
            )
    return rows


def _validate_prepared_stage_for_intent(
    stage_root: Path,
    *,
    candidate_root: Path,
    shelf_root: Path,
    generation_id: str,
    activation_receipt_id: str,
) -> dict[str, Any]:
    if stage_root.is_symlink() or not stage_root.is_dir():
        raise ReleaseShelfError("release shelf activation stage is unsafe")
    pointer = _load_public_pointer(stage_root / CURRENT_POINTER)
    if (
        pointer.get("generationId") != generation_id
        or pointer.get("activationReceiptId") != activation_receipt_id
    ):
        raise ReleaseShelfError(
            "release shelf activation stage belongs to a different intent"
        )
    entries = {item.name for item in stage_root.iterdir()}
    if entries != {CURRENT_POINTER, GENERATIONS_DIRECTORY, LAYOUT_MARKER}:
        raise ReleaseShelfError(
            "release shelf activation stage closure is invalid"
        )
    _require_layout_marker(stage_root)
    expected_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{shelf_root.name}-release-shelf-verify-",
            dir=shelf_root.parent,
        )
    )
    try:
        expected = expected_parent / "prepared"
        prepare_layout(
            candidate_root,
            expected,
            generation_id=generation_id,
            activated_at=str(pointer["activatedAt"]),
            activation_receipt_id=activation_receipt_id,
        )
        expected_pointer = _load_public_pointer(expected / CURRENT_POINTER)
        if pointer != expected_pointer:
            raise ReleaseShelfError(
                "release shelf activation stage pointer differs from pinned candidate"
            )
        staged_generation = (
            stage_root / GENERATIONS_DIRECTORY / generation_id
        )
        final_generation = (
            shelf_root / GENERATIONS_DIRECTORY / generation_id
        )
        staged_exists = staged_generation.is_dir() and not staged_generation.is_symlink()
        final_exists = final_generation.is_dir() and not final_generation.is_symlink()
        if staged_exists and final_exists:
            raise ReleaseShelfError(
                "release shelf activation stage has duplicate generation closure"
            )
        if staged_exists:
            observed_generation = staged_generation
        elif final_exists:
            if any((stage_root / GENERATIONS_DIRECTORY).iterdir()):
                raise ReleaseShelfError(
                    "release shelf activation stage has an ambiguous generation"
                )
            observed_generation = final_generation
        else:
            raise ReleaseShelfError(
                "release shelf activation stage lost its pinned generation"
            )
        expected_generation = expected / GENERATIONS_DIRECTORY / generation_id
        if _tree_fingerprint(observed_generation) != _tree_fingerprint(
            expected_generation
        ):
            raise ReleaseShelfError(
                "release shelf activation generation differs from pinned candidate"
            )
        verify_generation(
            observed_generation,
            pointer,
            require_sealed_modes=False,
        )
        _normalize_public_generation_modes(observed_generation)
        verify_generation(observed_generation, pointer)
        return pointer
    finally:
        shutil.rmtree(expected_parent, ignore_errors=True)


def reconcile_activation_stage_residue(
    candidate_root: Path,
    shelf_root: Path,
    *,
    generation_id: str,
    activation_receipt_id: str,
) -> Path | None:
    """Return the one exact same-intent stage; reject every unknown residue."""
    generation_id = validate_generation_id(generation_id)
    activation_receipt_id = validate_generation_id(activation_receipt_id)
    matching: list[Path] = []
    for path in sorted(shelf_root.iterdir(), key=lambda item: item.name):
        if not path.name.startswith(ACTIVATION_STAGE_PREFIX):
            continue
        try:
            _validate_prepared_stage_for_intent(
                path,
                candidate_root=candidate_root,
                shelf_root=shelf_root,
                generation_id=generation_id,
                activation_receipt_id=activation_receipt_id,
            )
        except (OSError, ReleaseShelfError) as exc:
            raise ReleaseShelfError(
                f"unknown release shelf activation stage residue: {path.name}"
            ) from exc
        matching.append(path)
    if len(matching) > 1:
        raise ReleaseShelfError(
            "multiple same-intent release shelf activation stages are ambiguous"
        )
    return matching[0] if matching else None


def _validate_committed_activation_for_intent(
    candidate_root: Path,
    shelf_root: Path,
    *,
    generation_id: str,
    activation_receipt_id: str,
) -> dict[str, Any]:
    pointer = load_pointer(shelf_root / CURRENT_POINTER)
    if (
        pointer.get("generationId") != generation_id
        or pointer.get("activationReceiptId") != activation_receipt_id
    ):
        raise ReleaseShelfError(
            "committed release shelf activation belongs to a different intent"
        )
    _require_layout_marker(shelf_root, require_public_mode=False)
    final_generation = (
        shelf_root / GENERATIONS_DIRECTORY / generation_id
    )
    verify_generation(
        final_generation,
        pointer,
        require_sealed_modes=False,
    )
    expected_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{shelf_root.name}-release-shelf-committed-verify-",
            dir=shelf_root.parent,
        )
    )
    try:
        expected = expected_parent / "prepared"
        prepare_layout(
            candidate_root,
            expected,
            generation_id=generation_id,
            activated_at=str(pointer["activatedAt"]),
            activation_receipt_id=activation_receipt_id,
        )
        expected_pointer = _load_public_pointer(expected / CURRENT_POINTER)
        if pointer != expected_pointer or _tree_fingerprint(
            final_generation
        ) != _tree_fingerprint(
            expected / GENERATIONS_DIRECTORY / generation_id
        ):
            raise ReleaseShelfError(
                "committed activation differs from the pinned candidate intent"
            )
        _repair_authenticated_layout_modes(
            shelf_root,
            pointer,
            publish_pointer=True,
        )
        return pointer
    finally:
        shutil.rmtree(expected_parent, ignore_errors=True)


def _retire_activation_stage(stage_root: Path, shelf_root: Path) -> Path:
    retired = shelf_root.parent / (
        f".{shelf_root.name}-retired-activation-stage-"
        f"{uuid.uuid4().hex}"
    )
    os.rename(stage_root, retired)
    for directory in (shelf_root, shelf_root.parent):
        descriptor = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    try:
        shutil.rmtree(retired)
        descriptor = os.open(
            shelf_root.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        # The authoritative shelf no longer contains the stage. A sibling
        # retirement residue is safe for later operator cleanup.
        pass
    return retired


def activate_filesystem(
    candidate_root: Path,
    shelf_root: Path,
    *,
    initialize_layout: bool,
    generation_id: str | None = None,
    activated_at: str | None = None,
    activation_receipt_id: str | None = None,
    promotion_lease: _PromotionLockLease | None = None,
    allow_orphan_generation_recovery: bool = False,
) -> dict[str, Any]:
    generation_id = validate_generation_id(generation_id or new_generation_id())
    activation_receipt_id = validate_generation_id(
        activation_receipt_id or new_activation_receipt_id()
    )
    shelf_root.mkdir(parents=True, exist_ok=True)
    if shelf_root.is_symlink():
        raise ReleaseShelfError("release shelf root must not be a symbolic link")
    shelf_root = shelf_root.resolve(strict=True)
    if promotion_lease is not None:
        promotion_lease.validate_for(shelf_root)
        lock_scope: contextlib.AbstractContextManager[object] = contextlib.nullcontext(
            promotion_lease
        )
    else:
        lock_scope = promotion_lock(shelf_root)
    stage_parent: Path | None = None
    activation_succeeded = False
    try:
        with lock_scope as active_lease:
            lease = promotion_lease or active_lease
            refuse_server_managed_filesystem_shelf(shelf_root)
            if (
                not initialize_layout
                and not (shelf_root / CURRENT_POINTER).is_file()
            ):
                raise ReleaseShelfError(
                    f"{shelf_root} has no {LAYOUT_MARKER}; explicit layout "
                    "initialization is required"
                )
            stage_parent = reconcile_activation_stage_residue(
                candidate_root,
                shelf_root,
                generation_id=generation_id,
                activation_receipt_id=activation_receipt_id,
            )
            final_generation = (
                shelf_root / GENERATIONS_DIRECTORY / generation_id
            )
            if (
                stage_parent is None
                and final_generation.exists()
                and not allow_orphan_generation_recovery
            ):
                raise ReleaseShelfError(
                    f"generation ID has already been used: {generation_id}"
                )
            if (
                stage_parent is None
                and allow_orphan_generation_recovery
                and (shelf_root / CURRENT_POINTER).is_file()
            ):
                return _validate_committed_activation_for_intent(
                    candidate_root,
                    shelf_root,
                    generation_id=generation_id,
                    activation_receipt_id=activation_receipt_id,
                )
            if stage_parent is None:
                preparing_parent = Path(
                    tempfile.mkdtemp(
                        prefix=f".{shelf_root.name}-release-shelf-preparing-",
                        dir=shelf_root.parent,
                    )
                )
                try:
                    prepared = preparing_parent / "prepared"
                    prepare_layout(
                        candidate_root,
                        prepared,
                        generation_id=generation_id,
                        activated_at=activated_at,
                        activation_receipt_id=activation_receipt_id,
                    )
                    stage_parent = (
                        shelf_root
                        / _stage_intent_name(
                            generation_id,
                            activation_receipt_id,
                        )
                    )
                    os.rename(prepared, stage_parent)
                    root_descriptor = os.open(shelf_root, os.O_RDONLY)
                    try:
                        os.fsync(root_descriptor)
                    finally:
                        os.close(root_descriptor)
                finally:
                    shutil.rmtree(preparing_parent, ignore_errors=True)
            _validate_prepared_stage_for_intent(
                stage_parent,
                candidate_root=candidate_root,
                shelf_root=shelf_root,
                generation_id=generation_id,
                activation_receipt_id=activation_receipt_id,
            )
            result = activate_prepared_filesystem(
                stage_parent,
                shelf_root,
                initialize_layout=initialize_layout,
                promotion_lease=lease,
                allow_orphan_generation_recovery=(
                    allow_orphan_generation_recovery
                ),
            )
            _retire_activation_stage(stage_parent, shelf_root)
            stage_parent = None
            activation_succeeded = True
            return result
    finally:
        if activation_succeeded and stage_parent is not None:
            _retire_activation_stage(stage_parent, shelf_root)


def activate_prepared_filesystem(
    prepared_root: Path,
    shelf_root: Path,
    *,
    initialize_layout: bool,
    promotion_lease: _PromotionLockLease | None = None,
    allow_orphan_generation_recovery: bool = False,
) -> dict[str, Any]:
    shelf_root.mkdir(parents=True, exist_ok=True)
    pointer = _load_public_pointer(prepared_root / CURRENT_POINTER)
    generation_id = validate_generation_id(str(pointer.get("generationId") or ""))
    prepared_generation = prepared_root / GENERATIONS_DIRECTORY / generation_id
    final_generation = shelf_root / GENERATIONS_DIRECTORY / generation_id
    if prepared_generation.is_dir() and not prepared_generation.is_symlink():
        verify_generation(prepared_generation, pointer)
    elif (
        allow_orphan_generation_recovery
        and final_generation.is_dir()
        and not final_generation.is_symlink()
    ):
        verify_generation(
            final_generation,
            pointer,
            require_sealed_modes=False,
        )
    else:
        raise ReleaseShelfError(
            "prepared activation generation is unavailable"
        )
    if prepared_root.stat().st_dev != shelf_root.stat().st_dev:
        raise ReleaseShelfError("prepared generation and current.json must share one filesystem")
    if promotion_lease is not None:
        promotion_lease.validate_for(shelf_root)
        lock_scope: contextlib.AbstractContextManager[object] = contextlib.nullcontext(
            promotion_lease
        )
    else:
        lock_scope = promotion_lock(shelf_root)
    with lock_scope:
        if promotion_lease is not None:
            promotion_lease.validate_for(shelf_root)
        refuse_server_managed_filesystem_shelf(shelf_root)
        pointer_path = shelf_root / CURRENT_POINTER
        marker_path = shelf_root / LAYOUT_MARKER
        existing_pointer: dict[str, Any] | None = None
        if pointer_path.is_file():
            try:
                existing_pointer = _load_public_pointer(pointer_path)
            except ReleaseShelfError:
                if not allow_orphan_generation_recovery:
                    raise
                existing_pointer = load_pointer(pointer_path)
                existing_generation = (
                    shelf_root
                    / GENERATIONS_DIRECTORY
                    / str(existing_pointer["generationId"])
                )
                verify_generation(
                    existing_generation,
                    existing_pointer,
                    require_sealed_modes=False,
                )
                _repair_authenticated_layout_modes(
                    shelf_root,
                    existing_pointer,
                    publish_pointer=True,
                )
        marker_exists = marker_path.exists() or marker_path.is_symlink()
        if marker_exists:
            try:
                _require_layout_marker(shelf_root)
            except ReleaseShelfError:
                if not allow_orphan_generation_recovery:
                    raise
                _require_layout_marker(
                    shelf_root,
                    require_public_mode=False,
                )
                _atomic_write_layout_marker(marker_path)
                _require_layout_marker(shelf_root)
        if existing_pointer is None and not initialize_layout:
            raise ReleaseShelfError(
                f"{shelf_root} has no {LAYOUT_MARKER}; explicit layout initialization is required"
            )
        if existing_pointer is not None:
            existing_generation = (
                shelf_root
                / GENERATIONS_DIRECTORY
                / str(existing_pointer["generationId"])
            )
            verify_generation(existing_generation, existing_pointer)
        generations_root = shelf_root / GENERATIONS_DIRECTORY
        shelf_root.chmod(SHARED_DIRECTORY_MODE)
        generations_root.mkdir(mode=SHARED_DIRECTORY_MODE, exist_ok=True)
        generations_root.chmod(SHARED_DIRECTORY_MODE)
        final_generation = generations_root / generation_id
        if final_generation.exists():
            if not allow_orphan_generation_recovery:
                raise ReleaseShelfError(
                    f"generation ID has already been used: {generation_id}"
                )
            if allow_orphan_generation_recovery:
                verify_generation(
                    final_generation,
                    pointer,
                    require_sealed_modes=False,
                )
                _normalize_public_generation_modes(final_generation)
            verify_generation(final_generation, pointer)
            if prepared_generation.exists() and existing_pointer != pointer:
                # Only the governed recovery lane may explicitly opt into this
                # same-intent reuse after independently validating its prestate.
                pass
        try:
            if not final_generation.exists():
                # Some deployment filesystems require the moved directory
                # itself to retain owner-write permission for rename(2).
                # The private stage is owner-only and every child remains
                # sealed; restore the public 0555 root before publishing any
                # authority pointer.
                prepared_generation.chmod(0o755)
                try:
                    os.rename(prepared_generation, final_generation)
                finally:
                    if final_generation.exists():
                        final_generation.chmod(SEALED_DIRECTORY_MODE)
                    elif prepared_generation.exists():
                        prepared_generation.chmod(SEALED_DIRECTORY_MODE)
                parent_descriptor = os.open(generations_root, os.O_RDONLY)
                try:
                    os.fsync(parent_descriptor)
                finally:
                    os.close(parent_descriptor)
            verify_generation(final_generation, pointer)
            if not marker_exists:
                _create_layout_marker(shelf_root)
            _require_layout_marker(shelf_root)
            _atomic_write_json(shelf_root / CURRENT_POINTER, pointer)
            _require_layout_marker(shelf_root)
            root_descriptor = os.open(shelf_root, os.O_RDONLY)
            try:
                os.fsync(root_descriptor)
            finally:
                os.close(root_descriptor)
            return pointer
        except Exception:
            raise


def prepare_layout(
    candidate_root: Path,
    output_root: Path,
    *,
    generation_id: str | None = None,
    activated_at: str | None = None,
    activation_receipt_id: str | None = None,
) -> dict[str, Any]:
    generation_id = validate_generation_id(generation_id or new_generation_id())
    if output_root.exists() and any(output_root.iterdir()):
        raise ReleaseShelfError(f"prepared output root must be empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    generation_root = output_root / GENERATIONS_DIRECTORY / generation_id
    pointer = materialize_generation(
        candidate_root,
        generation_root,
        generation_id,
        activated_at=activated_at,
        activation_receipt_id=activation_receipt_id,
    )
    write_json(
        output_root / CURRENT_POINTER,
        pointer,
        mode=PUBLIC_METADATA_FILE_MODE,
    )
    _atomic_write_layout_marker(output_root / LAYOUT_MARKER)
    return pointer


def prepare_sidecar_active_layout(
    candidate_root: Path,
    output_root: Path,
    *,
    generation_id: str,
    activated_at: str,
    activation_receipt_id: str,
) -> dict[str, Any]:
    """Materialize one complete current generation for a read-only sidecar.

    No server activation is claimed. The current generation is assembled and
    verified offline, while the controller retains the external authority
    receipt that pins every digest before routing can change.
    """

    pointer = prepare_layout(
        candidate_root,
        output_root,
        generation_id=generation_id,
        activated_at=activated_at,
        activation_receipt_id=activation_receipt_id,
    )
    output_root = output_root.resolve(strict=True)
    generation_root = (
        output_root / GENERATIONS_DIRECTORY / str(pointer["generationId"])
    )

    for name in (CANONICAL_MANIFEST, COMPATIBILITY_MANIFEST):
        source = candidate_root / name
        destination = output_root / name
        shutil.copyfile(source, destination)
        destination.chmod(PUBLIC_METADATA_FILE_MODE)

    write_json(
        output_root / WRITER_POLICY,
        {
            "schemaVersion": SERVER_WRITER_POLICY_SCHEMA,
            "mode": SIDECAR_WRITER_POLICY_MODE,
        },
        mode=0o600,
    )

    pointer_path = output_root / CURRENT_POINTER
    pointer_bytes = pointer_path.read_bytes()
    pointer_sha256 = hashlib.sha256(pointer_bytes).hexdigest()

    verify_generation(generation_root, pointer)
    for path in (
        output_root / CANONICAL_MANIFEST,
        output_root / COMPATIBILITY_MANIFEST,
    ):
        if sha256_file(path) != sha256_file(candidate_root / path.name):
            raise ReleaseShelfError(
                "server active shelf compatibility mirror changed during preparation"
            )
    fsync_tree(output_root)
    return {
        "pointer": pointer,
        "pointerSha256": pointer_sha256,
        "activationCandidateSha256": sha256_file(
            generation_root / ACTIVATION_CANDIDATE
        ),
        "canonicalMirrorSha256": sha256_file(
            output_root / CANONICAL_MANIFEST
        ),
        "compatibilityMirrorSha256": sha256_file(
            output_root / COMPATIBILITY_MANIFEST
        ),
        "writerPolicy": SIDECAR_WRITER_POLICY_MODE,
    }


def verify_http_projection(
    pointer_url: str,
    generation_base_url: str,
    expected_generation_id: str,
) -> dict[str, Any]:
    def fetch_json(url: str) -> tuple[dict[str, Any], bytes]:
        request = Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - operator-selected URL
                body = response.read()
        except Exception as exc:  # pragma: no cover - exercised by shell integration
            raise ReleaseShelfError(f"failed to fetch {url}: {exc}") from exc
        try:
            payload = json.loads(body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReleaseShelfError(f"remote JSON is malformed at {url}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ReleaseShelfError(f"remote JSON must be an object at {url}")
        return payload, body

    expected_generation_id = validate_generation_id(expected_generation_id)
    pointer, _ = fetch_json(pointer_url)
    validate_pointer_payload(pointer)
    if pointer.get("generationId") != expected_generation_id:
        raise ReleaseShelfError("remote current pointer did not activate the expected generation")
    manifest_bindings = pointer.get("manifests")
    if not isinstance(manifest_bindings, dict):
        raise ReleaseShelfError("remote pointer is missing manifest bindings")
    base = generation_base_url.rstrip("/") + f"/{expected_generation_id}"
    for name, digest_key in (
        (CANONICAL_MANIFEST, "canonical"),
        (COMPATIBILITY_MANIFEST, "compatibility"),
    ):
        manifest, body = fetch_json(f"{base}/{name}")
        if manifest.get("generationId") != expected_generation_id:
            raise ReleaseShelfError(f"remote {name} generationId mismatch")
        binding = manifest_bindings.get(digest_key)
        if not isinstance(binding, dict) or hashlib.sha256(body).hexdigest() != binding.get("sha256"):
            raise ReleaseShelfError(f"remote {name} SHA-256 does not match current pointer")
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    mode = subparsers.add_parser("mode", help="validate and report legacy/generation mode")
    mode.add_argument("--shelf-root", type=Path, required=True)
    mode.add_argument("--initialize-layout", action="store_true")

    resolve = subparsers.add_parser("resolve", help="resolve one validated shelf snapshot")
    resolve.add_argument("--shelf-root", type=Path, required=True)

    prepare = subparsers.add_parser("prepare", help="prepare an object-storage generation")
    prepare.add_argument("--candidate-root", type=Path, required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--generation-id")
    prepare.add_argument("--activated-at")
    prepare.add_argument("--activation-receipt-id")

    project_manifests = subparsers.add_parser(
        "project-manifests",
        help="project one canonical/compatibility manifest pair to an exact generation",
    )
    project_manifests.add_argument("--canonical-manifest", type=Path, required=True)
    project_manifests.add_argument("--compatibility-manifest", type=Path, required=True)
    project_manifests.add_argument("--generation-id", required=True)

    activate = subparsers.add_parser(
        "activate-filesystem", help="stage, validate, and atomically activate a filesystem shelf"
    )
    activate.add_argument("--candidate-root", type=Path, required=True)
    activate.add_argument("--shelf-root", type=Path, required=True)
    activate.add_argument("--initialize-layout", action="store_true")
    activate.add_argument("--generation-id")
    activate.add_argument("--activated-at")
    activate.add_argument("--activation-receipt-id")

    activate_prepared = subparsers.add_parser(
        "activate-prepared-filesystem",
        help="atomically activate an already validated same-filesystem generation",
    )
    activate_prepared.add_argument("--prepared-root", type=Path, required=True)
    activate_prepared.add_argument("--shelf-root", type=Path, required=True)
    activate_prepared.add_argument("--initialize-layout", action="store_true")

    verify = subparsers.add_parser("verify", help="verify generation bytes against a pointer")
    verify.add_argument("--generation-root", type=Path, required=True)
    verify.add_argument("--pointer", type=Path, required=True)

    pointer = subparsers.add_parser("pointer", help="validate and print pointer metadata")
    pointer.add_argument("--pointer", type=Path, required=True)

    verify_http = subparsers.add_parser(
        "verify-http", help="verify a remote pointer and its immutable manifests"
    )
    verify_http.add_argument("--pointer-url", required=True)
    verify_http.add_argument("--generation-base-url", required=True)
    verify_http.add_argument("--expected-generation-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "mode":
            state, _, _ = resolve_shelf_root(args.shelf_root)
            print("generation" if state == "generation" or args.initialize_layout else "legacy")
        elif args.command == "resolve":
            _, root, pointer = resolve_shelf_root(args.shelf_root)
            print(json.dumps({"root": str(root), "pointer": pointer}, sort_keys=True))
        elif args.command == "prepare":
            pointer = prepare_layout(
                args.candidate_root,
                args.output_root,
                generation_id=args.generation_id,
                activated_at=args.activated_at,
                activation_receipt_id=args.activation_receipt_id,
            )
            print(json.dumps(pointer, sort_keys=True))
        elif args.command == "project-manifests":
            result = project_manifest_pair(
                args.canonical_manifest,
                args.compatibility_manifest,
                args.generation_id,
            )
            print(json.dumps(result, sort_keys=True))
        elif args.command == "activate-filesystem":
            pointer = activate_filesystem(
                args.candidate_root,
                args.shelf_root,
                initialize_layout=args.initialize_layout,
                generation_id=args.generation_id,
                activated_at=args.activated_at,
                activation_receipt_id=args.activation_receipt_id,
            )
            print(json.dumps(pointer, sort_keys=True))
        elif args.command == "activate-prepared-filesystem":
            pointer = activate_prepared_filesystem(
                args.prepared_root,
                args.shelf_root,
                initialize_layout=args.initialize_layout,
            )
            print(json.dumps(pointer, sort_keys=True))
        elif args.command == "verify":
            pointer = load_pointer(args.pointer)
            verify_generation(args.generation_root, pointer)
            print(json.dumps(pointer, sort_keys=True))
        elif args.command == "pointer":
            print(json.dumps(load_pointer(args.pointer), sort_keys=True))
        elif args.command == "verify-http":
            pointer = verify_http_projection(
                args.pointer_url,
                args.generation_base_url,
                args.expected_generation_id,
            )
            print(json.dumps(pointer, sort_keys=True))
        return 0
    except ReleaseShelfError as exc:
        print(f"release shelf error: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
