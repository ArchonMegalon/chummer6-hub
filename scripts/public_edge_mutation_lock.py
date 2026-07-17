#!/usr/bin/env python3
"""Crash-consistent shared public-edge mutation lock authority."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict, dataclass
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile
from typing import Any


LOCK_ROOT = Path("/docker/chummercomplete/.state")
LOCK_PATH = LOCK_ROOT / "public-edge-mutation.lock"
AUTH_ROOT = LOCK_ROOT / "public-edge-lock-recovery-receipts"
TOKEN_FILE_NAME = "owner-token"
RENAME_NOREPLACE = 1
AT_FDCWD = -100


class PublicEdgeMutationLockUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MutationLease:
    actor: str
    token: str
    token_sha256: str
    lock_path: Path
    lock_device: int
    lock_inode: int
    token_device: int
    token_inode: int
    authorization_path: Path
    authorization_device: int
    authorization_inode: int

    def receipt(self, *, status: str) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("token")
        return {
            "contractName": "chummer.public_edge_mutation_lease.v1",
            "status": status,
            "actor": payload["actor"],
            "tokenSha256": payload["token_sha256"],
            "lockPath": str(payload["lock_path"]),
            "lockDevice": payload["lock_device"],
            "lockInode": payload["lock_inode"],
            "tokenDevice": payload["token_device"],
            "tokenInode": payload["token_inode"],
            "authorizationPath": str(payload["authorization_path"]),
            "authorizationDevice": payload["authorization_device"],
            "authorizationInode": payload["authorization_inode"],
            "automaticStaleRecovery": False,
        }


def _validate_actor(actor: str) -> str:
    normalized = actor.strip()
    if re.fullmatch(r"[a-z][a-z0-9-]{0,31}", normalized) is None:
        raise ValueError("mutation lock actor must be a safe lowercase literal")
    return normalized


def _ensure_private_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise PublicEdgeMutationLockUnavailable("mutation lock directory must be absolute")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if current.exists() or current.is_symlink():
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise PublicEdgeMutationLockUnavailable(
                    "mutation lock directory path must not contain symlinks"
                )
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if stat.S_ISLNK(current.lstat().st_mode):
            raise PublicEdgeMutationLockUnavailable(
                "mutation lock directory path must not contain symlinks"
            )
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise PublicEdgeMutationLockUnavailable(
            "mutation lock directory must be caller-owned mode 0700"
        )
    return path


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private_file(path: Path, payload: bytes) -> os.stat_result:
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise PublicEdgeMutationLockUnavailable("created mutation capability is unsafe")
    return metadata


def _read_token(path: Path, *, expected_identity: tuple[int, int] | None = None) -> str:
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise PublicEdgeMutationLockUnavailable("mutation capability has unsafe identity")
    if expected_identity is not None and (metadata.st_dev, metadata.st_ino) != expected_identity:
        raise PublicEdgeMutationLockUnavailable("mutation capability identity changed")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise PublicEdgeMutationLockUnavailable("mutation capability changed while opening")
        payload = os.read(descriptor, 129)
        if len(payload) > 128:
            raise PublicEdgeMutationLockUnavailable("mutation capability is oversized")
    finally:
        os.close(descriptor)
    try:
        token = payload.decode("ascii").strip()
    except UnicodeError as error:
        raise PublicEdgeMutationLockUnavailable("mutation capability is not ASCII") from error
    if re.fullmatch(r"[0-9a-f]{64}", token) is None:
        raise PublicEdgeMutationLockUnavailable("mutation capability is malformed")
    return token


def _rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise PublicEdgeMutationLockUnavailable("renameat2 is required for mutation authority")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(destination),
        RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in (errno.EEXIST, errno.ENOTEMPTY):
            raise PublicEdgeMutationLockUnavailable(
                "another public-edge mutation owns the shared deployment authority"
            )
        raise PublicEdgeMutationLockUnavailable(
            f"cannot atomically publish public-edge mutation lock: {os.strerror(error_number)}"
        )


def acquire_mutation_lease(
    *,
    actor: str,
    lock_path: Path = LOCK_PATH,
    authorization_root: Path = AUTH_ROOT,
) -> MutationLease:
    actor = _validate_actor(actor)
    lock_root = _ensure_private_directory(lock_path.parent)
    authorization_root = _ensure_private_directory(authorization_root)
    token = secrets.token_hex(32)
    token_sha256 = hashlib.sha256(token.encode("ascii")).hexdigest()
    authorization_path = authorization_root / f"{actor}-{token_sha256}.owner-token"
    staging = lock_root / f".{lock_path.name}.staging.{token_sha256}"
    token_payload = (token + "\n").encode("ascii")

    authorization_metadata: os.stat_result | None = None
    staging_created = False
    published = False
    try:
        authorization_metadata = _write_private_file(authorization_path, token_payload)
        _fsync_directory(authorization_root)
        staging.mkdir(mode=0o700)
        staging_created = True
        staging_metadata = staging.lstat()
        if (
            not stat.S_ISDIR(staging_metadata.st_mode)
            or staging_metadata.st_uid != os.getuid()
            or stat.S_IMODE(staging_metadata.st_mode) != 0o700
        ):
            raise PublicEdgeMutationLockUnavailable("staging mutation lock is unsafe")
        token_metadata = _write_private_file(staging / TOKEN_FILE_NAME, token_payload)
        _fsync_directory(staging)
        _fsync_directory(lock_root)
        _rename_noreplace(staging, lock_path)
        published = True
        staging_created = False
        _fsync_directory(lock_root)
        lock_metadata = lock_path.lstat()
        published_token = lock_path / TOKEN_FILE_NAME
        current_token_metadata = published_token.lstat()
        if (
            (current_token_metadata.st_dev, current_token_metadata.st_ino)
            != (token_metadata.st_dev, token_metadata.st_ino)
            or _read_token(published_token) != token
            or _read_token(authorization_path) != token
        ):
            raise PublicEdgeMutationLockUnavailable("published mutation lease identity drifted")
        return MutationLease(
            actor=actor,
            token=token,
            token_sha256=token_sha256,
            lock_path=lock_path,
            lock_device=lock_metadata.st_dev,
            lock_inode=lock_metadata.st_ino,
            token_device=token_metadata.st_dev,
            token_inode=token_metadata.st_ino,
            authorization_path=authorization_path,
            authorization_device=authorization_metadata.st_dev,
            authorization_inode=authorization_metadata.st_ino,
        )
    except Exception:
        if staging_created:
            try:
                (staging / TOKEN_FILE_NAME).unlink()
            except FileNotFoundError:
                pass
            try:
                staging.rmdir()
            except OSError:
                pass
        # A unique durable authorization orphan is nonblocking and intentionally retained if
        # lock publication may have happened; manual orphan cleanup can prove and remove it.
        if not published and authorization_metadata is not None:
            try:
                authorization_path.unlink()
                _fsync_directory(authorization_root)
            except OSError:
                pass
        raise


def release_mutation_lease(lease: MutationLease) -> None:
    lock_metadata = lease.lock_path.lstat()
    if (lock_metadata.st_dev, lock_metadata.st_ino) != (
        lease.lock_device,
        lease.lock_inode,
    ):
        raise PublicEdgeMutationLockUnavailable("public-edge mutation lock identity changed")
    internal = lease.lock_path / TOKEN_FILE_NAME
    internal_token = _read_token(
        internal, expected_identity=(lease.token_device, lease.token_inode)
    )
    external_token = _read_token(
        lease.authorization_path,
        expected_identity=(lease.authorization_device, lease.authorization_inode),
    )
    if not (
        hmac.compare_digest(internal_token, lease.token)
        and hmac.compare_digest(external_token, lease.token)
    ):
        raise PublicEdgeMutationLockUnavailable("mutation lease capability mismatch")
    if sorted(entry.name for entry in os.scandir(lease.lock_path)) != [TOKEN_FILE_NAME]:
        raise PublicEdgeMutationLockUnavailable("mutation lock contains unexpected entries")

    retired = lease.lock_path.parent / f".{lease.lock_path.name}.retired.{lease.token_sha256}"
    _rename_noreplace(lease.lock_path, retired)
    _fsync_directory(lease.lock_path.parent)
    internal = retired / TOKEN_FILE_NAME
    internal.unlink()
    retired.rmdir()
    _fsync_directory(lease.lock_path.parent)
    lease.authorization_path.unlink()
    _fsync_directory(lease.authorization_path.parent)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("mutation lease receipt must not be a symlink")
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
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _load_lease_receipt(path: Path) -> MutationLease:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractName") != "chummer.public_edge_mutation_lease.v1":
        raise ValueError("mutation lease receipt contract drifted")
    authorization_path = Path(str(payload["authorizationPath"]))
    token = _read_token(authorization_path)
    if hashlib.sha256(token.encode("ascii")).hexdigest() != payload["tokenSha256"]:
        raise ValueError("mutation lease authorization digest drifted")
    return MutationLease(
        actor=str(payload["actor"]),
        token=token,
        token_sha256=str(payload["tokenSha256"]),
        lock_path=Path(str(payload["lockPath"])),
        lock_device=int(payload["lockDevice"]),
        lock_inode=int(payload["lockInode"]),
        token_device=int(payload["tokenDevice"]),
        token_inode=int(payload["tokenInode"]),
        authorization_path=authorization_path,
        authorization_device=int(payload["authorizationDevice"]),
        authorization_inode=int(payload["authorizationInode"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the crash-consistent public-edge mutation lease.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    acquire_parser = subparsers.add_parser("acquire")
    acquire_parser.add_argument("--actor", required=True)
    acquire_parser.add_argument("--output", type=Path, required=True)
    acquire_parser.add_argument("--lock-path", type=Path, default=LOCK_PATH)
    acquire_parser.add_argument(
        "--authorization-root", type=Path, default=AUTH_ROOT
    )
    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("--lease-receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "acquire":
            lease = acquire_mutation_lease(
                actor=args.actor,
                lock_path=args.lock_path,
                authorization_root=args.authorization_root,
            )
            receipt = lease.receipt(status="active")
            _atomic_write(args.output, receipt)
        else:
            lease = _load_lease_receipt(args.lease_receipt)
            release_mutation_lease(lease)
            receipt = lease.receipt(status="released")
            _atomic_write(args.lease_receipt, receipt)
    except PublicEdgeMutationLockUnavailable as error:
        if str(error).startswith("another public-edge mutation"):
            print(str(error), file=sys.stderr)
            return 75
        parser.error(str(error))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(receipt, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
