#!/usr/bin/env bash
set -euo pipefail

# Local proof only: this runner never contacts public DNS or a voice provider.
project_name="chummer-build-ghost-private-nonprod"
loopback_port="${CHUMMER_BUILD_GHOST_PRIVATE_HTTPS_PORT:-8443}"
contract_digest="sha256:473a30bae8bfdff67ca6bd925e51a499c953b2def8000917f2f2b017ba01f14b"
owner_name="synthetic-build-ghost-canary"
cross_owner_name="synthetic-build-ghost-cross-owner"
canary_tmp="$(mktemp -d)"
chmod 0700 "$canary_tmp"

workspace_id=""
workspace_etag=""
workspace_closed="false"
grant_outstanding="false"
grant_pending_path=""
presentation_id=""

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'positive_canary=failed stage=preflight missing=%s\n' "$1"
        exit 1
    }
}

container_id() {
    local service_name="$1"
    local resolved
    resolved="$(docker ps \
        --filter "label=com.docker.compose.project=$project_name" \
        --filter "label=com.docker.compose.service=$service_name" \
        --filter status=running \
        --format '{{.ID}}')"
    if [ "$(printf '%s\n' "$resolved" | sed '/^$/d' | wc -l)" -ne 1 ]; then
        printf 'positive_canary=failed stage=preflight service=%s\n' "$service_name"
        exit 1
    fi
    printf '%s' "$resolved"
}

securely_remove_temp() {
    local path
    while IFS= read -r -d '' path; do
        chmod u+w "$path" 2>/dev/null || true
        shred --force --remove=unlink --zero "$path" 2>/dev/null || {
            truncate --size 0 "$path" 2>/dev/null || true
            unlink "$path" 2>/dev/null || true
        }
    done < <(find "$canary_tmp" -mindepth 1 -maxdepth 1 -type f -print0)
    rmdir "$canary_tmp" 2>/dev/null || true
}

close_workspace() {
    local close_status
    if [ "$workspace_closed" = "false" ] && [ -n "$workspace_id" ] && [ -n "$workspace_etag" ]; then
        close_status="$(curl --silent \
            --output "$canary_tmp/cleanup-response.json" \
            --write-out '%{http_code}' \
            --cacert "$canary_tmp/root.crt" \
            --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
            --request DELETE \
            --header "X-Chummer-Owner: $owner_name" \
            --header "If-Match: $workspace_etag" \
            "https://canary.chummer.run:${loopback_port}/api/workspaces/$workspace_id" || true)"
        [ "$close_status" = "200" ] && workspace_closed="true"
    fi
}

drain_grant() {
    if [ "$grant_outstanding" = "true" ] \
        && [ -n "$presentation_id" ] \
        && [ -f "$canary_tmp/root.crt" ] \
        && [ -f "$canary_tmp/tool-request.json" ] \
        && [ -f "$canary_tmp/tool-request-headers.txt" ]; then
        curl --silent \
            --output "$canary_tmp/drain-response.json" \
            --cacert "$canary_tmp/root.crt" \
            --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
            --header "@$canary_tmp/tool-request-headers.txt" \
            --data-binary "@$canary_tmp/tool-request.json" \
            "https://canary.chummer.run:${loopback_port}/api/v1/ai/build-ghost/tool" \
            >/dev/null 2>&1 || true
        if [ -n "$grant_pending_path" ] \
            && ! docker exec "$presentation_id" test -f "$grant_pending_path"; then
            grant_outstanding="false"
        fi
    fi
}

cleanup() {
    drain_grant
    close_workspace
    securely_remove_temp
}
trap cleanup EXIT

for required in base64 curl cut date docker find jq rg rmdir sed sha256sum shred tr truncate unlink wc; do
    require_command "$required"
done

edge_id="$(container_id build-ghost-private-edge)"
presentation_id="$(container_id chummer-build-ghost-presentation)"
ai_id="$(container_id chummer-build-ghost-ai)"

docker cp "$edge_id:/data/caddy/pki/authorities/local/root.crt" "$canary_tmp/root.crt" >/dev/null
chmod 0600 "$canary_tmp/root.crt"

fabricated_key="synthetic-unknown-packet-key-00000000000000000001"
fabricated_digest="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
jq -n \
    --arg key "$fabricated_key" \
    --arg digest "$fabricated_digest" \
    '{packet_access_key:$key,packet_digest:$digest,locale:"en-US",request_kind:"current-build"}' \
    > "$canary_tmp/fabricated-request.json"
jq '. + {unexpected_private_field:"blocked"}' "$canary_tmp/fabricated-request.json" \
    > "$canary_tmp/unknown-field-request.json"
{
    printf 'Content-Type: application/json\n'
    printf 'Authorization: Bearer %s\n' "$fabricated_key"
    printf 'X-Chummer-Build-Ghost-Tool-Contract: %s\n' "$contract_digest"
} > "$canary_tmp/fabricated-request-headers.txt"
sed "s/$contract_digest/sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/" \
    "$canary_tmp/fabricated-request-headers.txt" > "$canary_tmp/wrong-contract-headers.txt"
chmod 0600 "$canary_tmp/fabricated-request.json" "$canary_tmp/unknown-field-request.json" \
    "$canary_tmp/fabricated-request-headers.txt" "$canary_tmp/wrong-contract-headers.txt"

unknown_key_status="$(curl --silent --show-error \
    --output "$canary_tmp/unknown-key-response.json" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header "@$canary_tmp/fabricated-request-headers.txt" \
    --data-binary "@$canary_tmp/fabricated-request.json" \
    "https://canary.chummer.run:${loopback_port}/api/v1/ai/build-ghost/tool")"
wrong_contract_status="$(curl --silent --show-error \
    --output "$canary_tmp/wrong-contract-response.json" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header "@$canary_tmp/wrong-contract-headers.txt" \
    --data-binary "@$canary_tmp/fabricated-request.json" \
    "https://canary.chummer.run:${loopback_port}/api/v1/ai/build-ghost/tool")"
unknown_field_status="$(curl --silent --show-error \
    --output "$canary_tmp/unknown-field-response.json" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header "@$canary_tmp/fabricated-request-headers.txt" \
    --data-binary "@$canary_tmp/unknown-field-request.json" \
    "https://canary.chummer.run:${loopback_port}/api/v1/ai/build-ghost/tool")"
neighbor_status="$(curl --silent --show-error \
    --output "$canary_tmp/neighbor-response.json" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header 'Content-Type: application/json' \
    --header "Authorization: Bearer $fabricated_key" \
    --data '{}' \
    "https://canary.chummer.run:${loopback_port}/api/v1/ai/build-ghost/explain")"
presentation_neighbor_status="$(curl --silent --show-error \
    --output "$canary_tmp/presentation-neighbor-response.json" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "presentation.canary.chummer.run:${loopback_port}:127.0.0.1" \
    "https://presentation.canary.chummer.run:${loopback_port}/health/ready")"
if [ "$unknown_key_status" != "410" ] \
    || [ "$wrong_contract_status" != "401" ] \
    || [ "$unknown_field_status" != "400" ] \
    || [ "$neighbor_status" != "404" ] \
    || [ "$presentation_neighbor_status" != "404" ]; then
    printf 'positive_canary=failed stage=negative-boundaries unknown_key=%s wrong_contract=%s unknown_field=%s neighbor=%s presentation_neighbor=%s\n' \
        "$unknown_key_status" "$wrong_contract_status" "$unknown_field_status" "$neighbor_status" \
        "$presentation_neighbor_status"
    exit 1
fi

character_xml='<character><name>Synthetic Rook Canary</name><alias>Synthetic Rook Canary</alias><metatype>Human</metatype><buildmethod>Priority</buildmethod><createdversion>1.0</createdversion><appversion>1.0</appversion><karma>0</karma><nuyen>0</nuyen><created>True</created></character>'
content_base64="$(printf '%s' "$character_xml" | base64 -w0)"
jq -n \
    --arg content "$content_base64" \
    '{contentBase64:$content,format:"NativeXml",rulesetId:"SR5",schemaVersion:1,payloadKind:"workspace"}' \
    > "$canary_tmp/import-request.json"
chmod 0600 "$canary_tmp/import-request.json"

import_status="$(curl --silent --show-error \
    --output "$canary_tmp/import-response.json" \
    --dump-header "$canary_tmp/import-headers.txt" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header 'Content-Type: application/json' \
    --header "X-Chummer-Owner: $owner_name" \
    --data-binary "@$canary_tmp/import-request.json" \
    "https://canary.chummer.run:${loopback_port}/api/workspaces/import")"
if [ "$import_status" != "200" ]; then
    printf 'positive_canary=failed stage=import status=%s\n' "$import_status"
    exit 1
fi

workspace_id="$(jq -er '.id | select(type == "string" and length > 0)' "$canary_tmp/import-response.json")"
workspace_revision="$(jq -er '.contentRevision | select(type == "number")' "$canary_tmp/import-response.json")"
workspace_etag="$(sed -n 's/^[Ee][Tt][Aa][Gg]:[[:space:]]*\(.*\)\r$/\1/p' "$canary_tmp/import-headers.txt" | sed -n '1p')"
if [ -z "$workspace_etag" ]; then
    workspace_etag="\"rev-$workspace_revision\""
fi

cross_owner_status="$(curl --silent --show-error \
    --output "$canary_tmp/cross-owner-response.json" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header 'Content-Type: application/json' \
    --header "X-Chummer-Owner: $cross_owner_name" \
    --data '{"locale":"en-US","requestKind":"current-build"}' \
    "https://canary.chummer.run:${loopback_port}/api/workspaces/$workspace_id/build-ghost/tool-access")"
if [ "$cross_owner_status" != "503" ]; then
    printf 'positive_canary=failed stage=cross-owner status=%s expected=503\n' "$cross_owner_status"
    exit 1
fi

grant_status="$(curl --silent --show-error \
    --output "$canary_tmp/grant-response.json" \
    --dump-header "$canary_tmp/grant-response-headers.txt" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header 'Content-Type: application/json' \
    --header "X-Chummer-Owner: $owner_name" \
    --data '{"locale":"en-US","requestKind":"current-build"}' \
    "https://canary.chummer.run:${loopback_port}/api/workspaces/$workspace_id/build-ghost/tool-access")"
grant_cache_control="$(sed -n 's/^[Cc]ache-[Cc]ontrol:[[:space:]]*\(.*\)\r$/\1/p' "$canary_tmp/grant-response-headers.txt" | sed -n '1p')"
if [ "$grant_status" != "200" ] || [ "$grant_cache_control" != "no-store" ]; then
    printf 'positive_canary=failed stage=grant status=%s cache=%s cross_owner=%s\n' \
        "$grant_status" "$grant_cache_control" "$cross_owner_status"
    exit 1
fi

jq -er '.packetAccessKey | select(type == "string" and length >= 32)' "$canary_tmp/grant-response.json" \
    > "$canary_tmp/packet-key.txt"
jq -er '.packetDigest | select(test("^sha256:[0-9a-fA-F]{64}$"))' "$canary_tmp/grant-response.json" \
    > "$canary_tmp/packet-digest.txt"
jq -n \
    --rawfile key "$canary_tmp/packet-key.txt" \
    --rawfile digest "$canary_tmp/packet-digest.txt" \
    '{packet_access_key:($key|rtrimstr("\n")),packet_digest:($digest|rtrimstr("\n")),locale:"en-US",request_kind:"current-build",question:"Give one grounded, advisory build observation."}' \
    > "$canary_tmp/tool-request.json"
{
    printf 'Content-Type: application/json\n'
    printf 'Authorization: Bearer '
    tr -d '\n' < "$canary_tmp/packet-key.txt"
    printf '\nX-Chummer-Build-Ghost-Tool-Contract: %s\n' "$contract_digest"
} > "$canary_tmp/tool-request-headers.txt"
chmod 0600 "$canary_tmp/packet-key.txt" "$canary_tmp/packet-digest.txt" \
    "$canary_tmp/tool-request.json" "$canary_tmp/tool-request-headers.txt"
grant_pending_hash="$(tr -d '\n' < "$canary_tmp/packet-key.txt" | sha256sum | cut -d ' ' -f 1)"
grant_pending_path="/app/state/build-ghost-packet-access/pending/${grant_pending_hash}.json"
grant_outstanding="true"
expires_at="$(jq -er '.expiresAtUtc | select(type == "string" and length > 0)' "$canary_tmp/grant-response.json")"
expires_epoch="$(date -u --date "$expires_at" +%s)"
ttl_seconds="$((expires_epoch - $(date -u +%s)))"
if [ "$ttl_seconds" -le 0 ] || [ "$ttl_seconds" -gt 300 ]; then
    printf 'positive_canary=failed stage=grant-ttl ttl_seconds=%s\n' "$ttl_seconds"
    exit 1
fi

tool_status="$(curl --silent --show-error \
    --output "$canary_tmp/tool-response.json" \
    --dump-header "$canary_tmp/tool-response-headers.txt" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header "@$canary_tmp/tool-request-headers.txt" \
    --data-binary "@$canary_tmp/tool-request.json" \
    "https://canary.chummer.run:${loopback_port}/api/v1/ai/build-ghost/tool")"
if ! docker exec "$presentation_id" test -f "$grant_pending_path"; then
    grant_outstanding="false"
fi
if [ "$tool_status" != "200" ]; then
    printf 'positive_canary=failed stage=tool status=%s cross_owner=%s\n' "$tool_status" "$cross_owner_status"
    exit 1
fi

response_characters="$(LC_ALL=C.UTF-8 wc -m < "$canary_tmp/tool-response.json" | tr -d ' ')"
response_schema="$(jq -er '.schema' "$canary_tmp/tool-response.json")"
response_digest="$(jq -er '.packetDigest' "$canary_tmp/tool-response.json")"
response_locale="$(jq -er '.locale' "$canary_tmp/tool-response.json")"
packet_digest="$(tr -d '\n' < "$canary_tmp/packet-digest.txt")"
header_digest="$(sed -n 's/^[Xx]-[Cc]hummer-[Bb]uild-[Gg]host-[Pp]acket-[Dd]igest:[[:space:]]*\(.*\)\r$/\1/p' "$canary_tmp/tool-response-headers.txt" | sed -n '1p')"
cache_control="$(sed -n 's/^[Cc]ache-[Cc]ontrol:[[:space:]]*\(.*\)\r$/\1/p' "$canary_tmp/tool-response-headers.txt" | sed -n '1p')"
if [ "$response_schema" != "chummer.build_ghost_analysis.v1" ] \
    || [ "$response_digest" != "$packet_digest" ] \
    || [ "$header_digest" != "$packet_digest" ] \
    || [ "$response_locale" != "en-US" ] \
    || [ "$cache_control" != "no-store" ] \
    || [ "$response_characters" -gt 15000 ]; then
    printf 'positive_canary=failed stage=packet-validation status=%s characters=%s\n' "$tool_status" "$response_characters"
    exit 1
fi

forbidden_count="$(jq '[paths | map(tostring) | join(".") | select(test("rawxml|privatenotes|gmnotes|hiddenmembers|groupnotes"; "i"))] | length' "$canary_tmp/tool-response.json")"
if [ "$forbidden_count" != "0" ]; then
    printf 'positive_canary=failed stage=privacy forbidden_fields=%s\n' "$forbidden_count"
    exit 1
fi

replay_status="$(curl --silent --show-error \
    --output "$canary_tmp/replay-response.json" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header "@$canary_tmp/tool-request-headers.txt" \
    --data-binary "@$canary_tmp/tool-request.json" \
    "https://canary.chummer.run:${loopback_port}/api/v1/ai/build-ghost/tool")"
if [ "$replay_status" != "410" ]; then
    printf 'positive_canary=failed stage=replay status=%s\n' "$replay_status"
    exit 1
fi

presentation_leaks="$(docker logs "$presentation_id" 2>&1 | rg --fixed-strings --file "$canary_tmp/packet-key.txt" --count || true)"
ai_leaks="$(docker logs "$ai_id" 2>&1 | rg --fixed-strings --file "$canary_tmp/packet-key.txt" --count || true)"
pending_grants="$(docker exec "$presentation_id" sh -lc 'find /app/state/build-ghost-packet-access -type f 2>/dev/null | wc -l' | tr -d ' ')"
if [ "${presentation_leaks:-0}" != "0" ] || [ "${ai_leaks:-0}" != "0" ] || [ "$pending_grants" != "0" ]; then
    printf 'positive_canary=failed stage=secret-or-grant-cleanliness presentation_leaks=%s ai_leaks=%s pending=%s\n' \
        "${presentation_leaks:-0}" "${ai_leaks:-0}" "$pending_grants"
    exit 1
fi

for required_false in \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED \
    CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED; do
    if ! docker inspect "$ai_id" --format '{{range .Config.Env}}{{println .}}{{end}}' \
        | rg --fixed-strings --line-regexp "${required_false}=false" >/dev/null; then
        printf 'positive_canary=failed stage=provider-gates gate=%s\n' "$required_false"
        exit 1
    fi
done

close_workspace
if [ "$workspace_closed" != "true" ]; then
    printf 'positive_canary=failed stage=workspace-cleanup\n'
    exit 1
fi
closed_status="$(curl --silent --show-error \
    --output "$canary_tmp/closed-response.json" \
    --write-out '%{http_code}' \
    --cacert "$canary_tmp/root.crt" \
    --resolve "canary.chummer.run:${loopback_port}:127.0.0.1" \
    --header "X-Chummer-Owner: $owner_name" \
    "https://canary.chummer.run:${loopback_port}/api/workspaces/$workspace_id")"
if [ "$closed_status" != "404" ]; then
    printf 'positive_canary=failed stage=workspace-cleanup-verification status=%s\n' "$closed_status"
    exit 1
fi

printf 'positive_canary=passed unknown_key=%s wrong_contract=%s unknown_field=%s neighbor=%s presentation_neighbor=%s import=%s cross_owner=%s grant=%s grant_cache=%s tool=%s replay=%s schema=%s locale=%s characters=%s cache=%s ttl_seconds=%s pending_grants=%s gates=false cleanup=%s\n' \
    "$unknown_key_status" "$wrong_contract_status" "$unknown_field_status" "$neighbor_status" \
    "$presentation_neighbor_status" \
    "$import_status" "$cross_owner_status" "$grant_status" "$grant_cache_control" \
    "$tool_status" "$replay_status" \
    "$response_schema" "$response_locale" "$response_characters" "$cache_control" "$ttl_seconds" \
    "$pending_grants" "$closed_status"
