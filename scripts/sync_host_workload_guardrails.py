#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from host_workload_guardrails_common import ASSET_MAP, REPO_ROOT


def resolve_host_path(host_root: Path, host_path: str) -> Path:
    if host_root == Path("/"):
        return Path(host_path)
    return host_root / host_path.lstrip("/")


def target_mode(path: Path) -> int:
    if path.suffix == ".sh":
        return 0o755
    return 0o644


def sync_assets(host_root: Path, apply: bool) -> tuple[dict[str, object], int]:
    results: list[dict[str, object]] = []
    changed = 0

    for repo_rel, host_path_str in ASSET_MAP:
        repo_path = REPO_ROOT / repo_rel
        target_path = resolve_host_path(host_root, host_path_str)
        repo_text = repo_path.read_text(encoding="utf-8")
        exists = target_path.exists()
        current_text = target_path.read_text(encoding="utf-8") if exists else None
        matches = exists and current_text.rstrip() == repo_text.rstrip()

        action = "ok" if matches else ("update" if exists else "create")
        result = {
            "repo_path": repo_rel,
            "target_path": str(target_path),
            "action": action,
        }

        if apply and not matches:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(repo_text, encoding="utf-8")
            os.chmod(target_path, target_mode(target_path))
            changed += 1
            result["applied"] = True
        else:
            result["applied"] = False
            if not matches:
                changed += 1

        results.append(result)

    return {"assets": results}, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync repo-managed Plex/cloud workload guardrails onto a host root.")
    parser.add_argument("--apply", action="store_true", help="Write the repo mirror into the target host root.")
    parser.add_argument(
        "--host-root",
        type=Path,
        default=Path("/"),
        help="Alternate host root for dry-run testing. Defaults to /.",
    )
    parser.add_argument("--json-out", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    report, changed = sync_assets(args.host_root, args.apply)
    report["checked_at"] = datetime.now(UTC).isoformat()
    report["repo_root"] = str(REPO_ROOT)
    report["host_root"] = str(args.host_root)
    report["mode"] = "apply" if args.apply else "dry-run"
    report["changed_count"] = changed
    report["status"] = "pass"

    payload = json.dumps(report, indent=2) + "\n"
    if args.json_out:
        args.json_out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
