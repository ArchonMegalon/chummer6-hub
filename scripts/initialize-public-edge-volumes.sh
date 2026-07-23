#!/bin/sh
set -eu

fail() {
  printf '%s\n' "public-edge volume initialization failed: $*" >&2
  exit 1
}

validate_numeric_identity() {
  label="$1"
  value="$2"
  case "$value" in
    ''|*[!0-9]*)
      fail "$label must be a positive numeric id"
      ;;
  esac
  [ "$value" -gt 0 ] || fail "$label must not be root"
  [ "$value" -le 2147483647 ] || fail "$label is outside the supported range"
}

require_mount_root() {
  root="$1"
  [ -d "$root" ] || fail "$root is not a mounted directory"
  [ ! -L "$root" ] || fail "$root must not be a symbolic link"
}

probe_as_portal_identity() {
  root="$1"
  # The single-quoted program is expanded by the deliberately isolated child shell.
  # shellcheck disable=SC2016
  setpriv \
    --reuid="$portal_uid" \
    --regid="$portal_gid" \
    --clear-groups \
    /bin/sh -eu -c '
      expected_uid="$1"
      expected_gid="$2"
      root="$3"
      probe="$root/.chummer-volume-probe.$$"
      created=0
      cleanup() {
        if [ "$created" -eq 1 ]; then
          rm -f -- "$probe/write-test"
          rmdir -- "$probe" 2>/dev/null || true
        fi
      }
      trap cleanup EXIT
      trap "exit 1" HUP INT TERM

      [ "$(id -u)" = "$expected_uid" ] || exit 1
      [ "$(id -g)" = "$expected_gid" ] || exit 1
      mkdir -m 700 -- "$probe"
      created=1
      (umask 077 && : > "$probe/write-test")
      rm -f -- "$probe/write-test"
      rmdir -- "$probe"
      created=0
      trap - EXIT HUP INT TERM
    ' volume-probe "$portal_uid" "$portal_gid" "$root" \
    || fail "$root is not writable as ${portal_uid}:${portal_gid}"
}

verify_tree_as_portal_identity() {
  root="$1"
  # The single-quoted program is expanded by the deliberately isolated child shell.
  # shellcheck disable=SC2016
  setpriv \
    --reuid="$portal_uid" \
    --regid="$portal_gid" \
    --clear-groups \
    /bin/sh -eu -c '
      expected_uid="$1"
      expected_gid="$2"
      root="$3"
      mismatched="$(find -P "$root" -xdev \( ! -uid "$expected_uid" -o ! -gid "$expected_gid" \) -print -quit)"
      [ -z "$mismatched" ] || {
        printf "%s\n" "$mismatched did not migrate to ${expected_uid}:${expected_gid}" >&2
        exit 1
      }
    ' ownership-verifier "$portal_uid" "$portal_gid" "$root" \
    || fail "cannot verify ownership below $root as ${portal_uid}:${portal_gid}"
}

migrate_mutable_root() {
  root="$1"
  require_mount_root "$root"

  # Take physical directories top-down so a legacy owner-only tree can be traversed
  # without DAC_OVERRIDE. -P and -xdev prevent traversal through links or submounts.
  chown 0:0 -- "$root" || fail "cannot take ownership of $root"
  find -P "$root" -xdev -type d -exec chown 0:0 -- {} \; \
    || fail "cannot traverse physical directories below $root"

  unsafe_entry="$(find -P "$root" -xdev ! -type d ! -type f -print -quit)" \
    || fail "cannot inspect $root"
  [ -z "$unsafe_entry" ] || fail "$root contains unsupported entry: $unsafe_entry"

  find -P "$root" -xdev -depth -exec chown -- "${portal_uid}:${portal_gid}" {} + \
    || fail "cannot migrate ownership below $root"
  # The migrated root may be mode 0700. Verify as its new owner instead of
  # broadening the initializer with DAC_OVERRIDE or DAC_READ_SEARCH.
  verify_tree_as_portal_identity "$root"

  probe_as_portal_identity "$root"
}

ensure_private_directory_as_portal_identity() {
  directory="$1"
  case "$directory" in
    /app/state/*) ;;
    *) fail "$directory is outside the mutable application-state root" ;;
  esac

  # Core's store-backed delegated GM edit boundary deliberately refuses to
  # create its state root. Provision and verify that root as the same non-root
  # identity that runs the portal, after the volume ownership migration.
  # shellcheck disable=SC2016
  setpriv \
    --reuid="$portal_uid" \
    --regid="$portal_gid" \
    --clear-groups \
    /bin/sh -eu -c '
      expected_uid="$1"
      expected_gid="$2"
      directory="$3"
      [ ! -L "$directory" ] || exit 1
      if [ -e "$directory" ]; then
        [ -d "$directory" ] || exit 1
      else
        mkdir -m 700 -- "$directory"
      fi
      chmod 700 -- "$directory"
      [ "$(stat -c %u -- "$directory")" = "$expected_uid" ] || exit 1
      [ "$(stat -c %g -- "$directory")" = "$expected_gid" ] || exit 1
      [ "$(stat -c %a -- "$directory")" = "700" ] || exit 1
    ' private-directory-provisioner "$portal_uid" "$portal_gid" "$directory" \
    || fail "$directory cannot be provisioned for ${portal_uid}:${portal_gid}"

  probe_as_portal_identity "$directory"
}

validate_sha256() {
  label="$1"
  value="$2"
  case "$value" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
    *) fail "$label must be a lowercase SHA-256" ;;
  esac
}

require_regular_input() {
  path="$1"
  label="$2"
  [ -f "$path" ] || fail "$label is not a regular file"
  [ ! -L "$path" ] || fail "$label must not be a symbolic link"
  [ "$(stat -c %h -- "$path")" = "1" ] || fail "$label must have one link"
}

file_sha256() {
  sha256sum -- "$1" | awk '{ print $1 }'
}

# sha256-file-tree-v1: the SHA-256 of the byte stream produced by GNU
# sha256sum for every physical regular file, sorted by its ./relative path.
# Modes are deliberately excluded because copied runtime inputs are normalized.
tree_sha256() {
  root="$1"
  require_mount_root "$root"
  unsafe_entry="$(find -P "$root" -xdev ! -type d ! -type f -print -quit)" \
    || fail "cannot inspect immutable tree $root"
  [ -z "$unsafe_entry" ] || fail "$root contains unsupported entry: $unsafe_entry"
  (
    cd "$root"
    find -P . -xdev -type f -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 -r sha256sum --
  ) | sha256sum | awk '{ print $1 }'
}

verify_tree_sha256() {
  root="$1"
  expected="$2"
  label="$3"
  observed="$(tree_sha256 "$root")" \
    || fail "$label tree digest could not be computed"
  [ "$observed" = "$expected" ] || fail "$label tree digest drifted"
}

verify_file_sha256() {
  path="$1"
  expected="$2"
  label="$3"
  require_regular_input "$path" "$label"
  observed="$(file_sha256 "$path")" \
    || fail "$label digest could not be computed"
  [ "$observed" = "$expected" ] || fail "$label digest drifted"
}

json_safe_string_values() {
  path="$1"
  key="$2"
  grep -Eo \
    "\"${key}\"[[:space:]]*:[[:space:]]*\"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\"" \
    "$path" \
    | sed -E 's/^[^:]+:[[:space:]]*"([^"]+)"$/\1/' \
    | LC_ALL=C sort -u
}

require_single_json_safe_string() {
  path="$1"
  key="$2"
  label="$3"
  values="$(json_safe_string_values "$path" "$key")" \
    || fail "$label could not be inspected"
  [ -n "$values" ] || fail "$label omits $key"
  [ "$(printf '%s\n' "$values" | wc -l)" -eq 1 ] \
    || fail "$label has conflicting $key values"
  printf '%s\n' "$values"
}

require_active_release_shelf() {
  root="$1"
  require_mount_root "$root"
  for required_file in \
    .release-shelf-layout-v1 \
    .release-shelf-writer-policy.json \
    current.json \
    RELEASE_CHANNEL.generated.json \
    releases.json
  do
    require_regular_input "$root/$required_file" \
      "active release shelf $required_file"
  done
  [ "$(stat -c %s -- "$root/current.json")" -le 65536 ] \
    || fail "active release shelf current.json is oversized"
  printf 'v1\n' | cmp -s - "$root/.release-shelf-layout-v1" \
    || fail "active release shelf layout marker bytes drifted"
  grep -Eq \
    '"schemaVersion"[[:space:]]*:[[:space:]]*"chummer.release-shelf.writer-policy/v1"' \
    "$root/.release-shelf-writer-policy.json" \
    || fail "active release shelf writer-policy schema drifted"
  grep -Eq \
    '"mode"[[:space:]]*:[[:space:]]*"server-journal-v1"' \
    "$root/.release-shelf-writer-policy.json" \
    || fail "active release shelf writer-policy mode drifted"
  grep -Eq \
    '"schemaVersion"[[:space:]]*:[[:space:]]*"chummer.release-shelf.current/v1"' \
    "$root/current.json" \
    || fail "active release shelf current schema drifted"

  generation_id="$(
    require_single_json_safe_string \
      "$root/current.json" \
      generationId \
      "active release shelf current.json"
  )"
  receipt_id="$(
    require_single_json_safe_string \
      "$root/current.json" \
      activationReceiptId \
      "active release shelf current.json"
  )"
  generation_root="$root/generations/$generation_id"
  receipt_root="$root/.release-shelf-activation-journal/$receipt_id"
  [ -d "$generation_root" ] && [ ! -L "$generation_root" ] \
    || fail "active release shelf current generation is unavailable"
  [ -d "$receipt_root" ] && [ ! -L "$receipt_root" ] \
    || fail "active release shelf committed receipt is unavailable"
  for required_file in \
    activation-candidate.json \
    RELEASE_CHANNEL.generated.json \
    releases.json
  do
    require_regular_input "$generation_root/$required_file" \
      "active generation $required_file"
  done
  require_regular_input "$receipt_root/intent.json" \
    "active release shelf activation intent"
  require_regular_input "$receipt_root/outcome.json" \
    "active release shelf activation outcome"

  intent_generation="$(
    require_single_json_safe_string \
      "$receipt_root/intent.json" \
      generationId \
      "active release shelf activation intent"
  )"
  intent_receipt="$(
    require_single_json_safe_string \
      "$receipt_root/intent.json" \
      activationReceiptId \
      "active release shelf activation intent"
  )"
  outcome_receipt="$(
    require_single_json_safe_string \
      "$receipt_root/outcome.json" \
      activationReceiptId \
      "active release shelf activation outcome"
  )"
  [ "$intent_generation" = "$generation_id" ] \
    || fail "active release shelf intent generation disagrees with current.json"
  [ "$intent_receipt" = "$receipt_id" ] \
    || fail "active release shelf intent receipt disagrees with current.json"
  [ "$outcome_receipt" = "$receipt_id" ] \
    || fail "active release shelf outcome receipt disagrees with current.json"
  grep -Eq '"state"[[:space:]]*:[[:space:]]*"committed"' \
    "$receipt_root/outcome.json" \
    || fail "active release shelf receipt is not committed"

  target_pointer_values="$(
    grep -Eo \
      '"targetPointerBase64"[[:space:]]*:[[:space:]]*"[A-Za-z0-9+/=]+"' \
      "$receipt_root/intent.json" \
      | sed -E 's/^[^:]+:[[:space:]]*"([^"]+)"$/\1/' \
      | LC_ALL=C sort -u
  )" || fail "active release shelf target pointer could not be inspected"
  [ -n "$target_pointer_values" ] \
    || fail "active release shelf intent omits target pointer authority"
  [ "$(printf '%s\n' "$target_pointer_values" | wc -l)" -eq 1 ] \
    || fail "active release shelf intent has conflicting target pointers"
  printf '%s' "$target_pointer_values" \
    | base64 -d \
    | cmp -s - "$root/current.json" \
    || fail "active release shelf receipt does not bind current.json bytes"
}

reset_runtime_input_root() {
  root="$1"
  require_mount_root "$root"
  unsafe_entry="$(find -P "$root" -xdev ! -type d ! -type f -print -quit)" \
    || fail "cannot inspect isolated runtime-input volume $root"
  [ -z "$unsafe_entry" ] \
    || fail "$root contains unsupported pre-existing entry: $unsafe_entry"
  find -P "$root" -xdev -exec chown 0:0 -- {} + \
    || fail "cannot take ownership below $root"
  find -P "$root" -xdev -type d -exec chmod 0700 -- {} + \
    || fail "cannot make $root writable for initialization"
  find -P "$root" -xdev -mindepth 1 -depth -delete \
    || fail "cannot reset isolated runtime-input volume $root"
}

copy_immutable_tree() {
  source="$1"
  destination="$2"
  expected="$3"
  label="$4"
  verify_tree_sha256 "$source" "$expected" "$label source"
  reset_runtime_input_root "$destination"
  cp -a -- "$source/." "$destination/" \
    || fail "cannot copy $label into its isolated volume"
  unsafe_entry="$(find -P "$destination" -xdev ! -type d ! -type f -print -quit)" \
    || fail "cannot inspect copied $label"
  [ -z "$unsafe_entry" ] || fail "copied $label contains unsupported entry: $unsafe_entry"
  chown -R 0:0 -- "$destination" || fail "cannot seal copied $label ownership"
  find -P "$destination" -xdev -type f -exec chmod 0444 -- {} + \
    || fail "cannot seal copied $label files"
  find -P "$destination" -xdev -type d -exec chmod 0555 -- {} + \
    || fail "cannot seal copied $label directories"
  verify_tree_sha256 "$destination" "$expected" "$label copy"
}

copy_isolated_release_shelf() {
  source="$1"
  destination="$2"
  expected="$3"
  require_active_release_shelf "$source"
  verify_tree_sha256 "$source" "$expected" "active release shelf source"
  reset_runtime_input_root "$destination"
  cp -a -- "$source/." "$destination/" \
    || fail "cannot copy the active release shelf"
  unsafe_entry="$(find -P "$destination" -xdev ! -type d ! -type f -print -quit)" \
    || fail "cannot inspect the copied release shelf"
  [ -z "$unsafe_entry" ] \
    || fail "copied release shelf contains unsupported entry: $unsafe_entry"
  require_active_release_shelf "$destination"
  chown -R 0:0 -- "$destination" \
    || fail "cannot seal copied release shelf ownership"
  find -P "$destination" -xdev -type f -exec chmod 0444 -- {} + \
    || fail "cannot seal copied release shelf files"
  find -P "$destination" -xdev -type d -exec chmod 0555 -- {} + \
    || fail "cannot seal copied release shelf directories"
  require_active_release_shelf "$destination"
  verify_tree_sha256 "$destination" "$expected" "copied release shelf"
}

copy_runtime_proofs() {
  destination="$1"
  runtime_source="$2"
  runtime_expected="$3"
  gold_source="$4"
  gold_expected="$5"
  verify_file_sha256 "$runtime_source" "$runtime_expected" "runtime proof"
  verify_file_sha256 "$gold_source" "$gold_expected" "final-gold handoff"
  reset_runtime_input_root "$destination"
  cp -- "$runtime_source" "$destination/HUB_LOCAL_RELEASE_PROOF.generated.json" \
    || fail "cannot copy runtime proof"
  cp -- "$gold_source" "$destination/FINAL_GOLD_JANITOR.generated.json" \
    || fail "cannot copy final-gold handoff"
  chown -R 0:0 -- "$destination" || fail "cannot seal runtime proofs ownership"
  chmod 0444 -- "$destination/HUB_LOCAL_RELEASE_PROOF.generated.json" \
    "$destination/FINAL_GOLD_JANITOR.generated.json" \
    || fail "cannot seal runtime proof files"
  chmod 0555 -- "$destination" || fail "cannot seal runtime proof directory"
  verify_file_sha256 \
    "$destination/HUB_LOCAL_RELEASE_PROOF.generated.json" \
    "$runtime_expected" \
    "copied runtime proof"
  verify_file_sha256 \
    "$destination/FINAL_GOLD_JANITOR.generated.json" \
    "$gold_expected" \
    "copied final-gold handoff"
}

copy_runtime_secrets() {
  destination="$1"
  certificate_source="$2"
  certificate_expected="$3"
  password_source="$4"
  password_expected="$5"
  verify_file_sha256 "$certificate_source" "$certificate_expected" "certificate"
  verify_file_sha256 "$password_source" "$password_expected" "certificate password"
  reset_runtime_input_root "$destination"
  cp -- "$certificate_source" \
    "$destination/data-protection-key-encryption.pfx" \
    || fail "cannot copy certificate"
  cp -- "$password_source" \
    "$destination/data-protection-key-encryption.password" \
    || fail "cannot copy certificate password"
  chmod 0700 -- "$destination" || fail "cannot protect runtime-secret directory"
  chmod 0400 -- \
    "$destination/data-protection-key-encryption.pfx" \
    "$destination/data-protection-key-encryption.password" \
    || fail "cannot protect runtime-secret files"
  chown -R -- "${portal_uid}:${portal_gid}" "$destination" \
    || fail "cannot assign runtime-secret ownership"
  verify_file_sha256 \
    "$destination/data-protection-key-encryption.pfx" \
    "$certificate_expected" \
    "copied certificate"
  verify_file_sha256 \
    "$destination/data-protection-key-encryption.password" \
    "$password_expected" \
    "copied certificate password"
}

verify_tree_as_runtime_identity() {
  root="$1"
  label="$2"
  setpriv \
    --reuid="$portal_uid" \
    --regid="$portal_gid" \
    --clear-groups \
    /bin/sh -eu -c '
      root="$1"
      find -P "$root" -xdev -exec /bin/sh -eu -c '\''
        for entry do
          if [ -d "$entry" ]; then
            [ -r "$entry" ] && [ -x "$entry" ] || exit 1
          elif [ -f "$entry" ]; then
            [ -r "$entry" ] || exit 1
          else
            exit 1
          fi
        done
      '\'' runtime-tree-entry {} +
    ' runtime-tree "$root" \
    || fail "$label is not fully readable as the exact portal identity"
}

verify_secret_identity_boundary() {
  secret_root="$1"
  setpriv \
    --reuid="$portal_uid" \
    --regid="$portal_gid" \
    --clear-groups \
    /bin/sh -eu -c '
      expected_uid="$1"
      expected_gid="$2"
      root="$3"
      [ "$(id -u)" = "$expected_uid" ]
      [ "$(id -g)" = "$expected_gid" ]
      [ "$(id -G)" = "$expected_gid" ]
      test -r "$root/data-protection-key-encryption.pfx"
      test -r "$root/data-protection-key-encryption.password"
      test "$(stat -c %u:%g:%a -- "$root")" = "$expected_uid:$expected_gid:700"
      test "$(stat -c %u:%g:%a -- "$root/data-protection-key-encryption.pfx")" = "$expected_uid:$expected_gid:400"
      test "$(stat -c %u:%g:%a -- "$root/data-protection-key-encryption.password")" = "$expected_uid:$expected_gid:400"
    ' runtime-secret-reader "$portal_uid" "$portal_gid" "$secret_root" \
    || fail "runtime secrets are not exact-owner readable by the portal"

  unrelated_uid=65534
  unrelated_gid=65534
  if [ "$unrelated_uid" = "$portal_uid" ]; then
    unrelated_uid=65533
  fi
  if [ "$unrelated_gid" = "$portal_gid" ]; then
    unrelated_gid=65533
  fi
  setpriv \
    --reuid="$unrelated_uid" \
    --regid="$unrelated_gid" \
    --clear-groups \
    /bin/sh -eu -c '
      root="$1"
      ! test -r "$root/data-protection-key-encryption.pfx"
      ! test -r "$root/data-protection-key-encryption.password"
    ' unrelated-secret-reader "$secret_root" \
    || fail "runtime secrets are readable by an unrelated identity"
}

run_public_download_initializer() {
  certificate_sha="${CHUMMER_DATA_PROTECTION_CERTIFICATE_SHA256-}"
  password_sha="${CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_SHA256-}"
  app_sha="${CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256-}"
  fleet_sha="${CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256-}"
  shelf_sha="${CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256-}"
  projection_sha="${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256-}"
  runtime_proof_sha="${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256-}"
  final_gold_sha="${CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256-}"
  validate_sha256 CHUMMER_DATA_PROTECTION_CERTIFICATE_SHA256 "$certificate_sha"
  validate_sha256 CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_SHA256 "$password_sha"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256 "$app_sha"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256 "$fleet_sha"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256 "$shelf_sha"
  validate_sha256 CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256 "$projection_sha"
  validate_sha256 CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256 "$runtime_proof_sha"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256 "$final_gold_sha"

  for mutable_root in \
    /app/state \
    /release-upload-sessions \
    /windows-proof-store \
    /windows-proof-upload-sessions
  do
    migrate_mutable_root "$mutable_root"
    setpriv \
      --reuid="$portal_uid" \
      --regid="$portal_gid" \
      --clear-groups \
      chmod 0700 -- "$mutable_root" \
      || fail "cannot protect isolated mutable root $mutable_root"
  done
  ensure_private_directory_as_portal_identity /app/state/core-workspaces
  ensure_private_directory_as_portal_identity /app/state/data-protection-keys-v2

  verify_tree_sha256 /runtime-inputs/app "$app_sha" "app overlay"
  verify_tree_sha256 /runtime-inputs/fleet "$fleet_sha" "fleet/static"
  copy_isolated_release_shelf \
    /runtime-inputs/shelf \
    /downloads-source \
    "$shelf_sha"
  copy_immutable_tree \
    /runtime-inputs/projection \
    /public-projection-staging \
    "$projection_sha" \
    "public projection"
  copy_runtime_proofs \
    /proofs-staging \
    /runtime-inputs/HUB_LOCAL_RELEASE_PROOF.generated.json \
    "$runtime_proof_sha" \
    /runtime-inputs/FINAL_GOLD_JANITOR.generated.json \
    "$final_gold_sha"
  copy_runtime_secrets \
    /run/chummer-secrets \
    /runtime-inputs/data-protection-key-encryption.pfx \
    "$certificate_sha" \
    /runtime-inputs/data-protection-key-encryption.password \
    "$password_sha"

  verify_tree_as_runtime_identity /runtime-inputs/app "app overlay"
  verify_tree_as_runtime_identity /runtime-inputs/fleet "fleet/static"
  verify_tree_as_runtime_identity /downloads-source "isolated release shelf"
  verify_tree_as_runtime_identity /public-projection-staging "copied projection"
  verify_tree_as_runtime_identity /proofs-staging "copied runtime proofs"
  verify_secret_identity_boundary /run/chummer-secrets
  printf '%s\n' \
    "public-download runtime inputs verified for ${portal_uid}:${portal_gid}"
}

portal_uid="${CHUMMER_PORTAL_UID:-1654}"
portal_gid="${CHUMMER_PORTAL_GID:-1654}"
validate_numeric_identity CHUMMER_PORTAL_UID "$portal_uid"
validate_numeric_identity CHUMMER_PORTAL_GID "$portal_gid"
command -v setpriv >/dev/null 2>&1 || fail "setpriv is unavailable in the portal image"

umask 077
if [ "${CHUMMER_PUBLIC_DOWNLOAD_RUNTIME_INIT:-false}" = "true" ]; then
  run_public_download_initializer
else
  for mutable_root in \
    /app/state \
    /release-upload-sessions \
    /windows-proof-store \
    /windows-proof-upload-sessions
  do
    migrate_mutable_root "$mutable_root"
  done

  ensure_private_directory_as_portal_identity /app/state/core-workspaces
  ensure_private_directory_as_portal_identity /app/state/data-protection-keys-v2

  # /downloads-source is a host bind and remains operator-owned. Prove access as the
  # portal identity, but never change its ownership or modes from inside the container.
  require_mount_root /downloads-source
  probe_as_portal_identity /downloads-source

  printf '%s\n' "public-edge mutable roots verified for ${portal_uid}:${portal_gid}"
fi
