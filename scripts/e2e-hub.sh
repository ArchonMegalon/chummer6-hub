#!/usr/bin/env bash
set -euo pipefail

HUB_EDGE_COMPOSE_FILE="${HUB_EDGE_COMPOSE_FILE:-docker-compose.public-edge.yml}"
HUB_PLAYWRIGHT_TIMEOUT_SECONDS="${CHUMMER_HUB_E2E_TIMEOUT_SECONDS:-300}"
HUB_BASE_URL="${CHUMMER_HUB_PLAYWRIGHT_BASE_URL:-http://127.0.0.1:${CHUMMER_PUBLIC_EDGE_PORT:-8091}}"

if [[ -n "${CHUMMER_HUB_PLAYWRIGHT:-}" ]]; then
  RUN_HUB_PLAYWRIGHT="$CHUMMER_HUB_PLAYWRIGHT"
elif [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  RUN_HUB_PLAYWRIGHT="1"
else
  RUN_HUB_PLAYWRIGHT="0"
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

compose_up_log="$(mktemp)"
set +e
docker compose -f "$HUB_EDGE_COMPOSE_FILE" up -d --build chummer-run-identity chummer-portal 2>&1 | tee "$compose_up_log"
compose_up_status=${PIPESTATUS[0]}
set -e
if [[ "$compose_up_status" -ne 0 ]]; then
  if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" ]] && is_docker_permission_error_text "$compose_up_log"; then
    echo "skipping hub e2e: docker daemon permission denied in this environment."
    rm -f "$compose_up_log"
    exit 0
  fi

  rm -f "$compose_up_log"
  exit "$compose_up_status"
fi
rm -f "$compose_up_log"

if [[ "$RUN_HUB_PLAYWRIGHT" != "1" ]]; then
  echo "skipping hub playwright e2e (set CHUMMER_HUB_PLAYWRIGHT=1 to enable)"
  exit 0
fi

playwright_log="$(mktemp)"
export CHUMMER_RUN_CF_TUNNEL_TOKEN="${CHUMMER_RUN_CF_TUNNEL_TOKEN:-disabled-for-local-hub-e2e}"
set +e
timeout "${HUB_PLAYWRIGHT_TIMEOUT_SECONDS}"s docker compose -f legacy/tooling/docker/docker-compose.yml --profile test run --build --rm \
  -e CHUMMER_HUB_PLAYWRIGHT_BASE_URL="$HUB_BASE_URL" \
  chummer-playwright-hub 2>&1 | tee "$playwright_log"
playwright_status=${PIPESTATUS[0]}
set -e
if [[ "$playwright_status" -ne 0 ]]; then
  if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" ]] && is_docker_permission_error_text "$playwright_log"; then
    echo "skipping hub playwright e2e: docker daemon permission denied in this environment."
    rm -f "$playwright_log"
    exit 0
  fi

  rm -f "$playwright_log"
  echo "hub playwright e2e failed or timed out after ${HUB_PLAYWRIGHT_TIMEOUT_SECONDS}s" >&2
  exit "$playwright_status"
fi

rm -f "$playwright_log"
echo "hub e2e completed"
