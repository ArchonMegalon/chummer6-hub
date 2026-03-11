#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DOWNLOADS_DIR="${DOWNLOADS_DIR:-$REPO_ROOT/Docker/Downloads/files}"
MANIFEST_PATH="${MANIFEST_PATH:-$REPO_ROOT/Docker/Downloads/releases.json}"
PORTAL_MANIFEST_PATH="${PORTAL_MANIFEST_PATH:-$REPO_ROOT/Chummer.Portal/downloads/releases.json}"
PORTAL_DOWNLOADS_DIR="${PORTAL_DOWNLOADS_DIR:-$REPO_ROOT/Chummer.Portal/downloads}"
RELEASE_VERSION="${RELEASE_VERSION:-unpublished}"
RELEASE_CHANNEL="${RELEASE_CHANNEL:-docker}"
RELEASE_PUBLISHED_AT="${RELEASE_PUBLISHED_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

mkdir -p "$(dirname "$MANIFEST_PATH")"
mkdir -p "$(dirname "$PORTAL_MANIFEST_PATH")"
mkdir -p "$DOWNLOADS_DIR"

python3 - "$DOWNLOADS_DIR" "$MANIFEST_PATH" "$RELEASE_VERSION" "$RELEASE_CHANNEL" "$RELEASE_PUBLISHED_AT" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

downloads_dir = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
version = sys.argv[3]
channel = sys.argv[4]
published_at = sys.argv[5]

app_labels = {
    "avalonia": "Avalonia Desktop",
    "blazor-desktop": "Blazor Desktop",
}
platform_names = {
    "win-x64": "Windows x64",
    "win-arm64": "Windows ARM64",
    "linux-x64": "Linux x64",
    "linux-arm64": "Linux ARM64",
    "osx-arm64": "macOS ARM64",
    "osx-x64": "macOS x64",
}

pattern = re.compile(r"^chummer-(?P<app>avalonia|blazor-desktop)-(?P<rid>[^.]+)\.(?P<ext>zip|tar\.gz)$")
downloads = []

for artifact in sorted(downloads_dir.iterdir()):
    if not artifact.is_file():
        continue

    match = pattern.match(artifact.name)
    if not match:
        continue

    app = match.group("app")
    rid = match.group("rid")
    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    size_bytes = artifact.stat().st_size
    downloads.append(
        {
            "id": f"{app}-{rid}",
            "platform": f"{app_labels.get(app, app)} {platform_names.get(rid, rid)}",
            "url": f"/downloads/files/{artifact.name}",
            "sha256": sha256,
            "sizeBytes": size_bytes,
        }
    )

if not downloads:
    version = "unpublished"

manifest = {
    "version": version,
    "channel": channel,
    "publishedAt": published_at,
    "downloads": downloads,
}

manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"wrote {manifest_path} with {len(downloads)} download entry(ies)")
PY

resolved_manifest_path="$(realpath "$MANIFEST_PATH")"
resolved_portal_manifest_path="$(realpath -m "$PORTAL_MANIFEST_PATH")"
if [[ "$resolved_manifest_path" == "$resolved_portal_manifest_path" ]]; then
  echo "portal manifest path matches manifest output; skipped secondary sync"
else
  cp "$MANIFEST_PATH" "$PORTAL_MANIFEST_PATH"
  echo "synced portal manifest -> $PORTAL_MANIFEST_PATH"

  portal_files_dir="$PORTAL_DOWNLOADS_DIR/files"
  mkdir -p "$portal_files_dir"
  mapfile -t portal_artifacts < <(find "$DOWNLOADS_DIR" -maxdepth 1 -type f \( -name "chummer-*.zip" -o -name "chummer-*.tar.gz" \) | sort)
  if [[ "${#portal_artifacts[@]}" -gt 0 ]]; then
    rm -f "$portal_files_dir"/chummer-*.zip "$portal_files_dir"/chummer-*.tar.gz
    cp "${portal_artifacts[@]}" "$portal_files_dir"/
    echo "synced ${#portal_artifacts[@]} local portal artifact(s) -> $portal_files_dir"
  else
    echo "no local desktop artifacts found in $DOWNLOADS_DIR for portal file sync"
  fi
fi
