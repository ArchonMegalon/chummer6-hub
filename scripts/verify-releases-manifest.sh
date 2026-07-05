#!/usr/bin/env bash
set -euo pipefail

REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"
TARGET="${1:-${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}}"

if [[ -z "${TARGET}" ]]; then
  echo "Provide a portal base URL or manifest path as the first argument (or set CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL)." >&2
  exit 1
fi

if [[ "$TARGET" =~ ^https?://[^[:space:]]+$ && "$TARGET" != *.json ]]; then
  TARGET="${TARGET%/}/downloads/releases.json"
fi

if [[ ! -f "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" ]]; then
  echo "Missing registry verifier: $REGISTRY_ROOT/scripts/verify_public_release_channel.py" >&2
  exit 1
fi

array_count() {
  local array_name="${1:-}"
  [[ -n "$array_name" ]] || {
    printf '0\n'
    return 0
  }

  local restore_nounset=0
  case "$-" in
    *u*)
      restore_nounset=1
      set +u
      ;;
  esac

  eval "set -- \"\${${array_name}[@]}\""
  local count="$#"

  if (( restore_nounset == 1 )); then
    set -u
  fi

  printf '%s\n' "$count"
}

VERIFY_ARGS=()
if [[ "${CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE:-1}" != "0" ]]; then
  VERIFY_ARGS+=(--require-complete-desktop-coverage)
fi

if (( $(array_count VERIFY_ARGS) > 0 )); then
  python3 "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" "${VERIFY_ARGS[@]}" "$TARGET"
else
  python3 "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" "$TARGET"
fi
