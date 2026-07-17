from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
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


def rendered_compose(
    *, source_root: Path, build_context: Path, overlay_root: Path
) -> dict[str, object]:
    def build(*, tool: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "context": str(build_context),
            "dockerfile": str(source_root / "Chummer.Run.Api" / "Dockerfile"),
            "additional_contexts": {
                "run-services-source": str(source_root),
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
    hub_proof_source = (
        "/docker/chummercomplete/chummer.run-services/.codex-studio/published/"
        "HUB_LOCAL_RELEASE_PROOF.generated.json"
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
                "extra_hosts": ["host.docker.internal=host-gateway"],
                "environment": {
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
                        hub_proof_source,
                        "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json",
                        read_only=True,
                    ),
                    bind(
                        hub_proof_source,
                        "/app/wwwroot/proofs/mac-codex-release/"
                        "HUB_LOCAL_RELEASE_PROOF.generated.json",
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
                "environment": {
                    "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE": (
                        "/run/chummer-secrets/"
                        "install-linking-postgres-migrator.connection-string"
                    ),
                    "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE": "chummer_runtime",
                },
                "volumes": [
                    bind(
                        "/runbook/credentials/postgres-migrator.connection-string",
                        "/run/chummer-secrets/"
                        "install-linking-postgres-migrator.connection-string",
                        read_only=True,
                    )
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
                "environment": {
                    "ASPNETCORE_ENVIRONMENT": "Production",
                    "CHUMMER_DATA_PROTECTION_KEYS_PATH": "/app/state/data-protection-keys",
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
                ],
                "networks": {"public-origin": {}},
            },
        },
    }


def fixture_roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "source"
    build_context = tmp_path / "workspace"
    overlay_root = tmp_path / "overlay" / "app"
    (source_root / "Chummer.Run.Api").mkdir(parents=True)
    build_context.mkdir()
    overlay_root.mkdir(parents=True)
    (source_root / "Chummer.Run.Api" / "Dockerfile").write_text(
        "FROM scratch\n", encoding="utf-8"
    )
    return source_root, build_context, overlay_root


def test_compose_attestation_accepts_only_canonical_runtime_and_omits_environment(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
    )

    receipt = module.validate_runtime(
        payload,
        project_name="chummer6-hub",
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        published_port=8091,
    )
    output = tmp_path / "receipt.json"
    module.atomic_write_json(output, receipt)

    assert receipt["status"] == "pass"
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
            "must not be privileged",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].update(
                cap_add=["NET_ADMIN"]
            ),
            "cap_add must be empty",
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
            "import ports must be empty",
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
                CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED="false"
            ),
            "SHELF_LAYOUT_V1_REQUIRED is not the canonical literal value",
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
    source_root, build_context, overlay_root = fixture_roots(tmp_path)
    payload = copy.deepcopy(
        rendered_compose(
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
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
            published_port=8091,
        )


def test_compose_attestation_runs_under_isolated_python(tmp_path: Path) -> None:
    source_root, build_context, overlay_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
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
            "--published-port",
            "8091",
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
