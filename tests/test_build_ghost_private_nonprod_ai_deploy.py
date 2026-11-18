import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh"
SCRIPT = DEPLOY.read_text(encoding="utf-8")


def main_sequence() -> str:
    return SCRIPT.split("for required in awk bash", 1)[1]


def main_body() -> str:
    return SCRIPT.split("main() {", 1)[1].split(
        'if [ "${BASH_SOURCE[0]}" = "$0" ]; then', 1
    )[0]


def test_deployer_is_valid_bash_without_executing_docker():
    result = subprocess.run(
        ["bash", "-n", str(DEPLOY)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_old_image_is_resolved_and_immutably_preserved_before_build_or_recreate():
    assert 'old_ai_image="$(docker inspect "$old_ai_id" --format \'{{.Image}}\')"' in SCRIPT
    assert '[[ "$old_ai_image" =~ ^sha256:[0-9a-f]{64}$ ]]' in SCRIPT
    assert 'nonce="$(openssl rand -hex 12)"' in SCRIPT
    assert 'rollback-${timestamp}-${old_short:0:16}-${nonce}' in SCRIPT
    assert 'if docker image inspect "$rollback_ref" >/dev/null 2>&1; then' in SCRIPT
    assert 'fail "rollback-reference-collision"' in SCRIPT
    assert 'docker image tag "$old_ai_image" "$rollback_ref"' in SCRIPT
    assert '[ "$preserved_id" = "$old_ai_image" ]' in SCRIPT

    sequence = main_sequence()
    assert sequence.index("preserve_rollback_image") < sequence.index("build_candidate_under_limits")
    assert sequence.index("build_candidate_under_limits") < sequence.index('activation_started="true"')
    assert sequence.index('activation_started="true"') < sequence.index(
        'compose up -d --no-deps --no-build --force-recreate "$ai_service"'
    )


def test_host_lock_is_nonblocking_held_for_main_and_released_on_exit(tmp_path):
    lock_file = tmp_path / "ai-deploy.lock"
    owner_script = (
        'source "$1"; acquire_deploy_lock "$2"; '
        "printf 'locked\\n'; read -r _"
    )
    owner = subprocess.Popen(
        ["bash", "-c", owner_script, "lock-owner", str(DEPLOY), str(lock_file)],
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
                'source "$1"; acquire_deploy_lock "$2"; printf "unexpected\\n"',
                "lock-contender",
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

    released = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; acquire_deploy_lock "$2"; printf "acquired\\n"',
            "lock-after-owner",
            str(DEPLOY),
            str(lock_file),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert released.returncode == 0, released.stderr
    assert released.stdout == "acquired\n"


def test_fixed_host_lock_is_acquired_before_runtime_or_build_work():
    assert (
        'deploy_lock_file="/docker/chummercomplete/.state/locks/'
        'chummer-build-ghost-private-nonprod-ai-deploy.lock"'
    ) in SCRIPT
    assert 'flock --nonblock "$deploy_lock_fd"' in SCRIPT
    assert 'fail "concurrent-deploy-lock-held"' in SCRIPT
    body = main_body()
    assert body.index('acquire_deploy_lock "$deploy_lock_file"') < body.index(
        'presentation_id_before="$(running_container_id "$presentation_service")"'
    )
    assert body.index('acquire_deploy_lock "$deploy_lock_file"') < body.index(
        "build_candidate_under_limits"
    )


def test_activation_and_rollback_are_bounded_to_ai_and_preserve_the_rollback_tag():
    recreate = 'compose up -d --no-deps --no-build --force-recreate "$ai_service"'
    assert SCRIPT.count(recreate) == 2
    assert 'docker image tag "$rollback_ref" "$deployment_image"' in SCRIPT
    assert '"$(image_id "$rollback_ref" 2>/dev/null)" != "$old_ai_image"' in SCRIPT
    assert 'rollback_ref=%s image=%s' in SCRIPT
    assert 'compose up -d --no-deps --no-build --force-recreate "$presentation_service"' not in SCRIPT
    assert 'compose up -d --no-deps --no-build --force-recreate "$edge_service"' not in SCRIPT
    assert "compose down" not in SCRIPT
    assert "docker rm" not in SCRIPT
    assert "docker image rm" not in SCRIPT
    assert "docker rmi" not in SCRIPT
    assert "docker image prune" not in SCRIPT
    assert "docker system prune" not in SCRIPT
    assert "trap on_exit EXIT" in SCRIPT
    assert "if ! (rollback_if_needed); then" in SCRIPT


def test_preactivation_recheck_closes_build_time_identity_drift():
    verification = SCRIPT.split("verify_activation_authority_unchanged()", 1)[1].split(
        "rollback_if_needed()", 1
    )[0]
    assert '[ "$(image_id "$rollback_ref")" = "$old_ai_image" ]' in verification
    assert 'current_ai_id="$(running_container_id "$ai_service")"' in verification
    assert '[ "$current_ai_id" = "$old_ai_id" ]' in verification
    assert 'current_ai_image="$(docker inspect "$current_ai_id" --format \'{{.Image}}\')"' in verification
    assert '[ "$current_ai_image" = "$old_ai_image" ]' in verification
    assert '[ "$(running_container_id "$presentation_service")" = "$presentation_id_before" ]' in verification
    assert '[ "$(running_container_id "$edge_service")" = "$edge_id_before" ]' in verification

    body = main_body()
    assert body.index("build_candidate_under_limits") < body.index(
        "verify_activation_authority_unchanged"
    )
    assert body.index("verify_activation_authority_unchanged") < body.index(
        'activation_started="true"'
    )
    assert (
        "ensure_hard_limits\n    verify_activation_authority_unchanged\n\n"
        '    activation_started="true"'
    ) in body


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
    assert 'sleep "$build_poll_seconds"' in SCRIPT


def test_source_and_rendered_compose_authority_fail_closed():
    for variable in (
        "CHUMMER_RUN_SERVICES_REVISION",
        "CHUMMER_CORE_ENGINE_REVISION",
        "CHUMMER_HUB_REGISTRY_REVISION",
        "CHUMMER_MEDIA_FACTORY_REVISION",
    ):
        assert variable in SCRIPT
    assert 'status --porcelain --untracked-files=all' in SCRIPT
    assert '[ "$CHUMMER_RUN_SERVICES_SOURCE" = "$repo_root" ]' in SCRIPT
    assert "compose config --format json" in SCRIPT
    assert '.services[$service].build.args.CHUMMER_RUN_SERVICES_REVISION == $hub' in SCRIPT
    assert '.services[$service].build.args.CHUMMER_CORE_ENGINE_REVISION == $core' in SCRIPT
    assert '.services[$service].build.args.CHUMMER_HUB_REGISTRY_REVISION == $registry' in SCRIPT
    assert '.services[$service].build.args.CHUMMER_MEDIA_FACTORY_REVISION == $media' in SCRIPT
    assert 'run.chummer.build-ghost.profile' in SCRIPT
    assert 'private-nonprod' in SCRIPT


def test_all_provider_gates_remain_false_before_build_and_after_activation():
    gate_names = (
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED",
    )
    for gate_name in gate_names:
        assert gate_name in SCRIPT
    preserve = SCRIPT.split("preserve_rollback_image()", 1)[1].split("verify_rendered_compose()", 1)[0]
    assert 'assert_provider_gates_false "$old_ai_id"' in preserve
    postchecks = SCRIPT.split("run_postchecks()", 1)[1].split("rollback_if_needed()", 1)[0]
    assert 'assert_provider_gates_false "$current_ai_id"' in postchecks
    assert '.receipt.remoteExecutionEnabled == false' in SCRIPT
    assert '.receipt.remoteAttempted == false' in SCRIPT


def test_postchecks_bind_grounded_request_revision_digest_and_auth():
    assert "chummer.build_ghost_analysis.v1" in SCRIPT
    assert "build-ghost-rook-v1" in SCRIPT
    assert 'workspaceRevision:$revision' in SCRIPT
    assert 'grounded-request-workspace-revision-drift' in SCRIPT
    assert 'grounded-request-packet-digest-drift' in SCRIPT
    assert "chummer.tough_tongue.build_ghost_request.v1" in SCRIPT
    assert 'Authorization: Bearer %s' in SCRIPT
    assert 'http://127.0.0.1:8080/api/v1/ai/build-ghost/explain' in SCRIPT
    assert '[ "$status" = "200" ]' in SCRIPT
    assert '.receipt.requestId == $request_id' in SCRIPT
    assert '.receipt.packetDigest == $packet_digest' in SCRIPT
    assert '.usedDeterministicFallback == true' in SCRIPT
    assert 'remote-execution-disabled-by-default' in SCRIPT
    assert '[ "$missing_status" = "401" ]' in SCRIPT
    assert '[ "$invalid_status" = "401" ]' in SCRIPT


def test_neighbor_ids_and_public_404_are_required_without_widening_ingress():
    assert '[ "$(running_container_id "$presentation_service")" = "$presentation_id_before" ]' in SCRIPT
    assert '[ "$(running_container_id "$edge_service")" = "$edge_id_before" ]' in SCRIPT
    assert '[ "$host_ip" = "127.0.0.1" ]' in SCRIPT
    assert '--cacert "$deploy_tmp/root.crt"' in SCRIPT
    assert 'https://canary.chummer.run:$host_port/api/v1/ai/build-ghost/explain' in SCRIPT
    assert '[ "$status" = "404" ]' in SCRIPT
    assert "public-explain-route-present" in SCRIPT


def test_internal_secrets_are_inherited_without_receipt_or_trace_output():
    assert "set -x" not in SCRIPT
    assert "load_runtime_secrets_without_output" in SCRIPT
    assert 'CHUMMER_AI_INTERNAL_API_TOKEN required' in SCRIPT
    assert 'CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN required' in SCRIPT
    assert 'compose config --format json > "$rendered"' in SCRIPT
    assert 'chmod 0600 "$rendered"' in SCRIPT
    assert 'shred --force --remove=unlink --zero "$path"' in SCRIPT
    assert 'printf \'%s\' "$CHUMMER_AI_INTERNAL_API_TOKEN"' not in SCRIPT
    assert "CHUMMER_AI_INTERNAL_API_TOKEN=" not in SCRIPT


def test_explicit_quarantine_is_fail_closed_and_mutually_exclusive_with_operator_config():
    assert 'quarantine_requested="${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_QUARANTINE:-0}"' in SCRIPT
    assert '*) fail "tough-tongue-quarantine-flag-invalid" ;;' in SCRIPT
    assert 'fail "tough-tongue-quarantine-conflicts-with-operator-config"' in SCRIPT
    assert 'fail "tough-tongue-quarantine-conflicts-with-runtime-evidence"' in SCRIPT
    assert "validate_quarantine_request\n    deploy_tmp=" in SCRIPT


def test_quarantine_rejects_ambiguous_or_conflicting_requests_without_runtime_work():
    cases = (
        (
            {"CHUMMER_BUILD_GHOST_TOUGH_TONGUE_QUARANTINE": "true"},
            "tough-tongue-quarantine-flag-invalid",
        ),
        (
            {
                "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_QUARANTINE": "1",
                "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_OPERATOR_CONFIG_FILE": "/private/config.json",
            },
            "tough-tongue-quarantine-conflicts-with-operator-config",
        ),
        (
            {
                "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_QUARANTINE": "1",
                "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_RUNTIME_EVIDENCE_ROOT": "/private/evidence",
            },
            "tough-tongue-quarantine-conflicts-with-runtime-evidence",
        ),
    )
    for values, expected_stage in cases:
        environment = os.environ.copy()
        for name in (
            "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_QUARANTINE",
            "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_OPERATOR_CONFIG_FILE",
            "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_RUNTIME_EVIDENCE_ROOT",
        ):
            environment.pop(name, None)
        environment.update(values)
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; validate_quarantine_request',
                "quarantine-validation-test",
                str(DEPLOY),
            ],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr.strip() == f"ai_deploy=failed stage={expected_stage}"


def test_quarantine_never_reads_old_provider_credentials_and_retains_internal_auth(tmp_path):
    environment = os.environ.copy()
    environment["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_QUARANTINE"] = "1"
    environment.pop("CHUMMER_BUILD_GHOST_TOUGH_TONGUE_OPERATOR_CONFIG_FILE", None)
    environment.pop("CHUMMER_BUILD_GHOST_TOUGH_TONGUE_RUNTIME_EVIDENCE_ROOT", None)
    result = subprocess.run(
        [
            "bash",
            "-c",
            r'''
source "$1"
load_existing_environment() {
    local variable_name="$2"
    case "$variable_name" in
        CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN|CHUMMER_AI_INTERNAL_API_TOKEN)
            printf -v "$variable_name" '%s' 'test-internal-auth-only'
            export "${variable_name?}"
            ;;
        CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY)
            printf -v "$variable_name" '%s' 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='
            export "${variable_name?}"
            ;;
        *) return 91 ;;
    esac
}
load_existing_environment_or_empty() { return 92; }
old_ai_id=test-container
load_runtime_secrets_without_output
[ "$CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN" = test-internal-auth-only ]
[ "$CHUMMER_AI_INTERNAL_API_TOKEN" = test-internal-auth-only ]
[ "$CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY" = \
  AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= ]
for variable_name in \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_PROVIDER \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_NAME \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_ASSET_PATH \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_DIGEST \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_RECEIPT_JSON \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_PROVIDER \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_ID \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ALLOW_LEGACY_CASCADE \
    EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST; do
    [ -z "${!variable_name}" ]
done
[ "$CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE" = \
  "$script_root/tough-tongue-read-only-binding-contract.unconfigured.json" ]
''',
            "quarantine-function-test",
            str(DEPLOY),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_quarantine_render_postcheck_and_rollback_require_empty_provider_runtime():
    render = SCRIPT.split("verify_rendered_compose()", 1)[1].split(
        "build_candidate_under_limits()", 1
    )[0]
    for variable_name in (
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_PROVIDER",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_NAME",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_ASSET_PATH",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_DIGEST",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_RECEIPT_JSON",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_PROVIDER",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_ID",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ALLOW_LEGACY_CASCADE",
        "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST",
    ):
        assert f".services[$service].environment.{variable_name} == \"\"" in render
        assert variable_name in SCRIPT.split("assert_provider_runtime_quarantined()", 1)[1]
    assert '.secrets["build-ghost-tough-tongue-read-only-binding-contract"].file == $sentinel' in render
    assert 'fail "compose-tough-tongue-quarantine-drift"' in render
    postchecks = SCRIPT.split("run_postchecks()", 1)[1].split(
        "verify_activation_authority_unchanged()", 1
    )[0]
    rollback = SCRIPT.split("rollback_if_needed()", 1)[1].split("on_exit()", 1)[0]
    assert 'assert_provider_runtime_quarantined "$current_ai_id"' in postchecks
    assert 'assert_provider_gates_false "$restored_ai_id"' in rollback
    assert 'assert_provider_runtime_quarantined "$restored_ai_id"' in rollback
    assert 'docker container inspect "$old_ai_id"' in SCRIPT
    assert 'fail "postcheck-quarantine-superseded-container-retained"' in SCRIPT
    assert 'credentials_present=false provider_side_revocation=false' in SCRIPT
