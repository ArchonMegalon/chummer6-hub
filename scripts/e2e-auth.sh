#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${CHUMMER_API_BASE_URL:-${CHUMMER_WEB_BASE_URL:-http://127.0.0.1:${CHUMMER_API_PORT:-${CHUMMER_WEB_PORT:-8088}}}}"
API_KEY="${CHUMMER_API_KEY:-}"

if [[ -z "$API_KEY" ]]; then
  echo "auth E2E skipped: CHUMMER_API_KEY is not set"
  exit 0
fi

request_code() {
  local path="$1"
  shift
  curl -sS -o /tmp/chummer-auth-response.json -w "%{http_code}" "$BASE_URL$path" "$@"
}

assert_status() {
  local expected="$1"
  local actual="$2"
  local context="$3"
  if [[ "$actual" != "$expected" ]]; then
    echo "Unexpected status for $context: expected $expected, got $actual" >&2
    cat /tmp/chummer-auth-response.json >&2 || true
    exit 1
  fi
}

echo "[auth] verifying public endpoints stay accessible without key"
status=$(request_code "/api/health")
assert_status "200" "$status" "/api/health without key"
status=$(request_code "/api/info")
assert_status "200" "$status" "/api/info without key"
status=$(request_code "/api/commands")
assert_status "200" "$status" "/api/commands without key"
status=$(request_code "/api/navigation-tabs")
assert_status "200" "$status" "/api/navigation-tabs without key"
status=$(request_code "/api/content/overlays")
assert_status "200" "$status" "/api/content/overlays without key"

echo "[auth] verifying protected endpoint blocks missing/invalid key"
status=$(request_code "/api/tools/master-index")
assert_status "401" "$status" "/api/tools/master-index without key"
if ! rg -q '"missing_or_invalid_api_key"' /tmp/chummer-auth-response.json; then
  echo "Protected response did not include auth error marker" >&2
  cat /tmp/chummer-auth-response.json >&2 || true
  exit 1
fi

status=$(request_code "/api/tools/master-index" -H "X-Api-Key: wrong-key")
assert_status "401" "$status" "/api/tools/master-index wrong key"

echo "[auth] verifying protected endpoint succeeds with correct key"
status=$(request_code "/api/tools/master-index" -H "X-Api-Key: $API_KEY")
assert_status "200" "$status" "/api/tools/master-index correct key"

echo "auth E2E completed"
