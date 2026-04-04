#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARITY_CHECKLIST="$ROOT/docs/PARITY_CHECKLIST.md"
PARITY_GENERATOR="$ROOT/scripts/generate-parity-checklist.sh"
UI_PUBLISHED_DIR="${CHUMMER_UI_PUBLISHED_DIR:-$ROOT/../chummer-presentation/.codex-studio/published}"
WORKFLOW_GATE_RECEIPT="$UI_PUBLISHED_DIR/DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json"
VISUAL_FAMILIARITY_RECEIPT="$UI_PUBLISHED_DIR/DESKTOP_VISUAL_FAMILIARITY_EXIT_GATE.generated.json"

if [[ ! -x "$PARITY_GENERATOR" ]]; then
  echo "parity generator script is missing or not executable: $PARITY_GENERATOR" >&2
  exit 2
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "ripgrep (rg) is required for parity auditing." >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required for parity auditing." >&2
  exit 2
fi

if ! bash "$PARITY_GENERATOR"; then
  echo "parity audit failed: parity checklist generation reported drift." >&2
  exit 1
fi

if [[ ! -f "$PARITY_CHECKLIST" ]]; then
  echo "parity audit failed: generated checklist is missing at $PARITY_CHECKLIST" >&2
  exit 1
fi

summary_block="$(awk '/^## Summary/{flag=1; next} /^## /{if(flag){exit}} flag {print}' "$PARITY_CHECKLIST")"
if [[ -z "$summary_block" ]]; then
  echo "parity audit failed: summary block missing in $PARITY_CHECKLIST" >&2
  exit 1
fi

if ! python3 - "$WORKFLOW_GATE_RECEIPT" "$VISUAL_FAMILIARITY_RECEIPT" <<'PY'
import json
import pathlib
import sys


def read_status(path: pathlib.Path) -> str:
    if not path.is_file():
        raise SystemExit(f"parity audit failed: required executable receipt is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"parity audit failed: executable receipt must be a JSON object: {path}")
    status = str(data.get("status", "")).strip().lower()
    if status not in {"pass", "passed", "ready"}:
        raise SystemExit(
            f"parity audit failed: executable receipt status must be pass/passed/ready: "
            f"{path} (status={status or 'missing'})"
        )
    return status


paths = [pathlib.Path(value) for value in sys.argv[1:]]
results = [(path, read_status(path)) for path in paths]
for path, status in results:
    print(f"receipt ok: {path.name} (status={status})")
PY
then
  exit 1
fi

echo "UI Parity Audit"
echo "==============="
echo "$summary_block" | sed '/^[[:space:]]*$/d'
echo
echo "Parity audit passed: parity oracle coverage and executable UI receipts are synchronized."
