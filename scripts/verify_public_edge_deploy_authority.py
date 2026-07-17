#!/usr/bin/python3
"""Minimal, wrapper-owned authority gate for a public-edge deploy source tree.

This module deliberately uses only the Python standard library and an absolute
Git binary.  It is safe to run before importing or executing anything from the
operator-selected source tree.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


TRUSTED_GIT = "/usr/bin/git"
FULL_COMMIT_PATTERN = re.compile(r"[0-9a-fA-F]{40}\Z")
REMOTE_REF_PATTERN = re.compile(
    r"refs/remotes/[A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?\Z"
)
GENERATED_PROOF_PREFIX = ".codex-studio/published/"


def _git_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _run_git(repo_root: Path, *args: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        [
            TRUSTED_GIT,
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "credential.helper=",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "submodule.recurse=false",
            "-C",
            str(repo_root),
            *args,
        ],
        check=False,
        env=_git_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 and not allow_failure:
        detail = result.stderr.strip() or result.stdout.strip() or f"status {result.returncode}"
        raise RuntimeError(f"trusted git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _validate_expected_head(value: str) -> str:
    candidate = value.strip()
    if FULL_COMMIT_PATTERN.fullmatch(candidate) is None:
        raise ValueError("expected deploy head must be an externally supplied full 40-hex commit")
    return candidate.lower()


def _validate_expected_upstream_ref(value: str) -> str:
    candidate = value.strip()
    if (
        REMOTE_REF_PATTERN.fullmatch(candidate) is None
        or ".." in candidate
        or "//" in candidate
        or "@{" in candidate
        or candidate.endswith(".lock")
    ):
        raise ValueError(
            "expected deploy upstream must be an externally supplied full refs/remotes/... ref"
        )
    return candidate


def _dirty_paths(line: str) -> list[str]:
    path = line[3:].strip() if len(line) > 3 else line.strip()
    if " -> " in path:
        return [candidate.strip() for candidate in path.split(" -> ") if candidate.strip()]
    return [path] if path else []


def verify_authority(
    repo_root: Path,
    *,
    expected_head: str,
    expected_upstream_ref: str,
    ignore_generated_proof_drift: bool = False,
) -> dict[str, Any]:
    expected = _validate_expected_head(expected_head)
    expected_upstream = _validate_expected_upstream_ref(expected_upstream_ref)
    selected_root = repo_root.resolve(strict=True)
    if not selected_root.is_dir():
        raise ValueError("selected deploy source root is not a directory")

    inside = _run_git(selected_root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        raise ValueError("selected deploy source is not a Git worktree")
    top_level = Path(_run_git(selected_root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top_level != selected_root:
        raise ValueError(
            f"selected deploy source {selected_root} is not the Git worktree root {top_level}"
        )

    head = _run_git(top_level, "rev-parse", "--verify", "HEAD^{commit}").lower()
    branch_ref = _run_git(top_level, "symbolic-ref", "--quiet", "HEAD")
    if not branch_ref.startswith("refs/heads/"):
        raise ValueError("selected deploy source must be on a local branch with an upstream")
    configured_upstream = _run_git(
        top_level, "for-each-ref", "--format=%(upstream)", branch_ref
    )
    if configured_upstream != expected_upstream:
        raise ValueError(
            "selected deploy branch upstream "
            f"{configured_upstream or '<unset>'} does not match expected {expected_upstream}"
        )
    upstream_head = _run_git(
        top_level, "rev-parse", "--verify", f"{expected_upstream}^{{commit}}"
    ).lower()

    findings: list[dict[str, str]] = []
    if head != expected:
        findings.append(
            {
                "id": "wrong_head",
                "severity": "blocker",
                "detail": f"selected deploy HEAD {head} does not match expected {expected}",
            }
        )
    if upstream_head != expected:
        findings.append(
            {
                "id": "wrong_upstream_head",
                "severity": "blocker",
                "detail": (
                    f"selected deploy upstream {expected_upstream} resolves to {upstream_head}, "
                    f"not expected {expected}"
                ),
            }
        )

    status_lines = [
        line
        for line in _run_git(
            top_level, "status", "--porcelain=v1", "--untracked-files=all"
        ).splitlines()
        if line.strip()
    ]
    ignored_lines = (
        [
            line
            for line in status_lines
            if _dirty_paths(line)
            and all(
                path.startswith(GENERATED_PROOF_PREFIX)
                for path in _dirty_paths(line)
            )
        ]
        if ignore_generated_proof_drift
        else []
    )
    dirty_lines = [line for line in status_lines if line not in ignored_lines]
    if dirty_lines:
        findings.append(
            {
                "id": "dirty_worktree",
                "severity": "blocker",
                "detail": "selected deploy source has uncommitted or untracked source files",
            }
        )

    return {
        "contractName": "chummer.public_edge_deploy_authority.v1",
        "status": "pass" if not findings else "fail",
        "repoRoot": str(top_level),
        "head": head,
        "expectedHead": expected,
        "branchRef": branch_ref,
        "configuredUpstreamRef": configured_upstream,
        "expectedUpstreamRef": expected_upstream,
        "upstreamHead": upstream_head,
        "dirtyLineCount": len(dirty_lines),
        "ignoredGeneratedProofDriftCount": len(ignored_lines),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify selected public-edge source authority before executing it."
    )
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-upstream-ref", required=True)
    parser.add_argument("--ignore-generated-proof-drift", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_authority(
            Path(args.repo_root),
            expected_head=args.expected_head,
            expected_upstream_ref=args.expected_upstream_ref,
            ignore_generated_proof_drift=args.ignore_generated_proof_drift,
        )
    except Exception as exc:
        receipt = {
            "contractName": "chummer.public_edge_deploy_authority.v1",
            "status": "fail",
            "findings": [
                {"id": "authority_error", "severity": "blocker", "detail": str(exc)}
            ],
        }

    # The receipt is intentionally always emitted: callers can persist the
    # exact authority decision without asking selected-source code to do so.
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
