import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "build-ghost-private-nonprod"
DEPLOY = OPS / "deploy-presentation-with-rollback.sh"
PREFLIGHT = OPS / "preflight-packet-access-state.sh"
DOCKERFILE = OPS / "Dockerfile.presentation-private-nonprod"
COMPOSE = (ROOT / "docker-compose.build-ghost-private-nonprod.yml").read_text(encoding="utf-8")
DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")
SCRIPT = DEPLOY.read_text(encoding="utf-8")
DOCKERFILE_TEXT = DOCKERFILE.read_text(encoding="utf-8")
CANARY = (OPS / "run-local-canary.sh").read_text(encoding="utf-8")


def main_body() -> str:
    return SCRIPT.split("main() {", 1)[1].split(
        'if [ "${BASH_SOURCE[0]}" = "$0" ]; then', 1
    )[0]


def run_preflight(store: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(PREFLIGHT), str(store)],
        check=False,
        capture_output=True,
        text=True,
    )


def write_json(path: Path, schema: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": schema}), encoding="utf-8")


def test_shell_entrypoints_are_syntax_valid_without_running_docker():
    for shell, script in (("bash", DEPLOY), ("sh", PREFLIGHT)):
        result = subprocess.run(
            [shell, "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_empty_packet_store_is_the_only_unkeyed_state_admitted(tmp_path):
    store = tmp_path / "store"
    for directory in ("pending", "claims", "audit", "revocations"):
        (store / directory).mkdir(parents=True)

    empty = run_preflight(store)
    assert empty.returncode == 0, empty.stderr
    assert empty.stdout == "packet_store_preflight=passed state=empty\n"

    write_json(store / "pending" / "opaque.json", "chummer.build_ghost.packet_access_pending.v1")
    unkeyed = run_preflight(store)
    assert unkeyed.returncode != 0
    assert "stage=nonempty-unkeyed-state" in unkeyed.stderr
    assert "opaque" not in unkeyed.stderr


def test_empty_legacy_consumed_directory_is_admitted_and_preserved(tmp_path):
    store = tmp_path / "store"
    (store / "pending").mkdir(parents=True)
    consumed = store / "consumed"
    consumed.mkdir()

    result = run_preflight(store)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "packet_store_preflight=passed state=empty\n"
    assert consumed.is_dir()
    assert not consumed.is_symlink()
    assert list(consumed.iterdir()) == []


@pytest.mark.parametrize("entry_kind", ("file", "directory", "symlink", "fifo"))
def test_nonempty_legacy_consumed_directory_is_rejected(tmp_path, entry_kind):
    store = tmp_path / "store"
    consumed = store / "consumed"
    consumed.mkdir(parents=True)
    entry = consumed / "legacy-entry"
    if entry_kind == "file":
        entry.write_text("legacy", encoding="utf-8")
    elif entry_kind == "directory":
        entry.mkdir()
    elif entry_kind == "symlink":
        target = tmp_path / "legacy-target"
        target.write_text("legacy", encoding="utf-8")
        entry.symlink_to(target)
    else:
        os.mkfifo(entry)

    result = run_preflight(store)

    assert result.returncode != 0
    assert "packet_store_preflight=failed" in result.stderr


@pytest.mark.parametrize("consumed_kind", ("file", "symlink", "fifo"))
def test_legacy_consumed_path_must_be_a_real_directory(tmp_path, consumed_kind):
    store = tmp_path / "store"
    store.mkdir()
    consumed = store / "consumed"
    if consumed_kind == "file":
        consumed.write_text("legacy", encoding="utf-8")
    elif consumed_kind == "symlink":
        target = tmp_path / "legacy-target"
        target.mkdir()
        consumed.symlink_to(target, target_is_directory=True)
    else:
        os.mkfifo(consumed)

    result = run_preflight(store)

    assert result.returncode != 0
    assert "packet_store_preflight=failed" in result.stderr


def test_v1_or_ambiguous_authority_fails_without_rewriting_state(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    authority = store / "state-authority.v2.json"
    write_json(authority, "chummer.build_ghost.packet_access_store_authority.v1")
    before = authority.read_bytes()

    result = run_preflight(store)

    assert result.returncode != 0
    assert "stage=authority-not-v2" in result.stderr
    assert authority.read_bytes() == before
    assert "rm " not in PREFLIGHT.read_text(encoding="utf-8")
    assert "mv " not in PREFLIGHT.read_text(encoding="utf-8")


def test_structurally_v2_state_is_admitted_but_v1_lifecycle_state_is_not(tmp_path):
    store = tmp_path / "store"
    write_json(
        store / "state-authority.v2.json",
        "chummer.build_ghost.packet_access_store_authority.v2",
    )
    schemas = {
        "pending": "chummer.build_ghost.packet_access_pending.v2",
        "claims": "chummer.build_ghost.packet_access_pending.v2",
        "audit": "chummer.build_ghost.packet_access_audit.v2",
        "revocations": "chummer.build_ghost.workspace_revocation.v2",
    }
    for directory, schema in schemas.items():
        write_json(store / directory / "opaque.json", schema)

    admitted = run_preflight(store)
    assert admitted.returncode == 0, admitted.stderr
    assert admitted.stdout == "packet_store_preflight=passed state=keyed-v2\n"

    write_json(store / "audit" / "legacy.json", "chummer.build_ghost.packet_access_audit.v1")
    legacy = run_preflight(store)
    assert legacy.returncode != 0
    assert "stage=lifecycle-state-not-v2" in legacy.stderr
    assert "legacy" not in legacy.stderr


def test_host_owned_dockerfile_binds_every_build_source_revision():
    assert "dockerfile: ops/build-ghost-private-nonprod/Dockerfile.presentation-private-nonprod" in COMPOSE
    assert "context: ." in COMPOSE
    for variable in (
        "CHUMMER_RUN_SERVICES_REVISION",
        "CHUMMER_PRESENTATION_REVISION",
        "CHUMMER_CORE_ENGINE_REVISION",
        "CHUMMER_HUB_REGISTRY_REVISION",
        "CHUMMER_UI_KIT_REVISION",
        "CHUMMER_MEDIA_FACTORY_REVISION",
    ):
        assert f"{variable}: ${{{variable}:?" in COMPOSE
        assert f"ARG {variable}" in DOCKERFILE_TEXT
    for context in (
        "presentation-source",
        "core-engine-source",
        "run-services-source",
        "hub-registry-source",
        "ui-kit-source",
        "media-factory-source",
    ):
        assert f"COPY --from={context}" in DOCKERFILE_TEXT
    assert 'org.opencontainers.image.revision="${CHUMMER_PRESENTATION_REVISION}"' in DOCKERFILE_TEXT
    assert 'run.chummer.build-ghost.profile="private-nonprod"' in DOCKERFILE_TEXT
    assert "!ops/build-ghost-private-nonprod/Dockerfile.presentation-private-nonprod" in DOCKERIGNORE


def test_deployer_uses_the_shared_nonblocking_lane_lock_for_the_whole_operation(tmp_path):
    assert (
        'deploy_lock_file="/docker/chummercomplete/.state/locks/'
        'chummer-build-ghost-private-nonprod-ai-deploy.lock"'
    ) in SCRIPT
    lock_file = tmp_path / "shared-deploy.lock"
    owner = subprocess.Popen(
        [
            "bash",
            "-c",
            'source "$1"; acquire_deploy_lock "$2"; printf "locked\\n"; read -r _',
            "owner",
            str(DEPLOY),
            str(lock_file),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert owner.stdout is not None
        assert owner.stdout.readline() == "locked\n"
        contender = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; acquire_deploy_lock "$2"',
                "contender",
                str(DEPLOY),
                str(lock_file),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert contender.returncode != 0
        assert "stage=concurrent-deploy-lock-held" in contender.stderr
    finally:
        assert owner.stdin is not None
        owner.stdin.close()
        owner.wait(timeout=5)


def test_source_and_store_admission_precede_candidate_build_and_activation():
    body = main_body()
    assert body.index("validate_sources_and_labels") < body.index("preserve_rollback_image")
    assert body.index('preflight_packet_store "$old_presentation_id"') < body.index(
        "build_candidate_under_limits"
    )
    assert body.index("build_candidate_under_limits") < body.index(
        "verify_activation_authority_unchanged"
    )
    assert body.index("verify_activation_authority_unchanged") < body.index(
        'activation_started="true"'
    )
    preactivation = SCRIPT.split("verify_activation_authority_unchanged()", 1)[1].split(
        "run_postchecks()", 1
    )[0]
    assert 'preflight_packet_store "$old_presentation_id"' in preactivation
    assert '[ "$(image_id "$rollback_ref")" = "$old_presentation_image" ]' in preactivation
    assert '[ "$(running_container_id "$ai_service")" = "$ai_id_before" ]' in preactivation
    assert '[ "$(running_container_id "$edge_service")" = "$edge_id_before" ]' in preactivation
    assert preactivation.count("validate_sources_and_labels") == 1


def test_release_pin_and_oci_revision_share_the_exact_presentation_main_commit():
    release_revision = "8090e53f6dd64794145d81d7698394e4881d0c02"
    assert f'presentation_release_revision="{release_revision}"' in SCRIPT
    assert (
        '[ "$CHUMMER_PRESENTATION_REVISION" = "$presentation_release_revision" ]'
        in SCRIPT
    )
    assert 'org.opencontainers.image.revision="${CHUMMER_PRESENTATION_REVISION}"' in DOCKERFILE_TEXT


def test_keyed_packet_preflight_parses_every_json_object_and_exact_schema():
    assert 'validate_packet_state_json "$container_id"' in SCRIPT
    assert "'type == \"object\" and (.schema | type == \"string\") and .schema == $expected'" in SCRIPT
    for schema in (
        "chummer.build_ghost.packet_access_store_authority.v2",
        "chummer.build_ghost.packet_access_pending.v2",
        "chummer.build_ghost.packet_access_audit.v2",
        "chummer.build_ghost.workspace_revocation.v2",
    ):
        assert schema in SCRIPT


def test_rendered_compose_uses_normalized_hub_context_and_exact_source_args():
    assert '--arg repo "$repo_root"' in SCRIPT
    assert '.services[$service].build.context == $repo' in SCRIPT
    assert '.services[$service].build.context == "."' not in SCRIPT
    for variable in (
        "CHUMMER_RUN_SERVICES_REVISION",
        "CHUMMER_PRESENTATION_REVISION",
        "CHUMMER_CORE_ENGINE_REVISION",
        "CHUMMER_HUB_REGISTRY_REVISION",
        "CHUMMER_UI_KIT_REVISION",
        "CHUMMER_MEDIA_FACTORY_REVISION",
    ):
        assert f".services[$service].build.args.{variable}" in SCRIPT


def test_rollback_image_is_unique_verified_and_preserved_before_build():
    assert 'old_presentation_image="$(docker inspect "$old_presentation_id" --format \'{{.Image}}\')"' in SCRIPT
    assert '[[ "$old_presentation_image" =~ ^sha256:[0-9a-f]{64}$ ]]' in SCRIPT
    assert 'nonce="$(openssl rand -hex 12)"' in SCRIPT
    assert 'rollback-${timestamp}-${old_short:0:16}-${nonce}' in SCRIPT
    assert 'docker image tag "$old_presentation_image" "$rollback_ref"' in SCRIPT
    assert '[ "$preserved_id" = "$old_presentation_image" ]' in SCRIPT
    body = main_body()
    assert body.index("preserve_rollback_image") < body.index("build_candidate_under_limits")


def test_activation_and_automatic_rollback_are_presentation_only():
    recreate = 'compose up -d --no-deps --no-build --force-recreate "$presentation_service"'
    assert SCRIPT.count(recreate) == 2
    assert 'docker image tag "$rollback_ref" "$deployment_image"' in SCRIPT
    assert 'compose up -d --no-deps --no-build --force-recreate "$ai_service"' not in SCRIPT
    assert 'compose up -d --no-deps --no-build --force-recreate "$edge_service"' not in SCRIPT
    for forbidden in (
        "compose down",
        "docker rm",
        "docker image rm",
        "docker rmi",
        "docker image prune",
        "docker system prune",
    ):
        assert forbidden not in SCRIPT
    assert "trap on_exit EXIT" in SCRIPT
    assert "rollback_if_needed" in SCRIPT
    assert 'candidate_built="true"' in SCRIPT
    assert "restore_pre_activation_tag_if_needed" in SCRIPT
    assert "preactivation-tag-restored" in SCRIPT


def test_postchecks_cover_auth_lifecycle_neighbors_gates_and_ingress_absence():
    assert 'private-route-missing-auth-not-401' in SCRIPT
    assert 'private-route-invalid-auth-not-401' in SCRIPT
    assert 'positive_canary=passed .*tool=200 replay=410 revoked=410 terminal_equivalent=true' in SCRIPT
    assert 'postcheck-keyed-authority-not-created' in SCRIPT
    assert 'postcheck-ai-container-changed' in SCRIPT
    assert 'postcheck-edge-container-changed' in SCRIPT
    assert "assert_provider_gates_false" in SCRIPT
    assert 'https://canary.chummer.run:$host_port/api/v1/ai/build-ghost/explain' in SCRIPT
    assert 'public-explain-not-404' in SCRIPT
    assert 'timeout --signal=TERM --kill-after=60s 900s' in SCRIPT


def test_canary_network_and_secret_cleanup_are_bounded_even_on_failure():
    assert '"$curl_binary" --connect-timeout 5 --max-time 30 "$@"' in CANARY
    cleanup = CANARY.split("cleanup() {", 1)[1].split("}\ntrap cleanup EXIT", 1)[0]
    assert "set +e" in cleanup
    assert "drain_grant || true" in cleanup
    assert "close_workspace || true" in cleanup
    assert "securely_remove_temp || true" in cleanup
    assert cleanup.index("securely_remove_temp") > cleanup.index("close_workspace")
    close = CANARY.split("close_workspace() {", 1)[1].split("\n}\n\ndrain_grant", 1)[0]
    assert "return 0" in close


def test_host_cutoffs_are_hard_and_build_polling_is_interruptible():
    assert 'CHUMMER_BUILD_GHOST_DEPLOY_MAX_IO_FULL_AVG10:-10' in SCRIPT
    assert 'CHUMMER_BUILD_GHOST_DEPLOY_MINIMUM_FREE_GIB:-20' in SCRIPT
    assert 'max-io-cutoff-must-not-exceed-ten' in SCRIPT
    assert 'minimum-free-space-must-be-at-least-twenty-gib' in SCRIPT
    assert 'build-poll-must-be-one-to-fifteen-seconds' in SCRIPT
    assert "/proc/pressure/io" in SCRIPT
    assert "df -Pk /docker" in SCRIPT
    assert "setsid bash -c" in SCRIPT
    assert 'kill -TERM -- "-$build_pid"' in SCRIPT
    assert 'kill -KILL -- "-$build_pid"' in SCRIPT


def test_runtime_secrets_are_inherited_only_in_memory_and_temp_is_shredded():
    assert "set -x" not in SCRIPT
    assert "load_runtime_environment_without_output" in SCRIPT
    assert "runtime-service-token-neighbor-drift" in SCRIPT
    assert 'compose config --format json > "$rendered"' in SCRIPT
    assert 'chmod 0600 "$rendered"' in SCRIPT
    assert 'shred --force --remove=unlink --zero "$path"' in SCRIPT
    assert "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN=" not in SCRIPT
    assert "CHUMMER_AI_INTERNAL_API_TOKEN=" not in SCRIPT
