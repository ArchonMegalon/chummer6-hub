#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

NUGET_ENDPOINT="${NUGET_ENDPOINT:-api.nuget.org:443}"
CHECK_DOCKER="${CHECK_DOCKER:-1}"
CHECK_NUGET="${CHECK_NUGET:-1}"
PREREQ_LOG_DIR="${PREREQ_LOG_DIR:-}"

status=0

is_true() {
  local value
  value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

resolve_log_file() {
  local base_name="$1"
  local uid_suffix
  uid_suffix="$(id -u 2>/dev/null || echo user)"
  local candidates=()
  if [[ -n "$PREREQ_LOG_DIR" ]]; then
    candidates+=("$PREREQ_LOG_DIR/${base_name}.${uid_suffix}.log")
  fi
  if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
    candidates+=("${XDG_RUNTIME_DIR}/${base_name}.${uid_suffix}.log")
  fi
  if [[ -n "${TMPDIR:-}" ]]; then
    candidates+=("${TMPDIR}/${base_name}.${uid_suffix}.log")
  fi
  if [[ -n "${HOME:-}" ]]; then
    candidates+=("${HOME}/.cache/chummer/${base_name}.${uid_suffix}.log")
  fi
  candidates+=("$REPO_ROOT/.tmp/${base_name}.${uid_suffix}.log")
  candidates+=("$PWD/${base_name}.${uid_suffix}.log")

  for candidate in "${candidates[@]}"; do
    local dir
    dir="$(dirname "$candidate")"
    if mkdir -p "$dir" 2>/dev/null && : > "$candidate" 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done

  echo "/dev/null"
}

DOCKER_LOG_FILE="$(resolve_log_file "chummer-strict-prereq-docker")"
NUGET_LOG_FILE="$(resolve_log_file "chummer-strict-prereq-nuget")"

echo "== strict host gate prerequisites =="

if is_true "$CHECK_DOCKER"; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "[FAIL] docker CLI not found."
    status=1
  else
    if docker ps >"$DOCKER_LOG_FILE" 2>&1; then
      echo "[PASS] docker daemon reachable."
    else
      echo "[FAIL] docker daemon not reachable."
      if [[ "$DOCKER_LOG_FILE" != "/dev/null" ]]; then
        cat "$DOCKER_LOG_FILE" || true
      fi
      status=1
    fi
  fi
else
  echo "[SKIP] docker prerequisite check disabled."
fi

if is_true "$CHECK_NUGET"; then
  host="${NUGET_ENDPOINT%:*}"
  port="${NUGET_ENDPOINT##*:}"
  if [[ -z "$host" || -z "$port" || "$host" == "$port" ]]; then
    echo "[FAIL] invalid NUGET_ENDPOINT value '$NUGET_ENDPOINT' (expected host:port)."
    status=1
  else
    set +e
    python3 - "$host" "$port" <<'PY' >"$NUGET_LOG_FILE" 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.create_connection((host, port), timeout=3):
    pass
PY
    probe_status=$?
    set -e
    if [[ "$probe_status" -eq 0 ]]; then
      echo "[PASS] nuget endpoint reachable: $NUGET_ENDPOINT"
    else
      echo "[FAIL] nuget endpoint not reachable: $NUGET_ENDPOINT"
      if [[ "$NUGET_LOG_FILE" != "/dev/null" ]]; then
        cat "$NUGET_LOG_FILE" || true
      fi
      status=1
    fi
  fi
else
  echo "[SKIP] nuget prerequisite check disabled."
fi

if [[ "$status" -eq 0 ]]; then
  echo "Strict host gates are ready."
else
  echo "Strict host gates are NOT ready."
fi

exit "$status"
