#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import UTC, datetime
import errno
import fcntl
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
from typing import Any, Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    from scripts.strict_json_contract import (
        StrictJsonContractError,
        strict_json_object,
    )
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from strict_json_contract import StrictJsonContractError, strict_json_object

try:
    from scripts.public_edge_payload_modes import (
        PayloadModePolicyError,
        normalize_payload_modes,
        validate_payload_modes,
        validate_payload_modes_against_receipt,
    )
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from public_edge_payload_modes import (
        PayloadModePolicyError,
        normalize_payload_modes,
        validate_payload_modes,
        validate_payload_modes_against_receipt,
    )


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
DEFAULT_SOURCE_ROOT = RUN_SERVICES_ROOT
DEFAULT_STAGING_ROOT = RUN_SERVICES_ROOT / ".state" / "public-edge-portal-overlay-next" / "app"
DEFAULT_ACTIVE_ROOT = RUN_SERVICES_ROOT / ".state" / "public-edge-portal-overlay" / "app"
DEFAULT_BACKUP_ROOT = RUN_SERVICES_ROOT / ".state" / "public-edge-portal-overlay-backups"
DEFAULT_BUILD_ROOT = RUN_SERVICES_ROOT / ".state" / "public-edge-portal-overlay-build"
DEFAULT_OUTPUT = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "PUBLIC_EDGE_PORTAL_OVERLAY_PUBLISH.generated.json"
DEFAULT_CONFIGURATION = "Release"
DEFAULT_VERIFY_TIMEOUT_SECONDS = 30.0
DEFAULT_VERIFICATION_DEADLINE_SECONDS = 15.0 * 60.0
DEFAULT_PUBLISH_TIMEOUT_SECONDS = 30.0 * 60.0
MAX_VERIFY_TIMEOUT_SECONDS = 10.0 * 60.0
MAX_VERIFICATION_DEADLINE_SECONDS = 60.0 * 60.0
MAX_PUBLISH_TIMEOUT_SECONDS = 2.0 * 60.0 * 60.0
DEFAULT_MINIMUM_FREE_DISK_BYTES = 8 * 1024 * 1024 * 1024
MAX_MINIMUM_FREE_DISK_BYTES = (1 << 63) - 1
PUBLISH_TIMEOUT_EXIT_CODE = 124
PUBLISH_TIMEOUT_TERMINATION_GRACE_SECONDS = 10.0
MAX_RELEASE_CHANNEL_RECEIPT_BYTES = 16 * 1024 * 1024
DEFAULT_PUBLISH_LOCK_FILE = "public-edge-portal-overlay.publish.lock"
CONTRACT_NAME = "chummer.public_edge_portal_overlay_publish.v1"
SOURCE_FINGERPRINT_ALGORITHM = "sha256-canonical-path-content-size-v1"
STAGED_PAYLOAD_FINGERPRINT_ALGORITHM = (
    "sha256-canonical-path-content-size-posix-mode-runtime-mount-exclusions-v3"
)
FULL_DEPLOYMENT_DIGEST_CONTRACT_NAME = "chummer.public_edge_full_deployment_digest.v1"
FULL_DEPLOYMENT_DIGEST_ALGORITHM = "sha256-canonical-json-v1"
ACTIVATION_TRANSACTION_CONTRACT_NAME = "chummer.public_edge_portal_overlay_activation_transaction.v1"
RENAME_NOREPLACE = 1
RENAME_EXCHANGE = 2
OVERLAY_BUILD_INFO_RELATIVE_PATH = Path(".codex-studio") / "runtime" / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
LIVE_SURFACE_PARITY_SCRIPT_PATH = RUN_SERVICES_ROOT / "scripts" / "verify_live_surface_parity.py"
DOWNLOADS_VERSION_MARKER_SCRIPT_PATH = RUN_SERVICES_ROOT / "scripts" / "verify_downloads_version_marker.py"
VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME = ".verification-program-authority"
VERIFICATION_PROGRAM_BINDING_CONTRACT_NAME = "chummer.public_edge_verification_programs.v1"
VERIFICATION_PROGRAM_SOURCES = {
    "downloadsVersionMarker": DOWNLOADS_VERSION_MARKER_SCRIPT_PATH,
    "liveSurfaceParity": LIVE_SURFACE_PARITY_SCRIPT_PATH,
}
RETIRED_PUBLIC_PLAY_PROXY_ENV_NAMES = frozenset(
    {
        "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED",
        "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED",
        "CHUMMER_PUBLIC_PLAY_PROXY_URL",
        "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY",
        "CHUMMER_PUBLIC_PLAY_PROXY_ALLOWED_ORIGINS",
        "CHUMMER_PUBLIC_PLAY_PROXY_ALLOWED_HOSTS",
        "CHUMMER_PUBLIC_PLAY_PROXY_ALLOWLIST",
    }
)
SEALED_PYTHON_PROGRAM_WRAPPER = """
import hashlib
import os
import sys

descriptor = int(sys.argv[1])
expected_sha256 = sys.argv[2]
synthetic_file = sys.argv[3]
os.lseek(descriptor, 0, os.SEEK_SET)
chunks = []
while True:
    chunk = os.read(descriptor, 1024 * 1024)
    if not chunk:
        break
    chunks.append(chunk)
program_bytes = b"".join(chunks)
actual_sha256 = hashlib.sha256(program_bytes).hexdigest()
if actual_sha256 != expected_sha256:
    raise SystemExit("sealed verification program digest mismatch")
sys.argv = [synthetic_file, *sys.argv[4:]]
namespace = {
    "__name__": "__main__",
    "__file__": synthetic_file,
    "__package__": None,
    "__builtins__": __builtins__,
}
exec(compile(program_bytes, synthetic_file, "exec"), namespace, namespace)
""".strip()
ISOLATED_BUILD_WORKSPACE_COPY_MAP = {
    Path("."): (
        Path(".dockerignore"),
    ),
    Path("chummer.run-services"): (
        Path("Directory.Build.props"),
        Path("Directory.Build.targets"),
        Path("global.json"),
        Path(".dockerignore"),
        Path("docker-compose.public-edge.yml"),
        Path("scripts") / "generate_public_play_worker_projection.py",
        Path("scripts") / "public_edge_payload_modes.py",
        Path("scripts") / "strict_json_contract.py",
        Path("scripts") / "validate_public_pwa_proof_authority.py",
        Path("scripts") / "verify_public_pwa_static_assets.py",
        Path("Chummer.Run.Api"),
        Path("Chummer.InstallLinking.Postgres.Tool"),
        Path("Chummer.Campaign.Contracts"),
        Path("Chummer.Control.Contracts"),
        Path("Chummer.Play.Contracts"),
        Path("Chummer.Run.Contracts"),
        Path("Chummer.World.Contracts"),
    ),
    Path("chummer-design"): (
        Path(".dockerignore"),
        Path("products") / "chummer",
    ),
    Path("chummer-core-engine"): (
        Path("Directory.Build.props"),
        Path("Directory.Build.targets"),
        Path("global.json"),
        Path("Chummer.Contracts"),
    ),
    Path("chummer-hub-registry"): (
        Path("Directory.Build.props"),
        Path("Directory.Build.targets"),
        Path("Chummer.Hub.Registry.Contracts"),
        Path("Chummer.Run.Registry"),
    ),
    Path("fleet") / "repos" / "chummer-media-factory": (
        Path("Directory.Build.props"),
        Path("Directory.Build.targets"),
        Path("src") / "Chummer.Media.Contracts",
    ),
}
ISOLATED_OVERLAY_PAYLOAD_COPY_MAP = {
    Path("chummer.run-services"): (
        Path(".codex-design"),
    ),
    Path("chummer-hub-registry"): (
        Path("black-ledger"),
    ),
}
ISOLATED_BUILD_IGNORED_NAMES = frozenset(
    {
        ".codex-studio",
        ".git",
        ".hg",
        ".idea",
        ".state",
        ".svn",
        ".tmp",
        ".vexp",
        ".vs",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "__pycache__",
        "TestResults",
        "bin",
        "bin_tmp",
        "node_modules",
        "obj",
    }
)
REQUIRED_COMPOSE_MOUNTPOINTS = (
    Path("wwwroot") / "proofs" / "mac-codex-release" / "HUB_LOCAL_RELEASE_PROOF.generated.json",
)
REQUIRED_LANDING_MARKERS = {
    "playDisabledTarget": 'data-disabled-target="/mobile/player"',
    "playSignInRoute": 'data-sign-in-href="/login?next=%2Fmobile%2Fplayer"',
    "turnAnchor": "#turn-runsite-card",
    "turnAnchorNormalizedHash": 'const normalizedHash = window.location.hash.split("?")[0];',
    "turnAnchorRedirect": "window.location.replace(`/mobile/player${window.location.search}${normalizedHash}`);",
}
ALLOWED_OVERLAY_ACTIVATION_RECEIPT_FAILURES = frozenset(
    {
        "release channel supportabilityState is not launch-supported",
    }
)
ALLOWED_OVERLAY_ACTIVATION_RECEIPT_FAILURE_PREFIXES = (
    "release channel rolloutState is blocking:",
)
OVERLAY_ACTIVATION_RECEIPT_REQUIRED_TRUE_FIELDS = (
    "release_channel_receipt_sha256_matches",
    "downloads_has_marker",
    "status_redirect_has_marker",
    "downloads_version_marker_matches_release_channel",
    "status_redirect_version_marker_matches_release_channel",
    "status_redirect_heading_matches_release_channel",
    "status_redirect_heading_recognized",
    "visible_version_matches_release_channel",
    "public_release_manifest_exists",
    "public_release_channel_matches_release_channel",
    "public_release_status_matches_release_channel",
    "public_release_version_matches_release_channel",
    "public_release_published_at_matches_release_channel",
    "public_release_proof_freshness_matches_release_channel",
    "public_release_supportability_matches_release_channel",
    "public_release_rollout_matches_release_channel",
    "public_release_copy_safe",
    "public_release_has_preview_or_review_caveat",
    "release_manifest_channel_matches_release_channel",
    "release_manifest_status_matches_release_channel",
    "release_manifest_version_matches_release_channel",
    "release_manifest_published_at_matches_release_channel",
    "release_manifest_proof_freshness_matches_release_channel",
    "release_manifest_supportability_compatible_with_release_channel",
    "release_manifest_rollout_compatible_with_release_channel",
    "release_manifest_internal_supportability_consistent",
    "release_manifest_copy_safe",
    "release_manifest_has_preview_or_review_caveat",
)
OVERLAY_ACTIVATION_RECEIPT_REQUIRED_FALSE_FIELDS = (
    "status_redirect_heading_uses_generic_updated_copy",
)
OVERLAY_ACTIVATION_RECEIPT_REQUIRED_EXACT_FIELDS = {
    "contractName": "chummer.downloads_version_marker.bound.v1",
    "release_channel_receipt_binding_status": "pass",
    "downloads_status": 200,
    "status_status": 200,
    "release_manifest_http_status": 200,
}
OVERLAY_PASS_RECEIPT_REQUIRED_TRUE_FIELDS = tuple(
    field
    for field in OVERLAY_ACTIVATION_RECEIPT_REQUIRED_TRUE_FIELDS
    if field
    not in {
        "public_release_has_preview_or_review_caveat",
        "release_manifest_has_preview_or_review_caveat",
    }
)
CRITICAL_SOURCE_FINGERPRINT_FILES = {
    "landing": Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Landing.cshtml",
    "downloads": Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Downloads.cshtml",
    "status": Path("Chummer.Run.Api") / "Views" / "PublicLanding" / "Status.cshtml",
    "program": Path("Chummer.Run.Api") / "Program.cs",
    "readyForTonight": Path("Chummer.Run.Api") / "Services" / "ReadyForTonightService.cs",
    "authController": Path("Chummer.Run.Api") / "Controllers" / "AuthController.cs",
    "billingAuthController": Path("Chummer.Run.Api") / "Controllers" / "BrilliantDirectoriesBillingController.cs",
    "authEntryView": Path("Chummer.Run.Api") / "Views" / "Auth" / "Entry.cshtml",
    "billingMembershipView": Path("Chummer.Run.Api") / "Views" / "Billing" / "Membership.cshtml",
    "authPolicy": Path("Chummer.Run.Api") / "Services" / "HubEmailSignInPolicy.cs",
    "siteViewModels": Path("Chummer.Run.Api") / "ViewModels" / "SiteViewModels.cs",
}
class OverlayPublishLockUnavailable(RuntimeError):
    pass


class OverlayDiskCapacityError(RuntimeError):
    def __init__(self, check: dict[str, Any]) -> None:
        self.check = check
        failures = check.get("failures")
        rendered_failures = "; ".join(str(item) for item in failures or [])
        super().__init__(
            "public-edge overlay disk-capacity preflight failed"
            + (f": {rendered_failures}" if rendered_failures else "")
        )


class VerificationDeadlineExceeded(BaseException):
    """Internal cancellation that must not be swallowed by broad probe handlers."""

    def __init__(self, *, phase: str, deadline_seconds: float, elapsed_seconds: float) -> None:
        self.phase = phase
        self.deadline_seconds = deadline_seconds
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"local verification exceeded its {deadline_seconds:g}-second global deadline during {phase}"
        )


class OverlayActivationError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        rollback_status: str,
        recovery_path: Path | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rollback_status = rollback_status
        self.recovery_path = recovery_path


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_text(value: object) -> str:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def strict_json_object_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        return strict_json_object(payload, label=label)
    except StrictJsonContractError as exc:
        raise RuntimeError(f"{label} is not strict JSON") from exc


def normalized_absolute_path(path: Path) -> Path:
    """Normalize dot segments without following any symlink in a mutable path."""
    return Path(os.path.abspath(os.fspath(path)))


def assert_no_symlink_components(path: Path, *, label: str) -> None:
    absolute_path = normalized_absolute_path(path)
    current = Path(absolute_path.anchor)
    for component in absolute_path.parts[1:]:
        current /= component
        try:
            component_stat = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeError(f"unable to validate {label} path component {current}: {exc}") from exc
        if stat.S_ISLNK(component_stat.st_mode):
            raise RuntimeError(f"unsafe public-edge overlay {label} contains a symlink component: {current}")


def assert_regular_overlay_tree(root: Path, *, label: str) -> None:
    assert_no_symlink_components(root, label=label)
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise RuntimeError(f"unable to inspect {label} {root}: {exc}") from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise RuntimeError(f"unsafe public-edge overlay {label} is not a directory: {root}")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        directory = Path(dirpath)
        for name in [*dirnames, *filenames]:
            candidate = directory / name
            try:
                candidate_stat = candidate.lstat()
            except OSError as exc:
                raise RuntimeError(f"unable to inspect {label} entry {candidate}: {exc}") from exc
            if stat.S_ISLNK(candidate_stat.st_mode):
                raise RuntimeError(f"unsafe public-edge overlay {label} contains a symlink: {candidate}")
            if not (stat.S_ISDIR(candidate_stat.st_mode) or stat.S_ISREG(candidate_stat.st_mode)):
                raise RuntimeError(
                    f"unsafe public-edge overlay {label} contains a non-regular entry: {candidate}"
                )


def overlay_tree_fingerprint(root: Path, *, label: str) -> dict[str, Any]:
    assert_regular_overlay_tree(root, label=label)
    rows = fingerprint_rows_for_path(root, Path("."))
    return {
        "algorithm": SOURCE_FINGERPRINT_ALGORITHM,
        "aggregateSha256": sha256_text(
            json.dumps(rows, sort_keys=True, separators=(",", ":"))
        ),
        "fileCount": len(rows),
    }


def directory_identity(path: Path, *, label: str) -> dict[str, int]:
    try:
        identity = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"unable to inspect {label} identity {path}: {exc}") from exc
    if not stat.S_ISDIR(identity.st_mode):
        raise RuntimeError(f"unsafe public-edge overlay {label} is not a directory: {path}")
    return {
        "device": identity.st_dev,
        "inode": identity.st_ino,
        "mode": stat.S_IMODE(identity.st_mode),
        "uid": identity.st_uid,
        "gid": identity.st_gid,
        "modifiedTimeNs": identity.st_mtime_ns,
    }


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    assert_no_symlink_components(path.parent, label="receipt parent")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    assert_no_symlink_components(path, label="receipt snapshot")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def read_stable_regular_bytes(
    path: Path,
    *,
    label: str,
    maximum_bytes: int = MAX_RELEASE_CHANNEL_RECEIPT_BYTES,
) -> tuple[bytes, os.stat_result]:
    normalized_path = normalized_absolute_path(path)
    assert_no_symlink_components(normalized_path, label=label)
    try:
        path_stat = normalized_path.lstat()
    except OSError as exc:
        raise RuntimeError(f"unable to inspect {label} {normalized_path}: {exc}") from exc
    if not stat.S_ISREG(path_stat.st_mode):
        raise RuntimeError(f"{label} is not a regular file: {normalized_path}")
    if path_stat.st_size > maximum_bytes:
        raise RuntimeError(f"{label} exceeds {maximum_bytes} bytes: {normalized_path}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(normalized_path, flags)
    except OSError as exc:
        raise RuntimeError(f"unable to open {label} {normalized_path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"{label} is not a regular file: {normalized_path}")
        chunks: list[bytes] = []
        byte_count = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > maximum_bytes:
                raise RuntimeError(f"{label} exceeds {maximum_bytes} bytes: {normalized_path}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

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
        raise RuntimeError(f"{label} changed while it was being read: {normalized_path}")
    return b"".join(chunks), after


def _verification_program_binding_status(binding: dict[str, Any]) -> bool:
    return bool(
        binding.get("status") == "pass"
        and binding.get("sourceSha256Matches") is True
        and binding.get("snapshotSha256Matches") is True
        and binding.get("snapshotIdentityMatches") is True
        and binding.get("snapshotIndependentInode") is True
        and binding.get("snapshotLinkCount") == 1
        and binding.get("snapshotWriteBits") == 0
    )


def refresh_verification_program_binding(binding: dict[str, Any]) -> dict[str, Any]:
    refreshed = dict(binding)
    expected_sha256 = str(binding.get("sha256Expected") or "").strip().lower()
    source_path = normalized_absolute_path(Path(str(binding.get("sourcePath") or "")))
    snapshot_path = normalized_absolute_path(Path(str(binding.get("snapshotPath") or "")))
    try:
        source_bytes, source_stat = read_stable_regular_bytes(
            source_path,
            label="verification program source",
        )
        snapshot_bytes, snapshot_stat = read_stable_regular_bytes(
            snapshot_path,
            label="verification program snapshot",
        )
        source_sha256 = sha256_bytes(source_bytes)
        snapshot_sha256 = sha256_bytes(snapshot_bytes)
        expected_snapshot_identity = (
            int(binding.get("snapshotDevice") or -1),
            int(binding.get("snapshotInode") or -1),
        )
        actual_snapshot_identity = (snapshot_stat.st_dev, snapshot_stat.st_ino)
        independent_inode = (source_stat.st_dev, source_stat.st_ino) != actual_snapshot_identity
        refreshed.update(
            {
                "sourceSha256Actual": source_sha256,
                "sourceSha256Matches": source_sha256 == expected_sha256,
                "snapshotSha256Actual": snapshot_sha256,
                "snapshotSha256Matches": snapshot_sha256 == expected_sha256,
                "snapshotDevice": snapshot_stat.st_dev,
                "snapshotInode": snapshot_stat.st_ino,
                "snapshotIdentityMatches": actual_snapshot_identity == expected_snapshot_identity,
                "snapshotIndependentInode": independent_inode,
                "snapshotLinkCount": snapshot_stat.st_nlink,
                "snapshotWriteBits": stat.S_IMODE(snapshot_stat.st_mode) & 0o222,
                "byteLength": len(snapshot_bytes),
                "error": "",
            }
        )
    except Exception as exc:
        refreshed.update(
            {
                "sourceSha256Actual": "",
                "sourceSha256Matches": False,
                "snapshotSha256Actual": "",
                "snapshotSha256Matches": False,
                "snapshotIdentityMatches": False,
                "snapshotIndependentInode": False,
                "snapshotLinkCount": 0,
                "snapshotWriteBits": -1,
                "error": str(exc),
            }
        )
    refreshed["status"] = "pass" if _verification_program_binding_status(refreshed) else "fail"
    return refreshed


def verification_program_binding_envelope(
    programs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    refreshed = {
        name: refresh_verification_program_binding(binding)
        for name, binding in programs.items()
    }
    expected_names = set(VERIFICATION_PROGRAM_SOURCES)
    status = "pass" if set(refreshed) == expected_names and all(
        _verification_program_binding_status(binding)
        for binding in refreshed.values()
    ) else "fail"
    return {
        "contractName": VERIFICATION_PROGRAM_BINDING_CONTRACT_NAME,
        "status": status,
        "programs": refreshed,
    }


def snapshot_verification_program(
    name: str,
    source_path: Path,
    snapshot_root: Path,
) -> dict[str, Any]:
    source_path = normalized_absolute_path(source_path)
    source_bytes, source_stat = read_stable_regular_bytes(
        source_path,
        label=f"{name} verification program source",
    )
    source_sha256 = sha256_bytes(source_bytes)
    snapshot_path = snapshot_root / f"{source_path.stem}.{source_sha256}.py"
    assert_no_symlink_components(snapshot_path, label=f"{name} verification program snapshot")
    if snapshot_path.exists() or snapshot_path.is_symlink():
        existing_bytes, existing_stat = read_stable_regular_bytes(
            snapshot_path,
            label=f"{name} verification program snapshot",
        )
        if sha256_bytes(existing_bytes) != source_sha256 or existing_bytes != source_bytes:
            raise RuntimeError(
                f"content-addressed {name} verification program snapshot is corrupt: {snapshot_path}"
            )
        if existing_stat.st_nlink != 1:
            raise RuntimeError(
                f"content-addressed {name} verification program snapshot has unsafe hardlinks: {snapshot_path}"
            )
        if stat.S_IMODE(existing_stat.st_mode) & 0o222:
            raise RuntimeError(
                f"content-addressed {name} verification program snapshot is writable: {snapshot_path}"
            )
    else:
        atomic_write_bytes(snapshot_path, source_bytes)
        os.chmod(snapshot_path, 0o444, follow_symlinks=False)
        fsync_directory(snapshot_path.parent)

    snapshot_bytes, snapshot_stat = read_stable_regular_bytes(
        snapshot_path,
        label=f"{name} verification program snapshot",
    )
    if (source_stat.st_dev, source_stat.st_ino) == (snapshot_stat.st_dev, snapshot_stat.st_ino):
        raise RuntimeError(f"{name} verification program snapshot shares the source inode")
    if snapshot_stat.st_nlink != 1:
        raise RuntimeError(f"{name} verification program snapshot has unsafe hardlinks")
    if stat.S_IMODE(snapshot_stat.st_mode) & 0o222:
        raise RuntimeError(f"{name} verification program snapshot remains writable")
    if sha256_bytes(snapshot_bytes) != source_sha256 or snapshot_bytes != source_bytes:
        raise RuntimeError(f"{name} verification program snapshot digest changed after materialization")

    binding = {
        "name": name,
        "sourcePath": str(source_path),
        "snapshotPath": str(snapshot_path),
        "sha256Expected": source_sha256,
        "sourceSha256Actual": source_sha256,
        "sourceSha256Matches": True,
        "snapshotSha256Actual": source_sha256,
        "snapshotSha256Matches": True,
        "snapshotDevice": snapshot_stat.st_dev,
        "snapshotInode": snapshot_stat.st_ino,
        "snapshotIdentityMatches": True,
        "snapshotIndependentInode": True,
        "snapshotLinkCount": snapshot_stat.st_nlink,
        "snapshotWriteBits": stat.S_IMODE(snapshot_stat.st_mode) & 0o222,
        "byteLength": len(snapshot_bytes),
        "error": "",
        "status": "pass",
    }
    return refresh_verification_program_binding(binding)


def snapshot_verification_programs(snapshot_root: Path) -> dict[str, Any]:
    assert_no_symlink_components(snapshot_root, label="verification program authority root")
    snapshot_root.mkdir(parents=True, exist_ok=True)
    programs = {
        name: snapshot_verification_program(name, source_path, snapshot_root)
        for name, source_path in VERIFICATION_PROGRAM_SOURCES.items()
    }
    envelope = verification_program_binding_envelope(programs)
    if envelope["status"] != "pass":
        raise RuntimeError("verification program snapshots failed their initial digest binding")
    return envelope


@contextmanager
def sealed_verification_program_execution(program_binding: dict[str, Any]):
    refreshed = refresh_verification_program_binding(program_binding)
    if not _verification_program_binding_status(refreshed):
        raise RuntimeError("verification program binding failed before sealed execution")
    snapshot_path = Path(str(refreshed["snapshotPath"]))
    snapshot_bytes, _ = read_stable_regular_bytes(
        snapshot_path,
        label="verification program snapshot selected for execution",
    )
    expected_sha256 = str(refreshed["sha256Expected"])
    if sha256_bytes(snapshot_bytes) != expected_sha256:
        raise RuntimeError("verification program snapshot digest changed before sealed execution")
    if not hasattr(os, "memfd_create"):
        raise RuntimeError("sealed verification program execution is unavailable on this host")
    required_fcntl_names = ("F_ADD_SEALS", "F_GET_SEALS", "F_SEAL_SEAL", "F_SEAL_SHRINK", "F_SEAL_GROW", "F_SEAL_WRITE")
    if any(not hasattr(fcntl, name) for name in required_fcntl_names):
        raise RuntimeError("verification program memfd sealing is unavailable on this host")

    descriptor = os.memfd_create(
        f"chummer-{refreshed.get('name')}-{expected_sha256}",
        flags=getattr(os, "MFD_CLOEXEC", 0) | getattr(os, "MFD_ALLOW_SEALING", 0x0002),
    )
    try:
        offset = 0
        while offset < len(snapshot_bytes):
            offset += os.write(descriptor, snapshot_bytes[offset:])
        os.lseek(descriptor, 0, os.SEEK_SET)
        required_seals = (
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE
        )
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, required_seals)
        actual_seals = int(fcntl.fcntl(descriptor, fcntl.F_GET_SEALS))
        if actual_seals & required_seals != required_seals:
            raise RuntimeError("verification program execution memfd is not fully sealed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        sealed_chunks: list[bytes] = []
        while True:
            sealed_chunk = os.read(descriptor, 1024 * 1024)
            if not sealed_chunk:
                break
            sealed_chunks.append(sealed_chunk)
        sealed_sha256 = sha256_bytes(b"".join(sealed_chunks))
        os.lseek(descriptor, 0, os.SEEK_SET)
        if sealed_sha256 != expected_sha256:
            raise RuntimeError("sealed verification program bytes do not match the selected snapshot")
        yield {
            "descriptor": descriptor,
            "path": f"/proc/self/fd/{descriptor}",
            "sha256Expected": expected_sha256,
            "sha256Actual": sealed_sha256,
            "sha256Matches": True,
            "byteLength": len(snapshot_bytes),
            "seals": actual_seals,
            "mode": "sealed_memfd_from_content_addressed_snapshot",
        }
    finally:
        os.close(descriptor)


def _release_manifest_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _release_manifest_nested_text(payload: dict[str, Any], *path: str) -> str:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "").strip()


def read_bound_release_channel_receipt(
    path: Path,
    expected_sha256: str,
) -> tuple[bytes, dict[str, Any]]:
    normalized_path = normalized_absolute_path(path)
    normalized_expected_sha256 = str(expected_sha256 or "").strip().lower()
    if len(normalized_expected_sha256) != 64 or any(
        character not in "0123456789abcdef"
        for character in normalized_expected_sha256
    ):
        raise RuntimeError("release-channel receipt SHA-256 must be exactly 64 hexadecimal characters")

    assert_no_symlink_components(normalized_path, label="release-channel receipt")
    try:
        path_stat = normalized_path.lstat()
    except OSError as exc:
        raise RuntimeError(f"unable to inspect release-channel receipt {normalized_path}: {exc}") from exc
    if not stat.S_ISREG(path_stat.st_mode):
        raise RuntimeError(f"release-channel receipt is not a regular file: {normalized_path}")
    if path_stat.st_size > MAX_RELEASE_CHANNEL_RECEIPT_BYTES:
        raise RuntimeError(
            f"release-channel receipt exceeds {MAX_RELEASE_CHANNEL_RECEIPT_BYTES} bytes: {normalized_path}"
        )

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(normalized_path, flags)
    except OSError as exc:
        raise RuntimeError(f"unable to open release-channel receipt {normalized_path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"release-channel receipt is not a regular file: {normalized_path}")
        chunks: list[bytes] = []
        total_bytes = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_RELEASE_CHANNEL_RECEIPT_BYTES:
                raise RuntimeError(
                    f"release-channel receipt exceeds {MAX_RELEASE_CHANNEL_RECEIPT_BYTES} bytes: {normalized_path}"
                )
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after or total_bytes != before.st_size:
        raise RuntimeError("release-channel receipt changed while it was being read")

    raw_bytes = b"".join(chunks)
    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha256 != normalized_expected_sha256:
        raise RuntimeError(
            "release-channel receipt SHA-256 mismatch: "
            f"expected {normalized_expected_sha256}, got {actual_sha256}"
        )
    parsed = strict_json_object_bytes(raw_bytes, label="release-channel receipt")

    envelope = {
        "selectedPath": str(normalized_path),
        "snapshotPath": "",
        "sha256Expected": normalized_expected_sha256,
        "sha256Actual": actual_sha256,
        "sha256Matches": True,
        "byteLength": len(raw_bytes),
        "status": _release_manifest_text(parsed, "status"),
        "version": _release_manifest_text(parsed, "version", "releaseVersion", "release_version"),
        "channel": _release_manifest_text(parsed, "channel", "channelId", "channel_id"),
        "publishedAt": _release_manifest_text(parsed, "publishedAt", "published_at"),
        "proofFreshnessStatus": _release_manifest_nested_text(
            parsed,
            "publicTrustMetrics",
            "proofFreshness",
            "status",
        ),
        "supportabilityState": _release_manifest_text(
            parsed,
            "supportabilityState",
            "supportability_state",
        ),
    }
    return raw_bytes, envelope


def snapshot_bound_release_channel_receipt(
    snapshot_root: Path,
    raw_bytes: bytes,
    binding: dict[str, Any],
) -> Path:
    snapshot_path = (
        snapshot_root
        / f"RELEASE_CHANNEL.{binding['sha256Actual']}.json"
    )
    atomic_write_bytes(snapshot_path, raw_bytes)
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != binding["sha256Actual"]:
        raise RuntimeError("release-channel receipt snapshot digest changed after atomic write")
    binding["snapshotPath"] = str(snapshot_path)
    return snapshot_path


def _renameat2(left: Path, right: Path, flags: int) -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError) as exc:
        raise RuntimeError("atomic renameat2 is unavailable on this host") from exc
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    left_parent_stat = left.parent.stat()
    right_parent_stat = right.parent.stat()
    left_parent_descriptor = os.open(left.parent, directory_flags)
    try:
        right_parent_descriptor = os.open(right.parent, directory_flags)
        try:
            pinned_left_stat = os.fstat(left_parent_descriptor)
            pinned_right_stat = os.fstat(right_parent_descriptor)
            if (pinned_left_stat.st_dev, pinned_left_stat.st_ino) != (
                left_parent_stat.st_dev,
                left_parent_stat.st_ino,
            ):
                raise RuntimeError(f"atomic rename left parent changed during validation: {left.parent}")
            if (pinned_right_stat.st_dev, pinned_right_stat.st_ino) != (
                right_parent_stat.st_dev,
                right_parent_stat.st_ino,
            ):
                raise RuntimeError(f"atomic rename right parent changed during validation: {right.parent}")
            result = renameat2(
                left_parent_descriptor,
                os.fsencode(left.name),
                right_parent_descriptor,
                os.fsencode(right.name),
                flags,
            )
            if result != 0:
                error_number = ctypes.get_errno()
                if error_number in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.ENOTSUP}:
                    raise RuntimeError("atomic directory rename flags are unsupported by this filesystem")
                raise OSError(error_number, os.strerror(error_number), f"{left} <-> {right}")
        finally:
            os.close(right_parent_descriptor)
    finally:
        os.close(left_parent_descriptor)


def atomic_exchange_overlay_roots(left: Path, right: Path) -> None:
    _renameat2(left, right, RENAME_EXCHANGE)


def atomic_move_overlay_root(source: Path, destination: Path) -> None:
    _renameat2(source, destination, RENAME_NOREPLACE)


def existing_ancestor(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate == candidate.parent:
            raise RuntimeError(f"unable to find an existing ancestor for {path}")
        candidate = candidate.parent
    return candidate


def require_same_filesystem(*paths: Path) -> None:
    devices: dict[Path, int] = {}
    for path in paths:
        ancestor = existing_ancestor(path)
        try:
            devices[path] = ancestor.stat().st_dev
        except OSError as exc:
            raise RuntimeError(f"unable to inspect filesystem for {path}: {exc}") from exc
    if len(set(devices.values())) != 1:
        details = ", ".join(f"{path}={device}" for path, device in devices.items())
        raise RuntimeError(
            "public-edge overlay atomic activation requires one filesystem: " + details
        )


def _read_stable_fingerprint_file(path: Path) -> tuple[bytes, int]:
    try:
        path_identity = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"unable to inspect fingerprinted input {path}: {exc}") from exc
    if stat.S_ISLNK(path_identity.st_mode):
        raise RuntimeError(f"fingerprinted input must not be a symlink: {path}")
    if not stat.S_ISREG(path_identity.st_mode):
        raise RuntimeError(f"fingerprinted input must be a regular file: {path}")
    if path_identity.st_nlink != 1:
        raise RuntimeError(f"fingerprinted input must not have hardlink aliases: {path}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"unable to open fingerprinted input safely {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (before.st_dev, before.st_ino) != (path_identity.st_dev, path_identity.st_ino)
        ):
            raise RuntimeError(f"fingerprinted input changed before it was read: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
        stat.S_IMODE(before.st_mode),
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
        stat.S_IMODE(after.st_mode),
    )
    if before_identity != after_identity or total != before.st_size:
        raise RuntimeError(f"fingerprinted input changed while it was read: {path}")
    try:
        path_after = path.lstat()
    except OSError as exc:
        raise RuntimeError(
            f"fingerprinted input path changed after it was read: {path}"
        ) from exc
    current_path_identity = (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_size,
        path_after.st_mtime_ns,
        path_after.st_ctime_ns,
        path_after.st_nlink,
        stat.S_IMODE(path_after.st_mode),
    )
    if (
        not stat.S_ISREG(path_after.st_mode)
        or path_after.st_nlink != 1
        or current_path_identity != after_identity
    ):
        raise RuntimeError(
            f"fingerprinted input pathname no longer identifies the bytes read: {path}"
        )
    return b"".join(chunks), stat.S_IMODE(after.st_mode)


def fingerprint_rows_for_path(
    source_path: Path,
    logical_root: Path,
    *,
    excluded_relative_paths: tuple[Path, ...] = (),
    include_mode: bool = False,
) -> list[dict[str, Any]]:
    normalized_exclusions: tuple[Path, ...] = tuple(
        Path(str(path).replace("\\", "/")) for path in excluded_relative_paths
    )
    if any(
        path.is_absolute() or path == Path(".") or ".." in path.parts
        for path in normalized_exclusions
    ):
        raise ValueError("fingerprint exclusions must be safe relative paths")

    def is_excluded(relative_path: Path) -> bool:
        return any(
            relative_path == excluded or excluded in relative_path.parents
            for excluded in normalized_exclusions
        )

    candidates: list[Path] = []
    try:
        source_identity = source_path.lstat()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise RuntimeError(f"unable to inspect fingerprinted copy-plan root {source_path}: {exc}") from exc
    if stat.S_ISLNK(source_identity.st_mode):
        raise RuntimeError(f"fingerprinted copy-plan root must not be a symlink: {source_path}")
    if stat.S_ISREG(source_identity.st_mode):
        candidates = [source_path]
    elif stat.S_ISDIR(source_identity.st_mode):
        def fail_walk(error: OSError) -> None:
            raise RuntimeError(
                f"unable to enumerate fingerprinted copy-plan tree {source_path}: {error}"
            ) from error

        for dirpath, dirnames, filenames in os.walk(
            source_path,
            followlinks=False,
            onerror=fail_walk,
        ):
            directory = Path(dirpath)
            relative_directory = directory.relative_to(source_path)
            symlinked_directories = [
                name for name in dirnames if (directory / name).is_symlink()
            ]
            if symlinked_directories:
                raise RuntimeError(
                    "fingerprinted copy-plan tree contains symlinked directories: "
                    + ", ".join(
                        str(directory / name) for name in sorted(symlinked_directories)
                    )
                )
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name not in ISOLATED_BUILD_IGNORED_NAMES
                and not is_excluded(relative_directory / name)
            )
            for filename in sorted(filenames):
                if filename in ISOLATED_BUILD_IGNORED_NAMES:
                    continue
                candidate_relative = relative_directory / filename
                if is_excluded(candidate_relative):
                    continue
                candidates.append(directory / filename)
    else:
        raise RuntimeError(
            f"fingerprinted copy-plan root must be a regular file or directory: {source_path}"
        )

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            if stat.S_ISREG(source_identity.st_mode):
                relative_path = logical_root
            else:
                relative_path = logical_root / candidate.relative_to(source_path)
            payload, mode = _read_stable_fingerprint_file(candidate)
        except (OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError(f"unable to fingerprint copied input {candidate}: {exc}") from exc
        row: dict[str, Any] = {
            "path": str(relative_path).replace(os.sep, "/"),
            "sha256": sha256_bytes(payload),
            "sizeBytes": len(payload),
        }
        if include_mode:
            row["mode"] = f"{mode:04o}"
        rows.append(row)
    return rows


def build_input_rows(source_root: Path) -> list[dict[str, Any]]:
    workspace_root = source_root.parent.resolve()
    source_relative_root = relative_source_root(source_root.resolve(), workspace_root)
    copy_plan: list[tuple[Path, tuple[Path, ...]]] = []
    if source_relative_root == Path("chummer.run-services"):
        for relative_root, include_paths in ISOLATED_BUILD_WORKSPACE_COPY_MAP.items():
            if (workspace_root / relative_root).exists():
                copy_plan.append((relative_root, include_paths))
    else:
        copy_plan.append((source_relative_root, (Path("."),)))

    rows: list[dict[str, Any]] = []
    for relative_root, include_paths in copy_plan:
        for include_path in include_paths:
            source_path = workspace_root / relative_root / include_path
            rows.extend(
                fingerprint_rows_for_path(
                    source_path,
                    relative_root / include_path,
                )
            )
    runtime_mounted_paths = {
        str(source_relative_root / "Chummer.Run.Api" / relative_path).replace(os.sep, "/")
        for relative_path in REQUIRED_COMPOSE_MOUNTPOINTS
    }
    rows = [row for row in rows if str(row.get("path") or "") not in runtime_mounted_paths]
    rows.sort(key=lambda row: str(row["path"]))
    return rows


def build_input_fingerprint(source_root: Path) -> dict[str, Any]:
    rows = build_input_rows(source_root)
    return {
        "algorithm": SOURCE_FINGERPRINT_ALGORITHM,
        "aggregateSha256": sha256_text(
            json.dumps(rows, sort_keys=True, separators=(",", ":"))
        ),
        "fileCount": len(rows),
    }


def overlay_payload_input_rows(source_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    payload_roots = (
        (source_root / ".codex-design", Path("chummer.run-services") / ".codex-design"),
        (
            source_root.parent / "chummer-hub-registry" / "black-ledger",
            Path("chummer-hub-registry") / "black-ledger",
        ),
    )
    for source_path, logical_root in payload_roots:
        rows.extend(fingerprint_rows_for_path(source_path, logical_root))
    rows.sort(key=lambda row: str(row["path"]))
    return rows


def overlay_payload_input_fingerprint(source_root: Path) -> dict[str, Any]:
    rows = overlay_payload_input_rows(source_root)
    return {
        "algorithm": SOURCE_FINGERPRINT_ALGORITHM,
        "aggregateSha256": sha256_text(
            json.dumps(rows, sort_keys=True, separators=(",", ":"))
        ),
        "fileCount": len(rows),
    }


def staged_payload_rows(root: Path) -> list[dict[str, Any]]:
    rows = fingerprint_rows_for_path(
        root,
        Path("."),
        excluded_relative_paths=(
            OVERLAY_BUILD_INFO_RELATIVE_PATH,
            Path("state"),
            *REQUIRED_COMPOSE_MOUNTPOINTS,
        ),
        include_mode=True,
    )
    rows.sort(key=lambda row: str(row["path"]))
    return rows


def staged_payload_runtime_mount_exclusions() -> list[str]:
    return sorted(
        str(relative_path).replace(os.sep, "/")
        for relative_path in REQUIRED_COMPOSE_MOUNTPOINTS
    )


def staged_payload_fingerprint(root: Path) -> dict[str, Any]:
    rows = staged_payload_rows(root)
    payload_mode_receipt = validate_payload_modes(root)
    if payload_mode_receipt.get("status") != "pass":
        raise PayloadModePolicyError(
            "staged payload modes must satisfy the runtime policy before fingerprinting"
        )
    entry_by_path = {
        str(entry.get("relativePath") or ""): entry
        for entry in payload_mode_receipt.get("entries") or []
        if isinstance(entry, dict)
    }
    missing_or_invalid_mountpoints = [
        relative_path
        for relative_path in staged_payload_runtime_mount_exclusions()
        if (entry := entry_by_path.get(relative_path)) is None
        or entry.get("kind") != "file"
        or entry.get("modeActual") != "0644"
        or entry.get("modeExpected") != "0644"
        or entry.get("matches") is not True
    ]
    if missing_or_invalid_mountpoints:
        raise PayloadModePolicyError(
            "staged payload must contain every declared runtime-mounted file exclusion: "
            + ", ".join(missing_or_invalid_mountpoints)
        )
    digest_input = {
        "fileRows": rows,
        "payloadModeEntryBinding": payload_mode_receipt["entryBinding"],
        "payloadModeExecutablePolicy": payload_mode_receipt["executablePolicy"],
    }
    return {
        "algorithm": STAGED_PAYLOAD_FINGERPRINT_ALGORITHM,
        "aggregateSha256": sha256_text(
            json.dumps(digest_input, sort_keys=True, separators=(",", ":"))
        ),
        "fileCount": len(rows),
        "excludedRelativePaths": staged_payload_runtime_mount_exclusions(),
    }


def full_deployment_digest(
    source_fingerprint_value: dict[str, Any],
    staged_payload_fingerprint_value: dict[str, Any],
) -> dict[str, str]:
    """Bind the complete source closure to the exact staged overlay payload bytes."""
    digest_input = {
        "contractName": FULL_DEPLOYMENT_DIGEST_CONTRACT_NAME,
        "algorithm": FULL_DEPLOYMENT_DIGEST_ALGORITHM,
        "sourceFingerprint": source_fingerprint_value,
        "stagedPayloadFingerprint": staged_payload_fingerprint_value,
    }
    return {
        "contractName": FULL_DEPLOYMENT_DIGEST_CONTRACT_NAME,
        "algorithm": FULL_DEPLOYMENT_DIGEST_ALGORITHM,
        "sha256": sha256_text(
            json.dumps(
                digest_input,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        ),
    }


def fingerprint_envelope_matches(
    recorded: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    recorded_count = recorded.get("fileCount")
    recorded_algorithm = recorded.get("algorithm")
    expected_algorithm = expected.get("algorithm")
    return bool(
        recorded_algorithm == expected_algorithm
        and recorded_algorithm
        in {SOURCE_FINGERPRINT_ALGORITHM, STAGED_PAYLOAD_FINGERPRINT_ALGORITHM}
        and len(str(recorded.get("aggregateSha256") or "").strip()) == 64
        and recorded.get("aggregateSha256") == expected.get("aggregateSha256")
        and isinstance(recorded_count, int)
        and not isinstance(recorded_count, bool)
        and recorded_count == expected.get("fileCount")
        and (
            recorded_algorithm == SOURCE_FINGERPRINT_ALGORITHM
            or recorded.get("excludedRelativePaths")
            == expected.get("excludedRelativePaths")
            == staged_payload_runtime_mount_exclusions()
        )
    )


def source_fingerprint(source_root: Path) -> dict[str, Any]:
    files: dict[str, dict[str, str]] = {}
    aggregate_inputs: dict[str, str] = {}
    for key, relative_path in CRITICAL_SOURCE_FINGERPRINT_FILES.items():
        normalized_path = str(relative_path).replace(os.sep, "/")
        absolute_path = source_root / relative_path
        digest = sha256_bytes(absolute_path.read_bytes()) if absolute_path.is_file() else ""
        files[key] = {
            "relativePath": normalized_path,
            "sha256": digest,
        }
        aggregate_inputs[key] = digest
    aggregate_sha = sha256_text(json.dumps(aggregate_inputs, sort_keys=True, separators=(",", ":")))
    return {
        "aggregateSha256": aggregate_sha,
        "files": files,
        "buildInputs": build_input_fingerprint(source_root),
        "overlayPayloadInputs": overlay_payload_input_fingerprint(source_root),
    }


def source_fingerprint_comparison(
    recorded: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    recorded_aggregate = str(recorded.get("aggregateSha256") or "").strip()
    expected_aggregate = str(expected.get("aggregateSha256") or "").strip()
    recorded_files = recorded.get("files") if isinstance(recorded.get("files"), dict) else {}
    expected_files = expected.get("files") if isinstance(expected.get("files"), dict) else {}
    critical_file_detail_mismatches: list[str] = []
    if set(recorded_files) != set(expected_files):
        critical_file_detail_mismatches.extend(
            f"missing:{key}" for key in sorted(set(expected_files) - set(recorded_files))
        )
        critical_file_detail_mismatches.extend(
            f"unexpected:{key}" for key in sorted(set(recorded_files) - set(expected_files))
        )
    for key, expected_entry_value in expected_files.items():
        expected_entry = expected_entry_value if isinstance(expected_entry_value, dict) else {}
        recorded_entry_value = recorded_files.get(key)
        recorded_entry = recorded_entry_value if isinstance(recorded_entry_value, dict) else {}
        expected_relative_path = str(expected_entry.get("relativePath") or "").strip()
        recorded_relative_path = str(recorded_entry.get("relativePath") or "").strip()
        expected_sha = str(expected_entry.get("sha256") or "").strip()
        recorded_sha = str(recorded_entry.get("sha256") or "").strip()
        if (
            not expected_relative_path
            or recorded_relative_path != expected_relative_path
            or len(expected_sha) != 64
            or recorded_sha != expected_sha
        ):
            critical_file_detail_mismatches.append(key)
    critical_file_details_match = bool(expected_files) and not critical_file_detail_mismatches
    recorded_build_inputs = (
        recorded.get("buildInputs") if isinstance(recorded.get("buildInputs"), dict) else {}
    )
    expected_build_inputs = (
        expected.get("buildInputs") if isinstance(expected.get("buildInputs"), dict) else {}
    )
    recorded_build_aggregate = str(
        recorded_build_inputs.get("aggregateSha256") or ""
    ).strip()
    expected_build_aggregate = str(
        expected_build_inputs.get("aggregateSha256") or ""
    ).strip()
    recorded_build_count = recorded_build_inputs.get("fileCount")
    expected_build_count = expected_build_inputs.get("fileCount")
    recorded_build_algorithm = str(recorded_build_inputs.get("algorithm") or "").strip()
    expected_build_algorithm = str(expected_build_inputs.get("algorithm") or "").strip()
    build_input_algorithm_matches = bool(
        recorded_build_algorithm == SOURCE_FINGERPRINT_ALGORITHM
        and expected_build_algorithm == SOURCE_FINGERPRINT_ALGORITHM
    )
    recorded_overlay_payload_inputs = (
        recorded.get("overlayPayloadInputs")
        if isinstance(recorded.get("overlayPayloadInputs"), dict)
        else {}
    )
    expected_overlay_payload_inputs = (
        expected.get("overlayPayloadInputs")
        if isinstance(expected.get("overlayPayloadInputs"), dict)
        else {}
    )
    recorded_overlay_payload_algorithm = str(
        recorded_overlay_payload_inputs.get("algorithm") or ""
    ).strip()
    expected_overlay_payload_algorithm = str(
        expected_overlay_payload_inputs.get("algorithm") or ""
    ).strip()
    recorded_overlay_payload_aggregate = str(
        recorded_overlay_payload_inputs.get("aggregateSha256") or ""
    ).strip()
    expected_overlay_payload_aggregate = str(
        expected_overlay_payload_inputs.get("aggregateSha256") or ""
    ).strip()
    recorded_overlay_payload_count = recorded_overlay_payload_inputs.get("fileCount")
    expected_overlay_payload_count = expected_overlay_payload_inputs.get("fileCount")
    overlay_payload_inputs_match = bool(
        recorded_overlay_payload_algorithm == SOURCE_FINGERPRINT_ALGORITHM
        and expected_overlay_payload_algorithm == SOURCE_FINGERPRINT_ALGORITHM
        and len(recorded_overlay_payload_aggregate) == 64
        and recorded_overlay_payload_aggregate == expected_overlay_payload_aggregate
        and isinstance(recorded_overlay_payload_count, int)
        and not isinstance(recorded_overlay_payload_count, bool)
        and recorded_overlay_payload_count == expected_overlay_payload_count
    )
    critical_matches = bool(
        len(recorded_aggregate) == 64
        and recorded_aggregate == expected_aggregate
        and critical_file_details_match
    )
    build_inputs_match = bool(
        build_input_algorithm_matches
        and len(recorded_build_aggregate) == 64
        and recorded_build_aggregate == expected_build_aggregate
        and isinstance(recorded_build_count, int)
        and not isinstance(recorded_build_count, bool)
        and recorded_build_count == expected_build_count
    )
    return {
        "recordedAggregateSha256": recorded_aggregate,
        "expectedAggregateSha256": expected_aggregate,
        "criticalFilesMatchCurrentSource": critical_matches,
        "criticalFileDetailsMatchCurrentSource": critical_file_details_match,
        "criticalFileDetailMismatches": sorted(set(critical_file_detail_mismatches)),
        "recordedBuildInputAlgorithm": recorded_build_algorithm,
        "expectedBuildInputAlgorithm": expected_build_algorithm,
        "buildInputAlgorithmMatches": build_input_algorithm_matches,
        "recordedBuildInputAggregateSha256": recorded_build_aggregate,
        "expectedBuildInputAggregateSha256": expected_build_aggregate,
        "recordedBuildInputFileCount": recorded_build_count,
        "expectedBuildInputFileCount": expected_build_count,
        "buildInputsMatchCurrentSource": build_inputs_match,
        "recordedOverlayPayloadInputAlgorithm": recorded_overlay_payload_algorithm,
        "expectedOverlayPayloadInputAlgorithm": expected_overlay_payload_algorithm,
        "recordedOverlayPayloadInputAggregateSha256": recorded_overlay_payload_aggregate,
        "expectedOverlayPayloadInputAggregateSha256": expected_overlay_payload_aggregate,
        "recordedOverlayPayloadInputFileCount": recorded_overlay_payload_count,
        "expectedOverlayPayloadInputFileCount": expected_overlay_payload_count,
        "overlayPayloadInputsMatchCurrentSource": overlay_payload_inputs_match,
        "matchesCurrentSource": (
            critical_matches and build_inputs_match and overlay_payload_inputs_match
        ),
    }


def staged_source_fingerprint_check(staging_root: Path, source_root: Path) -> dict[str, Any]:
    build_info_path = staging_root / OVERLAY_BUILD_INFO_RELATIVE_PATH
    expected = source_fingerprint(source_root)
    recorded: dict[str, Any] = {}
    recorded_staged_payload_fingerprint: dict[str, Any] = {}
    recorded_payload_mode_receipt: dict[str, Any] = {}
    payload: dict[str, Any] = {}
    reason = ""
    if not build_info_path.is_file():
        reason = "staging_build_info_missing"
    else:
        try:
            parsed_payload = strict_json_object_bytes(
                build_info_path.read_bytes(),
                label="staging build-info receipt",
            )
        except (OSError, RuntimeError):
            reason = "staging_build_info_invalid"
        else:
            payload = parsed_payload
            candidate = payload.get("sourceFingerprint")
            if isinstance(candidate, dict):
                recorded = candidate
            elif not reason:
                reason = "staging_source_fingerprint_missing"
            staged_payload_candidate = payload.get("stagedPayloadFingerprint")
            if isinstance(staged_payload_candidate, dict):
                recorded_staged_payload_fingerprint = staged_payload_candidate
            payload_mode_candidate = payload.get("payloadModeReceipt")
            if isinstance(payload_mode_candidate, dict):
                recorded_payload_mode_receipt = payload_mode_candidate

    comparison = source_fingerprint_comparison(recorded, expected)
    try:
        expected_staged_payload_fingerprint = staged_payload_fingerprint(staging_root)
    except RuntimeError:
        expected_staged_payload_fingerprint = {}
        if not reason:
            reason = "staging_payload_shape_or_mode_invalid"
    staged_payload_matches = fingerprint_envelope_matches(
        recorded_staged_payload_fingerprint,
        expected_staged_payload_fingerprint,
    )
    payload_mode_binding: dict[str, Any] = {
        "status": "fail",
        "failures": ["payload_mode_receipt_missing"],
    }
    if recorded_payload_mode_receipt:
        try:
            payload_mode_binding = validate_payload_modes_against_receipt(
                staging_root,
                recorded_payload_mode_receipt,
            )
        except RuntimeError:
            payload_mode_binding = {
                "status": "fail",
                "failures": ["payload_mode_receipt_invalid"],
            }
    matches = bool(
        not reason
        and comparison["matchesCurrentSource"]
        and staged_payload_matches
        and payload_mode_binding.get("status") == "pass"
    )
    if not reason and not comparison["recordedBuildInputAggregateSha256"]:
        reason = "staging_build_input_fingerprint_missing"
    elif not reason and not comparison["recordedOverlayPayloadInputAggregateSha256"]:
        reason = "staging_overlay_payload_fingerprint_missing"
    elif not reason and not recorded_staged_payload_fingerprint:
        reason = "staging_payload_fingerprint_missing"
    elif not reason and not recorded_payload_mode_receipt:
        reason = "staging_payload_mode_receipt_missing"
    elif not reason and payload_mode_binding.get("status") != "pass":
        reason = "staging_payload_mode_receipt_mismatch"
    elif not reason and not staged_payload_matches:
        reason = "staging_payload_fingerprint_mismatch"
    elif not reason and not matches:
        reason = "staging_source_fingerprint_mismatch"
    return {
        "status": "pass" if matches else "fail",
        "reason": reason,
        "buildInfoPath": str(build_info_path),
        **comparison,
        "stagedPayloadMatchesRecordedFingerprint": staged_payload_matches,
        "recordedStagedPayloadFingerprint": recorded_staged_payload_fingerprint,
        "expectedStagedPayloadFingerprint": expected_staged_payload_fingerprint,
        "recordedPayloadModeReceipt": recorded_payload_mode_receipt,
        "payloadModeBinding": payload_mode_binding,
        "recordedSourceFingerprint": recorded,
        "expectedSourceFingerprint": expected,
    }


def validated_timeout_seconds(value: object, *, label: str, maximum: float) -> float:
    try:
        timeout_seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must be a finite positive number") from exc
    if (
        not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > maximum
    ):
        raise RuntimeError(
            f"{label} must be greater than 0 and no more than {maximum:g} seconds"
        )
    return timeout_seconds


def validated_minimum_free_disk_bytes(value: object) -> int:
    if isinstance(value, bool):
        raise RuntimeError("minimum free disk bytes must be a non-negative integer")
    try:
        minimum_free_bytes = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError("minimum free disk bytes must be a non-negative integer") from exc
    if (
        isinstance(value, float)
        and (not math.isfinite(value) or value != minimum_free_bytes)
    ):
        raise RuntimeError("minimum free disk bytes must be a non-negative integer")
    if minimum_free_bytes < 0 or minimum_free_bytes > MAX_MINIMUM_FREE_DISK_BYTES:
        raise RuntimeError(
            "minimum free disk bytes must be between 0 and "
            f"{MAX_MINIMUM_FREE_DISK_BYTES}"
        )
    return minimum_free_bytes


def nearest_existing_capacity_probe(path: Path) -> Path:
    probe = normalized_absolute_path(path)
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            raise RuntimeError(
                f"unable to find an existing parent for disk-capacity probe: {path}"
            )
        probe = parent
    if not probe.is_dir():
        probe = probe.parent
    return probe


def disk_capacity_check(
    *,
    staging_root: Path,
    build_root: Path,
    minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_DISK_BYTES,
    allow_low_disk_capacity: bool = False,
) -> dict[str, Any]:
    minimum_free_bytes = validated_minimum_free_disk_bytes(minimum_free_bytes)
    roots = {
        "stagingRoot": normalized_absolute_path(staging_root),
        "buildRoot": normalized_absolute_path(build_root),
    }
    filesystems_by_device: dict[int, dict[str, Any]] = {}
    for label, root in roots.items():
        assert_no_symlink_components(root, label=f"{label} disk-capacity root")
        probe = nearest_existing_capacity_probe(root)
        probe_stat = probe.stat()
        usage = shutil.disk_usage(probe)
        device = int(probe_stat.st_dev)
        entry = filesystems_by_device.setdefault(
            device,
            {
                "device": device,
                "probePath": str(probe),
                "roots": [],
                "totalBytes": int(usage.total),
                "usedBytes": int(usage.used),
                "freeBytes": int(usage.free),
            },
        )
        entry["roots"].append({"label": label, "path": str(root)})
        entry["freeBytes"] = min(int(entry["freeBytes"]), int(usage.free))
        entry["sufficient"] = bool(
            int(entry["freeBytes"]) >= minimum_free_bytes
        )

    filesystems = sorted(filesystems_by_device.values(), key=lambda item: int(item["device"]))
    failures = [
        (
            f"device {item['device']} has {item['freeBytes']} free bytes; "
            f"requires at least {minimum_free_bytes}"
        )
        for item in filesystems
        if item.get("sufficient") is not True
    ]
    status = "pass" if not failures else "overridden" if allow_low_disk_capacity else "fail"
    return {
        "status": status,
        "checkedAtUtc": now_iso(),
        "minimumFreeBytes": minimum_free_bytes,
        "defaultMinimumFreeBytes": DEFAULT_MINIMUM_FREE_DISK_BYTES,
        "overrideRequested": bool(allow_low_disk_capacity),
        "filesystems": filesystems,
        "failures": failures,
    }


def require_disk_capacity(**kwargs: Any) -> dict[str, Any]:
    check = disk_capacity_check(**kwargs)
    if check["status"] == "fail":
        raise OverlayDiskCapacityError(check)
    return check


def preflight_disk_capacity_matches(
    check: dict[str, Any],
    *,
    staging_root: Path,
    build_root: Path,
    minimum_free_bytes: int,
    allow_low_disk_capacity: bool,
) -> bool:
    observed_roots = {
        str(root.get("label") or ""): normalized_absolute_path(
            Path(str(root.get("path") or "."))
        )
        for filesystem in check.get("filesystems") or []
        if isinstance(filesystem, dict)
        for root in filesystem.get("roots") or []
        if isinstance(root, dict)
    }
    return bool(
        check.get("status") in {"pass", "overridden"}
        and check.get("minimumFreeBytes") == minimum_free_bytes
        and check.get("overrideRequested") is bool(allow_low_disk_capacity)
        and observed_roots.get("stagingRoot") == normalized_absolute_path(staging_root)
        and observed_roots.get("buildRoot") == normalized_absolute_path(build_root)
    )


class VerificationBudget:
    def __init__(self, deadline_seconds: float) -> None:
        self.deadline_seconds = validated_timeout_seconds(
            deadline_seconds,
            label="global verification deadline",
            maximum=MAX_VERIFICATION_DEADLINE_SECONDS,
        )
        self.started_at_monotonic = time.monotonic()
        self.deadline_at_monotonic = (
            self.started_at_monotonic + self.deadline_seconds
        )
        self.phase = "verification_setup"

    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_at_monotonic)

    def remaining_seconds(
        self,
        phase: str,
        per_operation_limit: float | None = None,
    ) -> float:
        self.phase = phase
        remaining = self.deadline_at_monotonic - time.monotonic()
        if remaining <= 0:
            raise self.timeout_error()
        if per_operation_limit is not None:
            remaining = min(
                remaining,
                validated_timeout_seconds(
                    per_operation_limit,
                    label=f"{phase} timeout",
                    maximum=MAX_VERIFICATION_DEADLINE_SECONDS,
                ),
            )
        return max(0.001, remaining)

    def timeout_error(self) -> VerificationDeadlineExceeded:
        return VerificationDeadlineExceeded(
            phase=self.phase,
            deadline_seconds=self.deadline_seconds,
            elapsed_seconds=self.elapsed_seconds(),
        )


@contextmanager
def enforce_verification_wall_clock_deadline(
    budget: VerificationBudget,
):
    if (
        threading.current_thread() is not threading.main_thread()
        or not hasattr(signal, "SIGALRM")
        or not hasattr(signal, "setitimer")
    ):
        raise RuntimeError(
            "hard global verification deadline requires the Unix main thread"
        )
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    armed_at = time.monotonic()

    def deadline_handler(_signum: int, _frame: object) -> None:
        raise budget.timeout_error()

    signal.signal(signal.SIGALRM, deadline_handler)
    signal.setitimer(signal.ITIMER_REAL, budget.remaining_seconds("verification_setup"))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)
        previous_delay, previous_interval = previous_timer
        if previous_delay > 0:
            elapsed = max(0.0, time.monotonic() - armed_at)
            signal.setitimer(
                signal.ITIMER_REAL,
                max(0.001, previous_delay - elapsed),
                previous_interval,
            )


def _terminate_process_group(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        stdout, stderr = process.communicate(
            timeout=PUBLISH_TIMEOUT_TERMINATION_GRACE_SECONDS
        )
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate(
            timeout=PUBLISH_TIMEOUT_TERMINATION_GRACE_SECONDS
        )
    return stdout or "", stderr or ""


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: float = DEFAULT_PUBLISH_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    bounded_timeout_seconds = validated_timeout_seconds(
        timeout_seconds,
        label="publish timeout",
        maximum=MAX_PUBLISH_TIMEOUT_SECONDS,
    )
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=bounded_timeout_seconds)
    except subprocess.TimeoutExpired:
        stdout, stderr = _terminate_process_group(process)
        timeout_message = (
            "public-edge overlay publish timed out after "
            f"{bounded_timeout_seconds:g} seconds; the isolated process group was terminated"
        )
        stderr = f"{stderr.rstrip()}\n{timeout_message}\n" if stderr else timeout_message + "\n"
        return subprocess.CompletedProcess(
            args=command,
            returncode=PUBLISH_TIMEOUT_EXIT_CODE,
            stdout=stdout or "",
            stderr=stderr,
        )
    return subprocess.CompletedProcess(
        args=command,
        returncode=process.returncode,
        stdout=stdout or "",
        stderr=stderr or "",
    )


def publish_lock_path(source_root: Path, active_root: Path | None = None) -> Path:
    if active_root is not None:
        return normalized_absolute_path(active_root).parent / DEFAULT_PUBLISH_LOCK_FILE
    return normalized_absolute_path(source_root) / ".state" / DEFAULT_PUBLISH_LOCK_FILE


@contextmanager
def overlay_publish_lock(source_root: Path, active_root: Path | None = None):
    lock_path = publish_lock_path(source_root, active_root)
    assert_no_symlink_components(lock_path.parent, label="publish lock parent")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise OverlayPublishLockUnavailable(f"unable to open public-edge overlay lock {lock_path}: {exc}") from exc
    try:
        opened_stat = os.fstat(descriptor)
        path_stat = os.lstat(lock_path)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or opened_stat.st_nlink != 1
            or (opened_stat.st_dev, opened_stat.st_ino)
            != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise OverlayPublishLockUnavailable(
                f"public-edge overlay lock changed identity or has unsafe hardlinks: {lock_path}"
            )
    except Exception:
        os.close(descriptor)
        raise
    handle = os.fdopen(descriptor, "r+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip() or "unknown owner"
            raise OverlayPublishLockUnavailable(
                f"another public-edge overlay publisher already owns {lock_path}: {owner}"
            ) from exc
        try:
            locked_stat = os.fstat(handle.fileno())
            current_path_stat = os.lstat(lock_path)
        except OSError as exc:
            raise OverlayPublishLockUnavailable(
                f"unable to revalidate public-edge overlay lock {lock_path}: {exc}"
            ) from exc
        if (
            not stat.S_ISREG(locked_stat.st_mode)
            or locked_stat.st_nlink != 1
            or (locked_stat.st_dev, locked_stat.st_ino)
            != (current_path_stat.st_dev, current_path_stat.st_ino)
        ):
            raise OverlayPublishLockUnavailable(
                f"public-edge overlay lock changed identity or has unsafe hardlinks: {lock_path}"
            )
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "sourceRoot": str(source_root.resolve()),
                    "startedAtUtc": now_iso(),
                },
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()
        try:
            yield lock_path
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def ignored_isolated_build_entries(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in ISOLATED_BUILD_IGNORED_NAMES}


def copy_file_with_hardlink_fallback(source: str | Path, destination: str | Path) -> str | os.PathLike[str]:
    # The isolated workspace is a source snapshot, not a second view of the
    # live inode. Hardlinks let in-place source edits mutate the build inputs
    # after their fingerprint was recorded.
    return shutil.copy2(source, destination)


def relative_source_root(source_root: Path, workspace_root: Path) -> Path:
    try:
        return source_root.relative_to(workspace_root)
    except ValueError:
        return Path(source_root.name)


def paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def paths_alias_or_overlap(left: Path, right: Path) -> bool:
    left_normalized = normalized_absolute_path(left)
    right_normalized = normalized_absolute_path(right)
    if paths_overlap(left_normalized, right_normalized):
        return True
    left_resolved = left_normalized.resolve(strict=False)
    right_resolved = right_normalized.resolve(strict=False)
    return paths_overlap(left_resolved, right_resolved)


def path_is_within(path: Path, root: Path) -> bool:
    normalized_path = normalized_absolute_path(path)
    normalized_root = normalized_absolute_path(root)
    return normalized_path == normalized_root or normalized_root in normalized_path.parents


def paths_are_aliases(left: Path, right: Path) -> bool:
    left_normalized = normalized_absolute_path(left)
    right_normalized = normalized_absolute_path(right)
    if (
        left_normalized == right_normalized
        or left_normalized.resolve(strict=False) == right_normalized.resolve(strict=False)
    ):
        return True
    try:
        left_stat = left_normalized.lstat()
        right_stat = right_normalized.lstat()
    except OSError:
        return False
    return (left_stat.st_dev, left_stat.st_ino) == (right_stat.st_dev, right_stat.st_ino)


def assert_safe_planned_file(path: Path, *, label: str) -> None:
    assert_no_symlink_components(path, label=label)
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError(f"unable to inspect {label} {path}: {exc}") from exc
    if not stat.S_ISREG(path_stat.st_mode):
        raise RuntimeError(f"unsafe public-edge overlay {label} is not a regular file: {path}")
    if path_stat.st_nlink != 1:
        raise RuntimeError(
            f"unsafe public-edge overlay {label} has hardlink aliases: {path}"
        )


def assert_safe_planned_directory(path: Path, *, label: str) -> None:
    assert_no_symlink_components(path, label=label)
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError(f"unable to inspect {label} {path}: {exc}") from exc
    if not stat.S_ISDIR(path_stat.st_mode):
        raise RuntimeError(f"unsafe public-edge overlay {label} is not a directory: {path}")


def validate_publisher_path_plan(
    *,
    output: Path,
    release_channel_receipt: Path,
    release_channel_receipt_sha256: str,
    source_root: Path,
    staging_root: Path,
    active_root: Path,
    backup_root: Path,
    build_root: Path,
    activation_mode: str,
) -> dict[str, Path]:
    if activation_mode != "copy":
        raise RuntimeError(
            "public-edge overlay hardlink activation is disabled; activation must use independent staged bytes"
        )
    normalized_sha256 = str(release_channel_receipt_sha256 or "").strip().lower()
    if len(normalized_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in normalized_sha256
    ):
        raise RuntimeError("release-channel receipt SHA-256 must be exactly 64 hexadecimal characters")

    source_root = normalized_absolute_path(source_root.resolve())
    output = normalized_absolute_path(output)
    release_channel_receipt = normalized_absolute_path(release_channel_receipt)
    staging_root = normalized_absolute_path(staging_root)
    active_root = normalized_absolute_path(active_root)
    backup_root = normalized_absolute_path(backup_root)
    build_root = normalized_absolute_path(build_root)
    validate_materialize_roots(
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
    )

    output_parent = output.parent
    release_authority_root = output_parent / ".release-channel-authority"
    verification_program_authority_root = (
        output_parent / VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME
    )
    release_channel_snapshot = (
        release_authority_root / f"RELEASE_CHANNEL.{normalized_sha256}.json"
    )
    verification_receipt = output_parent / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json"
    local_parity_receipt = output_parent / "LIVE_SURFACE_PARITY.local-overlay.generated.json"
    startup_log = output_parent / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.startup.log"
    staging_build_info = staging_root / OVERLAY_BUILD_INFO_RELATIVE_PATH
    active_build_info = active_root / OVERLAY_BUILD_INFO_RELATIVE_PATH
    lock_file = publish_lock_path(source_root, active_root)
    activation_journal = activation_transaction_journal_path(active_root)

    planned_files = {
        "output receipt": output,
        "release-channel snapshot": release_channel_snapshot,
        "verification receipt": verification_receipt,
        "local parity receipt": local_parity_receipt,
        "startup log": startup_log,
        "staging build-info receipt": staging_build_info,
        "active build-info receipt": active_build_info,
        "publish lock": lock_file,
        "activation journal": activation_journal,
    }
    planned_directories = {
        "release-channel authority root": release_authority_root,
        "verification-program authority root": verification_program_authority_root,
    }
    for label, path in planned_files.items():
        assert_safe_planned_file(path, label=label)
    for label, path in planned_directories.items():
        assert_safe_planned_directory(path, label=label)
    assert_no_symlink_components(release_channel_receipt, label="selected release-channel receipt")

    file_items = list(planned_files.items())
    for index, (left_label, left_path) in enumerate(file_items):
        for right_label, right_path in file_items[index + 1 :]:
            if paths_are_aliases(left_path, right_path):
                raise RuntimeError(
                    "unsafe public-edge overlay reserved path collision: "
                    f"{left_label}={left_path} and {right_label}={right_path}"
                )
    directory_items = list(planned_directories.items())
    for index, (left_label, left_path) in enumerate(directory_items):
        for right_label, right_path in directory_items[index + 1 :]:
            if paths_alias_or_overlap(left_path, right_path):
                raise RuntimeError(
                    "unsafe public-edge overlay reserved authority-root collision: "
                    f"{left_label}={left_path} and {right_label}={right_path}"
                )
    allowed_file_directory_containment = {
        ("release-channel snapshot", "release-channel authority root"),
    }
    for file_label, file_path in planned_files.items():
        for directory_label, directory_path in planned_directories.items():
            if (file_label, directory_label) in allowed_file_directory_containment:
                continue
            if paths_alias_or_overlap(file_path, directory_path):
                raise RuntimeError(
                    "unsafe public-edge overlay reserved file/authority-root collision: "
                    f"{file_label}={file_path} and {directory_label}={directory_path}"
                )

    mutable_roots = {
        "stagingRoot": staging_root,
        "activeRoot": active_root,
        "backupRoot": backup_root,
        "buildRoot": build_root,
    }
    output_side_files = {
        label: path
        for label, path in planned_files.items()
        if label
        in {
            "output receipt",
            "release-channel snapshot",
            "verification receipt",
            "local parity receipt",
            "startup log",
        }
    }
    for file_label, file_path in output_side_files.items():
        for root_label, root_path in mutable_roots.items():
            if paths_alias_or_overlap(file_path, root_path):
                raise RuntimeError(
                    "unsafe public-edge overlay derived write overlaps a mutable root: "
                    f"{file_label}={file_path} {root_label}={root_path}"
                )
    for directory_label, directory_path in planned_directories.items():
        for root_label, root_path in mutable_roots.items():
            if paths_alias_or_overlap(directory_path, root_path):
                raise RuntimeError(
                    "unsafe public-edge overlay authority root overlaps a mutable root: "
                    f"{directory_label}={directory_path} {root_label}={root_path}"
                )
    active_transaction_namespace = active_root.parent
    for path_label, path in {**output_side_files, **planned_directories}.items():
        if path_is_within(path, active_transaction_namespace) or path_is_within(
            path.resolve(strict=False),
            active_transaction_namespace.resolve(strict=False),
        ):
            raise RuntimeError(
                "unsafe public-edge overlay derived write enters the reserved active transaction namespace: "
                f"{path_label}={path} namespace={active_transaction_namespace}"
            )

    allowed_source_receipt_root = source_root / ".codex-studio" / "published"
    for file_label, file_path in output_side_files.items():
        if path_is_within(file_path.resolve(strict=False), source_root.resolve(strict=False)) and not path_is_within(
            file_path.resolve(strict=False),
            allowed_source_receipt_root.resolve(strict=False),
        ):
            raise RuntimeError(
                "unsafe public-edge overlay derived write enters the source tree outside the confined receipt root: "
                f"{file_label}={file_path} allowedRoot={allowed_source_receipt_root}"
            )
    for directory_label, directory_path in planned_directories.items():
        if path_is_within(directory_path.resolve(strict=False), source_root.resolve(strict=False)) and not path_is_within(
            directory_path.resolve(strict=False),
            allowed_source_receipt_root.resolve(strict=False),
        ):
            raise RuntimeError(
                "unsafe public-edge overlay authority root enters the source tree outside the confined receipt root: "
                f"{directory_label}={directory_path} allowedRoot={allowed_source_receipt_root}"
            )

    for label, path in {**planned_files, **planned_directories}.items():
        if paths_are_aliases(path, release_channel_receipt):
            raise RuntimeError(
                "unsafe public-edge overlay derived path aliases the selected release-channel receipt: "
                f"{label}={path} selected={release_channel_receipt}"
            )
    for authority_label, authority_root in planned_directories.items():
        if path_is_within(release_channel_receipt, authority_root) or path_is_within(
            release_channel_receipt.resolve(strict=False),
            authority_root.resolve(strict=False),
        ):
            raise RuntimeError(
                "unsafe selected release-channel receipt is inside a publisher authority root: "
                f"{authority_label}={authority_root} selected={release_channel_receipt}"
            )
    for root_label, root_path in mutable_roots.items():
        if path_is_within(release_channel_receipt, root_path) or path_is_within(
            release_channel_receipt.resolve(strict=False),
            root_path.resolve(strict=False),
        ):
            raise RuntimeError(
                "unsafe selected release-channel receipt is inside a mutable publisher root: "
                f"selected={release_channel_receipt} {root_label}={root_path}"
            )

    return {
        "output": output,
        "releaseChannelReceipt": release_channel_receipt,
        "sourceRoot": source_root,
        "stagingRoot": staging_root,
        "activeRoot": active_root,
        "backupRoot": backup_root,
        "buildRoot": build_root,
        "releaseAuthorityRoot": release_authority_root,
        "releaseChannelSnapshot": release_channel_snapshot,
        "verificationProgramAuthorityRoot": verification_program_authority_root,
        "verificationReceipt": verification_receipt,
        "localParityReceipt": local_parity_receipt,
        "startupLog": startup_log,
        "stagingBuildInfo": staging_build_info,
        "activeBuildInfo": active_build_info,
        "publishLock": lock_file,
        "activationJournal": activation_journal,
    }


def invalidate_prior_publisher_outputs(path_plan: dict[str, Path]) -> list[str]:
    invalidated: list[str] = []
    parent_directories: set[Path] = set()
    for key, label in (
        ("output", "prior output receipt"),
        ("verificationReceipt", "prior verification receipt"),
        ("localParityReceipt", "prior local-parity receipt"),
        ("startupLog", "prior verification startup log"),
    ):
        path = path_plan[key]
        if not path.exists() and not path.is_symlink():
            continue
        assert_safe_planned_file(path, label=label)
        path.unlink()
        invalidated.append(str(path))
        parent_directories.add(path.parent)
    for parent in parent_directories:
        fsync_directory(parent)
    return invalidated


def validate_materialize_roots(
    *,
    source_root: Path,
    staging_root: Path,
    active_root: Path,
    backup_root: Path,
    build_root: Path,
) -> None:
    mutable_roots = {
        "stagingRoot": staging_root,
        "activeRoot": active_root,
        "backupRoot": backup_root,
        "buildRoot": build_root,
    }
    names = list(mutable_roots)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            left = mutable_roots[left_name]
            right = mutable_roots[right_name]
            left_resolved = left.resolve(strict=False)
            right_resolved = right.resolve(strict=False)
            if paths_overlap(left, right) or paths_overlap(left_resolved, right_resolved):
                raise RuntimeError(
                    f"unsafe public-edge overlay roots overlap: {left_name}={left} and {right_name}={right}"
                )
    for name in ("stagingRoot", "buildRoot", "activeRoot", "backupRoot"):
        mutable_root = mutable_roots[name]
        assert_no_symlink_components(mutable_root, label=name)
        if mutable_root.exists() and not mutable_root.is_dir():
            raise RuntimeError(f"unsafe public-edge overlay root is not a directory: {name}={mutable_root}")
        mutable_resolved = mutable_root.resolve(strict=False)
        if (
            mutable_root == source_root
            or mutable_root in source_root.parents
            or mutable_resolved == source_root
            or mutable_resolved in source_root.parents
        ):
            raise RuntimeError(
                f"unsafe public-edge overlay root contains the source tree: {name}={mutable_root} sourceRoot={source_root}"
            )


def materialize_isolated_build_workspace(source_root: Path, build_root: Path) -> tuple[Path, list[str]]:
    workspace_root = source_root.parent.resolve()
    source_relative_root = relative_source_root(source_root, workspace_root)
    isolated_workspace_root = build_root / "workspace"
    copied_roots: list[str] = []
    copy_plan: list[tuple[Path, tuple[Path, ...]]] = []
    if source_relative_root == Path("chummer.run-services"):
        merged_copy_map: dict[Path, list[Path]] = {}
        for copy_map in (
            ISOLATED_BUILD_WORKSPACE_COPY_MAP,
            ISOLATED_OVERLAY_PAYLOAD_COPY_MAP,
        ):
            for relative_root, include_paths in copy_map.items():
                merged_copy_map.setdefault(relative_root, [])
                for include_path in include_paths:
                    if include_path not in merged_copy_map[relative_root]:
                        merged_copy_map[relative_root].append(include_path)
        for relative_root, include_paths in merged_copy_map.items():
            if (workspace_root / relative_root).exists():
                copy_plan.append((relative_root, tuple(include_paths)))
    else:
        copy_plan.append((source_relative_root, (Path("."),)))
        if (workspace_root / "chummer-hub-registry" / "black-ledger").exists():
            copy_plan.append(
                (Path("chummer-hub-registry"), (Path("black-ledger"),))
            )

    for relative_root, include_paths in copy_plan:
        destination_root = isolated_workspace_root / relative_root
        for include_path in include_paths:
            source_path = workspace_root / relative_root / include_path
            if not source_path.exists():
                continue
            destination_path = destination_root / include_path
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.is_dir():
                shutil.copytree(
                    source_path,
                    destination_path,
                    ignore=ignored_isolated_build_entries,
                    copy_function=copy_file_with_hardlink_fallback,
                )
            else:
                copy_file_with_hardlink_fallback(source_path, destination_path)
        copied_root = str(destination_root)
        if copied_root not in copied_roots:
            copied_roots.append(copied_root)

    return (isolated_workspace_root / source_relative_root, copied_roots)


def load_live_surface_parity_module(program_binding: dict[str, Any]) -> Any:
    refreshed = refresh_verification_program_binding(program_binding)
    if not _verification_program_binding_status(refreshed):
        raise RuntimeError("live-surface parity program binding failed before import")
    snapshot_path = Path(str(refreshed["snapshotPath"]))
    snapshot_bytes, _ = read_stable_regular_bytes(
        snapshot_path,
        label="live-surface parity program snapshot",
    )
    if sha256_bytes(snapshot_bytes) != refreshed["sha256Expected"]:
        raise RuntimeError("live-surface parity program snapshot changed before compilation")

    # Compile and execute the exact bound bytes. importlib's source loader can
    # write __pycache__ beside the authority snapshot and re-open live source.
    module_name = f"verify_live_surface_parity_for_overlay_{refreshed['sha256Expected']}"
    module = types.ModuleType(module_name)
    synthetic_source_path = str(refreshed["sourcePath"])
    module.__file__ = synthetic_source_path
    module.__package__ = ""
    code = compile(snapshot_bytes, synthetic_source_path, "exec")
    exec(code, module.__dict__)
    after_import = refresh_verification_program_binding(refreshed)
    if not _verification_program_binding_status(after_import):
        raise RuntimeError("live-surface parity program binding drifted during import")
    return module


def build_overlay_verification_env(base_url: str, dependency_base_url: str) -> dict[str, str]:
    normalized_dependency_base_url = dependency_base_url.rstrip("/")
    return {
        "CHUMMER_PRODUCTLIFT_FEEDBACK_URL": f"{normalized_dependency_base_url}/feedback",
        "CHUMMER_PRODUCTLIFT_ROADMAP_URL": f"{normalized_dependency_base_url}/roadmap",
        "GOOGLE_OIDC_CLIENT_ID": "local-overlay-proof-client",
        "GOOGLE_OIDC_CLIENT_SECRET": "local-overlay-proof-secret",
        "GOOGLE_OIDC_REDIRECT_URI": f"{base_url.rstrip('/')}/auth/google/callback",
    }


def build_isolated_overlay_process_env(
    inherited_env: dict[str, str],
    *,
    base_url: str,
    temp_root: Path,
    source_root: Path,
) -> dict[str, str]:
    """Build the verification child environment without retired Play transport state."""
    env = dict(inherited_env)
    for name in RETIRED_PUBLIC_PLAY_PROXY_ENV_NAMES:
        env.pop(name, None)
    env["ASPNETCORE_ENVIRONMENT"] = "Development"
    env["ASPNETCORE_URLS"] = base_url
    env["URLS"] = base_url
    for name in ("HTTP_PORTS", "HTTPS_PORTS", "ASPNETCORE_HTTP_PORTS", "ASPNETCORE_HTTPS_PORTS"):
        env.pop(name, None)
    env["TMPDIR"] = str(temp_root)
    env["CHUMMER_PUBLIC_CANON_ROOT"] = str(source_root)
    return env


class LocalPublicRuntimeDependencyStub:
    def __init__(self) -> None:
        self.port = pick_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> LocalPublicRuntimeDependencyStub:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_HEAD(self) -> None:  # noqa: N802
                self._write_response(head_only=True)

            def do_GET(self) -> None:  # noqa: N802
                self._write_response(head_only=False)

            def _write_response(self, *, head_only: bool) -> None:
                payload, content_type = stub._build_payload(self.path)
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if not head_only:
                    self.wfile.write(payload)

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="local-public-runtime-dependency-stub",
            daemon=True,
        )
        self._thread.start()
        try:
            wait_for_http(self.base_url, "/http_api/posts?tab=feedback", 5.0)
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _build_payload(self, raw_path: str) -> tuple[bytes, str]:
        path = urlparse(raw_path).path or "/"
        if path == "/http_api/posts":
            return (
                json.dumps(
                    {
                        "data": [],
                        "total": 0,
                    }
                ).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        return b"<html><body>Local dependency stub</body></html>\n", "text/html; charset=utf-8"


def verify_local_live_surface_parity(
    base_url: str,
    output_path: Path,
    program_binding: dict[str, Any],
    *,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    try:
        module = load_live_surface_parity_module(program_binding)
        payload = module.verify(
            base_url,
            output_path,
            None,
            deadline_monotonic,
        )
        refreshed_binding = refresh_verification_program_binding(program_binding)
        binding_matches = _verification_program_binding_status(refreshed_binding)
        failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
        return {
            "status": (
                str(payload.get("status") or "").strip()
                if binding_matches
                else "fail"
            ),
            "receiptPath": str(output_path),
            "failureCount": len(failures),
            "failures": failures[:12],
            "verdict": str(payload.get("verdict") or "").strip(),
            "programBinding": refreshed_binding,
            "programBindingMatches": binding_matches,
            "programSnapshotImported": str(refreshed_binding.get("snapshotPath") or ""),
        }
    except Exception as exc:
        return {
            "status": "fail",
            "receiptPath": str(output_path),
            "failureCount": 1,
            "failures": [str(exc)],
            "verdict": "LIVE_SURFACE_PARITY_NOT_READY",
            "programBinding": refresh_verification_program_binding(program_binding),
            "programBindingMatches": False,
            "programSnapshotImported": "",
        }


DEFAULT_VERIFY_LOCAL_LIVE_SURFACE_PARITY_FN = verify_local_live_surface_parity


def ensure_empty_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_optional_tree(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return True


def merge_optional_tree(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    copied_any = False
    for source_path in source.rglob("*"):
        relative_path = source_path.relative_to(source)
        destination_path = destination / relative_path
        if source_path.is_dir():
            destination_path.mkdir(parents=True, exist_ok=True)
            continue
        if destination_path.exists():
            continue
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        copied_any = True
    return copied_any


def backup_destination_path(backup_root: Path) -> Path:
    assert_no_symlink_components(backup_root, label="backup root")
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    transaction_root = backup_root / timestamp
    counter = 1
    while True:
        try:
            transaction_root.mkdir()
            return transaction_root / "app"
        except FileExistsError:
            transaction_root = backup_root / f"{timestamp}-{counter}"
            counter += 1


def retired_overlay_path(active_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    transaction_root = active_root.parent / f".{active_root.name}.retired-{timestamp}"
    counter = 1
    while True:
        try:
            transaction_root.mkdir()
            return transaction_root / "app"
        except FileExistsError:
            transaction_root = active_root.parent / f".{active_root.name}.retired-{timestamp}-{counter}"
            counter += 1


def activation_transaction_journal_path(active_root: Path) -> Path:
    return active_root.parent / f".{active_root.name}.activation-transaction.json"


def assert_no_incomplete_activation_transaction(active_root: Path) -> None:
    journal_path = activation_transaction_journal_path(active_root)
    if journal_path.exists() or journal_path.is_symlink():
        raise OverlayActivationError(
            "incomplete_activation_transaction_requires_recovery",
            rollback_status="recovery_required",
            recovery_path=journal_path,
        )


def backup_overlay_tree(active_root: Path, backup_root: Path) -> Path | None:
    if not active_root.exists():
        return None
    assert_regular_overlay_tree(active_root, label="active root")
    destination = backup_destination_path(backup_root)
    require_same_filesystem(active_root, destination.parent)
    atomic_move_overlay_root(active_root, destination)
    return destination


def _remove_empty_transaction_parent(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.rmdir()
    except OSError:
        pass


def _prepare_activation_candidate(
    staging_root: Path,
    active_root: Path,
    *,
    mode: str,
) -> tuple[Path, Path | None, dict[str, Any]]:
    if mode != "copy":
        raise RuntimeError(
            "public-edge overlay hardlink activation is disabled; activation must use independent staged bytes"
        )
    staging_fingerprint = overlay_tree_fingerprint(staging_root, label="staging root")
    return staging_root, None, staging_fingerprint


def activate_overlay_tree(
    staging_root: Path,
    active_root: Path,
    *,
    mode: str = "copy",
    backup_root: Path | None = None,
) -> dict[str, Any]:
    assert_no_incomplete_activation_transaction(active_root)
    assert_no_symlink_components(active_root, label="active root")
    active_root.parent.mkdir(parents=True, exist_ok=True)
    candidate_root, candidate_container, candidate_fingerprint = _prepare_activation_candidate(
        staging_root,
        active_root,
        mode=mode,
    )
    candidate_identity = directory_identity(candidate_root, label="activation candidate")
    active_existed = active_root.exists()
    prior_active_fingerprint: dict[str, Any] | None = None
    prior_active_identity: dict[str, int] | None = None
    old_tree_destination: Path | None = None
    preserve_old_tree = backup_root is not None
    if active_existed:
        prior_active_fingerprint = overlay_tree_fingerprint(active_root, label="active root")
        prior_active_identity = directory_identity(active_root, label="active root")
        old_tree_destination = (
            backup_destination_path(backup_root)
            if backup_root is not None
            else retired_overlay_path(active_root)
        )

    same_filesystem_paths = [candidate_root, active_root.parent]
    if old_tree_destination is not None:
        same_filesystem_paths.append(old_tree_destination.parent)
    journal_path = activation_transaction_journal_path(active_root)
    journal_payload = {
        "contractName": ACTIVATION_TRANSACTION_CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "status": "prepared",
        "mode": mode,
        "stagingRoot": str(staging_root),
        "candidateRoot": str(candidate_root),
        "activeRoot": str(active_root),
        "activeExisted": active_existed,
        "oldTreeDestination": str(old_tree_destination) if old_tree_destination is not None else "",
        "preserveOldTree": preserve_old_tree,
        "candidateFingerprint": candidate_fingerprint,
        "candidateIdentity": candidate_identity,
        "priorActiveFingerprint": prior_active_fingerprint or {},
        "priorActiveIdentity": prior_active_identity or {},
    }
    try:
        require_same_filesystem(*same_filesystem_paths)
        atomic_write_json(journal_path, journal_payload)
    except Exception as exc:
        if candidate_container is not None:
            shutil.rmtree(candidate_container, ignore_errors=True)
        if old_tree_destination is not None:
            _remove_empty_transaction_parent(old_tree_destination.parent)
        raise OverlayActivationError(
            "activation_preflight_failed",
            rollback_status="active_unchanged",
        ) from exc

    exchanged = False
    installed_without_prior = False
    old_tree_moved = False
    recovery_path: Path | None = None
    transaction_committed = False
    try:
        if active_existed:
            atomic_exchange_overlay_roots(candidate_root, active_root)
            exchanged = True
        else:
            atomic_move_overlay_root(candidate_root, active_root)
            installed_without_prior = True

        installed_fingerprint = overlay_tree_fingerprint(active_root, label="activated root")
        installed_identity = directory_identity(active_root, label="activated root")
        if not (
            fingerprint_envelope_matches(candidate_fingerprint, installed_fingerprint)
            and installed_identity == candidate_identity
        ):
            raise RuntimeError("activated overlay does not match the prepared candidate")
        if active_existed:
            displaced_fingerprint = overlay_tree_fingerprint(
                candidate_root,
                label="displaced active root",
            )
            displaced_identity = directory_identity(
                candidate_root,
                label="displaced active root",
            )
            if prior_active_fingerprint is None or not fingerprint_envelope_matches(
                prior_active_fingerprint,
                displaced_fingerprint,
            ) or displaced_identity != prior_active_identity:
                raise RuntimeError("displaced active overlay does not match the exact prior tree")

        if active_existed and old_tree_destination is not None:
            atomic_move_overlay_root(candidate_root, old_tree_destination)
            exchanged = False
            old_tree_moved = True
            backup_fingerprint = overlay_tree_fingerprint(
                old_tree_destination,
                label="preserved prior active root",
            )
            backup_identity = directory_identity(
                old_tree_destination,
                label="preserved prior active root",
            )
            if prior_active_fingerprint is None or not fingerprint_envelope_matches(
                prior_active_fingerprint,
                backup_fingerprint,
            ) or backup_identity != prior_active_identity:
                raise RuntimeError("preserved prior active overlay does not match the exact prior tree")
        transaction_committed = True
    except Exception as exc:
        rollback_status = "active_unchanged"
        rollback_error: Exception | None = None
        try:
            rollback_candidate_root = candidate_root
            if old_tree_moved and old_tree_destination is not None and active_root.exists():
                atomic_exchange_overlay_roots(old_tree_destination, active_root)
                old_tree_moved = False
                rollback_candidate_root = old_tree_destination
                rollback_status = "exact_prior_active_restored"
            elif exchanged and candidate_root.exists() and active_root.exists():
                atomic_exchange_overlay_roots(candidate_root, active_root)
                exchanged = False
                rollback_status = "exact_prior_active_restored"
            elif installed_without_prior and active_root.exists():
                atomic_move_overlay_root(active_root, candidate_root)
                installed_without_prior = False
                rollback_status = "prior_absence_restored"
            if active_existed and prior_active_fingerprint is not None:
                restored_fingerprint = overlay_tree_fingerprint(
                    active_root,
                    label="rolled back active root",
                )
                if not fingerprint_envelope_matches(
                    prior_active_fingerprint,
                    restored_fingerprint,
                ):
                    raise RuntimeError("rolled back active overlay does not match the exact prior tree")
            elif not active_existed and active_root.exists():
                raise RuntimeError("activation rollback did not restore prior active-root absence")
            if rollback_candidate_root.exists():
                if rollback_candidate_root != staging_root:
                    atomic_move_overlay_root(rollback_candidate_root, staging_root)
        except Exception as rollback_exc:
            rollback_error = rollback_exc
            rollback_status = "rollback_failed_recovery_required"
            recovery_path = journal_path
        if rollback_error is None:
            journal_path.unlink(missing_ok=True)
            fsync_directory(journal_path.parent)
            if old_tree_destination is not None:
                _remove_empty_transaction_parent(old_tree_destination.parent)
        reason = "activation_transaction_failed"
        if rollback_error is not None:
            reason = "activation_transaction_failed_and_rollback_failed"
        raise OverlayActivationError(
            reason,
            rollback_status=rollback_status,
            recovery_path=recovery_path,
        ) from exc
    finally:
        if candidate_container is not None:
            _remove_empty_transaction_parent(candidate_container)

    transaction_cleanup_status = "complete"
    if transaction_committed:
        try:
            journal_path.unlink(missing_ok=True)
            fsync_directory(journal_path.parent)
        except OSError:
            transaction_cleanup_status = "journal_retained_recovery_required"

    retired_cleanup_status = "not_applicable"
    retired_recovery_path = ""
    if active_existed and old_tree_destination is not None and not preserve_old_tree:
        try:
            shutil.rmtree(old_tree_destination)
            _remove_empty_transaction_parent(old_tree_destination.parent)
            retired_cleanup_status = "removed"
        except OSError:
            retired_cleanup_status = "retained_for_manual_cleanup"
            retired_recovery_path = str(old_tree_destination)

    return {
        "atomicCutover": True,
        "backupPath": str(old_tree_destination) if preserve_old_tree and old_tree_destination is not None else "",
        "rollbackStatus": "not_required",
        "retiredCleanupStatus": retired_cleanup_status,
        "retiredRecoveryPath": retired_recovery_path,
        "transactionJournalPath": str(journal_path),
        "transactionCleanupStatus": transaction_cleanup_status,
    }


def staging_overlay_ready(staging_root: Path) -> bool:
    return (staging_root / "Chummer.Run.Api.dll").is_file()


def ensure_required_compose_mountpoints(root: Path) -> list[str]:
    created: list[str] = []
    for relative_path in REQUIRED_COMPOSE_MOUNTPOINTS:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("{}\n", encoding="utf-8")
            created.append(str(relative_path).replace(os.sep, "/"))
    return created


def write_overlay_build_info(
    root: Path,
    *,
    source_root: Path,
    built_source_fingerprint: dict[str, Any],
    status: str,
    activation_status: str,
    verification: dict[str, Any],
) -> Path:
    build_info_path = root / OVERLAY_BUILD_INFO_RELATIVE_PATH
    assert_safe_planned_file(build_info_path, label="overlay build-info receipt")
    build_info_path.parent.mkdir(parents=True, exist_ok=True)
    if not build_info_path.is_file():
        atomic_write_json(build_info_path, {})
    normalize_payload_modes(root)
    payload_mode_receipt = validate_payload_modes(root)
    if payload_mode_receipt.get("status") != "pass":
        raise PayloadModePolicyError(
            "overlay build-info cannot bind a payload with unsafe runtime modes"
        )
    built_staged_payload_fingerprint = staged_payload_fingerprint(root)
    payload = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "status": status,
        "testOnly": bool(verification.get("testOnlyHooksInjected")),
        "authoritativeReceipt": not bool(
            verification.get("testOnlyHooksInjected")
        ),
        "sourceRoot": str(source_root),
        "activationStatus": activation_status,
        "verificationReason": str(verification.get("reason") or "").strip(),
        "verificationStatus": str(verification.get("status") or "").strip(),
        "verificationReceiptPath": str(verification.get("receiptPath") or "").strip(),
        "verificationReceiptStatus": str(verification.get("receiptStatus") or "").strip(),
        "verificationInvocationId": str(
            verification.get("verificationInvocationId") or ""
        ).strip(),
        "receiptInvocationMatchesCurrent": bool(
            verification.get("receiptInvocationMatchesCurrent")
        ),
        "receiptProcessResultConsistent": bool(
            verification.get("receiptProcessResultConsistent")
        ),
        "verificationPrograms": verification.get("verificationPrograms") or {},
        "verificationProgramsMatch": bool(
            verification.get("verificationProgramsMatch")
        ),
        "receiptProgramBindingsMatch": bool(
            verification.get("receiptProgramBindingsMatch")
        ),
        "productionExecutionEvidence": verification.get(
            "productionExecutionEvidence"
        )
        or {},
        "productionExecutionEvidenceMatches": bool(
            verification.get("productionExecutionEvidenceMatches")
        ),
        "verifierProgramSnapshotExecuted": str(
            verification.get("verifierProgramSnapshotExecuted") or ""
        ).strip(),
        "verifierProgramExecutionMode": str(
            verification.get("verifierProgramExecutionMode") or ""
        ).strip(),
        "verifierProgramExecutionSha256Expected": str(
            verification.get("verifierProgramExecutionSha256Expected") or ""
        ).strip(),
        "verifierProgramExecutionSha256Actual": str(
            verification.get("verifierProgramExecutionSha256Actual") or ""
        ).strip(),
        "verifierProgramExecutionSha256Matches": bool(
            verification.get("verifierProgramExecutionSha256Matches")
        ),
        "parityProgramSnapshotImported": str(
            verification.get("parityProgramSnapshotImported") or ""
        ).strip(),
        "verificationBaseUrl": str(verification.get("baseUrl") or "").strip(),
        "releaseChannelReceiptPath": str(verification.get("releaseChannelReceiptPath") or "").strip(),
        "releaseChannelReceiptSnapshotPath": str(
            verification.get("releaseChannelReceiptSnapshotPath") or ""
        ).strip(),
        "releaseChannelReceiptSha256Expected": str(
            verification.get("releaseChannelReceiptSha256Expected") or ""
        ).strip(),
        "releaseChannelReceiptSha256Actual": str(
            verification.get("releaseChannelReceiptSha256Actual") or ""
        ).strip(),
        "releaseChannelReceiptSha256Matches": bool(
            verification.get("releaseChannelReceiptSha256Matches")
        ),
        "releaseChannelVersion": str(verification.get("releaseChannelVersion") or "").strip(),
        "releaseChannelPublishedAt": str(
            verification.get("releaseChannelPublishedAt") or ""
        ).strip(),
        "releaseManifestConservativeReviewFloorApplied": bool(
            verification.get("releaseManifestConservativeReviewFloorApplied")
        ),
        "releaseManifestSupportabilityExact": verification.get(
            "releaseManifestSupportabilityExact"
        ),
        "releaseManifestSupportabilityCompatible": verification.get(
            "releaseManifestSupportabilityCompatible"
        ),
        "releaseManifestRolloutExact": verification.get(
            "releaseManifestRolloutExact"
        ),
        "releaseManifestRolloutCompatible": verification.get(
            "releaseManifestRolloutCompatible"
        ),
        "landingMarkerStatus": str(verification.get("landingMarkerStatus") or "").strip(),
        "landingHasPlayDisabledTarget": bool((verification.get("landingMarkerChecks") or {}).get("playDisabledTarget")),
        "landingHasPlaySignInRoute": bool((verification.get("landingMarkerChecks") or {}).get("playSignInRoute")),
        "landingHasTurnAnchor": bool((verification.get("landingMarkerChecks") or {}).get("turnAnchor")),
        "landingHasTurnAnchorRedirect": bool((verification.get("landingMarkerChecks") or {}).get("turnAnchorRedirect")),
        "landingBrowserRedirectStatus": str((verification.get("landingBrowserRedirect") or {}).get("status") or "").strip(),
        "landingBrowserRedirectEntryUrl": str((verification.get("landingBrowserRedirect") or {}).get("entryUrl") or "").strip(),
        "landingBrowserRedirectFinalUrl": str((verification.get("landingBrowserRedirect") or {}).get("finalUrl") or "").strip(),
        "landingBrowserRedirectExpectedPath": str((verification.get("landingBrowserRedirect") or {}).get("expectedPath") or "").strip(),
        "landingBrowserRedirectExpectedHash": str((verification.get("landingBrowserRedirect") or {}).get("expectedHash") or "").strip(),
        "landingBrowserRedirectPathMatches": bool((verification.get("landingBrowserRedirect") or {}).get("pathMatches")),
        "landingBrowserRedirectHashMatches": bool((verification.get("landingBrowserRedirect") or {}).get("hashMatches")),
        "landingMissingMarkerCount": len(verification.get("landingMissingMarkers") or []),
        "localLiveSurfaceParityStatus": str((verification.get("localLiveSurfaceParity") or {}).get("status") or "").strip(),
        "localLiveSurfaceParityFailureCount": int((verification.get("localLiveSurfaceParity") or {}).get("failureCount") or 0),
        "sourceFingerprint": built_source_fingerprint,
        "stagedPayloadFingerprint": built_staged_payload_fingerprint,
        "payloadModeReceipt": payload_mode_receipt,
        "fullDeploymentDigest": full_deployment_digest(
            built_source_fingerprint,
            built_staged_payload_fingerprint,
        ),
    }
    atomic_write_json(build_info_path, payload)
    normalize_payload_modes(root)
    mode_binding = validate_payload_modes_against_receipt(
        root,
        payload_mode_receipt,
    )
    if mode_binding.get("status") != "pass":
        raise PayloadModePolicyError(
            "overlay payload modes changed while build-info was finalized"
        )
    return build_info_path


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
    deadline = time.monotonic() + timeout_seconds
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    last_error = "not_started"
    while time.monotonic() < deadline:
        try:
            remaining_seconds = max(0.1, deadline - time.monotonic())
            request = Request(url, headers={"User-Agent": "ChummerPublicEdgeOverlayPublish/1.0"})
            with urlopen(request, timeout=min(timeout_seconds, remaining_seconds)) as response:
                body = response.read().decode("utf-8", errors="replace")
                if response.status == 200:
                    return body
                last_error = f"http_{response.status}"
        except HTTPError as exc:
            last_error = f"http_{exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"{url} did not return 200 before timeout ({last_error})")


def probe_overlay_readiness(
    base_url: str,
    timeout_seconds: float,
    *,
    open_url: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    """Require the combined readiness body and the default-off Play projection truth."""
    url = f"{base_url.rstrip('/')}/api/ready"
    request = Request(url, headers={"User-Agent": "ChummerPublicEdgeOverlayPublish/1.0"})
    http_status = 0
    raw_body = b""
    transport_error = ""
    try:
        with open_url(request, timeout=timeout_seconds) as response:
            http_status = int(response.status)
            raw_body = response.read()
    except HTTPError as exc:
        http_status = int(exc.code)
        raw_body = exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        transport_error = str(exc)

    payload: dict[str, Any] = {}
    json_error = ""
    if raw_body:
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            if isinstance(parsed, dict):
                payload = parsed
            else:
                json_error = "readiness body must be a JSON object"
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            json_error = str(exc)
    elif not transport_error:
        json_error = "readiness body is empty"

    hub_value = payload.get("hub")
    hub = hub_value if isinstance(hub_value, dict) else {}
    projection_value = payload.get("playProjection")
    projection = projection_value if isinstance(projection_value, dict) else {}
    top_ready = payload.get("ready")
    top_status = str(payload.get("status") or "").strip().lower()
    hub_ready = hub.get("ready")
    hub_status = str(hub.get("status") or "").strip().lower()
    projection_ready = projection.get("ready")
    checks = {
        "http200": http_status == 200,
        "bodyReady": top_ready is True,
        "bodyStatus": top_status == "ready",
        "hubObject": isinstance(hub_value, dict),
        "hubReady": hub_ready is True,
        "hubStatus": hub_status == "pass",
        "projectionObject": isinstance(projection_value, dict),
        "projectionDisabled": projection.get("enabled") is False,
        "projectionReady": projection_ready is True,
        "projectionStatus": str(projection.get("status") or "").strip().lower() == "disabled",
        "combinedConsistent": top_ready is True
        and top_status == "ready"
        and hub_ready is True
        and hub_status == "pass"
        and projection_ready is True,
        "jsonObject": bool(payload) and not json_error,
        "transport": not transport_error,
    }
    passed = all(checks.values())
    return {
        "status": "pass" if passed else "fail",
        "url": url,
        "httpStatus": http_status,
        "checks": checks,
        "bodyReady": payload.get("ready"),
        "bodyStatus": str(payload.get("status") or ""),
        "hub": {
            "ready": hub.get("ready"),
            "status": str(hub.get("status") or ""),
        },
        "playProjection": projection,
        "transportError": transport_error,
        "jsonError": json_error,
    }


def read_text_tail(path: Path, *, max_chars: int = 4000) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]


def receipt_failure_allowed_for_overlay_activation(value: object) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return False
    if normalized in ALLOWED_OVERLAY_ACTIVATION_RECEIPT_FAILURES:
        return True
    return any(normalized.startswith(prefix) for prefix in ALLOWED_OVERLAY_ACTIVATION_RECEIPT_FAILURE_PREFIXES)


def receipt_supports_overlay_activation(receipt_payload: dict[str, Any]) -> bool:
    if not receipt_payload:
        return False

    failures = receipt_payload.get("failures")
    if not isinstance(failures, list) or not failures:
        return False
    if any(not receipt_failure_allowed_for_overlay_activation(item) for item in failures):
        return False

    for field in OVERLAY_ACTIVATION_RECEIPT_REQUIRED_TRUE_FIELDS:
        if receipt_payload.get(field) is not True:
            return False

    for field in OVERLAY_ACTIVATION_RECEIPT_REQUIRED_FALSE_FIELDS:
        if receipt_payload.get(field) is not False:
            return False

    for field, expected in OVERLAY_ACTIVATION_RECEIPT_REQUIRED_EXACT_FIELDS.items():
        if receipt_payload.get(field) != expected:
            return False

    return True


def pass_receipt_satisfies_overlay_contract(receipt_payload: dict[str, Any]) -> bool:
    if not receipt_payload:
        return False

    for field in OVERLAY_PASS_RECEIPT_REQUIRED_TRUE_FIELDS:
        if receipt_payload.get(field) is not True:
            return False

    for field in OVERLAY_ACTIVATION_RECEIPT_REQUIRED_FALSE_FIELDS:
        if receipt_payload.get(field) is not False:
            return False

    for field, expected in OVERLAY_ACTIVATION_RECEIPT_REQUIRED_EXACT_FIELDS.items():
        if receipt_payload.get(field) != expected:
            return False

    return True


def verification_supports_overlay_activation(verification: dict[str, Any]) -> bool:
    if str(verification.get("status") or "").strip() == "pass":
        return True
    return bool(verification.get("receiptAllowsOverlayActivation"))


def verification_program_envelopes_match(
    expected: dict[str, Any],
    observed: dict[str, Any],
) -> bool:
    if (
        expected.get("contractName") != VERIFICATION_PROGRAM_BINDING_CONTRACT_NAME
        or observed.get("contractName") != VERIFICATION_PROGRAM_BINDING_CONTRACT_NAME
        or expected.get("status") != "pass"
        or observed.get("status") != "pass"
    ):
        return False
    expected_programs = expected.get("programs")
    observed_programs = observed.get("programs")
    if not isinstance(expected_programs, dict) or not isinstance(observed_programs, dict):
        return False
    if set(expected_programs) != set(VERIFICATION_PROGRAM_SOURCES) or set(observed_programs) != set(
        VERIFICATION_PROGRAM_SOURCES
    ):
        return False
    for name in VERIFICATION_PROGRAM_SOURCES:
        expected_binding = expected_programs.get(name)
        observed_binding = observed_programs.get(name)
        if not isinstance(expected_binding, dict) or not isinstance(observed_binding, dict):
            return False
        if not _verification_program_binding_status(observed_binding):
            return False
        for field in (
            "sourcePath",
            "snapshotPath",
            "sha256Expected",
            "sourceSha256Actual",
            "snapshotSha256Actual",
            "snapshotDevice",
            "snapshotInode",
        ):
            if observed_binding.get(field) != expected_binding.get(field):
                return False
    return True


def production_verification_evidence(
    verification: dict[str, Any],
    expected_programs: dict[str, Any],
    verification_receipt_path: Path,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    failures: list[str] = []
    expected_bindings = expected_programs.get("programs")
    expected_bindings = expected_bindings if isinstance(expected_bindings, dict) else {}
    verifier_binding = expected_bindings.get("downloadsVersionMarker")
    verifier_binding = verifier_binding if isinstance(verifier_binding, dict) else {}
    parity_binding = expected_bindings.get("liveSurfaceParity")
    parity_binding = parity_binding if isinstance(parity_binding, dict) else {}

    checks["sealedExecutionMode"] = (
        verification.get("verifierProgramExecutionMode")
        == "sealed_memfd_from_content_addressed_snapshot"
    )
    checks["sealedExecutionDigest"] = bool(
        verification.get("verifierProgramExecutionSha256Matches") is True
        and verification.get("verifierProgramExecutionSha256Expected")
        == verifier_binding.get("sha256Expected")
        and verification.get("verifierProgramExecutionSha256Actual")
        == verifier_binding.get("sha256Expected")
    )
    checks["verifierSnapshotPath"] = (
        str(verification.get("verifierProgramSnapshotExecuted") or "")
        == str(verifier_binding.get("snapshotPath") or "")
    )
    checks["paritySnapshotPath"] = (
        str(verification.get("parityProgramSnapshotImported") or "")
        == str(parity_binding.get("snapshotPath") or "")
    )
    local_parity = verification.get("localLiveSurfaceParity")
    local_parity = local_parity if isinstance(local_parity, dict) else {}
    observed_parity_binding = local_parity.get("programBinding")
    observed_parity_binding = (
        observed_parity_binding if isinstance(observed_parity_binding, dict) else {}
    )
    checks["parityBinding"] = bool(
        local_parity.get("programBindingMatches") is True
        and _verification_program_binding_status(observed_parity_binding)
        and all(
            observed_parity_binding.get(field) == parity_binding.get(field)
            for field in (
                "sourcePath",
                "snapshotPath",
                "sha256Expected",
                "sourceSha256Actual",
                "snapshotSha256Actual",
                "snapshotDevice",
                "snapshotInode",
            )
        )
    )
    checks["outerProgramEnvelope"] = bool(
        verification.get("verificationProgramsMatch") is True
        and verification.get("receiptProgramBindingsMatch") is True
        and verification_program_envelopes_match(
            expected_programs,
            verification.get("verificationPrograms") or {},
        )
    )

    try:
        receipt_path = normalized_absolute_path(
            Path(str(verification.get("receiptPath") or ""))
        )
        expected_receipt_path = normalized_absolute_path(verification_receipt_path)
        checks["receiptPath"] = receipt_path == expected_receipt_path
        receipt_bytes, receipt_stat = read_stable_regular_bytes(
            receipt_path,
            label="production verification child receipt",
        )
        receipt_sha256 = sha256_bytes(receipt_bytes)
        checks["receiptIndependentFile"] = receipt_stat.st_nlink == 1
        checks["receiptDigest"] = bool(
            verification.get("receiptSha256") == receipt_sha256
            and len(receipt_sha256) == 64
        )
        child_payload = json.loads(receipt_bytes.decode("utf-8"))
        if not isinstance(child_payload, dict):
            raise RuntimeError("production verification child receipt is not a JSON object")
        before_binding_sha256 = str(
            child_payload.get(
                "publisher_child_receipt_sha256_before_program_binding"
            )
            or ""
        ).strip().lower()
        checks["childProducerDigest"] = bool(
            len(before_binding_sha256) == 64
            and all(character in "0123456789abcdef" for character in before_binding_sha256)
            and verification.get("childReceiptSha256BeforeProgramBinding")
            == before_binding_sha256
        )
        checks["childProgramEnvelope"] = bool(
            child_payload.get("publisher_verification_programs_match") is True
            and verification_program_envelopes_match(
                expected_programs,
                child_payload.get("publisher_verification_programs") or {},
            )
        )
    except Exception as exc:
        checks.setdefault("receiptPath", False)
        checks.setdefault("receiptIndependentFile", False)
        checks.setdefault("receiptDigest", False)
        checks.setdefault("childProducerDigest", False)
        checks.setdefault("childProgramEnvelope", False)
        failures.append(str(exc))

    failures.extend(
        f"production verification evidence check failed: {name}"
        for name, passed in checks.items()
        if not passed
    )
    return {
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "failures": failures,
    }


def bind_verification_programs_into_child_receipt(
    receipt_path: Path,
    program_envelope: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    raw_receipt, receipt_stat = read_stable_regular_bytes(
        receipt_path,
        label="downloads-version child verification receipt",
    )
    if receipt_stat.st_nlink != 1:
        raise RuntimeError("downloads-version child verification receipt has unsafe hardlinks")
    try:
        parsed = json.loads(raw_receipt.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"downloads-version child verification receipt is invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("downloads-version child verification receipt must be a JSON object")
    producer_sha256 = sha256_bytes(raw_receipt)
    parsed["publisher_verification_programs"] = program_envelope
    parsed["publisher_verification_programs_match"] = program_envelope.get("status") == "pass"
    parsed["publisher_child_receipt_sha256_before_program_binding"] = producer_sha256
    atomic_write_json(receipt_path, parsed)
    rebound_bytes, rebound_stat = read_stable_regular_bytes(
        receipt_path,
        label="program-bound downloads-version child verification receipt",
    )
    if rebound_stat.st_nlink != 1:
        raise RuntimeError("program-bound child verification receipt has unsafe hardlinks")
    rebound_payload = json.loads(rebound_bytes.decode("utf-8"))
    if not isinstance(rebound_payload, dict):
        raise RuntimeError("program-bound child verification receipt must remain a JSON object")
    if not verification_program_envelopes_match(
        program_envelope,
        rebound_payload.get("publisher_verification_programs") or {},
    ):
        raise RuntimeError("child verification receipt did not retain exact program bindings")
    return rebound_payload, producer_sha256


def probe_landing_anchor_browser_redirect(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    entry_url = f"{base_url.rstrip('/')}/#turn-runsite-card"
    expected_path = "/mobile/player"
    expected_hash = "#turn-runsite-card"
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError as exc:
        return {
            "status": "fail",
            "reason": "playwright_unavailable",
            "entryUrl": entry_url,
            "finalUrl": "",
            "expectedPath": expected_path,
            "expectedHash": expected_hash,
            "pathMatches": False,
            "hashMatches": False,
            "error": str(exc),
            "title": "",
            "heading": "",
        }

    timeout_seconds = validated_timeout_seconds(
        timeout_seconds,
        label="landing browser redirect timeout",
        maximum=MAX_VERIFICATION_DEADLINE_SECONDS,
    )
    deadline_at_monotonic = time.monotonic() + timeout_seconds

    def remaining_timeout_ms(*, maximum_seconds: float | None = None) -> int:
        remaining = deadline_at_monotonic - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("landing browser redirect probe deadline exceeded")
        if maximum_seconds is not None:
            remaining = min(remaining, maximum_seconds)
        return max(1, int(remaining * 1000))

    try:
        with sync_playwright() as playwright:
            launch_failures: list[str] = []
            for browser_name in ("chromium", "firefox"):
                browser_type = getattr(playwright, browser_name, None)
                if browser_type is None:
                    launch_failures.append(f"{browser_name}: browser_type_unavailable")
                    continue
                browser = None
                page = None
                try:
                    browser = browser_type.launch(
                        headless=True,
                        timeout=remaining_timeout_ms(),
                    )
                    page = browser.new_page(viewport={"width": 390, "height": 844})
                    if hasattr(page, "set_default_timeout"):
                        page.set_default_timeout(remaining_timeout_ms())
                    page.goto(
                        entry_url,
                        wait_until="domcontentloaded",
                        timeout=remaining_timeout_ms(),
                    )
                    page.wait_for_function(
                        """
                        () => {
                            const currentUrl = new URL(window.location.href);
                            return currentUrl.pathname === '/mobile/player'
                                && currentUrl.hash === '#turn-runsite-card';
                        }
                        """,
                        timeout=remaining_timeout_ms(),
                    )
                    final_url = page.url
                    parsed = urlparse(final_url)
                    heading = ""
                    try:
                        heading = page.locator("h1").first.inner_text(
                            timeout=remaining_timeout_ms(maximum_seconds=2.0)
                        )
                    except PlaywrightError:
                        heading = ""
                    return {
                        "status": "pass",
                        "reason": "",
                        "entryUrl": entry_url,
                        "finalUrl": final_url,
                        "expectedPath": expected_path,
                        "expectedHash": expected_hash,
                        "pathMatches": parsed.path == expected_path,
                        "hashMatches": parsed.fragment == expected_hash.lstrip("#"),
                        "error": "",
                        "title": page.title(),
                        "heading": heading,
                        "browserName": browser_name,
                    }
                except Exception as exc:
                    launch_failures.append(f"{browser_name}: {exc}")
                finally:
                    if page is not None:
                        page.close()
                    if browser is not None:
                        browser.close()
    except Exception as exc:
        return {
            "status": "fail",
            "reason": "browser_redirect_failed",
            "entryUrl": entry_url,
            "finalUrl": "",
            "expectedPath": expected_path,
            "expectedHash": expected_hash,
            "pathMatches": False,
            "hashMatches": False,
            "error": str(exc),
            "title": "",
            "heading": "",
            "browserName": "",
        }
    return {
        "status": "fail",
        "reason": "browser_redirect_failed",
        "entryUrl": entry_url,
        "finalUrl": "",
        "expectedPath": expected_path,
        "expectedHash": expected_hash,
        "pathMatches": False,
        "hashMatches": False,
        "error": "\n\n".join(launch_failures),
        "title": "",
        "heading": "",
        "browserName": "",
    }


def finite_nonnegative_seconds(value: object) -> float:
    try:
        rendered = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(rendered):
        return 0.0
    return max(0.0, rendered)


def callable_accepts_keyword(callback: Callable[..., Any], keyword: str) -> bool:
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        or (
            parameter.name == keyword
            and parameter.kind
            in {
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }
        )
        for parameter in parameters
    )


def verification_deadline_receipt(
    *,
    exc: VerificationDeadlineExceeded,
    budget: VerificationBudget,
    verification_receipt_path: Path,
    release_channel_receipt: Path,
    release_channel_receipt_sha256: str,
    verification_programs: dict[str, Any] | None,
) -> dict[str, Any]:
    verification_receipt_path = normalized_absolute_path(verification_receipt_path)
    elapsed_seconds = finite_nonnegative_seconds(exc.elapsed_seconds)
    remaining_seconds = finite_nonnegative_seconds(
        budget.deadline_at_monotonic - time.monotonic()
    )
    deadline = {
        "status": "fail",
        "timedOut": True,
        "deadlineSeconds": finite_nonnegative_seconds(budget.deadline_seconds),
        "elapsedSeconds": elapsed_seconds,
        "remainingSeconds": remaining_seconds,
        "phase": str(exc.phase or "verification"),
    }
    child_payload = {
        "contractName": "chummer.public_edge_portal_overlay_verification_timeout.v1",
        "generatedAtUtc": now_iso(),
        "status": "fail",
        "reason": "verification_deadline_exceeded",
        "goalCompletionClaimAllowed": False,
        "verificationDeadline": deadline,
        "releaseChannelReceipt": str(normalized_absolute_path(release_channel_receipt)),
        "releaseChannelReceiptSha256Expected": str(
            release_channel_receipt_sha256 or ""
        ).strip().lower(),
    }
    receipt_persisted = False
    receipt_write_error = ""
    receipt_sha256 = ""
    try:
        atomic_write_json(verification_receipt_path, child_payload)
        receipt_sha256 = sha256_bytes(verification_receipt_path.read_bytes())
        receipt_persisted = True
    except Exception as write_exc:
        receipt_write_error = str(write_exc)

    program_envelope = dict(verification_programs or {})
    program_envelope.setdefault(
        "contractName",
        VERIFICATION_PROGRAM_BINDING_CONTRACT_NAME,
    )
    program_envelope["status"] = "fail"
    if not isinstance(program_envelope.get("programs"), dict):
        program_envelope["programs"] = {}
    return {
        "status": "fail",
        "reason": "verification_deadline_exceeded",
        "timedOut": True,
        "baseUrl": "",
        "receiptPath": str(verification_receipt_path),
        "receiptPersisted": receipt_persisted,
        "receiptWriteError": receipt_write_error,
        "receiptSha256": receipt_sha256,
        "exitCode": PUBLISH_TIMEOUT_EXIT_CODE,
        "receiptStatus": "fail" if receipt_persisted else "",
        "probeError": str(exc),
        "verificationDeadline": deadline,
        "releaseChannelReceiptPath": str(
            normalized_absolute_path(release_channel_receipt)
        ),
        "releaseChannelReceiptSnapshotPath": str(
            normalized_absolute_path(release_channel_receipt)
        ),
        "releaseChannelReceiptSha256Expected": str(
            release_channel_receipt_sha256 or ""
        ).strip().lower(),
        "releaseChannelReceiptSha256Actual": "",
        "releaseChannelReceiptSha256Matches": False,
        "receiptAllowsOverlayActivation": False,
        "receiptBindingMatchesSelectedInput": False,
        "receiptInvocationMatchesCurrent": False,
        "receiptProcessResultConsistent": False,
        "verificationPrograms": program_envelope,
        "verificationProgramsMatch": False,
        "receiptProgramBindingsMatch": False,
        "localLiveSurfaceParity": {
            "status": "skipped",
            "reason": "verification_deadline_exceeded",
            "failureCount": 1,
            "failures": [str(exc)],
        },
        "landingBrowserRedirect": {
            "status": "skipped",
            "reason": "verification_deadline_exceeded",
        },
    }


def verify_published_overlay(
    staging_root: Path,
    *,
    source_root: Path,
    verify_timeout_seconds: float,
    verification_receipt_path: Path,
    release_channel_receipt: Path,
    release_channel_receipt_sha256: str,
    verification_programs: dict[str, Any] | None = None,
    verification_deadline_seconds: float = DEFAULT_VERIFICATION_DEADLINE_SECONDS,
) -> dict[str, Any]:
    budget = VerificationBudget(verification_deadline_seconds)
    try:
        with enforce_verification_wall_clock_deadline(budget):
            result = _verify_published_overlay_with_budget(
                staging_root,
                source_root=source_root,
                verify_timeout_seconds=verify_timeout_seconds,
                verification_receipt_path=verification_receipt_path,
                release_channel_receipt=release_channel_receipt,
                release_channel_receipt_sha256=release_channel_receipt_sha256,
                verification_programs=verification_programs,
                verification_budget=budget,
            )
    except VerificationDeadlineExceeded as exc:
        return verification_deadline_receipt(
            exc=exc,
            budget=budget,
            verification_receipt_path=verification_receipt_path,
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            verification_programs=verification_programs,
        )

    result["verificationDeadline"] = {
        "status": "pass",
        "timedOut": False,
        "deadlineSeconds": finite_nonnegative_seconds(budget.deadline_seconds),
        "elapsedSeconds": finite_nonnegative_seconds(budget.elapsed_seconds()),
        "remainingSeconds": finite_nonnegative_seconds(
            budget.deadline_at_monotonic - time.monotonic()
        ),
        "phase": str(budget.phase or "verification_complete"),
    }
    result["timedOut"] = False
    return result


def _verify_published_overlay_with_budget(
    staging_root: Path,
    *,
    source_root: Path,
    verify_timeout_seconds: float,
    verification_receipt_path: Path,
    release_channel_receipt: Path,
    release_channel_receipt_sha256: str,
    verification_programs: dict[str, Any] | None = None,
    verification_budget: VerificationBudget,
) -> dict[str, Any]:
    verification_budget.remaining_seconds("verification_program_binding")
    verification_receipt_path = normalized_absolute_path(verification_receipt_path)
    if verification_programs is None:
        verification_programs = snapshot_verification_programs(
            verification_receipt_path.parent / VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME
        )
    verification_programs_before = verification_program_binding_envelope(
        verification_programs.get("programs")
        if isinstance(verification_programs.get("programs"), dict)
        else {}
    )
    if verification_programs_before["status"] != "pass":
        return {
            "status": "fail",
            "reason": "verification_program_binding_failed",
            "baseUrl": "",
            "receiptPath": str(verification_receipt_path),
            "exitCode": None,
            "receiptStatus": "",
            "probeError": "verification program binding failed before probe",
            "verificationPrograms": verification_programs_before,
            "verificationProgramsMatch": False,
        }
    assert_no_symlink_components(
        verification_receipt_path.parent,
        label="overlay verification receipt parent",
    )
    verification_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    local_live_surface_parity_path = verification_receipt_path.parent / "LIVE_SURFACE_PARITY.local-overlay.generated.json"
    startup_log_path = verification_receipt_path.parent / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.startup.log"
    for stale_path in (
        verification_receipt_path,
        local_live_surface_parity_path,
        startup_log_path,
    ):
        assert_no_symlink_components(stale_path, label="overlay verification derived output")
        stale_path.unlink(missing_ok=True)
    fsync_directory(verification_receipt_path.parent)
    verification_invocation_id = secrets.token_hex(16)
    app_dll = staging_root / "Chummer.Run.Api.dll"
    if not app_dll.is_file():
        return {
            "status": "fail",
            "reason": "published_app_missing_dll",
            "baseUrl": "",
            "receiptPath": str(verification_receipt_path),
            "exitCode": None,
            "receiptStatus": "",
            "probeError": "",
            "releaseChannelReceiptPath": str(release_channel_receipt),
            "releaseChannelReceiptSnapshotPath": str(release_channel_receipt),
            "releaseChannelReceiptSha256Expected": release_channel_receipt_sha256,
            "releaseChannelReceiptSha256Actual": "",
            "releaseChannelReceiptSha256Matches": False,
            "verificationInvocationId": verification_invocation_id,
            "receiptInvocationMatchesCurrent": False,
            "receiptProcessResultConsistent": False,
            "verificationPrograms": verification_programs_before,
            "verificationProgramsMatch": True,
        }

    port = pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    temp_root = Path(tempfile.mkdtemp(prefix="chummer-public-edge-overlay-verify-"))
    env = build_isolated_overlay_process_env(
        dict(os.environ),
        base_url=base_url,
        temp_root=temp_root,
        source_root=source_root,
    )
    try:
        with LocalPublicRuntimeDependencyStub() as dependency_stub:
            env.update(build_overlay_verification_env(base_url, dependency_stub.base_url))
            startup_log_path.parent.mkdir(parents=True, exist_ok=True)
            startup_log_flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            startup_log_descriptor = os.open(startup_log_path, startup_log_flags, 0o600)
            with os.fdopen(startup_log_descriptor, "w", encoding="utf-8") as startup_log_handle:
                process = subprocess.Popen(
                    ["dotnet", "Chummer.Run.Api.dll"],
                    cwd=str(staging_root),
                    env=env,
                    stdout=startup_log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                try:
                    wait_for_http(
                        base_url,
                        "/status",
                        verification_budget.remaining_seconds(
                            "status_startup_probe",
                            verify_timeout_seconds,
                        ),
                    )
                    overlay_readiness = probe_overlay_readiness(
                        base_url,
                        verification_budget.remaining_seconds(
                            "combined_readiness_probe",
                            verify_timeout_seconds,
                        ),
                    )
                    landing_body = wait_for_http(
                        base_url,
                        "/",
                        verification_budget.remaining_seconds(
                            "landing_http_probe",
                            verify_timeout_seconds,
                        ),
                    )
                    landing_marker_checks = {
                        name: marker in landing_body
                        for name, marker in REQUIRED_LANDING_MARKERS.items()
                    }
                    landing_missing_markers = [
                        marker
                        for name, marker in REQUIRED_LANDING_MARKERS.items()
                        if not landing_marker_checks.get(name, False)
                    ]
                    landing_browser_redirect = probe_landing_anchor_browser_redirect(
                        base_url,
                        verification_budget.remaining_seconds(
                            "landing_browser_redirect",
                            verify_timeout_seconds,
                        ),
                    )
                    verification_budget.remaining_seconds(
                        "downloads_version_verifier_setup"
                    )
                    verification_receipt_path.parent.mkdir(parents=True, exist_ok=True)
                    with sealed_verification_program_execution(
                        verification_programs_before["programs"]["downloadsVersionMarker"]
                    ) as verifier_execution:
                        child_timeout_seconds = verification_budget.remaining_seconds(
                            "downloads_version_verifier",
                            verify_timeout_seconds,
                        )
                        child_run_kwargs: dict[str, Any] = {
                            "cwd": str(RUN_SERVICES_ROOT),
                            "check": False,
                            "text": True,
                            "stdout": subprocess.PIPE,
                            "stderr": subprocess.PIPE,
                            "pass_fds": (int(verifier_execution["descriptor"]),),
                        }
                        if callable_accepts_keyword(subprocess.run, "timeout"):
                            child_run_kwargs["timeout"] = child_timeout_seconds
                        try:
                            completed = subprocess.run(
                                [
                                    sys.executable,
                                    "-c",
                                    SEALED_PYTHON_PROGRAM_WRAPPER,
                                    str(verifier_execution["descriptor"]),
                                    str(verifier_execution["sha256Expected"]),
                                    str(
                                        verification_programs_before["programs"][
                                            "downloadsVersionMarker"
                                        ]["sourcePath"]
                                    ),
                                    "--source-root",
                                    str(source_root),
                                    "--base-url",
                                    base_url,
                                    "--output",
                                    str(verification_receipt_path),
                                    "--timeout-seconds",
                                    str(child_timeout_seconds),
                                    "--release-channel-receipt",
                                    str(release_channel_receipt),
                                    "--release-channel-receipt-sha256",
                                    release_channel_receipt_sha256,
                                    "--invocation-id",
                                    verification_invocation_id,
                                ],
                                **child_run_kwargs,
                            )
                        except subprocess.TimeoutExpired as exc:
                            verification_budget.remaining_seconds(
                                "downloads_version_verifier_timeout"
                            )
                            raise RuntimeError(
                                "downloads-version verifier exceeded its bounded timeout "
                                f"of {child_timeout_seconds:g} seconds"
                            ) from exc
                    verification_budget.remaining_seconds(
                        "live_surface_parity_setup"
                    )
                    parity_verifier = verify_local_live_surface_parity
                    if parity_verifier is DEFAULT_VERIFY_LOCAL_LIVE_SURFACE_PARITY_FN:
                        local_live_surface_parity = parity_verifier(
                            base_url,
                            local_live_surface_parity_path,
                            verification_programs_before["programs"]["liveSurfaceParity"],
                            deadline_monotonic=verification_budget.deadline_at_monotonic,
                        )
                    else:
                        local_live_surface_parity = parity_verifier(
                            base_url,
                            local_live_surface_parity_path,
                            verification_programs_before["programs"]["liveSurfaceParity"],
                        )
                    verification_budget.remaining_seconds(
                        "live_surface_parity_complete"
                    )
                    verification_programs_after = verification_program_binding_envelope(
                        verification_programs_before["programs"]
                    )
                    verification_programs_match = verification_program_envelopes_match(
                        verification_programs_before,
                        verification_programs_after,
                    )
                    parity_program_binding_matches = bool(
                        local_live_surface_parity.get("programBindingMatches") is True
                        and str(
                            local_live_surface_parity.get("programSnapshotImported") or ""
                        ).strip()
                        == str(
                            verification_programs_before["programs"]["liveSurfaceParity"][
                                "snapshotPath"
                            ]
                        )
                    )
                    receipt_status = ""
                    receipt_payload: dict[str, Any] = {}
                    receipt_allows_overlay_activation = False
                    pass_receipt_contract_satisfied = False
                    child_receipt_sha256_before_program_binding = ""
                    if verification_receipt_path.is_file():
                        receipt_payload, child_receipt_sha256_before_program_binding = (
                            bind_verification_programs_into_child_receipt(
                                verification_receipt_path,
                                verification_programs_after,
                            )
                        )
                        receipt_status = str(receipt_payload.get("status") or "").strip()
                        receipt_allows_overlay_activation = receipt_supports_overlay_activation(receipt_payload)
                        pass_receipt_contract_satisfied = pass_receipt_satisfies_overlay_contract(
                            receipt_payload
                        )
                    receipt_binding_matches_selected_input = bool(
                        receipt_payload.get("release_channel_receipt_sha256_matches") is True
                        and str(
                            receipt_payload.get("release_channel_receipt_sha256_expected") or ""
                        ).strip().lower()
                        == release_channel_receipt_sha256
                        and str(
                            receipt_payload.get("release_channel_receipt_sha256_actual") or ""
                        ).strip().lower()
                        == release_channel_receipt_sha256
                        and normalized_absolute_path(
                            Path(str(receipt_payload.get("release_channel_receipt") or ""))
                        )
                        == normalized_absolute_path(release_channel_receipt)
                    )
                    receipt_invocation_matches_current = bool(
                        str(receipt_payload.get("invocation_id") or "").strip()
                        == verification_invocation_id
                    )
                    receipt_process_result_consistent = bool(
                        (receipt_status == "pass" and completed.returncode == 0)
                        or (receipt_status == "fail" and completed.returncode == 1)
                    )
                    receipt_program_bindings_match = bool(
                        receipt_payload.get("publisher_verification_programs_match") is True
                        and verification_program_envelopes_match(
                            verification_programs_after,
                            receipt_payload.get("publisher_verification_programs") or {},
                        )
                    )
                    program_binding_failure = bool(
                        not verification_programs_match
                        or not parity_program_binding_matches
                        or (receipt_payload and not receipt_program_bindings_match)
                    )
                    browser_redirect_passed = str(landing_browser_redirect.get("status") or "").strip() == "pass"
                    local_live_surface_parity_passed = str(local_live_surface_parity.get("status") or "").strip() == "pass"
                    overlay_readiness_passed = str(overlay_readiness.get("status") or "").strip() == "pass"
                    receipt_passed_for_overlay = (
                        receipt_binding_matches_selected_input
                        and receipt_invocation_matches_current
                        and receipt_process_result_consistent
                        and verification_programs_match
                        and parity_program_binding_matches
                        and receipt_program_bindings_match
                        and (
                        (
                            receipt_status == "pass"
                            and pass_receipt_contract_satisfied
                        )
                        or receipt_allows_overlay_activation
                        )
                    )
                    passed = (
                        receipt_passed_for_overlay
                        and overlay_readiness_passed
                        and not landing_missing_markers
                        and browser_redirect_passed
                        and local_live_surface_parity_passed
                    )
                    startup_log_handle.flush()
                    return {
                        "status": "pass" if passed else "fail",
                        "reason": (
                            ""
                            if passed
                            else "verification_program_binding_mismatch"
                            if program_binding_failure
                            else "combined_readiness_failed"
                            if overlay_readiness_passed is False
                            else "landing_marker_missing"
                            if receipt_passed_for_overlay and landing_missing_markers
                            else "landing_browser_redirect_failed"
                            if receipt_passed_for_overlay and browser_redirect_passed is False
                            else "live_surface_parity_failed"
                            if receipt_passed_for_overlay and local_live_surface_parity_passed is False
                            else "verification_failed"
                        ),
                        "baseUrl": base_url,
                        "receiptPath": str(verification_receipt_path),
                        "exitCode": completed.returncode,
                        "receiptStatus": receipt_status,
                        "receiptSha256": hashlib.sha256(verification_receipt_path.read_bytes()).hexdigest() if verification_receipt_path.is_file() else "",
                        "childReceiptSha256BeforeProgramBinding": child_receipt_sha256_before_program_binding,
                        "probeError": "",
                        "stdout": completed.stdout[-4000:],
                        "stderr": completed.stderr[-4000:],
                        "receiptAllowsOverlayActivation": receipt_allows_overlay_activation,
                        "passReceiptContractSatisfied": pass_receipt_contract_satisfied,
                        "receiptBindingMatchesSelectedInput": receipt_binding_matches_selected_input,
                        "verificationInvocationId": verification_invocation_id,
                        "receiptInvocationMatchesCurrent": receipt_invocation_matches_current,
                        "receiptProcessResultConsistent": receipt_process_result_consistent,
                        "verificationPrograms": verification_programs_after,
                        "verificationProgramsMatch": verification_programs_match,
                        "receiptProgramBindingsMatch": receipt_program_bindings_match,
                        "verifierProgramSnapshotExecuted": str(
                            verification_programs_before["programs"]["downloadsVersionMarker"][
                                "snapshotPath"
                            ]
                        ),
                        "verifierProgramExecutionMode": str(verifier_execution["mode"]),
                        "verifierProgramExecutionSha256Expected": str(
                            verifier_execution["sha256Expected"]
                        ),
                        "verifierProgramExecutionSha256Actual": str(
                            verifier_execution["sha256Actual"]
                        ),
                        "verifierProgramExecutionSha256Matches": bool(
                            verifier_execution["sha256Matches"]
                        ),
                        "parityProgramSnapshotImported": str(
                            local_live_surface_parity.get("programSnapshotImported") or ""
                        ),
                        "releaseChannelReceiptPath": str(
                            receipt_payload.get("release_channel_receipt") or ""
                        ).strip(),
                        "releaseChannelReceiptSnapshotPath": str(release_channel_receipt),
                        "releaseChannelReceiptSha256Expected": str(
                            receipt_payload.get("release_channel_receipt_sha256_expected") or ""
                        ).strip(),
                        "releaseChannelReceiptSha256Actual": str(
                            receipt_payload.get("release_channel_receipt_sha256_actual") or ""
                        ).strip(),
                        "releaseChannelReceiptSha256Matches": bool(
                            receipt_payload.get("release_channel_receipt_sha256_matches")
                        ),
                        "releaseChannelVersion": str(
                            receipt_payload.get("release_channel_version") or ""
                        ).strip(),
                        "releaseChannelPublishedAt": str(
                            receipt_payload.get("release_channel_published_at") or ""
                        ).strip(),
                        "releaseManifestConservativeReviewFloorApplied": bool(
                            receipt_payload.get(
                                "release_manifest_conservative_review_floor_applied"
                            )
                        ),
                        "releaseManifestSupportabilityExact": receipt_payload.get(
                            "release_manifest_supportability_matches_release_channel"
                        ),
                        "releaseManifestSupportabilityCompatible": receipt_payload.get(
                            "release_manifest_supportability_compatible_with_release_channel"
                        ),
                        "releaseManifestRolloutExact": receipt_payload.get(
                            "release_manifest_rollout_matches_release_channel"
                        ),
                        "releaseManifestRolloutCompatible": receipt_payload.get(
                            "release_manifest_rollout_compatible_with_release_channel"
                        ),
                        "landingMarkerStatus": "pass" if not landing_missing_markers else "fail",
                        "landingMarkerChecks": landing_marker_checks,
                        "landingMissingMarkers": landing_missing_markers,
                        "landingBrowserRedirect": landing_browser_redirect,
                        "combinedReadiness": overlay_readiness,
                        "localRuntimeDependencyBaseUrl": dependency_stub.base_url,
                        "localLiveSurfaceParity": local_live_surface_parity,
                        "startupLogPath": str(startup_log_path),
                        "startupLogTail": read_text_tail(startup_log_path),
                        "receiptSummary": {
                            "statusRedirectHeading": receipt_payload.get("status_redirect_heading"),
                            "statusRedirectHeadingExpected": receipt_payload.get("status_redirect_heading_expected"),
                            "downloadsHasMarker": receipt_payload.get("downloads_has_marker"),
                            "statusRedirectHasMarker": receipt_payload.get("status_redirect_has_marker"),
                            "receiptAllowsOverlayActivation": receipt_allows_overlay_activation,
                            "passReceiptContractSatisfied": pass_receipt_contract_satisfied,
                            "receiptBindingMatchesSelectedInput": receipt_binding_matches_selected_input,
                            "receiptInvocationMatchesCurrent": receipt_invocation_matches_current,
                            "receiptProcessResultConsistent": receipt_process_result_consistent,
                            "verificationProgramsMatch": verification_programs_match,
                            "receiptProgramBindingsMatch": receipt_program_bindings_match,
                            "releaseChannelReceiptSha256": str(
                                receipt_payload.get("release_channel_receipt_sha256_actual") or ""
                            ).strip(),
                            "releaseChannelVersion": str(
                                receipt_payload.get("release_channel_version") or ""
                            ).strip(),
                            "releaseChannelPublishedAt": str(
                                receipt_payload.get("release_channel_published_at") or ""
                            ).strip(),
                            "releaseManifestConservativeReviewFloorApplied": bool(
                                receipt_payload.get(
                                    "release_manifest_conservative_review_floor_applied"
                                )
                            ),
                            "landingHasPlayDisabledTarget": landing_marker_checks.get("playDisabledTarget"),
                            "landingHasPlaySignInRoute": landing_marker_checks.get("playSignInRoute"),
                            "landingHasTurnAnchor": landing_marker_checks.get("turnAnchor"),
                            "landingHasTurnAnchorRedirect": landing_marker_checks.get("turnAnchorRedirect"),
                            "landingBrowserRedirectStatus": landing_browser_redirect.get("status"),
                            "landingBrowserRedirectPathMatches": landing_browser_redirect.get("pathMatches"),
                            "landingBrowserRedirectHashMatches": landing_browser_redirect.get("hashMatches"),
                            "combinedReadinessStatus": overlay_readiness.get("status"),
                            "combinedReadinessHttpStatus": overlay_readiness.get("httpStatus"),
                            "combinedReadinessBodyReady": overlay_readiness.get("bodyReady"),
                            "playProjectionStatus": (
                                overlay_readiness.get("playProjection") or {}
                            ).get("status"),
                            "localLiveSurfaceParityStatus": local_live_surface_parity.get("status"),
                            "localLiveSurfaceParityFailureCount": local_live_surface_parity.get("failureCount"),
                        },
                    }
                except RuntimeError as exc:
                    startup_log_handle.flush()
                    failed_programs = verification_program_binding_envelope(
                        verification_programs_before["programs"]
                    )
                    return {
                        "status": "fail",
                        "reason": "startup_probe_failed",
                        "baseUrl": base_url,
                        "receiptPath": str(verification_receipt_path),
                        "exitCode": process.poll(),
                        "receiptStatus": "",
                        "probeError": str(exc),
                        "startupLogPath": str(startup_log_path),
                        "startupLogTail": read_text_tail(startup_log_path),
                        "verificationPrograms": failed_programs,
                        "verificationProgramsMatch": False,
                    }
                finally:
                    if process.poll() is None:
                        remaining_cleanup_seconds = max(
                            0.0,
                            verification_budget.deadline_at_monotonic
                            - time.monotonic(),
                        )
                        if remaining_cleanup_seconds <= 0:
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except (ProcessLookupError, AttributeError):
                                process.kill()
                            try:
                                process.wait(timeout=1.0)
                            except subprocess.TimeoutExpired:
                                pass
                        else:
                            try:
                                os.killpg(process.pid, signal.SIGTERM)
                            except (ProcessLookupError, AttributeError):
                                process.terminate()
                            try:
                                process.wait(
                                    timeout=min(10.0, remaining_cleanup_seconds)
                                )
                            except subprocess.TimeoutExpired:
                                try:
                                    os.killpg(process.pid, signal.SIGKILL)
                                except (ProcessLookupError, AttributeError):
                                    process.kill()
                                try:
                                    process.wait(timeout=1.0)
                                except subprocess.TimeoutExpired:
                                    pass
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def materialize(
    output: Path,
    *,
    release_channel_receipt: Path,
    release_channel_receipt_sha256: str,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    active_root: Path = DEFAULT_ACTIVE_ROOT,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
    build_root: Path = DEFAULT_BUILD_ROOT,
    configuration: str = DEFAULT_CONFIGURATION,
    activate: bool = False,
    reuse_staging: bool = False,
    skip_backup_on_activate: bool = False,
    activation_mode: str = "copy",
    verify_timeout_seconds: float = DEFAULT_VERIFY_TIMEOUT_SECONDS,
    verification_deadline_seconds: float = DEFAULT_VERIFICATION_DEADLINE_SECONDS,
    publish_timeout_seconds: float = DEFAULT_PUBLISH_TIMEOUT_SECONDS,
    minimum_free_disk_bytes: int = DEFAULT_MINIMUM_FREE_DISK_BYTES,
    allow_low_disk_capacity: bool = False,
    _preflight_disk_capacity_check: dict[str, Any] | None = None,
    run_command_fn: Callable[..., subprocess.CompletedProcess[str]] = run_command,
    verify_overlay_fn: Callable[..., dict[str, Any]] = verify_published_overlay,
) -> dict[str, Any]:
    test_hooks_injected = bool(
        run_command_fn is not run_command
        or verify_overlay_fn is not verify_published_overlay
    )
    if test_hooks_injected and activate:
        raise RuntimeError(
            "non-production publisher callbacks cannot activate a public-edge overlay"
        )
    verify_timeout_seconds = validated_timeout_seconds(
        verify_timeout_seconds,
        label="verification timeout",
        maximum=MAX_VERIFY_TIMEOUT_SECONDS,
    )
    verification_deadline_seconds = validated_timeout_seconds(
        verification_deadline_seconds,
        label="global verification deadline",
        maximum=MAX_VERIFICATION_DEADLINE_SECONDS,
    )
    publish_timeout_seconds = validated_timeout_seconds(
        publish_timeout_seconds,
        label="publish timeout",
        maximum=MAX_PUBLISH_TIMEOUT_SECONDS,
    )
    path_plan = validate_publisher_path_plan(
        output=output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        activation_mode=activation_mode,
    )
    output = path_plan["output"]
    release_channel_receipt = path_plan["releaseChannelReceipt"]
    source_root = path_plan["sourceRoot"]
    staging_root = path_plan["stagingRoot"]
    active_root = path_plan["activeRoot"]
    backup_root = path_plan["backupRoot"]
    build_root = path_plan["buildRoot"]
    minimum_free_disk_bytes = validated_minimum_free_disk_bytes(
        minimum_free_disk_bytes
    )
    if _preflight_disk_capacity_check is None:
        capacity_check = require_disk_capacity(
            staging_root=staging_root,
            build_root=build_root,
            minimum_free_bytes=minimum_free_disk_bytes,
            allow_low_disk_capacity=allow_low_disk_capacity,
        )
    else:
        if not preflight_disk_capacity_matches(
            _preflight_disk_capacity_check,
            staging_root=staging_root,
            build_root=build_root,
            minimum_free_bytes=minimum_free_disk_bytes,
            allow_low_disk_capacity=allow_low_disk_capacity,
        ):
            raise RuntimeError(
                "preflight disk-capacity evidence does not match publisher inputs"
            )
        capacity_check = _preflight_disk_capacity_check
    release_channel_raw_bytes, release_channel_binding = read_bound_release_channel_receipt(
        release_channel_receipt,
        release_channel_receipt_sha256,
    )
    normalized_release_channel_sha256 = str(
        release_channel_binding["sha256Actual"]
    )
    assert_no_incomplete_activation_transaction(active_root)
    release_channel_snapshot_path = snapshot_bound_release_channel_receipt(
        path_plan["releaseAuthorityRoot"],
        release_channel_raw_bytes,
        release_channel_binding,
    )
    if not paths_are_aliases(release_channel_snapshot_path, path_plan["releaseChannelSnapshot"]):
        raise RuntimeError("release-channel snapshot did not use the preflighted content-addressed path")
    verification_programs = snapshot_verification_programs(
        path_plan["verificationProgramAuthorityRoot"]
    )
    workspace_root = source_root.parent.resolve()
    project_path = source_root / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"
    cleaned_paths = [
        build_root,
        staging_root,
    ]
    verification_receipt_path = path_plan["verificationReceipt"]
    build_source_root = source_root
    overlay_payload_source_root = source_root
    build_project_path = project_path
    copied_build_workspace_roots: list[str] = []
    publish_command: list[str] = []
    built_source_fingerprint: dict[str, Any] = {}
    staging_source_fingerprint_check: dict[str, Any] = {
        "status": "not_checked",
        "reason": "publish_not_started",
        "buildInfoPath": str(staging_root / OVERLAY_BUILD_INFO_RELATIVE_PATH),
        "recordedAggregateSha256": "",
        "expectedAggregateSha256": "",
        "matchesCurrentSource": False,
    }

    publish_skipped = False
    publish_skip_reason = ""
    if reuse_staging:
        if staging_overlay_ready(staging_root):
            staging_source_fingerprint_check = staged_source_fingerprint_check(staging_root, source_root)
            if staging_source_fingerprint_check["status"] == "pass":
                built_source_fingerprint = dict(
                    staging_source_fingerprint_check.get("recordedSourceFingerprint") or {}
                )
                ensure_empty_directory(build_root)
                overlay_payload_source_root, copied_build_workspace_roots = materialize_isolated_build_workspace(
                    source_root,
                    build_root,
                )
                snapshot_fingerprint = source_fingerprint(overlay_payload_source_root)
                snapshot_comparison = source_fingerprint_comparison(
                    built_source_fingerprint,
                    snapshot_fingerprint,
                )
                if snapshot_comparison["matchesCurrentSource"]:
                    publish_skipped = True
                    publish_skip_reason = "reused_existing_staging_overlay"
                    publish = subprocess.CompletedProcess(
                        args=publish_command,
                        returncode=0,
                        stdout="reused existing staging overlay\n",
                        stderr="",
                    )
                else:
                    publish_skip_reason = "source_changed_during_reuse_snapshot"
                    staging_source_fingerprint_check.update(
                        {
                            "status": "fail",
                            "reason": publish_skip_reason,
                            **snapshot_comparison,
                            "recordedSourceFingerprint": built_source_fingerprint,
                            "expectedSourceFingerprint": snapshot_fingerprint,
                        }
                    )
                    publish = subprocess.CompletedProcess(
                        args=publish_command,
                        returncode=1,
                        stdout="",
                        stderr=publish_skip_reason + "\n",
                    )
            else:
                publish_skip_reason = str(staging_source_fingerprint_check.get("reason") or "staging_source_fingerprint_invalid")
                publish = subprocess.CompletedProcess(
                    args=publish_command,
                    returncode=1,
                    stdout="",
                    stderr=publish_skip_reason + "\n",
                )
        else:
            publish_skip_reason = "staging_overlay_missing_app_dll"
            publish = subprocess.CompletedProcess(
                args=publish_command,
                returncode=1,
                stdout="",
                stderr="staging overlay is not ready for reuse\n",
            )
    else:
        ensure_empty_directory(build_root)
        ensure_empty_directory(staging_root)
        build_source_root, copied_build_workspace_roots = materialize_isolated_build_workspace(source_root, build_root)
        overlay_payload_source_root = build_source_root
        built_source_fingerprint = source_fingerprint(build_source_root)
        build_project_path = build_source_root / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"
        publish_command = [
            "dotnet",
            "publish",
            str(build_project_path),
            "-c",
            configuration,
            "-o",
            str(staging_root),
            "--nologo",
            "-m:1",
            "-p:BuildInParallel=false",
            "-p:UseSharedCompilation=false",
            "-p:ChummerDesktopRuntimeIdentifiers=",
        ]
        if run_command_fn is run_command:
            publish = run_command_fn(
                publish_command,
                cwd=build_source_root,
                timeout_seconds=publish_timeout_seconds,
            )
        else:
            publish = run_command_fn(publish_command, cwd=build_source_root)

    if not reuse_staging:
        current_source_fingerprint = source_fingerprint(source_root)
        comparison = source_fingerprint_comparison(
            built_source_fingerprint,
            current_source_fingerprint,
        )
        source_matches_current = bool(comparison["matchesCurrentSource"])
        staging_source_fingerprint_check = {
            "status": "pass" if source_matches_current else "fail",
            "reason": "" if source_matches_current else "source_changed_during_overlay_build",
            "buildInfoPath": str(staging_root / OVERLAY_BUILD_INFO_RELATIVE_PATH),
            **comparison,
            "recordedSourceFingerprint": built_source_fingerprint,
            "expectedSourceFingerprint": current_source_fingerprint,
        }

    copied_source_wwwroot = False
    copied_codex_design = False
    copied_black_ledger = False
    verification: dict[str, Any] = {
        "status": "skipped",
        "reason": "publish_failed",
        "baseUrl": "",
        "receiptPath": str(verification_receipt_path),
        "exitCode": None,
        "receiptStatus": "",
        "probeError": "",
        "releaseChannelReceiptPath": str(release_channel_binding["selectedPath"]),
        "releaseChannelReceiptSnapshotPath": str(
            release_channel_snapshot_path or ""
        ),
        "releaseChannelReceiptSha256Expected": normalized_release_channel_sha256,
        "releaseChannelReceiptSha256Actual": normalized_release_channel_sha256,
        "releaseChannelReceiptSha256Matches": False,
        "verificationPrograms": verification_programs,
        "verificationProgramsMatch": True,
        "receiptProgramBindingsMatch": False,
        "testOnlyHooksInjected": test_hooks_injected,
    }
    backup_path: Path | None = None
    backup_skipped = False
    backup_skip_reason = ""
    activation_status = "not_requested"
    activation_failure_reason = ""
    activation_rollback_status = "not_required"
    activation_recovery_path = ""
    activation_atomic_cutover = False
    activation_retired_cleanup_status = "not_applicable"
    activation_retired_recovery_path = ""
    activation_transaction_cleanup_status = "not_started"
    activation_transaction_journal_path_value = str(
        activation_transaction_journal_path(active_root)
    )
    compose_mountpoints_created: list[str] = []
    staged_payload_integrity_check: dict[str, Any] = {
        "status": "not_checked",
        "reason": "publish_not_verified",
        "beforeVerification": {},
        "afterVerification": {},
    }
    payload_mode_normalization: dict[str, Any] = {
        "status": "not_checked",
    }
    payload_mode_integrity_check: dict[str, Any] = {
        "status": "not_checked",
    }

    if publish.returncode == 0:
        overlay_payload_workspace_root = overlay_payload_source_root.parent
        source_wwwroot = overlay_payload_source_root / "Chummer.Run.Api" / "wwwroot"
        codex_design_source = overlay_payload_source_root / ".codex-design"
        black_ledger_source = (
            overlay_payload_workspace_root / "chummer-hub-registry" / "black-ledger"
        )
        (staging_root / "state").mkdir(parents=True, exist_ok=True)
        copied_source_wwwroot = merge_optional_tree(source_wwwroot, staging_root / "wwwroot")
        copied_codex_design = copy_optional_tree(codex_design_source, staging_root / ".codex-design")
        copied_black_ledger = copy_optional_tree(black_ledger_source, staging_root / "black-ledger")
        compose_mountpoints_created = ensure_required_compose_mountpoints(staging_root)
        normalized_mode_receipt = normalize_payload_modes(staging_root)
        payload_mode_normalization = {
            "status": normalized_mode_receipt["status"],
            "changedEntryCount": normalized_mode_receipt["normalization"][
                "changedEntryCount"
            ],
            "entryBinding": normalized_mode_receipt["entryBinding"],
        }
        pre_verification_payload_mode_receipt = validate_payload_modes(staging_root)
        pre_verification_staged_payload_fingerprint = staged_payload_fingerprint(staging_root)
        post_copy_source_fingerprint = source_fingerprint(source_root)
        post_copy_comparison = source_fingerprint_comparison(
            built_source_fingerprint,
            post_copy_source_fingerprint,
        )
        source_drift_already_observed = staging_source_fingerprint_check.get("status") == "fail"
        post_copy_source_matches = bool(
            post_copy_comparison["matchesCurrentSource"] and not source_drift_already_observed
        )
        staging_source_fingerprint_check.update(
            {
                "status": "pass" if post_copy_source_matches else "fail",
                "reason": (
                    ""
                    if post_copy_source_matches
                    else str(staging_source_fingerprint_check.get("reason") or "source_changed_during_overlay_copy")
                ),
                **post_copy_comparison,
                "matchesCurrentSource": post_copy_source_matches,
                "recordedSourceFingerprint": built_source_fingerprint,
                "expectedSourceFingerprint": post_copy_source_fingerprint,
            }
        )
        if post_copy_source_matches:
            verification_kwargs: dict[str, Any] = {
                "source_root": source_root,
                "verify_timeout_seconds": verify_timeout_seconds,
                "verification_receipt_path": verification_receipt_path,
                "release_channel_receipt": release_channel_snapshot_path,
                "release_channel_receipt_sha256": normalized_release_channel_sha256,
                "verification_programs": verification_programs,
            }
            if callable_accepts_keyword(
                verify_overlay_fn,
                "verification_deadline_seconds",
            ):
                verification_kwargs["verification_deadline_seconds"] = (
                    verification_deadline_seconds
                )
            verification = verify_overlay_fn(
                staging_root,
                **verification_kwargs,
            )
            verification["testOnlyHooksInjected"] = test_hooks_injected
            observed_verification_programs = verification.get("verificationPrograms")
            observed_verification_programs = (
                observed_verification_programs
                if isinstance(observed_verification_programs, dict)
                else {}
            )
            current_verification_programs = verification_program_binding_envelope(
                verification_programs["programs"]
            )
            measured_production_evidence = production_verification_evidence(
                verification,
                verification_programs,
                verification_receipt_path,
            )
            production_execution_evidence_matches = (
                measured_production_evidence["status"] == "pass"
            )
            verification_programs_match = bool(
                verification.get("verificationProgramsMatch") is True
                and verification.get("receiptProgramBindingsMatch") is True
                and verification_program_envelopes_match(
                    verification_programs,
                    observed_verification_programs,
                )
                and verification_program_envelopes_match(
                    verification_programs,
                    current_verification_programs,
                )
                and (
                    test_hooks_injected
                    or production_execution_evidence_matches
                )
            )
            verification["verificationPrograms"] = current_verification_programs
            verification["verificationProgramsMatch"] = verification_programs_match
            verification["productionExecutionEvidence"] = measured_production_evidence
            verification["productionExecutionEvidenceMatches"] = (
                production_execution_evidence_matches
            )
            verification_binding_matches = bool(
                verification.get("receiptBindingMatchesSelectedInput") is True
                and verification.get("receiptInvocationMatchesCurrent") is True
                and verification.get("receiptProcessResultConsistent") is True
                and verification.get("releaseChannelReceiptSha256Matches") is True
                and str(
                    verification.get("releaseChannelReceiptSha256Expected") or ""
                ).strip().lower()
                == normalized_release_channel_sha256
                and str(
                    verification.get("releaseChannelReceiptSha256Actual") or ""
                ).strip().lower()
                == normalized_release_channel_sha256
                and normalized_absolute_path(
                    Path(str(verification.get("releaseChannelReceiptSnapshotPath") or ""))
                )
                == normalized_absolute_path(release_channel_snapshot_path)
                and verification_programs_match
            )
            if not verification_binding_matches:
                verification["status"] = "fail"
                if verification.get("timedOut") is not True:
                    verification["reason"] = (
                        "verification_program_binding_mismatch"
                        if not verification_programs_match
                        else "release_channel_receipt_binding_mismatch"
                    )
                verification["receiptAllowsOverlayActivation"] = False
            payload_mode_integrity_check = validate_payload_modes_against_receipt(
                staging_root,
                pre_verification_payload_mode_receipt,
            )
            if payload_mode_integrity_check.get("status") != "pass":
                verification["status"] = "fail"
                verification["reason"] = "staging_payload_modes_changed_during_verification"
                verification["receiptAllowsOverlayActivation"] = False
            staged_payload_fingerprint_error = ""
            try:
                post_verification_staged_payload_fingerprint = (
                    staged_payload_fingerprint(staging_root)
                )
            except (OSError, RuntimeError) as exc:
                post_verification_staged_payload_fingerprint = {}
                staged_payload_fingerprint_error = str(exc)
            staged_payload_unchanged = bool(
                not staged_payload_fingerprint_error
                and fingerprint_envelope_matches(
                    pre_verification_staged_payload_fingerprint,
                    post_verification_staged_payload_fingerprint,
                )
            )
            staged_payload_change_reason = (
                "staging_payload_modes_changed_during_verification"
                if payload_mode_integrity_check.get("status") != "pass"
                else "staging_payload_changed_during_verification"
            )
            staged_payload_integrity_check = {
                "status": "pass" if staged_payload_unchanged else "fail",
                "reason": (
                    ""
                    if staged_payload_unchanged
                    else staged_payload_change_reason
                ),
                "beforeVerification": pre_verification_staged_payload_fingerprint,
                "afterVerification": post_verification_staged_payload_fingerprint,
                "inspectionError": staged_payload_fingerprint_error,
            }
            if not staged_payload_unchanged:
                verification["status"] = "fail"
                verification["reason"] = staged_payload_change_reason
                verification["receiptAllowsOverlayActivation"] = False
            post_verification_source_fingerprint = source_fingerprint(source_root)
            post_verification_comparison = source_fingerprint_comparison(
                built_source_fingerprint,
                post_verification_source_fingerprint,
            )
            post_verification_source_matches = bool(
                post_verification_comparison["matchesCurrentSource"]
            )
            staging_source_fingerprint_check.update(
                {
                    "status": "pass" if post_verification_source_matches else "fail",
                    "reason": (
                        ""
                        if post_verification_source_matches
                        else "source_changed_during_overlay_verification"
                    ),
                    **post_verification_comparison,
                    "recordedSourceFingerprint": built_source_fingerprint,
                    "expectedSourceFingerprint": post_verification_source_fingerprint,
                }
            )
        else:
            verification = {
                "status": "skipped",
                "reason": "source_fingerprint_mismatch_after_overlay_copy",
                "baseUrl": "",
                "receiptPath": str(verification_receipt_path),
                "exitCode": None,
                "receiptStatus": "",
                "probeError": "",
                "verificationPrograms": verification_program_binding_envelope(
                    verification_programs["programs"]
                ),
                "verificationProgramsMatch": False,
                "receiptProgramBindingsMatch": False,
            }
            staged_payload_integrity_check = {
                "status": "skipped",
                "reason": "source_fingerprint_mismatch_after_overlay_copy",
                "beforeVerification": pre_verification_staged_payload_fingerprint,
                "afterVerification": {},
            }
            payload_mode_integrity_check = {
                "status": "skipped",
                "reason": "source_fingerprint_mismatch_after_overlay_copy",
            }
        verification_passed_for_activation = verification_supports_overlay_activation(verification)
        source_matches_current = bool(staging_source_fingerprint_check.get("matchesCurrentSource"))
        if activate and verification_passed_for_activation and source_matches_current:
            if skip_backup_on_activate:
                backup_skipped = True
                backup_skip_reason = "requested"
            try:
                write_overlay_build_info(
                    staging_root,
                    source_root=source_root,
                    built_source_fingerprint=built_source_fingerprint,
                    status="pass",
                    activation_status="activated",
                    verification=verification,
                )
                activation_result = activate_overlay_tree(
                    staging_root,
                    active_root,
                    mode=activation_mode,
                    backup_root=None if skip_backup_on_activate else backup_root,
                )
                backup_path_value = str(activation_result.get("backupPath") or "")
                backup_path = Path(backup_path_value) if backup_path_value else None
                activation_atomic_cutover = bool(activation_result.get("atomicCutover"))
                activation_rollback_status = str(
                    activation_result.get("rollbackStatus") or "not_required"
                )
                activation_retired_cleanup_status = str(
                    activation_result.get("retiredCleanupStatus") or "not_applicable"
                )
                activation_retired_recovery_path = str(
                    activation_result.get("retiredRecoveryPath") or ""
                )
                activation_transaction_journal_path_value = str(
                    activation_result.get("transactionJournalPath")
                    or activation_transaction_journal_path_value
                )
                activation_transaction_cleanup_status = str(
                    activation_result.get("transactionCleanupStatus") or "complete"
                )
                if activation_transaction_cleanup_status == "complete":
                    activation_status = "activated"
                else:
                    activation_status = "activation_failure_recovery_required"
                    activation_failure_reason = "activation_journal_cleanup_failed"
                    activation_rollback_status = "committed_recovery_required"
                    activation_recovery_path = activation_transaction_journal_path_value
            except Exception as exc:
                activation_failure_reason = (
                    exc.reason
                    if isinstance(exc, OverlayActivationError)
                    else "activation_preflight_failed"
                )
                activation_rollback_status = (
                    exc.rollback_status
                    if isinstance(exc, OverlayActivationError)
                    else "active_unchanged"
                )
                activation_recovery_path = (
                    str(exc.recovery_path)
                    if isinstance(exc, OverlayActivationError) and exc.recovery_path is not None
                    else ""
                )
                activation_status = (
                    "activation_failure_recovery_required"
                    if activation_rollback_status == "rollback_failed_recovery_required"
                    else "rolled_back_after_activation_failure"
                    if activation_rollback_status
                    in {"exact_prior_active_restored", "prior_absence_restored"}
                    else "blocked_by_activation_failure"
                )
        elif activate and not source_matches_current:
            activation_status = "blocked_by_source_fingerprint_mismatch"
        elif activate:
            activation_status = "blocked_by_failed_verification"
        else:
            activation_status = "staged_only"

    verification_passed_for_activation = verification_supports_overlay_activation(verification)
    source_matches_current = bool(staging_source_fingerprint_check.get("matchesCurrentSource"))
    activation_satisfied = (
        activation_status == "activated" if activate else activation_status == "staged_only"
    )
    status = (
        "pass"
        if publish.returncode == 0
        and verification_passed_for_activation
        and source_matches_current
        and activation_satisfied
        else "fail"
    )
    computed_status = status
    if test_hooks_injected and computed_status == "pass":
        status = "test_only"
    next_action = (
        "Discard this test-only receipt; rerun with the production publisher and verifier functions."
        if test_hooks_injected
        else
        "Recreate chummer-portal from the refreshed mounted overlay and rerun local /status postdeploy proof."
        if status == "pass" and activate
        else "Overlay payload staged and verified; activate it explicitly before recreating chummer-portal."
        if status == "pass"
        else "Rebuild the staged overlay from current source before activation."
        if not source_matches_current
        else "Fix publish or verification failures before replacing the mounted public-edge overlay."
    )
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "status": status,
        "testOutcomeStatus": computed_status if test_hooks_injected else "",
        "testOnly": test_hooks_injected,
        "authoritativeReceipt": not test_hooks_injected,
        "goalCompletionClaimAllowed": False,
        "sourceRoot": str(source_root),
        "projectPath": str(project_path),
        "buildSourceRoot": str(build_source_root),
        "buildProjectPath": str(build_project_path),
        "copiedBuildWorkspaceRoots": copied_build_workspace_roots,
        "configuration": configuration,
        "publishTimeoutSeconds": publish_timeout_seconds,
        "verifyTimeoutSeconds": verify_timeout_seconds,
        "verificationDeadlineSeconds": verification_deadline_seconds,
        "diskCapacityCheck": capacity_check,
        "stagingRoot": str(staging_root),
        "activeRoot": str(active_root),
        "backupRoot": str(backup_root),
        "buildRoot": str(build_root),
        "releaseChannelReceipt": release_channel_binding,
        "verificationPrograms": verification.get("verificationPrograms") or {},
        "verificationProgramsMatch": bool(
            verification.get("verificationProgramsMatch")
        ),
        "productionExecutionEvidenceMatches": bool(
            verification.get("productionExecutionEvidenceMatches")
        ),
        "activateRequested": activate,
        "activationStatus": activation_status,
        "activationAtomicCutover": activation_atomic_cutover,
        "activationFailureReason": activation_failure_reason,
        "activationRollbackStatus": activation_rollback_status,
        "activationRecoveryPath": activation_recovery_path,
        "activationRetiredCleanupStatus": activation_retired_cleanup_status,
        "activationRetiredRecoveryPath": activation_retired_recovery_path,
        "activationTransactionJournalPath": activation_transaction_journal_path_value,
        "activationTransactionCleanupStatus": activation_transaction_cleanup_status,
        "reuseStaging": reuse_staging,
        "skipBackupOnActivate": skip_backup_on_activate,
        "activationMode": activation_mode,
        "cleanedPaths": [str(path) for path in cleaned_paths],
        "publishCommand": publish_command,
        "publish": {
            "exitCode": publish.returncode,
            "stdoutTail": publish.stdout[-4000:],
            "stderrTail": publish.stderr[-4000:],
            "timedOut": publish.returncode == PUBLISH_TIMEOUT_EXIT_CODE,
            "timeoutSeconds": publish_timeout_seconds,
            "skipped": publish_skipped,
            "skipReason": publish_skip_reason,
        },
        "stagingSourceFingerprintCheck": staging_source_fingerprint_check,
        "composeMountpointsCreated": compose_mountpoints_created,
        "copiedSourceWwwroot": copied_source_wwwroot,
        "copiedCodexDesign": copied_codex_design,
        "copiedBlackLedger": copied_black_ledger,
        "verification": verification,
        "stagedPayloadIntegrityCheck": staged_payload_integrity_check,
        "payloadModeNormalization": payload_mode_normalization,
        "payloadModeIntegrityCheck": payload_mode_integrity_check,
        "backupPath": str(backup_path) if backup_path is not None else "",
        "backupSkipped": backup_skipped,
        "backupSkipReason": backup_skip_reason,
        "nextAction": next_action,
        "warning": (
            "The public-edge compose service bind-mounts /app from the active overlay root. Rebuilding the image alone does not refresh runtime payload."
        ),
    }
    if publish.returncode == 0:
        verification_passed_for_activation = verification_supports_overlay_activation(verification)
        build_info_status = (
            "pass"
            if verification_passed_for_activation
            and source_matches_current
            and (not activate or activation_status == "activated")
            else "fail"
        )
        if test_hooks_injected and build_info_status == "pass":
            build_info_status = "test_only"
        if staging_root.exists():
            build_info_path = write_overlay_build_info(
                staging_root,
                source_root=source_root,
                built_source_fingerprint=built_source_fingerprint,
                status=build_info_status,
                activation_status=activation_status,
                verification=verification,
            )
            payload["stagingBuildInfoPath"] = str(build_info_path)
        else:
            payload["stagingBuildInfoPath"] = ""
        if activation_status == "activated":
            active_build_info_path = active_root / OVERLAY_BUILD_INFO_RELATIVE_PATH
            if not active_build_info_path.is_file():
                raise RuntimeError(
                    "activated overlay is missing its transactionally installed build metadata"
                )
            payload["activeBuildInfoPath"] = str(active_build_info_path)
        else:
            payload["activeBuildInfoPath"] = ""
    else:
        payload["stagingBuildInfoPath"] = ""
        payload["activeBuildInfoPath"] = ""
    atomic_write_json(output, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage and optionally activate a verified public-edge overlay payload.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--release-channel-receipt",
        type=Path,
        required=True,
        help="Exact release-channel receipt snapshot to bind into staged verification.",
    )
    parser.add_argument(
        "--release-channel-receipt-sha256",
        required=True,
        help="Operator-supplied SHA-256 of the exact release-channel receipt bytes.",
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--staging-root", type=Path, default=DEFAULT_STAGING_ROOT)
    parser.add_argument("--active-root", type=Path, default=DEFAULT_ACTIVE_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--build-root", type=Path, default=DEFAULT_BUILD_ROOT)
    parser.add_argument("--configuration", default=DEFAULT_CONFIGURATION)
    parser.add_argument(
        "--verify-timeout-seconds",
        type=float,
        default=DEFAULT_VERIFY_TIMEOUT_SECONDS,
        help=(
            "Per-probe verification timeout in seconds "
            f"(default {DEFAULT_VERIFY_TIMEOUT_SECONDS:g}, maximum {MAX_VERIFY_TIMEOUT_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--verification-deadline-seconds",
        type=float,
        default=DEFAULT_VERIFICATION_DEADLINE_SECONDS,
        help=(
            "Hard wall-clock budget for the entire local verification phase in seconds "
            f"(default {DEFAULT_VERIFICATION_DEADLINE_SECONDS:g}, maximum {MAX_VERIFICATION_DEADLINE_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--publish-timeout-seconds",
        type=float,
        default=DEFAULT_PUBLISH_TIMEOUT_SECONDS,
        help=(
            "dotnet publish timeout in seconds "
            f"(default {DEFAULT_PUBLISH_TIMEOUT_SECONDS:g}, maximum {MAX_PUBLISH_TIMEOUT_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--minimum-free-disk-bytes",
        type=int,
        default=DEFAULT_MINIMUM_FREE_DISK_BYTES,
        help=(
            "Required free bytes on every filesystem hosting the staging or build root "
            f"before any receipt or staging mutation (default {DEFAULT_MINIMUM_FREE_DISK_BYTES})."
        ),
    )
    parser.add_argument(
        "--allow-low-disk-capacity",
        action="store_true",
        help=(
            "Explicitly override a failed disk-capacity floor. The override and measured "
            "capacity remain recorded in the publisher receipt."
        ),
    )
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--reuse-staging", action="store_true")
    parser.add_argument("--skip-backup-on-activate", action="store_true")
    parser.add_argument("--activation-mode", choices=("copy",), default="copy")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    publish_timeout_seconds: float | None = None
    verify_timeout_seconds: float | None = None
    verification_deadline_seconds: float | None = None
    minimum_free_disk_bytes: int | None = None
    allow_low_disk_capacity = bool(
        getattr(args, "allow_low_disk_capacity", False)
    )
    capacity_check: dict[str, Any] = {}
    timeout_validation_errors: list[str] = []
    resolved_source_root = args.source_root.resolve()
    normalized_active_root = normalized_absolute_path(args.active_root)
    path_plan: dict[str, Path] | None = None
    try:
        try:
            publish_timeout_seconds = validated_timeout_seconds(
                getattr(
                    args,
                    "publish_timeout_seconds",
                    DEFAULT_PUBLISH_TIMEOUT_SECONDS,
                ),
                label="publish timeout",
                maximum=MAX_PUBLISH_TIMEOUT_SECONDS,
            )
        except RuntimeError as exc:
            timeout_validation_errors.append(str(exc))
        try:
            verify_timeout_seconds = validated_timeout_seconds(
                args.verify_timeout_seconds,
                label="verification timeout",
                maximum=MAX_VERIFY_TIMEOUT_SECONDS,
            )
        except RuntimeError as exc:
            timeout_validation_errors.append(str(exc))
        try:
            verification_deadline_seconds = validated_timeout_seconds(
                getattr(
                    args,
                    "verification_deadline_seconds",
                    DEFAULT_VERIFICATION_DEADLINE_SECONDS,
                ),
                label="global verification deadline",
                maximum=MAX_VERIFICATION_DEADLINE_SECONDS,
            )
        except RuntimeError as exc:
            timeout_validation_errors.append(str(exc))
        try:
            minimum_free_disk_bytes = validated_minimum_free_disk_bytes(
                getattr(
                    args,
                    "minimum_free_disk_bytes",
                    DEFAULT_MINIMUM_FREE_DISK_BYTES,
                )
            )
        except RuntimeError as exc:
            timeout_validation_errors.append(str(exc))
        if timeout_validation_errors:
            raise RuntimeError(
                "invalid public-edge publisher timeout configuration: "
                + "; ".join(timeout_validation_errors)
            )

        path_plan = validate_publisher_path_plan(
            output=args.output,
            release_channel_receipt=args.release_channel_receipt,
            release_channel_receipt_sha256=args.release_channel_receipt_sha256,
            source_root=resolved_source_root,
            staging_root=args.staging_root,
            active_root=normalized_active_root,
            backup_root=args.backup_root,
            build_root=args.build_root,
            activation_mode=args.activation_mode,
        )
        with overlay_publish_lock(
            path_plan["sourceRoot"],
            path_plan["activeRoot"],
        ):
            capacity_check = require_disk_capacity(
                staging_root=path_plan["stagingRoot"],
                build_root=path_plan["buildRoot"],
                minimum_free_bytes=minimum_free_disk_bytes,
                allow_low_disk_capacity=allow_low_disk_capacity,
            )
            invalidate_prior_publisher_outputs(path_plan)
            payload = materialize(
                path_plan["output"],
                release_channel_receipt=path_plan["releaseChannelReceipt"],
                release_channel_receipt_sha256=args.release_channel_receipt_sha256,
                source_root=path_plan["sourceRoot"],
                staging_root=path_plan["stagingRoot"],
                active_root=path_plan["activeRoot"],
                backup_root=path_plan["backupRoot"],
                build_root=path_plan["buildRoot"],
                configuration=args.configuration,
                activate=args.activate,
                reuse_staging=args.reuse_staging,
                skip_backup_on_activate=args.skip_backup_on_activate,
                activation_mode=args.activation_mode,
                verify_timeout_seconds=verify_timeout_seconds,
                verification_deadline_seconds=verification_deadline_seconds,
                publish_timeout_seconds=publish_timeout_seconds,
                minimum_free_disk_bytes=minimum_free_disk_bytes,
                allow_low_disk_capacity=allow_low_disk_capacity,
                _preflight_disk_capacity_check=capacity_check,
            )
    except Exception as exc:
        lock_unavailable = isinstance(exc, OverlayPublishLockUnavailable)
        activation_error = isinstance(exc, OverlayActivationError)
        if isinstance(exc, OverlayDiskCapacityError):
            capacity_check = exc.check
        failure_reason = (
            "overlay_publish_lock_unavailable"
            if lock_unavailable
            else exc.reason
            if activation_error
            else "overlay_publish_preflight_failed"
        )
        activation_status = (
            "blocked_by_active_publisher"
            if lock_unavailable
            else "activation_failure_recovery_required"
            if activation_error and exc.rollback_status == "recovery_required"
            else "blocked_by_preflight_failure"
        )
        payload = {
            "contractName": CONTRACT_NAME,
            "generatedAtUtc": now_iso(),
            "status": "fail",
            "goalCompletionClaimAllowed": False,
            "sourceRoot": str(resolved_source_root),
            "projectPath": str(resolved_source_root / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"),
            "buildSourceRoot": str(resolved_source_root),
            "buildProjectPath": str(resolved_source_root / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"),
            "configuration": args.configuration,
            "publishTimeoutSeconds": publish_timeout_seconds,
            "verifyTimeoutSeconds": verify_timeout_seconds,
            "verificationDeadlineSeconds": verification_deadline_seconds,
            "timeoutValidation": {
                "status": "fail" if timeout_validation_errors else "pass",
                "errors": timeout_validation_errors,
            },
            "stagingRoot": str(normalized_absolute_path(args.staging_root)),
            "activeRoot": str(normalized_active_root),
            "backupRoot": str(normalized_absolute_path(args.backup_root)),
            "buildRoot": str(normalized_absolute_path(args.build_root)),
            "diskCapacityCheck": capacity_check or {
                "status": "not_checked",
                "minimumFreeBytes": minimum_free_disk_bytes,
                "defaultMinimumFreeBytes": DEFAULT_MINIMUM_FREE_DISK_BYTES,
                "overrideRequested": allow_low_disk_capacity,
                "filesystems": [],
                "failures": [],
            },
            "releaseChannelReceipt": {
                "selectedPath": str(normalized_absolute_path(args.release_channel_receipt)),
                "snapshotPath": "",
                "sha256Expected": str(args.release_channel_receipt_sha256 or "").strip().lower(),
                "sha256Actual": "",
                "sha256Matches": False,
            },
            "activateRequested": args.activate,
            "activationStatus": activation_status,
            "activationAtomicCutover": False,
            "activationFailureReason": failure_reason,
            "activationRollbackStatus": exc.rollback_status if activation_error else "not_started",
            "activationRecoveryPath": (
                str(exc.recovery_path)
                if activation_error and exc.recovery_path is not None
                else ""
            ),
            "activationTransactionJournalPath": str(
                activation_transaction_journal_path(normalized_active_root)
            ),
            "reuseStaging": args.reuse_staging,
            "skipBackupOnActivate": args.skip_backup_on_activate,
            "activationMode": args.activation_mode,
            "publishCommand": [],
            "publish": {
                "exitCode": None,
                "stdoutTail": "",
                "stderrTail": "",
                "timedOut": False,
                "timeoutSeconds": publish_timeout_seconds,
                "skipped": True,
                "skipReason": failure_reason,
            },
            "composeMountpointsCreated": [],
            "copiedSourceWwwroot": False,
            "copiedCodexDesign": False,
            "copiedBlackLedger": False,
            "verification": {
                "status": "skipped",
                "reason": failure_reason,
                "baseUrl": "",
                "receiptPath": str(
                    path_plan["verificationReceipt"]
                    if path_plan is not None
                    else normalized_absolute_path(args.output).parent
                    / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json"
                ),
                "exitCode": None,
                "receiptStatus": "",
                "probeError": "",
            },
            "backupPath": "",
            "backupSkipped": False,
            "backupSkipReason": "",
            "stagingBuildInfoPath": "",
            "activeBuildInfoPath": "",
            "nextAction": (
                "Wait for the active overlay publisher to finish and rerun this publish lane."
                if lock_unavailable
                else "Resolve the recorded preflight or recovery condition before rerunning this publish lane."
            ),
            "warning": str(exc),
            "lockPath": str(
                path_plan["publishLock"]
                if path_plan is not None
                else publish_lock_path(resolved_source_root, normalized_active_root)
            ),
            "failureReceiptWritten": False,
        }
    print(json.dumps(payload, sort_keys=True, allow_nan=False))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
