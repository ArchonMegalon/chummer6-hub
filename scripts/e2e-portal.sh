#!/usr/bin/env bash
set -euo pipefail

CHUMMER_API_KEY="${CHUMMER_API_KEY:-}"
PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS="${CHUMMER_PORTAL_E2E_TIMEOUT_SECONDS:-240}"
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

compose_args=(-f docker-compose.yml)

compose_up_log="$(mktemp)"
set +e
docker compose "${compose_args[@]}" --profile portal up -d --build chummer-api chummer-blazor-portal chummer-hub-web-portal chummer-avalonia-browser chummer-portal \
  chummer-session-web-portal chummer-coach-web-portal \
  2>&1 | tee "$compose_up_log"
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

if [[ "$RUN_PORTAL_PLAYWRIGHT" == "1" ]]; then
  echo "running portal playwright e2e (timeout: ${PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS}s)"
  playwright_log="$(mktemp)"
  set +e
  timeout "${PORTAL_PLAYWRIGHT_TIMEOUT_SECONDS}"s docker compose "${compose_args[@]}" --profile test --profile portal run --build --rm chummer-playwright-portal \
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
