#!/usr/bin/env bash
set -euo pipefail

HUB_EDGE_COMPOSE_FILE="${HUB_EDGE_COMPOSE_FILE:-docker-compose.public-edge.yml}"
HUB_PLAYWRIGHT_TIMEOUT_SECONDS="${CHUMMER_HUB_E2E_TIMEOUT_SECONDS:-300}"
HUB_BASE_URL="${CHUMMER_HUB_PLAYWRIGHT_BASE_URL:-http://127.0.0.1:${CHUMMER_PUBLIC_EDGE_PORT:-8091}}"
HUB_SKIP_EDGE_REBUILD="${CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD:-0}"
HUB_LOCAL_PROOF_PATH="${CHUMMER_HUB_LOCAL_PROOF_PATH:-.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json}"

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

if [[ "$HUB_SKIP_EDGE_REBUILD" == "1" || "$HUB_SKIP_EDGE_REBUILD" == "true" || "$HUB_SKIP_EDGE_REBUILD" == "TRUE" ]]; then
  echo "reusing current hub edge containers for playwright e2e"
else
  compose_rm_log="$(mktemp)"
  set +e
  docker compose -f "$HUB_EDGE_COMPOSE_FILE" rm -fsv chummer-run-identity chummer-portal 2>&1 | tee "$compose_rm_log"
  compose_rm_status=${PIPESTATUS[0]}
  set -e
  if [[ "$compose_rm_status" -ne 0 ]]; then
    if [[ "$PLAYWRIGHT_SOFT_FAIL" == "1" ]] && is_docker_permission_error_text "$compose_rm_log"; then
      echo "skipping hub e2e: docker daemon permission denied in this environment."
      rm -f "$compose_rm_log"
      exit 0
    fi

    rm -f "$compose_rm_log"
    exit "$compose_rm_status"
  fi
  rm -f "$compose_rm_log"

  compose_up_log="$(mktemp)"
  set +e
  docker compose -f "$HUB_EDGE_COMPOSE_FILE" up -d --build --remove-orphans chummer-run-identity chummer-portal 2>&1 | tee "$compose_up_log"
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
fi

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
mkdir -p "$(dirname "$HUB_LOCAL_PROOF_PATH")"
python3 - "$HUB_LOCAL_PROOF_PATH" "$HUB_BASE_URL" "$HUB_EDGE_COMPOSE_FILE" "$HUB_PLAYWRIGHT_TIMEOUT_SECONDS" "$HUB_SKIP_EDGE_REBUILD" <<'PY'
import datetime as dt
import json
import sys

out_path, base_url, compose_file, timeout_seconds, skip_rebuild = sys.argv[1:]
payload = {
    "contract_name": "chummer6-hub.local_release_proof",
    "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "status": "passed",
    "base_url": base_url,
    "compose_file": compose_file,
    "playwright_timeout_seconds": int(timeout_seconds),
    "edge_rebuild_skipped": skip_rebuild.lower() in {"1", "true"},
}
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
PY
echo "hub e2e completed"
