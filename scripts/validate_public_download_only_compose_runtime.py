#!/usr/bin/env python3
"""Attest the rendered public-download-only Compose runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any


MAX_COMPOSE_BYTES = 16 * 1024 * 1024
CONTRACT_NAME = "chummer.public-download-only-compose-runtime-attestation/v1"
MATERIALIZATION_CONTRACT_NAME = (
    "chummer.public-download-only-compose-materialization/v1"
)
CANONICAL_PROJECT_NAME = "chummer6-hub"
CANONICAL_PUBLISHED_PORT = 8091
CANONICAL_PORTAL_USER = "1654:1654"
CANONICAL_SOURCE_NAMES = (
    "docker-compose.public-edge.yml",
    "docker-compose.public-downloads.yml",
)
CANONICAL_APP_OVERLAY_SOURCE = (
    "/docker/chummercomplete/chummer.run-services/"
    ".state/public-edge-portal-overlay/app"
)
CANONICAL_PROJECTION_SOURCE = (
    "/docker/chummercomplete/chummer.run-services/.codex-studio/published"
)
CANONICAL_DOWNLOADS_SOURCE = (
    "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads"
)
CANONICAL_FLEET_SOURCE = "/docker/fleet/.codex-studio/published"
CANONICAL_FINAL_GOLD_SOURCE = (
    "/docker/chummercomplete/chummer.run-services/.codex-studio/"
    "published/FINAL_GOLD_JANITOR.generated.json"
)
POSTURES = {
    "initial-release-shelf-public-download-cutover": {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    },
    "initial-release-shelf-public-download-cutover-recover": {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    },
    "initial-release-shelf-public-download-steady": {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    },
}
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40}$")
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
EXPECTED_PORTAL_KEYS = {
    "cap_drop",
    "command",
    "cpu_shares",
    "cpus",
    "entrypoint",
    "environment",
    "healthcheck",
    "image",
    "mem_limit",
    "networks",
    "ports",
    "profiles",
    "restart",
    "security_opt",
    "ulimits",
    "user",
    "volumes",
}
EXPECTED_ROOT_VOLUMES = {
    "chummer-release-upload-sessions": {
        "name": "chummer6-hub_chummer-release-upload-sessions"
    },
    "chummer-run-api-state": {
        "name": "chummer6-hub_chummer-run-api-state"
    },
    "chummer-windows-proof-store": {
        "name": "chummer6-hub_chummer-windows-proof-store"
    },
    "chummer-windows-proof-upload-sessions": {
        "name": "chummer6-hub_chummer-windows-proof-upload-sessions"
    },
}
EXPECTED_ROOT_NETWORKS = {
    "ea-origin": {
        "external": True,
        "ipam": {},
        "name": "ea_default",
    },
    "fleet-origin": {
        "external": True,
        "ipam": {},
        "name": "codex-fleet-net",
    },
    "public-origin": {
        "external": True,
        "ipam": {},
        "name": "chummer5a_default",
    },
}
CRITICAL_ENVIRONMENT = {
    "ASPNETCORE_ENVIRONMENT": "Production",
    "CHUMMER_DOWNLOADS_SOURCE_ROOT": "/downloads-source",
    "CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS": "false",
    "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_REQUIRED": "true",
    "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT": "/public-projection",
    "CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED": "false",
    "CHUMMER_WINDOWS_PROOF_UPLOAD_ENABLED": "false",
}


def mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a sequence")
    return value


def contains_postgres_material(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            contains_postgres_material(key)
            or contains_postgres_material(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_postgres_material(item) for item in value)
    return isinstance(value, str) and (
        "install-linking-postgres" in value.lower()
        or "chummer_install_linking_postgres" in value.lower()
    )


def read_payload() -> tuple[dict[str, Any], str]:
    raw = sys.stdin.buffer.read(MAX_COMPOSE_BYTES + 1)
    if not raw or len(raw) > MAX_COMPOSE_BYTES:
        raise ValueError("rendered Compose JSON is empty or oversized")
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("rendered Compose JSON is invalid") from exc
    return (
        mapping(payload, "rendered Compose document"),
        hashlib.sha256(raw).hexdigest(),
    )


def read_owned_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError(f"{label} metadata is unsafe")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    return mapping(payload, label), raw


def validate_materialization_authority(
    receipt_path: Path,
    compose_path: Path,
    *,
    operation: str,
    source_root: Path,
    source_head: str,
    candidate_image_id: str,
) -> dict[str, Any]:
    if SOURCE_HEAD_PATTERN.fullmatch(source_head) is None:
        raise ValueError("expected source HEAD is invalid")
    receipt, _ = read_owned_json(
        receipt_path,
        "Compose materialization receipt",
    )
    compose, compose_raw = read_owned_json(
        compose_path,
        "materialized Compose document",
    )
    expected_receipt_fields = {
        "contractName",
        "status",
        "operation",
        "sourceRoot",
        "sourceHead",
        "baseComposeSource",
        "baseComposeSourceSha256",
        "profileSource",
        "profileSourceSha256",
        "candidateImageId",
        "composeSha256",
    }
    if set(receipt) != expected_receipt_fields:
        raise ValueError("Compose materialization receipt fields drifted")
    try:
        canonical_source_root = source_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("expected source root is unavailable") from exc
    expected_base = canonical_source_root / CANONICAL_SOURCE_NAMES[0]
    expected_profile = canonical_source_root / CANONICAL_SOURCE_NAMES[1]
    if (
        receipt.get("contractName") != MATERIALIZATION_CONTRACT_NAME
        or receipt.get("status") != "pass"
        or receipt.get("operation") != operation
        or receipt.get("sourceRoot") != str(canonical_source_root)
        or receipt.get("sourceHead") != source_head
        or receipt.get("baseComposeSource") != str(expected_base)
        or receipt.get("profileSource") != str(expected_profile)
        or receipt.get("candidateImageId") != candidate_image_id
    ):
        raise ValueError("Compose materialization authority drifted")
    for path, field in (
        (expected_base, "baseComposeSourceSha256"),
        (expected_profile, "profileSourceSha256"),
    ):
        try:
            observed = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError("revision-bound Compose source is unavailable") from exc
        if receipt.get(field) != observed:
            raise ValueError("revision-bound Compose source digest drifted")
    compose_sha256 = hashlib.sha256(compose_raw).hexdigest()
    if (
        SHA256_PATTERN.fullmatch(str(receipt.get("composeSha256", ""))) is None
        or receipt.get("composeSha256") != compose_sha256
    ):
        raise ValueError("materialized Compose digest drifted")
    materialized_services = mapping(
        compose.get("services"),
        "materialized Compose services",
    )
    if (
        set(materialized_services) != {"chummer-portal"}
        or mapping(
            materialized_services.get("chummer-portal"),
            "materialized portal",
        ).get("image")
        != candidate_image_id
    ):
        raise ValueError("materialized Compose candidate authority drifted")
    return {
        "sourceRoot": str(canonical_source_root),
        "sourceHead": source_head,
        "baseComposeSourceSha256": receipt["baseComposeSourceSha256"],
        "profileSourceSha256": receipt["profileSourceSha256"],
        "materializedComposeSha256": compose_sha256,
    }


def expected_mounts(
    *,
    certificate_source: str,
    certificate_password_source: str,
    runtime_proof_source: str,
) -> list[dict[str, Any]]:
    return [
        {
            "bind": {},
            "read_only": True,
            "source": CANONICAL_APP_OVERLAY_SOURCE,
            "target": "/app",
            "type": "bind",
        },
        {
            "source": "chummer-run-api-state",
            "target": "/app/state",
            "type": "volume",
            "volume": {},
        },
        {
            "bind": {},
            "read_only": True,
            "source": certificate_source,
            "target": "/run/chummer-secrets/data-protection-key-encryption.pfx",
            "type": "bind",
        },
        {
            "bind": {},
            "read_only": True,
            "source": certificate_password_source,
            "target": (
                "/run/chummer-secrets/"
                "data-protection-key-encryption.password"
            ),
            "type": "bind",
        },
        {
            "bind": {},
            "read_only": True,
            "source": CANONICAL_FLEET_SOURCE,
            "target": "/fleet-artifacts",
            "type": "bind",
        },
        {
            "bind": {},
            "source": CANONICAL_DOWNLOADS_SOURCE,
            "target": "/downloads-source",
            "type": "bind",
        },
        {
            "source": "chummer-release-upload-sessions",
            "target": "/release-upload-sessions",
            "type": "volume",
            "volume": {},
        },
        {
            "source": "chummer-windows-proof-store",
            "target": "/windows-proof-store",
            "type": "volume",
            "volume": {},
        },
        {
            "source": "chummer-windows-proof-upload-sessions",
            "target": "/windows-proof-upload-sessions",
            "type": "volume",
            "volume": {},
        },
        {
            "bind": {},
            "read_only": True,
            "source": CANONICAL_PROJECTION_SOURCE,
            "target": "/public-projection",
            "type": "bind",
        },
        {
            "bind": {},
            "read_only": True,
            "source": runtime_proof_source,
            "target": "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json",
            "type": "bind",
        },
        {
            "bind": {},
            "read_only": True,
            "source": CANONICAL_FINAL_GOLD_SOURCE,
            "target": "/proofs/FINAL_GOLD_JANITOR.generated.json",
            "type": "bind",
        },
    ]


def validate(
    payload: dict[str, Any],
    *,
    operation: str,
    candidate_image_id: str,
    certificate_source: str,
    certificate_password_source: str,
    runtime_proof_source: str,
    materialization: dict[str, Any],
    rendered_compose_sha256: str,
) -> dict[str, Any]:
    if set(payload) != {"name", "networks", "services", "volumes"}:
        raise ValueError("rendered Compose root closure drifted")
    if payload.get("name") != CANONICAL_PROJECT_NAME:
        raise ValueError("rendered Compose project authority drifted")
    if IMAGE_ID_PATTERN.fullmatch(candidate_image_id) is None:
        raise ValueError("candidate image is not an immutable Docker image ID")
    services = mapping(payload.get("services"), "rendered services")
    if set(services) != {"chummer-portal"}:
        raise ValueError("rendered runtime is not the exact portal-only closure")
    if contains_postgres_material(payload):
        raise ValueError("rendered runtime retained PostgreSQL material")
    portal = mapping(services.get("chummer-portal"), "rendered portal")
    if set(portal) != EXPECTED_PORTAL_KEYS:
        raise ValueError("rendered portal field closure drifted")
    if portal.get("image") != candidate_image_id:
        raise ValueError("rendered portal candidate image is not pinned")
    if "build" in portal:
        raise ValueError("public-download-only runtime must be build-free")
    if portal.get("user") != CANONICAL_PORTAL_USER:
        raise ValueError("rendered portal runtime identity drifted")
    if portal.get("command") is not None or portal.get("entrypoint") is not None:
        raise ValueError("rendered portal process authority drifted")
    if portal.get("cap_drop") != ["ALL"]:
        raise ValueError("rendered portal capability drop drifted")
    if portal.get("security_opt") != ["no-new-privileges:true"]:
        raise ValueError("rendered portal security policy drifted")

    environment = mapping(portal.get("environment"), "rendered portal environment")
    if any(name.startswith("CHUMMER_INSTALL_LINKING") for name in environment):
        raise ValueError("rendered portal retained InstallLinking configuration")
    if environment.get("CHUMMER_PUBLIC_DOWNLOAD_ONLY") != "true":
        raise ValueError("rendered portal did not select public-download-only mode")
    for name, expected in CRITICAL_ENVIRONMENT.items():
        if environment.get(name) != expected:
            raise ValueError(f"rendered portal {name} authority drifted")
    for name, expected in POSTURES[operation].items():
        if environment.get(name) != expected:
            raise ValueError(f"rendered portal {name} posture drifted")

    if portal.get("extra_hosts") not in (None, []):
        raise ValueError("rendered portal host mapping is not the closed posture")
    mounts = sequence(portal.get("volumes"), "rendered portal mounts")
    if mounts != expected_mounts(
        certificate_source=certificate_source,
        certificate_password_source=certificate_password_source,
        runtime_proof_source=runtime_proof_source,
    ):
        raise ValueError("rendered portal mount authority drifted")

    if portal.get("healthcheck") != EXPECTED_HEALTHCHECK:
        raise ValueError("rendered portal serving-only healthcheck drifted")
    if "depends_on" in portal:
        raise ValueError("rendered portal retained service dependencies")
    if portal.get("profiles") != ["public-downloads"]:
        raise ValueError("rendered portal profile selector drifted")
    if portal.get("networks") != {
        "public-origin": {"aliases": ["chummer-portal"]},
        "fleet-origin": {},
        "ea-origin": {},
    }:
        raise ValueError("rendered portal network contract drifted")
    if mapping(payload.get("networks"), "rendered networks") != EXPECTED_ROOT_NETWORKS:
        raise ValueError("rendered external network authority drifted")
    if mapping(payload.get("volumes"), "rendered volumes") != EXPECTED_ROOT_VOLUMES:
        raise ValueError("rendered named-volume authority drifted")
    if portal.get("ports") != [
        {
            "mode": "ingress",
            "protocol": "tcp",
            "published": str(CANONICAL_PUBLISHED_PORT),
            "target": 8080,
        }
    ]:
        raise ValueError("rendered portal published port drifted")
    return {
        "contractName": CONTRACT_NAME,
        "status": "pass",
        "operation": operation,
        "runtimeProfile": "public-download-only",
        "projectName": CANONICAL_PROJECT_NAME,
        "portalImageId": candidate_image_id,
        "toolImage": None,
        "postgresServicesAbsent": True,
        "postgresEnvironmentAbsent": True,
        "postgresMountsAbsent": True,
        "postgresHostMappingAbsent": True,
        "portalBuildAbsent": True,
        "publicDownloadsHealthcheck": True,
        "releaseShelfPosture": POSTURES[operation],
        "mountCount": len(mounts),
        "publishedPort": CANONICAL_PUBLISHED_PORT,
        "renderedComposeSha256": rendered_compose_sha256,
        **materialization,
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
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--materialized-compose", type=Path, required=True)
    parser.add_argument("--materialization-receipt", type=Path, required=True)
    parser.add_argument("--candidate-image-id", required=True)
    parser.add_argument("--certificate-source", required=True)
    parser.add_argument("--certificate-password-source", required=True)
    parser.add_argument("--runtime-proof-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        for label, value in (
            ("certificate source", args.certificate_source),
            ("certificate password source", args.certificate_password_source),
            ("runtime proof source", args.runtime_proof_source),
        ):
            if not Path(value).is_absolute() or "\x00" in value:
                raise ValueError(f"{label} is not an absolute path")
        materialization = validate_materialization_authority(
            args.materialization_receipt,
            args.materialized_compose,
            operation=args.operation,
            source_root=args.source_root,
            source_head=args.source_head,
            candidate_image_id=args.candidate_image_id,
        )
        payload, rendered_compose_sha256 = read_payload()
        receipt = validate(
            payload,
            operation=args.operation,
            candidate_image_id=args.candidate_image_id,
            certificate_source=args.certificate_source,
            certificate_password_source=args.certificate_password_source,
            runtime_proof_source=args.runtime_proof_source,
            materialization=materialization,
            rendered_compose_sha256=rendered_compose_sha256,
        )
        atomic_write(args.output, receipt)
    except (OSError, ValueError) as exc:
        print(f"public_download_only_compose_runtime: {exc}", file=sys.stderr)
        return 1
    print("public_download_only_compose_runtime:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
