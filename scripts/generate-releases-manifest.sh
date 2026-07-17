#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"

DOWNLOADS_DIR="${DOWNLOADS_DIR:-$REPO_ROOT/legacy/tooling/docker/Docker/Downloads/files}"
MANIFEST_PATH="${MANIFEST_PATH:-$REPO_ROOT/legacy/tooling/docker/Docker/Downloads/releases.json}"
PORTAL_MANIFEST_PATH="${PORTAL_MANIFEST_PATH:-$REPO_ROOT/Chummer.Portal/downloads/releases.json}"
PORTAL_DOWNLOADS_DIR="${PORTAL_DOWNLOADS_DIR:-$REPO_ROOT/Chummer.Portal/downloads}"
STARTUP_SMOKE_DIR="${STARTUP_SMOKE_DIR:-$(dirname "$DOWNLOADS_DIR")/startup-smoke}"
STARTUP_SMOKE_MAX_AGE_SECONDS="${CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS:-}"
PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-}"
RELEASE_VERSION="${RELEASE_VERSION:-unpublished}"
RELEASE_CHANNEL="${RELEASE_CHANNEL:-stable}"
RELEASE_PUBLISHED_AT="${RELEASE_PUBLISHED_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
CHUMMER_MACOS_PUBLIC_SHELF_ENABLED="${CHUMMER_MACOS_PUBLIC_SHELF_ENABLED:-false}"
CANONICAL_MANIFEST_PATH="${CANONICAL_MANIFEST_PATH:-$(dirname "$MANIFEST_PATH")/RELEASE_CHANNEL.generated.json}"
PORTAL_CANONICAL_MANIFEST_PATH="${PORTAL_CANONICAL_MANIFEST_PATH:-$(dirname "$PORTAL_MANIFEST_PATH")/RELEASE_CHANNEL.generated.json}"
SOURCE_MANIFEST_PATH="${SOURCE_MANIFEST_PATH:-}"
RELEASE_PROOF_PATH="${RELEASE_PROOF_PATH:-}"
PREVIEW_INSTALL_ACCESS_CLASS="${CHUMMER_PREVIEW_INSTALL_ACCESS_CLASS:-}"
FORCE_ACCOUNT_REQUIRED_DOWNLOADS="${CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS:-}"
PUBLIC_WEB_BASE_URL="${CHUMMER_PUBLIC_WEB_BASE_URL:-https://chummer.run}"
DOWNLOADS_PREFIX="${CHUMMER_PUBLIC_DOWNLOADS_PREFIX:-${PUBLIC_WEB_BASE_URL%/}/downloads/files}"
PUBLIC_VERSION="${CHUMMER_PUBLIC_VERSION:-0.0.0.1}"

lower_ascii() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
}

resolve_ui_localization_release_gate_path() {
  local explicit_path="${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH:-}"
  if [[ -n "$explicit_path" ]]; then
    echo "$explicit_path"
    return 0
  fi

  local candidate
  for candidate in \
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

if [[ -z "$PUBLIC_SKIP_STARTUP_SMOKE_FILTER" ]]; then
  if [[ "$(lower_ascii "$RELEASE_CHANNEL")" == "preview" ]]; then
    PUBLIC_SKIP_STARTUP_SMOKE_FILTER="true"
  else
    PUBLIC_SKIP_STARTUP_SMOKE_FILTER="false"
  fi
fi

UI_LOCALIZATION_RELEASE_GATE_PATH="$(resolve_ui_localization_release_gate_path)"

if [[ ! -f "$REGISTRY_ROOT/scripts/materialize_public_release_channel.py" ]]; then
  echo "Missing registry materializer: $REGISTRY_ROOT/scripts/materialize_public_release_channel.py" >&2
  exit 1
fi

prune_obsolete_regression_packets() {
  local startup_smoke_dir="$1"
  python3 - "$startup_smoke_dir" <<'PY'
import json
import hashlib
import sys
from pathlib import Path

startup_smoke_dir = Path(sys.argv[1])
passing_statuses = {"pass", "passed", "ready"}

def normalize_digest(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw[len("sha256:") :]
    return raw

def sha256_for(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

for receipt_path in sorted(startup_smoke_dir.glob("startup-smoke-*.receipt.json")):
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except Exception:
        continue
    if not isinstance(payload, dict):
        continue
    status = str(payload.get("status") or "").strip().lower()
    if status not in passing_statuses:
        continue
    head = str(payload.get("headId") or payload.get("appKey") or "").strip()
    rid = str(payload.get("rid") or "").strip()
    if not head or not rid:
        continue
    packet_path = startup_smoke_dir / f"release-regression-{head}-{rid}.json"
    if not packet_path.is_file():
        continue

    receipt_digest = normalize_digest(payload.get("artifactDigest") or payload.get("artifactSha256"))
    artifact_path = Path(str(payload.get("artifactPath") or "").strip())
    if artifact_path.is_file():
        current_digest = sha256_for(artifact_path)
        if receipt_digest and current_digest != receipt_digest:
            continue
    else:
        current_digest = ""

    try:
        packet_payload = json.loads(packet_path.read_text(encoding="utf-8-sig"))
    except Exception:
        continue
    if not isinstance(packet_payload, dict):
        continue
    packet_digest = normalize_digest(packet_payload.get("artifactSha256"))
    if receipt_digest and packet_digest and receipt_digest != packet_digest:
        continue
    if current_digest and packet_digest and current_digest != packet_digest:
        continue

    packet_path.unlink()
    print(packet_path)
PY
}

sanitize_ui_localization_release_gate_payload() {
  local source_path="${1:-}"
  local output_path="${2:-}"
  python3 - "$source_path" "$output_path" <<'PY'
import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
if not isinstance(payload, dict):
    raise SystemExit(f"ui localization release gate payload must be a JSON object: {source_path}")

allowed = {
    "status",
    "generatedAt",
    "generated_at",
    "defaultKeyCount",
    "default_key_count",
    "explicitFallbackRuntime",
    "explicit_fallback_runtime",
    "signoffSmokeRunner",
    "signoff_smoke_runner",
    "signoffSmokeRunnerStatus",
    "signoff_smoke_runner_status",
    "shippingLocales",
    "shipping_locales",
    "acceptanceGates",
    "acceptance_gates",
    "domainCoverage",
    "domain_coverage",
    "localeDomainCoverage",
    "locale_domain_coverage",
    "blockingFindings",
    "blocking_findings",
    "blockingFindingsCount",
    "blocking_findings_count",
    "translationBacklogFindings",
    "translation_backlog_findings",
    "translationBacklogFindingsCount",
    "translation_backlog_findings_count",
    "localeSummary",
    "locale_summary",
}
sanitized = {key: payload[key] for key in payload if key in allowed}
if "generatedAt" not in sanitized and "generated_at" in sanitized:
    sanitized["generatedAt"] = sanitized["generated_at"]
row_allowed = {
    "locale",
    "untranslated_key_count",
    "untranslatedKeyCount",
    "override_count",
    "overrideCount",
    "minimum_override_count",
    "minimumOverrideCount",
    "missing_release_seed_keys",
    "missingReleaseSeedKeys",
    "legacy_xml_present",
    "legacyXmlPresent",
    "legacy_data_xml_present",
    "legacyDataXmlPresent",
}
locale_rows = sanitized.get("localeSummary")
if isinstance(locale_rows, list):
    sanitized["localeSummary"] = [
        {key: value for key, value in row.items() if key in row_allowed}
        for row in locale_rows
        if isinstance(row, dict)
    ]
locale_rows_alias = sanitized.get("locale_summary")
if isinstance(locale_rows_alias, list):
    sanitized["locale_summary"] = [
        {key: value for key, value in row.items() if key in row_allowed}
        for row in locale_rows_alias
        if isinstance(row, dict)
    ]
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
PY
}

SANITIZED_UI_LOCALIZATION_RELEASE_GATE_PATH=""

assert_legacy_release_shelf_target() {
  local target_root="${1:-}"
  local target_label="${2:-release manifest target}"
  [[ -n "$target_root" ]] || {
    echo "$target_label is empty" >&2
    exit 1
  }
  if [[ -e "$target_root/.release-shelf-writer-policy.json" ]]; then
    echo "$target_label is owned by server-journal-v1; direct manifest generation is forbidden: $target_root" >&2
    exit 1
  fi
  if [[ -e "$target_root/.release-shelf-layout-v1" || -e "$target_root/current.json" ]]; then
    echo "$target_label uses immutable release-shelf layout v1; direct manifest generation is forbidden: $target_root" >&2
    exit 1
  fi
}

# This generator produces a candidate. It must never mutate a server-managed or
# already activated generation shelf through legacy top-level paths.
assert_legacy_release_shelf_target "$(dirname "$MANIFEST_PATH")" "manifest output root"
assert_legacy_release_shelf_target "$(dirname "$CANONICAL_MANIFEST_PATH")" "canonical manifest output root"
assert_legacy_release_shelf_target "$(dirname "$PORTAL_MANIFEST_PATH")" "portal manifest output root"
assert_legacy_release_shelf_target "$(dirname "$PORTAL_CANONICAL_MANIFEST_PATH")" "portal canonical manifest output root"
assert_legacy_release_shelf_target "$(dirname "$DOWNLOADS_DIR")" "downloads output root"
assert_legacy_release_shelf_target "$PORTAL_DOWNLOADS_DIR" "portal downloads output root"

mkdir -p "$(dirname "$MANIFEST_PATH")"
mkdir -p "$(dirname "$PORTAL_MANIFEST_PATH")"
mkdir -p "$DOWNLOADS_DIR"

promoted_file_names=()

to_bool() {
  local value
  value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

array_count() {
  local array_name="${1:-}"
  [[ -n "$array_name" ]] || {
    printf '0\n'
    return 0
  }

  local restore_nounset=0
  case "$-" in
    *u*)
      restore_nounset=1
      set +u
      ;;
  esac

  eval "set -- \"\${${array_name}[@]}\""
  local count="$#"

  if (( restore_nounset == 1 )); then
    set -u
  fi

  printf '%s\n' "$count"
}

normalize_preview_install_access_classes() {
  local manifest_path="$1"
  local release_channel="$2"
  : "$release_channel"

  python3 - "$manifest_path" "$release_channel" "$PREVIEW_INSTALL_ACCESS_CLASS" "${CHUMMER_PREVIEW_WINDOWS_INSTALL_ACCESS_CLASS:-open_public}" "${CHUMMER_PREVIEW_LINUX_INSTALL_ACCESS_CLASS:-open_public}" "${CHUMMER_PREVIEW_MACOS_INSTALL_ACCESS_CLASS:-account_required}" "$FORCE_ACCOUNT_REQUIRED_DOWNLOADS" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
release_channel = str(sys.argv[2] or "").strip().lower()
global_access_class = str(sys.argv[3] or "").strip().lower()
windows_access_class = str(sys.argv[4] or "open_public").strip().lower() or "open_public"
linux_access_class = str(sys.argv[5] or "open_public").strip().lower() or "open_public"
macos_access_class = str(sys.argv[6] or "account_required").strip().lower() or "account_required"
force_account_required_downloads = str(sys.argv[7] or "").strip().lower() in {"1", "true", "yes", "on"}

payload = json.loads(manifest_path.read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit(0)


def normalize_platform(artifact: dict[str, object]) -> str:
    candidates = [
        artifact.get("platform"),
        artifact.get("platformId"),
        artifact.get("rid"),
        artifact.get("artifactId"),
        artifact.get("fileName"),
    ]
    joined = " ".join(str(value or "").strip().lower() for value in candidates if str(value or "").strip())
    if not joined:
        return ""
    if "windows" in joined or "win-" in joined or joined.endswith(".exe"):
        return "windows"
    if "linux" in joined:
        return "linux"
    if "macos" in joined or "osx" in joined or joined.endswith(".dmg") or joined.endswith(".pkg"):
        return "macos"
    return ""


def resolved_access_class(artifact: dict[str, object]) -> str:
    if force_account_required_downloads:
        return "account_required"
    if global_access_class:
        return global_access_class
    platform = normalize_platform(artifact)
    if platform == "windows":
        return windows_access_class
    if platform == "linux":
        return linux_access_class
    if platform == "macos":
        return macos_access_class
    return ""

downloads = payload.get("downloads")
if isinstance(downloads, list):
    changed = False
    for artifact in downloads:
        if not isinstance(artifact, dict):
            continue
        if not force_account_required_downloads:
            kind = str(artifact.get("kind") or "").strip().lower()
            platform_tokens = " ".join(
                str(artifact.get(key) or "").strip().lower()
                for key in ("platform", "platformId", "rid", "artifactId", "fileName")
            )
            if kind not in {"installer", "dmg", "pkg", "msix"}:
                continue
        access_class = resolved_access_class(artifact)
        if not access_class:
            continue
        if str(artifact.get("installAccessClass") or "").strip().lower() == access_class:
            continue
        artifact["installAccessClass"] = access_class
        changed = True
    if changed:
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0)

changed = False
for artifact in payload.get("artifacts") or []:
    if not isinstance(artifact, dict):
        continue

    if not force_account_required_downloads:
        kind = str(artifact.get("kind") or "").strip().lower()
        platform_tokens = " ".join(
            str(artifact.get(key) or "").strip().lower()
            for key in ("platform", "platformId", "rid", "artifactId", "fileName")
        )
        if kind not in {"installer", "dmg", "pkg", "msix"}:
            continue

    access_class = resolved_access_class(artifact)
    if not access_class:
        continue

    if str(artifact.get("installAccessClass") or "").strip().lower() == access_class:
        continue

    artifact["installAccessClass"] = access_class
    changed = True

if changed:
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

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
    artifact_bound_registry_names = {
        "expected_desktop_route_truth_rows",
        "expected_install_aware_artifact_registry_rows",
        "expected_desktop_surface_ref_rows",
        "expected_artifact_identity_registry_rows",
        "expected_artifact_publication_binding_rows",
    }
    helper = getattr(module, name, None)
    if callable(helper) and name not in artifact_bound_registry_names:
        return helper(payload)
    if materializer is None:
        return helper(payload) if callable(helper) else current_value
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
                artifacts,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "artifact_identity_registry")
            else current_value
        ),
        "expected_artifact_publication_binding_rows": lambda: (
            materializer.artifact_publication_bindings(
                tuple_coverage,
                artifacts,
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

# Recompute verifier-owned registry surfaces once more after supportability/trust normalization
# so carried-forward manifests cannot keep stale dependent rows such as desktopSurfaceRefs.
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

materialize_aur_sidecar() {
  local output_root="${1:-}"
  local manifest_path="${2:-}"
  local files_root="${3:-}"
  if [[ -z "$output_root" || -z "$manifest_path" || -z "$files_root" || ! -f "$manifest_path" || ! -d "$files_root" ]]; then
    return 0
  fi
  if [[ ! -f "$SCRIPT_DIR/materialize-aur-package.py" ]]; then
    return 0
  fi

  python3 "$SCRIPT_DIR/materialize-aur-package.py" \
    --manifest "$manifest_path" \
    --files-root "$files_root" \
    --output-root "$output_root" \
    --downloads-prefix "$DOWNLOADS_PREFIX" \
    --optional >/dev/null
}

stamp_public_version() {
  local manifest_path="${1:-}"
  local public_version="${2:-}"
  if [[ -z "$manifest_path" || -z "$public_version" || ! -f "$manifest_path" ]]; then
    return 0
  fi

  python3 - "$manifest_path" "$public_version" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
public_version = str(sys.argv[2]).strip()
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
if public_version:
    payload["publicVersion"] = public_version
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

is_public_artifact() {
  local artifact_name
  artifact_name="$(basename "$1")"
  if ! to_bool "$CHUMMER_MACOS_PUBLIC_SHELF_ENABLED" && [[ "$artifact_name" == chummer-*-osx-* ]]; then
    return 1
  fi
  if [[ "$artifact_name" == chummer-*-win-*-payload.zip ]]; then
    return 0
  fi
  case "$artifact_name" in
    chummer-*-win-*.zip|chummer-*-win-*.tar.gz|chummer-*-win-*.exe)
      if [[ "$artifact_name" != *-installer.exe ]]; then
        return 1
      fi
      ;;
  esac
  return 0
}

materialize_windows_payload_sidecar_from_manifest() {
  local manifest_path="${1:-}"
  local sidecar_path="${2:-}"
  python3 - "$manifest_path" "$sidecar_path" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
sidecar_path = Path(sys.argv[2])
target_name = sidecar_path.name

payload = json.loads(manifest_path.read_text(encoding="utf-8"))
rows = payload.get("artifacts")
if not isinstance(rows, list):
    rows = payload.get("downloads")
if not isinstance(rows, list):
    rows = []

for row in rows:
    if not isinstance(row, dict):
        continue
    payload_file_name = str(row.get("payloadFileName") or "").strip()
    payload_download_url = str(row.get("payloadDownloadUrl") or "").strip()
    if not payload_file_name:
        continue
    candidates = {f"{payload_file_name}.json"}
    payload_url_name = Path(payload_download_url.split("?", 1)[0].split("#", 1)[0]).name if payload_download_url else ""
    if payload_url_name:
        candidates.add(f"{payload_url_name}.json")
    if target_name not in candidates:
        continue
    sidecar = {
        "contractName": "chummer6-ui.windows_bootstrap_payload",
        "fileName": payload_file_name,
        "installerFileName": str(row.get("fileName") or "").strip(),
        "downloadUrl": payload_download_url,
        "sha256": str(row.get("payloadSha256") or "").strip(),
        "sizeBytes": int(row.get("payloadSizeBytes") or 0),
    }
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0)

raise SystemExit(f"could not derive Windows payload sidecar from manifest truth for {target_name}")
PY
}

filtered_downloads_dir="$(mktemp -d)"
cleanup() {
  if [[ -n "$SANITIZED_UI_LOCALIZATION_RELEASE_GATE_PATH" && -f "$SANITIZED_UI_LOCALIZATION_RELEASE_GATE_PATH" ]]; then
    rm -f "$SANITIZED_UI_LOCALIZATION_RELEASE_GATE_PATH"
  fi
  rm -rf "$filtered_downloads_dir"
}
trap cleanup EXIT

if [[ -n "$UI_LOCALIZATION_RELEASE_GATE_PATH" && -f "$UI_LOCALIZATION_RELEASE_GATE_PATH" ]]; then
  SANITIZED_UI_LOCALIZATION_RELEASE_GATE_PATH="$(mktemp)"
  sanitize_ui_localization_release_gate_payload \
    "$UI_LOCALIZATION_RELEASE_GATE_PATH" \
    "$SANITIZED_UI_LOCALIZATION_RELEASE_GATE_PATH"
  UI_LOCALIZATION_RELEASE_GATE_PATH="$SANITIZED_UI_LOCALIZATION_RELEASE_GATE_PATH"
fi
if [[ -d "$STARTUP_SMOKE_DIR" ]]; then
  prune_obsolete_regression_packets "$STARTUP_SMOKE_DIR" >/dev/null
fi

while IFS= read -r artifact; do
  [[ -f "$artifact" ]] || continue
  if is_public_artifact "$artifact"; then
    cp "$artifact" "$filtered_downloads_dir/"
  fi
done < <(find "$DOWNLOADS_DIR" -maxdepth 1 -type f \( \
  -name "chummer-*.zip" -o \
  -name "chummer-*.tar.gz" -o \
  -name "chummer-*.exe" -o \
  -name "chummer-*.deb" -o \
  -name "chummer-*.pkg" -o \
  -name "chummer-*.dmg" -o \
  -name "chummer-*.msix" -o \
  -name "chummer-*.json" \
\) | sort)

materialize_args=(
  --downloads-dir "$filtered_downloads_dir"
  --channel "$RELEASE_CHANNEL"
  --version "$RELEASE_VERSION"
  --published-at "$RELEASE_PUBLISHED_AT"
  --downloads-prefix "$DOWNLOADS_PREFIX"
  --output "$CANONICAL_MANIFEST_PATH"
  --compat-output "$MANIFEST_PATH"
)

if [[ -n "$SOURCE_MANIFEST_PATH" && -f "$SOURCE_MANIFEST_PATH" ]]; then
  materialize_args+=(--manifest "$SOURCE_MANIFEST_PATH")
fi

if [[ -n "$RELEASE_PROOF_PATH" && -f "$RELEASE_PROOF_PATH" ]]; then
  materialize_args+=(--proof "$RELEASE_PROOF_PATH")
fi

if [[ -n "$UI_LOCALIZATION_RELEASE_GATE_PATH" && -f "$UI_LOCALIZATION_RELEASE_GATE_PATH" ]]; then
  materialize_args+=(--ui-localization-release-gate "$UI_LOCALIZATION_RELEASE_GATE_PATH")
fi

materializer_help="$(python3 "$REGISTRY_ROOT/scripts/materialize_public_release_channel.py" --help 2>&1 || true)"
if [[ -d "$STARTUP_SMOKE_DIR" && "$materializer_help" == *"--startup-smoke-dir"* ]]; then
  materialize_args+=(--startup-smoke-dir "$STARTUP_SMOKE_DIR")
fi
if [[ -n "$STARTUP_SMOKE_MAX_AGE_SECONDS" && "$materializer_help" == *"--startup-smoke-max-age-seconds"* ]]; then
  materialize_args+=(--startup-smoke-max-age-seconds "$STARTUP_SMOKE_MAX_AGE_SECONDS")
fi
if to_bool "$PUBLIC_SKIP_STARTUP_SMOKE_FILTER" && [[ "$materializer_help" == *"--skip-startup-smoke-filter"* ]]; then
  materialize_args+=(--skip-startup-smoke-filter)
fi
if [[ "$materializer_help" == *"--required-desktop-platforms"* ]]; then
  materialize_args+=(--required-desktop-platforms "${CHUMMER_PUBLIC_REQUIRED_DESKTOP_PLATFORMS:-linux,windows,macos}")
fi

python3 "$REGISTRY_ROOT/scripts/materialize_public_release_channel.py" "${materialize_args[@]}" >/dev/null
normalize_preview_install_access_classes "$CANONICAL_MANIFEST_PATH" "$RELEASE_CHANNEL"
normalize_preview_install_access_classes "$MANIFEST_PATH" "$RELEASE_CHANNEL"
stamp_public_version "$CANONICAL_MANIFEST_PATH" "$PUBLIC_VERSION"
stamp_public_version "$MANIFEST_PATH" "$PUBLIC_VERSION"
canonicalize_release_channel_registries "$CANONICAL_MANIFEST_PATH"
canonicalize_release_channel_registries "$MANIFEST_PATH"
filter_files_to_manifest_truth "$DOWNLOADS_DIR" "$CANONICAL_MANIFEST_PATH"
materialize_aur_sidecar "$(dirname "$MANIFEST_PATH")" "$MANIFEST_PATH" "$DOWNLOADS_DIR"
promoted_file_names=()
while IFS= read -r file_name; do
  [[ -n "$file_name" ]] || continue
  promoted_file_names+=("$file_name")
done < <(python3 - "$CANONICAL_MANIFEST_PATH" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
seen = set()
for artifact in payload.get("artifacts") or []:
    if not isinstance(artifact, dict):
        continue
    file_name = str(artifact.get("fileName") or "").strip()
    if not file_name:
        file_name = Path(str(artifact.get("downloadUrl") or "").strip()).name
    if file_name and file_name not in seen:
        print(file_name)
        seen.add(file_name)
    payload_file_name = str(artifact.get("payloadFileName") or "").strip()
    if payload_file_name and payload_file_name not in seen:
        print(payload_file_name)
        seen.add(payload_file_name)
    payload_url_name = Path(str(artifact.get("payloadDownloadUrl") or "").strip()).name
    if payload_url_name and payload_url_name not in seen:
        print(payload_url_name)
        seen.add(payload_url_name)
    for sidecar_name in (f"{payload_file_name}.json" if payload_file_name else "", f"{payload_url_name}.json" if payload_url_name else ""):
        if sidecar_name and sidecar_name not in seen:
            print(sidecar_name)
            seen.add(sidecar_name)
PY
)

resolved_manifest_path="$(realpath "$MANIFEST_PATH")"
resolved_portal_manifest_path="$(realpath -m "$PORTAL_MANIFEST_PATH")"
if [[ "$resolved_manifest_path" == "$resolved_portal_manifest_path" ]]; then
  echo "portal manifest path matches manifest output; skipped secondary sync"
else
  cp "$MANIFEST_PATH" "$PORTAL_MANIFEST_PATH"
  cp "$CANONICAL_MANIFEST_PATH" "$PORTAL_CANONICAL_MANIFEST_PATH"
  stamp_public_version "$PORTAL_MANIFEST_PATH" "$PUBLIC_VERSION"
  stamp_public_version "$PORTAL_CANONICAL_MANIFEST_PATH" "$PUBLIC_VERSION"
  canonicalize_release_channel_registries "$PORTAL_MANIFEST_PATH"
  canonicalize_release_channel_registries "$PORTAL_CANONICAL_MANIFEST_PATH"
  echo "synced portal manifest -> $PORTAL_MANIFEST_PATH"

  portal_files_dir="$PORTAL_DOWNLOADS_DIR/files"
  mkdir -p "$portal_files_dir"
  rm -f \
    "$portal_files_dir"/chummer-*.zip \
    "$portal_files_dir"/chummer-*.tar.gz \
    "$portal_files_dir"/chummer-*.exe \
    "$portal_files_dir"/chummer-*.deb \
    "$portal_files_dir"/chummer-*.pkg \
    "$portal_files_dir"/chummer-*.dmg \
    "$portal_files_dir"/chummer-*.msix \
    "$portal_files_dir"/chummer-*-installer.exe \
    "$portal_files_dir"/chummer-*-installer.deb \
    "$portal_files_dir"/chummer-*-installer.pkg \
    "$portal_files_dir"/chummer-*-installer.dmg \
    "$portal_files_dir"/chummer-*-installer.msix
  portal_artifacts=()
  for file_name in "${promoted_file_names[@]}"; do
    artifact_path="$filtered_downloads_dir/$file_name"
    if [[ ! -f "$artifact_path" ]]; then
      if [[ "$file_name" == chummer-*-payload.zip.json ]]; then
        materialize_windows_payload_sidecar_from_manifest "$CANONICAL_MANIFEST_PATH" "$artifact_path"
      fi
    fi
    if [[ ! -f "$artifact_path" ]]; then
      echo "promoted artifact missing from downloads source: $artifact_path" >&2
      exit 1
    fi
    portal_artifacts+=("$artifact_path")
  done
  portal_artifact_count="$(array_count portal_artifacts)"
  if (( portal_artifact_count > 0 )); then
    cp "${portal_artifacts[@]}" "$portal_files_dir"/
    filter_files_to_manifest_truth "$portal_files_dir" "$PORTAL_CANONICAL_MANIFEST_PATH"
    materialize_aur_sidecar "$PORTAL_DOWNLOADS_DIR" "$PORTAL_MANIFEST_PATH" "$portal_files_dir"
    echo "synced ${portal_artifact_count} local portal artifact(s) -> $portal_files_dir"
  else
    echo "no local desktop artifacts found in $DOWNLOADS_DIR for portal file sync"
  fi
fi
