#!/usr/bin/env bash
set -euo pipefail
cd "/docker/chummercomplete/chummer.run-services"
source "./scripts/ai/_env.sh"
/docker/chummercomplete/scripts/codex_context_guard.sh "$(pwd)"

CODEX_SANDBOX="${CODEX_SANDBOX:-danger-full-access}"
CODEX_APPROVAL="${CODEX_APPROVAL:-never}"

BOOT_FILE=".codex.boot.prompt.txt"
{
  printf 'SYSTEM INITIALIZATION\n'
  printf 'Read these files first and obey them strictly:\n'
  printf -- '- instructions.md\n'
  printf -- '- .codex-design/product/README.md\n'
  printf -- '- .codex-design/repo/IMPLEMENTATION_SCOPE.md\n'
  printf -- '- .codex-design/review/REVIEW_CONTEXT.md\n'
  printf -- '- docs/HOSTED_BOUNDARY.md\n'
  printf -- '- .agent-memory.md\n\n'
  cat ".agent-memory.md"
  printf '\n\n'
  cat "/docker/chummercomplete/hub.day1.prompt.txt"
  printf '\n'
} > "$BOOT_FILE"

HELP_OUT="$(codex --help 2>&1 || true)"
SHIM_ARGS=(--sandbox "$CODEX_SANDBOX" -a "$CODEX_APPROVAL")

if printf '%s' "$HELP_OUT" | grep -Eq '(^|[[:space:]])exec([[:space:]]|$)'; then
  exec codex exec "${SHIM_ARGS[@]}" "$(cat "$BOOT_FILE")"
else
  exec codex "${SHIM_ARGS[@]}" "$(cat "$BOOT_FILE")"
fi
