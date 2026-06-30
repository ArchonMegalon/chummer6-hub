#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand_compose_value(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        fallback = match.group(2)
        current = os.environ.get(key)
        if current:
            return current
        return fallback or ""

    return ENV_PATTERN.sub(replace, value)


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


def resolve_compose_build_source(compose_file: Path, service_name: str) -> Path:
    compose_file = compose_file.resolve()
    payload = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    services = payload.get("services") if isinstance(payload, dict) else None
    if not isinstance(services, dict) or service_name not in services:
        raise ValueError(f"{compose_file} does not define service {service_name!r}")

    service = services[service_name]
    if not isinstance(service, dict):
        raise ValueError(f"{compose_file} service {service_name!r} is not an object")

    build = service.get("build")
    if not isinstance(build, dict):
        raise ValueError(f"{compose_file} service {service_name!r} does not use object-form build config")

    context_value = expand_compose_value(str(build.get("context") or "").strip())
    dockerfile_value = expand_compose_value(str(build.get("dockerfile") or "").strip())
    if not context_value or not dockerfile_value:
        raise ValueError(f"{compose_file} service {service_name!r} build config requires context and dockerfile")

    context_path = Path(context_value)
    if not context_path.is_absolute():
        context_path = compose_file.parent / context_path
    context_path = context_path.resolve()

    dockerfile_path = Path(dockerfile_value)
    if not dockerfile_path.is_absolute():
        dockerfile_path = context_path / dockerfile_path
    dockerfile_path = dockerfile_path.resolve()

    try:
        relative_dockerfile = dockerfile_path.relative_to(context_path)
    except ValueError as exc:
        raise ValueError(f"{dockerfile_path} is outside build context {context_path}") from exc

    if len(relative_dockerfile.parts) < 2:
        raise ValueError(
            f"{compose_file} service {service_name!r} dockerfile {dockerfile_value!r} "
            "does not identify a source directory under the build context"
        )

    return (context_path / relative_dockerfile.parts[0]).resolve()


def verify(
    repo_root: Path,
    expected_head: str | None = None,
    require_upstream: bool = False,
    compose_file: Path | None = None,
    compose_service: str | None = None,
) -> dict[str, Any]:
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
    compose_build_source = ""
    if compose_file is not None or compose_service:
        if compose_file is None or not compose_service:
            raise ValueError("--compose-file and --compose-service must be supplied together")

        build_source = resolve_compose_build_source(compose_file, compose_service)
        compose_build_source = str(build_source)
        if build_source != top_level:
            findings.append(
                {
                    "id": "compose_build_source_mismatch",
                    "severity": "blocker",
                    "detail": (
                        f"compose service {compose_service} builds from {build_source}, "
                        f"but deploy source gate was run against {top_level}"
                    ),
                }
            )

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
        "composeFile": str(compose_file.resolve()) if compose_file is not None else "",
        "composeService": compose_service or "",
        "composeBuildSource": compose_build_source,
        "dirtyLineCount": len(dirty_lines),
        "dirtyLines": dirty_lines[:50],
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify that a public-edge deploy source tree is clean and at the intended revision.")
    parser.add_argument("--repo-root", default=".", help="Git worktree to verify.")
    parser.add_argument("--expected-head", default="", help="Exact commit SHA expected for this deploy source.")
    parser.add_argument("--require-upstream", action="store_true", help="Require HEAD to match the configured upstream branch.")
    parser.add_argument("--compose-file", default="", help="Optional compose file whose service build source must match --repo-root.")
    parser.add_argument("--compose-service", default="", help="Compose service name to validate when --compose-file is supplied.")
    parser.add_argument("--json", action="store_true", help="Print a JSON receipt.")
    args = parser.parse_args(argv)

    try:
        receipt = verify(
            Path(args.repo_root),
            expected_head=args.expected_head or None,
            require_upstream=args.require_upstream,
            compose_file=Path(args.compose_file) if args.compose_file else None,
            compose_service=args.compose_service or None,
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
