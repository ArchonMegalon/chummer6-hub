#!/usr/bin/env bash
set -euo pipefail
cd "/docker/chummercomplete/chummer.run-services"
source "./scripts/ai/_env.sh"

BOOT_FILE=".codex.resume.boot.txt"
{
  printf 'SYSTEM RE-ENTRY\n'
  printf 'Read these files first and obey them strictly:\n'
  printf -- '- instructions.md\n'
  printf -- '- .agent-memory.md\n'
  printf -- '- AGENT_MEMORY.md\n'
  printf -- '- audit.md\n'
  printf -- '- %s\n' "chummer-run-services.design.v2.md"
  if [ -f AGENTS.md ]; then printf -- '- AGENTS.md\n'; fi
  printf '\n'
  cat instructions.md
  printf '\n\n'
  cat .agent-memory.md
  printf '\n\n'
  cat AGENT_MEMORY.md
  printf '\n\n'
  cat audit.md
  printf '\n\nInspect current repo state before changing anything. Do not repeat already completed work. Continue silently through the queue until fully complete or truly blocked on missing info/permissions.\n'
} > "$BOOT_FILE"

HELP_OUT="$(codex --help 2>&1 || true)"
if printf '%s' "$HELP_OUT" | grep -q -- '--full-auto'; then
  exec codex --full-auto "$(cat "$BOOT_FILE")"
elif printf '%s' "$HELP_OUT" | grep -Eq '(^|[[:space:]])exec([[:space:]]|$)'; then
  exec codex exec "$(cat "$BOOT_FILE")"
else
  exec codex "$(cat "$BOOT_FILE")"
fi
