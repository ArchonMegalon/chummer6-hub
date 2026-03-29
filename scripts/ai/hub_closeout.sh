#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

HUB_EDGE_COMPOSE_FILE="${HUB_EDGE_COMPOSE_FILE:-docker-compose.public-edge.yml}"
HUB_LOCAL_BASE_URL="${HUB_LOCAL_BASE_URL:-http://127.0.0.1:${CHUMMER_PUBLIC_EDGE_PORT:-8091}}"
HUB_LIVE_BASE_URL="${HUB_LIVE_BASE_URL:-https://chummer.run}"
HUB_PUBLIC_HOST="${HUB_PUBLIC_HOST:-chummer.run}"
HUB_CLOSEOUT_BUILD="${HUB_CLOSEOUT_BUILD:-1}"
HUB_CLOSEOUT_BROWSER="${HUB_CLOSEOUT_BROWSER:-1}"
HUB_CLOSEOUT_LIVE_AUDIT="${HUB_CLOSEOUT_LIVE_AUDIT:-1}"

echo "== hub closeout =="
echo "local base: $HUB_LOCAL_BASE_URL"
echo "live base: $HUB_LIVE_BASE_URL"

if [[ "$HUB_CLOSEOUT_BUILD" == "1" || "$HUB_CLOSEOUT_BUILD" == "true" || "$HUB_CLOSEOUT_BUILD" == "TRUE" ]]; then
  echo
  echo "== rebuild local public edge =="
  docker compose -f "$HUB_EDGE_COMPOSE_FILE" up -d --build --remove-orphans chummer-run-identity chummer-portal
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
fi

echo
echo "hub closeout passed"
