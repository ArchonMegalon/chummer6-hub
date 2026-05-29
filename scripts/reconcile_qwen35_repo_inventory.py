#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


COMPLETION_ROOT = Path("/docker/chummercomplete/_completion/chummer6_absolute_completion")
INVENTORY_PATH = COMPLETION_ROOT / "REPO_INVENTORY.yaml"
RUN_LEDGER_PATH = COMPLETION_ROOT / "RUN_LEDGER.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_git(repo: Path, args: list[str]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def live_state(repo_path: str) -> dict[str, Any]:
    repo = Path(repo_path)
    if not repo.exists():
        return {
            "availability": "missing",
            "status": "missing",
            "branch": None,
            "head_sha": None,
            "dirty": None,
            "upstream": None,
            "ahead": None,
            "behind": None,
            "clean": None,
        }
    dirty_output = run_git(repo, ["status", "--porcelain"])
    upstream = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    ahead = behind = None
    if upstream:
        counts = run_git(repo, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
        if counts:
            parts = counts.split()
            if len(parts) == 2:
                ahead, behind = parts
    dirty = bool(dirty_output) if dirty_output is not None else None
    return {
        "availability": "mounted",
        "status": "mounted",
        "branch": run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "head_sha": run_git(repo, ["rev-parse", "HEAD"]),
        "dirty": dirty,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "clean": None if dirty is None else not dirty,
    }


def main() -> int:
    payload = yaml.safe_load(INVENTORY_PATH.read_text(encoding="utf-8")) or {}
    repos = payload.get("repos") or []
    if not isinstance(repos, list):
        raise SystemExit("REPO_INVENTORY.yaml has no repos list")
    generated_at = now_iso()
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        path = str(repo.get("path") or "").strip()
        if not path:
            continue
        state = live_state(path)
        for key in ("branch", "head_sha", "dirty", "upstream", "ahead", "behind", "availability", "status", "clean"):
            repo[key] = state[key]
        if repo.get("baseline_owner") == "release-readiness-cleanup" and repo.get("dirty"):
            repo["baseline_state_note"] = (
                "Live workspace state changed after release-readiness cleanup; "
                "inventory was reconciled to current git state."
            )
            repo["baseline_owner"] = "live_inventory_reconciliation"
    payload["generated_at"] = generated_at
    INVENTORY_PATH.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with RUN_LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(
            "{"
            f"\"timestamp\":\"{generated_at}\","
            "\"run_id\":\"20260509T094222Z\","
            "\"pass\":1,"
            "\"phase\":\"inventory\","
            "\"action\":\"reconcile_repo_inventory_to_live_state\","
            "\"status\":\"completed\","
            "\"repo_path\":\"/docker/chummercomplete/_completion/chummer6_absolute_completion\","
            "\"artifacts\":[\"REPO_INVENTORY.yaml\"]"
            "}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
