#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARITY_CHECKLIST="$ROOT/docs/PARITY_CHECKLIST.md"
PARITY_GENERATOR="$ROOT/scripts/generate-parity-checklist.sh"
DEFAULT_UI_PUBLISHED_DIR="$ROOT/../chummer6-ui/.codex-studio/published"
LEGACY_UI_PUBLISHED_DIR="$ROOT/../chummer-presentation/.codex-studio/published"
UI_PUBLISHED_DIR="${CHUMMER_UI_PUBLISHED_DIR:-$DEFAULT_UI_PUBLISHED_DIR}"

resolve_receipt_path() {
  local file_name="$1"
  local primary="$UI_PUBLISHED_DIR/$file_name"
  if [[ -f "$primary" ]]; then
    echo "$primary"
    return 0
  fi
  if [[ -z "${CHUMMER_UI_PUBLISHED_DIR:-}" ]]; then
    local legacy="$LEGACY_UI_PUBLISHED_DIR/$file_name"
    if [[ -f "$legacy" ]]; then
      echo "$legacy"
      return 0
    fi
  fi
  echo "$primary"
}

WORKFLOW_GATE_RECEIPT="$(resolve_receipt_path "DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json")"
VISUAL_FAMILIARITY_RECEIPT="$(resolve_receipt_path "DESKTOP_VISUAL_FAMILIARITY_EXIT_GATE.generated.json")"

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
import datetime as dt
import json
import pathlib
import sys

UTC = dt.timezone.utc
DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS = 24 * 60 * 60
DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS = 5 * 60


def require_object(value: object, *, message: str) -> dict:
    if not isinstance(value, dict):
        raise SystemExit(message)
    return value


def require_string_list(value: object, *, message: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(message)
    return value


def require_pass_status(value: object, *, message: str) -> None:
    normalized = str(value or "").strip().lower()
    if normalized not in {"pass", "passed", "ready"}:
        raise SystemExit(message + f" (status={normalized or 'missing'})")


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


def require_empty_problem_map(value: object, *, message: str) -> None:
    if not isinstance(value, dict):
        raise SystemExit(message)
    for _, nested in value.items():
        if isinstance(nested, dict):
            if nested:
                raise SystemExit(message)
            continue
        if isinstance(nested, list):
            if nested:
                raise SystemExit(message)
            continue
        if nested not in (None, ""):
            raise SystemExit(message)


def require_true_bool(value: object, *, message: str) -> None:
    if value is not True:
        raise SystemExit(message)


def require_head_marker_statuses_pass(value: object, *, message: str) -> None:
    marker_statuses = require_object(value, message=message)
    for head, markers in marker_statuses.items():
        if not isinstance(head, str):
            raise SystemExit(message)
        marker_map = require_object(markers, message=message)
        for marker, status in marker_map.items():
            if not isinstance(marker, str):
                raise SystemExit(message)
            normalized = str(status or "").strip().lower()
            if normalized != "pass":
                raise SystemExit(
                    f"{message}: {head}.{marker}={normalized or 'missing'}"
                )


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


def parse_generated_at(path: pathlib.Path, data: dict) -> dt.datetime:
    raw = str(data.get("generatedAt") or data.get("generated_at") or "").strip()
    if not raw:
        raise SystemExit(f"parity audit failed: executable receipt generatedAt/generated_at is missing: {path}")
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(
            f"parity audit failed: executable receipt generatedAt/generated_at is invalid: {path} ({raw})"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def read_int_value(
    evidence: dict,
    key: str,
    *,
    default_value: int,
    path: pathlib.Path,
) -> int:
    value = evidence.get(key)
    if value is None:
        return default_value
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            f"parity audit failed: receipt evidence field {key} must be an integer when present: {path}"
        ) from exc
    if parsed < 0:
        raise SystemExit(f"parity audit failed: receipt evidence field {key} must be >= 0: {path}")
    return parsed


def validate_timestamp_freshness(path: pathlib.Path, data: dict, evidence: dict) -> None:
    generated_at = parse_generated_at(path, data)
    max_age_seconds = read_int_value(
        evidence,
        "proof_freshness_max_age_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS,
        path=path,
    )
    max_future_skew_seconds = read_int_value(
        evidence,
        "proof_freshness_max_future_skew_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS,
        path=path,
    )
    now = dt.datetime.now(UTC)
    age_seconds = int((now - generated_at).total_seconds())
    if age_seconds > max_age_seconds:
        raise SystemExit(
            "parity audit failed: executable receipt generatedAt/generated_at is stale: "
            f"{path} (age_seconds={age_seconds}, max_age_seconds={max_age_seconds})"
        )
    if age_seconds < -max_future_skew_seconds:
        raise SystemExit(
            "parity audit failed: executable receipt generatedAt/generated_at is in the future: "
            f"{path} (future_skew_seconds={abs(age_seconds)}, max_future_skew_seconds={max_future_skew_seconds})"
        )


def validate_workflow_contract(path: pathlib.Path, data: dict) -> None:
    evidence = require_object(
        data.get("evidence"),
        message=f"parity audit failed: workflow receipt evidence must be a JSON object: {path}",
    )
    flagship_required_heads = set(
        require_string_list(
            evidence.get("flagship_required_desktop_heads"),
            message=f"parity audit failed: workflow receipt flagship_required_desktop_heads must be a string array: {path}",
        )
    )
    required_heads = {"avalonia", "blazor-desktop"}
    missing_required_heads = sorted(required_heads.difference(flagship_required_heads))
    if missing_required_heads:
        raise SystemExit(
            "parity audit failed: workflow receipt is missing required flagship desktop heads: "
            + ", ".join(missing_required_heads)
            + f" ({path})"
        )
    require_empty_collection(
        evidence.get("flagship_missing_or_not_ready_desktop_heads"),
        message=f"parity audit failed: workflow receipt reports missing or non-ready flagship desktop heads: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_missing_canonical_required_desktop_heads"),
        message=f"parity audit failed: workflow receipt reports missing canonical required desktop heads: {path}",
    )
    require_empty_problem_map(
        evidence.get("flagship_head_missing_contract_markers"),
        message=f"parity audit failed: workflow receipt reports missing flagship head contract markers: {path}",
    )
    require_head_marker_statuses_pass(
        evidence.get("flagship_head_contract_marker_statuses"),
        message=f"parity audit failed: workflow receipt reports non-pass flagship head contract markers: {path}",
    )
    require_true_bool(
        evidence.get("release_channel_receipt_exists"),
        message=f"parity audit failed: workflow receipt reports missing release-channel evidence receipt: {path}",
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
    require_empty_collection(
        evidence.get("missing_required_workflow_family_audit_tests"),
        message=f"parity audit failed: workflow receipt reports missing required workflow-family audit tests: {path}",
    )
    require_pass_status(
        evidence.get("sr4_workflow_parity_status"),
        message=f"parity audit failed: workflow receipt sr4 parity proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("chummer5a_workflow_parity_status"),
        message=f"parity audit failed: workflow receipt chummer5a parity proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("sr4_sr6_frontier_status"),
        message=f"parity audit failed: workflow receipt sr4/sr6 frontier proof is not pass-ready: {path}",
    )
    validate_timestamp_freshness(path, data, evidence)


def validate_visual_contract(path: pathlib.Path, data: dict) -> None:
    evidence = require_object(
        data.get("evidence"),
        message=f"parity audit failed: visual receipt evidence must be a JSON object: {path}",
    )
    required_tests = require_string_list(
        evidence.get("required_tests"),
        message=f"parity audit failed: visual receipt required_tests must be a string array: {path}",
    )
    expected_required_tests = {
        "Desktop_shell_preserves_chummer5a_familiarity_cues",
        "Loaded_runner_workbench_preserves_legacy_frmcareer_landmarks",
        "Character_creation_preserves_familiar_dense_builder_rhythm",
        "Advancement_and_karma_journal_workflows_preserve_familiar_progression_rhythm",
        "Magic_workflows_execute_with_specific_dialog_fields_and_confirm_actions",
        "Matrix_workflows_execute_with_specific_dialog_fields_and_confirm_actions",
        "Runtime_backed_ruleset_switch_preserves_sr4_sr5_and_sr6_codex_landmarks",
    }
    missing_required_tests = sorted(expected_required_tests.difference(required_tests))
    if missing_required_tests:
        raise SystemExit(
            "parity audit failed: visual receipt is missing required milestone-2 visual tests: "
            + ", ".join(missing_required_tests)
            + f" ({path})"
        )
    required_interaction_keys = set(
        require_string_list(
            evidence.get("required_legacy_interaction_keys"),
            message=f"parity audit failed: visual receipt required_legacy_interaction_keys must be a string array: {path}",
        )
    )
    required_surfaces = {
        "runtimeBackedLegacyWorkbench",
        "legacyDenseBuilderRhythm",
        "legacyCreationWorkflowRhythm",
        "legacyAdvancementWorkflowRhythm",
        "legacyBrowseDetailConfirmRhythm",
        "legacyContactsDiaryRhythm",
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
    required_visual_status_fields = {
        "runtime_backed_legacy_workbench": "runtime-backed legacy workbench",
        "legacy_dense_builder_rhythm": "legacy dense builder rhythm",
        "legacy_creation_workflow_rhythm": "legacy creation workflow rhythm",
        "legacy_advancement_workflow_rhythm": "legacy advancement workflow rhythm",
        "legacy_browse_detail_confirm_rhythm": "legacy browse-detail-confirm rhythm",
        "legacy_contacts_diary_rhythm": "legacy contacts/diary rhythm",
        "legacy_magic_workflow_rhythm": "legacy magic workflow rhythm",
        "legacy_matrix_workflow_rhythm": "legacy matrix workflow rhythm",
        "legacy_gear_workflow_rhythm": "legacy gear workflow rhythm",
        "legacy_cyberware_dialog_rhythm": "legacy cyberware dialog rhythm",
        "legacy_vehicles_builder_rhythm": "legacy vehicles builder rhythm",
        "legacy_contacts_workflow_rhythm": "legacy contacts workflow rhythm",
        "legacy_diary_workflow_rhythm": "legacy diary workflow rhythm",
        "legacy_familiarity_bridge": "legacy familiarity bridge",
    }
    for key, label in required_visual_status_fields.items():
        require_pass_status(
            evidence.get(key),
            message=f"parity audit failed: visual receipt {label} proof is not pass-ready: {path}",
        )
    require_empty_collection(
        evidence.get("missing_required_legacy_interaction_keys"),
        message=f"parity audit failed: visual receipt reports missing required legacy interaction keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_missing_canonical_required_desktop_heads"),
        message=f"parity audit failed: visual receipt reports missing canonical required desktop heads: {path}",
    )
    require_empty_problem_map(
        evidence.get("flagship_head_missing_contract_markers"),
        message=f"parity audit failed: visual receipt reports missing flagship head contract markers: {path}",
    )
    require_head_marker_statuses_pass(
        evidence.get("flagship_head_contract_marker_statuses"),
        message=f"parity audit failed: visual receipt reports non-pass flagship head contract markers: {path}",
    )
    require_true_bool(
        evidence.get("release_channel_receipt_exists"),
        message=f"parity audit failed: visual receipt reports missing release-channel evidence receipt: {path}",
    )
    require_empty_collection(
        evidence.get("missing_theme_tokens"),
        message=f"parity audit failed: visual receipt reports missing required legacy theme tokens: {path}",
    )
    require_pass_status(
        evidence.get("flagship_theme_readability_contrast"),
        message=f"parity audit failed: visual receipt flagship theme/readability proof is not pass-ready: {path}",
    )
    require_empty_collection(
        evidence.get("missing_tests"),
        message=f"parity audit failed: visual receipt reports missing required visual tests: {path}",
    )
    required_screenshots = require_string_list(
        evidence.get("required_screenshots"),
        message=f"parity audit failed: visual receipt required_screenshots must be a string array: {path}",
    )
    expected_required_screenshots = {
        "01-initial-shell-light.png",
        "02-menu-open-light.png",
        "03-settings-open-light.png",
        "04-loaded-runner-light.png",
        "05-dense-section-light.png",
        "06-dense-section-dark.png",
        "07-loaded-runner-tabs-light.png",
        "08-cyberware-dialog-light.png",
        "09-vehicles-section-light.png",
        "10-contacts-section-light.png",
        "11-diary-dialog-light.png",
        "12-magic-dialog-light.png",
        "13-matrix-dialog-light.png",
        "14-advancement-dialog-light.png",
        "15-creation-section-light.png",
    }
    missing_required_screenshots = sorted(expected_required_screenshots.difference(required_screenshots))
    if missing_required_screenshots:
        raise SystemExit(
            "parity audit failed: visual receipt is missing required milestone-2 screenshots: "
            + ", ".join(missing_required_screenshots)
            + f" ({path})"
        )
    require_empty_collection(
        evidence.get("missing_screenshots"),
        message=f"parity audit failed: visual receipt reports missing required screenshots: {path}",
    )
    require_empty_collection(
        evidence.get("invalid_screenshots"),
        message=f"parity audit failed: visual receipt reports invalid screenshots: {path}",
    )
    require_empty_collection(
        evidence.get("undersized_screenshots"),
        message=f"parity audit failed: visual receipt reports undersized screenshots: {path}",
    )
    require_empty_collection(
        evidence.get("stale_screenshots"),
        message=f"parity audit failed: visual receipt reports stale screenshots: {path}",
    )
    require_empty_collection(
        evidence.get("screenshots_older_than_flagship_receipt"),
        message=f"parity audit failed: visual receipt reports screenshots older than flagship receipt: {path}",
    )
    validate_timestamp_freshness(path, data, evidence)


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
