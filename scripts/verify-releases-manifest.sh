#!/usr/bin/env bash
set -euo pipefail

REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"
TARGET="${1:-${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}}"

if [[ -z "${TARGET}" ]]; then
  echo "Provide a portal base URL or manifest path as the first argument (or set CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL)." >&2
  exit 1
fi

if [[ ! -f "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" ]]; then
  echo "Missing registry verifier: $REGISTRY_ROOT/scripts/verify_public_release_channel.py" >&2
  exit 1
fi

python3 "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" "$TARGET"
