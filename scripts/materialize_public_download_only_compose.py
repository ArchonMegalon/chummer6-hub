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
import subprocess
import tempfile
from typing import Any

import yaml


CONTRACT_NAME = "chummer.public-download-only-compose-materialization/v1"
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40}$")
BASE_COMPOSE_NAME = "docker-compose.public-edge.yml"
PROFILE_COMPOSE_NAME = "docker-compose.public-downloads.yml"
POSTURES = {
    "initial-release-shelf-public-download-cutover": ("true", "false"),
    "initial-release-shelf-public-download-cutover-recover": ("true", "false"),
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
INITIALIZER_SERVICE = "chummer-public-download-init"
PORTAL_SERVICE = "chummer-portal"
LOGICAL_VOLUMES = {
    "public-download-app": "CHUMMER_PUBLIC_DOWNLOAD_APP_VOLUME",
    "public-download-fleet": "CHUMMER_PUBLIC_DOWNLOAD_FLEET_VOLUME",
    "public-download-state": "CHUMMER_PUBLIC_DOWNLOAD_STATE_VOLUME",
    "public-download-upload-sessions": (
        "CHUMMER_PUBLIC_DOWNLOAD_UPLOAD_SESSIONS_VOLUME"
    ),
    "public-download-windows-proof": (
        "CHUMMER_PUBLIC_DOWNLOAD_WINDOWS_PROOF_VOLUME"
    ),
    "public-download-windows-proof-upload": (
        "CHUMMER_PUBLIC_DOWNLOAD_WINDOWS_PROOF_UPLOAD_VOLUME"
    ),
    "public-download-runtime-secrets": (
        "CHUMMER_PUBLIC_DOWNLOAD_RUNTIME_SECRETS_VOLUME"
    ),
    "public-download-projection": "CHUMMER_PUBLIC_DOWNLOAD_PROJECTION_VOLUME",
    "public-download-proofs": "CHUMMER_PUBLIC_DOWNLOAD_PROOFS_VOLUME",
    "public-download-shelf": "CHUMMER_PUBLIC_DOWNLOAD_SHELF_VOLUME",
}
PUBLIC_PORTAL_ENVIRONMENT = {
    "ASPNETCORE_ENVIRONMENT": "Production",
    "ASPNETCORE_HTTPS_PORT": "443",
    "CHUMMER_ENABLE_HTTPS_REDIRECTION": "false",
    "AllowedHosts": "chummer.run;www.chummer.run",
    "CHUMMER_PUBLIC_ALLOWED_HOSTS": "chummer.run;www.chummer.run",
    "CHUMMER_PUBLIC_CANONICAL_ORIGIN": "https://chummer.run",
    "CHUMMER_PUBLIC_CANON_ROOT": "/app",
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
INITIALIZER_ENVIRONMENT = {
    "CHUMMER_PUBLIC_DOWNLOAD_RUNTIME_INIT": "true",
    "CHUMMER_PORTAL_UID": "1654",
    "CHUMMER_PORTAL_GID": "1654",
    "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_SHA256": (
        "${CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_SHA256:"
        "?Set the operation-bound sidecar certificate SHA-256}"
    ),
    "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_SHA256": (
        "${CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_SHA256:"
        "?Set the operation-bound sidecar certificate-password SHA-256}"
    ),
    "CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256": (
        "${CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256:"
        "?Set the app-overlay tree SHA-256}"
    ),
    "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256": (
        "${CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256:"
        "?Set the fleet tree SHA-256}"
    ),
    "CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256": (
        "${CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256:"
        "?Set the prevalidated active shelf tree SHA-256}"
    ),
    "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256": (
        "${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256:"
        "?Set the projection tree SHA-256}"
    ),
    "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256": (
        "${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256:"
        "?Set the runtime-proof SHA-256}"
    ),
    "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256": (
        "${CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256:"
        "?Set the final-gold SHA-256}"
    ),
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
PUBLIC_DOWNLOAD_PROFILE_HEALTHCHECK = {
    "test": PUBLIC_DOWNLOAD_HEALTHCHECK["test"],
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


def mount_source(value: object) -> str:
    if isinstance(value, str):
        return value.split(":", 1)[0]
    if isinstance(value, dict):
        source = value.get("source")
        return source if isinstance(source, str) else ""
    return ""


def validate_profile_source(
    source: Path,
    *,
    raw: bytes,
) -> str:
    try:
        text = raw.decode("utf-8")
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(
            "public-downloads Compose profile is unavailable or invalid"
        ) from exc
    replacements = {
        "    env_file: !reset []": "    env_file: []",
        "    depends_on: !reset {}": "    depends_on: {}",
        "    extra_hosts: !reset []": "    extra_hosts: []",
        "    environment: !override {}": "    environment: {}",
        "    volumes: !override []": "    volumes: []",
    }
    if (
        any(text.count(tagged) != 1 for tagged in replacements)
        or text.count("!reset") != 3
        or text.count("!override") != 2
    ):
        raise ValueError(
            "public-downloads Compose profile tag closure drifted"
        )
    normalized_text = text
    for tagged, normalized in replacements.items():
        normalized_text = normalized_text.replace(tagged, normalized)
    try:
        payload = yaml.safe_load(normalized_text)
    except yaml.YAMLError as exc:
        raise ValueError(
            "public-downloads Compose profile is unavailable or invalid"
        ) from exc
    root = require_mapping(payload, "public-downloads Compose profile")
    if set(root) != {"services"}:
        raise ValueError("public-downloads Compose profile root drifted")
    services = require_mapping(
        root.get("services"),
        "public-downloads Compose profile services",
    )
    if set(services) != {"chummer-portal"}:
        raise ValueError("public-downloads Compose profile service closure drifted")
    portal = require_mapping(
        services.get("chummer-portal"),
        "public-downloads Compose profile portal",
    )
    expected_fields = {
        "profiles",
        "env_file",
        "depends_on",
        "extra_hosts",
        "environment",
        "volumes",
        "healthcheck",
    }
    if set(portal) != expected_fields:
        raise ValueError("public-downloads Compose profile portal fields drifted")
    if portal.get("profiles") != ["public-downloads"]:
        raise ValueError("public-downloads Compose profile selector drifted")
    for name, expected in (
        ("env_file", []),
        ("depends_on", {}),
        ("extra_hosts", []),
        ("environment", {}),
        ("volumes", []),
    ):
        if portal.get(name) != expected:
            raise ValueError(
                f"public-downloads {name} closure drifted"
            )
    if portal.get("extra_hosts") != []:
        raise ValueError(
            "public-downloads extra_hosts reset contract drifted"
        )
    if portal.get("healthcheck") != PUBLIC_DOWNLOAD_PROFILE_HEALTHCHECK:
        raise ValueError("public-downloads Compose profile healthcheck drifted")
    return hashlib.sha256(raw).hexdigest()


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


def required_environment(name: str, description: str) -> str:
    return f"${{{name}:?{description}}}"


def initializer_mounts() -> list[str]:
    return [
        "public-download-app:/app-staging",
        "public-download-fleet:/fleet-staging",
        "public-download-state:/app/state",
        "public-download-upload-sessions:/release-upload-sessions",
        "public-download-windows-proof:/windows-proof-store",
        (
            "public-download-windows-proof-upload:"
            "/windows-proof-upload-sessions"
        ),
        "public-download-runtime-secrets:/run/chummer-secrets",
        "public-download-projection:/public-projection-staging",
        "public-download-proofs:/proofs-staging",
        "public-download-shelf:/downloads-source",
        (
            required_environment(
                "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_FILE",
                "Set the operation-bound sidecar PKCS#12 certificate",
            )
            + ":/runtime-inputs/data-protection-key-encryption.pfx:ro"
        ),
        (
            required_environment(
                "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_FILE",
                "Set the operation-bound sidecar certificate password",
            )
            + ":/runtime-inputs/data-protection-key-encryption.password:ro"
        ),
        (
            required_environment(
                "CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR",
                "Set the immutable portal app overlay",
            )
            + ":/runtime-inputs/app:ro"
        ),
        (
            required_environment(
                "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SOURCE",
                "Set the immutable fleet/static source",
            )
            + ":/runtime-inputs/fleet:ro"
        ),
        (
            required_environment(
                "CHUMMER_PUBLIC_DOWNLOAD_SHELF_SOURCE",
                "Set the prevalidated active release shelf",
            )
            + ":/runtime-inputs/shelf:ro"
        ),
        (
            required_environment(
                "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT",
                "Set the authenticated projection source",
            )
            + ":/runtime-inputs/projection:ro"
        ),
        (
            required_environment(
                "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE",
                "Set the authenticated runtime proof",
            )
            + ":/runtime-inputs/HUB_LOCAL_RELEASE_PROOF.generated.json:ro"
        ),
        (
            required_environment(
                "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE",
                "Set the reviewed final-gold handoff",
            )
            + ":/runtime-inputs/FINAL_GOLD_JANITOR.generated.json:ro"
        ),
    ]


def portal_mounts() -> list[str]:
    return [
        "public-download-app:/app:ro",
        "public-download-state:/app/state",
        "public-download-runtime-secrets:/run/chummer-secrets:ro",
        "public-download-fleet:/fleet-artifacts:ro",
        "public-download-shelf:/downloads-source:ro",
        "public-download-upload-sessions:/release-upload-sessions",
        "public-download-windows-proof:/windows-proof-store",
        (
            "public-download-windows-proof-upload:"
            "/windows-proof-upload-sessions"
        ),
        "public-download-projection:/public-projection:ro",
        "public-download-proofs:/proofs:ro",
    ]


def materialize(
    source: Path,
    *,
    profile_source: Path,
    source_raw: bytes,
    profile_raw: bytes,
    candidate_image_id: str,
    operation: str,
) -> tuple[dict[str, Any], str, str]:
    if IMAGE_ID_PATTERN.fullmatch(candidate_image_id) is None:
        raise ValueError("candidate image is not an immutable Docker image ID")
    try:
        payload = yaml.safe_load(source_raw.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("canonical Compose source is unavailable or invalid") from exc
    root = require_mapping(payload, "Compose document")
    services = require_mapping(root.get("services"), "Compose services")
    missing_services = REMOVED_SERVICES.difference(services)
    if missing_services:
        raise ValueError("canonical Compose source lost a PostgreSQL service")

    base_portal = require_mapping(
        services.get(PORTAL_SERVICE),
        "portal service",
    )
    base_initializer = require_mapping(
        services.get("chummer-portal-volume-init"),
        "portal initializer service",
    )
    if (
        base_portal.get("image") != "chummer-run-api:local"
        or "build" not in base_portal
    ):
        raise ValueError("canonical portal image/build contract drifted")
    if base_initializer.get("image") != "chummer-run-api:local":
        raise ValueError("canonical portal initializer image contract drifted")
    profile_sha256 = validate_profile_source(
        profile_source,
        raw=profile_raw,
    )
    if "depends_on" not in base_portal:
        raise ValueError("canonical portal dependency contract drifted")
    base_environment = require_mapping(
        base_portal.get("environment"),
        "portal environment",
    )
    if not REMOVED_PORTAL_ENVIRONMENT.issubset(base_environment):
        raise ValueError("canonical portal PostgreSQL environment contract drifted")

    extra_hosts = base_portal.get("extra_hosts")
    if (
        not isinstance(extra_hosts, list)
        or len(extra_hosts) != 2
        or extra_hosts[0] != "host.docker.internal:host-gateway"
        or "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME" not in str(extra_hosts[1])
        or "CHUMMER_INSTALL_LINKING_POSTGRES_IP" not in str(extra_hosts[1])
    ):
        raise ValueError("canonical portal PostgreSQL host mapping contract drifted")

    volumes = base_portal.get("volumes")
    if not isinstance(volumes, list):
        raise ValueError("canonical portal volumes must be a sequence")
    observed_removed_targets = {
        mount_target(item)
        for item in volumes
        if mount_target(item) in REMOVED_PORTAL_MOUNT_TARGETS
    }
    if observed_removed_targets != REMOVED_PORTAL_MOUNT_TARGETS:
        raise ValueError("canonical portal PostgreSQL mount contract drifted")

    if base_portal.get("healthcheck") != EXPECTED_BASE_HEALTHCHECK:
        raise ValueError("canonical portal healthcheck contract drifted")
    if base_portal.get("cap_drop") != ["ALL"] or base_portal.get(
        "security_opt"
    ) != ["no-new-privileges:true"]:
        raise ValueError("canonical portal security contract drifted")
    portal_networks = require_mapping(
        base_portal.get("networks"),
        "canonical portal networks",
    )
    root_networks = require_mapping(
        root.get("networks"),
        "canonical Compose networks",
    )
    if (
        set(portal_networks) != {"public-origin", "fleet-origin", "ea-origin"}
        or not set(portal_networks).issubset(root_networks)
    ):
        raise ValueError("canonical portal network closure drifted")

    layout_required, migration_allowed = POSTURES[operation]
    environment = dict(PUBLIC_PORTAL_ENVIRONMENT)
    environment["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] = layout_required
    environment["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = (
        migration_allowed
    )
    portal = {
        "image": candidate_image_id,
        "restart": "unless-stopped",
        "user": "1654:1654",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "ulimits": {"core": 0},
        "depends_on": {
            INITIALIZER_SERVICE: {
                "condition": "service_completed_successfully",
            }
        },
        "environment": environment,
        "volumes": portal_mounts(),
        "ports": ["172.17.0.1:18091:8080"],
        "healthcheck": PUBLIC_DOWNLOAD_HEALTHCHECK,
        "mem_limit": "${CHUMMER_PORTAL_MEMORY_LIMIT:-1536m}",
        "cpu_shares": 256,
        "cpus": "${CHUMMER_PORTAL_CPUS:-1.00}",
        "network_mode": "bridge",
        "profiles": ["public-downloads"],
    }
    initializer = {
        "image": candidate_image_id,
        "profiles": ["public-downloads"],
        "restart": "no",
        "user": "0:0",
        "read_only": True,
        "cap_drop": ["ALL"],
        "cap_add": ["CHOWN", "SETUID", "SETGID", "DAC_READ_SEARCH"],
        "security_opt": ["no-new-privileges:true"],
        "network_mode": "none",
        "ulimits": {"core": 0},
        "pids_limit": 64,
        "environment": INITIALIZER_ENVIRONMENT,
        "entrypoint": [
            "/usr/local/libexec/chummer/initialize-public-edge-volumes.sh"
        ],
        "volumes": initializer_mounts(),
    }
    root = {
        "services": {
            INITIALIZER_SERVICE: initializer,
            PORTAL_SERVICE: portal,
        },
        "volumes": {
            logical_name: {
                "external": True,
                "name": required_environment(
                    environment_name,
                    f"Set the operation-bound {logical_name} volume",
                ),
            }
            for logical_name, environment_name in LOGICAL_VOLUMES.items()
        },
    }
    if _contains_install_linking_postgres(root):
        raise ValueError(
            "public-download-only Compose projection retained PostgreSQL material"
        )
    return root, hashlib.sha256(source_raw).hexdigest(), profile_sha256


def verify_revision_bound_sources(
    source_root: Path,
    *,
    source_head: str,
    source: Path,
    profile_source: Path,
) -> tuple[Path, Path, Path, bytes, bytes]:
    if SOURCE_HEAD_PATTERN.fullmatch(source_head) is None:
        raise ValueError("source HEAD must be a lowercase full 40-hex commit")
    try:
        canonical_root = source_root.resolve(strict=True)
        canonical_source = source.resolve(strict=True)
        canonical_profile = profile_source.resolve(strict=True)
    except OSError as exc:
        raise ValueError("revision-bound Compose source is unavailable") from exc
    expected_source = canonical_root / BASE_COMPOSE_NAME
    expected_profile = canonical_root / PROFILE_COMPOSE_NAME
    if (
        source.is_symlink()
        or profile_source.is_symlink()
        or canonical_source != expected_source
        or canonical_profile != expected_profile
    ):
        raise ValueError("Compose sources are not the canonical source-root files")
    try:
        observed_head = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(canonical_root),
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("source HEAD could not be independently verified") from exc
    if observed_head != source_head:
        raise ValueError("source HEAD does not match the checked-out commit")
    source_buffers: list[bytes] = []
    for path, relative in (
        (canonical_source, BASE_COMPOSE_NAME),
        (canonical_profile, PROFILE_COMPOSE_NAME),
    ):
        try:
            committed = subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(canonical_root),
                    "show",
                    f"{source_head}:{relative}",
                ],
                check=True,
                capture_output=True,
                timeout=10,
            ).stdout
            working = path.read_bytes()
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(
                f"{relative} could not be verified against source HEAD"
            ) from exc
        if working != committed:
            raise ValueError(f"{relative} is not byte-identical to source HEAD")
        source_buffers.append(working)
    return (
        canonical_root,
        canonical_source,
        canonical_profile,
        source_buffers[0],
        source_buffers[1],
    )


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
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--profile-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--candidate-image-id", required=True)
    parser.add_argument("--operation", choices=tuple(POSTURES), required=True)
    args = parser.parse_args(argv)
    try:
        (
            source_root,
            source,
            profile_source,
            source_raw,
            profile_raw,
        ) = verify_revision_bound_sources(
            args.source_root,
            source_head=args.source_head,
            source=args.source,
            profile_source=args.profile_source,
        )
        projected, base_sha256, profile_sha256 = materialize(
            source,
            profile_source=profile_source,
            source_raw=source_raw,
            profile_raw=profile_raw,
            candidate_image_id=args.candidate_image_id,
            operation=args.operation,
        )
        body = (
            json.dumps(
                projected,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        atomic_write(args.output, body)
        receipt = {
            "contractName": CONTRACT_NAME,
            "status": "pass",
            "operation": args.operation,
            "sourceRoot": str(source_root),
            "sourceHead": args.source_head,
            "baseComposeSource": str(source),
            "baseComposeSourceSha256": base_sha256,
            "profileSource": str(profile_source),
            "profileSourceSha256": profile_sha256,
            "candidateImageId": args.candidate_image_id,
            "composeSha256": hashlib.sha256(body).hexdigest(),
        }
        atomic_write(
            args.receipt_output,
            (
                json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)
                + "\n"
            ).encode("utf-8"),
        )
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        print(f"public_download_only_compose: {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
