#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_WORKSPACE_ROOT = Path("/docker/chummercomplete")
DEFAULT_SOURCE_ROOT = (
    DEFAULT_WORKSPACE_ROOT / "chummer-hub-registry" / ".codex-studio" / "published"
)
DEFAULT_NAMES = (
    "RELEASE_CHANNEL.generated.json",
    "releases.json",
)
LAYOUT_MARKER = ".release-shelf-layout-v1"
CURRENT_POINTER = "current.json"


class LegacyReleaseShelfTargetError(RuntimeError):
    pass


def assert_legacy_release_shelf_target(target_root: Path) -> None:
    marker = target_root / LAYOUT_MARKER
    pointer = target_root / CURRENT_POINTER
    if marker.exists() or pointer.exists():
        raise LegacyReleaseShelfTargetError(
            "refusing legacy manifest mirror mutation after release shelf layout-v1 "
            f"activation: {target_root}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync authoritative registry manifest mirrors into workspace portal artifact roots."
    )
    parser.add_argument(
        "--workspace-root",
        default=str(DEFAULT_WORKSPACE_ROOT),
        help="Workspace root containing chummer.run-services, chummer6-ui, and chummer-presentation.",
    )
    parser.add_argument(
        "--source-root",
        default=str(DEFAULT_SOURCE_ROOT),
        help="Authoritative root containing the manifest files to mirror.",
    )
    parser.add_argument(
        "--name",
        action="append",
        dest="names",
        help="Manifest file name to sync. Repeat to sync multiple names.",
    )
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Create expected mirror targets even when they do not already exist.",
    )
    return parser.parse_args(argv)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def display_path(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root.resolve()))
    except ValueError:
        return str(path.resolve())


def mirror_target_paths(workspace_root: Path, name: str) -> list[Path]:
    candidates = (
        workspace_root / "chummer.run-services" / "Chummer.Portal" / "downloads" / name,
        workspace_root / "chummer-presentation" / "Chummer.Portal" / "downloads" / name,
        workspace_root / "chummer6-ui" / "Chummer.Portal" / "downloads" / name,
        workspace_root / "chummer-presentation" / "Docker" / "Downloads" / name,
        workspace_root / "chummer6-ui" / "Docker" / "Downloads" / name,
        workspace_root / "chummer-presentation" / ".codex-studio" / "published" / "portal" / name,
        workspace_root / "chummer6-ui" / ".codex-studio" / "published" / "portal" / name,
    )
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def sync_single_manifest(
    source_root: Path,
    workspace_root: Path,
    *,
    name: str,
    create_missing: bool = False,
) -> dict[str, Any]:
    source_path = source_root / name
    result: dict[str, Any] = {
        "name": name,
        "source": display_path(source_path, workspace_root),
        "source_exists": source_path.is_file(),
        "status": "missing_source",
        "updated_targets": [],
        "unchanged_targets": [],
        "skipped_missing_targets": [],
    }
    if not source_path.is_file():
        return result

    source_bytes = source_path.read_bytes()
    result["source_sha256"] = sha256_bytes(source_bytes)

    for target_path in mirror_target_paths(workspace_root, name):
        target_display = display_path(target_path, workspace_root)
        if not target_path.exists() and not create_missing:
            result["skipped_missing_targets"].append(target_display)
            continue

        current_bytes = target_path.read_bytes() if target_path.is_file() else None
        if current_bytes == source_bytes:
            result["unchanged_targets"].append(target_display)
            continue

        write_bytes_atomic(target_path, source_bytes)
        result["updated_targets"].append(target_display)

    result["status"] = "synced"
    return result


def sync_workspace_portal_manifest_mirrors(
    source_root: Path,
    workspace_root: Path,
    *,
    names: list[str],
    create_missing: bool = False,
) -> dict[str, Any]:
    assert_legacy_release_shelf_target(source_root)
    target_roots = {
        target.parent
        for name in names
        for target in mirror_target_paths(workspace_root, name)
    }
    # Preflight every target before the first write so one marked mirror cannot
    # leave the workspace with a partially synchronized legacy projection.
    for target_root in sorted(target_roots):
        assert_legacy_release_shelf_target(target_root)
    file_results = [
        sync_single_manifest(
            source_root,
            workspace_root,
            name=name,
            create_missing=create_missing,
        )
        for name in names
    ]
    missing_sources = [
        item["name"] for item in file_results if item.get("status") == "missing_source"
    ]
    return {
        "status": "fail" if missing_sources else "pass",
        "workspace_root": str(workspace_root.resolve()),
        "source_root": str(source_root.resolve()),
        "create_missing": create_missing,
        "files": file_results,
        "missing_sources": missing_sources,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace_root = Path(args.workspace_root).resolve()
    source_root = Path(args.source_root).resolve()
    names = list(dict.fromkeys(args.names or list(DEFAULT_NAMES)))
    summary = sync_workspace_portal_manifest_mirrors(
        source_root,
        workspace_root,
        names=names,
        create_missing=args.create_missing,
    )
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
