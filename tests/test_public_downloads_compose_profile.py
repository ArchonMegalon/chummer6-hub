from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE = ROOT / "docker-compose.public-edge.yml"
PUBLIC_DOWNLOADS_COMPOSE = ROOT / "docker-compose.public-downloads.yml"
PORTAL = "chummer-portal"
POSTGRES_ENVIRONMENT_KEYS = {
    "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE",
    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST",
    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE",
    "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT",
    "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
}
POSTGRES_MOUNT_TARGETS = {
    "/run/chummer-secrets/install-linking-postgres-runtime.connection-string",
    "/run/chummer-secrets/install-linking-postgres-server-ca.pem",
}


def render_compose(*files: Path) -> dict[str, object]:
    command = ["docker", "compose"]
    for path in files:
        command.extend(["-f", str(path)])
    command.extend(
        [
            "--profile",
            "public-downloads",
            "config",
            "--format",
            "json",
            "--no-interpolate",
            "--no-env-resolution",
        ]
    )
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def portal(compose: dict[str, object]) -> dict[str, object]:
    services = compose["services"]
    assert isinstance(services, dict)
    value = services[PORTAL]
    assert isinstance(value, dict)
    return value


def volume_targets(service: dict[str, object]) -> set[str]:
    targets: set[str] = set()
    for volume in service.get("volumes", []):
        assert isinstance(volume, dict)
        target = volume.get("target")
        assert isinstance(target, str)
        targets.add(target)
    return targets


def environment_keys(service: dict[str, object]) -> set[str]:
    environment = service.get("environment", {})
    if isinstance(environment, dict):
        return set(environment)
    assert isinstance(environment, list)
    keys: set[str] = set()
    for item in environment:
        assert isinstance(item, str)
        keys.add(item.partition("=")[0])
    return keys


def test_public_download_profile_closes_inherited_runtime_authority() -> None:
    base = portal(render_compose(BASE_COMPOSE))
    scoped = portal(render_compose(BASE_COMPOSE, PUBLIC_DOWNLOADS_COMPOSE))

    base_environment_keys = environment_keys(base)
    scoped_environment_keys = environment_keys(scoped)
    assert POSTGRES_ENVIRONMENT_KEYS <= base_environment_keys
    assert scoped_environment_keys == set()

    base_targets = volume_targets(base)
    scoped_targets = volume_targets(scoped)
    assert POSTGRES_MOUNT_TARGETS <= base_targets
    assert scoped_targets == set()

    assert "extra_hosts" in base
    assert not scoped.get("extra_hosts")
    assert not scoped.get("depends_on")
    assert not scoped.get("env_file")
    assert scoped.get("profiles") == ["public-downloads"]


def test_public_download_profile_uses_only_the_scoped_portal_healthcheck() -> None:
    base = portal(render_compose(BASE_COMPOSE))
    scoped = portal(render_compose(BASE_COMPOSE, PUBLIC_DOWNLOADS_COMPOSE))

    base_test = base["healthcheck"]["test"]
    scoped_test = scoped["healthcheck"]["test"]
    assert base_test[-1] == "/api/ready"
    assert scoped_test[-1] == "/api/ready/public-downloads"
    assert "/api/ready/public-downloads" not in base_test
