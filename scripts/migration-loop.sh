#!/usr/bin/env bash
set -euo pipefail

MAX_ITERS="${1:-6}"
PORT="${CHUMMER_API_PORT:-${CHUMMER_WEB_PORT:-8088}}"
UI_PORT="${CHUMMER_BLAZOR_PORT:-8089}"
AUTH_KEY="${CHUMMER_API_KEY:-migration-smoke-key}"
PORTAL_E2E="${CHUMMER_PORTAL_E2E:-1}"
FAILED=0

for ((iter = 1; iter <= MAX_ITERS; iter++)); do
  echo "===== migration slice iteration ${iter}/${MAX_ITERS} ====="

  export CHUMMER_API_KEY="$AUTH_KEY"
  export CHUMMER_API_PORT="$PORT"
  export CHUMMER_WEB_PORT="$PORT"
  export CHUMMER_BLAZOR_PORT="$UI_PORT"

  if docker compose up -d --build --remove-orphans chummer-api chummer-blazor \
    && bash scripts/audit-compliance.sh \
    && bash scripts/e2e-live.sh \
    && bash scripts/e2e-ui.sh \
    && bash scripts/e2e-auth.sh \
    && if [[ "$PORTAL_E2E" == "1" ]]; then bash scripts/e2e-portal.sh; else true; fi \
    && docker compose --profile test run --build --rm chummer-tests; then
    echo "iteration $iter passed all gates"
    continue
  fi

  echo "[debug] dumping service logs after failed iteration"
  docker compose logs --tail 200 chummer-api chummer-blazor chummer-portal || true
  echo "iteration $iter failed; continuing to next loop"
  FAILED=$((FAILED + 1))
done

if [[ "$FAILED" -gt 0 ]]; then
  echo "loop finished ${MAX_ITERS} iterations with ${FAILED} failed iteration(s)" >&2
  exit 1
fi

echo "compliance achieved across ${MAX_ITERS}/${MAX_ITERS} iterations"
exit 0
