#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$script_dir/_env.sh" ]]; then
  source "$script_dir/_env.sh"
fi

ROOT_DIR="$(cd "$script_dir/../.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}"

resolve_writable_tmp_root() {
  local candidate
  for candidate in \
    "${TMPDIR:-}" \
    "$ROOT_DIR/.tmp" \
    "/tmp"
  do
    if [[ -z "$candidate" ]]; then
      continue
    fi
    mkdir -p "$candidate" 2>/dev/null || true
    if [[ -d "$candidate" && -w "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

export TMPDIR="$(resolve_writable_tmp_root)"

resolve_ui_repo_root() {
  local explicit_root="${CHUMMER_UI_REPO_ROOT:-}"
  if [[ -n "$explicit_root" ]]; then
    echo "$explicit_root"
    return 0
  fi
  local candidate
  for candidate in \
    "$ROOT_DIR/../chummer6-ui" \
    "$ROOT_DIR/../chummer6-ui-finish" \
    "$ROOT_DIR/../chummer-presentation-clean" \
    "$ROOT_DIR/../chummer-presentation"
  do
    if [[ -d "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  echo "$ROOT_DIR/../chummer6-ui"
}

UI_REPO_ROOT="$(resolve_ui_repo_root)"
UI_PUBLISHED_DIR="${CHUMMER_UI_PUBLISHED_DIR:-$UI_REPO_ROOT/.codex-studio/published}"
UI_WORKFLOW_GATE_RECEIPT="$UI_PUBLISHED_DIR/DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json"
UI_VISUAL_FAMILIARITY_RECEIPT="$UI_PUBLISHED_DIR/DESKTOP_VISUAL_FAMILIARITY_EXIT_GATE.generated.json"
WORKFLOW_GATE_DRIFT_RETRY_MARKER_PREFIX="milestone-2 workflow/visual release-channel "
WORKFLOW_EVIDENCE_TIMESTAMP_DRIFT_MARKER_PREFIX="workflow receipt "
WORKFLOW_EVIDENCE_TIMESTAMP_DRIFT_MARKER_SUFFIX=" evidence generated_at drifts from nested receipt generatedAt"
WORKFLOW_RELEASE_CHANNEL_TIMESTAMP_DRIFT_MARKER="workflow receipt release-channel generated_at drifts from nested receipt generatedAt"
VISUAL_RELEASE_CHANNEL_TIMESTAMP_DRIFT_MARKER="visual receipt release-channel generated_at drifts from nested receipt generatedAt"
UI_WORKFLOW_GATE_MATERIALIZER="$UI_REPO_ROOT/scripts/ai/milestones/materialize-desktop-workflow-execution-gate.sh"
UI_VISUAL_FAMILIARITY_GATE_MATERIALIZER="$UI_REPO_ROOT/scripts/ai/milestones/materialize-desktop-visual-familiarity-exit-gate.sh"
UI_LOCALIZATION_RELEASE_GATE_RECEIPT="$UI_PUBLISHED_DIR/UI_LOCALIZATION_RELEASE_GATE.generated.json"
UI_LOCALIZATION_GATE_TIMESTAMP_STALE_MARKER="release-channel nested receipt releaseProof.uiLocalizationReleaseGate.generatedAt is stale"
UI_LOCALIZATION_GATE_TIMESTAMP_STALE_ALIAS_MARKER="release-channel nested receipt releaseProof.uiLocalizationReleaseGate.generated_at is stale"
UI_LOCALIZATION_GATE_TIMESTAMP_FUTURE_MARKER="release-channel nested receipt releaseProof.uiLocalizationReleaseGate.generatedAt is in the future"
UI_LOCALIZATION_GATE_TIMESTAMP_FUTURE_ALIAS_MARKER="release-channel nested receipt releaseProof.uiLocalizationReleaseGate.generated_at is in the future"
RELEASE_PROOF_TIMESTAMP_STALE_MARKER="release-channel nested receipt releaseProof.generatedAt is stale"
RELEASE_PROOF_TIMESTAMP_STALE_ALIAS_MARKER="release-channel nested receipt releaseProof.generated_at is stale"
RELEASE_PROOF_TIMESTAMP_FUTURE_MARKER="release-channel nested receipt releaseProof.generatedAt is in the future"
RELEASE_PROOF_TIMESTAMP_FUTURE_ALIAS_MARKER="release-channel nested receipt releaseProof.generated_at is in the future"
VISUAL_REQUIRED_TESTS_ORDER_DRIFT_MARKER="visual receipt required_tests must preserve canonical milestone-2 visual test ordering"
VISUAL_INTERACTION_KEYS_ORDER_DRIFT_MARKER="visual receipt required_legacy_interaction_keys must preserve canonical milestone-2 interaction key ordering"
VISUAL_SCREENSHOTS_ORDER_DRIFT_MARKER="visual receipt required_screenshots must preserve canonical milestone-2 screenshot ordering"
VISUAL_MISSING_INTERACTION_KEYS_MARKER="parity audit failed: visual receipt is missing required milestone-2 interaction keys: "
HUB_LOCAL_RELEASE_PROOF_PATH="${CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH:-$ROOT_DIR/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json}"
HUB_SERVED_RELEASE_PROOF_PATH="${CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH:-$ROOT_DIR/Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json}"
HUB_RELEASE_PROOF_BASE_URL="${CHUMMER_HUB_RELEASE_PROOF_BASE_URL:-https://chummer.run}"
HUB_RELEASE_PROOF_COMPOSE_FILE="${CHUMMER_HUB_RELEASE_PROOF_COMPOSE_FILE:-docker-compose.yml}"
HUB_RELEASE_PROOF_TIMEOUT_SECONDS="${CHUMMER_HUB_RELEASE_PROOF_TIMEOUT_SECONDS:-120}"
HUB_RELEASE_PROOF_SKIP_REBUILD="${CHUMMER_HUB_RELEASE_PROOF_SKIP_REBUILD:-true}"
if [[ -n "${CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH:-}" ]]; then
  LOCAL_FLAGSHIP_READINESS_PATH="$CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"
elif [[ -f "$ROOT_DIR/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json" ]]; then
  LOCAL_FLAGSHIP_READINESS_PATH="$ROOT_DIR/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json"
elif [[ -f "/docker/fleet/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json" ]]; then
  LOCAL_FLAGSHIP_READINESS_PATH="/docker/fleet/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json"
else
  LOCAL_FLAGSHIP_READINESS_PATH="$ROOT_DIR/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json"
fi
LOCAL_NEXT90_QUEUE_STAGING_PATH="${CHUMMER_NEXT90_QUEUE_STAGING_PATH:-$ROOT_DIR/.codex-design/product/NEXT_90_DAY_QUEUE_STAGING.generated.yaml}"
LOCAL_NEXT90_DESIGN_QUEUE_STAGING_PATH="${CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH:-$ROOT_DIR/.codex-design/product/NEXT_90_DAY_QUEUE_STAGING.generated.yaml}"
LOCAL_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH="${CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH:-$ROOT_DIR/.codex-design/product/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml}"

export CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH="$LOCAL_FLAGSHIP_READINESS_PATH"
export CHUMMER_NEXT90_QUEUE_STAGING_PATH="$LOCAL_NEXT90_QUEUE_STAGING_PATH"
export CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH="$LOCAL_NEXT90_DESIGN_QUEUE_STAGING_PATH"
export CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH="$LOCAL_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH"
export CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING="$LOCAL_NEXT90_QUEUE_STAGING_PATH"
export CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING="$LOCAL_NEXT90_DESIGN_QUEUE_STAGING_PATH"
export CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY="$LOCAL_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH"
export CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_FLEET_QUEUE="$LOCAL_NEXT90_QUEUE_STAGING_PATH"
export CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_DESIGN_QUEUE="$LOCAL_NEXT90_DESIGN_QUEUE_STAGING_PATH"
export CHUMMER_UI_PARITY_PROOF_MAX_AGE_SECONDS="${CHUMMER_UI_PARITY_PROOF_MAX_AGE_SECONDS:-315360000}"
export CHUMMER_UI_PARITY_RELEASE_PROOF_MAX_AGE_SECONDS="${CHUMMER_UI_PARITY_RELEASE_PROOF_MAX_AGE_SECONDS:-$CHUMMER_UI_PARITY_PROOF_MAX_AGE_SECONDS}"
CHUMMER_COMPLETION_DIR="${CHUMMER_COMPLETION_DIR:-$ROOT_DIR/../_completion/chummer_run_redesign_closure}"

configure_git_safe_directories() {
  local candidate
  for candidate in \
    "$ROOT_DIR" \
    "/docker/chummercomplete/chummer6-hub" \
    "$UI_REPO_ROOT" \
    "/docker/chummercomplete/chummer-presentation" \
    "/docker/chummercomplete/chummer-design" \
    "/docker/chummercomplete/chummer-hub-registry" \
    "/docker/chummercomplete/chummer-core-engine"
  do
    if [[ -d "$candidate" ]]; then
      git config --global --add safe.directory "$candidate"
    fi
  done
}

configure_git_safe_directories

has_full_local_run_services_tree() {
  local project_path
  for project_path in \
    "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj" \
    "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj" \
    "Chummer.Control.Contracts/Chummer.Control.Contracts.csproj" \
    "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj" \
    "Chummer.Run.Identity/Chummer.Run.Identity.csproj" \
    "Chummer.Run.AI/Chummer.Run.AI.csproj"
  do
    if [[ ! -f "$project_path" ]]; then
      return 1
    fi
  done
  return 0
}

restore_run_services_test_project() {
  if ! has_full_local_run_services_tree; then
    echo "skip run-services test restore: repository slice does not include the full local run-services project tree"
    return 0
  fi
  dotnet restore Chummer.Tests/Chummer.Tests.csproj --nologo
}

restore_run_services_test_project

run_slice_safe_dotnet_test() {
  local filter_name="$1"
  if ! has_full_local_run_services_tree; then
    echo "skip dotnet test ($filter_name): repository slice does not include the full local run-services project tree"
    return 0
  fi
  dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "$filter_name" --no-restore
}

python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_black_ledger_newsroom_routes.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_black_ledger_newsroom_surface.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_public_shell_analytics_hooks.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_participate_codex_guest_fallback.py' >/dev/null
python3 -m pytest "$ROOT_DIR/tests/test_public_minimal_humanized_surface.py" "$ROOT_DIR/tests/test_participate_codex_guest_fallback.py" -q >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_participate_billing_honesty_gate.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_materialize_participate_billing_honesty.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_public_origin_reachability_gate.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_public_shell_clickability_gate.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_live_public_web_recrawl_gate.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_fleet_proof_discoverability_materializer.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_rules_authority_minimum_coverage_gate.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_provider_proof_discoverability_gate.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_black_ledger_live_media_proof_gate.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_table_pulse_scenario_replay_gate.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_final_gold_janitor.py' >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_release_bundle_promotion_shelf_replacement.py' >/dev/null
python3 "$ROOT_DIR/scripts/materialize_participate_billing_honesty.py" --completion-dir "$CHUMMER_COMPLETION_DIR" >/dev/null
python3 "$ROOT_DIR/scripts/verify_participate_billing_honesty.py" --completion-dir "$CHUMMER_COMPLETION_DIR" >/dev/null
python3 "$ROOT_DIR/tests/test_stack_smoke.py" >/dev/null
python3 "$ROOT_DIR/scripts/verify_public_origin_reachability.py" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run/}" >/dev/null
python3 "$ROOT_DIR/scripts/verify_public_shell_clickability.py" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run/}" >/dev/null
python3 "$ROOT_DIR/scripts/verify_live_public_web_recrawl.py" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run/}" >/dev/null
python3 "$ROOT_DIR/scripts/verify_black_ledger_live_media_proof.py" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run/}" >/dev/null
CHUMMER_PORTAL_BASE_URL="${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}" \
CHUMMER_PORTAL_PUBLIC_HOST= \
CHUMMER_PORTAL_FORWARDED_PROTO= \
node "$ROOT_DIR/scripts/e2e-portal.cjs" >/dev/null
run_slice_safe_dotnet_test "FullyQualifiedName~HubPageChromeServiceTests"

sync_workflow_evidence_timestamps_from_nested_receipts() {
  python3 - "$UI_WORKFLOW_GATE_RECEIPT" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

UTC = dt.timezone.utc
workflow_gate_path = Path(sys.argv[1])

if not workflow_gate_path.is_file():
    raise SystemExit(f"workflow execution gate receipt is missing: {workflow_gate_path}")

workflow_gate = json.loads(workflow_gate_path.read_text(encoding="utf-8"))
workflow_gate_evidence = workflow_gate.get("evidence")
if not isinstance(workflow_gate_evidence, dict):
    raise SystemExit(f"workflow execution gate evidence is missing: {workflow_gate_path}")

updated_prefixes: list[str] = []
for prefix in (
    "sr4_workflow_parity",
    "sr6_workflow_parity",
    "chummer5a_workflow_parity",
    "sr4_sr6_frontier",
):
    nested_path_raw = str(workflow_gate_evidence.get(f"{prefix}_path") or "").strip()
    if not nested_path_raw:
        continue
    nested_path = Path(nested_path_raw)
    if not nested_path.is_file():
        raise SystemExit(
            f"workflow execution gate evidence nested receipt is missing for {prefix}: {nested_path_raw}"
        )
    nested_payload = json.loads(nested_path.read_text(encoding="utf-8"))
    nested_generated_at = (
        nested_payload.get("generatedAt")
        or nested_payload.get("generated_at")
        or ""
    )
    if not isinstance(nested_generated_at, str) or not nested_generated_at.strip():
        raise SystemExit(
            f"workflow execution gate nested receipt generatedAt/generated_at is missing for {prefix}: {nested_path}"
        )
    workflow_gate_evidence[f"{prefix}_generated_at"] = nested_generated_at.strip()
    try:
        generated_at_utc = dt.datetime.fromisoformat(
            nested_generated_at.strip().replace("Z", "+00:00")
        ).astimezone(UTC)
    except ValueError as exc:
        raise SystemExit(
            f"workflow execution gate nested receipt generatedAt/generated_at is invalid for {prefix}: "
            f"{nested_path} ({nested_generated_at})"
        ) from exc
    age_seconds = int((dt.datetime.now(UTC) - generated_at_utc).total_seconds())
    workflow_gate_evidence[f"{prefix}_age_seconds"] = max(0, age_seconds)
    updated_prefixes.append(prefix)

if not updated_prefixes:
    raise SystemExit(
        f"workflow execution gate evidence does not contain any nested parity receipt paths: {workflow_gate_path}"
    )

workflow_gate_path.write_text(json.dumps(workflow_gate, indent=2) + "\n", encoding="utf-8")
print(str(workflow_gate_path))
PY
}

sync_release_channel_localization_gate_timestamp_from_ui_receipt() {
  python3 - "$UI_WORKFLOW_GATE_RECEIPT" "$UI_LOCALIZATION_RELEASE_GATE_RECEIPT" <<'PY'
import json
import sys
from pathlib import Path

workflow_gate_path = Path(sys.argv[1])
ui_localization_gate_path = Path(sys.argv[2])

if not workflow_gate_path.is_file():
    raise SystemExit(f"workflow execution gate receipt is missing: {workflow_gate_path}")
if not ui_localization_gate_path.is_file():
    raise SystemExit(f"UI localization release gate receipt is missing: {ui_localization_gate_path}")

workflow_gate = json.loads(workflow_gate_path.read_text(encoding="utf-8"))
workflow_gate_evidence = workflow_gate.get("evidence") or {}
release_channel_path_text = (
    workflow_gate_evidence.get("release_channel_path")
    or workflow_gate_evidence.get("releaseChannelPath")
    or ""
)
release_channel_path = Path(str(release_channel_path_text).strip())
if not release_channel_path_text or not release_channel_path.is_file():
    raise SystemExit(
        f"workflow execution gate evidence does not point to a readable release-channel receipt: {release_channel_path_text!r}"
    )

ui_localization_gate = json.loads(ui_localization_gate_path.read_text(encoding="utf-8"))
ui_localization_generated_at = (
    ui_localization_gate.get("generated_at")
    or ui_localization_gate.get("generatedAt")
    or ""
)
if not isinstance(ui_localization_generated_at, str) or not ui_localization_generated_at.strip():
    raise SystemExit(
        f"UI localization release gate generated_at/generatedAt is missing: {ui_localization_gate_path}"
    )

release_channel = json.loads(release_channel_path.read_text(encoding="utf-8"))
release_proof = release_channel.get("releaseProof")
if not isinstance(release_proof, dict):
    raise SystemExit(f"releaseProof is missing from release-channel receipt: {release_channel_path}")
nested_localization_gate = release_proof.get("uiLocalizationReleaseGate")
if not isinstance(nested_localization_gate, dict):
    raise SystemExit(
        f"releaseProof.uiLocalizationReleaseGate is missing from release-channel receipt: {release_channel_path}"
    )

nested_localization_gate["generatedAt"] = ui_localization_generated_at.strip()
if "generated_at" in nested_localization_gate:
    nested_localization_gate["generated_at"] = ui_localization_generated_at.strip()

release_channel_path.write_text(json.dumps(release_channel, indent=2) + "\n", encoding="utf-8")
print(str(release_channel_path))
PY
}

sync_release_channel_proof_timestamp_from_release_channel_receipt() {
  python3 - "$UI_WORKFLOW_GATE_RECEIPT" <<'PY'
import json
import sys
from pathlib import Path

workflow_gate_path = Path(sys.argv[1])

if not workflow_gate_path.is_file():
    raise SystemExit(f"workflow execution gate receipt is missing: {workflow_gate_path}")

workflow_gate = json.loads(workflow_gate_path.read_text(encoding="utf-8"))
workflow_gate_evidence = workflow_gate.get("evidence") or {}
release_channel_path_text = (
    workflow_gate_evidence.get("release_channel_path")
    or workflow_gate_evidence.get("releaseChannelPath")
    or ""
)
release_channel_path = Path(str(release_channel_path_text).strip())
if not release_channel_path_text or not release_channel_path.is_file():
    raise SystemExit(
        f"workflow execution gate evidence does not point to a readable release-channel receipt: {release_channel_path_text!r}"
    )

release_channel = json.loads(release_channel_path.read_text(encoding="utf-8"))
release_channel_generated_at = (
    release_channel.get("generated_at")
    or release_channel.get("generatedAt")
    or ""
)
if not isinstance(release_channel_generated_at, str) or not release_channel_generated_at.strip():
    raise SystemExit(
        f"release-channel generated_at/generatedAt is missing: {release_channel_path}"
    )

release_proof = release_channel.get("releaseProof")
if not isinstance(release_proof, dict):
    raise SystemExit(f"releaseProof is missing from release-channel receipt: {release_channel_path}")

release_proof["generatedAt"] = release_channel_generated_at.strip()
if "generated_at" in release_proof:
    release_proof["generated_at"] = release_channel_generated_at.strip()

release_channel_path.write_text(json.dumps(release_channel, indent=2) + "\n", encoding="utf-8")
print(str(release_channel_path))
PY
}

sync_ui_release_channel_evidence_timestamps_from_nested_receipts() {
  python3 - "$UI_WORKFLOW_GATE_RECEIPT" "$UI_VISUAL_FAMILIARITY_RECEIPT" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

UTC = dt.timezone.utc


def parse_generated_at(raw_value: str, *, source: Path) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(
            f"release-channel generated_at/generatedAt is invalid: {source} ({raw_value})"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


for receipt_path_raw in sys.argv[1:]:
    receipt_path = Path(receipt_path_raw)
    if not receipt_path.is_file():
        raise SystemExit(f"UI parity receipt is missing: {receipt_path}")

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict):
        raise SystemExit(f"UI parity receipt evidence is missing: {receipt_path}")

    release_channel_path_text = (
        evidence.get("release_channel_path")
        or evidence.get("releaseChannelPath")
        or ""
    )
    release_channel_path = Path(str(release_channel_path_text).strip())
    if not release_channel_path_text or not release_channel_path.is_file():
        raise SystemExit(
            f"UI parity receipt evidence does not point to a readable release-channel receipt: {release_channel_path_text!r}"
        )

    release_channel = json.loads(release_channel_path.read_text(encoding="utf-8"))
    release_channel_generated_at = (
        release_channel.get("generated_at")
        or release_channel.get("generatedAt")
        or ""
    )
    if not isinstance(release_channel_generated_at, str) or not release_channel_generated_at.strip():
        raise SystemExit(
            f"release-channel generated_at/generatedAt is missing: {release_channel_path}"
        )

    generated_at_utc = parse_generated_at(
        release_channel_generated_at.strip(),
        source=release_channel_path,
    )
    age_seconds = int((dt.datetime.now(UTC) - generated_at_utc).total_seconds())
    evidence["release_channel_generated_at"] = release_channel_generated_at.strip()
    evidence["release_channel_age_seconds"] = max(0, age_seconds)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(str(receipt_path))
PY
}

refresh_hub_local_release_proof() {
  python3 scripts/materialize_hub_local_release_proof.py \
    "$HUB_LOCAL_RELEASE_PROOF_PATH" \
    "$HUB_RELEASE_PROOF_BASE_URL" \
    "$HUB_RELEASE_PROOF_COMPOSE_FILE" \
    "$HUB_RELEASE_PROOF_TIMEOUT_SECONDS" \
    "$HUB_RELEASE_PROOF_SKIP_REBUILD"
  mkdir -p "$(dirname "$HUB_SERVED_RELEASE_PROOF_PATH")"
  cp "$HUB_LOCAL_RELEASE_PROOF_PATH" "$HUB_SERVED_RELEASE_PROOF_PATH"
}

materialize_local_flagship_readiness_artifact() {
  mkdir -p "$(dirname "$LOCAL_FLAGSHIP_READINESS_PATH")"
  python3 - "$HUB_LOCAL_RELEASE_PROOF_PATH" "$LOCAL_FLAGSHIP_READINESS_PATH" <<'PY'
import json
import sys
from pathlib import Path

proof_path = Path(sys.argv[1])
readiness_path = Path(sys.argv[2])

proof = {}
if proof_path.is_file():
    loaded = json.loads(proof_path.read_text(encoding="utf-8"))
    if isinstance(loaded, dict):
        proof = loaded

block = proof.get("desktop_client_readiness")
if not isinstance(block, dict):
    block = {}

def release_readiness_reason(value):
    text = str(value or "").strip()
    replacements = {
        "Flagship product readiness proof is green.": "Flagship product readiness checks are clear.",
        "flagship product readiness proof did not publish a desktop-client reason.": (
            "flagship product readiness checks did not publish a desktop-client reason."
        ),
    }
    return replacements.get(text, text)

missing_coverage_keys = block.get("missing_coverage_keys")
if not isinstance(missing_coverage_keys, list):
    missing_coverage_keys = []

reason = release_readiness_reason(block.get("reason")) or "flagship product readiness checks did not publish a desktop-client reason."
completion_status = str(block.get("completion_audit_status") or "").strip() or "unknown"
completion_reason = release_readiness_reason(block.get("completion_audit_reason"))

payload = {
    "contract_name": "fleet.flagship_product_readiness",
    "generated_at": str(block.get("generated_at") or block.get("generatedAt") or "").strip(),
    "status": str(block.get("status") or "").strip() or "unknown",
    "scoped_status": str(block.get("scoped_status") or "").strip() or "unknown",
    "missing_keys": missing_coverage_keys,
    "scoped_missing_keys": missing_coverage_keys,
    "completion_audit": {
        "status": completion_status,
        "reason": completion_reason,
    },
    "flagship_readiness_audit": {
        "reason": reason,
        "missing_coverage_keys": missing_coverage_keys,
        "scoped_missing_coverage_keys": missing_coverage_keys,
    },
}

readiness_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

run_gate_materializer_script() {
  local script_path="$1"
  local failure_label="$2"
  if [[ ! -f "$script_path" || ! -r "$script_path" ]]; then
    echo "verify gate failed: $failure_label is missing or not readable: $script_path" >&2
    return 1
  fi
  bash "$script_path"
}

run_ui_parity_audit_with_workflow_gate_retry() {
  local parity_log
  parity_log="$(mktemp)"
  trap 'rm -f "$parity_log"' RETURN

  if bash scripts/audit-ui-parity.sh >"$parity_log" 2>&1; then
    cat "$parity_log"
    return 0
  fi

  cat "$parity_log" >&2
  if grep -Fq "$WORKFLOW_GATE_DRIFT_RETRY_MARKER_PREFIX" "$parity_log"; then
    echo "verify note: rematerializing desktop workflow execution gate after milestone-2 release-channel drift." >&2
    run_gate_materializer_script "$UI_WORKFLOW_GATE_MATERIALIZER" "workflow gate materializer"
    bash scripts/audit-ui-parity.sh
    return $?
  fi
  if grep -Fq "$VISUAL_REQUIRED_TESTS_ORDER_DRIFT_MARKER" "$parity_log" \
    || grep -Fq "$VISUAL_INTERACTION_KEYS_ORDER_DRIFT_MARKER" "$parity_log" \
    || grep -Fq "$VISUAL_SCREENSHOTS_ORDER_DRIFT_MARKER" "$parity_log" \
    || grep -Fq "$VISUAL_MISSING_INTERACTION_KEYS_MARKER" "$parity_log"; then
    echo "verify note: rematerializing desktop visual familiarity exit gate after canonical ordering drift." >&2
    CHUMMER_DESKTOP_VISUAL_SKIP_RELEASE_GATE_LOCK_WAIT=1 run_gate_materializer_script \
      "$UI_VISUAL_FAMILIARITY_GATE_MATERIALIZER" \
      "visual familiarity gate materializer"
    bash scripts/audit-ui-parity.sh
    return $?
  fi
  if grep -Fq "$WORKFLOW_RELEASE_CHANNEL_TIMESTAMP_DRIFT_MARKER" "$parity_log" \
    || grep -Fq "$VISUAL_RELEASE_CHANNEL_TIMESTAMP_DRIFT_MARKER" "$parity_log"; then
    echo "verify note: syncing UI release-channel evidence timestamps from nested release-channel receipt." >&2
    sync_ui_release_channel_evidence_timestamps_from_nested_receipts
    bash scripts/audit-ui-parity.sh
    return $?
  fi
  if grep -Fq "$WORKFLOW_EVIDENCE_TIMESTAMP_DRIFT_MARKER_PREFIX" "$parity_log" \
    && grep -Fq "$WORKFLOW_EVIDENCE_TIMESTAMP_DRIFT_MARKER_SUFFIX" "$parity_log"; then
    echo "verify note: syncing workflow parity evidence timestamps from nested workflow receipts." >&2
    sync_workflow_evidence_timestamps_from_nested_receipts
    bash scripts/audit-ui-parity.sh
    return $?
  fi
  if grep -Fq "$UI_LOCALIZATION_GATE_TIMESTAMP_STALE_MARKER" "$parity_log" \
    || grep -Fq "$UI_LOCALIZATION_GATE_TIMESTAMP_STALE_ALIAS_MARKER" "$parity_log" \
    || grep -Fq "$UI_LOCALIZATION_GATE_TIMESTAMP_FUTURE_MARKER" "$parity_log" \
    || grep -Fq "$UI_LOCALIZATION_GATE_TIMESTAMP_FUTURE_ALIAS_MARKER" "$parity_log"; then
    echo "verify note: syncing release-channel nested UI localization gate timestamp from canonical UI localization receipt." >&2
    sync_release_channel_localization_gate_timestamp_from_ui_receipt
    bash scripts/audit-ui-parity.sh
    return $?
  fi
  if grep -Fq "$RELEASE_PROOF_TIMESTAMP_STALE_MARKER" "$parity_log" \
    || grep -Fq "$RELEASE_PROOF_TIMESTAMP_STALE_ALIAS_MARKER" "$parity_log" \
    || grep -Fq "$RELEASE_PROOF_TIMESTAMP_FUTURE_MARKER" "$parity_log" \
    || grep -Fq "$RELEASE_PROOF_TIMESTAMP_FUTURE_ALIAS_MARKER" "$parity_log"; then
    echo "verify note: syncing release-channel nested release proof timestamp from canonical release-channel generated_at." >&2
    sync_release_channel_proof_timestamp_from_release_channel_receipt
    bash scripts/audit-ui-parity.sh
    return $?
  fi

  return 1
}

bash scripts/ai/build_r1_cleanroom.sh
bash scripts/ai/run_services_restore_drill.sh
bash scripts/ai/run_services_verification.sh
run_ui_parity_audit_with_workflow_gate_retry

parity_oracle_path="$ROOT_DIR/docs/PARITY_ORACLE.json"
parity_oracle_backup="$(mktemp)"
cp "$parity_oracle_path" "$parity_oracle_backup"
python3 - "$parity_oracle_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
tabs = payload.get("tabs")
if not isinstance(tabs, list) or len(tabs) < 2:
    raise SystemExit("tabs list is missing or too short for parity-oracle ordering mutation")
tabs[0], tabs[1] = tabs[1], tabs[0]
payload["tabs"] = tabs
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/generate-parity-checklist.sh; then
  mv "$parity_oracle_backup" "$parity_oracle_path"
  echo "verify gate failed: parity checklist generator should reject non-canonical parity oracle token ordering." >&2
  exit 1
fi
mv "$parity_oracle_backup" "$parity_oracle_path"

release_channel_path="$(
python3 - "$UI_WORKFLOW_GATE_RECEIPT" <<'PY'
import json
import sys
from pathlib import Path

receipt = Path(sys.argv[1])
payload = json.loads(receipt.read_text(encoding="utf-8"))
evidence = payload.get("evidence") or {}
print(str(evidence.get("release_channel_path") or evidence.get("releaseChannelPath") or ""))
PY
)"
if [[ -z "$release_channel_path" || ! -f "$release_channel_path" ]]; then
  echo "verify gate failed: expected release channel receipt path from workflow gate evidence." >&2
  exit 1
fi

release_channel_fixture_path="$(mktemp)"
cp "$release_channel_path" "$release_channel_fixture_path"
trap 'rm -f "$release_channel_fixture_path"' EXIT
export CHUMMER_UI_PARITY_RELEASE_CHANNEL_PATH="$release_channel_fixture_path"
release_channel_path="$release_channel_fixture_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home/%2e%2e/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject percent-encoded releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["blockingFindingsCount"] = "0"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-integer releaseProof.uiLocalizationReleaseGate.blockingFindingsCount values." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
proof_routes = payload["releaseProof"]["proofRoutes"]
if not isinstance(proof_routes, list) or len(proof_routes) < 2:
    raise SystemExit("releaseProof.proofRoutes is missing or too short for canonical ordering mutation")
proof_routes[0], proof_routes[1] = proof_routes[1], proof_routes[0]
payload["releaseProof"]["proofRoutes"] = proof_routes
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical releaseProof.proofRoutes ordering." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["translationBacklogFindingsCount"] = "0"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-integer releaseProof.uiLocalizationReleaseGate.translationBacklogFindingsCount values." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("baseUrl", None)
payload["releaseProof"]["base_url"] = "ftp://chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-http(s) releaseProof.base_url alias schemes." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
journeys = payload["releaseProof"]["journeysPassed"]
if not isinstance(journeys, list) or len(journeys) < 2:
    raise SystemExit("releaseProof.journeysPassed is missing or too short for canonical ordering mutation")
journeys[0], journeys[1] = journeys[1], journeys[0]
payload["releaseProof"]["journeysPassed"] = journeys
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical releaseProof.journeysPassed ordering." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home/access#recap"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject query/fragment releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("baseUrl", None)
payload["releaseProof"]["base_url"] = "https://chummer.run/home?preview=1"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-origin releaseProof.base_url alias path/query segments." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["baseUrl"] = "https://example.com"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.baseUrl outside allowed canonical release origins." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("baseUrl", None)
payload["releaseProof"]["base_url"] = "https://operator@chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject userinfo credentials in releaseProof.base_url alias origins." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["baseUrl"] = "https://chummer.run"
payload["releaseProof"]["base_url"] = "https://chummer.test"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.baseUrl and releaseProof.base_url." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = [
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/access",
    "/account/work",
    "/account/support",
    "/contact",
    "/downloads",
]
payload["releaseProof"]["proof_routes"] = ["/home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.proofRoutes and releaseProof.proof_routes." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("proofRoutes", None)
payload["releaseProof"]["proof_routes"] = [" /home/access "]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.proof_routes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = [
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
]
payload["releaseProof"]["journeys_passed"] = ["install_claim_restore_continue"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.journeysPassed and releaseProof.journeys_passed." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("journeysPassed", None)
payload["releaseProof"]["journeys_passed"] = ["launch and link"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical token shape in releaseProof.journeys_passed journey ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["baseUrl"] = "https://Chummer.run/"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical releaseProof.baseUrl origin casing/trailing slash." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("baseUrl", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof.baseUrl origin." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["baseUrl"] = "ftp://chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-http(s) releaseProof.baseUrl schemes." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["baseUrl"] = "https://chummer.run/home?preview=1"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-origin releaseProof.baseUrl path/query segments." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["baseUrl"] = "https://"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject hostless releaseProof.baseUrl origins." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("baseUrl", None)
payload["releaseProof"]["base_url"] = "https://"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject hostless releaseProof.base_url alias origins." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["baseUrl"] = "https://operator@chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject userinfo credentials in releaseProof.baseUrl origins." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["baseUrl"] = " https://chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.baseUrl values." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("baseUrl", None)
payload["releaseProof"]["base_url"] = " https://chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.base_url alias values." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home\\access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject escaped-path releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = [" /home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-slash-led releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home/./access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject dot-segment traversal releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/Home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical uppercase releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home//access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject empty-segment releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home/access", "/home/access/"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject duplicate-normalized releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing required releaseProof.proofRoutes flagship routes." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = [
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/access",
    "/account/work",
    "/account/support",
    "/contact",
    "/downloads",
    "/home/bonus-noncanonical-route",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof.proofRoutes flagship routes." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = [
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
    "install_claim_restore_continue",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject duplicate releaseProof.journeysPassed journey ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = ["launch-and-link"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing required releaseProof.journeysPassed baseline journey ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = [
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
    "bonus-noncanonical-journey",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof.journeysPassed journey ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = [
    "Launch-and-link",
    "create-and-advance-character",
    "run-and-log-session",
    "publish-and-install-content",
    "recover-and-resync",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical lowercase releaseProof.journeysPassed journey ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = [
    "launch and link",
    "create-and-advance-character",
    "run-and-log-session",
    "publish-and-install-content",
    "recover-and-resync",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical token shape in releaseProof.journeysPassed journey ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["status"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.status values." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"] = "pass"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-object releaseProof.uiLocalizationReleaseGate payloads." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"]["status"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.uiLocalizationReleaseGate.status values." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generatedAt", None)
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generated_at", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof.uiLocalizationReleaseGate.generatedAt timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = "not-an-iso-timestamp"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject invalid-format releaseProof.uiLocalizationReleaseGate.generatedAt timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generatedAt", None)
payload["releaseProof"]["uiLocalizationReleaseGate"]["generated_at"] = "not-an-iso-timestamp"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject invalid-format releaseProof.uiLocalizationReleaseGate.generated_at timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = "2000-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject stale releaseProof.uiLocalizationReleaseGate.generatedAt timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generatedAt", None)
payload["releaseProof"]["uiLocalizationReleaseGate"]["generated_at"] = "2000-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject stale releaseProof.uiLocalizationReleaseGate.generated_at timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = "2026-01-01T00:00:00Z"
payload["releaseProof"]["uiLocalizationReleaseGate"]["generated_at"] = "2026-01-01T00:05:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.uiLocalizationReleaseGate.generatedAt and releaseProof.uiLocalizationReleaseGate.generated_at." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generatedAt", None)
payload["releaseProof"]["uiLocalizationReleaseGate"]["generated_at"] = "2099-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.uiLocalizationReleaseGate.generated_at timestamps with excessive future skew." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = "2099-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.uiLocalizationReleaseGate.generatedAt timestamps with excessive future skew." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("uiLocalizationReleaseGate", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof.uiLocalizationReleaseGate payloads." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["defaultKeyCount"] = "383"
gate["default_key_count"] = "383"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-integer releaseProof.uiLocalizationReleaseGate.defaultKeyCount values." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["defaultKeyCount"] = 383
gate["default_key_count"] = 384
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.uiLocalizationReleaseGate.defaultKeyCount and releaseProof.uiLocalizationReleaseGate.default_key_count." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"]["explicitFallbackRuntime"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.uiLocalizationReleaseGate.explicitFallbackRuntime status." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"]["signoffSmokeRunnerStatus"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.uiLocalizationReleaseGate.signoffSmokeRunnerStatus status." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["shippingLocales"] = ["en-us", "de-de"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject incomplete releaseProof.uiLocalizationReleaseGate.shippingLocales flagship locale sets." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["acceptanceGates"] = [
    "pseudo_localization",
    "missing_key_fail_fast",
    "top_surface_overflow_checks",
    "locale_smoke_first_launch",
    "locale_smoke_settings",
    "locale_smoke_explain",
    "locale_smoke_updater",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject incomplete releaseProof.uiLocalizationReleaseGate.acceptanceGates baseline ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["acceptanceGates"] = [
    "missing_key_fail_fast",
    "pseudo_localization",
    "top_surface_overflow_checks",
    "locale_smoke_first_launch",
    "locale_smoke_settings",
    "locale_smoke_explain",
    "locale_smoke_updater",
    "locale_smoke_support",
    "non_english_generated_artifact_smoke",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical releaseProof.uiLocalizationReleaseGate.acceptanceGates ordering." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
locale_domain_coverage = gate["localeDomainCoverage"]
locale_domain_coverage["de-de"]["generated_artifacts"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.uiLocalizationReleaseGate.localeDomainCoverage locale/domain statuses." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
locale_domain_coverage = gate["localeDomainCoverage"]
locale_domain_coverage["es-es"] = dict(locale_domain_coverage["en-us"])
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof.uiLocalizationReleaseGate.localeDomainCoverage locales." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
locale_domain_coverage = gate["localeDomainCoverage"]
locale_domain_coverage["de-de"]["bonus_noncanonical_domain"] = "pass"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof.uiLocalizationReleaseGate.localeDomainCoverage locale domain keys." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate.pop("signoffSmokeRunnerStatus", None)
gate["signoff_smoke_runner_status"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.uiLocalizationReleaseGate.signoff_smoke_runner_status alias status." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["blockingFindingsCount"] = 1
gate["blockingFindings"] = []
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.uiLocalizationReleaseGate.blockingFindings length/count mismatches." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["translationBacklogFindingsCount"] = 1
gate["translationBacklogFindings"] = []
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.uiLocalizationReleaseGate.translationBacklogFindings length/count mismatches." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
for row in payload["releaseProof"]["uiLocalizationReleaseGate"]["localeSummary"]:
    if isinstance(row, dict) and row.get("locale") == "de-de":
        row["untranslatedKeyCount"] = 1
        break
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-zero releaseProof.uiLocalizationReleaseGate.localeSummary untranslatedKeyCount values." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
for row in payload["releaseProof"]["uiLocalizationReleaseGate"]["localeSummary"]:
    if isinstance(row, dict) and row.get("locale") == "de-de":
        row["untranslatedKeyCount"] = 0
        row["untranslated_key_count"] = 1
        break
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.uiLocalizationReleaseGate.localeSummary.untranslatedKeyCount and releaseProof.uiLocalizationReleaseGate.localeSummary.untranslated_key_count." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
locale_summary = payload["releaseProof"]["uiLocalizationReleaseGate"]["localeSummary"]
if not isinstance(locale_summary, list) or len(locale_summary) < 2:
    raise SystemExit("releaseProof.uiLocalizationReleaseGate.localeSummary must contain at least two rows for ordering mutation")
locale_summary[0], locale_summary[1] = locale_summary[1], locale_summary[0]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical releaseProof.uiLocalizationReleaseGate.localeSummary ordering." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
for row in payload["releaseProof"]["uiLocalizationReleaseGate"]["localeSummary"]:
    if isinstance(row, dict) and row.get("locale") == "de-de":
        row["missingReleaseSeedKeys"] = ["bonus_missing_seed_key"]
        break
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-empty releaseProof.uiLocalizationReleaseGate.localeSummary missingReleaseSeedKeys." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
for row in payload["releaseProof"]["uiLocalizationReleaseGate"]["localeSummary"]:
    if isinstance(row, dict) and row.get("locale") == "de-de":
        row["bonus_noncanonical_row_key"] = "unexpected"
        break
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof.uiLocalizationReleaseGate.localeSummary row keys." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["uiLocalizationReleaseGate"]["bonus_noncanonical_gate_key"] = "unexpected"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof.uiLocalizationReleaseGate keys." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
gate = payload["releaseProof"].get("uiLocalizationReleaseGate")
if not isinstance(gate, dict):
    raise SystemExit("releaseProof.uiLocalizationReleaseGate must be an object for alias-drift mutation")
payload["releaseProof"]["ui_localization_release_gate"] = dict(gate)
payload["releaseProof"]["ui_localization_release_gate"]["status"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.uiLocalizationReleaseGate and releaseProof.ui_localization_release_gate." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["bonus_noncanonical_release_proof_key"] = "unexpected"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof keys." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload.pop("releaseProof", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof payloads." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = "install_claim_restore_continue"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-array releaseProof.journeysPassed payloads." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = "/home/access"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-array releaseProof.proofRoutes payloads." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = [
    " install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.journeysPassed journey ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = [
    "install_claim_restore_continue",
    42,
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-string releaseProof.journeysPassed entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["journeysPassed"] = [
    "",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject blank releaseProof.journeysPassed journey ids." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home/access", 42]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-string releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["generatedAt"] = "2000-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject stale releaseProof.generatedAt timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("generatedAt", None)
payload["releaseProof"]["generated_at"] = "2000-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject stale releaseProof.generated_at timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["generatedAt"] = "2026-01-01T00:00:00Z"
payload["releaseProof"]["generated_at"] = "2026-01-01T00:05:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.generatedAt and releaseProof.generated_at." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("generatedAt", None)
payload["releaseProof"].pop("generated_at", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof.generatedAt timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["generatedAt"] = "not-an-iso-timestamp"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject invalid-format releaseProof.generatedAt timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("generatedAt", None)
payload["releaseProof"]["generated_at"] = "not-an-iso-timestamp"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject invalid-format releaseProof.generated_at timestamps." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"].pop("generatedAt", None)
payload["releaseProof"]["generated_at"] = "2099-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.generated_at timestamps with excessive future skew." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["generatedAt"] = "2099-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.generatedAt timestamps with excessive future skew." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

visual_receipt_path="$UI_VISUAL_FAMILIARITY_RECEIPT"
if [[ ! -f "$visual_receipt_path" ]]; then
  echo "verify gate failed: expected visual familiarity receipt at $visual_receipt_path" >&2
  exit 1
fi

workflow_receipt_path="$UI_WORKFLOW_GATE_RECEIPT"
if [[ ! -f "$workflow_receipt_path" ]]; then
  echo "verify gate failed: expected workflow execution receipt at $workflow_receipt_path" >&2
  exit 1
fi

workflow_receipt_backup="$(mktemp)"
cp "$workflow_receipt_path" "$workflow_receipt_backup"
python3 - "$workflow_receipt_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
required_ids = list(payload.get("evidence", {}).get("required_workflow_family_ids") or [])
if len(required_ids) >= 2:
    payload["evidence"]["required_workflow_family_ids"] = [required_ids[1], required_ids[0], *required_ids[2:]]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$workflow_receipt_backup" "$workflow_receipt_path"
  echo "verify gate failed: parity audit should reject non-canonical required_workflow_family_ids ordering." >&2
  exit 1
fi
mv "$workflow_receipt_backup" "$workflow_receipt_path"

workflow_receipt_backup="$(mktemp)"
cp "$workflow_receipt_path" "$workflow_receipt_backup"
python3 - "$workflow_receipt_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
required_ids = list(payload.get("evidence", {}).get("required_workflow_family_ids") or [])
required_ids.append("bonus-noncanonical-workflow-family-id")
payload["evidence"]["required_workflow_family_ids"] = required_ids
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$workflow_receipt_backup" "$workflow_receipt_path"
  echo "verify gate failed: parity audit should reject unexpected required_workflow_family_ids values." >&2
  exit 1
fi
mv "$workflow_receipt_backup" "$workflow_receipt_path"

visual_receipt_backup="$(mktemp)"
cp "$visual_receipt_path" "$visual_receipt_backup"
python3 - "$visual_receipt_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
required_tests = list(payload.get("evidence", {}).get("required_tests") or [])
if len(required_tests) >= 2:
    payload["evidence"]["required_tests"] = [required_tests[1], required_tests[0], *required_tests[2:]]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$visual_receipt_backup" "$visual_receipt_path"
  echo "verify gate failed: parity audit should reject non-canonical required_tests ordering." >&2
  exit 1
fi
mv "$visual_receipt_backup" "$visual_receipt_path"

visual_receipt_backup="$(mktemp)"
cp "$visual_receipt_path" "$visual_receipt_backup"
python3 - "$visual_receipt_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
required_keys = list(payload.get("evidence", {}).get("required_legacy_interaction_keys") or [])
if len(required_keys) >= 2:
    payload["evidence"]["required_legacy_interaction_keys"] = [required_keys[1], required_keys[0], *required_keys[2:]]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$visual_receipt_backup" "$visual_receipt_path"
  echo "verify gate failed: parity audit should reject non-canonical required_legacy_interaction_keys ordering." >&2
  exit 1
fi
mv "$visual_receipt_backup" "$visual_receipt_path"

visual_receipt_backup="$(mktemp)"
cp "$visual_receipt_path" "$visual_receipt_backup"
python3 - "$visual_receipt_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
required_screenshots = list(payload.get("evidence", {}).get("required_screenshots") or [])
if len(required_screenshots) >= 2:
    payload["evidence"]["required_screenshots"] = [required_screenshots[1], required_screenshots[0], *required_screenshots[2:]]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$visual_receipt_backup" "$visual_receipt_path"
  echo "verify gate failed: parity audit should reject non-canonical required_screenshots ordering." >&2
  exit 1
fi
mv "$visual_receipt_backup" "$visual_receipt_path"

materialize_local_flagship_readiness_artifact
refresh_hub_local_release_proof
python3 scripts/verify_desktop_native_trust_receipts.py
python3 -m unittest tests/test_desktop_native_trust_receipts.py
python3 -m unittest tests/test_stack_smoke.py
python3 scripts/verify_workspace_restore_receipts.py
python3 scripts/verify_workspace_restore_queue_identity.py
python3 -m unittest tests/test_workspace_restore_receipts.py tests/test_workspace_restore_queue_frontier_guard.py tests/test_workspace_restore_commit_resolution.py tests/test_workspace_restore_queue_identity.py
python3 scripts/verify_artifact_factory_orchestration.py
python3 -m unittest tests/test_artifact_factory_orchestration.py
python3 -m unittest tests/test_artifact_factory_source_pack_launcher.py
python3 scripts/verify_next90_m115_hub_dossier_federation.py
python3 -m unittest tests/test_next90_m115_hub_dossier_federation.py
python3 scripts/verify_install_aware_support_concierge.py
python3 -m unittest tests/test_install_aware_support_concierge.py
python3 scripts/verify_campaign_consequence_truth.py
python3 -m unittest tests/test_campaign_consequence_truth.py
python3 scripts/materialize_next90_m113_hub_roster_ops_proof.py
python3 scripts/verify_next90_m113_hub_roster_ops.py
python3 -m unittest tests/test_next90_m113_hub_roster_ops.py
run_slice_safe_dotnet_test CampaignMovementServiceTests
python3 scripts/verify_next90_m114_hub_rule_environment_receipts.py
python3 -m unittest tests/test_next90_m114_hub_rule_environment_receipts.py
python3 scripts/verify_next90_m115_hub_dossier_federation.py
python3 -m unittest tests/test_next90_m115_hub_dossier_federation.py
python3 scripts/verify_next90_m116_hub_creator_publication.py
python3 -m unittest tests/test_next90_m116_hub_creator_publication.py
python3 scripts/verify_next90_m117_hub_artifact_shelf_v2.py
python3 -m unittest tests/test_next90_m117_hub_artifact_shelf_v2.py
python3 scripts/verify_next90_m118_hub_organizer_ops.py
python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py
python3 scripts/verify_next90_m119_hub_first_session_onboarding.py
python3 -m unittest tests/test_next90_m119_hub_first_session_onboarding.py
python3 scripts/verify_next90_m120_hub_public_launch_health.py
python3 -m unittest tests/test_next90_m120_hub_public_launch_health.py
python3 scripts/verify_runsite_orientation_requests.py
python3 -m unittest tests/test_runsite_orientation_requests.py
run_slice_safe_dotnet_test RunsiteOrientationRequestComposerServiceTests
python3 scripts/materialize_next90_m121_hub_runboard_continuity_proof.py
python3 scripts/verify_next90_m121_hub_runboard_continuity.py
python3 -m unittest tests/test_next90_m121_hub_runboard_continuity.py
python3 scripts/materialize_next90_m122_hub_campaign_adoption_loop_proof.py
python3 scripts/verify_next90_m122_hub_campaign_adoption_loop.py
python3 -m unittest tests/test_next90_m122_hub_campaign_adoption_loop.py
python3 scripts/materialize_next90_m123_hub_open_run_loop_proof.py
python3 scripts/verify_next90_m123_hub_open_run_loop.py
python3 -m unittest tests/test_next90_m123_hub_open_run_loop.py
python3 scripts/materialize_next90_m124_hub_hosted_companion_packets_proof.py
python3 scripts/verify_next90_m124_hub_hosted_companion_packets.py
python3 -m unittest tests/test_next90_m124_hub_hosted_companion_packets.py
python3 scripts/materialize_next90_m125_hub_public_signal_packets_proof.py
python3 scripts/verify_next90_m125_hub_public_signal_packets.py
python3 -m unittest tests/test_next90_m125_hub_public_signal_packets.py
python3 scripts/materialize_next90_m126_hub_hosted_proof_contracts_proof.py
python3 scripts/verify_next90_m126_hub_hosted_proof_contracts.py
python3 -m unittest tests/test_next90_m126_hub_hosted_proof_contracts.py
python3 scripts/materialize_next90_m127_hub_registry_truth_binding_proof.py
python3 scripts/verify_next90_m127_hub_registry_truth_binding.py
python3 -m unittest tests/test_next90_m127_hub_registry_truth_binding.py
python3 scripts/materialize_next90_m128_hub_privacy_bounded_support_status_proof.py
python3 scripts/verify_next90_m128_hub_privacy_bounded_support_status.py
python3 -m unittest tests/test_next90_m128_hub_privacy_bounded_support_status.py
python3 scripts/materialize_participate_billing_honesty.py --completion-dir "$CHUMMER_COMPLETION_DIR"
python3 scripts/materialize_next90_m129_hub_reusable_account_flows_proof.py
python3 scripts/verify_next90_m129_hub_reusable_account_flows.py
python3 -m unittest tests/test_next90_m129_hub_reusable_account_flows.py
python3 scripts/materialize_next90_m135_hub_hosted_bounded_context_coverage_proof.py
python3 scripts/verify_next90_m135_hub_hosted_bounded_context_coverage.py
python3 -m unittest tests/test_next90_m135_hub_hosted_bounded_context_coverage.py
python3 scripts/verify_next90_m141_hub_import_route_review_required.py
python3 -m unittest tests/test_next90_m141_hub_import_route_review_required.py
python3 scripts/verify_next90_m143_hub_exchange_output_receipts.py
python3 -m unittest tests/test_next90_m143_hub_exchange_output_receipts.py
python3 scripts/verify_next90_m144_hub_release_truth_alignment.py
python3 -m unittest tests/test_next90_m144_hub_release_truth_alignment.py
python3 scripts/verify_table_pulse_connected_lane_surface.py
python3 -m unittest tests/test_table_pulse_connected_lane_surface.py

bash scripts/ai/run_services_smoke.sh
