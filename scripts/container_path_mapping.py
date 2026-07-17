from __future__ import annotations

import json
import subprocess
from pathlib import Path


def normalize_path(path: str | Path) -> str:
    return str(Path(str(path or "")).expanduser().resolve(strict=False))


def docker_container_mount_mappings(container_name: str, *, timeout_seconds: float = 15.0) -> list[tuple[str, str]]:
    try:
        completed = subprocess.run(
            ["docker", "inspect", container_name, "--format", "{{json .Mounts}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        mounts = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []

    pairs: list[tuple[str, str]] = []
    for mount in mounts if isinstance(mounts, list) else []:
        if not isinstance(mount, dict):
            continue
        destination = str(mount.get("Destination") or "").strip()
        source = str(mount.get("Source") or "").strip()
        if not destination or not source:
            continue
        pairs.append((normalize_path(destination), normalize_path(source)))
    return sorted(pairs, key=lambda item: len(item[0]), reverse=True)


def resolve_host_path(container_path: str | Path, mappings: list[tuple[str, str]]) -> str:
    normalized = normalize_path(container_path)
    for container_prefix, host_prefix in mappings:
        if normalized == container_prefix:
            return host_prefix
        prefix = f"{container_prefix}/"
        if normalized.startswith(prefix):
            suffix = normalized[len(prefix) :]
            return normalize_path(Path(host_prefix) / suffix)
    return normalized
