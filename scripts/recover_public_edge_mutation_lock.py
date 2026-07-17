#!/usr/bin/env python3
"""Manually recover a stale public-edge mutation lock with durable evidence."""

from __future__ import annotations

import argparse
import ctypes
from datetime import UTC, datetime
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Any


LOCK_DIR = Path("/docker/chummercomplete/.state/public-edge-mutation.lock")
RECEIPT_ROOT = Path(
    "/docker/chummercomplete/.state/public-edge-lock-recovery-receipts"
)
TOKEN_FILE_NAME = "owner-token"
CONFIRMATION = "REMOVE_STALE_PUBLIC_EDGE_MUTATION_LOCK"
OPERATOR_ATTESTATION = "I_VERIFIED_NO_PUBLIC_EDGE_MUTATION_IS_RUNNING"
ORPHAN_CONFIRMATION = "REMOVE_ORPHANED_PUBLIC_EDGE_MUTATION_ARTIFACT"
INCOMPLETE_CONFIRMATION = "REMOVE_INCOMPLETE_PUBLIC_EDGE_MUTATION_LOCK"
MINIMUM_ALLOWED_AGE_SECONDS = 300
MAX_TOKEN_BYTES = 128
RENAME_NOREPLACE = 1
AT_FDCWD = -100


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_directory(path: Path, *, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    normalized = Path(os.path.abspath(path))
    current = Path(normalized.anchor)
    for component in normalized.parts[1:]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{label} must not contain symlink components")
    metadata = normalized.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise ValueError(f"{label} must be a caller-owned mode-0700 directory")
    return normalized


def _read_private_token(path: Path, *, label: str) -> tuple[str, os.stat_result]:
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    normalized = Path(os.path.abspath(path))
    metadata = normalized.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError(f"{label} must be a caller-owned single-link mode-0600 file")
    descriptor = os.open(
        normalized,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError(f"{label} changed identity while opening")
        payload = os.read(descriptor, MAX_TOKEN_BYTES + 1)
        if len(payload) > MAX_TOKEN_BYTES:
            raise ValueError(f"{label} is oversized")
    finally:
        os.close(descriptor)
    try:
        token = payload.decode("ascii").strip()
    except UnicodeError as error:
        raise ValueError(f"{label} is not ASCII") from error
    if re.fullmatch(r"[0-9a-f]{64}", token) is None:
        raise ValueError(f"{label} is malformed")
    return token, metadata


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise ValueError("renameat2 is required for crash-consistent recovery")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(destination),
        RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in (errno.EEXIST, errno.ENOTEMPTY):
            raise ValueError("recovery retirement path already exists")
        raise OSError(
            error_number,
            f"cannot atomically retire public-edge mutation lock: {os.strerror(error_number)}",
        )


def _authorization_token(
    owner_token_file: Path,
    *,
    receipt_root: Path,
    expected_device: int | None = None,
    expected_inode: int | None = None,
    expected_mtime_ns: int | None = None,
) -> tuple[str, str, os.stat_result, Path]:
    if not owner_token_file.is_absolute():
        raise ValueError("operator authorization token file must be absolute")
    normalized = Path(os.path.abspath(owner_token_file))
    if normalized.parent != receipt_root:
        raise ValueError(
            "operator authorization token file must be directly inside the canonical receipt root"
        )
    token, metadata = _read_private_token(
        normalized, label="operator authorization token file"
    )
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    if re.fullmatch(rf"[a-z][a-z0-9-]{{0,31}}-{digest}\.owner-token", normalized.name) is None:
        raise ValueError("operator authorization token filename does not bind its token digest")
    expected_values = (expected_device, expected_inode, expected_mtime_ns)
    if any(value is not None for value in expected_values):
        if any(value is None for value in expected_values):
            raise ValueError("authorization identity must be supplied completely")
        if (metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns) != expected_values:
            raise ValueError("operator authorization token identity does not match manual inspection")
    return token, digest, metadata, normalized


def _validate_reason_and_authority(
    *,
    minimum_age_seconds: int,
    reason: str,
    confirmation: str,
    expected_confirmation: str,
    operator_attestation: str,
) -> str:
    if confirmation != expected_confirmation:
        raise ValueError("manual recovery confirmation is missing")
    if operator_attestation != OPERATOR_ATTESTATION:
        raise ValueError("manual no-active-mutation attestation is missing")
    if minimum_age_seconds < MINIMUM_ALLOWED_AGE_SECONDS:
        raise ValueError(
            f"minimum age must be at least {MINIMUM_ALLOWED_AGE_SECONDS} seconds"
        )
    normalized_reason = reason.strip()
    if (
        not normalized_reason
        or len(normalized_reason) > 512
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in normalized_reason
        )
    ):
        raise ValueError(
            "recovery reason must be a nonempty safe literal of at most 512 characters"
        )
    return normalized_reason


def _validate_output(output: Path, *, receipt_root: Path) -> Path:
    if not output.is_absolute():
        raise ValueError("recovery receipt output must be absolute")
    normalized = Path(os.path.abspath(output))
    if normalized.parent != receipt_root:
        raise ValueError(
            "recovery receipt output must be directly inside the canonical receipt root"
        )
    if normalized.exists() or normalized.is_symlink():
        raise ValueError("recovery receipt output must be a new path")
    return normalized


def _age_seconds(metadata: os.stat_result, *, minimum: int, now_ns: int) -> int:
    age_ns = now_ns - metadata.st_mtime_ns
    if age_ns < minimum * 1_000_000_000:
        raise ValueError("public-edge mutation artifact is not old enough for manual recovery")
    return age_ns // 1_000_000_000


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    if path.is_symlink():
        raise ValueError("stale-lock recovery receipt output must not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def recover_stale_lock(
    *,
    lock_dir: Path,
    receipt_root: Path,
    output: Path,
    owner_token_file: Path,
    expected_device: int,
    expected_inode: int,
    expected_mtime_ns: int,
    minimum_age_seconds: int,
    reason: str,
    confirmation: str,
    operator_attestation: str,
    expected_authorization_device: int | None = None,
    expected_authorization_inode: int | None = None,
    expected_authorization_mtime_ns: int | None = None,
    now_ns: int | None = None,
) -> dict[str, Any]:
    normalized_reason = _validate_reason_and_authority(
        minimum_age_seconds=minimum_age_seconds,
        reason=reason,
        confirmation=confirmation,
        expected_confirmation=CONFIRMATION,
        operator_attestation=operator_attestation,
    )

    receipt_root = _validate_directory(receipt_root, label="recovery receipt root")
    output = _validate_output(output, receipt_root=receipt_root)
    authorization_token, token_digest, authorization_metadata, owner_token_file = (
        _authorization_token(
            owner_token_file,
            receipt_root=receipt_root,
            expected_device=expected_authorization_device,
            expected_inode=expected_authorization_inode,
            expected_mtime_ns=expected_authorization_mtime_ns,
        )
    )

    lock_dir = _validate_directory(lock_dir, label="public-edge mutation lock")
    lock_metadata = lock_dir.lstat()
    actual_identity = (lock_metadata.st_dev, lock_metadata.st_ino, lock_metadata.st_mtime_ns)
    expected_identity = (expected_device, expected_inode, expected_mtime_ns)
    if actual_identity != expected_identity:
        raise ValueError("public-edge mutation lock identity does not match manual inspection")
    current_ns = time.time_ns() if now_ns is None else now_ns
    observed_age_seconds = _age_seconds(
        lock_metadata, minimum=minimum_age_seconds, now_ns=current_ns
    )

    token_path = lock_dir / TOKEN_FILE_NAME
    lock_token, lock_token_metadata = _read_private_token(
        token_path, label="stale lock owner token"
    )
    if not hmac.compare_digest(authorization_token, lock_token):
        raise ValueError("operator authorization token does not own the stale lock")
    entries = sorted(entry.name for entry in os.scandir(lock_dir))
    if entries != [TOKEN_FILE_NAME]:
        raise ValueError("stale public-edge mutation lock contains unexpected entries")

    authorized_at = _now()
    receipt: dict[str, Any] = {
        "contractName": "chummer.public_edge_mutation_lock_recovery.v1",
        "status": "in_progress",
        "authorizedAtUtc": authorized_at,
        "removedAtUtc": None,
        "lockPath": str(lock_dir),
        "lockDevice": lock_metadata.st_dev,
        "lockInode": lock_metadata.st_ino,
        "lockMtimeNs": lock_metadata.st_mtime_ns,
        "minimumAgeSeconds": minimum_age_seconds,
        "observedAgeSeconds": observed_age_seconds,
        "ownerTokenSha256": token_digest,
        "authorizationPath": str(owner_token_file),
        "authorizationDevice": authorization_metadata.st_dev,
        "authorizationInode": authorization_metadata.st_ino,
        "authorizationMtimeNs": authorization_metadata.st_mtime_ns,
        "operatorAttestation": OPERATOR_ATTESTATION,
        "reason": normalized_reason,
        "automaticRecovery": False,
    }
    _atomic_write(output, receipt)

    current_lock = lock_dir.lstat()
    current_token = token_path.lstat()
    current_authorization = owner_token_file.lstat()
    if (
        (current_lock.st_dev, current_lock.st_ino, current_lock.st_mtime_ns)
        != actual_identity
        or (current_token.st_dev, current_token.st_ino)
        != (lock_token_metadata.st_dev, lock_token_metadata.st_ino)
        or (
            current_authorization.st_dev,
            current_authorization.st_ino,
            current_authorization.st_mtime_ns,
        )
        != (
            authorization_metadata.st_dev,
            authorization_metadata.st_ino,
            authorization_metadata.st_mtime_ns,
        )
    ):
        raise ValueError("stale lock identity changed after authorization")
    current_lock_token, _ = _read_private_token(
        token_path, label="stale lock owner token"
    )
    current_authorization_token, _ = _read_private_token(
        owner_token_file, label="operator authorization token file"
    )
    if not (
        hmac.compare_digest(current_lock_token, lock_token)
        and hmac.compare_digest(current_authorization_token, authorization_token)
    ):
        raise ValueError("stale lock capability changed after authorization")
    retired = lock_dir.parent / f".{lock_dir.name}.retired.{token_digest}"
    _rename_noreplace(lock_dir, retired)
    _fsync_directory(lock_dir.parent)
    retired_token = retired / TOKEN_FILE_NAME
    retired_token.unlink()
    retired.rmdir()
    _fsync_directory(lock_dir.parent)
    owner_token_file.unlink()
    _fsync_directory(receipt_root)

    receipt["status"] = "pass"
    receipt["removedAtUtc"] = _now()
    _atomic_write(output, receipt)
    return receipt


def cleanup_orphaned_artifact(
    *,
    lock_path: Path,
    receipt_root: Path,
    output: Path,
    owner_token_file: Path,
    artifact_path: Path | None,
    expected_authorization_device: int,
    expected_authorization_inode: int,
    expected_authorization_mtime_ns: int,
    expected_artifact_device: int | None,
    expected_artifact_inode: int | None,
    expected_artifact_mtime_ns: int | None,
    minimum_age_seconds: int,
    reason: str,
    confirmation: str,
    operator_attestation: str,
    now_ns: int | None = None,
) -> dict[str, Any]:
    """Remove a digest-bound staging/retired/auth orphan after manual inspection."""

    normalized_reason = _validate_reason_and_authority(
        minimum_age_seconds=minimum_age_seconds,
        reason=reason,
        confirmation=confirmation,
        expected_confirmation=ORPHAN_CONFIRMATION,
        operator_attestation=operator_attestation,
    )
    receipt_root = _validate_directory(receipt_root, label="recovery receipt root")
    output = _validate_output(output, receipt_root=receipt_root)
    token, token_digest, authorization_metadata, owner_token_file = _authorization_token(
        owner_token_file,
        receipt_root=receipt_root,
        expected_device=expected_authorization_device,
        expected_inode=expected_authorization_inode,
        expected_mtime_ns=expected_authorization_mtime_ns,
    )
    current_ns = time.time_ns() if now_ns is None else now_ns
    authorization_age = _age_seconds(
        authorization_metadata, minimum=minimum_age_seconds, now_ns=current_ns
    )

    if not lock_path.is_absolute():
        raise ValueError("public-edge mutation lock path must be absolute")
    lock_path = Path(os.path.abspath(lock_path))
    lock_root = _validate_directory(lock_path.parent, label="public-edge lock root")

    artifact: Path | None = None
    artifact_metadata: os.stat_result | None = None
    internal_metadata: os.stat_result | None = None
    artifact_kind = "authorization_only"
    artifact_age: int | None = None
    if artifact_path is not None:
        if not artifact_path.is_absolute():
            raise ValueError("orphaned mutation artifact path must be absolute")
        artifact = Path(os.path.abspath(artifact_path))
        if artifact.parent != lock_root:
            raise ValueError("orphaned mutation artifact must be directly inside the lock root")
        match = re.fullmatch(
            rf"\.{re.escape(lock_path.name)}\.(staging|retired)\.{token_digest}",
            artifact.name,
        )
        if match is None:
            raise ValueError("orphaned mutation artifact name does not bind the authorization digest")
        artifact_kind = match.group(1)
        artifact = _validate_directory(artifact, label="orphaned mutation artifact")
        artifact_metadata = artifact.lstat()
        supplied_identity = (
            expected_artifact_device,
            expected_artifact_inode,
            expected_artifact_mtime_ns,
        )
        if any(value is None for value in supplied_identity):
            raise ValueError("orphaned mutation artifact identity must be supplied completely")
        if (
            artifact_metadata.st_dev,
            artifact_metadata.st_ino,
            artifact_metadata.st_mtime_ns,
        ) != supplied_identity:
            raise ValueError("orphaned mutation artifact identity does not match manual inspection")
        artifact_age = _age_seconds(
            artifact_metadata, minimum=minimum_age_seconds, now_ns=current_ns
        )
        entries = sorted(entry.name for entry in os.scandir(artifact))
        if entries not in ([], [TOKEN_FILE_NAME]):
            raise ValueError("orphaned mutation artifact contains unexpected entries")
        if entries:
            internal_token, internal_metadata = _read_private_token(
                artifact / TOKEN_FILE_NAME,
                label="orphaned mutation artifact owner token",
            )
            if not hmac.compare_digest(token, internal_token):
                raise ValueError("orphaned mutation artifact capability mismatch")
    else:
        expected_artifact_values = (
            expected_artifact_device,
            expected_artifact_inode,
            expected_artifact_mtime_ns,
        )
        if any(value is not None for value in expected_artifact_values):
            raise ValueError("authorization-only cleanup must not supply an artifact identity")
        for entry in os.scandir(lock_root):
            if entry.name.endswith(f".{token_digest}"):
                raise ValueError("a digest-bound mutation artifact still requires explicit cleanup")
        if lock_path.exists():
            candidate_token = lock_path / TOKEN_FILE_NAME
            if candidate_token.exists():
                fixed_token, _ = _read_private_token(
                    candidate_token, label="fixed mutation lock owner token"
                )
                if hashlib.sha256(fixed_token.encode("ascii")).hexdigest() == token_digest:
                    raise ValueError("authorization still owns the fixed mutation lock")

    receipt: dict[str, Any] = {
        "contractName": "chummer.public_edge_mutation_lock_recovery.v1",
        "recoveryMode": "orphan_cleanup",
        "status": "in_progress",
        "authorizedAtUtc": _now(),
        "removedAtUtc": None,
        "artifactKind": artifact_kind,
        "artifactPath": str(artifact) if artifact is not None else None,
        "artifactDevice": artifact_metadata.st_dev if artifact_metadata else None,
        "artifactInode": artifact_metadata.st_ino if artifact_metadata else None,
        "artifactMtimeNs": artifact_metadata.st_mtime_ns if artifact_metadata else None,
        "observedArtifactAgeSeconds": artifact_age,
        "authorizationPath": str(owner_token_file),
        "authorizationDevice": authorization_metadata.st_dev,
        "authorizationInode": authorization_metadata.st_ino,
        "authorizationMtimeNs": authorization_metadata.st_mtime_ns,
        "observedAuthorizationAgeSeconds": authorization_age,
        "minimumAgeSeconds": minimum_age_seconds,
        "ownerTokenSha256": token_digest,
        "operatorAttestation": OPERATOR_ATTESTATION,
        "reason": normalized_reason,
        "automaticRecovery": False,
    }
    _atomic_write(output, receipt)

    current_authorization = owner_token_file.lstat()
    if (
        current_authorization.st_dev,
        current_authorization.st_ino,
        current_authorization.st_mtime_ns,
    ) != (
        authorization_metadata.st_dev,
        authorization_metadata.st_ino,
        authorization_metadata.st_mtime_ns,
    ):
        raise ValueError("authorization identity changed after orphan cleanup authorization")
    current_authorization_token, _ = _read_private_token(
        owner_token_file, label="operator authorization token file"
    )
    if not hmac.compare_digest(current_authorization_token, token):
        raise ValueError("authorization capability changed after orphan cleanup authorization")
    if artifact is not None and artifact_metadata is not None:
        current_artifact = artifact.lstat()
        if (
            current_artifact.st_dev,
            current_artifact.st_ino,
            current_artifact.st_mtime_ns,
        ) != (
            artifact_metadata.st_dev,
            artifact_metadata.st_ino,
            artifact_metadata.st_mtime_ns,
        ):
            raise ValueError("orphaned mutation artifact identity changed after authorization")
        if internal_metadata is not None:
            current_internal = (artifact / TOKEN_FILE_NAME).lstat()
            if (current_internal.st_dev, current_internal.st_ino) != (
                internal_metadata.st_dev,
                internal_metadata.st_ino,
            ):
                raise ValueError("orphaned mutation capability identity changed after authorization")
            current_internal_token, _ = _read_private_token(
                artifact / TOKEN_FILE_NAME,
                label="orphaned mutation artifact owner token",
            )
            if not hmac.compare_digest(current_internal_token, token):
                raise ValueError("orphaned mutation capability changed after authorization")
            (artifact / TOKEN_FILE_NAME).unlink()
        artifact.rmdir()
        _fsync_directory(lock_root)
    owner_token_file.unlink()
    _fsync_directory(receipt_root)
    receipt["status"] = "pass"
    receipt["removedAtUtc"] = _now()
    _atomic_write(output, receipt)
    return receipt


def recover_incomplete_lock(
    *,
    lock_dir: Path,
    receipt_root: Path,
    output: Path,
    owner_token_file: Path,
    expected_device: int,
    expected_inode: int,
    expected_mtime_ns: int,
    expected_authorization_device: int,
    expected_authorization_inode: int,
    expected_authorization_mtime_ns: int,
    minimum_age_seconds: int,
    reason: str,
    confirmation: str,
    operator_attestation: str,
    now_ns: int | None = None,
) -> dict[str, Any]:
    """Remove a manually inspected empty fixed lock left by a legacy partial publish."""

    normalized_reason = _validate_reason_and_authority(
        minimum_age_seconds=minimum_age_seconds,
        reason=reason,
        confirmation=confirmation,
        expected_confirmation=INCOMPLETE_CONFIRMATION,
        operator_attestation=operator_attestation,
    )
    receipt_root = _validate_directory(receipt_root, label="recovery receipt root")
    output = _validate_output(output, receipt_root=receipt_root)
    _token, token_digest, authorization_metadata, owner_token_file = _authorization_token(
        owner_token_file,
        receipt_root=receipt_root,
        expected_device=expected_authorization_device,
        expected_inode=expected_authorization_inode,
        expected_mtime_ns=expected_authorization_mtime_ns,
    )
    lock_dir = _validate_directory(lock_dir, label="incomplete public-edge mutation lock")
    lock_metadata = lock_dir.lstat()
    actual_identity = (
        lock_metadata.st_dev,
        lock_metadata.st_ino,
        lock_metadata.st_mtime_ns,
    )
    if actual_identity != (expected_device, expected_inode, expected_mtime_ns):
        raise ValueError("incomplete mutation lock identity does not match manual inspection")
    if list(os.scandir(lock_dir)):
        raise ValueError("incomplete mutation lock recovery accepts only an empty fixed lock")
    current_ns = time.time_ns() if now_ns is None else now_ns
    lock_age = _age_seconds(
        lock_metadata, minimum=minimum_age_seconds, now_ns=current_ns
    )
    authorization_age = _age_seconds(
        authorization_metadata, minimum=minimum_age_seconds, now_ns=current_ns
    )
    receipt: dict[str, Any] = {
        "contractName": "chummer.public_edge_mutation_lock_recovery.v1",
        "recoveryMode": "incomplete_fixed_lock",
        "status": "in_progress",
        "authorizedAtUtc": _now(),
        "removedAtUtc": None,
        "lockPath": str(lock_dir),
        "lockDevice": lock_metadata.st_dev,
        "lockInode": lock_metadata.st_ino,
        "lockMtimeNs": lock_metadata.st_mtime_ns,
        "observedAgeSeconds": lock_age,
        "authorizationPath": str(owner_token_file),
        "authorizationDevice": authorization_metadata.st_dev,
        "authorizationInode": authorization_metadata.st_ino,
        "authorizationMtimeNs": authorization_metadata.st_mtime_ns,
        "observedAuthorizationAgeSeconds": authorization_age,
        "minimumAgeSeconds": minimum_age_seconds,
        "ownerTokenSha256": token_digest,
        "operatorAttestation": OPERATOR_ATTESTATION,
        "reason": normalized_reason,
        "automaticRecovery": False,
    }
    _atomic_write(output, receipt)
    current_lock = lock_dir.lstat()
    current_authorization = owner_token_file.lstat()
    if (
        current_lock.st_dev,
        current_lock.st_ino,
        current_lock.st_mtime_ns,
    ) != actual_identity or (
        current_authorization.st_dev,
        current_authorization.st_ino,
        current_authorization.st_mtime_ns,
    ) != (
        authorization_metadata.st_dev,
        authorization_metadata.st_ino,
        authorization_metadata.st_mtime_ns,
    ):
        raise ValueError("incomplete mutation lock identity changed after authorization")
    current_authorization_token, _ = _read_private_token(
        owner_token_file, label="operator authorization token file"
    )
    if hashlib.sha256(current_authorization_token.encode("ascii")).hexdigest() != token_digest:
        raise ValueError("authorization capability changed after incomplete lock authorization")
    lock_dir.rmdir()
    _fsync_directory(lock_dir.parent)
    owner_token_file.unlink()
    _fsync_directory(receipt_root)
    receipt["status"] = "pass"
    receipt["removedAtUtc"] = _now()
    _atomic_write(output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manually recover an authenticated stale public-edge mutation lock."
    )
    parser.add_argument(
        "--mode",
        choices=("stale-lock", "orphan", "incomplete-lock"),
        default="stale-lock",
    )
    parser.add_argument("--owner-token-file", type=Path, required=True)
    parser.add_argument("--expected-lock-device", type=int)
    parser.add_argument("--expected-lock-inode", type=int)
    parser.add_argument("--expected-lock-mtime-ns", type=int)
    parser.add_argument("--expected-authorization-device", type=int, required=True)
    parser.add_argument("--expected-authorization-inode", type=int, required=True)
    parser.add_argument("--expected-authorization-mtime-ns", type=int, required=True)
    parser.add_argument("--orphan-path", type=Path)
    parser.add_argument("--expected-artifact-device", type=int)
    parser.add_argument("--expected-artifact-inode", type=int)
    parser.add_argument("--expected-artifact-mtime-ns", type=int)
    parser.add_argument("--minimum-age-seconds", type=int, default=900)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--operator-attestation", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        lock_identity = (
            args.expected_lock_device,
            args.expected_lock_inode,
            args.expected_lock_mtime_ns,
        )
        common = {
            "receipt_root": RECEIPT_ROOT,
            "output": args.output,
            "owner_token_file": args.owner_token_file,
            "expected_authorization_device": args.expected_authorization_device,
            "expected_authorization_inode": args.expected_authorization_inode,
            "expected_authorization_mtime_ns": args.expected_authorization_mtime_ns,
            "minimum_age_seconds": args.minimum_age_seconds,
            "reason": args.reason,
            "confirmation": args.confirm,
            "operator_attestation": args.operator_attestation,
        }
        if args.mode == "orphan":
            if any(value is not None for value in lock_identity):
                raise ValueError("orphan cleanup must not supply a fixed lock identity")
            receipt = cleanup_orphaned_artifact(
                lock_path=LOCK_DIR,
                artifact_path=args.orphan_path,
                expected_artifact_device=args.expected_artifact_device,
                expected_artifact_inode=args.expected_artifact_inode,
                expected_artifact_mtime_ns=args.expected_artifact_mtime_ns,
                **common,
            )
        else:
            if any(value is None for value in lock_identity):
                raise ValueError("fixed lock identity must be supplied completely")
            if args.orphan_path is not None or any(
                value is not None
                for value in (
                    args.expected_artifact_device,
                    args.expected_artifact_inode,
                    args.expected_artifact_mtime_ns,
                )
            ):
                raise ValueError("fixed lock recovery must not supply orphan artifact inputs")
            fixed_common = {
                "lock_dir": LOCK_DIR,
                "expected_device": args.expected_lock_device,
                "expected_inode": args.expected_lock_inode,
                "expected_mtime_ns": args.expected_lock_mtime_ns,
                **common,
            }
            if args.mode == "incomplete-lock":
                receipt = recover_incomplete_lock(**fixed_common)
            else:
                receipt = recover_stale_lock(**fixed_common)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(receipt, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
