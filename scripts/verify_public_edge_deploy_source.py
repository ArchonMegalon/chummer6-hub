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
GENERATED_PROOF_PREFIXES = (".codex-studio/published/",)
TRUSTED_GIT = "/usr/bin/git"
PORTAL_SERVICE_WORKER_GUARD_MARKERS = (
    "RUN test -f /app/publish/wwwroot/service-worker.js",
    "grep -Fq 'const CACHE_VERSION = \"v19\";' /app/publish/wwwroot/service-worker.js",
    "grep -Fq 'const CACHE_CONTRACT = \"run-api-projection-v2\";' /app/publish/wwwroot/service-worker.js",
    "grep -Fq 'const CRITICAL_SHELL_ASSETS = [' /app/publish/wwwroot/service-worker.js",
    "grep -Fq '\"/manifest.play.webmanifest\"' /app/publish/wwwroot/service-worker.js",
    "grep -Fq 'play_public_route_network_unavailable' /app/publish/wwwroot/service-worker.js",
    "grep -Fq 'url.pathname.startsWith(\"/api/play/\")' /app/publish/wwwroot/service-worker.js",
    "! grep -Fq 'self.skipWaiting()' /app/publish/wwwroot/service-worker.js",
    "! grep -Fq 'self.clients.claim()' /app/publish/wwwroot/service-worker.js",
    "! grep -Fq '\"/mobile-turn-companion.js\"' /app/publish/wwwroot/service-worker.js",
)


def expand_compose_value(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        fallback = match.group(2)
        current = os.environ.get(key)
        if current:
            return current
        return fallback or ""

    return ENV_PATTERN.sub(replace, value)


def resolve_path_value(value: str, base_dir: Path) -> Path:
    expanded = expand_compose_value(value.strip())
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def run_git(repo_root: Path, *args: str) -> str:
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
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        },
        stdin=subprocess.DEVNULL,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def resolve_compose_source_paths(compose_file: Path, service_name: str) -> tuple[Path, Path, Path]:
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

    if dockerfile_path.name != "Dockerfile" or not dockerfile_path.parent.name.startswith("Chummer.Run."):
        raise ValueError(
            f"{compose_file} service {service_name!r} dockerfile {dockerfile_value!r} "
            "does not identify a Chummer.Run service Dockerfile"
        )
    dockerfile_source = dockerfile_path.parent.parent.resolve()

    additional_contexts = build.get("additional_contexts")
    if isinstance(additional_contexts, dict):
        run_services_source = additional_contexts.get("run-services-source")
        if isinstance(run_services_source, str) and run_services_source.strip():
            return resolve_path_value(run_services_source, compose_file.parent), dockerfile_source, dockerfile_path

    return dockerfile_source, dockerfile_source, dockerfile_path


def dockerfile_has_portal_service_worker_guard(dockerfile_path: Path) -> bool:
    text = dockerfile_path.read_text(encoding="utf-8")
    return all(marker in text for marker in PORTAL_SERVICE_WORKER_GUARD_MARKERS)


def dirty_line_paths(line: str) -> list[str]:
    if len(line) > 3 and line[2] == " ":
        raw_path = line[3:].strip()
    elif len(line) > 2 and line[1] == " ":
        raw_path = line[2:].strip()
    else:
        raw_path = line.strip()
    if " -> " in raw_path:
        return [item.strip() for item in raw_path.split(" -> ") if item.strip()]
    return [raw_path] if raw_path else []


def is_generated_proof_dirty_line(line: str) -> bool:
    paths = dirty_line_paths(line)
    return bool(paths) and all(
        any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in GENERATED_PROOF_PREFIXES)
        for path in paths
    )


def verify(
    repo_root: Path,
    expected_head: str | None = None,
    require_upstream: bool = False,
    compose_file: Path | None = None,
    compose_service: str | None = None,
    ignore_generated_proof_drift: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    inside = run_git(repo_root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        raise ValueError(f"{repo_root} is not a git worktree")

    top_level = Path(run_git(repo_root, "rev-parse", "--show-toplevel")).resolve()
    head = run_git(top_level, "rev-parse", "HEAD")
    branch = run_git(top_level, "branch", "--show-current")
    status = run_git(top_level, "status", "--porcelain=v1", "--untracked-files=all")
    raw_dirty_lines = [line for line in status.splitlines() if line.strip()]
    ignored_dirty_lines = (
        [line for line in raw_dirty_lines if is_generated_proof_dirty_line(line)]
        if ignore_generated_proof_drift
        else []
    )
    dirty_lines = [line for line in raw_dirty_lines if line not in ignored_dirty_lines]

    findings: list[dict[str, str]] = []
    compose_build_source = ""
    compose_dockerfile_source = ""
    compose_dockerfile_path = ""
    if compose_file is not None or compose_service:
        if compose_file is None or not compose_service:
            raise ValueError("--compose-file and --compose-service must be supplied together")

        build_source, dockerfile_source, dockerfile_path = resolve_compose_source_paths(compose_file, compose_service)
        compose_build_source = str(build_source)
        compose_dockerfile_source = str(dockerfile_source)
        compose_dockerfile_path = str(dockerfile_path)
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
        if not dockerfile_has_portal_service_worker_guard(dockerfile_path):
            findings.append(
                {
                    "id": "missing_portal_service_worker_publish_guard",
                    "severity": "blocker",
                    "detail": (
                        f"compose service {compose_service} Dockerfile {dockerfile_path} does not fail closed "
                        "when the published root service worker is not the canonical Run API projection"
                    ),
                }
            )
        if dockerfile_source != top_level:
            findings.append(
                {
                    "id": "compose_dockerfile_source_mismatch",
                    "severity": "blocker",
                    "detail": (
                        f"compose service {compose_service} reads Dockerfile from {dockerfile_source}, "
                        f"but deploy source gate was run against {top_level}"
                    ),
                }
            )
        if build_source != dockerfile_source:
            findings.append(
                {
                    "id": "compose_split_source_mismatch",
                    "severity": "blocker",
                    "detail": (
                        f"compose service {compose_service} builds content from {build_source} "
                        f"but reads Dockerfile from {dockerfile_source}"
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
        "ignoreGeneratedProofDrift": ignore_generated_proof_drift,
        "composeFile": str(compose_file.resolve()) if compose_file is not None else "",
        "composeService": compose_service or "",
        "composeBuildSource": compose_build_source,
        "composeDockerfileSource": compose_dockerfile_source,
        "composeDockerfilePath": compose_dockerfile_path,
        "totalDirtyLineCount": len(raw_dirty_lines),
        "dirtyLineCount": len(dirty_lines),
        "dirtyLines": dirty_lines[:50],
        "ignoredDirtyLineCount": len(ignored_dirty_lines),
        "ignoredDirtyLines": ignored_dirty_lines[:50],
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify that a public-edge deploy source tree is clean and at the intended revision.")
    parser.add_argument("--repo-root", default=".", help="Git worktree to verify.")
    parser.add_argument("--expected-head", default="", help="Exact commit SHA expected for this deploy source.")
    parser.add_argument("--require-upstream", action="store_true", help="Require HEAD to match the configured upstream branch.")
    parser.add_argument("--compose-file", default="", help="Optional compose file whose service build source must match --repo-root.")
    parser.add_argument("--compose-service", default="", help="Compose service name to validate when --compose-file is supplied.")
    parser.add_argument(
        "--ignore-generated-proof-drift",
        action="store_true",
        help="Ignore dirty files under .codex-studio/published because they are generated proof receipts, not public-edge build source.",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON receipt.")
    args = parser.parse_args(argv)

    try:
        receipt = verify(
            Path(args.repo_root),
            expected_head=args.expected_head or None,
            require_upstream=args.require_upstream,
            compose_file=Path(args.compose_file) if args.compose_file else None,
            compose_service=args.compose_service or None,
            ignore_generated_proof_drift=args.ignore_generated_proof_drift,
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
