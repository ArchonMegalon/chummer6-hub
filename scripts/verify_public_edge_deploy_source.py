#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def verify(repo_root: Path, expected_head: str | None = None, require_upstream: bool = False) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    inside = run_git(repo_root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        raise ValueError(f"{repo_root} is not a git worktree")

    top_level = Path(run_git(repo_root, "rev-parse", "--show-toplevel")).resolve()
    head = run_git(top_level, "rev-parse", "HEAD")
    branch = run_git(top_level, "branch", "--show-current")
    status = run_git(top_level, "status", "--porcelain=v1", "--untracked-files=all")
    dirty_lines = [line for line in status.splitlines() if line.strip()]

    findings: list[dict[str, str]] = []
    if dirty_lines:
        findings.append(
            {
                "id": "dirty_worktree",
                "severity": "blocker",
                "detail": "public-edge deploy source has uncommitted or untracked files",
            }
        )

    if expected_head:
        expected = expected_head.strip()
        if head != expected:
            findings.append(
                {
                    "id": "wrong_head",
                    "severity": "blocker",
                    "detail": f"public-edge deploy source HEAD {head} does not match expected {expected}",
                }
            )

    upstream = ""
    if require_upstream:
        upstream = run_git(top_level, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        upstream_head = run_git(top_level, "rev-parse", upstream)
        if head != upstream_head:
            findings.append(
                {
                    "id": "not_at_upstream_head",
                    "severity": "blocker",
                    "detail": f"public-edge deploy source HEAD {head} does not match {upstream} {upstream_head}",
                }
            )

    return {
        "contractName": "chummer.public_edge_deploy_source.v1",
        "status": "pass" if not findings else "fail",
        "repoRoot": str(top_level),
        "branch": branch,
        "head": head,
        "expectedHead": expected_head or "",
        "requireUpstream": require_upstream,
        "upstream": upstream,
        "dirtyLineCount": len(dirty_lines),
        "dirtyLines": dirty_lines[:50],
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify that a public-edge deploy source tree is clean and at the intended revision.")
    parser.add_argument("--repo-root", default=".", help="Git worktree to verify.")
    parser.add_argument("--expected-head", default="", help="Exact commit SHA expected for this deploy source.")
    parser.add_argument("--require-upstream", action="store_true", help="Require HEAD to match the configured upstream branch.")
    parser.add_argument("--json", action="store_true", help="Print a JSON receipt.")
    args = parser.parse_args(argv)

    try:
        receipt = verify(
            Path(args.repo_root),
            expected_head=args.expected_head or None,
            require_upstream=args.require_upstream,
        )
    except Exception as exc:
        receipt = {
            "contractName": "chummer.public_edge_deploy_source.v1",
            "status": "fail",
            "findings": [{"id": "verification_error", "severity": "blocker", "detail": str(exc)}],
        }

    if args.json or receipt["status"] != "pass":
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print("public_edge_deploy_source:ok")

    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
