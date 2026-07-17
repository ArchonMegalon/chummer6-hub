#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
DEFAULT_MIRROR_ROOTS = {
    "public_edge_main": WORKSPACE_ROOT / "chummer.run-services-public-edge-main",
    "participate_main": WORKSPACE_ROOT / "chummer.run-services-participate-main",
}

# Keep this exact set aligned with
# check_public_edge_deploy_preflight.PUBLIC_EDGE_OPERATIONAL_MIRROR_EXACT_PATH_SPECS.
CONTRACTED_RELATIVE_PATHS = (
    Path("Chummer.Run.Api/Views/PublicLanding/Status.cshtml"),
    Path("Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"),
    Path("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml"),
    Path("Chummer.Run.Api/Views/PublicLanding/Home.cshtml"),
    Path("Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml"),
    Path("Chummer.Run.Api/Controllers/PublicLandingController.cs"),
    Path("Chummer.Run.Api/wwwroot/service-worker.js"),
)

RENAME_EXCHANGE = 2
_LIBC = ctypes.CDLL(None, use_errno=True)


class MirrorSafetyError(RuntimeError):
    def __init__(self, blocker_id: str, path: str, detail: str = "") -> None:
        super().__init__(detail or f"{blocker_id}: {path}")
        self.blocker_id = blocker_id
        self.path = path
        self.detail = detail

    def blocker(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.blocker_id, "path": self.path}
        if self.detail:
            result["detail"] = self.detail
        return result


class FileSnapshot:
    def __init__(
        self,
        *,
        payload: bytes,
        device: int,
        inode: int,
        mode: int,
        user_id: int,
        group_id: int,
        link_count: int,
        size: int,
        modified_ns: int,
        changed_ns: int,
    ) -> None:
        self.payload = payload
        self.device = device
        self.inode = inode
        self.mode = mode
        self.user_id = user_id
        self.group_id = group_id
        self.link_count = link_count
        self.size = size
        self.modified_ns = modified_ns
        self.changed_ns = changed_ns

    @property
    def identity(self) -> tuple[int, int]:
        return self.device, self.inode

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.payload)


class PreparedUpdate:
    def __init__(
        self,
        *,
        item: dict[str, Any],
        mirror_root_fd: int,
        mirror_root_path: Path,
        parent_fd: int,
        target_fd: int,
        stage_fd: int,
        target_name: str,
        stage_name: str,
        target_snapshot: FileSnapshot,
        stage_snapshot: FileSnapshot,
    ) -> None:
        self.item = item
        self.mirror_root_fd = mirror_root_fd
        self.mirror_root_path = mirror_root_path
        self.parent_fd = parent_fd
        self.target_fd = target_fd
        self.stage_fd = stage_fd
        self.target_name = target_name
        self.stage_name = stage_name
        self.target_snapshot = target_snapshot
        self.stage_snapshot = stage_snapshot
        self.activated = False
        self.retain_stage = False


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_relative_path(value: Path) -> bool:
    return not value.is_absolute() and bool(value.parts) and all(
        part not in {"", ".", ".."} for part in value.parts
    )


def _directory_open_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise MirrorSafetyError(
            "descriptor_safety_unavailable",
            "filesystem",
            "O_NOFOLLOW and O_DIRECTORY are required",
        )
    if os.open not in os.supports_dir_fd:
        raise MirrorSafetyError(
            "descriptor_safety_unavailable",
            "filesystem",
            "descriptor-relative open is required",
        )
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _file_open_flags(*, writable: bool = False) -> int:
    flags = os.O_RDWR if writable else os.O_RDONLY
    return flags | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _raise_open_error(error: OSError, display_path: str) -> None:
    if error.errno == errno.ENOENT:
        raise MirrorSafetyError("missing_file", display_path) from error
    if error.errno in {errno.ELOOP, errno.ENOTDIR}:
        raise MirrorSafetyError("unsafe_symlink", display_path) from error
    raise MirrorSafetyError("file_open_failed", display_path, str(error)) from error


def open_root_directory(path: Path) -> int:
    absolute = path.absolute()
    if not absolute.is_absolute() or ".." in absolute.parts:
        raise MirrorSafetyError("invalid_root_path", str(path))
    flags = _directory_open_flags()
    try:
        descriptor = os.open(absolute.anchor, flags)
    except OSError as error:
        _raise_open_error(error, str(absolute))
        raise AssertionError("unreachable")
    try:
        for component in absolute.parts[1:]:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                _raise_open_error(error, str(absolute))
                raise AssertionError("unreachable")
            os.close(descriptor)
            descriptor = child
        root_stat = os.fstat(descriptor)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise MirrorSafetyError("not_directory", str(absolute))
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def root_identity(path: Path) -> tuple[int, int]:
    descriptor = open_root_directory(path)
    try:
        root_stat = os.fstat(descriptor)
        return root_stat.st_dev, root_stat.st_ino
    finally:
        os.close(descriptor)


def _root_identity_payload(identity: tuple[int, int]) -> dict[str, int]:
    return {"device": identity[0], "inode": identity[1]}


def _identity_from_payload(payload: Any) -> tuple[int, int] | None:
    if not isinstance(payload, dict):
        return None
    device = payload.get("device")
    inode = payload.get("inode")
    if not isinstance(device, int) or not isinstance(inode, int):
        return None
    return device, inode


def _relative_path(path: Path, root: Path) -> Path:
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as error:
        raise MirrorSafetyError("path_outside_root", str(path)) from error
    if not safe_relative_path(relative):
        raise MirrorSafetyError("invalid_relative_path", str(path))
    return relative


def _open_parent_directory(
    root_fd: int, relative_path: Path, display_path: str
) -> tuple[int, str]:
    if not safe_relative_path(relative_path):
        raise MirrorSafetyError("invalid_relative_path", display_path)
    descriptor = os.dup(root_fd)
    try:
        for component in relative_path.parts[:-1]:
            try:
                child = os.open(component, _directory_open_flags(), dir_fd=descriptor)
            except OSError as error:
                _raise_open_error(error, display_path)
                raise AssertionError("unreachable")
            os.close(descriptor)
            descriptor = child
        return descriptor, relative_path.name
    except Exception:
        os.close(descriptor)
        raise


def _snapshot_open_file(descriptor: int, display_path: str) -> FileSnapshot:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise MirrorSafetyError("not_regular_file", display_path)
    if before.st_nlink != 1:
        raise MirrorSafetyError(
            "unexpected_hardlink_count",
            display_path,
            f"linkCount={before.st_nlink}",
        )
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    except OSError as error:
        raise MirrorSafetyError("file_read_failed", display_path, str(error)) from error
    before_version = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_version = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_uid,
        after.st_gid,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_version != after_version:
        raise MirrorSafetyError("file_changed_during_read", display_path)
    return FileSnapshot(
        payload=b"".join(chunks),
        device=after.st_dev,
        inode=after.st_ino,
        mode=stat.S_IMODE(after.st_mode),
        user_id=after.st_uid,
        group_id=after.st_gid,
        link_count=after.st_nlink,
        size=after.st_size,
        modified_ns=after.st_mtime_ns,
        changed_ns=after.st_ctime_ns,
    )


def _open_named_regular(parent_fd: int, name: str, display_path: str) -> tuple[int, FileSnapshot]:
    try:
        descriptor = os.open(name, _file_open_flags(), dir_fd=parent_fd)
    except OSError as error:
        _raise_open_error(error, display_path)
        raise AssertionError("unreachable")
    try:
        return descriptor, _snapshot_open_file(descriptor, display_path)
    except Exception:
        os.close(descriptor)
        raise


def _read_relative_regular(root_fd: int, relative_path: Path, display_path: str) -> FileSnapshot:
    parent_fd, name = _open_parent_directory(root_fd, relative_path, display_path)
    try:
        descriptor, snapshot = _open_named_regular(parent_fd, name, display_path)
        os.close(descriptor)
        return snapshot
    finally:
        os.close(parent_fd)


def inspect_regular_file(
    path: Path, *, root: Path
) -> tuple[FileSnapshot | None, dict[str, Any] | None]:
    root_fd: int | None = None
    try:
        root_fd = open_root_directory(root)
        relative_path = _relative_path(path, root)
        return _read_relative_regular(root_fd, relative_path, str(path)), None
    except MirrorSafetyError as error:
        return None, error.blocker()
    finally:
        if root_fd is not None:
            os.close(root_fd)


def read_regular_file(path: Path, *, root: Path) -> tuple[bytes | None, dict[str, Any] | None]:
    snapshot, failure = inspect_regular_file(path, root=root)
    return (snapshot.payload if snapshot is not None else None), failure


def _file_identity_payload(snapshot: FileSnapshot) -> dict[str, int]:
    return {
        "device": snapshot.device,
        "inode": snapshot.inode,
        "mode": snapshot.mode,
        "userId": snapshot.user_id,
        "groupId": snapshot.group_id,
        "linkCount": snapshot.link_count,
        "size": snapshot.size,
        "modifiedNs": snapshot.modified_ns,
        "changedNs": snapshot.changed_ns,
    }


def _matches_planned_file_identity(snapshot: FileSnapshot, payload: Any) -> bool:
    return isinstance(payload, dict) and payload == _file_identity_payload(snapshot)


def git_dirty_paths(root: Path, paths: tuple[Path, ...]) -> tuple[list[str], str | None]:
    command = [
        "git",
        "-C",
        str(root),
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *[str(path) for path in paths],
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"git exited {completed.returncode}"
        return [], detail
    return [line for line in completed.stdout.splitlines() if line.strip()], None


def build_sync_plan(
    source_root: Path,
    mirror_roots: dict[str, Path],
    *,
    relative_paths: tuple[Path, ...] = CONTRACTED_RELATIVE_PATHS,
) -> dict[str, Any]:
    source_root = source_root.absolute()
    blockers: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    mirrors: list[dict[str, Any]] = []

    try:
        source_identity: tuple[int, int] | None = root_identity(source_root)
    except MirrorSafetyError:
        source_identity = None
        blockers.append({"id": "unsafe_or_missing_source_root", "path": str(source_root)})
    if not mirror_roots:
        blockers.append({"id": "no_mirror_roots_configured"})
    if not relative_paths or any(not safe_relative_path(path) for path in relative_paths):
        blockers.append({"id": "invalid_contracted_path_set"})

    mirror_identities: dict[str, tuple[int, int]] = {}
    seen_mirror_roots: dict[tuple[int, int], str] = {}
    for mirror_name, configured_root in mirror_roots.items():
        mirror_root = configured_root.absolute()
        try:
            canonical_identity = root_identity(mirror_root)
        except MirrorSafetyError:
            continue
        mirror_identities[mirror_name] = canonical_identity
        if source_identity is not None and canonical_identity == source_identity:
            blockers.append(
                {"id": "mirror_aliases_source_root", "mirror": mirror_name, "path": str(mirror_root)}
            )
        prior_name = seen_mirror_roots.get(canonical_identity)
        if prior_name is not None:
            blockers.append(
                {
                    "id": "duplicate_mirror_root",
                    "mirror": mirror_name,
                    "otherMirror": prior_name,
                    "path": str(mirror_root),
                }
            )
        else:
            seen_mirror_roots[canonical_identity] = mirror_name

    source_snapshots: dict[Path, FileSnapshot] = {}
    if not blockers:
        for relative_path in relative_paths:
            source_path = source_root / relative_path
            snapshot, failure = inspect_regular_file(source_path, root=source_root)
            if failure:
                blockers.append({**failure, "mirror": "canonical"})
            elif snapshot is not None:
                source_snapshots[relative_path] = snapshot

    for mirror_name, configured_root in mirror_roots.items():
        mirror_root = configured_root.absolute()
        mirror_summary: dict[str, Any] = {
            "name": mirror_name,
            "root": str(mirror_root),
            "rootIdentity": (
                _root_identity_payload(mirror_identities[mirror_name])
                if mirror_name in mirror_identities
                else None
            ),
            "dirtyPaths": [],
        }
        mirrors.append(mirror_summary)
        if mirror_name not in mirror_identities:
            blockers.append(
                {"id": "unsafe_or_missing_mirror_root", "mirror": mirror_name, "path": str(mirror_root)}
            )
            continue
        dirty, git_failure = git_dirty_paths(mirror_root, relative_paths)
        mirror_summary["dirtyPaths"] = dirty
        if git_failure:
            blockers.append(
                {"id": "mirror_git_status_failed", "mirror": mirror_name, "detail": git_failure}
            )
        elif dirty:
            blockers.append(
                {"id": "mirror_contracted_paths_dirty", "mirror": mirror_name, "paths": dirty}
            )

        for relative_path in relative_paths:
            source_snapshot = source_snapshots.get(relative_path)
            if source_snapshot is None:
                continue
            target_path = mirror_root / relative_path
            target_snapshot, failure = inspect_regular_file(target_path, root=mirror_root)
            if failure:
                blockers.append({**failure, "mirror": mirror_name})
                continue
            assert target_snapshot is not None
            source_digest = source_snapshot.sha256
            target_digest = target_snapshot.sha256
            files.append(
                {
                    "mirror": mirror_name,
                    "relativePath": str(relative_path),
                    "sourcePath": str(source_root / relative_path),
                    "targetPath": str(target_path),
                    "sourceSha256": source_digest,
                    "targetSha256": target_digest,
                    "sourceIdentity": _file_identity_payload(source_snapshot),
                    "targetIdentity": _file_identity_payload(target_snapshot),
                    "matchesCanonical": source_digest == target_digest,
                    "sourceBytes": len(source_snapshot.payload),
                    "targetBytes": len(target_snapshot.payload),
                }
            )

    drift_count = sum(not item["matchesCanonical"] for item in files)
    status = "blocked" if blockers else ("pass" if drift_count == 0 else "review_required")
    return {
        "contractName": "chummer.public_edge_operational_mirror_sync.v1",
        "status": status,
        "mode": "check",
        "sourceRoot": str(source_root),
        "sourceRootIdentity": (
            _root_identity_payload(source_identity) if source_identity is not None else None
        ),
        "contractedRelativePaths": [str(path) for path in relative_paths],
        "mirrors": mirrors,
        "files": files,
        "blockers": blockers,
        "driftCount": drift_count,
        "updatedCount": 0,
    }


def _snapshot_matches(
    actual: FileSnapshot,
    expected: FileSnapshot,
    *,
    strict_version: bool,
) -> bool:
    common = (
        actual.identity == expected.identity
        and actual.sha256 == expected.sha256
        and actual.mode == expected.mode
        and actual.user_id == expected.user_id
        and actual.group_id == expected.group_id
        and actual.link_count == expected.link_count == 1
    )
    if not common or not strict_version:
        return common
    return (
        actual.size == expected.size
        and actual.modified_ns == expected.modified_ns
        and actual.changed_ns == expected.changed_ns
    )


def _read_named_regular(parent_fd: int, name: str, display_path: str) -> FileSnapshot:
    descriptor, snapshot = _open_named_regular(parent_fd, name, display_path)
    os.close(descriptor)
    return snapshot


def _write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError(errno.EIO, "short write while staging mirror update")
        remaining = remaining[written:]


def _create_staged_file(
    parent_fd: int,
    target_name: str,
    payload: bytes,
    target_snapshot: FileSnapshot,
    display_path: str,
) -> tuple[str, int, FileSnapshot]:
    descriptor: int | None = None
    stage_name = ""
    for _ in range(32):
        candidate = f".{target_name}.chummer-sync-{secrets.token_hex(16)}"
        try:
            descriptor = os.open(
                candidate,
                _file_open_flags(writable=True) | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=parent_fd,
            )
            stage_name = candidate
            break
        except FileExistsError:
            continue
        except OSError as error:
            raise MirrorSafetyError("stage_create_failed", display_path, str(error)) from error
    if descriptor is None:
        raise MirrorSafetyError("stage_create_failed", display_path, "temporary name exhaustion")
    try:
        staged_stat = os.fstat(descriptor)
        if (staged_stat.st_uid, staged_stat.st_gid) != (
            target_snapshot.user_id,
            target_snapshot.group_id,
        ):
            os.fchown(descriptor, target_snapshot.user_id, target_snapshot.group_id)
        os.fchmod(descriptor, target_snapshot.mode)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        snapshot = _snapshot_open_file(descriptor, display_path)
        if snapshot.payload != payload:
            raise MirrorSafetyError("stage_validation_failed", display_path)
        return stage_name, descriptor, snapshot
    except Exception:
        os.close(descriptor)
        try:
            os.unlink(stage_name, dir_fd=parent_fd)
        except OSError:
            pass
        raise


def _atomic_exchange_entries(parent_fd: int, left_name: str, right_name: str) -> None:
    left = os.fsencode(left_name)
    right = os.fsencode(right_name)
    renameat2 = getattr(_LIBC, "renameat2", None)
    if renameat2 is not None:
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        if renameat2(parent_fd, left, parent_fd, right, RENAME_EXCHANGE) == 0:
            return
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), f"{left_name}<->{right_name}")

    renameatx_np = getattr(_LIBC, "renameatx_np", None)
    if renameatx_np is not None:
        renameatx_np.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameatx_np.restype = ctypes.c_int
        if renameatx_np(parent_fd, left, parent_fd, right, RENAME_EXCHANGE) == 0:
            return
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), f"{left_name}<->{right_name}")

    raise MirrorSafetyError(
        "atomic_exchange_unavailable",
        f"{left_name}<->{right_name}",
        "renameat2(RENAME_EXCHANGE) or renameatx_np(RENAME_SWAP) is required",
    )


def _fsync_directory(descriptor: int) -> None:
    os.fsync(descriptor)


def _validate_entry_path_binding(entry: PreparedUpdate) -> None:
    display_path = entry.item["targetPath"]
    fresh_root_fd = open_root_directory(entry.mirror_root_path)
    fresh_parent_fd: int | None = None
    try:
        held_root = os.fstat(entry.mirror_root_fd)
        fresh_root = os.fstat(fresh_root_fd)
        if (held_root.st_dev, held_root.st_ino) != (fresh_root.st_dev, fresh_root.st_ino):
            raise MirrorSafetyError("mirror_root_path_changed", str(entry.mirror_root_path))
        fresh_parent_fd, target_name = _open_parent_directory(
            fresh_root_fd,
            Path(entry.item["relativePath"]),
            display_path,
        )
        held_parent = os.fstat(entry.parent_fd)
        fresh_parent = os.fstat(fresh_parent_fd)
        if target_name != entry.target_name or (
            held_parent.st_dev,
            held_parent.st_ino,
        ) != (fresh_parent.st_dev, fresh_parent.st_ino):
            raise MirrorSafetyError("mirror_parent_path_changed", display_path)
    finally:
        if fresh_parent_fd is not None:
            os.close(fresh_parent_fd)
        os.close(fresh_root_fd)


def _validate_pre_activation(entry: PreparedUpdate) -> None:
    display_path = entry.item["targetPath"]
    _validate_entry_path_binding(entry)
    held_target = _snapshot_open_file(entry.target_fd, display_path)
    named_target = _read_named_regular(entry.parent_fd, entry.target_name, display_path)
    held_stage = _snapshot_open_file(entry.stage_fd, display_path)
    named_stage = _read_named_regular(entry.parent_fd, entry.stage_name, display_path)
    if not _snapshot_matches(held_target, entry.target_snapshot, strict_version=True):
        raise MirrorSafetyError("mirror_changed_before_activation", display_path)
    if not _snapshot_matches(named_target, entry.target_snapshot, strict_version=True):
        raise MirrorSafetyError("mirror_path_changed_before_activation", display_path)
    if not _snapshot_matches(held_stage, entry.stage_snapshot, strict_version=True):
        raise MirrorSafetyError("stage_changed_before_activation", display_path)
    if not _snapshot_matches(named_stage, entry.stage_snapshot, strict_version=True):
        raise MirrorSafetyError("stage_path_changed_before_activation", display_path)


def _restore_failed_exchange(
    entry: PreparedUpdate,
    post_target: FileSnapshot | None,
    post_stage: FileSnapshot | None,
) -> str | None:
    target_is_ours = post_target is not None and _snapshot_matches(
        post_target, entry.stage_snapshot, strict_version=False
    )
    stage_is_original = post_stage is not None and _snapshot_matches(
        post_stage, entry.target_snapshot, strict_version=False
    )
    if not target_is_ours and not stage_is_original:
        entry.retain_stage = True
        return "exchange rollback refused because neither path retained a trusted transaction identity"
    try:
        _atomic_exchange_entries(entry.parent_fd, entry.target_name, entry.stage_name)
        entry.activated = False
        _fsync_directory(entry.parent_fd)
        restored_target = _read_named_regular(
            entry.parent_fd, entry.target_name, entry.item["targetPath"]
        )
        restored_stage = _read_named_regular(
            entry.parent_fd, entry.stage_name, entry.item["targetPath"]
        )
    except Exception as error:
        entry.retain_stage = True
        return f"exchange rollback failed: {error}"
    expected_target = post_stage
    expected_stage = post_target
    if (
        expected_target is None
        or expected_stage is None
        or not _snapshot_matches(restored_target, expected_target, strict_version=False)
        or not _snapshot_matches(restored_stage, expected_stage, strict_version=False)
    ):
        entry.retain_stage = True
        return "exchange rollback post-validation failed"
    if not _snapshot_matches(restored_stage, entry.stage_snapshot, strict_version=False):
        entry.retain_stage = True
        return "unexpected staged-path content retained after exchange rollback"
    return None


def _activate_entry(entry: PreparedUpdate) -> None:
    _validate_pre_activation(entry)
    _atomic_exchange_entries(entry.parent_fd, entry.target_name, entry.stage_name)
    entry.activated = True
    _fsync_directory(entry.parent_fd)
    post_target: FileSnapshot | None = None
    post_stage: FileSnapshot | None = None
    try:
        post_target = _read_named_regular(
            entry.parent_fd, entry.target_name, entry.item["targetPath"]
        )
        post_stage = _read_named_regular(
            entry.parent_fd, entry.stage_name, entry.item["targetPath"]
        )
        if not _snapshot_matches(post_target, entry.stage_snapshot, strict_version=False):
            raise MirrorSafetyError("activated_target_validation_failed", entry.item["targetPath"])
        if not _snapshot_matches(post_stage, entry.target_snapshot, strict_version=False):
            raise MirrorSafetyError("displaced_target_validation_failed", entry.item["targetPath"])
    except Exception as error:
        rollback_error = _restore_failed_exchange(entry, post_target, post_stage)
        detail = str(error)
        if rollback_error:
            detail = f"{detail}; {rollback_error}"
        raise MirrorSafetyError("activation_cas_failed", entry.item["targetPath"], detail) from error


def _validate_activated_entry(entry: PreparedUpdate) -> None:
    if not entry.activated:
        raise MirrorSafetyError("transaction_state_invalid", entry.item["targetPath"])
    _validate_entry_path_binding(entry)
    target = _read_named_regular(entry.parent_fd, entry.target_name, entry.item["targetPath"])
    backup = _read_named_regular(entry.parent_fd, entry.stage_name, entry.item["targetPath"])
    if not _snapshot_matches(target, entry.stage_snapshot, strict_version=False):
        raise MirrorSafetyError("post_activation_target_changed", entry.item["targetPath"])
    if not _snapshot_matches(backup, entry.target_snapshot, strict_version=False):
        raise MirrorSafetyError("post_activation_backup_changed", entry.item["targetPath"])


def _rollback_entry(entry: PreparedUpdate) -> str | None:
    if not entry.activated:
        return None
    try:
        current_target = _read_named_regular(
            entry.parent_fd, entry.target_name, entry.item["targetPath"]
        )
        current_backup = _read_named_regular(
            entry.parent_fd, entry.stage_name, entry.item["targetPath"]
        )
    except Exception as error:
        entry.retain_stage = True
        return f"rollback pre-validation failed: {error}"
    if not _snapshot_matches(current_target, entry.stage_snapshot, strict_version=False):
        entry.retain_stage = True
        return "rollback refused because target changed after activation"
    if not _snapshot_matches(current_backup, entry.target_snapshot, strict_version=False):
        entry.retain_stage = True
        return "rollback refused because backup changed after activation"
    try:
        _atomic_exchange_entries(entry.parent_fd, entry.target_name, entry.stage_name)
        entry.activated = False
        _fsync_directory(entry.parent_fd)
        restored_target = _read_named_regular(
            entry.parent_fd, entry.target_name, entry.item["targetPath"]
        )
        staged_update = _read_named_regular(
            entry.parent_fd, entry.stage_name, entry.item["targetPath"]
        )
    except Exception as error:
        entry.retain_stage = True
        return f"rollback failed: {error}"
    if not _snapshot_matches(restored_target, entry.target_snapshot, strict_version=False):
        entry.retain_stage = True
        return "rollback target post-validation failed"
    if not _snapshot_matches(staged_update, entry.stage_snapshot, strict_version=False):
        entry.retain_stage = True
        return "rollback stage post-validation failed"
    return None


def _unlink_stage(entry: PreparedUpdate, expected: FileSnapshot) -> None:
    current = _read_named_regular(entry.parent_fd, entry.stage_name, entry.item["targetPath"])
    if not _snapshot_matches(current, expected, strict_version=False):
        entry.retain_stage = True
        raise MirrorSafetyError("stage_cleanup_identity_mismatch", entry.item["targetPath"])
    os.unlink(entry.stage_name, dir_fd=entry.parent_fd)
    _fsync_directory(entry.parent_fd)
    entry.stage_name = ""


def _close_entry(entry: PreparedUpdate) -> None:
    os.close(entry.target_fd)
    os.close(entry.stage_fd)
    os.close(entry.parent_fd)


def _prepare_update(
    item: dict[str, Any],
    source_root_fd: int,
    mirror_root_fd: int,
    mirror_root_path: Path,
) -> PreparedUpdate:
    relative_path = Path(item["relativePath"])
    source_snapshot = _read_relative_regular(
        source_root_fd, relative_path, item["sourcePath"]
    )
    if (
        source_snapshot.sha256 != item["sourceSha256"]
        or not _matches_planned_file_identity(source_snapshot, item.get("sourceIdentity"))
    ):
        raise MirrorSafetyError("canonical_changed_after_preflight", item["sourcePath"])
    parent_fd, target_name = _open_parent_directory(
        mirror_root_fd, relative_path, item["targetPath"]
    )
    target_fd: int | None = None
    stage_fd: int | None = None
    stage_name = ""
    try:
        target_fd, target_snapshot = _open_named_regular(
            parent_fd, target_name, item["targetPath"]
        )
        if (
            target_snapshot.sha256 != item["targetSha256"]
            or not _matches_planned_file_identity(target_snapshot, item.get("targetIdentity"))
        ):
            raise MirrorSafetyError("mirror_changed_after_preflight", item["targetPath"])
        stage_name, stage_fd, stage_snapshot = _create_staged_file(
            parent_fd,
            target_name,
            source_snapshot.payload,
            target_snapshot,
            item["targetPath"],
        )
        return PreparedUpdate(
            item=item,
            mirror_root_fd=mirror_root_fd,
            mirror_root_path=mirror_root_path,
            parent_fd=parent_fd,
            target_fd=target_fd,
            stage_fd=stage_fd,
            target_name=target_name,
            stage_name=stage_name,
            target_snapshot=target_snapshot,
            stage_snapshot=stage_snapshot,
        )
    except Exception:
        if stage_fd is not None:
            os.close(stage_fd)
        if stage_name:
            try:
                os.unlink(stage_name, dir_fd=parent_fd)
            except OSError:
                pass
        if target_fd is not None:
            os.close(target_fd)
        os.close(parent_fd)
        raise


def _validated_root(path: Path, expected_payload: Any, blocker_id: str) -> int:
    expected = _identity_from_payload(expected_payload)
    if expected is None:
        raise MirrorSafetyError("sync_plan_missing_root_identity", str(path))
    descriptor = open_root_directory(path)
    actual_stat = os.fstat(descriptor)
    if (actual_stat.st_dev, actual_stat.st_ino) != expected:
        os.close(descriptor)
        raise MirrorSafetyError(blocker_id, str(path))
    return descriptor


def apply_sync_plan(plan: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(plan))
    result["mode"] = "apply"
    if result.get("blockers"):
        result["status"] = "blocked"
        return result

    drifted = [item for item in plan.get("files", []) if not item.get("matchesCanonical")]
    if not drifted:
        result["status"] = "pass"
        return result

    source_root = Path(plan["sourceRoot"])
    mirror_by_name = {mirror["name"]: mirror for mirror in plan.get("mirrors", [])}
    source_root_fd: int | None = None
    mirror_root_fds: dict[str, int] = {}
    prepared: list[PreparedUpdate] = []
    final_target_identities: dict[tuple[str, str], dict[str, int]] = {}
    commit_started = False
    try:
        source_root_fd = _validated_root(
            source_root,
            plan.get("sourceRootIdentity"),
            "canonical_root_changed_after_preflight",
        )
        for mirror_name in {item["mirror"] for item in drifted}:
            mirror = mirror_by_name.get(mirror_name)
            if mirror is None:
                raise MirrorSafetyError("sync_plan_missing_mirror", mirror_name)
            mirror_root_fds[mirror_name] = _validated_root(
                Path(mirror["root"]),
                mirror.get("rootIdentity"),
                "mirror_root_changed_after_preflight",
            )
            dirty, git_failure = git_dirty_paths(
                Path(mirror["root"]),
                tuple(Path(path) for path in plan["contractedRelativePaths"]),
            )
            if git_failure:
                raise MirrorSafetyError("mirror_git_status_failed", mirror["root"], git_failure)
            if dirty:
                raise MirrorSafetyError(
                    "mirror_changed_after_preflight",
                    mirror["root"],
                    json.dumps(dirty),
                )

        for item in drifted:
            relative_path = Path(item["relativePath"])
            mirror = mirror_by_name[item["mirror"]]
            if not safe_relative_path(relative_path):
                raise MirrorSafetyError("invalid_relative_path", item["relativePath"])
            if Path(item["sourcePath"]) != source_root / relative_path:
                raise MirrorSafetyError("sync_plan_source_path_mismatch", item["sourcePath"])
            if Path(item["targetPath"]) != Path(mirror["root"]) / relative_path:
                raise MirrorSafetyError("sync_plan_target_path_mismatch", item["targetPath"])
            prepared.append(
                _prepare_update(
                    item,
                    source_root_fd,
                    mirror_root_fds[item["mirror"]],
                    Path(mirror["root"]),
                )
            )

        for entry in prepared:
            _validate_pre_activation(entry)
        for entry in prepared:
            _activate_entry(entry)

        for entry in prepared:
            _validate_activated_entry(entry)
            source_snapshot = _read_relative_regular(
                source_root_fd,
                Path(entry.item["relativePath"]),
                entry.item["sourcePath"],
            )
            if (
                source_snapshot.sha256 != entry.item["sourceSha256"]
                or not _matches_planned_file_identity(
                    source_snapshot, entry.item.get("sourceIdentity")
                )
            ):
                raise MirrorSafetyError(
                    "canonical_changed_during_activation", entry.item["sourcePath"]
                )

        # The exchange retained every displaced target until all activations and
        # source/target post-validations passed. Deleting those backups is the
        # transaction commit point.
        for entry in prepared:
            _validate_activated_entry(entry)
        commit_started = True
        for entry in prepared:
            _unlink_stage(entry, entry.target_snapshot)
        for entry in prepared:
            _validate_entry_path_binding(entry)
            final_target = _read_named_regular(
                entry.parent_fd, entry.target_name, entry.item["targetPath"]
            )
            if not _snapshot_matches(final_target, entry.stage_snapshot, strict_version=False):
                raise MirrorSafetyError(
                    "post_commit_target_changed", entry.item["targetPath"]
                )
            final_target_identities[
                (entry.item["mirror"], entry.item["relativePath"])
            ] = _file_identity_payload(final_target)

        result["updatedCount"] = len(prepared)
        result["driftCount"] = 0
        result["status"] = "pass"
        for item in result["files"]:
            if not item["matchesCanonical"]:
                item["targetSha256"] = item["sourceSha256"]
                item["targetBytes"] = item["sourceBytes"]
                item["targetIdentity"] = final_target_identities[
                    (item["mirror"], item["relativePath"])
                ]
                item["matchesCanonical"] = True
        return result
    except Exception as error:
        rollback_failures: list[dict[str, str]] = []
        if not commit_started:
            for entry in reversed(prepared):
                rollback_error = _rollback_entry(entry)
                if rollback_error:
                    rollback_failures.append(
                        {"path": entry.item["targetPath"], "detail": rollback_error}
                    )
        for entry in prepared:
            if not entry.activated and entry.stage_name and not entry.retain_stage:
                try:
                    _unlink_stage(entry, entry.stage_snapshot)
                except Exception as cleanup_error:
                    entry.retain_stage = True
                    rollback_failures.append(
                        {"path": entry.item["targetPath"], "detail": str(cleanup_error)}
                    )
        retained = [
            str(Path(entry.item["targetPath"]).parent / entry.stage_name)
            for entry in prepared
            if entry.stage_name and entry.retain_stage
        ]
        blocker: dict[str, Any]
        if isinstance(error, MirrorSafetyError):
            blocker = error.blocker()
        else:
            blocker = {"id": "atomic_update_failed", "detail": str(error)}
        if rollback_failures:
            blocker["rollbackFailures"] = rollback_failures
        if retained:
            blocker["retainedRollbackPaths"] = retained
        result["blockers"] = [blocker]
        result["status"] = "blocked"
        result["updatedCount"] = sum(entry.activated for entry in prepared)
        return result
    finally:
        for entry in prepared:
            _close_entry(entry)
        for descriptor in mirror_root_fds.values():
            os.close(descriptor)
        if source_root_fd is not None:
            os.close(source_root_fd)


def parse_mirror(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("mirror must use NAME=/absolute/path")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("mirror path must be absolute")
    return name.strip(), path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check exact public-edge operational mirror parity. Writes require --apply, "
            "and dirty contracted target paths are always refused."
        )
    )
    parser.add_argument("--source-root", type=Path, default=RUN_SERVICES_ROOT)
    parser.add_argument("--mirror", action="append", type=parse_mirror, default=[])
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mirror_roots = dict(args.mirror) if args.mirror else dict(DEFAULT_MIRROR_ROOTS)
    plan = build_sync_plan(args.source_root, mirror_roots)
    result = apply_sync_plan(plan) if args.apply else plan
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
