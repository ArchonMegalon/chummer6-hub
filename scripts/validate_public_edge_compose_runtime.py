#!/usr/bin/env python3
"""Validate the rendered public-edge Compose runtime without persisting secrets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    # Keep isolated-mode authority independent of PYTHONPATH while allowing audited siblings.
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

try:
    from scripts.strict_json_contract import StrictJsonContractError, strict_json_object
except ModuleNotFoundError:  # Direct ``python3 scripts/...`` execution.
    from strict_json_contract import StrictJsonContractError, strict_json_object


MAX_RENDERED_COMPOSE_BYTES = 16 * 1024 * 1024
EXPECTED_PORTAL_IMAGE = "chummer-run-api:local"
EXPECTED_TOOL_IMAGE = "chummer-install-linking-postgres-tool:local"
EXPECTED_TOOL_TARGET = "install-linking-postgres-tool-final"
PROXY_GATE_KEYS = (
    "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED",
    "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED",
)
FORBIDDEN_PROXY_KEYS = (
    "CHUMMER_PUBLIC_PLAY_PROXY_URL",
    "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY",
    "CHUMMER_PUBLIC_PLAY_PROXY_ALLOWED_ORIGINS",
    "CHUMMER_PUBLIC_PLAY_PROXY_ALLOWED_HOSTS",
    "CHUMMER_PUBLIC_PLAY_PROXY_ALLOWLIST",
)
EXPECTED_FLEET_MEDIA_CONTEXT = (
    "/docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts"
)
EXPECTED_DESIGN_PRODUCT_CONTEXT = "/docker/chummercomplete/chummer-design"
EXPECTED_DOWNLOADS_SOURCE = (
    "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads"
)
EXPECTED_FLEET_ARTIFACT_ROOT = "/docker/fleet/.codex-studio/published"
EXPECTED_HUB_PROOF_SOURCE = (
    "/docker/chummercomplete/chummer.run-services/.codex-studio/published/"
    "HUB_LOCAL_RELEASE_PROOF.generated.json"
)
EXPECTED_FINAL_GOLD_SOURCE = (
    "/docker/chummercomplete/chummer.run-services/.codex-studio/published/"
    "FINAL_GOLD_JANITOR.generated.json"
)
EXPECTED_PORTAL_ENVIRONMENT = {
    "AllowedHosts": "chummer.run",
    "CHUMMER_PUBLIC_ALLOWED_HOSTS": "chummer.run",
    "CHUMMER_PUBLIC_CANONICAL_ORIGIN": "https://chummer.run",
    "CHUMMER_PUBLIC_CANON_ROOT": "/app",
    "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
    "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    "CHUMMER_RELEASE_UPLOAD_SESSION_ROOT": "/release-upload-sessions",
    "CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED": "false",
    "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
    "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
}
EXPECTED_PORTAL_HEALTHCHECK = {
    "test": [
        "CMD",
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        "5",
        "--header",
        "Host: chummer.run",
        "http://127.0.0.1:8080/api/ready",
    ],
    "interval": "15s",
    "timeout": "5s",
    "retries": 5,
    "start_period": "45s",
}
EXPECTED_PORTAL_DEPENDENCIES = {
    "chummer-portal-volume-init": {
        "condition": "service_completed_successfully",
        "required": True,
    },
    "chummer-public-blazor": {"condition": "service_healthy", "required": True},
    "chummer-run-identity": {"condition": "service_healthy", "required": True},
    "support-progress-mock": {"condition": "service_healthy", "required": True},
}
EXPECTED_CORE_ULIMIT = {"core": {}}
EXPECTED_TOOL_PROFILE = ["install-linking-postgres-admin"]
EXPECTED_TOOL_TMPFS = ["/tmp:rw,noexec,nosuid,nodev,mode=1777"]
EXPECTED_PORTAL_RESOURCES = {
    "cpu_shares": 256,
    "cpus": 1,
    "mem_limit": "1610612736",
}
EXPECTED_SERVICE_FIELDS = {
    "chummer-portal-volume-init": {
        "cap_add",
        "cap_drop",
        "command",
        "entrypoint",
        "environment",
        "image",
        "network_mode",
        "pids_limit",
        "read_only",
        "restart",
        "security_opt",
        "ulimits",
        "user",
        "volumes",
    },
    "chummer-portal": {
        "build",
        "cap_drop",
        "command",
        "cpu_shares",
        "cpus",
        "depends_on",
        "entrypoint",
        "environment",
        "extra_hosts",
        "healthcheck",
        "image",
        "mem_limit",
        "networks",
        "ports",
        "restart",
        "security_opt",
        "ulimits",
        "user",
        "volumes",
    },
    "chummer-install-linking-postgres-admin": {
        "build",
        "cap_drop",
        "command",
        "entrypoint",
        "environment",
        "image",
        "networks",
        "profiles",
        "read_only",
        "restart",
        "security_opt",
        "tmpfs",
        "ulimits",
        "user",
        "volumes",
    },
    "chummer-install-linking-postgres-import": {
        "build",
        "cap_drop",
        "command",
        "entrypoint",
        "environment",
        "image",
        "networks",
        "profiles",
        "read_only",
        "restart",
        "security_opt",
        "tmpfs",
        "ulimits",
        "user",
        "volumes",
    },
}


def mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def require_exact_mapping(
    value: object, *, expected: dict[str, Any], label: str
) -> None:
    if not isinstance(value, dict) or value != expected:
        raise ValueError(f"rendered {label} drifted from the canonical runtime policy")


def require_exact_sequence(value: object, *, expected: list[Any], label: str) -> None:
    if not isinstance(value, list) or value != expected:
        raise ValueError(f"rendered {label} drifted from the canonical runtime policy")


def require_empty_sequence(value: object, *, label: str) -> None:
    if value not in (None, []):
        raise ValueError(f"rendered {label} must be empty")


def require_empty_mapping(value: object, *, label: str) -> None:
    if value not in (None, {}):
        raise ValueError(f"rendered {label} must be empty")


def require_exact_service_fields(
    service: dict[str, Any], *, service_name: str
) -> None:
    expected_fields = EXPECTED_SERVICE_FIELDS[service_name]
    if set(service) != expected_fields:
        raise ValueError(
            f"rendered {service_name} service fields drifted from the canonical "
            "runtime policy"
        )


def require_exact_mounts(
    service: dict[str, Any],
    *,
    service_name: str,
    policies: list[dict[str, Any]],
) -> None:
    raw_mounts = service.get("volumes")
    if not isinstance(raw_mounts, list):
        raise ValueError(f"rendered {service_name} volumes must be a list")
    if len(raw_mounts) != len(policies):
        raise ValueError(f"rendered {service_name} mount set is not canonical")

    mounts_by_target: dict[str, dict[str, Any]] = {}
    for index, raw_mount in enumerate(raw_mounts):
        mount = mapping(raw_mount, label=f"rendered {service_name} mount {index}")
        target = mount.get("target")
        if not isinstance(target, str) or not target or target in mounts_by_target:
            raise ValueError(f"rendered {service_name} mount targets must be unique strings")
        mounts_by_target[target] = mount

    expected_targets = {str(policy["target"]) for policy in policies}
    if set(mounts_by_target) != expected_targets:
        raise ValueError(f"rendered {service_name} mount targets are not canonical")

    for policy in policies:
        target = str(policy["target"])
        mount = mounts_by_target[target]
        mount_type = str(policy["type"])
        expected_keys = {"type", "source", "target", mount_type}
        if policy.get("read_only") is True:
            expected_keys.add("read_only")
        if set(mount) != expected_keys:
            raise ValueError(
                f"rendered {service_name} mount {target} contains non-canonical fields"
            )
        if mount.get("type") != mount_type or mount.get(mount_type) != {}:
            raise ValueError(
                f"rendered {service_name} mount {target} type policy drifted"
            )
        if policy.get("read_only") is True and mount.get("read_only") is not True:
            raise ValueError(
                f"rendered {service_name} mount {target} must be read-only"
            )
        source = mount.get("source")
        if policy.get("opaque_source") is True:
            if (
                not isinstance(source, str)
                or not source.startswith("/")
                or Path(os.path.normpath(source)) != Path(source)
            ):
                raise ValueError(
                    f"rendered {service_name} mount {target} source must be an "
                    "absolute normalized path"
                )
        elif source != policy["source"]:
            raise ValueError(
                f"rendered {service_name} mount {target} source is not canonical"
            )


def require_service_security(
    service: dict[str, Any],
    *,
    service_name: str,
    read_only: bool,
    cap_add: list[str] | None = None,
    pids_limit: int | None = None,
) -> None:
    if service.get("privileged", False) is not False:
        raise ValueError(f"rendered {service_name} must not be privileged")
    require_exact_sequence(
        service.get("cap_drop"), expected=["ALL"], label=f"{service_name} cap_drop"
    )
    if cap_add is None:
        require_empty_sequence(service.get("cap_add"), label=f"{service_name} cap_add")
    else:
        require_exact_sequence(
            service.get("cap_add"), expected=cap_add, label=f"{service_name} cap_add"
        )
    require_exact_sequence(
        service.get("security_opt"),
        expected=["no-new-privileges:true"],
        label=f"{service_name} security_opt",
    )
    if service.get("read_only", False) is not read_only:
        raise ValueError(f"rendered {service_name} read_only policy drifted")
    require_exact_mapping(
        service.get("ulimits"),
        expected=EXPECTED_CORE_ULIMIT,
        label=f"{service_name} ulimits",
    )
    if pids_limit is None:
        if "pids_limit" in service:
            raise ValueError(f"rendered {service_name} must not override pids_limit")
    elif service.get("pids_limit") != pids_limit:
        raise ValueError(f"rendered {service_name} pids_limit policy drifted")


def require_runtime_identity(selected: dict[str, dict[str, Any]]) -> tuple[str, str]:
    runtime_services = (
        "chummer-portal",
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-import",
    )
    users = {
        service_name: selected[service_name].get("user")
        for service_name in runtime_services
    }
    portal_user = users["chummer-portal"]
    if not isinstance(portal_user, str):
        raise ValueError("rendered portal user must be an explicit nonroot uid:gid")
    match = re.fullmatch(r"([1-9][0-9]*):([1-9][0-9]*)", portal_user)
    if match is None or any(user != portal_user for user in users.values()):
        raise ValueError(
            "rendered portal and PostgreSQL tool users must be the same nonroot uid:gid"
        )
    if selected["chummer-portal-volume-init"].get("user") != "0:0":
        raise ValueError("rendered portal initializer user must be exactly 0:0")
    initializer_environment = mapping(
        selected["chummer-portal-volume-init"].get("environment"),
        label="rendered portal initializer environment",
    )
    expected_initializer_environment = {
        "CHUMMER_PORTAL_UID": match.group(1),
        "CHUMMER_PORTAL_GID": match.group(2),
    }
    if initializer_environment != expected_initializer_environment:
        raise ValueError(
            "rendered portal initializer identity is inconsistent with the runtime user"
        )
    return match.group(1), match.group(2)


def volume_mount_policy(source: str, target: str) -> dict[str, Any]:
    return {"type": "volume", "source": source, "target": target}


def bind_mount_policy(
    source: str, target: str, *, read_only: bool = False
) -> dict[str, Any]:
    policy: dict[str, Any] = {"type": "bind", "source": source, "target": target}
    if read_only:
        policy["read_only"] = True
    return policy


def opaque_read_only_bind_policy(target: str) -> dict[str, Any]:
    return {
        "type": "bind",
        "target": target,
        "read_only": True,
        "opaque_source": True,
    }


def read_rendered_compose() -> dict[str, Any]:
    payload = sys.stdin.buffer.read(MAX_RENDERED_COMPOSE_BYTES + 1)
    if len(payload) > MAX_RENDERED_COMPOSE_BYTES:
        raise ValueError("rendered Compose configuration exceeds the bounded input limit")
    return strict_json_object(payload, label="rendered public-edge Compose configuration")


def require_exact_build(
    service: dict[str, Any],
    *,
    service_name: str,
    source_root: Path,
    build_context: Path,
    expected_target: str,
    runtime_uid: str,
    runtime_gid: str,
) -> dict[str, Any]:
    build = mapping(service.get("build"), label=f"{service_name} build")
    contexts = mapping(
        build.get("additional_contexts"),
        label=f"{service_name} additional contexts",
    )
    expected_dockerfile = str(source_root / "Chummer.Run.Api" / "Dockerfile")
    actual_target = str(build.get("target") or "")
    expected_contexts = {
        "run-services-source": str(source_root),
        "fleet-media-factory-contracts": EXPECTED_FLEET_MEDIA_CONTEXT,
        "design-product": EXPECTED_DESIGN_PRODUCT_CONTEXT,
    }
    expected_build_keys = {"context", "dockerfile", "additional_contexts", "args"}
    if expected_target:
        expected_build_keys.add("target")
    args = mapping(build.get("args"), label=f"{service_name} build args")
    expected_arg_keys = {
        "CHUMMER_BUILD_CONCURRENCY",
        "CHUMMER_RUNTIME_UID",
        "CHUMMER_RUNTIME_GID",
    }
    concurrency = args.get("CHUMMER_BUILD_CONCURRENCY")
    checks = {
        "fields": set(build) == expected_build_keys,
        "context": str(build.get("context") or "") == str(build_context),
        "dockerfile": str(build.get("dockerfile") or "") == expected_dockerfile,
        "additionalContexts": contexts == expected_contexts,
        "target": actual_target == expected_target,
        "argFields": set(args) == expected_arg_keys,
        "buildConcurrency": isinstance(concurrency, str)
        and re.fullmatch(r"[1-9][0-9]*", concurrency) is not None,
        "runtimeUid": args.get("CHUMMER_RUNTIME_UID") == runtime_uid,
        "runtimeGid": args.get("CHUMMER_RUNTIME_GID") == runtime_gid,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ValueError(
            f"{service_name} rendered build authority drifted: {','.join(failures)}"
        )
    return {
        "context": str(build_context),
        "dockerfile": expected_dockerfile,
        "additionalContexts": expected_contexts,
        "target": expected_target,
        "runtimeIdentityConsistent": True,
    }


def validate_runtime(
    payload: dict[str, Any],
    *,
    project_name: str,
    source_root: Path,
    build_context: Path,
    overlay_root: Path,
    published_port: int,
) -> dict[str, Any]:
    if payload.get("name") != project_name:
        raise ValueError("rendered Compose project name is not the canonical deployment authority")
    services = mapping(payload.get("services"), label="rendered Compose services")
    required_services = (
        "chummer-portal-volume-init",
        "chummer-portal",
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-import",
    )
    selected: dict[str, dict[str, Any]] = {}
    for service_name in required_services:
        selected[service_name] = mapping(
            services.get(service_name), label=f"rendered {service_name} service"
        )
        require_exact_service_fields(
            selected[service_name], service_name=service_name
        )

    if selected["chummer-portal"].get("image") != EXPECTED_PORTAL_IMAGE:
        raise ValueError("rendered portal image tag is not canonical")
    if selected["chummer-portal-volume-init"].get("image") != EXPECTED_PORTAL_IMAGE:
        raise ValueError("rendered portal initializer image tag is not canonical")
    for service_name in (
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-import",
    ):
        if selected[service_name].get("image") != EXPECTED_TOOL_IMAGE:
            raise ValueError(f"rendered {service_name} image tag is not canonical")

    initializer = selected["chummer-portal-volume-init"]
    portal = selected["chummer-portal"]
    admin = selected["chummer-install-linking-postgres-admin"]
    importer = selected["chummer-install-linking-postgres-import"]
    runtime_uid, runtime_gid = require_runtime_identity(selected)

    if "build" in initializer:
        raise ValueError("rendered portal initializer must reuse the attested portal image")
    require_service_security(
        initializer,
        service_name="chummer-portal-volume-init",
        read_only=True,
        cap_add=["CHOWN", "SETUID", "SETGID"],
        pids_limit=32,
    )
    require_service_security(
        portal,
        service_name="chummer-portal",
        read_only=False,
    )
    require_exact_mapping(
        {field: portal.get(field) for field in EXPECTED_PORTAL_RESOURCES},
        expected=EXPECTED_PORTAL_RESOURCES,
        label="chummer-portal resource limits",
    )
    for service_name, service in (
        ("chummer-install-linking-postgres-admin", admin),
        ("chummer-install-linking-postgres-import", importer),
    ):
        require_service_security(
            service,
            service_name=service_name,
            read_only=True,
        )

    build_receipts = {
        "chummer-portal": require_exact_build(
            portal,
            service_name="chummer-portal",
            source_root=source_root,
            build_context=build_context,
            expected_target="",
            runtime_uid=runtime_uid,
            runtime_gid=runtime_gid,
        )
    }
    for service_name, service in (
        ("chummer-install-linking-postgres-admin", admin),
        ("chummer-install-linking-postgres-import", importer),
    ):
        build_receipts[service_name] = require_exact_build(
            service,
            service_name=service_name,
            source_root=source_root,
            build_context=build_context,
            expected_target=EXPECTED_TOOL_TARGET,
            runtime_uid=runtime_uid,
            runtime_gid=runtime_gid,
        )

    require_exact_sequence(
        initializer.get("entrypoint"),
        expected=["/usr/local/libexec/chummer/initialize-public-edge-volumes.sh"],
        label="portal initializer entrypoint",
    )
    if initializer.get("command") is not None:
        raise ValueError("rendered portal initializer command must use the image default")
    if initializer.get("restart") != "no":
        raise ValueError("rendered portal initializer restart policy drifted")
    if initializer.get("network_mode") != "none":
        raise ValueError("rendered portal initializer network mode must be none")
    require_empty_mapping(initializer.get("networks"), label="portal initializer networks")
    require_empty_sequence(initializer.get("profiles"), label="portal initializer profiles")
    require_empty_sequence(initializer.get("tmpfs"), label="portal initializer tmpfs")

    if portal.get("entrypoint") is not None or portal.get("command") is not None:
        raise ValueError("rendered portal command and entrypoint must use the image defaults")
    if portal.get("restart") != "unless-stopped":
        raise ValueError("rendered portal restart policy drifted")
    if portal.get("network_mode") is not None:
        raise ValueError("rendered portal must not override network mode")
    require_empty_sequence(portal.get("profiles"), label="portal profiles")
    require_empty_sequence(portal.get("tmpfs"), label="portal tmpfs")

    for service_name, service, command in (
        ("chummer-install-linking-postgres-admin", admin, ["validate"]),
        (
            "chummer-install-linking-postgres-import",
            importer,
            ["refuse-import-without-explicit-command"],
        ),
    ):
        require_exact_sequence(
            service.get("command"), expected=command, label=f"{service_name} command"
        )
        if service.get("entrypoint") is not None:
            raise ValueError(f"rendered {service_name} must use the image entrypoint")
        if service.get("restart") != "no":
            raise ValueError(f"rendered {service_name} restart policy drifted")
        if service.get("network_mode") is not None:
            raise ValueError(f"rendered {service_name} must not override network mode")
        require_exact_sequence(
            service.get("profiles"),
            expected=EXPECTED_TOOL_PROFILE,
            label=f"{service_name} profiles",
        )
        require_exact_sequence(
            service.get("tmpfs"),
            expected=EXPECTED_TOOL_TMPFS,
            label=f"{service_name} tmpfs",
        )

    require_exact_mounts(
        initializer,
        service_name="chummer-portal-volume-init",
        policies=[
            volume_mount_policy("chummer-run-api-state", "/app/state"),
            volume_mount_policy(
                "chummer-release-upload-sessions", "/release-upload-sessions"
            ),
            volume_mount_policy("chummer-windows-proof-store", "/windows-proof-store"),
            volume_mount_policy(
                "chummer-windows-proof-upload-sessions",
                "/windows-proof-upload-sessions",
            ),
            bind_mount_policy(EXPECTED_DOWNLOADS_SOURCE, "/downloads-source"),
        ],
    )
    require_exact_mounts(
        portal,
        service_name="chummer-portal",
        policies=[
            bind_mount_policy(str(overlay_root), "/app", read_only=True),
            volume_mount_policy("chummer-run-api-state", "/app/state"),
            opaque_read_only_bind_policy(
                "/run/chummer-secrets/data-protection-key-encryption.pfx"
            ),
            opaque_read_only_bind_policy(
                "/run/chummer-secrets/data-protection-key-encryption.password"
            ),
            opaque_read_only_bind_policy(
                "/run/chummer-secrets/install-linking-postgres-runtime.connection-string"
            ),
            bind_mount_policy(
                EXPECTED_FLEET_ARTIFACT_ROOT, "/fleet-artifacts", read_only=True
            ),
            bind_mount_policy(EXPECTED_DOWNLOADS_SOURCE, "/downloads-source"),
            volume_mount_policy(
                "chummer-release-upload-sessions", "/release-upload-sessions"
            ),
            volume_mount_policy("chummer-windows-proof-store", "/windows-proof-store"),
            volume_mount_policy(
                "chummer-windows-proof-upload-sessions",
                "/windows-proof-upload-sessions",
            ),
            bind_mount_policy(
                EXPECTED_HUB_PROOF_SOURCE,
                "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json",
                read_only=True,
            ),
            bind_mount_policy(
                EXPECTED_HUB_PROOF_SOURCE,
                "/app/wwwroot/proofs/mac-codex-release/"
                "HUB_LOCAL_RELEASE_PROOF.generated.json",
                read_only=True,
            ),
            bind_mount_policy(
                EXPECTED_FINAL_GOLD_SOURCE,
                "/proofs/FINAL_GOLD_JANITOR.generated.json",
                read_only=True,
            ),
        ],
    )
    require_exact_mounts(
        admin,
        service_name="chummer-install-linking-postgres-admin",
        policies=[
            opaque_read_only_bind_policy(
                "/run/chummer-secrets/install-linking-postgres-migrator.connection-string"
            )
        ],
    )
    require_exact_mounts(
        importer,
        service_name="chummer-install-linking-postgres-import",
        policies=[
            volume_mount_policy("chummer-run-api-state", "/app/state"),
            opaque_read_only_bind_policy(
                "/run/chummer-secrets/data-protection-key-encryption.pfx"
            ),
            opaque_read_only_bind_policy(
                "/run/chummer-secrets/data-protection-key-encryption.password"
            ),
            opaque_read_only_bind_policy(
                "/run/chummer-secrets/install-linking-postgres-runtime.connection-string"
            ),
        ],
    )

    require_exact_sequence(
        portal.get("ports"),
        expected=[
            {
                "mode": "ingress",
                "protocol": "tcp",
                "published": str(published_port),
                "target": 8080,
            }
        ],
        label="portal ports",
    )
    require_exact_mapping(
        portal.get("healthcheck"),
        expected=EXPECTED_PORTAL_HEALTHCHECK,
        label="portal healthcheck",
    )
    require_exact_mapping(
        portal.get("depends_on"),
        expected=EXPECTED_PORTAL_DEPENDENCIES,
        label="portal dependencies",
    )
    require_exact_sequence(
        portal.get("extra_hosts"),
        expected=["host.docker.internal=host-gateway"],
        label="portal extra_hosts",
    )
    require_exact_mapping(
        portal.get("networks"),
        expected={
            "public-origin": {"aliases": ["chummer-portal"]},
            "fleet-origin": {},
            "ea-origin": {},
        },
        label="portal networks",
    )
    for service_name, service in (
        ("chummer-portal-volume-init", initializer),
        ("chummer-install-linking-postgres-admin", admin),
        ("chummer-install-linking-postgres-import", importer),
    ):
        require_empty_sequence(service.get("ports"), label=f"{service_name} ports")
        if service.get("healthcheck") is not None:
            raise ValueError(f"rendered {service_name} must not define a healthcheck")
        require_empty_mapping(
            service.get("depends_on"), label=f"{service_name} dependencies"
        )
        require_empty_sequence(
            service.get("extra_hosts"), label=f"{service_name} extra_hosts"
        )
    for service_name, service in (
        ("chummer-install-linking-postgres-admin", admin),
        ("chummer-install-linking-postgres-import", importer),
    ):
        require_exact_mapping(
            service.get("networks"),
            expected={"public-origin": {}},
            label=f"{service_name} networks",
        )

    environment = mapping(portal.get("environment"), label="rendered portal environment")
    for key in PROXY_GATE_KEYS:
        if environment.get(key) != "false":
            raise ValueError(f"rendered {key} must be the literal string false")
    for key, expected_value in EXPECTED_PORTAL_ENVIRONMENT.items():
        if key in PROXY_GATE_KEYS:
            continue
        if environment.get(key) != expected_value:
            raise ValueError(f"rendered portal {key} is not the canonical literal value")
    for key in FORBIDDEN_PROXY_KEYS:
        if key in environment:
            raise ValueError(f"rendered portal contains forbidden retired proxy key {key}")
    for key in environment:
        if (
            key.startswith("CHUMMER_PUBLIC_PLAY_PROXY_")
            or key.startswith("CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_")
        ) and key not in PROXY_GATE_KEYS:
            raise ValueError(f"rendered portal contains unrecognized proxy key {key}")

    admin_environment = mapping(
        admin.get("environment"), label="rendered PostgreSQL admin environment"
    )
    if set(admin_environment) != {
        "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE",
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
    }:
        raise ValueError("rendered PostgreSQL admin environment fields drifted")
    if admin_environment.get("CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE") != (
        "/run/chummer-secrets/install-linking-postgres-migrator.connection-string"
    ):
        raise ValueError("rendered PostgreSQL admin credential target drifted")
    runtime_role = admin_environment.get("CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE")
    if (
        not isinstance(runtime_role, str)
        or not runtime_role
        or len(runtime_role) > 128
        or any(ord(character) < 32 for character in runtime_role)
    ):
        raise ValueError("rendered PostgreSQL runtime role must be a bounded literal")

    require_exact_mapping(
        importer.get("environment"),
        expected={
            "ASPNETCORE_ENVIRONMENT": "Production",
            "CHUMMER_DATA_PROTECTION_KEYS_PATH": "/app/state/data-protection-keys",
            "CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH": (
                "/run/chummer-secrets/data-protection-key-encryption.pfx"
            ),
            "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE": (
                "/run/chummer-secrets/data-protection-key-encryption.password"
            ),
            "CHUMMER_INSTALL_LINKING_STORE_PATH": (
                "/app/state/install-linking/install-linking-store.json"
            ),
            "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE": (
                "/run/chummer-secrets/install-linking-postgres-runtime.connection-string"
            ),
        },
        label="PostgreSQL import environment",
    )

    return {
        "contractName": "chummer.public_edge_compose_runtime_attestation.v1",
        "status": "pass",
        "projectName": project_name,
        "portalImage": EXPECTED_PORTAL_IMAGE,
        "toolImage": EXPECTED_TOOL_IMAGE,
        "sourceRoot": str(source_root),
        "buildContext": str(build_context),
        "overlayRoot": str(overlay_root),
        "overlayReadOnly": True,
        "publishedPort": published_port,
        "proxyGates": {key: "false" for key in PROXY_GATE_KEYS},
        "retiredProxyKeysAbsent": True,
        "runtimePolicyChecks": [
            "closed-service-fields",
            "identity",
            "security",
            "resource-limits",
            "command-entrypoint",
            "mounts",
            "ports-health",
            "dependency-network",
            "profiles-tmpfs-restart",
            "critical-environment",
        ],
        "mountCounts": {
            service_name: len(selected[service_name]["volumes"])
            for service_name in required_services
        },
        "builds": build_receipts,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Compose runtime attestation output must not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        rendered = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def existing_absolute_directory(value: str, *, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be an existing directory")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Attest the secret-bearing rendered public-edge Compose runtime from stdin."
    )
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--build-context", required=True)
    parser.add_argument("--overlay-root", required=True)
    parser.add_argument("--published-port", required=True, type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.project_name) is None:
        parser.error("project name must be a safe literal")
    if not 1 <= args.published_port <= 65535:
        parser.error("published port must be in the range 1..65535")
    try:
        source_root = existing_absolute_directory(args.source_root, label="source root")
        build_context = existing_absolute_directory(args.build_context, label="build context")
        overlay_root = Path(args.overlay_root)
        if not overlay_root.is_absolute():
            raise ValueError("overlay root must be absolute")
        overlay_root = Path(os.path.normpath(overlay_root))
        receipt = validate_runtime(
            read_rendered_compose(),
            project_name=args.project_name,
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            published_port=args.published_port,
        )
        atomic_write_json(args.output, receipt)
    except (OSError, ValueError, StrictJsonContractError) as exc:
        print(f"public_edge_compose_runtime_attestation: {exc}", file=sys.stderr)
        return 1
    print("public_edge_compose_runtime_attestation:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
