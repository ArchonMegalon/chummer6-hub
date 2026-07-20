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
CANDIDATE_CAPTURE_WORKFLOW = ".github/workflows/windows-native-evidence-capture.yml"
CANDIDATE_FINALIZE_WORKFLOW = ".github/workflows/windows-native-evidence-finalize.yml"
CANDIDATE_UI_REPOSITORY = "ArchonMegalon/chummer6-ui"
CANDIDATE_UI_REF = "refs/heads/main"
CANDIDATE_RID = "win-x64"
CANDIDATE_HEAD_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CANDIDATE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CANDIDATE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,38})$")
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
    manifest_outputs = manifest.get("outputs")
    if (
        not isinstance(manifest_outputs, dict)
        or set(manifest_outputs) != set(SNAPSHOT_OUTPUT_NAMES)
    ):
        raise ProjectionBlocked("public projection snapshot output inventory drifted")

    outputs: dict[str, Path] = {}
    output_digests: dict[str, str] = {}
    output_payloads: dict[str, bytes] = {}
    for name in SNAPSHOT_OUTPUT_NAMES:
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
    if not hmac.compare_digest(_snapshot_digest(output_digests), snapshot_sha256):
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


def _candidate_embedded_bytes(value: object, *, label: str) -> bytes:
    if not isinstance(value, dict) or set(value) != {
        "path",
        "sha256",
        "sizeBytes",
        "base64",
    }:
        raise ProjectionBlocked(f"{label} custody binding drifted")
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
    if (
        value.get("repository") != CANDIDATE_UI_REPOSITORY
        or value.get("workflow") != workflow
        or value.get("ref") != CANDIDATE_UI_REF
        or CANDIDATE_COMMIT_RE.fullmatch(str(value.get("sha") or "")) is None
        or any(not isinstance(value.get(name), str) or not value[name] for name in (
            "runId",
            "runAttempt",
            "actor",
            "artifactName",
        ))
    ):
        raise ProjectionBlocked(f"{label} provenance drifted")
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
    first_value = manifest.get(first)
    second_value = manifest.get(second)
    if first_value is not None and second_value is not None and first_value != second_value:
        raise ProjectionBlocked(f"{label} aliases disagree")
    selected = first_value if first_value is not None else second_value
    if not isinstance(selected, str) or not selected:
        raise ProjectionBlocked(f"{label} is missing")
    return selected


def _candidate_windows_scope(
    canonical: dict[str, object],
    candidate_rows: list[dict[str, object]],
    candidate: dict[str, object],
) -> dict[str, object]:
    version = _candidate_manifest_alias(
        canonical, "version", "releaseVersion", label="candidate release version"
    )
    channel = _candidate_manifest_alias(
        canonical, "channelId", "channel", label="candidate release channel"
    )
    if version != candidate["version"]:
        raise ProjectionBlocked("candidate release version differs from its authority identity")
    coverage = canonical.get("desktopTupleCoverage")
    heads_value = coverage.get("requiredDesktopHeads") if isinstance(coverage, dict) else None
    if (
        not isinstance(heads_value, list)
        or not heads_value
        or any(
            not isinstance(head, str) or CANDIDATE_HEAD_RE.fullmatch(head) is None
            for head in heads_value
        )
        or len(set(heads_value)) != len(heads_value)
    ):
        raise ProjectionBlocked("candidate requiredDesktopHeads is invalid")
    heads = tuple(heads_value)
    artifacts_value = canonical.get("artifacts")
    if not isinstance(artifacts_value, list) or not artifacts_value:
        raise ProjectionBlocked("candidate release manifest has no artifacts")
    candidate_by_path = {str(row["path"]): row for row in candidate_rows}
    artifacts: dict[str, dict[str, dict[str, object]]] = {}
    for head in heads:
        matching = [
            artifact
            for artifact in artifacts_value
            if isinstance(artifact, dict)
            and artifact.get("head") == head
            and artifact.get("platform") == "windows"
            and artifact.get("rid") == CANDIDATE_RID
        ]
        installers = [artifact for artifact in matching if artifact.get("kind") == "installer"]
        payloads = [
            artifact
            for artifact in matching
            if artifact.get("kind") in {"archive", "payload"}
            and str(artifact.get("fileName") or "").endswith("-payload.zip")
        ]
        if len(installers) != 1 or len(payloads) != 1:
            raise ProjectionBlocked(
                f"candidate manifest must name one Windows installer and payload for {head}"
            )
        artifacts[head] = {}
        for role, artifact in (("installer", installers[0]), ("payload", payloads[0])):
            file_name = artifact.get("fileName")
            digest = artifact.get("sha256")
            size = artifact.get("sizeBytes")
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
    return {"version": version, "channel": channel, "heads": heads, "artifacts": artifacts}


def _validate_candidate_native_evidence(
    native: object,
    *,
    canonical: dict[str, object],
    candidate_rows: list[dict[str, object]],
    candidate: dict[str, object],
    now: datetime,
) -> None:
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
            raw_entry, label=f"candidate native-Windows {path}"
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
        finalized.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-finalized-inventory"
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
        or provenance.get("contractVersion") != 1
        or provenance.get("release")
        != {"channel": scope["channel"], "version": scope["version"]}
        or provenance.get("manifest")
        != {
            "path": "RELEASE_CHANNEL.generated.json",
            "sha256": candidate["canonicalManifestSha256"],
        }
        or [row["path"] for row in provenance_rows] != sorted(expected_content_paths)
        or provenance != native.get("candidateContentInventory")
        or hashlib.sha256(provenance_bytes).hexdigest()
        != native.get("candidateContentInventorySha256")
    ):
        raise ProjectionBlocked("candidate native-Windows content inventory binding drifted")
    candidate_by_path = {str(row["path"]): row for row in candidate_rows}
    if any(candidate_by_path.get(str(row["path"])) != row for row in provenance_rows):
        raise ProjectionBlocked("candidate native-Windows content bytes drifted")

    capture, capture_bytes, _ = documents[CANDIDATE_CAPTURE_FILE]
    capture_at = _candidate_timestamp(
        capture.get("generatedAt"), label="candidate capture timestamp", now=now
    )
    if (
        capture.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-capture"
        or capture.get("contractVersion") != 1
        or capture.get("status") != "captured"
        or capture.get("captureMode") != "interactive"
        or capture.get("version") != scope["version"]
        or capture.get("channelId") != scope["channel"]
        or capture.get("source") != capture_source
        or capture.get("candidate")
        != {
            "manifestSha256": candidate["canonicalManifestSha256"],
            "contentInventorySha256": hashlib.sha256(provenance_bytes).hexdigest(),
        }
        or capture_at != summary_capture_at
    ):
        raise ProjectionBlocked("candidate native-Windows capture receipt drifted")

    capture_inventory, capture_inventory_bytes, _ = documents[CANDIDATE_CAPTURE_INVENTORY_FILE]
    if (
        capture_inventory.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-capture-inventory"
        or capture_inventory.get("contractVersion") != 1
        or capture_inventory.get("captureManifestSha256")
        != hashlib.sha256(capture_bytes).hexdigest()
    ):
        raise ProjectionBlocked("candidate native-Windows capture inventory drifted")
    _candidate_inventory_rows(
        capture_inventory.get("files"),
        label="candidate native-Windows capture inventory",
        allow_empty=True,
    )

    finalization, _, _ = documents[CANDIDATE_FINALIZATION_FILE]
    finalization_at = _candidate_timestamp(
        finalization.get("generatedAt"),
        label="candidate finalization timestamp",
        now=now,
    )
    proof_rows = finalization.get("proofs")
    if (
        finalization.get("contractName")
        != "chummer6-ui.preview-nightly-native-windows-finalization"
        or finalization.get("contractVersion") != 1
        or finalization.get("status") != "passed"
        or finalization.get("humanReviewConfirmed") is not True
        or finalization.get("reviewerWasCaptureActor") is not False
        or finalization.get("reviewer") != reviewer
        or finalization.get("captureSource") != capture_source
        or finalization.get("finalizationSource") != finalization_source
        or finalization.get("captureInventorySha256")
        != hashlib.sha256(capture_inventory_bytes).hexdigest()
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

    export, _, _ = documents[CANDIDATE_PROVENANCE_EXPORT_FILE]
    if (
        export.get("contractName") != "chummer6-ui.preview-nightly-candidate-export"
        or export.get("contractVersion") != 1
        or export.get("status") != "exported"
    ):
        raise ProjectionBlocked("candidate native-Windows export receipt drifted")

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
            or startup.get("bootstrapPayloadSizeBytes") != payload["sizeBytes"]
            or not isinstance(native_host, dict)
            or native_host.get("contractName") != "chummer6-ui.native_windows_host_evidence"
            or native_host.get("status") != "verified"
            or native_host.get("isNativeWindows") is not True
            or native_host.get("hostPlatform") != "windows"
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
        if (
            proof.get("contractName") != "chummer6-ui.windows_installer_visual_proof"
            or proof.get("contractVersion") != 1
            or proof.get("status") != "passed"
            or proof.get("headId") != head
            or proof.get("platform") != "windows"
            or proof.get("rid") != CANDIDATE_RID
            or proof.get("releaseVersion") != scope["version"]
            or proof.get("channelId") != scope["channel"]
            or proof.get("artifactFileName") != installer["fileName"]
            or proof.get("artifactDigest") != f"sha256:{installer['sha256']}"
            or proof.get("checks")
            != {"capture_mode": "interactive", "human_review_confirmed": True}
            or proof.get("readabilityReview") != {"status": "passed", "reviewer": reviewer}
            or proof.get("contrastReview") != {"status": "passed", "reviewer": reviewer}
            or proof.get("clippingReview") != {"status": "passed", "reviewer": reviewer}
            or proof.get("finalizationBinding") != finalization_source
        ):
            raise ProjectionBlocked(f"candidate {head} visual proof is not a finalized human pass")


def _validate_candidate_import_authority(payload: bytes) -> dict[str, object]:
    authority = _strict_json_object(payload, label="candidate import authority")
    if set(authority) != {
        "contractName",
        "contractVersion",
        "status",
        "generatedAtUtc",
        "expiresAtUtc",
        "candidate",
        "custody",
    } or (
        authority.get("contractName")
        != "chummer.release-upload.candidate-import-authority/v1"
        or authority.get("contractVersion") != 1
        or authority.get("status") != PROJECTION_STATUS_CANDIDATE_IMPORT_READY
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
    if (
        not isinstance(candidate.get("version"), str)
        or not candidate["version"]
        or isinstance(candidate.get("fileCount"), bool)
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
        "inventory",
        "nativeWindowsFinalizedEvidence",
    }:
        raise ProjectionBlocked("candidate import custody property set drifted")
    canonical_bytes = _candidate_embedded_bytes(
        custody.get("canonicalManifest"), label="candidate canonical manifest"
    )
    if hashlib.sha256(canonical_bytes).hexdigest() != candidate["canonicalManifestSha256"]:
        raise ProjectionBlocked("candidate canonical manifest custody digest drifted")
    inventory_bytes = _candidate_embedded_bytes(
        custody.get("inventory"), label="candidate upload inventory"
    )
    inventory = _strict_json_object(
        inventory_bytes, label="candidate upload inventory custody"
    )
    rows = inventory.get("files")
    if (
        inventory.get("contractName")
        != "chummer.release-upload.candidate-inventory/v1"
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
            canonical_row_seen = digest == candidate["canonicalManifestSha256"]
    if (
        not canonical_row_seen
        or total_bytes != candidate["totalBytes"]
        or inventory_digest.hexdigest() != candidate["inventorySha256"]
    ):
        raise ProjectionBlocked("candidate upload inventory custody summary drifted")

    canonical = _strict_json_object(
        canonical_bytes, label="candidate canonical release manifest custody"
    )
    _validate_candidate_native_evidence(
        custody.get("nativeWindowsFinalizedEvidence"),
        canonical=canonical,
        candidate_rows=candidate_rows,
        candidate=candidate,
        now=now,
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
        source_manifest = _strict_json_object(
            _stable_read(
                source.snapshot_directory / SNAPSHOT_MANIFEST_NAME,
                label="source current snapshot manifest",
            ),
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
