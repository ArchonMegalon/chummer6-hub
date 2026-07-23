#!/usr/bin/env python3
"""Attest the rendered public-download-only Compose runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any


MAX_COMPOSE_BYTES = 16 * 1024 * 1024
CONTRACT_NAME = "chummer.public-download-only-compose-runtime-attestation/v1"
POSTURES = {
    "initial-release-shelf-public-download-cutover": {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "false",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "true",
    },
    "initial-release-shelf-public-download-cutover-recover": {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "false",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    },
    "initial-release-shelf-public-download-steady": {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    },
}
IMAGE_PATTERN = re.compile(
    r"^chummer-run-api:public-download-[0-9a-f]{16}-[a-z0-9]{8}$"
)
REMOVED_SERVICES = {
    "chummer-install-linking-postgres-admin",
    "chummer-install-linking-postgres-import",
    "chummer-install-linking-postgres-import-presence-proof",
    "chummer-install-linking-postgres-runtime-proof",
}
EXPECTED_HEALTHCHECK = {
    "test": [
        "CMD",
        "dotnet",
        "/app/loopback-probe/Chummer.Run.LoopbackProbe.dll",
        "/api/ready/public-downloads",
    ],
    "interval": "15s",
    "timeout": "5s",
    "retries": 5,
    "start_period": "45s",
}
EXPECTED_DEPENDENCIES = {
    "chummer-portal-volume-init": {
        "condition": "service_completed_successfully",
        "required": True,
    },
    "chummer-public-blazor": {"condition": "service_healthy", "required": True},
    "chummer-run-identity": {"condition": "service_healthy", "required": True},
    "support-progress-mock": {"condition": "service_healthy", "required": True},
}
EXPECTED_MOUNT_TARGETS = {
    "/app",
    "/app/state",
    "/downloads-source",
    "/fleet-artifacts",
    "/proofs/FINAL_GOLD_JANITOR.generated.json",
    "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "/public-projection",
    "/release-upload-sessions",
    "/run/chummer-secrets/data-protection-key-encryption.password",
    "/run/chummer-secrets/data-protection-key-encryption.pfx",
    "/windows-proof-store",
    "/windows-proof-upload-sessions",
}


def mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a sequence")
    return value


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_COMPOSE_BYTES + 1)
    if not raw or len(raw) > MAX_COMPOSE_BYTES:
        raise ValueError("rendered Compose JSON is empty or oversized")
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("rendered Compose JSON is invalid") from exc
    return mapping(payload, "rendered Compose document")


def validate(
    payload: dict[str, Any],
    *,
    operation: str,
    project_name: str,
    candidate_image: str,
    published_port: int,
) -> dict[str, Any]:
    if payload.get("name") != project_name:
        raise ValueError("rendered Compose project authority drifted")
    if IMAGE_PATTERN.fullmatch(candidate_image) is None:
        raise ValueError("candidate image tag is not a public-download unique tag")
    services = mapping(payload.get("services"), "rendered services")
    if REMOVED_SERVICES.intersection(services):
        raise ValueError("rendered runtime retained a PostgreSQL service")
    portal = mapping(services.get("chummer-portal"), "rendered portal")
    initializer = mapping(
        services.get("chummer-portal-volume-init"),
        "rendered portal initializer",
    )
    if portal.get("image") != candidate_image:
        raise ValueError("rendered portal candidate image is not pinned")
    if initializer.get("image") != candidate_image:
        raise ValueError("rendered initializer candidate image is not pinned")
    if "build" in portal or "build" in initializer:
        raise ValueError("public-download-only runtime must be build-free")
    if portal.get("user") is None or portal.get("user") == "0:0":
        raise ValueError("rendered portal runtime identity must be nonroot")
    if initializer.get("user") != "0:0":
        raise ValueError("rendered initializer identity drifted")
    for service_name, service in (
        ("portal", portal),
        ("initializer", initializer),
    ):
        if service.get("privileged", False) is not False:
            raise ValueError(f"rendered {service_name} became privileged")
        if service.get("cap_drop") != ["ALL"]:
            raise ValueError(f"rendered {service_name} capability drop drifted")
        if service.get("security_opt") != ["no-new-privileges:true"]:
            raise ValueError(f"rendered {service_name} security policy drifted")

    environment = mapping(portal.get("environment"), "rendered portal environment")
    if any(name.startswith("CHUMMER_INSTALL_LINKING") for name in environment):
        raise ValueError("rendered portal retained InstallLinking configuration")
    if environment.get("CHUMMER_PUBLIC_DOWNLOAD_ONLY") != "true":
        raise ValueError("rendered portal did not select public-download-only mode")
    for name, expected in POSTURES[operation].items():
        if environment.get(name) != expected:
            raise ValueError(f"rendered portal {name} posture drifted")

    if portal.get("extra_hosts") != ["host.docker.internal=host-gateway"]:
        raise ValueError("rendered portal host mapping is not the closed posture")
    mounts = sequence(portal.get("volumes"), "rendered portal mounts")
    targets: set[str] = set()
    for item in mounts:
        mount = mapping(item, "rendered portal mount")
        target = mount.get("target")
        if not isinstance(target, str) or target in targets:
            raise ValueError("rendered portal mount targets are invalid")
        targets.add(target)
        serialized = json.dumps(mount, sort_keys=True).lower()
        if "install-linking" in serialized or "postgres" in serialized:
            raise ValueError("rendered portal retained an InstallLinking mount")
    if targets != EXPECTED_MOUNT_TARGETS:
        raise ValueError("rendered portal mount closure drifted")

    if portal.get("healthcheck") != EXPECTED_HEALTHCHECK:
        raise ValueError("rendered portal serving-only healthcheck drifted")
    if portal.get("depends_on") != EXPECTED_DEPENDENCIES:
        raise ValueError("rendered portal dependency contract drifted")
    if portal.get("networks") != {
        "public-origin": {"aliases": ["chummer-portal"]},
        "fleet-origin": {},
        "ea-origin": {},
    }:
        raise ValueError("rendered portal network contract drifted")
    if portal.get("ports") != [
        {
            "mode": "ingress",
            "protocol": "tcp",
            "published": str(published_port),
            "target": 8080,
        }
    ]:
        raise ValueError("rendered portal published port drifted")
    return {
        "contractName": CONTRACT_NAME,
        "status": "pass",
        "operation": operation,
        "runtimeProfile": "public-download-only",
        "projectName": project_name,
        "portalImage": candidate_image,
        "toolImage": None,
        "postgresServicesAbsent": True,
        "postgresEnvironmentAbsent": True,
        "postgresMountsAbsent": True,
        "postgresHostMappingAbsent": True,
        "portalBuildAbsent": True,
        "publicDownloadsHealthcheck": True,
        "releaseShelfPosture": POSTURES[operation],
        "mountCount": len(mounts),
        "publishedPort": published_port,
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("attestation output must not be a symlink")
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=tuple(POSTURES), required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--published-port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.published_port <= 65535:
            raise ValueError("published port is outside the TCP range")
        receipt = validate(
            read_payload(),
            operation=args.operation,
            project_name=args.project_name,
            candidate_image=args.candidate_image,
            published_port=args.published_port,
        )
        atomic_write(args.output, receipt)
    except (OSError, ValueError) as exc:
        print(f"public_download_only_compose_runtime: {exc}", file=sys.stderr)
        return 1
    print("public_download_only_compose_runtime:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
