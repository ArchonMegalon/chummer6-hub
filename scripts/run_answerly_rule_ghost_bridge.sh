#!/usr/bin/env bash
set -euo pipefail

ROOT="/docker/chummercomplete/chummer.run-services"
API_PROJECT="$ROOT/Chummer.Run.Api/Chummer.Run.Api.csproj"
ENV_FILE="${ANSWERLY_RULE_GHOST_ENV_FILE:-/docker/EA/.env}"
PORT="${ANSWERLY_RULE_GHOST_PORT:-5099}"
LOCAL_TOKEN="${ANSWERLY_RULE_GHOST_API_TOKEN:-ruleghost-local-token}"
PID_DIR="${ROOT}/.artifacts/answerly-rule-ghost"
mkdir -p "$PID_DIR"
TUNNEL_PROVIDER="${ANSWERLY_RULE_GHOST_TUNNEL_PROVIDER:-cloudflared}"

if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    export "$key=$value"
  done < "$ENV_FILE"
fi

export ANSWERLY_ENABLED="${ANSWERLY_ENABLED:-true}"
export ANSWERLY_SUPPORT_ENABLED="${ANSWERLY_SUPPORT_ENABLED:-true}"
export ANSWERLY_HUMANIZER_ENABLED="${ANSWERLY_HUMANIZER_ENABLED:-true}"
export ANSWERLY_OPENAI_COMPAT_ENABLED="${ANSWERLY_OPENAI_COMPAT_ENABLED:-true}"
export ANSWERLY_PROVIDER_VERIFICATION_STATE="${ANSWERLY_PROVIDER_VERIFICATION_STATE:-verified_full_adapter}"
export ANSWERLY_OPENAI_COMPAT_API_TOKEN="$LOCAL_TOKEN"
export CHUMMER_ENABLE_HTTPS_REDIRECTION=false
export ASPNETCORE_URLS="http://127.0.0.1:${PORT}"

API_LOG="${PID_DIR}/api.log"
TUNNEL_LOG="${PID_DIR}/tunnel.log"

if [[ ! -f "${PID_DIR}/api.pid" ]] || ! kill -0 "$(cat "${PID_DIR}/api.pid")" 2>/dev/null; then
  nohup dotnet run --no-build --no-launch-profile --project "$API_PROJECT" -p:UseAppHost=false >"$API_LOG" 2>&1 &
  echo $! > "${PID_DIR}/api.pid"
fi

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/status" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

start_cloudflared() {
  local binary="${PID_DIR}/cloudflared"
  if [[ ! -x "$binary" ]]; then
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o "$binary"
    chmod +x "$binary"
  fi

  nohup "$binary" tunnel --url "http://127.0.0.1:${PORT}" >"$TUNNEL_LOG" 2>&1 &
  echo $! > "${PID_DIR}/tunnel.pid"
}

start_localtunnel() {
  nohup npx -y localtunnel --port "$PORT" >"$TUNNEL_LOG" 2>&1 &
  echo $! > "${PID_DIR}/tunnel.pid"
}

if [[ ! -f "${PID_DIR}/tunnel.pid" ]] || ! kill -0 "$(cat "${PID_DIR}/tunnel.pid")" 2>/dev/null; then
  if [[ "$TUNNEL_PROVIDER" == "cloudflared" ]]; then
    start_cloudflared
  else
    start_localtunnel
  fi
fi

for _ in $(seq 1 90); do
  if [[ "$TUNNEL_PROVIDER" == "cloudflared" ]]; then
    if grep -q 'trycloudflare.com' "$TUNNEL_LOG" 2>/dev/null; then
      break
    fi
  else
    if grep -q 'your url is:' "$TUNNEL_LOG" 2>/dev/null; then
      break
    fi
  fi
  sleep 1
done

if [[ "$TUNNEL_PROVIDER" == "cloudflared" ]]; then
  TUNNEL_URL="$(grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -n 1)"
else
  TUNNEL_URL="$(sed -n 's/.*your url is: //p' "$TUNNEL_LOG" | tail -n 1)"
fi
if [[ -z "$TUNNEL_URL" ]]; then
  echo "Could not determine localtunnel URL." >&2
  exit 1
fi

export ANSWERLY_RULE_GHOST_ENDPOINT="${TUNNEL_URL}/api/v1/chat/completions"
export ANSWERLY_RULE_GHOST_API_TOKEN="$LOCAL_TOKEN"

python3 "$ROOT/scripts/sync_answerly_rule_ghost.py"

cat <<EOF
RULE_GHOST_LOCAL_URL=http://127.0.0.1:${PORT}/api/v1/chat/completions
RULE_GHOST_PUBLIC_URL=${ANSWERLY_RULE_GHOST_ENDPOINT}
RULE_GHOST_MODEL=sr-rulebot
EOF
