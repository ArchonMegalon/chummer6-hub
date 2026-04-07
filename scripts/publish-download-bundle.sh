#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUNDLE_DIR="${1:-$REPO_ROOT/dist}"
DEPLOY_DIR="${2:-$REPO_ROOT/legacy/tooling/docker/Docker/Downloads}"
PORTAL_MANIFEST_PATH="${PORTAL_MANIFEST_PATH:-}"
PORTAL_DOWNLOADS_DIR="${PORTAL_DOWNLOADS_DIR:-}"
DEPLOY_MODE="${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_ENABLED:-false}"
LIVE_VERIFY_TARGET="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}"
MANIFEST_SOURCE="$BUNDLE_DIR/releases.json"
FILES_SOURCE="$BUNDLE_DIR/files"
RELEASE_PROOF_PATH="${RELEASE_PROOF_PATH:-}"
STARTUP_SMOKE_SOURCE="${STARTUP_SMOKE_SOURCE:-$BUNDLE_DIR/startup-smoke}"

to_bool() {
  local value
  value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

is_public_artifact() {
  local artifact_name
  artifact_name="$(basename "$1")"
  if ! to_bool "${CHUMMER_MACOS_PUBLIC_SHELF_ENABLED:-false}" && [[ "$artifact_name" == chummer-*-osx-* ]]; then
    return 1
  fi
  return 0
}

if [[ -z "$PORTAL_MANIFEST_PATH" ]]; then
  if [[ "$(realpath "$DEPLOY_DIR")" == "$(realpath "$REPO_ROOT/legacy/tooling/docker/Docker/Downloads")" ]]; then
    PORTAL_MANIFEST_PATH="$REPO_ROOT/Chummer.Portal/downloads/releases.json"
  else
    PORTAL_MANIFEST_PATH="$DEPLOY_DIR/releases.json"
  fi
fi

if [[ -z "$PORTAL_DOWNLOADS_DIR" ]]; then
  PORTAL_DOWNLOADS_DIR="$(dirname "$PORTAL_MANIFEST_PATH")"
fi

if [[ ! -d "$BUNDLE_DIR" ]]; then
  echo "Bundle directory not found: $BUNDLE_DIR" >&2
  exit 1
fi

if [[ ! -d "$FILES_SOURCE" ]]; then
  echo "Bundle is missing files directory: $FILES_SOURCE" >&2
  echo "Expected desktop-download-bundle layout: releases.json + files/chummer-*" >&2
  exit 1
fi

mapfile -t artifacts < <(find "$FILES_SOURCE" -maxdepth 1 -type f \
  \( -name "chummer-avalonia-*.exe" -o -name "chummer-avalonia-*.zip" -o \
     -name "chummer-avalonia-*.tar.gz" -o -name "chummer-avalonia-*-installer.exe" -o -name "chummer-avalonia-*-installer.deb" -o \
     -name "chummer-avalonia-*-installer.pkg" -o -name "chummer-avalonia-*-installer.dmg" -o \
     -name "chummer-avalonia-*-installer.msix" -o -name "chummer-blazor-desktop-*.exe" -o -name "chummer-blazor-desktop-*.zip" -o \
     -name "chummer-blazor-desktop-*.tar.gz" -o -name "chummer-blazor-desktop-*-installer.exe" -o \
     -name "chummer-blazor-desktop-*-installer.deb" -o -name "chummer-blazor-desktop-*-installer.pkg" -o \
     -name "chummer-blazor-desktop-*-installer.dmg" -o -name "chummer-blazor-desktop-*-installer.msix" \) \
  | sort | while IFS= read -r artifact; do
      [[ -f "$artifact" ]] || continue
      if is_public_artifact "$artifact"; then
        printf '%s\n' "$artifact"
      fi
    done)

if [[ "${#artifacts[@]}" -eq 0 ]]; then
  echo "No desktop artifacts found under $FILES_SOURCE" >&2
  exit 1
fi

sync_source_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$sync_source_dir"
}
trap cleanup EXIT

for artifact in "${artifacts[@]}"; do
  cp "$artifact" "$sync_source_dir/"
done

release_version="unpublished"
release_channel="docker"
release_published_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ -f "$MANIFEST_SOURCE" ]]; then
  readarray -t manifest_meta < <(python3 - "$MANIFEST_SOURCE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
print(str(data.get("version", "unpublished")))
print(str(data.get("channel", "docker")))
print(str(data.get("publishedAt", "")))
PY
)

  if [[ -n "${manifest_meta[0]:-}" ]]; then
    release_version="${manifest_meta[0]}"
  fi
  if [[ -n "${manifest_meta[1]:-}" ]]; then
    release_channel="${manifest_meta[1]}"
  fi
  if [[ -n "${manifest_meta[2]:-}" ]]; then
    release_published_at="${manifest_meta[2]}"
  fi
fi

DOWNLOADS_DIR="$sync_source_dir" \
MANIFEST_PATH="$DEPLOY_DIR/releases.json" \
PORTAL_MANIFEST_PATH="$PORTAL_MANIFEST_PATH" \
PORTAL_DOWNLOADS_DIR="$PORTAL_DOWNLOADS_DIR" \
RELEASE_VERSION="$release_version" \
RELEASE_CHANNEL="$release_channel" \
RELEASE_PUBLISHED_AT="$release_published_at" \
SOURCE_MANIFEST_PATH="$MANIFEST_SOURCE" \
RELEASE_PROOF_PATH="$RELEASE_PROOF_PATH" \
STARTUP_SMOKE_DIR="$STARTUP_SMOKE_SOURCE" \
bash "$SCRIPT_DIR/generate-releases-manifest.sh"

readarray -t promoted_file_names < <(python3 - "$DEPLOY_DIR/RELEASE_CHANNEL.generated.json" <<'PY'
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

mkdir -p "$DEPLOY_DIR/files"
find "$DEPLOY_DIR/files" -maxdepth 1 -type f \
  \( -name "chummer-avalonia-*.exe" -o -name "chummer-avalonia-*.zip" -o -name "chummer-avalonia-*.tar.gz" -o \
     -name "chummer-avalonia-*-installer.exe" -o -name "chummer-avalonia-*-installer.deb" -o \
     -name "chummer-avalonia-*-installer.pkg" -o -name "chummer-avalonia-*-installer.dmg" -o \
     -name "chummer-avalonia-*-installer.msix" -o -name "chummer-blazor-desktop-*.exe" -o -name "chummer-blazor-desktop-*.zip" -o \
     -name "chummer-blazor-desktop-*.tar.gz" -o -name "chummer-blazor-desktop-*-installer.exe" -o \
     -name "chummer-blazor-desktop-*-installer.deb" -o -name "chummer-blazor-desktop-*-installer.pkg" -o \
     -name "chummer-blazor-desktop-*-installer.dmg" -o -name "chummer-blazor-desktop-*-installer.msix" \) \
  -delete

for file_name in "${promoted_file_names[@]}"; do
  source_path="$sync_source_dir/$file_name"
  if [[ ! -f "$source_path" ]]; then
    echo "promoted artifact missing from bundle source: $source_path" >&2
    exit 1
  fi
  cp "$source_path" "$DEPLOY_DIR/files/"
done

if to_bool "$DEPLOY_MODE"; then
  export CHUMMER_PORTAL_DOWNLOADS_REQUIRE_PUBLISHED_VERSION="${CHUMMER_PORTAL_DOWNLOADS_REQUIRE_PUBLISHED_VERSION:-true}"
  export CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS:-true}"
  if [[ -z "$LIVE_VERIFY_TARGET" ]]; then
    echo "Deployment mode requires CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL for live manifest verification." >&2
    exit 1
  fi
fi

bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$DEPLOY_DIR"

if [[ -n "$LIVE_VERIFY_TARGET" ]]; then
  bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$LIVE_VERIFY_TARGET"
fi

echo "Published ${#promoted_file_names[@]} public desktop artifact(s) into $DEPLOY_DIR"
