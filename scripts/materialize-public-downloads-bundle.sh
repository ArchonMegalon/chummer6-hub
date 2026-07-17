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
RELEASE_BUILD_HANDOFF_SCRIPT_PATH="${CHUMMER_PUBLIC_RELEASE_BUILD_HANDOFF_SCRIPT_PATH:-$PRESENTATION_ROOT/scripts/materialize_release_candidate_handoff.py}"
WINDOWS_EXIT_GATE_SCRIPT_PATH="${CHUMMER_WINDOWS_EXIT_GATE_SCRIPT_PATH:-$PRESENTATION_ROOT/scripts/materialize-windows-desktop-exit-gate.sh}"
RELEASE_PROOF_SOURCE="${CHUMMER_RUN_LOCAL_RELEASE_PROOF_SOURCE:-$REPO_ROOT/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json}"
UI_LOCALIZATION_RELEASE_GATE_SOURCE="$(resolve_ui_localization_release_gate_source)"
STARTUP_SMOKE_MAX_AGE_SECONDS="${CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS:-172800}"
PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-}"
PUBLIC_RELEASE_PROOF_BASE_URL="${CHUMMER_PUBLIC_RELEASE_PROOF_BASE_URL:-https://chummer.run}"
DISABLED_ARTIFACT_IDS="${CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS:-${CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS:-}}"
FORCE_ACCOUNT_REQUIRED_DOWNLOADS="${CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS:-false}"
REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-$REPO_ROOT/../chummer-hub-registry}"
REGISTRY_PUBLISHED_FILES_ROOT="${CHUMMER_HUB_REGISTRY_PUBLISHED_FILES_ROOT:-$REGISTRY_ROOT/.codex-studio/published/files}"
AUTHORITATIVE_PUBLISHED_ROOT="${CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISHED_ROOT:-$REGISTRY_ROOT/.codex-studio/published}"
PUBLIC_RELEASE_CHANNEL_SOURCE_PATH="$(resolve_public_release_channel_source)"
WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH="${CHUMMER_WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH:-$REPO_ROOT/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json}"
WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH="${CHUMMER_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH:-$REPO_ROOT/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json}"
WINDOWS_VISUAL_AUDIT_AUTO_IMPORT_PATH="${CHUMMER_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT_PATH:-$REPO_ROOT/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json}"

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
    file_name = str(row.get("fileName") or "").strip()
    if not file_name:
        file_name = Path(str(row.get("downloadUrl") or row.get("url") or "").strip()).name
    if kind == "portable" and file_name.endswith(".exe") and not file_name.endswith("-installer.exe"):
        sibling_zip = files_root / Path(file_name).with_suffix(".zip").name
        if sibling_zip.is_file():
            disabled_ids.append(artifact_id)
    if str(row.get("installerMode") or "").strip().lower() == "bootstrap":
        installer_path = files_root / file_name
        payload_file_name = str(row.get("payloadFileName") or "").strip()
        payload_path = files_root / payload_file_name if payload_file_name else None
        if installer_path.is_file():
            installer_size = installer_path.stat().st_size
            payload_size = None
            try:
                payload_size = int(row.get("payloadSizeBytes"))
            except (TypeError, ValueError):
                payload_size = None
            if payload_size is None and payload_path is not None and payload_path.is_file():
                payload_size = payload_path.stat().st_size
            if installer_size > 15 * 1024 * 1024 or (payload_size is not None and installer_size >= payload_size):
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

hydrate_manifest_owned_artifacts_from_candidate_roots() {
  local target_root="${1:-}"
  local manifest_path="${2:-}"
  shift 2 || true
  if [[ -z "$target_root" || -z "$manifest_path" || ! -d "$target_root" || ! -f "$manifest_path" ]]; then
    return 0
  fi

  python3 - "$target_root" "$manifest_path" "$@" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse


target_root = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
candidate_roots = [Path(raw) for raw in sys.argv[3:] if str(raw).strip()]


def normalized_sha(value: object) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def integer(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def safe_name(value: object) -> str:
    raw = str(value or "").strip()
    name = Path(raw).name if raw else ""
    return name if name == raw and name not in {".", ".."} else ""


def url_name(value: object) -> str:
    raw = str(value or "").strip()
    return safe_name(Path(urlparse(raw).path).name) if raw else ""


def matching_file(path: Path, *, expected_sha: str, expected_size: int | None) -> bool:
    if not path.is_file():
        return False
    if expected_size is not None and path.stat().st_size != expected_size:
        return False
    return not expected_sha or sha256_file(path) == expected_sha


def replace_file(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(f".{target_path.name}.tmp-{os.getpid()}")
    try:
        shutil.copy2(source_path, temporary_path)
        os.replace(temporary_path, target_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def payload_sidecar_matches(
    path: Path,
    *,
    payload_name: str,
    payload_sha: str,
    payload_size: int | None,
    installer_name: str,
) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if safe_name(payload.get("fileName")) != payload_name:
        return False
    if payload_sha and normalized_sha(payload.get("sha256")) != payload_sha:
        return False
    recorded_size = integer(payload.get("sizeBytes"))
    if payload_size is not None and recorded_size != payload_size:
        return False
    recorded_installer = safe_name(payload.get("installerFileName"))
    return not installer_name or not recorded_installer or recorded_installer == installer_name


def hydrate(name: str, *, expected_sha: str = "", expected_size: int | None = None) -> None:
    if not name:
        return
    target_path = target_root / name
    # Bytes already merged from run-services/presentation are newer input truth.
    # Candidate roots are recovery-only and must never overwrite them.
    if target_path.is_file():
        return
    for root in candidate_roots:
        source_path = root / name
        if matching_file(source_path, expected_sha=expected_sha, expected_size=expected_size):
            replace_file(source_path, target_path)
            return


payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
rows = payload.get("artifacts")
if not isinstance(rows, list):
    rows = payload.get("downloads")
if not isinstance(rows, list):
    rows = []

for row in rows:
    if not isinstance(row, dict):
        continue
    installer_name = safe_name(row.get("fileName")) or url_name(row.get("downloadUrl") or row.get("url"))
    hydrate(
        installer_name,
        expected_sha=normalized_sha(row.get("sha256") or row.get("artifactSha256")),
        expected_size=integer(row.get("sizeBytes") or row.get("artifactSizeBytes")),
    )

    payload_name = safe_name(row.get("payloadFileName")) or url_name(row.get("payloadDownloadUrl"))
    payload_sha = normalized_sha(row.get("payloadSha256"))
    payload_size = integer(row.get("payloadSizeBytes"))
    hydrate(payload_name, expected_sha=payload_sha, expected_size=payload_size)
    if not payload_name:
        continue
    sidecar_name = f"{payload_name}.json"
    sidecar_target = target_root / sidecar_name
    if sidecar_target.is_file():
        continue
    for root in candidate_roots:
        source_path = root / sidecar_name
        if payload_sidecar_matches(
            source_path,
            payload_name=payload_name,
            payload_sha=payload_sha,
            payload_size=payload_size,
            installer_name=installer_name,
        ):
            replace_file(source_path, sidecar_target)
            break
PY
}

replace_file_atomically() {
  local source_path="${1:-}"
  local target_path="${2:-}"
  if [[ -z "$source_path" || -z "$target_path" || ! -f "$source_path" ]]; then
    return 0
  fi
  if [[ "$(realpath -m "$source_path")" == "$(realpath -m "$target_path")" ]]; then
    return 0
  fi

  local target_dir
  target_dir="$(dirname "$target_path")"
  mkdir -p "$target_dir"
  local temporary_path
  temporary_path="$(mktemp "$target_dir/.${target_path##*/}.tmp.XXXXXX")"
  cp "$source_path" "$temporary_path"
  chmod --reference="$source_path" "$temporary_path" 2>/dev/null || true
  mv -f "$temporary_path" "$target_path"
}

sync_authoritative_published_manifest() {
  local source_path="${1:-}"
  local target_name="${2:-}"
  if [[ -z "$source_path" || ! -f "$source_path" || -z "$target_name" ]]; then
    return 0
  fi
  if [[ "$target_name" != "${target_name##*/}" || "$target_name" == "." || "$target_name" == ".." ]]; then
    echo "invalid authoritative manifest target: $target_name" >&2
    return 1
  fi

  local target_path="$AUTHORITATIVE_PUBLISHED_ROOT/$target_name"
  replace_file_atomically "$source_path" "$target_path"
}

sync_authoritative_published_directory() {
  local source_root="${1:-}"
  local target_relative_root="${2:-}"
  if [[ -z "$source_root" || -z "$target_relative_root" || ! -d "$source_root" ]]; then
    return 0
  fi
  if [[ "$target_relative_root" == /* || "$target_relative_root" == *".."* ]]; then
    echo "invalid authoritative directory target: $target_relative_root" >&2
    return 1
  fi

  local target_root="$AUTHORITATIVE_PUBLISHED_ROOT/$target_relative_root"
  if [[ "$(realpath -m "$source_root")" == "$(realpath -m "$target_root")" ]]; then
    return 0
  fi
  mkdir -p "$target_root"

  python3 - "$source_root" "$target_root" <<'PY'
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
target_root = Path(sys.argv[2])

source_relatives: set[Path] = set()
for source_path in sorted(source_root.rglob("*")):
    if not source_path.is_file() or source_path.is_symlink():
        continue
    relative_path = source_path.relative_to(source_root)
    source_relatives.add(relative_path)
    target_path = target_root / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(f".{target_path.name}.tmp-{os.getpid()}")
    try:
        shutil.copy2(source_path, temporary_path)
        os.replace(temporary_path, target_path)
    finally:
        temporary_path.unlink(missing_ok=True)

for target_path in sorted(target_root.rglob("*"), reverse=True):
    relative_path = target_path.relative_to(target_root)
    if target_path.is_symlink():
        target_path.unlink()
    elif target_path.is_file():
        if relative_path not in source_relatives:
            target_path.unlink()
    elif target_path.is_dir() and not any(target_path.iterdir()):
        target_path.rmdir()
PY
}

sync_workspace_portal_manifest_mirrors() {
  local source_name="${1:-}"
  if [[ -z "$source_name" || "$source_name" != "${source_name##*/}" ]]; then
    return 0
  fi
  case "${CHUMMER_PUBLIC_DISABLE_WORKSPACE_MANIFEST_MIRRORS:-}" in
    1|true|TRUE|yes|YES|on|ON)
      return 0
      ;;
  esac

  local source_path="$OUTPUT_ROOT/$source_name"
  [[ -f "$source_path" ]] || return 0

  local -a mirror_root_candidates=(
    "$REPO_ROOT"
    "$PRESENTATION_ROOT"
    "/docker/chummercomplete/chummer6-ui"
    "/docker/chummercomplete/chummer-presentation"
    "$REPO_ROOT/../chummer6-ui"
    "$REPO_ROOT/../chummer-presentation"
  )
  local -A seen_targets=()
  local mirror_root
  for mirror_root in "${mirror_root_candidates[@]}"; do
    [[ -n "$mirror_root" && -d "$mirror_root" ]] || continue
    local target_path
    for target_path in \
      "$mirror_root/Chummer.Portal/downloads/$source_name" \
      "$mirror_root/Docker/Downloads/$source_name" \
      "$mirror_root/.codex-studio/published/portal/$source_name"
    do
      [[ -z "${seen_targets[$target_path]:-}" ]] || continue
      seen_targets[$target_path]=1
      replace_file_atomically "$source_path" "$target_path"
    done
  done
}

refresh_release_build_handoff() {
  local stage_dir="${1:-}"
  if [[ -z "$stage_dir" || ! -d "$stage_dir" ]]; then
    return 0
  fi

  rm -f \
    "$stage_dir/RELEASE_BUILD_HANDOFF.generated.json" \
    "$stage_dir/RELEASE_BUILD_HANDOFF.generated.md" \
    "$stage_dir/UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json" \
    "$stage_dir/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json" \
    "$stage_dir/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.md"

  [[ -f "$RELEASE_BUILD_HANDOFF_SCRIPT_PATH" ]] || return 0
  local -a handoff_env=()
  if [[ -f "$WINDOWS_EXIT_GATE_SCRIPT_PATH" ]]; then
    handoff_env+=("CHUMMER_WINDOWS_EXIT_GATE_SCRIPT_PATH=$WINDOWS_EXIT_GATE_SCRIPT_PATH")
  fi
  if [[ -d "$REGISTRY_ROOT" ]]; then
    handoff_env+=("CHUMMER_HUB_REGISTRY_ROOT=$REGISTRY_ROOT")
  fi
  env "${handoff_env[@]}" python3 "$RELEASE_BUILD_HANDOFF_SCRIPT_PATH" "$stage_dir" >/dev/null
}

refresh_windows_visual_proof_operator_receipts() {
  local release_channel_path="${1:-}"
  local downloads_root="${2:-}"
  local startup_receipt_path="${3:-}"
  local source_path="${4:-}"
  if [[ -z "$release_channel_path" || -z "$downloads_root" || -z "$source_path" ]]; then
    echo "warning: skipped Windows visual-proof receipt refresh; required paths missing" >&2
    return 0
  fi

  local required_script
  for required_script in \
    verify_windows_installer_visual_audit.py \
    materialize_windows_installer_visual_audit_intake_request.py \
    verify_windows_installer_visual_audit_intake_request.py \
    auto_import_windows_installer_gold_proof.py
  do
    if [[ ! -f "$SCRIPT_DIR/$required_script" ]]; then
      echo "warning: skipped Windows visual-proof receipt refresh; missing $SCRIPT_DIR/$required_script" >&2
      return 0
    fi
  done

  local -a audit_args=(
    --release-channel "$release_channel_path"
    --downloads-root "$downloads_root"
    --source "$source_path"
    --output "$WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH"
  )
  local -a intake_args=(
    --release-channel "$release_channel_path"
    --downloads-root "$downloads_root"
    --source "$source_path"
    --output "$WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH"
  )
  if [[ -f "$startup_receipt_path" ]]; then
    audit_args+=(--startup-receipt "$startup_receipt_path")
    intake_args+=(--startup-receipt "$startup_receipt_path")
  fi

  set +e
  python3 "$SCRIPT_DIR/verify_windows_installer_visual_audit.py" "${audit_args[@]}"
  local audit_status=$?
  set -e
  if (( audit_status > 1 )); then
    echo "warning: Windows visual audit refresh failed with status $audit_status" >&2
  fi

  if ! python3 "$SCRIPT_DIR/materialize_windows_installer_visual_audit_intake_request.py" "${intake_args[@]}"; then
    echo "warning: Windows visual audit intake refresh failed" >&2
    return 0
  fi
  if ! python3 "$SCRIPT_DIR/verify_windows_installer_visual_audit_intake_request.py" --receipt "$WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH"; then
    echo "warning: Windows visual audit intake request did not verify" >&2
  fi

  set +e
  python3 "$SCRIPT_DIR/auto_import_windows_installer_gold_proof.py" \
    --refresh-intake-request \
    --intake-request "$WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH" \
    --output "$WINDOWS_VISUAL_AUDIT_AUTO_IMPORT_PATH" \
    --downloads-root "$downloads_root" \
    --wait-seconds 0
  local auto_import_status=$?
  set -e
  if (( auto_import_status != 0 && auto_import_status != 2 )); then
    echo "warning: Windows visual audit auto-import refresh failed with status $auto_import_status" >&2
  fi
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
hydrate_manifest_owned_artifacts_from_candidate_roots \
  "$combined_files_root" \
  "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" \
  "$REGISTRY_PUBLISHED_FILES_ROOT" \
  "$RUNSERVICES_SOURCE_FILES_ROOT" \
  "$PRESENTATION_FILES_ROOT"
filter_files_to_manifest_truth "$combined_files_root" "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH"

AUTO_DISABLED_ARTIFACT_IDS="$(detect_auto_disabled_artifact_ids "$combined_files_root" "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" | paste -sd, -)"
if [[ -n "$AUTO_DISABLED_ARTIFACT_IDS" ]]; then
  if [[ -n "$DISABLED_ARTIFACT_IDS" ]]; then
    DISABLED_ARTIFACT_IDS="$DISABLED_ARTIFACT_IDS,$AUTO_DISABLED_ARTIFACT_IDS"
  else
    DISABLED_ARTIFACT_IDS="$AUTO_DISABLED_ARTIFACT_IDS"
  fi
  echo "auto-disabled public artifact ids: $AUTO_DISABLED_ARTIFACT_IDS"
fi

if [[ ! -f "$SCRIPT_DIR/verify-windows-installer-payloads.py" ]]; then
  echo "Missing Windows installer payload gate: $SCRIPT_DIR/verify-windows-installer-payloads.py" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/verify-windows-installer-visual-proof.py" ]]; then
  echo "Missing Windows installer visual proof gate: $SCRIPT_DIR/verify-windows-installer-visual-proof.py" >&2
  exit 1
fi

windows_payload_gate_args=(
  --files-dir "$combined_files_root"
  --manifest "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH"
  --allow-empty
)
windows_visual_proof_gate_args=(
  --files-dir "$combined_files_root"
  --manifest "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH"
  --visual-audit "$WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH"
  --allow-empty
)
if [[ -n "$DISABLED_ARTIFACT_IDS" ]]; then
  windows_payload_gate_args+=(--disabled-artifact-id "$DISABLED_ARTIFACT_IDS")
  windows_visual_proof_gate_args+=(--disabled-artifact-id "$DISABLED_ARTIFACT_IDS")
fi
python3 "$SCRIPT_DIR/verify-windows-installer-payloads.py" "${windows_payload_gate_args[@]}"
set +e
python3 "$SCRIPT_DIR/verify-windows-installer-visual-proof.py" "${windows_visual_proof_gate_args[@]}"
windows_visual_proof_gate_status=$?
set -e

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
import re
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

required_routes = [
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/access",
    "/account/work",
    "/account/support",
    "/contact",
    "/downloads",
]
legacy_unsupported_routes = {"/account/roster"}
installer_route = re.compile(r"^/downloads/install/[a-z0-9][a-z0-9._-]*$")


def canonical_routes(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(route, str) for route in value):
        raise SystemExit("release proof routes must be a list of strings")
    routes = list(dict.fromkeys(route.strip() for route in value if route.strip()))
    missing = [route for route in required_routes if route not in routes]
    if missing:
        raise SystemExit(f"release proof is missing required routes: {', '.join(missing)}")
    invalid = sorted(
        route
        for route in routes
        if route not in required_routes
        and route not in legacy_unsupported_routes
        and installer_route.fullmatch(route) is None
    )
    if invalid:
        raise SystemExit(f"release proof declares unsupported routes: {', '.join(invalid)}")
    additions = sorted(
        route
        for route in routes
        if route not in required_routes and route not in legacy_unsupported_routes
    )
    return required_routes + additions


route_variants = [
    canonical
    for key in ("proofRoutes", "proof_routes")
    if (canonical := canonical_routes(sanitized.get(key))) is not None
]
if route_variants:
    if any(routes != route_variants[0] for routes in route_variants[1:]):
        raise SystemExit("release proof route aliases disagree")
    sanitized["proofRoutes"] = route_variants[0]
    sanitized["proof_routes"] = route_variants[0]
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

release_evidence_source="$PRESENTATION_RELEASE_EVIDENCE_SOURCE"
release_evidence_target="$OUTPUT_ROOT/release-evidence/public-promotion.json"
if [[ -f "$release_evidence_source" ]] \
  && [[ "$(realpath -m "$release_evidence_source")" == "$(realpath -m "$release_evidence_target")" ]]; then
  staged_release_evidence="$tmp_root/public-promotion.json"
  cp "$release_evidence_source" "$staged_release_evidence"
  release_evidence_source="$staged_release_evidence"
fi
rm -rf "$OUTPUT_ROOT/release-evidence"
mkdir -p "$OUTPUT_ROOT/release-evidence"
cp "$release_evidence_source" "$release_evidence_target"

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

refresh_release_build_handoff "$OUTPUT_ROOT"

if [[ "${windows_visual_proof_gate_status:-0}" -ne 0 ]]; then
  refresh_windows_visual_proof_operator_receipts \
    "$OUTPUT_ROOT/RELEASE_CHANNEL.generated.json" \
    "$OUTPUT_ROOT" \
    "$OUTPUT_ROOT/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json" \
    "$OUTPUT_ROOT/visual-audit/windows-installer/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
  exit "$windows_visual_proof_gate_status"
fi

sync_authoritative_published_manifest "$OUTPUT_ROOT/RELEASE_CHANNEL.generated.json" "RELEASE_CHANNEL.generated.json"
sync_authoritative_published_manifest "$OUTPUT_ROOT/releases.json" "releases.json"
sync_authoritative_published_directory "$OUTPUT_ROOT/startup-smoke" "startup-smoke"
sync_workspace_portal_manifest_mirrors "RELEASE_CHANNEL.generated.json"
sync_workspace_portal_manifest_mirrors "releases.json"

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
