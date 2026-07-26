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
  [ "${#value}" -eq 64 ] || fail "$label must be a lowercase SHA-256"
  case "$value" in
    *[!0123456789abcdef]*) fail "$label must be a lowercase SHA-256" ;;
  esac
}

validate_projection_snapshot_id() {
  value="$1"
  case "$value" in
    public-projection-*)
      digest="${value#public-projection-}"
      ;;
    *)
      fail "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ID is invalid"
      ;;
  esac
  validate_sha256 CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ID "$digest"
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
  printf 'v1\n' \
    | cmp -s - "$root/.release-shelf-layout-v1" \
    || fail "active release shelf layout marker bytes drifted"
  grep -Eq \
    '"schemaVersion"[[:space:]]*:[[:space:]]*"chummer.release-shelf.writer-policy/v1"' \
    "$root/.release-shelf-writer-policy.json" \
    || fail "active release shelf writer-policy schema drifted"
  grep -Eq \
    '"mode"[[:space:]]*:[[:space:]]*"sidecar-readonly-v1"' \
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
  generation_root="$root/generations/$generation_id"
  [ -d "$generation_root" ] && [ ! -L "$generation_root" ] \
    || fail "active release shelf current generation is unavailable"
  for required_file in \
    activation-candidate.json \
    RELEASE_CHANNEL.generated.json \
    releases.json
  do
    require_regular_input "$generation_root/$required_file" \
      "active generation $required_file"
  done
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
  cp -R --no-preserve=mode,ownership,timestamps -- "$source/." "$destination/" \
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

require_candidate_projection_snapshot() {
  root="$1"
  label="$2"
  require_mount_root "$root"
  [ "$(stat -c %a -- "$root")" = "555" ] \
    || fail "$label directory mode drifted"

  expected_inventory="$(
    printf '%s\n' \
      FLAGSHIP_PRODUCT_READINESS.generated.json \
      HUB_LOCAL_RELEASE_PROOF.generated.json \
      HUB_SERVED_RELEASE_PROOF.generated.json \
      LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json \
      NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json \
      NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json \
      PUBLIC_PROJECTION_SNAPSHOT.generated.json \
      RELEASE_CHANNEL.generated.json \
      RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json \
      | LC_ALL=C sort
  )"
  observed_inventory="$(
    find -P "$root" -xdev -mindepth 1 -maxdepth 1 -printf '%f\n' \
      | LC_ALL=C sort
  )" || fail "$label inventory could not be inspected"
  [ "$observed_inventory" = "$expected_inventory" ] \
    || fail "$label inventory drifted"
  nested_entry="$(find -P "$root" -xdev -mindepth 2 -print -quit)" \
    || fail "$label nested inventory could not be inspected"
  [ -z "$nested_entry" ] || fail "$label contains nested or extra material"

  for name in \
    FLAGSHIP_PRODUCT_READINESS.generated.json \
    HUB_LOCAL_RELEASE_PROOF.generated.json \
    HUB_SERVED_RELEASE_PROOF.generated.json \
    LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json \
    NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json \
    NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json \
    PUBLIC_PROJECTION_SNAPSHOT.generated.json \
    RELEASE_CHANNEL.generated.json \
    RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json
  do
    require_regular_input "$root/$name" "$label $name"
    [ "$(stat -c %a -- "$root/$name")" = "644" ] \
      || fail "$label $name mode drifted"
  done
}

copy_candidate_projection_authority() {
  source="$1"
  destination="$2"
  snapshot_id="$3"
  current_expected="$4"
  snapshot_tree_expected="$5"

  require_mount_root "$source"
  current_source="$source/CURRENT.json"
  snapshot_source="$source/$snapshot_id"
  require_regular_input "$current_source" "public projection CURRENT"
  [ "$(stat -c %a -- "$current_source")" = "644" ] \
    || fail "public projection CURRENT mode drifted"
  verify_file_sha256 \
    "$current_source" \
    "$current_expected" \
    "public projection CURRENT"
  require_candidate_projection_snapshot \
    "$snapshot_source" \
    "public projection snapshot"
  verify_tree_sha256 \
    "$snapshot_source" \
    "$snapshot_tree_expected" \
    "public projection snapshot"

  reset_runtime_input_root "$destination"
  snapshot_stage="$destination/.projection-snapshot-stage.$$"
  current_stage="$destination/.CURRENT.json.$$"
  if [ -e "$snapshot_stage" ] || [ -L "$snapshot_stage" ]; then
    fail "public projection snapshot stage already exists"
  fi
  if [ -e "$current_stage" ] || [ -L "$current_stage" ]; then
    fail "public projection CURRENT stage already exists"
  fi
  mkdir -m 0700 -- "$snapshot_stage" \
    || fail "cannot create public projection snapshot stage"
  cp -R \
    --preserve=mode \
    --no-preserve=ownership,timestamps \
    -- "$snapshot_source/." "$snapshot_stage/" \
    || fail "cannot stage the public projection snapshot"
  chown -R 0:0 -- "$snapshot_stage" \
    || fail "cannot seal staged public projection ownership"
  chmod 0555 -- "$snapshot_stage" \
    || fail "cannot preserve public projection snapshot mode"
  require_candidate_projection_snapshot \
    "$snapshot_stage" \
    "staged public projection snapshot"
  verify_tree_sha256 \
    "$snapshot_stage" \
    "$snapshot_tree_expected" \
    "staged public projection snapshot"
  mv -- "$snapshot_stage" "$destination/$snapshot_id" \
    || fail "cannot atomically install the public projection snapshot"

  cp \
    --preserve=mode \
    --no-preserve=ownership,timestamps \
    -- "$current_source" "$current_stage" \
    || fail "cannot stage public projection CURRENT"
  chown 0:0 -- "$current_stage" \
    || fail "cannot seal staged public projection CURRENT ownership"
  [ "$(stat -c %a -- "$current_stage")" = "644" ] \
    || fail "staged public projection CURRENT mode drifted"
  verify_file_sha256 \
    "$current_stage" \
    "$current_expected" \
    "staged public projection CURRENT"
  mv -- "$current_stage" "$destination/CURRENT.json" \
    || fail "cannot atomically install public projection CURRENT"
  chmod 0555 -- "$destination" \
    || fail "cannot seal public projection authority root"

  expected_root_inventory="$(
    printf '%s\n' CURRENT.json "$snapshot_id" | LC_ALL=C sort
  )"
  observed_root_inventory="$(
    find -P "$destination" -xdev -mindepth 1 -maxdepth 1 -printf '%f\n' \
      | LC_ALL=C sort
  )" || fail "copied public projection root could not be inspected"
  [ "$observed_root_inventory" = "$expected_root_inventory" ] \
    || fail "copied public projection root contains extra material"
  verify_file_sha256 \
    "$destination/CURRENT.json" \
    "$current_expected" \
    "copied public projection CURRENT"
  require_candidate_projection_snapshot \
    "$destination/$snapshot_id" \
    "copied public projection snapshot"
  verify_tree_sha256 \
    "$destination/$snapshot_id" \
    "$snapshot_tree_expected" \
    "copied public projection snapshot"

  # Re-read the bind source after the atomic destination commits so a source
  # mutation cannot leave a mixed CURRENT/snapshot authority in the volume.
  verify_file_sha256 \
    "$current_source" \
    "$current_expected" \
    "public projection CURRENT"
  require_candidate_projection_snapshot \
    "$snapshot_source" \
    "public projection snapshot"
  verify_tree_sha256 \
    "$snapshot_source" \
    "$snapshot_tree_expected" \
    "public projection snapshot"
}

copy_isolated_release_shelf() {
  source="$1"
  destination="$2"
  expected="$3"
  require_active_release_shelf "$source"
  verify_tree_sha256 "$source" "$expected" "active release shelf source"
  reset_runtime_input_root "$destination"
  cp -R --no-preserve=mode,ownership,timestamps -- "$source/." "$destination/" \
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
  certificate_expected="$2"
  password_expected="$3"
  setpriv \
    --reuid="$portal_uid" \
    --regid="$portal_gid" \
    --clear-groups \
    /bin/sh -eu -c '
      expected_uid="$1"
      expected_gid="$2"
      root="$3"
      certificate_expected="$4"
      password_expected="$5"
      certificate="$root/data-protection-key-encryption.pfx"
      password="$root/data-protection-key-encryption.password"
      [ "$(id -u)" = "$expected_uid" ]
      [ "$(id -g)" = "$expected_gid" ]
      [ "$(id -G)" = "$expected_gid" ]
      test -f "$certificate"
      test ! -L "$certificate"
      test "$(stat -c %h -- "$certificate")" = 1
      test -r "$certificate"
      test -f "$password"
      test ! -L "$password"
      test "$(stat -c %h -- "$password")" = 1
      test -r "$password"
      test "$(stat -c %u:%g:%a -- "$root")" = "$expected_uid:$expected_gid:700"
      test "$(stat -c %u:%g:%a -- "$certificate")" = "$expected_uid:$expected_gid:400"
      test "$(stat -c %u:%g:%a -- "$password")" = "$expected_uid:$expected_gid:400"
      certificate_observed="$(sha256sum -- "$certificate")"
      certificate_observed="${certificate_observed%% *}"
      test "$certificate_observed" = "$certificate_expected"
      password_observed="$(sha256sum -- "$password")"
      password_observed="${password_observed%% *}"
      test "$password_observed" = "$password_expected"
    ' runtime-secret-reader \
      "$portal_uid" \
      "$portal_gid" \
      "$secret_root" \
      "$certificate_expected" \
      "$password_expected" \
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
  certificate_sha="${CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_SHA256-}"
  password_sha="${CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_SHA256-}"
  app_sha="${CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256-}"
  fleet_sha="${CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256-}"
  shelf_sha="${CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256-}"
  projection_sha="${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256-}"
  projection_current_sha="${CHUMMER_PUBLIC_EDGE_PROJECTION_CURRENT_SHA256-}"
  projection_snapshot_id="${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ID-}"
  runtime_proof_sha="${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256-}"
  final_gold_sha="${CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256-}"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_SHA256 "$certificate_sha"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_SHA256 "$password_sha"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256 "$app_sha"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256 "$fleet_sha"
  validate_sha256 CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256 "$shelf_sha"
  validate_sha256 CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256 "$projection_sha"
  validate_sha256 CHUMMER_PUBLIC_EDGE_PROJECTION_CURRENT_SHA256 "$projection_current_sha"
  validate_projection_snapshot_id "$projection_snapshot_id"
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

  copy_immutable_tree \
    /runtime-inputs/app \
    /app-staging \
    "$app_sha" \
    "portal app"
  copy_immutable_tree \
    /runtime-inputs/fleet \
    /fleet-staging \
    "$fleet_sha" \
    "fleet/static"
  copy_isolated_release_shelf \
    /runtime-inputs/shelf \
    /downloads-source \
    "$shelf_sha"
  copy_candidate_projection_authority \
    /runtime-inputs/projection \
    /public-projection-staging \
    "$projection_snapshot_id" \
    "$projection_current_sha" \
    "$projection_sha"
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

  verify_tree_as_runtime_identity /app-staging "copied portal app"
  verify_tree_as_runtime_identity /fleet-staging "copied fleet/static"
  verify_tree_as_runtime_identity /downloads-source "isolated release shelf"
  verify_tree_as_runtime_identity /public-projection-staging "copied projection"
  verify_tree_as_runtime_identity /proofs-staging "copied runtime proofs"
  verify_secret_identity_boundary \
    /run/chummer-secrets \
    "$certificate_sha" \
    "$password_sha"
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
