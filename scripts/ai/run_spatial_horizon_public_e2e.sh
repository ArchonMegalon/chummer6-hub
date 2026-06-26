#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$script_dir/_env.sh" ]]; then
  source "$script_dir/_env.sh"
fi

ROOT_DIR="$(cd "$script_dir/../.." && pwd)"
cd "$ROOT_DIR"

TMP_ROOT="${ROOT_DIR}/.tmp"
if ! mkdir -p "$TMP_ROOT" 2>/dev/null || [[ ! -w "$TMP_ROOT" ]]; then
  TMP_ROOT="${TMPDIR:-/tmp}"
fi
TMP_DIR="$(mktemp -d "${TMP_ROOT}/spatial-horizons-e2e.XXXXXX")"
SERVER_PID=""
SERVER_LOG="$TMP_DIR/server.log"

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

pick_port() {
  local port
  for port in 18088 18089 18090 18091; do
    if ! ss -ltn "( sport = :${port} )" 2>/dev/null | tail -n +2 | grep -q .; then
      echo "$port"
      return 0
    fi
  done

  echo "no free verification port found in 18088-18091" >&2
  return 1
}

wait_for_server() {
  local base_url="$1"
  local attempt
  for attempt in $(seq 1 120); do
    if curl -fsS "$base_url/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "timed out waiting for local server at $base_url" >&2
  cat "$SERVER_LOG" >&2 || true
  return 1
}

PORT="$(pick_port)"
BASE_URL="http://127.0.0.1:${PORT}"

dotnet run \
  --project Chummer.Run.Api/Chummer.Run.Api.csproj \
  --no-launch-profile \
  --urls "$BASE_URL" \
  >"$SERVER_LOG" 2>&1 &
SERVER_PID="$!"

wait_for_server "$BASE_URL"

BASE_URL="$BASE_URL" npx playwright test \
  tests/public/runsite-public.spec.ts \
  tests/public/propertyquarry-public.spec.ts

echo "spatial horizon public playwright passed at $BASE_URL"
