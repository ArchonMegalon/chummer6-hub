#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HUB_EDGE_COMPOSE_FILE="${HUB_EDGE_COMPOSE_FILE:-docker-compose.public-edge.yml}"
HUB_EDGE_PROJECT_NAME="${CHUMMER_HUB_EDGE_PROJECT_NAME:-chummer6-hub}"
HUB_PLAYWRIGHT_PROJECT_NAME="${CHUMMER_HUB_PLAYWRIGHT_COMPOSE_PROJECT_NAME:-chummer6-hub-playwright}"
HUB_PLAYWRIGHT_TIMEOUT_SECONDS="${CHUMMER_HUB_E2E_TIMEOUT_SECONDS:-300}"
HUB_BASE_URL="${CHUMMER_HUB_PLAYWRIGHT_BASE_URL:-http://127.0.0.1:${CHUMMER_PUBLIC_EDGE_PORT:-8091}}"
HUB_PUBLIC_HOST="${CHUMMER_HUB_PUBLIC_HOST:-chummer.run}"
HUB_SKIP_EDGE_REBUILD="${CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD:-0}"
PUBLIC_EDGE_DEPLOY_SOURCE_GATE="${CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE:-1}"
PUBLIC_EDGE_EXPECTED_HEAD="${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:-}"
PUBLIC_EDGE_DEPLOY_REPO_ROOT="${CHUMMER_PUBLIC_EDGE_DEPLOY_REPO_ROOT:-${CHUMMER_RUN_SERVICES_SOURCE:-$ROOT_DIR}}"
HUB_LOCAL_PROOF_PATH="${CHUMMER_HUB_LOCAL_PROOF_PATH:-.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json}"
HUB_SYNTHETIC_SUPPORT_CLEANUP_SCRIPT="${CHUMMER_HUB_SYNTHETIC_SUPPORT_CLEANUP_SCRIPT:-scripts/cleanup_synthetic_support_cases.py}"
AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG="${CHUMMER_AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG:-$ROOT_DIR/.state/auth_signin_automation_paused.flag}"

cd "$ROOT_DIR"

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

wait_for_hub_edge() {
  local max_attempts="${CHUMMER_HUB_E2E_READY_ATTEMPTS:-30}"
  local sleep_seconds="${CHUMMER_HUB_E2E_READY_SLEEP_SECONDS:-1}"
  local curl_args=(--connect-timeout 5 --max-time 15 --silent --show-error --fail)
  local header_args=()

  if [[ "$HUB_BASE_URL" == http://* ]]; then
    header_args=(-H "Host: $HUB_PUBLIC_HOST" -H "X-Forwarded-Proto: https")
  fi

  local attempt
  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if curl "${curl_args[@]}" "${header_args[@]}" "$HUB_BASE_URL/" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_seconds"
  done

  echo "timed out waiting for hub edge readiness at $HUB_BASE_URL/" >&2
  return 1
}

resolve_hub_internal_token() {
  docker compose -p "$HUB_EDGE_PROJECT_NAME" -f "$HUB_EDGE_COMPOSE_FILE" ps -q chummer-portal \
    | head -n 1 \
    | xargs -r docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | grep '^FLEET_INTERNAL_API_TOKEN=' \
    | head -n 1 \
    | cut -d= -f2-
}

cleanup_synthetic_support_cases() {
  local token
  token="$(resolve_hub_internal_token || true)"
  if [[ -z "$token" ]]; then
    echo "skipping synthetic support-case cleanup: FLEET_INTERNAL_API_TOKEN is unavailable."
    return 0
  fi

  python3 "$HUB_SYNTHETIC_SUPPORT_CLEANUP_SCRIPT" \
    --base-url "$HUB_BASE_URL" \
    --public-host "$HUB_PUBLIC_HOST" \
    --forwarded-proto https \
    --token "$token"
}

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
  python3 scripts/verify_public_edge_deploy_source.py "${gate_args[@]}"
}

resolve_hub_proof_base_url() {
  if [[ "$HUB_BASE_URL" == http://* ]]; then
    printf 'https://%s\n' "$HUB_PUBLIC_HOST"
    return 0
  fi

  printf '%s\n' "$HUB_BASE_URL"
}

hub_signed_in_work_args() {
  if [[ -f "$AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG" ]]; then
    echo "skipping signed-in hub audit: auth/sign-in automation is paused at $AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG" >&2
    return 0
  fi

  printf '%s\n' --verify-signed-in-work
}

if [[ "$HUB_SKIP_EDGE_REBUILD" == "1" || "$HUB_SKIP_EDGE_REBUILD" == "true" || "$HUB_SKIP_EDGE_REBUILD" == "TRUE" ]]; then
  echo "reusing current hub edge containers for playwright e2e"
else
  verify_public_edge_deploy_source chummer-run-identity
  verify_public_edge_deploy_source chummer-portal

  compose_up_log="$(mktemp)"
  set +e
  docker compose -p "$HUB_EDGE_PROJECT_NAME" -f "$HUB_EDGE_COMPOSE_FILE" up -d --build --remove-orphans chummer-run-identity chummer-portal 2>&1 | tee "$compose_up_log"
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

wait_for_hub_edge

hub_live_audit_args=(--base-url "$HUB_BASE_URL")
if [[ "$HUB_BASE_URL" == http://* ]]; then
  hub_live_audit_args+=(--public-host "$HUB_PUBLIC_HOST" --forwarded-proto https --verify-http-redirects)
  while IFS= read -r extra_arg; do
    [[ -n "$extra_arg" ]] || continue
    hub_live_audit_args+=("$extra_arg")
  done < <(hub_signed_in_work_args)
fi

python3 scripts/hub-live-audit.py "${hub_live_audit_args[@]}"

if [[ "$RUN_HUB_PLAYWRIGHT" == "1" ]]; then
  cleanup_synthetic_support_cases

  playwright_log="$(mktemp)"
  playwright_base_url="$HUB_BASE_URL"
  export CHUMMER_RUN_CF_TUNNEL_TOKEN="${CHUMMER_RUN_CF_TUNNEL_TOKEN:-disabled-for-local-hub-e2e}"
  set +e
  docker compose -p "$HUB_PLAYWRIGHT_PROJECT_NAME" -f legacy/tooling/docker/docker-compose.yml --profile test build \
    chummer-playwright-hub 2>&1 | tee "$playwright_log"
  playwright_status=${PIPESTATUS[0]}
  if [[ "$playwright_status" -eq 0 ]]; then
    timeout "${HUB_PLAYWRIGHT_TIMEOUT_SECONDS}"s docker run --rm --network host \
      -e CHUMMER_HUB_PLAYWRIGHT_BASE_URL="$playwright_base_url" \
      -e CHUMMER_HUB_PLAYWRIGHT_FORWARDED_PROTO="https" \
      chummer-playwright:local \
      node /work/scripts/e2e-hub-playwright.cjs 2>&1 | tee -a "$playwright_log"
    playwright_status=${PIPESTATUS[0]}
  fi
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
  cleanup_synthetic_support_cases
else
  echo "skipping hub playwright e2e (set CHUMMER_HUB_PLAYWRIGHT=1 to enable)"
fi

mkdir -p "$(dirname "$HUB_LOCAL_PROOF_PATH")"
hub_proof_base_url="$(resolve_hub_proof_base_url)"
python3 scripts/materialize_hub_local_release_proof.py \
  "$HUB_LOCAL_PROOF_PATH" \
  "$hub_proof_base_url" \
  "$HUB_EDGE_COMPOSE_FILE" \
  "$HUB_PLAYWRIGHT_TIMEOUT_SECONDS" \
  "$HUB_SKIP_EDGE_REBUILD" >/dev/null
echo "hub e2e completed"
