#!/usr/bin/env bash
set -euo pipefail

API_URL="${CHUMMER_API_BASE_URL:-${CHUMMER_WEB_BASE_URL:-http://127.0.0.1:${CHUMMER_API_PORT:-${CHUMMER_WEB_PORT:-8088}}}}"
UI_URL="${CHUMMER_BLAZOR_BASE_URL:-http://127.0.0.1:${CHUMMER_BLAZOR_PORT:-8089}}"
PLAYWRIGHT_UI_URL="${CHUMMER_UI_PLAYWRIGHT_BASE_URL:-http://127.0.0.1:${CHUMMER_BLAZOR_PORT:-8089}}"
API_KEY="${CHUMMER_API_KEY:-}"
MAX_CURL_ATTEMPTS="${CHUMMER_E2E_CURL_ATTEMPTS:-5}"
MAX_CURL_SECONDS="${CHUMMER_E2E_CURL_MAX_SECONDS:-30}"
CURL_ARGS=(--connect-timeout 5 --max-time "$MAX_CURL_SECONDS")
if [[ -n "${CHUMMER_UI_PLAYWRIGHT:-}" ]]; then
  RUN_PLAYWRIGHT="$CHUMMER_UI_PLAYWRIGHT"
elif [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  RUN_PLAYWRIGHT="1"
else
  RUN_PLAYWRIGHT="0"
fi
if [[ -n "${CHUMMER_E2E_PLAYWRIGHT_SOFT_FAIL:-}" ]]; then
  PLAYWRIGHT_SOFT_FAIL="$CHUMMER_E2E_PLAYWRIGHT_SOFT_FAIL"
elif [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  PLAYWRIGHT_SOFT_FAIL="0"
else
  PLAYWRIGHT_SOFT_FAIL="1"
fi
if [[ -n "${CHUMMER_E2E_DOCKER_FALLBACK:-}" ]]; then
  USE_DOCKER_FALLBACK="$CHUMMER_E2E_DOCKER_FALLBACK"
elif [[ "$RUN_PLAYWRIGHT" == "1" ]]; then
  USE_DOCKER_FALLBACK="1"
else
  USE_DOCKER_FALLBACK="0"
fi
DOCKER_FALLBACK_AVAILABLE="1"
DOCKER_DAEMON_PERMISSION_DENIED="0"
SKIP_REASON=""

is_docker_permission_error_text() {
  local source_file="$1"
  grep -Eqi "permission denied while trying to connect to the Docker daemon socket|operation not permitted|got permission denied while trying to connect to the docker daemon socket" "$source_file"
}

probe_docker_fallback_access() {
  local probe_log
  probe_log="$(mktemp)"
  set +e
  docker compose --profile test ps >"$probe_log" 2>&1
  local status=$?
  set -e
  if [[ "$status" -eq 0 ]]; then
    rm -f "$probe_log"
    return 0
  fi

  DOCKER_FALLBACK_AVAILABLE="0"
  if is_docker_permission_error_text "$probe_log"; then
    DOCKER_DAEMON_PERMISSION_DENIED="1"
  fi
  rm -f "$probe_log"
  return 0
}

curl_with_retries() {
  local max_attempts="${1:-$MAX_CURL_ATTEMPTS}"
  shift

  local attempt
  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if curl "$@"; then
      return 0
    fi
    if (( attempt < max_attempts )); then
      sleep 2
    fi
  done

  return 1
}

docker_fetch_with_key() {
  local url="$1"
  local key="${2:-}"
  docker compose --profile test run --rm -T chummer-playwright node -e \
    "const url=process.argv[1];const key=process.argv[2]||'';const headers=key?{'X-Api-Key':key}:{};fetch(url,{headers}).then(async r=>{const t=await r.text();if(!r.ok){console.error('HTTP '+r.status);process.exit(1);}process.stdout.write(t);}).catch(e=>{console.error(e.message);process.exit(1);});" \
    "$url" "$key"
}

curl_with_key() {
  local url="$1"
  local context="${2:-$url}"
  local response
  if [[ -n "$API_KEY" ]]; then
    if ! response=$(curl_with_retries "$MAX_CURL_ATTEMPTS" -fsS "${CURL_ARGS[@]}" -H "X-Api-Key: $API_KEY" "$url"); then
      if [[ "$USE_DOCKER_FALLBACK" == "1" ]]; then
        if ! response=$(docker_fetch_with_key "$url" "$API_KEY"); then
          echo "request failed for $context after ${MAX_CURL_ATTEMPTS} attempts: $url" >&2
          return 1
        fi
      else
        echo "request failed for $context after ${MAX_CURL_ATTEMPTS} attempts: $url" >&2
        return 1
      fi
    fi
  else
    if ! response=$(curl_with_retries "$MAX_CURL_ATTEMPTS" -fsS "${CURL_ARGS[@]}" "$url"); then
      if [[ "$USE_DOCKER_FALLBACK" == "1" ]]; then
        if ! response=$(docker_fetch_with_key "$url"); then
          echo "request failed for $context after ${MAX_CURL_ATTEMPTS} attempts: $url" >&2
          return 1
        fi
      else
        echo "request failed for $context after ${MAX_CURL_ATTEMPTS} attempts: $url" >&2
        return 1
      fi
    fi
  fi

  printf '%s' "$response"
}

wait_for_url() {
  local url="$1"
  local max_attempts="${2:-45}"
  local sleep_seconds="${3:-1}"
  local attempt
  local docker_probe_log
  local host_attempts="$max_attempts"
  local docker_attempts="$max_attempts"

  if [[ "$USE_DOCKER_FALLBACK" == "1" ]]; then
    host_attempts="${CHUMMER_E2E_HOST_PROBE_ATTEMPTS:-6}"
    docker_attempts="${CHUMMER_E2E_DOCKER_PROBE_ATTEMPTS:-20}"
  fi

  for ((attempt = 1; attempt <= host_attempts; attempt++)); do
    if curl_with_retries 1 -fsS "${CURL_ARGS[@]}" "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_seconds"
  done

  if [[ "$USE_DOCKER_FALLBACK" == "1" ]]; then
    if [[ "$DOCKER_FALLBACK_AVAILABLE" == "1" ]]; then
      for ((attempt = 1; attempt <= docker_attempts; attempt++)); do
        docker_probe_log="$(mktemp)"
        if docker_fetch_with_key "$url" "$API_KEY" > /dev/null 2>"$docker_probe_log"; then
          rm -f "$docker_probe_log"
          return 0
        fi
        if is_docker_permission_error_text "$docker_probe_log"; then
          DOCKER_DAEMON_PERMISSION_DENIED="1"
          rm -f "$docker_probe_log"
          if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" ]]; then
            SKIP_REASON="docker daemon permission denied while probing $url"
            return 2
          fi
        else
          rm -f "$docker_probe_log"
        fi
        sleep "$sleep_seconds"
      done
    elif [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" && "$DOCKER_DAEMON_PERMISSION_DENIED" == "1" ]]; then
      SKIP_REASON="docker daemon permission denied while probing $url"
      return 2
    fi
  fi

  echo "Timed out waiting for $url" >&2
  return 1
}

if [[ "$USE_DOCKER_FALLBACK" == "1" ]]; then
  probe_docker_fallback_access
fi

wait_for_url "$API_URL/api/health" || wait_status=$?
if [[ "${wait_status:-0}" -eq 2 ]]; then
  echo "skipping ui e2e: $SKIP_REASON"
  exit 0
elif [[ "${wait_status:-0}" -ne 0 ]]; then
  exit "${wait_status:-1}"
fi
unset wait_status

wait_for_url "$UI_URL/health" || wait_status=$?
if [[ "${wait_status:-0}" -eq 2 ]]; then
  echo "skipping ui e2e: $SKIP_REASON"
  exit 0
elif [[ "${wait_status:-0}" -ne 0 ]]; then
  exit "${wait_status:-1}"
fi
unset wait_status

api_health=$(curl_with_key "$API_URL/api/health" "api-health")
ui_health=$(curl_with_key "$UI_URL/health" "blazor-health")
ui_html=$(curl_with_key "$UI_URL/" "blazor-root-html")

if ! grep -q '"ok":true' <<<"$api_health"; then
  echo "API health response did not contain ok=true: $api_health" >&2
  exit 1
fi

if ! grep -q '"head":"blazor"' <<<"$ui_health"; then
  echo "Blazor health response did not contain head=blazor: $ui_health" >&2
  exit 1
fi

if ! grep -q "Chummer Blazor Head" <<<"$ui_html"; then
  echo "Blazor shell marker not found in root page response." >&2
  exit 1
fi

if ! grep -q "_framework/blazor.web.js" <<<"$ui_html"; then
  echo "Blazor framework script marker missing from root page response." >&2
  exit 1
fi

PLAYWRIGHT_TIMEOUT_SECONDS="${CHUMMER_UI_PLAYWRIGHT_TIMEOUT_SECONDS:-240}"
if [[ "$RUN_PLAYWRIGHT" == "1" ]]; then
  if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" && "$DOCKER_DAEMON_PERMISSION_DENIED" == "1" ]]; then
    echo "skipping playwright ui e2e: docker daemon permission denied in this environment."
    exit 0
  fi

  echo "running playwright ui e2e against ${PLAYWRIGHT_UI_URL} (timeout: ${PLAYWRIGHT_TIMEOUT_SECONDS}s)"
  playwright_log="$(mktemp)"
  set +e
  CHUMMER_API_KEY="$API_KEY" CHUMMER_UI_PLAYWRIGHT_BASE_URL="$PLAYWRIGHT_UI_URL" \
    timeout "${PLAYWRIGHT_TIMEOUT_SECONDS}"s docker compose --profile test run --build --rm -T chummer-playwright \
    2>&1 | tee "$playwright_log"
  playwright_status=${PIPESTATUS[0]}
  set -e
  if [[ "$playwright_status" -ne 0 ]]; then
    if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" ]] && is_docker_permission_error_text "$playwright_log"; then
      echo "skipping playwright ui e2e: docker daemon permission denied in this environment."
      rm -f "$playwright_log"
      exit 0
    fi

    rm -f "$playwright_log"
    echo "playwright ui e2e failed or timed out after ${PLAYWRIGHT_TIMEOUT_SECONDS}s" >&2
    exit "$playwright_status"
  fi
  rm -f "$playwright_log"
else
  echo "skipping playwright ui e2e (set CHUMMER_UI_PLAYWRIGHT=1 to enable)"
fi

echo "ui E2E completed"
