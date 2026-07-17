#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
COMPOSE_PATH = RUN_SERVICES_ROOT / "docker-compose.public-edge.yml"

HEALTHCHECK_CONTRACTS: dict[str, tuple[str, ...]] = {
    "support-progress-mock": ("python", "http://127.0.0.1:8080/healthz"),
    "chummer-presentation-api": ("curl", "http://127.0.0.1:8080/health"),
    "chummer-public-blazor": ("curl", "http://127.0.0.1:8080/blazor/health"),
    "chummer-play-web": ("curl", "http://127.0.0.1:8080/health"),
    "chummer-run-identity": ("curl", "http://127.0.0.1:8080/health"),
    "chummer-portal": ("curl", "http://127.0.0.1:8080/api/ready"),
    "chummer-run-cloudflared": ("cloudflared", "tunnel", "127.0.0.1:2000", "ready"),
}

CLOUDFLARED_DEFAULT_IMAGE = "cloudflare/cloudflared:${CHUMMER_CLOUDFLARED_IMAGE_TAG:-2026.7.0}"
CLOUDFLARED_RUNTIME_COMMAND_FRAGMENTS = ("--metrics", "0.0.0.0:2000", "run")

DEPENDENCY_CONTRACTS = {
    "chummer-public-blazor": {"chummer-presentation-api"},
    "chummer-portal": {
        "chummer-public-blazor",
        "chummer-run-identity",
        "support-progress-mock",
    },
    "chummer-run-cloudflared": {"chummer-portal"},
}

MEMORY_LIMIT_CONTRACTS = {
    "support-progress-mock": "${CHUMMER_SUPPORT_PROGRESS_MEMORY_LIMIT:-128m}",
    "chummer-presentation-api": "${CHUMMER_PRESENTATION_API_MEMORY_LIMIT:-1g}",
    "chummer-public-blazor": "${CHUMMER_PUBLIC_BLAZOR_MEMORY_LIMIT:-1g}",
    "chummer-play-web": "${CHUMMER_PLAY_WEB_MEMORY_LIMIT:-768m}",
    "chummer-run-identity": "${CHUMMER_IDENTITY_MEMORY_LIMIT:-512m}",
    "chummer-portal": "${CHUMMER_PORTAL_MEMORY_LIMIT:-1536m}",
    "chummer-run-cloudflared": "${CHUMMER_CLOUDFLARED_MEMORY_LIMIT:-256m}",
}

CURL_RUNTIME_DOCKERFILES = (
    RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Dockerfile",
    RUN_SERVICES_ROOT / "Chummer.Run.Identity" / "Dockerfile",
    WORKSPACE_ROOT / "chummer-play" / "src" / "Chummer.Play.Web" / "Dockerfile",
    WORKSPACE_ROOT / "chummer-presentation" / "Chummer.Api" / "Dockerfile",
    WORKSPACE_ROOT / "chummer-presentation" / "Chummer.Blazor" / "Dockerfile",
)

HEALTH_ROUTE_SOURCE_CONTRACTS = {
    RUN_SERVICES_ROOT / "scripts" / "support_progress_mock.py": (
        'if self.path == "/healthz":',
    ),
    WORKSPACE_ROOT / "chummer-presentation" / "Chummer.Api" / "Endpoints" / "InfoEndpoints.cs": (
        'app.MapGet("/health"',
    ),
    WORKSPACE_ROOT / "chummer-presentation" / "Chummer.Blazor" / "Program.cs": (
        "app.UseHostedBuildHealthChecks(",
    ),
    WORKSPACE_ROOT
    / "chummer-presentation"
    / "Chummer.Blazor"
    / "Services"
    / "HostedBuildWorkspacePersistenceReadiness.cs": (
        'PathString healthPath = AppendPath(pathBase, "/health");',
        "context.Request.Path == healthPath",
    ),
    WORKSPACE_ROOT / "chummer-play" / "src" / "Chummer.Play.Web" / "PlayWebApplication.cs": (
        'app.MapGet("/health"',
    ),
    RUN_SERVICES_ROOT / "Chummer.Run.Identity" / "Program.cs": (
        'app.MapMethods("/health", [HttpMethods.Get, HttpMethods.Head]',
    ),
    RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Program.cs": (
        'app.MapMethods("/api/health", new[] { HttpMethods.Get, HttpMethods.Head }',
        'app.MapMethods("/api/ready", new[] { HttpMethods.Get, HttpMethods.Head }',
    ),
}


def load_compose(path: Path = COMPOSE_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"compose document must be a mapping: {path}")
    return payload


def validate_compose(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    services = payload.get("services")
    if not isinstance(services, dict):
        return ["compose services mapping is missing"]

    for service_name, required_fragments in HEALTHCHECK_CONTRACTS.items():
        service = services.get(service_name)
        if not isinstance(service, dict):
            failures.append(f"required service is missing: {service_name}")
            continue
        healthcheck = service.get("healthcheck")
        if not isinstance(healthcheck, dict):
            failures.append(f"{service_name} healthcheck is missing")
            continue
        test = healthcheck.get("test")
        if not isinstance(test, list) or not test:
            failures.append(f"{service_name} healthcheck test must be a non-empty exec list")
        else:
            command = " ".join(str(item) for item in test)
            for fragment in required_fragments:
                if fragment not in command:
                    failures.append(
                        f"{service_name} healthcheck is missing required fragment: {fragment}"
                    )
        for field in ("interval", "timeout", "retries", "start_period"):
            if field not in healthcheck:
                failures.append(f"{service_name} healthcheck is missing {field}")

    for service_name, expected_dependencies in DEPENDENCY_CONTRACTS.items():
        service = services.get(service_name)
        if not isinstance(service, dict):
            failures.append(f"required service is missing: {service_name}")
            continue
        dependencies = service.get("depends_on")
        if not isinstance(dependencies, dict):
            failures.append(f"{service_name} depends_on must use health-conditioned mapping syntax")
            continue
        for dependency in sorted(expected_dependencies):
            dependency_config = dependencies.get(dependency)
            if not isinstance(dependency_config, dict):
                failures.append(f"{service_name} dependency is missing: {dependency}")
                continue
            if dependency_config.get("condition") != "service_healthy":
                failures.append(
                    f"{service_name} dependency {dependency} must require service_healthy"
                )

    for service_name, expected_limit in MEMORY_LIMIT_CONTRACTS.items():
        service = services.get(service_name)
        if not isinstance(service, dict):
            failures.append(f"required service is missing: {service_name}")
            continue
        if service.get("mem_limit") != expected_limit:
            failures.append(
                f"{service_name} mem_limit must be overrideable with default {expected_limit}"
            )

    cloudflared = services.get("chummer-run-cloudflared")
    if isinstance(cloudflared, dict):
        if cloudflared.get("image") != CLOUDFLARED_DEFAULT_IMAGE:
            failures.append(
                "chummer-run-cloudflared image must use the current versioned default "
                f"{CLOUDFLARED_DEFAULT_IMAGE}"
            )
        runtime_command = cloudflared.get("command")
        if not isinstance(runtime_command, list):
            failures.append("chummer-run-cloudflared command must use exec-list syntax")
        else:
            for fragment in CLOUDFLARED_RUNTIME_COMMAND_FRAGMENTS:
                if fragment not in runtime_command:
                    failures.append(
                        "chummer-run-cloudflared runtime command is missing required fragment: "
                        f"{fragment}"
                    )

    return failures


def validate_runtime_sources() -> list[str]:
    failures: list[str] = []
    curl_install_marker = "apt-get install -y --no-install-recommends curl"
    for dockerfile in CURL_RUNTIME_DOCKERFILES:
        if not dockerfile.is_file():
            failures.append(f"health-probed runtime Dockerfile is missing: {dockerfile}")
            continue
        if curl_install_marker not in dockerfile.read_text(encoding="utf-8"):
            failures.append(f"health-probed runtime does not install curl: {dockerfile}")

    for source_path, required_markers in HEALTH_ROUTE_SOURCE_CONTRACTS.items():
        if not source_path.is_file():
            failures.append(f"health route source is missing: {source_path}")
            continue
        source = source_path.read_text(encoding="utf-8")
        for marker in required_markers:
            if marker not in source:
                failures.append(
                    f"health route source {source_path} is missing required marker: {marker}"
                )
    return failures


def main() -> int:
    try:
        payload = load_compose()
    except (OSError, ValueError) as exc:
        print(f"public-edge operability verification failed: {exc}", file=sys.stderr)
        return 1

    failures = [*validate_compose(payload), *validate_runtime_sources()]
    if failures:
        print("public-edge operability verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("public-edge compose operability verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
