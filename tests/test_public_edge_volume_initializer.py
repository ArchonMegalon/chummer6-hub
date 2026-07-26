from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.public-edge.yml"
SCRIPT_PATH = ROOT / "scripts" / "initialize-public-edge-volumes.sh"
DOCKERFILE_PATH = ROOT / "Chummer.Run.Api" / "Dockerfile"


def run_sha256_validator(value: str) -> subprocess.CompletedProcess[str]:
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    start = script.index("validate_sha256() {")
    end = script.index("\n\nrequire_regular_input()", start)
    function = script[start:end]
    harness = (
        "set -eu\n"
        "fail() { printf '%s\\n' \"public-edge volume initialization failed: $*\" >&2; exit 1; }\n"
        f"{function}\n"
        'validate_sha256 TEST_SHA256 "$1"\n'
    )
    return subprocess.run(
        ["/bin/sh", "-eu", "-c", harness, "sha256-validator", value],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_sha256_validator_accepts_exact_lowercase_digest() -> None:
    result = run_sha256_validator("0123456789abcdef" * 4)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 63,
        "a" * 65,
        ("a" * 63) + "A",
        ("a" * 31) + "g" + ("a" * 32),
    ],
    ids=["empty", "63-chars", "65-chars", "uppercase", "nonhex"],
)
def test_sha256_validator_rejects_invalid_digest(value: str) -> None:
    result = run_sha256_validator(value)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "public-edge volume initialization failed: "
        "TEST_SHA256 must be a lowercase SHA-256\n"
    )


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
    assert (
        "ensure_private_directory_as_portal_identity /app/state/core-workspaces"
        in script
    )
    assert (
        "ensure_private_directory_as_portal_identity "
        "/app/state/data-protection-keys-v2"
    ) in script
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


def test_projection_seed_commits_the_exact_authority_pointer_last() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    start = script.index("copy_candidate_projection_authority() {")
    end = script.index("\n\ncopy_isolated_release_shelf()", start)
    projection_copy = script[start:end]

    assert "require_candidate_projection_snapshot" in projection_copy
    assert 'verify_file_sha256 \\\n    "$current_source"' in projection_copy
    assert 'verify_tree_sha256 \\\n    "$snapshot_source"' in projection_copy
    assert "--preserve=mode" in projection_copy
    assert "--no-preserve=ownership,timestamps" in projection_copy
    assert (
        'mv -- "$snapshot_stage" "$destination/$snapshot_id"'
        in projection_copy
    )
    assert (
        'mv -- "$current_stage" "$destination/CURRENT.json"'
        in projection_copy
    )
    assert projection_copy.index(
        'mv -- "$snapshot_stage" "$destination/$snapshot_id"'
    ) < projection_copy.index(
        'mv -- "$current_stage" "$destination/CURRENT.json"'
    )
    assert "copied public projection root contains extra material" in (
        projection_copy
    )
    assert projection_copy.count(
        '"public projection snapshot"'
    ) >= 4


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
    assert portal["environment"][
        "Chummer__CoreGmCharacterEdits__WorkspaceStorePath"
    ] == "/app/state/core-workspaces"
    assert portal["environment"]["CHUMMER_DATA_PROTECTION_KEYS_PATH"] == (
        "/app/state/data-protection-keys-v2"
    )
    assert services["chummer-install-linking-postgres-import"]["environment"][
        "CHUMMER_DATA_PROTECTION_KEYS_PATH"
    ] == "/app/state/data-protection-keys-v2"


def test_portal_image_contains_initializer_and_setpriv_contract() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert "command -v setpriv >/dev/null" in dockerfile
    assert (
        "COPY --from=run-services-source --chmod=0555 scripts/initialize-public-edge-volumes.sh "
        "/usr/local/libexec/chummer/initialize-public-edge-volumes.sh"
    ) in dockerfile
