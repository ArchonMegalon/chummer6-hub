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


def require_object(value: object, *, message: str) -> dict:
    if not isinstance(value, dict):
        raise SystemExit(message)
    return value


def require_string_list(value: object, *, message: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(message)
    return value


def require_empty_collection(value: object, *, message: str) -> None:
    if isinstance(value, dict):
        if value:
            raise SystemExit(message)
        return
    if isinstance(value, list):
        if value:
            raise SystemExit(message)
        return
    raise SystemExit(message)


def read_receipt(path: pathlib.Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"parity audit failed: required executable receipt is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"parity audit failed: executable receipt must be a JSON object: {path}")
    return data


def read_status(path: pathlib.Path, data: dict) -> str:
    status = str(data.get("status", "")).strip().lower()
    if status not in {"pass", "passed", "ready"}:
        raise SystemExit(
            f"parity audit failed: executable receipt status must be pass/passed/ready: "
            f"{path} (status={status or 'missing'})"
        )
    return status


def validate_workflow_contract(path: pathlib.Path, data: dict) -> None:
    evidence = require_object(
        data.get("evidence"),
        message=f"parity audit failed: workflow receipt evidence must be a JSON object: {path}",
    )
    required_families = require_string_list(
        evidence.get("required_workflow_family_ids"),
        message=f"parity audit failed: workflow receipt required_workflow_family_ids must be a string array: {path}",
    )
    expected_families = {
        "metatype-priorities-karma-entry",
        "attributes-skills-skill-groups-specializations-knowledge-languages",
        "create-open-import-save-save-as-print-export",
        "dense-workbench-affordances-search-add-edit-remove-preview-drill-in-compare",
        "improvements-explain-result-parity",
        "qualities-contacts-identities-notes-calendar-expenses-lifestyles-sources",
        "cyberware-bioware-modular-hierarchies-nested-plugins",
        "armor-weapons-gear-vehicles-drones-mods-custom-items-locations-containers",
        "magic-adept-resonance-sprites-spells-rituals-spirits-powers-metamagics-echoes-complex-forms",
        "recovery-reload-migration-roundtrips",
    }
    missing_expected = sorted(expected_families.difference(required_families))
    if missing_expected:
        raise SystemExit(
            "parity audit failed: workflow receipt is missing required milestone-2 family ids: "
            + ", ".join(missing_expected)
            + f" ({path})"
        )
    require_empty_collection(
        evidence.get("missing_required_workflow_family_ids"),
        message=f"parity audit failed: workflow receipt reports missing required workflow family ids: {path}",
    )
    require_empty_collection(
        evidence.get("not_ready_required_workflow_family_ids"),
        message=f"parity audit failed: workflow receipt reports non-ready required workflow family ids: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_execution_missing_receipts"),
        message=f"parity audit failed: workflow receipt reports missing execution receipts: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_execution_failing_receipts"),
        message=f"parity audit failed: workflow receipt reports failing execution receipts: {path}",
    )


def validate_visual_contract(path: pathlib.Path, data: dict) -> None:
    evidence = require_object(
        data.get("evidence"),
        message=f"parity audit failed: visual receipt evidence must be a JSON object: {path}",
    )
    required_interaction_keys = set(
        require_string_list(
            evidence.get("required_legacy_interaction_keys"),
            message=f"parity audit failed: visual receipt required_legacy_interaction_keys must be a string array: {path}",
        )
    )
    required_surfaces = {
        "legacyCreationWorkflowRhythm",
        "legacyAdvancementWorkflowRhythm",
        "legacyMagicWorkflowRhythm",
        "legacyMatrixWorkflowRhythm",
        "legacyGearWorkflowRhythm",
        "legacyCyberwareDialogRhythm",
        "legacyVehiclesBuilderRhythm",
        "legacyContactsWorkflowRhythm",
        "legacyDiaryWorkflowRhythm",
    }
    missing_surface_keys = sorted(required_surfaces.difference(required_interaction_keys))
    if missing_surface_keys:
        raise SystemExit(
            "parity audit failed: visual receipt is missing required milestone-2 interaction keys: "
            + ", ".join(missing_surface_keys)
            + f" ({path})"
        )
    require_empty_collection(
        evidence.get("missing_required_legacy_interaction_keys"),
        message=f"parity audit failed: visual receipt reports missing required legacy interaction keys: {path}",
    )
    require_empty_collection(
        evidence.get("missing_tests"),
        message=f"parity audit failed: visual receipt reports missing required visual tests: {path}",
    )


workflow_path = pathlib.Path(sys.argv[1])
visual_path = pathlib.Path(sys.argv[2])
workflow_data = read_receipt(workflow_path)
visual_data = read_receipt(visual_path)
results = [
    (workflow_path, read_status(workflow_path, workflow_data)),
    (visual_path, read_status(visual_path, visual_data)),
]
validate_workflow_contract(workflow_path, workflow_data)
validate_visual_contract(visual_path, visual_data)
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
