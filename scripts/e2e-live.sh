#!/usr/bin/env bash
set -euo pipefail

if [[ "${CHUMMER_ALLOW_LEGACY_WORKSPACE_E2E:-0}" != "1" ]]; then
  cat >&2 <<'EOF'
scripts/e2e-live.sh targets the retired standalone workspace API surface.
Use the current Hub exit gate instead:

  CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh

Set CHUMMER_ALLOW_LEGACY_WORKSPACE_E2E=1 only when intentionally testing
the archived /api/workspaces runtime.
EOF
  exit 64
fi

BASE_URL="${CHUMMER_API_BASE_URL:-${CHUMMER_WEB_BASE_URL:-http://127.0.0.1:${CHUMMER_API_PORT:-${CHUMMER_WEB_PORT:-8088}}}}"
XML_FILE="${1:-Chummer.Tests/TestFiles/BLUE.chum5}"
API_KEY="${CHUMMER_API_KEY:-}"
READY_TIMEOUT_SECONDS="${CHUMMER_READY_TIMEOUT_SECONDS:-60}"

curl_json() {
  local method="$1"
  local url="$2"
  shift 2
  if [[ -n "$API_KEY" ]]; then
    curl -fsS -X "$method" "$url" -H "X-Api-Key: $API_KEY" "$@"
  else
    curl -fsS -X "$method" "$url" "$@"
  fi
}

check_get() {
  local path="$1"
  local response_file status body
  response_file=$(mktemp)

  if [[ -n "$API_KEY" ]]; then
    status=$(curl -sSL -o "$response_file" -w "%{http_code}" "$BASE_URL$path" -H "X-Api-Key: $API_KEY")
  else
    status=$(curl -sSL -o "$response_file" -w "%{http_code}" "$BASE_URL$path")
  fi

  body=$(cat "$response_file")
  rm -f "$response_file"

  if [[ "$status" -lt 200 || "$status" -ge 300 ]]; then
    echo "GET $path failed with HTTP $status" >&2
    [[ -n "$body" ]] && echo "$body" >&2
    exit 1
  fi

  printf '%s' "$body"
}

check_status() {
  local path="$1"
  local response_file status
  response_file=$(mktemp)
  if [[ -n "$API_KEY" ]]; then
    status=$(curl -sSL -o "$response_file" -w "%{http_code}" "$BASE_URL$path" -H "X-Api-Key: $API_KEY")
  else
    status=$(curl -sSL -o "$response_file" -w "%{http_code}" "$BASE_URL$path")
  fi
  rm -f "$response_file"
  printf '%s' "$status"
}

wait_for_service() {
  local deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
  echo "waiting for API readiness at $BASE_URL/api/health (timeout: ${READY_TIMEOUT_SECONDS}s)"
  while (( SECONDS < deadline )); do
    if curl_json GET "$BASE_URL/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "API did not become ready within ${READY_TIMEOUT_SECONDS}s" >&2
  return 1
}

if [[ ! -f "$XML_FILE" ]]; then
  echo "E2E XML file not found: $XML_FILE" >&2
  exit 1
fi

xml_escaped=$(perl -0777 -pe 's/^\xEF\xBB\xBF//; s/\\/\\\\/g; s/"/\\"/g; s/\r//g; s/\n/\\n/g' "$XML_FILE")
xml_payload="{\"xml\":\"$xml_escaped\"}"
payload_file=$(mktemp)
response_file=$(mktemp)
import_payload_file=""
metadata_payload_file=""
trap 'rm -f "$payload_file" "$response_file" "${import_payload_file:-}" "${metadata_payload_file:-}"' EXIT
printf '%s' "$xml_payload" > "$payload_file"

request_json() {
  local method="$1"
  local path="$2"
  local body_file="${3:-}"
  local out status
  echo "checking: $method $path" >&2
  if [[ -n "$API_KEY" ]]; then
    if [[ -n "$body_file" ]]; then
      status=$(curl -sS -o "$response_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" -H "Content-Type: application/json" -H "X-Api-Key: $API_KEY" --data-binary "@$body_file")
    else
      status=$(curl -sS -o "$response_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" -H "X-Api-Key: $API_KEY")
    fi
  else
    if [[ -n "$body_file" ]]; then
      status=$(curl -sS -o "$response_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" -H "Content-Type: application/json" --data-binary "@$body_file")
    else
      status=$(curl -sS -o "$response_file" -w "%{http_code}" -X "$method" "$BASE_URL$path")
    fi
  fi
  out=$(cat "$response_file")
  if [[ "$status" -lt 200 || "$status" -ge 300 ]]; then
    echo "status: $status" >&2
    [[ -n "$out" ]] && echo "$out" >&2
    echo "failed: $method $path" >&2
    return 1
  fi
  if [[ "$method" == "DELETE" ]]; then
    return 0
  fi
  if [[ -z "$out" ]]; then
    echo "Empty response from $method $path" >&2
    return 1
  fi
  printf '%s' "$out"
}

wait_for_service
check_get "/api/v1/public/horizons/capabilities?horizonId=runsite&artifactKindOrCapabilityId=runsite-tour" >/dev/null
check_get "/api/health" >/dev/null
check_get "/api/shell/bootstrap" >/dev/null
check_get "/api/workspaces" >/dev/null
openapi_status="$(check_status "/openapi/")"
if [[ "$openapi_status" == "200" ]]; then
  docs_html="$(check_get "/openapi/")"
  if ! printf '%s' "$docs_html" | grep -qi 'Self-hosted OpenAPI explorer'; then
    echo "Docs UI did not return expected self-hosted docs content" >&2
    exit 1
  fi
  if printf '%s' "$docs_html" | grep -qi 'jsdelivr'; then
    echo "Docs UI unexpectedly references external jsdelivr assets" >&2
    exit 1
  fi
else
  echo "note: skipping OpenAPI/docs smoke on $BASE_URL because /openapi/ is not exposed (status=$openapi_status)"
fi

echo "service healthy at $BASE_URL"

import_payload_file=$(mktemp)
python3 - <<'PY' "$XML_FILE" > "$import_payload_file"
import base64, json, pathlib, sys
xml = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig")
print(json.dumps({
    "contentBase64": base64.b64encode(xml.encode("utf-8")).decode("ascii"),
    "format": "NativeXml",
    "xml": None,
    "rulesetId": "sr5",
}))
PY
import_response="$(request_json POST "/api/workspaces/import" "$import_payload_file")"
workspace_id="$(python3 - <<'PY' "$import_response"
import json, sys
print(json.loads(sys.argv[1])["id"])
PY
)"
echo "imported workspace: $workspace_id"

request_json GET "/api/workspaces?maxCount=5" >/dev/null
request_json GET "/api/workspaces/$workspace_id/summary" >/dev/null
request_json GET "/api/workspaces/$workspace_id/validate" >/dev/null
request_json GET "/api/workspaces/$workspace_id/profile" >/dev/null
request_json GET "/api/workspaces/$workspace_id/progress" >/dev/null
request_json GET "/api/workspaces/$workspace_id/skills" >/dev/null
request_json GET "/api/workspaces/$workspace_id/rules" >/dev/null
request_json GET "/api/workspaces/$workspace_id/build" >/dev/null
request_json GET "/api/workspaces/$workspace_id/movement" >/dev/null
request_json GET "/api/workspaces/$workspace_id/awakening" >/dev/null
request_json GET "/api/workspaces/$workspace_id/sections/attributes" >/dev/null
request_json GET "/api/workspaces/$workspace_id/sections/gear" >/dev/null
request_json GET "/api/workspaces/$workspace_id/sections/weapons" >/dev/null

metadata_payload_file=$(mktemp)
printf '%s' '{"displayName":"BLUE E2E Smoke"}' > "$metadata_payload_file"
request_json PATCH "/api/workspaces/$workspace_id/metadata" "$metadata_payload_file" >/dev/null

request_json POST "/api/workspaces/$workspace_id/save" >/dev/null
request_json POST "/api/workspaces/$workspace_id/download" >/dev/null
request_json GET "/api/workspaces/$workspace_id/export" >/dev/null
request_json GET "/api/workspaces/$workspace_id/print" >/dev/null
request_json DELETE "/api/workspaces/$workspace_id" >/dev/null

echo "workspace live E2E completed"

echo "live E2E completed"
