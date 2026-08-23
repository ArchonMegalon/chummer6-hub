#!/usr/bin/env bash
set -euo pipefail

# Bounded private-lane deployer. This script changes only Presentation, keeps
# every provider gate false, and never deletes its immutable rollback image.
umask 077

script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_root/../.." && pwd -P)"
compose_file="$repo_root/docker-compose.build-ghost-private-nonprod.yml"
runtime_config_materializer="$repo_root/scripts/materialize_build_ghost_tough_tongue_runtime_config.py"
operator_runtime_config_file="${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_OPERATOR_CONFIG_FILE:-}"
operator_runtime_evidence_root="${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_RUNTIME_EVIDENCE_ROOT:-}"
packet_preflight="$script_root/preflight-packet-access-state.sh"
canary_script="$script_root/run-local-canary.sh"
project_name="chummer-build-ghost-private-nonprod"
presentation_service="chummer-build-ghost-presentation"
ai_service="chummer-build-ghost-ai"
edge_service="build-ghost-private-edge"
deployment_image="chummer-build-ghost-presentation:private-nonprod"
rollback_repository="chummer-build-ghost-presentation"
presentation_release_revision="1c492202ac708f302b59f47c2bb1e4c67e352328"
packet_store_schema_label="run.chummer.build-ghost.packet-store-schema"
packet_store_schema_version="v2"
# Deliberately shared with the AI helper so the two private-lane activations
# cannot overlap even though the historical filename names the AI lane.
deploy_lock_file="/docker/chummercomplete/.state/locks/chummer-build-ghost-private-nonprod-ai-deploy.lock"
max_io_full_avg10="${CHUMMER_BUILD_GHOST_DEPLOY_MAX_IO_FULL_AVG10:-10}"
minimum_free_gib="${CHUMMER_BUILD_GHOST_DEPLOY_MINIMUM_FREE_GIB:-20}"
build_poll_seconds="${CHUMMER_BUILD_GHOST_DEPLOY_POLL_SECONDS:-10}"
recovery_mode="${CHUMMER_BUILD_GHOST_PRESENTATION_RECOVERY_MODE:-false}"

deploy_tmp=""
build_pid=""
candidate_built="false"
activation_started="false"
deploy_succeeded="false"
rollback_started="false"
old_presentation_id=""
old_presentation_image=""
old_presentation_store_schema=""
old_packet_store_volume_name=""
rollback_ref=""
candidate_recovery_ref=""
candidate_image=""
ai_id_before=""
edge_id_before=""
deploy_lock_fd=""
last_packet_store_state=""
initial_packet_store_state=""
runtime_evidence_dir=""
runtime_environment_file=""
runtime_contract_file=""
runtime_receipt_file=""
runtime_evidence_device=""
runtime_evidence_inode=""
runtime_environment_digest=""
compose_environment_args=()
tough_tongue_runtime_variables=(
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE
    EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST
)

fail() {
    printf 'presentation_deploy=failed stage=%s\n' "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "preflight-missing-$1"
}

acquire_deploy_lock() {
    local requested_lock_file="${1:-$deploy_lock_file}"
    local requested_lock_root
    requested_lock_root="$(dirname -- "$requested_lock_file")"
    mkdir -p -- "$requested_lock_root"
    [ ! -L "$requested_lock_file" ] || fail "deploy-lock-must-not-be-symlink"
    exec {deploy_lock_fd}>> "$requested_lock_file"
    chmod 0600 "$requested_lock_file"
    flock --nonblock "$deploy_lock_fd" || fail "concurrent-deploy-lock-held"
}

compose() {
    docker compose "${compose_environment_args[@]}" \
        --project-name "$project_name" \
        --project-directory "$repo_root" \
        --file "$compose_file" \
        "$@"
}

resolve_running_container_id() {
    local service_name="$1"
    local resolved
    resolved="$(docker ps --no-trunc \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "label=com.docker.compose.service=$service_name" \
        --filter status=running \
        --format '{{.ID}}')" || return 1
    [ "$(printf '%s\n' "$resolved" | sed '/^$/d' | wc -l)" -eq 1 ] || return 1
    printf '%s' "$resolved"
}

running_container_id() {
    local service_name="$1"
    local resolved
    resolved="$(resolve_running_container_id "$service_name")" \
        || fail "runtime-$service_name-not-exactly-one"
    printf '%s' "$resolved"
}

ensure_hard_limits() {
    local io_full_avg10 free_kib minimum_free_kib
    io_full_avg10="$(awk '/^full / { for (field = 1; field <= NF; field++) if ($field ~ /^avg10=/) { split($field, pair, "="); print pair[2]; exit } }' /proc/pressure/io)"
    [ -n "$io_full_avg10" ] || fail "host-io-pressure-unreadable"
    awk -v observed="$io_full_avg10" -v maximum="$max_io_full_avg10" \
        'BEGIN { exit !(observed <= maximum) }' || fail "host-io-pressure-cutoff"

    free_kib="$(df -Pk /docker | awk 'NR == 2 { print $4 }')"
    minimum_free_kib="$((minimum_free_gib * 1024 * 1024))"
    [ -n "$free_kib" ] || fail "host-free-space-unreadable"
    [ "$free_kib" -ge "$minimum_free_kib" ] || fail "host-free-space-cutoff"
}

validate_control_values() {
    [[ "$max_io_full_avg10" =~ ^([0-9]+)(\.[0-9]+)?$ ]] || fail "max-io-cutoff-invalid"
    awk -v value="$max_io_full_avg10" 'BEGIN { exit !(value > 0 && value <= 10) }' \
        || fail "max-io-cutoff-must-not-exceed-ten"
    [[ "$minimum_free_gib" =~ ^[0-9]+$ ]] || fail "minimum-free-space-invalid"
    [ "$minimum_free_gib" -ge 20 ] || fail "minimum-free-space-must-be-at-least-twenty-gib"
    [[ "$build_poll_seconds" =~ ^[0-9]+$ ]] || fail "build-poll-invalid"
    if [ "$build_poll_seconds" -lt 1 ] || [ "$build_poll_seconds" -gt 15 ]; then
        fail "build-poll-must-be-one-to-fifteen-seconds"
    fi
    case "$recovery_mode" in
        true|false) ;;
        *) fail "presentation-recovery-mode-invalid" ;;
    esac
}

validate_source() {
    local variable_name="$1"
    local revision_variable_name="$2"
    local source_path expected_revision actual_revision dirty
    source_path="${!variable_name:-}"
    expected_revision="${!revision_variable_name:-}"
    [ -n "$source_path" ] || fail "source-$variable_name-missing"
    [[ "$source_path" == /* ]] || fail "source-$variable_name-not-absolute"
    source_path="$(realpath -e -- "$source_path")"
    git -C "$source_path" rev-parse --git-dir >/dev/null 2>&1 \
        || fail "source-$variable_name-not-git"
    actual_revision="$(git -C "$source_path" rev-parse --verify HEAD)"
    [[ "$actual_revision" =~ ^[0-9a-f]{40}$ ]] || fail "source-$variable_name-head-invalid"
    [[ "$expected_revision" =~ ^[0-9a-f]{40}$ ]] || fail "revision-$revision_variable_name-invalid"
    [ "$actual_revision" = "$expected_revision" ] || fail "source-$variable_name-revision-drift"
    dirty="$(git -C "$source_path" status --porcelain --untracked-files=all)"
    [ -z "$dirty" ] || fail "source-$variable_name-dirty"
    printf -v "$variable_name" '%s' "$source_path"
    export "${variable_name?}"
}

validate_sources_and_labels() {
    validate_source CHUMMER_RUN_SERVICES_SOURCE CHUMMER_RUN_SERVICES_REVISION
    [ "$CHUMMER_RUN_SERVICES_SOURCE" = "$repo_root" ] || fail "hub-source-does-not-own-helper"
    validate_source CHUMMER_PRESENTATION_SOURCE CHUMMER_PRESENTATION_REVISION
    [ "$CHUMMER_PRESENTATION_REVISION" = "$presentation_release_revision" ] \
        || fail "presentation-revision-not-release-pin"
    validate_source CHUMMER_CORE_ENGINE_SOURCE CHUMMER_CORE_ENGINE_REVISION
    validate_source CHUMMER_HUB_REGISTRY_SOURCE CHUMMER_HUB_REGISTRY_REVISION
    validate_source CHUMMER_UI_KIT_SOURCE CHUMMER_UI_KIT_REVISION
    validate_source CHUMMER_MEDIA_FACTORY_SOURCE CHUMMER_MEDIA_FACTORY_REVISION
}

read_existing_environment() {
    local container_id="$1"
    local variable_name="$2"
    local required="$3"
    local destination="$4"
    local environment line matches value
    environment="$(docker inspect "$container_id" --format '{{range .Config.Env}}{{println .}}{{end}}')"
    line="$(printf '%s\n' "$environment" | awk -v prefix="$variable_name=" 'index($0, prefix) == 1 { print }')"
    matches="$(printf '%s\n' "$environment" | awk -v prefix="$variable_name=" 'index($0, prefix) == 1 { count++ } END { print count + 0 }')"
    [ "$matches" -eq 1 ] || fail "runtime-env-$variable_name-not-exactly-one"
    value="${line#*=}"
    if [ "$required" = "required" ] && [ -z "$value" ]; then
        fail "runtime-env-$variable_name-empty"
    fi
    printf -v "$destination" '%s' "$value"
}

read_existing_environment_or_empty() {
    local container_id="$1"
    local variable_name="$2"
    local destination="$3"
    local environment line matches value=""
    environment="$(docker inspect "$container_id" --format '{{range .Config.Env}}{{println .}}{{end}}')"
    line="$(printf '%s\n' "$environment" | awk -v prefix="$variable_name=" 'index($0, prefix) == 1 { print }')"
    matches="$(printf '%s\n' "$environment" | awk -v prefix="$variable_name=" 'index($0, prefix) == 1 { count++ } END { print count + 0 }')"
    [ "$matches" -le 1 ] || fail "runtime-env-$variable_name-ambiguous"
    if [ "$matches" -eq 1 ]; then
        value="${line#*=}"
    fi
    printf -v "$destination" '%s' "$value"
}

prepare_operator_runtime_config() {
    local materializer_log owner resolved_root variable_name
    if [ -z "$operator_runtime_config_file" ]; then
        [ -z "$operator_runtime_evidence_root" ] \
            || fail "operator-tough-tongue-evidence-without-config"
        return 0
    fi
    [ -x "$runtime_config_materializer" ] \
        || fail "operator-tough-tongue-materializer-unavailable"
    [ -n "$operator_runtime_evidence_root" ] \
        || fail "operator-tough-tongue-evidence-root-required"
    case "$operator_runtime_evidence_root" in
        /*) ;;
        *) fail "operator-tough-tongue-evidence-root-invalid" ;;
    esac
    resolved_root="$(realpath -e -- "$operator_runtime_evidence_root")" \
        || fail "operator-tough-tongue-evidence-root-unavailable"
    [ "$resolved_root" = "$operator_runtime_evidence_root" ] \
        || fail "operator-tough-tongue-evidence-root-authority-invalid"
    owner="$(id -u)"
    if [ ! -d "$operator_runtime_evidence_root" ] \
        || [ -L "$operator_runtime_evidence_root" ] \
        || [ "$(stat -c '%a:%u' -- "$operator_runtime_evidence_root")" != "700:$owner" ]; then
        fail "operator-tough-tongue-evidence-root-authority-invalid"
    fi
    runtime_evidence_dir="$(mktemp -d -- \
        "$operator_runtime_evidence_root/runtime.XXXXXXXXXXXX")" \
        || fail "operator-tough-tongue-evidence-directory-unavailable"
    chmod 0700 "$runtime_evidence_dir"
    runtime_environment_file="$runtime_evidence_dir/runtime.env"
    runtime_contract_file="$runtime_evidence_dir/read-only-contract.json"
    runtime_receipt_file="$runtime_evidence_dir/runtime-receipt.json"
    runtime_evidence_device="$(stat -c '%d' -- "$runtime_evidence_dir")"
    runtime_evidence_inode="$(stat -c '%i' -- "$runtime_evidence_dir")"
    materializer_log="$deploy_tmp/tough-tongue-runtime-materializer.log"
    if ! python3 "$runtime_config_materializer" \
        --config "$operator_runtime_config_file" \
        --output-env "$runtime_environment_file" \
        --output-contract "$runtime_contract_file" \
        --receipt "$runtime_receipt_file" >"$materializer_log" 2>&1; then
        chmod 0600 "$materializer_log" 2>/dev/null || true
        fail "operator-tough-tongue-config-invalid"
    fi
    chmod 0600 "$materializer_log"
    verify_materialized_runtime_pair \
        "$runtime_environment_file" "$runtime_contract_file" "$runtime_receipt_file"
    runtime_environment_digest="$(jq -er '.environmentFileDigest' "$runtime_receipt_file")"
    jq -e \
        '.schema == "chummer.build_ghost.tough_tongue.runtime_config_receipt.v1"
         and .status == "ready-for-read-only-probe"
         and .providerReadbackVerified == false
         and .providerActivationAuthorized == false
         and .providerMutationPerformed == false
         and .readyForResourceBinding == false
         and .providerPlanLabelReadbackVerified == false
         and (
           .bindingCandidatesConfigured == true
           or (
             .bindingCandidatesConfigured == false
             and .candidateRefCount == 0
             and .candidateRefDigests == {}
             and .readyForAccountSelection == true
             and .accountSelectionPolicySource == "user_authority"
             and .premiumBasis == "operator_policy_available_minutes_gt_threshold"
             and .premiumThresholdMinutes == 1100
             and .premiumValidityCalendarMonths == 11
             and .premiumGrantCount > 0
           )
         )
         and .rawCredentialsInReceipt == false
         and .rawCandidateRefsInReceipt == false' \
        "$runtime_receipt_file" >/dev/null \
        || fail "operator-tough-tongue-receipt-invalid"
    compose_environment_args=(--env-file "$runtime_environment_file")
    for variable_name in "${tough_tongue_runtime_variables[@]}"; do
        unset "$variable_name"
    done
}

securely_remove_runtime_environment() {
    local cleanup_digest_args=()
    [ -n "$runtime_environment_file" ] || return 0
    if [ -n "$runtime_environment_digest" ]; then
        cleanup_digest_args=(--expected-environment-digest "$runtime_environment_digest")
    fi
    if ! python3 "$runtime_config_materializer" \
        --destroy-environment "$runtime_environment_file" \
        --expected-parent-device "$runtime_evidence_device" \
        --expected-parent-inode "$runtime_evidence_inode" \
        "${cleanup_digest_args[@]}" >/dev/null 2>&1; then
        printf 'presentation_deploy=failed stage=operator-tough-tongue-environment-cleanup-failed\n' >&2
        return 1
    fi
    compose_environment_args=()
}

verify_materialized_runtime_pair() {
    local environment_file="$1"
    local contract_file="$2"
    local receipt_file="$3"
    local owner identity_before identity_after environment_digest contract_digest
    local receipt_evidence expected_evidence receipt_without_evidence
    local output_device output_inode actual_output_identity
    owner="$(id -u)"
    if [ ! -f "$environment_file" ] || [ -L "$environment_file" ] \
        || [ "$(stat -c '%a:%u:%h' -- "$environment_file")" != "600:$owner:1" ]; then
        fail "operator-tough-tongue-environment-authority-invalid"
    fi
    if [ ! -f "$contract_file" ] || [ -L "$contract_file" ] \
        || [ "$(stat -c '%a:%u:%h' -- "$contract_file")" != "400:$owner:1" ]; then
        fail "operator-tough-tongue-contract-authority-invalid"
    fi
    if [ ! -f "$receipt_file" ] || [ -L "$receipt_file" ] \
        || [ "$(stat -c '%a:%u:%h' -- "$receipt_file")" != "600:$owner:1" ]; then
        fail "operator-tough-tongue-receipt-authority-invalid"
    fi
    identity_before="$(stat -c '%d:%i:%s:%y:%z:%f:%u:%h' -- \
        "$environment_file" "$contract_file" "$receipt_file")"
    environment_digest="sha256:$(sha256sum -- "$environment_file" | awk '{print $1}')"
    contract_digest="sha256:$(sha256sum -- "$contract_file" | awk '{print $1}')"
    receipt_evidence="$(jq -er '.evidenceDigest' "$receipt_file")"
    receipt_without_evidence="$(jq -cS 'del(.evidenceDigest)' "$receipt_file")"
    expected_evidence="sha256:$(printf '%s' "$receipt_without_evidence" | sha256sum | awk '{print $1}')"
    output_device="$(jq -er '.outputDirectoryDevice | numbers' "$receipt_file")"
    output_inode="$(jq -er '.outputDirectoryInode | numbers' "$receipt_file")"
    if ! [[ "$output_device" =~ ^[0-9]+$ ]] \
        || ! [[ "$output_inode" =~ ^[1-9][0-9]*$ ]]; then
        fail "operator-tough-tongue-output-directory-binding-invalid"
    fi
    actual_output_identity="$(stat -c '%d:%i' -- "$(dirname -- "$environment_file")")"
    [ "$actual_output_identity" = "$output_device:$output_inode" ] \
        || fail "operator-tough-tongue-output-directory-changed"
    if [ -n "$runtime_evidence_device" ] || [ -n "$runtime_evidence_inode" ]; then
        [ "$actual_output_identity" = "$runtime_evidence_device:$runtime_evidence_inode" ] \
            || fail "operator-tough-tongue-output-directory-changed"
    fi
    jq -e \
        --arg environment_digest "$environment_digest" \
        --arg contract_digest "$contract_digest" \
        '.environmentFileDigest == $environment_digest
         and .readOnlyContractFileDigest == $contract_digest
         and .contractSnapshotMode == "0400"
         and .publicationOrder == ["contract-snapshot", "receipt", "environment"]' \
        "$receipt_file" >/dev/null \
        || fail "operator-tough-tongue-pair-digest-invalid"
    [ "$receipt_evidence" = "$expected_evidence" ] \
        || fail "operator-tough-tongue-receipt-digest-invalid"
    identity_after="$(stat -c '%d:%i:%s:%y:%z:%f:%u:%h' -- \
        "$environment_file" "$contract_file" "$receipt_file")"
    [ "$identity_before" = "$identity_after" ] \
        || fail "operator-tough-tongue-pair-changed"
}

load_runtime_environment_without_output() {
    local ai_service_token
    read_existing_environment "$old_presentation_id" \
        CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN required \
        CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN
    export CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN
    read_existing_environment "$ai_id_before" \
        CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN required ai_service_token
    [ "$ai_service_token" = "$CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN" ] \
        || fail "runtime-service-token-neighbor-drift"
    unset ai_service_token

    read_existing_environment "$ai_id_before" CHUMMER_AI_INTERNAL_API_TOKEN required CHUMMER_AI_INTERNAL_API_TOKEN
    export CHUMMER_AI_INTERNAL_API_TOKEN
    if [ -n "$operator_runtime_config_file" ]; then
        return 0
    fi
    for variable_name in \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID; do
        read_existing_environment "$ai_id_before" "$variable_name" optional "$variable_name"
        export "${variable_name?}"
    done
    for variable_name in \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID \
        EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST; do
        read_existing_environment_or_empty "$ai_id_before" "$variable_name" "$variable_name"
        export "${variable_name?}"
    done
    [ -z "$EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST" ] \
        || fail "configured-readback-contract-requires-operator-config"
}

securely_remove_temp() {
    local path
    [ -n "$deploy_tmp" ] && [ -d "$deploy_tmp" ] || return 0
    while IFS= read -r -d '' path; do
        chmod u+w "$path" 2>/dev/null || true
        shred --force --remove=unlink --zero "$path" 2>/dev/null || {
            truncate --size 0 "$path" 2>/dev/null || true
            unlink "$path" 2>/dev/null || true
        }
    done < <(find "$deploy_tmp" -mindepth 1 -maxdepth 1 -type f -print0)
    rmdir "$deploy_tmp" 2>/dev/null || true
}

terminate_build() {
    [ -n "$build_pid" ] || return 0
    kill -0 "$build_pid" 2>/dev/null || {
        build_pid=""
        return 0
    }
    kill -TERM -- "-$build_pid" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        kill -0 "$build_pid" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "$build_pid" 2>/dev/null; then
        kill -KILL -- "-$build_pid" 2>/dev/null || true
    fi
    wait "$build_pid" 2>/dev/null || true
    build_pid=""
}

image_id() {
    docker image inspect "$1" --format '{{.Id}}'
}

image_label() {
    docker image inspect "$1" --format "{{ index .Config.Labels \"$2\" }}"
}

verify_source_labels() {
    local image="$1"
    [ "$(image_label "$image" org.opencontainers.image.revision)" = "$CHUMMER_PRESENTATION_REVISION" ] \
        || fail "image-presentation-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.hub-revision)" = "$CHUMMER_RUN_SERVICES_REVISION" ] \
        || fail "image-hub-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.core-revision)" = "$CHUMMER_CORE_ENGINE_REVISION" ] \
        || fail "image-core-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.hub-registry-revision)" = "$CHUMMER_HUB_REGISTRY_REVISION" ] \
        || fail "image-registry-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.ui-kit-revision)" = "$CHUMMER_UI_KIT_REVISION" ] \
        || fail "image-ui-kit-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.media-factory-revision)" = "$CHUMMER_MEDIA_FACTORY_REVISION" ] \
        || fail "image-media-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.profile)" = "private-nonprod" ] \
        || fail "image-profile-label-drift"
    [ "$(image_label "$image" "$packet_store_schema_label")" = "$packet_store_schema_version" ] \
        || fail "image-packet-store-schema-label-drift"
}

provider_gates_are_false() {
    local container_id="$1"
    local environment required_false
    environment="$(docker inspect "$container_id" --format '{{range .Config.Env}}{{println .}}{{end}}')" \
        || return 1
    for required_false in \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED; do
        [ "$(printf '%s\n' "$environment" | awk -v expected="$required_false=false" '$0 == expected { count++ } END { print count + 0 }')" -eq 1 ] \
            || return 1
    done
}

assert_provider_gates_false() {
    local container_id="$1"
    provider_gates_are_false "$container_id" || fail "provider-gates-not-exact-false"
}

snapshot_running_presentation() {
    old_presentation_id="$(running_container_id "$presentation_service")"
    old_presentation_image="$(docker inspect "$old_presentation_id" --format '{{.Image}}')"
    [[ "$old_presentation_image" =~ ^sha256:[0-9a-f]{64}$ ]] \
        || fail "old-presentation-image-id-invalid"
    [ "$(image_id "$old_presentation_image")" = "$old_presentation_image" ] \
        || fail "old-presentation-image-unresolvable"
    old_presentation_store_schema="$(image_label "$old_presentation_image" "$packet_store_schema_label")"
    old_packet_store_volume_name="$(packet_store_volume_name_from_presentation "$old_presentation_id")" \
        || fail "old-presentation-state-volume-invalid"
}

snapshot_contained_presentation() {
    local status
    presentation_is_contained || fail "recovery-presentation-not-contained"
    old_presentation_id="$(service_container_id_any_state "$presentation_service")" \
        || fail "recovery-presentation-not-exactly-one"
    status="$(docker inspect "$old_presentation_id" --format '{{.State.Status}}')"
    [ "$status" = "exited" ] || fail "recovery-presentation-not-exited"
    old_presentation_image="$(docker inspect "$old_presentation_id" --format '{{.Image}}')"
    [[ "$old_presentation_image" =~ ^sha256:[0-9a-f]{64}$ ]] \
        || fail "recovery-presentation-image-id-invalid"
    [ "$(image_id "$old_presentation_image")" = "$old_presentation_image" ] \
        || fail "recovery-presentation-image-unresolvable"
    old_presentation_store_schema="$(image_label "$old_presentation_image" "$packet_store_schema_label")"
    [ "$old_presentation_store_schema" = "$packet_store_schema_version" ] \
        || fail "recovery-presentation-image-not-v2"
    old_packet_store_volume_name="$(packet_store_volume_name_from_presentation "$old_presentation_id")" \
        || fail "recovery-presentation-state-volume-invalid"
}

snapshot_presentation_authority() {
    if [ "$recovery_mode" = "true" ]; then
        snapshot_contained_presentation
    else
        snapshot_running_presentation
    fi
}

preserve_rollback_image() {
    local timestamp nonce old_short preserved_id preserved_schema

    timestamp="$(date -u +%Y%m%dt%H%M%Sz)"
    nonce="$(openssl rand -hex 12)"
    old_short="${old_presentation_image#sha256:}"
    rollback_ref="$rollback_repository:rollback-${timestamp}-${old_short:0:16}-${nonce}"
    if docker image inspect "$rollback_ref" >/dev/null 2>&1; then
        fail "rollback-reference-collision"
    fi
    docker image tag "$old_presentation_image" "$rollback_ref"
    preserved_id="$(image_id "$rollback_ref")"
    [ "$preserved_id" = "$old_presentation_image" ] \
        || fail "rollback-reference-verification-failed"
    preserved_schema="$(image_label "$rollback_ref" "$packet_store_schema_label")"
    [ "$preserved_schema" = "$old_presentation_store_schema" ] \
        || fail "rollback-reference-schema-label-drift"
    printf 'presentation_deploy=prepared rollback_ref=%s old_image=%s\n' \
        "$rollback_ref" "$old_presentation_image"
}

preserve_candidate_recovery_image() {
    local timestamp nonce candidate_short preserved_id preserved_schema
    candidate_image="$(image_id "$deployment_image")"
    [[ "$candidate_image" =~ ^sha256:[0-9a-f]{64}$ ]] \
        || fail "candidate-image-id-invalid"
    verify_source_labels "$candidate_image"

    timestamp="$(date -u +%Y%m%dt%H%M%Sz)"
    nonce="$(openssl rand -hex 12)"
    candidate_short="${candidate_image#sha256:}"
    candidate_recovery_ref="$rollback_repository:v2-recovery-${timestamp}-${candidate_short:0:16}-${nonce}"
    if docker image inspect "$candidate_recovery_ref" >/dev/null 2>&1; then
        fail "candidate-recovery-reference-collision"
    fi
    docker image tag "$candidate_image" "$candidate_recovery_ref"
    preserved_id="$(image_id "$candidate_recovery_ref")"
    [ "$preserved_id" = "$candidate_image" ] \
        || fail "candidate-recovery-reference-verification-failed"
    preserved_schema="$(image_label "$candidate_recovery_ref" "$packet_store_schema_label")"
    [ "$preserved_schema" = "$packet_store_schema_version" ] \
        || fail "candidate-recovery-schema-label-drift"
    verify_source_labels "$candidate_recovery_ref"
    readonly candidate_image candidate_recovery_ref
    printf 'presentation_deploy=candidate-recovery-prepared candidate_recovery_ref=%s candidate_image=%s\n' \
        "$candidate_recovery_ref" "$candidate_image"
}

preflight_packet_store() {
    local container_id="$1"
    local result directory expected_schema state_path
    local path_manifest="$deploy_tmp/packet-store-paths"
    if docker exec "$container_id" test ! -e /app/state/build-ghost-packet-access \
        && docker exec "$container_id" test ! -L /app/state/build-ghost-packet-access \
        && docker exec "$container_id" test -d /app/state \
        && docker exec "$container_id" test ! -L /app/state; then
        result='packet_store_preflight=passed state=empty'
    else
        result="$(docker exec -i "$container_id" sh -s -- \
            /app/state/build-ghost-packet-access < "$packet_preflight")" \
            || fail "packet-store-preflight"
    fi
    case "$result" in
        'packet_store_preflight=passed state=empty'|'packet_store_preflight=passed state=keyed-v2') ;;
        *) fail "packet-store-preflight-ambiguous" ;;
    esac

    last_packet_store_state="${result##*state=}"

    if [ "$result" = 'packet_store_preflight=passed state=empty' ]; then
        return 0
    fi

    validate_packet_state_json "$container_id" \
        /app/state/build-ghost-packet-access/state-authority.v2.json \
        chummer.build_ghost.packet_access_store_authority.v2
    while read -r directory expected_schema; do
        : > "$path_manifest"
        docker exec "$container_id" find \
            "/app/state/build-ghost-packet-access/$directory" \
            -mindepth 1 -maxdepth 1 -type f -name '*.json' -print0 \
            > "$path_manifest" || fail "packet-store-json-list-unreadable"
        while IFS= read -r -d '' state_path; do
            validate_packet_state_json "$container_id" "$state_path" "$expected_schema"
        done < "$path_manifest"
    done <<'EOF'
pending chummer.build_ghost.packet_access_pending.v2
claims chummer.build_ghost.packet_access_pending.v2
audit chummer.build_ghost.packet_access_audit.v2
revocations chummer.build_ghost.workspace_revocation.v2
EOF
}

validate_packet_state_json() {
    local container_id="$1"
    local state_path="$2"
    local expected_schema="$3"
    if ! docker exec "$container_id" cat -- "$state_path" \
        | jq -e --arg expected "$expected_schema" \
            'type == "object" and (.schema | type == "string") and .schema == $expected' \
            >/dev/null; then
        fail "packet-store-json-or-schema-invalid"
    fi
}

verify_rendered_compose() {
    local rendered="$deploy_tmp/compose.rendered.json"
    compose config --format json > "$rendered"
    chmod 0600 "$rendered"
    jq -e \
        --arg service "$presentation_service" \
        --arg ai "$ai_service" \
        --arg repo "$repo_root" \
        --arg hub "$CHUMMER_RUN_SERVICES_REVISION" \
        --arg presentation "$CHUMMER_PRESENTATION_REVISION" \
        --arg core "$CHUMMER_CORE_ENGINE_REVISION" \
        --arg registry "$CHUMMER_HUB_REGISTRY_REVISION" \
        --arg ui "$CHUMMER_UI_KIT_REVISION" \
        --arg media "$CHUMMER_MEDIA_FACTORY_REVISION" \
        '.services[$service].image == "chummer-build-ghost-presentation:private-nonprod"
         and .services[$service].build.context == $repo
         and .services[$service].build.dockerfile == "ops/build-ghost-private-nonprod/Dockerfile.presentation-private-nonprod"
         and .services[$service].build.args.CHUMMER_RUN_SERVICES_REVISION == $hub
         and .services[$service].build.args.CHUMMER_PRESENTATION_REVISION == $presentation
         and .services[$service].build.args.CHUMMER_CORE_ENGINE_REVISION == $core
         and .services[$service].build.args.CHUMMER_HUB_REGISTRY_REVISION == $registry
         and .services[$service].build.args.CHUMMER_UI_KIT_REVISION == $ui
         and .services[$service].build.args.CHUMMER_MEDIA_FACTORY_REVISION == $media
         and .services[$service].environment.CHUMMER_BUILD_GHOST_PACKET_ACCESS_STORE_ROOT == "/app/state/build-ghost-packet-access"
         and ((.services[$service].ports // []) | length == 0)
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED == "false"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED == "false"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED == "false"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED == "false"
         and .services[$ai].environment.EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_PATH == "/run/secrets/tough-tongue-read-only-binding-contract.json"
         and any(.services[$ai].secrets[]?;
             .source == "build-ghost-tough-tongue-read-only-binding-contract"
             and .target == "tough-tongue-read-only-binding-contract.json")' \
        "$rendered" >/dev/null || fail "compose-render-drift"
    if [ -n "$operator_runtime_config_file" ]; then
        jq -e --arg service "$ai_service" \
            '.services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS != ""
             and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS != ""
             and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF != ""
             and (.services[$service].environment.EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST
                  | test("^sha256:[0-9a-f]{64}$"))' \
            "$rendered" >/dev/null || fail "compose-operator-runtime-drift"
        if jq -e '.bindingCandidatesConfigured == false' \
            "$runtime_receipt_file" >/dev/null; then
            jq -e --arg service "$ai_service" \
                '.services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID == ""
                 and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID == ""
                 and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID == ""
                 and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID == ""
                 and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID == ""' \
                "$rendered" >/dev/null || fail "compose-audit-only-candidates-drift"
        else
            jq -e --arg service "$ai_service" \
                '.services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID != ""
                 and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID != ""
                 and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID != ""
                 and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID != ""
                 and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID != ""' \
                "$rendered" >/dev/null || fail "compose-binding-candidates-drift"
        fi
    fi
    if rg --fixed-strings '/api/v1/ai/build-ghost/explain' "$script_root/Caddyfile" >/dev/null; then
        fail "public-explain-route-present"
    fi
}

build_candidate_under_limits() {
    local build_status
    ensure_hard_limits
    setsid bash -c 'exec "$@"' deploy-build \
        docker compose "${compose_environment_args[@]}" \
        --project-name "$project_name" \
        --project-directory "$repo_root" \
        --file "$compose_file" \
        build "$presentation_service" \
        > "$deploy_tmp/build.log" 2>&1 &
    build_pid="$!"
    while kill -0 "$build_pid" 2>/dev/null; do
        if ! ensure_hard_limits; then
            terminate_build
            fail "candidate-build-host-cutoff"
        fi
        sleep "$build_poll_seconds"
    done
    set +e
    wait "$build_pid"
    build_status="$?"
    set -e
    build_pid=""
    [ "$build_status" -eq 0 ] || fail "candidate-build-failed"
    candidate_built="true"
    ensure_hard_limits
    verify_source_labels "$deployment_image"
}

wait_for_presentation_health() {
    local container_id="$1"
    local enforce_limits="${2:-enforce-limits}"
    local health
    for _ in $(seq 1 60); do
        if [ "$enforce_limits" = "enforce-limits" ]; then
            ensure_hard_limits
        fi
        health="$(docker inspect "$container_id" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}')"
        if [ "$health" = "healthy" ] \
            && docker exec "$container_id" curl --fail --silent --show-error --max-time 5 \
                http://127.0.0.1:8080/health/ready >/dev/null; then
            return 0
        fi
        [ "$health" != "unhealthy" ] || return 1
        sleep 2
    done
    return 1
}

copy_edge_root_certificate() {
    docker cp "$edge_id_before:/data/caddy/pki/authorities/local/root.crt" \
        "$deploy_tmp/root.crt" >/dev/null
    chmod 0600 "$deploy_tmp/root.crt"
}

edge_binding() {
    local binding host_ip host_port
    binding="$(docker inspect "$edge_id_before" --format '{{with (index .NetworkSettings.Ports "443/tcp")}}{{with (index . 0)}}{{.HostIp}}:{{.HostPort}}{{end}}{{end}}')"
    host_ip="${binding%:*}"
    host_port="${binding##*:}"
    [ "$host_ip" = "127.0.0.1" ] || fail "edge-not-loopback-only"
    [[ "$host_port" =~ ^[0-9]+$ ]] || fail "edge-port-invalid"
    printf '%s:%s' "$host_ip" "$host_port"
}

verify_private_route_auth() {
    local binding host_ip host_port missing_status invalid_status
    binding="$(edge_binding)"
    host_ip="${binding%:*}"
    host_port="${binding##*:}"
    jq -cS -n \
        --arg key 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' \
        --arg digest 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
        '{packet_access_key:$key,packet_digest:$digest,locale:"en-US",request_kind:"current-build"}' \
        > "$deploy_tmp/private-auth-request.json"
    chmod 0600 "$deploy_tmp/private-auth-request.json"
    missing_status="$(curl --silent --show-error --max-time 15 \
        --output /dev/null --write-out '%{http_code}' \
        --cacert "$deploy_tmp/root.crt" \
        --resolve "presentation.canary.chummer.run:$host_port:$host_ip" \
        --header 'Content-Type: application/json' \
        --data-binary "@$deploy_tmp/private-auth-request.json" \
        "https://presentation.canary.chummer.run:$host_port/api/internal/build-ghost/tool/resolve")"
    invalid_status="$(curl --silent --show-error --max-time 15 \
        --output /dev/null --write-out '%{http_code}' \
        --cacert "$deploy_tmp/root.crt" \
        --resolve "presentation.canary.chummer.run:$host_port:$host_ip" \
        --header 'Content-Type: application/json' \
        --header 'Authorization: Bearer invalid-presentation-deploy-check' \
        --data-binary "@$deploy_tmp/private-auth-request.json" \
        "https://presentation.canary.chummer.run:$host_port/api/internal/build-ghost/tool/resolve")"
    [ "$missing_status" = "401" ] || fail "private-route-missing-auth-not-401"
    [ "$invalid_status" = "401" ] || fail "private-route-invalid-auth-not-401"
}

verify_public_explain_absent() {
    local binding host_ip host_port status
    binding="$(edge_binding)"
    host_ip="${binding%:*}"
    host_port="${binding##*:}"
    status="$(curl --silent --show-error --max-time 15 \
        --output /dev/null --write-out '%{http_code}' \
        --cacert "$deploy_tmp/root.crt" \
        --resolve "canary.chummer.run:$host_port:$host_ip" \
        --request POST --header 'Content-Type: application/json' --data '{}' \
        "https://canary.chummer.run:$host_port/api/v1/ai/build-ghost/explain")"
    [ "$status" = "404" ] || fail "public-explain-not-404"
}

verify_lifecycle_canary() {
    local receipt
    if ! timeout --signal=TERM --kill-after=60s 900s \
        "$canary_script" > "$deploy_tmp/lifecycle-canary.log" 2>&1; then
        receipt="$(rg --line-regexp 'positive_canary=(failed|passed) .*' \
            "$deploy_tmp/lifecycle-canary.log" | sed -n '$p' || true)"
        if [ -n "$receipt" ]; then
            printf '%s\n' "$receipt" >&2
        else
            printf 'positive_canary=failed stage=receipt-missing\n' >&2
        fi
        fail "lifecycle-canary-failed"
    fi
    rg --line-regexp \
        'positive_canary=passed .*tool=200 replay=410 revoked=410 terminal_equivalent=true .*gates=false cleanup=404' \
        "$deploy_tmp/lifecycle-canary.log" >/dev/null \
        || fail "lifecycle-canary-receipt-drift"
}

verify_activation_authority_unchanged() {
    local current_presentation_id current_presentation_image
    [ "$(image_id "$rollback_ref")" = "$old_presentation_image" ] \
        || fail "preactivation-rollback-reference-drift"
    candidate_recovery_is_preserved \
        || fail "preactivation-candidate-recovery-reference-drift"
    verify_source_labels "$candidate_recovery_ref"
    if [ "$recovery_mode" = "true" ]; then
        presentation_is_contained || fail "preactivation-recovery-containment-drift"
        current_presentation_id="$(service_container_id_any_state "$presentation_service")" \
            || fail "preactivation-recovery-presentation-not-exactly-one"
    else
        current_presentation_id="$(running_container_id "$presentation_service")"
    fi
    [ "$current_presentation_id" = "$old_presentation_id" ] \
        || fail "preactivation-presentation-container-drift"
    current_presentation_image="$(docker inspect "$current_presentation_id" --format '{{.Image}}')"
    [ "$current_presentation_image" = "$old_presentation_image" ] \
        || fail "preactivation-presentation-image-drift"
    [ "$(packet_store_volume_name_from_presentation "$current_presentation_id")" \
        = "$old_packet_store_volume_name" ] \
        || fail "preactivation-state-volume-drift"
    [ "$(running_container_id "$ai_service")" = "$ai_id_before" ] \
        || fail "preactivation-ai-container-drift"
    [ "$(running_container_id "$edge_service")" = "$edge_id_before" ] \
        || fail "preactivation-edge-container-drift"
    assert_provider_gates_false "$ai_id_before"
    preflight_initial_packet_store
    [ "$last_packet_store_state" = "$initial_packet_store_state" ] \
        || fail "preactivation-packet-store-state-drift"
    validate_sources_and_labels
}

prepare_candidate_activation_tag() {
    candidate_recovery_is_preserved \
        || fail "preactivation-candidate-recovery-reference-drift"
    verify_source_labels "$candidate_recovery_ref"
    docker image tag "$candidate_recovery_ref" "$deployment_image" \
        || fail "preactivation-candidate-retag-failed"
    [ "$(image_id "$deployment_image" 2>/dev/null)" = "$candidate_image" ] \
        || fail "preactivation-candidate-retag-verification-failed"
    candidate_recovery_is_preserved \
        || fail "preactivation-candidate-recovery-reference-drift-after-retag"
}

validate_initial_packet_store_compatibility() {
    if [ "$initial_packet_store_state" = "keyed-v2" ] \
        && [ "$old_presentation_store_schema" != "$packet_store_schema_version" ]; then
        fail "initial-keyed-v2-running-image-incompatible"
    fi
}

service_container_id_any_state() {
    local service_name="$1"
    local resolved
    resolved="$(docker ps --all --no-trunc \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "label=com.docker.compose.service=$service_name" \
        --format '{{.ID}}')" || return 1
    [ "$(printf '%s\n' "$resolved" | sed '/^$/d' | wc -l)" -eq 1 ] || return 1
    printf '%s' "$resolved"
}

stop_running_presentations() {
    local running_ids container_id
    running_ids="$(docker ps --no-trunc \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "label=com.docker.compose.service=$presentation_service" \
        --format '{{.ID}}')" || return 1
    while IFS= read -r container_id; do
        [ -n "$container_id" ] || continue
        docker stop --time 30 "$container_id" >/dev/null || return 1
    done <<EOF
$running_ids
EOF
}

presentation_is_contained() {
    local running_ids
    running_ids="$(docker ps --no-trunc \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "label=com.docker.compose.service=$presentation_service" \
        --format '{{.ID}}')" || return 1
    [ "$(printf '%s\n' "$running_ids" | sed '/^$/d' | wc -l)" -eq 0 ]
}

neighbors_and_gates_are_unchanged() {
    local current_ai_id current_edge_id
    current_ai_id="$(resolve_running_container_id "$ai_service")" || return 1
    current_edge_id="$(resolve_running_container_id "$edge_service")" || return 1
    [ "$current_ai_id" = "$ai_id_before" ] || return 1
    [ "$current_edge_id" = "$edge_id_before" ] || return 1
    provider_gates_are_false "$ai_id_before"
}

packet_store_volume_name_from_presentation() {
    local container_id="$1"
    local mount_record mount_count mount_type mount_read_write volume_name volume_project volume_role
    mount_record="$(docker inspect "$container_id" --format \
        '{{range .Mounts}}{{if eq .Destination "/app/state"}}{{printf "%s|%t|%s\n" .Type .RW .Name}}{{end}}{{end}}')" \
        || return 1
    mount_count="$(printf '%s\n' "$mount_record" | sed '/^$/d' | wc -l)"
    [ "$mount_count" -eq 1 ] || return 1
    IFS='|' read -r mount_type mount_read_write volume_name <<EOF
$mount_record
EOF
    [ "$mount_type" = "volume" ] || return 1
    [ "$mount_read_write" = "true" ] || return 1
    [[ "$volume_name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || return 1
    volume_project="$(docker volume inspect "$volume_name" --format \
        '{{index .Labels "com.docker.compose.project"}}')" || return 1
    volume_role="$(docker volume inspect "$volume_name" --format \
        '{{index .Labels "com.docker.compose.volume"}}')" || return 1
    [ "$volume_project" = "$project_name" ] || return 1
    [ "$volume_role" = "build-ghost-packet-access" ] || return 1
    printf '%s' "$volume_name"
}

classify_packet_store_volume_for_rollback() {
    local volume_name="$1"
    local inspection_image="${2:-$candidate_recovery_ref}"
    local path_state result
    [[ "$volume_name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
        printf 'unknown'
        return 0
    }
    path_state="$(docker run --rm --pull never --read-only --network none --cap-drop ALL \
        --security-opt no-new-privileges \
        --mount "type=volume,src=$volume_name,dst=/app/state,readonly" \
        --entrypoint sh "$inspection_image" -c '
            if [ ! -e /app/state/build-ghost-packet-access ] \
                && [ ! -L /app/state/build-ghost-packet-access ]; then
                printf "absent"
            elif [ -d /app/state/build-ghost-packet-access ] \
                && [ ! -L /app/state/build-ghost-packet-access ]; then
                printf "present"
            else
                printf "invalid"
                exit 1
            fi
        ' 2>/dev/null)" || {
        printf 'unknown'
        return 0
    }
    if [ "$path_state" = "absent" ]; then
        printf 'empty'
        return 0
    fi
    [ "$path_state" = "present" ] || {
        printf 'unknown'
        return 0
    }
    result="$(docker run --rm --pull never --interactive --read-only --network none --cap-drop ALL \
        --security-opt no-new-privileges \
        --mount "type=volume,src=$volume_name,dst=/app/state,readonly" \
        --entrypoint sh "$inspection_image" -s -- \
        /app/state/build-ghost-packet-access < "$packet_preflight" 2>/dev/null)" || {
        printf 'unknown'
        return 0
    }
    case "$result" in
        'packet_store_preflight=passed state=empty') printf 'empty' ;;
        'packet_store_preflight=passed state=keyed-v2') printf 'keyed-v2' ;;
        *) printf 'unknown' ;;
    esac
}

preflight_initial_packet_store() {
    local state
    if [ "$recovery_mode" = "false" ]; then
        preflight_packet_store "$old_presentation_id"
        return 0
    fi
    state="$(classify_packet_store_volume_for_rollback \
        "$old_packet_store_volume_name" "$old_presentation_image")"
    case "$state" in
        empty|keyed-v2) ;;
        *) fail "recovery-packet-store-state-unprovable" ;;
    esac
    last_packet_store_state="$state"
}

classify_contained_packet_store_for_rollback() {
    local container_id volume_name
    presentation_is_contained || {
        printf 'unknown'
        return 0
    }
    neighbors_and_gates_are_unchanged || {
        printf 'unknown'
        return 0
    }
    container_id="$(service_container_id_any_state "$presentation_service")" || {
        printf 'unknown'
        return 0
    }
    volume_name="$(packet_store_volume_name_from_presentation "$container_id")" || {
        printf 'unknown'
        return 0
    }
    [ "$volume_name" = "$old_packet_store_volume_name" ] || {
        printf 'unknown'
        return 0
    }
    classify_packet_store_volume_for_rollback "$volume_name"
}

quiesce_and_classify_packet_store_for_rollback() {
    stop_running_presentations || {
        printf 'unknown'
        return 0
    }
    classify_contained_packet_store_for_rollback
}

terminally_verify_legacy_empty_store_for_rollback() {
    local container_id volume_name terminal_state final_container_id final_volume_name
    presentation_is_contained || return 1
    neighbors_and_gates_are_unchanged || return 1
    container_id="$(service_container_id_any_state "$presentation_service")" || return 1
    volume_name="$(packet_store_volume_name_from_presentation "$container_id")" || return 1
    [ "$volume_name" = "$old_packet_store_volume_name" ] || return 1
    terminal_state="$(classify_packet_store_volume_for_rollback "$volume_name")" || return 1
    [ "$terminal_state" = "empty" ] || return 1
    presentation_is_contained || return 1
    neighbors_and_gates_are_unchanged || return 1
    final_container_id="$(service_container_id_any_state "$presentation_service")" || return 1
    [ "$final_container_id" = "$container_id" ] || return 1
    final_volume_name="$(packet_store_volume_name_from_presentation "$final_container_id")" || return 1
    [ "$final_volume_name" = "$volume_name" ] || return 1
    presentation_is_contained || return 1
    neighbors_and_gates_are_unchanged
}

rollback_image_is_preserved() {
    [ -n "$rollback_ref" ] || return 1
    [ "$(image_id "$rollback_ref" 2>/dev/null)" = "$old_presentation_image" ]
}

candidate_recovery_is_preserved() {
    [ -n "$candidate_recovery_ref" ] || return 1
    [ -n "$candidate_image" ] || return 1
    [ "$(image_id "$candidate_recovery_ref" 2>/dev/null)" = "$candidate_image" ] || return 1
    [ "$(image_label "$candidate_recovery_ref" "$packet_store_schema_label" 2>/dev/null)" \
        = "$packet_store_schema_version" ]
}

recovery_containment_is_verified() {
    rollback_image_is_preserved \
        && candidate_recovery_is_preserved \
        && presentation_is_contained \
        && neighbors_and_gates_are_unchanged
}

contain_presentation_for_recovery() {
    local reason="$1"
    case "$reason" in
        v2-authority-present|packet-store-state-unprovable|rollback-restore-failed|recovery-candidate-failed) ;;
        *) reason="packet-store-state-unprovable" ;;
    esac
    if ! stop_running_presentations \
        || ! recovery_containment_is_verified \
        || ! recovery_containment_is_verified; then
        printf 'presentation_deploy=recovery-required reason=%s containment=failed packet_store=preserved candidate_recovery_ref=%s old_rollback=preserved\n' \
            "$reason" "$candidate_recovery_ref" >&2
        return 1
    fi
    printf 'presentation_deploy=recovery-required reason=%s containment=verified packet_store=preserved candidate_recovery_ref=%s old_rollback=preserved neighbors=unchanged gates=false\n' \
        "$reason" "$candidate_recovery_ref" >&2
}

run_postchecks() {
    local current_presentation_id current_presentation_image current_packet_store_volume_name
    current_presentation_id="$(running_container_id "$presentation_service")"
    [ "$current_presentation_id" != "$old_presentation_id" ] \
        || fail "postcheck-presentation-container-not-recreated"
    current_presentation_image="$(docker inspect "$current_presentation_id" --format '{{.Image}}')"
    [ "$current_presentation_image" = "$candidate_image" ] \
        || fail "postcheck-presentation-image-not-candidate"
    current_packet_store_volume_name="$(packet_store_volume_name_from_presentation "$current_presentation_id")" \
        || fail "postcheck-state-volume-invalid"
    [ "$current_packet_store_volume_name" = "$old_packet_store_volume_name" ] \
        || fail "postcheck-state-volume-drift"
    candidate_recovery_is_preserved \
        || fail "postcheck-candidate-recovery-reference-drift"
    verify_source_labels "$candidate_recovery_ref"
    wait_for_presentation_health "$current_presentation_id" || fail "postcheck-presentation-health"
    [ "$(running_container_id "$presentation_service")" = "$current_presentation_id" ] \
        || fail "postcheck-presentation-container-changed-after-health"
    [ "$(docker inspect "$current_presentation_id" --format '{{.Image}}')" = "$candidate_image" ] \
        || fail "postcheck-presentation-image-changed-after-health"
    [ "$(running_container_id "$ai_service")" = "$ai_id_before" ] \
        || fail "postcheck-ai-container-changed"
    [ "$(running_container_id "$edge_service")" = "$edge_id_before" ] \
        || fail "postcheck-edge-container-changed"
    assert_provider_gates_false "$ai_id_before"
    copy_edge_root_certificate
    verify_private_route_auth
    verify_public_explain_absent
    verify_lifecycle_canary
    preflight_packet_store "$current_presentation_id"
    docker exec "$current_presentation_id" test -f \
        /app/state/build-ghost-packet-access/state-authority.v2.json \
        || fail "postcheck-keyed-authority-not-created"
    [ "$(running_container_id "$ai_service")" = "$ai_id_before" ] \
        || fail "postcheck-ai-container-changed-after-canary"
    [ "$(running_container_id "$edge_service")" = "$edge_id_before" ] \
        || fail "postcheck-edge-container-changed-after-canary"
    assert_provider_gates_false "$ai_id_before"
    [ "$(running_container_id "$presentation_service")" = "$current_presentation_id" ] \
        || fail "postcheck-presentation-container-changed-after-canary"
    [ "$(docker inspect "$current_presentation_id" --format '{{.Image}}')" = "$candidate_image" ] \
        || fail "postcheck-presentation-image-changed-after-canary"
    candidate_recovery_is_preserved \
        || fail "postcheck-candidate-recovery-reference-drift-after-canary"
}

restore_preserved_presentation_image() {
    local restored_presentation_id restored_image post_health_presentation_id post_health_image
    if ! docker image tag "$rollback_ref" "$deployment_image"; then
        printf 'presentation_deploy=rollback-failed stage=deployment-retag\n' >&2
        return 1
    fi
    if [ "$(image_id "$deployment_image" 2>/dev/null)" != "$old_presentation_image" ]; then
        printf 'presentation_deploy=rollback-failed stage=deployment-retag-verification\n' >&2
        return 1
    fi
    if ! compose up -d --no-deps --no-build --force-recreate "$presentation_service"; then
        printf 'presentation_deploy=rollback-failed stage=presentation-recreate\n' >&2
        return 1
    fi
    restored_presentation_id="$(resolve_running_container_id "$presentation_service")" || {
        printf 'presentation_deploy=rollback-failed stage=restored-presentation-not-running\n' >&2
        return 1
    }
    restored_image="$(docker inspect "$restored_presentation_id" --format '{{.Image}}')" || {
        printf 'presentation_deploy=rollback-failed stage=restored-presentation-uninspectable\n' >&2
        return 1
    }
    if [ "$restored_image" != "$old_presentation_image" ]; then
        printf 'presentation_deploy=rollback-failed stage=runtime-verification\n' >&2
        return 1
    fi
    if ! wait_for_presentation_health "$restored_presentation_id" rollback-verification; then
        printf 'presentation_deploy=rollback-failed stage=runtime-verification\n' >&2
        return 1
    fi
    post_health_presentation_id="$(resolve_running_container_id "$presentation_service")" || {
        printf 'presentation_deploy=rollback-failed stage=post-health-presentation-not-exactly-one\n' >&2
        return 1
    }
    post_health_image="$(docker inspect "$post_health_presentation_id" --format '{{.Image}}')" || {
        printf 'presentation_deploy=rollback-failed stage=post-health-presentation-uninspectable\n' >&2
        return 1
    }
    if [ "$post_health_presentation_id" != "$restored_presentation_id" ] \
        || [ "$post_health_image" != "$old_presentation_image" ] \
        || ! neighbors_and_gates_are_unchanged \
        || ! rollback_image_is_preserved \
        || ! candidate_recovery_is_preserved; then
        printf 'presentation_deploy=rollback-failed stage=runtime-verification\n' >&2
        return 1
    fi
    printf 'presentation_deploy=rollback-restored rollback_ref=%s image=%s\n' \
        "$rollback_ref" "$old_presentation_image" >&2
    return 0
}

restore_preserved_presentation_image_or_contain() {
    local rollback_policy="${1:-v2-compatible}"
    if [ "$rollback_policy" = "legacy-empty" ] \
        && ! terminally_verify_legacy_empty_store_for_rollback; then
        contain_presentation_for_recovery packet-store-state-unprovable || true
        return 1
    fi
    if restore_preserved_presentation_image; then
        return 0
    fi
    contain_presentation_for_recovery rollback-restore-failed || true
    return 1
}

rollback_if_needed() {
    local rollback_schema quiesced_state containment_reason
    if [ "$activation_started" != "true" ] || [ "$deploy_succeeded" = "true" ] \
        || [ "$rollback_started" = "true" ]; then
        return 0
    fi
    rollback_started="true"
    printf 'presentation_deploy=rollback-started rollback_ref=%s\n' "$rollback_ref" >&2
    set +e
    if [ -z "$rollback_ref" ] \
        || [ "$(image_id "$rollback_ref" 2>/dev/null)" != "$old_presentation_image" ]; then
        printf 'presentation_deploy=rollback-failed stage=preserved-image-unavailable\n' >&2
        contain_presentation_for_recovery rollback-restore-failed || true
        return 1
    fi

    rollback_schema="$(image_label "$rollback_ref" "$packet_store_schema_label" 2>/dev/null)"
    quiesced_state="$(quiesce_and_classify_packet_store_for_rollback)"
    if [ "$quiesced_state" != "empty" ] && [ "$quiesced_state" != "keyed-v2" ]; then
        contain_presentation_for_recovery packet-store-state-unprovable || return 1
        return 1
    fi
    if [ "$recovery_mode" = "true" ]; then
        contain_presentation_for_recovery recovery-candidate-failed || return 1
        return 1
    fi
    if [ "$rollback_schema" = "$packet_store_schema_version" ]; then
        restore_preserved_presentation_image_or_contain v2-compatible
        return $?
    fi
    if [ "$quiesced_state" = "empty" ]; then
        restore_preserved_presentation_image_or_contain legacy-empty
        return $?
    fi
    if [ "$quiesced_state" = "keyed-v2" ]; then
        containment_reason="v2-authority-present"
    else
        containment_reason="packet-store-state-unprovable"
    fi
    contain_presentation_for_recovery "$containment_reason" || return 1
    return 1
}

restore_pre_activation_tag_if_needed() {
    if [ "$candidate_built" != "true" ] || [ "$activation_started" = "true" ] \
        || [ "$deploy_succeeded" = "true" ]; then
        return 0
    fi
    if [ -z "$rollback_ref" ] \
        || [ "$(image_id "$rollback_ref" 2>/dev/null)" != "$old_presentation_image" ]; then
        printf 'presentation_deploy=preactivation-tag-restore-failed stage=preserved-image-unavailable\n' >&2
        return 1
    fi
    docker image tag "$rollback_ref" "$deployment_image"
    if [ "$(image_id "$deployment_image" 2>/dev/null)" != "$old_presentation_image" ]; then
        printf 'presentation_deploy=preactivation-tag-restore-failed stage=deployment-retag-verification\n' >&2
        return 1
    fi
    printf 'presentation_deploy=preactivation-tag-restored rollback_ref=%s image=%s\n' \
        "$rollback_ref" "$old_presentation_image" >&2
    return 0
}

on_exit() {
    local status="$?"
    trap - EXIT HUP INT TERM
    terminate_build
    if ! (rollback_if_needed); then
        status=1
    fi
    if ! (restore_pre_activation_tag_if_needed); then
        status=1
    fi
    if ! securely_remove_runtime_environment; then
        status=1
    fi
    securely_remove_temp
    exit "$status"
}

main() {
    trap on_exit EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM

    for lock_required in chmod dirname flock mkdir; do
        require_command "$lock_required"
    done
    acquire_deploy_lock "$deploy_lock_file"
    for required in awk bash cat curl cut date df docker find git id jq mktemp mv openssl python3 realpath rg rmdir sed seq setsid sha256sum shred sleep stat timeout truncate unlink wc; do
        require_command "$required"
    done
    [ -x "$packet_preflight" ] || fail "packet-store-preflight-not-executable"
    [ -x "$canary_script" ] || fail "lifecycle-canary-not-executable"
    validate_control_values
    deploy_tmp="$(mktemp -d)"
    chmod 0700 "$deploy_tmp"
    prepare_operator_runtime_config
    validate_sources_and_labels
    ensure_hard_limits

    ai_id_before="$(running_container_id "$ai_service")"
    edge_id_before="$(running_container_id "$edge_service")"
    assert_provider_gates_false "$ai_id_before"
    snapshot_presentation_authority
    preflight_initial_packet_store
    initial_packet_store_state="$last_packet_store_state"
    validate_initial_packet_store_compatibility
    preserve_rollback_image
    load_runtime_environment_without_output
    verify_rendered_compose
    build_candidate_under_limits
    preserve_candidate_recovery_image
    ensure_hard_limits
    verify_activation_authority_unchanged
    prepare_candidate_activation_tag

    activation_started="true"
    compose up -d --no-deps --no-build --force-recreate "$presentation_service"
    run_postchecks
    deploy_succeeded="true"
    printf 'presentation_deploy=passed rollback_ref=%s old_image=%s candidate_recovery_ref=%s candidate_image=%s recovery_mode=%s sources=exact packet_store=keyed-v2 auth=401 lifecycle=one-use-replay-revocation gates=false neighbors=unchanged public_explain=404\n' \
        "$rollback_ref" "$old_presentation_image" "$candidate_recovery_ref" "$candidate_image" "$recovery_mode"
    if [ -n "$runtime_receipt_file" ]; then
        printf 'presentation_deploy_runtime_contract=retained receipt=%s contract=%s credentials_retained=false\n' \
            "$runtime_receipt_file" "$runtime_contract_file"
    fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
