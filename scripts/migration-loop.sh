#!/usr/bin/env bash
set -euo pipefail

MAX_ITERS="${1:-6}"
HUB_EDGE_COMPOSE_FILE="${HUB_EDGE_COMPOSE_FILE:-docker-compose.public-edge.yml}"
PORTAL_E2E="${CHUMMER_PORTAL_E2E:-1}"
HUB_E2E="${CHUMMER_HUB_E2E:-1}"
FAILED=0

for ((iter = 1; iter <= MAX_ITERS; iter++)); do
  echo "===== migration slice iteration ${iter}/${MAX_ITERS} ====="

  if docker compose -f "$HUB_EDGE_COMPOSE_FILE" up -d --build --remove-orphans chummer-run-identity chummer-portal \
    && bash scripts/audit-compliance.sh \
    && if [[ "$PORTAL_E2E" == "1" ]]; then CHUMMER_PORTAL_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-portal.sh; else true; fi \
    && if [[ "$HUB_E2E" == "1" ]]; then CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh; else true; fi; then
    echo "iteration $iter passed all gates"
    continue
  fi

  echo "[debug] dumping service logs after failed iteration"
  docker compose -f "$HUB_EDGE_COMPOSE_FILE" logs --tail 200 chummer-run-identity chummer-portal || true
  echo "iteration $iter failed; continuing to next loop"
  FAILED=$((FAILED + 1))
done

if [[ "$FAILED" -gt 0 ]]; then
  echo "loop finished ${MAX_ITERS} iterations with ${FAILED} failed iteration(s)" >&2
  exit 1
fi

echo "compliance achieved across ${MAX_ITERS}/${MAX_ITERS} iterations"
exit 0
