#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"

DOWNLOADS_DIR="${DOWNLOADS_DIR:-$REPO_ROOT/legacy/tooling/docker/Docker/Downloads/files}"
MANIFEST_PATH="${MANIFEST_PATH:-$REPO_ROOT/legacy/tooling/docker/Docker/Downloads/releases.json}"
PORTAL_MANIFEST_PATH="${PORTAL_MANIFEST_PATH:-$REPO_ROOT/Chummer.Portal/downloads/releases.json}"
PORTAL_DOWNLOADS_DIR="${PORTAL_DOWNLOADS_DIR:-$REPO_ROOT/Chummer.Portal/downloads}"
RELEASE_VERSION="${RELEASE_VERSION:-unpublished}"
RELEASE_CHANNEL="${RELEASE_CHANNEL:-docker}"
RELEASE_PUBLISHED_AT="${RELEASE_PUBLISHED_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
CHUMMER_MACOS_PUBLIC_SHELF_ENABLED="${CHUMMER_MACOS_PUBLIC_SHELF_ENABLED:-false}"
CANONICAL_MANIFEST_PATH="${CANONICAL_MANIFEST_PATH:-$(dirname "$MANIFEST_PATH")/RELEASE_CHANNEL.generated.json}"
PORTAL_CANONICAL_MANIFEST_PATH="${PORTAL_CANONICAL_MANIFEST_PATH:-$(dirname "$PORTAL_MANIFEST_PATH")/RELEASE_CHANNEL.generated.json}"
SOURCE_MANIFEST_PATH="${SOURCE_MANIFEST_PATH:-}"
RELEASE_PROOF_PATH="${RELEASE_PROOF_PATH:-}"

if [[ ! -f "$REGISTRY_ROOT/scripts/materialize_public_release_channel.py" ]]; then
  echo "Missing registry materializer: $REGISTRY_ROOT/scripts/materialize_public_release_channel.py" >&2
  exit 1
fi

mkdir -p "$(dirname "$MANIFEST_PATH")"
mkdir -p "$(dirname "$PORTAL_MANIFEST_PATH")"
mkdir -p "$DOWNLOADS_DIR"

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
  rm -rf "$filtered_downloads_dir"
}
trap cleanup EXIT

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

python3 "$REGISTRY_ROOT/scripts/materialize_public_release_channel.py" "${materialize_args[@]}" >/dev/null

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
  mapfile -t portal_artifacts < <(find "$filtered_downloads_dir" -maxdepth 1 -type f \( \
    -name "chummer-*-installer.exe" -o \
    -name "chummer-*-installer.deb" -o \
    -name "chummer-*-installer.pkg" -o \
    -name "chummer-*-installer.dmg" -o \
    -name "chummer-*-installer.msix" \
  \) | sort)
  if [[ "${#portal_artifacts[@]}" -gt 0 ]]; then
    rm -f \
      "$portal_files_dir"/chummer-*.zip \
      "$portal_files_dir"/chummer-*.tar.gz \
      "$portal_files_dir"/chummer-*-installer.exe \
      "$portal_files_dir"/chummer-*-installer.deb \
      "$portal_files_dir"/chummer-*-installer.pkg \
      "$portal_files_dir"/chummer-*-installer.dmg \
      "$portal_files_dir"/chummer-*-installer.msix
    cp "${portal_artifacts[@]}" "$portal_files_dir"/
    echo "synced ${#portal_artifacts[@]} local portal artifact(s) -> $portal_files_dir"
  else
    echo "no local desktop artifacts found in $DOWNLOADS_DIR for portal file sync"
  fi
fi
