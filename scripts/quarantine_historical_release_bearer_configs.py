#!/usr/bin/env python3
"""Audit or quarantine historical macOS release bearer curl configs.

The release publisher no longer persists curl authentication configuration.
This utility exists only to remove files created by older release workspaces.
It never emits file contents or bearer values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_NAME = "chummer.historical-release-bearer-config-quarantine/v1"
TARGET_FILE_NAME = "upload-auth.curl"
QUARANTINE_DIRECTORY_NAME = ".credential-quarantine"
QUARANTINE_CONFIRMATION = "QUARANTINE_HISTORICAL_RELEASE_BEARER_CONFIGS"
DEFAULT_RELEASE_ROOT = Path("/Users/tibor/work/chummer-release")
MAX_CREDENTIAL_FILE_BYTES = 1024 * 1024
BEARER_MATERIAL = re.compile(
    rb"(?im)(?:authorization\s*:\s*bearer|oauth2-bearer\s*=)"
)


class AuditError(RuntimeError):
    """The requested audit could not be performed safely."""


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
    for run_root in _iter_run_directories(release_root):
        for current_root, directory_names, file_names in os.walk(
            run_root,
            topdown=True,
            followlinks=False,
        ):
            safe_directories: list[str] = []
            for directory_name in sorted(directory_names):
                directory_path = Path(current_root) / directory_name
                try:
                    directory_stat = os.lstat(directory_path)
                except FileNotFoundError:
                    continue
                if stat.S_ISDIR(directory_stat.st_mode):
                    safe_directories.append(directory_name)
            directory_names[:] = safe_directories
            if TARGET_FILE_NAME in file_names:
                yield Path(current_root) / TARGET_FILE_NAME


def _read_stable_regular_file(path: Path) -> tuple[bytes, os.stat_result]:
    try:
        initial = os.lstat(path)
    except FileNotFoundError as exc:
        raise AuditError(f"candidate disappeared before audit: {path}") from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise AuditError(f"candidate is not a regular non-symlink file: {path}")
    if initial.st_nlink != 1:
        raise AuditError(f"candidate has multiple hard links: {path}")
    if initial.st_size > MAX_CREDENTIAL_FILE_BYTES:
        raise AuditError(f"candidate exceeds the safe audit size limit: {path}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AuditError(f"unable to open candidate safely: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != initial.st_dev
            or opened.st_ino != initial.st_ino
            or opened.st_mode != initial.st_mode
            or opened.st_size != initial.st_size
        ):
            raise AuditError(f"candidate changed while it was opened: {path}")
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
                f"candidate exceeds the safe audit size limit: {path}"
            )
        final = os.fstat(descriptor)
        if (
            final.st_dev != opened.st_dev
            or final.st_ino != opened.st_ino
            or final.st_mode != opened.st_mode
            or final.st_size != opened.st_size
            or len(content) != opened.st_size
        ):
            raise AuditError(f"candidate changed during audit: {path}")
        return content, final
    finally:
        os.close(descriptor)


def _git_tracking(path: Path) -> tuple[bool, str | None]:
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
    )
    if completed.returncode != 0:
        return False, None
    git_root = Path(completed.stdout.strip())
    try:
        relative_path = path.relative_to(git_root)
    except ValueError:
        return False, None
    tracked = subprocess.run(
        (
            "git",
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
    )
    return tracked.returncode == 0, str(git_root)


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
        "bearerMaterialDetected": bool(BEARER_MATERIAL.search(content)),
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


def _ensure_owner_only_directory(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while True:
        try:
            current_stat = os.lstat(current)
        except FileNotFoundError:
            missing.append(current)
            if current.parent == current:
                raise AuditError(
                    f"unable to establish directory ancestry: {path}"
                )
            current = current.parent
            continue
        if stat.S_ISLNK(current_stat.st_mode) or not stat.S_ISDIR(
            current_stat.st_mode
        ):
            raise AuditError(f"unsafe directory ancestry: {current}")
        break

    for directory in reversed(missing):
        os.mkdir(directory, mode=0o700)
        created_stat = os.lstat(directory)
        if stat.S_ISLNK(created_stat.st_mode) or not stat.S_ISDIR(
            created_stat.st_mode
        ):
            raise AuditError(f"unsafe created directory: {directory}")
        os.chmod(directory, 0o700)

    path_stat = os.lstat(path)
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
        raise AuditError(f"unsafe directory: {path}")
    os.chmod(path, 0o700)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_CLOEXEC", 0
    )
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    if not path.is_absolute():
        raise AuditError("receipt path must be absolute")
    _ensure_owner_only_directory(path.parent)
    data = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = -1
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


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


def quarantine_candidates(
    release_root: Path,
    audit: Mapping[str, Any],
) -> dict[str, Any]:
    root = _validate_release_root(release_root)
    run_id = (
        dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex
    )
    quarantine_root = root / QUARANTINE_DIRECTORY_NAME / run_id
    _ensure_owner_only_directory(quarantine_root)
    if os.lstat(quarantine_root).st_dev != os.lstat(root).st_dev:
        raise AuditError("quarantine must be on the same filesystem")

    moved: list[dict[str, Any]] = []
    for candidate in audit["candidates"]:
        relative_path = Path(str(candidate["relativePath"]))
        source = root / relative_path
        content, source_stat = _read_stable_regular_file(source)
        if (
            hashlib.sha256(content).hexdigest()
            != candidate["_contentSha256"]
        ):
            raise AuditError(
                f"candidate changed after audit: {relative_path.as_posix()}"
            )
        destination = quarantine_root / relative_path
        _ensure_owner_only_directory(destination.parent)
        if os.lstat(destination.parent).st_dev != source_stat.st_dev:
            raise AuditError(
                f"candidate quarantine crosses filesystems: "
                f"{relative_path.as_posix()}"
            )
        if destination.exists() or destination.is_symlink():
            raise AuditError(
                f"quarantine destination already exists: "
                f"{relative_path.as_posix()}"
            )
        os.rename(source, destination)
        os.chmod(destination, 0o600)
        _fsync_directory(source.parent)
        _fsync_directory(destination.parent)
        moved.append(
            {
                **candidate,
                "quarantineRelativePath": destination.relative_to(
                    root
                ).as_posix(),
            }
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
    }
    receipt_path = quarantine_root / "QUARANTINE_RECEIPT.generated.json"
    result["receiptRelativePath"] = receipt_path.relative_to(root).as_posix()
    _write_receipt(receipt_path, _redacted_payload(result))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-root",
        type=Path,
        default=DEFAULT_RELEASE_ROOT,
        help="Exact macOS release workspace root.",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Optional absolute owner-only path for a redacted audit receipt.",
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
        audit = audit_release_root(options.release_root)
        result = (
            quarantine_candidates(options.release_root, audit)
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
