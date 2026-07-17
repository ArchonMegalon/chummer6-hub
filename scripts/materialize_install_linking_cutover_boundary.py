#!/usr/bin/env python3
"""Record the irreversible InstallLinking PostgreSQL cutover boundary."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    # Keep isolated-mode authority independent of PYTHONPATH while allowing audited siblings.
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

try:
    from scripts.strict_json_contract import strict_json_object
except ModuleNotFoundError:  # Direct ``python3 scripts/...`` execution.
    from strict_json_contract import strict_json_object


CONTRACT_NAME = "chummer.install_linking_postgres_cutover_boundary.v1"
PHASES = (
    "prepare_starting",
    "prepare_completed",
    "import_completed",
    "validate_completed",
    "public_acceptance_completed",
)
MAX_RECEIPT_BYTES = 256 * 1024
MAX_BUILD_INFO_BYTES = 16 * 1024 * 1024


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_existing(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError("cutover boundary receipt must be a caller-owned mode-0600 regular file")
    payload = path.read_bytes()
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ValueError("cutover boundary receipt is oversized")
    # The runbook uses mktemp to reserve a private pathname before the first atomic write.
    if not payload:
        return None
    return strict_json_object(payload, label="InstallLinking cutover boundary receipt")


def bind_active_build_info(path: Path) -> tuple[Path, str]:
    if not path.is_absolute():
        raise ValueError("active build-info path must be absolute")
    normalized = Path(os.path.abspath(path))
    resolved = normalized.resolve(strict=True)
    if resolved != normalized:
        raise ValueError("active build-info path must not contain symlinks")
    metadata = normalized.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError("active build-info must be a single-link regular file")
    if metadata.st_size > MAX_BUILD_INFO_BYTES:
        raise ValueError("active build-info is oversized")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        byte_count = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > MAX_BUILD_INFO_BYTES:
                raise ValueError("active build-info is oversized")
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        or byte_count != before.st_size
        or (before.st_dev, before.st_ino) != (metadata.st_dev, metadata.st_ino)
    ):
        raise ValueError("active build-info changed while it was being bound")
    return normalized, digest.hexdigest()


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("cutover boundary receipt output must not be a symlink")
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
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        directory_descriptor = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def materialize(
    *,
    output: Path,
    phase: str,
    cutover_id: str,
    candidate_image_id: str,
    active_build_info: Path,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError("unsupported cutover boundary phase")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_image_id) is None:
        raise ValueError("candidate image id must be a full lowercase SHA-256 image id")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}", cutover_id) is None:
        raise ValueError("cutover id must be a safe literal of at most 128 characters")
    active_build_info, active_build_info_sha256 = bind_active_build_info(active_build_info)
    existing = load_existing(output)
    phase_index = PHASES.index(phase)
    created_at = now_iso()
    if existing is None:
        if phase != PHASES[0]:
            raise ValueError("cutover boundary receipt must start at prepare_starting")
    else:
        if existing.get("contractName") != CONTRACT_NAME:
            raise ValueError("cutover boundary receipt contract drifted")
        if existing.get("cutoverId") != cutover_id:
            raise ValueError("cutover boundary receipt belongs to another cutover")
        if existing.get("candidateImageId") != candidate_image_id:
            raise ValueError("cutover boundary candidate image identity drifted")
        if (
            existing.get("activeBuildInfoPath") != str(active_build_info)
            or existing.get("activeBuildInfoSha256") != active_build_info_sha256
        ):
            raise ValueError("cutover boundary active build-info binding drifted")
        prior_phase = str(existing.get("phase") or "")
        if prior_phase not in PHASES:
            raise ValueError("cutover boundary prior phase is invalid")
        prior_phase_index = PHASES.index(prior_phase)
        if phase_index < prior_phase_index:
            raise ValueError("cutover boundary phase cannot move backwards")
        if phase_index > prior_phase_index + 1:
            raise ValueError("cutover boundary phase cannot skip an irreversible checkpoint")
        created_at = str(existing.get("createdAtUtc") or created_at)
    accepted = phase == "public_acceptance_completed"
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "status": "pass" if accepted else "in_progress",
        "cutoverId": cutover_id,
        "phase": phase,
        "createdAtUtc": created_at,
        "updatedAtUtc": now_iso(),
        "candidateImageId": candidate_image_id,
        "activeBuildInfoPath": str(active_build_info),
        "activeBuildInfoSha256": active_build_info_sha256,
        "irreversibleDatabaseBoundaryMayHaveBeenEntered": True,
        "prepareCompleted": phase_index >= PHASES.index("prepare_completed"),
        "importCompleted": phase_index >= PHASES.index("import_completed"),
        "validateCompleted": phase_index >= PHASES.index("validate_completed"),
        "publicAcceptanceCompleted": accepted,
        "automaticDatabaseRollbackAllowed": False,
        "recoveryAuthority": {
            "mode": "postgres_pitr_or_governed_recovery",
            "portalAndTunnelMustRemainStoppedUntilAccepted": not accepted,
            "preserveFailedAuthorityAndLogs": True,
            "localMirrorRollbackAllowed": False,
            "schemaOrGenerationRewindAllowed": False,
        },
    }
    atomic_write(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Advance the durable InstallLinking cutover-boundary receipt."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--cutover-id", required=True)
    parser.add_argument("--candidate-image-id", required=True)
    parser.add_argument("--active-build-info", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = materialize(
            output=args.output,
            phase=args.phase,
            cutover_id=args.cutover_id,
            candidate_image_id=args.candidate_image_id,
            active_build_info=args.active_build_info,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
