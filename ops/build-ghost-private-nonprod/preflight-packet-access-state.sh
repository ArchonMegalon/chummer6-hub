#!/bin/sh
set -eu

# Read-only structural admission gate for the private packet-access volume.
# The application remains the keyed-MAC authority; this gate only prevents a
# known unkeyed/v1 or ambiguous store from reaching the activation boundary.
store_root="${1:-}"

fail() {
    printf 'packet_store_preflight=failed stage=%s\n' "$1" >&2
    exit 1
}

[ -n "$store_root" ] || fail "store-root-missing"
[ -d "$store_root" ] || fail "store-root-not-directory"
[ ! -L "$store_root" ] || fail "store-root-symlink"

if [ "$(find "$store_root" -type l | wc -l | tr -d ' ')" -ne 0 ]; then
    fail "store-symlink-present"
fi

for directory in pending claims audit revocations; do
    if [ -e "$store_root/$directory" ] && [ ! -d "$store_root/$directory" ]; then
        fail "state-directory-invalid"
    fi
done

legacy_consumed_path="$store_root/consumed"
if [ -e "$legacy_consumed_path" ] || [ -L "$legacy_consumed_path" ]; then
    [ -d "$legacy_consumed_path" ] || fail "legacy-consumed-directory-invalid"
    [ ! -L "$legacy_consumed_path" ] || fail "legacy-consumed-directory-invalid"
    legacy_consumed_entries="$(find "$legacy_consumed_path" -mindepth 1 -maxdepth 1 \
        | wc -l | tr -d ' ')"
    [ "$legacy_consumed_entries" -eq 0 ] || fail "legacy-consumed-state-not-empty"
fi

unknown_root_entries="$(find "$store_root" -mindepth 1 -maxdepth 1 \
    ! -name pending ! -name claims ! -name audit ! -name revocations \
    ! -name consumed ! -name .operation.lock ! -name state-authority.v2.json \
    | wc -l | tr -d ' ')"
[ "$unknown_root_entries" -eq 0 ] || fail "unknown-root-state"

for directory in pending claims audit revocations; do
    [ -d "$store_root/$directory" ] || continue
    unknown_entries="$(find "$store_root/$directory" -mindepth 1 -maxdepth 1 \
        ! -type f -o -type f ! -name '*.json' | wc -l | tr -d ' ')"
    [ "$unknown_entries" -eq 0 ] || fail "unknown-lifecycle-state"
done

pending_count="$(find "$store_root/pending" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
claims_count="$(find "$store_root/claims" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
audit_count="$(find "$store_root/audit" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
revocation_count="$(find "$store_root/revocations" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
state_count="$((pending_count + claims_count + audit_count + revocation_count))"
authority_path="$store_root/state-authority.v2.json"

if [ ! -e "$authority_path" ] && [ ! -L "$authority_path" ]; then
    [ "$state_count" -eq 0 ] || fail "nonempty-unkeyed-state"
    printf 'packet_store_preflight=passed state=empty\n'
    exit 0
fi

[ -f "$authority_path" ] || fail "authority-not-regular-file"
[ ! -L "$authority_path" ] || fail "authority-symlink"
grep -Eq '"schema"[[:space:]]*:[[:space:]]*"chummer\.build_ghost\.packet_access_store_authority\.v2"' \
    "$authority_path" || fail "authority-not-v2"

validate_schema_set() {
    directory="$1"
    expected_schema="$2"
    [ -d "$store_root/$directory" ] || return 0
    invalid_count="$(find "$store_root/$directory" -maxdepth 1 -type f -name '*.json' \
        -exec grep -EL '"schema"[[:space:]]*:[[:space:]]*"'"$expected_schema"'"' {} + \
        | wc -l | tr -d ' ')"
    [ "$invalid_count" -eq 0 ] || fail "lifecycle-state-not-v2"
}

validate_schema_set pending 'chummer\.build_ghost\.packet_access_pending\.v2'
validate_schema_set claims 'chummer\.build_ghost\.packet_access_pending\.v2'
validate_schema_set audit 'chummer\.build_ghost\.packet_access_audit\.v2'
validate_schema_set revocations 'chummer\.build_ghost\.workspace_revocation\.v2'

printf 'packet_store_preflight=passed state=keyed-v2\n'
