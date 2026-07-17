#!/usr/bin/env python3
"""Bind a restarted portal container to the exact governed overlay and source tree."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Callable

try:
    from scripts.strict_json_contract import StrictJsonContractError, strict_json_object
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from strict_json_contract import StrictJsonContractError, strict_json_object

try:
    from scripts.publish_public_edge_portal_overlay import (
        FULL_DEPLOYMENT_DIGEST_ALGORITHM,
        FULL_DEPLOYMENT_DIGEST_CONTRACT_NAME,
        full_deployment_digest,
        source_fingerprint,
        staged_payload_fingerprint,
        validate_payload_modes_against_receipt,
    )
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from publish_public_edge_portal_overlay import (
        FULL_DEPLOYMENT_DIGEST_ALGORITHM,
        FULL_DEPLOYMENT_DIGEST_CONTRACT_NAME,
        full_deployment_digest,
        source_fingerprint,
        staged_payload_fingerprint,
        validate_payload_modes_against_receipt,
    )


BUILD_INFO_RELATIVE_PATH = (
    Path(".codex-studio")
    / "runtime"
    / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
)
EXPECTED_PREFLIGHT_CONTRACT = "chummer.public_edge_deploy_preflight.v1"
EXPECTED_BUILD_INFO_CONTRACT = "chummer.public_edge_portal_overlay_publish.v1"
MAX_JSON_BYTES = 16 * 1024 * 1024


class OverlayBindingError(RuntimeError):
    pass


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _read_regular_bytes(path: Path, *, owner_only: bool) -> bytes:
    normalized = _absolute(path)
    try:
        path_stat = normalized.lstat()
    except OSError as exc:
        raise OverlayBindingError("cutover binding input is unavailable") from exc
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or stat.S_ISLNK(path_stat.st_mode)
        or path_stat.st_nlink != 1
        or path_stat.st_size <= 0
        or path_stat.st_size > MAX_JSON_BYTES
    ):
        raise OverlayBindingError("cutover binding input is invalid")
    if owner_only and path_stat.st_mode & 0o077:
        raise OverlayBindingError("cutover binding receipt must be owner-only")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(normalized, flags)
    except OSError as exc:
        raise OverlayBindingError("cutover binding input cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (before.st_dev, before.st_ino)
            != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise OverlayBindingError("cutover binding input changed before read")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_JSON_BYTES:
                raise OverlayBindingError("cutover binding input is too large")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_nlink, stat.S_IMODE(before.st_mode))
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_nlink, stat.S_IMODE(after.st_mode))
        or total != before.st_size
    ):
        raise OverlayBindingError("cutover binding input changed while being read")
    try:
        path_after = normalized.lstat()
    except OSError as exc:
        raise OverlayBindingError("cutover binding input pathname changed after read") from exc
    if (
        not stat.S_ISREG(path_after.st_mode)
        or path_after.st_nlink != 1
        or (
            path_after.st_dev,
            path_after.st_ino,
            path_after.st_size,
            path_after.st_mtime_ns,
            path_after.st_ctime_ns,
            path_after.st_nlink,
            stat.S_IMODE(path_after.st_mode),
        )
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
            stat.S_IMODE(after.st_mode),
        )
    ):
        raise OverlayBindingError("cutover binding input pathname changed after read")
    return b"".join(chunks)


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        return strict_json_object(raw, label=label)
    except StrictJsonContractError as exc:
        raise OverlayBindingError(f"{label} is not valid UTF-8 JSON") from exc


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise OverlayBindingError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise OverlayBindingError(f"{label} is invalid") from exc
    if parsed.tzinfo is None:
        raise OverlayBindingError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)


def validate_binding(
    *,
    preflight: dict[str, Any],
    active_build_info_bytes: bytes,
    container_build_info_bytes: bytes,
    source_root: Path,
    active_root: Path,
    not_before_utc: datetime,
    fingerprint_provider: Callable[[Path], dict[str, Any]] = source_fingerprint,
    staged_fingerprint_provider: Callable[[Path], dict[str, Any]] = staged_payload_fingerprint,
) -> None:
    normalized_source = source_root.resolve()
    normalized_active = active_root.resolve()
    if (
        preflight.get("contractName") != EXPECTED_PREFLIGHT_CONTRACT
        or preflight.get("status") != "pass"
        or Path(str(preflight.get("sourceRoot") or "")).resolve() != normalized_source
        or Path(str(preflight.get("overlayRoot") or "")).resolve() != normalized_active
        or _utc(preflight.get("generatedAtUtc"), "preflight generatedAtUtc")
        < not_before_utc.astimezone(UTC)
    ):
        raise OverlayBindingError("post-activation preflight is not bound to this cutover")

    binding = preflight.get("overlayBuildInfoSourceFingerprint")
    if not isinstance(binding, dict):
        raise OverlayBindingError("overlay fingerprint binding is missing")
    recorded = binding.get("recordedAggregateSha256")
    expected = binding.get("expectedAggregateSha256")
    recorded_full_deployment_sha256 = binding.get(
        "recordedFullDeploymentDigestSha256"
    )
    expected_full_deployment_sha256 = binding.get(
        "expectedFullDeploymentDigestSha256"
    )
    if (
        binding.get("aggregateMatchesCurrentSource") is not True
        or binding.get("fullDeploymentDigestMatchesRecordedInputs") is not True
        or binding.get("fullDeploymentDigestMatchesCurrentDeployment") is not True
        or (binding.get("payloadModeBinding") or {}).get("status") != "pass"
        or binding.get("sourceRootMatches") is not True
        or binding.get("missingKeys") != []
        or binding.get("mismatchedKeys") != []
        or binding.get("semanticMismatches") != []
        or not isinstance(recorded, str)
        or len(recorded) != 64
        or recorded != expected
        or not isinstance(recorded_full_deployment_sha256, str)
        or len(recorded_full_deployment_sha256) != 64
        or recorded_full_deployment_sha256 != expected_full_deployment_sha256
    ):
        raise OverlayBindingError("overlay fingerprint preflight did not prove equality")

    expected_build_info_path = (normalized_active / BUILD_INFO_RELATIVE_PATH).resolve()
    if Path(str(binding.get("path") or "")).resolve() != expected_build_info_path:
        raise OverlayBindingError("preflight build-info path does not match the mounted overlay")
    if active_build_info_bytes != container_build_info_bytes:
        raise OverlayBindingError("running container build-info differs from the active overlay")

    build_info = _json_object(active_build_info_bytes, "overlay build-info")
    source_envelope = build_info.get("sourceFingerprint")
    staged_payload_envelope = build_info.get("stagedPayloadFingerprint")
    payload_mode_receipt = build_info.get("payloadModeReceipt")
    recorded_full_deployment_digest = build_info.get("fullDeploymentDigest")
    build_info_sha = (
        source_envelope.get("aggregateSha256")
        if isinstance(source_envelope, dict)
        else None
    )
    try:
        current_source = fingerprint_provider(normalized_source)
        current_staged_payload = staged_fingerprint_provider(normalized_active)
        payload_mode_binding = validate_payload_modes_against_receipt(
            normalized_active,
            payload_mode_receipt,
        )
    except RuntimeError as exc:
        raise OverlayBindingError(
            "running overlay does not match the current source, payload shape, and modes"
        ) from exc
    current_sha = current_source.get("aggregateSha256")
    if (
        not isinstance(source_envelope, dict)
        or not isinstance(staged_payload_envelope, dict)
        or not isinstance(recorded_full_deployment_digest, dict)
        or not isinstance(payload_mode_receipt, dict)
    ):
        raise OverlayBindingError("running overlay full deployment identity is missing")
    recomputed_recorded_digest = full_deployment_digest(
        source_envelope,
        staged_payload_envelope,
    )
    expected_current_digest = full_deployment_digest(
        current_source,
        current_staged_payload,
    )
    if (
        build_info.get("contractName") != EXPECTED_BUILD_INFO_CONTRACT
        or build_info.get("status") != "pass"
        or build_info.get("activationStatus") != "activated"
        or Path(str(build_info.get("sourceRoot") or "")).resolve() != normalized_source
        or build_info_sha != recorded
        or current_sha != recorded
        or staged_payload_envelope != current_staged_payload
        or payload_mode_binding.get("status") != "pass"
        or recorded_full_deployment_digest.get("contractName")
        != FULL_DEPLOYMENT_DIGEST_CONTRACT_NAME
        or recorded_full_deployment_digest.get("algorithm")
        != FULL_DEPLOYMENT_DIGEST_ALGORITHM
        or recorded_full_deployment_digest != recomputed_recorded_digest
        or recorded_full_deployment_digest != expected_current_digest
        or recorded_full_deployment_digest.get("sha256")
        != recorded_full_deployment_sha256
    ):
        raise OverlayBindingError(
            "running overlay is not derived from the current source and active payload"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-receipt", required=True, type=Path)
    parser.add_argument("--container-build-info-receipt", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--active-root", required=True, type=Path)
    parser.add_argument("--not-before-utc", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        active_build_info_path = args.active_root / BUILD_INFO_RELATIVE_PATH
        active_bytes = _read_regular_bytes(active_build_info_path, owner_only=False)
        container_bytes = _read_regular_bytes(
            args.container_build_info_receipt,
            owner_only=True,
        )
        preflight = _json_object(
            _read_regular_bytes(args.preflight_receipt, owner_only=True),
            "post-activation preflight",
        )
        validate_binding(
            preflight=preflight,
            active_build_info_bytes=active_bytes,
            container_build_info_bytes=container_bytes,
            source_root=args.source_root,
            active_root=args.active_root,
            not_before_utc=_utc(args.not_before_utc, "cutover not-before timestamp"),
        )
    except OverlayBindingError as exc:
        print(f"install-linking cutover overlay binding failed: {exc}", file=sys.stderr)
        return 1
    print("install-linking cutover overlay binding passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
