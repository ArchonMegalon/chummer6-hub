#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUNDLE_DIR="${1:-${DOWNLOAD_BUNDLE_DIR:-$REPO_ROOT/dist}}"
MANIFEST_SOURCE="$BUNDLE_DIR/releases.json"
FILES_SOURCE="$BUNDLE_DIR/files"
S3_TARGET_URI="${CHUMMER_PORTAL_DOWNLOADS_S3_URI:-}"
S3_LATEST_URI="${CHUMMER_PORTAL_DOWNLOADS_S3_LATEST_URI:-}"
S3_ENDPOINT_URL="${CHUMMER_PORTAL_DOWNLOADS_S3_ENDPOINT_URL:-}"
VERIFY_URL="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}"

if [[ ! -f "$MANIFEST_SOURCE" || ! -d "$FILES_SOURCE" ]]; then
  echo "Expected desktop-download-bundle layout: releases.json + files/chummer-*" >&2
  exit 1
fi

if [[ -z "$S3_TARGET_URI" ]]; then
  echo "Set CHUMMER_PORTAL_DOWNLOADS_S3_URI (for example: s3://bucket/path)." >&2
  exit 1
fi

if [[ -z "$VERIFY_URL" ]]; then
  echo "Set CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL to verify published manifest after object-storage sync." >&2
  exit 1
fi

export CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS:-true}"

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI is required for object-storage publish mode." >&2
  exit 1
fi

endpoint_args=()
if [[ -n "$S3_ENDPOINT_URL" ]]; then
  endpoint_args=(--endpoint-url "$S3_ENDPOINT_URL")
fi

copy_target() {
  local target_uri="$1"
  aws s3 cp "$FILES_SOURCE/" "$target_uri/files/" --recursive "${endpoint_args[@]}"
  aws s3 cp "$MANIFEST_SOURCE" "$target_uri/releases.json" "${endpoint_args[@]}"
}

copy_target "$S3_TARGET_URI"
if [[ -n "$S3_LATEST_URI" ]]; then
  copy_target "$S3_LATEST_URI"
fi

bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$VERIFY_URL"

artifact_count="$(find "$FILES_SOURCE" -maxdepth 1 -type f \( -name 'chummer-*.zip' -o -name 'chummer-*.tar.gz' \) | wc -l | tr -d ' ')"
echo "Published ${artifact_count} desktop artifact(s) to object storage target: $S3_TARGET_URI"
if [[ -n "$S3_LATEST_URI" ]]; then
  echo "Also published latest alias target: $S3_LATEST_URI"
fi
