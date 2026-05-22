#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"
REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"

BUNDLE_DIR="${1:-${DOWNLOAD_BUNDLE_DIR:-$REPO_ROOT/Chummer.Portal/downloads}}"
MANIFEST_PATH="${CHUMMER_RELEASE_UPLOAD_MANIFEST_PATH:-$BUNDLE_DIR/releases.json}"
CANONICAL_MANIFEST_PATH="${CHUMMER_RELEASE_UPLOAD_CANONICAL_MANIFEST_PATH:-$BUNDLE_DIR/RELEASE_CHANNEL.generated.json}"
UPLOAD_URL="${CHUMMER_RELEASE_UPLOAD_URL:-https://chummer.run/api/internal/releases/bundles}"
SESSIONS_URL="${CHUMMER_RELEASE_UPLOAD_SESSIONS_URL:-${UPLOAD_URL%/bundles}/upload-sessions}"
PUBLIC_BASE_URL="${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}"
VERIFY_URL="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-$PUBLIC_BASE_URL/downloads/RELEASE_CHANNEL.generated.json}"
TOKEN="${CHUMMER_RELEASE_UPLOAD_TOKEN:-}"
TOKEN_FILE="${CHUMMER_RELEASE_UPLOAD_TOKEN_FILE:-${CHUMMER_RELEASE_UPLOAD_TOKEN_PATH:-}}"
CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE="${CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE:-0}"
ARTIFACT_FACTORY_AUTOLAUNCH="${CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH:-1}"
ARTIFACT_FACTORY_REQUESTED_BY="${CHUMMER_ARTIFACT_FACTORY_REQUESTED_BY:-fleet.release}"
ARTIFACT_FACTORY_REQUIRED_FAMILIES="${CHUMMER_ARTIFACT_FACTORY_REQUIRED_FAMILIES:-}"
ARTIFACT_FACTORY_SOURCE_PACKS="${CHUMMER_ARTIFACT_FACTORY_SOURCE_PACKS:-}"
ARTIFACT_FACTORY_REQUESTED_FORMATS="${CHUMMER_ARTIFACT_FACTORY_REQUESTED_FORMATS:-}"
ARTIFACT_FACTORY_AUDIENCE="${CHUMMER_ARTIFACT_FACTORY_AUDIENCE:-}"
ARTIFACT_FACTORY_LOCALE="${CHUMMER_ARTIFACT_FACTORY_LOCALE:-}"
ALLOW_DIRECT_FALLBACK="${CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK:-1}"
DRY_RUN="${CHUMMER_RELEASE_UPLOAD_DRY_RUN:-0}"
VERIFY_MANIFEST="${CHUMMER_RELEASE_UPLOAD_VERIFY_MANIFEST:-1}"
VERIFY_ROUTES="${CHUMMER_RELEASE_UPLOAD_VERIFY_ROUTES:-1}"
CHUNK_BYTES="${CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES:-52428800}"
DIRECT_LIMIT_BYTES="${CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES:-$CHUNK_BYTES}"
ARTIFACT_FACTORY_REQUEST_MATERIALIZER="$SCRIPT_DIR/materialize_artifact_factory_source_pack_batch.py"
ARTIFACT_FACTORY_LAUNCHER="$SCRIPT_DIR/launch_artifact_factory_source_pack_batch.py"

if [[ ! -d "$BUNDLE_DIR" ]]; then
  echo "Bundle directory not found: $BUNDLE_DIR" >&2
  exit 1
fi

if [[ ! -f "$MANIFEST_PATH" ]]; then
  echo "Bundle is missing releases.json: $MANIFEST_PATH" >&2
  exit 1
fi

if [[ ! -f "$CANONICAL_MANIFEST_PATH" ]]; then
  echo "Bundle is missing RELEASE_CHANNEL.generated.json: $CANONICAL_MANIFEST_PATH" >&2
  exit 1
fi

if [[ ! -d "$BUNDLE_DIR/files" ]]; then
  echo "Bundle is missing files/: $BUNDLE_DIR/files" >&2
  exit 1
fi

if [[ ! -f "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" ]]; then
  echo "Missing registry verifier: $REGISTRY_ROOT/scripts/verify_public_release_channel.py" >&2
  exit 1
fi

if [[ ! -f "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" ]]; then
  echo "Missing registry verifier: $REGISTRY_ROOT/scripts/verify_public_release_channel.py" >&2
  exit 1
fi

to_bool() {
  local value
  value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
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
    )

tuple_coverage = payload.get("desktopTupleCoverage")
if not isinstance(tuple_coverage, dict):
    tuple_coverage = fallback_tuple_coverage(payload)
if isinstance(tuple_coverage, dict):
    payload["desktopTupleCoverage"] = tuple_coverage

channel_id = str(payload.get("channelId") or payload.get("channel") or "").strip()
release_version = str(payload.get("version") or "").strip()

def derive_verifier_owned_value(name: str, current_value: object) -> object:
    helper = getattr(module, name, None)
    if callable(helper):
        try:
            return helper(payload)
        except TypeError:
            pass
    fallback_helpers = {
        "expected_install_aware_artifact_registry_rows": lambda: (
            materializer.install_aware_artifact_registry(
                tuple_coverage,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "install_aware_artifact_registry")
            else current_value
        ),
        "expected_desktop_route_truth_rows": lambda: (
            materializer.desktop_route_truth(
                tuple_coverage,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "desktop_route_truth")
            else current_value
        ),
        "expected_external_proof_request_rows": lambda: (
            materializer.external_proof_requests(tuple_coverage)
            if tuple_coverage is not None and hasattr(materializer, "external_proof_requests")
            else current_value
        ),
    }
    fallback = fallback_helpers.get(name)
    return fallback() if fallback is not None else current_value

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
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

canonicalize_bundle_release_channel_registries() {
  canonicalize_release_channel_registries "$MANIFEST_PATH"
  canonicalize_release_channel_registries "$CANONICAL_MANIFEST_PATH"
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
    )

tuple_coverage = payload.get("desktopTupleCoverage")
if not isinstance(tuple_coverage, dict):
    tuple_coverage = fallback_tuple_coverage(payload)
if isinstance(tuple_coverage, dict):
    payload["desktopTupleCoverage"] = tuple_coverage

channel_id = str(payload.get("channelId") or payload.get("channel") or "").strip()
release_version = str(payload.get("version") or "").strip()

def derive_verifier_owned_value(name: str, current_value: object) -> object:
    helper = getattr(module, name, None)
    if callable(helper):
        try:
            return helper(payload)
        except TypeError:
            pass
    fallback_helpers = {
        "expected_install_aware_artifact_registry_rows": lambda: (
            materializer.install_aware_artifact_registry(
                tuple_coverage,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "install_aware_artifact_registry")
            else current_value
        ),
        "expected_desktop_route_truth_rows": lambda: (
            materializer.desktop_route_truth(
                tuple_coverage,
                channel_id=channel_id,
                release_version=release_version,
            )
            if tuple_coverage is not None and hasattr(materializer, "desktop_route_truth")
            else current_value
        ),
        "expected_external_proof_request_rows": lambda: (
            materializer.external_proof_requests(tuple_coverage)
            if tuple_coverage is not None and hasattr(materializer, "external_proof_requests")
            else current_value
        ),
    }
    fallback = fallback_helpers.get(name)
    return fallback() if fallback is not None else current_value

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
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

canonicalize_bundle_release_channel_registries() {
  canonicalize_release_channel_registries "$MANIFEST_PATH"
  canonicalize_release_channel_registries "$CANONICAL_MANIFEST_PATH"
}

resolve_upload_token() {
  if [[ -n "${TOKEN:-}" ]]; then
    return 0
  fi

  if [[ -z "$TOKEN_FILE" ]]; then
    return 1
  fi

  if [[ ! -f "$TOKEN_FILE" ]]; then
    echo "Configured CHUMMER_RELEASE_UPLOAD_TOKEN_FILE not found: $TOKEN_FILE" >&2
    return 1
  fi

  TOKEN="$(head -n 1 "$TOKEN_FILE" | tr -d '\r\n')"
  if [[ -z "${TOKEN:-}" ]]; then
    echo "Configured CHUMMER_RELEASE_UPLOAD_TOKEN_FILE is empty: $TOKEN_FILE" >&2
    return 1
  fi

  TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
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
  : > "$config_path"
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

resolve_base_url() {
  local explicit_base_url="${1:-}"
  local fallback_upload_url="$2"
  local fallback_public_base_url="$3"
  python3 - "$explicit_base_url" "$fallback_upload_url" "$fallback_public_base_url" <<'PY'
import sys
from urllib.parse import urlsplit

explicit = str(sys.argv[1]).strip()
upload_url = str(sys.argv[2]).strip()
public_base_url = str(sys.argv[3]).strip()
if explicit:
    print(explicit)
    raise SystemExit(0)

parsed = urlsplit(upload_url)
if parsed.scheme and parsed.netloc:
    print(f"{parsed.scheme}://{parsed.netloc}")
    raise SystemExit(0)

print(public_base_url)
PY
}

collect_upload_files() {
  local bundle_root="$1"
  [[ -f "$MANIFEST_PATH" ]] && printf '%s\n' "$MANIFEST_PATH"
  [[ -f "$CANONICAL_MANIFEST_PATH" ]] && printf '%s\n' "$CANONICAL_MANIFEST_PATH"
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
$PUBLIC_BASE_URL/downloads/install/avalonia-win-x64-installer
$PUBLIC_BASE_URL/downloads/install/avalonia-win-x64-installer/proof
$PUBLIC_BASE_URL/downloads/proof/windows/chummer-avalonia-win-x64-installer.exe
EOF
}

resolve_release_proof_path() {
  local bundle_root="$1"
  local repo_root="$2"
  local explicit_path="${3:-}"
  python3 - "$bundle_root" "$repo_root" "$explicit_path" <<'PY'
import sys
from pathlib import Path

bundle_root = Path(sys.argv[1]).resolve()
repo_root = Path(sys.argv[2]).resolve()
explicit = str(sys.argv[3]).strip()

if explicit:
    candidate = Path(explicit).expanduser()
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    if candidate.is_file():
        print(candidate)
        raise SystemExit(0)
    raise SystemExit(1)

candidates = [
    bundle_root / "proof" / "HUB_LOCAL_RELEASE_PROOF.generated.json",
    repo_root / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json",
    repo_root / "Chummer.Run.Api" / "wwwroot" / "proofs" / "mac-codex-release" / "HUB_LOCAL_RELEASE_PROOF.generated.json",
]

for candidate in candidates:
    if candidate.is_file():
        print(candidate)
        raise SystemExit(0)

raise SystemExit(1)
PY
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
  echo "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL='$VERIFY_URL' CHUMMER_RELEASE_UPLOAD_TOKEN_FILE='$TOKEN_FILE' bash '$SCRIPT_DIR/publish-download-bundle-http.sh' '$BUNDLE_DIR'"
  echo "If CHUMMER_RELEASE_UPLOAD_TOKEN is unset, set CHUMMER_RELEASE_UPLOAD_TOKEN_FILE or CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE=1."
  exit 0
fi

if ! resolve_upload_token; then
  if to_bool "$CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE"; then
    echo "Cannot continue: CHUMMER_RELEASE_UPLOAD_TOKEN missing and interactive prompt disabled (CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE=1)." >&2
    echo "Set CHUMMER_RELEASE_UPLOAD_TOKEN or CHUMMER_RELEASE_UPLOAD_TOKEN_FILE/CHUMMER_RELEASE_UPLOAD_TOKEN_PATH for live HTTP upload." >&2
    exit 1
  fi

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
ARTIFACT_FACTORY_TOKEN="${CHUMMER_ARTIFACT_FACTORY_TOKEN:-$TOKEN}"
write_auth_curl_config "$auth_curl_config"
ARTIFACT_FACTORY_BASE_URL="$(resolve_base_url "${CHUMMER_ARTIFACT_FACTORY_BASE_URL:-}" "$UPLOAD_URL" "$PUBLIC_BASE_URL")"
RELEASE_PROOF_PATH_RESOLVED=""
if RELEASE_PROOF_PATH_RESOLVED="$(resolve_release_proof_path "$BUNDLE_DIR" "$REPO_ROOT" "${RELEASE_PROOF_PATH:-}")"; then
  :
else
  RELEASE_PROOF_PATH_RESOLVED=""
fi

request_common=(
  --config "$auth_curl_config"
  -H "Accept: application/json"
)

canonicalize_bundle_release_channel_registries

canonicalize_bundle_release_channel_registries

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
    file_size="$(stat -c '%s' "$file_path" 2>/dev/null || stat -f '%z' "$file_path" 2>/dev/null || wc -c < "$file_path" || echo 0)"
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

if to_bool "$ARTIFACT_FACTORY_AUTOLAUNCH"; then
  if [[ ! -f "$ARTIFACT_FACTORY_REQUEST_MATERIALIZER" ]]; then
    echo "Artifact-factory request materializer missing: $ARTIFACT_FACTORY_REQUEST_MATERIALIZER" >&2
    exit 1
  fi
  if [[ ! -f "$ARTIFACT_FACTORY_LAUNCHER" ]]; then
    echo "Artifact-factory launcher missing: $ARTIFACT_FACTORY_LAUNCHER" >&2
    exit 1
  fi
  if [[ -z "${ARTIFACT_FACTORY_TOKEN:-}" ]]; then
    echo "Artifact-factory autolaunch requires CHUMMER_ARTIFACT_FACTORY_TOKEN or CHUMMER_RELEASE_UPLOAD_TOKEN." >&2
    exit 1
  fi

  artifact_factory_request="$tmp_root/artifact-factory-source-pack-batch.json"
  artifact_factory_response="$tmp_root/artifact-factory-source-pack-batch-response.json"
  materializer_args=(
    "python3"
    "$ARTIFACT_FACTORY_REQUEST_MATERIALIZER"
    "--release-manifest" "$MANIFEST_PATH"
    "--promotion-result" "$response_json"
    "--requested-by" "$ARTIFACT_FACTORY_REQUESTED_BY"
    "--output" "$artifact_factory_request"
  )
  if [[ -n "$RELEASE_PROOF_PATH_RESOLVED" ]]; then
    materializer_args+=("--release-proof" "$RELEASE_PROOF_PATH_RESOLVED")
  fi
  IFS=',' read -r -a required_families <<< "$ARTIFACT_FACTORY_REQUIRED_FAMILIES"
  for family in "${required_families[@]}"; do
    family="$(echo "$family" | xargs)"
    [[ -n "$family" ]] || continue
    materializer_args+=("--required-family" "$family")
  done
  IFS=',' read -r -a requested_formats <<< "$ARTIFACT_FACTORY_REQUESTED_FORMATS"
  for requested_format in "${requested_formats[@]}"; do
    requested_format="$(echo "$requested_format" | xargs)"
    [[ -n "$requested_format" ]] || continue
    materializer_args+=("--requested-format" "$requested_format")
  done
  if [[ -n "${ARTIFACT_FACTORY_AUDIENCE:-}" ]]; then
    materializer_args+=("--audience" "$ARTIFACT_FACTORY_AUDIENCE")
  fi
  if [[ -n "${ARTIFACT_FACTORY_LOCALE:-}" ]]; then
    materializer_args+=("--locale" "$ARTIFACT_FACTORY_LOCALE")
  fi
  IFS=':' read -r -a source_pack_files <<< "$ARTIFACT_FACTORY_SOURCE_PACKS"
  for source_pack_file in "${source_pack_files[@]}"; do
    source_pack_file="$(echo "$source_pack_file" | xargs)"
    [[ -n "$source_pack_file" ]] || continue
    materializer_args+=("--source-pack-file" "$source_pack_file")
  done
  "${materializer_args[@]}"

  python3 "$ARTIFACT_FACTORY_LAUNCHER" \
    --base-url "$ARTIFACT_FACTORY_BASE_URL" \
    --token "$ARTIFACT_FACTORY_TOKEN" \
    --request-file "$artifact_factory_request" > "$artifact_factory_response"
  echo "Artifact-factory batch launched via $ARTIFACT_FACTORY_BASE_URL"
fi

if to_bool "$VERIFY_ROUTES"; then
  verify_routes="${CHUMMER_RELEASE_UPLOAD_VERIFY_URLS:-$(build_default_verify_routes)}"
  while IFS= read -r route; do
    [[ -n "$route" ]] || continue
    verify_route "$route"
  done <<< "$verify_routes"
fi

echo "Live publish verification completed."
