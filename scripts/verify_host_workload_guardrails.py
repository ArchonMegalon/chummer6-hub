#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from container_path_mapping import docker_container_mount_mappings, resolve_host_path
from host_workload_guardrails_common import (
    ASSET_MAP,
    CONTAINER_ALIAS_PATHS,
    CONTAINER_PROBES,
    EXPECTED_SNIPPETS,
    HOST_ALIAS_PATHS,
    REPO_ROOT,
    WATCHDOG_TIMERS,
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False, timeout=timeout)


def systemctl_show(unit: str) -> dict[str, str]:
    result = run(
        [
            "systemctl",
            "show",
            unit,
            "--property=ActiveState,SubState,Result,NextElapseUSecRealtime,LastTriggerUSec",
        ],
        timeout=15,
    )
    props: dict[str, str] = {"command_status": str(result.returncode)}
    if result.returncode != 0:
        props["stderr"] = result.stderr.strip()
        return props
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key] = value
    return props


def verify_repo_assets() -> tuple[list[dict[str, object]], list[str]]:
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for repo_rel, _host_path in ASSET_MAP:
        repo_path = REPO_ROOT / repo_rel
        asset_result: dict[str, object] = {
            "repo_path": repo_rel,
            "exists": repo_path.exists(),
        }
        if not repo_path.exists():
            failures.append(f"missing repo asset: {repo_rel}")
            results.append(asset_result)
            continue
        text = read_text(repo_path)
        asset_result["sha256"] = sha256_text(text)
        snippets = EXPECTED_SNIPPETS.get(repo_rel, [])
        missing_snippets = [snippet for snippet in snippets if snippet not in text]
        asset_result["expected_snippets_ok"] = not missing_snippets
        if missing_snippets:
            asset_result["missing_snippets"] = missing_snippets
            failures.append(f"repo asset drift: {repo_rel}")
        results.append(asset_result)
    return results, failures


def verify_live_assets() -> tuple[list[dict[str, object]], list[str]]:
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for repo_rel, host_path_str in ASSET_MAP:
        repo_path = REPO_ROOT / repo_rel
        host_path = Path(host_path_str)
        asset_result: dict[str, object] = {
            "repo_path": repo_rel,
            "host_path": host_path_str,
            "host_exists": host_path.exists(),
        }
        if not host_path.exists():
            failures.append(f"missing live asset: {host_path_str}")
            results.append(asset_result)
            continue
        repo_text = read_text(repo_path)
        host_text = read_text(host_path)
        matches = repo_text.rstrip() == host_text.rstrip()
        asset_result["matches_repo"] = matches
        asset_result["host_sha256"] = sha256_text(host_text)
        if not matches:
            failures.append(f"live asset drift: {host_path_str}")
        results.append(asset_result)
    return results, failures


def bytes_to_gib(value: int) -> float:
    return round(value / (1024 ** 3), 2)


def disk_free_gib(path: str) -> float | None:
    target = Path(path)
    if not target.exists():
        return None
    usage = shutil.disk_usage(target)
    return bytes_to_gib(usage.free)


def check_aliases() -> dict[str, object]:
    host_aliases: dict[str, object] = {}
    for alias in HOST_ALIAS_PATHS:
        path = Path(alias)
        host_aliases[alias] = {
            "exists": path.exists(),
            "is_symlink": path.is_symlink(),
            "target": os.readlink(path) if path.is_symlink() else None,
        }
    return host_aliases


def parse_qbittorrent_save_path(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    for line in config_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Downloads\\SavePath="):
            return line.split("=", 1)[1].rstrip("/") or None
        if line.startswith("Session\\DefaultSavePath="):
            return line.split("=", 1)[1].rstrip("/") or None
    return None


def run_docker_probe(path: str) -> dict[str, object]:
    result = run(
        [
            "docker",
            "exec",
            "plex",
            "sh",
            "-lc",
            'file="$1"; head -c 1048576 -- "$file" >/dev/null',
            "sh",
            path,
        ],
        timeout=45,
    )
    return {
        "path": path,
        "ok": result.returncode == 0,
        "stderr": result.stderr.strip() or None,
    }


def run_docker_alias_probe() -> dict[str, object]:
    probe_script = (
        'for p in "$@"; do '
        '[ -e "$p" ] || { echo "$p missing" >&2; exit 1; }; '
        "done"
    )
    result = run(["docker", "exec", "plex", "sh", "-lc", probe_script, "sh", *CONTAINER_ALIAS_PATHS], timeout=30)
    return {
        "paths": CONTAINER_ALIAS_PATHS,
        "ok": result.returncode == 0,
        "stderr": result.stderr.strip() or None,
    }


def run_qbittorrent_write_probe(save_path: str) -> dict[str, object]:
    probe_script = 'd="$1"; f="$d/.host-workload-verify.$$"; ls -1A "$d" >/dev/null 2>&1; : > "$f"; rm -f "$f"'
    result = run(
        ["docker", "exec", "qbittorrent_pia", "sh", "-lc", probe_script, "sh", save_path],
        timeout=45,
    )
    return {
        "path": save_path,
        "ok": result.returncode == 0,
        "stderr": result.stderr.strip() or None,
    }


def resolve_qbittorrent_host_save_path(save_path: str | None) -> str | None:
    cleaned = str(save_path or "").strip()
    if not cleaned:
        return None
    mappings = docker_container_mount_mappings("qbittorrent_pia")
    resolved = resolve_host_path(cleaned, mappings)
    return resolved or None


def verify_runtime() -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []
    runtime: dict[str, object] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "disk_free_gib": {
            "/": disk_free_gib("/"),
            "/var/cache/rclone": disk_free_gib("/var/cache/rclone"),
        },
        "timers": {unit: systemctl_show(unit) for unit in WATCHDOG_TIMERS},
        "host_aliases": check_aliases(),
    }

    docker_status = run(["docker", "ps", "--filter", "name=^/plex$", "--format", "{{.Status}}"], timeout=15)
    runtime["plex_container"] = {
        "command_status": docker_status.returncode,
        "status": docker_status.stdout.strip() or None,
        "stderr": docker_status.stderr.strip() or None,
    }
    if docker_status.returncode != 0 or not docker_status.stdout.strip():
        failures.append("plex container is not running")
        return runtime, failures

    for unit, details in runtime["timers"].items():
        if details.get("ActiveState") != "active":
            failures.append(f"watchdog timer not active: {unit}")

    probe_results = {name: run_docker_probe(path) for name, path in CONTAINER_PROBES.items()}
    alias_probe = run_docker_alias_probe()
    runtime["container_probes"] = probe_results
    runtime["container_alias_probe"] = alias_probe

    qbittorrent_status = run(["docker", "ps", "--filter", "name=^/qbittorrent_pia$", "--format", "{{.Status}}"], timeout=15)
    qbittorrent_config = Path("/docker/arr-v2/qbittorrent-vpn/qBittorrent/qBittorrent.conf")
    qbittorrent_log = Path("/docker/arr-v2/qbittorrent-vpn/qBittorrent/logs/qbittorrent.log")
    qbittorrent_save_path = parse_qbittorrent_save_path(qbittorrent_config)
    qbittorrent_runtime: dict[str, object] = {
        "container_status": qbittorrent_status.stdout.strip() or None,
        "config_exists": qbittorrent_config.exists(),
        "log_exists": qbittorrent_log.exists(),
        "save_path": qbittorrent_save_path,
        "host_save_path": resolve_qbittorrent_host_save_path(qbittorrent_save_path),
    }
    if qbittorrent_status.returncode == 0 and qbittorrent_status.stdout.strip() and qbittorrent_save_path:
        qbittorrent_runtime["write_probe"] = run_qbittorrent_write_probe(qbittorrent_save_path)
        if not qbittorrent_runtime["write_probe"]["ok"]:
            failures.append("qbittorrent write probe failed")
    runtime["qbittorrent_storage"] = qbittorrent_runtime

    for name, result in probe_results.items():
        if not result["ok"]:
            failures.append(f"container probe failed: {name}")
    if not alias_probe["ok"]:
        failures.append("container alias probe failed")

    for alias, details in runtime["host_aliases"].items():
        alias_ok = details["exists"] and details["is_symlink"]
        if not alias_ok:
            failures.append(f"host alias missing or not a symlink: {alias}")

    return runtime, failures


def build_report(repo_only: bool) -> tuple[dict[str, object], list[str]]:
    repo_assets, failures = verify_repo_assets()
    report: dict[str, object] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "repo_root": str(REPO_ROOT),
        "repo_assets": repo_assets,
    }
    if repo_only:
        return report, failures

    live_assets, live_failures = verify_live_assets()
    runtime, runtime_failures = verify_runtime()
    failures.extend(live_failures)
    failures.extend(runtime_failures)
    report["live_assets"] = live_assets
    report["runtime"] = runtime
    return report, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify repo and live host workload guardrails for Plex/cloud playback.")
    parser.add_argument("--repo-only", action="store_true", help="Only verify the mirrored repo assets.")
    parser.add_argument("--json-out", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    report, failures = build_report(repo_only=args.repo_only)
    report["status"] = "pass" if not failures else "fail"
    report["failures"] = failures

    payload = json.dumps(report, indent=2) + "\n"
    if args.json_out:
        args.json_out.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
