#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CHUMMER_API_KEY="${CHUMMER_API_KEY:-}"
PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS="${CHUMMER_PORTAL_E2E_TIMEOUT_SECONDS:-240}"
PORTAL_EDGE_COMPOSE_FILE="${CHUMMER_PORTAL_EDGE_COMPOSE_FILE:-$ROOT_DIR/docker-compose.public-edge.yml}"
PORTAL_EDGE_PROJECT_NAME="${CHUMMER_PORTAL_EDGE_PROJECT_NAME:-${CHUMMER_HUB_EDGE_PROJECT_NAME:-${COMPOSE_PROJECT_NAME:-chummer6-hub}}}"
PORTAL_BASE_URL="${CHUMMER_PORTAL_BASE_URL:-http://127.0.0.1:${CHUMMER_PUBLIC_EDGE_PORT:-8091}}"
PORTAL_PUBLIC_HOST="${CHUMMER_PORTAL_PUBLIC_HOST:-chummer.run}"
PORTAL_FORWARDED_PROTO="${CHUMMER_PORTAL_FORWARDED_PROTO:-https}"
PORTAL_SKIP_EDGE_REBUILD="${CHUMMER_PORTAL_E2E_SKIP_EDGE_REBUILD:-0}"
if [[ -n "${CHUMMER_PORTAL_PLAYWRIGHT:-}" ]]; then
  RUN_PORTAL_PLAYWRIGHT="$CHUMMER_PORTAL_PLAYWRIGHT"
elif [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  RUN_PORTAL_PLAYWRIGHT="1"
else
  RUN_PORTAL_PLAYWRIGHT="0"
fi
if [[ -n "${CHUMMER_E2E_PLAYWRIGHT_SOFT_FAIL:-}" ]]; then
  PLAYWRIGHT_SOFT_FAIL="$CHUMMER_E2E_PLAYWRIGHT_SOFT_FAIL"
elif [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  PLAYWRIGHT_SOFT_FAIL="0"
else
  PLAYWRIGHT_SOFT_FAIL="1"
fi

is_docker_permission_error_text() {
  local source_file="$1"
  grep -Eqi "permission denied while trying to connect to the Docker daemon socket|operation not permitted|got permission denied while trying to connect to the docker daemon socket" "$source_file"
}

wait_for_portal_edge() {
  local max_attempts="${CHUMMER_PORTAL_E2E_READY_ATTEMPTS:-30}"
  local sleep_seconds="${CHUMMER_PORTAL_E2E_READY_SLEEP_SECONDS:-1}"
  local curl_args=(--connect-timeout 5 --max-time 15 --silent --show-error --fail)
  local header_args=()

  if [[ "$PORTAL_BASE_URL" == http://* ]]; then
    header_args=(-H "Host: $PORTAL_PUBLIC_HOST" -H "X-Forwarded-Proto: $PORTAL_FORWARDED_PROTO")
  fi

  local attempt
  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if curl "${curl_args[@]}" "${header_args[@]}" "$PORTAL_BASE_URL/" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_seconds"
  done

  echo "timed out waiting for portal edge readiness at $PORTAL_BASE_URL/" >&2
  return 1
}

if [[ -n "$CHUMMER_API_KEY" ]]; then
  export CHUMMER_API_KEY
fi

if [[ "$PORTAL_SKIP_EDGE_REBUILD" == "1" || "$PORTAL_SKIP_EDGE_REBUILD" == "true" || "$PORTAL_SKIP_EDGE_REBUILD" == "TRUE" ]]; then
  echo "reusing current public-edge containers for portal playwright e2e"
else
  compose_up_log="$(mktemp)"
  set +e
  docker compose -p "$PORTAL_EDGE_PROJECT_NAME" -f "$PORTAL_EDGE_COMPOSE_FILE" up -d --build --remove-orphans chummer-run-identity chummer-portal 2>&1 | tee "$compose_up_log"
  compose_up_status=${PIPESTATUS[0]}
  set -e
  if [[ "$compose_up_status" -ne 0 ]]; then
    if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" ]] && is_docker_permission_error_text "$compose_up_log"; then
      echo "skipping portal e2e: docker daemon permission denied in this environment."
      rm -f "$compose_up_log"
      exit 0
    fi

    rm -f "$compose_up_log"
    exit "$compose_up_status"
  fi
  rm -f "$compose_up_log"
fi

wait_for_portal_edge

if [[ "$RUN_PORTAL_PLAYWRIGHT" == "1" ]]; then
  echo "running portal playwright e2e (timeout: ${PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS}s)"
  playwright_log="$(mktemp)"
  set +e
  timeout "${PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS}"s env \
    CHUMMER_PORTAL_BASE_URL="$PORTAL_BASE_URL" \
    CHUMMER_PORTAL_PUBLIC_HOST="$PORTAL_PUBLIC_HOST" \
    CHUMMER_PORTAL_FORWARDED_PROTO="$PORTAL_FORWARDED_PROTO" \
    node "$SCRIPT_DIR/e2e-portal.cjs" \
    2>&1 | tee "$playwright_log"
  playwright_status=${PIPESTATUS[0]}
  set -e
  if [[ "$playwright_status" -ne 0 ]]; then
    if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" ]] && is_docker_permission_error_text "$playwright_log"; then
      echo "skipping portal playwright e2e: docker daemon permission denied in this environment."
      rm -f "$playwright_log"
      exit 0
    fi

    rm -f "$playwright_log"
    echo "portal playwright e2e failed or timed out after ${PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS}s" >&2
    exit "$playwright_status"
  fi
  rm -f "$playwright_log"
else
  echo "skipping portal playwright e2e (set CHUMMER_PORTAL_PLAYWRIGHT=1 to enable)"
fi

echo "portal e2e completed"
