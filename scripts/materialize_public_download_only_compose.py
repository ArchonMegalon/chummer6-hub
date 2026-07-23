#!/usr/bin/env python3
"""Derive the closed public-download-only runtime Compose document."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

import yaml


CONTRACT_NAME = "chummer.public-download-only-compose-materialization/v1"
PUBLIC_DOWNLOAD_IMAGE = re.compile(
    r"^chummer-run-api:public-download-[0-9a-f]{16}-[a-z0-9]{8}$"
)
POSTURES = {
    "initial-release-shelf-public-download-cutover": ("false", "true"),
    "initial-release-shelf-public-download-cutover-recover": ("false", "false"),
    "initial-release-shelf-public-download-steady": ("true", "false"),
}
REMOVED_SERVICES = {
    "chummer-install-linking-postgres-admin",
    "chummer-install-linking-postgres-import",
    "chummer-install-linking-postgres-import-presence-proof",
    "chummer-install-linking-postgres-runtime-proof",
}
REMOVED_PORTAL_ENVIRONMENT = {
    "CHUMMER_INSTALL_LINKING_STORE_PATH",
    "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE",
    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE",
    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST",
    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT",
    "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
}
REMOVED_PORTAL_MOUNT_TARGETS = {
    "/run/chummer-secrets/install-linking-postgres-runtime.connection-string",
    "/run/chummer-secrets/install-linking-postgres-server-ca.pem",
}
EXPECTED_BASE_HEALTHCHECK = {
    "test": [
        "CMD",
        "dotnet",
        "/app/loopback-probe/Chummer.Run.LoopbackProbe.dll",
        "/api/ready",
    ],
    "interval": "15s",
    "timeout": "5s",
    "retries": 5,
    "start_period": "45s",
}
PUBLIC_DOWNLOAD_HEALTHCHECK = {
    **EXPECTED_BASE_HEALTHCHECK,
    "test": [
        "CMD",
        "dotnet",
        "/app/loopback-probe/Chummer.Run.LoopbackProbe.dll",
        "/api/ready/public-downloads",
    ],
}


def require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def mount_target(value: object) -> str:
    if isinstance(value, str):
        parts = value.rsplit(":", 2)
        return parts[-2] if len(parts) == 3 and parts[-1] == "ro" else parts[-1]
    if isinstance(value, dict):
        target = value.get("target")
        return target if isinstance(target, str) else ""
    return ""


def _contains_install_linking_postgres(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            _contains_install_linking_postgres(key)
            or _contains_install_linking_postgres(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_install_linking_postgres(item) for item in value)
    return isinstance(value, str) and "install-linking-postgres" in value.lower()


def materialize(
    source: Path,
    *,
    candidate_image: str,
    operation: str,
) -> dict[str, Any]:
    if PUBLIC_DOWNLOAD_IMAGE.fullmatch(candidate_image) is None:
        raise ValueError("candidate image is not a unique public-download tag")
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("canonical Compose source is unavailable or invalid") from exc
    root = require_mapping(payload, "Compose document")
    services = require_mapping(root.get("services"), "Compose services")
    missing_services = REMOVED_SERVICES.difference(services)
    if missing_services:
        raise ValueError("canonical Compose source lost a PostgreSQL service")
    for service_name in REMOVED_SERVICES:
        del services[service_name]

    portal = require_mapping(services.get("chummer-portal"), "portal service")
    initializer = require_mapping(
        services.get("chummer-portal-volume-init"),
        "portal initializer service",
    )
    if portal.get("image") != "chummer-run-api:local" or "build" not in portal:
        raise ValueError("canonical portal image/build contract drifted")
    if initializer.get("image") != "chummer-run-api:local":
        raise ValueError("canonical portal initializer image contract drifted")
    portal["image"] = candidate_image
    initializer["image"] = candidate_image
    del portal["build"]

    environment = require_mapping(
        portal.get("environment"),
        "portal environment",
    )
    if not REMOVED_PORTAL_ENVIRONMENT.issubset(environment):
        raise ValueError("canonical portal PostgreSQL environment contract drifted")
    for name in REMOVED_PORTAL_ENVIRONMENT:
        del environment[name]
    layout_required, migration_allowed = POSTURES[operation]
    environment["CHUMMER_PUBLIC_DOWNLOAD_ONLY"] = "true"
    environment["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] = layout_required
    environment["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = (
        migration_allowed
    )

    extra_hosts = portal.get("extra_hosts")
    if (
        not isinstance(extra_hosts, list)
        or len(extra_hosts) != 2
        or extra_hosts[0] != "host.docker.internal:host-gateway"
        or "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME" not in str(extra_hosts[1])
        or "CHUMMER_INSTALL_LINKING_POSTGRES_IP" not in str(extra_hosts[1])
    ):
        raise ValueError("canonical portal PostgreSQL host mapping contract drifted")
    portal["extra_hosts"] = ["host.docker.internal:host-gateway"]

    volumes = portal.get("volumes")
    if not isinstance(volumes, list):
        raise ValueError("canonical portal volumes must be a sequence")
    observed_removed_targets = {
        mount_target(item)
        for item in volumes
        if mount_target(item) in REMOVED_PORTAL_MOUNT_TARGETS
    }
    if observed_removed_targets != REMOVED_PORTAL_MOUNT_TARGETS:
        raise ValueError("canonical portal PostgreSQL mount contract drifted")
    portal["volumes"] = [
        item
        for item in volumes
        if mount_target(item) not in REMOVED_PORTAL_MOUNT_TARGETS
    ]

    if portal.get("healthcheck") != EXPECTED_BASE_HEALTHCHECK:
        raise ValueError("canonical portal healthcheck contract drifted")
    portal["healthcheck"] = PUBLIC_DOWNLOAD_HEALTHCHECK
    if _contains_install_linking_postgres(root):
        raise ValueError(
            "public-download-only Compose projection retained PostgreSQL material"
        )
    return root


def atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError("public-download-only Compose output must be new")
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
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError("public-download-only Compose output metadata is unsafe")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--operation", choices=tuple(POSTURES), required=True)
    args = parser.parse_args(argv)
    try:
        projected = materialize(
            args.source,
            candidate_image=args.candidate_image,
            operation=args.operation,
        )
        body = yaml.safe_dump(
            projected,
            allow_unicode=False,
            default_flow_style=False,
            sort_keys=False,
        ).encode("utf-8")
        atomic_write(args.output, body)
        receipt = {
            "contractName": CONTRACT_NAME,
            "status": "pass",
            "operation": args.operation,
            "candidateImage": args.candidate_image,
            "composeSha256": hashlib.sha256(body).hexdigest(),
        }
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        print(f"public_download_only_compose: {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
