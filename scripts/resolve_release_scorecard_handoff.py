#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Optional, Sequence


SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_HANDOFF_BYTES = 64 * 1024
MAX_CONVERGENCE_BYTES = 4 * 1024 * 1024
HANDOFF_FIELDS = {
    "contractName",
    "releaseVersion",
    "convergenceSha256",
    "scorecardPath",
    "scorecardSha256",
}


class ResolutionError(ValueError):
    pass


class HandoffNotReady(Exception):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Wait for and resolve one caller-owned immutable campaign-operability "
            "scorecard handoff created after live review-seed convergence."
        )
    )
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--convergence", type=Path, required=True)
    parser.add_argument("--expected-release-version", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ResolutionError(f"{label} contains duplicate JSON field {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResolutionError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ResolutionError(f"{label} must be a JSON object")
    return value


def _caller_owned_root(path: Path) -> Path:
    try:
        root = path.resolve(strict=True)
        metadata = root.stat()
    except OSError as error:
        raise ResolutionError("allowed handoff root is unavailable") from error
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise ResolutionError("allowed handoff root must be a caller-owned directory")
    if metadata.st_mode & 0o022:
        raise ResolutionError("allowed handoff root must not be group- or world-writable")
    return root


def _confined_path(path: Path, root: Path, label: str, *, must_exist: bool) -> Path:
    if not path.is_absolute():
        raise ResolutionError(f"{label} must be an absolute path")
    try:
        resolved = path.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ResolutionError(f"{label} must stay beneath the caller-owned run workspace") from error
    return resolved


def _stable_handoff(path: Path, root: Path) -> bytes:
    _confined_path(path, root, "scorecard handoff", must_exist=False)
    try:
        path_metadata = os.lstat(path)
    except FileNotFoundError as error:
        raise HandoffNotReady from error
    except OSError as error:
        raise ResolutionError("scorecard handoff could not be inspected") from error
    if stat.S_ISLNK(path_metadata.st_mode):
        raise ResolutionError("scorecard handoff must not be a symbolic link")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as error:
        raise HandoffNotReady from error
    except OSError as error:
        raise ResolutionError("scorecard handoff could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ResolutionError("scorecard handoff must be a single-link regular file")
        if before.st_uid != os.getuid():
            raise ResolutionError("scorecard handoff must be owned by the current caller")
        if stat.S_IMODE(before.st_mode) != 0o600:
            raise ResolutionError("scorecard handoff must have mode 0600")
        if before.st_size < 1 or before.st_size > MAX_HANDOFF_BYTES:
            raise ResolutionError("scorecard handoff has an invalid byte length")
        remaining = before.st_size + 1
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    raw = b"".join(chunks)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
        item.st_nlink,
    )
    if identity(before) != identity(after) or len(raw) != before.st_size:
        raise ResolutionError("scorecard handoff changed during stable read")
    try:
        final_path_metadata = os.lstat(path)
    except OSError as error:
        raise ResolutionError("scorecard handoff changed during stable read") from error
    if (final_path_metadata.st_dev, final_path_metadata.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        raise ResolutionError("scorecard handoff changed during stable read")
    _confined_path(path, root, "scorecard handoff", must_exist=True)
    return raw


def _convergence_digest(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ResolutionError("review-seed convergence receipt could not be read") from error
    if not raw or len(raw) > MAX_CONVERGENCE_BYTES:
        raise ResolutionError("review-seed convergence receipt has an invalid byte length")
    payload = _strict_json(raw, "review-seed convergence receipt")
    if (
        payload.get("contractName") != "chummer.live-release-convergence/v1"
        or payload.get("contractVersion") != 1
        or payload.get("status") != "pass"
        or payload.get("mismatchCount") != 0
        or payload.get("failureCount") != 0
        or payload.get("releaseDecisionStatus") != "review_required"
    ):
        raise ResolutionError("review-seed convergence receipt is not an exact passing review candidate")
    return hashlib.sha256(raw).hexdigest()


def _resolve_payload(
    raw: bytes,
    root: Path,
    release_version: str,
    convergence_sha256: str,
) -> dict[str, Any]:
    payload = _strict_json(raw, "scorecard handoff")
    if set(payload) != HANDOFF_FIELDS:
        raise ResolutionError("scorecard handoff has an unexpected field set")
    if (
        payload.get("contractName") != "chummer.release-scorecard-handoff-request/v1"
        or payload.get("releaseVersion") != release_version
        or payload.get("convergenceSha256") != convergence_sha256
    ):
        raise ResolutionError("scorecard handoff does not bind the exact review-seed convergence")
    scorecard_sha256 = payload.get("scorecardSha256")
    scorecard_path_raw = payload.get("scorecardPath")
    if not isinstance(scorecard_sha256, str) or SHA256.fullmatch(scorecard_sha256) is None:
        raise ResolutionError("scorecard handoff scorecardSha256 must be canonical SHA-256")
    if not isinstance(scorecard_path_raw, str) or not scorecard_path_raw:
        raise ResolutionError("scorecard handoff scorecardPath must be an absolute path")
    scorecard_path = _confined_path(
        Path(scorecard_path_raw), root, "scorecard path", must_exist=True
    )
    return {
        "contractName": "chummer.release-scorecard-handoff-resolution/v1",
        "status": "pass",
        "releaseVersion": release_version,
        "convergenceSha256": convergence_sha256,
        "scorecardPath": str(scorecard_path),
        "scorecardSha256": scorecard_sha256,
        "handoffSha256": hashlib.sha256(raw).hexdigest(),
    }


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(
                (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            )
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ResolutionError("scorecard handoff resolution output already exists") from error


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        if not 0 <= args.timeout_seconds <= 3600:
            raise ResolutionError("handoff timeout must be between 0 and 3600 seconds")
        if not 1 <= args.poll_seconds <= 30:
            raise ResolutionError("handoff poll interval must be between 1 and 30 seconds")
        release_version = args.expected_release_version.strip()
        if not release_version or len(release_version) > 128:
            raise ResolutionError("expected release version is invalid")
        root = _caller_owned_root(args.allowed_root)
        _confined_path(args.handoff, root, "scorecard handoff", must_exist=False)
        convergence_sha256 = _convergence_digest(args.convergence)
        deadline = time.monotonic() + args.timeout_seconds
        while True:
            try:
                raw = _stable_handoff(args.handoff, root)
                resolution = _resolve_payload(
                    raw, root, release_version, convergence_sha256
                )
                break
            except HandoffNotReady:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ResolutionError(
                        "timed out waiting for the caller-owned scorecard handoff"
                    )
                wait_seconds = min(float(args.poll_seconds), remaining)
                print(
                    "waiting for caller-owned scorecard handoff "
                    f"at {args.handoff} ({max(1, int(remaining))}s remaining)",
                    file=sys.stderr,
                )
                time.sleep(wait_seconds)
        _write_new(args.output, resolution)
    except (ResolutionError, OSError) as error:
        print(f"release scorecard handoff resolution failed: {error}", file=sys.stderr)
        return 1
    print("release_scorecard_handoff_resolution:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
