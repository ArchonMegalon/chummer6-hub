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
    "$REPO_ROOT/../chummer-presentation/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json"
  do
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  echo "$PRESENTATION_ROOT/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json"
}

PRESENTATION_ROOT="$(resolve_ui_repo_root)"
OUTPUT_ROOT="${1:-$REPO_ROOT/Chummer.Portal/downloads}"

resolve_ui_downloads_path() {
  local relative_path="$1"
  local candidate
  for candidate in \
    "$PRESENTATION_ROOT/Docker/Downloads/$relative_path" \
    "$PRESENTATION_ROOT/Chummer.Portal/downloads/$relative_path"
  do
    if [[ -e "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  echo "$PRESENTATION_ROOT/Docker/Downloads/$relative_path"
}

RUNSERVICES_SOURCE_FILES_ROOT="${CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT:-$REPO_ROOT/legacy/tooling/docker/Docker/Downloads/files}"
PRESENTATION_FILES_ROOT="${CHUMMER_PRESENTATION_FILES_ROOT:-$(resolve_ui_downloads_path "files")}"
PRESENTATION_STARTUP_SMOKE_ROOT="${CHUMMER_PRESENTATION_STARTUP_SMOKE_ROOT:-$(resolve_ui_downloads_path "startup-smoke")}"
PRESENTATION_RELEASE_CHANNEL_PATH="${CHUMMER_PRESENTATION_RELEASE_CHANNEL_PATH:-$(resolve_ui_downloads_path "RELEASE_CHANNEL.generated.json")}"
PRESENTATION_RELEASE_EVIDENCE_SOURCE="${CHUMMER_PRESENTATION_RELEASE_EVIDENCE_SOURCE:-$PRESENTATION_ROOT/Docker/Downloads/release-evidence/public-promotion.json}"
RELEASE_PROOF_SOURCE="${CHUMMER_RUN_LOCAL_RELEASE_PROOF_SOURCE:-$REPO_ROOT/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json}"
UI_LOCALIZATION_RELEASE_GATE_SOURCE="$(resolve_ui_localization_release_gate_source)"
STARTUP_SMOKE_MAX_AGE_SECONDS="${CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS:-172800}"
DISABLED_ARTIFACT_IDS="${CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS:-${CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS:-}}"

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

tmp_root="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_root"
}
trap cleanup EXIT

combined_files_root="$tmp_root/files"
combined_startup_smoke_root="$tmp_root/startup-smoke"
generated_root="$tmp_root/generated"
mkdir -p "$combined_files_root" "$combined_startup_smoke_root" "$generated_root"

cp "$RUNSERVICES_SOURCE_FILES_ROOT"/chummer-* "$combined_files_root"/
cp "$PRESENTATION_FILES_ROOT"/chummer-* "$combined_files_root"/

if [[ -d "$PRESENTATION_STARTUP_SMOKE_ROOT" ]]; then
  find "$PRESENTATION_STARTUP_SMOKE_ROOT" -maxdepth 1 -type f -name 'startup-smoke-*.receipt.json' -print0 \
    | while IFS= read -r -d '' receipt_path; do
        cp "$receipt_path" "$combined_startup_smoke_root"/
      done
fi

sanitized_release_proof_path="$tmp_root/HUB_LOCAL_RELEASE_PROOF.generated.json"
python3 - "$RELEASE_PROOF_SOURCE" "$sanitized_release_proof_path" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
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
target.write_text(
    json.dumps({key: value for key, value in payload.items() if key in allowed}, indent=2) + "\n",
    encoding="utf-8",
)
PY

release_channel="preview"
release_version="run-20260411-201805"
release_published_at="2026-04-11T20:19:24Z"

if [[ -f "$PRESENTATION_RELEASE_CHANNEL_PATH" ]]; then
  while IFS= read -r value; do
    release_meta+=("$value")
  done < <(python3 - "$PRESENTATION_RELEASE_CHANNEL_PATH" <<'PY'
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
MANIFEST_PATH="$generated_root/releases.json" \
CANONICAL_MANIFEST_PATH="$generated_root/RELEASE_CHANNEL.generated.json" \
PORTAL_MANIFEST_PATH="$OUTPUT_ROOT/releases.json" \
PORTAL_CANONICAL_MANIFEST_PATH="$OUTPUT_ROOT/RELEASE_CHANNEL.generated.json" \
PORTAL_DOWNLOADS_DIR="$OUTPUT_ROOT" \
STARTUP_SMOKE_DIR="$combined_startup_smoke_root" \
RELEASE_PROOF_PATH="$sanitized_release_proof_path" \
CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH="$UI_LOCALIZATION_RELEASE_GATE_SOURCE" \
CHUMMER_MACOS_PUBLIC_SHELF_ENABLED=true \
RELEASE_CHANNEL="$release_channel" \
RELEASE_VERSION="$release_version" \
RELEASE_PUBLISHED_AT="$release_published_at" \
CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS="$STARTUP_SMOKE_MAX_AGE_SECONDS" \
bash "$SCRIPT_DIR/generate-releases-manifest.sh"

rm -rf "$OUTPUT_ROOT/proof/windows"
mkdir -p "$OUTPUT_ROOT/proof/windows"
find "$RUNSERVICES_SOURCE_FILES_ROOT" -maxdepth 1 -type f -name 'chummer-*-win-x64-installer.exe' -print0 \
  | while IFS= read -r -d '' installer_path; do
      cp "$installer_path" "$OUTPUT_ROOT/proof/windows"/
    done

rm -rf "$OUTPUT_ROOT/release-evidence"
mkdir -p "$OUTPUT_ROOT/release-evidence"
cp "$PRESENTATION_RELEASE_EVIDENCE_SOURCE" "$OUTPUT_ROOT/release-evidence/public-promotion.json"

rm -rf "$OUTPUT_ROOT/startup-smoke"
mkdir -p "$OUTPUT_ROOT/startup-smoke"
find "$combined_startup_smoke_root" -maxdepth 1 -type f -name 'startup-smoke-*.receipt.json' -print0 \
  | while IFS= read -r -d '' receipt_path; do
      cp "$receipt_path" "$OUTPUT_ROOT/startup-smoke"/
    done

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
