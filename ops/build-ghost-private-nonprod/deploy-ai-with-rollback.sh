#!/usr/bin/env bash
set -euo pipefail

# Bounded private-lane deployer. This script never deploys Presentation or edge,
# never enables a provider gate, and never deletes its immutable rollback tag.
umask 077

script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_root/../.." && pwd -P)"
compose_file="$repo_root/docker-compose.build-ghost-private-nonprod.yml"
project_name="chummer-build-ghost-private-nonprod"
ai_service="chummer-build-ghost-ai"
presentation_service="chummer-build-ghost-presentation"
edge_service="build-ghost-private-edge"
deployment_image="chummer-build-ghost-ai:private-nonprod"
rollback_repository="chummer-build-ghost-ai"
deploy_lock_file="/docker/chummercomplete/.state/locks/chummer-build-ghost-private-nonprod-ai-deploy.lock"
max_io_full_avg10="${CHUMMER_BUILD_GHOST_DEPLOY_MAX_IO_FULL_AVG10:-10}"
minimum_free_gib="${CHUMMER_BUILD_GHOST_DEPLOY_MINIMUM_FREE_GIB:-20}"
build_poll_seconds="${CHUMMER_BUILD_GHOST_DEPLOY_POLL_SECONDS:-10}"
workspace_revision="${CHUMMER_BUILD_GHOST_DEPLOY_CHECK_WORKSPACE_REVISION:-1}"

deploy_tmp=""
build_pid=""
activation_started="false"
deploy_succeeded="false"
rollback_started="false"
old_ai_id=""
old_ai_image=""
rollback_ref=""
presentation_id_before=""
edge_id_before=""
deploy_lock_fd=""

fail() {
    printf 'ai_deploy=failed stage=%s\n' "$1" >&2
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
    docker compose \
        --project-name "$project_name" \
        --project-directory "$repo_root" \
        --file "$compose_file" \
        "$@"
}

running_container_id() {
    local service_name="$1"
    local resolved
    resolved="$(docker ps --no-trunc \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "label=com.docker.compose.service=$service_name" \
        --filter status=running \
        --format '{{.ID}}')"
    if [ "$(printf '%s\n' "$resolved" | sed '/^$/d' | wc -l)" -ne 1 ]; then
        fail "runtime-$service_name-not-exactly-one"
    fi
    printf '%s' "$resolved"
}

ensure_hard_limits() {
    local io_full_avg10 free_kib minimum_free_kib
    io_full_avg10="$(awk '/^full / { for (index = 1; index <= NF; index++) if ($index ~ /^avg10=/) { split($index, pair, "="); print pair[2]; exit } }' /proc/pressure/io)"
    [ -n "$io_full_avg10" ] || fail "host-io-pressure-unreadable"
    if ! awk -v observed="$io_full_avg10" -v maximum="$max_io_full_avg10" 'BEGIN { exit !(observed <= maximum) }'; then
        fail "host-io-pressure-cutoff"
    fi

    free_kib="$(df -Pk /docker | awk 'NR == 2 { print $4 }')"
    minimum_free_kib="$((minimum_free_gib * 1024 * 1024))"
    [ -n "$free_kib" ] || fail "host-free-space-unreadable"
    if [ "$free_kib" -lt "$minimum_free_kib" ]; then
        fail "host-free-space-cutoff"
    fi
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
    [[ "$workspace_revision" =~ ^[1-9][0-9]*$ ]] || fail "workspace-revision-invalid"
}

validate_source() {
    local variable_name="$1"
    local revision_variable_name="${2:-}"
    local source_path expected_revision actual_revision dirty
    source_path="${!variable_name:-}"
    [ -n "$source_path" ] || fail "source-$variable_name-missing"
    [[ "$source_path" == /* ]] || fail "source-$variable_name-not-absolute"
    source_path="$(realpath -e -- "$source_path")"
    [ -d "$source_path/.git" ] || git -C "$source_path" rev-parse --git-dir >/dev/null 2>&1 \
        || fail "source-$variable_name-not-git"
    actual_revision="$(git -C "$source_path" rev-parse --verify HEAD)"
    [[ "$actual_revision" =~ ^[0-9a-f]{40}$ ]] || fail "source-$variable_name-head-invalid"
    dirty="$(git -C "$source_path" status --porcelain --untracked-files=all)"
    [ -z "$dirty" ] || fail "source-$variable_name-dirty"

    if [ -n "$revision_variable_name" ]; then
        expected_revision="${!revision_variable_name:-}"
        [[ "$expected_revision" =~ ^[0-9a-f]{40}$ ]] || fail "revision-$revision_variable_name-invalid"
        [ "$actual_revision" = "$expected_revision" ] || fail "source-$variable_name-revision-drift"
    fi

    printf -v "$variable_name" '%s' "$source_path"
    export "${variable_name?}"
}

validate_sources_and_labels() {
    validate_source CHUMMER_RUN_SERVICES_SOURCE CHUMMER_RUN_SERVICES_REVISION
    [ "$CHUMMER_RUN_SERVICES_SOURCE" = "$repo_root" ] || fail "hub-source-does-not-own-helper"
    validate_source CHUMMER_CORE_ENGINE_SOURCE CHUMMER_CORE_ENGINE_REVISION
    validate_source CHUMMER_HUB_REGISTRY_SOURCE CHUMMER_HUB_REGISTRY_REVISION
    validate_source CHUMMER_MEDIA_FACTORY_SOURCE CHUMMER_MEDIA_FACTORY_REVISION
    validate_source CHUMMER_PRESENTATION_SOURCE
    validate_source CHUMMER_UI_KIT_SOURCE
}

load_existing_environment() {
    local container_id="$1"
    local variable_name="$2"
    local required="$3"
    local environment line matches value
    environment="$(docker inspect "$container_id" --format '{{range .Config.Env}}{{println .}}{{end}}')"
    line="$(printf '%s\n' "$environment" | awk -v prefix="$variable_name=" 'index($0, prefix) == 1 { print }')"
    matches="$(printf '%s\n' "$environment" | awk -v prefix="$variable_name=" 'index($0, prefix) == 1 { count++ } END { print count + 0 }')"
    [ "$matches" -eq 1 ] || fail "runtime-env-$variable_name-not-exactly-one"
    value="${line#*=}"
    if [ "$required" = "required" ] && [ -z "$value" ]; then
        fail "runtime-env-$variable_name-empty"
    fi
    printf -v "$variable_name" '%s' "$value"
    export "${variable_name?}"
}

load_runtime_secrets_without_output() {
    load_existing_environment "$old_ai_id" CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN required
    load_existing_environment "$old_ai_id" CHUMMER_AI_INTERNAL_API_TOKEN required
    load_existing_environment "$old_ai_id" CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS optional
    load_existing_environment "$old_ai_id" CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS optional
    load_existing_environment "$old_ai_id" CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF optional
    load_existing_environment "$old_ai_id" CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID optional
    load_existing_environment "$old_ai_id" CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID optional
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
    [ "$(image_label "$image" org.opencontainers.image.revision)" = "$CHUMMER_RUN_SERVICES_REVISION" ] \
        || fail "image-hub-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.core-revision)" = "$CHUMMER_CORE_ENGINE_REVISION" ] \
        || fail "image-core-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.hub-registry-revision)" = "$CHUMMER_HUB_REGISTRY_REVISION" ] \
        || fail "image-registry-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.media-factory-revision)" = "$CHUMMER_MEDIA_FACTORY_REVISION" ] \
        || fail "image-media-label-drift"
    [ "$(image_label "$image" run.chummer.build-ghost.profile)" = "private-nonprod" ] \
        || fail "image-profile-label-drift"
}

preserve_rollback_image() {
    local timestamp nonce old_short preserved_id
    old_ai_id="$(running_container_id "$ai_service")"
    old_ai_image="$(docker inspect "$old_ai_id" --format '{{.Image}}')"
    [[ "$old_ai_image" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "old-ai-image-id-invalid"
    [ "$(image_id "$old_ai_image")" = "$old_ai_image" ] || fail "old-ai-image-unresolvable"
    assert_provider_gates_false "$old_ai_id"

    timestamp="$(date -u +%Y%m%dt%H%M%Sz)"
    nonce="$(openssl rand -hex 12)"
    old_short="${old_ai_image#sha256:}"
    rollback_ref="$rollback_repository:rollback-${timestamp}-${old_short:0:16}-${nonce}"
    if docker image inspect "$rollback_ref" >/dev/null 2>&1; then
        fail "rollback-reference-collision"
    fi
    docker image tag "$old_ai_image" "$rollback_ref"
    preserved_id="$(image_id "$rollback_ref")"
    [ "$preserved_id" = "$old_ai_image" ] || fail "rollback-reference-verification-failed"
    printf 'ai_deploy=prepared rollback_ref=%s old_image=%s\n' "$rollback_ref" "$old_ai_image"
}

verify_rendered_compose() {
    local rendered="$deploy_tmp/compose.rendered.json"
    compose config --format json > "$rendered"
    chmod 0600 "$rendered"
    jq -e \
        --arg service "$ai_service" \
        --arg hub "$CHUMMER_RUN_SERVICES_REVISION" \
        --arg core "$CHUMMER_CORE_ENGINE_REVISION" \
        --arg registry "$CHUMMER_HUB_REGISTRY_REVISION" \
        --arg media "$CHUMMER_MEDIA_FACTORY_REVISION" \
        '.services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED == "false"
         and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED == "false"
         and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED == "false"
         and .services[$service].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED == "false"
         and .services[$service].build.args.CHUMMER_RUN_SERVICES_REVISION == $hub
         and .services[$service].build.args.CHUMMER_CORE_ENGINE_REVISION == $core
         and .services[$service].build.args.CHUMMER_HUB_REGISTRY_REVISION == $registry
         and .services[$service].build.args.CHUMMER_MEDIA_FACTORY_REVISION == $media
         and ((.services[$service].ports // []) | length == 0)' \
        "$rendered" >/dev/null || fail "compose-render-drift"
    if rg --fixed-strings '/api/v1/ai/build-ghost/explain' \
        "$script_root/Caddyfile" >/dev/null; then
        fail "public-explain-route-present"
    fi
}

build_candidate_under_limits() {
    local build_status
    ensure_hard_limits
    setsid bash -c 'exec "$@"' deploy-build \
        docker compose \
        --project-name "$project_name" \
        --project-directory "$repo_root" \
        --file "$compose_file" \
        build "$ai_service" \
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
    ensure_hard_limits
    verify_source_labels "$deployment_image"
}

assert_provider_gates_false() {
    local container_id="$1"
    local environment required_false
    environment="$(docker inspect "$container_id" --format '{{range .Config.Env}}{{println .}}{{end}}')"
    for required_false in \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED; do
        [ "$(printf '%s\n' "$environment" | awk -v expected="$required_false=false" '$0 == expected { count++ } END { print count + 0 }')" -eq 1 ] \
            || fail "postcheck-provider-gate-$required_false"
    done
}

wait_for_ai_health() {
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
                http://127.0.0.1:8080/api/health >/dev/null; then
            return 0
        fi
        [ "$health" != "unhealthy" ] || return 1
        sleep 2
    done
    return 1
}

create_grounded_request() {
    local request_id="$1"
    local packet_file="$deploy_tmp/analysis-packet.json"
    local request_file="$deploy_tmp/explain-request.json"
    local requested_at packet_digest owner_scope_hash idempotency_key fallback_text
    requested_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    fallback_text="Deterministic private Rook deployment check."
    idempotency_key="deploy:$request_id:$workspace_revision"
    owner_scope_hash="sha256:$(printf '%s' "$project_name:$request_id" | sha256sum | cut -d ' ' -f 1)"

    jq -cS -n \
        --arg schema 'chummer.build_ghost_analysis.v1' \
        --arg persona 'build-ghost-rook-v1' \
        --arg avatar 'build-ghost-rook-avatar-v1' \
        --arg voice 'build-ghost-rook-voice-v1' \
        --arg locale 'en-US' \
        --argjson revision "$workspace_revision" \
        '{schema:$schema,personaId:$persona,avatarId:$avatar,voiceId:$voice,packetDigest:"",locale:$locale,
          supportedLocales:[$locale],localeFallbackChain:[$locale],workspaceId:"synthetic-deploy-postcheck",
          workspaceRevision:$revision,runner:{facts:[]},optimizationStrategies:[],ruleExplanations:[],variants:[],
          groupCapabilityPosture:{visibilityPosture:"hidden",visibleMembers:[]},sourceAnchors:[],allowedSuggestedActions:[]}' \
        > "$packet_file"
    packet_digest="sha256:$(printf '%s' "$(< "$packet_file")" | sha256sum | cut -d ' ' -f 1)"
    jq -cS --arg digest "$packet_digest" '.packetDigest = $digest' "$packet_file" \
        > "$deploy_tmp/analysis-packet.bound.json"
    mv "$deploy_tmp/analysis-packet.bound.json" "$packet_file"
    [ "$(jq -er '.workspaceRevision' "$packet_file")" = "$workspace_revision" ] \
        || fail "grounded-request-workspace-revision-drift"
    [ "$(jq -er '.packetDigest' "$packet_file")" = "$packet_digest" ] \
        || fail "grounded-request-packet-digest-drift"

    jq -cS -n \
        --arg schema 'chummer.tough_tongue.build_ghost_request.v1' \
        --arg request_id "$request_id" \
        --arg owner_scope_hash "$owner_scope_hash" \
        --arg packet_digest "$packet_digest" \
        --arg locale 'en-US' \
        --rawfile packet "$packet_file" \
        --arg fallback "$fallback_text" \
        --arg idempotency_key "$idempotency_key" \
        --arg requested_at "$requested_at" \
        '{schema:$schema,requestId:$request_id,ownerScopeHash:$owner_scope_hash,packetDigest:$packet_digest,
          locale:$locale,analysisPacketJson:($packet|rtrimstr("\n")),deterministicFallbackText:$fallback,
          idempotencyKey:$idempotency_key,requestedAtUtc:$requested_at}' \
        > "$request_file"
    chmod 0600 "$packet_file" "$request_file"
}

verify_authenticated_fallback() {
    local container_id="$1"
    local request_id response status invalid_status missing_status packet_digest fallback_text
    request_id="deploy-check-$(date -u +%Y%m%dt%H%M%Sz)-$(openssl rand -hex 8)"
    create_grounded_request "$request_id"
    packet_digest="$(jq -er '.packetDigest' "$deploy_tmp/explain-request.json")"
    fallback_text="$(jq -er '.deterministicFallbackText' "$deploy_tmp/explain-request.json")"

    response="$({ printf 'Authorization: Bearer %s\n' "$CHUMMER_AI_INTERNAL_API_TOKEN"; } \
        | docker exec -i "$container_id" curl --silent --show-error --max-time 15 \
            --output - --write-out '\n%{http_code}' \
            --header @- --header 'Content-Type: application/json' \
            --data-binary "$(< "$deploy_tmp/explain-request.json")" \
            http://127.0.0.1:8080/api/v1/ai/build-ghost/explain)"
    status="${response##*$'\n'}"
    printf '%s' "${response%$'\n'*}" > "$deploy_tmp/explain-response.json"
    [ "$status" = "200" ] || fail "postcheck-authenticated-explain-status"
    jq -e \
        --arg request_id "$request_id" \
        --arg packet_digest "$packet_digest" \
        --arg fallback "$fallback_text" \
        '.usedDeterministicFallback == true
         and .safeText == $fallback
         and .receipt.requestId == $request_id
         and .receipt.packetDigest == $packet_digest
         and .receipt.remoteExecutionEnabled == false
         and .receipt.remoteAttempted == false
         and .receipt.fallbackReason == "remote-disabled"
         and (.receipt.validationReasons | index("remote-execution-disabled-by-default") != null)' \
        "$deploy_tmp/explain-response.json" >/dev/null \
        || fail "postcheck-grounded-fallback-binding"

    missing_status="$(docker exec "$container_id" curl --silent --show-error --max-time 15 \
        --output /dev/null --write-out '%{http_code}' \
        --header 'Content-Type: application/json' \
        --data-binary "$(< "$deploy_tmp/explain-request.json")" \
        http://127.0.0.1:8080/api/v1/ai/build-ghost/explain)"
    [ "$missing_status" = "401" ] || fail "postcheck-missing-auth-not-unauthorized"

    invalid_status="$({ printf 'Authorization: Bearer invalid-deploy-check-%s\n' "$request_id"; } \
        | docker exec -i "$container_id" curl --silent --show-error --max-time 15 \
            --output /dev/null --write-out '%{http_code}' \
            --header @- --header 'Content-Type: application/json' \
            --data-binary "$(< "$deploy_tmp/explain-request.json")" \
            http://127.0.0.1:8080/api/v1/ai/build-ghost/explain)"
    [ "$invalid_status" = "401" ] || fail "postcheck-invalid-auth-not-unauthorized"
}

verify_public_explain_absent() {
    local edge_id="$1"
    local binding host_ip host_port status
    binding="$(docker inspect "$edge_id" --format '{{with (index .NetworkSettings.Ports "443/tcp")}}{{with (index . 0)}}{{.HostIp}}:{{.HostPort}}{{end}}{{end}}')"
    host_ip="${binding%:*}"
    host_port="${binding##*:}"
    [ "$host_ip" = "127.0.0.1" ] || fail "postcheck-edge-not-loopback-only"
    [[ "$host_port" =~ ^[0-9]+$ ]] || fail "postcheck-edge-port-invalid"
    docker cp "$edge_id:/data/caddy/pki/authorities/local/root.crt" \
        "$deploy_tmp/root.crt" >/dev/null
    chmod 0600 "$deploy_tmp/root.crt"
    status="$(curl --silent --show-error --max-time 15 \
        --output /dev/null --write-out '%{http_code}' \
        --cacert "$deploy_tmp/root.crt" \
        --resolve "canary.chummer.run:$host_port:$host_ip" \
        --request POST --header 'Content-Type: application/json' --data '{}' \
        "https://canary.chummer.run:$host_port/api/v1/ai/build-ghost/explain")"
    [ "$status" = "404" ] || fail "postcheck-public-explain-not-404"
}

run_postchecks() {
    local current_ai_id current_ai_image
    current_ai_id="$(running_container_id "$ai_service")"
    [ "$current_ai_id" != "$old_ai_id" ] || fail "postcheck-ai-container-not-recreated"
    current_ai_image="$(docker inspect "$current_ai_id" --format '{{.Image}}')"
    [ "$current_ai_image" = "$(image_id "$deployment_image")" ] \
        || fail "postcheck-ai-image-not-candidate"
    verify_source_labels "$current_ai_image"
    wait_for_ai_health "$current_ai_id" || fail "postcheck-ai-health"
    assert_provider_gates_false "$current_ai_id"
    [ "$(running_container_id "$presentation_service")" = "$presentation_id_before" ] \
        || fail "postcheck-presentation-container-changed"
    [ "$(running_container_id "$edge_service")" = "$edge_id_before" ] \
        || fail "postcheck-edge-container-changed"
    verify_authenticated_fallback "$current_ai_id"
    verify_public_explain_absent "$edge_id_before"
}

verify_activation_authority_unchanged() {
    local current_ai_id current_ai_image
    [ "$(image_id "$rollback_ref")" = "$old_ai_image" ] \
        || fail "preactivation-rollback-reference-drift"
    current_ai_id="$(running_container_id "$ai_service")"
    [ "$current_ai_id" = "$old_ai_id" ] \
        || fail "preactivation-ai-container-drift"
    current_ai_image="$(docker inspect "$current_ai_id" --format '{{.Image}}')"
    [ "$current_ai_image" = "$old_ai_image" ] \
        || fail "preactivation-ai-image-drift"
    [ "$(running_container_id "$presentation_service")" = "$presentation_id_before" ] \
        || fail "preactivation-presentation-container-drift"
    [ "$(running_container_id "$edge_service")" = "$edge_id_before" ] \
        || fail "preactivation-edge-container-drift"
}

rollback_if_needed() {
    local restored_ai_id restored_image
    if [ "$activation_started" != "true" ] || [ "$deploy_succeeded" = "true" ] \
        || [ "$rollback_started" = "true" ]; then
        return 0
    fi
    rollback_started="true"
    printf 'ai_deploy=rollback-started rollback_ref=%s\n' "$rollback_ref" >&2
    set +e
    if [ -z "$rollback_ref" ] \
        || [ "$(image_id "$rollback_ref" 2>/dev/null)" != "$old_ai_image" ]; then
        printf 'ai_deploy=rollback-failed stage=preserved-image-unavailable\n' >&2
        return 1
    fi
    docker image tag "$rollback_ref" "$deployment_image"
    if [ "$(image_id "$deployment_image" 2>/dev/null)" != "$old_ai_image" ]; then
        printf 'ai_deploy=rollback-failed stage=deployment-retag-verification\n' >&2
        return 1
    fi
    compose up -d --no-deps --no-build --force-recreate "$ai_service"
    restored_ai_id="$(running_container_id "$ai_service")"
    restored_image="$(docker inspect "$restored_ai_id" --format '{{.Image}}')"
    if [ "$restored_image" != "$old_ai_image" ] \
        || ! wait_for_ai_health "$restored_ai_id" rollback-verification \
        || [ "$(running_container_id "$presentation_service")" != "$presentation_id_before" ] \
        || [ "$(running_container_id "$edge_service")" != "$edge_id_before" ]; then
        printf 'ai_deploy=rollback-failed stage=runtime-verification\n' >&2
        return 1
    fi
    printf 'ai_deploy=rollback-restored rollback_ref=%s image=%s\n' "$rollback_ref" "$old_ai_image" >&2
    return 0
}

on_exit() {
    local status="$?"
    trap - EXIT HUP INT TERM
    terminate_build
    if ! (rollback_if_needed); then
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
    for required in awk bash cut date df docker find git jq mv openssl realpath rg rmdir sed seq setsid sha256sum shred sleep truncate unlink wc; do
        require_command "$required"
    done
    validate_control_values
    deploy_tmp="$(mktemp -d)"
    chmod 0700 "$deploy_tmp"
    validate_sources_and_labels
    ensure_hard_limits

    presentation_id_before="$(running_container_id "$presentation_service")"
    edge_id_before="$(running_container_id "$edge_service")"
    preserve_rollback_image
    load_runtime_secrets_without_output
    ensure_hard_limits
    verify_rendered_compose
    build_candidate_under_limits
    ensure_hard_limits
    verify_activation_authority_unchanged

    activation_started="true"
    compose up -d --no-deps --no-build --force-recreate "$ai_service"
    run_postchecks
    deploy_succeeded="true"
    printf 'ai_deploy=passed rollback_ref=%s old_image=%s candidate_image=%s gates=false neighbors=unchanged public_explain=404 deterministic_fallback=true remote_attempted=false\n' \
        "$rollback_ref" "$old_ai_image" "$(image_id "$deployment_image")"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
