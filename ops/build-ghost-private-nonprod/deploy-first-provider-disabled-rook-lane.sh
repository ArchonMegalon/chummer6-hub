#!/usr/bin/env bash
# shellcheck disable=SC2015
set -euo pipefail

# Governed first transition into the provider-disabled private Rook lane.
# This is intentionally separate from the AI-only and Presentation-only rolling
# helpers: those recover the journal key from an already bootstrapped AI.
umask 077

script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_root/../.." && pwd -P)"
compose_file="$repo_root/docker-compose.build-ghost-private-nonprod.yml"
canary_script="$script_root/run-local-canary.sh"
unconfigured_contract="$script_root/tough-tongue-read-only-binding-contract.unconfigured.json"
project_name="chummer-build-ghost-private-nonprod"
presentation_service="chummer-build-ghost-presentation"
ai_service="chummer-build-ghost-ai"
edge_service="build-ghost-private-edge"
initializer_service="build-ghost-live-support-store-init"
presentation_image="chummer-build-ghost-presentation:private-nonprod"
ai_image="chummer-build-ghost-ai:private-nonprod"
edge_image="caddy:2.10.2-alpine"
live_volume="${project_name}_build-ghost-live-support"
lane_lock="/docker/chummercomplete/.state/locks/chummer-build-ghost-private-nonprod-ai-deploy.lock"
minimum_free_gib="${CHUMMER_BUILD_GHOST_FIRST_ROLLOUT_MINIMUM_FREE_GIB:-28}"
max_io_full_avg10="${CHUMMER_BUILD_GHOST_DEPLOY_MAX_IO_FULL_AVG10:-10}"
poll_seconds="${CHUMMER_BUILD_GHOST_DEPLOY_POLL_SECONDS:-10}"
build_timeout_seconds="${CHUMMER_BUILD_GHOST_FIRST_ROLLOUT_BUILD_TIMEOUT_SECONDS:-3600}"
up_timeout_seconds="${CHUMMER_BUILD_GHOST_FIRST_ROLLOUT_UP_TIMEOUT_SECONDS:-900}"
receipt_path="${CHUMMER_BUILD_GHOST_FIRST_ROLLOUT_RECEIPT:-}"

deploy_tmp=""
build_pid=""
activation_started="false"
deploy_succeeded="false"
rollback_started="false"
failure_stage="not-started"
receipt_written="false"
old_presentation_id=""
old_ai_id=""
old_edge_id=""
old_presentation_image=""
old_ai_image=""
old_edge_image=""
old_packet_volume=""
old_caddy_data_volume=""
old_caddy_config_volume=""
old_caddy_trust_volume=""
presentation_rollback_ref=""
ai_rollback_ref=""
edge_rollback_ref=""
candidate_presentation_image=""
candidate_ai_image=""

required_empty_provider_variables=(
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_PROVIDER
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_NAME
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_ASSET_PATH
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_DIGEST
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_RECEIPT_JSON
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_PROVIDER
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ALLOW_LEGACY_CASCADE
    EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST
)

required_literal_empty_live_variables=(
    CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_RECEIPT_PATH
    CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_HMAC_KEY
    CHUMMER_BUILD_GHOST_LIVE_SUPPORT_ACCOUNT_SCOPE_REF_DIGEST
    CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SCENARIO_REF_DIGEST
    CHUMMER_BUILD_GHOST_LIVE_SUPPORT_AVATAR_BINDING_DIGEST
    CHUMMER_BUILD_GHOST_ROOK_VIDBOARD_MEDIA_HREF
    CHUMMER_BUILD_GHOST_ROOK_VIDBOARD_MEDIA_DIGEST
    CHUMMER_BUILD_GHOST_PERSONA_RELEASE_REGISTRY_PATH
    CHUMMER_BUILD_GHOST_MEETING_BROKER_BASE_URL
    CHUMMER_BUILD_GHOST_MEETING_BROKER_API_TOKEN
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_API_KEY
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_SCENARIO_ID
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_NAME
)

fail() {
    failure_stage="$1"
    printf 'rook_first_rollout=failed stage=%s\n' "$failure_stage" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "preflight-missing-$1"
}

compose() {
    COMPOSE_PROFILES='' docker compose \
        --project-name "$project_name" \
        --project-directory "$repo_root" \
        --file "$compose_file" \
        "$@"
}

image_id() {
    docker image inspect "$1" --format '{{.Id}}'
}

running_container_id() {
    local service="$1" resolved
    resolved="$(docker ps --no-trunc \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "label=com.docker.compose.service=$service" \
        --filter status=running --format '{{.ID}}')"
    [ "$(printf '%s\n' "$resolved" | sed '/^$/d' | wc -l)" -eq 1 ] \
        || fail "runtime-$service-not-exactly-one"
    printf '%s' "$resolved"
}

validate_control_values() {
    [ "${CHUMMER_BUILD_GHOST_PRIVATE_HTTPS_PORT:-8443}" = 8443 ] \
        || fail "loopback-port-must-remain-8443"
    [[ "$minimum_free_gib" =~ ^[0-9]+$ ]] && [ "$minimum_free_gib" -ge 28 ] \
        || fail "minimum-free-space-must-be-at-least-twenty-eight-gib"
    [[ "$max_io_full_avg10" =~ ^([0-9]+)(\.[0-9]+)?$ ]] \
        || fail "max-io-cutoff-invalid"
    awk -v value="$max_io_full_avg10" 'BEGIN { exit !(value > 0 && value <= 10) }' \
        || fail "max-io-cutoff-must-not-exceed-ten"
    [[ "$poll_seconds" =~ ^[0-9]+$ ]] \
        && [ "$poll_seconds" -ge 1 ] && [ "$poll_seconds" -le 15 ] \
        || fail "build-poll-must-be-one-to-fifteen-seconds"
    [[ "$build_timeout_seconds" =~ ^[0-9]+$ ]] \
        && [ "$build_timeout_seconds" -ge 300 ] && [ "$build_timeout_seconds" -le 7200 ] \
        || fail "build-timeout-invalid"
    [[ "$up_timeout_seconds" =~ ^[0-9]+$ ]] \
        && [ "$up_timeout_seconds" -ge 120 ] && [ "$up_timeout_seconds" -le 1800 ] \
        || fail "activation-timeout-invalid"
}

host_limits_ok() {
    local free_kib required_kib io_full_avg10
    io_full_avg10="$(awk '/^full / { for (field=1; field<=NF; field++) if ($field ~ /^avg10=/) { split($field,pair,"="); print pair[2]; exit } }' /proc/pressure/io)"
    [ -n "$io_full_avg10" ] \
        && awk -v observed="$io_full_avg10" -v maximum="$max_io_full_avg10" \
            'BEGIN { exit !(observed <= maximum) }' \
        || return 1
    free_kib="$(df -Pk /docker | awk 'NR == 2 {print $4}')"
    required_kib="$((minimum_free_gib * 1024 * 1024))"
    [ -n "$free_kib" ] && [ "$free_kib" -ge "$required_kib" ]
}

ensure_host_limits() {
    host_limits_ok || fail "host-disk-or-io-pressure-cutoff"
}

validate_source() {
    local source_variable="$1" revision_variable="$2"
    local source expected actual dirty
    source="${!source_variable:-}"
    expected="${!revision_variable:-}"
    [ -n "$source" ] && [[ "$source" == /* ]] \
        || fail "source-$source_variable-missing-or-relative"
    source="$(realpath -e -- "$source")" \
        || fail "source-$source_variable-unavailable"
    [[ "$expected" =~ ^[0-9a-f]{40}$ ]] \
        || fail "revision-$revision_variable-invalid"
    git -C "$source" rev-parse --git-dir >/dev/null 2>&1 \
        || fail "source-$source_variable-not-git"
    actual="$(git -C "$source" rev-parse --verify HEAD)"
    [ "$actual" = "$expected" ] || fail "source-$source_variable-revision-drift"
    dirty="$(git -C "$source" status --porcelain --untracked-files=all)"
    [ -z "$dirty" ] || fail "source-$source_variable-dirty"
    printf -v "$source_variable" '%s' "$source"
    export "${source_variable?}"
}

validate_sources_and_authoritative_hub() {
    local remote_main matches
    validate_source CHUMMER_RUN_SERVICES_SOURCE CHUMMER_RUN_SERVICES_REVISION
    [ "$CHUMMER_RUN_SERVICES_SOURCE" = "$repo_root" ] \
        || fail "hub-source-does-not-own-helper"
    validate_source CHUMMER_PRESENTATION_SOURCE CHUMMER_PRESENTATION_REVISION
    validate_source CHUMMER_CORE_ENGINE_SOURCE CHUMMER_CORE_ENGINE_REVISION
    validate_source CHUMMER_HUB_REGISTRY_SOURCE CHUMMER_HUB_REGISTRY_REVISION
    validate_source CHUMMER_UI_KIT_SOURCE CHUMMER_UI_KIT_REVISION
    validate_source CHUMMER_MEDIA_FACTORY_SOURCE CHUMMER_MEDIA_FACTORY_REVISION
    remote_main="$(git -C "$repo_root" ls-remote --exit-code origin refs/heads/main)" \
        || fail "hub-authoritative-main-unavailable"
    matches="$(printf '%s\n' "$remote_main" | awk '$2=="refs/heads/main"{count++} END{print count+0}')"
    [ "$matches" -eq 1 ] || fail "hub-authoritative-main-ambiguous"
    remote_main="${remote_main%%[[:space:]]*}"
    [ "$remote_main" = "$CHUMMER_RUN_SERVICES_REVISION" ] \
        || fail "hub-head-is-not-authoritative-origin-main"
}

validate_external_secrets_without_output() {
    local decoded_length
    [ -n "${CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN:-}" ] \
        && [ "${#CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN}" -ge 32 ] \
        || fail "private-tool-service-token-invalid"
    [ -n "${CHUMMER_AI_INTERNAL_API_TOKEN:-}" ] \
        && [ "${#CHUMMER_AI_INTERNAL_API_TOKEN}" -ge 32 ] \
        || fail "ai-internal-token-invalid"
    [ "$CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN" != "$CHUMMER_AI_INTERNAL_API_TOKEN" ] \
        || fail "service-tokens-not-distinct"
    [[ "${CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY:-}" =~ ^[A-Za-z0-9+/]{43}=$ ]] \
        || fail "live-support-session-store-key-invalid"
    decoded_length="$(printf '%s' "$CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY" \
        | base64 --decode 2>/dev/null | wc -c)"
    [ "$decoded_length" -eq 32 ] || fail "live-support-session-store-key-invalid"
    [ "$CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY" != "$CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN" ] \
        && [ "$CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY" != "$CHUMMER_AI_INTERNAL_API_TOKEN" ] \
        || fail "live-support-session-store-key-not-distinct"
}

pin_provider_disabled_environment() {
    local variable
    for variable in "${required_empty_provider_variables[@]}"; do
        printf -v "$variable" ''
        export "${variable?}"
    done
    export CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE="$unconfigured_contract"
    unset COMPOSE_PROFILES
}

verify_rendered_provider_disabled_compose() {
    local rendered="$deploy_tmp/compose.rendered.json" variable
    compose config --format json > "$rendered"
    chmod 0600 "$rendered"
    jq -e --arg ai "$ai_service" --arg presentation "$presentation_service" --arg edge "$edge_service" \
        --arg initializer "$initializer_service" --arg sentinel "$unconfigured_contract" \
        --arg hub "$CHUMMER_RUN_SERVICES_REVISION" \
        --arg presentation_revision "$CHUMMER_PRESENTATION_REVISION" \
        --arg core "$CHUMMER_CORE_ENGINE_REVISION" \
        --arg registry "$CHUMMER_HUB_REGISTRY_REVISION" \
        --arg ui "$CHUMMER_UI_KIT_REVISION" \
        --arg media "$CHUMMER_MEDIA_FACTORY_REVISION" \
        '.services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED == "false"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED == "false"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED == "false"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED == "false"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED == "false"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SINGLE_INSTANCE == "true"
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY == $ENV.CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY
         and .services[$presentation].environment.CHUMMER_AI_INTERNAL_API_TOKEN == .services[$ai].environment.CHUMMER_AI_INTERNAL_API_TOKEN
         and (.services[$edge].ports | length) == 1
         and .services[$edge].ports[0].host_ip == "127.0.0.1"
         and .services[$edge].ports[0].target == 443
         and ((.services[$presentation].ports // []) | length) == 0
         and ((.services[$ai].ports // []) | length) == 0
         and .networks["build-ghost-private"].internal == true
         and .services[$initializer].network_mode == "none"
         and .services[$initializer].read_only == true
         and .secrets["build-ghost-tough-tongue-read-only-binding-contract"].file == $sentinel
         and .services[$ai].build.args.CHUMMER_RUN_SERVICES_REVISION == $hub
         and .services[$ai].build.args.CHUMMER_CORE_ENGINE_REVISION == $core
         and .services[$ai].build.args.CHUMMER_HUB_REGISTRY_REVISION == $registry
         and .services[$ai].build.args.CHUMMER_MEDIA_FACTORY_REVISION == $media
         and .services[$presentation].build.args.CHUMMER_RUN_SERVICES_REVISION == $hub
         and .services[$presentation].build.args.CHUMMER_PRESENTATION_REVISION == $presentation_revision
         and .services[$presentation].build.args.CHUMMER_CORE_ENGINE_REVISION == $core
         and .services[$presentation].build.args.CHUMMER_HUB_REGISTRY_REVISION == $registry
         and .services[$presentation].build.args.CHUMMER_UI_KIT_REVISION == $ui
         and .services[$presentation].build.args.CHUMMER_MEDIA_FACTORY_REVISION == $media
         and (.services | has("build-ghost-cloudflare-access-edge") | not)' \
        "$rendered" >/dev/null || fail "compose-loopback-or-provider-posture-drift"
    for variable in "${required_empty_provider_variables[@]}" "${required_literal_empty_live_variables[@]}"; do
        jq -e --arg ai "$ai_service" --arg variable "$variable" \
            '.services[$ai].environment[$variable] == ""' "$rendered" >/dev/null \
            || fail "compose-provider-input-$variable-not-empty"
    done
}

image_label() {
    docker image inspect "$1" --format "{{index .Config.Labels \"$2\"}}"
}

verify_candidate_source_labels() {
    [ "$(image_label "$presentation_image" org.opencontainers.image.revision)" = "$CHUMMER_PRESENTATION_REVISION" ] \
        && [ "$(image_label "$presentation_image" run.chummer.build-ghost.hub-revision)" = "$CHUMMER_RUN_SERVICES_REVISION" ] \
        && [ "$(image_label "$presentation_image" run.chummer.build-ghost.core-revision)" = "$CHUMMER_CORE_ENGINE_REVISION" ] \
        && [ "$(image_label "$presentation_image" run.chummer.build-ghost.hub-registry-revision)" = "$CHUMMER_HUB_REGISTRY_REVISION" ] \
        && [ "$(image_label "$presentation_image" run.chummer.build-ghost.ui-kit-revision)" = "$CHUMMER_UI_KIT_REVISION" ] \
        && [ "$(image_label "$presentation_image" run.chummer.build-ghost.media-factory-revision)" = "$CHUMMER_MEDIA_FACTORY_REVISION" ] \
        && [ "$(image_label "$presentation_image" run.chummer.build-ghost.packet-store-schema)" = v2 ] \
        || fail "presentation-candidate-source-label-drift"
    [ "$(image_label "$ai_image" org.opencontainers.image.revision)" = "$CHUMMER_RUN_SERVICES_REVISION" ] \
        && [ "$(image_label "$ai_image" run.chummer.build-ghost.core-revision)" = "$CHUMMER_CORE_ENGINE_REVISION" ] \
        && [ "$(image_label "$ai_image" run.chummer.build-ghost.hub-registry-revision)" = "$CHUMMER_HUB_REGISTRY_REVISION" ] \
        && [ "$(image_label "$ai_image" run.chummer.build-ghost.media-factory-revision)" = "$CHUMMER_MEDIA_FACTORY_REVISION" ] \
        || fail "ai-candidate-source-label-drift"
}

assert_healthy() {
    local container="$1"
    [ "$(docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}')" = healthy ]
}

volume_for_mount() {
    local container="$1" destination="$2" resolved
    resolved="$(docker inspect "$container" --format \
        '{{range .Mounts}}{{if and (eq .Type "volume") (eq .Destination "'"$destination"'")}}{{println .Name}}{{end}}{{end}}')"
    [ "$(printf '%s\n' "$resolved" | sed '/^$/d' | wc -l)" -eq 1 ] \
        || fail "runtime-volume-$destination-not-exactly-one"
    printf '%s' "$resolved"
}

assert_loopback_edge() {
    local container="$1"
    docker inspect "$container" --format '{{json .HostConfig.PortBindings}}' \
        | jq -e 'keys == ["443/tcp"] and .["443/tcp"] == [{"HostIp":"127.0.0.1","HostPort":"8443"}]' \
            >/dev/null || fail "runtime-edge-not-exact-loopback"
}

snapshot_runtime_authority() {
    old_presentation_id="$(running_container_id "$presentation_service")"
    old_ai_id="$(running_container_id "$ai_service")"
    old_edge_id="$(running_container_id "$edge_service")"
    assert_healthy "$old_presentation_id" || fail "runtime-presentation-unhealthy"
    assert_healthy "$old_ai_id" || fail "runtime-ai-unhealthy"
    [ "$(docker inspect "$old_edge_id" --format '{{.State.Status}}')" = running ] \
        || fail "runtime-edge-not-running"
    assert_loopback_edge "$old_edge_id"
    old_presentation_image="$(docker inspect "$old_presentation_id" --format '{{.Image}}')"
    old_ai_image="$(docker inspect "$old_ai_id" --format '{{.Image}}')"
    old_edge_image="$(docker inspect "$old_edge_id" --format '{{.Image}}')"
    old_packet_volume="$(volume_for_mount "$old_presentation_id" /app/state)"
    old_caddy_data_volume="$(volume_for_mount "$old_edge_id" /data)"
    old_caddy_config_volume="$(volume_for_mount "$old_edge_id" /config)"
    old_caddy_trust_volume="$(volume_for_mount "$old_ai_id" /caddy-trust)"
    if docker volume inspect "$live_volume" >/dev/null 2>&1; then
        fail "live-support-volume-must-be-new-and-absent"
    fi
}

create_rollback_refs() {
    local nonce
    nonce="$(date -u +%Y%m%dT%H%M%SZ)-${CHUMMER_RUN_SERVICES_REVISION:0:12}-$$"
    presentation_rollback_ref="chummer-build-ghost-presentation:first-rollout-rollback-$nonce"
    ai_rollback_ref="chummer-build-ghost-ai:first-rollout-rollback-$nonce"
    edge_rollback_ref="chummer-build-ghost-private-edge:first-rollout-rollback-$nonce"
    for ref in "$presentation_rollback_ref" "$ai_rollback_ref" "$edge_rollback_ref"; do
        ! docker image inspect "$ref" >/dev/null 2>&1 || fail "rollback-reference-collision"
    done
    docker image tag "$old_presentation_image" "$presentation_rollback_ref"
    docker image tag "$old_ai_image" "$ai_rollback_ref"
    docker image tag "$old_edge_image" "$edge_rollback_ref"
    [ "$(image_id "$presentation_rollback_ref")" = "$old_presentation_image" ] \
        && [ "$(image_id "$ai_rollback_ref")" = "$old_ai_image" ] \
        && [ "$(image_id "$edge_rollback_ref")" = "$old_edge_image" ] \
        || fail "rollback-reference-verification"
}

terminate_build() {
    [ -n "$build_pid" ] || return 0
    if kill -0 "$build_pid" 2>/dev/null; then
        kill -TERM -- "-$build_pid" 2>/dev/null || true
        wait "$build_pid" 2>/dev/null || true
    fi
    build_pid=""
}

build_under_limits() {
    local started now status
    started="$(date +%s)"
    setsid bash -c 'exec "$@"' rook-first-rollout-build \
        docker compose --project-name "$project_name" --project-directory "$repo_root" \
        --file "$compose_file" build "$presentation_service" "$ai_service" \
        > "$deploy_tmp/build.log" 2>&1 &
    build_pid="$!"
    while kill -0 "$build_pid" 2>/dev/null; do
        host_limits_ok || { terminate_build; fail "candidate-build-host-cutoff"; }
        now="$(date +%s)"
        [ "$((now - started))" -le "$build_timeout_seconds" ] \
            || { terminate_build; fail "candidate-build-timeout"; }
        sleep "$poll_seconds"
    done
    set +e
    wait "$build_pid"
    status="$?"
    set -e
    build_pid=""
    [ "$status" -eq 0 ] || fail "candidate-build-failed"
    candidate_presentation_image="$(image_id "$presentation_image")"
    candidate_ai_image="$(image_id "$ai_image")"
    [ "$candidate_presentation_image" != "$old_presentation_image" ] \
        || fail "presentation-candidate-image-unchanged"
    [ "$candidate_ai_image" != "$old_ai_image" ] || fail "ai-candidate-image-unchanged"
    verify_candidate_source_labels
}

verify_preactivation_authority() {
    validate_sources_and_authoritative_hub
    ensure_host_limits
    [ "$(running_container_id "$presentation_service")" = "$old_presentation_id" ] \
        && [ "$(running_container_id "$ai_service")" = "$old_ai_id" ] \
        && [ "$(running_container_id "$edge_service")" = "$old_edge_id" ] \
        || fail "preactivation-container-drift"
    [ "$(docker inspect "$old_presentation_id" --format '{{.Image}}')" = "$old_presentation_image" ] \
        && [ "$(docker inspect "$old_ai_id" --format '{{.Image}}')" = "$old_ai_image" ] \
        && [ "$(docker inspect "$old_edge_id" --format '{{.Image}}')" = "$old_edge_image" ] \
        || fail "preactivation-image-drift"
    [ "$(volume_for_mount "$old_presentation_id" /app/state)" = "$old_packet_volume" ] \
        && [ "$(volume_for_mount "$old_edge_id" /data)" = "$old_caddy_data_volume" ] \
        && [ "$(volume_for_mount "$old_edge_id" /config)" = "$old_caddy_config_volume" ] \
        && [ "$(volume_for_mount "$old_ai_id" /caddy-trust)" = "$old_caddy_trust_volume" ] \
        || fail "preactivation-volume-drift"
    ! docker volume inspect "$live_volume" >/dev/null 2>&1 \
        || fail "preactivation-live-support-volume-not-new"
}

wait_for_health() {
    local service="$1" container health
    container="$(running_container_id "$service")"
    for _ in $(seq 1 90); do
        health="$(docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}')"
        [ "$health" = healthy ] && return 0
        [ "$health" != unhealthy ] || return 1
        sleep 2
        container="$(running_container_id "$service")"
    done
    return 1
}

assert_provider_disabled_runtime() {
    local ai_id environment variable
    ai_id="$(running_container_id "$ai_service")"
    environment="$(docker inspect "$ai_id" --format '{{range .Config.Env}}{{println .}}{{end}}')"
    for variable in \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED \
        CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED; do
        [ "$(printf '%s\n' "$environment" | awk -v expected="$variable=false" '$0==expected{n++} END{print n+0}')" -eq 1 ] \
            || fail "postcheck-provider-gate-$variable"
    done
    for variable in "${required_empty_provider_variables[@]}" "${required_literal_empty_live_variables[@]}"; do
        [ "$(printf '%s\n' "$environment" | awk -v expected="$variable=" '$0==expected{n++} END{print n+0}')" -eq 1 ] \
            || fail "postcheck-provider-input-$variable"
    done
}

verify_live_volume_and_initializer() {
    local ai_id init_id
    docker volume inspect "$live_volume" --format '{{json .Labels}}' \
        | jq -e --arg project "$project_name" \
            '.["com.docker.compose.project"]==$project and .["com.docker.compose.volume"]=="build-ghost-live-support"' \
            >/dev/null || fail "postcheck-live-support-volume-labels"
    ai_id="$(running_container_id "$ai_service")"
    [ "$(volume_for_mount "$ai_id" /app/state/build-ghost-live-support)" = "$live_volume" ] \
        || fail "postcheck-live-support-volume-mount"
    init_id="$(docker ps -a --no-trunc \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "label=com.docker.compose.service=$initializer_service" \
        --format '{{.ID}}')"
    [ "$(printf '%s\n' "$init_id" | sed '/^$/d' | wc -l)" -eq 1 ] \
        && [ "$(docker inspect "$init_id" --format '{{.State.ExitCode}}')" = 0 ] \
        || fail "postcheck-live-support-initializer"
    docker exec "$ai_id" sh -ec \
        'p=/app/state/build-ghost-live-support; [ -d "$p" ] && [ ! -L "$p" ] && [ "$(stat -c "%a:%u" "$p")" = "700:$(id -u)" ]' \
        >/dev/null || fail "postcheck-live-support-store-authority"
}

verify_postactivation() {
    local presentation_id ai_id edge_id
    presentation_id="$(running_container_id "$presentation_service")"
    ai_id="$(running_container_id "$ai_service")"
    edge_id="$(running_container_id "$edge_service")"
    [ "$(docker inspect "$presentation_id" --format '{{.Image}}')" = "$candidate_presentation_image" ] \
        && [ "$(docker inspect "$ai_id" --format '{{.Image}}')" = "$candidate_ai_image" ] \
        && [ "$(docker inspect "$edge_id" --format '{{.Image}}')" = "$old_edge_image" ] \
        || fail "postcheck-image-drift"
    wait_for_health "$presentation_service" || fail "postcheck-presentation-health"
    wait_for_health "$ai_service" || fail "postcheck-ai-health"
    assert_loopback_edge "$edge_id"
    [ "$(volume_for_mount "$presentation_id" /app/state)" = "$old_packet_volume" ] \
        && [ "$(volume_for_mount "$edge_id" /data)" = "$old_caddy_data_volume" ] \
        && [ "$(volume_for_mount "$edge_id" /config)" = "$old_caddy_config_volume" ] \
        && [ "$(volume_for_mount "$ai_id" /caddy-trust)" = "$old_caddy_trust_volume" ] \
        || fail "postcheck-existing-volume-drift"
    assert_provider_disabled_runtime
    verify_live_volume_and_initializer
}

run_exact_local_canary() {
    timeout --signal=TERM --kill-after=30 "$up_timeout_seconds" "$canary_script" \
        > "$deploy_tmp/canary.log" 2>&1 || fail "local-canary-failed"
    for required in 'positive_canary=passed' 'gates=false' 'rook=text-fallback' \
        'live_support=disabled' 'store=private'; do
        rg --fixed-strings "$required" "$deploy_tmp/canary.log" >/dev/null \
            || fail "local-canary-terminal-receipt-invalid"
    done
}

rollback_if_needed() {
    local restored_presentation restored_ai restored_edge
    [ "$activation_started" = true ] && [ "$deploy_succeeded" != true ] \
        && [ "$rollback_started" != true ] || return 0
    rollback_started="true"
    printf 'rook_first_rollout=rollback-started volumes=preserved\n' >&2
    [ "$(image_id "$presentation_rollback_ref" 2>/dev/null)" = "$old_presentation_image" ] \
        && [ "$(image_id "$ai_rollback_ref" 2>/dev/null)" = "$old_ai_image" ] \
        && [ "$(image_id "$edge_rollback_ref" 2>/dev/null)" = "$old_edge_image" ] \
        || return 1
    docker image tag "$presentation_rollback_ref" "$presentation_image"
    docker image tag "$ai_rollback_ref" "$ai_image"
    docker image tag "$edge_rollback_ref" "$edge_image"
    timeout --signal=TERM --kill-after=30 "$up_timeout_seconds" \
        docker compose --project-name "$project_name" --project-directory "$repo_root" \
        --file "$compose_file" up -d --no-deps --no-build --force-recreate \
        "$presentation_service" "$edge_service" "$ai_service" >/dev/null || return 1
    restored_presentation="$(running_container_id "$presentation_service")"
    restored_ai="$(running_container_id "$ai_service")"
    restored_edge="$(running_container_id "$edge_service")"
    [ "$(docker inspect "$restored_presentation" --format '{{.Image}}')" = "$old_presentation_image" ] \
        && [ "$(docker inspect "$restored_ai" --format '{{.Image}}')" = "$old_ai_image" ] \
        && [ "$(docker inspect "$restored_edge" --format '{{.Image}}')" = "$old_edge_image" ] \
        && wait_for_health "$presentation_service" \
        && wait_for_health "$ai_service" \
        && [ "$(volume_for_mount "$restored_presentation" /app/state)" = "$old_packet_volume" ] \
        && [ "$(volume_for_mount "$restored_edge" /data)" = "$old_caddy_data_volume" ] \
        && [ "$(volume_for_mount "$restored_edge" /config)" = "$old_caddy_config_volume" ] \
        || return 1
    assert_loopback_edge "$restored_edge"
    printf 'rook_first_rollout=rollback-restored volumes=preserved\n' >&2
}

restore_mutable_tags_after_failure() {
    [ "$deploy_succeeded" != true ] || return 0
    [ -z "$presentation_rollback_ref" ] || docker image tag "$presentation_rollback_ref" "$presentation_image"
    [ -z "$ai_rollback_ref" ] || docker image tag "$ai_rollback_ref" "$ai_image"
    [ -z "$edge_rollback_ref" ] || docker image tag "$edge_rollback_ref" "$edge_image"
}

validate_receipt_target() {
    local parent
    [ -n "$receipt_path" ] && [[ "$receipt_path" == /* ]] \
        || fail "receipt-path-required-and-absolute"
    parent="$(dirname -- "$receipt_path")"
    [ -d "$parent" ] && [ ! -L "$parent" ] \
        && [ "$(realpath -e -- "$parent")" = "$parent" ] \
        && [ "$(stat -c '%a:%u' "$parent")" = "700:$(id -u)" ] \
        || fail "receipt-directory-authority-invalid"
    [ ! -e "$receipt_path" ] && [ ! -L "$receipt_path" ] \
        || fail "receipt-path-must-be-new"
}

write_redacted_receipt() {
    local status="$1" outcome="$2" parent temp
    [ -n "$receipt_path" ] && [ "$receipt_written" != true ] || return 0
    [[ "$receipt_path" == /* ]] || return 1
    parent="$(dirname -- "$receipt_path")"
    [ -d "$parent" ] && [ ! -L "$parent" ] \
        && [ "$(stat -c '%a:%u' "$parent")" = "700:$(id -u)" ] \
        && [ ! -e "$receipt_path" ] && [ ! -L "$receipt_path" ] || return 1
    temp="$(mktemp --tmpdir="$parent" .rook-first-rollout-receipt.XXXXXXXXXXXX)" || return 1
    jq -n \
        --arg generated_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --arg status "$status" --arg outcome "$outcome" --arg stage "$failure_stage" \
        --arg hub "${CHUMMER_RUN_SERVICES_REVISION:-}" \
        --arg presentation "${CHUMMER_PRESENTATION_REVISION:-}" \
        --arg core "${CHUMMER_CORE_ENGINE_REVISION:-}" \
        --arg registry "${CHUMMER_HUB_REGISTRY_REVISION:-}" \
        --arg ui "${CHUMMER_UI_KIT_REVISION:-}" \
        --arg media "${CHUMMER_MEDIA_FACTORY_REVISION:-}" \
        --arg presentation_rollback "$presentation_rollback_ref" \
        --arg ai_rollback "$ai_rollback_ref" --arg edge_rollback "$edge_rollback_ref" \
        --arg live_volume "$live_volume" \
        '{contract_name:"chummer.build_ghost.first_provider_disabled_rook_rollout.v1",
          generated_at_utc:$generated_at_utc,status:$status,outcome:$outcome,stage:$stage,
          redacted:true,provider_execution_enabled:false,loopback_only:true,
          sources:{hub:$hub,presentation:$presentation,core:$core,hub_registry:$registry,ui_kit:$ui,media_factory:$media},
          rollback_refs:{presentation:$presentation_rollback,ai:$ai_rollback,edge:$edge_rollback},
          volumes:{live_support:$live_volume,deleted:false}}' > "$temp" || { unlink "$temp"; return 1; }
    chmod 0600 "$temp"
    ln -- "$temp" "$receipt_path" || { unlink "$temp"; return 1; }
    unlink "$temp"
    receipt_written="true"
}

securely_remove_temp() {
    local path
    [ -n "$deploy_tmp" ] && [ -d "$deploy_tmp" ] || return 0
    while IFS= read -r -d '' path; do
        chmod u+w "$path" 2>/dev/null || true
        shred --force --remove=unlink --zero "$path" 2>/dev/null || return 1
    done < <(find "$deploy_tmp" -mindepth 1 -maxdepth 1 -type f -print0)
    rmdir "$deploy_tmp"
}

on_exit() {
    local status="$?" outcome="failed"
    trap - EXIT HUP INT TERM
    terminate_build
    if ! (rollback_if_needed); then
        status=1
        outcome="rollback-failed-volumes-preserved"
    elif [ "$activation_started" = true ] && [ "$deploy_succeeded" != true ]; then
        outcome="rollback-restored-volumes-preserved"
    fi
    restore_mutable_tags_after_failure || status=1
    if [ "$deploy_succeeded" = true ]; then
        outcome="deployed-provider-disabled"
    fi
    write_redacted_receipt "$([ "$status" -eq 0 ] && printf passed || printf failed)" "$outcome" || status=1
    securely_remove_temp || status=1
    exit "$status"
}

main() {
    trap on_exit EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    for required in awk base64 bash chmod date df dirname docker find flock git id jq kill ln mktemp realpath rg rmdir sed seq setsid shred sleep stat timeout unlink wc; do
        require_command "$required"
    done
    validate_control_values
    validate_receipt_target
    [ -n "${CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK:-}" ] \
        || fail "compose-required-ingress-network-name-missing"
    docker network inspect "$CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK" >/dev/null 2>&1 \
        || fail "compose-required-ingress-network-unavailable"
    [ ! -L "$lane_lock" ] || fail "lane-lock-must-not-be-symlink"
    mkdir -p -- "$(dirname -- "$lane_lock")"
    exec {lane_lock_fd}>> "$lane_lock"
    chmod 0600 "$lane_lock"
    flock --nonblock "$lane_lock_fd" || fail "concurrent-private-lane-deploy"
    deploy_tmp="$(mktemp -d)"
    chmod 0700 "$deploy_tmp"
    validate_sources_and_authoritative_hub
    validate_external_secrets_without_output
    pin_provider_disabled_environment
    ensure_host_limits
    snapshot_runtime_authority
    verify_rendered_provider_disabled_compose
    create_rollback_refs
    build_under_limits
    verify_preactivation_authority
    activation_started="true"
    timeout --signal=TERM --kill-after=30 "$up_timeout_seconds" \
        docker compose --project-name "$project_name" --project-directory "$repo_root" \
        --file "$compose_file" up -d --no-build >/dev/null \
        || fail "full-lane-activation-failed"
    verify_postactivation
    run_exact_local_canary
    deploy_succeeded="true"
    failure_stage="none"
    printf 'rook_first_rollout=passed providers=disabled loopback=true canary=passed volumes_deleted=false rollback_refs=retained\n'
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
