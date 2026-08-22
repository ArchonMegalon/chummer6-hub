#!/usr/bin/env bash
set -euo pipefail

# Bounded private-lane deployer. This script changes only Presentation, keeps
# every provider gate false, and never deletes its immutable rollback image.
umask 077

script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_root/../.." && pwd -P)"
compose_file="$repo_root/docker-compose.build-ghost-private-nonprod.yml"
packet_preflight="$script_root/preflight-packet-access-state.sh"
canary_script="$script_root/run-local-canary.sh"
project_name="chummer-build-ghost-private-nonprod"
presentation_service="chummer-build-ghost-presentation"
ai_service="chummer-build-ghost-ai"
edge_service="build-ghost-private-edge"
deployment_image="chummer-build-ghost-presentation:private-nonprod"
rollback_repository="chummer-build-ghost-presentation"
# Deliberately shared with the AI helper so the two private-lane activations
# cannot overlap even though the historical filename names the AI lane.
deploy_lock_file="/docker/chummercomplete/.state/locks/chummer-build-ghost-private-nonprod-ai-deploy.lock"
max_io_full_avg10="${CHUMMER_BUILD_GHOST_DEPLOY_MAX_IO_FULL_AVG10:-10}"
minimum_free_gib="${CHUMMER_BUILD_GHOST_DEPLOY_MINIMUM_FREE_GIB:-20}"
build_poll_seconds="${CHUMMER_BUILD_GHOST_DEPLOY_POLL_SECONDS:-10}"

deploy_tmp=""
build_pid=""
candidate_built="false"
activation_started="false"
deploy_succeeded="false"
rollback_started="false"
old_presentation_id=""
old_presentation_image=""
rollback_ref=""
ai_id_before=""
edge_id_before=""
deploy_lock_fd=""

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
    for variable_name in \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID \
        CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID; do
        read_existing_environment "$ai_id_before" "$variable_name" optional "$variable_name"
        export "${variable_name?}"
    done
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
            || fail "provider-gate-$required_false"
    done
}

preserve_rollback_image() {
    local timestamp nonce old_short preserved_id
    old_presentation_id="$(running_container_id "$presentation_service")"
    old_presentation_image="$(docker inspect "$old_presentation_id" --format '{{.Image}}')"
    [[ "$old_presentation_image" =~ ^sha256:[0-9a-f]{64}$ ]] \
        || fail "old-presentation-image-id-invalid"
    [ "$(image_id "$old_presentation_image")" = "$old_presentation_image" ] \
        || fail "old-presentation-image-unresolvable"

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
    printf 'presentation_deploy=prepared rollback_ref=%s old_image=%s\n' \
        "$rollback_ref" "$old_presentation_image"
}

preflight_packet_store() {
    local container_id="$1"
    local result
    result="$(docker exec -i "$container_id" sh -s -- \
        /app/state/build-ghost-packet-access < "$packet_preflight")" \
        || fail "packet-store-preflight"
    case "$result" in
        'packet_store_preflight=passed state=empty'|'packet_store_preflight=passed state=keyed-v2') ;;
        *) fail "packet-store-preflight-ambiguous" ;;
    esac
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
         and .services[$ai].environment.CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED == "false"' \
        "$rendered" >/dev/null || fail "compose-render-drift"
    if rg --fixed-strings '/api/v1/ai/build-ghost/explain' "$script_root/Caddyfile" >/dev/null; then
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
        '{packetAccessKey:$key,packetDigest:$digest,locale:"en-US",requestKind:"current-build"}' \
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
    if ! "$canary_script" > "$deploy_tmp/lifecycle-canary.log" 2>&1; then
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
    current_presentation_id="$(running_container_id "$presentation_service")"
    [ "$current_presentation_id" = "$old_presentation_id" ] \
        || fail "preactivation-presentation-container-drift"
    current_presentation_image="$(docker inspect "$current_presentation_id" --format '{{.Image}}')"
    [ "$current_presentation_image" = "$old_presentation_image" ] \
        || fail "preactivation-presentation-image-drift"
    [ "$(running_container_id "$ai_service")" = "$ai_id_before" ] \
        || fail "preactivation-ai-container-drift"
    [ "$(running_container_id "$edge_service")" = "$edge_id_before" ] \
        || fail "preactivation-edge-container-drift"
    assert_provider_gates_false "$ai_id_before"
    preflight_packet_store "$old_presentation_id"
}

run_postchecks() {
    local current_presentation_id current_presentation_image
    current_presentation_id="$(running_container_id "$presentation_service")"
    [ "$current_presentation_id" != "$old_presentation_id" ] \
        || fail "postcheck-presentation-container-not-recreated"
    current_presentation_image="$(docker inspect "$current_presentation_id" --format '{{.Image}}')"
    [ "$current_presentation_image" = "$(image_id "$deployment_image")" ] \
        || fail "postcheck-presentation-image-not-candidate"
    verify_source_labels "$current_presentation_image"
    wait_for_presentation_health "$current_presentation_id" || fail "postcheck-presentation-health"
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
}

rollback_if_needed() {
    local restored_presentation_id restored_image
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
        return 1
    fi
    docker image tag "$rollback_ref" "$deployment_image"
    if [ "$(image_id "$deployment_image" 2>/dev/null)" != "$old_presentation_image" ]; then
        printf 'presentation_deploy=rollback-failed stage=deployment-retag-verification\n' >&2
        return 1
    fi
    compose up -d --no-deps --no-build --force-recreate "$presentation_service"
    restored_presentation_id="$(running_container_id "$presentation_service")"
    restored_image="$(docker inspect "$restored_presentation_id" --format '{{.Image}}')"
    if [ "$restored_image" != "$old_presentation_image" ] \
        || ! wait_for_presentation_health "$restored_presentation_id" rollback-verification \
        || [ "$(running_container_id "$ai_service")" != "$ai_id_before" ] \
        || [ "$(running_container_id "$edge_service")" != "$edge_id_before" ]; then
        printf 'presentation_deploy=rollback-failed stage=runtime-verification\n' >&2
        return 1
    fi
    printf 'presentation_deploy=rollback-restored rollback_ref=%s image=%s\n' \
        "$rollback_ref" "$old_presentation_image" >&2
    return 0
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
    for required in awk bash curl cut date df docker find git jq mktemp mv openssl realpath rg rmdir sed seq setsid shred sleep truncate unlink wc; do
        require_command "$required"
    done
    [ -x "$packet_preflight" ] || fail "packet-store-preflight-not-executable"
    [ -x "$canary_script" ] || fail "lifecycle-canary-not-executable"
    validate_control_values
    deploy_tmp="$(mktemp -d)"
    chmod 0700 "$deploy_tmp"
    validate_sources_and_labels
    ensure_hard_limits

    ai_id_before="$(running_container_id "$ai_service")"
    edge_id_before="$(running_container_id "$edge_service")"
    assert_provider_gates_false "$ai_id_before"
    preserve_rollback_image
    preflight_packet_store "$old_presentation_id"
    load_runtime_environment_without_output
    verify_rendered_compose
    build_candidate_under_limits
    ensure_hard_limits
    verify_activation_authority_unchanged

    activation_started="true"
    compose up -d --no-deps --no-build --force-recreate "$presentation_service"
    run_postchecks
    deploy_succeeded="true"
    printf 'presentation_deploy=passed rollback_ref=%s old_image=%s candidate_image=%s sources=exact packet_store=keyed-v2 auth=401 lifecycle=one-use-replay-revocation gates=false neighbors=unchanged public_explain=404\n' \
        "$rollback_ref" "$old_presentation_image" "$(image_id "$deployment_image")"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
