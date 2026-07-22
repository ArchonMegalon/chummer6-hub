#!/usr/bin/env python3
"""Build and verify one Hub public projection without partial publication."""

from __future__ import annotations

import ctypes
import errno
import argparse
import base64
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_AUTHORITY_BYTES = 32 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 16 * 1024
READ_CHUNK_BYTES = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
AUTHORITY_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]+$", re.IGNORECASE)
SNAPSHOT_ID_RE = re.compile(r"^public-projection-[0-9a-f]{64}$")
SNAPSHOT_CONTRACT = "chummer.public_projection_snapshot/v1"
CURRENT_CONTRACT = "chummer.public_projection_current/v1"
PROJECTION_STATUS_PASS = "pass"
PROJECTION_STATUS_REVIEW_REQUIRED = "review_required"
PROJECTION_STATUS_CANDIDATE_IMPORT_READY = "candidate_import_ready"
PROJECTION_STAGE_RELEASE_UPLOAD_READY = "release_upload_ready"
PROJECTION_STAGE_CODE_DEPLOY_REVIEW_REQUIRED = "code_deploy_review_required"
PROJECTION_STAGE_CANDIDATE_IMPORT_READY = "candidate_import_ready"
PROJECTION_PURPOSE_RELEASE_UPLOAD = "release-upload"
PROJECTION_PURPOSE_CODE_DEPLOY = "code-deploy"
PROJECTION_PURPOSE_CANDIDATE_IMPORT = "candidate-import"
SNAPSHOT_MANIFEST_NAME = "PUBLIC_PROJECTION_SNAPSHOT.generated.json"
CURRENT_POINTER_NAME = "CURRENT.json"
PUBLICATION_LOCK_NAME = ".PUBLIC_PROJECTION.lock"
SNAPSHOT_OUTPUT_NAMES = (
    "HUB_LOCAL_RELEASE_PROOF.generated.json",
    "HUB_SERVED_RELEASE_PROOF.generated.json",
    "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
    "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
    "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
    "RELEASE_CHANNEL.generated.json",
    "FLAGSHIP_PRODUCT_READINESS.generated.json",
)
CANDIDATE_IMPORT_AUTHORITY_NAME = "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
CANDIDATE_SNAPSHOT_OUTPUT_NAMES = (*SNAPSHOT_OUTPUT_NAMES, CANDIDATE_IMPORT_AUTHORITY_NAME)
CANDIDATE_CAPTURE_FILE = "WINDOWS_NATIVE_CAPTURE.generated.json"
CANDIDATE_CAPTURE_INVENTORY_FILE = "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
CANDIDATE_FINALIZATION_FILE = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
CANDIDATE_FINALIZED_INVENTORY_FILE = "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"
CANDIDATE_PROVENANCE_INVENTORY_FILE = (
    "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"
)
CANDIDATE_PROVENANCE_EXPORT_FILE = (
    "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
)
CANDIDATE_UPLOAD_CONTENT_INVENTORY_FILE = (
    "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"
)
CANDIDATE_UPLOAD_EXPORT_FILE = "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
CANDIDATE_PROMOTED_HEADS = ("avalonia",)
CANDIDATE_CAPTURE_WORKFLOW = ".github/workflows/windows-native-evidence-capture.yml"
CANDIDATE_FINALIZE_WORKFLOW = ".github/workflows/windows-native-evidence-finalize.yml"
CANDIDATE_PRODUCER_WORKFLOW = ".github/workflows/preview-nightly-candidate-export.yml"
CANDIDATE_UI_REPOSITORY = "ArchonMegalon/chummer6-ui"
CANDIDATE_UI_REF = "refs/heads/main"
CANDIDATE_RID = "win-x64"
CANDIDATE_EXACT_SCOPE = "avalonia:windows:win-x64"
CANDIDATE_AUTHORITY_CONTRACT_V2 = "chummer.release-upload.candidate-import-authority/v2"
CANDIDATE_AUTHORITY_CONTRACT_V3 = "chummer.release-upload.candidate-import-authority/v3"
CANDIDATE_PUBLICATION_SCOPE_FILE = "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json"
CANDIDATE_UNSIGNED_SCOPE_FILE = "PREVIEW_NIGHTLY_UNSIGNED_SCOPE.proposed.json"
CANDIDATE_UNSIGNED_COMPOSITION_FILE = (
    "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json"
)
CANDIDATE_REGISTRY_RECEIPT_FILE = "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json"
CANDIDATE_REGISTRY_AUTHORITY_FILE = "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json"
CANDIDATE_REGISTRY_FINALIZE_FILE = "PREVIEW_PUBLICATION_DELTA_FINALIZE.json"
CANDIDATE_AUTHENTICODE_PATH = (
    "proof/windows-native/authenticode/"
    "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"
)
CANDIDATE_HEAD_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CANDIDATE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CANDIDATE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,38})$")
CANDIDATE_GITHUB_LOGIN_RE = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?|github-actions\[bot\])$"
)
CANDIDATE_POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$")
CANDIDATE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$")
CANDIDATE_GITHUB_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
CANDIDATE_EXPORT_RUNNER_LABEL_RE = re.compile(
    r"^chummer-preview-nightly-export-[a-z0-9]{12,64}$"
)
CANDIDATE_PROOF_MAX_AGE = timedelta(hours=24)


class ProjectionBlocked(RuntimeError):
    pass


class ProjectionCommitReconcileRequired(RuntimeError):
    """CURRENT changed, but its directory durability could not be confirmed."""

    def __init__(self, snapshot: "ProjectionSnapshot", reason: str) -> None:
        super().__init__(reason)
        self.snapshot = snapshot
        self.reason = reason


@dataclass(frozen=True)
class ProjectionSnapshot:
    current_pointer: Path
    snapshot_directory: Path
    snapshot_id: str
    snapshot_sha256: str
    outputs: Mapping[str, Path]
    output_sha256: Mapping[str, str]
    manifest_sha256: str = ""
    status: str = PROJECTION_STATUS_PASS
    projection_stage: str = PROJECTION_STAGE_RELEASE_UPLOAD_READY
    code_deployment_authority: bool = True
    release_upload_authority: bool = True
    candidate_import_authority: bool = False
    release_gate_findings: tuple[Mapping[str, str], ...] = ()


def _required(environment: Mapping[str, str], name: str) -> str:
    value = str(environment.get(name) or "").strip()
    if not value:
        raise ProjectionBlocked(f"public projection requires {name}")
    return value


def _expected_sha256(environment: Mapping[str, str], name: str) -> str:
    value = _required(environment, name).lower()
    if SHA256_RE.fullmatch(value) is None:
        raise ProjectionBlocked(f"{name} must be a 64-character SHA256")
    return value


def _authority_reference(environment: Mapping[str, str], name: str) -> str:
    value = _required(environment, name)
    if AUTHORITY_RE.fullmatch(value) is None or value.lower().startswith("file://"):
        raise ProjectionBlocked(f"{name} must be a non-file immutable authority reference")
    return value


def _stable_read(path: Path, *, label: str, maximum_bytes: int = MAX_AUTHORITY_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProjectionBlocked(f"{label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ProjectionBlocked(f"{label} must be a single-link regular file")
        if before.st_size < 1 or before.st_size > maximum_bytes:
            raise ProjectionBlocked(f"{label} has an invalid size")
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        try:
            path_metadata = path.lstat()
        except OSError as exc:
            raise ProjectionBlocked(f"{label} changed during stable read") from exc
    finally:
        os.close(descriptor)

    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_mode,
        before.st_nlink,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_mode,
        after.st_nlink,
    )
    if before_identity != after_identity or (
        path_metadata.st_dev,
        path_metadata.st_ino,
    ) != (after.st_dev, after.st_ino):
        raise ProjectionBlocked(f"{label} changed during stable read")
    payload = b"".join(chunks)
    if len(payload) != before.st_size:
        raise ProjectionBlocked(f"{label} changed during stable read")
    return payload


def _stage_authority(
    *,
    source: Path,
    destination: Path,
    expected_sha256: str,
    label: str,
) -> None:
    payload = _stable_read(source, label=label)
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise ProjectionBlocked(f"{label} SHA256 does not match its immutable handoff")
    try:
        destination.write_bytes(payload)
        destination.chmod(0o400)
    except OSError as exc:
        raise ProjectionBlocked(f"could not stage {label}") from exc


def _portable_path(path: Path) -> str:
    try:
        return f"repo://ArchonMegalon/chummer6-hub/{path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()}"
    except (OSError, ValueError):
        return "<local-path>"


def sanitize_diagnostic(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        text = raw[:MAX_DIAGNOSTIC_BYTES].decode("utf-8", errors="replace")
    else:
        text = raw[:MAX_DIAGNOSTIC_BYTES]
    text = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|ticket|api[_-]?key|secret|password)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]{8,})?\b",
        "<redacted-token>",
        text,
    )
    text = re.sub(
        r"(?<![A-Za-z0-9:])(?:/Users/|/home/|/root/|/tmp/|/private/|/var/tmp/|/docker/|/workspace/)[^\s\"']*",
        "<local-path>",
        text,
    )
    text = re.sub(
        r"(?i)\b[A-Z]:[\\/](?:Users|Temp|workspace)[\\/][^\s\"']*",
        "<local-path>",
        text,
    )
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-40:])[:MAX_DIAGNOSTIC_BYTES]


def _run_gate(
    name: str,
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    timeout_seconds: int = 1800,
) -> None:
    try:
        completed = subprocess.run(
            list(command),
            cwd=REPO_ROOT,
            env=dict(environment),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        diagnostic = sanitize_diagnostic((exc.stderr or b"") + (exc.stdout or b""))
        suffix = f": {diagnostic}" if diagnostic else ""
        raise ProjectionBlocked(f"{name} timed out{suffix}") from exc
    except OSError as exc:
        raise ProjectionBlocked(f"{name} could not start") from exc
    if completed.returncode != 0:
        diagnostic = sanitize_diagnostic(completed.stderr or completed.stdout)
        suffix = f": {diagnostic}" if diagnostic else ""
        raise ProjectionBlocked(
            f"{name} failed with exit code {completed.returncode}{suffix}"
        )


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _projection_authority(status: str) -> tuple[str, bool, bool, bool]:
    if status == PROJECTION_STATUS_PASS:
        return PROJECTION_STAGE_RELEASE_UPLOAD_READY, True, True, False
    if status == PROJECTION_STATUS_REVIEW_REQUIRED:
        return PROJECTION_STAGE_CODE_DEPLOY_REVIEW_REQUIRED, True, False, False
    if status == PROJECTION_STATUS_CANDIDATE_IMPORT_READY:
        return PROJECTION_STAGE_CANDIDATE_IMPORT_READY, False, False, True
    raise ProjectionBlocked("public projection status is invalid")


def _projection_output_names(status: str) -> tuple[str, ...]:
    return (
        CANDIDATE_SNAPSHOT_OUTPUT_NAMES
        if status == PROJECTION_STATUS_CANDIDATE_IMPORT_READY
        else SNAPSHOT_OUTPUT_NAMES
    )


def _validate_projection_authority(
    payload: Mapping[str, object],
    *,
    status: str,
    label: str,
) -> tuple[str, bool, bool, bool]:
    (
        stage,
        code_deployment_authority,
        release_upload_authority,
        candidate_import_authority,
    ) = (
        _projection_authority(status)
    )
    if (
        payload.get("projectionStage") != stage
        or payload.get("codeDeploymentAuthority") is not code_deployment_authority
        or payload.get("releaseUploadAuthority") is not release_upload_authority
        or payload.get("candidateImportAuthority") is not candidate_import_authority
    ):
        raise ProjectionBlocked(f"{label} authority posture drifted")
    return (
        stage,
        code_deployment_authority,
        release_upload_authority,
        candidate_import_authority,
    )


def _review_gate_finding(
    name: str,
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
) -> dict[str, str] | None:
    """Run a release-only gate without turning its failure into deploy authority."""

    try:
        _run_gate(name, command, environment=environment)
    except ProjectionBlocked as exc:
        return {
            "gate": name,
            "status": "fail",
            "reason": sanitize_diagnostic(str(exc)),
        }
    return None


def _review_required_windows_receipt(
    release_gate_findings: Sequence[Mapping[str, str]],
) -> bytes:
    findings = [dict(finding) for finding in release_gate_findings]
    findings.append(
        {
            "gate": "live public Windows installer",
            "status": "postdeploy_required",
            "reason": "live Windows installer proof must pass after code deployment",
        }
    )
    return _canonical_json_bytes(
        {
            "contract_name": "chummer.live_public_windows_installer",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": PROJECTION_STATUS_REVIEW_REQUIRED,
            "verdict": "LIVE_PUBLIC_WINDOWS_INSTALLER_POSTDEPLOY_REQUIRED",
            "checked_artifact_count": 0,
            "artifact": None,
            "checked_artifacts": [],
            "failures": [
                f"{finding['gate']}: {finding['reason']}" for finding in findings
            ],
            "release_gate_findings": findings,
            "code_deployment_authority": True,
            "release_upload_authority": False,
        }
    )


def _validate_review_gate_findings(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ProjectionBlocked(
            "staged review-required receipt does not record release blockers"
        )
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"gate", "status", "reason"}:
            raise ProjectionBlocked(
                "staged review-required release gate finding drifted"
            )
        gate = str(item.get("gate") or "").strip()
        status = str(item.get("status") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if (
            not gate
            or gate in seen
            or status not in {"fail", "postdeploy_required"}
            or not reason
        ):
            raise ProjectionBlocked(
                "staged review-required release gate finding is invalid"
            )
        seen.add(gate)
        findings.append({"gate": gate, "status": status, "reason": reason})
    if not any(
        finding == {
            "gate": "live public Windows installer",
            "status": "postdeploy_required",
            "reason": "live Windows installer proof must pass after code deployment",
        }
        for finding in findings
    ):
        raise ProjectionBlocked(
            "staged review-required receipt omits the live Windows blocker"
        )
    return findings


def _candidate_import_gate_findings() -> list[dict[str, str]]:
    return [
        {
            "gate": "live release convergence after candidate import",
            "status": "postdeploy_required",
            "reason": "candidate bytes require live verification before release upload authority can be restored",
        }
    ]


def _validate_candidate_import_gate_findings(value: object) -> list[dict[str, str]]:
    expected = _candidate_import_gate_findings()
    if value != expected:
        raise ProjectionBlocked(
            "candidate-import snapshot must retain the exact live-verification blocker"
        )
    return expected


def _projection_release_gate_findings(
    payload: Mapping[str, object],
    *,
    status: str,
    label: str,
) -> list[dict[str, str]]:
    value = payload.get("releaseGateFindings")
    if status == PROJECTION_STATUS_PASS:
        if value not in (None, []):
            raise ProjectionBlocked(f"{label} unexpectedly records release blockers")
        return []
    if status == PROJECTION_STATUS_REVIEW_REQUIRED:
        return _validate_review_gate_findings(value)
    if status == PROJECTION_STATUS_CANDIDATE_IMPORT_READY:
        return _validate_candidate_import_gate_findings(value)
    raise ProjectionBlocked(f"{label} release gate status is invalid")


def _strict_json_object(payload: bytes, *, label: str) -> dict[str, object]:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ProjectionBlocked(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectionBlocked(f"{label} is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise ProjectionBlocked(f"{label} must be a JSON object")
    return value


class _JsonNumber:
    __slots__ = ("raw",)

    def __init__(self, raw: str) -> None:
        self.raw = raw


def _json_semantic_object(payload: bytes, *, label: str) -> dict[str, object]:
    def reject_constant(value: str) -> object:
        raise ValueError(f"non-JSON numeric constant {value!r}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            parse_int=_JsonNumber,
            parse_float=_JsonNumber,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProjectionBlocked(f"{label} is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise ProjectionBlocked(f"{label} must be a JSON object")
    return value


def _json_semantic_equal(left: object, right: object) -> bool:
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and set(left) == set(right)
            and all(
                _json_semantic_equal(left[key], right[key])
                for key in left
            )
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(
                _json_semantic_equal(left_item, right_item)
                for left_item, right_item in zip(left, right)
            )
        )
    if isinstance(left, _JsonNumber) or isinstance(right, _JsonNumber):
        return (
            isinstance(left, _JsonNumber)
            and isinstance(right, _JsonNumber)
            and left.raw == right.raw
        )
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left is right
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    return False


def _require_real_directory(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ProjectionBlocked(f"{label} must be an existing real directory") from exc
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ProjectionBlocked(f"{label} must be an existing real directory")


def _require_safe_publication_root(path: Path) -> None:
    _require_real_directory(path, label="public projection snapshot root")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ProjectionBlocked(
            "public projection snapshot root ownership is unavailable"
        ) from exc
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise ProjectionBlocked(
            "public projection snapshot root must be current-user-owned and not group/world writable"
        )


def _write_fsynced_file(path: Path, payload: bytes, *, mode: int, label: str) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, mode)
    except OSError as exc:
        raise ProjectionBlocked(f"could not create {label}") from exc
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ProjectionBlocked(f"could not write {label}")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
    except OSError as exc:
        raise ProjectionBlocked(f"could not write {label}") from exc
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path, *, label: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProjectionBlocked(f"could not open {label}") from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise ProjectionBlocked(f"could not synchronize {label}") from exc
    finally:
        os.close(descriptor)


def _acquire_publication_lock(snapshot_root: Path) -> int:
    """Acquire one non-blocking, root-scoped publication authority."""

    _require_safe_publication_root(snapshot_root)
    lock_path = snapshot_root / PUBLICATION_LOCK_NAME
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ProjectionBlocked("public projection publication lock is unavailable") from exc
    try:
        descriptor_metadata = os.fstat(descriptor)
        path_metadata = lock_path.lstat()
        if (
            not stat.S_ISREG(descriptor_metadata.st_mode)
            or descriptor_metadata.st_nlink != 1
            or descriptor_metadata.st_uid != os.getuid()
            or stat.S_IMODE(descriptor_metadata.st_mode) != 0o600
            or (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
            != (path_metadata.st_dev, path_metadata.st_ino)
        ):
            raise ProjectionBlocked(
                "public projection publication lock has unsafe file identity"
            )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProjectionBlocked(
                "another public projection publication transaction is active"
            ) from exc
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_uid,
        ) != (
            descriptor_metadata.st_dev,
            descriptor_metadata.st_ino,
            descriptor_metadata.st_mode,
            descriptor_metadata.st_nlink,
            descriptor_metadata.st_uid,
        ):
            raise ProjectionBlocked(
                "public projection publication lock changed during acquisition"
            )
        return descriptor
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _release_publication_lock(descriptor: int) -> None:
    """Best-effort unlock; a durable commit must never become a CLI failure here."""

    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(descriptor)
    except OSError:
        pass


def _exclusive_snapshot_rename(source: Path, destination: Path) -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            rename_exclusive = getattr(libc, "renamex_np")
            rename_exclusive.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
            rename_exclusive.restype = ctypes.c_int
            result = rename_exclusive(
                os.fsencode(source),
                os.fsencode(destination),
                ctypes.c_uint(0x00000004),  # RENAME_EXCL
            )
        elif sys.platform.startswith("linux"):
            rename_exclusive = getattr(libc, "renameat2")
            rename_exclusive.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename_exclusive.restype = ctypes.c_int
            result = rename_exclusive(
                -100,
                os.fsencode(source),
                -100,
                os.fsencode(destination),
                ctypes.c_uint(1),  # RENAME_NOREPLACE
            )
        else:
            raise ProjectionBlocked("exclusive snapshot rename is unsupported on this host")
    except (AttributeError, OSError) as exc:
        raise ProjectionBlocked("exclusive snapshot rename is unavailable") from exc
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
            raise ProjectionBlocked("immutable public projection snapshot already exists")
        raise ProjectionBlocked(
            f"exclusive snapshot rename failed with errno {error_number}"
        )


def _snapshot_digest(
    output_digests: Mapping[str, str],
    output_names: Sequence[str] = SNAPSHOT_OUTPUT_NAMES,
) -> str:
    digest = hashlib.sha256()
    for name in output_names:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(output_digests[name].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _remove_private_stage(path: Path) -> None:
    def restore_private_permissions(
        function,
        raw_path: str,
        _exception_info,
    ) -> None:
        try:
            os.chmod(raw_path, 0o700)
            function(raw_path)
        except OSError as exc:
            raise ProjectionBlocked(
                "could not remove private public projection stage"
            ) from exc

    try:
        shutil.rmtree(path, onerror=restore_private_permissions)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ProjectionBlocked("could not remove private public projection stage") from exc


def _path_from_env(environment: Mapping[str, str], name: str) -> Path:
    raw = _required(environment, name)
    try:
        path = Path(raw).expanduser()
    except (OSError, RuntimeError) as exc:
        raise ProjectionBlocked(f"{name} path could not be resolved") from exc
    return path if path.is_absolute() else REPO_ROOT / path


def _snapshot_root(environment: Mapping[str, str]) -> Path:
    explicit = str(environment.get("CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT") or "").strip()
    try:
        if explicit:
            root = Path(explicit).expanduser()
            if not root.is_absolute():
                root = REPO_ROOT / root
        else:
            legacy_output = str(
                environment.get("CHUMMER_HUB_LOCAL_RELEASE_PROOF_OUTPUT")
                or ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            ).strip()
            legacy_path = Path(legacy_output).expanduser()
            if not legacy_path.is_absolute():
                legacy_path = REPO_ROOT / legacy_path
            root = legacy_path.parent
    except (OSError, RuntimeError) as exc:
        raise ProjectionBlocked("public projection snapshot root could not be resolved") from exc
    _require_safe_publication_root(root)
    return root


def _validate_current_pointer_target(pointer_path: Path) -> None:
    try:
        metadata = pointer_path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ProjectionBlocked("could not inspect current public projection pointer") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ProjectionBlocked("current public projection pointer has unsafe file identity")


def _commit_current_pointer(
    *,
    pointer_stage: Path,
    current_pointer: Path,
    snapshot_root: Path,
    result: ProjectionSnapshot,
) -> None:
    """Commit CURRENT and distinguish an uncertain durable commit from no commit."""

    try:
        os.replace(pointer_stage, current_pointer)
    except OSError as exc:
        try:
            pointer_stage.unlink()
        except OSError:
            pass
        try:
            _remove_private_stage(result.snapshot_directory)
        except ProjectionBlocked:
            pass
        raise ProjectionBlocked("atomic CURRENT pointer commit failed") from exc

    try:
        _fsync_directory(
            snapshot_root,
            label="public projection CURRENT commit root",
        )
    except ProjectionBlocked as exc:
        # os.replace already changed the public authority. Do not collapse this
        # state into the generic pre-commit failure path: the caller must report
        # the exact snapshot that now requires durability reconciliation.
        raise ProjectionCommitReconcileRequired(result, str(exc)) from exc


def _prepare_pointer_file(snapshot_root: Path, payload: bytes) -> Path:
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".CURRENT.",
            suffix=".tmp",
            dir=snapshot_root,
        )
    except OSError as exc:
        raise ProjectionBlocked("could not create current public projection pointer stage") from exc
    temporary_path = Path(temporary_name)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ProjectionBlocked("could not write current public projection pointer stage")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o644)
        os.close(descriptor)
        descriptor = -1
        return temporary_path
    except (OSError, ProjectionBlocked) as exc:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary_path.unlink()
        except OSError:
            pass
        if isinstance(exc, ProjectionBlocked):
            raise
        raise ProjectionBlocked("could not prepare current public projection pointer") from exc


def _validate_staged_outputs(
    output_paths: Mapping[str, Path],
    *,
    projection_status: str,
) -> tuple[dict[str, bytes], dict[str, str]]:
    payloads: dict[str, bytes] = {}
    digests: dict[str, str] = {}
    for name in SNAPSHOT_OUTPUT_NAMES:
        payload = _stable_read(output_paths[name], label=f"staged {name}")
        payloads[name] = payload
        digests[name] = hashlib.sha256(payload).hexdigest()

    if payloads[SNAPSHOT_OUTPUT_NAMES[0]] != payloads[SNAPSHOT_OUTPUT_NAMES[1]]:
        raise ProjectionBlocked("staged local and served Hub proofs disagree")

    local_payload = _strict_json_object(
        payloads["HUB_LOCAL_RELEASE_PROOF.generated.json"],
        label="staged Hub local release proof",
    )
    expected_authorities = {
        "release_channel",
        "flagship_readiness",
        "fleet_queue",
        "design_queue",
        "design_successor_registry",
    }
    authority_inputs = local_payload.get("authority_inputs")
    if not isinstance(authority_inputs, dict) or set(authority_inputs) != expected_authorities:
        raise ProjectionBlocked("staged Hub proof does not bind all five authority inputs")
    release_channel_authority = authority_inputs.get("release_channel")
    if (
        not isinstance(release_channel_authority, dict)
        or release_channel_authority.get("sha256")
        != digests["RELEASE_CHANNEL.generated.json"]
    ):
        raise ProjectionBlocked(
            "staged release channel does not match the Hub proof authority input"
        )
    readiness_authority = authority_inputs.get("flagship_readiness")
    if (
        not isinstance(readiness_authority, dict)
        or readiness_authority.get("sha256")
        != digests["FLAGSHIP_PRODUCT_READINESS.generated.json"]
    ):
        raise ProjectionBlocked(
            "staged flagship readiness does not match the Hub proof authority input"
        )

    m125_payload = _strict_json_object(
        payloads["NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json"],
        label="staged M125 proof",
    )
    m126_payload = _strict_json_object(
        payloads["NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json"],
        label="staged M126 proof",
    )
    windows_payload = _strict_json_object(
        payloads["LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json"],
        label="staged live Windows receipt",
    )
    if (
        not isinstance(m125_payload.get("package_proof"), dict)
        or m125_payload["package_proof"].get("package_id")
        != "next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign"
    ):
        raise ProjectionBlocked("staged M125 proof contract drifted")
    if (
        not isinstance(m126_payload.get("package_proof"), dict)
        or m126_payload["package_proof"].get("package_id")
        != "next90-m126-hub-define-hosted-proof-contracts-for-open-runs-shadowcaster"
    ):
        raise ProjectionBlocked("staged M126 proof contract drifted")
    if projection_status == PROJECTION_STATUS_PASS:
        if windows_payload.get("status") != PROJECTION_STATUS_PASS:
            raise ProjectionBlocked("staged live Windows receipt is not passing")
    elif projection_status == PROJECTION_STATUS_REVIEW_REQUIRED:
        if (
            windows_payload.get("contract_name")
            != "chummer.live_public_windows_installer"
            or windows_payload.get("status") != PROJECTION_STATUS_REVIEW_REQUIRED
            or windows_payload.get("verdict")
            != "LIVE_PUBLIC_WINDOWS_INSTALLER_POSTDEPLOY_REQUIRED"
            or windows_payload.get("checked_artifact_count") != 0
            or windows_payload.get("checked_artifacts") != []
            or windows_payload.get("code_deployment_authority") is not True
            or windows_payload.get("release_upload_authority") is not False
        ):
            raise ProjectionBlocked(
                "staged review-required Windows receipt authority drifted"
            )
        findings = _validate_review_gate_findings(
            windows_payload.get("release_gate_findings")
        )
        expected_failures = [
            f"{finding['gate']}: {finding['reason']}" for finding in findings
        ]
        if windows_payload.get("failures") != expected_failures:
            raise ProjectionBlocked(
                "staged review-required release gate failure summary drifted"
            )
    else:
        raise ProjectionBlocked("staged public projection status is invalid")
    return payloads, digests


def resolve_snapshot_generation(
    snapshot_root: Path,
    *,
    snapshot_id: str,
    snapshot_sha256: str,
    manifest_sha256: str,
    purpose: str = PROJECTION_PURPOSE_RELEASE_UPLOAD,
) -> ProjectionSnapshot:
    """Authenticate one immutable generation without consulting CURRENT."""

    if purpose not in {
        PROJECTION_PURPOSE_RELEASE_UPLOAD,
        PROJECTION_PURPOSE_CODE_DEPLOY,
        PROJECTION_PURPOSE_CANDIDATE_IMPORT,
    }:
        raise ProjectionBlocked("public projection resolution purpose is invalid")
    if (
        SNAPSHOT_ID_RE.fullmatch(snapshot_id) is None
        or SHA256_RE.fullmatch(snapshot_sha256) is None
        or SHA256_RE.fullmatch(manifest_sha256) is None
        or snapshot_id != f"public-projection-{snapshot_sha256}"
    ):
        raise ProjectionBlocked("public projection generation identity is invalid")

    _require_real_directory(snapshot_root, label="public projection snapshot root")
    snapshot_directory = snapshot_root / snapshot_id
    _require_real_directory(snapshot_directory, label="public projection snapshot")
    manifest_bytes = _stable_read(
        snapshot_directory / SNAPSHOT_MANIFEST_NAME,
        label="public projection snapshot manifest",
    )
    if not hmac.compare_digest(
        hashlib.sha256(manifest_bytes).hexdigest(),
        manifest_sha256,
    ):
        raise ProjectionBlocked("public projection snapshot manifest digest drifted")
    manifest = _strict_json_object(
        manifest_bytes,
        label="public projection snapshot manifest",
    )
    status = str(manifest.get("status") or "")
    if (
        manifest.get("contractName") != SNAPSHOT_CONTRACT
        or manifest.get("snapshotId") != snapshot_id
        or manifest.get("snapshotSha256") != snapshot_sha256
    ):
        raise ProjectionBlocked("public projection snapshot manifest binding drifted")
    (
        projection_stage,
        code_deployment_authority,
        release_upload_authority,
        candidate_import_authority,
    ) = _validate_projection_authority(
        manifest,
        status=status,
        label="public projection snapshot manifest",
    )
    release_gate_findings = _projection_release_gate_findings(
        manifest,
        status=status,
        label="public projection snapshot manifest",
    )
    if purpose == PROJECTION_PURPOSE_RELEASE_UPLOAD and not release_upload_authority:
        raise ProjectionBlocked(
            "public projection generation is not authorized for release upload"
        )
    if purpose == PROJECTION_PURPOSE_CODE_DEPLOY and not code_deployment_authority:
        raise ProjectionBlocked(
            "public projection generation is not authorized for code deployment"
        )
    if purpose == PROJECTION_PURPOSE_CANDIDATE_IMPORT and not candidate_import_authority:
        raise ProjectionBlocked(
            "public projection generation is not authorized for candidate import"
        )
    output_names = _projection_output_names(status)
    manifest_outputs = manifest.get("outputs")
    if (
        not isinstance(manifest_outputs, dict)
        or set(manifest_outputs) != set(output_names)
    ):
        raise ProjectionBlocked("public projection snapshot output inventory drifted")

    outputs: dict[str, Path] = {}
    output_digests: dict[str, str] = {}
    output_payloads: dict[str, bytes] = {}
    for name in output_names:
        entry = manifest_outputs.get(name)
        if not isinstance(entry, dict) or entry.get("relativePath") != name:
            raise ProjectionBlocked("public projection snapshot output path drifted")
        expected_digest = str(entry.get("sha256") or "").lower()
        if SHA256_RE.fullmatch(expected_digest) is None:
            raise ProjectionBlocked("public projection snapshot output digest is invalid")
        output_path = snapshot_directory / name
        output_payload = _stable_read(output_path, label=f"public projection {name}")
        if not hmac.compare_digest(
            hashlib.sha256(output_payload).hexdigest(),
            expected_digest,
        ):
            raise ProjectionBlocked("public projection snapshot output digest drifted")
        if entry.get("sizeBytes") != len(output_payload):
            raise ProjectionBlocked("public projection snapshot output size drifted")
        outputs[name] = output_path
        output_digests[name] = expected_digest
        output_payloads[name] = output_payload
    if not hmac.compare_digest(
        _snapshot_digest(output_digests, output_names), snapshot_sha256
    ):
        raise ProjectionBlocked("public projection snapshot aggregate digest drifted")
    if output_payloads[SNAPSHOT_OUTPUT_NAMES[0]] != output_payloads[SNAPSHOT_OUTPUT_NAMES[1]]:
        raise ProjectionBlocked("public local and served Hub proofs disagree")
    return ProjectionSnapshot(
        current_pointer=snapshot_root / CURRENT_POINTER_NAME,
        snapshot_directory=snapshot_directory,
        snapshot_id=snapshot_id,
        snapshot_sha256=snapshot_sha256,
        outputs=outputs,
        output_sha256=output_digests,
        manifest_sha256=manifest_sha256,
        status=status,
        projection_stage=projection_stage,
        code_deployment_authority=code_deployment_authority,
        release_upload_authority=release_upload_authority,
        candidate_import_authority=candidate_import_authority,
        release_gate_findings=tuple(release_gate_findings),
    )


def resolve_current_snapshot(
    snapshot_root: Path,
    *,
    purpose: str = PROJECTION_PURPOSE_RELEASE_UPLOAD,
) -> ProjectionSnapshot:
    """Resolve and authenticate every output through the one atomic CURRENT pointer."""

    if purpose not in {
        PROJECTION_PURPOSE_RELEASE_UPLOAD,
        PROJECTION_PURPOSE_CODE_DEPLOY,
        PROJECTION_PURPOSE_CANDIDATE_IMPORT,
    }:
        raise ProjectionBlocked("public projection resolution purpose is invalid")

    _require_real_directory(snapshot_root, label="public projection snapshot root")
    current_pointer = snapshot_root / CURRENT_POINTER_NAME
    current_bytes = _stable_read(
        current_pointer,
        label="current public projection pointer",
    )
    current_payload = _strict_json_object(
        current_bytes,
        label="current public projection pointer",
    )
    if current_payload.get("contractName") != CURRENT_CONTRACT:
        raise ProjectionBlocked("current public projection pointer contract drifted")
    status = str(current_payload.get("status") or "")
    (
        projection_stage,
        code_deployment_authority,
        release_upload_authority,
        candidate_import_authority,
    ) = _validate_projection_authority(
        current_payload,
        status=status,
        label="current public projection pointer",
    )
    release_gate_findings = _projection_release_gate_findings(
        current_payload,
        status=status,
        label="current public projection pointer",
    )
    if purpose == PROJECTION_PURPOSE_RELEASE_UPLOAD and not release_upload_authority:
        raise ProjectionBlocked(
            "current public projection is not authorized for release upload"
        )
    if purpose == PROJECTION_PURPOSE_CODE_DEPLOY and not code_deployment_authority:
        raise ProjectionBlocked(
            "current public projection is not authorized for code deployment"
        )
    if purpose == PROJECTION_PURPOSE_CANDIDATE_IMPORT and not candidate_import_authority:
        raise ProjectionBlocked(
            "current public projection is not authorized for candidate import"
        )
    snapshot_id = str(current_payload.get("snapshotId") or "")
    snapshot_sha256 = str(current_payload.get("snapshotSha256") or "").lower()
    manifest_sha256 = str(current_payload.get("manifestSha256") or "").lower()
    if SNAPSHOT_ID_RE.fullmatch(snapshot_id) is None:
        raise ProjectionBlocked("current public projection pointer snapshot id is invalid")
    if snapshot_id != f"public-projection-{snapshot_sha256}" or SHA256_RE.fullmatch(manifest_sha256) is None:
        raise ProjectionBlocked("current public projection pointer digest binding is invalid")
    output_names = _projection_output_names(status)
    expected_pointer_outputs = {name: f"{snapshot_id}/{name}" for name in output_names}
    if (
        current_payload.get("manifestRelativePath")
        != f"{snapshot_id}/{SNAPSHOT_MANIFEST_NAME}"
        or current_payload.get("outputs") != expected_pointer_outputs
    ):
        raise ProjectionBlocked("current public projection pointer output inventory drifted")

    snapshot = resolve_snapshot_generation(
        snapshot_root,
        snapshot_id=snapshot_id,
        snapshot_sha256=snapshot_sha256,
        manifest_sha256=manifest_sha256,
        purpose=purpose,
    )
    if (
        snapshot.status != status
        or snapshot.projection_stage != projection_stage
        or snapshot.code_deployment_authority is not code_deployment_authority
        or snapshot.release_upload_authority is not release_upload_authority
        or snapshot.candidate_import_authority is not candidate_import_authority
        or snapshot.release_gate_findings != tuple(release_gate_findings)
    ):
        raise ProjectionBlocked(
            "current public projection pointer and snapshot posture drifted"
        )
    final_current_bytes = _stable_read(
        current_pointer,
        label="current public projection pointer",
    )
    if not hmac.compare_digest(current_bytes, final_current_bytes):
        raise ProjectionBlocked("current public projection pointer changed during authentication")
    return snapshot


def _candidate_embedded_bytes(
    value: object,
    *,
    label: str,
    expected_path: str,
) -> bytes:
    if not isinstance(value, dict) or set(value) != {
        "path",
        "sha256",
        "sizeBytes",
        "base64",
    }:
        raise ProjectionBlocked(f"{label} custody binding drifted")
    if value.get("path") != expected_path:
        raise ProjectionBlocked(f"{label} custody path drifted")
    digest = str(value.get("sha256") or "")
    size = value.get("sizeBytes")
    encoded = value.get("base64")
    if (
        SHA256_RE.fullmatch(digest) is None
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 1
        or not isinstance(encoded, str)
    ):
        raise ProjectionBlocked(f"{label} custody binding is invalid")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ProjectionBlocked(f"{label} custody bytes are invalid") from exc
    if len(payload) != size or not hmac.compare_digest(
        hashlib.sha256(payload).hexdigest(), digest
    ):
        raise ProjectionBlocked(f"{label} custody bytes drifted")
    return payload


def _candidate_timestamp(
    value: object,
    *,
    label: str,
    now: datetime,
    require_fresh: bool = True,
) -> datetime:
    if not isinstance(value, str) or not value:
        raise ProjectionBlocked(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProjectionBlocked(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ProjectionBlocked(f"{label} must be UTC")
    parsed = parsed.astimezone(timezone.utc)
    if require_fresh and (
        parsed > now + timedelta(minutes=5) or now - parsed > CANDIDATE_PROOF_MAX_AGE
    ):
        raise ProjectionBlocked(f"{label} is stale or future-dated")
    return parsed


def _candidate_source(value: object, *, label: str, workflow: str) -> dict[str, object]:
    required = {
        "repository",
        "workflow",
        "runId",
        "runAttempt",
        "ref",
        "sha",
        "actor",
        "artifactName",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ProjectionBlocked(f"{label} property set drifted")
    run_id = value.get("runId")
    run_attempt = value.get("runAttempt")
    actor = value.get("actor")
    artifact_name = value.get("artifactName")
    actor_pattern = (
        CANDIDATE_GITHUB_LOGIN_RE
        if workflow == CANDIDATE_CAPTURE_WORKFLOW
        else CANDIDATE_REVIEWER_RE
    )
    if (
        value.get("repository") != CANDIDATE_UI_REPOSITORY
        or value.get("workflow") != workflow
        or value.get("ref") != CANDIDATE_UI_REF
        or CANDIDATE_COMMIT_RE.fullmatch(str(value.get("sha") or "")) is None
        or not isinstance(run_id, str)
        or CANDIDATE_POSITIVE_INTEGER_RE.fullmatch(run_id) is None
        or int(run_id) > 9_007_199_254_740_991
        or not isinstance(run_attempt, str)
        or CANDIDATE_POSITIVE_INTEGER_RE.fullmatch(run_attempt) is None
        or int(run_attempt) > 9_007_199_254_740_991
        or not isinstance(actor, str)
        or actor_pattern.fullmatch(actor) is None
        or not isinstance(artifact_name, str)
        or not artifact_name.strip()
    ):
        raise ProjectionBlocked(f"{label} provenance drifted")
    expected_artifact_name = (
        f"windows-native-evidence-{run_id}-{run_attempt}"
        if workflow == CANDIDATE_CAPTURE_WORKFLOW
        else f"windows-native-evidence-finalized-{run_id}-{run_attempt}"
    )
    if artifact_name != expected_artifact_name:
        raise ProjectionBlocked(f"{label} artifact identity drifted")
    return value


def _candidate_relative_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ProjectionBlocked(f"{label} is invalid")
    parts = value.split("/")
    if any(not part or part in {".", ".."} or ":" in part for part in parts):
        raise ProjectionBlocked(f"{label} is invalid")
    return value


def _candidate_inventory_rows(
    value: object,
    *,
    label: str,
    allow_empty: bool = False,
) -> list[dict[str, object]]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ProjectionBlocked(f"{label} is invalid")
    rows: list[dict[str, object]] = []
    previous = ""
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {"path", "sha256", "sizeBytes"}:
            raise ProjectionBlocked(f"{label} row drifted")
        path = _candidate_relative_path(raw.get("path"), label=f"{label} path")
        digest = raw.get("sha256")
        size = raw.get("sizeBytes")
        if (
            path <= previous
            or SHA256_RE.fullmatch(str(digest or "")) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ProjectionBlocked(f"{label} row is invalid")
        rows.append({"path": path, "sha256": digest, "sizeBytes": size})
        previous = path
    return rows


def _candidate_manifest_alias(
    manifest: dict[str, object], first: str, second: str, *, label: str
) -> str:
    if first in manifest and not isinstance(manifest[first], str):
        raise ProjectionBlocked(f"{label} alias type drifted")
    if second in manifest and not isinstance(manifest[second], str):
        raise ProjectionBlocked(f"{label} alias type drifted")
    first_value = manifest.get(first)
    second_value = manifest.get(second)
    if first_value is not None and second_value is not None and first_value != second_value:
        raise ProjectionBlocked(f"{label} aliases disagree")
    selected = first_value if first_value is not None else second_value
    if not isinstance(selected, str) or not selected:
        raise ProjectionBlocked(f"{label} is missing")
    return selected


def _candidate_version(value: object, *, label: str) -> str:
    if not isinstance(value, str) or CANDIDATE_VERSION_RE.fullmatch(value) is None:
        raise ProjectionBlocked(f"{label} is invalid")
    return value


def _candidate_windows_scope(
    canonical: dict[str, object],
    candidate_rows: list[dict[str, object]],
    candidate: dict[str, object],
    *,
    allow_ancillary_files: bool = False,
    expected_channel: str | None = None,
) -> dict[str, object]:
    version = _candidate_version(
        _candidate_manifest_alias(
            canonical, "version", "releaseVersion", label="candidate release version"
        ),
        label="candidate release version",
    )
    channel = _candidate_manifest_alias(
        canonical, "channelId", "channel", label="candidate release channel"
    )
    if version != candidate["version"]:
        raise ProjectionBlocked("candidate release version differs from its authority identity")
    if expected_channel is not None and channel != expected_channel:
        raise ProjectionBlocked("candidate release channel differs from its authority identity")
    coverage = canonical.get("desktopTupleCoverage")
    heads_value = coverage.get("requiredDesktopHeads") if isinstance(coverage, dict) else None
    if heads_value != list(CANDIDATE_PROMOTED_HEADS) or any(
        not isinstance(head, str) or CANDIDATE_HEAD_RE.fullmatch(head) is None
        for head in heads_value or []
    ):
        raise ProjectionBlocked(
            "candidate requiredDesktopHeads differs from the promoted Avalonia head"
        )
    heads = tuple(heads_value)
    artifacts_value = canonical.get("artifacts")
    if not isinstance(artifacts_value, list) or not artifacts_value:
        raise ProjectionBlocked("candidate release manifest has no artifacts")
    windows_artifacts: list[dict[str, object]] = []
    candidate_by_path = {str(row["path"]): row for row in candidate_rows}
    expected_file_paths: set[str] = set()
    for artifact in artifacts_value:
        if not isinstance(artifact, dict):
            raise ProjectionBlocked("candidate release manifest contains a non-object artifact")
        if artifact.get("head") not in heads:
            raise ProjectionBlocked(
                "candidate release manifest contains a desktop artifact outside "
                "requiredDesktopHeads"
            )
        platform = artifact.get("platform")
        rid = artifact.get("rid")
        if (
            artifact.get("kind") != "installer"
            or platform not in {"linux", "macos", "windows"}
            or platform == "windows"
            and rid != CANDIDATE_RID
            or platform == "linux"
            and rid != "linux-x64"
            or platform == "macos"
            and rid not in {"osx-arm64", "osx-x64"}
        ):
            raise ProjectionBlocked(
                "candidate release manifest contains an artifact outside the exact "
                "finalized desktop shelf scope"
            )
        file_name = artifact.get("fileName")
        digest = artifact.get("sha256")
        size = artifact.get("sizeBytes")
        path = f"files/{file_name}"
        if (
            not isinstance(file_name, str)
            or not file_name
            or "/" in file_name
            or "\\" in file_name
            or SHA256_RE.fullmatch(str(digest or "")) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 1
            or path in expected_file_paths
            or candidate_by_path.get(path)
            != {"path": path, "sha256": digest, "sizeBytes": size}
        ):
            raise ProjectionBlocked("candidate desktop artifact differs from upload inventory")
        expected_file_paths.add(path)
        if platform == "windows":
            windows_artifacts.append(artifact)
    artifacts: dict[str, dict[str, dict[str, object]]] = {}
    for head in heads:
        matching = [artifact for artifact in windows_artifacts if artifact.get("head") == head]
        if len(matching) != 1:
            raise ProjectionBlocked(
                f"candidate manifest must name one Windows installer row for {head}"
            )
        installer_row = matching[0]
        if (
            installer_row.get("installerMode") != "bootstrap"
            or installer_row.get("payloadAcquisitionMode") != "download"
        ):
            raise ProjectionBlocked(f"candidate {head} installer delivery mode is invalid")
        artifacts[head] = {}
        for role, file_key, digest_key, size_key in (
            ("installer", "fileName", "sha256", "sizeBytes"),
            ("payload", "payloadFileName", "payloadSha256", "payloadSizeBytes"),
        ):
            file_name = installer_row.get(file_key)
            digest = installer_row.get(digest_key)
            size = installer_row.get(size_key)
            if (
                not isinstance(file_name, str)
                or not file_name
                or "/" in file_name
                or "\\" in file_name
                or SHA256_RE.fullmatch(str(digest or "")) is None
                or isinstance(size, bool)
                or not isinstance(size, int)
                or size < 1
                or role == "installer"
                and not file_name.lower().endswith(".exe")
            ):
                raise ProjectionBlocked(f"candidate {head} {role} metadata is invalid")
            path = f"files/{file_name}"
            expected_row = {"path": path, "sha256": digest, "sizeBytes": size}
            if candidate_by_path.get(path) != expected_row:
                raise ProjectionBlocked(
                    f"candidate {head} {role} manifest bytes differ from upload inventory"
                )
            artifacts[head][role] = {
                **expected_row,
                "fileName": file_name,
            }
    expected_file_paths.update(
        str(artifacts[head][role]["path"])
        for head in heads
        for role in ("installer", "payload")
    )
    expected_candidate_paths = {
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        *expected_file_paths,
    }
    actual_candidate_paths = {str(row["path"]) for row in candidate_rows}
    if (
        (not allow_ancillary_files and actual_candidate_paths != expected_candidate_paths)
        or (
            allow_ancillary_files
            and not expected_candidate_paths.issubset(actual_candidate_paths)
        )
    ):
        raise ProjectionBlocked(
            "candidate upload inventory differs from the exact finalized desktop shelf"
        )
    return {
        "version": version,
        "channel": channel,
        "heads": heads,
        "artifacts": artifacts,
        "manifestArtifactPaths": sorted(expected_file_paths),
    }


def _candidate_positive_github_integer(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or CANDIDATE_POSITIVE_INTEGER_RE.fullmatch(value) is None
        or int(value) > 9_007_199_254_740_991
    ):
        raise ProjectionBlocked(f"{label} must be an exact positive GitHub integer string")
    return value


def _candidate_github_timestamp(value: object, *, label: str) -> datetime:
    if (
        not isinstance(value, str)
        or CANDIDATE_GITHUB_TIMESTAMP_RE.fullmatch(value) is None
    ):
        raise ProjectionBlocked(f"{label} must be an exact UTC GitHub timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise ProjectionBlocked(f"{label} is invalid") from exc


def _candidate_expected_export_heads(scope: dict[str, object]) -> list[dict[str, object]]:
    artifacts = scope["artifacts"]

    def binding(artifact: dict[str, object]) -> dict[str, object]:
        return {
            "relativePath": artifact["path"],
            "fileName": artifact["fileName"],
            "sha256": artifact["sha256"],
            "sizeBytes": artifact["sizeBytes"],
        }

    return [
        {
            "headId": head,
            "rid": CANDIDATE_RID,
            "installer": binding(artifacts[head]["installer"]),
            "payload": binding(artifacts[head]["payload"]),
        }
        for head in scope["heads"]
    ]


def _validate_candidate_export_artifact_binding(
    value: object,
    *,
    expected: dict[str, object],
    label: str,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "relativePath",
        "fileName",
        "sha256",
        "sizeBytes",
    }:
        raise ProjectionBlocked(f"{label} property set drifted")
    size = value.get("sizeBytes")
    if (
        value.get("relativePath") != expected["relativePath"]
        or value.get("fileName") != expected["fileName"]
        or value.get("sha256") != expected["sha256"]
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size != expected["sizeBytes"]
    ):
        raise ProjectionBlocked(f"{label} drifted")


def _validate_candidate_export_heads(
    value: object,
    *,
    scope: dict[str, object],
    label: str,
) -> None:
    expected_heads = _candidate_expected_export_heads(scope)
    if not isinstance(value, list) or len(value) != len(expected_heads):
        raise ProjectionBlocked(f"{label} scope drifted")
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {
            "headId",
            "rid",
            "installer",
            "payload",
        }:
            raise ProjectionBlocked(f"{label} head property set drifted")
        expected = expected_heads[index]
        if raw.get("headId") != expected["headId"] or raw.get("rid") != expected["rid"]:
            raise ProjectionBlocked(f"{label} scope drifted")
        _validate_candidate_export_artifact_binding(
            raw.get("installer"),
            expected=expected["installer"],
            label=f"{label} installer",
        )
        _validate_candidate_export_artifact_binding(
            raw.get("payload"),
            expected=expected["payload"],
            label=f"{label} payload",
        )


def _validate_candidate_capture_heads(
    value: object,
    *,
    scope: dict[str, object],
    finalized_by_path: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    if not isinstance(value, list) or len(value) != len(CANDIDATE_PROMOTED_HEADS):
        raise ProjectionBlocked("candidate capture must contain exactly one Avalonia head")
    expected_export_heads = _candidate_expected_export_heads(scope)
    result: dict[str, dict[str, object]] = {}
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {
            "authenticodeVerification",
            "headId",
            "rid",
            "installer",
            "payload",
            "receipt",
            "progressLog",
            "screenshots",
        }:
            raise ProjectionBlocked("candidate capture head property set drifted")
        head = CANDIDATE_PROMOTED_HEADS[index]
        if raw.get("headId") != head or raw.get("rid") != CANDIDATE_RID or head in result:
            raise ProjectionBlocked("candidate capture head scope drifted")
        expected_export = expected_export_heads[index]
        _validate_candidate_export_artifact_binding(
            raw.get("installer"),
            expected=expected_export["installer"],
            label="candidate capture installer binding",
        )
        _validate_candidate_export_artifact_binding(
            raw.get("payload"),
            expected=expected_export["payload"],
            label="candidate capture payload binding",
        )

        for property_name, expected_path in (
            (
                "receipt",
                f"startup-smoke/startup-smoke-{head}-{CANDIDATE_RID}.receipt.json",
            ),
            (
                "progressLog",
                f"startup-smoke/windows-installer-progress-{head}-{CANDIDATE_RID}.log",
            ),
        ):
            binding = raw.get(property_name)
            if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
                raise ProjectionBlocked(f"candidate capture {property_name} binding drifted")
            digest = binding.get("sha256")
            inventory_row = finalized_by_path.get(expected_path)
            if (
                binding.get("path") != expected_path
                or SHA256_RE.fullmatch(str(digest or "")) is None
                or inventory_row is None
                or inventory_row["sha256"] != digest
                or not isinstance(inventory_row["sizeBytes"], int)
                or inventory_row["sizeBytes"] < 1
            ):
                raise ProjectionBlocked(
                    f"candidate capture {property_name} differs from finalized inventory"
                )

        screenshots = raw.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) != 2:
            raise ProjectionBlocked("candidate capture screenshot set drifted")
        expected_screenshots: list[dict[str, object]] = []
        digests: set[str] = set()
        for screenshot_index, role in enumerate(("progress", "completion")):
            screenshot = screenshots[screenshot_index]
            if not isinstance(screenshot, dict) or set(screenshot) != {
                "role",
                "path",
                "sha256",
                "width",
                "height",
            }:
                raise ProjectionBlocked("candidate capture screenshot binding drifted")
            expected_path = (
                f"screenshots/windows-installer-{head}-{CANDIDATE_RID}-{role}.png"
            )
            digest = screenshot.get("sha256")
            width = screenshot.get("width")
            height = screenshot.get("height")
            inventory_row = finalized_by_path.get(expected_path)
            if (
                screenshot.get("role") != role
                or screenshot.get("path") != expected_path
                or SHA256_RE.fullmatch(str(digest or "")) is None
                or isinstance(width, bool)
                or not isinstance(width, int)
                or not 320 <= width <= 16_384
                or isinstance(height, bool)
                or not isinstance(height, int)
                or not 200 <= height <= 16_384
                or inventory_row is None
                or inventory_row["sha256"] != digest
                or not isinstance(inventory_row["sizeBytes"], int)
                or inventory_row["sizeBytes"] < 1
                or str(digest) in digests
            ):
                raise ProjectionBlocked(
                    "candidate capture screenshot differs from finalized inventory"
                )
            digests.add(str(digest))
            expected_screenshots.append(
                {"role": role, "path": expected_path, "sha256": digest}
            )
        result[head] = {"screenshots": expected_screenshots}
        authenticode = raw.get("authenticodeVerification")
        auth_path = (
            "authenticode/"
            "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"
        )
        if (
            not isinstance(authenticode, dict)
            or set(authenticode)
            != {
                "path",
                "sha256",
                "signerCertificateSha256",
                "signerSpkiSha256",
                "sizeBytes",
                "timestampUtc",
            }
            or authenticode.get("path") != auth_path
            or finalized_by_path.get(auth_path)
            != {
                "path": auth_path,
                "sha256": authenticode.get("sha256"),
                "sizeBytes": authenticode.get("sizeBytes"),
            }
        ):
            raise ProjectionBlocked("candidate capture Authenticode binding drifted")
    return result


def _validate_capture_candidate_binding(
    value: object,
    *,
    documents: dict[str, tuple[dict[str, object], bytes, dict[str, object]]],
    canonical_manifest_sha256: str,
    capture_source: dict[str, object],
    capture_generated_at: datetime,
) -> dict[str, object]:
    required = {
        "actor",
        "artifactCreatedAt",
        "artifactExpiresAt",
        "artifactId",
        "artifactName",
        "artifactSha256",
        "authenticatedApiSha256",
        "contentInventory",
        "contentInventorySha256",
        "exportReceipt",
        "exportReceiptSha256",
        "handoffSha256",
        "manifestPath",
        "manifestSha256",
        "ref",
        "repository",
        "runAttempt",
        "runId",
        "sha",
        "workflow",
        "fullShelfCompatibilityManifest",
        "fullShelfCompatibilityManifestPath",
        "fullShelfCompatibilityManifestSha256",
        "fullShelfManifest",
        "fullShelfManifestPath",
        "fullShelfManifestSha256",
        "publicationScope",
        "publicationScopePath",
        "publicationScopeSha256",
        "registryPrepareFiles",
        "registryPrepareSha256",
        "scopeDecisionSha256",
        "signingReceipt",
        "signingReceiptPath",
        "signingReceiptSha256",
        "supplyChain",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ProjectionBlocked("candidate capture binding property set drifted")
    if (
        value.get("repository") != CANDIDATE_UI_REPOSITORY
        or value.get("workflow") != CANDIDATE_PRODUCER_WORKFLOW
        or value.get("ref") != CANDIDATE_UI_REF
        or CANDIDATE_COMMIT_RE.fullmatch(str(value.get("sha") or "")) is None
        or CANDIDATE_GITHUB_LOGIN_RE.fullmatch(str(value.get("actor") or "")) is None
    ):
        raise ProjectionBlocked("candidate capture producer provenance drifted")
    for name in ("runId", "runAttempt", "artifactId"):
        _candidate_positive_github_integer(value.get(name), label=f"candidate capture {name}")
    if value.get("artifactName") != (
        f"preview-nightly-candidate-{value['runId']}-{value['runAttempt']}"
    ):
        raise ProjectionBlocked("candidate capture artifact name drifted")
    for name in (
        "artifactSha256",
        "authenticatedApiSha256",
        "contentInventorySha256",
        "exportReceiptSha256",
        "handoffSha256",
        "manifestSha256",
        "fullShelfCompatibilityManifestSha256",
        "fullShelfManifestSha256",
        "publicationScopeSha256",
        "registryPrepareSha256",
        "scopeDecisionSha256",
        "signingReceiptSha256",
    ):
        if SHA256_RE.fullmatch(str(value.get(name) or "")) is None:
            raise ProjectionBlocked(f"candidate capture {name} is invalid")
    for name in (
        "fullShelfCompatibilityManifest",
        "fullShelfManifest",
        "publicationScope",
        "signingReceipt",
    ):
        binding = value.get(name)
        path_name = f"{name}Path"
        digest_name = f"{name}Sha256"
        if (
            not isinstance(binding, dict)
            or set(binding) != {"path", "sha256", "sizeBytes"}
            or binding.get("path")
            != f"candidate-provenance/{value.get(path_name)}"
            or binding.get("sha256") != value.get(digest_name)
            or isinstance(binding.get("sizeBytes"), bool)
            or not isinstance(binding.get("sizeBytes"), int)
            or binding["sizeBytes"] < 1
        ):
            raise ProjectionBlocked(f"candidate capture {name} binding drifted")
    if not isinstance(value.get("registryPrepareFiles"), list) or not isinstance(
        value.get("supplyChain"), dict
    ):
        raise ProjectionBlocked("candidate capture Windows-only provenance drifted")
    if (
        value.get("manifestPath") != "RELEASE_CHANNEL.generated.json"
        or value.get("manifestSha256") != canonical_manifest_sha256
    ):
        raise ProjectionBlocked("candidate capture manifest binding drifted")
    created_at = _candidate_github_timestamp(
        value.get("artifactCreatedAt"), label="candidate capture artifactCreatedAt"
    )
    expires_at = _candidate_github_timestamp(
        value.get("artifactExpiresAt"), label="candidate capture artifactExpiresAt"
    )
    if (
        created_at >= expires_at
        or created_at > capture_generated_at + timedelta(minutes=5)
        or expires_at <= capture_generated_at
    ):
        raise ProjectionBlocked("candidate capture artifact lifetime drifted")
    if any(
        value.get(name) != capture_source.get(name)
        for name in ("repository", "ref", "sha")
    ):
        raise ProjectionBlocked("candidate capture revision differs from capture source")

    for name, path, digest_name in (
        ("contentInventory", CANDIDATE_PROVENANCE_INVENTORY_FILE, "contentInventorySha256"),
        ("exportReceipt", CANDIDATE_PROVENANCE_EXPORT_FILE, "exportReceiptSha256"),
    ):
        binding = value.get(name)
        if not isinstance(binding, dict) or set(binding) != {"path", "sha256", "sizeBytes"}:
            raise ProjectionBlocked(f"candidate capture {name} property set drifted")
        _document, payload, entry = documents[path]
        expected_sha256 = hashlib.sha256(payload).hexdigest()
        binding_size = binding.get("sizeBytes")
        if (
            binding.get("path") != path
            or binding.get("sha256") != expected_sha256
            or isinstance(binding_size, bool)
            or not isinstance(binding_size, int)
            or binding_size != len(payload)
            or value.get(digest_name) != expected_sha256
            or entry.get("sha256") != expected_sha256
            or entry.get("sizeBytes") != len(payload)
        ):
            raise ProjectionBlocked(f"candidate capture {name} custody drifted")
    return value


def _validate_candidate_export_receipt(
    receipt: dict[str, object],
    *,
    receipt_semantic: dict[str, object],
    candidate_binding: dict[str, object],
    candidate_binding_semantic: dict[str, object],
    canonical_manifest_sha256: str,
    scope: dict[str, object],
) -> None:
    required = {
        "candidateManifest",
        "contentInventory",
        "contractName",
        "contractVersion",
        "heads",
        "release",
        "source",
        "status",
        "publicationScope",
        "supplyChain",
        "supplyChainVerification",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ProjectionBlocked("candidate export receipt property set drifted")
    if (
        receipt.get("contractName") != "chummer6-ui.preview-nightly-candidate-export"
        or type(receipt.get("contractVersion")) is not int
        or receipt.get("contractVersion") != 2
        or receipt.get("status") != "exported"
        or not _json_semantic_equal(
            receipt_semantic.get("release"),
            {"channel": scope["channel"], "version": scope["version"]},
        )
        or not _json_semantic_equal(
            receipt_semantic.get("candidateManifest"),
            {
                "path": "RELEASE_CHANNEL.generated.json",
                "sha256": canonical_manifest_sha256,
            },
        )
        or not _json_semantic_equal(
            receipt_semantic.get("contentInventory"),
            {
                "path": CANDIDATE_PROVENANCE_INVENTORY_FILE.rsplit("/", 1)[-1],
                "sha256": candidate_binding["contentInventorySha256"],
            },
        )
    ):
        raise ProjectionBlocked("candidate export release or byte binding drifted")
    if (
        not _json_semantic_equal(
            receipt_semantic.get("publicationScope"),
            {
                "registryPrepareSha256": candidate_binding[
                    "registryPrepareSha256"
                ]
            },
        )
        or not _json_semantic_equal(
            receipt_semantic.get("supplyChain"),
            candidate_binding_semantic.get("supplyChain"),
        )
        or not _json_semantic_equal(
            receipt_semantic.get("supplyChainVerification"),
            {
                "mode": "release_authoritative",
                "releaseAuthoritative": True,
            },
        )
    ):
        raise ProjectionBlocked("candidate export Windows-only authority drifted")
    _validate_candidate_export_heads(
        receipt.get("heads"),
        scope=scope,
        label="candidate export required-head",
    )
    source = receipt.get("source")
    required_source = {
        "actor",
        "artifactName",
        "ref",
        "repository",
        "runAttempt",
        "runId",
        "runnerLabel",
        "sha",
        "workflow",
    }
    if not isinstance(source, dict) or set(source) != required_source:
        raise ProjectionBlocked("candidate export source property set drifted")
    for name in (
        "actor",
        "artifactName",
        "ref",
        "repository",
        "runAttempt",
        "runId",
        "sha",
        "workflow",
    ):
        if source.get(name) != candidate_binding[name] or not isinstance(source.get(name), str):
            raise ProjectionBlocked("candidate export source differs from capture authority")
    if (
        not isinstance(source.get("runnerLabel"), str)
        or CANDIDATE_EXPORT_RUNNER_LABEL_RE.fullmatch(source["runnerLabel"]) is None
    ):
        raise ProjectionBlocked("candidate export runner label drifted")


def _validate_candidate_native_evidence(
    native: object,
    *,
    canonical: dict[str, object],
    candidate_rows: list[dict[str, object]],
    candidate: dict[str, object],
    now: datetime,
) -> dict[str, object]:
    required_native = {
        "status",
        "captureGeneratedAtUtc",
        "finalizationGeneratedAtUtc",
        "reviewer",
        "captureSource",
        "finalizationSource",
        "candidateContentInventorySha256",
        "candidateContentInventory",
        "files",
    }
    if (
        not isinstance(native, dict)
        or set(native) != required_native
        or native.get("status") != "passed"
        or CANDIDATE_REVIEWER_RE.fullmatch(str(native.get("reviewer") or "")) is None
        or not isinstance(native.get("files"), list)
    ):
        raise ProjectionBlocked("candidate native-Windows evidence custody drifted")
    reviewer = str(native["reviewer"])
    summary_capture_at = _candidate_timestamp(
        native.get("captureGeneratedAtUtc"),
        label="candidate capture summary timestamp",
        now=now,
    )
    summary_finalization_at = _candidate_timestamp(
        native.get("finalizationGeneratedAtUtc"),
        label="candidate finalization summary timestamp",
        now=now,
    )
    capture_source = _candidate_source(
        native.get("captureSource"),
        label="candidate capture source",
        workflow=CANDIDATE_CAPTURE_WORKFLOW,
    )
    finalization_source = _candidate_source(
        native.get("finalizationSource"),
        label="candidate finalization source",
        workflow=CANDIDATE_FINALIZE_WORKFLOW,
    )
    if (
        capture_source["actor"] != "github-actions[bot]"
        or finalization_source["actor"] != reviewer
        or reviewer == capture_source["actor"]
        or capture_source["sha"] != finalization_source["sha"]
    ):
        raise ProjectionBlocked("candidate protected reviewer provenance drifted")

    documents: dict[str, tuple[dict[str, object], bytes, dict[str, object]]] = {}
    for raw_entry in native["files"]:
        if not isinstance(raw_entry, dict):
            raise ProjectionBlocked("candidate native-Windows evidence entry drifted")
        path = _candidate_relative_path(
            raw_entry.get("path"), label="candidate native-Windows evidence path"
        )
        if path in documents:
            raise ProjectionBlocked("candidate native-Windows evidence path is duplicated")
        evidence_bytes = _candidate_embedded_bytes(
            raw_entry,
            label=f"candidate native-Windows {path}",
            expected_path=path,
        )
        documents[path] = (
            _strict_json_object(evidence_bytes, label=f"candidate native-Windows {path}"),
            evidence_bytes,
            raw_entry,
        )

    scope = _candidate_windows_scope(canonical, candidate_rows, candidate)
    heads = scope["heads"]
    artifacts = scope["artifacts"]
    fixed_paths = {
        CANDIDATE_CAPTURE_FILE,
        CANDIDATE_CAPTURE_INVENTORY_FILE,
        CANDIDATE_FINALIZATION_FILE,
        CANDIDATE_FINALIZED_INVENTORY_FILE,
        CANDIDATE_PROVENANCE_INVENTORY_FILE,
        CANDIDATE_PROVENANCE_EXPORT_FILE,
        *{
            f"startup-smoke/startup-smoke-{head}-{CANDIDATE_RID}.receipt.json"
            for head in heads
        },
    }
    if not fixed_paths.issubset(documents):
        raise ProjectionBlocked("candidate native-Windows evidence custody is incomplete")

    finalized, _, _ = documents[CANDIDATE_FINALIZED_INVENTORY_FILE]
    if (
        set(finalized)
        != {"contractName", "contractVersion", "captureInventorySha256", "files"}
        or finalized.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-finalized-inventory"
        or type(finalized.get("contractVersion")) is not int
        or finalized.get("contractVersion") != 1
    ):
        raise ProjectionBlocked("candidate finalized native-Windows inventory contract drifted")
    finalized_rows = _candidate_inventory_rows(
        finalized.get("files"), label="candidate finalized native-Windows inventory"
    )
    finalized_by_path = {str(row["path"]): row for row in finalized_rows}
    for path, (_document, evidence_bytes, entry) in documents.items():
        if path == CANDIDATE_FINALIZED_INVENTORY_FILE:
            continue
        if finalized_by_path.get(path) != {
            "path": path,
            "sha256": entry["sha256"],
            "sizeBytes": len(evidence_bytes),
        }:
            raise ProjectionBlocked("candidate embedded evidence disagrees with finalized inventory")

    provenance, provenance_bytes, _ = documents[CANDIDATE_PROVENANCE_INVENTORY_FILE]
    expected_content_paths = [
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        *[
            str(artifacts[head][role]["path"])
            for head in heads
            for role in ("installer", "payload")
        ],
    ]
    provenance_rows = _candidate_inventory_rows(
        provenance.get("files"), label="candidate native-Windows content inventory"
    )
    if (
        provenance.get("contractName")
        != "chummer6-ui.preview-nightly-candidate-content-inventory"
        or type(provenance.get("contractVersion")) is not int
        or provenance.get("contractVersion") != 2
        or provenance.get("release")
        != {"channel": scope["channel"], "version": scope["version"]}
        or provenance.get("manifest")
        != {
            "path": "RELEASE_CHANNEL.generated.json",
            "sha256": candidate["canonicalManifestSha256"],
        }
        or not set(expected_content_paths).issubset(
            {str(row["path"]) for row in provenance_rows}
        )
        or provenance != native.get("candidateContentInventory")
        or hashlib.sha256(provenance_bytes).hexdigest()
        != native.get("candidateContentInventorySha256")
    ):
        raise ProjectionBlocked("candidate native-Windows content inventory binding drifted")
    candidate_by_path = {str(row["path"]): row for row in candidate_rows}
    provenance_by_path = {str(row["path"]): row for row in provenance_rows}
    if any(
        candidate_by_path.get(path) != provenance_by_path.get(path)
        for path in expected_content_paths
    ):
        raise ProjectionBlocked("candidate native-Windows content bytes drifted")
    capture, capture_bytes, _ = documents[CANDIDATE_CAPTURE_FILE]
    capture_at = _candidate_timestamp(
        capture.get("generatedAt"), label="candidate capture timestamp", now=now
    )
    if (
        set(capture)
        != {
            "authenticodeVerification",
            "candidate",
            "captureMode",
            "channelId",
            "contractName",
            "contractVersion",
            "generatedAt",
            "heads",
            "source",
            "status",
            "version",
        }
        or capture.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-capture"
        or type(capture.get("contractVersion")) is not int
        or capture.get("contractVersion") != 2
        or capture.get("status") != "captured"
        or capture.get("captureMode") != "interactive"
        or capture.get("version") != scope["version"]
        or capture.get("channelId") != scope["channel"]
        or capture.get("source") != capture_source
        or capture_at != summary_capture_at
    ):
        raise ProjectionBlocked("candidate native-Windows capture receipt drifted")
    capture_candidate = _validate_capture_candidate_binding(
        capture.get("candidate"),
        documents=documents,
        canonical_manifest_sha256=str(candidate["canonicalManifestSha256"]),
        capture_source=capture_source,
        capture_generated_at=capture_at,
    )
    capture_heads = _validate_candidate_capture_heads(
        capture.get("heads"), scope=scope, finalized_by_path=finalized_by_path
    )

    capture_inventory, capture_inventory_bytes, _ = documents[CANDIDATE_CAPTURE_INVENTORY_FILE]
    if (
        set(capture_inventory)
        != {
            "contractName",
            "contractVersion",
            "captureContract",
            "captureManifestSha256",
            "files",
        }
        or capture_inventory.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-capture-inventory"
        or type(capture_inventory.get("contractVersion")) is not int
        or capture_inventory.get("contractVersion") != 2
        or capture_inventory.get("captureContract")
        != "chummer6-ui.preview-nightly-native-windows-capture"
        or capture_inventory.get("captureManifestSha256")
        != hashlib.sha256(capture_bytes).hexdigest()
    ):
        raise ProjectionBlocked("candidate native-Windows capture inventory drifted")
    capture_rows = _candidate_inventory_rows(
        capture_inventory.get("files"),
        label="candidate native-Windows capture inventory",
    )
    if any(
        finalized_by_path.get(str(row["path"])) != row for row in capture_rows
    ):
        raise ProjectionBlocked(
            "candidate native-Windows capture inventory differs from its finalized capture tree"
        )
    capture_inventory_sha256 = hashlib.sha256(capture_inventory_bytes).hexdigest()
    if finalized.get("captureInventorySha256") != capture_inventory_sha256:
        raise ProjectionBlocked(
            "candidate finalized inventory capture binding drifted"
        )

    finalization, finalization_bytes, _ = documents[CANDIDATE_FINALIZATION_FILE]
    finalization_at = _candidate_timestamp(
        finalization.get("generatedAt"),
        label="candidate finalization timestamp",
        now=now,
    )
    proof_rows = finalization.get("proofs")
    if (
        set(finalization)
        != {
            "authenticodeVerification",
            "captureInventorySha256",
            "captureSource",
            "contractName",
            "contractVersion",
            "finalizationSource",
            "generatedAt",
            "humanReviewConfirmed",
            "proofs",
            "reviewer",
            "reviewerWasCaptureActor",
            "scopeApproval",
            "status",
        }
        or finalization.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-finalization"
        or type(finalization.get("contractVersion")) is not int
        or finalization.get("contractVersion") != 2
        or finalization.get("status") != "passed"
        or finalization.get("humanReviewConfirmed") is not True
        or finalization.get("reviewerWasCaptureActor") is not False
        or finalization.get("reviewer") != reviewer
        or finalization.get("captureSource") != capture_source
        or finalization.get("finalizationSource") != finalization_source
        or finalization.get("captureInventorySha256")
        != capture_inventory_sha256
        or finalization_at != summary_finalization_at
        or not isinstance(proof_rows, list)
        or len(proof_rows) != len(heads)
    ):
        raise ProjectionBlocked("candidate native-Windows finalization receipt drifted")

    proofs_by_head: dict[str, tuple[str, dict[str, object], bytes]] = {}
    for row in proof_rows:
        if not isinstance(row, dict) or set(row) != {"headId", "path", "sha256"}:
            raise ProjectionBlocked("candidate finalization visual binding drifted")
        head = row.get("headId")
        path = _candidate_relative_path(row.get("path"), label="candidate visual proof path")
        if head not in heads or head in proofs_by_head or path not in documents:
            raise ProjectionBlocked("candidate finalization visual head scope drifted")
        proof, proof_bytes, _ = documents[path]
        if row.get("sha256") != hashlib.sha256(proof_bytes).hexdigest():
            raise ProjectionBlocked("candidate finalization visual digest drifted")
        proofs_by_head[str(head)] = (path, proof, proof_bytes)
    expected_document_paths = fixed_paths | {path for path, _, _ in proofs_by_head.values()}
    if set(documents) != expected_document_paths:
        raise ProjectionBlocked("candidate native-Windows evidence file scope drifted")
    expected_finalized_paths = {
        *(str(row["path"]) for row in capture_rows),
        CANDIDATE_CAPTURE_INVENTORY_FILE,
        CANDIDATE_FINALIZATION_FILE,
        *(path for path, _, _ in proofs_by_head.values()),
        "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json",
    }
    if set(finalized_by_path) != expected_finalized_paths:
        raise ProjectionBlocked(
            "candidate finalized native-Windows inventory file scope drifted"
        )
    non_capture_paths = {
        CANDIDATE_CAPTURE_INVENTORY_FILE,
        CANDIDATE_FINALIZATION_FILE,
        "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json",
        *(path for path, _, _ in proofs_by_head.values()),
    }
    expected_capture_rows = [
        row for row in finalized_rows if str(row["path"]) not in non_capture_paths
    ]
    if capture_rows != expected_capture_rows:
        raise ProjectionBlocked(
            "candidate native-Windows capture inventory differs from its exact pre-finalization tree"
        )

    export, export_bytes, _ = documents[CANDIDATE_PROVENANCE_EXPORT_FILE]
    _validate_candidate_export_receipt(
        export,
        receipt_semantic=_json_semantic_object(
            export_bytes,
            label="candidate export receipt",
        ),
        candidate_binding=capture_candidate,
        candidate_binding_semantic=_json_semantic_object(
            capture_bytes,
            label="candidate capture receipt",
        )["candidate"],
        canonical_manifest_sha256=str(candidate["canonicalManifestSha256"]),
        scope=scope,
    )

    for head in heads:
        installer = artifacts[head]["installer"]
        payload = artifacts[head]["payload"]
        startup_path = f"startup-smoke/startup-smoke-{head}-{CANDIDATE_RID}.receipt.json"
        startup, _, _ = documents[startup_path]
        native_host = startup.get("nativeHostEvidence")
        if (
            startup.get("status") != "pass"
            or startup.get("readyCheckpoint") != "pre_ui_event_loop"
            or startup.get("executionEnvironment") != "native_windows"
            or startup.get("headId") != head
            or startup.get("platform") != "windows"
            or startup.get("rid") != CANDIDATE_RID
            or startup.get("releaseVersion") != scope["version"]
            or startup.get("channelId") != scope["channel"]
            or startup.get("artifactFileName") != installer["fileName"]
            or startup.get("artifactDigest") != f"sha256:{installer['sha256']}"
            or startup.get("bootstrapPayloadAcquisitionMode") != "download"
            or startup.get("bootstrapPayloadFileName") != payload["fileName"]
            or startup.get("bootstrapPayloadSha256") != payload["sha256"]
            or isinstance(startup.get("bootstrapPayloadSizeBytes"), bool)
            or not isinstance(startup.get("bootstrapPayloadSizeBytes"), int)
            or startup.get("bootstrapPayloadSizeBytes") != payload["sizeBytes"]
            or not isinstance(native_host, dict)
            or native_host.get("contractName") != "chummer6-ui.native_windows_host_evidence"
            or native_host.get("status") != "verified"
            or native_host.get("isNativeWindows") is not True
            or native_host.get("hostPlatform") != "windows"
            or not isinstance(native_host.get("runner"), str)
            or not native_host["runner"].strip()
            or "wine" in str(native_host.get("runner") or "").lower()
        ):
            raise ProjectionBlocked(f"candidate {head} startup receipt is not native Windows")

        _, proof, _ = proofs_by_head[head]
        _candidate_timestamp(
            proof.get("generatedAt"), label=f"candidate {head} visual timestamp", now=now
        )
        screenshots = proof.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) != 2:
            raise ProjectionBlocked(f"candidate {head} visual screenshot set drifted")
        roles: set[str] = set()
        for screenshot in screenshots:
            if not isinstance(screenshot, dict) or set(screenshot) != {"role", "path", "sha256"}:
                raise ProjectionBlocked(f"candidate {head} visual screenshot binding drifted")
            role = screenshot.get("role")
            path = _candidate_relative_path(
                screenshot.get("path"), label=f"candidate {head} screenshot path"
            )
            digest = screenshot.get("sha256")
            if (
                role not in {"progress", "completion"}
                or role in roles
                or SHA256_RE.fullmatch(str(digest or "")) is None
                or finalized_by_path.get(path, {}).get("sha256") != digest
            ):
                raise ProjectionBlocked(f"candidate {head} visual screenshot proof drifted")
            roles.add(str(role))
        if screenshots != capture_heads[head]["screenshots"]:
            raise ProjectionBlocked(
                f"candidate {head} visual screenshots differ from the capture head"
            )
        checks = proof.get("checks")
        review = proof.get("review")
        capture_binding = proof.get("captureBinding")
        expected_capture_binding = {
            key: capture_source[key]
            for key in (
                "repository",
                "workflow",
                "runId",
                "runAttempt",
                "ref",
                "sha",
                "artifactName",
            )
        }
        expected_capture_binding["inventorySha256"] = hashlib.sha256(
            capture_inventory_bytes
        ).hexdigest()
        if (
            set(proof)
            != {
                "artifactDigest",
                "artifactFileName",
                "authenticodeVerification",
                "captureBinding",
                "channel",
                "channelId",
                "checks",
                "clippingReview",
                "contractName",
                "contractVersion",
                "contrastReview",
                "finalizationBinding",
                "generatedAt",
                "head",
                "headId",
                "platform",
                "readabilityReview",
                "releaseVersion",
                "review",
                "rid",
                "screenshots",
                "status",
                "version",
            }
            or
            proof.get("contractName") != "chummer6-ui.windows_installer_visual_proof"
            or type(proof.get("contractVersion")) is not int
            or proof["contractVersion"] != 1
            or proof.get("status") != "passed"
            or proof.get("version") != scope["version"]
            or proof.get("headId") != head
            or proof.get("head") != head
            or proof.get("platform") != "windows"
            or proof.get("rid") != CANDIDATE_RID
            or proof.get("releaseVersion") != scope["version"]
            or proof.get("channel") != scope["channel"]
            or proof.get("channelId") != scope["channel"]
            or proof.get("artifactFileName") != installer["fileName"]
            or proof.get("artifactDigest") != f"sha256:{installer['sha256']}"
            or not isinstance(checks, dict)
            or set(checks) != {"capture_mode", "human_review_confirmed"}
            or checks.get("capture_mode") != "interactive"
            or checks.get("human_review_confirmed") is not True
            or proof.get("readabilityReview") != {"status": "passed", "reviewer": reviewer}
            or proof.get("contrastReview") != {"status": "passed", "reviewer": reviewer}
            or proof.get("clippingReview") != {"status": "passed", "reviewer": reviewer}
            or review
            != {
                "authenticatedReviewer": reviewer,
                "captureActor": capture_source["actor"],
                "allowlistSource": "repository variable plus protected environment",
                "explicitConfirmations": {
                    "readability": "passed",
                    "contrast": "passed",
                    "clipping": "passed",
                },
            }
            or capture_binding != expected_capture_binding
            or proof.get("finalizationBinding") != finalization_source
            or proof.get("authenticodeVerification")
            != finalization.get("authenticodeVerification")
        ):
            raise ProjectionBlocked(f"candidate {head} visual proof is not a finalized human pass")
    return {
        "candidate": capture_candidate,
        "captureInventorySha256": capture_inventory_sha256,
        "finalizationBytes": finalization_bytes,
        "visualProofs": {
            head: proof for head, (_path, proof, _raw) in proofs_by_head.items()
        },
    }


def _candidate_canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _candidate_ui_compact_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _candidate_reference(
    value: object,
    *,
    path: str,
    raw: bytes,
    label: str,
) -> None:
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "sizeBytes"}:
        raise ProjectionBlocked(f"{label} byte reference drifted")
    if value != {
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
    }:
        raise ProjectionBlocked(f"{label} byte reference differs from held bytes")


def _candidate_embedded_documents(
    value: object,
    *,
    label: str,
) -> dict[str, tuple[dict[str, object], bytes]]:
    if not isinstance(value, list) or not value:
        raise ProjectionBlocked(f"{label} embedded file inventory is empty")
    documents: dict[str, tuple[dict[str, object], bytes]] = {}
    for entry in value:
        if not isinstance(entry, dict):
            raise ProjectionBlocked(f"{label} embedded file entry drifted")
        path = _candidate_relative_path(entry.get("path"), label=f"{label} path")
        if path in documents:
            raise ProjectionBlocked(f"{label} embedded file path is duplicated")
        raw = _candidate_embedded_bytes(entry, label=f"{label} {path}", expected_path=path)
        documents[path] = (
            _strict_json_object(raw, label=f"{label} {path}"),
            raw,
        )
    return documents


def _validate_candidate_finalized_publication(
    value: object,
    *,
    canonical_raw: bytes,
    compatibility_raw: bytes,
    candidate: dict[str, object],
    native_package: dict[str, object],
) -> tuple[dict[str, object], bytes, dict[str, tuple[dict[str, object], bytes]]]:
    summary_keys = {
        "status",
        "exactIncomingDesktopScope",
        "publicationScopeSha256",
        "scopeDecisionSha256",
        "signingReceiptSha256",
        "nativeEvidenceSha256",
        "authenticodeVerificationSha256",
        "approvalSha256",
        "visualApprovalSha256",
        "actors",
        "files",
    }
    if not isinstance(value, dict) or set(value) != summary_keys:
        raise ProjectionBlocked("candidate finalized publication evidence custody drifted")
    if (
        value.get("status") != "passed"
        or value.get("exactIncomingDesktopScope") != CANDIDATE_EXACT_SCOPE
    ):
        raise ProjectionBlocked("candidate finalized publication evidence scope drifted")
    documents = _candidate_embedded_documents(
        value.get("files"), label="candidate finalized publication evidence"
    )
    if CANDIDATE_PUBLICATION_SCOPE_FILE not in documents:
        raise ProjectionBlocked("candidate finalized publication scope is absent")
    scope, scope_raw = documents[CANDIDATE_PUBLICATION_SCOPE_FILE]
    scope_keys = {
        "approval",
        "approvalIndependent",
        "authenticodeRequired",
        "authenticodeVerificationSha256",
        "buildEvidenceTuples",
        "contractName",
        "contractVersion",
        "deployAuthorized",
        "fullShelfCompatibilityManifestSha256",
        "fullShelfInventory",
        "fullShelfInventorySha256",
        "fullShelfManifestSha256",
        "incumbentSnapshot",
        "incumbentSnapshotSha256",
        "macosSoak",
        "nativeEvidenceComposite",
        "nativeEvidenceSha256",
        "nonPublishedEvidenceTuples",
        "postPublicationShelfTuples",
        "publicationDeltaTuples",
        "publicationEligible",
        "registryPrepare",
        "registryFinalizeEligible",
        "release",
        "retainedTuples",
        "scopeDecision",
        "scopeDecisionSha256",
        "signingReceipt",
        "signingReceiptSha256",
        "status",
        "uploadAuthorized",
        "visualApprovalSha256",
    }
    if (
        set(scope) != scope_keys
        or scope.get("contractName")
        != "chummer6-ui.preview-nightly-windows-publication-scope"
        or type(scope.get("contractVersion")) is not int
        or scope.get("contractVersion") != 2
        or scope.get("status") != "validated"
        or scope.get("release")
        != {"channel": "preview", "version": candidate["version"]}
        or scope.get("approvalIndependent") is not True
        or scope.get("authenticodeRequired") is not True
        or scope.get("registryFinalizeEligible") is not True
        or any(
            scope.get(key) is not False
            for key in ("publicationEligible", "uploadAuthorized", "deployAuthorized")
        )
        or scope.get("fullShelfManifestSha256")
        != hashlib.sha256(canonical_raw).hexdigest()
        or scope.get("fullShelfCompatibilityManifestSha256")
        != hashlib.sha256(compatibility_raw).hexdigest()
    ):
        raise ProjectionBlocked("candidate finalized publication scope contract drifted")
    delta = scope.get("publicationDeltaTuples")
    retained = scope.get("retainedTuples")
    post = scope.get("postPublicationShelfTuples")
    evidence_rows = scope.get("nonPublishedEvidenceTuples")
    if (
        not isinstance(delta, list)
        or [
            (row.get("head"), row.get("platform"), row.get("rid"), row.get("artifactRole"))
            if isinstance(row, dict)
            else None
            for row in delta
        ]
        != [
            ("avalonia", "windows", CANDIDATE_RID, "installer"),
            ("avalonia", "windows", CANDIDATE_RID, "payload"),
        ]
        or not isinstance(retained, list)
        or any(not isinstance(row, dict) or row.get("platform") == "windows" for row in retained)
        or not isinstance(post, list)
        or post
        != sorted(
            [*retained, *delta],
            key=lambda row: (
                row["platform"],
                row["rid"],
                row["head"],
                row["artifactRole"],
                row["path"],
            ),
        )
        or not isinstance(evidence_rows, list)
        or len(evidence_rows) != 1
        or (
            evidence_rows[0].get("platform"),
            evidence_rows[0].get("rid"),
            evidence_rows[0].get("artifactRole"),
        )
        != ("linux", "linux-x64", "installer")
    ):
        raise ProjectionBlocked("candidate finalized publication tuple partition drifted")
    full_inventory = scope.get("fullShelfInventory")
    if (
        not isinstance(full_inventory, list)
        or scope.get("fullShelfInventorySha256")
        != _candidate_canonical_sha256(full_inventory)
        or scope.get("scopeDecisionSha256")
        != _candidate_canonical_sha256(scope.get("scopeDecision"))
    ):
        raise ProjectionBlocked("candidate finalized publication shelf digest graph drifted")
    signing = scope.get("signingReceipt")
    approval = scope.get("approval")
    if (
        not isinstance(signing, dict)
        or set(signing) != {"path", "sha256"}
        or not isinstance(approval, dict)
        or set(approval) != {"approver", "path", "sha256"}
    ):
        raise ProjectionBlocked("candidate finalized publication evidence references drifted")
    visual_path = (
        f"WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-{CANDIDATE_RID}.generated.json"
    )
    native_finalization_path = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
    composite = scope.get("nativeEvidenceComposite")
    composite_contracts = {
        "wrapper": (
            "chummer6-ui.preview-nightly-native-windows-evidence",
            1,
            "NATIVE_WINDOWS_EVIDENCE.generated.json",
        ),
        "nativeFinalization": (
            "chummer6-ui.preview-nightly-native-windows-finalization",
            2,
            native_finalization_path,
        ),
        "visualProof": (
            "chummer6-ui.windows_installer_visual_proof",
            1,
            visual_path,
        ),
        "authenticodeVerification": (
            "chummer6-ui.windows-authenticode-verification",
            1,
            CANDIDATE_AUTHENTICODE_PATH,
        ),
    }
    if not isinstance(composite, dict) or set(composite) != set(composite_contracts):
        raise ProjectionBlocked("candidate native evidence composite scope drifted")
    expected_paths = {
        CANDIDATE_PUBLICATION_SCOPE_FILE,
        str(signing["path"]),
        "NATIVE_WINDOWS_EVIDENCE.generated.json",
        native_finalization_path,
        CANDIDATE_AUTHENTICODE_PATH,
        str(approval["path"]),
        visual_path,
    }
    if set(documents) != expected_paths:
        raise ProjectionBlocked("candidate finalized publication evidence file scope drifted")
    for key, (contract_name, contract_version, path) in composite_contracts.items():
        reference = composite.get(key)
        raw = documents[path][1]
        if (
            not isinstance(reference, dict)
            or set(reference)
            != {"contractName", "contractVersion", "path", "sha256", "sizeBytes"}
            or type(reference.get("contractVersion")) is not int
            or type(reference.get("sizeBytes")) is not int
            or reference
            != {
                "contractName": contract_name,
                "contractVersion": contract_version,
                "path": path,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "sizeBytes": len(raw),
            }
        ):
            raise ProjectionBlocked(
                f"candidate native evidence composite {key} reference drifted"
            )
    digest_bindings = {
        CANDIDATE_PUBLICATION_SCOPE_FILE: value.get("publicationScopeSha256"),
        str(signing["path"]): value.get("signingReceiptSha256"),
        "NATIVE_WINDOWS_EVIDENCE.generated.json": value.get("nativeEvidenceSha256"),
        CANDIDATE_AUTHENTICODE_PATH: value.get("authenticodeVerificationSha256"),
        str(approval["path"]): value.get("approvalSha256"),
        visual_path: (
            value.get("visualApprovalSha256", [None])[0]
            if isinstance(value.get("visualApprovalSha256"), list)
            and len(value["visualApprovalSha256"]) == 1
            else None
        ),
    }
    if any(
        digest != hashlib.sha256(documents[path][1]).hexdigest()
        for path, digest in digest_bindings.items()
    ) or any(
        scope.get(key) != value.get(key)
        for key in (
            "scopeDecisionSha256",
            "signingReceiptSha256",
            "nativeEvidenceSha256",
            "authenticodeVerificationSha256",
            "visualApprovalSha256",
        )
    ):
        raise ProjectionBlocked("candidate finalized publication evidence digest aliases drifted")
    if approval.get("sha256") != value.get("approvalSha256"):
        raise ProjectionBlocked("candidate finalized publication approval digest drifted")
    actors = value.get("actors")
    if not isinstance(actors, dict) or set(actors) != {
        "candidateProducer",
        "nativeCapture",
        "visualReviewer",
        "scopeApprover",
    }:
        raise ProjectionBlocked("candidate finalized publication actor set drifted")
    actor_values = list(actors.values())
    if any(
        not isinstance(actor, str) or CANDIDATE_GITHUB_LOGIN_RE.fullmatch(actor) is None
        for actor in actor_values
    ):
        raise ProjectionBlocked("candidate finalized publication actors are invalid")
    review_owner = str(actors["scopeApprover"]).lower()
    if (
        str(actors["visualReviewer"]).lower() != review_owner
        or str(actors["candidateProducer"]).lower() == review_owner
        or str(actors["nativeCapture"]).lower() == review_owner
    ):
        raise ProjectionBlocked(
            "candidate finalized publication review owner is not independent"
        )
    native = documents["NATIVE_WINDOWS_EVIDENCE.generated.json"][0]
    native_candidate = native.get("candidateProvenance")
    native_candidate = (
        native_candidate.get("candidate") if isinstance(native_candidate, dict) else None
    )
    native_capture = native.get("captureSource")
    approval_document = documents[str(approval["path"])][0]
    visual_document = documents[visual_path][0]
    visual_review = visual_document.get("review")
    signing_document = documents[str(signing["path"])][0]
    authenticode_document = documents[CANDIDATE_AUTHENTICODE_PATH][0]
    finalization_document = documents[native_finalization_path][0]
    portable_visual_keys = {
        "artifactDigest",
        "artifactFileName",
        "authenticodeVerification",
        "captureBinding",
        "channel",
        "channelId",
        "checks",
        "clippingReview",
        "contractName",
        "contractVersion",
        "contrastReview",
        "finalizationBinding",
        "generatedAt",
        "head",
        "headId",
        "platform",
        "readabilityReview",
        "releaseVersion",
        "review",
        "rid",
        "screenshots",
        "status",
        "version",
    }
    native_wrapper_keys = {
        "archivePath",
        "archiveSha256",
        "authenticodeVerification",
        "candidateProvenance",
        "captureInventorySha256",
        "captureSource",
        "contractName",
        "contractVersion",
        "fileCount",
        "finalizationSha256",
        "finalizationSource",
        "finalizedInventorySha256",
        "githubActionsProvenance",
        "nativeFinalization",
        "progressLogSha256",
        "release",
        "scopeApproval",
        "startupReceiptSha256",
        "status",
        "treeSha256",
        "visualProof",
        "visualProofSha256",
        "visualReviewers",
    }
    if (
        set(native) != native_wrapper_keys
        or native.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-evidence"
        or native.get("contractVersion") != 1
        or native.get("status") != "passed"
        or native.get("release")
        != {"channel": "preview", "version": candidate["version"]}
        or native.get("captureInventorySha256")
        != native_package.get("captureInventorySha256")
        or documents[native_finalization_path][1]
        != native_package.get("finalizationBytes")
        or not isinstance(native_candidate, dict)
        or native_candidate != native_package.get("candidate")
        or native_candidate.get("actor") != actors["candidateProducer"]
        or not isinstance(native_capture, dict)
        or native_capture.get("actor") != actors["nativeCapture"]
        or native.get("nativeFinalization")
        != {
            "path": native_finalization_path,
            "sha256": hashlib.sha256(documents[native_finalization_path][1]).hexdigest(),
            "sizeBytes": len(documents[native_finalization_path][1]),
        }
        or native.get("visualProof")
        != {
            "path": visual_path,
            "sha256": hashlib.sha256(documents[visual_path][1]).hexdigest(),
            "sizeBytes": len(documents[visual_path][1]),
        }
        or native.get("visualProofSha256")
        != {"avalonia": hashlib.sha256(documents[visual_path][1]).hexdigest()}
        or native.get("visualReviewers")
        != {"avalonia": actors["visualReviewer"]}
        or finalization_document.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-finalization"
        or finalization_document.get("contractVersion") != 2
        or finalization_document.get("status") != "passed"
        or finalization_document.get("reviewer") != actors["scopeApprover"]
        or approval_document.get("contractName")
        != "chummer6-ui.preview-nightly-windows-publication-approval"
        or approval_document.get("contractVersion") != 2
        or approval_document.get("status") != "approved"
        or approval_document.get("approver") != actors["scopeApprover"]
        or not isinstance(visual_review, dict)
        or visual_document.get("status") != "passed"
        or visual_review.get("authenticatedReviewer") != actors["visualReviewer"]
        or signing_document.get("contractName")
        != "chummer6-ui.desktop_artifact_signing"
        or signing_document.get("contractVersion") != 2
        or signing_document.get("signingStatus") != "pass"
        or authenticode_document.get("contractName")
        != "chummer6-ui.windows-authenticode-verification"
        or authenticode_document.get("contractVersion") != 1
        or authenticode_document.get("status") != "verified"
    ):
        raise ProjectionBlocked("candidate finalized native/signing/approval evidence drifted")

    wrapper_auth = native.get("authenticodeVerification")
    wrapper_finalization = native.get("finalizationSource")
    wrapper_capture_inventory = native.get("captureInventorySha256")
    expected_capture_binding = (
        {
            key: native_capture[key]
            for key in (
                "repository",
                "workflow",
                "runId",
                "runAttempt",
                "ref",
                "sha",
                "artifactName",
            )
        }
        if isinstance(native_capture, dict)
        else None
    )
    if isinstance(expected_capture_binding, dict):
        expected_capture_binding["inventorySha256"] = wrapper_capture_inventory
    expected_review = {
        "allowlistSource": "repository variable plus protected environment",
        "authenticatedReviewer": actors["visualReviewer"],
        "captureActor": actors["nativeCapture"],
        "explicitConfirmations": {
            "clipping": "passed",
            "contrast": "passed",
            "readability": "passed",
        },
    }
    expected_review_result = {
        "reviewer": actors["visualReviewer"],
        "status": "passed",
    }
    installer = delta[0]
    screenshots = visual_document.get("screenshots")
    if (
        set(visual_document) != portable_visual_keys
        or visual_document.get("contractName")
        != "chummer6-ui.windows_installer_visual_proof"
        or type(visual_document.get("contractVersion")) is not int
        or visual_document.get("contractVersion") != 1
        or visual_document.get("status") != "passed"
        or visual_document.get("version") != candidate["version"]
        or visual_document.get("releaseVersion") != candidate["version"]
        or visual_document.get("channel") != "preview"
        or visual_document.get("channelId") != "preview"
        or visual_document.get("platform") != "windows"
        or visual_document.get("head") != "avalonia"
        or visual_document.get("headId") != "avalonia"
        or visual_document.get("rid") != CANDIDATE_RID
        or visual_document.get("artifactFileName") != installer.get("fileName")
        or visual_document.get("artifactDigest")
        != f"sha256:{installer.get('sha256')}"
        or visual_document.get("checks")
        != {"capture_mode": "interactive", "human_review_confirmed": True}
        or visual_document.get("readabilityReview") != expected_review_result
        or visual_document.get("contrastReview") != expected_review_result
        or visual_document.get("clippingReview") != expected_review_result
        or visual_document.get("review") != expected_review
        or visual_document.get("captureBinding") != expected_capture_binding
        or visual_document.get("finalizationBinding") != wrapper_finalization
        or visual_document.get("authenticodeVerification") != wrapper_auth
        or not isinstance(visual_document.get("generatedAt"), str)
        or not str(visual_document["generatedAt"]).endswith("Z")
        or not isinstance(screenshots, list)
        or len(screenshots) != 2
    ):
        raise ProjectionBlocked("candidate portable Windows visual proof drifted")
    screenshot_digests: set[str] = set()
    raw_visuals = native_package.get("visualProofs")
    raw_visual = raw_visuals.get("avalonia") if isinstance(raw_visuals, dict) else None
    raw_screenshots = raw_visual.get("screenshots") if isinstance(raw_visual, dict) else None
    if not isinstance(raw_screenshots, list) or len(raw_screenshots) != 2:
        raise ProjectionBlocked("candidate raw Windows visual screenshot set drifted")
    for screenshot, role in zip(screenshots, ("progress", "completion"), strict=True):
        expected_path = (
            "proof/windows-native/screenshots/"
            f"windows-installer-avalonia-{CANDIDATE_RID}-{role}.png"
        )
        if (
            not isinstance(screenshot, dict)
            or set(screenshot) != {"path", "role", "sha256"}
            or screenshot.get("role") != role
            or screenshot.get("path") != expected_path
            or not isinstance(screenshot.get("sha256"), str)
            or SHA256_RE.fullmatch(screenshot["sha256"]) is None
            or screenshot["sha256"] in screenshot_digests
            or not isinstance(raw_screenshots[0 if role == "progress" else 1], dict)
            or raw_screenshots[0 if role == "progress" else 1].get("role") != role
            or raw_screenshots[0 if role == "progress" else 1].get("sha256")
            != screenshot.get("sha256")
        ):
            raise ProjectionBlocked(
                "candidate portable Windows visual screenshot binding drifted"
            )
        screenshot_digests.add(screenshot["sha256"])
    return scope, scope_raw, documents


def _validate_candidate_registry_graph(
    *,
    candidate_receipt: dict[str, object],
    candidate_receipt_raw: bytes,
    registry_authority: dict[str, object],
    registry_authority_raw: bytes,
    finalize: dict[str, object],
    finalize_raw: bytes,
    registry_summary: object,
    canonical_raw: bytes,
    compatibility_raw: bytes,
    scope: dict[str, object],
    scope_raw: bytes,
    evidence_documents: dict[str, tuple[dict[str, object], bytes]],
    candidate: dict[str, object],
) -> None:
    candidate_keys = {
        "canonicalManifest", "channel", "compatibilityManifest", "compositionInput",
        "compositionInputDocument", "contractName", "contractVersion", "deltaPlatforms",
        "deployAuthority", "evidencePlatforms", "fullShelfInventory",
        "fullShelfInventorySha256", "incumbentDesktopTupleSetSha256",
        "incumbentCanonicalManifestBytesBase64", "incumbentSnapshotSha256",
        "nonPublishedEvidenceTupleSetSha256", "postPublicationTupleSetSha256",
        "publicationDeltaTupleSetSha256", "publicationEligible", "publicationStatus",
        "registryProjectionInputs", "releaseUploadAuthority", "routeAuthority",
        "releaseVersion", "retainedPlatforms", "retainedTupleSetSha256", "shelfPlatforms",
    }
    if (
        set(candidate_receipt) != candidate_keys
        or candidate_receipt_raw != _canonical_json_bytes(candidate_receipt)
        or candidate_receipt.get("contractName")
        != "chummer.registry.preview-publication-delta-candidate"
        or type(candidate_receipt.get("contractVersion")) is not int
        or candidate_receipt.get("contractVersion") != 1
        or candidate_receipt.get("channel") != "preview"
        or candidate_receipt.get("releaseVersion") != candidate["version"]
        or candidate_receipt.get("publicationStatus") != "review_required"
        or candidate_receipt.get("deltaPlatforms") != ["windows"]
        or candidate_receipt.get("evidencePlatforms") != ["linux"]
        or any(
            candidate_receipt.get(key) is not False
            for key in (
                "publicationEligible", "releaseUploadAuthority", "deployAuthority", "routeAuthority"
            )
        )
    ):
        raise ProjectionBlocked("Registry PREPARE candidate receipt contract drifted")
    _candidate_reference(
        candidate_receipt.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="Registry candidate canonical manifest",
    )
    _candidate_reference(
        candidate_receipt.get("compatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="Registry candidate compatibility manifest",
    )
    full_inventory = candidate_receipt.get("fullShelfInventory")
    if (
        not isinstance(full_inventory, list)
        or candidate_receipt.get("fullShelfInventorySha256")
        != _candidate_canonical_sha256(full_inventory)
        or full_inventory
        != [
            {
                "mode": f"{row['mode']:04o}",
                "path": row["path"],
                "sha256": row["sha256"],
                "sizeBytes": row["sizeBytes"],
            }
            for row in scope.get("fullShelfInventory", [])
        ]
    ):
        raise ProjectionBlocked("Registry PREPARE candidate shelf inventory drifted")
    prepare = scope.get("registryPrepare")
    if (
        not isinstance(prepare, dict)
        or prepare.get("candidateReceiptSha256")
        != hashlib.sha256(candidate_receipt_raw).hexdigest()
        or prepare.get("status") != "review_required"
        or prepare.get("finalizeAvailable") is not True
        or prepare.get("finalizeReceipt") is not None
        or prepare.get("wholeDirectoryVerified") is not True
        or any(
            prepare.get(key) is not False
            for key in (
                "publicationEligible", "releaseUploadAuthority", "deployAuthority", "routeAuthority"
            )
        )
    ):
        raise ProjectionBlocked("final UI scope Registry PREPARE binding drifted")

    authority_keys = {
        "candidateImportAuthority", "candidateReceipt", "candidateReviewAuthority",
        "canonicalManifest", "channel", "compatibilityManifest", "compositionInputSha256",
        "contractName", "contractVersion", "deltaPlatforms", "deployAuthority",
        "dispositions", "evidence", "evidencePlatforms", "fullShelfInventorySha256",
        "incumbentSnapshotSha256", "nonPublishedEvidenceTupleSetSha256",
        "postPublicationTupleSetSha256", "publicationDeltaTupleSetSha256",
        "publicationEligible", "releaseUploadAuthority", "releaseVersion",
        "retainedPlatforms", "retainedTupleSetSha256", "routeAuthority", "scope",
        "shelfPlatforms", "sourceScope",
    }
    if (
        set(registry_authority) != authority_keys
        or registry_authority_raw != _canonical_json_bytes(registry_authority)
        or registry_authority.get("contractName")
        != "chummer.registry.preview-publication-delta-authority"
        or type(registry_authority.get("contractVersion")) is not int
        or registry_authority.get("contractVersion") != 1
        or registry_authority.get("candidateImportAuthority") is not True
        or registry_authority.get("candidateReviewAuthority") is not True
        or registry_authority.get("channel") != "preview"
        or registry_authority.get("releaseVersion") != candidate["version"]
        or registry_authority.get("deltaPlatforms") != ["windows"]
        or registry_authority.get("evidencePlatforms") != ["linux"]
        or registry_authority.get("scope") != "windows_only"
        or any(
            registry_authority.get(key) is not False
            for key in (
                "publicationEligible", "releaseUploadAuthority", "deployAuthority", "routeAuthority"
            )
        )
    ):
        raise ProjectionBlocked("Registry FINALIZE candidate authority contract drifted")
    for key in (
        "fullShelfInventorySha256", "incumbentSnapshotSha256",
        "nonPublishedEvidenceTupleSetSha256", "postPublicationTupleSetSha256",
        "publicationDeltaTupleSetSha256", "retainedPlatforms", "retainedTupleSetSha256",
        "shelfPlatforms",
    ):
        if registry_authority.get(key) != candidate_receipt.get(key):
            raise ProjectionBlocked("Registry FINALIZE/PREPARE digest graph drifted")
    _candidate_reference(
        registry_authority.get("candidateReceipt"),
        path=CANDIDATE_REGISTRY_RECEIPT_FILE,
        raw=candidate_receipt_raw,
        label="Registry authority candidate receipt",
    )
    _candidate_reference(
        registry_authority.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="Registry authority canonical manifest",
    )
    _candidate_reference(
        registry_authority.get("compatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="Registry authority compatibility manifest",
    )
    _candidate_reference(
        registry_authority.get("sourceScope"),
        path=CANDIDATE_PUBLICATION_SCOPE_FILE,
        raw=scope_raw,
        label="Registry authority final scope",
    )
    dispositions = registry_authority.get("dispositions")
    if (
        not isinstance(dispositions, list)
        or not dispositions
        or sum(
            isinstance(row, dict)
            and row.get("disposition") == "delta"
            and row.get("platform") == "windows"
            and row.get("rid") == CANDIDATE_RID
            for row in dispositions
        )
        != 1
        or any(
            not isinstance(row, dict)
            or row.get("disposition") not in {"delta", "retained_incumbent"}
            or row.get("disposition") == "retained_incumbent"
            and row.get("platform") not in {"linux", "macos"}
            for row in dispositions
        )
    ):
        raise ProjectionBlocked("Registry FINALIZE artifact dispositions drifted")
    evidence = registry_authority.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {
        "approval", "nativeEvidence", "signingReceipt", "visualEvidence"
    }:
        raise ProjectionBlocked("Registry FINALIZE evidence set drifted")
    evidence_paths = {
        "approval": scope["approval"]["path"],
        "nativeEvidence": "NATIVE_WINDOWS_EVIDENCE.generated.json",
        "signingReceipt": scope["signingReceipt"]["path"],
    }
    for key, path in evidence_paths.items():
        _candidate_reference(
            evidence.get(key), path=path, raw=evidence_documents[path][1],
            label=f"Registry evidence {key}",
        )
    visual_path = f"WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-{CANDIDATE_RID}.generated.json"
    visual_refs = evidence.get("visualEvidence")
    if not isinstance(visual_refs, list) or len(visual_refs) != 1:
        raise ProjectionBlocked("Registry FINALIZE visual evidence set drifted")
    _candidate_reference(
        visual_refs[0], path=visual_path, raw=evidence_documents[visual_path][1],
        label="Registry visual evidence",
    )

    finalize_keys = {
        "authority", "candidateBytesMutated", "candidateImportAuthority",
        "candidateReceipt", "candidateReviewAuthority", "canonicalManifest", "channel",
        "compatibilityManifest", "contractName", "contractVersion", "deployAuthority",
        "fullShelfInventorySha256", "publicationEligible", "releaseUploadAuthority",
        "releaseVersion", "routeAuthority", "sourceScope", "verificationStatus",
    }
    if (
        set(finalize) != finalize_keys
        or finalize_raw != _canonical_json_bytes(finalize)
        or finalize.get("contractName") != "chummer.registry.preview-publication-delta-finalize"
        or type(finalize.get("contractVersion")) is not int
        or finalize.get("contractVersion") != 1
        or finalize.get("candidateBytesMutated") is not False
        or finalize.get("candidateImportAuthority") is not True
        or finalize.get("candidateReviewAuthority") is not True
        or finalize.get("channel") != "preview"
        or finalize.get("releaseVersion") != candidate["version"]
        or finalize.get("verificationStatus") != "finalized"
        or finalize.get("fullShelfInventorySha256")
        != candidate_receipt.get("fullShelfInventorySha256")
        or any(
            finalize.get(key) is not False
            for key in (
                "publicationEligible", "releaseUploadAuthority", "deployAuthority", "routeAuthority"
            )
        )
    ):
        raise ProjectionBlocked("Registry FINALIZE receipt contract drifted")
    for key, path, raw in (
        ("authority", CANDIDATE_REGISTRY_AUTHORITY_FILE, registry_authority_raw),
        ("candidateReceipt", CANDIDATE_REGISTRY_RECEIPT_FILE, candidate_receipt_raw),
        ("canonicalManifest", "RELEASE_CHANNEL.generated.json", canonical_raw),
        ("compatibilityManifest", "releases.json", compatibility_raw),
        ("sourceScope", CANDIDATE_PUBLICATION_SCOPE_FILE, scope_raw),
    ):
        _candidate_reference(finalize.get(key), path=path, raw=raw, label=f"Registry finalize {key}")
    expected_summary = {
        "status": "finalized",
        "candidateImportAuthority": True,
        "candidateReviewAuthority": True,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": False,
        "scope": "windows_only",
        "exactIncomingDesktopScope": CANDIDATE_EXACT_SCOPE,
        "candidateReceiptSha256": hashlib.sha256(candidate_receipt_raw).hexdigest(),
        "authoritySha256": hashlib.sha256(registry_authority_raw).hexdigest(),
        "finalizeReceiptSha256": hashlib.sha256(finalize_raw).hexdigest(),
    }
    if registry_summary != expected_summary:
        raise ProjectionBlocked("Registry finalization custody summary drifted")


def _candidate_unsigned_inventory(
    value: object,
    *,
    label: str,
    retained: bool = False,
) -> list[dict[str, object]]:
    if not isinstance(value, list) or (not value and not retained):
        raise ProjectionBlocked(f"{label} is invalid")
    expected_keys = {"mode", "path", "sha256", "sizeBytes"}
    if retained:
        expected_keys.add("retentionKind")
    rows: list[dict[str, object]] = []
    previous = ""
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != expected_keys:
            raise ProjectionBlocked(f"{label} row property set drifted")
        path = _candidate_relative_path(raw.get("path"), label=f"{label} path")
        mode = raw.get("mode")
        size = raw.get("sizeBytes")
        digest = raw.get("sha256")
        if (
            path <= previous
            or isinstance(mode, bool)
            or not isinstance(mode, int)
            or not 0 <= mode <= 0o777
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or SHA256_RE.fullmatch(str(digest or "")) is None
            or retained
            and raw.get("retentionKind") not in {"managed_artifact", "ancillary"}
        ):
            raise ProjectionBlocked(f"{label} row is invalid")
        rows.append(dict(raw))
        previous = path
    return rows


def _candidate_pretty_sha256(value: object) -> str:
    return hashlib.sha256(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()


def _candidate_unsigned_directory_modes(
    value: object,
    *,
    label: str,
) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or len(value) > 100_000:
        raise ProjectionBlocked(f"{label} is invalid")
    rows: list[dict[str, object]] = []
    previous = ""
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {"mode", "path"}:
            raise ProjectionBlocked(f"{label} row property set drifted")
        path = _candidate_relative_path(raw.get("path"), label=f"{label} path")
        mode = raw.get("mode")
        if (
            path <= previous
            or isinstance(mode, bool)
            or not isinstance(mode, int)
            or not 0 <= mode <= 0o777
        ):
            raise ProjectionBlocked(f"{label} row is invalid")
        rows.append({"mode": mode, "path": path})
        previous = path
    return rows


def _candidate_unsigned_projection_inputs(value: object) -> None:
    expected_paths = {
        "materializer": "scripts/materialize_unsigned_preview_publication_delta.py",
        "schema": "contracts/preview-publication-delta-v2.schema.json",
    }
    if not isinstance(value, dict) or set(value) != set(expected_paths):
        raise ProjectionBlocked("unsigned Registry projection inputs drifted")
    for name, path in expected_paths.items():
        reference = value.get(name)
        if (
            not isinstance(reference, dict)
            or set(reference) != {"path", "sha256", "sizeBytes"}
            or reference.get("path") != path
            or SHA256_RE.fullmatch(str(reference.get("sha256") or "")) is None
            or isinstance(reference.get("sizeBytes"), bool)
            or not isinstance(reference.get("sizeBytes"), int)
            or reference["sizeBytes"] < 1
        ):
            raise ProjectionBlocked(
                f"unsigned Registry projection input {name} drifted"
            )


def _candidate_unheld_reference(
    value: object,
    *,
    path: str,
    label: str,
) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "sha256", "sizeBytes"}
        or value.get("path") != path
        or SHA256_RE.fullmatch(str(value.get("sha256") or "")) is None
        or isinstance(value.get("sizeBytes"), bool)
        or not isinstance(value.get("sizeBytes"), int)
        or value["sizeBytes"] < 1
    ):
        raise ProjectionBlocked(f"{label} byte reference drifted")


def _candidate_unsigned_provenance(
    documents: Mapping[str, bytes],
    *,
    source_sha: str,
    version: str,
) -> None:
    paths = {
        "packagePlaneLock": "provenance/config/package-plane.lock.json",
        "packagePlaneReceipt": "provenance/UI_FRESH_PACKAGE_PLANE.generated.json",
        "retainedManifest": (
            "provenance/retained-windows-publish-closure/manifest.json"
        ),
        "nativeToolchainLock": (
            "provenance/config/windows-native-bootstrap-toolchain.lock.json"
        ),
    }
    parsed = {
        name: _strict_json_object(
            documents[path], label=f"candidate unsigned {name}"
        )
        for name, path in paths.items()
    }
    lock = parsed["packagePlaneLock"]
    if (
        lock.get("contractName") != "chummer6-ui.fresh-package-plane-lock"
        or type(lock.get("contractVersion")) is not int
        or lock.get("contractVersion") != 8
        or lock.get("approvedPackageSources") != ["same-run-local-feed"]
    ):
        raise ProjectionBlocked("candidate unsigned package-plane lock drifted")
    receipt = parsed["packagePlaneReceipt"]
    if (
        receipt.get("contractName")
        != "chummer6-ui.fresh-package-plane-verification"
        or type(receipt.get("contractVersion")) is not int
        or receipt.get("contractVersion") != 8
        or receipt.get("status") != "passed"
        or receipt.get("consumerCommit") != source_sha
        or receipt.get("mode") != "integration"
        or receipt.get("localCompatibilityTree") is not False
        or receipt.get("packageCacheWasFresh") is not True
        or receipt.get("stubPackagesAllowed") is not False
        or receipt.get("packageSources") != ["same-run-local-feed"]
    ):
        raise ProjectionBlocked("candidate unsigned package-plane receipt drifted")
    lock_raw = documents[paths["packagePlaneLock"]]
    lock_binding = {
        "sha256": hashlib.sha256(lock_raw).hexdigest(),
        "sizeBytes": len(lock_raw),
    }
    retained = parsed["retainedManifest"]
    expected_release = {"channel": "preview", "version": version}
    publish = retained.get("publish")
    release_eligibility = retained.get("releaseEligibility")
    if (
        receipt.get("consumerPackagePlaneLock") != lock_binding
        or retained.get("contractName")
        != "chummer6-ui.retained-windows-publish-closure"
        or type(retained.get("contractVersion")) is not int
        or retained.get("contractVersion") != 2
        or retained.get("status") != "passed"
        or retained.get("consumerCommit") != source_sha
        or retained.get("release") != expected_release
        or retained.get("packagePlaneLock") != lock_binding
        or retained.get("atomicallyRetained") is not True
        or retained.get("authoritative") is not True
        or retained.get("deterministicRepacking") is not False
        or not isinstance(release_eligibility, dict)
        or release_eligibility.get("eligible") is not False
        or not isinstance(publish, dict)
        or publish.get("status") != "passed"
        or publish.get("releaseChannel") != "preview"
        or publish.get("releaseVersion") != version
    ):
        raise ProjectionBlocked("candidate unsigned retained manifest drifted")
    pointer = receipt.get("retainedWindowsBundle")
    retained_raw = documents[paths["retainedManifest"]]
    if (
        not isinstance(pointer, dict)
        or pointer.get("contractName")
        != "chummer6-ui.retained-windows-publish-closure-pointer"
        or type(pointer.get("contractVersion")) is not int
        or pointer.get("contractVersion") != 2
        or pointer.get("status") != "passed"
        or pointer.get("consumerCommit") != source_sha
        or pointer.get("release") != expected_release
        or pointer.get("atomicallyRetained") is not True
        or pointer.get("authority") is not False
        or pointer.get("manifestIsAuthoritative") is not True
        or pointer.get("manifest")
        != {
            "sha256": hashlib.sha256(retained_raw).hexdigest(),
            "sizeBytes": len(retained_raw),
        }
    ):
        raise ProjectionBlocked("candidate unsigned retained pointer drifted")
    native = parsed["nativeToolchainLock"]
    snapshot = native.get("debian_snapshot")
    packages = native.get("packages")
    if (
        set(native)
        != {
            "container_image",
            "contract_name",
            "debian_snapshot",
            "packages",
            "platform",
            "schema_version",
        }
        or native.get("contract_name")
        != "chummer6-ui.windows_native_bootstrap_toolchain_lock"
        or type(native.get("schema_version")) is not int
        or native.get("schema_version") != 1
        or native.get("platform") != {"architecture": "amd64", "os": "linux"}
        or not isinstance(snapshot, dict)
        or snapshot.get("install_roots") != ["nsis", "p7zip-full"]
        or snapshot.get("include_recommends") is not False
        or not isinstance(packages, list)
        or not packages
        or any(
            not isinstance(row, dict)
            or SHA256_RE.fullmatch(str(row.get("sha256") or "")) is None
            or isinstance(row.get("size"), bool)
            or not isinstance(row.get("size"), int)
            or row["size"] < 1
            for row in packages
        )
    ):
        raise ProjectionBlocked("candidate unsigned native toolchain lock drifted")


def _validate_candidate_import_authority_v3(
    authority: dict[str, object],
) -> dict[str, object]:
    expected_root_keys = {
        "candidate",
        "candidateImportAuthority",
        "candidateReviewAuthority",
        "codeDeploymentAuthority",
        "contractName",
        "contractVersion",
        "crossRunBitReproducible",
        "custody",
        "deployAuthority",
        "exactIncomingDesktopScope",
        "expiresAtUtc",
        "generatedAtUtc",
        "platformScope",
        "publicationAuthorized",
        "publicationEligible",
        "releaseUploadAuthority",
        "routeAuthority",
        "signaturePolicy",
        "status",
    }
    signature_policy = {
        "signatureStatus": "unsigned",
        "signingRequired": False,
        "unsignedReason": "preview_policy",
    }
    if (
        set(authority) != expected_root_keys
        or authority.get("contractName") != CANDIDATE_AUTHORITY_CONTRACT_V3
        or type(authority.get("contractVersion")) is not int
        or authority.get("contractVersion") != 3
        or authority.get("status") != PROJECTION_STATUS_CANDIDATE_IMPORT_READY
        or authority.get("candidateImportAuthority") is not True
        or authority.get("candidateReviewAuthority") is not True
        or authority.get("exactIncomingDesktopScope") != CANDIDATE_EXACT_SCOPE
        or authority.get("platformScope") != "windows_only"
        or authority.get("crossRunBitReproducible") is not False
        or authority.get("signaturePolicy") != signature_policy
        or any(
            authority.get(key) is not False
            for key in (
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
                "codeDeploymentAuthority",
            )
        )
    ):
        raise ProjectionBlocked("unsigned candidate import authority contract drifted")
    try:
        generated_at = datetime.fromisoformat(
            str(authority.get("generatedAtUtc") or "").replace("Z", "+00:00")
        )
        expires_at = datetime.fromisoformat(
            str(authority.get("expiresAtUtc") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ProjectionBlocked("unsigned candidate authority timestamps are invalid") from exc
    now = datetime.now(timezone.utc)
    if (
        generated_at.utcoffset() != timezone.utc.utcoffset(generated_at)
        or expires_at.utcoffset() != timezone.utc.utcoffset(expires_at)
        or generated_at > now + timedelta(minutes=5)
        or generated_at < now - timedelta(hours=6, minutes=5)
        or expires_at <= now
        or expires_at > generated_at + timedelta(hours=6)
    ):
        raise ProjectionBlocked("unsigned candidate authority lifetime drifted")

    candidate = authority.get("candidate")
    candidate_keys = {
        "bundleIdentitySha256",
        "canonicalManifestSha256",
        "fileCount",
        "inventorySha256",
        "totalBytes",
        "version",
    }
    if not isinstance(candidate, dict) or set(candidate) != candidate_keys:
        raise ProjectionBlocked("unsigned candidate identity drifted")
    _candidate_version(candidate.get("version"), label="unsigned candidate version")
    if any(
        SHA256_RE.fullmatch(str(candidate.get(name) or "")) is None
        for name in (
            "bundleIdentitySha256",
            "canonicalManifestSha256",
            "inventorySha256",
        )
    ) or any(
        isinstance(candidate.get(name), bool)
        or not isinstance(candidate.get(name), int)
        or candidate[name] < minimum
        for name, minimum in (("fileCount", 1), ("totalBytes", 0))
    ):
        raise ProjectionBlocked("unsigned candidate summary drifted")
    identity = {
        key: candidate[key]
        for key in (
            "version",
            "canonicalManifestSha256",
            "inventorySha256",
            "fileCount",
            "totalBytes",
        )
    }
    if candidate.get("bundleIdentitySha256") != hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest():
        raise ProjectionBlocked("unsigned candidate bundle identity drifted")

    custody = authority.get("custody")
    custody_keys = {
        "canonicalManifest",
        "compatibilityManifest",
        "inventory",
        "registryFinalization",
        "registryFinalizeAuthority",
        "registryFinalizeReceipt",
        "registryPrepareCandidateReceipt",
        "unsignedPublicationEvidence",
    }
    if not isinstance(custody, dict) or set(custody) != custody_keys:
        raise ProjectionBlocked("unsigned candidate custody property set drifted")
    canonical_raw = _candidate_embedded_bytes(
        custody.get("canonicalManifest"),
        label="unsigned candidate canonical manifest",
        expected_path="RELEASE_CHANNEL.generated.json",
    )
    compatibility_raw = _candidate_embedded_bytes(
        custody.get("compatibilityManifest"),
        label="unsigned candidate compatibility manifest",
        expected_path="releases.json",
    )
    canonical = _strict_json_object(
        canonical_raw, label="unsigned candidate canonical manifest"
    )
    compatibility = _strict_json_object(
        compatibility_raw, label="unsigned candidate compatibility manifest"
    )
    if hashlib.sha256(canonical_raw).hexdigest() != candidate.get(
        "canonicalManifestSha256"
    ):
        raise ProjectionBlocked("unsigned candidate canonical digest drifted")
    inventory_raw = _candidate_embedded_bytes(
        custody.get("inventory"),
        label="unsigned candidate upload inventory",
        expected_path="CANDIDATE_UPLOAD_INVENTORY.generated.json",
    )
    inventory = _strict_json_object(
        inventory_raw, label="unsigned candidate upload inventory"
    )
    if (
        set(inventory) != {"contractName", "contractVersion", "files"}
        or inventory.get("contractName")
        != "chummer.release-upload.candidate-inventory/v1"
        or type(inventory.get("contractVersion")) is not int
        or inventory.get("contractVersion") != 1
    ):
        raise ProjectionBlocked("unsigned candidate upload inventory contract drifted")
    candidate_rows = _candidate_inventory_rows(
        inventory.get("files"), label="unsigned candidate upload inventory"
    )
    inventory_digest = hashlib.sha256()
    for row in candidate_rows:
        path = str(row["path"])
        encoded = path.encode("utf-8")
        inventory_digest.update(len(encoded).to_bytes(8, "big"))
        inventory_digest.update(encoded)
        inventory_digest.update(int(row["sizeBytes"]).to_bytes(8, "big"))
        inventory_digest.update(bytes.fromhex(str(row["sha256"])))
    if (
        len(candidate_rows) != candidate.get("fileCount")
        or sum(int(row["sizeBytes"]) for row in candidate_rows)
        != candidate.get("totalBytes")
        or inventory_digest.hexdigest() != candidate.get("inventorySha256")
    ):
        raise ProjectionBlocked("unsigned candidate upload inventory summary drifted")
    candidate_by_path = {str(row["path"]): row for row in candidate_rows}
    if candidate_by_path.get("RELEASE_CHANNEL.generated.json") != {
        "path": "RELEASE_CHANNEL.generated.json",
        "sha256": hashlib.sha256(canonical_raw).hexdigest(),
        "sizeBytes": len(canonical_raw),
    } or candidate_by_path.get("releases.json") != {
        "path": "releases.json",
        "sha256": hashlib.sha256(compatibility_raw).hexdigest(),
        "sizeBytes": len(compatibility_raw),
    }:
        raise ProjectionBlocked("unsigned candidate manifest inventory custody drifted")
    canonical_scope = _candidate_windows_scope(
        canonical,
        candidate_rows,
        candidate,
        allow_ancillary_files=True,
        expected_channel="preview",
    )
    compatibility_version = _candidate_version(
        _candidate_manifest_alias(
            compatibility,
            "version",
            "releaseVersion",
            label="unsigned candidate compatibility release version",
        ),
        label="unsigned candidate compatibility release version",
    )
    compatibility_channel = _candidate_manifest_alias(
        compatibility,
        "channelId",
        "channel",
        label="unsigned candidate compatibility release channel",
    )
    if (
        compatibility_version != candidate["version"]
        or compatibility_channel != "preview"
    ):
        raise ProjectionBlocked(
            "unsigned candidate compatibility release identity drifted"
        )

    evidence = custody.get("unsignedPublicationEvidence")
    evidence_keys = {
        "crossRunBitReproducible",
        "exactIncomingDesktopScope",
        "files",
        "freshDeltaSha256",
        "fullShelfInventorySha256",
        "incumbentInventorySha256",
        "platformScope",
        "provenance",
        "publicationScopeSha256",
        "retainedInventorySha256",
        "signaturePolicy",
        "sourceSha",
        "status",
    }
    if (
        not isinstance(evidence, dict)
        or set(evidence) != evidence_keys
        or evidence.get("status") != "passed"
        or evidence.get("exactIncomingDesktopScope") != CANDIDATE_EXACT_SCOPE
        or evidence.get("platformScope") != "windows_only"
        or evidence.get("crossRunBitReproducible") is not False
        or evidence.get("signaturePolicy") != signature_policy
        or CANDIDATE_COMMIT_RE.fullmatch(str(evidence.get("sourceSha") or ""))
        is None
        or not isinstance(evidence.get("files"), list)
    ):
        raise ProjectionBlocked("unsigned candidate evidence posture drifted")
    evidence_documents: dict[str, bytes] = {}
    for reference in evidence["files"]:
        if not isinstance(reference, dict):
            raise ProjectionBlocked("unsigned candidate evidence entry drifted")
        path = _candidate_relative_path(
            reference.get("path"), label="unsigned candidate evidence path"
        )
        if path in evidence_documents:
            raise ProjectionBlocked("unsigned candidate evidence path is duplicated")
        evidence_documents[path] = _candidate_embedded_bytes(
            reference,
            label=f"unsigned candidate evidence {path}",
            expected_path=path,
        )
    provenance_paths = {
        "packagePlaneLock": "provenance/config/package-plane.lock.json",
        "packagePlaneReceipt": "provenance/UI_FRESH_PACKAGE_PLANE.generated.json",
        "retainedManifest": (
            "provenance/retained-windows-publish-closure/manifest.json"
        ),
        "nativeToolchainLock": (
            "provenance/config/windows-native-bootstrap-toolchain.lock.json"
        ),
    }
    expected_evidence_paths = {
        CANDIDATE_UNSIGNED_SCOPE_FILE,
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        *provenance_paths.values(),
    }
    if set(evidence_documents) != expected_evidence_paths:
        raise ProjectionBlocked("unsigned candidate evidence file scope drifted")
    if (
        evidence_documents["RELEASE_CHANNEL.generated.json"] != canonical_raw
        or evidence_documents["releases.json"] != compatibility_raw
    ):
        raise ProjectionBlocked("unsigned candidate duplicate manifest custody drifted")
    scope_raw = evidence_documents[CANDIDATE_UNSIGNED_SCOPE_FILE]
    scope = _strict_json_object(scope_raw, label="unsigned candidate UI scope")
    if scope_raw != (
        json.dumps(scope, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8"):
        raise ProjectionBlocked("unsigned candidate UI scope serialization drifted")
    scope_keys = {
        "compatibilityManifest",
        "contractName",
        "contractVersion",
        "crossRunBitReproducible",
        "deployAuthorized",
        "freshDelta",
        "fullShelfInventory",
        "fullShelfInventorySha256",
        "incumbentInventorySha256",
        "platformScope",
        "provenance",
        "publicationAuthorized",
        "publicationManifest",
        "release",
        "retainedFromIncumbent",
        "signature",
        "sourceSha",
        "status",
        "uploadAuthorized",
    }
    signature = {"policy": "preview_policy", "required": False, "status": "unsigned"}
    if (
        set(scope) != scope_keys
        or scope.get("contractName")
        != "chummer6-ui.preview-nightly-unsigned-publication-scope"
        or type(scope.get("contractVersion")) is not int
        or scope.get("contractVersion") != 3
        or scope.get("status") != "prepared"
        or scope.get("release")
        != {"channel": "preview", "version": candidate["version"]}
        or scope.get("platformScope") != "windows_only"
        or scope.get("crossRunBitReproducible") is not False
        or scope.get("signature") != signature
        or scope.get("sourceSha") != evidence.get("sourceSha")
        or any(
            scope.get(key) is not False
            for key in (
                "publicationAuthorized",
                "uploadAuthorized",
                "deployAuthorized",
            )
        )
    ):
        raise ProjectionBlocked("unsigned candidate UI scope posture drifted")
    _candidate_reference(
        scope.get("publicationManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="unsigned UI publication manifest",
    )
    _candidate_reference(
        scope.get("compatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="unsigned UI compatibility manifest",
    )
    scope_provenance = scope.get("provenance")
    if not isinstance(scope_provenance, dict) or set(scope_provenance) != set(
        provenance_paths
    ):
        raise ProjectionBlocked("unsigned UI provenance property set drifted")
    for name, path in provenance_paths.items():
        raw = evidence_documents[path]
        if scope_provenance.get(name) != {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sizeBytes": len(raw),
        }:
            raise ProjectionBlocked("unsigned UI provenance byte binding drifted")
    _candidate_unsigned_provenance(
        evidence_documents,
        source_sha=str(scope["sourceSha"]),
        version=str(candidate["version"]),
    )

    full_inventory = _candidate_unsigned_inventory(
        scope.get("fullShelfInventory"), label="unsigned UI full shelf inventory"
    )
    full_by_path = {str(row["path"]): row for row in full_inventory}
    if (
        scope.get("fullShelfInventorySha256")
        != _candidate_ui_compact_sha256(full_inventory)
        or evidence.get("fullShelfInventorySha256")
        != scope.get("fullShelfInventorySha256")
        or evidence.get("incumbentInventorySha256")
        != scope.get("incumbentInventorySha256")
        or set(full_by_path) != set(candidate_by_path)
        or any(
            {
                "path": path,
                "sha256": row["sha256"],
                "sizeBytes": row["sizeBytes"],
            }
            != candidate_by_path[path]
            for path, row in full_by_path.items()
        )
    ):
        raise ProjectionBlocked("unsigned UI full shelf inventory drifted")
    fresh = scope.get("freshDelta")
    if not isinstance(fresh, list) or len(fresh) != 2:
        raise ProjectionBlocked("unsigned UI fresh Windows delta drifted")
    expected_roles = (("installer", "installer"), ("bootstrap_payload", "payload"))
    for row, (role, canonical_role) in zip(fresh, expected_roles, strict=True):
        expected = canonical_scope["artifacts"]["avalonia"][canonical_role]
        full = full_by_path[str(expected["path"])]
        if row != {
            "artifactRole": role,
            "fileName": expected["fileName"],
            "head": "avalonia",
            "mode": full["mode"],
            "path": expected["path"],
            "platform": "windows",
            "rid": CANDIDATE_RID,
            "sha256": expected["sha256"],
            "sizeBytes": expected["sizeBytes"],
        }:
            raise ProjectionBlocked("unsigned UI fresh Windows delta byte drifted")
    if [row.get("fileName") for row in fresh if isinstance(row, dict)] != [
        "chummer-avalonia-win-x64-installer.exe",
        "chummer-avalonia-win-x64-payload.zip",
    ]:
        raise ProjectionBlocked("unsigned UI fresh Windows filenames drifted")
    retained = _candidate_unsigned_inventory(
        scope.get("retainedFromIncumbent"),
        label="unsigned UI retained inventory",
        retained=True,
    )
    reserved = {
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        *(str(row["path"]) for row in fresh),
    }
    retained_by_path = {str(row["path"]): row for row in retained}
    if set(full_by_path) != {*reserved, *retained_by_path} or set(
        retained_by_path
    ) & reserved:
        raise ProjectionBlocked("unsigned UI retained/fresh inventory partition drifted")
    managed = set(canonical_scope["manifestArtifactPaths"]) - {
        str(row["path"]) for row in fresh
    }
    for path, row in retained_by_path.items():
        full = full_by_path[path]
        if any(full[key] != row[key] for key in ("mode", "sha256", "sizeBytes")) or row[
            "retentionKind"
        ] != ("managed_artifact" if path in managed else "ancillary"):
            raise ProjectionBlocked("unsigned UI retained byte classification drifted")
    if not managed.issubset(retained_by_path):
        raise ProjectionBlocked("unsigned UI retained managed inventory is incomplete")
    if (
        evidence.get("publicationScopeSha256")
        != hashlib.sha256(scope_raw).hexdigest()
        or evidence.get("freshDeltaSha256")
        != _candidate_ui_compact_sha256(fresh)
        or evidence.get("retainedInventorySha256")
        != _candidate_ui_compact_sha256(retained)
        or evidence.get("provenance") != scope_provenance
    ):
        raise ProjectionBlocked("unsigned candidate evidence digest graph drifted")

    registry_candidate_raw = _candidate_embedded_bytes(
        custody.get("registryPrepareCandidateReceipt"),
        label="unsigned Registry PREPARE candidate receipt",
        expected_path=CANDIDATE_REGISTRY_RECEIPT_FILE,
    )
    registry_authority_raw = _candidate_embedded_bytes(
        custody.get("registryFinalizeAuthority"),
        label="unsigned Registry FINALIZE authority",
        expected_path=CANDIDATE_REGISTRY_AUTHORITY_FILE,
    )
    registry_finalize_raw = _candidate_embedded_bytes(
        custody.get("registryFinalizeReceipt"),
        label="unsigned Registry FINALIZE receipt",
        expected_path=CANDIDATE_REGISTRY_FINALIZE_FILE,
    )
    registry_candidate = _strict_json_object(
        registry_candidate_raw, label="unsigned Registry PREPARE candidate receipt"
    )
    registry_authority = _strict_json_object(
        registry_authority_raw, label="unsigned Registry FINALIZE authority"
    )
    registry_finalize = _strict_json_object(
        registry_finalize_raw, label="unsigned Registry FINALIZE receipt"
    )
    if any(
        raw != _canonical_json_bytes(document)
        for raw, document in (
            (registry_candidate_raw, registry_candidate),
            (registry_authority_raw, registry_authority),
            (registry_finalize_raw, registry_finalize),
        )
    ):
        raise ProjectionBlocked("unsigned Registry receipts are not canonical JSON")
    candidate_keys = {
        "canonicalManifest",
        "channel",
        "codeDeploymentAuthority",
        "compatibilityManifest",
        "compositionInput",
        "compositionInputDocument",
        "contractName",
        "contractVersion",
        "crossRunBitReproducible",
        "deltaPlatforms",
        "deployAuthority",
        "evidencePlatforms",
        "fullShelfInventory",
        "fullShelfInventorySha256",
        "incumbentDirectoryModesSha256",
        "incumbentInventorySha256",
        "incumbentSnapshotSha256",
        "platformScope",
        "projectionInputs",
        "proposedDirectoryModesSha256",
        "provenance",
        "publicationAuthorized",
        "publicationEligible",
        "publicationStatus",
        "releaseUploadAuthority",
        "releaseVersion",
        "retainedInventorySha256",
        "retainedPlatforms",
        "routeAuthority",
        "shelfPlatforms",
        "signaturePolicy",
        "sourceSha",
        "windowsDelta",
    }
    if (
        set(registry_candidate) != candidate_keys
        or registry_candidate.get("contractName")
        != "chummer.registry.preview-publication-delta-candidate"
        or type(registry_candidate.get("contractVersion")) is not int
        or registry_candidate.get("contractVersion") != 2
        or registry_candidate.get("channel") != "preview"
        or registry_candidate.get("releaseVersion") != candidate["version"]
        or registry_candidate.get("publicationStatus") != "review_required"
        or registry_candidate.get("platformScope") != "windows_only"
        or registry_candidate.get("crossRunBitReproducible") is not False
        or registry_candidate.get("signaturePolicy") != signature_policy
        or registry_candidate.get("sourceSha") != scope["sourceSha"]
        or registry_candidate.get("deltaPlatforms") != ["windows"]
        or registry_candidate.get("evidencePlatforms") != []
        or any(
            registry_candidate.get(key) is not False
            for key in (
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
                "codeDeploymentAuthority",
            )
        )
    ):
        raise ProjectionBlocked("unsigned Registry PREPARE v2 posture drifted")
    _candidate_reference(
        registry_candidate.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="unsigned Registry candidate canonical manifest",
    )
    _candidate_reference(
        registry_candidate.get("compatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="unsigned Registry candidate compatibility manifest",
    )
    if (
        registry_candidate.get("fullShelfInventory") != full_inventory
        or registry_candidate.get("fullShelfInventorySha256")
        != _candidate_ui_compact_sha256(full_inventory)
    ):
        raise ProjectionBlocked("unsigned Registry PREPARE shelf inventory drifted")

    composition = registry_candidate.get("compositionInputDocument")
    composition_keys = {
        "contractName",
        "contractVersion",
        "crossRunBitReproducible",
        "deployAuthorized",
        "freshDelta",
        "incumbentSnapshot",
        "platformScope",
        "proposedCanonicalManifest",
        "proposedCompatibilityManifest",
        "proposedDirectoryModes",
        "proposedDirectoryModesSha256",
        "proposedShelfInventory",
        "proposedShelfInventorySha256",
        "provenance",
        "publicationAuthorized",
        "release",
        "retainedFromIncumbent",
        "signature",
        "sourceSha",
        "status",
        "uploadAuthorized",
    }
    if not isinstance(composition, dict):
        raise ProjectionBlocked("unsigned Registry composition request is missing")
    composition_raw = (
        json.dumps(composition, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _candidate_reference(
        registry_candidate.get("compositionInput"),
        path=CANDIDATE_UNSIGNED_COMPOSITION_FILE,
        raw=composition_raw,
        label="unsigned Registry composition request",
    )
    if (
        set(composition) != composition_keys
        or composition.get("contractName")
        != "chummer6-ui.preview-nightly-unsigned-composition-request"
        or type(composition.get("contractVersion")) is not int
        or composition.get("contractVersion") != 3
        or composition.get("status") != "prepared"
        or composition.get("release")
        != {"channel": "preview", "version": candidate["version"]}
        or composition.get("platformScope") != "windows_only"
        or composition.get("crossRunBitReproducible") is not False
        or composition.get("signature") != signature
        or composition.get("sourceSha") != scope["sourceSha"]
        or any(
            composition.get(key) is not False
            for key in (
                "publicationAuthorized",
                "uploadAuthorized",
                "deployAuthorized",
            )
        )
    ):
        raise ProjectionBlocked("unsigned composition request posture drifted")
    _candidate_reference(
        composition.get("proposedCanonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="unsigned composition canonical manifest",
    )
    _candidate_reference(
        composition.get("proposedCompatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="unsigned composition compatibility manifest",
    )
    proposed_inventory = _candidate_unsigned_inventory(
        composition.get("proposedShelfInventory"),
        label="unsigned composition proposed inventory",
    )
    proposed_modes = _candidate_unsigned_directory_modes(
        composition.get("proposedDirectoryModes"),
        label="unsigned composition proposed directory modes",
    )
    if (
        proposed_inventory != full_inventory
        or composition.get("proposedShelfInventorySha256")
        != _candidate_ui_compact_sha256(proposed_inventory)
        or composition.get("proposedDirectoryModesSha256")
        != _candidate_ui_compact_sha256(proposed_modes)
    ):
        raise ProjectionBlocked("unsigned composition proposed shelf graph drifted")
    incumbent = composition.get("incumbentSnapshot")
    incumbent_keys = {
        "canonicalManifest",
        "compatibilityManifest",
        "directoryModes",
        "directoryModesSha256",
        "fullShelfInventory",
        "fullShelfInventorySha256",
        "snapshotSha256",
    }
    if not isinstance(incumbent, dict) or set(incumbent) != incumbent_keys:
        raise ProjectionBlocked("unsigned composition incumbent snapshot drifted")
    incumbent_inventory = _candidate_unsigned_inventory(
        incumbent.get("fullShelfInventory"),
        label="unsigned composition incumbent inventory",
    )
    incumbent_modes = _candidate_unsigned_directory_modes(
        incumbent.get("directoryModes"),
        label="unsigned composition incumbent directory modes",
    )
    incumbent_body = {
        key: incumbent[key]
        for key in incumbent_keys
        if key != "snapshotSha256"
    }
    if (
        incumbent.get("fullShelfInventorySha256")
        != _candidate_ui_compact_sha256(incumbent_inventory)
        or incumbent.get("directoryModesSha256")
        != _candidate_ui_compact_sha256(incumbent_modes)
        or incumbent.get("snapshotSha256")
        != _candidate_ui_compact_sha256(incumbent_body)
        or incumbent.get("fullShelfInventorySha256")
        != scope["incumbentInventorySha256"]
    ):
        raise ProjectionBlocked("unsigned composition incumbent digest graph drifted")
    _candidate_unheld_reference(
        incumbent.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        label="unsigned incumbent canonical manifest",
    )
    _candidate_unheld_reference(
        incumbent.get("compatibilityManifest"),
        path="releases.json",
        label="unsigned incumbent compatibility manifest",
    )
    if composition.get("retainedFromIncumbent") != retained:
        raise ProjectionBlocked("unsigned composition retained inventory drifted")
    incumbent_by_path = {str(row["path"]): row for row in incumbent_inventory}
    for row in retained:
        exact = {
            key: row[key] for key in ("mode", "path", "sha256", "sizeBytes")
        }
        if (
            incumbent_by_path.get(str(row["path"])) != exact
            or full_by_path.get(str(row["path"])) != exact
        ):
            raise ProjectionBlocked("unsigned retained bytes differ across shelves")
    composition_fresh = composition.get("freshDelta")
    artifacts = canonical.get("artifacts")
    windows_rows = [
        row
        for row in artifacts or []
        if isinstance(row, dict)
        and row.get("head") == "avalonia"
        and row.get("platform") == "windows"
        and row.get("rid") == CANDIDATE_RID
    ]
    if (
        not isinstance(composition_fresh, list)
        or len(composition_fresh) != 2
        or len(windows_rows) != 1
    ):
        raise ProjectionBlocked("unsigned composition fresh delta drifted")
    manifest_row_sha256 = _candidate_ui_compact_sha256(windows_rows[0])
    for composition_row, scope_row in zip(
        composition_fresh, fresh, strict=True
    ):
        if (
            not isinstance(composition_row, dict)
            or set(composition_row)
            != {
                "artifactRole",
                "fileName",
                "head",
                "manifestRowSha256",
                "mode",
                "path",
                "platform",
                "rid",
                "sha256",
                "sizeBytes",
            }
            or composition_row.get("manifestRowSha256") != manifest_row_sha256
            or {
                key: value
                for key, value in composition_row.items()
                if key != "manifestRowSha256"
            }
            != scope_row
        ):
            raise ProjectionBlocked("unsigned composition fresh byte graph drifted")
    composition_provenance = composition.get("provenance")
    if (
        not isinstance(composition_provenance, dict)
        or set(composition_provenance) != set(provenance_paths)
    ):
        raise ProjectionBlocked("unsigned composition provenance drifted")
    for name, path in provenance_paths.items():
        _candidate_reference(
            composition_provenance.get(name),
            path=path,
            raw=evidence_documents[path],
            label=f"unsigned composition provenance {name}",
        )
        if scope_provenance.get(name) != {
            "sha256": hashlib.sha256(evidence_documents[path]).hexdigest(),
            "sizeBytes": len(evidence_documents[path]),
        }:
            raise ProjectionBlocked("unsigned composition/UI provenance drifted")

    expected_windows_delta = {
        str(row["artifactRole"]): {
            "path": row["path"],
            "sha256": row["sha256"],
            "sizeBytes": row["sizeBytes"],
        }
        for row in fresh
    }
    canonical_platforms = {
        row.get("platform") for row in artifacts or [] if isinstance(row, dict)
    }
    if (
        any(not isinstance(row, dict) for row in artifacts or [])
        or not canonical_platforms.issubset({"linux", "macos", "windows"})
        or registry_candidate.get("incumbentInventorySha256")
        != incumbent["fullShelfInventorySha256"]
        or registry_candidate.get("incumbentSnapshotSha256")
        != incumbent["snapshotSha256"]
        or registry_candidate.get("incumbentDirectoryModesSha256")
        != incumbent["directoryModesSha256"]
        or registry_candidate.get("proposedDirectoryModesSha256")
        != composition["proposedDirectoryModesSha256"]
        or registry_candidate.get("retainedInventorySha256")
        != _candidate_ui_compact_sha256(retained)
        or registry_candidate.get("retainedPlatforms")
        != sorted(canonical_platforms - {"windows"})
        or registry_candidate.get("shelfPlatforms")
        != sorted(canonical_platforms)
        or registry_candidate.get("windowsDelta") != expected_windows_delta
        or registry_candidate.get("provenance") != composition_provenance
    ):
        raise ProjectionBlocked("unsigned Registry PREPARE custody graph drifted")
    _candidate_unsigned_projection_inputs(registry_candidate.get("projectionInputs"))

    mixed_graph = {
        "authorityContractVersion": 2,
        "candidateReceiptContractVersion": 2,
        "compositionRequestContractVersion": 3,
        "finalizeReceiptContractVersion": 2,
        "sourceScopeContractVersion": 3,
    }
    authority_keys = {
        "candidateImportAuthority", "candidateReceipt", "candidateReviewAuthority",
        "canonicalManifest", "channel", "codeDeploymentAuthority", "compatibilityManifest",
        "compositionRequest", "contractName", "contractVersion",
        "crossRunBitReproducible", "deltaPlatforms", "deployAuthority",
        "evidencePlatforms", "fullShelfInventorySha256", "incumbentInventorySha256",
        "incumbentSnapshotSha256", "mixedVersionGraph", "platformScope",
        "projectionInputs", "proposedDirectoryModesSha256", "provenance",
        "publicationAuthorized", "publicationEligible",
        "releaseUploadAuthority", "releaseVersion", "retainedInventorySha256",
        "retainedPlatforms", "routeAuthority",
        "shelfPlatforms", "signaturePolicy", "sourceScope", "sourceSha", "windowsDelta",
    }
    if (
        set(registry_authority) != authority_keys
        or registry_authority.get("contractName")
        != "chummer.registry.preview-publication-delta-authority"
        or registry_authority.get("contractVersion") != 2
        or registry_authority.get("candidateImportAuthority") is not True
        or registry_authority.get("candidateReviewAuthority") is not True
        or registry_authority.get("channel") != "preview"
        or registry_authority.get("releaseVersion") != candidate["version"]
        or registry_authority.get("deltaPlatforms") != ["windows"]
        or registry_authority.get("evidencePlatforms") != []
        or registry_authority.get("platformScope") != "windows_only"
        or registry_authority.get("crossRunBitReproducible") is not False
        or registry_authority.get("mixedVersionGraph") != mixed_graph
        or registry_authority.get("signaturePolicy") != signature_policy
        or registry_authority.get("sourceSha") != scope["sourceSha"]
        or registry_authority.get("incumbentInventorySha256")
        != scope["incumbentInventorySha256"]
        or registry_authority.get("retainedInventorySha256")
        != _candidate_ui_compact_sha256(retained)
        or any(
            registry_authority.get(key) is not False
            for key in (
                "publicationAuthorized", "publicationEligible", "releaseUploadAuthority",
                "deployAuthority", "routeAuthority", "codeDeploymentAuthority",
            )
        )
    ):
        raise ProjectionBlocked("unsigned Registry authority v2 posture drifted")
    for key in (
        "fullShelfInventorySha256",
        "incumbentInventorySha256",
        "incumbentSnapshotSha256",
        "proposedDirectoryModesSha256",
        "retainedInventorySha256",
        "retainedPlatforms",
        "shelfPlatforms",
    ):
        if registry_authority.get(key) != registry_candidate.get(key):
            raise ProjectionBlocked("unsigned Registry v2 digest graph drifted")
    for value, path, raw, label in (
        (registry_authority.get("candidateReceipt"), CANDIDATE_REGISTRY_RECEIPT_FILE, registry_candidate_raw, "candidate receipt"),
        (registry_authority.get("canonicalManifest"), "RELEASE_CHANNEL.generated.json", canonical_raw, "canonical manifest"),
        (registry_authority.get("compatibilityManifest"), "releases.json", compatibility_raw, "compatibility manifest"),
        (registry_authority.get("compositionRequest"), CANDIDATE_UNSIGNED_COMPOSITION_FILE, composition_raw, "composition request"),
        (registry_authority.get("sourceScope"), CANDIDATE_UNSIGNED_SCOPE_FILE, scope_raw, "source scope"),
    ):
        _candidate_reference(value, path=path, raw=raw, label=f"unsigned Registry {label}")
    if registry_authority.get("windowsDelta") != expected_windows_delta:
        raise ProjectionBlocked("unsigned Registry Windows delta drifted")
    _candidate_unsigned_projection_inputs(registry_authority.get("projectionInputs"))
    if registry_authority.get("projectionInputs") != registry_candidate.get(
        "projectionInputs"
    ):
        raise ProjectionBlocked("unsigned Registry projection input graph drifted")
    registry_provenance = registry_authority.get("provenance")
    if not isinstance(registry_provenance, dict) or set(registry_provenance) != set(
        provenance_paths
    ):
        raise ProjectionBlocked("unsigned Registry provenance property set drifted")
    if registry_provenance != registry_candidate.get("provenance"):
        raise ProjectionBlocked("unsigned Registry provenance graph drifted")
    for name, path in provenance_paths.items():
        _candidate_reference(
            registry_provenance.get(name),
            path=path,
            raw=evidence_documents[path],
            label=f"unsigned Registry provenance {name}",
        )

    finalize_keys = {
        "authority", "candidateBytesMutated", "candidateImportAuthority",
        "candidateReceipt", "candidateReviewAuthority", "canonicalManifest", "channel",
        "codeDeploymentAuthority", "compatibilityManifest", "compositionRequest", "contractName",
        "contractVersion", "deployAuthority", "fullShelfInventorySha256",
        "mixedVersionGraph", "platformScope", "provenance", "publicationAuthorized",
        "publicationEligible", "releaseUploadAuthority", "releaseVersion", "routeAuthority",
        "signaturePolicy", "sourceScope", "verificationStatus", "windowsDelta",
    }
    if (
        set(registry_finalize) != finalize_keys
        or registry_finalize.get("contractName")
        != "chummer.registry.preview-publication-delta-finalize"
        or registry_finalize.get("contractVersion") != 2
        or registry_finalize.get("verificationStatus") != "finalized"
        or registry_finalize.get("candidateBytesMutated") is not False
        or registry_finalize.get("candidateImportAuthority") is not True
        or registry_finalize.get("candidateReviewAuthority") is not True
        or registry_finalize.get("channel") != "preview"
        or registry_finalize.get("releaseVersion") != candidate["version"]
        or registry_finalize.get("platformScope") != "windows_only"
        or registry_finalize.get("mixedVersionGraph") != mixed_graph
        or registry_finalize.get("signaturePolicy") != signature_policy
        or registry_finalize.get("windowsDelta") != expected_windows_delta
        or registry_finalize.get("provenance") != registry_provenance
        or registry_finalize.get("fullShelfInventorySha256")
        != registry_candidate.get("fullShelfInventorySha256")
        or any(
            registry_finalize.get(key) is not False
            for key in (
                "publicationAuthorized", "publicationEligible", "releaseUploadAuthority",
                "deployAuthority", "routeAuthority", "codeDeploymentAuthority",
            )
        )
    ):
        raise ProjectionBlocked("unsigned Registry finalize v2 posture drifted")
    for key, path, raw in (
        ("authority", CANDIDATE_REGISTRY_AUTHORITY_FILE, registry_authority_raw),
        ("candidateReceipt", CANDIDATE_REGISTRY_RECEIPT_FILE, registry_candidate_raw),
        ("canonicalManifest", "RELEASE_CHANNEL.generated.json", canonical_raw),
        ("compatibilityManifest", "releases.json", compatibility_raw),
        ("compositionRequest", CANDIDATE_UNSIGNED_COMPOSITION_FILE, composition_raw),
        ("sourceScope", CANDIDATE_UNSIGNED_SCOPE_FILE, scope_raw),
    ):
        _candidate_reference(
            registry_finalize.get(key),
            path=path,
            raw=raw,
            label=f"unsigned Registry finalize {key}",
        )
    expected_summary = {
        "status": "finalized",
        "candidateImportAuthority": True,
        "candidateReviewAuthority": True,
        "publicationAuthorized": False,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": False,
        "codeDeploymentAuthority": False,
        "scope": "windows_only",
        "exactIncomingDesktopScope": CANDIDATE_EXACT_SCOPE,
        "signaturePolicy": signature_policy,
        "candidateReceiptSha256": hashlib.sha256(registry_candidate_raw).hexdigest(),
        "authoritySha256": hashlib.sha256(registry_authority_raw).hexdigest(),
        "finalizeReceiptSha256": hashlib.sha256(registry_finalize_raw).hexdigest(),
    }
    if custody.get("registryFinalization") != expected_summary:
        raise ProjectionBlocked("unsigned Registry finalization summary drifted")
    return authority


def _validate_candidate_import_authority(payload: bytes) -> dict[str, object]:
    authority = _strict_json_object(payload, label="candidate import authority")
    if authority.get("contractName") == CANDIDATE_AUTHORITY_CONTRACT_V3:
        return _validate_candidate_import_authority_v3(authority)
    if set(authority) != {
        "contractName",
        "contractVersion",
        "status",
        "candidateImportAuthority",
        "candidateReviewAuthority",
        "publicationEligible",
        "releaseUploadAuthority",
        "deployAuthority",
        "routeAuthority",
        "exactIncomingDesktopScope",
        "generatedAtUtc",
        "expiresAtUtc",
        "candidate",
        "custody",
    } or (
        authority.get("contractName")
        != CANDIDATE_AUTHORITY_CONTRACT_V2
        or type(authority.get("contractVersion")) is not int
        or authority.get("contractVersion") != 2
        or authority.get("status") != PROJECTION_STATUS_CANDIDATE_IMPORT_READY
        or authority.get("candidateImportAuthority") is not True
        or authority.get("candidateReviewAuthority") is not True
        or authority.get("exactIncomingDesktopScope") != CANDIDATE_EXACT_SCOPE
        or any(
            authority.get(key) is not False
            for key in (
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
            )
        )
    ):
        raise ProjectionBlocked("candidate import authority contract drifted")
    try:
        generated_at = datetime.fromisoformat(
            str(authority.get("generatedAtUtc") or "").replace("Z", "+00:00")
        )
        expires_at = datetime.fromisoformat(
            str(authority.get("expiresAtUtc") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ProjectionBlocked("candidate import authority timestamps are invalid") from exc
    now = datetime.now(timezone.utc)
    if (
        generated_at.utcoffset() != timezone.utc.utcoffset(generated_at)
        or expires_at.utcoffset() != timezone.utc.utcoffset(expires_at)
        or generated_at > now + timedelta(minutes=5)
        or generated_at < now - timedelta(hours=6, minutes=5)
        or expires_at <= now
        or expires_at > now + timedelta(hours=6, minutes=5)
        or expires_at <= generated_at
        or expires_at > generated_at + timedelta(hours=6)
    ):
        raise ProjectionBlocked("candidate import authority is expired or outside its bounded lifetime")

    candidate = authority.get("candidate")
    expected_candidate_keys = {
        "version",
        "canonicalManifestSha256",
        "inventorySha256",
        "fileCount",
        "totalBytes",
        "bundleIdentitySha256",
    }
    if not isinstance(candidate, dict) or set(candidate) != expected_candidate_keys:
        raise ProjectionBlocked("candidate import identity drifted")
    for name in (
        "canonicalManifestSha256",
        "inventorySha256",
        "bundleIdentitySha256",
    ):
        if SHA256_RE.fullmatch(str(candidate.get(name) or "")) is None:
            raise ProjectionBlocked("candidate import digest binding is invalid")
    _candidate_version(candidate.get("version"), label="candidate import version")
    if (
        isinstance(candidate.get("fileCount"), bool)
        or not isinstance(candidate.get("fileCount"), int)
        or candidate["fileCount"] < 1
        or isinstance(candidate.get("totalBytes"), bool)
        or not isinstance(candidate.get("totalBytes"), int)
        or candidate["totalBytes"] < 0
    ):
        raise ProjectionBlocked("candidate import summary is invalid")
    identity_material = json.dumps(
        {
            key: candidate[key]
            for key in (
                "version",
                "canonicalManifestSha256",
                "inventorySha256",
                "fileCount",
                "totalBytes",
            )
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if not hmac.compare_digest(
        hashlib.sha256(identity_material).hexdigest(),
        str(candidate["bundleIdentitySha256"]),
    ):
        raise ProjectionBlocked("candidate import bundle identity drifted")

    custody = authority.get("custody")
    if not isinstance(custody, dict) or set(custody) != {
        "canonicalManifest",
        "compatibilityManifest",
        "inventory",
        "nativeWindowsFinalizedEvidence",
        "finalizedPublicationEvidence",
        "registryPrepareCandidateReceipt",
        "registryFinalizeAuthority",
        "registryFinalizeReceipt",
        "registryFinalization",
    }:
        raise ProjectionBlocked("candidate import custody property set drifted")
    canonical_bytes = _candidate_embedded_bytes(
        custody.get("canonicalManifest"),
        label="candidate canonical manifest",
        expected_path="RELEASE_CHANNEL.generated.json",
    )
    if hashlib.sha256(canonical_bytes).hexdigest() != candidate["canonicalManifestSha256"]:
        raise ProjectionBlocked("candidate canonical manifest custody digest drifted")
    compatibility_bytes = _candidate_embedded_bytes(
        custody.get("compatibilityManifest"),
        label="candidate compatibility manifest",
        expected_path="releases.json",
    )
    _strict_json_object(
        compatibility_bytes, label="candidate compatibility release manifest custody"
    )
    inventory_bytes = _candidate_embedded_bytes(
        custody.get("inventory"),
        label="candidate upload inventory",
        expected_path="CANDIDATE_UPLOAD_INVENTORY.generated.json",
    )
    inventory = _strict_json_object(
        inventory_bytes, label="candidate upload inventory custody"
    )
    rows = inventory.get("files")
    if (
        set(inventory) != {"contractName", "contractVersion", "files"}
        or inventory.get("contractName")
        != "chummer.release-upload.candidate-inventory/v1"
        or type(inventory.get("contractVersion")) is not int
        or inventory.get("contractVersion") != 1
        or not isinstance(rows, list)
        or len(rows) != candidate["fileCount"]
    ):
        raise ProjectionBlocked("candidate upload inventory custody contract drifted")
    candidate_rows = _candidate_inventory_rows(
        rows, label="candidate upload inventory custody"
    )
    inventory_digest = hashlib.sha256()
    total_bytes = 0
    previous_path = ""
    canonical_row_seen = False
    compatibility_row_seen = False
    for row in candidate_rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "sizeBytes"}:
            raise ProjectionBlocked("candidate upload inventory row drifted")
        path = row.get("path")
        digest = row.get("sha256")
        size = row.get("sizeBytes")
        if (
            not isinstance(path, str)
            or not path
            or path <= previous_path
            or SHA256_RE.fullmatch(str(digest or "")) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ProjectionBlocked("candidate upload inventory row is invalid")
        previous_path = path
        encoded_path = path.encode("utf-8")
        inventory_digest.update(len(encoded_path).to_bytes(8, "big"))
        inventory_digest.update(encoded_path)
        inventory_digest.update(size.to_bytes(8, "big"))
        inventory_digest.update(bytes.fromhex(str(digest)))
        total_bytes += size
        if path == "RELEASE_CHANNEL.generated.json":
            canonical_row_seen = (
                digest == candidate["canonicalManifestSha256"]
                and size == len(canonical_bytes)
            )
        elif path == "releases.json":
            compatibility_row_seen = (
                digest == hashlib.sha256(compatibility_bytes).hexdigest()
                and size == len(compatibility_bytes)
            )
    if (
        not canonical_row_seen
        or not compatibility_row_seen
        or total_bytes != candidate["totalBytes"]
        or inventory_digest.hexdigest() != candidate["inventorySha256"]
    ):
        raise ProjectionBlocked("candidate upload inventory custody summary drifted")

    canonical = _strict_json_object(
        canonical_bytes, label="candidate canonical release manifest custody"
    )
    native_package = _validate_candidate_native_evidence(
        custody.get("nativeWindowsFinalizedEvidence"),
        canonical=canonical,
        candidate_rows=candidate_rows,
        candidate=candidate,
        now=now,
    )
    publication_scope, publication_scope_raw, publication_documents = (
        _validate_candidate_finalized_publication(
            custody.get("finalizedPublicationEvidence"),
            canonical_raw=canonical_bytes,
            compatibility_raw=compatibility_bytes,
            candidate=candidate,
            native_package=native_package,
        )
    )
    registry_candidate_raw = _candidate_embedded_bytes(
        custody.get("registryPrepareCandidateReceipt"),
        label="Registry PREPARE candidate receipt",
        expected_path=CANDIDATE_REGISTRY_RECEIPT_FILE,
    )
    registry_authority_raw = _candidate_embedded_bytes(
        custody.get("registryFinalizeAuthority"),
        label="Registry FINALIZE authority",
        expected_path=CANDIDATE_REGISTRY_AUTHORITY_FILE,
    )
    registry_finalize_raw = _candidate_embedded_bytes(
        custody.get("registryFinalizeReceipt"),
        label="Registry FINALIZE receipt",
        expected_path=CANDIDATE_REGISTRY_FINALIZE_FILE,
    )
    _validate_candidate_registry_graph(
        candidate_receipt=_strict_json_object(
            registry_candidate_raw, label="Registry PREPARE candidate receipt"
        ),
        candidate_receipt_raw=registry_candidate_raw,
        registry_authority=_strict_json_object(
            registry_authority_raw, label="Registry FINALIZE authority"
        ),
        registry_authority_raw=registry_authority_raw,
        finalize=_strict_json_object(
            registry_finalize_raw, label="Registry FINALIZE receipt"
        ),
        finalize_raw=registry_finalize_raw,
        registry_summary=custody.get("registryFinalization"),
        canonical_raw=canonical_bytes,
        compatibility_raw=compatibility_bytes,
        scope=publication_scope,
        scope_raw=publication_scope_raw,
        evidence_documents=publication_documents,
        candidate=candidate,
    )
    return authority


def _publish_candidate_import_snapshot_locked(
    snapshot_root: Path,
    *,
    authority_path: Path,
    expected_authority_sha256: str,
) -> ProjectionSnapshot:
    source = resolve_current_snapshot(
        snapshot_root, purpose=PROJECTION_PURPOSE_CODE_DEPLOY
    )
    authority_payload = _stable_read(
        authority_path, label="candidate import authority"
    )
    actual_authority_sha256 = hashlib.sha256(authority_payload).hexdigest()
    if (
        SHA256_RE.fullmatch(expected_authority_sha256) is None
        or not hmac.compare_digest(actual_authority_sha256, expected_authority_sha256)
    ):
        raise ProjectionBlocked(
            "candidate import authority SHA256 does not match its immutable handoff"
        )
    _validate_candidate_import_authority(authority_payload)

    snapshot_stage = Path(
        tempfile.mkdtemp(prefix=".public-projection-candidate.", dir=snapshot_root)
    )
    pointer_stage: Path | None = None
    try:
        output_payloads: dict[str, bytes] = {}
        output_digests: dict[str, str] = {}
        for name in SNAPSHOT_OUTPUT_NAMES:
            payload = _stable_read(source.outputs[name], label=f"source current {name}")
            if not hmac.compare_digest(
                hashlib.sha256(payload).hexdigest(), source.output_sha256[name]
            ):
                raise ProjectionBlocked("source current output changed during candidate staging")
            _write_fsynced_file(
                snapshot_stage / name,
                payload,
                mode=0o644,
                label=f"candidate snapshot {name}",
            )
            output_payloads[name] = payload
            output_digests[name] = source.output_sha256[name]
        _write_fsynced_file(
            snapshot_stage / CANDIDATE_IMPORT_AUTHORITY_NAME,
            authority_payload,
            mode=0o644,
            label="candidate import authority output",
        )
        output_payloads[CANDIDATE_IMPORT_AUTHORITY_NAME] = authority_payload
        output_digests[CANDIDATE_IMPORT_AUTHORITY_NAME] = actual_authority_sha256

        snapshot_sha256 = _snapshot_digest(
            output_digests, CANDIDATE_SNAPSHOT_OUTPUT_NAMES
        )
        snapshot_id = f"public-projection-{snapshot_sha256}"
        source_manifest_bytes = _stable_read(
            source.snapshot_directory / SNAPSHOT_MANIFEST_NAME,
            label="source current snapshot manifest",
        )
        if not hmac.compare_digest(
            hashlib.sha256(source_manifest_bytes).hexdigest(),
            source.manifest_sha256,
        ):
            raise ProjectionBlocked(
                "source current snapshot manifest changed during candidate staging"
            )
        source_manifest = _strict_json_object(
            source_manifest_bytes,
            label="source current snapshot manifest",
        )
        findings = _candidate_import_gate_findings()
        manifest = {
            "contractName": SNAPSHOT_CONTRACT,
            "status": PROJECTION_STATUS_CANDIDATE_IMPORT_READY,
            "projectionStage": PROJECTION_STAGE_CANDIDATE_IMPORT_READY,
            "codeDeploymentAuthority": False,
            "releaseUploadAuthority": False,
            "candidateImportAuthority": True,
            "releaseGateFindings": findings,
            "snapshotId": snapshot_id,
            "snapshotSha256": snapshot_sha256,
            "authorityInputs": source_manifest.get("authorityInputs"),
            "outputs": {
                name: {
                    "relativePath": name,
                    "sha256": output_digests[name],
                    "sizeBytes": len(output_payloads[name]),
                }
                for name in CANDIDATE_SNAPSHOT_OUTPUT_NAMES
            },
        }
        manifest_bytes = _canonical_json_bytes(manifest)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        _write_fsynced_file(
            snapshot_stage / SNAPSHOT_MANIFEST_NAME,
            manifest_bytes,
            mode=0o644,
            label="candidate public projection manifest",
        )
        snapshot_stage.chmod(0o555)
        _fsync_directory(snapshot_stage, label="candidate public projection stage")
        final_directory = snapshot_root / snapshot_id
        pointer_payload = _canonical_json_bytes(
            {
                "contractName": CURRENT_CONTRACT,
                "status": PROJECTION_STATUS_CANDIDATE_IMPORT_READY,
                "projectionStage": PROJECTION_STAGE_CANDIDATE_IMPORT_READY,
                "codeDeploymentAuthority": False,
                "releaseUploadAuthority": False,
                "candidateImportAuthority": True,
                "releaseGateFindings": findings,
                "snapshotId": snapshot_id,
                "snapshotSha256": snapshot_sha256,
                "manifestRelativePath": f"{snapshot_id}/{SNAPSHOT_MANIFEST_NAME}",
                "manifestSha256": manifest_sha256,
                "outputs": {
                    name: f"{snapshot_id}/{name}"
                    for name in CANDIDATE_SNAPSHOT_OUTPUT_NAMES
                },
            }
        )
        pointer_stage = _prepare_pointer_file(snapshot_root, pointer_payload)
        result = ProjectionSnapshot(
            current_pointer=snapshot_root / CURRENT_POINTER_NAME,
            snapshot_directory=final_directory,
            snapshot_id=snapshot_id,
            snapshot_sha256=snapshot_sha256,
            outputs={
                name: final_directory / name for name in CANDIDATE_SNAPSHOT_OUTPUT_NAMES
            },
            output_sha256=output_digests,
            manifest_sha256=manifest_sha256,
            status=PROJECTION_STATUS_CANDIDATE_IMPORT_READY,
            projection_stage=PROJECTION_STAGE_CANDIDATE_IMPORT_READY,
            code_deployment_authority=False,
            release_upload_authority=False,
            candidate_import_authority=True,
            release_gate_findings=tuple(findings),
        )
        _validate_current_pointer_target(result.current_pointer)
        _fsync_directory(snapshot_root, label="candidate projection precommit root")
        _exclusive_snapshot_rename(snapshot_stage, final_directory)
        snapshot_stage = None
        _fsync_directory(snapshot_root, label="candidate projection snapshot commit root")
        _commit_current_pointer(
            pointer_stage=pointer_stage,
            current_pointer=result.current_pointer,
            snapshot_root=snapshot_root,
            result=result,
        )
        pointer_stage = None
        return result
    finally:
        if snapshot_stage is not None:
            _remove_private_stage(snapshot_stage)
        if pointer_stage is not None:
            pointer_stage.unlink(missing_ok=True)


def publish_candidate_import_snapshot(
    snapshot_root: Path,
    *,
    authority_path: Path,
    expected_authority_sha256: str,
) -> ProjectionSnapshot:
    lock_descriptor = _acquire_publication_lock(snapshot_root)
    try:
        return _publish_candidate_import_snapshot_locked(
            snapshot_root,
            authority_path=authority_path,
            expected_authority_sha256=expected_authority_sha256,
        )
    finally:
        _release_publication_lock(lock_descriptor)


def _run_projection_locked(
    source_environment: Mapping[str, str],
    snapshot_root: Path,
    *,
    gate_commands: Iterable[tuple[str, Sequence[str]]] | None = None,
    review_gate_commands: Iterable[tuple[str, Sequence[str]]] | None = None,
    code_deploy_stage: bool = False,
) -> ProjectionSnapshot:
    if review_gate_commands is not None and not code_deploy_stage:
        raise ProjectionBlocked(
            "release review gates are valid only for a code-deploy stage"
        )
    using_default_gate_commands = gate_commands is None
    projection_status = (
        PROJECTION_STATUS_REVIEW_REQUIRED
        if code_deploy_stage
        else PROJECTION_STATUS_PASS
    )
    (
        projection_stage,
        code_deployment_authority,
        release_upload_authority,
        candidate_import_authority,
    ) = _projection_authority(projection_status)
    current_pointer = snapshot_root / CURRENT_POINTER_NAME
    _validate_current_pointer_target(current_pointer)
    for commit_name in (
        "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT",
    ):
        commit = _required(source_environment, commit_name).lower()
        if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            raise ProjectionBlocked(f"{commit_name} must be a full 40-character SHA")

    authority_specs = (
        (
            "release_channel",
            "CHUMMER_HUB_RELEASE_CHANNEL_PATH",
            "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256",
            "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY",
            "RELEASE_CHANNEL.generated.json",
        ),
        (
            "flagship_readiness",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY",
            "FLAGSHIP_PRODUCT_READINESS.generated.json",
        ),
        (
            "fleet_queue",
            "CHUMMER_FLEET_QUEUE_STAGING_PATH",
            "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256",
            "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY",
            "FLEET_NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
        ),
        (
            "design_queue",
            "CHUMMER_DESIGN_QUEUE_STAGING_PATH",
            "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256",
            "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY",
            "DESIGN_NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
        ),
        (
            "successor_registry",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY",
            "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
        ),
    )

    authority_stage: Path | None = None
    snapshot_stage: Path | None = None
    pointer_stage: Path | None = None
    try:
        authority_stage = Path(
            tempfile.mkdtemp(prefix=".public-projection-inputs.", dir=snapshot_root)
        )
        snapshot_stage = Path(
            tempfile.mkdtemp(prefix=".public-projection-snapshot.", dir=snapshot_root)
        )
    except OSError as exc:
        if authority_stage is not None:
            try:
                _remove_private_stage(authority_stage)
            except ProjectionBlocked:
                pass
        raise ProjectionBlocked("could not create private public projection stage") from exc

    try:
        staged_paths: dict[str, Path] = {}
        authority_values: dict[str, str] = {}
        digest_values: dict[str, str] = {}
        for label, path_name, digest_name, authority_name, staged_name in authority_specs:
            source = _path_from_env(source_environment, path_name)
            digest = _expected_sha256(source_environment, digest_name)
            authority = _authority_reference(source_environment, authority_name)
            staged_path = authority_stage / staged_name
            _stage_authority(
                source=source,
                destination=staged_path,
                expected_sha256=digest,
                label=label.replace("_", " "),
            )
            staged_paths[label] = staged_path
            authority_values[label] = authority
            digest_values[label] = digest

        staged_proof = snapshot_stage / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        staged_served_proof = snapshot_stage / "HUB_SERVED_RELEASE_PROOF.generated.json"
        staged_m125_proof = snapshot_stage / "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json"
        staged_m126_proof = snapshot_stage / "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json"
        staged_windows_receipt = snapshot_stage / "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json"
        staged_release_channel = snapshot_stage / "RELEASE_CHANNEL.generated.json"
        staged_flagship_readiness = (
            snapshot_stage / "FLAGSHIP_PRODUCT_READINESS.generated.json"
        )
        child_environment = dict(source_environment)
        for sensitive_name in tuple(child_environment):
            if re.search(
                r"(?:AUTHORIZATION|PASSWORD|SECRET|TICKET|TOKEN|API[_-]?KEY)",
                sensitive_name,
                re.IGNORECASE,
            ):
                child_environment.pop(sensitive_name, None)
        child_environment.update(
            {
                "CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS": "1",
                "CHUMMER_HUB_RELEASE_CHANNEL_PATH": str(staged_paths["release_channel"]),
                "CHUMMER_NEXT90_M144_RELEASE_CHANNEL": str(staged_paths["release_channel"]),
                "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH": str(staged_paths["flagship_readiness"]),
                "CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH": str(authority_stage / "public-edge-mutation.lock"),
                "CHUMMER_NEXT90_M120_LOCAL_RELEASE_PROOF": str(staged_proof),
                "CHUMMER_NEXT90_M120_SERVED_RELEASE_PROOF": str(staged_served_proof),
                "CHUMMER_NEXT90_M125_PROOF_PATH": str(staged_m125_proof),
                "CHUMMER_NEXT90_M126_PROOF_PATH": str(staged_m126_proof),
                "CHUMMER_NEXT90_M144_LOCAL_RELEASE_PROOF": str(staged_proof),
                "CHUMMER_NEXT90_M144_SERVED_RELEASE_PROOF": str(staged_served_proof),
                "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(staged_proof),
                "CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH": str(staged_served_proof),
                "CHUMMER_PUBLIC_PROJECTION_WINDOWS_OUTPUT": str(staged_windows_receipt),
                "CHUMMER_FLEET_FLAGSHIP_READINESS_PATH": str(staged_paths["flagship_readiness"]),
                "CHUMMER_FLEET_QUEUE_STAGING_PATH": str(staged_paths["fleet_queue"]),
                "CHUMMER_DESIGN_QUEUE_STAGING_PATH": str(staged_paths["design_queue"]),
                "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH": str(staged_paths["successor_registry"]),
                "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(staged_paths["fleet_queue"]),
                "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(staged_paths["design_queue"]),
                "CHUMMER_NEXT90_SUCCESSOR_REGISTRY_PATH": str(staged_paths["successor_registry"]),
            }
        )
        child_environment["CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256"] = digest_values["release_channel"]
        child_environment["CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256"] = digest_values["flagship_readiness"]
        child_environment["CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY"] = authority_values["release_channel"]
        child_environment["CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY"] = authority_values["flagship_readiness"]

        for milestone in ("M120", "M125", "M126", "M144"):
            prefix = f"CHUMMER_NEXT90_{milestone}"
            child_environment[f"{prefix}_QUEUE_STAGING"] = str(staged_paths["fleet_queue"])
            child_environment[f"{prefix}_DESIGN_QUEUE_STAGING"] = str(staged_paths["design_queue"])
        child_environment["CHUMMER_NEXT90_M120_SUCCESSOR_REGISTRY"] = str(staged_paths["successor_registry"])
        child_environment["CHUMMER_NEXT90_M144_SUCCESSOR_REGISTRY"] = str(staged_paths["successor_registry"])

        materializer_command = (
            sys.executable,
            str(REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"),
            str(staged_proof),
            str(source_environment.get("CHUMMER_PUBLIC_BASE_URL") or "https://chummer.run"),
            str(source_environment.get("CHUMMER_HUB_LOCAL_RELEASE_PROOF_COMPOSE_FILE") or "docker-compose.yml"),
            "120",
            "true",
        )
        _run_gate(
            "Hub local release proof materializer",
            materializer_command,
            environment=child_environment,
        )
        local_proof_bytes = _stable_read(
            staged_proof,
            label="staged Hub local release proof",
        )
        try:
            staged_proof.chmod(0o400)
        except OSError as exc:
            raise ProjectionBlocked("could not seal staged Hub local release proof") from exc
        _write_fsynced_file(
            staged_served_proof,
            local_proof_bytes,
            mode=0o400,
            label="staged served Hub release proof",
        )
        release_channel_bytes = _stable_read(
            staged_paths["release_channel"],
            label="staged release channel authority",
        )
        _write_fsynced_file(
            staged_release_channel,
            release_channel_bytes,
            mode=0o400,
            label="staged authenticated release channel",
        )
        flagship_readiness_bytes = _stable_read(
            staged_paths["flagship_readiness"],
            label="staged flagship readiness authority",
        )
        _write_fsynced_file(
            staged_flagship_readiness,
            flagship_readiness_bytes,
            mode=0o400,
            label="staged authenticated flagship readiness",
        )

        if gate_commands is None:
            materializing_gate_commands = (
                ("M125 public signal packets", (sys.executable, "scripts/verify_next90_m125_hub_public_signal_packets.py")),
                ("M126 hosted proof contracts", (sys.executable, "scripts/verify_next90_m126_hub_hosted_proof_contracts.py")),
            )
            release_gate_commands = (
                ("M120 public launch health", (sys.executable, "scripts/verify_next90_m120_hub_public_launch_health.py")),
                ("desktop native trust receipts", (sys.executable, "scripts/verify_desktop_native_trust_receipts.py")),
                ("M144 release truth alignment", (sys.executable, "scripts/verify_next90_m144_hub_release_truth_alignment.py")),
            )
            gate_commands = materializing_gate_commands
            if review_gate_commands is None:
                review_gate_commands = release_gate_commands
        for name, command in gate_commands:
            _run_gate(name, command, environment=child_environment)
        if code_deploy_stage:
            release_gate_findings = [
                finding
                for name, command in review_gate_commands or ()
                if (
                    finding := _review_gate_finding(
                        name,
                        command,
                        environment=child_environment,
                    )
                )
                is not None
            ]
            _write_fsynced_file(
                staged_windows_receipt,
                _review_required_windows_receipt(release_gate_findings),
                mode=0o400,
                label="staged review-required Windows receipt",
            )
        elif using_default_gate_commands:
            for name, command in release_gate_commands:
                _run_gate(name, command, environment=child_environment)
            _run_gate(
                "live public Windows installer",
                (
                    sys.executable,
                    "scripts/verify_live_public_windows_installer.py",
                    "--output",
                    str(staged_windows_receipt),
                ),
                environment=child_environment,
            )

        output_paths = {
            "HUB_LOCAL_RELEASE_PROOF.generated.json": staged_proof,
            "HUB_SERVED_RELEASE_PROOF.generated.json": staged_served_proof,
            "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json": staged_m125_proof,
            "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json": staged_m126_proof,
            "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json": staged_windows_receipt,
            "RELEASE_CHANNEL.generated.json": staged_release_channel,
            "FLAGSHIP_PRODUCT_READINESS.generated.json": staged_flagship_readiness,
        }
        output_payloads, output_digests = _validate_staged_outputs(
            output_paths,
            projection_status=projection_status,
        )
        release_gate_findings = (
            _validate_review_gate_findings(
                _strict_json_object(
                    output_payloads["LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json"],
                    label="staged live Windows receipt",
                ).get("release_gate_findings")
            )
            if projection_status == PROJECTION_STATUS_REVIEW_REQUIRED
            else []
        )
        try:
            for output_path in output_paths.values():
                output_path.chmod(0o644)
        except OSError as exc:
            raise ProjectionBlocked("could not seal staged public projection outputs") from exc
        snapshot_sha256 = _snapshot_digest(output_digests)
        snapshot_id = f"public-projection-{snapshot_sha256}"
        snapshot_manifest = {
            "contractName": SNAPSHOT_CONTRACT,
            "status": projection_status,
            "projectionStage": projection_stage,
            "codeDeploymentAuthority": code_deployment_authority,
            "releaseUploadAuthority": release_upload_authority,
            "candidateImportAuthority": candidate_import_authority,
            "releaseGateFindings": release_gate_findings,
            "snapshotId": snapshot_id,
            "snapshotSha256": snapshot_sha256,
            "authorityInputs": _strict_json_object(
                output_payloads["HUB_LOCAL_RELEASE_PROOF.generated.json"],
                label="staged Hub local release proof",
            )["authority_inputs"],
            "outputs": {
                name: {
                    "relativePath": name,
                    "sha256": output_digests[name],
                    "sizeBytes": len(output_payloads[name]),
                }
                for name in SNAPSHOT_OUTPUT_NAMES
            },
        }
        manifest_bytes = _canonical_json_bytes(snapshot_manifest)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        _write_fsynced_file(
            snapshot_stage / SNAPSHOT_MANIFEST_NAME,
            manifest_bytes,
            mode=0o644,
            label="public projection snapshot manifest",
        )
        snapshot_stage.chmod(0o555)
        _fsync_directory(snapshot_stage, label="public projection snapshot stage")
        final_snapshot_directory = snapshot_root / snapshot_id
        pointer_payload = _canonical_json_bytes(
            {
                "contractName": CURRENT_CONTRACT,
                "status": projection_status,
                "projectionStage": projection_stage,
                "codeDeploymentAuthority": code_deployment_authority,
                "releaseUploadAuthority": release_upload_authority,
                "candidateImportAuthority": candidate_import_authority,
                "releaseGateFindings": release_gate_findings,
                "snapshotId": snapshot_id,
                "snapshotSha256": snapshot_sha256,
                "manifestRelativePath": f"{snapshot_id}/{SNAPSHOT_MANIFEST_NAME}",
                "manifestSha256": manifest_sha256,
                "outputs": {
                    name: f"{snapshot_id}/{name}" for name in SNAPSHOT_OUTPUT_NAMES
                },
            }
        )
        pointer_stage = _prepare_pointer_file(snapshot_root, pointer_payload)
        result = ProjectionSnapshot(
            current_pointer=current_pointer,
            snapshot_directory=final_snapshot_directory,
            snapshot_id=snapshot_id,
            snapshot_sha256=snapshot_sha256,
            outputs={
                name: final_snapshot_directory / name for name in SNAPSHOT_OUTPUT_NAMES
            },
            output_sha256=dict(output_digests),
            manifest_sha256=manifest_sha256,
            status=projection_status,
            projection_stage=projection_stage,
            code_deployment_authority=code_deployment_authority,
            release_upload_authority=release_upload_authority,
            candidate_import_authority=candidate_import_authority,
            release_gate_findings=tuple(release_gate_findings),
        )
        _remove_private_stage(authority_stage)
        authority_stage = None
        _validate_current_pointer_target(current_pointer)
        _fsync_directory(snapshot_root, label="public projection precommit root")
        _exclusive_snapshot_rename(snapshot_stage, final_snapshot_directory)
        snapshot_stage = None
        _fsync_directory(snapshot_root, label="public projection snapshot commit root")
        _commit_current_pointer(
            pointer_stage=pointer_stage,
            current_pointer=current_pointer,
            snapshot_root=snapshot_root,
            result=result,
        )
        pointer_stage = None
        return result
    except ProjectionBlocked:
        if authority_stage is not None:
            _remove_private_stage(authority_stage)
        if snapshot_stage is not None:
            _remove_private_stage(snapshot_stage)
        if pointer_stage is not None:
            try:
                pointer_stage.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ProjectionBlocked(
                    "could not remove current public projection pointer stage"
                ) from exc
        raise
    except (OSError, ValueError) as exc:
        if authority_stage is not None:
            try:
                _remove_private_stage(authority_stage)
            except ProjectionBlocked:
                pass
        if snapshot_stage is not None:
            try:
                _remove_private_stage(snapshot_stage)
            except ProjectionBlocked:
                pass
        if pointer_stage is not None:
            try:
                pointer_stage.unlink()
            except OSError:
                pass
        raise ProjectionBlocked("public projection filesystem transaction failed") from exc


def run_projection(
    environment: Mapping[str, str] | None = None,
    *,
    gate_commands: Iterable[tuple[str, Sequence[str]]] | None = None,
    review_gate_commands: Iterable[tuple[str, Sequence[str]]] | None = None,
    code_deploy_stage: bool = False,
) -> ProjectionSnapshot:
    source_environment = dict(os.environ if environment is None else environment)
    snapshot_root = _snapshot_root(source_environment)
    lock_descriptor = _acquire_publication_lock(snapshot_root)
    try:
        return _run_projection_locked(
            source_environment,
            snapshot_root,
            gate_commands=gate_commands,
            review_gate_commands=review_gate_commands,
            code_deploy_stage=code_deploy_stage,
        )
    finally:
        _release_publication_lock(lock_descriptor)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish or authenticate the Hub public projection snapshot."
    )
    parser.add_argument(
        "--resolve-current",
        type=Path,
        help="Authenticate CURRENT under this snapshot root without publishing.",
    )
    parser.add_argument(
        "--output-name",
        choices=CANDIDATE_SNAPSHOT_OUTPUT_NAMES,
        action="append",
        default=[],
        help="Include an authenticated output path and digest in resolve output; repeat for multiple outputs.",
    )
    parser.add_argument(
        "--purpose",
        choices=(
            PROJECTION_PURPOSE_RELEASE_UPLOAD,
            PROJECTION_PURPOSE_CODE_DEPLOY,
            PROJECTION_PURPOSE_CANDIDATE_IMPORT,
        ),
        default=PROJECTION_PURPOSE_RELEASE_UPLOAD,
        help="Require CURRENT authority for release upload or bounded code deployment.",
    )
    parser.add_argument(
        "--code-deploy-stage",
        action="store_true",
        help="Publish a review-required snapshot that permits code deployment but not release upload.",
    )
    parser.add_argument(
        "--candidate-import-authority",
        type=Path,
        help="Publish an exact candidate-import authority on top of authenticated CURRENT.",
    )
    parser.add_argument(
        "--candidate-import-authority-sha256",
        help="Immutable SHA-256 handoff for --candidate-import-authority.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("public projection requires Python 3.11 or newer", file=sys.stderr)
        return 2
    args = _parse_args(argv)
    if args.output_name and args.resolve_current is None:
        print("public projection blocked: --output-name requires --resolve-current", file=sys.stderr)
        return 2
    if args.purpose != PROJECTION_PURPOSE_RELEASE_UPLOAD and args.resolve_current is None:
        print("public projection blocked: --purpose requires --resolve-current", file=sys.stderr)
        return 2
    if args.code_deploy_stage and args.resolve_current is not None:
        print(
            "public projection blocked: --code-deploy-stage cannot resolve CURRENT",
            file=sys.stderr,
        )
        return 2
    if bool(args.candidate_import_authority) != bool(
        args.candidate_import_authority_sha256
    ):
        print(
            "public projection blocked: candidate-import authority path and SHA256 are both required",
            file=sys.stderr,
        )
        return 2
    if args.candidate_import_authority is not None and (
        args.resolve_current is not None or args.code_deploy_stage
    ):
        print(
            "public projection blocked: candidate-import publication is a distinct transaction",
            file=sys.stderr,
        )
        return 2
    try:
        if args.resolve_current is not None:
            snapshot = resolve_current_snapshot(
                args.resolve_current,
                purpose=args.purpose,
            )
            payload: dict[str, object] = {
                "contractName": CURRENT_CONTRACT,
                "status": snapshot.status,
                "projectionStage": snapshot.projection_stage,
                "codeDeploymentAuthority": snapshot.code_deployment_authority,
                "releaseUploadAuthority": snapshot.release_upload_authority,
                "candidateImportAuthority": snapshot.candidate_import_authority,
                "releaseGateFindings": list(snapshot.release_gate_findings),
                "snapshotId": snapshot.snapshot_id,
                "snapshotSha256": snapshot.snapshot_sha256,
                "manifestSha256": snapshot.manifest_sha256,
            }
            if args.output_name:
                if len(set(args.output_name)) != len(args.output_name):
                    raise ProjectionBlocked(
                        "public projection output name was requested more than once"
                    )
                if any(name not in snapshot.outputs for name in args.output_name):
                    raise ProjectionBlocked(
                        "requested output is outside the authenticated CURRENT inventory"
                    )
                selected_outputs = {
                    name: {
                        "name": name,
                        "path": str(snapshot.outputs[name]),
                        "sha256": snapshot.output_sha256[name],
                    }
                    for name in args.output_name
                }
                payload["outputs"] = selected_outputs
                if len(args.output_name) == 1:
                    payload["output"] = selected_outputs[args.output_name[0]]
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            return 0
        if args.candidate_import_authority is not None:
            snapshot = publish_candidate_import_snapshot(
                _snapshot_root(os.environ),
                authority_path=args.candidate_import_authority,
                expected_authority_sha256=str(
                    args.candidate_import_authority_sha256
                ).lower(),
            )
        else:
            snapshot = run_projection(code_deploy_stage=args.code_deploy_stage)
    except ProjectionCommitReconcileRequired as exc:
        payload = {
            "contractName": "chummer.public_projection_commit_reconcile/v1",
            "status": "reconcile_required",
            "currentMutated": True,
            "durabilityStatus": "unconfirmed",
            "snapshotId": exc.snapshot.snapshot_id,
            "snapshotSha256": exc.snapshot.snapshot_sha256,
            "reason": sanitize_diagnostic(exc.reason),
        }
        print(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            file=sys.stderr,
        )
        return 75
    except ProjectionBlocked as exc:
        print(f"public projection blocked: {sanitize_diagnostic(str(exc))}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("public projection blocked: filesystem transaction failed", file=sys.stderr)
        return 1
    print(
        "public projection ok: "
        f"{_portable_path(snapshot.current_pointer)} -> {snapshot.snapshot_id} "
        f"({snapshot.status})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
