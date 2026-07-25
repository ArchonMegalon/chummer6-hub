#!/usr/bin/env python3
"""Audit or quarantine historical macOS release bearer curl configs.

The release publisher no longer persists curl authentication configuration.
This utility exists only to remove files created by older release workspaces.
It never emits file contents or bearer values.

Stop release publishers before quarantine. On macOS, quarantine fails closed
when the release tree has any extended ACL; audit-only mode remains available.
"""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import uuid
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_NAME = "chummer.historical-release-bearer-config-quarantine/v1"
TARGET_FILE_NAME = "upload-auth.curl"
QUARANTINE_DIRECTORY_NAME = ".credential-quarantine"
QUARANTINE_CONFIRMATION = "QUARANTINE_HISTORICAL_RELEASE_BEARER_CONFIGS"
MAX_CREDENTIAL_FILE_BYTES = 1024 * 1024
AUTHORIZATION_BEARER = re.compile(
    rb"(?i)authorization[ \t]*:[ \t]*bearer[ \t]+(?=\S)"
)
OAUTH2_BEARER = re.compile(
    rb"(?i)^(?:--)?oauth2-bearer\b"
    rb"(?:[ \t]*[:=][ \t]*|[ \t]+)(?=\S)"
)
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
JOURNAL_FILE_NAME = "QUARANTINE_JOURNAL.generated.jsonl"
RECEIPT_FILE_NAME = "QUARANTINE_RECEIPT.generated.json"


class AuditError(RuntimeError):
    """The requested audit could not be performed safely."""


def _contains_bearer_material(content: bytes) -> bool:
    for raw_line in content.splitlines():
        line = raw_line.lstrip()
        if not line or line.startswith(b"#"):
            continue
        if AUTHORIZATION_BEARER.search(line) or OAUTH2_BEARER.match(line):
            return True
    return False


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _require_descriptor_relative_filesystem_support() -> None:
    required = (os.open, os.stat, os.mkdir, os.unlink, os.rename, os.link)
    if (
        any(operation not in os.supports_dir_fd for operation in required)
        or os.link not in os.supports_follow_symlinks
    ):
        raise AuditError(
            "platform lacks required descriptor-relative filesystem support"
        )


def _darwin_fd_has_extended_acl(
    descriptor: int,
    display_path: str,
) -> bool:
    if sys.platform != "darwin":
        return False
    completed = subprocess.run(
        (
            "/bin/ls",
            "-L",
            "-l",
            "-d",
            "-e",
            f"/dev/fd/{descriptor}",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        pass_fds=(descriptor,),
        env={**os.environ, "LC_ALL": "C"},
    )
    if completed.returncode != 0:
        raise AuditError(
            f"unable to verify macOS ACL confinement: {display_path}"
        )
    return len(completed.stdout.splitlines()) > 1


def _assert_no_extended_acl(
    descriptor: int,
    display_path: str,
) -> None:
    if _darwin_fd_has_extended_acl(descriptor, display_path):
        raise AuditError(
            f"extended ACL prevents owner-only confinement: {display_path}"
        )


def _assert_directory_safety(
    descriptor: int,
    display_path: str,
    *,
    owner_only: bool,
) -> os.stat_result:
    directory_stat = os.fstat(descriptor)
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise AuditError(f"unsafe directory: {display_path}")
    if directory_stat.st_uid != os.geteuid():
        raise AuditError(
            f"directory is not owned by the current user: {display_path}"
        )
    disallowed_mode = 0o077 if owner_only else 0o022
    if stat.S_IMODE(directory_stat.st_mode) & disallowed_mode:
        requirement = "owner-only" if owner_only else "non-writable"
        raise AuditError(
            f"directory is not {requirement} by other principals: "
            f"{display_path}"
        )
    _assert_no_extended_acl(descriptor, display_path)
    return directory_stat


def _open_absolute_directory_no_symlinks(path: Path) -> int:
    if not path.is_absolute():
        raise AuditError(f"directory path must be absolute: {path}")
    _require_descriptor_relative_filesystem_support()
    descriptor = os.open(os.sep, _directory_open_flags())
    try:
        current_display = Path(os.sep)
        for component in path.parts[1:]:
            try:
                next_descriptor = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise AuditError(
                    f"unsafe directory ancestry: {current_display / component}"
                ) from exc
            os.close(descriptor)
            descriptor = next_descriptor
            current_display /= component
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_relative_directory(
    parent_descriptor: int,
    components: Sequence[str],
    *,
    display_root: Path,
    create: bool,
    owner_only: bool,
    safe_mutation_ancestry: bool,
) -> int:
    descriptor = os.dup(parent_descriptor)
    current_display = display_root
    try:
        for component in components:
            if component in ("", ".", "..") or os.sep in component:
                raise AuditError(
                    f"unsafe relative directory component: {component!r}"
                )
            current_display /= component
            created = False
            try:
                next_descriptor = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise AuditError(
                        f"required directory does not exist: {current_display}"
                    )
                _assert_directory_safety(
                    descriptor,
                    str(current_display.parent),
                    owner_only=False,
                )
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    created = True
                except FileExistsError:
                    pass
                try:
                    next_descriptor = os.open(
                        component,
                        _directory_open_flags(),
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise AuditError(
                        f"unsafe created directory: {current_display}"
                    ) from exc
            except OSError as exc:
                raise AuditError(
                    f"unsafe directory ancestry: {current_display}"
                ) from exc
            os.close(descriptor)
            descriptor = next_descriptor
            if created:
                os.fchmod(descriptor, 0o700)
            if owner_only or created:
                _assert_directory_safety(
                    descriptor,
                    str(current_display),
                    owner_only=True,
                )
            elif safe_mutation_ancestry:
                _assert_directory_safety(
                    descriptor,
                    str(current_display),
                    owner_only=False,
                )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _mode_string(mode: int) -> str:
    return f"{stat.S_IMODE(mode):04o}"


def _validate_release_root(value: Path) -> Path:
    if not value.is_absolute():
        raise AuditError("release root must be an absolute path")
    try:
        root_stat = os.lstat(value)
    except FileNotFoundError as exc:
        raise AuditError(f"release root does not exist: {value}") from exc
    if stat.S_ISLNK(root_stat.st_mode):
        raise AuditError("release root cannot be a symbolic link")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise AuditError("release root is not a directory")
    descriptor = _open_absolute_directory_no_symlinks(value)
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != root_stat.st_dev
            or opened.st_ino != root_stat.st_ino
        ):
            raise AuditError("release root changed while it was opened")
    finally:
        os.close(descriptor)
    return value


def _iter_run_directories(release_root: Path) -> Iterable[Path]:
    for entry in sorted(os.scandir(release_root), key=lambda item: item.name):
        if not entry.name.startswith("run-"):
            continue
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError as exc:
            raise AuditError(
                f"unable to inspect release run entry: {entry.name}"
            ) from exc
        yield Path(entry.path)


def _iter_candidate_paths(release_root: Path) -> Iterable[Path]:
    def traversal_error(error: OSError) -> None:
        display_path = error.filename or release_root
        raise AuditError(
            f"unable to traverse release run directory: {display_path}"
        ) from error

    for run_root in _iter_run_directories(release_root):
        for current_root, directory_names, file_names in os.walk(
            run_root,
            topdown=True,
            onerror=traversal_error,
            followlinks=False,
        ):
            safe_directories: list[str] = []
            for directory_name in sorted(directory_names):
                directory_path = Path(current_root) / directory_name
                try:
                    directory_stat = os.lstat(directory_path)
                except FileNotFoundError as exc:
                    raise AuditError(
                        f"release run directory changed during traversal: "
                        f"{directory_path}"
                    ) from exc
                except OSError as exc:
                    raise AuditError(
                        f"unable to inspect release run directory: "
                        f"{directory_path}"
                    ) from exc
                if stat.S_ISDIR(directory_stat.st_mode):
                    safe_directories.append(directory_name)
            directory_names[:] = safe_directories
            if TARGET_FILE_NAME in file_names:
                yield Path(current_root) / TARGET_FILE_NAME


def _read_stable_regular_file_at(
    parent_descriptor: int,
    file_name: str,
    display_path: Path,
    *,
    retain_descriptor: bool = False,
) -> tuple[bytes, os.stat_result, int | None]:
    try:
        initial = os.stat(
            file_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError as exc:
        raise AuditError(
            f"candidate disappeared before audit: {display_path}"
        ) from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise AuditError(
            f"candidate is not a regular non-symlink file: {display_path}"
        )
    if initial.st_nlink != 1:
        raise AuditError(f"candidate has multiple hard links: {display_path}")
    if initial.st_size > MAX_CREDENTIAL_FILE_BYTES:
        raise AuditError(
            f"candidate exceeds the safe audit size limit: {display_path}"
        )

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        descriptor = os.open(
            file_name,
            flags,
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise AuditError(
            f"unable to open candidate safely: {display_path}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != initial.st_dev
            or opened.st_ino != initial.st_ino
            or opened.st_mode != initial.st_mode
            or opened.st_size != initial.st_size
            or opened.st_nlink != 1
        ):
            raise AuditError(
                f"candidate changed while it was opened: {display_path}"
            )
        chunks: list[bytes] = []
        remaining = MAX_CREDENTIAL_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > MAX_CREDENTIAL_FILE_BYTES:
            raise AuditError(
                f"candidate exceeds the safe audit size limit: {display_path}"
            )
        final = os.fstat(descriptor)
        if (
            final.st_dev != opened.st_dev
            or final.st_ino != opened.st_ino
            or final.st_mode != opened.st_mode
            or final.st_size != opened.st_size
            or final.st_nlink != 1
            or len(content) != opened.st_size
        ):
            raise AuditError(
                f"candidate changed during audit: {display_path}"
            )
        if retain_descriptor:
            retained = descriptor
            descriptor = -1
            return content, final, retained
        return content, final, None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_stable_regular_file(path: Path) -> tuple[bytes, os.stat_result]:
    parent_descriptor = _open_absolute_directory_no_symlinks(path.parent)
    try:
        content, file_stat, _ = _read_stable_regular_file_at(
            parent_descriptor,
            path.name,
            path,
        )
        return content, file_stat
    finally:
        os.close(parent_descriptor)


def _nearest_git_marker(path: Path) -> Path | None:
    current = path
    while True:
        marker = current / ".git"
        try:
            os.lstat(marker)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise AuditError(
                f"unable to inspect candidate Git marker: {marker}"
            ) from exc
        else:
            return marker
        if current.parent == current:
            return None
        current = current.parent


def _git_tracking(path: Path) -> tuple[bool, str | None]:
    git_environment = os.environ.copy()
    for key in (
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_WORK_TREE",
    ):
        git_environment.pop(key, None)
    git_environment["LC_ALL"] = "C"
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        (
            "git",
            "-C",
            str(path.parent),
            "rev-parse",
            "--show-toplevel",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=git_environment,
    )
    if completed.returncode != 0:
        if (
            "not a git repository" in completed.stderr.lower()
            and _nearest_git_marker(path.parent) is None
        ):
            return False, None
        raise AuditError("unable to determine candidate Git repository")
    git_root = Path(completed.stdout.strip())
    try:
        relative_path = path.relative_to(git_root)
    except ValueError:
        return False, None
    tracked = subprocess.run(
        (
            "git",
            "--literal-pathspecs",
            "-C",
            str(git_root),
            "ls-files",
            "--error-unmatch",
            "--",
            relative_path.as_posix(),
        ),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        env=git_environment,
    )
    if tracked.returncode == 0:
        return True, str(git_root)
    if tracked.returncode == 1:
        return False, str(git_root)
    raise AuditError("unable to determine candidate Git tracking state")


def _audit_candidate(release_root: Path, path: Path) -> dict[str, Any]:
    content, file_stat = _read_stable_regular_file(path)
    tracked, git_root = _git_tracking(path)
    record: dict[str, Any] = {
        "relativePath": path.relative_to(release_root).as_posix(),
        "_contentSha256": hashlib.sha256(content).hexdigest(),
        "sizeBytes": len(content),
        "mode": _mode_string(file_stat.st_mode),
        "modifiedAt": dt.datetime.fromtimestamp(
            file_stat.st_mtime,
            tz=dt.timezone.utc,
        )
        .isoformat()
        .replace("+00:00", "Z"),
        "bearerMaterialDetected": _contains_bearer_material(content),
        "gitTracked": tracked,
    }
    if git_root is not None:
        try:
            record["gitRootRelativePath"] = Path(git_root).relative_to(
                release_root
            ).as_posix()
        except ValueError:
            record["gitRootRelativePath"] = None
    return record


def audit_release_root(release_root: Path) -> dict[str, Any]:
    root = _validate_release_root(release_root)
    candidates = [
        _audit_candidate(root, path) for path in _iter_candidate_paths(root)
    ]
    candidates.sort(key=lambda row: str(row["relativePath"]))
    return {
        "contractName": CONTRACT_NAME,
        "generatedAt": _utc_now(),
        "releaseRoot": str(root),
        "targetFileName": TARGET_FILE_NAME,
        "status": "clean" if not candidates else "findings",
        "candidateCount": len(candidates),
        "bearerMaterialCount": sum(
            1 for row in candidates if row["bearerMaterialDetected"]
        ),
        "gitTrackedCount": sum(1 for row in candidates if row["gitTracked"]),
        "candidates": candidates,
    }


def _open_owner_only_directory(path: Path, *, create: bool) -> int:
    if not path.is_absolute():
        raise AuditError(f"owner-only directory must be absolute: {path}")
    _require_descriptor_relative_filesystem_support()
    root_descriptor = os.open(os.sep, _directory_open_flags())
    try:
        descriptor = _open_relative_directory(
            root_descriptor,
            path.parts[1:],
            display_root=Path(os.sep),
            create=create,
            owner_only=False,
            safe_mutation_ancestry=False,
        )
    finally:
        os.close(root_descriptor)
    try:
        _assert_directory_safety(
            descriptor,
            str(path),
            owner_only=True,
        )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _fsync_directory_descriptor(descriptor: int) -> bool:
    try:
        os.fsync(descriptor)
        return True
    except OSError as exc:
        unsupported_errors = {
            errno.EINVAL,
            getattr(errno, "ENOTSUP", errno.EINVAL),
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }
        if exc.errno in unsupported_errors:
            return False
        raise


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise AuditError("unable to complete private receipt write")
        offset += written


def _create_private_file_at(
    parent_descriptor: int,
    file_name: str,
    display_path: Path,
) -> tuple[int, os.stat_result]:
    if file_name in ("", ".", "..") or os.sep in file_name:
        raise AuditError(f"unsafe private file name: {file_name!r}")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(
            file_name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
    except FileExistsError as exc:
        raise AuditError(
            f"private receipt already exists: {display_path}"
        ) from exc
    except OSError as exc:
        raise AuditError(
            f"unable to create private receipt safely: {display_path}"
        ) from exc
    try:
        created = os.fstat(descriptor)
        os.fchmod(descriptor, 0o600)
        created = os.fstat(descriptor)
        if not stat.S_ISREG(created.st_mode) or created.st_nlink != 1:
            raise AuditError(f"unsafe private receipt file: {display_path}")
        _assert_no_extended_acl(descriptor, str(display_path))
        return descriptor, created
    except BaseException:
        os.close(descriptor)
        try:
            current = os.stat(
                file_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if "created" in locals() and (
                current.st_dev == created.st_dev
                and current.st_ino == created.st_ino
            ):
                os.unlink(file_name, dir_fd=parent_descriptor)
        except OSError:
            pass
        raise


def _write_receipt_at(
    parent_descriptor: int,
    file_name: str,
    display_path: Path,
    payload: Mapping[str, Any],
) -> None:
    data = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    descriptor, created = _create_private_file_at(
        parent_descriptor,
        file_name,
        display_path,
    )
    completed = False
    try:
        _write_all(descriptor, data)
        os.fsync(descriptor)
        current = os.stat(
            file_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            current.st_dev != created.st_dev
            or current.st_ino != created.st_ino
            or current.st_nlink != 1
        ):
            raise AuditError(
                f"private receipt changed during write: {display_path}"
            )
        _fsync_directory_descriptor(parent_descriptor)
        completed = True
    finally:
        os.close(descriptor)
        if not completed:
            try:
                current = os.stat(
                    file_name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if (
                    current.st_dev == created.st_dev
                    and current.st_ino == created.st_ino
                ):
                    os.unlink(file_name, dir_fd=parent_descriptor)
                    _fsync_directory_descriptor(parent_descriptor)
            except OSError:
                pass


def _write_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    if not path.is_absolute():
        raise AuditError("receipt path must be absolute")
    if path.name in ("", ".", ".."):
        raise AuditError("receipt path must name a file")
    parent_descriptor = _open_owner_only_directory(
        path.parent,
        create=True,
    )
    try:
        _write_receipt_at(
            parent_descriptor,
            path.name,
            path,
            payload,
        )
    finally:
        os.close(parent_descriptor)


def _redacted_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _redacted_payload(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [_redacted_payload(item) for item in value]
    return value


def _validated_candidate_relative_path(value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise AuditError("candidate relative path must be a non-empty string")
    if "\x00" in value:
        raise AuditError("candidate relative path contains a null byte")
    pure_path = PurePosixPath(value)
    if pure_path.is_absolute() or pure_path.as_posix() != value:
        raise AuditError(f"unsafe candidate relative path: {value!r}")
    if (
        len(pure_path.parts) < 2
        or not pure_path.parts[0].startswith("run-")
        or pure_path.parts[-1] != TARGET_FILE_NAME
        or any(part in ("", ".", "..") for part in pure_path.parts)
    ):
        raise AuditError(f"candidate is outside the quarantine scope: {value!r}")
    return Path(*pure_path.parts)


def _validated_quarantine_entries(
    release_root: Path,
    audit: Mapping[str, Any],
    expected_paths: Sequence[str],
) -> list[tuple[Mapping[str, Any], Path]]:
    if audit.get("contractName") != CONTRACT_NAME:
        raise AuditError("quarantine audit contract does not match")
    if audit.get("releaseRoot") != str(release_root):
        raise AuditError("quarantine audit release root does not match")
    if audit.get("targetFileName") != TARGET_FILE_NAME:
        raise AuditError("quarantine audit target filename does not match")
    if audit.get("status") != "findings":
        raise AuditError("quarantine audit does not contain findings")
    raw_candidates = audit.get("candidates")
    if not isinstance(raw_candidates, list):
        raise AuditError("quarantine audit candidates are malformed")

    entries: list[tuple[Mapping[str, Any], Path]] = []
    seen_paths: set[str] = set()
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, Mapping):
            raise AuditError("quarantine audit candidate is malformed")
        relative_path = _validated_candidate_relative_path(
            raw_candidate.get("relativePath")
        )
        canonical = relative_path.as_posix()
        if canonical in seen_paths:
            raise AuditError(f"duplicate quarantine candidate: {canonical}")
        seen_paths.add(canonical)
        digest = raw_candidate.get("_contentSha256")
        if not isinstance(digest, str) or SHA256_HEX.fullmatch(digest) is None:
            raise AuditError(
                f"quarantine audit digest is missing: {canonical}"
            )
        if raw_candidate.get("bearerMaterialDetected") is not True:
            raise AuditError(
                f"refusing to quarantine non-bearer candidate: {canonical}"
            )
        if raw_candidate.get("gitTracked") is not False:
            raise AuditError(
                f"refusing to quarantine Git-tracked candidate: {canonical}"
            )
        entries.append((raw_candidate, relative_path))

    if audit.get("candidateCount") != len(entries):
        raise AuditError("quarantine audit candidate count does not match")
    if audit.get("bearerMaterialCount") != len(entries):
        raise AuditError("quarantine audit bearer count does not match")
    if audit.get("gitTrackedCount") != 0:
        raise AuditError("quarantine audit includes Git-tracked candidates")
    expected = [
        _validated_candidate_relative_path(path).as_posix()
        for path in expected_paths
    ]
    if len(expected) != len(set(expected)):
        raise AuditError("quarantine targets contain duplicates")
    if sorted(expected) != sorted(seen_paths):
        raise AuditError(
            "current candidates do not exactly match the confirmed targets"
        )

    entries.sort(key=lambda entry: entry[1].as_posix())
    return entries


def _preflight_quarantine_candidate(
    root: Path,
    root_descriptor: int,
    candidate: Mapping[str, Any],
    relative_path: Path,
    root_stat: os.stat_result,
) -> dict[str, Any]:
    parent_descriptor = _open_relative_directory(
        root_descriptor,
        relative_path.parts[:-1],
        display_root=root,
        create=False,
        owner_only=False,
        safe_mutation_ancestry=True,
    )
    source_descriptor: int | None = None
    try:
        content, source_stat, source_descriptor = (
            _read_stable_regular_file_at(
                parent_descriptor,
                relative_path.name,
                root / relative_path,
                retain_descriptor=True,
            )
        )
        assert source_descriptor is not None
        if source_stat.st_uid != os.geteuid():
            raise AuditError(
                f"candidate is not owned by the current user: "
                f"{relative_path.as_posix()}"
            )
        if stat.S_IMODE(source_stat.st_mode) & 0o022:
            raise AuditError(
                f"candidate is writable by other principals: "
                f"{relative_path.as_posix()}"
            )
        if source_stat.st_dev != root_stat.st_dev:
            raise AuditError(
                f"candidate quarantine crosses filesystems: "
                f"{relative_path.as_posix()}"
            )
        _assert_no_extended_acl(
            source_descriptor,
            str(root / relative_path),
        )
        if hashlib.sha256(content).hexdigest() != candidate["_contentSha256"]:
            raise AuditError(
                f"candidate changed after audit: "
                f"{relative_path.as_posix()}"
            )
        if not _contains_bearer_material(content):
            raise AuditError(
                f"candidate no longer contains bearer material: "
                f"{relative_path.as_posix()}"
            )
        tracked, _ = _git_tracking(root / relative_path)
        if tracked:
            raise AuditError(
                f"candidate became Git-tracked after audit: "
                f"{relative_path.as_posix()}"
            )
        return {
            "candidate": candidate,
            "relativePath": relative_path,
            "parentDescriptor": parent_descriptor,
            "sourceDescriptor": source_descriptor,
            "sourceStat": source_stat,
        }
    except BaseException:
        if source_descriptor is not None:
            os.close(source_descriptor)
        os.close(parent_descriptor)
        raise


def _append_journal_event(
    descriptor: int,
    payload: Mapping[str, Any],
) -> None:
    data = (
        json.dumps(
            _redacted_payload(payload),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    _write_all(descriptor, data)
    os.fsync(descriptor)


def _restore_unexpected_rename(
    source_parent: int,
    destination_parent: int,
    file_name: str,
    destination_stat: os.stat_result,
) -> str:
    disposition = "replacement remains in private quarantine"
    try:
        os.link(
            file_name,
            file_name,
            src_dir_fd=destination_parent,
            dst_dir_fd=source_parent,
            follow_symlinks=False,
        )
        disposition = (
            "replacement may exist at source and in private quarantine"
        )
        source_stat = os.stat(
            file_name,
            dir_fd=source_parent,
            follow_symlinks=False,
        )
        if (
            source_stat.st_dev != destination_stat.st_dev
            or source_stat.st_ino != destination_stat.st_ino
            or source_stat.st_nlink != 2
        ):
            return disposition
        os.unlink(file_name, dir_fd=destination_parent)
        disposition = "replacement restored to source"
        _fsync_directory_descriptor(source_parent)
        _fsync_directory_descriptor(destination_parent)
    except OSError:
        pass
    return disposition


def _move_preflighted_candidate(
    root: Path,
    quarantine_root: Path,
    quarantine_descriptor: int,
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    relative_path = preflight["relativePath"]
    assert isinstance(relative_path, Path)
    source_parent = preflight["parentDescriptor"]
    source_descriptor = preflight["sourceDescriptor"]
    source_stat = preflight["sourceStat"]
    assert isinstance(source_parent, int)
    assert isinstance(source_descriptor, int)
    assert isinstance(source_stat, os.stat_result)
    destination_parent = _open_relative_directory(
        quarantine_descriptor,
        relative_path.parts[:-1],
        display_root=quarantine_root,
        create=True,
        owner_only=True,
        safe_mutation_ancestry=True,
    )
    try:
        tracked, _ = _git_tracking(root / relative_path)
        if tracked:
            raise AuditError(
                f"candidate became Git-tracked before quarantine: "
                f"{relative_path.as_posix()}"
            )
        if os.fstat(destination_parent).st_dev != source_stat.st_dev:
            raise AuditError(
                f"candidate quarantine crosses filesystems: "
                f"{relative_path.as_posix()}"
            )
        try:
            os.stat(
                relative_path.name,
                dir_fd=destination_parent,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise AuditError(
                f"quarantine destination already exists: "
                f"{relative_path.as_posix()}"
            )

        current_source = os.stat(
            relative_path.name,
            dir_fd=source_parent,
            follow_symlinks=False,
        )
        if (
            current_source.st_dev != source_stat.st_dev
            or current_source.st_ino != source_stat.st_ino
            or current_source.st_nlink != 1
            or os.fstat(source_descriptor).st_nlink != 1
        ):
            raise AuditError(
                f"candidate path changed before quarantine: "
                f"{relative_path.as_posix()}"
            )

        os.rename(
            relative_path.name,
            relative_path.name,
            src_dir_fd=source_parent,
            dst_dir_fd=destination_parent,
        )
        destination_stat = os.stat(
            relative_path.name,
            dir_fd=destination_parent,
            follow_symlinks=False,
        )
        moved_source = os.fstat(source_descriptor)
        if (
            destination_stat.st_dev != source_stat.st_dev
            or destination_stat.st_ino != source_stat.st_ino
            or moved_source.st_dev != source_stat.st_dev
            or moved_source.st_ino != source_stat.st_ino
            or moved_source.st_nlink != 1
        ):
            disposition = _restore_unexpected_rename(
                source_parent,
                destination_parent,
                relative_path.name,
                destination_stat,
            )
            raise AuditError(
                f"candidate identity changed during quarantine: "
                f"{relative_path.as_posix()} ({disposition})"
            )

        os.fchmod(source_descriptor, 0o600)
        os.fsync(source_descriptor)
        final_stat = os.stat(
            relative_path.name,
            dir_fd=destination_parent,
            follow_symlinks=False,
        )
        if (
            final_stat.st_dev != source_stat.st_dev
            or final_stat.st_ino != source_stat.st_ino
            or final_stat.st_nlink != 1
            or stat.S_IMODE(final_stat.st_mode) != 0o600
        ):
            raise AuditError(
                f"candidate changed after quarantine: "
                f"{relative_path.as_posix()}"
            )
        _fsync_directory_descriptor(destination_parent)
        _fsync_directory_descriptor(source_parent)
    finally:
        os.close(destination_parent)

    destination = quarantine_root / relative_path
    return {
        **preflight["candidate"],
        "quarantineRelativePath": destination.relative_to(root).as_posix(),
    }


def quarantine_candidates(
    release_root: Path,
    audit: Mapping[str, Any],
    expected_paths: Sequence[str],
) -> dict[str, Any]:
    root = _validate_release_root(release_root)
    entries = _validated_quarantine_entries(
        root,
        audit,
        expected_paths,
    )
    root_descriptor = _open_absolute_directory_no_symlinks(root)
    quarantine_parent: int | None = None
    quarantine_descriptor: int | None = None
    journal_descriptor: int | None = None
    preflighted: list[dict[str, Any]] = []
    try:
        root_stat = os.fstat(root_descriptor)
        _assert_directory_safety(
            root_descriptor,
            str(root),
            owner_only=False,
        )
        for candidate, relative_path in entries:
            preflighted.append(
                _preflight_quarantine_candidate(
                    root,
                    root_descriptor,
                    candidate,
                    relative_path,
                    root_stat,
                )
            )
        run_id = (
            dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid.uuid4().hex
        )
        quarantine_root = root / QUARANTINE_DIRECTORY_NAME / run_id
        quarantine_parent = _open_relative_directory(
            root_descriptor,
            (QUARANTINE_DIRECTORY_NAME,),
            display_root=root,
            create=True,
            owner_only=True,
            safe_mutation_ancestry=True,
        )
        quarantine_descriptor = _open_relative_directory(
            quarantine_parent,
            (run_id,),
            display_root=root / QUARANTINE_DIRECTORY_NAME,
            create=True,
            owner_only=True,
            safe_mutation_ancestry=True,
        )
        if os.fstat(quarantine_descriptor).st_dev != root_stat.st_dev:
            raise AuditError("quarantine must be on the same filesystem")
        _fsync_directory_descriptor(quarantine_parent)

        journal_path = quarantine_root / JOURNAL_FILE_NAME
        journal_descriptor, _ = _create_private_file_at(
            quarantine_descriptor,
            JOURNAL_FILE_NAME,
            journal_path,
        )
        _append_journal_event(
            journal_descriptor,
            {
                "contractName": CONTRACT_NAME,
                "event": "started",
                "at": _utc_now(),
                "releaseRoot": str(root),
                "quarantineRunRelativePath": quarantine_root.relative_to(
                    root
                ).as_posix(),
                "candidateRelativePaths": [
                    preflight["relativePath"].as_posix()
                    for preflight in preflighted
                ],
            },
        )
        _fsync_directory_descriptor(quarantine_descriptor)
        moved: list[dict[str, Any]] = []
        try:
            for preflight in preflighted:
                relative_path = preflight["relativePath"]
                _append_journal_event(
                    journal_descriptor,
                    {
                        "event": "move-planned",
                        "at": _utc_now(),
                        "relativePath": relative_path.as_posix(),
                    },
                )
                moved_candidate = _move_preflighted_candidate(
                    root,
                    quarantine_root,
                    quarantine_descriptor,
                    preflight,
                )
                moved.append(moved_candidate)
                _append_journal_event(
                    journal_descriptor,
                    {
                        "event": "moved",
                        "at": _utc_now(),
                        "relativePath": relative_path.as_posix(),
                        "quarantineRelativePath": moved_candidate[
                            "quarantineRelativePath"
                        ],
                    },
                )
            result = {
                **audit,
                "completedAt": _utc_now(),
                "status": "quarantined",
                "quarantineRunRelativePath": quarantine_root.relative_to(
                    root
                ).as_posix(),
                "quarantinedCount": len(moved),
                "candidates": moved,
                "rotationRequiredBeforeDeletion": bool(moved),
                "journalRelativePath": journal_path.relative_to(
                    root
                ).as_posix(),
            }
            receipt_path = quarantine_root / RECEIPT_FILE_NAME
            result["receiptRelativePath"] = receipt_path.relative_to(
                root
            ).as_posix()
            _write_receipt_at(
                quarantine_descriptor,
                RECEIPT_FILE_NAME,
                receipt_path,
                _redacted_payload(result),
            )
            _append_journal_event(
                journal_descriptor,
                {
                    "event": "completed",
                    "at": _utc_now(),
                    "quarantinedCount": len(moved),
                    "receiptRelativePath": result["receiptRelativePath"],
                },
            )
            return result
        except BaseException as exc:
            try:
                _append_journal_event(
                    journal_descriptor,
                    {
                        "event": "failed",
                        "at": _utc_now(),
                        "movedCount": len(moved),
                        "error": str(exc),
                    },
                )
            except (AuditError, OSError):
                pass
            raise AuditError(
                "quarantine did not complete; inspect the private journal at "
                f"{journal_path.relative_to(root).as_posix()}"
            ) from exc
    finally:
        for preflight in preflighted:
            os.close(preflight["sourceDescriptor"])
            os.close(preflight["parentDescriptor"])
        if journal_descriptor is not None:
            os.close(journal_descriptor)
        if quarantine_descriptor is not None:
            os.close(quarantine_descriptor)
        if quarantine_parent is not None:
            os.close(quarantine_parent)
        os.close(root_descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-root",
        type=Path,
        required=True,
        help="Exact macOS release workspace root.",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help=(
            "Audit-only absolute owner-only path for a redacted receipt; "
            "quarantine always writes its own internal receipt."
        ),
    )
    parser.add_argument(
        "--quarantine",
        action="store_true",
        help="Move findings to an owner-only same-volume quarantine.",
    )
    parser.add_argument(
        "--confirm",
        help=f"Required with --quarantine: {QUARANTINE_CONFIRMATION}",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="RUN_RELATIVE_PATH",
        help="Repeat for every candidate reported by the preceding audit.",
    )
    return parser


def run(arguments: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    try:
        if options.quarantine and options.confirm != QUARANTINE_CONFIRMATION:
            raise AuditError(
                f"--quarantine requires --confirm "
                f"{QUARANTINE_CONFIRMATION}"
            )
        if not options.quarantine and options.confirm:
            raise AuditError("--confirm is only valid with --quarantine")
        if options.quarantine and not options.target:
            raise AuditError("--quarantine requires at least one --target")
        if not options.quarantine and options.target:
            raise AuditError("--target is only valid with --quarantine")
        if options.quarantine and options.receipt is not None:
            raise AuditError(
                "--receipt is audit-only; quarantine writes a private "
                "internal receipt"
            )
        audit = audit_release_root(options.release_root)
        result = (
            quarantine_candidates(
                options.release_root,
                audit,
                options.target,
            )
            if options.quarantine
            else audit
        )
        redacted_result = _redacted_payload(result)
        if options.receipt is not None:
            _write_receipt(options.receipt, redacted_result)
        print(
            json.dumps(
                redacted_result,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except (AuditError, OSError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {
                    "contractName": CONTRACT_NAME,
                    "generatedAt": _utc_now(),
                    "status": "error",
                    "error": str(exc),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
