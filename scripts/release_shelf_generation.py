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
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen


POINTER_SCHEMA = "chummer.release-shelf.current/v1"
ACTIVATION_CANDIDATE_SCHEMA = "chummer.release-shelf.activation-candidate/v1"
LAYOUT_MARKER = ".release-shelf-layout-v1"
CURRENT_POINTER = "current.json"
GENERATIONS_DIRECTORY = "generations"
PROMOTION_LOCK = ".release-shelf-promotion.lock"
WRITER_POLICY = ".release-shelf-writer-policy.json"
SERVER_WRITER_POLICY_SCHEMA = "chummer.release-shelf.writer-policy/v1"
SERVER_WRITER_POLICY_MODE = "server-journal-v1"
CANONICAL_MANIFEST = "RELEASE_CHANNEL.generated.json"
COMPATIBILITY_MANIFEST = "releases.json"
ACTIVATION_CANDIDATE = "activation-candidate.json"
SAFE_GENERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PORTABLE_INVENTORY_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,254}$")
COPYABLE_FILES = {
    CANONICAL_MANIFEST,
    COMPATIBILITY_MANIFEST,
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


class ReleaseShelfError(RuntimeError):
    """Raised when a shelf or candidate fails closed."""


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
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


def _rewrite_versioned_url(value: str, generation_id: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    path = parsed.path
    generation_prefix = "/downloads/g/"
    if path.startswith(generation_prefix):
        suffix = path[len(generation_prefix) :]
        prior_generation, separator, remainder = suffix.partition("/")
        if not separator or not prior_generation or not remainder:
            raise ReleaseShelfError(f"malformed generation-bound download URL: {value}")
        path = f"{generation_prefix}{generation_id}/{remainder}"
    else:
        for prefix in VERSIONED_ROUTE_PREFIXES:
            if path.startswith(prefix):
                relative = path[len("/downloads/") :]
                path = f"{generation_prefix}{generation_id}/{relative}"
                break
    if path == parsed.path:
        return value
    if parsed.query or parsed.fragment:
        raise ReleaseShelfError(f"generation-bound download URLs cannot contain query or fragment: {value}")
    # Authoritative manifests carry site paths. Origins are deployment concerns and
    # must not create a second URL identity for the same immutable object.
    return path


_OMIT_MANIFEST_VALUE = object()


def _artifact_routes(payload: dict[str, Any], generation_id: str) -> dict[str, str]:
    routes: dict[str, str] = {}
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
            access_class = str(
                row.get("installAccessClass") or row.get("install_access_class") or ""
            ).strip().lower()
            route = (
                f"/downloads/g/{generation_id}/files/{file_name}"
                if access_class == "open_public"
                else f"/downloads/g/{generation_id}/install/{quote(artifact_id, safe='')}"
            )
            prior = routes.get(artifact_id)
            if prior is not None and prior != route:
                raise ReleaseShelfError(
                    f"manifest artifactId maps to multiple files: {artifact_id}"
                )
            routes[artifact_id] = route
    return routes


def _project_artifact_download_urls(
    payload: dict[str, Any], artifact_routes: dict[str, str]
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
                row["downloadUrl"] = route
            if "url" in row:
                row["url"] = route


def _rewrite_artifact_dispatch_url(
    value: str, artifact_routes: dict[str, str]
) -> str | object | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    prefixes = ("/downloads/install/", "/downloads/get/", "/downloads/file/")
    prefix = next((candidate for candidate in prefixes if parsed.path.startswith(candidate)), None)
    if prefix is None:
        return None
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ReleaseShelfError(
            f"release artifact dispatch URL must be a plain site path: {value}"
        )
    artifact_id, separator, suffix = parsed.path[len(prefix) :].partition("/")
    # Only the artifact dispatch itself represents immutable bytes. Continuation,
    # claim, template, and historic routes are mutable control-plane facts and are
    # deliberately omitted from an authoritative generation manifest.
    if not artifact_id or separator or suffix:
        return _OMIT_MANIFEST_VALUE
    return artifact_routes.get(artifact_id, _OMIT_MANIFEST_VALUE)


def _rewrite_manifest_value(
    value: Any, generation_id: str, artifact_routes: dict[str, str]
) -> Any:
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, item in value.items():
            if key in PROOF_ROUTE_KEYS:
                rewritten[key] = copy.deepcopy(item)
                continue
            projected = _rewrite_manifest_value(item, generation_id, artifact_routes)
            if projected is not _OMIT_MANIFEST_VALUE:
                rewritten[key] = projected
        return rewritten
    if isinstance(value, list):
        rewritten_items = [
            _rewrite_manifest_value(item, generation_id, artifact_routes) for item in value
        ]
        return [item for item in rewritten_items if item is not _OMIT_MANIFEST_VALUE]
    if isinstance(value, str):
        dispatch_projection = _rewrite_artifact_dispatch_url(value, artifact_routes)
        if dispatch_projection is not None:
            return dispatch_projection
        return _rewrite_versioned_url(value, generation_id)
    return value


def normalize_manifest(path: Path, generation_id: str) -> dict[str, Any]:
    payload = read_json_object(path, path.name)
    artifact_routes = _artifact_routes(payload, generation_id)
    source = copy.deepcopy(payload)
    _project_artifact_download_urls(source, artifact_routes)
    normalized = _rewrite_manifest_value(
        source, generation_id, artifact_routes
    )
    assert isinstance(normalized, dict)
    normalized["generationId"] = generation_id
    write_json(path, normalized)
    return normalized


def _walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in PROOF_ROUTE_KEYS:
                continue
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, str):
        yield value


def validate_manifest_routes(payload: dict[str, Any], generation_id: str, label: str) -> None:
    expected_prefix = f"/downloads/g/{generation_id}/"
    for value in _walk_strings(payload):
        try:
            parsed = urlsplit(value)
            path = parsed.path
        except ValueError:
            continue
        if not path.startswith("/downloads/"):
            continue
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ReleaseShelfError(f"{label} download URL must be a plain site path: {value}")
        decoded_path = unquote(path)
        if not decoded_path.startswith(expected_prefix):
            raise ReleaseShelfError(f"{label} retains non-generation download URL: {value}")
        relative_text = decoded_path[len(expected_prefix) :]
        relative = PurePosixPath(relative_text)
        invalid_root_shape = relative.parts[0] not in ALLOWED_GENERATION_ROUTE_ROOTS
        if relative.parts[0] == "install":
            invalid_root_shape = len(relative.parts) != 2
        if (
            not relative_text
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or invalid_root_shape
        ):
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
    canonical = normalize_manifest(generation_root / CANONICAL_MANIFEST, generation_id)
    compatibility = normalize_manifest(generation_root / COMPATIBILITY_MANIFEST, generation_id)
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
    write_json(generation_root / ACTIVATION_CANDIDATE, candidate_record)
    verify_generation(generation_root, pointer)
    fsync_tree(generation_root)
    return pointer


def verify_generation(generation_root: Path, pointer: dict[str, Any]) -> None:
    generation_id = validate_generation_id(str(pointer.get("generationId") or ""))
    if generation_root.name != generation_id:
        raise ReleaseShelfError(
            f"generation directory {generation_root.name!r} does not match pointer {generation_id!r}"
        )
    if pointer.get("schemaVersion") != POINTER_SCHEMA:
        raise ReleaseShelfError("unsupported release shelf pointer schemaVersion")
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


def resolve_shelf_root(shelf_root: Path) -> tuple[str, Path, dict[str, Any] | None]:
    marker_exists = (shelf_root / LAYOUT_MARKER).is_file()
    pointer_path = shelf_root / CURRENT_POINTER
    pointer_exists = pointer_path.is_file()
    if pointer_exists:
        pointer = load_pointer(pointer_path)
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
def promotion_lock(shelf_root: Path) -> Iterator[None]:
    shelf_root.mkdir(parents=True, exist_ok=True)
    lock_path = shelf_root / PROMOTION_LOCK
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _create_layout_marker(shelf_root: Path) -> None:
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{LAYOUT_MARKER}.", dir=shelf_root)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("v1\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, shelf_root / LAYOUT_MARKER)
    finally:
        temp_path.unlink(missing_ok=True)


def activate_filesystem(
    candidate_root: Path,
    shelf_root: Path,
    *,
    initialize_layout: bool,
    generation_id: str | None = None,
    activated_at: str | None = None,
    activation_receipt_id: str | None = None,
) -> dict[str, Any]:
    shelf_root.mkdir(parents=True, exist_ok=True)
    refuse_server_managed_filesystem_shelf(shelf_root)
    generation_id = validate_generation_id(generation_id or new_generation_id())
    stage_parent = Path(tempfile.mkdtemp(prefix=".release-shelf-stage-", dir=shelf_root))
    try:
        prepare_layout(
            candidate_root,
            stage_parent,
            generation_id=generation_id,
            activated_at=activated_at,
            activation_receipt_id=activation_receipt_id,
        )
        return activate_prepared_filesystem(
            stage_parent,
            shelf_root,
            initialize_layout=initialize_layout,
        )
    finally:
        shutil.rmtree(stage_parent, ignore_errors=True)


def activate_prepared_filesystem(
    prepared_root: Path,
    shelf_root: Path,
    *,
    initialize_layout: bool,
) -> dict[str, Any]:
    shelf_root.mkdir(parents=True, exist_ok=True)
    pointer = load_pointer(prepared_root / CURRENT_POINTER)
    generation_id = validate_generation_id(str(pointer.get("generationId") or ""))
    prepared_generation = prepared_root / GENERATIONS_DIRECTORY / generation_id
    verify_generation(prepared_generation, pointer)
    if prepared_root.stat().st_dev != shelf_root.stat().st_dev:
        raise ReleaseShelfError("prepared generation and current.json must share one filesystem")
    with promotion_lock(shelf_root):
        refuse_server_managed_filesystem_shelf(shelf_root)
        state, _, _ = resolve_shelf_root(shelf_root)
        if state == "legacy" and not initialize_layout:
            raise ReleaseShelfError(
                f"{shelf_root} has no {LAYOUT_MARKER}; explicit layout initialization is required"
            )
        generations_root = shelf_root / GENERATIONS_DIRECTORY
        generations_root.mkdir(exist_ok=True)
        final_generation = generations_root / generation_id
        if final_generation.exists():
            raise ReleaseShelfError(f"generation ID has already been used: {generation_id}")
        try:
            os.rename(prepared_generation, final_generation)
            parent_descriptor = os.open(generations_root, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
            verify_generation(final_generation, pointer)
            _atomic_write_json(shelf_root / CURRENT_POINTER, pointer)
            if state == "legacy":
                try:
                    _create_layout_marker(shelf_root)
                except OSError:
                    # current.json is the commit point and is already independently
                    # sufficient for v1 readers. Marker creation is a post-commit,
                    # non-retryable downgrade-sentinel warning.
                    pointer["durabilityWarning"] = (
                        "layout marker creation failed after current.json activation"
                    )
            # The rename above is the commit point. Directory fsync is best-effort so
            # a post-commit durability warning cannot turn success into a retry signal.
            try:
                root_descriptor = os.open(shelf_root, os.O_RDONLY)
                try:
                    os.fsync(root_descriptor)
                finally:
                    os.close(root_descriptor)
            except OSError:
                pointer["durabilityWarning"] = "shelf root directory fsync failed after activation"
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
    write_json(output_root / CURRENT_POINTER, pointer)
    (output_root / LAYOUT_MARKER).write_text("v1\n", encoding="utf-8")
    return pointer


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
