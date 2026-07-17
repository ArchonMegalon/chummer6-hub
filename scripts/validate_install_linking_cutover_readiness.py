#!/usr/bin/env python3
"""Validate the exact deep-readiness contract used by the PostgreSQL cutover."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

try:
    from scripts.strict_json_contract import StrictJsonContractError, strict_json_object
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from strict_json_contract import StrictJsonContractError, strict_json_object


MAX_RECEIPT_BYTES = 1024 * 1024
EXPECTED_CONTRACT = "chummer.run.api.deep_readiness.v2"
EXPECTED_SERVICE = "chummer.run.api"
INSTALL_LINKING_CHECK = "install_linking_store"
EXPECTED_INSTALL_LINKING_CODE = "postgres_authority_bound"
EXPECTED_DEPLOYMENT_CODE = "overlay_identity_bound"
EXPECTED_FULL_DEPLOYMENT_DIGEST_CONTRACT = "chummer.public_edge_full_deployment_digest.v1"
EXPECTED_FULL_DEPLOYMENT_DIGEST_ALGORITHM = "sha256-canonical-json-v1"
MAX_CLOCK_SKEW = timedelta(seconds=30)
DEFAULT_MAX_AGE_SECONDS = 120


class ReadinessValidationError(RuntimeError):
    pass


def _read_bounded_regular_bytes(
    path: Path,
    *,
    label: str,
    owner_only: bool,
) -> bytes:
    normalized = Path(os.path.abspath(os.fspath(path.expanduser())))
    try:
        before_path = normalized.lstat()
    except OSError as exc:
        raise ReadinessValidationError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(before_path.st_mode)
        or stat.S_ISLNK(before_path.st_mode)
        or before_path.st_nlink != 1
    ):
        raise ReadinessValidationError(f"{label} must be a regular unaliased file")
    if owner_only and before_path.st_mode & 0o077:
        raise ReadinessValidationError(f"{label} must be owner-only")
    if before_path.st_size <= 0 or before_path.st_size > MAX_RECEIPT_BYTES:
        raise ReadinessValidationError(f"{label} size is invalid")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(normalized, flags)
    except OSError as exc:
        raise ReadinessValidationError(f"{label} cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (before.st_dev, before.st_ino)
            != (before_path.st_dev, before_path.st_ino)
        ):
            raise ReadinessValidationError(f"{label} changed before read")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_RECEIPT_BYTES:
                raise ReadinessValidationError(f"{label} size is invalid")
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
        raise ReadinessValidationError(f"{label} changed while being read")
    try:
        path_after = normalized.lstat()
    except OSError as exc:
        raise ReadinessValidationError(f"{label} pathname changed after read") from exc
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
        raise ReadinessValidationError(f"{label} pathname changed after read")
    return b"".join(chunks)


def _read_owner_only_receipt(path: Path) -> dict[str, Any]:
    raw = _read_bounded_regular_bytes(
        path,
        label="readiness receipt",
        owner_only=True,
    )

    try:
        return strict_json_object(raw, label="readiness receipt")
    except StrictJsonContractError as exc:
        raise ReadinessValidationError("readiness receipt is not valid UTF-8 JSON") from exc


def _parse_utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ReadinessValidationError(f"{label} is missing")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReadinessValidationError(f"{label} is invalid") from exc
    if parsed.tzinfo is None:
        raise ReadinessValidationError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)


def _expected_deployment_identity(build_info_path: Path) -> tuple[str, str]:
    try:
        payload = strict_json_object(
            _read_bounded_regular_bytes(
                build_info_path,
                label="overlay build-info",
                owner_only=False,
            ),
            label="overlay build-info",
        )
    except StrictJsonContractError as exc:
        raise ReadinessValidationError("overlay build-info is not valid JSON") from exc
    fingerprint = payload.get("sourceFingerprint") if isinstance(payload, dict) else None
    aggregate = fingerprint.get("aggregateSha256") if isinstance(fingerprint, dict) else None
    if (
        not isinstance(aggregate, str)
        or len(aggregate) != 64
        or any(character not in "0123456789abcdef" for character in aggregate)
    ):
        raise ReadinessValidationError("overlay build-info source fingerprint is invalid")
    full_deployment_digest = (
        payload.get("fullDeploymentDigest") if isinstance(payload, dict) else None
    )
    full_deployment_sha256 = (
        full_deployment_digest.get("sha256")
        if isinstance(full_deployment_digest, dict)
        else None
    )
    if (
        not isinstance(full_deployment_digest, dict)
        or full_deployment_digest.get("contractName")
        != EXPECTED_FULL_DEPLOYMENT_DIGEST_CONTRACT
        or full_deployment_digest.get("algorithm")
        != EXPECTED_FULL_DEPLOYMENT_DIGEST_ALGORITHM
        or not isinstance(full_deployment_sha256, str)
        or len(full_deployment_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in full_deployment_sha256
        )
    ):
        raise ReadinessValidationError("overlay build-info full deployment digest is invalid")
    return aggregate, full_deployment_sha256


def validate_readiness(
    payload: dict[str, Any],
    *,
    expected_source_fingerprint_sha256: str,
    expected_full_deployment_digest_sha256: str,
    not_before_utc: datetime,
    now_utc: datetime | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> None:
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    not_before = not_before_utc.astimezone(UTC)
    generated_at = _parse_utc_timestamp(payload.get("generatedAt"), "readiness generatedAt")
    if generated_at < not_before:
        raise ReadinessValidationError("readiness predates this cutover")
    if generated_at > now + MAX_CLOCK_SKEW:
        raise ReadinessValidationError("readiness timestamp is in the future")
    if now - generated_at > timedelta(seconds=max_age_seconds):
        raise ReadinessValidationError("readiness receipt is stale")

    if payload.get("ready") is not True or payload.get("status") != "ready":
        raise ReadinessValidationError("combined readiness is not ready")

    hub = payload.get("hub")
    if not isinstance(hub, dict):
        raise ReadinessValidationError("deep-readiness report is missing")
    if (
        hub.get("contractName") != EXPECTED_CONTRACT
        or hub.get("service") != EXPECTED_SERVICE
        or hub.get("ready") is not True
        or hub.get("status") != "pass"
    ):
        raise ReadinessValidationError("deep-readiness contract is not current and passing")

    checks = hub.get("checks")
    if not isinstance(checks, list):
        raise ReadinessValidationError("deep-readiness checks are missing")
    install_linking_checks = [
        check
        for check in checks
        if isinstance(check, dict) and check.get("name") == INSTALL_LINKING_CHECK
    ]
    if len(install_linking_checks) != 1:
        raise ReadinessValidationError("install-linking readiness check is not unique")
    install_linking = install_linking_checks[0]
    if (
        install_linking.get("passed") is not True
        or install_linking.get("status") != "pass"
        or install_linking.get("code") != EXPECTED_INSTALL_LINKING_CODE
    ):
        raise ReadinessValidationError("install-linking authority is not ready")

    play_projection = payload.get("playProjection")
    if not isinstance(play_projection, dict) or play_projection.get("ready") is not True:
        raise ReadinessValidationError("Play projection is not ready")

    deployment_identity = payload.get("deploymentIdentity")
    if (
        not isinstance(deployment_identity, dict)
        or deployment_identity.get("ready") is not True
        or deployment_identity.get("code") != EXPECTED_DEPLOYMENT_CODE
        or deployment_identity.get("sourceFingerprintSha256")
        != expected_source_fingerprint_sha256
        or deployment_identity.get("fullDeploymentDigestSha256")
        != expected_full_deployment_digest_sha256
    ):
        raise ReadinessValidationError("readiness deployment identity does not match the activated overlay")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an owner-only Chummer deep-readiness receipt."
    )
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--expected-build-info", required=True, type=Path)
    parser.add_argument("--not-before-utc", required=True)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=DEFAULT_MAX_AGE_SECONDS,
        choices=range(1, 301),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        payload = _read_owner_only_receipt(args.receipt)
        (
            expected_source_fingerprint_sha256,
            expected_full_deployment_digest_sha256,
        ) = _expected_deployment_identity(args.expected_build_info)
        validate_readiness(
            payload,
            expected_source_fingerprint_sha256=expected_source_fingerprint_sha256,
            expected_full_deployment_digest_sha256=expected_full_deployment_digest_sha256,
            not_before_utc=_parse_utc_timestamp(
                args.not_before_utc,
                "cutover not-before timestamp",
            ),
            max_age_seconds=args.max_age_seconds,
        )
    except ReadinessValidationError as exc:
        print(f"install-linking cutover readiness failed: {exc}", file=sys.stderr)
        return 1
    print("install-linking cutover readiness passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
