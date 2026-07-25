#!/usr/bin/env python3
"""Verify and sync a legacy compatibility mirror from the active release generation.

The source is always resolved through ``current.json`` and validated with the shared
release-shelf contract. The target remains non-authoritative: this script refuses
layout-v1 or server-writer-policy targets and never writes the source shelf.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import release_shelf_generation as shelf


DEFAULT_SOURCE_ROOT = Path(
    "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads"
)
DEFAULT_TARGET_ROOT = Path(
    "/docker/chummercomplete/chummer-hub-registry/.codex-studio/published"
)
MANAGED_DIRECTORIES = (
    "files",
    "startup-smoke",
    "signing",
    "proof",
    "release-evidence",
)
MANAGED_FILES = (
    shelf.CANONICAL_MANIFEST,
    shelf.COMPATIBILITY_MANIFEST,
    "aur-packages.json",
)
MANAGED_NAMES = MANAGED_DIRECTORIES + MANAGED_FILES
RECEIPT_SCHEMA = "chummer.release-compatibility-mirror-sync/v1"


class CompatibilityMirrorSyncError(RuntimeError):
    """Raised when a compatibility mirror cannot be verified or repaired safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_regular_directory(path: Path, label: str) -> None:
    if not path.is_dir() or path.is_symlink():
        raise CompatibilityMirrorSyncError(f"{label} must be a regular directory")


def ensure_regular_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise CompatibilityMirrorSyncError(f"{label} must be a regular file")


def assert_no_links(root: Path, label: str) -> None:
    ensure_regular_directory(root, label)
    for path in root.rglob("*"):
        if path.is_symlink():
            raise CompatibilityMirrorSyncError(f"{label} cannot contain links: {path}")
        if not path.is_file() and not path.is_dir():
            raise CompatibilityMirrorSyncError(
                f"{label} contains an unsupported filesystem entry: {path}"
            )


def assert_legacy_target(target_root: Path) -> None:
    ensure_regular_directory(target_root, "compatibility mirror target")
    for forbidden in (
        shelf.LAYOUT_MARKER,
        shelf.CURRENT_POINTER,
        shelf.WRITER_POLICY,
    ):
        path = target_root / forbidden
        if path.exists() or path.is_symlink():
            raise CompatibilityMirrorSyncError(
                "refusing compatibility mirror mutation because the target carries "
                f"release authority metadata: {forbidden}"
            )


def canonical_target_entry(target_root: Path, name: str) -> Path | None:
    matches = [
        path
        for path in target_root.iterdir()
        if path.name.casefold() == name.casefold()
    ]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name:
        raise CompatibilityMirrorSyncError(
            f"compatibility mirror entry has ambiguous or noncanonical casing: {name}"
        )
    path = matches[0]
    if path.is_symlink():
        raise CompatibilityMirrorSyncError(
            f"compatibility mirror entry cannot be a link: {name}"
        )
    expected_directory = name in MANAGED_DIRECTORIES
    if expected_directory != path.is_dir():
        raise CompatibilityMirrorSyncError(
            f"compatibility mirror entry has the wrong filesystem type: {name}"
        )
    if expected_directory:
        assert_no_links(path, f"compatibility mirror {name}")
    elif not path.is_file():
        raise CompatibilityMirrorSyncError(
            f"compatibility mirror entry must be a regular file: {name}"
        )
    return path


def managed_snapshot(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in MANAGED_NAMES:
        path = root / name
        if path.is_dir() and not path.is_symlink():
            assert_no_links(path, f"managed {name} directory")
            for file_path in sorted(
                (item for item in path.rglob("*") if item.is_file()),
                key=lambda item: item.as_posix(),
            ):
                relative = file_path.relative_to(root).as_posix()
                folded = relative.casefold()
                if any(existing.casefold() == folded for existing in result):
                    raise CompatibilityMirrorSyncError(
                        f"managed mirror paths collide by case: {relative}"
                    )
                result[relative] = {
                    "sha256": sha256_file(file_path),
                    "sizeBytes": file_path.stat().st_size,
                }
        elif path.is_file() and not path.is_symlink():
            result[name] = {
                "sha256": sha256_file(path),
                "sizeBytes": path.stat().st_size,
            }
        elif path.exists() or path.is_symlink():
            raise CompatibilityMirrorSyncError(
                f"managed mirror entry is not regular: {name}"
            )
    return result


def aggregate_snapshot(snapshot: dict[str, dict[str, Any]]) -> str:
    encoded = json.dumps(
        snapshot,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def copy_managed_source(source_root: Path, staged_root: Path) -> None:
    staged_root.mkdir()
    for name in MANAGED_DIRECTORIES:
        source = source_root / name
        if not source.exists():
            continue
        assert_no_links(source, f"active generation {name}")
        shutil.copytree(source, staged_root / name, symlinks=False)
    for name in MANAGED_FILES:
        source = source_root / name
        if not source.exists():
            if name in (shelf.CANONICAL_MANIFEST, shelf.COMPATIBILITY_MANIFEST):
                raise CompatibilityMirrorSyncError(
                    f"active generation is missing required manifest: {name}"
                )
            continue
        ensure_regular_file(source, f"active generation {name}")
        shutil.copy2(source, staged_root / name)


def remove_regular_entry(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink():
        raise CompatibilityMirrorSyncError(
            f"refusing to remove linked compatibility mirror entry: {path.name}"
        )
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()
    else:
        raise CompatibilityMirrorSyncError(
            f"refusing to remove unsupported compatibility mirror entry: {path.name}"
        )


def move_regular_entry(source: Path, destination: Path) -> None:
    if source.is_symlink() or (not source.is_file() and not source.is_dir()):
        raise CompatibilityMirrorSyncError(
            f"compatibility mirror transaction source is not regular: {source}"
        )
    source.replace(destination)


@contextmanager
def source_promotion_lock(source_root: Path) -> Iterator[None]:
    lock_path = source_root / shelf.PROMOTION_LOCK
    ensure_regular_file(lock_path, "release shelf promotion lock")
    with lock_path.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def sync_active_release_compatibility_mirror(
    source_root: Path,
    target_root: Path,
    *,
    apply: bool,
) -> dict[str, Any]:
    source_root = source_root.resolve(strict=True)
    target_root = target_root.resolve(strict=True)
    ensure_regular_directory(source_root, "release shelf source")
    assert_legacy_target(target_root)

    with source_promotion_lock(source_root):
        pointer_path = source_root / shelf.CURRENT_POINTER
        ensure_regular_file(pointer_path, "release shelf current pointer")
        pointer_before = pointer_path.read_bytes()
        mode, generation_root, pointer = shelf.resolve_shelf_root(source_root)
        if mode != "generation" or pointer is None:
            raise CompatibilityMirrorSyncError(
                "compatibility mirror sync requires an active layout-v1 generation"
            )

        transaction_root = target_root / (
            f".release-compatibility-mirror-sync-{uuid.uuid4().hex}"
        )
        staged_root = transaction_root / "staged"
        backup_root = transaction_root / "backup"
        backed_up: list[str] = []
        installed: list[str] = []
        committed = False
        try:
            transaction_root.mkdir()
            backup_root.mkdir()
            copy_managed_source(generation_root, staged_root)
            expected = managed_snapshot(generation_root)
            staged = managed_snapshot(staged_root)
            if staged != expected:
                raise CompatibilityMirrorSyncError(
                    "staged mirror bytes do not match the active immutable generation"
                )
            if pointer_path.read_bytes() != pointer_before:
                raise CompatibilityMirrorSyncError(
                    "release shelf pointer changed while the mirror was staged"
                )

            current = managed_snapshot(target_root)
            drift = current != expected
            if apply and drift:
                existing: dict[str, Path] = {}
                for name in MANAGED_NAMES:
                    path = canonical_target_entry(target_root, name)
                    if path is not None:
                        existing[name] = path

                for name, path in existing.items():
                    move_regular_entry(path, backup_root / name)
                    backed_up.append(name)
                for name in MANAGED_NAMES:
                    path = staged_root / name
                    if path.exists():
                        move_regular_entry(path, target_root / name)
                        installed.append(name)

                if managed_snapshot(target_root) != expected:
                    raise CompatibilityMirrorSyncError(
                        "compatibility mirror verification failed after replacement"
                    )
                if pointer_path.read_bytes() != pointer_before:
                    raise CompatibilityMirrorSyncError(
                        "release shelf pointer changed while the mirror was replaced"
                    )
                committed = True
            elif apply:
                committed = True

            result = {
                "schemaVersion": RECEIPT_SCHEMA,
                "status": "pass" if apply or not drift else "drift",
                "mode": "apply" if apply else "check",
                "sourceRoot": str(source_root),
                "targetRoot": str(target_root),
                "generationId": pointer["generationId"],
                "releaseVersion": pointer["releaseVersion"],
                "channel": pointer["channel"],
                "pointerSha256": hashlib.sha256(pointer_before).hexdigest(),
                "inventoryDigest": pointer["inventoryDigest"],
                "managedFileCount": len(expected),
                "managedAggregateSha256": aggregate_snapshot(expected),
                "changed": bool(apply and drift),
                "inSync": not drift or apply,
                "checkedAtUtc": utc_now(),
            }
            return result
        except Exception:
            if apply and not committed:
                rollback_error: Exception | None = None
                try:
                    for name in installed:
                        remove_regular_entry(target_root / name)
                    for name in backed_up:
                        move_regular_entry(backup_root / name, target_root / name)
                except Exception as exc:  # pragma: no cover - catastrophic filesystem failure
                    rollback_error = exc
                if rollback_error is not None:
                    raise CompatibilityMirrorSyncError(
                        "compatibility mirror sync failed and prior mirror restoration failed"
                    ) from rollback_error
            raise
        finally:
            shutil.rmtree(transaction_root, ignore_errors=committed)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify or repair a non-authoritative compatibility mirror from the "
            "currently active immutable release generation."
        )
    )
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply a verified transactional repair. Without this flag, only check.",
    )
    parser.add_argument(
        "--receipt",
        help="Optional path for the non-secret JSON result receipt.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = sync_active_release_compatibility_mirror(
            Path(args.source_root),
            Path(args.target_root),
            apply=args.apply,
        )
    except (CompatibilityMirrorSyncError, shelf.ReleaseShelfError, OSError) as exc:
        failure = {
            "schemaVersion": RECEIPT_SCHEMA,
            "status": "fail",
            "mode": "apply" if args.apply else "check",
            "error": str(exc),
            "checkedAtUtc": utc_now(),
        }
        json.dump(failure, sys.stderr, indent=2)
        sys.stderr.write("\n")
        return 1

    if args.receipt:
        write_json_atomic(Path(args.receipt), result)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
