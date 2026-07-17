#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"

BUNDLE_DIR="${1:-${DOWNLOAD_BUNDLE_DIR:-$REPO_ROOT/Chummer.Portal/downloads}}"
MANIFEST_PATH="${CHUMMER_RELEASE_UPLOAD_MANIFEST_PATH:-$BUNDLE_DIR/releases.json}"
CANONICAL_MANIFEST_PATH="${CHUMMER_RELEASE_UPLOAD_CANONICAL_MANIFEST_PATH:-$BUNDLE_DIR/RELEASE_CHANNEL.generated.json}"
LEGACY_DIRECT_UPLOAD_URL="${CHUMMER_RELEASE_UPLOAD_URL:-}"
SESSIONS_URL="${CHUMMER_RELEASE_UPLOAD_SESSIONS_URL:-https://chummer.run/api/internal/releases/upload-sessions}"
PUBLIC_BASE_URL="${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}"
VERIFY_URL="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-$PUBLIC_BASE_URL/downloads/RELEASE_CHANNEL.generated.json}"
TOKEN="${CHUMMER_RELEASE_UPLOAD_TOKEN:-}"
TOKEN_FILE="${CHUMMER_RELEASE_UPLOAD_TOKEN_FILE:-${CHUMMER_RELEASE_UPLOAD_TOKEN_PATH:-}}"
CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE="${CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE:-0}"
ARTIFACT_FACTORY_AUTOLAUNCH="${CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH:-1}"
ARTIFACT_FACTORY_REQUIRED="${CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH_REQUIRED:-0}"
ARTIFACT_FACTORY_TOKEN="${CHUMMER_ARTIFACT_FACTORY_TOKEN:-}"
ARTIFACT_FACTORY_REQUESTED_BY="${CHUMMER_ARTIFACT_FACTORY_REQUESTED_BY:-fleet.release}"
ARTIFACT_FACTORY_REQUIRED_FAMILIES="${CHUMMER_ARTIFACT_FACTORY_REQUIRED_FAMILIES:-}"
ARTIFACT_FACTORY_SOURCE_PACKS="${CHUMMER_ARTIFACT_FACTORY_SOURCE_PACKS:-}"
ARTIFACT_FACTORY_REQUESTED_FORMATS="${CHUMMER_ARTIFACT_FACTORY_REQUESTED_FORMATS:-}"
ARTIFACT_FACTORY_AUDIENCE="${CHUMMER_ARTIFACT_FACTORY_AUDIENCE:-}"
ARTIFACT_FACTORY_LOCALE="${CHUMMER_ARTIFACT_FACTORY_LOCALE:-}"
ALLOW_DIRECT_FALLBACK="${CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK:-0}"
DRY_RUN="${CHUMMER_RELEASE_UPLOAD_DRY_RUN:-0}"
VERIFY_MANIFEST="${CHUMMER_RELEASE_UPLOAD_VERIFY_MANIFEST:-1}"
VERIFY_ROUTES="${CHUMMER_RELEASE_UPLOAD_VERIFY_ROUTES:-1}"
VERIFY_SHELF_TRUTH="${CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH:-1}"
VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT="${CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT:-3}"
VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS="${CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS:-2}"
VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES="${CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES:-6}"
VERIFY_PUBLIC_SHELL_TRUTH="${CHUMMER_RELEASE_UPLOAD_VERIFY_PUBLIC_SHELL_TRUTH:-1}"
ALLOW_PROOF_ONLY_VISUAL_HANDOFF="${CHUMMER_RELEASE_UPLOAD_ALLOW_PROOF_ONLY_VISUAL_HANDOFF:-0}"
FORCE_NIGHTLY_PUBLISH="${CHUMMER_FORCE_NIGHTLY_PUBLISH:-0}"
WINDOWS_VISUAL_PROOF_HANDOFF_PATH="${CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF_PATH:-$BUNDLE_DIR/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json}"
WINDOWS_DESKTOP_EXIT_GATE_PATH="${CHUMMER_UI_WINDOWS_DESKTOP_EXIT_GATE_PATH:-$BUNDLE_DIR/UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json}"
CHUNK_BYTES="${CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES:-52428800}"
DIRECT_LIMIT_BYTES="${CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES:-$CHUNK_BYTES}"
MAX_RESPONSE_BYTES="${CHUMMER_RELEASE_UPLOAD_MAX_RESPONSE_BYTES:-1048576}"
ARTIFACT_FACTORY_REQUEST_MATERIALIZER="$SCRIPT_DIR/materialize_artifact_factory_source_pack_batch.py"
ARTIFACT_FACTORY_LAUNCHER="$SCRIPT_DIR/launch_artifact_factory_source_pack_batch.py"
UPLOAD_ATTEMPT_RECEIPT_HELPER="${CHUMMER_RELEASE_UPLOAD_ATTEMPT_RECEIPT_HELPER:-$SCRIPT_DIR/release/release_upload_attempt_receipt.py}"
UPLOAD_ATTEMPT_RECEIPT_PATH="${CHUMMER_RELEASE_UPLOAD_ATTEMPT_RECEIPT_PATH:-$BUNDLE_DIR/release-upload-handoff.json}"

# Keep inherited bearer credentials out of every preflight/materializer child.
# Bash preserves an inherited export attribute across ordinary assignment, so
# explicitly de-export the private shell copies before invoking any child.
export -n TOKEN TOKEN_FILE ARTIFACT_FACTORY_TOKEN 2>/dev/null || true
unset \
  CHUMMER_RELEASE_UPLOAD_TOKEN \
  CHUMMER_RELEASE_UPLOAD_TOKEN_FILE \
  CHUMMER_RELEASE_UPLOAD_TOKEN_PATH \
  CHUMMER_RELEASE_UPLOAD_TICKET \
  CHUMMER_RELEASE_UPLOAD_TICKET_FILE \
  CHUMMER_RELEASE_UPLOAD_TICKET_PATH \
  CHUMMER_ARTIFACT_FACTORY_TOKEN \
  FLEET_INTERNAL_API_TOKEN \
  UPLOAD_AUTH_VALUE

if [[ ! -d "$BUNDLE_DIR" ]]; then
  echo "Bundle directory not found: $BUNDLE_DIR" >&2
  exit 1
fi

if [[ ! "$MAX_RESPONSE_BYTES" =~ ^[0-9]+$ ]] || (( MAX_RESPONSE_BYTES < 1024 || MAX_RESPONSE_BYTES > 16777216 )); then
  echo "CHUMMER_RELEASE_UPLOAD_MAX_RESPONSE_BYTES must be an integer from 1024 through 16777216." >&2
  exit 1
fi

if [[ -n "$LEGACY_DIRECT_UPLOAD_URL" ]]; then
  echo "CHUMMER_RELEASE_UPLOAD_URL is retired; configure CHUMMER_RELEASE_UPLOAD_SESSIONS_URL only." >&2
  exit 1
fi

case "$(printf '%s' "$ALLOW_DIRECT_FALLBACK" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on)
    echo "Direct release upload fallback is permanently disabled; use the durable upload-session protocol." >&2
    exit 1
    ;;
esac

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

if [[ ! -f "$SCRIPT_DIR/verify-windows-installer-payloads.py" ]]; then
  echo "Missing Windows installer payload gate: $SCRIPT_DIR/verify-windows-installer-payloads.py" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/verify-windows-installer-payloads.py" \
  --files-dir "$BUNDLE_DIR/files" \
  --manifest "$MANIFEST_PATH" \
  --manifest "$CANONICAL_MANIFEST_PATH" \
  --allow-empty

case "$(printf '%s' "$ALLOW_PROOF_ONLY_VISUAL_HANDOFF" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on)
    case "$(printf '%s' "$FORCE_NIGHTLY_PUBLISH" | tr '[:upper:]' '[:lower:]')" in
      1|true|yes|on) ;;
      *)
        echo "Proof-only Windows visual handoff also requires CHUMMER_FORCE_NIGHTLY_PUBLISH=1." >&2
        exit 1
        ;;
    esac
    if [[ ! -f "$SCRIPT_DIR/verify-windows-installer-visual-proof-handoff.py" ]]; then
      echo "Missing Windows proof-only visual handoff gate: $SCRIPT_DIR/verify-windows-installer-visual-proof-handoff.py" >&2
      exit 1
    fi
    python3 "$SCRIPT_DIR/verify-windows-installer-visual-proof-handoff.py" \
      --files-dir "$BUNDLE_DIR/files" \
      --manifest "$MANIFEST_PATH" \
      --manifest "$CANONICAL_MANIFEST_PATH" \
      --handoff "$WINDOWS_VISUAL_PROOF_HANDOFF_PATH" \
      --windows-gate "$WINDOWS_DESKTOP_EXIT_GATE_PATH"
    ;;
  0|false|no|off|"")
    if [[ ! -f "$SCRIPT_DIR/verify-windows-installer-visual-proof.py" ]]; then
      echo "Missing Windows installer visual proof gate: $SCRIPT_DIR/verify-windows-installer-visual-proof.py" >&2
      exit 1
    fi
    python3 "$SCRIPT_DIR/verify-windows-installer-visual-proof.py" \
      --files-dir "$BUNDLE_DIR/files" \
      --manifest "$MANIFEST_PATH" \
      --manifest "$CANONICAL_MANIFEST_PATH" \
      --allow-empty
    ;;
  *)
    echo "CHUMMER_RELEASE_UPLOAD_ALLOW_PROOF_ONLY_VISUAL_HANDOFF must be an explicit boolean." >&2
    exit 1
    ;;
esac

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
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

canonicalize_bundle_release_channel_registries() {
  canonicalize_release_channel_registries "$MANIFEST_PATH"
  canonicalize_release_channel_registries "$CANONICAL_MANIFEST_PATH"
}

resolve_upload_token() {
  if [[ -n "${TOKEN:-}" ]]; then
    if (( ${#TOKEN} > 8192 )) || [[ "$TOKEN" == *$'\n'* || "$TOKEN" == *$'\r'* ]]; then
      echo "Configured CHUMMER_RELEASE_UPLOAD_TOKEN must be a single value of at most 8192 bytes." >&2
      TOKEN=""
      return 1
    fi
    return 0
  fi

  if [[ -z "$TOKEN_FILE" ]]; then
    return 1
  fi

  if ! TOKEN="$(python3 - "$TOKEN_FILE" <<'PY'
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    metadata = path.lstat()
except OSError:
    raise SystemExit(1)
if (
    not stat.S_ISREG(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != os.geteuid()
    or stat.S_IMODE(metadata.st_mode) != 0o600
    or not (1 <= metadata.st_size <= 8192)
):
    raise SystemExit(1)
try:
    raw = path.read_bytes()
except OSError:
    raise SystemExit(1)
if b"\x00" in raw:
    raise SystemExit(1)
try:
    value = raw.decode("utf-8").rstrip("\r\n")
except UnicodeDecodeError:
    raise SystemExit(1)
if not value or "\r" in value or "\n" in value:
    raise SystemExit(1)
sys.stdout.write(value)
PY
  )"; then
    echo "Configured CHUMMER_RELEASE_UPLOAD_TOKEN_FILE must be a current-owner, non-symlink regular file with mode 0600 containing one UTF-8 line (1-8192 bytes): $TOKEN_FILE" >&2
    TOKEN=""
    return 1
  fi
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
  local auth_value="${1:-}"
  export -n auth_value 2>/dev/null || true
  [[ -n "$auth_value" ]] || return 1
  printf '%s' "$auth_value" \
    | python3 -c 'import sys; token = sys.stdin.read(); escaped = token.replace("\\\\", "\\\\\\\\").replace("\"", "\\\\\""); sys.stdout.write(f"header = \"Authorization: Bearer {escaped}\"\n")'
}

authenticated_curl() {
  write_auth_curl_config "$UPLOAD_AUTH_VALUE" \
    | curl -q --config - "$@"
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
from urllib.parse import unquote, urljoin, urlsplit

base_text = str(sys.argv[1]).strip()
candidate_text = str(sys.argv[2]).strip()
base = urlsplit(base_text)
if (
    base.scheme not in {"http", "https"}
    or not base.hostname
    or base.username is not None
    or base.password is not None
    or base.query
    or base.fragment
    or not base.path.rstrip("/").endswith("/upload-sessions")
):
    raise SystemExit("upload sessions base URL is invalid")

resolved = urlsplit(urljoin(base_text.rstrip("/") + "/", candidate_text))
try:
    base_authority = (base.scheme.lower(), base.hostname.lower(), base.port)
    resolved_authority = (resolved.scheme.lower(), (resolved.hostname or "").lower(), resolved.port)
except ValueError as exc:
    raise SystemExit("upload session URL has an invalid port") from exc

decoded_path = unquote(resolved.path)
segments = decoded_path.replace("\\", "/").split("/")
required_prefix = base.path.rstrip("/") + "/"
if (
    resolved_authority != base_authority
    or resolved.username is not None
    or resolved.password is not None
    or resolved.query
    or resolved.fragment
    or "\\" in resolved.path
    or any(segment in {".", ".."} for segment in segments)
    or not decoded_path.startswith(required_prefix)
):
    raise SystemExit("upload session response URL escaped its same-origin session root")

print(resolved.geturl())
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
  [[ -f "$bundle_root/aur-packages.json" ]] && printf '%s\n' "$bundle_root/aur-packages.json"
  [[ -f "$bundle_root/release-evidence/public-promotion.json" ]] && printf '%s\n' "$bundle_root/release-evidence/public-promotion.json"
  if [[ -d "$bundle_root/files" ]]; then
    find "$bundle_root/files" -type f | sort
  fi
  if [[ -d "$bundle_root/startup-smoke" ]]; then
    find "$bundle_root/startup-smoke" -type f | sort
  fi
  if [[ -d "$bundle_root/signing" ]]; then
    find "$bundle_root/signing" -type f | sort
  fi
  if [[ -d "$bundle_root/proof" ]]; then
    find "$bundle_root/proof" -type f | sort
  fi
}

print_sanitized_response() {
  local response_path="$1"
  python3 - "$response_path" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
max_response_bytes = 1024 * 1024
try:
    response_size = path.stat().st_size
    if response_size > max_response_bytes:
        print(f"(response display suppressed; {response_size} bytes exceeds {max_response_bytes}-byte limit)")
        raise SystemExit(0)
    raw = path.read_bytes()
except OSError:
    print("(response unavailable)")
    raise SystemExit(0)

try:
    payload = json.loads(raw.decode("utf-8"))
except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, MemoryError, ValueError):
    print(f"(non-JSON response suppressed; {len(raw)} bytes)")
    raise SystemExit(0)

try:
    allowed_scalars = (
        "status",
        "state",
        "version",
        "releaseVersion",
        "channel",
        "generationId",
        "publishedAt",
        "type",
        "traceId",
        "requestId",
        "itemCount",
    )
    allowed_collections = (
        "installDispatchUrls",
        "directFileUrls",
        "signedInInstallClaims",
        "artifacts",
        "errors",
    )
    safe_characters = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/+-TZ")
    summary = {"responseType": "json"}
    if isinstance(payload, dict):
        for field in allowed_scalars:
            value = payload.get(field)
            if isinstance(value, bool):
                summary[field] = value
            elif isinstance(value, int) and -(2**63) <= value < 2**63:
                summary[field] = value
            elif isinstance(value, str) and 0 < len(value) <= 160 and all(character in safe_characters for character in value):
                summary[field] = value
        for field in allowed_collections:
            value = payload.get(field)
            if isinstance(value, (dict, list)):
                summary[f"{field}Count"] = len(value)
        summary["suppressedFieldCount"] = max(0, len(payload) - len(summary) + 1)
    elif isinstance(payload, list):
        summary["itemCount"] = len(payload)
    else:
        summary["valueSuppressed"] = True
    rendered = json.dumps(summary, indent=2, sort_keys=True)
except (RecursionError, MemoryError, TypeError, ValueError):
    print(f"(JSON response display suppressed; {len(raw)} bytes could not be safely summarized)")
    raise SystemExit(0)
print(rendered)
PY
}

sanitize_release_upload_response_stream() {
  local output_path="$1"
  python3 -c '
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

output_path = Path(sys.argv[1])
max_bytes = int(sys.argv[2])
raw = bytearray()
tail = bytearray()
total_bytes = 0
while True:
    chunk = sys.stdin.buffer.read(65536)
    if not chunk:
        break
    total_bytes += len(chunk)
    tail = (tail + chunk)[-128:]
    remaining = max(0, max_bytes + 129 - len(raw))
    if remaining:
        raw.extend(chunk[:remaining])

status_match = re.search(rb"\nCHUMMER_HTTP_STATUS:([0-9]{3})\Z", bytes(tail))
status_code = status_match.group(1).decode("ascii") if status_match else "000"
stream_overflow = total_bytes > max_bytes + 128
body = b""
if status_match and not stream_overflow:
    trailer_size = len(status_match.group(0))
    body = bytes(raw[:-trailer_size])
overflow = stream_overflow or len(body) > max_bytes

safe_scalar = re.compile(r"^[A-Za-z0-9._:/+ -]{1,2048}$")
safe_identifier = re.compile(r"^[A-Za-z0-9._:+-]{1,200}$")
endpoint_fields = {
    "filesUrl", "FilesUrl", "files_url", "files",
    "chunksUrl", "ChunksUrl", "chunks_url", "chunks",
    "completeUrl", "CompleteUrl", "complete_url", "complete",
}
scalar_fields = (
    "contractName", "sessionId", "SessionId", "session_id", "id",
    "expiresAtUtc", "ExpiresAtUtc", "expires_at_utc", "expiresAt",
    *sorted(endpoint_fields), "status", "state", "version", "channel",
    "publishedAt", "supportabilityState", "compatibilityState",
    "traceId", "requestId", "success", "fileCount", "totalBytes",
)

def safe_url(value: object, *, allow_relative: bool) -> str | None:
    if not isinstance(value, str) or not (1 <= len(value) <= 2048):
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    parsed = urlsplit(value)
    if parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:
        return None
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
    elif not allow_relative or not value.startswith("/"):
        return None
    return value

summary: dict[str, object] = {"responseSanitized": True}
payload: object = None
if not status_match:
    summary["responseSuppressed"] = "missing_http_status"
elif overflow:
    summary["responseSuppressed"] = "size_limit"
else:
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        summary["responseSuppressed"] = "non_json"

if isinstance(payload, dict):
    for field_name in scalar_fields:
        value = payload.get(field_name)
        if isinstance(value, bool) or isinstance(value, int):
            summary[field_name] = value
        elif field_name in endpoint_fields:
            safe_value = safe_url(value, allow_relative=True)
            if safe_value is not None:
                summary[field_name] = safe_value
        elif isinstance(value, str) and safe_scalar.fullmatch(value):
            summary[field_name] = value

    for field_name in ("installDispatchUrls", "directFileUrls"):
        values = payload.get(field_name)
        if isinstance(values, list):
            safe_values = [safe for item in values[:256] if (safe := safe_url(item, allow_relative=False)) is not None]
            summary[field_name] = safe_values

    promoted_ids = payload.get("promotedArtifactIds")
    if isinstance(promoted_ids, list):
        summary["promotedArtifactIds"] = [
            item for item in promoted_ids[:512]
            if isinstance(item, str) and safe_identifier.fullmatch(item)
        ]
    summary["suppressedFieldCount"] = max(0, len(payload) - len(summary) + 2)
elif isinstance(payload, list):
    summary["itemCount"] = len(payload)

if output_path == Path("/dev/null"):
    print(status_code)
    raise SystemExit(0 if status_match else 65)

output_path.parent.mkdir(parents=True, exist_ok=True)
fd, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
temporary_path = Path(temporary_name)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, output_path)
    directory_fd = os.open(output_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
finally:
    try:
        temporary_path.unlink()
    except FileNotFoundError:
        pass
print(status_code)
if not status_match:
    raise SystemExit(65)
' "$output_path" "$MAX_RESPONSE_BYTES"
}

request_json() {
  local response_path="$1"
  local label="$2"
  local url="$3"
  shift 3
  local http_status=""
  if ! http_status="$(authenticated_curl -sS --max-filesize "$MAX_RESPONSE_BYTES" \
      --write-out $'\nCHUMMER_HTTP_STATUS:%{http_code}' "$@" "$url" \
      | sanitize_release_upload_response_stream "$response_path")"; then
    echo "$label failed." >&2
    [[ -f "$response_path" ]] && print_sanitized_response "$response_path" >&2 || true
    return 22
  fi
  if [[ ! "$http_status" =~ ^2 ]]; then
    echo "$label failed with HTTP $http_status" >&2
    print_sanitized_response "$response_path" >&2 || true
    return 22
  fi
}

verify_route() {
  local url="$1"
  curl -fsSL --range 0-0 -o /dev/null "$url"
  echo "Verified route: $url"
}

build_default_verify_routes() {
  python3 - "$MANIFEST_PATH" "$PUBLIC_BASE_URL" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

manifest_path = Path(sys.argv[1])
base_url = str(sys.argv[2]).rstrip("/")
routes = [
    f"{base_url}/downloads/",
    f"{base_url}/status",
    f"{base_url}/help",
    f"{base_url}/contact",
    f"{base_url}/login?next=%2F",
    f"{base_url}/account/billing",
    f"{base_url}/participate",
    f"{base_url}/partizipate",
    f"{base_url}/roadmap",
]

try:
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
except Exception:
    print("\n".join(routes))
    raise SystemExit(0)

for row in payload.get("downloads") or payload.get("artifacts") or []:
    if not isinstance(row, dict) or row.get("disabled") is True:
        continue
    artifact_id = str(row.get("id") or row.get("artifactId") or "").strip()
    if artifact_id:
        routes.append(f"{base_url}/downloads/install/{artifact_id}")
    file_name = str(row.get("fileName") or "").strip()
    if not file_name:
        url = str(row.get("url") or row.get("downloadUrl") or "").strip()
        if url:
            file_name = Path(urlparse(url).path).name
    if file_name:
        routes.append(f"{base_url}/downloads/files/{file_name}")

print("\n".join(dict.fromkeys(routes)))
PY
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
  echo "Upload sessions URL: $SESSIONS_URL"
  echo "Files staged: $file_count"
  echo
  echo "Exact live publish command:"
  echo "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL='$VERIFY_URL' CHUMMER_RELEASE_UPLOAD_TOKEN_FILE='$TOKEN_FILE' bash '$SCRIPT_DIR/publish-download-bundle-http.sh' '$BUNDLE_DIR'"
  echo "If CHUMMER_RELEASE_UPLOAD_TOKEN is unset, set CHUMMER_RELEASE_UPLOAD_TOKEN_FILE or CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE=1."
  exit 0
fi

if [[ ! -f "$UPLOAD_ATTEMPT_RECEIPT_HELPER" || -L "$UPLOAD_ATTEMPT_RECEIPT_HELPER" ]]; then
  echo "Durable upload-attempt receipt helper is missing or unsafe: $UPLOAD_ATTEMPT_RECEIPT_HELPER" >&2
  exit 1
fi

python3 "$UPLOAD_ATTEMPT_RECEIPT_HELPER" preflight \
  --receipt "$UPLOAD_ATTEMPT_RECEIPT_PATH"

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

UPLOAD_AUTH_VALUE="$TOKEN"
export -n UPLOAD_AUTH_VALUE 2>/dev/null || true
TOKEN=""

tmp_root="$(mktemp -d)"
UPLOAD_COMPLETION_ACCEPTED=0
cleanup() {
  local status="$?"
  trap - EXIT
  rm -rf "$tmp_root" || true
  if (( status != 0 )) && (( UPLOAD_COMPLETION_ACCEPTED == 1 )); then
    echo "Release completion was accepted before a later check failed; the release may already be public. Do not create or publish another session. Inspect $UPLOAD_ATTEMPT_RECEIPT_PATH and reconcile the recorded session." >&2
  fi
  exit "$status"
}
trap cleanup EXIT

ARTIFACT_FACTORY_BASE_URL="$(resolve_base_url "${CHUMMER_ARTIFACT_FACTORY_BASE_URL:-}" "$SESSIONS_URL" "$PUBLIC_BASE_URL")"
RELEASE_PROOF_PATH_RESOLVED=""
if RELEASE_PROOF_PATH_RESOLVED="$(resolve_release_proof_path "$BUNDLE_DIR" "$REPO_ROOT" "${RELEASE_PROOF_PATH:-}")"; then
  :
else
  RELEASE_PROOF_PATH_RESOLVED=""
fi

request_common=(
  -H "Accept: application/json"
)

canonicalize_bundle_release_channel_registries

upload_files=()
while IFS= read -r file_path; do
  [[ -n "$file_path" ]] || continue
  upload_files+=("$file_path")
done < <(collect_upload_files "$BUNDLE_DIR")

upload_file_count="$(array_count upload_files)"

if (( upload_file_count == 0 )); then
  echo "Bundle has no uploadable files: $BUNDLE_DIR" >&2
  exit 1
fi

echo "Publishing ${upload_file_count} bundle files from $BUNDLE_DIR"

session_json="$tmp_root/session.json"
response_json="$tmp_root/response.json"

request_json "$session_json" "create upload session" "$SESSIONS_URL" "${request_common[@]}" -X POST
session_id="$(resolve_json_field "$session_json" sessionId SessionId session_id id)"
[[ "$session_id" =~ ^[0-9a-f]{32}$ ]] || {
  echo "Upload session response contains an unsafe sessionId." >&2
  exit 1
}
files_url="$(resolve_json_field "$session_json" filesUrl FilesUrl files_url files || true)"
chunks_url="$(resolve_json_field "$session_json" chunksUrl ChunksUrl chunks_url chunks || true)"
complete_url="$(resolve_json_field "$session_json" completeUrl CompleteUrl complete_url complete || true)"
expires_at="$(resolve_json_field "$session_json" expiresAtUtc ExpiresAtUtc expires_at_utc expiresAt || true)"
[[ -n "$session_id" ]] || {
  echo "Upload session response missing sessionId." >&2
  exit 1
}

record_upload_attempt_state() {
  local state="$1"
  shift
  python3 "$UPLOAD_ATTEMPT_RECEIPT_HELPER" transition \
    --receipt "$UPLOAD_ATTEMPT_RECEIPT_PATH" \
    --summary "$candidate_summary" \
    --sessions-url "$SESSIONS_URL" \
    --session-id "$session_id" \
    --expires-at "$expires_at" \
    --state "$state" \
    "$@"
}

if ! record_upload_attempt_state created; then
  echo "Upload session $session_id was created, but its durable recovery handoff could not be written; no files were uploaded." >&2
  exit 1
fi

[[ -n "$files_url" ]] || files_url="${SESSIONS_URL%/}/${session_id}/files"
[[ -n "$chunks_url" ]] || chunks_url="${SESSIONS_URL%/}/${session_id}/chunks"
[[ -n "$complete_url" ]] || complete_url="${SESSIONS_URL%/}/${session_id}/complete"
files_url="$(join_url "$SESSIONS_URL" "$files_url")"
chunks_url="$(join_url "$SESSIONS_URL" "$chunks_url")"
complete_url="$(join_url "$SESSIONS_URL" "$complete_url")"
expected_files_url="$(join_url "$SESSIONS_URL" "${session_id}/files")"
expected_chunks_url="$(join_url "$SESSIONS_URL" "${session_id}/chunks")"
expected_complete_url="$(join_url "$SESSIONS_URL" "${session_id}/complete")"
[[ "$files_url" == "$expected_files_url" \
    && "$chunks_url" == "$expected_chunks_url" \
    && "$complete_url" == "$expected_complete_url" ]] || {
  echo "Upload session response endpoints do not match the created session." >&2
  exit 1
}

while IFS= read -r -d '' file_path; do
  relative_path="${file_path#$BUNDLE_DIR/}"
  file_size="$(stat -c '%s' "$file_path" 2>/dev/null || stat -f '%z' "$file_path" 2>/dev/null || wc -c < "$file_path" || echo 0)"
  if (( file_size <= DIRECT_LIMIT_BYTES )); then
    upload_file_direct "$file_path" "$relative_path" "$files_url" "${request_common[@]}"
  else
    upload_file_chunked "$file_path" "$relative_path" "$chunks_url" "${request_common[@]}"
  fi
done < <(array_values_nul upload_files)

record_upload_attempt_state uploaded
record_upload_attempt_state request_started
if ! request_json "$response_json" "complete upload session" "$complete_url" "${request_common[@]}" -X POST; then
  echo "Release completion outcome is unknown. Do not create another session; reconcile the request_started handoff at $UPLOAD_ATTEMPT_RECEIPT_PATH." >&2
  exit 1
fi
UPLOAD_COMPLETION_ACCEPTED=1
python3 "$UPLOAD_ATTEMPT_RECEIPT_HELPER" fsync-file --path "$response_json"
if ! record_upload_attempt_state completed; then
  echo "Upload completion returned success, but the durable handoff could not be acknowledged; reconcile session $session_id instead of creating another release." >&2
  exit 1
fi

echo "Upload accepted."
print_sanitized_response "$response_json" || echo "(release response display suppressed)"
echo

python3 "$SCRIPT_DIR/verify_release_upload_response_truth.py" \
  --local-manifest "$MANIFEST_PATH" \
  --local-canonical-manifest "$CANONICAL_MANIFEST_PATH" \
  --upload-response "$response_json"

if to_bool "$VERIFY_MANIFEST"; then
  CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 \
    bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$VERIFY_URL"
fi

if to_bool "$ARTIFACT_FACTORY_AUTOLAUNCH"; then
  if [[ ! -f "$ARTIFACT_FACTORY_REQUEST_MATERIALIZER" ]]; then
    artifact_factory_failure "Artifact-factory request materializer missing: $ARTIFACT_FACTORY_REQUEST_MATERIALIZER"
  elif [[ ! -f "$ARTIFACT_FACTORY_LAUNCHER" ]]; then
    artifact_factory_failure "Artifact-factory launcher missing: $ARTIFACT_FACTORY_LAUNCHER"
  elif [[ -z "${ARTIFACT_FACTORY_TOKEN:-}" ]]; then
    artifact_factory_failure "Artifact-factory autolaunch requires its own CHUMMER_ARTIFACT_FACTORY_TOKEN; release-upload credentials are never reused."
  else
    artifact_factory_request="$tmp_root/artifact-factory-source-pack-batch.json"
    artifact_factory_response="$tmp_root/artifact-factory-source-pack-batch-response.json"
    artifact_factory_stderr="$tmp_root/artifact-factory-source-pack-batch.stderr"
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

    if ! "${materializer_args[@]}" > /dev/null 2> "$artifact_factory_stderr"; then
      artifact_factory_detail="$(tr '\r\n' '  ' < "$artifact_factory_stderr" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
      artifact_factory_failure "${artifact_factory_detail:-artifact-factory source-pack materialization failed.}"
    elif ! FLEET_INTERNAL_API_TOKEN="$ARTIFACT_FACTORY_TOKEN" python3 "$ARTIFACT_FACTORY_LAUNCHER" \
      --base-url "$ARTIFACT_FACTORY_BASE_URL" \
      --request-file "$artifact_factory_request" > "$artifact_factory_response" 2> "$artifact_factory_stderr"; then
      artifact_factory_detail="$(tr '\r\n' '  ' < "$artifact_factory_stderr" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
      artifact_factory_failure "${artifact_factory_detail:-artifact-factory batch launch failed.}"
    else
      echo "Artifact-factory batch launched via $ARTIFACT_FACTORY_BASE_URL"
    fi
    ARTIFACT_FACTORY_TOKEN=""
  fi
fi

if to_bool "$VERIFY_ROUTES"; then
  verify_routes="${CHUMMER_RELEASE_UPLOAD_VERIFY_URLS:-$(build_default_verify_routes)}"
  while IFS= read -r route; do
    [[ -n "$route" ]] || continue
    verify_route "$route"
  done <<< "$verify_routes"
fi

if to_bool "$VERIFY_SHELF_TRUTH"; then
  python3 "$SCRIPT_DIR/public_download_shelf_truth_gate.py" \
    --base-url "$PUBLIC_BASE_URL" \
    --local-manifest "$MANIFEST_PATH" \
    --local-canonical-manifest "$CANONICAL_MANIFEST_PATH" \
    --live-confirmation-count "$VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT" \
    --live-confirmation-delay-seconds "$VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS" \
    --live-max-samples "$VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES"
fi

if to_bool "$VERIFY_PUBLIC_SHELL_TRUTH"; then
  python3 "$SCRIPT_DIR/public_shell_minimal_truth_gate.py" \
    --base-url "$PUBLIC_BASE_URL"
fi

echo "Live publish verification completed."
