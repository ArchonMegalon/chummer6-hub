#!/usr/bin/env python3
"""Verify the complete predeploy InstallLinking PostgreSQL cutover boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Sequence

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

try:
    from scripts.materialize_install_linking_cutover_boundary import (
        CONTRACT_NAME,
        bind_active_build_info,
        bind_all_postquiesce_reproofs,
        bind_cutover_run_receipt,
        load_existing,
        validate_existing_boundary_chain,
    )
except ModuleNotFoundError:
    from materialize_install_linking_cutover_boundary import (
        CONTRACT_NAME,
        bind_active_build_info,
        bind_all_postquiesce_reproofs,
        bind_cutover_run_receipt,
        load_existing,
        validate_existing_boundary_chain,
    )


VERIFICATION_CONTRACT = (
    "chummer.install_linking_postgres_cutover_boundary_verification.v1"
)
HEX_SHA256 = re.compile(r"[0-9a-f]{64}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
GIT_HEAD = re.compile(r"[0-9a-f]{40}")
MAX_INPUT_BYTES = 16 * 1024 * 1024


def stable_file_sha256(path: Path, *, owner_only: bool) -> str:
    if not path.is_absolute():
        raise ValueError("verified input path must be absolute")
    normalized = Path(os.path.abspath(path))
    current = Path(normalized.anchor)
    for component in normalized.parts[1:]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("verified input path must not contain symlinks")
    metadata = normalized.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size <= 0
        or metadata.st_size > MAX_INPUT_BYTES
        or (
            owner_only
            and (
                metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
            )
        )
    ):
        raise ValueError("verified input is not a safe bounded regular file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise ValueError("verified input is oversized")
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_after = normalized.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        or identity
        != (
            path_after.st_dev,
            path_after.st_ino,
            path_after.st_size,
            path_after.st_mtime_ns,
            path_after.st_ctime_ns,
        )
        or total != before.st_size
    ):
        raise ValueError("verified input changed while hashing")
    return digest.hexdigest()


def verify_boundary(
    *,
    boundary: Path,
    expected_boundary_sha256: str,
    expected_cutover_id: str | None,
    expected_source_head: str,
    expected_candidate_image_id: str,
    expected_candidate_tool_image_id: str,
    observed_candidate_image_id: str,
    observed_candidate_tool_image_id: str,
    source_root: Path,
    env_file: Path,
    expected_phase: str = "validate_completed",
) -> dict[str, Any]:
    if expected_phase not in {
        "validate_completed",
        "public_acceptance_completed",
    }:
        raise ValueError("expected cutover phase is invalid")
    expected_status = (
        "pass"
        if expected_phase == "public_acceptance_completed"
        else "in_progress"
    )
    expected_sequence = (
        5 if expected_phase == "public_acceptance_completed" else 4
    )
    expected_public_acceptance = (
        expected_phase == "public_acceptance_completed"
    )
    if (
        HEX_SHA256.fullmatch(expected_boundary_sha256) is None
        or GIT_HEAD.fullmatch(expected_source_head) is None
        or any(
            IMAGE_ID.fullmatch(value) is None
            for value in (
                expected_candidate_image_id,
                expected_candidate_tool_image_id,
                observed_candidate_image_id,
                observed_candidate_tool_image_id,
            )
        )
    ):
        raise ValueError("independent cutover identity input is invalid")
    boundary = Path(os.path.abspath(boundary))
    source_root = Path(os.path.abspath(source_root))
    env_file = Path(os.path.abspath(env_file))
    if stable_file_sha256(boundary, owner_only=True) != expected_boundary_sha256:
        raise ValueError("cutover boundary digest differs from the independent pin")
    if (
        observed_candidate_image_id != expected_candidate_image_id
        or observed_candidate_tool_image_id != expected_candidate_tool_image_id
    ):
        raise ValueError("locally observed unique candidate image identity drifted")
    receipt, receipt_sha256 = load_existing(boundary)
    if expected_cutover_id is None:
        derived_cutover_id = (
            receipt.get("cutoverId") if isinstance(receipt, dict) else None
        )
        if (
            not isinstance(derived_cutover_id, str)
            or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}",
                derived_cutover_id,
            )
            is None
        ):
            raise ValueError("cutover id is missing from the pinned boundary")
        expected_cutover_id = derived_cutover_id
    if (
        receipt is None
        or receipt_sha256 != expected_boundary_sha256
        or receipt.get("contractName") != CONTRACT_NAME
        or receipt.get("status") != expected_status
        or receipt.get("phase") != expected_phase
        or receipt.get("sequence") != expected_sequence
        or receipt.get("cutoverId") != expected_cutover_id
        or receipt.get("candidateImageId") != expected_candidate_image_id
        or receipt.get("candidateToolImageId")
        != expected_candidate_tool_image_id
        or receipt.get("validateCompleted") is not True
        or receipt.get("publicAcceptanceCompleted")
        is not expected_public_acceptance
        or receipt.get("importDisposition") != "skipped_no_local_store"
    ):
        raise ValueError("cutover boundary is not the complete predeploy checkpoint")
    build_info_path = Path(str(receipt.get("activeBuildInfoPath") or ""))
    (
        bound_build_info,
        build_info_sha256,
        build_info,
    ) = bind_active_build_info(
        build_info_path,
        cutover_id=expected_cutover_id,
        candidate_image_id=expected_candidate_image_id,
        candidate_tool_image_id=expected_candidate_tool_image_id,
    )
    if (
        receipt.get("activeBuildInfoPath") != str(bound_build_info)
        or receipt.get("activeBuildInfoSha256") != build_info_sha256
        or build_info.get("sourceHead") != expected_source_head
        or build_info.get("composeSha256")
        != stable_file_sha256(
            source_root / "docker-compose.public-edge.yml",
            owner_only=False,
        )
        or build_info.get("runnerSha256")
        != stable_file_sha256(
            source_root
            / "scripts"
            / "run_install_linking_postgres_cutover.py",
            owner_only=False,
        )
        or build_info.get("envSha256")
        != stable_file_sha256(env_file, owner_only=True)
    ):
        raise ValueError("cutover candidate build-info source binding drifted")
    validate_existing_boundary_chain(
        boundary,
        receipt,
        cutover_id=expected_cutover_id,
        candidate_image_id=expected_candidate_image_id,
        candidate_tool_image_id=expected_candidate_tool_image_id,
        active_build_info=bound_build_info,
        active_build_info_sha256=build_info_sha256,
        active_build_info_payload=build_info,
    )
    final_run = bind_cutover_run_receipt(
        boundary,
        cutover_id=expected_cutover_id,
        candidate_image_id=expected_candidate_image_id,
        candidate_tool_image_id=expected_candidate_tool_image_id,
        candidate_build_info_path=bound_build_info,
        candidate_build_info_sha256=build_info_sha256,
        required=True,
    )
    if final_run is None:
        raise ValueError("passing InstallLinking final run receipt is missing")
    final_run_path, final_run_sha256, final_run_payload = final_run
    bind_all_postquiesce_reproofs(
        boundary,
        cutover_id=expected_cutover_id,
        candidate_image_id=expected_candidate_image_id,
        candidate_tool_image_id=expected_candidate_tool_image_id,
        candidate_build_info_sha256=build_info_sha256,
        candidate_build_info=build_info,
    )
    return {
        "activeBuildInfoPath": str(bound_build_info),
        "activeBuildInfoSha256": build_info_sha256,
        "boundaryReceiptPath": str(boundary),
        "boundaryReceiptSha256": receipt_sha256,
        "candidateImageId": expected_candidate_image_id,
        "candidatePortalTag": build_info["candidatePortalTag"],
        "candidateToolImageId": expected_candidate_tool_image_id,
        "candidateToolTag": build_info["candidateToolTag"],
        "canonicalPortalTagIdBeforeAndAfter": build_info[
            "canonicalPortalTagIdBeforeAndAfter"
        ],
        "canonicalToolTagIdBeforeAndAfter": build_info[
            "canonicalToolTagIdBeforeAndAfter"
        ],
        "composeSha256": build_info["composeSha256"],
        "contractName": VERIFICATION_CONTRACT,
        "cutoverId": expected_cutover_id,
        "envSha256": build_info["envSha256"],
        "finalRunReceiptPath": str(final_run_path),
        "finalRunReceiptSha256": final_run_sha256,
        "finalRunReceiptStatus": final_run_payload["status"],
        "phase": expected_phase,
        "runnerSha256": build_info["runnerSha256"],
        "sourceHead": expected_source_head,
        "status": "pass",
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--expected-boundary-sha256", required=True)
    parser.add_argument("--expected-cutover-id")
    parser.add_argument("--expected-source-head", required=True)
    parser.add_argument("--expected-candidate-image-id", required=True)
    parser.add_argument("--expected-candidate-tool-image-id", required=True)
    parser.add_argument("--observed-candidate-image-id", required=True)
    parser.add_argument("--observed-candidate-tool-image-id", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument(
        "--expected-phase",
        choices=("validate_completed", "public_acceptance_completed"),
        default="validate_completed",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        payload = verify_boundary(
            **vars(parse_args(sys.argv[1:] if argv is None else argv))
        )
    except (OSError, ValueError) as exc:
        print(f"InstallLinking cutover boundary rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
