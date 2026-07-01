#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

HUB_EDGE_COMPOSE_FILE="${HUB_EDGE_COMPOSE_FILE:-docker-compose.public-edge.yml}"
HUB_EDGE_PROJECT_NAME="${CHUMMER_HUB_EDGE_PROJECT_NAME:-chummer6-hub}"
HUB_LOCAL_BASE_URL="${HUB_LOCAL_BASE_URL:-http://127.0.0.1:${CHUMMER_PUBLIC_EDGE_PORT:-8091}}"
HUB_LIVE_BASE_URL="${HUB_LIVE_BASE_URL:-https://chummer.run}"
HUB_PUBLIC_HOST="${HUB_PUBLIC_HOST:-chummer.run}"
HUB_CLOSEOUT_BUILD="${HUB_CLOSEOUT_BUILD:-1}"
HUB_CLOSEOUT_BROWSER="${HUB_CLOSEOUT_BROWSER:-1}"
HUB_CLOSEOUT_LIVE_AUDIT="${HUB_CLOSEOUT_LIVE_AUDIT:-1}"
HUB_CLOSEOUT_INCLUDE_BLAZOR="${HUB_CLOSEOUT_INCLUDE_BLAZOR:-0}"
HUB_ENV_FILE="${CHUMMER_HUB_ENV_FILE:-}"
PUBLIC_EDGE_DEPLOY_SOURCE_GATE="${CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE:-1}"
PUBLIC_EDGE_EXPECTED_HEAD="${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:-}"
PUBLIC_EDGE_DEPLOY_REPO_ROOT="${CHUMMER_PUBLIC_EDGE_DEPLOY_REPO_ROOT:-${CHUMMER_RUN_SERVICES_SOURCE:-$ROOT_DIR}}"

if [[ -z "$HUB_ENV_FILE" ]]; then
  if [[ -f "$ROOT_DIR/.env" ]]; then
    HUB_ENV_FILE="$ROOT_DIR/.env"
  elif [[ -f "/docker/chummercomplete/chummer.run-services/.env" ]]; then
    HUB_ENV_FILE="/docker/chummercomplete/chummer.run-services/.env"
  fi
fi

if [[ -n "$HUB_ENV_FILE" ]]; then
  # Preserve auth-critical values from the selected env file so compose does not
  # inherit empty shell variables and silently disable sign-in on rebuild.
  while IFS='=' read -r key value; do
    case "$key" in
      IDENTITY_ADMIN_KEY|GOOGLE_OIDC_CLIENT_ID|GOOGLE_OIDC_CLIENT_SECRET|GOOGLE_OIDC_REDIRECT_URI)
        export "$key=$value"
        ;;
    esac
  done < <(grep -E '^(IDENTITY_ADMIN_KEY|GOOGLE_OIDC_CLIENT_ID|GOOGLE_OIDC_CLIENT_SECRET|GOOGLE_OIDC_REDIRECT_URI)=' "$HUB_ENV_FILE" || true)
fi

compose_args=(-p "$HUB_EDGE_PROJECT_NAME" -f "$HUB_EDGE_COMPOSE_FILE")
if [[ -n "$HUB_ENV_FILE" ]]; then
  compose_args=(--env-file "$HUB_ENV_FILE" "${compose_args[@]}")
fi

echo "== hub closeout =="
echo "local base: $HUB_LOCAL_BASE_URL"
echo "live base: $HUB_LIVE_BASE_URL"
echo "compose project: $HUB_EDGE_PROJECT_NAME"
if [[ -n "$HUB_ENV_FILE" ]]; then
  echo "compose env file: $HUB_ENV_FILE"
else
  echo "compose env file: <none>"
fi
if [[ "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "1" || "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "true" || "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "TRUE" ]]; then
  echo "include blazor lane: yes"
else
  echo "include blazor lane: no"
fi

if [[ "$HUB_CLOSEOUT_BUILD" == "1" || "$HUB_CLOSEOUT_BUILD" == "true" || "$HUB_CLOSEOUT_BUILD" == "TRUE" ]]; then
  echo
  echo "== rebuild local public edge =="
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
  verify_public_edge_deploy_source chummer-run-identity
  verify_public_edge_deploy_source chummer-portal
  public_edge_services=(chummer-run-identity chummer-portal)
  if [[ "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "1" || "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "true" || "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "TRUE" ]]; then
    public_edge_services+=(chummer-public-blazor)
  fi
  docker compose "${compose_args[@]}" up -d --build --remove-orphans "${public_edge_services[@]}"
fi

echo
echo "== build + verification =="
dotnet build Chummer.Run.sln --nologo
bash scripts/ai/run_services_smoke.sh

if [[ "$HUB_CLOSEOUT_BROWSER" == "1" || "$HUB_CLOSEOUT_BROWSER" == "true" || "$HUB_CLOSEOUT_BROWSER" == "TRUE" ]]; then
  CHUMMER_HUB_PLAYWRIGHT=1 CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/ai/run_services_verification.sh
else
  bash scripts/ai/run_services_verification.sh
fi

echo
echo "== local route audit =="
python3 scripts/hub-live-audit.py \
  --base-url "$HUB_LOCAL_BASE_URL" \
  --public-host "$HUB_PUBLIC_HOST" \
  --forwarded-proto https \
  --verify-http-redirects \
  --verify-signed-in-work

if [[ "$HUB_CLOSEOUT_LIVE_AUDIT" == "1" || "$HUB_CLOSEOUT_LIVE_AUDIT" == "true" || "$HUB_CLOSEOUT_LIVE_AUDIT" == "TRUE" ]]; then
  echo
  echo "== live route audit =="
  python3 scripts/hub-live-audit.py --base-url "$HUB_LIVE_BASE_URL"
  python3 scripts/verify_live_public_windows_installer.py --base-url "$HUB_LIVE_BASE_URL"
fi

echo
echo "hub closeout passed"
