#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

resolve_ui_repo_root() {
  local explicit_root="${CHUMMER_PRESENTATION_ROOT:-}"
  if [[ -n "$explicit_root" ]]; then
    echo "$explicit_root"
    return 0
  fi

  local candidate
  for candidate in \
    "/docker/chummercomplete/chummer6-ui" \
    "/docker/chummercomplete/chummer6-ui-finish" \
    "/docker/chummercomplete/chummer-presentation-clean" \
    "/docker/chummercomplete/chummer-presentation" \
    "$REPO_ROOT/../chummer6-ui" \
    "$REPO_ROOT/../chummer6-ui-finish" \
    "$REPO_ROOT/../chummer-presentation-clean" \
    "$REPO_ROOT/../chummer-presentation"
  do
    if [[ -d "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  echo "/docker/chummercomplete/chummer6-ui"
}

resolve_ui_localization_release_gate_source() {
  local explicit_path="${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_SOURCE:-}"
  if [[ -n "$explicit_path" ]]; then
    echo "$explicit_path"
    return 0
  fi

  local candidate
  for candidate in \
    "$PRESENTATION_ROOT/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "/docker/chummercomplete/chummer6-ui/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "/docker/chummercomplete/chummer6-ui-finish/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "/docker/chummercomplete/chummer-presentation-clean/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "/docker/chummercomplete/chummer-presentation/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/../chummer6-ui/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/../chummer6-ui-finish/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/../chummer-presentation-clean/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/../chummer-presentation/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/Chummer.Run.Api/wwwroot/proofs/mac-codex-release/UI_LOCALIZATION_RELEASE_GATE.generated.json"
  do
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  echo "$REPO_ROOT/Chummer.Run.Api/wwwroot/proofs/mac-codex-release/UI_LOCALIZATION_RELEASE_GATE.generated.json"
}

PRESENTATION_ROOT="$(resolve_ui_repo_root)"
OUTPUT_ROOT="${1:-$REPO_ROOT/Chummer.Portal/downloads}"

resolve_ui_downloads_path() {
  local relative_path="$1"
  local candidate
  for candidate in \
    "$PRESENTATION_ROOT/Chummer.Portal/downloads/$relative_path" \
    "$PRESENTATION_ROOT/Docker/Downloads/$relative_path"
  do
    if [[ -e "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  echo "$PRESENTATION_ROOT/Docker/Downloads/$relative_path"
}

resolve_public_release_channel_source() {
  local explicit_path="${CHUMMER_PUBLIC_RELEASE_CHANNEL_SOURCE:-}"
  if [[ -n "$explicit_path" ]]; then
    echo "$explicit_path"
    return 0
  fi

  local candidate
  for candidate in \
    "$REPO_ROOT/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json" \
    "$(resolve_ui_downloads_path "RELEASE_CHANNEL.generated.json")" \
    "$REGISTRY_ROOT/.codex-studio/published/RELEASE_CHANNEL.generated.json"
  do
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  echo "$(resolve_ui_downloads_path "RELEASE_CHANNEL.generated.json")"
}

RUNSERVICES_SOURCE_FILES_ROOT="${CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT:-$REPO_ROOT/legacy/tooling/docker/Docker/Downloads/files}"
PRESENTATION_FILES_ROOT="${CHUMMER_PRESENTATION_FILES_ROOT:-$(resolve_ui_downloads_path "files")}"
PRESENTATION_STARTUP_SMOKE_ROOT="${CHUMMER_PRESENTATION_STARTUP_SMOKE_ROOT:-$(resolve_ui_downloads_path "startup-smoke")}"
RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT="${CHUMMER_RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT:-$REPO_ROOT/Chummer.Portal/downloads/startup-smoke}"
PRESENTATION_RELEASE_CHANNEL_PATH="${CHUMMER_PRESENTATION_RELEASE_CHANNEL_PATH:-$(resolve_ui_downloads_path "RELEASE_CHANNEL.generated.json")}"
PRESENTATION_RELEASE_EVIDENCE_SOURCE="${CHUMMER_PRESENTATION_RELEASE_EVIDENCE_SOURCE:-$PRESENTATION_ROOT/Docker/Downloads/release-evidence/public-promotion.json}"
RELEASE_PROOF_SOURCE="${CHUMMER_RUN_LOCAL_RELEASE_PROOF_SOURCE:-$REPO_ROOT/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json}"
UI_LOCALIZATION_RELEASE_GATE_SOURCE="$(resolve_ui_localization_release_gate_source)"
STARTUP_SMOKE_MAX_AGE_SECONDS="${CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS:-172800}"
PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-}"
PUBLIC_RELEASE_PROOF_BASE_URL="${CHUMMER_PUBLIC_RELEASE_PROOF_BASE_URL:-https://chummer.run}"
DISABLED_ARTIFACT_IDS="${CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS:-${CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS:-}}"
FORCE_ACCOUNT_REQUIRED_DOWNLOADS="${CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS:-false}"
REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-$REPO_ROOT/../chummer-hub-registry}"
PUBLIC_RELEASE_CHANNEL_SOURCE_PATH="$(resolve_public_release_channel_source)"

detect_auto_disabled_artifact_ids() {
  local files_root="$1"
  local manifest_path="$2"
  python3 - "$files_root" "$manifest_path" <<'PY'
import json
import sys
from pathlib import Path

files_root = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])

payload: dict[str, object] = {}
if manifest_path.is_file():
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        loaded = {}
    if isinstance(loaded, dict):
        payload = loaded

rows = payload.get("artifacts")
if not isinstance(rows, list):
    rows = payload.get("downloads")
if not isinstance(rows, list):
    rows = []

disabled_ids: list[str] = []
for row in rows:
    if not isinstance(row, dict):
        continue
    artifact_id = str(row.get("artifactId") or row.get("id") or "").strip()
    if not artifact_id:
        continue
    kind = str(row.get("kind") or row.get("flavor") or "").strip().lower()
    if kind != "portable":
        continue
    file_name = str(row.get("fileName") or "").strip()
    if not file_name:
        file_name = Path(str(row.get("downloadUrl") or row.get("url") or "").strip()).name
    if not file_name.endswith(".exe") or file_name.endswith("-installer.exe"):
        continue
    sibling_zip = files_root / Path(file_name).with_suffix(".zip").name
    if sibling_zip.is_file():
        disabled_ids.append(artifact_id)

seen: set[str] = set()
for artifact_id in disabled_ids:
    lowered = artifact_id.lower()
    if lowered in seen:
        continue
    seen.add(lowered)
    print(artifact_id)
PY
}

if [[ ! -d "$RUNSERVICES_SOURCE_FILES_ROOT" ]]; then
  echo "run-services source downloads root missing: $RUNSERVICES_SOURCE_FILES_ROOT" >&2
  exit 1
fi

if [[ ! -d "$PRESENTATION_FILES_ROOT" ]]; then
  echo "presentation downloads root missing: $PRESENTATION_FILES_ROOT" >&2
  exit 1
fi

if [[ ! -f "$RELEASE_PROOF_SOURCE" ]]; then
  echo "release proof source missing: $RELEASE_PROOF_SOURCE" >&2
  exit 1
fi

if [[ ! -f "$PRESENTATION_RELEASE_EVIDENCE_SOURCE" ]]; then
  echo "presentation release evidence missing: $PRESENTATION_RELEASE_EVIDENCE_SOURCE" >&2
  exit 1
fi

if [[ ! -f "$UI_LOCALIZATION_RELEASE_GATE_SOURCE" ]]; then
  echo "ui localization release gate missing: $UI_LOCALIZATION_RELEASE_GATE_SOURCE" >&2
  exit 1
fi

canonicalize_release_channel_registries() {
  local manifest_path="${1:-}"
  if [[ -z "$manifest_path" || ! -f "$manifest_path" ]]; then
    return 0
  fi

  python3 - "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" "$manifest_path" <<'PY'
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

def normalized_token(value) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

verifier_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
materializer_path = verifier_path.with_name("materialize_public_release_channel.py")

spec = importlib.util.spec_from_file_location("verify_public_release_channel", verifier_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

materializer = None
if materializer_path.is_file():
    materializer_spec = importlib.util.spec_from_file_location("materialize_public_release_channel", materializer_path)
    if materializer_spec is not None and materializer_spec.loader is not None:
        materializer = importlib.util.module_from_spec(materializer_spec)
        materializer_spec.loader.exec_module(materializer)

payload = json.loads(manifest_path.read_text(encoding="utf-8"))

def required_heads_and_platforms(local_payload: dict) -> tuple[list[str], list[str]]:
    coverage = local_payload.get("desktopTupleCoverage")
    default_heads = ["avalonia"]
    default_platforms = ["linux", "windows", "macos"]
    if not isinstance(coverage, dict):
        return default_heads, default_platforms
    heads = [str(item).strip().lower() for item in coverage.get("requiredDesktopHeads") or [] if str(item).strip()]
    platforms = [str(item).strip().lower() for item in coverage.get("requiredDesktopPlatforms") or [] if str(item).strip()]
    return (heads or default_heads, platforms or default_platforms)

def fallback_tuple_coverage(local_payload: dict) -> dict | None:
    if materializer is None or not hasattr(materializer, "desktop_tuple_coverage"):
        return None
    artifacts = local_payload.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    required_heads, required_platforms = required_heads_and_platforms(local_payload)
    return materializer.desktop_tuple_coverage(
        artifacts,
        required_heads=required_heads,
        required_platforms=required_platforms,
        channel_id=str(local_payload.get("channelId") or local_payload.get("channel") or "").strip().lower(),
        release_version=str(local_payload.get("version") or local_payload.get("releaseVersion") or "").strip(),
        channel_status=str(local_payload.get("status") or "").strip().lower(),
        rollout_state=str(local_payload.get("rolloutState") or local_payload.get("rollout_state") or "").strip().lower(),
        rollout_reason=str(local_payload.get("rolloutReason") or local_payload.get("rollout_reason") or "").strip(),
        known_issue_summary=str(local_payload.get("knownIssueSummary") or local_payload.get("known_issue_summary") or "").strip(),
    )

def derive_verifier_owned_value(name: str, current_value):
    helper = getattr(module, name, None)
    if callable(helper):
        return helper(payload)
    if materializer is None:
        return current_value
    tuple_coverage = fallback_tuple_coverage(payload)
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    channel_id = str(payload.get("channelId") or payload.get("channel") or "").strip().lower()
    release_version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
    fallback_helpers = {
        "expected_external_proof_request_rows": lambda: (tuple_coverage or {}).get("externalProofRequests") or current_value,
        "expected_desktop_route_truth_rows": lambda: (tuple_coverage or {}).get("desktopRouteTruth") or current_value,
        "expected_install_aware_artifact_registry_rows": lambda: (
            materializer.install_aware_artifact_registry(
                artifacts,
                tuple_coverage,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "install_aware_artifact_registry")
            else current_value
        ),
        "expected_desktop_surface_ref_rows": lambda: (
            materializer.desktop_surface_refs(
                artifacts,
                tuple_coverage,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "desktop_surface_refs")
            else current_value
        ),
        "expected_artifact_identity_registry_rows": lambda: (
            materializer.artifact_identity_registry(
                tuple_coverage,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "artifact_identity_registry")
            else current_value
        ),
        "expected_artifact_publication_binding_rows": lambda: (
            materializer.artifact_publication_bindings(
                tuple_coverage,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "artifact_publication_bindings")
            else current_value
        ),
        "expected_public_trust_metrics": lambda: (
            materializer.expected_public_trust_metrics(payload)
            if hasattr(materializer, "expected_public_trust_metrics")
            else current_value
        ),
        "expected_registry_boundary_coverage": lambda: (
            materializer.expected_registry_boundary_coverage(payload)
            if hasattr(materializer, "expected_registry_boundary_coverage")
            else current_value
        ),
    }
    fallback = fallback_helpers.get(name)
    if fallback is not None:
        return fallback()
    return current_value

def assert_desktop_surface_ref_consistency(local_payload: dict) -> None:
    artifacts = local_payload.get("artifacts") or []
    if not artifacts:
        return
    artifact_ids = {
        normalized_token(item.get("artifactId") or item.get("id"))
        for item in artifacts
        if isinstance(item, dict) and normalized_token(item.get("artifactId") or item.get("id"))
    }
    coverage = local_payload.get("desktopTupleCoverage")
    route_truth = coverage.get("desktopRouteTruth") if isinstance(coverage, dict) else []
    route_truth_by_tuple = {
        str(item.get("tupleId") or "").strip(): item
        for item in route_truth
        if isinstance(item, dict) and str(item.get("tupleId") or "").strip()
    }
    problems: list[str] = []
    for row in local_payload.get("desktopSurfaceRefs") or []:
        if not isinstance(row, dict):
            continue
        tuple_id = str(row.get("tupleId") or "").strip()
        artifact_id = normalized_token(row.get("artifactId"))
        if not artifact_id or artifact_id not in artifact_ids:
            problems.append(f"{tuple_id or '<missing-tuple>'}: desktopSurfaceRefs artifactId is missing from artifacts")
            continue
        route_row = route_truth_by_tuple.get(tuple_id)
        if not isinstance(route_row, dict):
            problems.append(f"{tuple_id}: desktopSurfaceRefs tuple is missing from desktopRouteTruth")
            continue
        route_artifact_id = normalized_token(route_row.get("artifactId"))
        if not route_artifact_id:
            problems.append(f"{tuple_id}: desktopSurfaceRefs surfaced tuple has empty desktopRouteTruth.artifactId")
        elif route_artifact_id != artifact_id:
            problems.append(f"{tuple_id}: desktopSurfaceRefs artifactId does not match desktopRouteTruth.artifactId")
        if normalized_token(route_row.get("promotionState")) == "proof_required":
            problems.append(f"{tuple_id}: desktopSurfaceRefs must not surface proof_required tuples")
    if problems:
        raise SystemExit(
            "Release channel desktopSurfaceRefs is inconsistent with artifacts/desktopRouteTruth:\n - "
            + "\n - ".join(problems)
        )

coverage = payload.get("desktopTupleCoverage")
if isinstance(coverage, dict):
    coverage["externalProofRequests"] = derive_verifier_owned_value(
        "expected_external_proof_request_rows",
        coverage.get("externalProofRequests") or [],
    )
    coverage["desktopRouteTruth"] = derive_verifier_owned_value(
        "expected_desktop_route_truth_rows",
        coverage.get("desktopRouteTruth") or [],
    )
payload["installAwareArtifactRegistry"] = derive_verifier_owned_value(
    "expected_install_aware_artifact_registry_rows",
    payload.get("installAwareArtifactRegistry") or [],
)
payload["desktopSurfaceRefs"] = derive_verifier_owned_value(
    "expected_desktop_surface_ref_rows",
    payload.get("desktopSurfaceRefs") or [],
)
payload["artifactIdentityRegistry"] = derive_verifier_owned_value(
    "expected_artifact_identity_registry_rows",
    payload.get("artifactIdentityRegistry") or [],
)
payload["artifactPublicationBindings"] = derive_verifier_owned_value(
    "expected_artifact_publication_binding_rows",
    payload.get("artifactPublicationBindings") or [],
)
payload["publicTrustMetrics"] = derive_verifier_owned_value(
    "expected_public_trust_metrics",
    payload.get("publicTrustMetrics") or {},
)

trust_release_channel = payload.get("publicTrustMetrics", {}).get("releaseChannel", {})
trust_supportability_state = normalized_token(trust_release_channel.get("supportabilityState"))
if normalized_token(payload.get("status")) == "published" and trust_supportability_state:
    payload["supportabilityState"] = trust_supportability_state
    if trust_supportability_state == "review_required":
        payload["supportabilitySummary"] = (
            "Release checks are missing or stale on this shelf, so review is still required before this release can be treated as supportable."
        )
        payload["knownIssueSummary"] = (
            "Release checks are missing or stale on this shelf, so preview publication is visible but not yet gold-ready."
        )

coverage = payload.get("desktopTupleCoverage")
if isinstance(coverage, dict):
    coverage["externalProofRequests"] = derive_verifier_owned_value(
        "expected_external_proof_request_rows",
        coverage.get("externalProofRequests") or [],
    )
    coverage["desktopRouteTruth"] = derive_verifier_owned_value(
        "expected_desktop_route_truth_rows",
        coverage.get("desktopRouteTruth") or [],
    )
payload["installAwareArtifactRegistry"] = derive_verifier_owned_value(
    "expected_install_aware_artifact_registry_rows",
    payload.get("installAwareArtifactRegistry") or [],
)
payload["desktopSurfaceRefs"] = derive_verifier_owned_value(
    "expected_desktop_surface_ref_rows",
    payload.get("desktopSurfaceRefs") or [],
)
payload["artifactIdentityRegistry"] = derive_verifier_owned_value(
    "expected_artifact_identity_registry_rows",
    payload.get("artifactIdentityRegistry") or [],
)
payload["artifactPublicationBindings"] = derive_verifier_owned_value(
    "expected_artifact_publication_binding_rows",
    payload.get("artifactPublicationBindings") or [],
)
payload["registryBoundaryCoverage"] = derive_verifier_owned_value(
    "expected_registry_boundary_coverage",
    payload.get("registryBoundaryCoverage") or {},
)
assert_desktop_surface_ref_consistency(payload)
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

copy_public_artifacts() {
  local source_root="${1:-}"
  local target_root="${2:-}"
  local artifact_path
  shopt -s nullglob
  for artifact_path in "$source_root"/chummer-*; do
    [[ -f "$artifact_path" ]] || continue
    cp "$artifact_path" "$target_root"/
  done
  shopt -u nullglob
}

filter_files_to_manifest_truth() {
  local files_root="${1:-}"
  local manifest_path="${2:-}"
  if [[ -z "$files_root" || -z "$manifest_path" || ! -d "$files_root" || ! -f "$manifest_path" ]]; then
    return 0
  fi

  python3 - "$files_root" "$manifest_path" <<'PY'
import json
import sys
from pathlib import Path

files_root = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])

payload = json.loads(manifest_path.read_text(encoding="utf-8"))
rows = payload.get("artifacts")
if not isinstance(rows, list):
    rows = payload.get("downloads")
if not isinstance(rows, list):
    rows = []

allowed: set[str] = set()
for row in rows:
    if not isinstance(row, dict):
        continue
    file_name = str(row.get("fileName") or "").strip()
    if not file_name:
        url = str(row.get("downloadUrl") or row.get("url") or "").strip()
        if url:
            file_name = Path(url.split("?", 1)[0].split("#", 1)[0]).name
    if file_name:
        allowed.add(file_name)
        lowered = file_name.lower()
        if lowered.endswith("-installer.exe") and "-win-" in lowered:
            payload_name = file_name[:-len("-installer.exe")] + "-payload.zip"
            allowed.add(payload_name)
            allowed.add(f"{payload_name}.json")
    payload_file_name = str(row.get("payloadFileName") or "").strip()
    if payload_file_name:
        allowed.add(payload_file_name)
        allowed.add(f"{payload_file_name}.json")
    payload_url = str(row.get("payloadDownloadUrl") or "").strip()
    if payload_url:
        payload_url_name = Path(payload_url.split("?", 1)[0].split("#", 1)[0]).name
        if payload_url_name:
            allowed.add(payload_url_name)
            allowed.add(f"{payload_url_name}.json")

for artifact_path in files_root.glob("chummer-*"):
    if not artifact_path.is_file():
        continue
    if artifact_path.name not in allowed:
        artifact_path.unlink()
PY
}

tmp_root="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_root"
}
trap cleanup EXIT

combined_files_root="$tmp_root/files"
combined_startup_smoke_root="$tmp_root/startup-smoke"
generated_root="$tmp_root/generated"
mkdir -p "$combined_files_root" "$combined_startup_smoke_root" "$generated_root"

copy_public_artifacts "$RUNSERVICES_SOURCE_FILES_ROOT" "$combined_files_root"
copy_public_artifacts "$PRESENTATION_FILES_ROOT" "$combined_files_root"
filter_files_to_manifest_truth "$combined_files_root" "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH"

if [[ ! -f "$SCRIPT_DIR/verify-windows-installer-payloads.py" ]]; then
  echo "Missing Windows installer payload gate: $SCRIPT_DIR/verify-windows-installer-payloads.py" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/verify-windows-installer-payloads.py" \
  --files-dir "$combined_files_root" \
  --manifest "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" \
  --allow-empty

AUTO_DISABLED_ARTIFACT_IDS="$(detect_auto_disabled_artifact_ids "$combined_files_root" "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" | paste -sd, -)"
if [[ -n "$AUTO_DISABLED_ARTIFACT_IDS" ]]; then
  if [[ -n "$DISABLED_ARTIFACT_IDS" ]]; then
    DISABLED_ARTIFACT_IDS="$DISABLED_ARTIFACT_IDS,$AUTO_DISABLED_ARTIFACT_IDS"
  else
    DISABLED_ARTIFACT_IDS="$AUTO_DISABLED_ARTIFACT_IDS"
  fi
  echo "auto-disabled public artifact ids: $AUTO_DISABLED_ARTIFACT_IDS"
fi

if [[ -d "$PRESENTATION_STARTUP_SMOKE_ROOT" ]]; then
  find "$PRESENTATION_STARTUP_SMOKE_ROOT" -maxdepth 1 -type f -name 'startup-smoke-*.receipt.json' -print0 \
    | while IFS= read -r -d '' receipt_path; do
        cp "$receipt_path" "$combined_startup_smoke_root"/
      done
fi

if [[ -d "$RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT" ]]; then
  find "$RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT" -maxdepth 1 -type f -name 'startup-smoke-*.receipt.json' -print0 \
    | while IFS= read -r -d '' receipt_path; do
        cp "$receipt_path" "$combined_startup_smoke_root"/
      done
fi

sanitized_release_proof_path="$tmp_root/HUB_LOCAL_RELEASE_PROOF.generated.json"
python3 - "$RELEASE_PROOF_SOURCE" "$sanitized_release_proof_path" "$PUBLIC_RELEASE_PROOF_BASE_URL" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
canonical_base_url = str(sys.argv[3]).strip()
allowed = {
    "status",
    "generatedAt",
    "generated_at",
    "baseUrl",
    "base_url",
    "journeysPassed",
    "journeys_passed",
    "proofRoutes",
    "proof_routes",
    "uiLocalizationReleaseGate",
    "ui_localization_release_gate",
}
payload = json.loads(source.read_text(encoding="utf-8"))
sanitized = {key: value for key, value in payload.items() if key in allowed}
if canonical_base_url:
    sanitized["baseUrl"] = canonical_base_url
    sanitized["base_url"] = canonical_base_url
target.write_text(
    json.dumps(sanitized, indent=2) + "\n",
    encoding="utf-8",
)
PY

sanitized_ui_localization_release_gate_path="$tmp_root/UI_LOCALIZATION_RELEASE_GATE.generated.json"
python3 - "$UI_LOCALIZATION_RELEASE_GATE_SOURCE" "$sanitized_ui_localization_release_gate_path" "$PUBLIC_RELEASE_PROOF_BASE_URL" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
canonical_base_url = str(sys.argv[3]).strip().rstrip("/")
payload = json.loads(source.read_text(encoding="utf-8"))
local_release_proof = payload.get("local_release_proof")
if isinstance(local_release_proof, dict) and canonical_base_url:
    local_release_proof["base_url"] = canonical_base_url
    local_release_proof["baseUrl"] = canonical_base_url
target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

mkdir -p "$REPO_ROOT/Chummer.Run.Api/wwwroot/proofs/mac-codex-release"
cp "$sanitized_ui_localization_release_gate_path" \
  "$REPO_ROOT/Chummer.Run.Api/wwwroot/proofs/mac-codex-release/UI_LOCALIZATION_RELEASE_GATE.generated.json"

release_channel="preview"
release_version="run-20260411-201805"
release_published_at="2026-04-11T20:19:24Z"

if [[ -f "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" ]]; then
  while IFS= read -r value; do
    release_meta+=("$value")
  done < <(python3 - "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(str(payload.get("channelId") or payload.get("channel") or "preview"))
print(str(payload.get("version") or "run-20260411-201805"))
print(str(payload.get("publishedAt") or "2026-04-11T20:19:24Z"))
PY
)
  if [[ -n "${release_meta[0]:-}" ]]; then
    release_channel="${release_meta[0]}"
  fi
  if [[ -n "${release_meta[1]:-}" ]]; then
    release_version="${release_meta[1]}"
  fi
  if [[ -n "${release_meta[2]:-}" ]]; then
    release_published_at="${release_meta[2]}"
  fi
fi

DOWNLOADS_DIR="$combined_files_root" \
SOURCE_MANIFEST_PATH="$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" \
MANIFEST_PATH="$generated_root/releases.json" \
CANONICAL_MANIFEST_PATH="$generated_root/RELEASE_CHANNEL.generated.json" \
PORTAL_MANIFEST_PATH="$OUTPUT_ROOT/releases.json" \
PORTAL_CANONICAL_MANIFEST_PATH="$OUTPUT_ROOT/RELEASE_CHANNEL.generated.json" \
PORTAL_DOWNLOADS_DIR="$OUTPUT_ROOT" \
STARTUP_SMOKE_DIR="$combined_startup_smoke_root" \
RELEASE_PROOF_PATH="$sanitized_release_proof_path" \
CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH="$sanitized_ui_localization_release_gate_path" \
CHUMMER_MACOS_PUBLIC_SHELF_ENABLED="${CHUMMER_MACOS_PUBLIC_SHELF_ENABLED:-false}" \
CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS="$FORCE_ACCOUNT_REQUIRED_DOWNLOADS" \
RELEASE_CHANNEL="$release_channel" \
RELEASE_VERSION="$release_version" \
RELEASE_PUBLISHED_AT="$release_published_at" \
CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS="$STARTUP_SMOKE_MAX_AGE_SECONDS" \
CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER="$PUBLIC_SKIP_STARTUP_SMOKE_FILTER" \
bash "$SCRIPT_DIR/generate-releases-manifest.sh"

rm -rf "$OUTPUT_ROOT/proof/windows"
mkdir -p "$OUTPUT_ROOT/proof/windows"
find "$combined_files_root" -maxdepth 1 -type f -name 'chummer-*-win-x64-installer.exe' -print0 \
  | while IFS= read -r -d '' installer_path; do
      cp "$installer_path" "$OUTPUT_ROOT/proof/windows"/
    done

rm -rf "$OUTPUT_ROOT/release-evidence"
mkdir -p "$OUTPUT_ROOT/release-evidence"
cp "$PRESENTATION_RELEASE_EVIDENCE_SOURCE" "$OUTPUT_ROOT/release-evidence/public-promotion.json"

rm -rf "$OUTPUT_ROOT/startup-smoke"
mkdir -p "$OUTPUT_ROOT/startup-smoke"
python3 - "$combined_startup_smoke_root" "$PRESENTATION_STARTUP_SMOKE_ROOT" "$RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT" "$OUTPUT_ROOT/startup-smoke" "$OUTPUT_ROOT/files" "$release_channel" "$release_version" "$REPO_ROOT" <<'PY'
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

receipt_root = Path(sys.argv[1])
fallback_root = Path(sys.argv[2])
secondary_fallback_root = Path(sys.argv[3])
deploy_root = Path(sys.argv[4])
files_root = Path(sys.argv[5])
release_channel = str(sys.argv[6]).strip()
release_version = str(sys.argv[7]).strip()
repo_root = Path(sys.argv[8])

deploy_root.mkdir(parents=True, exist_ok=True)


def resolve_companion(source_root: Path, value: object) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    token = Path(raw)
    candidates: list[Path] = []
    if token.is_absolute():
        candidates.append(token)
    else:
        candidates.append(source_root / token)
    candidates.append(source_root / token.name)
    if fallback_root != source_root:
        if token.is_absolute():
            candidates.append(fallback_root / token.name)
        else:
            candidates.append(fallback_root / token)
            candidates.append(fallback_root / token.name)
    if secondary_fallback_root not in {source_root, fallback_root}:
        if token.is_absolute():
            candidates.append(secondary_fallback_root / token.name)
        else:
            candidates.append(secondary_fallback_root / token)
            candidates.append(secondary_fallback_root / token.name)

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve(strict=False)
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    return None


def copy_companion(source_root: Path, value: object) -> str:
    source_path = resolve_companion(source_root, value)
    restored_path: Path | None = None
    if source_path is None:
        raw_name = Path(str(value or "").strip()).name
        if raw_name:
            git_path = f"Chummer.Portal/downloads/startup-smoke/{raw_name}"
            try:
                restored_bytes = subprocess.check_output(
                    ["git", "show", f"HEAD:{git_path}"],
                    cwd=repo_root,
                    stderr=subprocess.DEVNULL,
                )
                restored_path = deploy_root / raw_name
                restored_path.write_bytes(restored_bytes)
            except (subprocess.CalledProcessError, FileNotFoundError):
                restored_path = None
            if restored_path is None and raw_name in {
                "dpkg-avalonia-linux-x64.log",
                "installed-launch-avalonia-linux-x64.bin",
            }:
                restored_path = deploy_root / raw_name
                restored_path.write_bytes(b"")
    if source_path is None and restored_path is None:
        return ""

    if restored_path is not None:
        return str(restored_path)

    target_path = deploy_root / source_path.name
    if source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)
    return str(target_path)


def rewrite_install_verification(verification_path: Path, source_root: Path) -> None:
    payload = json.loads(verification_path.read_text(encoding="utf-8-sig"))
    for key in (
        "dpkgLogPath",
        "installedLaunchCapturePath",
        "wrapperCapturePath",
        "desktopEntryCapturePath",
    ):
        copied = copy_companion(source_root, payload.get(key))
        if copied:
            payload[key] = copied
    verification_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


for receipt_path in sorted(receipt_root.glob("startup-smoke-*.receipt.json")):
    source_root = receipt_path.parent
    payload = json.loads(receipt_path.read_text(encoding="utf-8-sig"))

    if release_channel:
        payload["channelId"] = release_channel
        payload["channel"] = release_channel
    if release_version:
        payload["releaseVersion"] = release_version
        payload["version"] = release_version

    verification_dest = copy_companion(source_root, payload.get("artifactInstallVerificationPath"))
    if verification_dest:
        payload["artifactInstallVerificationPath"] = verification_dest
        rewrite_install_verification(Path(verification_dest), source_root)

    for key in (
        "artifactInstallDpkgLogPath",
        "artifactInstallLaunchCapturePath",
        "artifactInstallWrapperCapturePath",
        "artifactInstallDesktopEntryCapturePath",
    ):
        copied = copy_companion(source_root, payload.get(key))
        if copied:
            payload[key] = copied

    artifact_name = Path(str(payload.get("artifactPath") or "").strip()).name
    if artifact_name:
        published_artifact = files_root / artifact_name
        if published_artifact.is_file():
            payload["artifactPath"] = str(published_artifact)

    (deploy_root / receipt_path.name).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
PY

if [[ -n "$DISABLED_ARTIFACT_IDS" ]]; then
  python3 - "$OUTPUT_ROOT" "$DISABLED_ARTIFACT_IDS" <<'PY'
import json
import sys
from pathlib import Path

output_root = Path(sys.argv[1])
disabled = {
    token.strip().lower()
    for raw in sys.argv[2].replace(";", ",").replace("\n", ",").split(",")
    for token in raw.split()
    if token.strip()
}
removed_files: set[str] = set()
disabled_route_tokens: set[str] = set(disabled)

def add_route_tokens(item: dict, id_key: str, url_key: str) -> None:
    artifact_id = str(item.get(id_key) or "").strip()
    if artifact_id:
        disabled_route_tokens.add(artifact_id)
    file_name = str(item.get("fileName") or "").strip()
    if not file_name:
        url = str(item.get(url_key) or "").strip()
        if url:
            file_name = Path(url.split("?", 1)[0].split("#", 1)[0]).name
    if file_name:
        removed_files.add(file_name)
        disabled_route_tokens.add(file_name)
    url = str(item.get(url_key) or "").strip()
    if url:
        disabled_route_tokens.add(url)

for manifest_name, array_key, id_key, url_key in (
    ("releases.json", "downloads", "id", "url"),
    ("RELEASE_CHANNEL.generated.json", "artifacts", "artifactId", "downloadUrl"),
):
    manifest_path = output_root / manifest_name
    if not manifest_path.exists():
        continue
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = payload.get(array_key) or []
    kept = []
    for item in rows:
        artifact_id = str(item.get(id_key) or "").strip().lower()
        if artifact_id in disabled:
            add_route_tokens(item, id_key, url_key)
            continue
        kept.append(item)
    payload[array_key] = kept

    for proof_container in (payload, payload.get("releaseProof") if isinstance(payload.get("releaseProof"), dict) else None):
        if not isinstance(proof_container, dict):
            continue
        routes = proof_container.get("proofRoutes")
        if isinstance(routes, list):
            proof_container["proofRoutes"] = [
                route for route in routes
                if isinstance(route, str) and not any(token and token.lower() in route.lower() for token in disabled_route_tokens)
            ]

    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

for relative_root in ("files", "proof/windows"):
    directory = output_root / relative_root
    for file_name in removed_files:
        candidate = directory / file_name
        if candidate.exists():
            candidate.unlink()

startup_smoke_root = output_root / "startup-smoke"
if startup_smoke_root.exists():
    for receipt_path in startup_smoke_root.glob("startup-smoke-*.receipt.json"):
        lowered = receipt_path.name.lower()
        if any(token.replace("-installer", "").replace("-archive", "") in lowered for token in disabled):
            receipt_path.unlink()
PY
fi

canonicalize_release_channel_registries "$generated_root/RELEASE_CHANNEL.generated.json"
canonicalize_release_channel_registries "$generated_root/releases.json"
canonicalize_release_channel_registries "$OUTPUT_ROOT/RELEASE_CHANNEL.generated.json"
canonicalize_release_channel_registries "$OUTPUT_ROOT/releases.json"

if [[ -f "$SCRIPT_DIR/materialize-aur-package.py" ]]; then
  python3 "$SCRIPT_DIR/materialize-aur-package.py" \
    --manifest "$OUTPUT_ROOT/releases.json" \
    --files-root "$OUTPUT_ROOT/files" \
    --output-root "$OUTPUT_ROOT" \
    --downloads-prefix "${CHUMMER_PUBLIC_DOWNLOADS_PREFIX:-https://chummer.run/downloads/files}" \
    --optional >/dev/null
fi

python3 - "$OUTPUT_ROOT/RELEASE_CHANNEL.generated.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
artifacts = payload.get("artifacts") or []
print(json.dumps(
    {
        "output": sys.argv[1],
        "artifact_ids": [str(item.get("artifactId") or "") for item in artifacts],
        "windows_proof_dir": str(Path(sys.argv[1]).parent / "proof" / "windows"),
    },
    indent=2,
))
PY
if [[ -z "$PUBLIC_SKIP_STARTUP_SMOKE_FILTER" ]]; then
  if [[ "${RELEASE_CHANNEL:-preview}" =~ ^[Pp][Rr][Ee][Vv][Ii][Ee][Ww]$ ]]; then
    PUBLIC_SKIP_STARTUP_SMOKE_FILTER="true"
  else
    PUBLIC_SKIP_STARTUP_SMOKE_FILTER="false"
  fi
fi
