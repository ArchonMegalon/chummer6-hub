#!/usr/bin/env python3
"""Snapshot or compare the exact InstallLinking namespace in a volume tar stream."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import tempfile
from typing import Any


CONTRACT_NAME = "chummer.install-linking-state-inventory/v1"
CANONICAL_VOLUME = "chummer6-hub_chummer-run-api-state"
SOURCE_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40}$")
OPERATIONS = {
    "initial-release-shelf-public-download-cutover",
    "initial-release-shelf-public-download-cutover-recover",
}
MAX_TAR_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 100_000


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def is_install_linking_path(path: PurePosixPath) -> bool:
    return any(
        "installlink" in re.sub(r"[^a-z0-9]", "", part.lower())
        for part in path.parts
    )


def normalized_member_path(name: str) -> PurePosixPath:
    candidate = PurePosixPath(name)
    while candidate.parts and candidate.parts[0] in {".", "/"}:
        candidate = PurePosixPath(*candidate.parts[1:])
    if (
        not candidate.parts
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError("volume tar contains an unsafe member path")
    return candidate


def inventory_from_stdin() -> tuple[list[dict[str, Any]], str]:
    raw = sys.stdin.buffer.read(MAX_TAR_BYTES + 1)
    if not raw or len(raw) > MAX_TAR_BYTES:
        raise ValueError("volume tar stream is empty or oversized")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:*")
    except (tarfile.TarError, OSError) as exc:
        raise ValueError("volume tar stream is invalid") from exc
    with archive:
        for index, member in enumerate(archive):
            if index >= MAX_MEMBERS:
                raise ValueError("volume tar stream has too many members")
            path = normalized_member_path(member.name)
            if not is_install_linking_path(path):
                continue
            rendered_path = path.as_posix()
            if rendered_path in seen:
                raise ValueError("InstallLinking volume tar path is duplicated")
            seen.add(rendered_path)
            common = {
                "path": rendered_path,
                "mode": member.mode & 0o7777,
                "uid": member.uid,
                "gid": member.gid,
            }
            if member.isdir():
                rows.append({**common, "type": "directory"})
                continue
            if not member.isfile():
                raise ValueError(
                    "InstallLinking namespace contains a symlink or special file"
                )
            if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                raise ValueError("InstallLinking state file is oversized")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("InstallLinking state file could not be read")
            content = handle.read(MAX_MEMBER_BYTES + 1)
            if len(content) != member.size or len(content) > MAX_MEMBER_BYTES:
                raise ValueError("InstallLinking state file size is unstable")
            rows.append(
                {
                    **common,
                    "type": "file",
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    rows.sort(key=lambda row: str(row["path"]).encode("utf-8"))
    return rows, hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def read_receipt(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("prior InstallLinking inventory receipt is invalid") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or not isinstance(payload, dict)
    ):
        raise ValueError("prior InstallLinking inventory receipt metadata is unsafe")
    return payload


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError("InstallLinking inventory output must be new")
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def validate_authority(operation: str, source_head: str, volume: str) -> None:
    if operation not in OPERATIONS:
        raise ValueError("InstallLinking inventory operation is invalid")
    if SOURCE_HEAD_PATTERN.fullmatch(source_head) is None:
        raise ValueError("InstallLinking inventory source HEAD is invalid")
    if volume != CANONICAL_VOLUME:
        raise ValueError("InstallLinking inventory volume is not canonical")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    compare_parser = subparsers.add_parser("compare")
    for command in (snapshot_parser, compare_parser):
        command.add_argument("--operation", required=True)
        command.add_argument("--source-head", required=True)
        command.add_argument("--volume", required=True)
        command.add_argument("--output", type=Path, required=True)
    compare_parser.add_argument("--before", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_authority(args.operation, args.source_head, args.volume)
        rows, inventory_sha256 = inventory_from_stdin()
        if args.command == "snapshot":
            payload = {
                "contractName": CONTRACT_NAME,
                "status": "pass",
                "phase": "before",
                "operation": args.operation,
                "sourceHead": args.source_head,
                "volume": args.volume,
                "namespaceRule": (
                    "alphanumeric-casefold path component contains installlink"
                ),
                "entryCount": len(rows),
                "inventorySha256": inventory_sha256,
                "entries": rows,
            }
        else:
            before = read_receipt(args.before)
            expected_fields = {
                "contractName",
                "status",
                "phase",
                "operation",
                "sourceHead",
                "volume",
                "namespaceRule",
                "entryCount",
                "inventorySha256",
                "entries",
            }
            if (
                set(before) != expected_fields
                or before.get("contractName") != CONTRACT_NAME
                or before.get("status") != "pass"
                or before.get("phase") != "before"
                or before.get("operation") != args.operation
                or before.get("sourceHead") != args.source_head
                or before.get("volume") != args.volume
                or before.get("entries") != rows
                or before.get("entryCount") != len(rows)
                or before.get("inventorySha256") != inventory_sha256
            ):
                raise ValueError(
                    "InstallLinking state changed across public-download cutover"
                )
            payload = {
                "contractName": CONTRACT_NAME,
                "status": "pass",
                "phase": "after",
                "operation": args.operation,
                "sourceHead": args.source_head,
                "volume": args.volume,
                "unchanged": True,
                "entryCount": len(rows),
                "beforeInventorySha256": inventory_sha256,
                "afterInventorySha256": inventory_sha256,
            }
        atomic_write(args.output, payload)
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(f"install_linking_state_inventory: {exc}", file=sys.stderr)
        return 1
    print("install_linking_state_inventory:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
