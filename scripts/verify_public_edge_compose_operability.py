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
    "chummer-observability-alertmanager": (
        "/bin/amtool",
        "http://127.0.0.1:9093",
        "config",
        "show",
    ),
    "chummer-observability-prometheus": (
        "/bin/promtool",
        "check",
        "healthy",
        "http://127.0.0.1:9090",
    ),
    "chummer-portal": ("curl", "http://127.0.0.1:8080/api/ready"),
    "chummer-run-cloudflared": ("cloudflared", "tunnel", "127.0.0.1:2000", "ready"),
    "chummer-run-cloudflared-replica": (
        "cloudflared",
        "tunnel",
        "127.0.0.1:2000",
        "ready",
    ),
}

CLOUDFLARED_PINNED_IMAGE = (
    "cloudflare/cloudflared:2026.7.0"
    "@sha256:8c70a8c2d373e93caac1ee79fcc615908a49ccf3f3975775d1e10d24e41327af"
)
CLOUDFLARED_PLATFORM = "linux/amd64"
CLOUDFLARED_SERVICE_NAMES = (
    "chummer-run-cloudflared",
    "chummer-run-cloudflared-replica",
)
CLOUDFLARED_RUNTIME_COMMAND_FRAGMENTS = ("--metrics", "0.0.0.0:2000", "run")
PROMETHEUS_PINNED_IMAGE = (
    "prom/prometheus:v3.13.0-distroless"
    "@sha256:f3b6aae627d96e7ad8256cdf6de5953247735117c6f577383fadb42efeeea7bc"
)
PROMETHEUS_RUNTIME_COMMAND_FRAGMENTS = (
    "--config.file=/etc/prometheus/prometheus.yml",
    "--storage.tsdb.path=/prometheus",
    "--web.enable-otlp-receiver",
    "--web.listen-address=0.0.0.0:9090",
)
ALERTMANAGER_PINNED_IMAGE = (
    "prom/alertmanager:v0.32.1"
    "@sha256:51a825c2a40acc3e338fdd00d622e01ec090f72be2b3ea46be0839cd47a4d286"
)
ALERTMANAGER_RUNTIME_COMMAND_FRAGMENTS = (
    "--config.file=/etc/alertmanager/alertmanager.yml",
    "--storage.path=/alertmanager",
    "--web.listen-address=0.0.0.0:9093",
)

DEPENDENCY_CONTRACTS = {
    "chummer-public-blazor": {"chummer-presentation-api"},
    "chummer-portal": {
        "chummer-public-blazor",
        "chummer-run-identity",
        "chummer-observability-prometheus",
        "support-progress-mock",
    },
    "chummer-observability-prometheus": {
        "chummer-observability-alertmanager",
    },
    "chummer-run-cloudflared": {"chummer-portal"},
    "chummer-run-cloudflared-replica": {"chummer-portal"},
}

MEMORY_LIMIT_CONTRACTS = {
    "support-progress-mock": "${CHUMMER_SUPPORT_PROGRESS_MEMORY_LIMIT:-128m}",
    "chummer-presentation-api": "${CHUMMER_PRESENTATION_API_MEMORY_LIMIT:-1g}",
    "chummer-public-blazor": "${CHUMMER_PUBLIC_BLAZOR_MEMORY_LIMIT:-1g}",
    "chummer-play-web": "${CHUMMER_PLAY_WEB_MEMORY_LIMIT:-768m}",
    "chummer-run-identity": "${CHUMMER_IDENTITY_MEMORY_LIMIT:-512m}",
    "chummer-observability-alertmanager": "${CHUMMER_OBSERVABILITY_ALERTMANAGER_MEMORY_LIMIT:-256m}",
    "chummer-observability-prometheus": "${CHUMMER_OBSERVABILITY_PROMETHEUS_MEMORY_LIMIT:-512m}",
    "chummer-portal": "${CHUMMER_PORTAL_MEMORY_LIMIT:-1536m}",
    "chummer-run-cloudflared": "${CHUMMER_CLOUDFLARED_MEMORY_LIMIT:-256m}",
    "chummer-run-cloudflared-replica": "${CHUMMER_CLOUDFLARED_MEMORY_LIMIT:-256m}",
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

OBSERVABILITY_RUNTIME_SOURCE_CONTRACTS = {
    RUN_SERVICES_ROOT / "Chummer.Run.Api" / "HubRequestObservabilityExtensions.cs": (
        "AddOpenTelemetry()",
        "AddMeter(HubRequestObservability.MeterName)",
        "AddOtlpExporter((exporterOptions, readerOptions)",
        "exporterOptions.Endpoint = metricsExport.MetricsSignalEndpoint",
        "exporterOptions.Protocol = OtlpExportProtocol.HttpProtobuf",
    ),
    RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Chummer.Run.Api.csproj": (
        'OpenTelemetry.Exporter.OpenTelemetryProtocol" Version="1.17.0"',
        'OpenTelemetry.Extensions.Hosting" Version="1.17.0"',
    ),
    RUN_SERVICES_ROOT / "ops" / "prometheus" / "prometheus.yml": (
        "translation_strategy: UnderscoreEscapingWithSuffixes",
        "out_of_order_time_window: 30m",
        "time: 28d",
        "/etc/prometheus/rules/*.yml",
        "chummer-observability-alertmanager:9093",
    ),
    RUN_SERVICES_ROOT / "ops" / "alertmanager" / "alertmanager.yml": (
        "receiver: primary_on_call",
        "bot_token_file: /run/secrets/chummer-observability/telegram-bot-token",
        "chat_id_file: /run/secrets/chummer-observability/telegram-chat-id",
    ),
    RUN_SERVICES_ROOT / "ops" / "prometheus" / "chummer-public-edge.rules.yml": (
        "chummer_run_api_requests_completed_total",
        "chummer_run_api_requests_duration_ms_bucket",
        "14.4 * 0.001",
        "6 * 0.001",
        "14.4 * 0.05",
        "6 * 0.05",
        "receiver_class: primary_on_call",
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

    storage_init = services.get("chummer-release-storage-init")
    if not isinstance(storage_init, dict):
        failures.append("required service is missing: chummer-release-storage-init")
    else:
        if storage_init.get("network_mode") != "none":
            failures.append(
                "chummer-release-storage-init network_mode must be none"
            )
        if "networks" in storage_init:
            failures.append(
                "chummer-release-storage-init must not join compose networks"
            )

    portal = services.get("chummer-portal")
    if isinstance(portal, dict):
        dependencies = portal.get("depends_on")
        storage_dependency = (
            dependencies.get("chummer-release-storage-init")
            if isinstance(dependencies, dict)
            else None
        )
        if not isinstance(storage_dependency, dict) or storage_dependency.get(
            "condition"
        ) != "service_completed_successfully":
            failures.append(
                "chummer-portal dependency chummer-release-storage-init must "
                "require service_completed_successfully"
            )

        environment = portal.get("environment")
        expected_otlp_environment = {
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": (
                "http://chummer-observability-prometheus:9090/api/v1/otlp"
            ),
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_METRIC_EXPORT_INTERVAL": "15000",
            "OTEL_SERVICE_NAME": "chummer.run.api",
            "OTEL_RESOURCE_ATTRIBUTES": "deployment.environment.name=production",
        }
        if not isinstance(environment, dict):
            failures.append("chummer-portal environment mapping is missing")
        else:
            for key, expected in expected_otlp_environment.items():
                if str(environment.get(key)) != expected:
                    failures.append(
                        f"chummer-portal {key} must be the governed OTLP value {expected}"
                    )

    observability_init = services.get("chummer-observability-storage-init")
    if not isinstance(observability_init, dict):
        failures.append("required service is missing: chummer-observability-storage-init")
    else:
        if observability_init.get("network_mode") != "none":
            failures.append("chummer-observability-storage-init network_mode must be none")
        init_dependencies = observability_init.get("networks")
        if init_dependencies is not None:
            failures.append("chummer-observability-storage-init must not join compose networks")

    prometheus = services.get("chummer-observability-prometheus")
    if isinstance(prometheus, dict):
        if prometheus.get("image") != PROMETHEUS_PINNED_IMAGE:
            failures.append(
                "chummer-observability-prometheus image must use the immutable supported runtime pin"
            )
        if prometheus.get("user") != "65532:65532":
            failures.append("chummer-observability-prometheus must run as uid/gid 65532")
        if prometheus.get("read_only") is not True:
            failures.append("chummer-observability-prometheus root filesystem must be read-only")
        if prometheus.get("cap_drop") != ["ALL"]:
            failures.append("chummer-observability-prometheus must drop every capability")
        if "ports" in prometheus:
            failures.append("chummer-observability-prometheus must not publish a host port")
        dependencies = prometheus.get("depends_on")
        init_dependency = (
            dependencies.get("chummer-observability-storage-init")
            if isinstance(dependencies, dict)
            else None
        )
        if not isinstance(init_dependency, dict) or init_dependency.get(
            "condition"
        ) != "service_completed_successfully":
            failures.append(
                "chummer-observability-prometheus must wait for successful storage initialization"
            )
        runtime_command = prometheus.get("command")
        if not isinstance(runtime_command, list):
            failures.append("chummer-observability-prometheus command must use exec-list syntax")
        else:
            for fragment in PROMETHEUS_RUNTIME_COMMAND_FRAGMENTS:
                if fragment not in runtime_command:
                    failures.append(
                        "chummer-observability-prometheus runtime command is missing "
                        f"required fragment: {fragment}"
                    )

    alertmanager = services.get("chummer-observability-alertmanager")
    if isinstance(alertmanager, dict):
        if alertmanager.get("image") != ALERTMANAGER_PINNED_IMAGE:
            failures.append(
                "chummer-observability-alertmanager image must use the immutable supported runtime pin"
            )
        expected_user = (
            "${CHUMMER_OBSERVABILITY_ALERTMANAGER_UID:-1000}:"
            "${CHUMMER_OBSERVABILITY_ALERTMANAGER_GID:-1000}"
        )
        if alertmanager.get("user") != expected_user:
            failures.append(
                "chummer-observability-alertmanager must run as the governed non-root uid/gid"
            )
        if alertmanager.get("read_only") is not True:
            failures.append(
                "chummer-observability-alertmanager root filesystem must be read-only"
            )
        if alertmanager.get("cap_drop") != ["ALL"]:
            failures.append(
                "chummer-observability-alertmanager must drop every capability"
            )
        if "ports" in alertmanager:
            failures.append(
                "chummer-observability-alertmanager must not publish a host port"
            )
        dependencies = alertmanager.get("depends_on")
        init_dependency = (
            dependencies.get("chummer-observability-storage-init")
            if isinstance(dependencies, dict)
            else None
        )
        if not isinstance(init_dependency, dict) or init_dependency.get(
            "condition"
        ) != "service_completed_successfully":
            failures.append(
                "chummer-observability-alertmanager must wait for successful storage initialization"
            )
        runtime_command = alertmanager.get("command")
        if not isinstance(runtime_command, list):
            failures.append(
                "chummer-observability-alertmanager command must use exec-list syntax"
            )
        else:
            for fragment in ALERTMANAGER_RUNTIME_COMMAND_FRAGMENTS:
                if fragment not in runtime_command:
                    failures.append(
                        "chummer-observability-alertmanager runtime command is missing "
                        f"required fragment: {fragment}"
                    )
        secret_mount = False
        volumes = alertmanager.get("volumes")
        if isinstance(volumes, list):
            for volume in volumes:
                if not isinstance(volume, dict):
                    continue
                if (
                    volume.get("target") == "/run/secrets/chummer-observability"
                    and volume.get("read_only") is True
                    and isinstance(volume.get("bind"), dict)
                    and volume["bind"].get("create_host_path") is False
                ):
                    secret_mount = True
                    break
        if not secret_mount:
            failures.append(
                "chummer-observability-alertmanager must mount the governed secret directory read-only"
            )

    for service_name in CLOUDFLARED_SERVICE_NAMES:
        cloudflared = services.get(service_name)
        if not isinstance(cloudflared, dict):
            continue
        if cloudflared.get("image") != CLOUDFLARED_PINNED_IMAGE:
            failures.append(
                f"{service_name} image must use the immutable current runtime pin "
                f"{CLOUDFLARED_PINNED_IMAGE}"
            )
        if cloudflared.get("platform") != CLOUDFLARED_PLATFORM:
            failures.append(
                f"{service_name} platform must match the pinned manifest "
                f"{CLOUDFLARED_PLATFORM}"
            )
        runtime_command = cloudflared.get("command")
        if not isinstance(runtime_command, list):
            failures.append(f"{service_name} command must use exec-list syntax")
        else:
            for fragment in CLOUDFLARED_RUNTIME_COMMAND_FRAGMENTS:
                if fragment not in runtime_command:
                    failures.append(
                        f"{service_name} runtime command is missing required fragment: "
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
    for source_path, required_markers in OBSERVABILITY_RUNTIME_SOURCE_CONTRACTS.items():
        if not source_path.is_file():
            failures.append(f"observability runtime source is missing: {source_path}")
            continue
        source = source_path.read_text(encoding="utf-8")
        for marker in required_markers:
            if marker not in source:
                failures.append(
                    f"observability runtime source {source_path} is missing required marker: {marker}"
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
