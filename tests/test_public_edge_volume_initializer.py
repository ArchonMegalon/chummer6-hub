from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.public-edge.yml"
SCRIPT_PATH = ROOT / "scripts" / "initialize-public-edge-volumes.sh"
DOCKERFILE_PATH = ROOT / "Chummer.Run.Api" / "Dockerfile"


def test_initializer_is_fail_closed_and_never_chowns_downloads_bind() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert script.startswith("#!/bin/sh\nset -eu\n")
    assert "CHUMMER_PORTAL_UID:-1654" in script
    assert "CHUMMER_PORTAL_GID:-1654" in script
    assert "setpriv" in script
    assert "--clear-groups" in script
    assert "find -P \"$root\" -xdev" in script
    assert "! -type d ! -type f" in script
    assert "mkdir -m 700 -- \"$probe\"" in script
    assert "rm -f -- \"$probe/write-test\"" in script
    assert "require_mount_root /downloads-source" in script
    assert "probe_as_portal_identity /downloads-source" in script
    assert all(
        "/downloads-source" not in line
        for line in script.splitlines()
        if line.lstrip().startswith("chown ") or "-exec chown" in line
    )

    for root in (
        "/app/state",
        "/release-upload-sessions",
        "/windows-proof-store",
        "/windows-proof-upload-sessions",
    ):
        assert root in script


def test_initializer_service_is_root_only_and_portal_remains_nonroot() -> None:
    yaml = pytest.importorskip("yaml")
    payload = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = payload["services"]
    initializer = services["chummer-portal-volume-init"]
    portal = services["chummer-portal"]

    assert initializer["image"] == portal["image"] == "chummer-run-api:local"
    assert initializer["restart"] == "no"
    assert initializer["user"] == "0:0"
    assert initializer["read_only"] is True
    assert initializer["network_mode"] == "none"
    assert initializer["cap_drop"] == ["ALL"]
    assert initializer["cap_add"] == ["CHOWN", "SETUID", "SETGID"]
    assert initializer["security_opt"] == ["no-new-privileges:true"]
    assert initializer["pids_limit"] == 32
    assert initializer["entrypoint"] == [
        "/usr/local/libexec/chummer/initialize-public-edge-volumes.sh"
    ]
    assert initializer["environment"] == {
        "CHUMMER_PORTAL_UID": "${CHUMMER_PORTAL_UID:-1654}",
        "CHUMMER_PORTAL_GID": "${CHUMMER_PORTAL_GID:-1654}",
    }
    assert initializer["volumes"] == [
        "chummer-run-api-state:/app/state",
        "chummer-release-upload-sessions:/release-upload-sessions",
        "chummer-windows-proof-store:/windows-proof-store",
        "chummer-windows-proof-upload-sessions:/windows-proof-upload-sessions",
        "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads:/downloads-source",
    ]
    assert "networks" not in initializer
    assert "ports" not in initializer
    assert "env_file" not in initializer

    assert portal["depends_on"]["chummer-portal-volume-init"] == {
        "condition": "service_completed_successfully"
    }
    assert portal["user"] == "${CHUMMER_PORTAL_UID:-1654}:${CHUMMER_PORTAL_GID:-1654}"
    assert portal["cap_drop"] == ["ALL"]
    assert "CHOWN" not in portal.get("cap_add", [])


def test_portal_image_contains_initializer_and_setpriv_contract() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert "command -v setpriv >/dev/null" in dockerfile
    assert (
        "COPY --from=run-services-source --chmod=0555 scripts/initialize-public-edge-volumes.sh "
        "/usr/local/libexec/chummer/initialize-public-edge-volumes.sh"
    ) in dockerfile
