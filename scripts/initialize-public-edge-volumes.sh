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

portal_uid="${CHUMMER_PORTAL_UID:-1654}"
portal_gid="${CHUMMER_PORTAL_GID:-1654}"
validate_numeric_identity CHUMMER_PORTAL_UID "$portal_uid"
validate_numeric_identity CHUMMER_PORTAL_GID "$portal_gid"
command -v setpriv >/dev/null 2>&1 || fail "setpriv is unavailable in the portal image"

umask 077
for mutable_root in \
  /app/state \
  /release-upload-sessions \
  /windows-proof-store \
  /windows-proof-upload-sessions
do
  migrate_mutable_root "$mutable_root"
done

# /downloads-source is a host bind and remains operator-owned. Prove access as the
# portal identity, but never change its ownership or modes from inside the container.
require_mount_root /downloads-source
probe_as_portal_identity /downloads-source

printf '%s\n' "public-edge mutable roots verified for ${portal_uid}:${portal_gid}"
