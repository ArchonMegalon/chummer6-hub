import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "build-ghost-private-nonprod"
DEPLOY = OPS / "deploy-presentation-with-rollback.sh"
AI_DEPLOY = OPS / "deploy-ai-with-rollback.sh"
PREFLIGHT = OPS / "preflight-packet-access-state.sh"
DOCKERFILE = OPS / "Dockerfile.presentation-private-nonprod"
COMPOSE = (ROOT / "docker-compose.build-ghost-private-nonprod.yml").read_text(encoding="utf-8")
DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")
SCRIPT = DEPLOY.read_text(encoding="utf-8")
DOCKERFILE_TEXT = DOCKERFILE.read_text(encoding="utf-8")
CANARY = (OPS / "run-local-canary.sh").read_text(encoding="utf-8")


def pressure_awk_program(script: Path) -> str:
    text = script.read_text(encoding="utf-8")
    marker = "io_full_avg10=\"$(awk '"
    return text.split(marker, 1)[1].split("' /proc/pressure/io)", 1)[0]


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


def run_deploy_harness(body: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", 'source "$1"; shift; ' + body, "harness", str(DEPLOY), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_shell_entrypoints_are_syntax_valid_without_running_docker():
    for shell, script in (("bash", DEPLOY), ("sh", PREFLIGHT)):
        result = subprocess.run(
            [shell, "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", (DEPLOY, AI_DEPLOY))
def test_host_pressure_probe_executes_on_the_host_awk(script):
    program = pressure_awk_program(script)
    result = subprocess.run(
        ["awk", program],
        input=(
            "some avg10=4.00 avg60=3.00 avg300=2.00 total=1\n"
            "full avg10=1.25 avg60=1.00 avg300=0.75 total=2\n"
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1.25\n"
    assert "for (index" not in program


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


@pytest.mark.parametrize("authority_kind", ("directory", "symlink", "fifo"))
def test_authority_marker_must_be_a_real_regular_file(tmp_path, authority_kind):
    store = tmp_path / "store"
    store.mkdir()
    authority = store / "state-authority.v2.json"
    if authority_kind == "directory":
        authority.mkdir()
    elif authority_kind == "symlink":
        target = tmp_path / "authority-target"
        target.write_text("{}", encoding="utf-8")
        authority.symlink_to(target)
    else:
        os.mkfifo(authority)

    result = run_preflight(store)

    assert result.returncode != 0
    assert "packet_store_preflight=failed" in result.stderr


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
    assert 'run.chummer.build-ghost.packet-store-schema="v2"' in DOCKERFILE_TEXT
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
    assert body.index("snapshot_presentation_authority") < body.index(
        "preflight_initial_packet_store"
    )
    assert body.index("preflight_initial_packet_store") < body.index(
        "validate_initial_packet_store_compatibility"
    )
    assert body.index("validate_initial_packet_store_compatibility") < body.index(
        "preserve_rollback_image"
    )
    assert body.index("preflight_initial_packet_store") < body.index(
        "build_candidate_under_limits"
    )
    assert body.index("build_candidate_under_limits") < body.index(
        "preserve_candidate_recovery_image"
    )
    assert body.index("preserve_candidate_recovery_image") < body.index(
        "verify_activation_authority_unchanged"
    )
    assert body.index("verify_activation_authority_unchanged") < body.index(
        "prepare_candidate_activation_tag"
    )
    assert body.index("prepare_candidate_activation_tag") < body.index(
        'activation_started="true"'
    )
    preactivation = SCRIPT.split("verify_activation_authority_unchanged()", 1)[1].split(
        "run_postchecks()", 1
    )[0]
    assert "preflight_initial_packet_store" in preactivation
    assert '[ "$(image_id "$rollback_ref")" = "$old_presentation_image" ]' in preactivation
    assert '[ "$(running_container_id "$ai_service")" = "$ai_id_before" ]' in preactivation
    assert '[ "$(running_container_id "$edge_service")" = "$edge_id_before" ]' in preactivation
    assert preactivation.count("validate_sources_and_labels") == 1


def test_internal_authority_probe_uses_the_shared_snake_case_wire_contract():
    probe = SCRIPT.split("verify_private_route_auth() {", 1)[1].split(
        "verify_public_explain_absent() {", 1
    )[0]
    assert "packet_access_key:$key" in probe
    assert "packet_digest:$digest" in probe
    assert "request_kind:\"current-build\"" in probe
    assert "packetAccessKey" not in probe
    assert "packetDigest" not in probe
    assert "requestKind" not in probe


def test_lifecycle_canary_failure_emits_only_its_bounded_receipt(tmp_path):
    canary = tmp_path / "failing-canary.sh"
    canary.write_text(
        "#!/bin/sh\n"
        "printf 'transport detail that must stay private\\n'\n"
        "printf 'positive_canary=failed stage=negative-boundaries provider_unknown_key=502\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    canary.chmod(0o700)
    result = run_deploy_harness(
        'deploy_tmp="$1"; canary_script="$2"; verify_lifecycle_canary',
        str(tmp_path),
        str(canary),
    )

    assert result.returncode != 0
    assert "positive_canary=failed stage=negative-boundaries provider_unknown_key=502" in result.stderr
    assert "stage=lifecycle-canary-failed" in result.stderr
    assert "transport detail" not in result.stderr


def test_lifecycle_canary_requires_the_exact_private_rook_terminal_receipt(tmp_path):
    current_canary = tmp_path / "current-canary.sh"
    current_canary.write_text(
        "#!/bin/sh\n"
        "printf 'positive_canary=passed tool=200 replay=410 revoked=410 "
        "terminal_equivalent=true gates=false cleanup=404 rook=text-fallback "
        "live_support=disabled store=private\\n'\n",
        encoding="utf-8",
    )
    current_canary.chmod(0o700)
    accepted = run_deploy_harness(
        'deploy_tmp="$1"; canary_script="$2"; verify_lifecycle_canary',
        str(tmp_path),
        str(current_canary),
    )

    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout == ""
    assert accepted.stderr == ""

    stale_canary = tmp_path / "stale-canary.sh"
    stale_canary.write_text(
        "#!/bin/sh\n"
        "printf 'positive_canary=passed tool=200 replay=410 revoked=410 "
        "terminal_equivalent=true gates=false cleanup=404\\n'\n",
        encoding="utf-8",
    )
    stale_canary.chmod(0o700)
    rejected = run_deploy_harness(
        'deploy_tmp="$1"; canary_script="$2"; verify_lifecycle_canary',
        str(tmp_path),
        str(stale_canary),
    )

    assert rejected.returncode != 0
    assert rejected.stdout == ""
    assert "stage=lifecycle-canary-receipt-drift" in rejected.stderr


def test_release_pin_and_oci_revision_share_the_exact_presentation_main_commit():
    release_revision = "1c492202ac708f302b59f47c2bb1e4c67e352328"
    assert f'presentation_release_revision="{release_revision}"' in SCRIPT
    assert (
        '[ "$CHUMMER_PRESENTATION_REVISION" = "$presentation_release_revision" ]'
        in SCRIPT
    )
    assert 'org.opencontainers.image.revision="${CHUMMER_PRESENTATION_REVISION}"' in DOCKERFILE_TEXT


def test_candidate_and_rollback_compatibility_use_the_exact_v2_image_label():
    assert 'packet_store_schema_label="run.chummer.build-ghost.packet-store-schema"' in SCRIPT
    assert 'packet_store_schema_version="v2"' in SCRIPT
    assert 'image-packet-store-schema-label-drift' in SCRIPT
    preserve = SCRIPT.split("preserve_rollback_image() {", 1)[1].split(
        "preflight_packet_store() {", 1
    )[0]
    assert 'image_label "$rollback_ref" "$packet_store_schema_label"' in preserve
    assert 'rollback-reference-schema-label-drift' in preserve


def test_keyed_v2_store_rejects_a_pre_v2_running_image_before_build():
    incompatible = run_deploy_harness(
        'initial_packet_store_state="keyed-v2"; '
        'old_presentation_store_schema=""; '
        "validate_initial_packet_store_compatibility"
    )
    assert incompatible.returncode != 0
    assert "stage=initial-keyed-v2-running-image-incompatible" in incompatible.stderr

    compatible = run_deploy_harness(
        'initial_packet_store_state="keyed-v2"; '
        'old_presentation_store_schema="v2"; '
        "validate_initial_packet_store_compatibility"
    )
    assert compatible.returncode == 0, compatible.stderr

    empty_legacy = run_deploy_harness(
        'initial_packet_store_state="empty"; '
        'old_presentation_store_schema=""; '
        "validate_initial_packet_store_compatibility"
    )
    assert empty_legacy.returncode == 0, empty_legacy.stderr


def test_contained_recovery_mode_is_explicit_and_requires_exact_v2_authority():
    invalid_mode = run_deploy_harness(
        'recovery_mode="automatic"; validate_control_values'
    )
    assert invalid_mode.returncode != 0
    assert "stage=presentation-recovery-mode-invalid" in invalid_mode.stderr

    accepted = run_deploy_harness(
        r'''
recovery_mode="true"
presentation_service="presentation"
packet_store_schema_label="packet-schema"
packet_store_schema_version="v2"
presentation_is_contained() { :; }
service_container_id_any_state() { printf 'stopped-presentation'; }
docker() {
    case "$*" in
        *State.Status*) printf 'exited' ;;
        *'{{.Image}}'*) printf 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' ;;
        *) return 1 ;;
    esac
}
image_id() { printf 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'; }
image_label() { printf 'v2'; }
packet_store_volume_name_from_presentation() { printf 'safe-volume'; }
snapshot_presentation_authority
printf 'id=%s image=%s volume=%s\n' "$old_presentation_id" "$old_presentation_image" "$old_packet_store_volume_name"
'''
    )
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout == (
        "id=stopped-presentation "
        "image=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
        "volume=safe-volume\n"
    )

    pre_v2 = run_deploy_harness(
        r'''
recovery_mode="true"
presentation_service="presentation"
packet_store_schema_label="packet-schema"
packet_store_schema_version="v2"
presentation_is_contained() { :; }
service_container_id_any_state() { printf 'stopped-presentation'; }
docker() {
    case "$*" in
        *State.Status*) printf 'exited' ;;
        *'{{.Image}}'*) printf 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' ;;
        *) return 1 ;;
    esac
}
image_id() { printf 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'; }
image_label() { printf 'v1'; }
packet_store_volume_name_from_presentation() { printf 'safe-volume'; }
snapshot_presentation_authority
'''
    )
    assert pre_v2.returncode != 0
    assert "stage=recovery-presentation-image-not-v2" in pre_v2.stderr


def test_contained_recovery_preflight_binds_the_old_volume_and_image():
    result = run_deploy_harness(
        r'''
recovery_mode="true"
old_packet_store_volume_name="safe-volume"
old_presentation_image="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
classify_packet_store_volume_for_rollback() {
    printf 'args=%s,%s\n' "$1" "$2" >&2
    printf 'keyed-v2'
}
preflight_initial_packet_store
printf 'state=%s\n' "$last_packet_store_state"
'''
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "state=keyed-v2\n"
    assert "args=safe-volume,sha256:" in result.stderr


def test_recovery_preactivation_rechecks_containment_volume_store_and_neighbors():
    result = run_deploy_harness(
        r'''
recovery_mode="true"
presentation_service="presentation"
ai_service="ai"
edge_service="edge"
rollback_ref="presentation:rollback"
old_presentation_id="stopped-presentation"
old_presentation_image="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
old_packet_store_volume_name="safe-volume"
candidate_recovery_ref="presentation:v2-recovery"
ai_id_before="ai-id"
edge_id_before="edge-id"
initial_packet_store_state="keyed-v2"
last_packet_store_state="keyed-v2"
image_id() { printf '%s' "$old_presentation_image"; }
candidate_recovery_is_preserved() { :; }
verify_source_labels() { [ "$1" = "$candidate_recovery_ref" ]; }
presentation_is_contained() { :; }
service_container_id_any_state() { printf 'stopped-presentation'; }
docker() {
    [ "$1" = "inspect" ] || return 1
    printf '%s' "$old_presentation_image"
}
packet_store_volume_name_from_presentation() { printf 'safe-volume'; }
running_container_id() {
    case "$1" in
        ai) printf 'ai-id' ;;
        edge) printf 'edge-id' ;;
        *) return 1 ;;
    esac
}
assert_provider_gates_false() { :; }
preflight_initial_packet_store() {
    printf 'store-rechecked\n'
    last_packet_store_state="keyed-v2"
}
validate_sources_and_labels() { printf 'sources-rechecked\n'; }
verify_activation_authority_unchanged
'''
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "store-rechecked\nsources-rechecked\n"


def test_running_preflight_treats_only_a_proven_absent_store_under_real_state_root_as_empty():
    admitted = run_deploy_harness(
        r'''
container_id="presentation"
deploy_tmp="/unused-for-empty-store"
docker() {
    [ "$1" = "exec" ] || return 1
    shift 2
    case "$*" in
        "test ! -e /app/state/build-ghost-packet-access") return 0 ;;
        "test ! -L /app/state/build-ghost-packet-access") return 0 ;;
        "test -d /app/state") return 0 ;;
        "test ! -L /app/state") return 0 ;;
        *) return 1 ;;
    esac
}
preflight_packet_store "$container_id"
printf 'state=%s\n' "$last_packet_store_state"
'''
    )
    assert admitted.returncode == 0, admitted.stderr
    assert admitted.stdout == "state=empty\n"

    rejected = run_deploy_harness(
        r'''
container_id="presentation"
deploy_tmp="/unused-for-empty-store"
docker() {
    [ "$1" = "exec" ] || return 1
    shift 2
    case "$*" in
        "test ! -e /app/state/build-ghost-packet-access") return 0 ;;
        "test ! -L /app/state/build-ghost-packet-access") return 0 ;;
        "test -d /app/state") return 0 ;;
        "test ! -L /app/state") return 1 ;;
        *) return 1 ;;
    esac
}
preflight_packet_store "$container_id"
'''
    )
    assert rejected.returncode != 0
    assert "stage=packet-store-preflight" in rejected.stderr


def run_rollback_branch(schema: str, state: str) -> subprocess.CompletedProcess[str]:
    return run_deploy_harness(
        r'''
activation_started="true"
deploy_succeeded="false"
rollback_started="false"
rollback_ref="presentation:rollback-test"
old_presentation_image="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
rollback_schema_under_test="$1"
quiesced_state_under_test="$2"
image_id() { printf '%s' "$old_presentation_image"; }
image_label() { printf '%s' "$rollback_schema_under_test"; }
quiesce_and_classify_packet_store_for_rollback() {
    printf 'quiesce\n' >&2
    printf '%s' "$quiesced_state_under_test"
}
terminally_verify_legacy_empty_store_for_rollback() { printf 'terminal-empty-proof\n'; }
restore_preserved_presentation_image() { printf 'restore\n'; }
contain_presentation_for_recovery() { printf 'contain:%s\n' "$1"; }
rollback_if_needed
''',
        schema,
        state,
    )


def test_missing_auth_v2_initialization_then_failure_never_recreates_pre_v2_image():
    result = run_rollback_branch("missing", "keyed-v2")

    assert result.returncode != 0
    assert result.stdout == "contain:v2-authority-present\n"
    assert "quiesce" in result.stderr
    assert "restore" not in result.stdout


def test_unknown_post_activation_store_state_contains_without_legacy_rollback():
    result = run_rollback_branch("missing", "unknown")

    assert result.returncode != 0
    assert result.stdout == "contain:packet-store-state-unprovable\n"
    assert "restore" not in result.stdout


def test_empty_pre_migration_store_allows_the_preserved_legacy_rollback():
    result = run_rollback_branch("missing", "empty")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "terminal-empty-proof\nrestore\n"
    assert "quiesce" in result.stderr


def test_exact_v2_rollback_image_requires_a_proven_empty_or_keyed_v2_store():
    empty = run_rollback_branch("v2", "empty")
    keyed = run_rollback_branch("v2", "keyed-v2")

    for result in (empty, keyed):
        assert result.returncode == 0, result.stderr
        assert result.stdout == "restore\n"
        assert "quiesce" in result.stderr


def test_exact_v2_rollback_image_with_unknown_state_is_contained():
    result = run_rollback_branch("v2", "unknown")

    assert result.returncode != 0
    assert result.stdout == "contain:packet-store-state-unprovable\n"
    assert "restore" not in result.stdout


def test_contained_recovery_failure_never_reactivates_the_known_bad_predecessor():
    result = run_deploy_harness(
        r'''
activation_started="true"
deploy_succeeded="false"
rollback_started="false"
recovery_mode="true"
rollback_ref="presentation:rollback-test"
old_presentation_image="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
image_id() { printf '%s' "$old_presentation_image"; }
image_label() { printf 'v2'; }
quiesce_and_classify_packet_store_for_rollback() { printf 'keyed-v2'; }
restore_preserved_presentation_image() { printf 'restore-must-not-run\n'; }
contain_presentation_for_recovery() { printf 'contain:%s\n' "$1"; }
rollback_if_needed
'''
    )

    assert result.returncode != 0
    assert result.stdout == "contain:recovery-candidate-failed\n"
    assert "restore-must-not-run" not in result.stdout


def test_failed_restore_is_immediately_followed_by_verified_containment():
    result = run_deploy_harness(
        r'''
activation_started="true"
deploy_succeeded="false"
rollback_started="false"
rollback_ref="presentation:rollback-test"
old_presentation_image="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
image_id() { printf '%s' "$old_presentation_image"; }
image_label() { printf 'v2'; }
quiesce_and_classify_packet_store_for_rollback() { printf 'keyed-v2'; }
restore_preserved_presentation_image() { printf 'restore-attempt\n'; return 1; }
contain_presentation_for_recovery() { printf 'contain:%s\n' "$1"; }
rollback_if_needed
'''
    )

    assert result.returncode != 0
    assert result.stdout == "restore-attempt\ncontain:rollback-restore-failed\n"


def test_candidate_image_gets_a_unique_verified_immutable_recovery_reference():
    result = run_deploy_harness(
        r'''
deployment_image="presentation:candidate"
rollback_repository="presentation"
candidate_under_test="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
date() { printf '20260822t173000z'; }
openssl() { printf '0123456789abcdef01234567'; }
image_id() { printf '%s' "$candidate_under_test"; }
image_label() { printf 'v2'; }
verify_source_labels() { printf 'verify:%s\n' "$1"; }
docker() {
    if [ "$1" = "image" ] && [ "$2" = "inspect" ]; then
        return 1
    fi
    if [ "$1" = "image" ] && [ "$2" = "tag" ]; then
        printf 'tag:%s:%s\n' "$3" "$4"
        return 0
    fi
    return 1
}
preserve_candidate_recovery_image
printf 'ref:%s\nimage:%s\n' "$candidate_recovery_ref" "$candidate_image"
'''
    )

    expected_ref = (
        "presentation:v2-recovery-20260822t173000z-"
        "bbbbbbbbbbbbbbbb-0123456789abcdef01234567"
    )
    assert result.returncode == 0, result.stderr
    assert f"tag:sha256:{'b' * 64}:{expected_ref}\n" in result.stdout
    assert f"verify:{expected_ref}\n" in result.stdout
    assert f"ref:{expected_ref}\n" in result.stdout
    assert f"image:sha256:{'b' * 64}\n" in result.stdout
    assert "v2-recovery-${timestamp}-${candidate_short:0:16}-${nonce}" in SCRIPT
    assert "candidate-recovery-reference-collision" in SCRIPT
    assert "candidate-recovery-reference-verification-failed" in SCRIPT
    assert "candidate-recovery-schema-label-drift" in SCRIPT
    assert "readonly candidate_image candidate_recovery_ref" in SCRIPT


def test_activation_and_success_are_bound_to_captured_candidate_and_recovery_ref():
    result = run_deploy_harness(
        r'''
candidate_image="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
candidate_recovery_ref="presentation:v2-recovery-test"
deployment_image="presentation:mutable"
candidate_recovery_is_preserved() { printf 'recovery-preserved\n'; }
verify_source_labels() { printf 'labels:%s\n' "$1"; }
docker() {
    [ "$1" = "image" ] && [ "$2" = "tag" ] || return 1
    printf 'tag:%s:%s\n' "$3" "$4"
}
image_id() { printf '%s' "$candidate_image"; }
prepare_candidate_activation_tag
'''
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "recovery-preserved\n"
        "labels:presentation:v2-recovery-test\n"
        "tag:presentation:v2-recovery-test:presentation:mutable\n"
        "recovery-preserved\n"
    )

    postchecks = SCRIPT.split("run_postchecks() {", 1)[1].split(
        "restore_preserved_presentation_image() {", 1
    )[0]
    assert '[ "$current_presentation_image" = "$candidate_image" ]' in postchecks
    assert 'image_id "$deployment_image"' not in postchecks
    body = main_body()
    success_receipt = body.split("presentation_deploy=passed", 1)[1]
    assert '"$candidate_recovery_ref" "$candidate_image"' in success_receipt
    assert 'image_id "$deployment_image"' not in success_receipt


def test_postchecks_reject_mutable_tag_as_candidate_authority():
    result = run_deploy_harness(
        r'''
presentation_service="presentation"
ai_service="ai"
edge_service="edge"
old_presentation_id="old-presentation"
candidate_image="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
candidate_recovery_ref="presentation:v2-recovery-test"
old_packet_store_volume_name="safe-volume"
ai_id_before="ai-id"
edge_id_before="edge-id"
running_container_id() {
    case "$1" in
        presentation) printf 'candidate-presentation' ;;
        ai) printf 'ai-id' ;;
        edge) printf 'edge-id' ;;
        *) return 1 ;;
    esac
}
docker() {
    if [ "$1" = "inspect" ]; then
        printf '%s' "$candidate_image"
        return 0
    fi
    [ "$1" = "exec" ] && return 0
    return 1
}
image_id() { printf 'mutable-tag-must-not-be-authority\n' >&2; return 1; }
candidate_recovery_is_preserved() { :; }
verify_source_labels() { [ "$1" = "$candidate_recovery_ref" ]; }
wait_for_presentation_health() { :; }
packet_store_volume_name_from_presentation() { printf 'safe-volume'; }
assert_provider_gates_false() { :; }
copy_edge_root_certificate() { :; }
verify_private_route_auth() { :; }
verify_public_explain_absent() { :; }
verify_lifecycle_canary() { :; }
preflight_packet_store() { :; }
run_postchecks
'''
    )

    assert result.returncode == 0, result.stderr
    assert "mutable-tag-must-not-be-authority" not in result.stderr


def run_quiesced_store_probe(store: Path) -> subprocess.CompletedProcess[str]:
    return run_deploy_harness(
        r'''
store_under_test="$1"
old_packet_store_volume_name="safe-volume"
stop_running_presentations() { :; }
presentation_is_contained() { :; }
neighbors_and_gates_are_unchanged() { :; }
service_container_id_any_state() { printf 'stopped-presentation-id'; }
packet_store_volume_name_from_presentation() { printf 'safe-volume'; }
classify_packet_store_volume_for_rollback() {
    if [ ! -e "$store_under_test" ] && [ ! -L "$store_under_test" ]; then
        printf 'empty'
        return 0
    fi
    result="$("$packet_preflight" "$store_under_test" 2>/dev/null)" || {
        printf 'unknown'
        return 0
    }
    case "$result" in
        'packet_store_preflight=passed state=empty') printf 'empty' ;;
        'packet_store_preflight=passed state=keyed-v2') printf 'keyed-v2' ;;
        *) printf 'unknown' ;;
    esac
}
quiesce_and_classify_packet_store_for_rollback
''',
        str(store),
    )


def test_quiesced_legacy_rollback_probe_requires_empty_and_authority_absent(tmp_path):
    absent = tmp_path / "absent"
    absent_result = run_quiesced_store_probe(absent)
    assert absent_result.returncode == 0, absent_result.stderr
    assert absent_result.stdout == "empty"

    empty = tmp_path / "empty"
    (empty / "pending").mkdir(parents=True)
    (empty / "consumed").mkdir()
    empty_result = run_quiesced_store_probe(empty)
    assert empty_result.returncode == 0, empty_result.stderr
    assert empty_result.stdout == "empty"

    keyed = tmp_path / "keyed"
    write_json(
        keyed / "state-authority.v2.json",
        "chummer.build_ghost.packet_access_store_authority.v2",
    )
    keyed_result = run_quiesced_store_probe(keyed)
    assert keyed_result.returncode == 0, keyed_result.stderr
    assert keyed_result.stdout == "keyed-v2"

    unknown = tmp_path / "unknown"
    write_json(
        unknown / "state-authority.v2.json",
        "chummer.build_ghost.packet_access_store_authority.v1",
    )
    unknown_result = run_quiesced_store_probe(unknown)
    assert unknown_result.returncode == 0, unknown_result.stderr
    assert unknown_result.stdout == "unknown"


def test_postchecks_reject_state_volume_drift_before_health_or_canary():
    result = run_deploy_harness(
        r'''
presentation_service="presentation"
old_presentation_id="old-presentation"
old_packet_store_volume_name="old-volume"
candidate_image="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
running_container_id() { printf 'candidate-presentation'; }
docker() {
    if [ "$1" = "inspect" ]; then
        printf '%s' "$candidate_image"
        return 0
    fi
    return 1
}
packet_store_volume_name_from_presentation() {
    printf 'different-volume'
}
wait_for_presentation_health() { printf 'health-must-not-run\n'; }
run_postchecks
'''
    )

    assert result.returncode != 0
    assert "stage=postcheck-state-volume-drift" in result.stderr
    assert "health-must-not-run" not in result.stdout


def test_legacy_restore_repeats_terminal_empty_state_and_containment_proof():
    rejected = run_deploy_harness(
        r'''
terminally_verify_legacy_empty_store_for_rollback() {
    printf 'terminal-proof-failed\n'
    return 1
}
restore_preserved_presentation_image() { printf 'restore-must-not-run\n'; }
contain_presentation_for_recovery() { printf 'contain:%s\n' "$1"; }
restore_preserved_presentation_image_or_contain legacy-empty
'''
    )

    assert rejected.returncode != 0
    assert rejected.stdout == (
        "terminal-proof-failed\ncontain:packet-store-state-unprovable\n"
    )
    assert "restore-must-not-run" not in rejected.stdout

    wrapper = SCRIPT.split("restore_preserved_presentation_image_or_contain() {", 1)[1].split(
        "rollback_if_needed() {", 1
    )[0]
    assert wrapper.index("terminally_verify_legacy_empty_store_for_rollback") < wrapper.index(
        "restore_preserved_presentation_image"
    )
    terminal = SCRIPT.split("terminally_verify_legacy_empty_store_for_rollback() {", 1)[1].split(
        "rollback_image_is_preserved() {", 1
    )[0]
    assert terminal.count("presentation_is_contained") >= 2
    assert terminal.count("neighbors_and_gates_are_unchanged") >= 2
    assert '[ "$terminal_state" = "empty" ]' in terminal
    assert '[ "$final_container_id" = "$container_id" ]' in terminal
    assert '[ "$final_volume_name" = "$volume_name" ]' in terminal


def test_contained_store_probe_uses_the_exact_labeled_volume_read_only():
    resolver = SCRIPT.split("packet_store_volume_name_from_presentation() {", 1)[1].split(
        "classify_packet_store_volume_for_rollback() {", 1
    )[0]
    assert 'com.docker.compose.project' in resolver
    assert 'com.docker.compose.volume' in resolver
    assert '[ "$volume_project" = "$project_name" ]' in resolver
    assert '[ "$volume_role" = "build-ghost-packet-access" ]' in resolver

    classifier = SCRIPT.split("classify_packet_store_volume_for_rollback() {", 1)[1].split(
        "classify_contained_packet_store_for_rollback() {", 1
    )[0]
    assert "docker run --rm --pull never --read-only --network none --cap-drop ALL" in classifier
    assert "docker run --rm --pull never --interactive --read-only --network none --cap-drop ALL" in classifier
    assert "--security-opt no-new-privileges" in classifier
    assert 'type=volume,src=$volume_name,dst=/app/state,readonly' in classifier
    assert 'printf "absent"' in classifier
    assert '/app/state/build-ghost-packet-access < "$packet_preflight"' in classifier


def test_fail_closed_containment_stops_only_presentation_and_verifies_neighbors_and_gates():
    result = run_deploy_harness(
        r'''
stop_running_presentations() { printf 'stop-presentation\n'; }
presentation_is_contained() { printf 'contained\n'; }
neighbors_and_gates_are_unchanged() { printf 'neighbors-and-gates\n'; }
rollback_image_is_preserved() { printf 'rollback-preserved\n'; }
candidate_recovery_is_preserved() { printf 'candidate-preserved\n'; }
candidate_recovery_ref="chummer-build-ghost-presentation:v2-recovery-test"
contain_presentation_for_recovery v2-authority-present
'''
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "stop-presentation\n"
        "rollback-preserved\ncandidate-preserved\ncontained\nneighbors-and-gates\n"
        "rollback-preserved\ncandidate-preserved\ncontained\nneighbors-and-gates\n"
    )
    assert (
        "reason=v2-authority-present containment=verified packet_store=preserved "
        "candidate_recovery_ref=chummer-build-ghost-presentation:v2-recovery-test "
        "old_rollback=preserved neighbors=unchanged gates=false"
        in result.stderr
    )

    stop_body = SCRIPT.split("stop_running_presentations() {", 1)[1].split(
        "presentation_is_contained() {", 1
    )[0]
    assert 'com.docker.compose.service=$presentation_service' in stop_body
    assert 'docker stop --time 30 "$container_id"' in stop_body
    assert "$ai_service" not in stop_body
    assert "$edge_service" not in stop_body
    containment = SCRIPT.split("contain_presentation_for_recovery() {", 1)[1].split(
        "run_postchecks() {", 1
    )[0]
    recovery_check = SCRIPT.split("recovery_containment_is_verified() {", 1)[1].split(
        "contain_presentation_for_recovery() {", 1
    )[0]
    assert containment.count("recovery_containment_is_verified") == 2
    assert "presentation_is_contained" in recovery_check
    assert "neighbors_and_gates_are_unchanged" in recovery_check
    assert "rollback_image_is_preserved" in recovery_check
    assert "candidate_recovery_is_preserved" in recovery_check
    assert "packet_store=preserved" in containment
    assert "candidate_recovery_ref=%s" in containment
    assert "old_rollback=preserved" in containment
    assert "compose up" not in containment
    assert "docker image tag" not in containment


def test_containment_receipt_requires_a_second_terminal_neighbor_verification():
    result = run_deploy_harness(
        r'''
neighbor_checks=0
stop_running_presentations() { printf 'stop-presentation\n'; }
presentation_is_contained() { printf 'contained\n'; }
neighbors_and_gates_are_unchanged() {
    neighbor_checks=$((neighbor_checks + 1))
    printf 'neighbors-check-%s\n' "$neighbor_checks"
    [ "$neighbor_checks" -eq 1 ]
}
rollback_image_is_preserved() { printf 'rollback-preserved\n'; }
candidate_recovery_is_preserved() { printf 'candidate-preserved\n'; }
candidate_recovery_ref="presentation:v2-recovery-test"
contain_presentation_for_recovery rollback-restore-failed
'''
    )

    assert result.returncode != 0
    assert "neighbors-check-1" in result.stdout
    assert "neighbors-check-2" in result.stdout
    assert "containment=failed" in result.stderr
    assert "containment=verified" not in result.stderr


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


def test_rollback_rechecks_neighbors_and_provider_gates_after_the_health_wait():
    restore = SCRIPT.split("restore_preserved_presentation_image() {", 1)[1].split(
        "restore_preserved_presentation_image_or_contain() {", 1
    )[0]

    assert restore.index("wait_for_presentation_health") < restore.index(
        "neighbors_and_gates_are_unchanged"
    )
    assert "current_ai_id" not in restore
    assert "current_edge_id" not in restore


@pytest.mark.parametrize(
    ("mode", "expected_returncode", "expected_stage"),
    (
        ("stable", 0, "rollback-restored"),
        ("id-drift", 1, "runtime-verification"),
        ("image-drift", 1, "runtime-verification"),
    ),
)
def test_rollback_re_resolves_same_exact_image_and_container_after_health(
    tmp_path, mode, expected_returncode, expected_stage
):
    resolve_count = tmp_path / "resolve-count"
    inspect_count = tmp_path / "inspect-count"
    resolve_count.write_text("0", encoding="utf-8")
    inspect_count.write_text("0", encoding="utf-8")
    result = run_deploy_harness(
        r'''
mode="$1"
resolve_count_file="$2"
inspect_count_file="$3"
presentation_service="presentation"
deployment_image="presentation:mutable"
rollback_ref="presentation:rollback"
old_presentation_image="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
docker() {
    if [ "$1" = "image" ] && [ "$2" = "tag" ]; then
        return 0
    fi
    if [ "$1" = "inspect" ]; then
        count="$(cat "$inspect_count_file")"
        count=$((count + 1))
        printf '%s' "$count" > "$inspect_count_file"
        if [ "$mode" = "image-drift" ] && [ "$count" -eq 2 ]; then
            printf 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
        else
            printf '%s' "$old_presentation_image"
        fi
        return 0
    fi
    return 1
}
image_id() { printf '%s' "$old_presentation_image"; }
compose() { :; }
resolve_running_container_id() {
    count="$(cat "$resolve_count_file")"
    count=$((count + 1))
    printf '%s' "$count" > "$resolve_count_file"
    if [ "$mode" = "id-drift" ] && [ "$count" -eq 2 ]; then
        printf 'restored-presentation-2'
    else
        printf 'restored-presentation-1'
    fi
}
wait_for_presentation_health() { :; }
neighbors_and_gates_are_unchanged() { :; }
rollback_image_is_preserved() { :; }
candidate_recovery_is_preserved() { :; }
restore_preserved_presentation_image
''',
        mode,
        str(resolve_count),
        str(inspect_count),
    )

    assert result.returncode == expected_returncode, result.stderr
    assert expected_stage in result.stderr
    assert resolve_count.read_text(encoding="utf-8") == "2"
    assert inspect_count.read_text(encoding="utf-8") == "2"

    restore = SCRIPT.split("restore_preserved_presentation_image() {", 1)[1].split(
        "restore_preserved_presentation_image_or_contain() {", 1
    )[0]
    health_index = restore.index("wait_for_presentation_health")
    assert restore.index('resolve_running_container_id "$presentation_service"', health_index) > health_index
    assert restore.index('docker inspect "$post_health_presentation_id"', health_index) > health_index


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
