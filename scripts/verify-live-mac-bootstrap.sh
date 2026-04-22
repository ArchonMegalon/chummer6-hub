#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
LOCAL_BOOTSTRAP_PATH="$ROOT/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh"
BASE_URL="${CHUMMER_BOOTSTRAP_VERIFY_BASE_URL:-https://chummer.run}"
PRIMARY_PATH="${CHUMMER_BOOTSTRAP_PRIMARY_PATH:-/downloads/release-upload/bootstrap.sh}"
LEGACY_PATH="${CHUMMER_BOOTSTRAP_LEGACY_PATH:-/artifacts/mac-codex-release-pipeline/bootstrap.sh}"
TIMEOUT_SECONDS="${CHUMMER_BOOTSTRAP_VERIFY_TIMEOUT_SECONDS:-60}"
FORWARDED_HOST="${CHUMMER_BOOTSTRAP_VERIFY_HOST:-}"
FORWARDED_PROTO="${CHUMMER_BOOTSTRAP_VERIFY_PROTO:-https}"

die() {
  printf '[verify-live-mac-bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

make_curl_args() {
  local -n _target="$1"
  _target=(
    "--connect-timeout" "10"
    "--max-time" "$TIMEOUT_SECONDS"
  )
  if [[ -n "$FORWARDED_HOST" ]]; then
    _target+=(
      "-H" "Host: $FORWARDED_HOST"
      "-H" "X-Forwarded-Proto: $FORWARDED_PROTO"
    )
  fi
}

[[ -f "$LOCAL_BOOTSTRAP_PATH" ]] || die "local bootstrap is missing: $LOCAL_BOOTSTRAP_PATH"

make_curl_args curl_args
local_sha="$(sha256_file "$LOCAL_BOOTSTRAP_PATH")"
primary_url="${BASE_URL%/}${PRIMARY_PATH}"
legacy_url="${BASE_URL%/}${LEGACY_PATH}"

bootstrap_body="$(mktemp)"
bootstrap_headers="$(mktemp)"
legacy_headers="$(mktemp)"
trap 'rm -f "$bootstrap_body" "$bootstrap_headers" "$legacy_headers"' EXIT

curl -fsSL "${curl_args[@]}" -D "$bootstrap_headers" "$primary_url" -o "$bootstrap_body"
live_sha="$(sha256_file "$bootstrap_body")"
[[ "$live_sha" == "$local_sha" ]] || die "live bootstrap drift: local sha256=$local_sha live sha256=$live_sha url=$primary_url"

curl -fsSI "${curl_args[@]}" "$legacy_url" > "$legacy_headers"
grep -iq '^location: /downloads/release-upload/bootstrap\.sh' "$legacy_headers" \
  || die "legacy bootstrap route does not redirect to primary path: $legacy_url"
grep -iq '^cache-control: private, no-store, max-age=0' "$legacy_headers" \
  || die "legacy bootstrap route is missing no-store cache policy: $legacy_url"

printf '[verify-live-mac-bootstrap] ok local=%s live=%s primary=%s legacy=%s\n' \
  "$local_sha" "$live_sha" "$primary_url" "$legacy_url"
