#!/usr/bin/env python3
"""Prepare owner-only storage for the staged release publication service."""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path


WRITER_POLICY_NAME = ".release-shelf-writer-policy.json"
WRITER_POLICY = {
    "schemaVersion": "chummer.release-shelf.writer-policy/v1",
    "mode": "server-journal-v1",
}


class StoragePreparationError(RuntimeError):
    pass


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def require_plain_directory(path: Path, label: str) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise StoragePreparationError(f"{label} must be a non-symlink directory: {path}")


def secure_session_tree(root: Path, uid: int, gid: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    require_plain_directory(root, "release upload session root")

    for current_root, directory_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_root)
        for name in [*directory_names, *file_names]:
            candidate = current / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise StoragePreparationError(
                    f"release upload session storage contains a symlink: {candidate}"
                )
            if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
                raise StoragePreparationError(
                    "release upload session storage contains an unsupported entry: "
                    f"{candidate}"
                )

    for current_root, directory_names, file_names in os.walk(
        root,
        topdown=False,
        followlinks=False,
    ):
        current = Path(current_root)
        for name in file_names:
            candidate = current / name
            os.chown(candidate, uid, gid, follow_symlinks=False)
            os.chmod(candidate, 0o600, follow_symlinks=False)
        for name in directory_names:
            candidate = current / name
            os.chown(candidate, uid, gid, follow_symlinks=False)
            os.chmod(candidate, 0o700, follow_symlinks=False)

    os.chown(root, uid, gid, follow_symlinks=False)
    os.chmod(root, 0o700, follow_symlinks=False)
    fsync_directory(root)


def validate_existing_writer_policy(path: Path, uid: int, gid: int) -> None:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != uid
        or metadata.st_gid != gid
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise StoragePreparationError(
            "release shelf writer policy must be an owner-only regular file owned "
            f"by {uid}:{gid}: {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoragePreparationError(
            f"release shelf writer policy is unreadable or malformed: {path}"
        ) from exc
    if payload != WRITER_POLICY:
        raise StoragePreparationError(
            f"release shelf writer policy is unsupported or noncanonical: {path}"
        )


def ensure_writer_policy(downloads_root: Path, uid: int, gid: int) -> Path:
    require_plain_directory(downloads_root, "release downloads root")
    policy_path = downloads_root / WRITER_POLICY_NAME
    if policy_path.exists() or policy_path.is_symlink():
        validate_existing_writer_policy(policy_path, uid, gid)
        return policy_path

    payload = (
        json.dumps(WRITER_POLICY, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{WRITER_POLICY_NAME}.",
        dir=downloads_root,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, uid, gid)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, policy_path)
        fsync_directory(downloads_root)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass

    validate_existing_writer_policy(policy_path, uid, gid)
    return policy_path


def positive_runtime_id(raw: str, label: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise StoragePreparationError(f"{label} must be a positive integer") from exc
    if value <= 0:
        raise StoragePreparationError(f"{label} must be a positive integer")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions-root", type=Path, required=True)
    parser.add_argument("--downloads-root", type=Path, required=True)
    parser.add_argument("--uid", required=True)
    parser.add_argument("--gid", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    uid = positive_runtime_id(args.uid, "runtime uid")
    gid = positive_runtime_id(args.gid, "runtime gid")
    sessions_root = args.sessions_root.resolve(strict=False)
    downloads_root = args.downloads_root.resolve(strict=True)
    secure_session_tree(sessions_root, uid, gid)
    ensure_writer_policy(downloads_root, uid, gid)
    print(
        "release publication storage ready: "
        f"sessions={sessions_root} writerPolicy={downloads_root / WRITER_POLICY_NAME}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
