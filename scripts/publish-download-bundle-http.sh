#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUNDLE_DIR="${1:-${DOWNLOAD_BUNDLE_DIR:-$REPO_ROOT/Chummer.Portal/downloads}}"
UPLOAD_URL="${CHUMMER_RELEASE_UPLOAD_URL:-https://chummer.run/api/internal/releases/bundles}"
SESSIONS_URL="${CHUMMER_RELEASE_UPLOAD_SESSIONS_URL:-${UPLOAD_URL%/bundles}/upload-sessions}"
PUBLIC_BASE_URL="${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}"
VERIFY_URL="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-$PUBLIC_BASE_URL/downloads/RELEASE_CHANNEL.generated.json}"
TOKEN="${CHUMMER_RELEASE_UPLOAD_TOKEN:-}"
ALLOW_DIRECT_FALLBACK="${CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK:-1}"
DRY_RUN="${CHUMMER_RELEASE_UPLOAD_DRY_RUN:-0}"
VERIFY_MANIFEST="${CHUMMER_RELEASE_UPLOAD_VERIFY_MANIFEST:-1}"
VERIFY_ROUTES="${CHUMMER_RELEASE_UPLOAD_VERIFY_ROUTES:-1}"
CHUNK_BYTES="${CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES:-52428800}"
DIRECT_LIMIT_BYTES="${CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES:-$CHUNK_BYTES}"

if [[ ! -d "$BUNDLE_DIR" ]]; then
  echo "Bundle directory not found: $BUNDLE_DIR" >&2
  exit 1
fi

if [[ ! -f "$BUNDLE_DIR/releases.json" ]]; then
  echo "Bundle is missing releases.json: $BUNDLE_DIR/releases.json" >&2
  exit 1
fi

if [[ ! -f "$BUNDLE_DIR/RELEASE_CHANNEL.generated.json" ]]; then
  echo "Bundle is missing RELEASE_CHANNEL.generated.json: $BUNDLE_DIR/RELEASE_CHANNEL.generated.json" >&2
  exit 1
fi

if [[ ! -d "$BUNDLE_DIR/files" ]]; then
  echo "Bundle is missing files/: $BUNDLE_DIR/files" >&2
  exit 1
fi

to_bool() {
  local value
  value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

prompt_for_upload_token() {
  if [[ ! -t 0 ]]; then
    return 1
  fi

  printf 'Paste the release upload handoff code or bearer token (input hidden): ' >&2
  IFS= read -r -s TOKEN || return 1
  printf '\n' >&2
  [[ -n "${TOKEN:-}" ]]
}

write_auth_curl_config() {
  local config_path="$1"
  chmod 600 "$config_path"
  printf '%s' "$TOKEN" | python3 -c 'from pathlib import Path; import sys; config_path = Path(sys.argv[1]); token = sys.stdin.read(); escaped = token.replace("\\\\", "\\\\\\\\").replace("\"", "\\\\\""); config_path.write_text(f"header = \"Authorization: Bearer {escaped}\"\n", encoding="utf-8")' "$config_path"
  TOKEN=""
}

resolve_json_field() {
  local json_path="$1"
  shift
  python3 - "$json_path" "$@" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in sys.argv[2:]:
    value = payload.get(key)
    if value is None:
        continue
    text = str(value).strip()
    if text:
        print(text)
        raise SystemExit(0)
raise SystemExit(1)
PY
}

join_url() {
  local base_url="$1"
  local maybe_relative="$2"
  python3 - "$base_url" "$maybe_relative" <<'PY'
import sys
from urllib.parse import urljoin

print(urljoin(sys.argv[1], sys.argv[2]))
PY
}

collect_upload_files() {
  local bundle_root="$1"
  [[ -f "$bundle_root/releases.json" ]] && printf '%s\n' "$bundle_root/releases.json"
  [[ -f "$bundle_root/RELEASE_CHANNEL.generated.json" ]] && printf '%s\n' "$bundle_root/RELEASE_CHANNEL.generated.json"
  [[ -f "$bundle_root/release-evidence/public-promotion.json" ]] && printf '%s\n' "$bundle_root/release-evidence/public-promotion.json"
  if [[ -d "$bundle_root/files" ]]; then
    find "$bundle_root/files" -type f | sort
  fi
  if [[ -d "$bundle_root/startup-smoke" ]]; then
    find "$bundle_root/startup-smoke" -type f | sort
  fi
  if [[ -d "$bundle_root/proof" ]]; then
    find "$bundle_root/proof" -type f | sort
  fi
}

create_bundle_archive() {
  local bundle_root="$1"
  local zip_path="$2"
  python3 - "$bundle_root" "$zip_path" <<'PY'
import sys
import zipfile
from pathlib import Path

bundle_root = Path(sys.argv[1]).resolve()
zip_path = Path(sys.argv[2]).resolve()
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(bundle_root.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(bundle_root))
PY
}

request_json() {
  local response_path="$1"
  local label="$2"
  local url="$3"
  shift 3
  local http_status
  http_status="$(curl -sS -o "$response_path" -w "%{http_code}" "$@" "$url")" || {
    echo "$label failed." >&2
    [[ -f "$response_path" ]] && cat "$response_path" >&2 || true
    return 22
  }
  if [[ ! "$http_status" =~ ^2 ]]; then
    echo "$label failed with HTTP $http_status" >&2
    cat "$response_path" >&2 || true
    return 22
  fi
}

verify_route() {
  local url="$1"
  curl -fsSL -o /dev/null "$url"
  echo "Verified route: $url"
}

build_default_verify_routes() {
  cat <<EOF
$PUBLIC_BASE_URL/downloads/install/avalonia-osx-arm64-installer
$PUBLIC_BASE_URL/downloads/install/blazor-desktop-osx-arm64-installer
$PUBLIC_BASE_URL/downloads/install/avalonia-win-x64-installer
$PUBLIC_BASE_URL/downloads/install/blazor-desktop-win-x64-installer
$PUBLIC_BASE_URL/downloads/install/avalonia-win-x64-installer/proof
$PUBLIC_BASE_URL/downloads/install/blazor-desktop-win-x64-installer/proof
$PUBLIC_BASE_URL/downloads/proof/windows/chummer-avalonia-win-x64-installer.exe
$PUBLIC_BASE_URL/downloads/proof/windows/chummer-blazor-desktop-win-x64-installer.exe
EOF
}

upload_file_direct() {
  local file_path="$1"
  local relative_path="$2"
  local files_url="$3"
  shift 3
  request_json /dev/null "upload file ${relative_path}" "$files_url" "$@" \
    -F "path=${relative_path}" \
    -F "file=@${file_path};type=application/octet-stream"
}

upload_file_chunked() {
  local file_path="$1"
  local relative_path="$2"
  local chunks_url="$3"
  shift 3
  local chunk_dir
  local chunk_path
  local total
  local index=0
  chunk_dir="$(mktemp -d)"
  split -b "$CHUNK_BYTES" "$file_path" "$chunk_dir/chunk."
  total="$(find "$chunk_dir" -maxdepth 1 -type f | wc -l | tr -d ' ')"
  while IFS= read -r chunk_path; do
    [[ -n "$chunk_path" ]] || continue
    request_json /dev/null "upload chunk ${index}/${total} for ${relative_path}" "$chunks_url" "$@" \
      -F "path=${relative_path}" \
      -F "index=${index}" \
      -F "total=${total}" \
      -F "chunk=@${chunk_path};type=application/octet-stream"
    index=$((index + 1))
  done < <(find "$chunk_dir" -maxdepth 1 -type f | sort)
  rm -rf "$chunk_dir"
}

if to_bool "$DRY_RUN"; then
  file_count="$(collect_upload_files "$BUNDLE_DIR" | wc -l | tr -d ' ')"
  echo "Dry run only. Bundle: $BUNDLE_DIR"
  echo "Upload URL: $UPLOAD_URL"
  echo "Upload sessions URL: $SESSIONS_URL"
  echo "Files staged: $file_count"
  echo
  echo "Exact live publish command:"
  echo "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL='$VERIFY_URL' bash '$SCRIPT_DIR/publish-download-bundle-http.sh' '$BUNDLE_DIR'"
  echo "If CHUMMER_RELEASE_UPLOAD_TOKEN is unset, the script will prompt for it with hidden input."
  exit 0
fi

if [[ -z "$TOKEN" ]]; then
  prompt_for_upload_token || {
    echo "Set CHUMMER_RELEASE_UPLOAD_TOKEN for live HTTP upload." >&2
    exit 1
  }
fi

tmp_root="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_root"
}
trap cleanup EXIT

auth_curl_config="$tmp_root/upload-auth.curl"
write_auth_curl_config "$auth_curl_config"

request_common=(
  --config "$auth_curl_config"
  -H "Accept: application/json"
)

upload_files=()
while IFS= read -r file_path; do
  [[ -n "$file_path" ]] || continue
  upload_files+=("$file_path")
done < <(collect_upload_files "$BUNDLE_DIR")

if (( ${#upload_files[@]} == 0 )); then
  echo "Bundle has no uploadable files: $BUNDLE_DIR" >&2
  exit 1
fi

echo "Publishing $((${#upload_files[@]})) bundle files from $BUNDLE_DIR"

session_json="$tmp_root/session.json"
response_json="$tmp_root/response.json"

if ! request_json "$session_json" "create upload session" "$SESSIONS_URL" "${request_common[@]}" -X POST; then
  if ! to_bool "$ALLOW_DIRECT_FALLBACK"; then
    exit 1
  fi
  echo "Upload session creation failed; falling back to direct bundle upload." >&2
  direct_bundle="$tmp_root/release-bundle.zip"
  create_bundle_archive "$BUNDLE_DIR" "$direct_bundle"
  request_json "$response_json" "direct release bundle upload" "$UPLOAD_URL" "${request_common[@]}" \
    -F "bundle=@${direct_bundle};type=application/zip"
else
  session_id="$(resolve_json_field "$session_json" sessionId SessionId session_id id)"
  files_url="$(resolve_json_field "$session_json" filesUrl FilesUrl files_url files || true)"
  chunks_url="$(resolve_json_field "$session_json" chunksUrl ChunksUrl chunks_url chunks || true)"
  complete_url="$(resolve_json_field "$session_json" completeUrl CompleteUrl complete_url complete || true)"
  [[ -n "$session_id" ]] || {
    echo "Upload session response missing sessionId." >&2
    exit 1
  }
  [[ -n "$files_url" ]] || files_url="${SESSIONS_URL%/}/${session_id}/files"
  [[ -n "$chunks_url" ]] || chunks_url="${SESSIONS_URL%/}/${session_id}/chunks"
  [[ -n "$complete_url" ]] || complete_url="${SESSIONS_URL%/}/${session_id}/complete"
  files_url="$(join_url "$SESSIONS_URL" "$files_url")"
  chunks_url="$(join_url "$SESSIONS_URL" "$chunks_url")"
  complete_url="$(join_url "$SESSIONS_URL" "$complete_url")"

  for file_path in "${upload_files[@]}"; do
    relative_path="${file_path#$BUNDLE_DIR/}"
    file_size="$(stat -f '%z' "$file_path" 2>/dev/null || stat -c '%s' "$file_path" 2>/dev/null || echo 0)"
    if (( file_size <= DIRECT_LIMIT_BYTES )); then
      upload_file_direct "$file_path" "$relative_path" "$files_url" "${request_common[@]}"
    else
      upload_file_chunked "$file_path" "$relative_path" "$chunks_url" "${request_common[@]}"
    fi
  done

  request_json "$response_json" "complete upload session" "$complete_url" "${request_common[@]}" -X POST
fi

echo "Upload accepted."
cat "$response_json"
echo

if to_bool "$VERIFY_MANIFEST"; then
  CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 \
    bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$VERIFY_URL"
fi

if to_bool "$VERIFY_ROUTES"; then
  verify_routes="${CHUMMER_RELEASE_UPLOAD_VERIFY_URLS:-$(build_default_verify_routes)}"
  while IFS= read -r route; do
    [[ -n "$route" ]] || continue
    verify_route "$route"
  done <<< "$verify_routes"
fi

echo "Live publish verification completed."
