#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Optional, Sequence


SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_SCORECARD_BYTES = 8 * 1024 * 1024
MAX_CONVERGENCE_BYTES = 4 * 1024 * 1024


class HandoffError(ValueError):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy one caller-owned, digest-pinned campaign-operability scorecard "
            "into release evidence after exact review-candidate convergence."
        )
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--convergence", type=Path, required=True)
    parser.add_argument("--expected-release-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args(argv)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise HandoffError(f"{label} contains duplicate JSON field {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise HandoffError(f"{label} must be a JSON object")
    return value


def _timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HandoffError(f"{label} must be a canonical UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as error:
        raise HandoffError(f"{label} must be a canonical UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise HandoffError(f"{label} must be a canonical UTC timestamp")
    return parsed.astimezone(dt.timezone.utc)


def _stable_owned_file(path: Path, allowed_root: Path, maximum_bytes: int) -> bytes:
    try:
        root = allowed_root.resolve(strict=True)
        root_metadata = root.stat()
    except OSError as error:
        raise HandoffError("allowed scorecard root is unavailable") from error
    if not stat.S_ISDIR(root_metadata.st_mode) or root_metadata.st_uid != os.getuid():
        raise HandoffError("allowed scorecard root must be a caller-owned directory")
    if root_metadata.st_mode & 0o022:
        raise HandoffError("allowed scorecard root must not be group- or world-writable")

    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise HandoffError("scorecard source must stay beneath the caller-owned run workspace") from error
    try:
        path_metadata = os.lstat(path)
    except OSError as error:
        raise HandoffError("scorecard source is unavailable") from error
    if stat.S_ISLNK(path_metadata.st_mode):
        raise HandoffError("scorecard source must not be a symbolic link")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise HandoffError("scorecard source could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise HandoffError("scorecard source must be a single-link regular file")
        if before.st_uid != os.getuid():
            raise HandoffError("scorecard source must be owned by the current caller")
        if before.st_mode & 0o022:
            raise HandoffError("scorecard source must not be group- or world-writable")
        if before.st_size < 1 or before.st_size > maximum_bytes:
            raise HandoffError("scorecard source has an invalid byte length")
        remaining = before.st_size + 1
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
        item.st_nlink,
    )
    raw = b"".join(chunks)
    if identity(before) != identity(after) or len(raw) != before.st_size:
        raise HandoffError("scorecard source changed during stable read")
    try:
        final_path_metadata = os.lstat(path)
    except OSError as error:
        raise HandoffError("scorecard source changed during stable read") from error
    if (final_path_metadata.st_dev, final_path_metadata.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        raise HandoffError("scorecard source changed during stable read")
    return raw


def _bounded_json_file(path: Path, label: str, maximum_bytes: int) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise HandoffError(f"{label} could not be read") from error
    if not raw or len(raw) > maximum_bytes:
        raise HandoffError(f"{label} has an invalid byte length")
    return raw, _strict_json(raw, label)


def _validate_convergence(payload: dict[str, Any], release_version: str) -> dt.datetime:
    if (
        payload.get("contractName") != "chummer.live-release-convergence/v1"
        or payload.get("contractVersion") != 1
        or payload.get("status") != "pass"
        or payload.get("mismatchCount") != 0
        or payload.get("failureCount") != 0
        or payload.get("mismatches") != []
        or payload.get("failures") != []
        or payload.get("releaseDecisionStatus") != "review_required"
    ):
        raise HandoffError("convergence receipt is not an exact zero-failure review candidate")
    truth = payload.get("releaseTruth")
    if (
        not isinstance(truth, dict)
        or truth.get("releaseVersion") != release_version
        or truth.get("releaseDecisionStatus") != "review_required"
        or truth.get("releaseDecisionSha256") != payload.get("releaseDecisionSha256")
    ):
        raise HandoffError("convergence receipt does not bind the expected review candidate")
    return _timestamp(payload.get("generatedAtUtc"), "convergence generatedAtUtc")


def _validate_scorecard(payload: dict[str, Any], convergence_at: dt.datetime) -> dt.datetime:
    summary = payload.get("summary")
    cells = payload.get("cells")
    if (
        payload.get("contract_name") != "chummer.campaign_operability_scorecard"
        or payload.get("contract_version") != 2
        or payload.get("preview_status") != "pass"
        or payload.get("preview_verdict") != "CAMPAIGN_OPERABILITY_PREVIEW_READY"
        or payload.get("preview_failures") != []
        or not isinstance(summary, dict)
        or summary.get("cell_count") != 36
        or summary.get("at_least_2_count") != 36
        or summary.get("below_2_count") != 0
        or summary.get("minimum_score") not in {2, 3}
        or not isinstance(cells, list)
        or len(cells) != 36
    ):
        raise HandoffError("scorecard is not a generated v2 36-cell preview-ready artifact")
    generated_at = _timestamp(payload.get("generated_at_utc"), "scorecard generated_at_utc")
    if generated_at < convergence_at:
        raise HandoffError("scorecard must be materialized after review-candidate convergence")
    now = dt.datetime.now(dt.timezone.utc)
    if generated_at > now + dt.timedelta(minutes=5):
        raise HandoffError("scorecard generated_at_utc is unreasonably in the future")
    return generated_at


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise HandoffError(f"output already exists: {path.name}") from error


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        expected = args.expected_sha256.strip()
        if SHA256.fullmatch(expected) is None:
            raise HandoffError("expected scorecard SHA-256 must be 64 lowercase hexadecimal characters")
        release_version = args.expected_release_version.strip()
        if not release_version or len(release_version) > 128:
            raise HandoffError("expected release version is invalid")

        convergence_raw, convergence = _bounded_json_file(
            args.convergence, "convergence receipt", MAX_CONVERGENCE_BYTES
        )
        convergence_at = _validate_convergence(convergence, release_version)
        scorecard_raw = _stable_owned_file(
            args.source, args.allowed_root, MAX_SCORECARD_BYTES
        )
        observed = hashlib.sha256(scorecard_raw).hexdigest()
        if not hmac.compare_digest(observed, expected):
            raise HandoffError("scorecard SHA-256 does not match the immutable handoff")
        scorecard = _strict_json(scorecard_raw, "scorecard")
        scorecard_at = _validate_scorecard(scorecard, convergence_at)

        receipt = {
            "contractName": "chummer.release-scorecard-handoff/v1",
            "status": "pass",
            "releaseVersion": release_version,
            "scorecardSha256": observed,
            "convergenceSha256": hashlib.sha256(convergence_raw).hexdigest(),
            "scorecardGeneratedAtUtc": scorecard_at.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
            "convergenceGeneratedAtUtc": convergence_at.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
        }
        receipt_raw = (
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        _write_new(args.output, scorecard_raw)
        _write_new(args.receipt, receipt_raw)
    except (HandoffError, OSError) as error:
        print(f"release scorecard handoff failed: {error}", file=sys.stderr)
        return 1
    print("release_scorecard_handoff:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
