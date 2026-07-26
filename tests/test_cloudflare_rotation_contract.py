from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.public-edge.yml"
RUNBOOK_PATH = ROOT / "scripts" / "runbook.sh"
PINNED_IMAGE = (
    "cloudflare/cloudflared:2026.7.0@"
    "sha256:8c70a8c2d373e93caac1ee79fcc615908a49ccf3f3975775d1e10d24e41327af"
)
TOKEN_TARGET = "/run/secrets/chummer-run-cloudflared.token"
COMPOSE_PROJECT_NAME = "chummer6-hub"
SERVICES = (
    "chummer-run-cloudflared",
    "chummer-run-cloudflared-replica",
)


def compose_payload() -> dict[str, object]:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI unavailable")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_PATH),
            "config",
            "--no-interpolate",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(result.stderr)
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def test_compose_defines_two_independent_hardened_token_file_connectors() -> None:
    payload = compose_payload()
    assert payload["name"] == COMPOSE_PROJECT_NAME
    services = payload["services"]
    assert isinstance(services, dict)

    for name in SERVICES:
        service = services[name]
        assert service["container_name"] == name
        assert service["image"] == PINNED_IMAGE
        assert service["platform"] == "linux/amd64"
        assert service["restart"] == "unless-stopped"
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert service.get("environment") in (None, {})
        command = service["command"]
        assert "--token-file" in command
        assert "--token" not in command
        assert TOKEN_TARGET in command
        health = service["healthcheck"]["test"]
        assert health == [
            "CMD",
            "cloudflared",
            "tunnel",
            "--metrics",
            "127.0.0.1:2000",
            "ready",
        ]
        mounts = [
            mount
            for mount in service["volumes"]
            if mount.get("target") == TOKEN_TARGET
        ]
        assert len(mounts) == 1
        assert mounts[0]["type"] == "bind"
        assert "CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE" in mounts[0]["source"]
        assert mounts[0]["target"] == TOKEN_TARGET
        assert mounts[0]["read_only"] is True
        assert mounts[0]["bind"] == {"create_host_path": False}
        assert "chummer-portal" in service["depends_on"]
        assert "public-origin" in service["networks"]


def test_docker_compose_accepts_anchor_and_hardening_contract() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI unavailable")
    version = subprocess.run(
        ["docker", "compose", "version"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if version.returncode != 0:
        pytest.skip("docker compose plugin unavailable")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_PATH),
            "config",
            "--no-interpolate",
            "-q",
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_runbook_is_proof_only_and_cannot_blindly_recreate_tunnel() -> None:
    source = RUNBOOK_PATH.read_text(encoding="utf-8")
    start = source.index("ensure_hub_cloudflare_tunnel() {")
    end = source.index("\nresolve_runbook_log_file()", start)
    function = source[start:end]

    assert "legacy_raw_token_requires_guarded_migration" in function
    assert "compose_env_not_owner_only" in function
    assert "token_file_not_owner_only" in function
    assert "canonical_connector_contract_failed" in function
    assert 'compose_project = "chummer6-hub"' in function
    assert "no lifecycle mutation performed" in function
    assert "docker compose" not in function
    assert " up " not in function


def test_runbook_documents_guarded_operator_contract() -> None:
    source = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "cloudflare-rotation-help" in source
    assert "Audit only (no Docker or Cloudflare mutation):" in source
    assert "Execute only after audit_passed:" in source
    assert "ROTATE_CHUMMER_RUN_CLOUDFLARE_TOKEN_ZERO_DOWNTIME" in source
    assert "three mandatory 600-second overlap dwells" in source
    assert "three additional mandatory 600-second dwells" in source
    assert "legacyMigrationCommitStarted or rotationCommitStarted" in source
    assert "never calls the Cloudflare connection DELETE endpoint" in source
    assert "/absolute/private/" in source
