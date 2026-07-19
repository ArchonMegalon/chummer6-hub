#!/usr/bin/env python3
"""Build and verify one Hub public projection without partial publication."""

from __future__ import annotations

import ctypes
import errno
import argparse
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
SNAPSHOT_MANIFEST_NAME = "PUBLIC_PROJECTION_SNAPSHOT.generated.json"
CURRENT_POINTER_NAME = "CURRENT.json"
PUBLICATION_LOCK_NAME = ".PUBLIC_PROJECTION.lock"
SNAPSHOT_OUTPUT_NAMES = (
    "HUB_LOCAL_RELEASE_PROOF.generated.json",
    "HUB_SERVED_RELEASE_PROOF.generated.json",
    "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
    "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
    "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
)


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


def _snapshot_digest(output_digests: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for name in SNAPSHOT_OUTPUT_NAMES:
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


def _validate_staged_outputs(output_paths: Mapping[str, Path]) -> tuple[dict[str, bytes], dict[str, str]]:
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
    if windows_payload.get("status") != "pass":
        raise ProjectionBlocked("staged live Windows receipt is not passing")
    return payloads, digests


def resolve_current_snapshot(snapshot_root: Path) -> ProjectionSnapshot:
    """Resolve and authenticate every output through the one atomic CURRENT pointer."""

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
    snapshot_id = str(current_payload.get("snapshotId") or "")
    snapshot_sha256 = str(current_payload.get("snapshotSha256") or "").lower()
    manifest_sha256 = str(current_payload.get("manifestSha256") or "").lower()
    if SNAPSHOT_ID_RE.fullmatch(snapshot_id) is None:
        raise ProjectionBlocked("current public projection pointer snapshot id is invalid")
    if snapshot_id != f"public-projection-{snapshot_sha256}" or SHA256_RE.fullmatch(manifest_sha256) is None:
        raise ProjectionBlocked("current public projection pointer digest binding is invalid")
    expected_pointer_outputs = {
        name: f"{snapshot_id}/{name}" for name in SNAPSHOT_OUTPUT_NAMES
    }
    if (
        current_payload.get("status") != "pass"
        or current_payload.get("manifestRelativePath")
        != f"{snapshot_id}/{SNAPSHOT_MANIFEST_NAME}"
        or current_payload.get("outputs") != expected_pointer_outputs
    ):
        raise ProjectionBlocked("current public projection pointer output inventory drifted")

    snapshot_directory = snapshot_root / snapshot_id
    _require_real_directory(snapshot_directory, label="current public projection snapshot")
    manifest_bytes = _stable_read(
        snapshot_directory / SNAPSHOT_MANIFEST_NAME,
        label="current public projection snapshot manifest",
    )
    if not hmac.compare_digest(hashlib.sha256(manifest_bytes).hexdigest(), manifest_sha256):
        raise ProjectionBlocked("current public projection snapshot manifest digest drifted")
    manifest = _strict_json_object(
        manifest_bytes,
        label="current public projection snapshot manifest",
    )
    if (
        manifest.get("contractName") != SNAPSHOT_CONTRACT
        or manifest.get("snapshotId") != snapshot_id
        or manifest.get("snapshotSha256") != snapshot_sha256
    ):
        raise ProjectionBlocked("current public projection snapshot manifest binding drifted")
    manifest_outputs = manifest.get("outputs")
    if not isinstance(manifest_outputs, dict) or set(manifest_outputs) != set(SNAPSHOT_OUTPUT_NAMES):
        raise ProjectionBlocked("current public projection snapshot output inventory drifted")

    outputs: dict[str, Path] = {}
    output_digests: dict[str, str] = {}
    output_payloads: dict[str, bytes] = {}
    for name in SNAPSHOT_OUTPUT_NAMES:
        entry = manifest_outputs.get(name)
        if not isinstance(entry, dict) or entry.get("relativePath") != name:
            raise ProjectionBlocked("current public projection snapshot output path drifted")
        expected_digest = str(entry.get("sha256") or "").lower()
        if SHA256_RE.fullmatch(expected_digest) is None:
            raise ProjectionBlocked("current public projection snapshot output digest is invalid")
        output_path = snapshot_directory / name
        output_payload = _stable_read(output_path, label=f"current {name}")
        if not hmac.compare_digest(hashlib.sha256(output_payload).hexdigest(), expected_digest):
            raise ProjectionBlocked("current public projection snapshot output digest drifted")
        if entry.get("sizeBytes") != len(output_payload):
            raise ProjectionBlocked("current public projection snapshot output size drifted")
        outputs[name] = output_path
        output_digests[name] = expected_digest
        output_payloads[name] = output_payload
    if not hmac.compare_digest(_snapshot_digest(output_digests), snapshot_sha256):
        raise ProjectionBlocked("current public projection snapshot aggregate digest drifted")
    if output_payloads[SNAPSHOT_OUTPUT_NAMES[0]] != output_payloads[SNAPSHOT_OUTPUT_NAMES[1]]:
        raise ProjectionBlocked("current local and served Hub proofs disagree")
    final_current_bytes = _stable_read(
        current_pointer,
        label="current public projection pointer",
    )
    if not hmac.compare_digest(current_bytes, final_current_bytes):
        raise ProjectionBlocked("current public projection pointer changed during authentication")
    return ProjectionSnapshot(
        current_pointer=current_pointer,
        snapshot_directory=snapshot_directory,
        snapshot_id=snapshot_id,
        snapshot_sha256=snapshot_sha256,
        outputs=outputs,
        output_sha256=output_digests,
    )


def _run_projection_locked(
    source_environment: Mapping[str, str],
    snapshot_root: Path,
    *,
    gate_commands: Iterable[tuple[str, Sequence[str]]] | None = None,
) -> ProjectionSnapshot:
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

        if gate_commands is None:
            gate_commands = (
                ("M120 public launch health", (sys.executable, "scripts/verify_next90_m120_hub_public_launch_health.py")),
                ("M125 public signal packets", (sys.executable, "scripts/verify_next90_m125_hub_public_signal_packets.py")),
                ("M126 hosted proof contracts", (sys.executable, "scripts/verify_next90_m126_hub_hosted_proof_contracts.py")),
                ("desktop native trust receipts", (sys.executable, "scripts/verify_desktop_native_trust_receipts.py")),
                ("M144 release truth alignment", (sys.executable, "scripts/verify_next90_m144_hub_release_truth_alignment.py")),
                (
                    "live public Windows installer",
                    (
                        sys.executable,
                        "scripts/verify_live_public_windows_installer.py",
                        "--output",
                        str(staged_windows_receipt),
                    ),
                ),
            )
        for name, command in gate_commands:
            _run_gate(name, command, environment=child_environment)

        output_paths = {
            "HUB_LOCAL_RELEASE_PROOF.generated.json": staged_proof,
            "HUB_SERVED_RELEASE_PROOF.generated.json": staged_served_proof,
            "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json": staged_m125_proof,
            "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json": staged_m126_proof,
            "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json": staged_windows_receipt,
        }
        output_payloads, output_digests = _validate_staged_outputs(output_paths)
        try:
            for output_path in output_paths.values():
                output_path.chmod(0o644)
        except OSError as exc:
            raise ProjectionBlocked("could not seal staged public projection outputs") from exc
        snapshot_sha256 = _snapshot_digest(output_digests)
        snapshot_id = f"public-projection-{snapshot_sha256}"
        snapshot_manifest = {
            "contractName": SNAPSHOT_CONTRACT,
            "status": "pass",
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
                "status": "pass",
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
) -> ProjectionSnapshot:
    source_environment = dict(os.environ if environment is None else environment)
    snapshot_root = _snapshot_root(source_environment)
    lock_descriptor = _acquire_publication_lock(snapshot_root)
    try:
        return _run_projection_locked(
            source_environment,
            snapshot_root,
            gate_commands=gate_commands,
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
        choices=SNAPSHOT_OUTPUT_NAMES,
        help="Include one authenticated output path and digest in resolve output.",
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
    try:
        if args.resolve_current is not None:
            snapshot = resolve_current_snapshot(args.resolve_current)
            payload: dict[str, object] = {
                "contractName": CURRENT_CONTRACT,
                "status": "pass",
                "snapshotId": snapshot.snapshot_id,
                "snapshotSha256": snapshot.snapshot_sha256,
            }
            if args.output_name:
                payload["output"] = {
                    "name": args.output_name,
                    "path": str(snapshot.outputs[args.output_name]),
                    "sha256": snapshot.output_sha256[args.output_name],
                }
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            return 0
        snapshot = run_projection()
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
        f"{_portable_path(snapshot.current_pointer)} -> {snapshot.snapshot_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
