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
PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE="${CHUMMER_PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE:-1}"
PUBLIC_EDGE_EXPECTED_HEAD="${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:-}"
PUBLIC_EDGE_DEPLOY_REPO_ROOT="${CHUMMER_PUBLIC_EDGE_DEPLOY_REPO_ROOT:-${CHUMMER_RUN_SERVICES_SOURCE:-$ROOT_DIR}}"
CANONICAL_RELEASE_CHANNEL_RECEIPT="/docker/chummercomplete/chummer-hub-registry/.codex-studio/published/RELEASE_CHANNEL.generated.json"
PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT:-$CANONICAL_RELEASE_CHANNEL_RECEIPT}"
PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256-}"
PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256="${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256-}"
FAILED=0

PUBLIC_EDGE_DEPLOY_REPO_ROOT="$(cd "$PUBLIC_EDGE_DEPLOY_REPO_ROOT" && pwd)"
export CHUMMER_RUN_SERVICES_SOURCE="$PUBLIC_EDGE_DEPLOY_REPO_ROOT"
export CHUMMER_RUN_SERVICES_CONTEXT_DIR="$PUBLIC_EDGE_DEPLOY_REPO_ROOT"
export CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:-/docker/chummercomplete}"

cd "$ROOT_DIR"

verify_public_edge_deploy_source() {
  local compose_service="$1"
  if [[ "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" == "0" || "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" == "false" || "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" == "FALSE" ]]; then
    return 0
  fi

  local gate_args=(
    --repo-root "$PUBLIC_EDGE_DEPLOY_REPO_ROOT"
    --compose-file "$HUB_EDGE_COMPOSE_FILE"
    --compose-service "$compose_service"
  )
  if [[ -n "$PUBLIC_EDGE_EXPECTED_HEAD" ]]; then
    gate_args+=(--expected-head "$PUBLIC_EDGE_EXPECTED_HEAD")
  fi
  python3 "$PUBLIC_EDGE_DEPLOY_REPO_ROOT/scripts/verify_public_edge_deploy_source.py" "${gate_args[@]}"
}

verify_public_edge_deploy_preflight() {
  if [[ "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "0" || "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "false" || "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "FALSE" ]]; then
    return 0
  fi

  if [[ "$PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" != "$CANONICAL_RELEASE_CHANNEL_RECEIPT" ]]; then
    echo "public-edge preflight refuses a non-canonical release-channel receipt" >&2
    return 2
  fi
  if [[ ! "$PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
    echo "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256 must be independently supplied as a lowercase SHA-256" >&2
    return 2
  fi
  if [[ ! "$PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
    echo "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256 must be independently supplied as a lowercase SHA-256" >&2
    return 2
  fi

  python3 "$PUBLIC_EDGE_DEPLOY_REPO_ROOT/scripts/check_public_edge_deploy_preflight.py" \
    --source-root "$PUBLIC_EDGE_DEPLOY_REPO_ROOT" \
    --runtime-proof-bind-source-sha256 "$PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" \
    --release-channel-receipt "$PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
    --release-channel-receipt-sha256 "$PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256"
}

deploy_public_edge_portal() {
  CHUMMER_PUBLIC_EDGE_COMPOSE_FILE="$HUB_EDGE_COMPOSE_FILE" \
  CHUMMER_PUBLIC_EDGE_PROJECT_NAME="$HUB_EDGE_PROJECT_NAME" \
    bash "$PUBLIC_EDGE_DEPLOY_REPO_ROOT/scripts/deploy_public_edge_portal.sh"
}

for ((iter = 1; iter <= MAX_ITERS; iter++)); do
  echo "===== migration slice iteration ${iter}/${MAX_ITERS} ====="

  if verify_public_edge_deploy_preflight \
    && verify_public_edge_deploy_source chummer-run-identity \
    && verify_public_edge_deploy_source chummer-portal \
    && docker compose -p "$HUB_EDGE_PROJECT_NAME" -f "$HUB_EDGE_COMPOSE_FILE" \
      up -d --build chummer-run-identity \
    && deploy_public_edge_portal \
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
