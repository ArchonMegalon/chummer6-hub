#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MAX_ITERS="${1:-6}"
HUB_EDGE_COMPOSE_FILE="${HUB_EDGE_COMPOSE_FILE:-docker-compose.public-edge.yml}"
HUB_EDGE_PROJECT_NAME="${CHUMMER_HUB_EDGE_PROJECT_NAME:-chummer6-hub}"
PORTAL_E2E="${CHUMMER_PORTAL_E2E:-1}"
HUB_E2E="${CHUMMER_HUB_E2E:-1}"
PUBLIC_EDGE_DEPLOY_SOURCE_GATE="${CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE:-1}"
PUBLIC_EDGE_EXPECTED_HEAD="${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:-}"
PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE="${CHUMMER_PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE:-1}"
FAILED=0

cd "$ROOT_DIR"

verify_public_edge_deploy_source() {
  if [[ "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" == "0" || "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" == "false" || "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" == "FALSE" ]]; then
    return 0
  fi

  local gate_args=(--repo-root "$ROOT_DIR")
  if [[ -n "$PUBLIC_EDGE_EXPECTED_HEAD" ]]; then
    gate_args+=(--expected-head "$PUBLIC_EDGE_EXPECTED_HEAD")
  fi
  python3 scripts/verify_public_edge_deploy_source.py "${gate_args[@]}"
}

verify_public_edge_deploy_preflight() {
  if [[ "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "0" || "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "false" || "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "FALSE" ]]; then
    return 0
  fi

  python3 scripts/check_public_edge_deploy_preflight.py
}

for ((iter = 1; iter <= MAX_ITERS; iter++)); do
  echo "===== migration slice iteration ${iter}/${MAX_ITERS} ====="

  if verify_public_edge_deploy_preflight \
    && verify_public_edge_deploy_source \
    && docker compose -p "$HUB_EDGE_PROJECT_NAME" -f "$HUB_EDGE_COMPOSE_FILE" up -d --build --remove-orphans chummer-run-identity chummer-portal \
    && bash scripts/audit-compliance.sh \
    && if [[ "$PORTAL_E2E" == "1" ]]; then CHUMMER_PORTAL_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-portal.sh; else true; fi \
    && if [[ "$HUB_E2E" == "1" ]]; then CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh; else true; fi; then
    echo "iteration $iter passed all gates"
    continue
  fi

  echo "[debug] dumping service logs after failed iteration"
  docker compose -p "$HUB_EDGE_PROJECT_NAME" -f "$HUB_EDGE_COMPOSE_FILE" logs --tail 200 chummer-run-identity chummer-portal || true
  echo "iteration $iter failed; continuing to next loop"
  FAILED=$((FAILED + 1))
done

if [[ "$FAILED" -gt 0 ]]; then
  echo "loop finished ${MAX_ITERS} iterations with ${FAILED} failed iteration(s)" >&2
  exit 1
fi

echo "compliance achieved across ${MAX_ITERS}/${MAX_ITERS} iterations"
exit 0
