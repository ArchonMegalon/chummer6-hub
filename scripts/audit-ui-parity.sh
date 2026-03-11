#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_INDEX="$ROOT/Chummer.Web/wwwroot/index.html"
DESIGNER="$ROOT/Chummer/Forms/ChummerMainForm.Designer.cs"

if [[ ! -f "$WEB_INDEX" || ! -f "$DESIGNER" ]]; then
  echo "required files missing" >&2
  exit 2
fi

web_commands=$(rg -No '^[[:space:]]*[a-z_]+[[:space:]]*:' "$WEB_INDEX" | sed -E 's/^\s*([a-z_]+)\s*:.*/\1/' | sort -u)
web_menus=$(rg -No 'data-command="[a-z_]+"' "$WEB_INDEX" | sed -E 's/.*data-command="([a-z_]+)".*/\1/' | sort -u)

# Curated desktop command set from ChummerMainForm and common utility forms.
desktop_expected=$(cat <<'CMDS'
file
edit
special
tools
windows
help
new_character
new_critter
open_character
open_for_printing
open_for_export
save_character
save_character_as
print_character
print_multiple
print_setup
export_character
copy
paste
dice_roller
global_settings
character_settings
translator
xml_editor
hero_lab_importer
master_index
character_roster
data_exporter
update
restart
report_bug
new_window
close_window
close_all
wiki
discord
revision_history
dumpshock
about
CMDS
)

missing_handlers=()
while IFS= read -r cmd; do
  [[ -z "$cmd" ]] && continue
  if ! grep -qx "$cmd" <<<"$web_commands"; then
    missing_handlers+=("$cmd")
  fi
done <<<"$desktop_expected"

placeholder_handlers=$(rg -No '^[[:space:]]*[a-z_]+[[:space:]]*:[[:space:]]*\(\)[[:space:]]*=>[[:space:]]*(showNote|window\.print|location\.reload)' "$WEB_INDEX" \
  | sed -E 's/^\s*([a-z_]+)\s*:.*/\1/' | sort -u || true)

cat <<REPORT
UI Parity Audit
==============
Web command handlers: $(wc -l <<<"$web_commands" | tr -d ' ')
Menu/toolbar command ids: $(wc -l <<<"$web_menus" | tr -d ' ')
Desktop expected commands: $(wc -l <<<"$desktop_expected" | tr -d ' ')

Missing desktop command handlers: ${#missing_handlers[@]}
REPORT

if [[ ${#missing_handlers[@]} -gt 0 ]]; then
  printf '  - %s\n' "${missing_handlers[@]}"
fi

echo
echo "Handlers still mapped to placeholder behavior:"
if [[ -n "$placeholder_handlers" ]]; then
  sed 's/^/  - /' <<<"$placeholder_handlers"
else
  echo "  - none"
fi

# Fail audit when key desktop commands are missing.
if [[ ${#missing_handlers[@]} -gt 0 ]]; then
  exit 1
fi
