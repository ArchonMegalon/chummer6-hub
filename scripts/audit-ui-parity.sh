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
REQUIRED_RELEASE_PROOF_JOURNEYS = (
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
)
REQUIRED_RELEASE_PROOF_ROUTES = (
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/work",
    "/account/support",
    "/contact",
)


def require_object(value: object, *, message: str) -> dict:
    if not isinstance(value, dict):
        raise SystemExit(message)
    return value


def require_string_list(value: object, *, message: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(message)
    return value


def require_canonical_unique_string_list(
    values: list[str],
    *,
    field_name: str,
    path: pathlib.Path,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for index, value in enumerate(values):
        if value != value.strip():
            raise SystemExit(
                f"parity audit failed: {field_name}[{index}] must not include leading/trailing whitespace: {path}"
            )
        token = value.strip()
        if not token:
            raise SystemExit(f"parity audit failed: {field_name}[{index}] must not be blank: {path}")
        normalized.append(token)
        if token in seen:
            duplicates.add(token)
        seen.add(token)
    if duplicates:
        raise SystemExit(
            f"parity audit failed: {field_name} must not contain duplicate ids: {path} ({', '.join(sorted(duplicates))})"
        )
    return normalized


def require_pass_status(value: object, *, message: str) -> None:
    normalized = str(value or "").strip().lower()
    if normalized not in {"pass", "passed", "ready"}:
        raise SystemExit(message + f" (status={normalized or 'missing'})")


def require_non_empty_string(value: object, *, message: str) -> str:
    parsed = str(value or "").strip()
    if not parsed:
        raise SystemExit(message)
    return parsed


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


def require_int_at_least(value: object, *, minimum: int, message: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(message) from exc
    if parsed < minimum:
        raise SystemExit(f"{message} (value={parsed}, minimum={minimum})")
    return parsed


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


def require_string_map(value: object, *, message: str) -> dict[str, str]:
    mapping = require_object(value, message=message)
    normalized: dict[str, str] = {}
    for raw_key, raw_value in mapping.items():
        if not isinstance(raw_key, str):
            raise SystemExit(message)
        key = raw_key.strip()
        if not key:
            raise SystemExit(message)
        parsed_value = str(raw_value or "").strip()
        if not parsed_value:
            raise SystemExit(message)
        normalized[key] = parsed_value
    return normalized


def normalized_token(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_release_proof_route(raw_route: object, *, field_path: str, source: pathlib.Path) -> str:
    if not isinstance(raw_route, str):
        raise SystemExit(f"parity audit failed: {field_path} must be a string: {source}")
    route = raw_route.strip()
    if not route:
        raise SystemExit(f"parity audit failed: {field_path} must not be blank: {source}")
    if not route.startswith("/"):
        raise SystemExit(f"parity audit failed: {field_path} must be a slash-led route path: {source}")
    if any(character.isspace() for character in route):
        raise SystemExit(f"parity audit failed: {field_path} must not include whitespace: {source}")
    if "?" in route or "#" in route:
        raise SystemExit(
            f"parity audit failed: {field_path} must not include query or fragment segments: {source}"
        )
    if "//" in route:
        raise SystemExit(f"parity audit failed: {field_path} must not include empty path segments: {source}")
    segments = route.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise SystemExit(f"parity audit failed: {field_path} must not include dot-segment traversal: {source}")
    canonical_route = route.lower()
    if canonical_route != "/":
        canonical_route = canonical_route.rstrip("/")
        if not canonical_route:
            canonical_route = "/"
    return canonical_route


def validate_release_channel_proof(release_channel_path: pathlib.Path, release_channel_data: dict) -> None:
    proof = require_object(
        release_channel_data.get("releaseProof"),
        message=(
            "parity audit failed: release-channel nested receipt releaseProof is required: "
            f"{release_channel_path}"
        ),
    )
    proof_status = normalized_token(proof.get("status"))
    if proof_status not in {"pass", "passed", "ready"}:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.status must be pass/passed/ready: "
            f"{release_channel_path} (status={proof_status or 'missing'})"
        )
    journeys_passed = proof.get("journeysPassed") or proof.get("journeys_passed")
    journeys = require_string_list(
        journeys_passed,
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must be a string array: "
            f"{release_channel_path}"
        ),
    )
    normalized_journeys = [normalized_token(journey) for journey in journeys]
    if any(not journey for journey in normalized_journeys):
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must not contain blank ids: "
            f"{release_channel_path}"
        )
    duplicate_journeys = sorted(
        journey for journey in set(normalized_journeys) if normalized_journeys.count(journey) > 1
    )
    if duplicate_journeys:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must not contain duplicate ids: "
            f"{release_channel_path} ({', '.join(duplicate_journeys)})"
        )
    missing_required_journeys = sorted(
        journey for journey in REQUIRED_RELEASE_PROOF_JOURNEYS if journey not in normalized_journeys
    )
    if missing_required_journeys:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.journeysPassed is missing required baseline journey ids: "
            f"{release_channel_path} ({', '.join(missing_required_journeys)})"
        )
    proof_routes = proof.get("proofRoutes") or proof.get("proof_routes")
    raw_routes = require_string_list(
        proof_routes,
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.proofRoutes must be a string array: "
            f"{release_channel_path}"
        ),
    )
    normalized_routes: list[str] = []
    for index, raw_route in enumerate(raw_routes):
        normalized_routes.append(
            normalize_release_proof_route(
                raw_route,
                field_path=f"releaseProof.proofRoutes[{index}]",
                source=release_channel_path,
            )
        )
    duplicate_routes = sorted(
        route for route in set(normalized_routes) if normalized_routes.count(route) > 1
    )
    if duplicate_routes:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.proofRoutes must not contain duplicate routes after normalization: "
            f"{release_channel_path} ({', '.join(duplicate_routes)})"
        )
    missing_required_routes = sorted(
        route for route in REQUIRED_RELEASE_PROOF_ROUTES if route not in normalized_routes
    )
    if missing_required_routes:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.proofRoutes is missing required flagship routes: "
            f"{release_channel_path} ({', '.join(missing_required_routes)})"
        )


def require_all_values_equal(
    value: object,
    *,
    expected: str,
    message: str,
) -> None:
    mapping = require_string_map(value, message=message)
    for key, item in mapping.items():
        if item != expected:
            raise SystemExit(f"{message}: {key}={item!r}, expected={expected!r}")


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


def read_release_channel_status(path: pathlib.Path, data: dict) -> str:
    status = str(data.get("status", "")).strip().lower()
    if status not in {"pass", "passed", "ready", "published"}:
        raise SystemExit(
            "parity audit failed: release-channel receipt status must be pass/passed/ready/published: "
            f"{path} (status={status or 'missing'})"
        )
    return status


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


def resolve_nested_receipt_path(parent_path: pathlib.Path, raw_path: str) -> pathlib.Path:
    nested = pathlib.Path(raw_path).expanduser()
    if not nested.is_absolute():
        nested = (parent_path.parent / nested).resolve()
    return nested


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
    release_channel_channel_id = require_non_empty_string(
        evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: workflow receipt release-channel channel id is missing: {path}",
    )
    require_non_empty_string(
        evidence.get("release_channel_version"),
        message=f"parity audit failed: workflow receipt release-channel version is missing: {path}",
    )
    release_channel_path_raw = require_non_empty_string(
        evidence.get("release_channel_path"),
        message=f"parity audit failed: workflow receipt release-channel path is missing: {path}",
    )
    release_channel_path = resolve_nested_receipt_path(path, release_channel_path_raw)
    release_channel_data = read_receipt(release_channel_path)
    read_release_channel_status(release_channel_path, release_channel_data)
    validate_release_channel_proof(release_channel_path, release_channel_data)
    release_channel_id = require_non_empty_string(
        release_channel_data.get("channelId"),
        message=(
            "parity audit failed: workflow receipt release-channel nested receipt channelId is missing: "
            f"{path} ({release_channel_path})"
        ),
    )
    workflow_release_channel_id = require_non_empty_string(
        evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: workflow receipt release-channel channel id is missing: {path}",
    )
    if release_channel_id != workflow_release_channel_id:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel channel id drifts from nested receipt: "
            f"{path} ({workflow_release_channel_id}) vs {release_channel_path} ({release_channel_id})"
        )
    release_channel_version = require_non_empty_string(
        release_channel_data.get("version"),
        message=(
            "parity audit failed: workflow receipt release-channel nested receipt version is missing: "
            f"{path} ({release_channel_path})"
        ),
    )
    workflow_release_channel_version = require_non_empty_string(
        evidence.get("release_channel_version"),
        message=f"parity audit failed: workflow receipt release-channel version is missing: {path}",
    )
    if release_channel_version != workflow_release_channel_version:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel version drifts from nested receipt: "
            f"{path} ({workflow_release_channel_version}) vs {release_channel_path} ({release_channel_version})"
        )
    workflow_release_channel_generated_at = parse_generated_at(
        path,
        {"generatedAt": evidence.get("release_channel_generated_at")},
    )
    release_channel_generated_at = parse_generated_at(release_channel_path, release_channel_data)
    if workflow_release_channel_generated_at != release_channel_generated_at:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel generated_at drifts from nested receipt generatedAt: "
            f"{path} (evidence_generated_at={workflow_release_channel_generated_at.isoformat()}, "
            f"nested_generated_at={release_channel_generated_at.isoformat()}, "
            f"nested_receipt={release_channel_path})"
        )
    now = dt.datetime.now(UTC)
    release_channel_age_seconds = int((now - release_channel_generated_at).total_seconds())
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
    if release_channel_age_seconds > max_age_seconds:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel nested receipt generatedAt is stale: "
            f"{path} (age_seconds={release_channel_age_seconds}, "
            f"max_age_seconds={max_age_seconds}, nested_receipt={release_channel_path})"
        )
    if release_channel_age_seconds < -max_future_skew_seconds:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel nested receipt generatedAt is in the future: "
            f"{path} (future_skew_seconds={abs(release_channel_age_seconds)}, "
            f"max_future_skew_seconds={max_future_skew_seconds}, nested_receipt={release_channel_path})"
        )
    require_all_values_equal(
        evidence.get("workflow_parity_receipt_channel_ids"),
        expected=workflow_release_channel_id,
        message=f"parity audit failed: workflow parity receipt channel ids drift from release-channel channel id: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_malformed_entries"),
        message=f"parity audit failed: workflow receipt has malformed flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_non_canonical_keys"),
        message=f"parity audit failed: workflow receipt has non-canonical flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_duplicate_normalized_keys"),
        message=f"parity audit failed: workflow receipt has duplicate normalized flagship head proof status keys: {path}",
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
        evidence.get("workflow_execution_weak_receipts"),
        message=f"parity audit failed: workflow receipt reports weakly grounded execution receipts: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_family_missing_receipts"),
        message=f"parity audit failed: workflow receipt reports missing workflow-family receipts: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_family_failing_receipts"),
        message=f"parity audit failed: workflow receipt reports failing workflow-family receipts: {path}",
    )
    require_int_at_least(
        evidence.get("workflow_family_receipt_count_checked"),
        minimum=1,
        message=f"parity audit failed: workflow receipt must check at least one workflow-family receipt: {path}",
    )
    require_int_at_least(
        evidence.get("workflow_execution_receipt_count_checked"),
        minimum=1,
        message=f"parity audit failed: workflow receipt must check at least one workflow execution receipt: {path}",
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
        evidence.get("sr6_workflow_parity_status"),
        message=f"parity audit failed: workflow receipt sr6 parity proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("chummer5a_workflow_parity_status"),
        message=f"parity audit failed: workflow receipt chummer5a parity proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("sr4_sr6_frontier_status"),
        message=f"parity audit failed: workflow receipt sr4/sr6 frontier proof is not pass-ready: {path}",
    )
    workflow_parity_proof_max_age_seconds = read_int_value(
        evidence,
        "workflow_parity_proof_max_age_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS,
        path=path,
    )
    for prefix, label in (
        ("sr4_workflow_parity", "sr4 workflow parity"),
        ("sr6_workflow_parity", "sr6 workflow parity"),
        ("chummer5a_workflow_parity", "chummer5a workflow parity"),
        ("sr4_sr6_frontier", "sr4/sr6 frontier parity"),
    ):
        nested_path_raw = require_non_empty_string(
            evidence.get(f"{prefix}_path"),
            message=(
                f"parity audit failed: workflow receipt {label} evidence path is missing: {path}"
            ),
        )
        nested_path = resolve_nested_receipt_path(path, nested_path_raw)
        nested_data = read_receipt(nested_path)
        read_status(nested_path, nested_data)
        nested_generated_at = parse_generated_at(
            path,
            {"generatedAt": evidence.get(f"{prefix}_generated_at")},
        )
        nested_receipt_generated_at = parse_generated_at(nested_path, nested_data)
        if nested_receipt_generated_at != nested_generated_at:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} evidence generated_at drifts from nested receipt generatedAt: {path} "
                f"(evidence_generated_at={nested_generated_at.isoformat()}, "
                f"nested_generated_at={nested_receipt_generated_at.isoformat()}, "
                f"nested_receipt={nested_path})"
            )
        nested_age_seconds = require_int_at_least(
            evidence.get(f"{prefix}_age_seconds"),
            minimum=0,
            message=(
                f"parity audit failed: workflow receipt {label} evidence age must be an integer >= 0: {path}"
            ),
        )
        if nested_age_seconds > workflow_parity_proof_max_age_seconds:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} evidence age exceeds allowed freshness window: {path} "
                f"(age_seconds={nested_age_seconds}, "
                f"max_age_seconds={workflow_parity_proof_max_age_seconds})"
            )
        now = dt.datetime.now(UTC)
        computed_age_seconds = int((now - nested_generated_at).total_seconds())
        nested_receipt_age_seconds = int((now - nested_receipt_generated_at).total_seconds())
        if computed_age_seconds > workflow_parity_proof_max_age_seconds:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} evidence generated_at is stale: {path} "
                f"(age_seconds={computed_age_seconds}, "
                f"max_age_seconds={workflow_parity_proof_max_age_seconds})"
            )
        if computed_age_seconds < -DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} evidence generated_at is in the future: {path} "
                f"(future_skew_seconds={abs(computed_age_seconds)}, "
                f"max_future_skew_seconds={DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS})"
            )
        if nested_receipt_age_seconds > workflow_parity_proof_max_age_seconds:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} nested receipt generatedAt is stale: {path} "
                f"(age_seconds={nested_receipt_age_seconds}, "
                f"max_age_seconds={workflow_parity_proof_max_age_seconds}, "
                f"nested_receipt={nested_path})"
            )
        if nested_receipt_age_seconds < -DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} nested receipt generatedAt is in the future: {path} "
                f"(future_skew_seconds={abs(nested_receipt_age_seconds)}, "
                f"max_future_skew_seconds={DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS}, "
                f"nested_receipt={nested_path})"
            )
    validate_timestamp_freshness(path, data, evidence)


def validate_visual_contract(path: pathlib.Path, data: dict) -> None:
    evidence = require_object(
        data.get("evidence"),
        message=f"parity audit failed: visual receipt evidence must be a JSON object: {path}",
    )
    required_tests = require_canonical_unique_string_list(
        require_string_list(
            evidence.get("required_tests"),
            message=f"parity audit failed: visual receipt required_tests must be a string array: {path}",
        ),
        field_name="visual receipt required_tests",
        path=path,
    )
    expected_required_tests = {
        "Desktop_shell_preserves_chummer5a_familiarity_cues",
        "Desktop_shell_preserves_classic_dense_three_pane_workbench_posture",
        "Theme_tokens_preserve_chummer5a_palette_and_readability",
        "Loaded_runner_preserves_visible_character_tab_posture",
        "Loaded_runner_header_stays_tab_panel_only_without_metric_cards",
        "Loaded_runner_workbench_preserves_legacy_frmcareer_landmarks",
        "Character_creation_preserves_familiar_dense_builder_rhythm",
        "Advancement_and_karma_journal_workflows_preserve_familiar_progression_rhythm",
        "Gear_builder_preserves_familiar_browse_detail_confirm_rhythm",
        "Vehicles_and_drones_builder_preserves_familiar_browse_detail_confirm_rhythm",
        "Cyberware_and_cyberlimb_builder_preserve_legacy_dialog_familiarity_cues",
        "Contacts_diary_and_support_routes_execute_with_public_path_visibility",
        "Magic_workflows_execute_with_specific_dialog_fields_and_confirm_actions",
        "Matrix_workflows_execute_with_specific_dialog_fields_and_confirm_actions",
        "Runtime_backed_menu_bar_preserves_classic_labels_and_clickable_primary_menus",
        "Runtime_backed_toolstrip_preserves_classic_labeled_workbench_actions",
        "Runtime_backed_toolstrip_preserves_flat_classic_toolbar_posture",
        "Runtime_backed_codex_tree_preserves_legacy_left_rail_navigation_posture",
        "Runtime_backed_ruleset_switch_preserves_sr4_sr5_and_sr6_codex_landmarks",
        "Runtime_backed_shell_avoids_modern_dashboard_copy_that_breaks_chummer5a_orientation",
        "Runtime_backed_shell_chrome_stays_enabled_after_runner_load",
        "Standalone_toolstrip_buttons_raise_expected_events",
        "Standalone_menu_bar_buttons_and_menu_commands_raise_expected_events",
        "Standalone_workspace_strip_quick_start_button_raises_expected_event",
        "Standalone_summary_header_tab_buttons_raise_expected_events",
        "Standalone_navigator_tree_selection_raises_workspace_tab_section_and_workflow_events",
        "Standalone_command_dialog_pane_routes_command_selection_field_updates_and_dialog_actions",
        "Standalone_coach_sidecar_copy_button_raises_event_when_launch_uri_is_available",
        "Loaded_runner_main_window_routes_navigation_palette_dialog_and_quick_action_surfaces_end_to_end",
    }
    missing_required_tests = sorted(expected_required_tests.difference(required_tests))
    if missing_required_tests:
        raise SystemExit(
            "parity audit failed: visual receipt is missing required milestone-2 visual tests: "
            + ", ".join(missing_required_tests)
            + f" ({path})"
        )
    required_interaction_keys = set(
        require_canonical_unique_string_list(
            require_string_list(
                evidence.get("required_legacy_interaction_keys"),
                message=f"parity audit failed: visual receipt required_legacy_interaction_keys must be a string array: {path}",
            ),
            field_name="visual receipt required_legacy_interaction_keys",
            path=path,
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
    require_non_empty_string(
        evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: visual receipt release-channel channel id is missing: {path}",
    )
    require_non_empty_string(
        evidence.get("release_channel_version"),
        message=f"parity audit failed: visual receipt release-channel version is missing: {path}",
    )
    release_channel_path_raw = require_non_empty_string(
        evidence.get("release_channel_path"),
        message=f"parity audit failed: visual receipt release-channel path is missing: {path}",
    )
    release_channel_path = resolve_nested_receipt_path(path, release_channel_path_raw)
    release_channel_data = read_receipt(release_channel_path)
    read_release_channel_status(release_channel_path, release_channel_data)
    validate_release_channel_proof(release_channel_path, release_channel_data)
    release_channel_id = require_non_empty_string(
        release_channel_data.get("channelId"),
        message=(
            "parity audit failed: visual receipt release-channel nested receipt channelId is missing: "
            f"{path} ({release_channel_path})"
        ),
    )
    visual_release_channel_id = require_non_empty_string(
        evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: visual receipt release-channel channel id is missing: {path}",
    )
    if release_channel_id != visual_release_channel_id:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel channel id drifts from nested receipt: "
            f"{path} ({visual_release_channel_id}) vs {release_channel_path} ({release_channel_id})"
        )
    release_channel_version = require_non_empty_string(
        release_channel_data.get("version"),
        message=(
            "parity audit failed: visual receipt release-channel nested receipt version is missing: "
            f"{path} ({release_channel_path})"
        ),
    )
    visual_release_channel_version = require_non_empty_string(
        evidence.get("release_channel_version"),
        message=f"parity audit failed: visual receipt release-channel version is missing: {path}",
    )
    if release_channel_version != visual_release_channel_version:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel version drifts from nested receipt: "
            f"{path} ({visual_release_channel_version}) vs {release_channel_path} ({release_channel_version})"
        )
    visual_release_channel_generated_at = parse_generated_at(
        path,
        {"generatedAt": evidence.get("release_channel_generated_at")},
    )
    release_channel_generated_at = parse_generated_at(release_channel_path, release_channel_data)
    if visual_release_channel_generated_at != release_channel_generated_at:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel generated_at drifts from nested receipt generatedAt: "
            f"{path} (evidence_generated_at={visual_release_channel_generated_at.isoformat()}, "
            f"nested_generated_at={release_channel_generated_at.isoformat()}, "
            f"nested_receipt={release_channel_path})"
        )
    now = dt.datetime.now(UTC)
    release_channel_age_seconds = int((now - release_channel_generated_at).total_seconds())
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
    if release_channel_age_seconds > max_age_seconds:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel nested receipt generatedAt is stale: "
            f"{path} (age_seconds={release_channel_age_seconds}, "
            f"max_age_seconds={max_age_seconds}, nested_receipt={release_channel_path})"
        )
    if release_channel_age_seconds < -max_future_skew_seconds:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel nested receipt generatedAt is in the future: "
            f"{path} (future_skew_seconds={abs(release_channel_age_seconds)}, "
            f"max_future_skew_seconds={max_future_skew_seconds}, nested_receipt={release_channel_path})"
        )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_malformed_entries"),
        message=f"parity audit failed: visual receipt has malformed flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_non_canonical_keys"),
        message=f"parity audit failed: visual receipt has non-canonical flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_duplicate_normalized_keys"),
        message=f"parity audit failed: visual receipt has duplicate normalized flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("missing_theme_tokens"),
        message=f"parity audit failed: visual receipt reports missing required legacy theme tokens: {path}",
    )
    require_pass_status(
        evidence.get("flagship_theme_readability_contrast"),
        message=f"parity audit failed: visual receipt flagship theme/readability proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_shell_menu"),
        message=f"parity audit failed: visual receipt runtime-backed shell menu proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_menu_bar_labels"),
        message=f"parity audit failed: visual receipt runtime-backed menu bar labels proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_toolstrip_actions"),
        message=f"parity audit failed: visual receipt runtime-backed toolstrip actions proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_tab_panel_only_header"),
        message=f"parity audit failed: visual receipt runtime-backed tab panel header proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_clickable_primary_menus"),
        message=f"parity audit failed: visual receipt runtime-backed clickable menu proof is not pass-ready: {path}",
    )
    require_true_bool(
        evidence.get("loaded_runner_tab_strip_control_present"),
        message=f"parity audit failed: visual receipt loaded runner tab-strip control proof is missing: {path}",
    )
    require_true_bool(
        evidence.get("loaded_runner_tab_posture_control_present"),
        message=f"parity audit failed: visual receipt loaded runner tab-posture control proof is missing: {path}",
    )
    require_empty_collection(
        evidence.get("missing_tests"),
        message=f"parity audit failed: visual receipt reports missing required visual tests: {path}",
    )
    required_screenshots = require_canonical_unique_string_list(
        require_string_list(
            evidence.get("required_screenshots"),
            message=f"parity audit failed: visual receipt required_screenshots must be a string array: {path}",
        ),
        field_name="visual receipt required_screenshots",
        path=path,
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
    screenshot_dir_raw = require_non_empty_string(
        evidence.get("screenshot_dir"),
        message=f"parity audit failed: visual receipt screenshot_dir is missing: {path}",
    )
    screenshot_dir = resolve_nested_receipt_path(path, screenshot_dir_raw)
    if not screenshot_dir.is_dir():
        raise SystemExit(
            f"parity audit failed: visual receipt screenshot_dir does not exist: {path} ({screenshot_dir})"
        )
    screenshot_timestamps = require_object(
        evidence.get("screenshot_timestamps"),
        message=f"parity audit failed: visual receipt screenshot_timestamps must be a JSON object: {path}",
    )
    screenshot_receipt_skew_max_seconds = read_int_value(
        evidence,
        "screenshot_receipt_skew_max_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS,
        path=path,
    )
    for screenshot_name in expected_required_screenshots:
        screenshot_path = screenshot_dir / screenshot_name
        if not screenshot_path.is_file():
            raise SystemExit(
                "parity audit failed: visual receipt required screenshot file is missing on disk: "
                f"{path} ({screenshot_path})"
            )
        timestamp_raw = screenshot_timestamps.get(screenshot_name)
        screenshot_timestamp = parse_generated_at(
            path,
            {"generatedAt": timestamp_raw},
        )
        screenshot_mtime = dt.datetime.fromtimestamp(
            screenshot_path.stat().st_mtime,
            tz=UTC,
        )
        timestamp_skew_seconds = abs(int((screenshot_mtime - screenshot_timestamp).total_seconds()))
        if timestamp_skew_seconds > screenshot_receipt_skew_max_seconds:
            raise SystemExit(
                "parity audit failed: visual receipt screenshot timestamp drifts from on-disk file mtime: "
                f"{path} (screenshot={screenshot_name}, "
                f"timestamp_skew_seconds={timestamp_skew_seconds}, "
                f"max_skew_seconds={screenshot_receipt_skew_max_seconds})"
            )
    validate_timestamp_freshness(path, data, evidence)


def validate_cross_receipt_alignment(
    workflow_path: pathlib.Path,
    workflow_data: dict,
    visual_path: pathlib.Path,
    visual_data: dict,
) -> None:
    workflow_evidence = require_object(
        workflow_data.get("evidence"),
        message=f"parity audit failed: workflow receipt evidence must be a JSON object: {workflow_path}",
    )
    visual_evidence = require_object(
        visual_data.get("evidence"),
        message=f"parity audit failed: visual receipt evidence must be a JSON object: {visual_path}",
    )
    workflow_release_channel_id = require_non_empty_string(
        workflow_evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: workflow receipt release-channel channel id is missing: {workflow_path}",
    )
    visual_release_channel_id = require_non_empty_string(
        visual_evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: visual receipt release-channel channel id is missing: {visual_path}",
    )
    if workflow_release_channel_id != visual_release_channel_id:
        raise SystemExit(
            "parity audit failed: milestone-2 workflow/visual release-channel ids drift: "
            f"{workflow_path} ({workflow_release_channel_id}) vs "
            f"{visual_path} ({visual_release_channel_id})"
        )
    workflow_release_version = require_non_empty_string(
        workflow_evidence.get("release_channel_version"),
        message=f"parity audit failed: workflow receipt release-channel version is missing: {workflow_path}",
    )
    visual_release_version = require_non_empty_string(
        visual_evidence.get("release_channel_version"),
        message=f"parity audit failed: visual receipt release-channel version is missing: {visual_path}",
    )
    if workflow_release_version != visual_release_version:
        raise SystemExit(
            "parity audit failed: milestone-2 workflow/visual release-channel versions drift: "
            f"{workflow_path} ({workflow_release_version}) vs "
            f"{visual_path} ({visual_release_version})"
        )
    workflow_release_channel_path = resolve_nested_receipt_path(
        workflow_path,
        require_non_empty_string(
            workflow_evidence.get("release_channel_path"),
            message=f"parity audit failed: workflow receipt release-channel path is missing: {workflow_path}",
        ),
    )
    visual_release_channel_path = resolve_nested_receipt_path(
        visual_path,
        require_non_empty_string(
            visual_evidence.get("release_channel_path"),
            message=f"parity audit failed: visual receipt release-channel path is missing: {visual_path}",
        ),
    )
    if workflow_release_channel_path != visual_release_channel_path:
        raise SystemExit(
            "parity audit failed: milestone-2 workflow/visual release-channel nested receipt paths drift: "
            f"{workflow_path} ({workflow_release_channel_path}) vs "
            f"{visual_path} ({visual_release_channel_path})"
        )
    workflow_release_channel_generated_at = parse_generated_at(
        workflow_path,
        {"generatedAt": workflow_evidence.get("release_channel_generated_at")},
    )
    visual_release_channel_generated_at = parse_generated_at(
        visual_path,
        {"generatedAt": visual_evidence.get("release_channel_generated_at")},
    )
    if workflow_release_channel_generated_at != visual_release_channel_generated_at:
        raise SystemExit(
            "parity audit failed: milestone-2 workflow/visual release-channel generated_at drift: "
            f"{workflow_path} ({workflow_release_channel_generated_at.isoformat()}) vs "
            f"{visual_path} ({visual_release_channel_generated_at.isoformat()})"
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
validate_cross_receipt_alignment(workflow_path, workflow_data, visual_path, visual_data)
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
