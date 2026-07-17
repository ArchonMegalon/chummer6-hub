#!/usr/bin/env python3
"""Materialize durable, non-secret release-upload recovery handoffs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = "chummer.release-upload-handoff/v1"
MAX_RECEIPT_BYTES = 64 * 1024
VALID_STATES = {
    "created",
    "uploaded",
    "request_started",
    "outcome_unknown",
    "completed",
    "durably_aborted",
}
ALLOWED_TRANSITIONS = {
    "created": {"uploaded", "durably_aborted"},
    "uploaded": {"request_started", "durably_aborted"},
    "request_started": {"outcome_unknown", "completed", "durably_aborted"},
    "outcome_unknown": {"outcome_unknown", "completed", "durably_aborted"},
    "completed": set(),
    "durably_aborted": set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def require_plain_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symbolic link")
    resolved = path.resolve(strict=True)
    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError(f"{label} must be a regular file")
    return resolved


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    parent = path.parent.resolve(strict=True)
    if path.exists() and path.is_symlink():
        raise ValueError("receipt target must not be a symbolic link")
    rendered = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        fsync_directory(parent)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def read_json_object(path: Path, *, max_bytes: int = MAX_RECEIPT_BYTES) -> dict[str, Any]:
    resolved = require_plain_file(path, label="receipt")
    metadata = resolved.stat()
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("receipt must be owned by the current user with mode 0600")
    size = metadata.st_size
    if size > max_bytes:
        raise ValueError(f"receipt exceeds {max_bytes} bytes")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("receipt must contain a JSON object")
    return payload


def normalized_api_origin(sessions_url: str) -> str:
    parsed = urlsplit(sessions_url.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("upload sessions URL has an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.rstrip("/").endswith("/upload-sessions")
    ):
        raise ValueError("upload sessions URL is not a canonical HTTP(S) sessions endpoint")
    default_port = 443 if parsed.scheme == "https" else 80
    authority = parsed.hostname.lower() if port in {None, default_port} else f"{parsed.hostname.lower()}:{port}"
    return f"{parsed.scheme.lower()}://{authority}"


def validate_session_id(value: str) -> str:
    candidate = value.strip()
    if re.fullmatch(r"[0-9a-f]{32}", candidate) is None:
        raise ValueError("sessionId must be the canonical lowercase 32-hex server identifier")
    return candidate


def validate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    required_fields = {
        "version",
        "canonicalManifestSha256",
        "inventorySha256",
        "fileCount",
        "totalBytes",
        "bundleIdentitySha256",
    }
    if set(candidate) != required_fields:
        raise ValueError("candidate summary has an unexpected property set")
    version = candidate.get("version")
    if not isinstance(version, str) or not (1 <= len(version) <= 160) or any(ord(character) < 0x21 or ord(character) > 0x7E for character in version):
        raise ValueError("candidate version must be a short printable ASCII identifier")
    for field in ("canonicalManifestSha256", "inventorySha256", "bundleIdentitySha256"):
        if not isinstance(candidate.get(field), str) or re.fullmatch(r"[0-9a-f]{64}", candidate[field]) is None:
            raise ValueError(f"candidate {field} must be lowercase SHA-256")
    file_count = candidate.get("fileCount")
    total_bytes = candidate.get("totalBytes")
    if isinstance(file_count, bool) or not isinstance(file_count, int) or not (1 <= file_count <= 100_000):
        raise ValueError("candidate fileCount is invalid")
    if isinstance(total_bytes, bool) or not isinstance(total_bytes, int) or not (0 <= total_bytes < 2**63):
        raise ValueError("candidate totalBytes is invalid")
    identity_fields = {
        field: candidate[field]
        for field in (
            "version",
            "canonicalManifestSha256",
            "inventorySha256",
            "fileCount",
            "totalBytes",
        )
    }
    identity_material = json.dumps(identity_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(identity_material).hexdigest() != candidate["bundleIdentitySha256"]:
        raise ValueError("candidate bundleIdentitySha256 does not bind the candidate summary")
    return candidate


def normalize_expiry(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    if len(candidate) > 64:
        raise ValueError("expiresAtUtc is too long")
    parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("expiresAtUtc must include an offset")
    if parsed.utcoffset().total_seconds() != 0:
        raise ValueError("expiresAtUtc must be expressed in UTC")
    return candidate.replace("+00:00", "Z")


def summarize(args: argparse.Namespace) -> int:
    bundle_root = Path(args.bundle_root).resolve(strict=True)
    if not bundle_root.is_dir():
        raise ValueError("bundle root must be a directory")
    canonical_manifest = require_plain_file(Path(args.canonical_manifest), label="canonical manifest")
    manifest_payload = json.loads(canonical_manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest_payload, dict):
        raise ValueError("canonical manifest must contain a JSON object")
    version = str(manifest_payload.get("version") or "").strip()
    if not version:
        raise ValueError("canonical manifest version is required")

    rows: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for raw_path in args.file:
        lexical = Path(raw_path)
        resolved = require_plain_file(lexical, label="upload inventory file")
        try:
            relative = resolved.relative_to(bundle_root).as_posix()
        except ValueError as exc:
            raise ValueError("every upload inventory file must be inside the bundle root") from exc
        if relative in seen:
            raise ValueError(f"duplicate upload inventory path: {relative}")
        seen.add(relative)
        rows.append((relative, resolved.stat().st_size, sha256_file(resolved)))
    if not rows:
        raise ValueError("upload inventory must contain at least one file")
    rows.sort(key=lambda row: row[0])

    inventory_digest = hashlib.sha256()
    total_bytes = 0
    for relative, size_bytes, digest in rows:
        encoded_path = relative.encode("utf-8")
        inventory_digest.update(len(encoded_path).to_bytes(8, "big"))
        inventory_digest.update(encoded_path)
        inventory_digest.update(size_bytes.to_bytes(8, "big"))
        inventory_digest.update(bytes.fromhex(digest))
        total_bytes += size_bytes

    candidate = {
        "version": version,
        "canonicalManifestSha256": sha256_file(canonical_manifest),
        "inventorySha256": inventory_digest.hexdigest(),
        "fileCount": len(rows),
        "totalBytes": total_bytes,
    }
    identity_material = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8")
    candidate["bundleIdentitySha256"] = hashlib.sha256(identity_material).hexdigest()
    validate_candidate(candidate)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write_json(output, candidate)
    return 0


def preflight(args: argparse.Namespace) -> int:
    receipt = Path(args.receipt)
    if not receipt.exists() and not receipt.is_symlink():
        return 0
    payload = read_json_object(receipt)
    schema = payload.get("schemaVersion")
    completion = payload.get("completion")
    state = completion.get("state") if isinstance(completion, dict) else None
    if schema != SCHEMA_VERSION or state not in VALID_STATES:
        raise ValueError("an unreadable or foreign durable upload receipt already occupies the target path")
    raise ValueError(
        f"durable upload receipt already exists in state {state!r}; reconcile or archive it before creating another session"
    )


def transition(args: argparse.Namespace) -> int:
    state = args.state
    if state not in VALID_STATES:
        raise ValueError(f"unsupported completion state: {state}")
    receipt = Path(args.receipt)
    candidate = validate_candidate(read_json_object(Path(args.summary)))
    session_id = validate_session_id(args.session_id)
    api_origin = normalized_api_origin(args.sessions_url)
    now = utc_now()

    if state == "created":
        if receipt.exists() or receipt.is_symlink():
            raise ValueError("durable upload receipt appeared before session creation could be recorded")
        payload: dict[str, Any] = {
            "schemaVersion": SCHEMA_VERSION,
            "apiOrigin": api_origin,
            "sessionId": session_id,
            "expiresAtUtc": normalize_expiry(args.expires_at),
            "candidate": candidate,
            "completion": {
                "state": state,
                "requestStartedAtUtc": None,
                "lastUpdatedAtUtc": now,
                "lastHttpStatus": None,
                "lastProblemType": None,
                "traceId": None,
            },
            "stateHistory": [{"state": state, "atUtc": now}],
        }
    else:
        payload = read_json_object(receipt)
        if payload.get("schemaVersion") != SCHEMA_VERSION:
            raise ValueError("durable upload receipt schema changed during the attempt")
        if payload.get("sessionId") != session_id or payload.get("apiOrigin") != api_origin:
            raise ValueError("durable upload receipt session binding changed during the attempt")
        if payload.get("candidate") != candidate:
            raise ValueError("durable upload receipt candidate binding changed during the attempt")
        completion = payload.get("completion")
        if not isinstance(completion, dict):
            raise ValueError("durable upload receipt completion object is missing")
        previous_state = completion.get("state")
        if previous_state not in ALLOWED_TRANSITIONS or state not in ALLOWED_TRANSITIONS[previous_state]:
            raise ValueError(f"invalid durable upload receipt transition: {previous_state!r} -> {state!r}")
        completion["state"] = state
        completion["lastUpdatedAtUtc"] = now
        if state == "request_started":
            completion["requestStartedAtUtc"] = now
        if args.http_status:
            completion["lastHttpStatus"] = args.http_status
        if args.problem_type:
            completion["lastProblemType"] = args.problem_type
        if args.trace_id:
            completion["traceId"] = args.trace_id
        history = payload.get("stateHistory")
        if not isinstance(history, list) or len(history) > 32:
            raise ValueError("durable upload receipt state history is invalid")
        history.append({"state": state, "atUtc": now})

    receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write_json(receipt, payload)
    return 0


def fsync_file(args: argparse.Namespace) -> int:
    path = require_plain_file(Path(args.path), label="response file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    fsync_directory(path.parent)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--receipt", required=True)
    preflight_parser.set_defaults(handler=preflight)

    summary_parser = subparsers.add_parser("summarize")
    summary_parser.add_argument("--bundle-root", required=True)
    summary_parser.add_argument("--canonical-manifest", required=True)
    summary_parser.add_argument("--output", required=True)
    summary_parser.add_argument("--file", action="append", default=[], required=True)
    summary_parser.set_defaults(handler=summarize)

    transition_parser = subparsers.add_parser("transition")
    transition_parser.add_argument("--receipt", required=True)
    transition_parser.add_argument("--summary", required=True)
    transition_parser.add_argument("--sessions-url", required=True)
    transition_parser.add_argument("--session-id", required=True)
    transition_parser.add_argument("--expires-at", default="")
    transition_parser.add_argument("--state", required=True)
    transition_parser.add_argument("--http-status", default="")
    transition_parser.add_argument("--problem-type", default="")
    transition_parser.add_argument("--trace-id", default="")
    transition_parser.set_defaults(handler=transition)

    fsync_parser = subparsers.add_parser("fsync-file")
    fsync_parser.add_argument("--path", required=True)
    fsync_parser.set_defaults(handler=fsync_file)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"release_upload_attempt_receipt: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
