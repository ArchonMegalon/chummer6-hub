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
RELEASE_VERSION="${RELEASE_VERSION:-unpublished}"
RELEASE_CHANNEL="${RELEASE_CHANNEL:-docker}"
RELEASE_PUBLISHED_AT="${RELEASE_PUBLISHED_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
CHUMMER_MACOS_PUBLIC_SHELF_ENABLED="${CHUMMER_MACOS_PUBLIC_SHELF_ENABLED:-false}"
CANONICAL_MANIFEST_PATH="${CANONICAL_MANIFEST_PATH:-$(dirname "$MANIFEST_PATH")/RELEASE_CHANNEL.generated.json}"
PORTAL_CANONICAL_MANIFEST_PATH="${PORTAL_CANONICAL_MANIFEST_PATH:-$(dirname "$PORTAL_MANIFEST_PATH")/RELEASE_CHANNEL.generated.json}"
SOURCE_MANIFEST_PATH="${SOURCE_MANIFEST_PATH:-}"
RELEASE_PROOF_PATH="${RELEASE_PROOF_PATH:-}"
UI_LOCALIZATION_RELEASE_GATE_PATH="${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH:-$REPO_ROOT/Chummer.Run.Api/wwwroot/proofs/mac-codex-release/UI_LOCALIZATION_RELEASE_GATE.generated.json}"

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

mkdir -p "$(dirname "$MANIFEST_PATH")"
mkdir -p "$(dirname "$PORTAL_MANIFEST_PATH")"
mkdir -p "$DOWNLOADS_DIR"

readarray -t promoted_file_names < <(true)

to_bool() {
  local value
  value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

is_public_artifact() {
  local artifact_name
  artifact_name="$(basename "$1")"
  if ! to_bool "$CHUMMER_MACOS_PUBLIC_SHELF_ENABLED" && [[ "$artifact_name" == chummer-*-osx-* ]]; then
    return 1
  fi
  return 0
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
  -name "chummer-*.msix" \
\) | sort)

materialize_args=(
  --downloads-dir "$filtered_downloads_dir"
  --channel "$RELEASE_CHANNEL"
  --version "$RELEASE_VERSION"
  --published-at "$RELEASE_PUBLISHED_AT"
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

python3 "$REGISTRY_ROOT/scripts/materialize_public_release_channel.py" "${materialize_args[@]}" >/dev/null
readarray -t promoted_file_names < <(python3 - "$CANONICAL_MANIFEST_PATH" <<'PY'
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
PY
)

resolved_manifest_path="$(realpath "$MANIFEST_PATH")"
resolved_portal_manifest_path="$(realpath -m "$PORTAL_MANIFEST_PATH")"
if [[ "$resolved_manifest_path" == "$resolved_portal_manifest_path" ]]; then
  echo "portal manifest path matches manifest output; skipped secondary sync"
else
  cp "$MANIFEST_PATH" "$PORTAL_MANIFEST_PATH"
  cp "$CANONICAL_MANIFEST_PATH" "$PORTAL_CANONICAL_MANIFEST_PATH"
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
      echo "promoted artifact missing from downloads source: $artifact_path" >&2
      exit 1
    fi
    portal_artifacts+=("$artifact_path")
  done
  if [[ "${#portal_artifacts[@]}" -gt 0 ]]; then
    cp "${portal_artifacts[@]}" "$portal_files_dir"/
    echo "synced ${#portal_artifacts[@]} local portal artifact(s) -> $portal_files_dir"
  else
    echo "no local desktop artifacts found in $DOWNLOADS_DIR for portal file sync"
  fi
fi
