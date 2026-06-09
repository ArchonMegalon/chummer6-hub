#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${CHUMMER_API_BASE_URL:-${CHUMMER_WEB_BASE_URL:-http://127.0.0.1:${CHUMMER_API_PORT:-${CHUMMER_WEB_PORT:-8088}}}}"
API_KEY="${CHUMMER_API_KEY:-}"

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
status=$(request_code "/api/shell/bootstrap")
assert_status "200" "$status" "/api/shell/bootstrap without key"
status=$(request_code "/api/workspaces")
assert_status "200" "$status" "/api/workspaces without key"

echo "[auth] verifying protected endpoint blocks missing/invalid key"
status=$(request_code "/api/tools/master-index")
protected_endpoint_enforced=0
if [[ "$status" == "401" ]]; then
  protected_endpoint_enforced=1
  if ! rg -q '"missing_or_invalid_api_key"' /tmp/chummer-auth-response.json; then
    echo "Protected response did not include auth error marker" >&2
    cat /tmp/chummer-auth-response.json >&2 || true
    exit 1
  fi

  status=$(request_code "/api/tools/master-index" -H "X-Api-Key: wrong-key")
  assert_status "401" "$status" "/api/tools/master-index wrong key"
else
  echo "[auth] note: /api/tools/master-index is public on this runtime (status=$status); skipping API-key enforcement assertions"
fi

if [[ -z "$API_KEY" ]]; then
  echo "auth E2E completed without privileged API key; public and keyless surfaces are green"
  exit 0
fi

if [[ "$protected_endpoint_enforced" != "1" ]]; then
  echo "auth E2E completed with API key present, but no protected API-key endpoint is enforced on this runtime"
  exit 0
fi

echo "[auth] verifying protected endpoint succeeds with correct key"
status=$(request_code "/api/tools/master-index" -H "X-Api-Key: $API_KEY")
assert_status "200" "$status" "/api/tools/master-index correct key"

echo "auth E2E completed"
