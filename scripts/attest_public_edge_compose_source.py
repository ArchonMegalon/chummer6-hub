#!/usr/bin/env python3
"""Capture immutable Compose source and digest-only environment bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any


CONTRACT = "chummer.public-edge.compose-source-binding/v1"
ENVIRONMENT_CONTRACT = "chummer.public-edge.compose-environment-binding/v1"
MAX_COMPOSE_BYTES = 8 * 1024 * 1024
MAX_ENVIRONMENT_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024


class ComposeSourceError(RuntimeError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ComposeSourceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def normalized_absolute_path(value: str | Path, label: str) -> Path:
    text = os.fspath(value)
    if not os.path.isabs(text) or os.path.normpath(text) != text:
        raise ComposeSourceError(f"{label} must be an absolute normalized path")
    return Path(text)


def file_identity(metadata: os.stat_result) -> dict[str, int]:
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "sizeBytes": metadata.st_size,
        "mtimeNs": metadata.st_mtime_ns,
        "ctimeNs": metadata.st_ctime_ns,
        "mode": stat.S_IMODE(metadata.st_mode),
        "uid": metadata.st_uid,
        "linkCount": metadata.st_nlink,
    }


def identity_tuple(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
    )


def read_stable_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    expected_mode: int | None = None,
    reject_group_world_write: bool = False,
) -> tuple[bytes, os.stat_result]:
    linked = os.stat(path, follow_symlinks=False)
    if (
        not stat.S_ISREG(linked.st_mode)
        or stat.S_ISLNK(linked.st_mode)
        or linked.st_nlink != 1
        or linked.st_uid != os.getuid()
        or linked.st_size <= 0
        or linked.st_size > maximum_bytes
        or (
            expected_mode is not None
            and stat.S_IMODE(linked.st_mode) != expected_mode
        )
        or (
            reject_group_world_write
            and stat.S_IMODE(linked.st_mode) & 0o022
        )
    ):
        raise ComposeSourceError(f"{label} is not a safe owner-controlled file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if identity_tuple(before) != identity_tuple(linked):
            raise ComposeSourceError(f"{label} changed while opened")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise ComposeSourceError(f"{label} exceeds its size bound")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    rebound = os.stat(path, follow_symlinks=False)
    if (
        identity_tuple(before) != identity_tuple(after)
        or identity_tuple(after) != identity_tuple(rebound)
        or total != after.st_size
    ):
        raise ComposeSourceError(f"{label} changed while read")
    return b"".join(chunks), after


def ensure_private_parent(path: Path, label: str) -> int:
    parent = path.parent
    metadata = os.stat(parent, follow_symlinks=False)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise ComposeSourceError(f"{label} parent is not owner-only")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(parent, flags)
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
        os.close(descriptor)
        raise ComposeSourceError(f"{label} parent changed while opened")
    return descriptor


def write_new_file(path: Path, raw: bytes, *, mode: int, label: str) -> None:
    parent_fd = ensure_private_parent(path, label)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path.name, flags, mode, dir_fd=parent_fd)
        try:
            os.fchmod(descriptor, mode)
            offset = 0
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    raise ComposeSourceError(f"short write while publishing {label}")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def render_receipt(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def capture(source: Path, snapshot: Path, receipt: Path) -> dict[str, Any]:
    source_raw, source_metadata = read_stable_file(
        source,
        label="public edge Compose source",
        maximum_bytes=MAX_COMPOSE_BYTES,
        reject_group_world_write=True,
    )
    write_new_file(
        snapshot,
        source_raw,
        mode=0o400,
        label="public edge Compose snapshot",
    )
    snapshot_raw, snapshot_metadata = read_stable_file(
        snapshot,
        label="public edge Compose snapshot",
        maximum_bytes=MAX_COMPOSE_BYTES,
        expected_mode=0o400,
    )
    recaptured_raw, recaptured_metadata = read_stable_file(
        source,
        label="public edge Compose source",
        maximum_bytes=MAX_COMPOSE_BYTES,
        reject_group_world_write=True,
    )
    if (
        source_raw != snapshot_raw
        or source_raw != recaptured_raw
        or identity_tuple(source_metadata) != identity_tuple(recaptured_metadata)
        or (source_metadata.st_dev, source_metadata.st_ino)
        == (snapshot_metadata.st_dev, snapshot_metadata.st_ino)
    ):
        raise ComposeSourceError(
            "public edge Compose source changed during immutable capture"
        )
    payload = {
        "contractName": CONTRACT,
        "status": "pass",
        "sourcePath": str(source),
        "snapshotPath": str(snapshot),
        "sha256": hashlib.sha256(source_raw).hexdigest(),
        "sourceIdentity": file_identity(source_metadata),
        "snapshotIdentity": file_identity(snapshot_metadata),
    }
    write_new_file(
        receipt,
        render_receipt(payload),
        mode=0o600,
        label="public edge Compose source receipt",
    )
    return payload


def load_receipt(path: Path) -> dict[str, Any]:
    raw, _ = read_stable_file(
        path,
        label="public edge Compose source receipt",
        maximum_bytes=MAX_RECEIPT_BYTES,
        expected_mode=0o600,
    )
    try:
        payload = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComposeSourceError("public edge Compose source receipt is malformed") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "contractName",
        "status",
        "sourcePath",
        "snapshotPath",
        "sha256",
        "sourceIdentity",
        "snapshotIdentity",
    }:
        raise ComposeSourceError("public edge Compose source receipt fields are invalid")
    if payload.get("contractName") != CONTRACT or payload.get("status") != "pass":
        raise ComposeSourceError("public edge Compose source receipt is not pass")
    return payload


def verify(source: Path, snapshot: Path, receipt: Path) -> dict[str, Any]:
    payload = load_receipt(receipt)
    if payload.get("sourcePath") != str(source) or payload.get("snapshotPath") != str(
        snapshot
    ):
        raise ComposeSourceError("public edge Compose binding paths changed")
    source_raw, source_metadata = read_stable_file(
        source,
        label="public edge Compose source",
        maximum_bytes=MAX_COMPOSE_BYTES,
        reject_group_world_write=True,
    )
    snapshot_raw, snapshot_metadata = read_stable_file(
        snapshot,
        label="public edge Compose snapshot",
        maximum_bytes=MAX_COMPOSE_BYTES,
        expected_mode=0o400,
    )
    digest = hashlib.sha256(source_raw).hexdigest()
    if (
        source_raw != snapshot_raw
        or digest != payload.get("sha256")
        or file_identity(source_metadata) != payload.get("sourceIdentity")
        or file_identity(snapshot_metadata) != payload.get("snapshotIdentity")
        or (source_metadata.st_dev, source_metadata.st_ino)
        == (snapshot_metadata.st_dev, snapshot_metadata.st_ino)
    ):
        raise ComposeSourceError("public edge Compose source binding changed")
    return {"contractName": CONTRACT, "status": "pass", "sha256": digest}


def capture_environment(source: Path, receipt: Path) -> dict[str, Any]:
    """Bind an owner-only Compose environment file without copying its contents."""
    source_raw, source_metadata = read_stable_file(
        source,
        label="public edge Compose environment",
        maximum_bytes=MAX_ENVIRONMENT_BYTES,
        expected_mode=0o600,
    )
    payload = {
        "contractName": ENVIRONMENT_CONTRACT,
        "status": "pass",
        "sourcePath": str(source),
        "sha256": hashlib.sha256(source_raw).hexdigest(),
        "sourceIdentity": file_identity(source_metadata),
        "sourceContentPersisted": False,
    }
    write_new_file(
        receipt,
        render_receipt(payload),
        mode=0o600,
        label="public edge Compose environment receipt",
    )
    return payload


def load_environment_receipt(path: Path) -> dict[str, Any]:
    raw, _ = read_stable_file(
        path,
        label="public edge Compose environment receipt",
        maximum_bytes=MAX_RECEIPT_BYTES,
        expected_mode=0o600,
    )
    try:
        payload = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComposeSourceError(
            "public edge Compose environment receipt is malformed"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {
        "contractName",
        "status",
        "sourcePath",
        "sha256",
        "sourceIdentity",
        "sourceContentPersisted",
    }:
        raise ComposeSourceError(
            "public edge Compose environment receipt fields are invalid"
        )
    if (
        payload.get("contractName") != ENVIRONMENT_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("sourceContentPersisted") is not False
    ):
        raise ComposeSourceError(
            "public edge Compose environment receipt is not pass"
        )
    return payload


def verify_environment(source: Path, receipt: Path) -> dict[str, Any]:
    payload = load_environment_receipt(receipt)
    if payload.get("sourcePath") != str(source):
        raise ComposeSourceError("public edge Compose environment path changed")
    source_raw, source_metadata = read_stable_file(
        source,
        label="public edge Compose environment",
        maximum_bytes=MAX_ENVIRONMENT_BYTES,
        expected_mode=0o600,
    )
    digest = hashlib.sha256(source_raw).hexdigest()
    if (
        digest != payload.get("sha256")
        or file_identity(source_metadata) != payload.get("sourceIdentity")
    ):
        raise ComposeSourceError("public edge Compose environment binding changed")
    return {
        "contractName": ENVIRONMENT_CONTRACT,
        "status": "pass",
        "sha256": digest,
        "sourceContentPersisted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "verify"):
        child = commands.add_parser(command)
        child.add_argument("--source", required=True)
        child.add_argument("--snapshot", required=True)
        child.add_argument("--receipt", required=True)
    for command in ("capture-environment", "verify-environment"):
        child = commands.add_parser(command)
        child.add_argument("--source", required=True)
        child.add_argument("--receipt", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = normalized_absolute_path(args.source, "Compose source")
        receipt = normalized_absolute_path(args.receipt, "Compose receipt")
        if args.command in {"capture", "verify"}:
            snapshot = normalized_absolute_path(args.snapshot, "Compose snapshot")
            result = (
                capture(source, snapshot, receipt)
                if args.command == "capture"
                else verify(source, snapshot, receipt)
            )
        else:
            result = (
                capture_environment(source, receipt)
                if args.command == "capture-environment"
                else verify_environment(source, receipt)
            )
    except (ComposeSourceError, OSError, ValueError, TypeError) as exc:
        print(f"public_edge_compose_source_attestation: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
