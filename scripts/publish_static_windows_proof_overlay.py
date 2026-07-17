#!/usr/bin/env python3
"""Publish or reconcile one append-only Windows proof candidate in a portal overlay.

This is a temporary, proof-only bridge. It never writes a current alias, the
canonical release shelf, or a container. The caller must explicitly identify
the portal overlay, canonical shelf, expected candidate, expected manifest
digest, receipt path, and the presence of the Cloudflare Access boundary.
Reconciliation is read-only with respect to an already-published candidate.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import quote, urlsplit

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from windows_proof_evidence import (  # noqa: E402
    MANIFEST_SCHEMA,
    validate_governed_windows_evidence,
    validate_manifest_freshness,
)

MANIFEST_NAME = "WINDOWS_PROOF_MANIFEST.generated.json"
RECEIPT_SCHEMA = "chummer.windows-proof.static-overlay-publication/v1"
PORTAL_MARKER = "Chummer.Run.Api.dll"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,254}$")
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
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
AT_FDCWD = -100
RENAME_NOREPLACE = 1


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


def sha256_file(path: Path, maximum_bytes: int = MAX_ARTIFACT_BYTES) -> tuple[int, str]:
    ensure_regular_file(path, "file")
    digest = hashlib.sha256()
    total = 0
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            fail(f"file must be regular: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(block)
                if total > maximum_bytes:
                    fail(f"file exceeds its byte limit: {path}")
                digest.update(block)
    finally:
        os.close(descriptor)
    if total <= 0:
        fail(f"file must not be empty: {path}")
    return total, digest.hexdigest()


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_safe_directory(path.parent, "receipt directory", create=False)
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


def ensure_no_symlink_ancestors(path: Path, label: str) -> None:
    current = path.absolute()
    while True:
        if current.exists() or current.is_symlink():
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                fail(f"{label} must not traverse a symbolic link: {current}")
        parent = current.parent
        if parent == current:
            break
        current = parent


def ensure_regular_file(path: Path, label: str) -> None:
    ensure_no_symlink_ancestors(path, label)
    try:
        metadata = path.lstat()
    except OSError as exc:
        fail(f"{label} is missing or inaccessible: {path}: {exc}")
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        fail(f"{label} must be a non-symlink regular file: {path}")


def ensure_safe_directory(path: Path, label: str, *, create: bool) -> None:
    ensure_no_symlink_ancestors(path, label)
    if not path.exists():
        if not create:
            fail(f"{label} must already exist: {path}")
        path.mkdir(parents=True, mode=0o755)
        ensure_no_symlink_ancestors(path, label)
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        fail(f"{label} must be a non-symlink directory: {path}")


def normalized_path(path: Path) -> Path:
    return Path(os.path.normcase(os.path.realpath(path.absolute())))


def paths_overlap(first: Path, second: Path) -> bool:
    left = normalized_path(first)
    right = normalized_path(second)
    return left == right or left in right.parents or right in left.parents


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
    if any(
        segment in {"", ".", ".."} or not SEGMENT_PATTERN.fullmatch(segment)
        for segment in segments
    ):
        fail("manifest contains a nonportable relativePath segment")
    return path


@dataclass(frozen=True)
class DeclaredArtifact:
    kind: str
    artifact_id: str
    relative_path: str
    file_name: str
    size: int
    sha256: str
    source_path: Path


@dataclass(frozen=True)
class ValidatedBundle:
    root: Path
    manifest_path: Path
    manifest_bytes: bytes
    manifest_sha256: str
    candidate_version: str
    artifacts: tuple[DeclaredArtifact, ...]
    inventory_digest: str


def require_exact(payload: dict[str, Any], key: str, expected: Any, label: str) -> None:
    if payload.get(key) != expected:
        fail(f"{label}.{key} must be {expected!r}")


def validate_manifest_posture(manifest: dict[str, Any]) -> None:
    for key, expected in (
        ("schemaVersion", MANIFEST_SCHEMA),
        ("channel", "preview"),
        ("releaseScope", "proof_only"),
        ("supportabilityState", "review_required"),
        ("publicTrustPosture", "blocked"),
        ("cfAccessGated", True),
        ("revoked", False),
    ):
        require_exact(manifest, key, expected, "manifest")
    validate_manifest_freshness(manifest)
    policy = manifest.get("proofOnlyPolicy")
    if not isinstance(policy, dict) or any(
        policy.get(key) is not True
        for key in ("enabled", "unsignedPreviewAllowed", "nativeWindowsValidationRequired")
    ):
        fail("manifest proofOnlyPolicy is incomplete")
    signing = manifest.get("signing")
    if not isinstance(signing, dict) or (
        signing.get("status") not in {"pass", "skipped_preview"}
        or signing.get("proofOnlyPolicyRecorded") is not True
    ):
        fail("manifest signing posture is invalid")
    smoke = manifest.get("compatibilitySmoke")
    if not isinstance(smoke, dict) or (
        smoke.get("status"),
        smoke.get("executionEnvironment"),
        smoke.get("nativeWindows"),
        smoke.get("payloadAcquisitionMode"),
    ) != ("pass", "wine_compatibility", False, "embedded"):
        fail("manifest compatibility smoke posture is invalid")
    exit_gate = manifest.get("visualExitGate")
    if not isinstance(exit_gate, dict) or (
        exit_gate.get("status") != "external_only"
        or exit_gate.get("evidenceArtifactId") is not None
    ):
        fail("manifest visual exit gate must remain external_only")
    handoff = manifest.get("nativeHostHandoff")
    if not isinstance(handoff, dict) or (
        handoff.get("status"),
        handoff.get("onlyBlocker"),
        handoff.get("onlyBlockerIsVisualProof"),
    ) != ("ready_for_windows_host", "visual_proof", True):
        fail("manifest native-host handoff posture is invalid")


def validate_bundle(root: Path) -> ValidatedBundle:
    ensure_safe_directory(root, "bundle root", create=False)
    manifest_path = root / MANIFEST_NAME
    ensure_regular_file(manifest_path, "Windows proof manifest")
    manifest_bytes = manifest_path.read_bytes()
    if not 1 <= len(manifest_bytes) <= MAX_MANIFEST_BYTES:
        fail("Windows proof manifest size is invalid")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = parse_json_bytes(manifest_bytes, "Windows proof manifest")
    validate_manifest_posture(manifest)
    candidate_version = str(manifest.get("candidateVersion") or "").strip()
    if not VERSION_PATTERN.fullmatch(candidate_version) or ".." in candidate_version:
        fail("manifest candidateVersion is invalid")
    rows = manifest.get("artifacts")
    if not isinstance(rows, list) or len(rows) != len(REQUIRED_KINDS):
        fail("manifest must declare exactly eight proof-only artifacts")

    artifacts: list[DeclaredArtifact] = []
    kinds: set[str] = set()
    paths: set[str] = set()
    portable_paths: set[str] = set()
    total_bytes = 0
    for row in rows:
        if not isinstance(row, dict):
            fail("manifest artifact rows must be objects")
        kind = str(row.get("kind") or "")
        artifact_id = str(row.get("artifactId") or "")
        relative_path = normalize_relative_path(row.get("relativePath"))
        file_name = str(row.get("fileName") or "")
        content_type = str(row.get("contentType") or "")
        size = row.get("size")
        digest = str(row.get("sha256") or "")
        if kind not in REQUIRED_KINDS or kind in kinds:
            fail("manifest artifact kind is invalid or duplicated")
        prefix, suffix = KIND_PATH_RULES[kind]
        if not relative_path.startswith(prefix) or not relative_path.endswith(suffix):
            fail(f"manifest path is not allowlisted for artifact kind {kind}")
        if (
            artifact_id != "avalonia-win-x64-installer"
            or row.get("head") != "avalonia"
            or row.get("rid") != "win-x64"
            or content_type != KIND_CONTENT_TYPES[kind]
            or Path(relative_path).name != file_name
            or relative_path in paths
            or relative_path.casefold() in portable_paths
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 1 <= size <= MAX_ARTIFACT_BYTES
            or not SHA256_PATTERN.fullmatch(digest)
        ):
            fail("manifest artifact row is invalid or collides under portable comparison")
        source_path = root.joinpath(*relative_path.split("/"))
        observed_size, observed_digest = sha256_file(source_path)
        if observed_size != size or observed_digest != digest:
            fail(f"manifest artifact bytes do not match {relative_path}")
        kinds.add(kind)
        paths.add(relative_path)
        portable_paths.add(relative_path.casefold())
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            fail("Windows proof bundle exceeds its total byte limit")
        artifacts.append(
            DeclaredArtifact(
                kind,
                artifact_id,
                relative_path,
                file_name,
                size,
                digest,
                source_path,
            )
        )
    if kinds != REQUIRED_KINDS:
        fail("manifest is missing a required proof-only artifact")

    by_kind = {artifact.kind: artifact for artifact in artifacts}
    governed_evidence = validate_governed_windows_evidence(
        version=candidate_version,
        installer_path=by_kind["installer"].source_path,
        provenance_path=by_kind["build_provenance_receipt"].source_path,
        sbom_path=by_kind["sbom"].source_path,
    )
    validate_manifest_freshness(manifest, not_before=governed_evidence.build_started_at)

    observed: set[str] = set()
    observed_directories: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"bundle contains a symbolic link: {path}")
        if path.is_file():
            observed.add(path.relative_to(root).as_posix())
        elif path.is_dir():
            observed_directories.add(path.relative_to(root).as_posix())
        else:
            fail(f"bundle contains a non-regular filesystem entry: {path}")
    if observed != paths | {MANIFEST_NAME}:
        fail("bundle contains undeclared, missing, or stale files")
    declared_directories = {
        parent.as_posix()
        for relative_path in paths
        for parent in Path(relative_path).parents
        if parent != Path(".")
    }
    if observed_directories != declared_directories:
        fail("bundle contains undeclared, missing, or stale directories")

    inventory_hash = hashlib.sha256()
    for artifact in sorted(artifacts, key=lambda item: item.relative_path):
        inventory_hash.update(
            f"{artifact.relative_path}\0{artifact.size}\0{artifact.sha256}\n".encode()
        )
    return ValidatedBundle(
        root,
        manifest_path,
        manifest_bytes,
        manifest_sha256,
        candidate_version,
        tuple(artifacts),
        inventory_hash.hexdigest(),
    )


def capture_canonical_identity(canonical_root: Path) -> dict[str, Any]:
    ensure_safe_directory(canonical_root, "canonical release root", create=False)
    pointer_path = canonical_root / "current.json"
    pointer_digest: str | None = None
    generation_id: str | None = None
    manifest_path = canonical_root / "RELEASE_CHANNEL.generated.json"
    if pointer_path.exists() or pointer_path.is_symlink():
        ensure_regular_file(pointer_path, "canonical current pointer")
        pointer_bytes = pointer_path.read_bytes()
        if not 1 <= len(pointer_bytes) <= MAX_MANIFEST_BYTES:
            fail("canonical current pointer size is invalid")
        pointer = parse_json_bytes(pointer_bytes, "canonical current pointer")
        pointer_digest = hashlib.sha256(pointer_bytes).hexdigest()
        generation_id = str(pointer.get("generationId") or "").strip()
        if not VERSION_PATTERN.fullmatch(generation_id):
            fail("canonical current pointer generationId is invalid")
        manifest_path = canonical_root / "generations" / generation_id / "RELEASE_CHANNEL.generated.json"
    ensure_regular_file(manifest_path, "canonical release manifest")
    manifest_bytes = manifest_path.read_bytes()
    if not 1 <= len(manifest_bytes) <= MAX_MANIFEST_BYTES:
        fail("canonical release manifest size is invalid")
    manifest = parse_json_bytes(manifest_bytes, "canonical release manifest")
    version = str(manifest.get("releaseVersion") or manifest.get("version") or "").strip()
    channel = str(manifest.get("channelId") or manifest.get("channel") or "").strip()
    published_at = str(manifest.get("publishedAt") or "").strip()
    if not version or not channel or not published_at:
        fail("canonical release manifest identity fields are incomplete")
    identity = {
        "root": str(canonical_root.absolute()),
        "generationId": generation_id,
        "pointerSha256": pointer_digest,
        "manifestRelativePath": manifest_path.relative_to(canonical_root).as_posix(),
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "releaseVersion": version,
        "channel": channel,
        "publishedAt": published_at,
    }
    identity["identitySha256"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return identity


def copy_verified_file(source: Path, destination: Path, size: int, digest: str) -> None:
    ensure_regular_file(source, "source artifact")
    ensure_safe_directory(destination.parent, "candidate directory", create=True)
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    destination_fd = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o644,
    )
    observed = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(source_fd, "rb", closefd=False) as source_stream, os.fdopen(
            destination_fd, "wb", closefd=False
        ) as destination_stream:
            for block in iter(lambda: source_stream.read(1024 * 1024), b""):
                total += len(block)
                if total > size:
                    fail("source artifact changed during publication")
                observed.update(block)
                destination_stream.write(block)
            destination_stream.flush()
            os.fsync(destination_stream.fileno())
    finally:
        os.close(source_fd)
        os.close(destination_fd)
    if total != size or observed.hexdigest() != digest:
        fail("source artifact changed during publication")
    os.chmod(destination, 0o644)


def fsync_tree(root: Path) -> None:
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        fsync_directory(directory)
    fsync_directory(root)


def atomic_rename_noreplace(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        fail(f"append-only candidate already exists: {destination}")
    if os.name == "posix":
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            fail("atomic no-replace rename is unavailable on this host")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            AT_FDCWD,
            os.fsencode(source),
            AT_FDCWD,
            os.fsencode(destination),
            RENAME_NOREPLACE,
        )
        if result != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                fail(f"append-only candidate already exists: {destination}")
            raise OSError(error, os.strerror(error), str(destination))
        return
    try:
        os.rename(source, destination)
    except FileExistsError:
        fail(f"append-only candidate already exists: {destination}")


def validate_public_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        fail("public origin must be an HTTPS origin without path, query, or fragment")
    return f"https://{parsed.netloc}"


@dataclass(frozen=True)
class PublicationRequest:
    bundle_root: Path
    overlay_root: Path
    canonical_root: Path
    receipt_path: Path
    expected_candidate_version: str
    expected_manifest_sha256: str
    cf_access_gated: bool
    public_origin: str
    reconcile_existing: bool = False


def validate_roots(request: PublicationRequest, bundle: ValidatedBundle) -> tuple[Path, Path]:
    ensure_safe_directory(request.overlay_root, "portal overlay root", create=False)
    ensure_regular_file(request.overlay_root / PORTAL_MARKER, "portal overlay marker")
    wwwroot = request.overlay_root / "wwwroot"
    ensure_safe_directory(wwwroot, "portal overlay wwwroot", create=False)
    ensure_safe_directory(request.canonical_root, "canonical release root", create=False)
    ensure_safe_directory(request.receipt_path.parent, "publication receipt directory", create=False)
    roots = {
        "bundle": bundle.root,
        "overlay": request.overlay_root,
        "canonical": request.canonical_root,
    }
    pairs = (("bundle", "overlay"), ("bundle", "canonical"), ("overlay", "canonical"))
    for left, right in pairs:
        if paths_overlap(roots[left], roots[right]):
            fail(f"{left} and {right} roots must be physically separate")
    if any(paths_overlap(request.receipt_path, root) for root in roots.values()):
        fail("publication receipt must live outside bundle, overlay, and canonical roots")
    candidate_parent = wwwroot / "downloads" / "proof" / "windows" / "candidates"
    ensure_no_symlink_ancestors(candidate_parent, "Windows proof candidate parent")
    target = candidate_parent / bundle.candidate_version
    if request.reconcile_existing:
        ensure_safe_directory(candidate_parent, "Windows proof candidate parent", create=False)
        ensure_safe_directory(target, "existing Windows proof candidate", create=False)
    elif target.exists() or target.is_symlink():
        fail(f"append-only candidate already exists: {target}")
    return candidate_parent, target


def transition_receipt(path: Path, receipt: dict[str, Any], state: str, **updates: Any) -> None:
    receipt.update(updates)
    receipt["state"] = state
    receipt["updatedAt"] = now_iso()
    atomic_json(path, receipt)


def bundle_identity(bundle: ValidatedBundle) -> dict[str, Any]:
    return {
        "candidateVersion": bundle.candidate_version,
        "manifestSha256": bundle.manifest_sha256,
        "inventoryDigest": bundle.inventory_digest,
        "artifactCount": len(bundle.artifacts),
        "treeFileCount": len(bundle.artifacts) + 1,
    }


def successful_verification() -> dict[str, bool]:
    """Return the common, completed-only verification contract.

    This object is intentionally added only after every check has run.  An
    activation or post-activation failure must not inherit optimistic flags
    from a preparing receipt.
    """
    return {
        "sourceBundleExactMatch": True,
        "targetBytesUnchanged": True,
        "targetTreeComplete": True,
        "proofOnlyPostureValidated": True,
        "canonicalIdentityUnchanged": True,
    }


def require_exact_bundle(source: ValidatedBundle, candidate: ValidatedBundle) -> None:
    if bundle_identity(candidate) != bundle_identity(source):
        fail("existing candidate does not exactly match the validated source bundle")


def candidate_routes(
    public_origin: str,
    bundle: ValidatedBundle,
) -> dict[str, str]:
    candidate_segment = quote(bundle.candidate_version, safe="")
    base_url = f"{public_origin}/downloads/proof/windows/candidates/{candidate_segment}"
    return {
        "manifest": f"{base_url}/{MANIFEST_NAME}",
        **{
            f"{artifact.artifact_id}:{artifact.kind}":
                f"{base_url}/{quote(artifact.relative_path, safe='/')}"
            for artifact in bundle.artifacts
        },
    }


def reconcile_existing_candidate(
    request: PublicationRequest,
    bundle: ValidatedBundle,
    target: Path,
    canonical_before: dict[str, Any],
    public_origin: str,
) -> dict[str, Any]:
    target_before = validate_bundle(target)
    require_exact_bundle(bundle, target_before)

    # Validate the complete target tree twice around the canonical observation.
    # This path never opens a target file for writing and never changes modes,
    # timestamps, aliases, or directory entries beneath the candidate root.
    target_after = validate_bundle(target)
    require_exact_bundle(bundle, target_after)
    canonical_after = capture_canonical_identity(request.canonical_root)
    if bundle_identity(target_after) != bundle_identity(target_before):
        fail("existing candidate changed during reconciliation")
    if canonical_after != canonical_before:
        fail("canonical release identity changed during reconciliation")

    timestamp = now_iso()
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA,
        "state": "completed",
        "operation": "reconcile_existing",
        "candidateVersion": bundle.candidate_version,
        "manifestSha256": bundle.manifest_sha256,
        "inventoryDigest": bundle.inventory_digest,
        "cfAccessGated": True,
        "overlayRoot": str(request.overlay_root.absolute()),
        "canonicalRoot": str(request.canonical_root.absolute()),
        "targetRelativePath": target.relative_to(request.overlay_root).as_posix(),
        "canonicalBefore": canonical_before,
        "canonicalAfter": canonical_after,
        "targetIdentityBefore": bundle_identity(target_before),
        "targetIdentityAfter": bundle_identity(target_after),
        "verification": successful_verification(),
        "routes": candidate_routes(public_origin, bundle),
        "createdAt": timestamp,
        "completedAt": timestamp,
        "updatedAt": timestamp,
    }
    atomic_json(request.receipt_path, receipt)
    return receipt


def publish(request: PublicationRequest) -> dict[str, Any]:
    if not request.cf_access_gated:
        fail("static Windows proof publication requires an explicit Cloudflare Access gate assertion")
    if not VERSION_PATTERN.fullmatch(request.expected_candidate_version):
        fail("expected candidate version is invalid")
    if not SHA256_PATTERN.fullmatch(request.expected_manifest_sha256):
        fail("expected manifest SHA-256 is invalid")
    if request.receipt_path.exists() or request.receipt_path.is_symlink():
        fail("publication receipt already exists; this append-only operation cannot be replayed")
    public_origin = validate_public_origin(request.public_origin)
    bundle = validate_bundle(request.bundle_root)
    if bundle.candidate_version != request.expected_candidate_version:
        fail("candidate version does not match the explicit expected version")
    if bundle.manifest_sha256 != request.expected_manifest_sha256:
        fail("manifest digest does not match the explicit expected SHA-256")
    candidate_parent, target = validate_roots(request, bundle)
    canonical_before = capture_canonical_identity(request.canonical_root)
    if request.reconcile_existing:
        return reconcile_existing_candidate(
            request,
            bundle,
            target,
            canonical_before,
            public_origin,
        )

    ensure_safe_directory(candidate_parent, "Windows proof candidate parent", create=True)
    if target.exists() or target.is_symlink():
        fail(f"append-only candidate already exists: {target}")

    staging = candidate_parent / f".{bundle.candidate_version}.{os.getpid()}.{os.urandom(8).hex()}.staging"
    if staging.exists() or staging.is_symlink():
        fail("unique staging path unexpectedly exists")
    staging.mkdir(mode=0o700)
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA,
        "state": "preparing",
        "operation": "publish_new",
        "candidateVersion": bundle.candidate_version,
        "manifestSha256": bundle.manifest_sha256,
        "inventoryDigest": bundle.inventory_digest,
        "cfAccessGated": True,
        "overlayRoot": str(request.overlay_root.absolute()),
        "canonicalRoot": str(request.canonical_root.absolute()),
        "targetRelativePath": target.relative_to(request.overlay_root).as_posix(),
        # A null before-identity is the explicit append-only assertion.  The
        # no-replace activation below is the enforcement mechanism.
        "targetIdentityBefore": None,
        "canonicalBefore": canonical_before,
        "createdAt": now_iso(),
    }
    try:
        copy_verified_file(
            bundle.manifest_path,
            staging / MANIFEST_NAME,
            len(bundle.manifest_bytes),
            bundle.manifest_sha256,
        )
        for artifact in bundle.artifacts:
            copy_verified_file(
                artifact.source_path,
                staging.joinpath(*artifact.relative_path.split("/")),
                artifact.size,
                artifact.sha256,
            )
        staged = validate_bundle(staging)
        if staged.manifest_sha256 != bundle.manifest_sha256 or staged.inventory_digest != bundle.inventory_digest:
            fail("staged candidate does not match the validated source bundle")
        os.chmod(staging, 0o755)
        fsync_tree(staging)
        canonical_pre_activation = capture_canonical_identity(request.canonical_root)
        if canonical_pre_activation != canonical_before:
            fail("canonical release identity changed before proof activation")
        transition_receipt(request.receipt_path, receipt, "activation_started")
        atomic_rename_noreplace(staging, target)
        fsync_directory(candidate_parent)
        published_before = validate_bundle(target)
        require_exact_bundle(bundle, published_before)
        published_after = validate_bundle(target)
        require_exact_bundle(bundle, published_after)
        if bundle_identity(published_after) != bundle_identity(published_before):
            fail("published candidate changed during post-activation verification")
        canonical_after = capture_canonical_identity(request.canonical_root)
        if canonical_after != canonical_before:
            transition_receipt(
                request.receipt_path,
                receipt,
                "canonical_drift_detected",
                canonicalAfter=canonical_after,
            )
            fail("canonical release identity changed during proof publication")
        transition_receipt(
            request.receipt_path,
            receipt,
            "completed",
            canonicalAfter=canonical_after,
            targetIdentityAfter=bundle_identity(published_after),
            verification=successful_verification(),
            completedAt=now_iso(),
            routes=candidate_routes(public_origin, bundle),
        )
        return receipt
    except BaseException:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)
            fsync_directory(candidate_parent)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-candidate-version", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--cf-access-gated", action="store_true")
    parser.add_argument(
        "--reconcile-existing",
        action="store_true",
        help="verify an existing candidate read-only and emit its durable receipt",
    )
    parser.add_argument("--public-origin", default="https://chummer.run")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        receipt = publish(
            PublicationRequest(
                bundle_root=args.bundle_root.absolute(),
                overlay_root=args.overlay_root.absolute(),
                canonical_root=args.canonical_root.absolute(),
                receipt_path=args.receipt.absolute(),
                expected_candidate_version=args.expected_candidate_version,
                expected_manifest_sha256=args.expected_manifest_sha256,
                cf_access_gated=args.cf_access_gated,
                public_origin=args.public_origin,
                reconcile_existing=args.reconcile_existing,
            )
        )
    except (OSError, ValueError) as exc:
        print(f"windows_proof_static_publish:fail: {exc}", file=sys.stderr)
        return 1
    operation = "reconcile" if receipt.get("operation") == "reconcile_existing" else "publish"
    print(
        f"windows_proof_static_{operation}:completed "
        f"candidate={receipt['candidateVersion']} manifestSha256={receipt['manifestSha256']} "
        f"receipt={args.receipt.absolute()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
