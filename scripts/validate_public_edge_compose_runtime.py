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


def mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


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
    checks = {
        "context": str(build.get("context") or "") == str(build_context),
        "dockerfile": str(build.get("dockerfile") or "") == expected_dockerfile,
        "additionalContexts": contexts == expected_contexts,
        "target": actual_target == expected_target,
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

    build_receipts = {
        "chummer-portal": require_exact_build(
            selected["chummer-portal"],
            service_name="chummer-portal",
            source_root=source_root,
            build_context=build_context,
            expected_target="",
        )
    }
    for service_name in (
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-import",
    ):
        build_receipts[service_name] = require_exact_build(
            selected[service_name],
            service_name=service_name,
            source_root=source_root,
            build_context=build_context,
            expected_target=EXPECTED_TOOL_TARGET,
        )

    volumes = selected["chummer-portal"].get("volumes")
    if not isinstance(volumes, list):
        raise ValueError("rendered portal volumes must be a list")
    app_mounts = [
        item
        for item in volumes
        if isinstance(item, dict) and item.get("target") == "/app"
    ]
    if len(app_mounts) != 1:
        raise ValueError("rendered portal must contain exactly one /app mount")
    app_mount = app_mounts[0]
    if (
        app_mount.get("type") != "bind"
        or app_mount.get("source") != str(overlay_root)
        or app_mount.get("read_only") is not True
    ):
        raise ValueError("rendered portal /app mount is not the canonical read-only overlay")

    ports = selected["chummer-portal"].get("ports")
    canonical_ports = [
        item
        for item in ports or []
        if isinstance(item, dict)
        and item.get("target") == 8080
        and str(item.get("published") or "") == str(published_port)
        and item.get("protocol") == "tcp"
    ]
    if len(canonical_ports) != 1 or len(ports or []) != 1:
        raise ValueError("rendered portal port binding is not the canonical runtime binding")

    environment = mapping(
        selected["chummer-portal"].get("environment"),
        label="rendered portal environment",
    )
    for key in PROXY_GATE_KEYS:
        if environment.get(key) != "false":
            raise ValueError(f"rendered {key} must be the literal string false")
    for key in FORBIDDEN_PROXY_KEYS:
        if key in environment:
            raise ValueError(f"rendered portal contains forbidden retired proxy key {key}")

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
