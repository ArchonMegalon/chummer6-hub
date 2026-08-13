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
INCUMBENT_PROJECT_NAME = "chummer6-hub"
CANDIDATE_BIND_ADDRESS = "172.17.0.1"
CANDIDATE_PUBLISHED_PORT = 18091
CANONICAL_PORTAL_USER = "1654:1654"
CANONICAL_INITIALIZER_USER = "0:0"
INITIALIZER_SERVICE = "chummer-public-download-init"
PORTAL_SERVICE = "chummer-portal"
CANONICAL_SOURCE_NAMES = (
    "docker-compose.public-edge.yml",
    "docker-compose.public-downloads.yml",
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
PROJECTION_SNAPSHOT_ID_PATTERN = re.compile(
    r"^public-projection-[0-9a-f]{64}$"
)
SOURCE_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VOLUME_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
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
    "depends_on",
    "entrypoint",
    "environment",
    "healthcheck",
    "image",
    "mem_limit",
    "network_mode",
    "ports",
    "profiles",
    "restart",
    "security_opt",
    "ulimits",
    "user",
    "volumes",
}
EXPECTED_INITIALIZER_KEYS = {
    "cap_add",
    "cap_drop",
    "command",
    "entrypoint",
    "environment",
    "image",
    "network_mode",
    "pids_limit",
    "profiles",
    "read_only",
    "restart",
    "security_opt",
    "ulimits",
    "user",
    "volumes",
}
LOGICAL_VOLUMES = {
    "public-download-app": "app_volume",
    "public-download-fleet": "fleet_volume",
    "public-download-state": "state_volume",
    "public-download-upload-sessions": "upload_sessions_volume",
    "public-download-windows-proof": "windows_proof_volume",
    "public-download-windows-proof-upload": "windows_proof_upload_volume",
    "public-download-runtime-secrets": "runtime_secrets_volume",
    "public-download-projection": "projection_volume",
    "public-download-proofs": "proofs_volume",
    "public-download-shelf": "shelf_volume",
}
CANONICAL_INCUMBENT_VOLUMES = {
    "chummer6-hub_chummer-run-api-state",
    "chummer6-hub_chummer-release-upload-sessions",
    "chummer6-hub_chummer-windows-proof-store",
    "chummer6-hub_chummer-windows-proof-upload-sessions",
}
PUBLIC_PORTAL_ENVIRONMENT = {
    "ASPNETCORE_ENVIRONMENT": "Production",
    "ASPNETCORE_HTTPS_PORT": "443",
    "CHUMMER_ENABLE_HTTPS_REDIRECTION": "false",
    "AllowedHosts": "chummer.run;www.chummer.run",
    "CHUMMER_PUBLIC_ALLOWED_HOSTS": "chummer.run;www.chummer.run",
    "CHUMMER_PUBLIC_CANONICAL_ORIGIN": "https://chummer.run",
    "CHUMMER_PUBLIC_CANON_ROOT": "/app",
    "CHUMMER_ACCOUNT_ERASURE_JOURNAL_PATH": (
        "/app/state/account-erasure-journal.json"
    ),
    "CHUMMER_PUBLIC_FLEET_ARTIFACT_ROOT": "/fleet-artifacts",
    "CHUMMER_DATA_PROTECTION_KEYS_PATH": (
        "/app/state/data-protection-keys-v2"
    ),
    "CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH": (
        "/run/chummer-secrets/data-protection-key-encryption.pfx"
    ),
    "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE": (
        "/run/chummer-secrets/data-protection-key-encryption.password"
    ),
    "CHUMMER_DOWNLOADS_SOURCE_ROOT": "/downloads-source",
    "CHUMMER_RELEASE_UPLOAD_SESSION_ROOT": "/release-upload-sessions",
    "CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED": "false",
    "CHUMMER_WINDOWS_PROOF_UPLOAD_ENABLED": "false",
    "CHUMMER_WINDOWS_PROOF_CF_ACCESS_GATED": "false",
    "CHUMMER_WINDOWS_PROOF_ROOT": "/windows-proof-store",
    "CHUMMER_WINDOWS_PROOF_UPLOAD_SESSION_ROOT": (
        "/windows-proof-upload-sessions"
    ),
    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE": (
        "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json"
    ),
    "CHUMMER_PUBLIC_LOCAL_RELEASE_PROOF_FILE": (
        "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json"
    ),
    "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT": "/public-projection",
    "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_REQUIRED": "true",
    "CHUMMER_PUBLIC_FINAL_GOLD_JANITOR_FILE": (
        "/proofs/FINAL_GOLD_JANITOR.generated.json"
    ),
    "CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS": "false",
    "CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER": "true",
    "CHUMMER_PUBLIC_DOWNLOAD_ONLY": "true",
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


def validate_operation_secret(
    path: Path,
    *,
    operation_root: Path,
    expected_sha256: str,
    label: str,
) -> str:
    try:
        canonical = path.resolve(strict=True)
        canonical.relative_to(operation_root)
        metadata = path.lstat()
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"{label} is not contained by the operation root"
        ) from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError(f"{label} metadata is unsafe")
    try:
        observed_sha256 = hashlib.sha256(canonical.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"{label} could not be read") from exc
    if observed_sha256 != expected_sha256:
        raise ValueError(f"{label} digest drifted")
    return str(canonical)


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
        set(materialized_services) != {INITIALIZER_SERVICE, PORTAL_SERVICE}
        or any(
            mapping(
                materialized_services.get(service_name),
                f"materialized {service_name}",
            ).get("image")
            != candidate_image_id
            for service_name in (INITIALIZER_SERVICE, PORTAL_SERVICE)
        )
    ):
        raise ValueError("materialized Compose candidate authority drifted")
    materialized_portal = mapping(
        materialized_services.get(PORTAL_SERVICE),
        "materialized portal",
    )
    materialized_environment = mapping(
        materialized_portal.get("environment"),
        "materialized portal environment",
    )
    if (
        "env_file" in materialized_portal
        or set(materialized_environment)
        != set(PUBLIC_PORTAL_ENVIRONMENT).union(
            {
                "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY",
                "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED",
                "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED",
            }
        )
        or materialized_environment.get(
            "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY"
        )
        != (
            "${CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY:"
            "?Set a persistent 64-character lowercase hexadecimal account-erasure receipt HMAC key}"
        )
    ):
        raise ValueError("materialized portal environment closure drifted")
    return {
        "sourceRoot": str(canonical_source_root),
        "sourceHead": source_head,
        "baseComposeSourceSha256": receipt["baseComposeSourceSha256"],
        "profileSourceSha256": receipt["profileSourceSha256"],
        "materializedComposeSha256": compose_sha256,
    }


def bind_mount(
    source: str,
    target: str,
    *,
    read_only: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "bind": {},
        "source": source,
        "target": target,
        "type": "bind",
    }
    if read_only:
        result["read_only"] = True
    return result


def volume_mount(
    source: str,
    target: str,
    *,
    read_only: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": source,
        "target": target,
        "type": "volume",
        "volume": {},
    }
    if read_only:
        result["read_only"] = True
    return result


def expected_portal_mounts(
    *,
    app_overlay_source: str,
    fleet_source: str,
 ) -> list[dict[str, Any]]:
    return [
        volume_mount("public-download-app", "/app", read_only=True),
        volume_mount(
            "public-download-state",
            "/app/state",
            read_only=False,
        ),
        volume_mount(
            "public-download-runtime-secrets",
            "/run/chummer-secrets",
            read_only=True,
        ),
        volume_mount(
            "public-download-fleet",
            "/fleet-artifacts",
            read_only=True,
        ),
        volume_mount(
            "public-download-shelf",
            "/downloads-source",
            read_only=True,
        ),
        volume_mount(
            "public-download-upload-sessions",
            "/release-upload-sessions",
            read_only=False,
        ),
        volume_mount(
            "public-download-windows-proof",
            "/windows-proof-store",
            read_only=False,
        ),
        volume_mount(
            "public-download-windows-proof-upload",
            "/windows-proof-upload-sessions",
            read_only=False,
        ),
        volume_mount(
            "public-download-projection",
            "/public-projection",
            read_only=True,
        ),
        volume_mount(
            "public-download-proofs",
            "/proofs",
            read_only=True,
        ),
    ]


def expected_initializer_mounts(
    *,
    certificate_source: str,
    certificate_password_source: str,
    app_overlay_source: str,
    fleet_source: str,
    shelf_source: str,
    projection_source: str,
    runtime_proof_source: str,
    final_gold_source: str,
) -> list[dict[str, Any]]:
    return [
        volume_mount("public-download-app", "/app-staging", read_only=False),
        volume_mount(
            "public-download-fleet",
            "/fleet-staging",
            read_only=False,
        ),
        volume_mount("public-download-state", "/app/state", read_only=False),
        volume_mount(
            "public-download-upload-sessions",
            "/release-upload-sessions",
            read_only=False,
        ),
        volume_mount(
            "public-download-windows-proof",
            "/windows-proof-store",
            read_only=False,
        ),
        volume_mount(
            "public-download-windows-proof-upload",
            "/windows-proof-upload-sessions",
            read_only=False,
        ),
        volume_mount(
            "public-download-runtime-secrets",
            "/run/chummer-secrets",
            read_only=False,
        ),
        volume_mount(
            "public-download-projection",
            "/public-projection-staging",
            read_only=False,
        ),
        volume_mount(
            "public-download-proofs",
            "/proofs-staging",
            read_only=False,
        ),
        volume_mount(
            "public-download-shelf",
            "/downloads-source",
            read_only=False,
        ),
        bind_mount(
            certificate_source,
            "/runtime-inputs/data-protection-key-encryption.pfx",
            read_only=True,
        ),
        bind_mount(
            certificate_password_source,
            "/runtime-inputs/data-protection-key-encryption.password",
            read_only=True,
        ),
        bind_mount(
            app_overlay_source,
            "/runtime-inputs/app",
            read_only=True,
        ),
        bind_mount(
            fleet_source,
            "/runtime-inputs/fleet",
            read_only=True,
        ),
        bind_mount(
            shelf_source,
            "/runtime-inputs/shelf",
            read_only=True,
        ),
        bind_mount(
            projection_source,
            "/runtime-inputs/projection",
            read_only=True,
        ),
        bind_mount(
            runtime_proof_source,
            "/runtime-inputs/HUB_LOCAL_RELEASE_PROOF.generated.json",
            read_only=True,
        ),
        bind_mount(
            final_gold_source,
            "/runtime-inputs/FINAL_GOLD_JANITOR.generated.json",
            read_only=True,
        ),
    ]


def expected_root_volumes(volume_names: dict[str, str]) -> dict[str, Any]:
    return {
        logical_name: {
            "external": True,
            "name": volume_names[argument_name],
        }
        for logical_name, argument_name in LOGICAL_VOLUMES.items()
    }


def validate(
    payload: dict[str, Any],
    *,
    project_name: str,
    operation_root: str,
    operation: str,
    candidate_image_id: str,
    certificate_source: str,
    certificate_password_source: str,
    certificate_sha256: str,
    certificate_password_sha256: str,
    app_overlay_source: str,
    app_overlay_sha256: str,
    fleet_source: str,
    fleet_sha256: str,
    shelf_source: str,
    shelf_sha256: str,
    projection_source: str,
    projection_current_sha256: str,
    projection_snapshot_id: str,
    projection_sha256: str,
    runtime_proof_source: str,
    runtime_proof_sha256: str,
    final_gold_source: str,
    final_gold_sha256: str,
    volume_names: dict[str, str],
    materialization: dict[str, Any],
    rendered_compose_sha256: str,
) -> dict[str, Any]:
    if set(payload) != {"name", "services", "volumes"}:
        raise ValueError("rendered Compose root closure drifted")
    if (
        payload.get("name") != project_name
        or project_name == INCUMBENT_PROJECT_NAME
        or VOLUME_NAME_PATTERN.fullmatch(project_name) is None
    ):
        raise ValueError("rendered isolated project authority drifted")
    if IMAGE_ID_PATTERN.fullmatch(candidate_image_id) is None:
        raise ValueError("candidate image is not an immutable Docker image ID")
    services = mapping(payload.get("services"), "rendered services")
    if set(services) != {INITIALIZER_SERVICE, PORTAL_SERVICE}:
        raise ValueError(
            "rendered runtime is not the exact portal-plus-initializer closure"
        )
    if contains_postgres_material(payload):
        raise ValueError("rendered runtime retained PostgreSQL material")
    portal = mapping(services.get(PORTAL_SERVICE), "rendered portal")
    initializer = mapping(
        services.get(INITIALIZER_SERVICE),
        "rendered initializer",
    )
    if set(portal) != EXPECTED_PORTAL_KEYS:
        raise ValueError("rendered portal field closure drifted")
    if set(initializer) != EXPECTED_INITIALIZER_KEYS:
        raise ValueError("rendered initializer field closure drifted")
    if portal.get("image") != candidate_image_id:
        raise ValueError("rendered portal candidate image is not pinned")
    if initializer.get("image") != candidate_image_id:
        raise ValueError("rendered initializer candidate image is not pinned")
    if "build" in portal:
        raise ValueError("public-download-only runtime must be build-free")
    if "build" in initializer:
        raise ValueError("public-download initializer must be build-free")
    if portal.get("user") != CANONICAL_PORTAL_USER:
        raise ValueError("rendered portal runtime identity drifted")
    if portal.get("command") is not None or portal.get("entrypoint") is not None:
        raise ValueError("rendered portal process authority drifted")
    if portal.get("cap_drop") != ["ALL"]:
        raise ValueError("rendered portal capability drop drifted")
    if portal.get("security_opt") != ["no-new-privileges:true"]:
        raise ValueError("rendered portal security policy drifted")
    if portal.get("ulimits") != {"core": {}}:
        raise ValueError("rendered portal core limit drifted")

    environment = mapping(portal.get("environment"), "rendered portal environment")
    account_erasure_hmac_key = environment.get(
        "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY"
    )
    if (
        not isinstance(account_erasure_hmac_key, str)
        or re.fullmatch(r"[0-9a-f]{64}", account_erasure_hmac_key) is None
    ):
        raise ValueError(
            "rendered portal account-erasure receipt HMAC key must be one "
            "persistent 64-character lowercase hexadecimal secret"
        )
    expected_environment = {
        **PUBLIC_PORTAL_ENVIRONMENT,
        **POSTURES[operation],
    }
    environment_without_secrets = dict(environment)
    del environment_without_secrets["CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY"]
    if environment_without_secrets != expected_environment:
        raise ValueError("rendered portal environment allowlist drifted")

    if portal.get("extra_hosts") not in (None, []):
        raise ValueError("rendered portal host mapping is not the closed posture")
    mounts = sequence(portal.get("volumes"), "rendered portal mounts")
    if mounts != expected_portal_mounts(
        app_overlay_source=app_overlay_source,
        fleet_source=fleet_source,
    ):
        raise ValueError("rendered portal mount authority drifted")

    if initializer.get("user") != CANONICAL_INITIALIZER_USER:
        raise ValueError("rendered initializer identity drifted")
    if initializer.get("command") is not None:
        raise ValueError("rendered initializer command authority drifted")
    if initializer.get("entrypoint") != [
        "/usr/local/libexec/chummer/initialize-public-edge-volumes.sh"
    ]:
        raise ValueError("rendered initializer entrypoint drifted")
    if initializer.get("restart") != "no":
        raise ValueError("rendered initializer restart policy drifted")
    if initializer.get("read_only") is not True:
        raise ValueError("rendered initializer root must be read-only")
    if initializer.get("network_mode") != "none":
        raise ValueError("rendered initializer network closure drifted")
    if initializer.get("cap_drop") != ["ALL"] or initializer.get(
        "cap_add"
    ) != ["CHOWN", "SETUID", "SETGID", "DAC_READ_SEARCH"]:
        raise ValueError("rendered initializer capability closure drifted")
    if initializer.get("security_opt") != ["no-new-privileges:true"]:
        raise ValueError("rendered initializer security policy drifted")
    if initializer.get("profiles") != ["public-downloads"]:
        raise ValueError("rendered initializer profile selector drifted")
    if initializer.get("pids_limit") != 64:
        raise ValueError("rendered initializer process limit drifted")
    if initializer.get("ulimits") != {"core": {}}:
        raise ValueError("rendered initializer core limit drifted")
    expected_initializer_environment = {
        "CHUMMER_PUBLIC_DOWNLOAD_RUNTIME_INIT": "true",
        "CHUMMER_PORTAL_UID": "1654",
        "CHUMMER_PORTAL_GID": "1654",
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_SHA256": (
            certificate_sha256
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_SHA256": (
            certificate_password_sha256
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256": app_overlay_sha256,
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256": fleet_sha256,
        "CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256": shelf_sha256,
        "CHUMMER_PUBLIC_EDGE_PROJECTION_CURRENT_SHA256": (
            projection_current_sha256
        ),
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ID": (
            projection_snapshot_id
        ),
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256": projection_sha256,
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256": (
            runtime_proof_sha256
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256": final_gold_sha256,
    }
    if mapping(
        initializer.get("environment"),
        "rendered initializer environment",
    ) != expected_initializer_environment:
        raise ValueError("rendered initializer environment closure drifted")
    initializer_mounts = sequence(
        initializer.get("volumes"),
        "rendered initializer mounts",
    )
    if initializer_mounts != expected_initializer_mounts(
        certificate_source=certificate_source,
        certificate_password_source=certificate_password_source,
        app_overlay_source=app_overlay_source,
        fleet_source=fleet_source,
        shelf_source=shelf_source,
        projection_source=projection_source,
        runtime_proof_source=runtime_proof_source,
        final_gold_source=final_gold_source,
    ):
        raise ValueError("rendered initializer mount authority drifted")

    if portal.get("healthcheck") != EXPECTED_HEALTHCHECK:
        raise ValueError("rendered portal serving-only healthcheck drifted")
    if portal.get("depends_on") != {
        INITIALIZER_SERVICE: {
            "condition": "service_completed_successfully",
            "required": True,
        }
    }:
        raise ValueError("rendered portal initializer dependency drifted")
    if portal.get("profiles") != ["public-downloads"]:
        raise ValueError("rendered portal profile selector drifted")
    if portal.get("network_mode") != "bridge":
        raise ValueError("rendered portal isolated network contract drifted")
    if mapping(
        payload.get("volumes"),
        "rendered volumes",
    ) != expected_root_volumes(volume_names):
        raise ValueError("rendered named-volume authority drifted")
    if portal.get("ports") != [
        {
            "mode": "ingress",
            "protocol": "tcp",
            "host_ip": CANDIDATE_BIND_ADDRESS,
            "published": str(CANDIDATE_PUBLISHED_PORT),
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
        "operationRoot": operation_root,
        "portalImageId": candidate_image_id,
        "initializerImageId": candidate_image_id,
        "initializerConstrained": True,
        "portalAppCopiedReadOnly": True,
        "portalFleetCopiedReadOnly": True,
        "longRunningSourceBindsAbsent": True,
        "releaseShelfPreinitialized": True,
        "releaseShelfPortalReadOnly": True,
        "isolatedVolumes": {
            logical_name: volume_names[argument_name]
            for logical_name, argument_name in LOGICAL_VOLUMES.items()
        },
        "runtimeInputs": {
            "appOverlay": {
                "source": app_overlay_source,
                "sha256": app_overlay_sha256,
            },
            "fleet": {"source": fleet_source, "sha256": fleet_sha256},
            "shelf": {"source": shelf_source, "sha256": shelf_sha256},
            "projection": {
                "source": projection_source,
                "currentSha256": projection_current_sha256,
                "snapshotId": projection_snapshot_id,
                "snapshotTreeSha256": projection_sha256,
            },
            "runtimeProof": {
                "source": runtime_proof_source,
                "sha256": runtime_proof_sha256,
            },
            "finalGold": {
                "source": final_gold_source,
                "sha256": final_gold_sha256,
            },
            "certificateSha256": certificate_sha256,
            "certificatePasswordSha256": certificate_password_sha256,
            "certificateAuthority": "operation-bound-sidecar-only",
        },
        "postgresServicesAbsent": True,
        "postgresEnvironmentAbsent": True,
        "postgresMountsAbsent": True,
        "postgresHostMappingAbsent": True,
        "portalBuildAbsent": True,
        "publicDownloadsHealthcheck": True,
        "releaseShelfPosture": POSTURES[operation],
        "portalMountCount": len(mounts),
        "initializerMountCount": len(initializer_mounts),
        "publishedAddress": CANDIDATE_BIND_ADDRESS,
        "publishedPort": CANDIDATE_PUBLISHED_PORT,
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
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--operation-root", type=Path, required=True)
    parser.add_argument("--operation", choices=tuple(POSTURES), required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--materialized-compose", type=Path, required=True)
    parser.add_argument("--materialization-receipt", type=Path, required=True)
    parser.add_argument("--candidate-image-id", required=True)
    parser.add_argument("--shelf-source", required=True)
    parser.add_argument("--shelf-sha256", required=True)
    parser.add_argument("--certificate-source", required=True)
    parser.add_argument("--certificate-password-source", required=True)
    parser.add_argument("--certificate-sha256", required=True)
    parser.add_argument("--certificate-password-sha256", required=True)
    parser.add_argument("--app-overlay-source", required=True)
    parser.add_argument("--app-overlay-sha256", required=True)
    parser.add_argument("--fleet-source", required=True)
    parser.add_argument("--fleet-sha256", required=True)
    parser.add_argument("--projection-source", required=True)
    parser.add_argument("--projection-current-sha256", required=True)
    parser.add_argument("--projection-snapshot-id", required=True)
    parser.add_argument("--projection-sha256", required=True)
    parser.add_argument("--runtime-proof-source", required=True)
    parser.add_argument("--runtime-proof-sha256", required=True)
    parser.add_argument("--final-gold-source", required=True)
    parser.add_argument("--final-gold-sha256", required=True)
    parser.add_argument("--state-volume", required=True)
    parser.add_argument("--app-volume", required=True)
    parser.add_argument("--fleet-volume", required=True)
    parser.add_argument("--upload-sessions-volume", required=True)
    parser.add_argument("--windows-proof-volume", required=True)
    parser.add_argument("--windows-proof-upload-volume", required=True)
    parser.add_argument("--runtime-secrets-volume", required=True)
    parser.add_argument("--projection-volume", required=True)
    parser.add_argument("--proofs-volume", required=True)
    parser.add_argument("--shelf-volume", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        for label, value in (
            ("shelf source", args.shelf_source),
            ("certificate source", args.certificate_source),
            ("certificate password source", args.certificate_password_source),
            ("app overlay source", args.app_overlay_source),
            ("fleet source", args.fleet_source),
            ("projection source", args.projection_source),
            ("runtime proof source", args.runtime_proof_source),
            ("final-gold source", args.final_gold_source),
        ):
            if not Path(value).is_absolute() or "\x00" in value:
                raise ValueError(f"{label} is not an absolute path")
        if (
            VOLUME_NAME_PATTERN.fullmatch(args.project_name) is None
            or args.project_name == INCUMBENT_PROJECT_NAME
        ):
            raise ValueError("candidate project name is not isolated")
        for label, digest in (
            ("shelf SHA-256", args.shelf_sha256),
            ("certificate SHA-256", args.certificate_sha256),
            (
                "certificate password SHA-256",
                args.certificate_password_sha256,
            ),
            ("app overlay SHA-256", args.app_overlay_sha256),
            ("fleet SHA-256", args.fleet_sha256),
            (
                "projection CURRENT SHA-256",
                args.projection_current_sha256,
            ),
            ("projection SHA-256", args.projection_sha256),
            ("runtime proof SHA-256", args.runtime_proof_sha256),
            ("final-gold SHA-256", args.final_gold_sha256),
        ):
            if SHA256_PATTERN.fullmatch(digest) is None:
                raise ValueError(f"{label} is invalid")
        if (
            PROJECTION_SNAPSHOT_ID_PATTERN.fullmatch(
                args.projection_snapshot_id
            )
            is None
        ):
            raise ValueError("projection snapshot id is invalid")
        try:
            operation_root = args.operation_root.resolve(strict=True)
            operation_root_metadata = args.operation_root.lstat()
        except OSError as exc:
            raise ValueError("operation root is unavailable") from exc
        if (
            not args.operation_root.is_absolute()
            or args.operation_root.is_symlink()
            or not stat.S_ISDIR(operation_root_metadata.st_mode)
            or operation_root_metadata.st_uid != os.getuid()
            or stat.S_IMODE(operation_root_metadata.st_mode) & 0o077
            or operation_root.name != args.project_name
        ):
            raise ValueError(
                "operation root is not private and project-bound"
            )
        certificate_source = validate_operation_secret(
            Path(args.certificate_source),
            operation_root=operation_root,
            expected_sha256=args.certificate_sha256,
            label="sidecar data-protection certificate",
        )
        certificate_password_source = validate_operation_secret(
            Path(args.certificate_password_source),
            operation_root=operation_root,
            expected_sha256=args.certificate_password_sha256,
            label="sidecar data-protection certificate password",
        )
        if certificate_source == certificate_password_source:
            raise ValueError(
                "sidecar data-protection certificate inputs are not distinct"
            )
        volume_names = {
            "app_volume": args.app_volume,
            "fleet_volume": args.fleet_volume,
            "state_volume": args.state_volume,
            "upload_sessions_volume": args.upload_sessions_volume,
            "windows_proof_volume": args.windows_proof_volume,
            "windows_proof_upload_volume": args.windows_proof_upload_volume,
            "runtime_secrets_volume": args.runtime_secrets_volume,
            "projection_volume": args.projection_volume,
            "proofs_volume": args.proofs_volume,
            "shelf_volume": args.shelf_volume,
        }
        if (
            len(set(volume_names.values())) != len(volume_names)
            or any(
                VOLUME_NAME_PATTERN.fullmatch(value) is None
                or value in CANONICAL_INCUMBENT_VOLUMES
                for value in volume_names.values()
            )
        ):
            raise ValueError(
                "runtime volumes are not unique isolated operation-bound names"
            )
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
            project_name=args.project_name,
            operation_root=str(operation_root),
            operation=args.operation,
            candidate_image_id=args.candidate_image_id,
            shelf_source=args.shelf_source,
            shelf_sha256=args.shelf_sha256,
            certificate_source=certificate_source,
            certificate_password_source=certificate_password_source,
            certificate_sha256=args.certificate_sha256,
            certificate_password_sha256=args.certificate_password_sha256,
            app_overlay_source=args.app_overlay_source,
            app_overlay_sha256=args.app_overlay_sha256,
            fleet_source=args.fleet_source,
            fleet_sha256=args.fleet_sha256,
            projection_source=args.projection_source,
            projection_current_sha256=args.projection_current_sha256,
            projection_snapshot_id=args.projection_snapshot_id,
            projection_sha256=args.projection_sha256,
            runtime_proof_source=args.runtime_proof_source,
            runtime_proof_sha256=args.runtime_proof_sha256,
            final_gold_source=args.final_gold_source,
            final_gold_sha256=args.final_gold_sha256,
            volume_names=volume_names,
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
