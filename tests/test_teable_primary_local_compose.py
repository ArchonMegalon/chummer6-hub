"""Render the local preparation only: never build, create, start or contact Teable."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.teable-primary-local.yml"


def inputs() -> dict[str, str]:
    # No ambient .env, cloud credential or Docker context is inherited.
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "CHUMMER_HUB_PRIMARY_IDENTITY_IMAGE": "sha256:" + "a" * 64,
        "CHUMMER_HUB_PRIMARY_API_IMAGE": "sha256:" + "b" * 64,
        "CHUMMER_HUB_PRIMARY_IDENTITY_TABLE_ID": "tbl1111111111111111",
        "CHUMMER_HUB_PRIMARY_API_TABLE_ID": "tbl2222222222222222",
        **{
            f"CHUMMER_HUB_PRIMARY_{service}_{kind}": f"/synthetic/chummer/{service.lower()}/{kind.lower()}"
            for service in ("IDENTITY", "API")
            for kind in ("CONFIG_FILE", "TOKEN_FILE", "STATE_DIRECTORY")
        },
    }


def render(environment: dict[str, str], *, google: bool = False) -> subprocess.CompletedProcess[str]:
    if not shutil.which("docker"):
        pytest.skip("Docker Compose is required for actual interpolation verification")
    command = ["docker", "compose", "-p", "chummer-teable-primary-local", "--env-file", "/dev/null", "-f", str(COMPOSE)]
    if google:
        command += ["-f", str(ROOT / "docker-compose.teable-primary-google.yml")]
    return subprocess.run(
        [*command, "config", "--format", "json"],
        env=environment, cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
    )


@pytest.fixture(scope="module")
def config() -> dict:
    result = render(inputs())
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_preparation_is_separate_local_and_never_builds_or_pulls(config: dict) -> None:
    assert config["name"] == "chummer-teable-primary-local"
    assert set(config["services"]) == {"hub", "identity"}
    assert not config.get("volumes")
    assert not config.get("secrets")
    assert set(config["networks"]) == {"primary"}
    assert not config["networks"]["primary"].get("external", False)
    for service in config["services"].values():
        assert service["image"].startswith("sha256:")
        assert service["pull_policy"] == "never"
        assert "build" not in service and "env_file" not in service
        assert service["restart"] == "no"
        assert service["user"] == "1000:1000"
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert set(service["networks"]) == {"primary"}
    assert not config["services"]["identity"].get("ports")
    assert {port["host_ip"] for port in config["services"]["hub"]["ports"]} == {"127.0.0.1"}


def test_only_selected_private_files_and_separate_state_are_mounted(config: dict) -> None:
    for service_name, service in config["services"].items():
        mounts = {mount["target"]: mount for mount in service["volumes"]}
        role = "api" if service_name == "hub" else "identity"
        assert set(mounts) == {"/app/appsettings.Production.json", f"/run/chummer-primary/{role}.token", "/app/state"}
        for target, mount in mounts.items():
            assert mount["type"] == "bind"
            assert mount["bind"]["create_host_path"] is False
            assert mount["source"].startswith(f"/synthetic/chummer/{role}/")
            assert bool(mount.get("read_only", False)) is (target != "/app/state")


def test_account_book_modes_are_primary_and_legacy_authorities_are_not_inherited(config: dict) -> None:
    hub = config["services"]["hub"]["environment"]
    modes = (
        "INSTALL_LINKING", "INSTALL_LINKED_WORKSPACE", "COMMUNITY", "SUPPORT",
        "BILLING_MEMBERSHIP", "MYFIRSTBOOK_USAGE", "HORIZON_ARTIFACT_USAGE",
        "HORIZON_REQUEST_RECEIPT", "ORIGIN_PROVIDER_RESERVATION", "ORIGIN_CHAPTER",
        "ORIGIN_DOCUMENT", "ORIGIN_PUBLICATION",
    )
    for mode in modes:
        assert hub[f"CHUMMER_{mode}_STORAGE_PROVIDER"] == "teable"
        prefix = "ORIGIN" if mode == "ORIGIN_CHAPTER" else mode
        assert hub[f"CHUMMER_{prefix}_TEABLE_TABLE_ID"] == inputs()["CHUMMER_HUB_PRIMARY_API_TABLE_ID"]
        assert hub[f"CHUMMER_{prefix}_TEABLE_TOKEN_FILE"] == "/run/chummer-primary/api.token"
    assert hub["CHUMMER_DATA_PROTECTION_KEY_PROTECTION_MODE"] == "teable_primary"
    assert hub["CHUMMER_DATA_PROTECTION_TEABLE_TOKEN_FILE"] == "/run/chummer-primary/api.token"
    assert hub["IDENTITY_SERVICE_BASE_URL"] == "http://identity:8080"
    for service in config["services"].values():
        environment = service["environment"]
        assert environment["ASPNETCORE_ENVIRONMENT"] == "Production"
        assert environment["IDENTITY_EMAIL_START_ENABLED"] == "false"
        assert not any("POSTGRES" in key or "CERTIFICATE" in key or key == "TEABLE_API_KEY" for key in environment)
        assert not any(key.endswith("_API_KEY") for key in environment)
    identity = config["services"]["identity"]["environment"]
    assert identity["CHUMMER_IDENTITY_STORAGE_PROVIDER"] == "teable"
    assert identity["CHUMMER_TEABLE_TABLE_ID"] != hub["CHUMMER_COMMUNITY_TEABLE_TABLE_ID"]


def test_preparation_explicitly_disables_projection_reconciliation_and_news_delivery(config: dict) -> None:
    hub = config["services"]["hub"]["environment"]
    for key in (
        "CHUMMER_TEABLE_IMPORTANT_WORK_ENABLED",
        "CHUMMER_TEABLE_IMPORTANT_WORK_RECONCILE_ENABLED",
        "CHUMMER_TEABLE_IMPORTANT_WORK_AUTOSYNC_ENABLED",
        "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED",
    ):
        assert hub[key] == "false"


@pytest.mark.parametrize("missing", [
    "CHUMMER_HUB_PRIMARY_API_IMAGE", "CHUMMER_HUB_PRIMARY_IDENTITY_IMAGE",
    "CHUMMER_HUB_PRIMARY_API_TOKEN_FILE", "CHUMMER_HUB_PRIMARY_IDENTITY_TOKEN_FILE",
    "CHUMMER_HUB_PRIMARY_API_CONFIG_FILE", "CHUMMER_HUB_PRIMARY_IDENTITY_CONFIG_FILE",
    "CHUMMER_HUB_PRIMARY_API_STATE_DIRECTORY", "CHUMMER_HUB_PRIMARY_IDENTITY_STATE_DIRECTORY",
    "CHUMMER_HUB_PRIMARY_API_TABLE_ID", "CHUMMER_HUB_PRIMARY_IDENTITY_TABLE_ID",
])
def test_missing_explicit_inputs_fail_before_a_container_can_be_created(missing: str) -> None:
    environment = inputs()
    del environment[missing]
    result = render(environment)
    assert result.returncode != 0
    assert missing in result.stderr


def google_inputs() -> dict[str, str]:
    return {
        **inputs(),
        "GOOGLE_OIDC_CLIENT_ID": "synthetic-client.apps.googleusercontent.com",
        "GOOGLE_OIDC_CLIENT_SECRET": "synthetic-not-a-credential",
        "GOOGLE_OIDC_REDIRECT_URI": "https://chummer.run/auth/google/callback",
        "UNRELATED_SECRET": "must-not-be-forwarded",
    }


def test_google_activation_changes_only_four_hub_settings(config: dict) -> None:
    result = render(google_inputs(), google=True)
    assert result.returncode == 0, result.stderr
    activated = json.loads(result.stdout)
    environment = activated["services"]["hub"]["environment"]
    assert environment.pop("CHUMMER_GOOGLE_OIDC_REQUIRED") == "true"
    for key in ("GOOGLE_OIDC_CLIENT_ID", "GOOGLE_OIDC_CLIENT_SECRET", "GOOGLE_OIDC_REDIRECT_URI"):
        assert environment.pop(key) == google_inputs()[key]
    # Exact comparison preserves loopback bindings, worker separation, all
    # primary stores, disabled emails/news, image/state roots and Identity.
    assert activated == config


def test_explicit_local_project_overrides_a_legacy_env_project() -> None:
    environment = google_inputs()
    environment["COMPOSE_PROJECT_NAME"] = "chummer6-hub"
    result = render(environment, google=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["name"] == "chummer-teable-primary-local"


@pytest.mark.parametrize("missing", [
    "GOOGLE_OIDC_CLIENT_ID", "GOOGLE_OIDC_CLIENT_SECRET", "GOOGLE_OIDC_REDIRECT_URI",
])
@pytest.mark.parametrize("blank", [False, True])
def test_google_activation_rejects_missing_or_empty_credentials(missing: str, blank: bool) -> None:
    environment = google_inputs()
    if blank:
        environment[missing] = ""
    else:
        del environment[missing]
    result = render(environment, google=True)
    assert result.returncode != 0
    assert missing in result.stderr
