#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
STATUS_DIR="${ROOT_DIR}/.tmp/ai-status"
STATUS_FILE="${STATUS_DIR}/current-status.txt"

mkdir -p "$STATUS_DIR"

if [ "$#" -eq 0 ]; then
  if [ -f "$STATUS_FILE" ]; then
    cat "$STATUS_FILE"
  fi
  exit 0
fi

printf '%s\n' "$*" > "$STATUS_FILE"
printf '%s\n' "$*"
