#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CHUMMER_API_KEY="${CHUMMER_API_KEY:-}"
PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS="${CHUMMER_PORTAL_E2E_TIMEOUT_SECONDS:-240}"
PORTAL_EDGE_COMPOSE_FILE="${CHUMMER_PORTAL_EDGE_COMPOSE_FILE:-$ROOT_DIR/docker-compose.public-edge.yml}"
PORTAL_BASE_URL="${CHUMMER_PORTAL_BASE_URL:-http://127.0.0.1:${CHUMMER_PUBLIC_EDGE_PORT:-8091}}"
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

if [[ -n "$CHUMMER_API_KEY" ]]; then
  export CHUMMER_API_KEY
fi

if [[ "$PORTAL_SKIP_EDGE_REBUILD" == "1" || "$PORTAL_SKIP_EDGE_REBUILD" == "true" || "$PORTAL_SKIP_EDGE_REBUILD" == "TRUE" ]]; then
  echo "reusing current public-edge containers for portal playwright e2e"
else
  compose_rm_log="$(mktemp)"
  set +e
  docker compose -f "$PORTAL_EDGE_COMPOSE_FILE" rm -fsv chummer-run-identity chummer-portal 2>&1 | tee "$compose_rm_log"
  compose_rm_status=${PIPESTATUS[0]}
  set -e
  if [[ "$compose_rm_status" -ne 0 ]]; then
    if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" ]] && is_docker_permission_error_text "$compose_rm_log"; then
      echo "skipping portal e2e: docker daemon permission denied in this environment."
      rm -f "$compose_rm_log"
      exit 0
    fi

    rm -f "$compose_rm_log"
    exit "$compose_rm_status"
  fi
  rm -f "$compose_rm_log"

  compose_up_log="$(mktemp)"
  set +e
  docker compose -f "$PORTAL_EDGE_COMPOSE_FILE" up -d --build --remove-orphans chummer-run-identity chummer-portal 2>&1 | tee "$compose_up_log"
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

if [[ "$RUN_PORTAL_PLAYWRIGHT" == "1" ]]; then
  echo "running portal playwright e2e (timeout: ${PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS}s)"
  playwright_log="$(mktemp)"
  set +e
  timeout "${PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS}"s env CHUMMER_PORTAL_BASE_URL="$PORTAL_BASE_URL" node "$SCRIPT_DIR/e2e-portal.cjs" \
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
