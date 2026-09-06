from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_public_edge_compose_runtime.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_public_edge_compose_runtime", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_portal_compose_pins_production_https_policy_against_env_drift() -> None:
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(
        encoding="utf-8"
    )
    portal = compose[
        compose.index("  chummer-portal:\n") :
        compose.index("\n  chummer-run-cloudflared:", compose.index("  chummer-portal:\n"))
    ]

    assert "ASPNETCORE_ENVIRONMENT: Production" in portal
    assert "AllowedHosts: chummer.run" in portal
    assert "CHUMMER_PUBLIC_ALLOWED_HOSTS: chummer.run" in portal
    assert "CHUMMER_PUBLIC_CANONICAL_ORIGIN: https://chummer.run" in portal
    assert "${CHUMMER_PUBLIC_CANONICAL_ORIGIN" not in portal


def rendered_compose(
    *,
    source_root: Path,
    build_context: Path,
    overlay_root: Path,
    projection_root: Path,
    runtime_proof_bind_source: Path | None = None,
) -> dict[str, object]:
    if runtime_proof_bind_source is None:
        runtime_proof_bind_source = fixture_runtime_proof(projection_root)

    def build(*, tool: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "context": str(build_context),
            "dockerfile": str(source_root / "Chummer.Run.Api" / "Dockerfile"),
            "additional_contexts": {
                "core-runtime-bundle": str(
                    source_root.parent
                    / "core-runtime-package-plane-c06f22c185c7b733637fdb76b3cf333f31716781-input"
                ),
                "run-services-source": str(source_root),
                "hub-registry-source": (
                    "/docker/chummercomplete/chummer-hub-registry"
                ),
                "hub-package-feed-input": str(
                    source_root.parent / "hub-package-feed-sh1852ea4eef6d-input"
                ),
                "fleet-media-factory-contracts": (
                    "/docker/fleet/repos/chummer-media-factory/src/"
                    "Chummer.Media.Contracts"
                ),
                "design-product": "/docker/chummercomplete/chummer-design",
            },
            "args": {
                "CHUMMER_BUILD_CONCURRENCY": "1",
                "CHUMMER_RUNTIME_UID": "1654",
                "CHUMMER_RUNTIME_GID": "1654",
            },
        }
        if tool:
            payload["target"] = "install-linking-postgres-tool-final"
        return payload

    def volume(source: str, target: str) -> dict[str, object]:
        return {"type": "volume", "source": source, "target": target, "volume": {}}

    def bind(
        source: str, target: str, *, read_only: bool = False
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": "bind",
            "source": source,
            "target": target,
            "bind": {},
        }
        if read_only:
            payload["read_only"] = True
        return payload

    security = {
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "ulimits": {"core": {}},
    }
    downloads_source = (
        "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads"
    )
    return {
        "name": "chummer6-hub",
        "services": {
            "chummer-portal-volume-init": {
                "image": "chummer-run-api:local",
                "restart": "no",
                "user": "0:0",
                "read_only": True,
                **security,
                "cap_add": ["CHOWN", "SETUID", "SETGID"],
                "network_mode": "none",
                "pids_limit": 32,
                "environment": {
                    "CHUMMER_PORTAL_UID": "1654",
                    "CHUMMER_PORTAL_GID": "1654",
                },
                "entrypoint": [
                    "/usr/local/libexec/chummer/initialize-public-edge-volumes.sh"
                ],
                "command": None,
                "volumes": [
                    volume("chummer-run-api-state", "/app/state"),
                    volume(
                        "chummer-release-upload-sessions", "/release-upload-sessions"
                    ),
                    volume("chummer-windows-proof-store", "/windows-proof-store"),
                    volume(
                        "chummer-windows-proof-upload-sessions",
                        "/windows-proof-upload-sessions",
                    ),
                    bind(downloads_source, "/downloads-source"),
                ],
            },
            "chummer-portal": {
                "image": "chummer-run-api:local",
                "build": build(),
                "restart": "unless-stopped",
            "user": "1654:1654",
            **security,
            "cpu_shares": 256,
            "cpus": 1,
            "mem_limit": "1610612736",
            "command": None,
                "entrypoint": None,
                "depends_on": {
                    "chummer-portal-volume-init": {
                        "condition": "service_completed_successfully",
                        "required": True,
                    },
                    "chummer-public-blazor": {
                        "condition": "service_healthy",
                        "required": True,
                    },
                    "chummer-run-identity": {
                        "condition": "service_healthy",
                        "required": True,
                    },
                    "support-progress-mock": {
                        "condition": "service_healthy",
                        "required": True,
                    },
                },
                "extra_hosts": [
                    "db.example.net=34.107.1.2",
                    "host.docker.internal=host-gateway",
                ],
                "environment": {
                    "ASPNETCORE_ENVIRONMENT": "Production",
                    "AllowedHosts": "chummer.run",
                    "CHUMMER_ACCOUNT_ERASURE_JOURNAL_PATH": (
                        "/app/state/account-erasure-journal.json"
                    ),
                    "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY": "a" * 64,
                    "CHUMMER_DATA_PROTECTION_KEYS_PATH": (
                        "/app/state/data-protection-keys-v2"
                    ),
                    "CHUMMER_PUBLIC_ALLOWED_HOSTS": "chummer.run",
                    "CHUMMER_PUBLIC_CANONICAL_ORIGIN": "https://chummer.run",
                    "CHUMMER_PUBLIC_CANON_ROOT": "/app",
                    "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
                    "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
                    "CHUMMER_RELEASE_UPLOAD_SESSION_ROOT": "/release-upload-sessions",
                    "CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED": "false",
                    "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
                    "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE": (
                        "chummer_install_linking"
                    ),
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST": "db.example.net",
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT": "5432",
                    "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE": (
                        "chummer_runtime"
                    ),
                    "SECRET_NOT_ALLOWED_IN_RECEIPT": "do-not-copy",
                },
                "volumes": [
                    bind(str(overlay_root), "/app", read_only=True),
                    volume("chummer-run-api-state", "/app/state"),
                    bind(
                        "/runbook/credentials/data-protection.pfx",
                        "/run/chummer-secrets/data-protection-key-encryption.pfx",
                        read_only=True,
                    ),
                    bind(
                        "/runbook/credentials/data-protection.password",
                        "/run/chummer-secrets/data-protection-key-encryption.password",
                        read_only=True,
                    ),
                    bind(
                        "/runbook/credentials/postgres-runtime.connection-string",
                        "/run/chummer-secrets/install-linking-postgres-runtime.connection-string",
                        read_only=True,
                    ),
                    bind(
                        "/runbook/credentials/postgres-server-ca.pem",
                        "/run/chummer-secrets/install-linking-postgres-server-ca.pem",
                        read_only=True,
                    ),
                    bind(
                        "/docker/fleet/.codex-studio/published",
                        "/fleet-artifacts",
                        read_only=True,
                    ),
                    bind(downloads_source, "/downloads-source"),
                    volume(
                        "chummer-release-upload-sessions", "/release-upload-sessions"
                    ),
                    volume("chummer-windows-proof-store", "/windows-proof-store"),
                    volume(
                        "chummer-windows-proof-upload-sessions",
                        "/windows-proof-upload-sessions",
                    ),
                    bind(
                        str(runtime_proof_bind_source),
                        "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json",
                        read_only=True,
                    ),
                    bind(
                        str(runtime_proof_bind_source),
                        (
                            "/app/wwwroot/proofs/mac-codex-release/"
                            "HUB_LOCAL_RELEASE_PROOF.generated.json"
                        ),
                        read_only=True,
                    ),
                    bind(
                        str(projection_root),
                        "/public-projection",
                        read_only=True,
                    ),
                    bind(
                        "/docker/chummercomplete/chummer.run-services/.codex-studio/"
                        "published/FINAL_GOLD_JANITOR.generated.json",
                        "/proofs/FINAL_GOLD_JANITOR.generated.json",
                        read_only=True,
                    ),
                ],
                "ports": [
                    {
                        "mode": "ingress",
                        "target": 8080,
                        "published": "8091",
                        "protocol": "tcp",
                    }
                ],
                "healthcheck": {
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
                },
                "networks": {
                    "public-origin": {"aliases": ["chummer-portal"]},
                    "fleet-origin": {},
                    "ea-origin": {},
                },
            },
            "chummer-install-linking-postgres-admin": {
                "image": "chummer-install-linking-postgres-tool:local",
                "build": build(tool=True),
                "profiles": ["install-linking-postgres-admin"],
                "restart": "no",
                "user": "1654:1654",
                "read_only": True,
                **security,
                "command": ["validate"],
                "entrypoint": None,
                "tmpfs": ["/tmp:rw,noexec,nosuid,nodev,mode=1777"],
                "extra_hosts": ["db.example.net=34.107.1.2"],
                "environment": {
                    "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE": (
                        "/run/chummer-secrets/"
                        "install-linking-postgres-migrator.connection-string"
                    ),
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE": (
                        "chummer_install_linking"
                    ),
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST": "db.example.net",
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT": "5432",
                    "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE": "chummer_runtime",
                },
                "volumes": [
                    bind(
                        "/runbook/credentials/postgres-migrator.connection-string",
                        "/run/chummer-secrets/"
                        "install-linking-postgres-migrator.connection-string",
                        read_only=True,
                    ),
                    bind(
                        "/runbook/credentials/postgres-server-ca.pem",
                        "/run/chummer-secrets/install-linking-postgres-server-ca.pem",
                        read_only=True,
                    ),
                ],
                "networks": {"public-origin": {}},
            },
            "chummer-install-linking-postgres-import": {
                "image": "chummer-install-linking-postgres-tool:local",
                "build": build(tool=True),
                "profiles": ["install-linking-postgres-admin"],
                "restart": "no",
                "user": "1654:1654",
                "read_only": True,
                **security,
                "command": ["refuse-import-without-explicit-command"],
                "entrypoint": None,
                "tmpfs": ["/tmp:rw,noexec,nosuid,nodev,mode=1777"],
                "extra_hosts": ["db.example.net=34.107.1.2"],
                "environment": {
                    "ASPNETCORE_ENVIRONMENT": "Production",
                    "CHUMMER_DATA_PROTECTION_KEYS_PATH": (
                        "/app/state/data-protection-keys-v2"
                    ),
                    "CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH": (
                        "/run/chummer-secrets/data-protection-key-encryption.pfx"
                    ),
                    "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE": (
                        "/run/chummer-secrets/"
                        "data-protection-key-encryption.password"
                    ),
                    "CHUMMER_INSTALL_LINKING_STORE_PATH": (
                        "/app/state/install-linking/install-linking-store.json"
                    ),
                    "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE": (
                        "/run/chummer-secrets/"
                        "install-linking-postgres-runtime.connection-string"
                    ),
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE": (
                        "chummer_install_linking"
                    ),
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST": "db.example.net",
                    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT": "5432",
                },
                "volumes": [
                    volume("chummer-run-api-state", "/app/state"),
                    bind(
                        "/runbook/credentials/data-protection.pfx",
                        "/run/chummer-secrets/data-protection-key-encryption.pfx",
                        read_only=True,
                    ),
                    bind(
                        "/runbook/credentials/data-protection.password",
                        "/run/chummer-secrets/data-protection-key-encryption.password",
                        read_only=True,
                    ),
                    bind(
                        "/runbook/credentials/postgres-runtime.connection-string",
                        "/run/chummer-secrets/"
                        "install-linking-postgres-runtime.connection-string",
                        read_only=True,
                    ),
                    bind(
                        "/runbook/credentials/postgres-server-ca.pem",
                        "/run/chummer-secrets/install-linking-postgres-server-ca.pem",
                        read_only=True,
                    ),
                ],
                "networks": {"public-origin": {}},
            },
        },
    }


def fixture_runtime_proof(projection_root: Path) -> Path:
    return (
        projection_root
        / f"public-projection-{'a' * 64}"
        / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    )


def fixture_roots(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source_root = tmp_path / "source"
    build_context = tmp_path / "workspace"
    overlay_root = tmp_path / "overlay" / "app"
    projection_root = tmp_path / "projection"
    runtime_proof_bind_source = fixture_runtime_proof(projection_root)
    (source_root / "Chummer.Run.Api").mkdir(parents=True)
    build_context.mkdir()
    overlay_root.mkdir(parents=True)
    runtime_proof_bind_source.parent.mkdir(parents=True)
    runtime_proof_bind_source.write_text("{}\n", encoding="utf-8")
    runtime_proof_bind_source.chmod(0o644)
    (source_root / "Chummer.Run.Api" / "Dockerfile").write_text(
        "FROM scratch\n", encoding="utf-8"
    )
    return source_root, build_context, overlay_root, projection_root


def test_compose_attestation_accepts_only_canonical_runtime_and_omits_environment(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )

    receipt = module.validate_runtime(
        payload,
        project_name="chummer6-hub",
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
        runtime_proof_bind_source=fixture_runtime_proof(projection_root),
        published_port=8091,
    )
    output = tmp_path / "receipt.json"
    module.atomic_write_json(output, receipt)

    assert receipt["status"] == "pass"
    assert receipt["projectionRoot"] == str(projection_root)
    assert receipt["projectionRootReadOnly"] is True
    assert receipt["runtimeProofBindSource"] == str(
        fixture_runtime_proof(projection_root)
    )
    assert receipt["runtimeProofBindSourceReadOnly"] is True
    compatibility = receipt["productionRuntimeCompatibility"]
    assert compatibility["status"] == "pass"
    assert all(compatibility["checks"].values())
    assert compatibility["secretValuesPersisted"] is False
    topology = receipt["portalOverlayMountTopology"]
    assert topology["status"] == "pass"
    assert topology["sourcePathsPersisted"] is False
    assert topology["sourceContentPersisted"] is False
    assert {
        row["containerTarget"] for row in topology["destinations"]
    } == {
        "/app",
        "/app/state",
        (
            "/app/wwwroot/proofs/mac-codex-release/"
            "HUB_LOCAL_RELEASE_PROOF.generated.json"
        ),
    }
    assert (
        stat.S_IMODE(fixture_runtime_proof(projection_root).stat().st_mode) == 0o644
    )
    assert receipt["operation"] == "deploy"
    assert receipt["releaseShelfPosture"] == {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    }
    assert receipt["proxyGates"] == {
        "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
        "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
    }
    serialized_receipt = output.read_text(encoding="utf-8")
    assert "do-not-copy" not in serialized_receipt
    assert "/runbook/credentials/" not in serialized_receipt
    assert "environment" not in receipt
    assert "volumes" not in receipt
    assert os.stat(output).st_mode & 0o777 == 0o600


def test_compose_attestation_accepts_consistent_nonroot_operator_identity(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    services = payload["services"]
    services["chummer-portal-volume-init"]["environment"] = {
        "CHUMMER_PORTAL_UID": "1000",
        "CHUMMER_PORTAL_GID": "1000",
    }
    for service_name in (
        "chummer-portal",
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-import",
    ):
        service = services[service_name]
        service["user"] = "1000:1000"
        service["build"]["args"]["CHUMMER_RUNTIME_UID"] = "1000"
        service["build"]["args"]["CHUMMER_RUNTIME_GID"] = "1000"

    receipt = module.validate_runtime(
        payload,
        project_name="chummer6-hub",
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
        runtime_proof_bind_source=fixture_runtime_proof(projection_root),
        published_port=8091,
    )

    assert receipt["status"] == "pass"
    assert all(
        build["runtimeIdentityConsistent"] is True
        for build in receipt["builds"].values()
    )


def test_compose_attestation_accepts_reviewed_single_label_postgres_host(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    services = payload["services"]
    reviewed_host = "chummer-private-stage-install-linking-postgres"
    reviewed_mapping = f"{reviewed_host}=172.25.0.12"
    services["chummer-portal"]["environment"][
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST"
    ] = reviewed_host
    services["chummer-portal"]["extra_hosts"][0] = reviewed_mapping
    for service_name in (
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-import",
    ):
        services[service_name]["environment"][
            "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST"
        ] = reviewed_host
        services[service_name]["extra_hosts"] = [reviewed_mapping]

    receipt = module.validate_runtime(
        payload,
        project_name="chummer6-hub",
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
        runtime_proof_bind_source=fixture_runtime_proof(projection_root),
        published_port=8091,
    )

    assert receipt["status"] == "pass"


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("ip-host", "canonical lowercase DNS name"),
        ("uppercase-host", "canonical lowercase DNS name"),
        ("invalid-address", "address is invalid"),
        ("loopback-address", "routable IPv4 address"),
        ("admin-mapping", "admin extra_hosts"),
        ("import-host", "import PostgreSQL expected host drifted"),
        ("missing-ca", "mount set is not canonical"),
    ],
)
def test_compose_attestation_rejects_postgres_identity_or_ca_drift(
    tmp_path: Path,
    drift: str,
    message: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    services = payload["services"]
    portal = services["chummer-portal"]
    admin = services["chummer-install-linking-postgres-admin"]
    importer = services["chummer-install-linking-postgres-import"]

    if drift == "ip-host":
        portal["environment"][
            "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST"
        ] = "34.107.1.2"
    elif drift == "uppercase-host":
        portal["environment"][
            "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST"
        ] = "DB.example.net"
    elif drift == "invalid-address":
        portal["extra_hosts"][0] = "db.example.net=not-an-address"
    elif drift == "loopback-address":
        portal["extra_hosts"][0] = "db.example.net=127.0.0.1"
    elif drift == "admin-mapping":
        admin["extra_hosts"] = ["db.example.net=34.107.1.3"]
    elif drift == "import-host":
        importer["environment"][
            "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST"
        ] = "other.example.net"
    elif drift == "missing-ca":
        portal["volumes"] = [
            mount
            for mount in portal["volumes"]
            if mount["target"]
            != "/run/chummer-secrets/install-linking-postgres-server-ca.pem"
        ]
    else:  # pragma: no cover - the parameter list is the closed authority.
        raise AssertionError(f"unhandled PostgreSQL identity drift: {drift}")

    with pytest.raises(ValueError, match=message):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=projection_root,
            runtime_proof_bind_source=fixture_runtime_proof(projection_root),
            published_port=8091,
        )


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("obsolete-target", "mount targets are not canonical"),
        ("wrong-source", "source is not canonical"),
        ("read-write", "must be read-only"),
        ("duplicate-target", "mount targets must be unique strings"),
        ("missing", "mount set is not canonical"),
        ("wrong-source-kind", "type policy drifted"),
        ("propagation", "type policy drifted"),
    ],
)
def test_compose_attestation_rejects_projection_mount_drift(
    tmp_path: Path,
    drift: str,
    message: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    volumes = payload["services"]["chummer-portal"]["volumes"]
    projection_mount = next(
        mount for mount in volumes if mount["target"] == "/public-projection"
    )

    if drift == "obsolete-target":
        projection_mount["target"] = (
            "/app/wwwroot/proofs/mac-codex-release/"
            "OBSOLETE_RELEASE_PROOF.generated.json"
        )
    elif drift == "wrong-source":
        projection_mount["source"] = "/attacker/projection"
    elif drift == "read-write":
        projection_mount["read_only"] = False
    elif drift == "duplicate-target":
        volumes[-1] = copy.deepcopy(projection_mount)
    elif drift == "missing":
        volumes.remove(projection_mount)
    elif drift == "wrong-source-kind":
        projection_mount["type"] = "volume"
    elif drift == "propagation":
        projection_mount["bind"]["propagation"] = "rshared"
    else:  # pragma: no cover - the parameter list is the closed authority.
        raise AssertionError(f"unhandled projection drift: {drift}")

    with pytest.raises(ValueError, match=message):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=projection_root,
            runtime_proof_bind_source=fixture_runtime_proof(projection_root),
            published_port=8091,
        )


@pytest.mark.parametrize(
    ("authority", "message"),
    [
        ("relative", "must be absolute"),
        ("symlink", "canonical non-symlink"),
        ("writable", "must not be group- or world-writable"),
    ],
)
def test_compose_attestation_rejects_untrusted_projection_root_authority(
    tmp_path: Path,
    authority: str,
    message: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    supplied_root = projection_root
    if authority == "relative":
        supplied_root = Path("projection")
    elif authority == "symlink":
        supplied_root = tmp_path / "projection-link"
        supplied_root.symlink_to(projection_root, target_is_directory=True)
    elif authority == "writable":
        projection_root.chmod(0o775)
    else:  # pragma: no cover - the parameter list is the closed authority.
        raise AssertionError(f"unhandled projection authority: {authority}")

    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=supplied_root,
    )
    with pytest.raises((OSError, ValueError), match=message):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=supplied_root,
            runtime_proof_bind_source=fixture_runtime_proof(projection_root),
            published_port=8091,
        )


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("wrong-target", "mount targets are not canonical"),
        ("wrong-source", "source is not canonical"),
        ("read-write", "must be read-only"),
        ("duplicate-target", "mount targets must be unique strings"),
        ("missing", "mount set is not canonical"),
        ("wrong-source-kind", "type policy drifted"),
        ("propagation", "type policy drifted"),
    ],
)
def test_compose_attestation_rejects_runtime_proof_mount_drift(
    tmp_path: Path,
    drift: str,
    message: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    runtime_proof_bind_source = fixture_runtime_proof(projection_root)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
        runtime_proof_bind_source=runtime_proof_bind_source,
    )
    volumes = payload["services"]["chummer-portal"]["volumes"]
    proof_mount = next(
        mount
        for mount in volumes
        if mount["target"] == "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json"
    )

    if drift == "wrong-target":
        proof_mount["target"] = "/proofs/unapproved.json"
    elif drift == "wrong-source":
        proof_mount["source"] = "/attacker/proof.json"
    elif drift == "read-write":
        proof_mount["read_only"] = False
    elif drift == "duplicate-target":
        volumes[-1] = copy.deepcopy(proof_mount)
    elif drift == "missing":
        volumes.remove(proof_mount)
    elif drift == "wrong-source-kind":
        proof_mount["type"] = "volume"
    elif drift == "propagation":
        proof_mount["bind"]["propagation"] = "rshared"
    else:  # pragma: no cover - the parameter list is the closed authority.
        raise AssertionError(f"unhandled runtime proof drift: {drift}")

    with pytest.raises(ValueError, match=message):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=projection_root,
            runtime_proof_bind_source=runtime_proof_bind_source,
            published_port=8091,
        )


@pytest.mark.parametrize(
    ("authority", "message"),
    [
        ("relative", "must be absolute"),
        ("symlink", "canonical non-symlink"),
        ("hardlink", "exactly one hard link"),
        ("mode-0600", "exact mode 0644"),
        ("mode-0640", "exact mode 0644"),
        ("writable", "must not be group- or world-writable"),
        ("writable-parent", "snapshot directory must not be group- or world-writable"),
        ("missing", "No such file"),
        ("outside-projection", "canonical projection snapshot proof"),
    ],
)
def test_compose_attestation_rejects_untrusted_runtime_proof_authority(
    tmp_path: Path,
    authority: str,
    message: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    runtime_proof_bind_source = fixture_runtime_proof(projection_root)
    supplied_source = runtime_proof_bind_source
    if authority == "relative":
        supplied_source = Path("HUB_LOCAL_RELEASE_PROOF.generated.json")
    elif authority == "symlink":
        supplied_source = (
            projection_root
            / f"public-projection-{'b' * 64}"
            / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
        supplied_source.parent.mkdir()
        supplied_source.symlink_to(runtime_proof_bind_source)
    elif authority == "hardlink":
        os.link(runtime_proof_bind_source, tmp_path / "runtime-proof-hardlink")
    elif authority == "mode-0600":
        runtime_proof_bind_source.chmod(0o600)
    elif authority == "mode-0640":
        runtime_proof_bind_source.chmod(0o640)
    elif authority == "writable":
        runtime_proof_bind_source.chmod(0o664)
    elif authority == "writable-parent":
        runtime_proof_bind_source.parent.chmod(0o775)
    elif authority == "missing":
        supplied_source = (
            projection_root
            / f"public-projection-{'b' * 64}"
            / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
    elif authority == "outside-projection":
        supplied_source = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        supplied_source.write_text("{}\n", encoding="utf-8")
        supplied_source.chmod(0o644)
    else:  # pragma: no cover - the parameter list is the closed authority.
        raise AssertionError(f"unhandled runtime proof authority: {authority}")

    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
        runtime_proof_bind_source=supplied_source,
    )
    with pytest.raises((OSError, ValueError), match=message):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=projection_root,
            runtime_proof_bind_source=supplied_source,
            published_port=8091,
        )


@pytest.mark.parametrize(
    ("operation", "layout_required", "migration_allowed"),
    [
        ("deploy", "true", "false"),
        ("initial-release-shelf-cutover", "false", "true"),
        ("initial-release-shelf-cutover-recover", "false", "false"),
    ],
)
def test_compose_attestation_accepts_only_exact_operation_posture(
    tmp_path: Path,
    operation: str,
    layout_required: str,
    migration_allowed: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    environment = payload["services"]["chummer-portal"]["environment"]
    environment["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] = layout_required
    environment["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = migration_allowed

    receipt = module.validate_runtime(
        payload,
        project_name="chummer6-hub",
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
        runtime_proof_bind_source=fixture_runtime_proof(projection_root),
        published_port=8091,
        operation=operation,
    )

    assert receipt["operation"] == operation
    assert receipt["releaseShelfPosture"] == {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": layout_required,
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": migration_allowed,
    }


@pytest.mark.parametrize(
    ("operation", "layout_required", "migration_allowed"),
    [
        (operation, layout_required, migration_allowed)
        for operation, accepted in (
            ("deploy", ("true", "false")),
            ("initial-release-shelf-cutover", ("false", "true")),
            ("initial-release-shelf-cutover-recover", ("false", "false")),
        )
        for layout_required, migration_allowed in (
            ("true", "true"),
            ("true", "false"),
            ("false", "true"),
            ("false", "false"),
        )
        if (layout_required, migration_allowed) != accepted
    ],
)
def test_compose_attestation_rejects_every_other_operation_posture(
    tmp_path: Path,
    operation: str,
    layout_required: str,
    migration_allowed: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    environment = payload["services"]["chummer-portal"]["environment"]
    environment["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] = layout_required
    environment["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = migration_allowed

    with pytest.raises(ValueError, match="exact .* literal value"):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=projection_root,
            runtime_proof_bind_source=fixture_runtime_proof(projection_root),
            published_port=8091,
            operation=operation,
        )


@pytest.mark.parametrize(
    "runtime_role",
    (
        "chummer_runtime",
        "_",
        "r" + "0" * 62,
    ),
)
def test_compose_attestation_accepts_postgres_tool_runtime_role_contract(
    tmp_path: Path,
    runtime_role: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    payload["services"]["chummer-install-linking-postgres-admin"][
        "environment"
    ]["CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE"] = runtime_role
    payload["services"]["chummer-portal"]["environment"][
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE"
    ] = runtime_role

    receipt = module.validate_runtime(
        payload,
        project_name="chummer6-hub",
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
        runtime_proof_bind_source=fixture_runtime_proof(projection_root),
        published_port=8091,
    )

    assert receipt["status"] == "pass"


@pytest.mark.parametrize(
    "runtime_role",
    (
        "",
        "9runtime",
        "Runtime",
        "runtime-role",
        "runtime role",
        "r" + "0" * 63,
    ),
)
def test_compose_attestation_rejects_roles_rejected_by_postgres_tool(
    tmp_path: Path,
    runtime_role: str,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    payload["services"]["chummer-install-linking-postgres-admin"][
        "environment"
    ]["CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE"] = runtime_role

    with pytest.raises(ValueError, match="\\^\\[a-z_\\]"):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=projection_root,
            runtime_proof_bind_source=fixture_runtime_proof(projection_root),
            published_port=8091,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(name="other"), "project name"),
        (
            lambda payload: payload["services"]["chummer-portal"].update(image="other"),
            "portal image",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["volumes"][0].update(
                read_only=False
            ),
            "must be read-only",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["ports"][0].update(
                published="8092"
            ),
            "portal ports",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_PUBLIC_PLAY_PROXY_ENABLED="true"
            ),
            "literal string false",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_PUBLIC_PLAY_PROXY_URL="https://retired.invalid"
            ),
            "forbidden retired proxy key",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_DATA_PROTECTION_KEYS_PATH="/app/state/data-protection-keys"
            ),
            "CHUMMER_DATA_PROTECTION_KEYS_PATH",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-import"
            ]["environment"].update(
                CHUMMER_DATA_PROTECTION_KEYS_PATH="/app/state/data-protection-keys"
            ),
            "import environment",
        ),
        (
            lambda payload: payload["services"]["chummer-install-linking-postgres-admin"][
                "build"
            ].update(target="other"),
            "build authority drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(user="0:0"),
            "same nonroot uid:gid",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-import"
            ].update(user="1655:1654"),
            "same nonroot uid:gid",
        ),
        (
            lambda payload: payload["services"]["chummer-portal-volume-init"][
                "environment"
            ].update(CHUMMER_PORTAL_UID="1655"),
            "initializer identity",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                privileged=True
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(pid="host"),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(ipc="host"),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                devices=["/dev/kvm:/dev/kvm"]
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                userns_mode="host"
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                runtime="attacker-runtime"
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                sysctls={"net.ipv4.ip_unprivileged_port_start": "0"}
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                group_add=["docker"]
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                isolation="hyperv"
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                cpu_shares=512
            ),
            "resource limits drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(cpus=2),
            "resource limits drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                mem_limit="3221225472"
            ),
            "resource limits drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-admin"
            ].update(pid="host"),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-admin"
            ].update(env_file=["/run/secrets/attacker.env"]),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal-volume-init"].update(
                cgroup="host"
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-import"
            ].update(ipc="host"),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                cap_add=["NET_ADMIN"]
            ),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal-volume-init"].update(
                cap_add=["CHOWN", "SETUID", "SETGID", "NET_ADMIN"]
            ),
            "cap_add drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-admin"
            ].update(read_only=False),
            "read_only policy drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal-volume-init"].update(
                pids_limit=64
            ),
            "pids_limit policy drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                ulimits={"core": {}, "nofile": {}}
            ),
            "ulimits drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["build"][
                "args"
            ].update(CHUMMER_RUNTIME_UID="0"),
            "build authority drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["build"][
                "additional_contexts"
            ].__setitem__(
                "hub-registry-source", "/tmp/untrusted-hub-registry"
            ),
            "build authority drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal-volume-init"].update(
                entrypoint=["/bin/sh"]
            ),
            "initializer entrypoint drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                command=["sleep", "infinity"]
            ),
            "command and entrypoint",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-admin"
            ].update(command=["import-local"]),
            "admin command drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-admin"
            ]["volumes"].append(
                {
                    "type": "bind",
                    "source": "/host",
                    "target": "/app",
                    "bind": {},
                }
            ),
            "mount set",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["volumes"][0][
                "bind"
            ].update(propagation="rshared"),
            "type policy drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-import"
            ].update(ports=[{"target": 8080, "published": "9999"}]),
            "service fields drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["healthcheck"].update(
                test=["CMD", "true"]
            ),
            "healthcheck drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["depends_on"][
                "chummer-portal-volume-init"
            ].update(condition="service_started"),
            "dependencies drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["extra_hosts"].append(
                "metadata.internal=169.254.169.254"
            ),
            "extra_hosts drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["networks"].update(
                attacker={}
            ),
            "networks drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-admin"
            ].update(profiles=["default"]),
            "profiles drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-import"
            ].update(tmpfs=["/tmp:rw,exec,suid,dev"]),
            "tmpfs drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-admin"
            ].update(restart="always"),
            "restart policy drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                AllowedHosts="*"
            ),
            "AllowedHosts is not the canonical literal value",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_PUBLIC_CANONICAL_ORIGIN="https://attacker.invalid"
            ),
            "CANONICAL_ORIGIN is not the canonical literal value",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_PUBLIC_CANONICAL_ORIGIN=""
            ),
            "CANONICAL_ORIGIN is not the canonical literal value",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_PUBLIC_CANONICAL_ORIGIN="http://chummer.run"
            ),
            "CANONICAL_ORIGIN is not the canonical literal value",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                ASPNETCORE_ENVIRONMENT="Development"
            ),
            "ASPNETCORE_ENVIRONMENT is not the canonical literal value",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED="false"
            ),
            "SHELF_LAYOUT_V1_REQUIRED is not the exact deploy literal value",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED="true"
            ),
            "DIRECT_BUNDLE_UPLOAD_ENABLED is not the canonical literal value",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_PUBLIC_PLAY_PROXY_BACKDOOR="http://attacker.invalid"
            ),
            "unrecognized proxy key",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-admin"
            ]["environment"].update(ASPNETCORE_ENVIRONMENT="Development"),
            "admin environment fields drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-install-linking-postgres-import"
            ]["environment"].update(ASPNETCORE_ENVIRONMENT="Development"),
            "import environment drifted",
        ),
    ],
)
def test_compose_attestation_rejects_runtime_authority_drift(
    tmp_path: Path, mutation, message: str
) -> None:
    module = load_module()
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = copy.deepcopy(
        rendered_compose(
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=projection_root,
        )
    )
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            projection_root=projection_root,
            runtime_proof_bind_source=fixture_runtime_proof(projection_root),
            published_port=8091,
        )


def test_compose_attestation_runs_under_isolated_python(tmp_path: Path) -> None:
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            str(SCRIPT),
            "--project-name",
            "chummer6-hub",
            "--source-root",
            str(source_root),
            "--build-context",
            str(build_context),
            "--overlay-root",
            str(overlay_root),
            "--projection-root",
            str(projection_root),
            "--runtime-proof-bind-source",
            str(fixture_runtime_proof(projection_root)),
            "--published-port",
            "8091",
            "--operation",
            "deploy",
            "--output",
            str(output),
        ],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "pass"


def test_compose_attestation_cli_rejects_ambiguous_missing_operation(
    tmp_path: Path,
) -> None:
    source_root, build_context, overlay_root, projection_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        projection_root=projection_root,
    )
    result = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            str(SCRIPT),
            "--project-name",
            "chummer6-hub",
            "--source-root",
            str(source_root),
            "--build-context",
            str(build_context),
            "--overlay-root",
            str(overlay_root),
            "--projection-root",
            str(projection_root),
            "--runtime-proof-bind-source",
            str(fixture_runtime_proof(projection_root)),
            "--published-port",
            "8091",
            "--output",
            str(tmp_path / "receipt.json"),
        ],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 2
    assert "--operation" in result.stderr
