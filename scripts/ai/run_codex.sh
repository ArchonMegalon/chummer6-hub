#!/usr/bin/env bash
set -euo pipefail
cd "/docker/chummercomplete/chummer.run-services"
source "./scripts/ai/_env.sh"

BOOT_FILE=".codex.boot.prompt.txt"
{
  printf 'SYSTEM INITIALIZATION\n'
  printf 'Read these files first and obey them strictly:\n'
  printf -- '- %s\n' "chummer-run-services.design.v2.md"
  printf -- '- .agent-memory.md\n\n'
  cat ".agent-memory.md"
  printf '\n\n'
  cat "/docker/chummercomplete/hub.day1.prompt.txt"
  printf '\n'
} > "$BOOT_FILE"

HELP_OUT="$(codex --help 2>&1 || true)"

if printf '%s' "$HELP_OUT" | grep -q -- '--full-auto'; then
  exec codex --full-auto "$(cat "$BOOT_FILE")"
elif printf '%s' "$HELP_OUT" | grep -Eq '(^|[[:space:]])exec([[:space:]]|$)'; then
  exec codex exec "$(cat "$BOOT_FILE")"
else
  exec codex "$(cat "$BOOT_FILE")"
fi
