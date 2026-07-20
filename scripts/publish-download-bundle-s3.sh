#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"

BUNDLE_DIR="${1:-${DOWNLOAD_BUNDLE_DIR:-$REPO_ROOT/dist}}"
MANIFEST_SOURCE="$BUNDLE_DIR/releases.json"
CANONICAL_MANIFEST_SOURCE="$BUNDLE_DIR/RELEASE_CHANNEL.generated.json"
FILES_SOURCE="$BUNDLE_DIR/files"
PROOF_SOURCE="$BUNDLE_DIR/proof"
STARTUP_SMOKE_SOURCE="${STARTUP_SMOKE_SOURCE:-$BUNDLE_DIR/startup-smoke}"
RELEASE_EVIDENCE_SOURCE="${RELEASE_EVIDENCE_SOURCE:-$BUNDLE_DIR/release-evidence}"
S3_TARGET_URI="${CHUMMER_PORTAL_DOWNLOADS_S3_URI:-}"
S3_LATEST_URI="${CHUMMER_PORTAL_DOWNLOADS_S3_LATEST_URI:-}"
S3_ENDPOINT_URL="${CHUMMER_PORTAL_DOWNLOADS_S3_ENDPOINT_URL:-}"
VERIFY_URL="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}"
CURRENT_VERIFY_URL="${CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL:-}"
GENERATION_VERIFY_BASE_URL="${CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL:-}"
RELEASE_SHELF_HELPER="$SCRIPT_DIR/release_shelf_generation.py"
SHELF_LAYOUT_MARKER=".release-shelf-layout-v1"
SHELF_GENERATION_ID="${CHUMMER_RELEASE_GENERATION_ID:-}"
PRIMARY_RELEASE_COMMITTED=false
PRIMARY_COMMITTED_GENERATION=""
EXACT_INCOMING_SCOPE_DECLARED="${CHUMMER_RELEASE_EXACT_INCOMING_TUPLES+yes}"
EXACT_INCOMING_SCOPE="${CHUMMER_RELEASE_EXACT_INCOMING_TUPLES-}"

if [[ ! -f "$MANIFEST_SOURCE" || ! -d "$FILES_SOURCE" ]]; then
  echo "Expected desktop-download-bundle layout: releases.json + files/chummer-*" >&2
  exit 1
fi

if [[ ! -f "$CANONICAL_MANIFEST_SOURCE" ]]; then
  if [[ ! -f "$REGISTRY_ROOT/scripts/materialize_public_release_channel.py" ]]; then
    echo "Missing registry materializer: $REGISTRY_ROOT/scripts/materialize_public_release_channel.py" >&2
    exit 1
  fi
  python3 "$REGISTRY_ROOT/scripts/materialize_public_release_channel.py" \
    --downloads-dir "$FILES_SOURCE" \
    --output "$CANONICAL_MANIFEST_SOURCE" \
    --compat-output "$MANIFEST_SOURCE" >/dev/null
fi

if [[ ! -f "$RELEASE_SHELF_HELPER" ]]; then
  echo "Missing immutable release shelf helper: $RELEASE_SHELF_HELPER" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/verify-windows-installer-payloads.py" ]]; then
  echo "Missing Windows installer payload gate: $SCRIPT_DIR/verify-windows-installer-payloads.py" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/verify-windows-installer-payloads.py" \
  --files-dir "$FILES_SOURCE" \
  --manifest "$MANIFEST_SOURCE" \
  --manifest "$CANONICAL_MANIFEST_SOURCE" \
  --allow-empty

if [[ ! -f "$SCRIPT_DIR/verify-windows-installer-visual-proof.py" ]]; then
  echo "Missing Windows installer visual proof gate: $SCRIPT_DIR/verify-windows-installer-visual-proof.py" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/verify-windows-installer-visual-proof.py" \
  --files-dir "$FILES_SOURCE" \
  --manifest "$MANIFEST_SOURCE" \
  --manifest "$CANONICAL_MANIFEST_SOURCE" \
  --allow-empty

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

sha256_for_file() {
  python3 - "$1" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

aws_cli() {
  if [[ -n "$S3_ENDPOINT_URL" ]]; then
    command aws --endpoint-url "$S3_ENDPOINT_URL" "$@"
  else
    command aws "$@"
  fi
}

filtered_files_dir="$(mktemp -d)"
generation_candidate_dir="$(mktemp -d)"
prepared_layout_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$filtered_files_dir" "$generation_candidate_dir" "$prepared_layout_dir"
}
report_publish_error() {
  local status="$1"
  if [[ "$PRIMARY_RELEASE_COMMITTED" == true ]]; then
    echo "PRIMARY_RELEASE_COMMITTED generation=$PRIMARY_COMMITTED_GENERATION; a post-commit verification or latest-alias step failed" >&2
  else
    echo "PRIMARY_RELEASE_NOT_COMMITTED; publication failed before the primary current.json commit point" >&2
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'report_publish_error "$?"' ERR

mkdir -p "$filtered_files_dir"
while IFS= read -r artifact; do
  [[ -f "$artifact" ]] || continue
  cp "$artifact" "$filtered_files_dir/"
done < <(find "$FILES_SOURCE" -maxdepth 1 -type f \( \
  -name 'chummer-*-installer.exe' -o \
  -name 'chummer-*-installer.deb' -o \
  -name 'chummer-*-installer.pkg' -o \
  -name 'chummer-*-installer.dmg' -o \
  -name 'chummer-*-installer.msix' -o \
  -name 'chummer-*-win-*-payload.zip' -o \
  -name 'chummer-*-win-*-payload.zip.json' \
\) | sort)

parse_s3_uri() {
  local target_uri="${1%/}"
  local without_scheme=""
  if [[ "$target_uri" != s3://* ]]; then
    echo "Object-storage target must use s3://: $target_uri" >&2
    return 1
  fi
  without_scheme="${target_uri#s3://}"
  S3_BUCKET="${without_scheme%%/*}"
  if [[ "$without_scheme" == */* ]]; then
    S3_PREFIX="${without_scheme#*/}"
  else
    S3_PREFIX=""
  fi
  S3_PREFIX="${S3_PREFIX%/}"
  if [[ -z "$S3_BUCKET" ]]; then
    echo "Object-storage target is missing a bucket: $target_uri" >&2
    return 1
  fi
}

s3_object_key() {
  local target_uri="$1"
  local relative_path="$2"
  parse_s3_uri "$target_uri"
  if [[ -n "$S3_PREFIX" ]]; then
    S3_OBJECT_KEY="$S3_PREFIX/$relative_path"
  else
    S3_OBJECT_KEY="$relative_path"
  fi
}

s3_head_or_absent() {
  local target_uri="$1"
  local relative_path="$2"
  local head_tmp=""
  local list_json=""
  local exact_count=""
  s3_object_key "$target_uri" "$relative_path"
  head_tmp="$(mktemp)"
  if aws_cli s3api head-object \
      --bucket "$S3_BUCKET" \
      --key "$S3_OBJECT_KEY" >"$head_tmp" 2>/dev/null; then
    cat "$head_tmp"
    rm -f "$head_tmp"
    return 0
  fi
  rm -f "$head_tmp"
  if ! list_json="$(aws_cli s3api list-objects-v2 \
      --bucket "$S3_BUCKET" \
      --prefix "$S3_OBJECT_KEY" \
      --max-keys 2)"; then
    echo "Unable to distinguish a missing S3 object from an authorization/transport failure: $target_uri/$relative_path" >&2
    return 1
  fi
  exact_count="$(python3 -c 'import json, sys; payload=json.load(sys.stdin); key=sys.argv[1]; print(sum(1 for row in payload.get("Contents", []) if row.get("Key") == key))' "$S3_OBJECT_KEY" <<<"$list_json")"
  if [[ "$exact_count" == "0" ]]; then
    return 3
  fi
  echo "S3 listed $target_uri/$relative_path, but HeadObject failed; refusing to treat it as absent" >&2
  return 1
}

s3_require_empty_target_root() {
  local target_uri="$1"
  local listing_json=""
  local inventory_prefix=""
  parse_s3_uri "$target_uri"
  inventory_prefix="$S3_PREFIX"
  if ! listing_json="$(aws_cli s3api list-objects-v2 \
      --bucket "$S3_BUCKET" \
      --prefix "$inventory_prefix" \
      --max-keys 2)"; then
    echo "Unable to inventory first-generation S3 target root: $target_uri" >&2
    return 1
  fi

  if ! python3 - "$inventory_prefix" "$target_uri" "$listing_json" <<'PY'
import json
import sys

prefix, label, raw = sys.argv[1:]
try:
    payload = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"{label} returned malformed bounded root inventory: {exc}")
if not isinstance(payload, dict):
    raise SystemExit(f"{label} bounded root inventory must be an object")
contents = payload.get("Contents", [])
truncated = payload.get("IsTruncated")
key_count = payload.get("KeyCount")
if not isinstance(contents, list) or not isinstance(truncated, bool):
    raise SystemExit(f"{label} bounded root inventory is missing Contents/IsTruncated truth")
if not isinstance(key_count, int) or isinstance(key_count, bool) or key_count != len(contents):
    raise SystemExit(f"{label} bounded root inventory has an invalid KeyCount")
keys = []
for row in contents:
    if not isinstance(row, dict) or not isinstance(row.get("Key"), str):
        raise SystemExit(f"{label} bounded root inventory contains a malformed object row")
    keys.append(row["Key"])
root_keys = (
    keys
    if not prefix
    else [key for key in keys if key == prefix or key.startswith(prefix + "/")]
)
if root_keys:
    raise SystemExit(
        f"{label} is not empty; first governed object is {root_keys[0]!r}"
    )
if truncated:
    raise SystemExit(
        f"{label} bounded inventory is truncated before emptiness can be proved"
    )
PY
  then
    echo "Refusing first-generation activation because the S3 target root is non-empty or ambiguous: $target_uri" >&2
    return 1
  fi
}

s3_put_immutable_file() {
  local target_uri="$1"
  local relative_path="$2"
  local source_path="$3"
  local digest="$4"
  local cache_control="${5:-}"
  local -a args=()
  s3_object_key "$target_uri" "$relative_path"
  args=(
    s3api put-object
    --bucket "$S3_BUCKET"
    --key "$S3_OBJECT_KEY"
    --body "$source_path"
    --if-none-match '*'
  )
  if [[ -n "$digest" ]]; then
    args+=(--metadata "sha256=$digest")
  fi
  if [[ -n "$cache_control" ]]; then
    args+=(--cache-control "$cache_control")
  fi
  aws_cli "${args[@]}" >/dev/null
}

s3_put_current_pointer() {
  local target_uri="$1"
  local source_path="$2"
  local digest="$3"
  local expected_etag="$4"
  local expect_absent="$5"
  local -a args=()
  s3_object_key "$target_uri" "current.json"
  args=(
    s3api put-object
    --bucket "$S3_BUCKET"
    --key "$S3_OBJECT_KEY"
    --body "$source_path"
    --cache-control "no-store, max-age=0"
    --metadata "sha256=$digest"
  )
  if [[ "$expect_absent" == true ]]; then
    args+=(--if-none-match '*')
  else
    if [[ -z "$expected_etag" ]]; then
      echo "S3 current pointer CAS requires a captured ETag" >&2
      return 1
    fi
    args+=(--if-match "$expected_etag")
  fi
  aws_cli "${args[@]}" >/dev/null
}

validate_remote_current_generation() {
  local target_uri="$1"
  local pointer_path="$2"
  local generation_id="$3"
  local validation_root=""
  local generation_root=""
  local inventory_paths=""
  local relative_path=""
  validation_root="$(mktemp -d)"
  generation_root="$validation_root/$generation_id"
  inventory_paths="$validation_root/inventory-paths.txt"
  mkdir -p "$generation_root"
  if ! aws_cli s3 cp "$target_uri/generations/$generation_id/activation-candidate.json" \
      "$generation_root/activation-candidate.json" --only-show-errors \
    || ! aws_cli s3 cp "$target_uri/generations/$generation_id/RELEASE_CHANNEL.generated.json" \
      "$generation_root/RELEASE_CHANNEL.generated.json" --only-show-errors \
    || ! aws_cli s3 cp "$target_uri/generations/$generation_id/releases.json" \
      "$generation_root/releases.json" --only-show-errors; then
    rm -rf "$validation_root"
    echo "$target_uri current generation is missing required contract objects" >&2
    return 1
  fi
  if ! python3 - "$generation_root/activation-candidate.json" >"$inventory_paths" <<'PY'
import json
import re
import sys
from pathlib import PurePosixPath

payload = json.load(open(sys.argv[1], encoding="utf-8"))
rows = payload.get("inventory")
if not isinstance(rows, list) or not rows:
    raise SystemExit("activation candidate inventory must be a non-empty list")
for row in rows:
    if not isinstance(row, dict):
        raise SystemExit("activation candidate inventory row must be an object")
    raw = str(row.get("path") or "")
    path = PurePosixPath(raw)
    digest = str(row.get("sha256") or "")
    if (
        not raw
        or "\n" in raw
        or "\r" in raw
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise SystemExit(f"unsafe activation inventory row: {raw!r}")
    print(raw)
PY
  then
    rm -rf "$validation_root"
    echo "$target_uri current generation has an invalid activation inventory" >&2
    return 1
  fi
  while IFS= read -r relative_path; do
    [[ -n "$relative_path" ]] || continue
    mkdir -p "$generation_root/$(dirname "$relative_path")"
    if ! aws_cli s3 cp "$target_uri/generations/$generation_id/$relative_path" \
      "$generation_root/$relative_path" --only-show-errors; then
      rm -rf "$validation_root"
      echo "$target_uri current generation is missing inventory object $relative_path" >&2
      return 1
    fi
  done <"$inventory_paths"
  if ! python3 "$RELEASE_SHELF_HELPER" verify \
    --generation-root "$generation_root" \
    --pointer "$pointer_path" >/dev/null; then
    rm -rf "$validation_root"
    echo "$target_uri current generation failed immutable shelf validation" >&2
    return 1
  fi
  rm -rf "$validation_root"
}

remote_layout_mode() {
  local target_uri="$1"
  local marker_head=""
  local pointer_head=""
  local presence_status=0
  local pointer_tmp=""
  local pointer_json=""
  local current_generation=""
  if pointer_head="$(s3_head_or_absent "$target_uri" "current.json")"; then
    pointer_tmp="$(mktemp)"
    aws_cli s3 cp "$target_uri/current.json" "$pointer_tmp" --only-show-errors
    pointer_json="$(python3 "$RELEASE_SHELF_HELPER" pointer --pointer "$pointer_tmp")"
    current_generation="$(python3 -c 'import json, sys; print(json.load(sys.stdin)["generationId"])' <<<"$pointer_json")"
    if ! validate_remote_current_generation "$target_uri" "$pointer_tmp" "$current_generation"; then
      rm -f "$pointer_tmp"
      return 1
    fi
    rm -f "$pointer_tmp"
    printf 'generation\n'
    return 0
  else
    presence_status=$?
    if [[ "$presence_status" -ne 3 ]]; then
      return "$presence_status"
    fi
  fi

  if marker_head="$(s3_head_or_absent "$target_uri" "$SHELF_LAYOUT_MARKER")"; then
    echo "$target_uri has $SHELF_LAYOUT_MARKER without current.json; refusing legacy fallback" >&2
    return 1
  else
    presence_status=$?
    if [[ "$presence_status" -ne 3 ]]; then
      return "$presence_status"
    fi
  fi
  # Layout-v1 is the only supported S3 writer protocol. An empty target is an
  # explicit first-generation initialization; there is no legacy top-level
  # publication fallback or opt-in switch.
  if ! s3_require_empty_target_root "$target_uri"; then
    return 1
  fi
  printf 'generation-empty\n'
}

stage_release_shelf_generation() {
  mkdir -p "$generation_candidate_dir/files"
  cp "$MANIFEST_SOURCE" "$generation_candidate_dir/releases.json"
  cp "$CANONICAL_MANIFEST_SOURCE" "$generation_candidate_dir/RELEASE_CHANNEL.generated.json"
  cp "$filtered_files_dir/"* "$generation_candidate_dir/files/"
  if [[ -d "$PROOF_SOURCE" ]]; then
    cp -R "$PROOF_SOURCE" "$generation_candidate_dir/proof"
  fi
  if [[ -d "$STARTUP_SMOKE_SOURCE" ]]; then
    cp -R "$STARTUP_SMOKE_SOURCE" "$generation_candidate_dir/startup-smoke"
  fi
  if [[ -d "$RELEASE_EVIDENCE_SOURCE" ]]; then
    cp -R "$RELEASE_EVIDENCE_SOURCE" "$generation_candidate_dir/release-evidence"
  fi
  if [[ -f "$BUNDLE_DIR/aur-packages.json" ]]; then
    cp "$BUNDLE_DIR/aur-packages.json" "$generation_candidate_dir/aur-packages.json"
  fi
  prepare_args=(
    prepare
    --candidate-root "$generation_candidate_dir"
    --output-root "$prepared_layout_dir"
  )
  if [[ -n "$SHELF_GENERATION_ID" ]]; then
    prepare_args+=(--generation-id "$SHELF_GENERATION_ID")
  fi
  PREPARED_POINTER_JSON="$(python3 "$RELEASE_SHELF_HELPER" "${prepare_args[@]}")"
  PREPARED_GENERATION_ID="$(python3 -c 'import json, sys; print(json.load(sys.stdin)["generationId"])' <<<"$PREPARED_POINTER_JSON")"
  PREPARED_GENERATION_ROOT="$prepared_layout_dir/generations/$PREPARED_GENERATION_ID"
}

activate_release_shelf_generation() {
  local target_uri="$1"
  local target_mode="$2"
  local target_role="$3"
  local generation_uri="$target_uri/generations/$PREPARED_GENERATION_ID"
  local source_path=""
  local relative_path=""
  local digest=""
  local size_bytes=""
  local remote_head=""
  local remote_digest=""
  local remote_size=""
  local pointer_digest=""
  local pointer_tmp=""
  local pointer_head=""
  local current_pointer_json=""
  local current_generation=""
  local current_etag=""
  local presence_status=0
  local expect_absent=false
  local marker_head=""
  local marker_tmp=""
  if [[ "$target_mode" != "generation" && "$target_mode" != "generation-empty" ]]; then
    echo "internal error: generation upload selected for legacy target $target_uri" >&2
    return 1
  fi

  pointer_tmp="$(mktemp)"
  if pointer_head="$(s3_head_or_absent "$target_uri" "current.json")"; then
    current_etag="$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("ETag") or "")' <<<"$pointer_head")"
    if [[ -z "$current_etag" ]]; then
      rm -f "$pointer_tmp"
      echo "$target_uri current.json HeadObject response is missing ETag; CAS cannot proceed" >&2
      return 1
    fi
    aws_cli s3 cp "$target_uri/current.json" "$pointer_tmp" --only-show-errors
    current_pointer_json="$(python3 "$RELEASE_SHELF_HELPER" pointer --pointer "$pointer_tmp")"
    current_generation="$(python3 -c 'import json, sys; print(json.load(sys.stdin)["generationId"])' <<<"$current_pointer_json")"
    validate_remote_current_generation "$target_uri" "$pointer_tmp" "$current_generation"
    if ! python3 - "$pointer_tmp" "$prepared_layout_dir/current.json" <<'PY'
import json
import sys
from datetime import datetime

def instant(value):
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)

current = json.load(open(sys.argv[1], encoding="utf-8"))
incoming = json.load(open(sys.argv[2], encoding="utf-8"))
if instant(incoming.get("publishedAt")) <= instant(current.get("publishedAt")):
    raise SystemExit(
        "incoming release publishedAt must be strictly newer than the active S3 generation"
    )
PY
    then
      rm -f "$pointer_tmp"
      return 1
    fi
  else
    presence_status=$?
    if [[ "$presence_status" -ne 3 ]]; then
      rm -f "$pointer_tmp"
      return "$presence_status"
    fi
    if [[ "$target_mode" != "generation-empty" ]]; then
      rm -f "$pointer_tmp"
      echo "$target_uri current.json disappeared after validated layout discovery; refusing first-generation fallback" >&2
      return 1
    fi
    expect_absent=true
    if marker_head="$(s3_head_or_absent "$target_uri" "$SHELF_LAYOUT_MARKER")"; then
      rm -f "$pointer_tmp"
      echo "$target_uri has $SHELF_LAYOUT_MARKER without current.json; refusing ambiguous activation" >&2
      return 1
    else
      presence_status=$?
      if [[ "$presence_status" -ne 3 ]]; then
        rm -f "$pointer_tmp"
        return "$presence_status"
      fi
    fi
    if ! s3_require_empty_target_root "$target_uri"; then
      rm -f "$pointer_tmp"
      return 1
    fi
  fi

  while IFS= read -r -d '' source_path; do
    relative_path="${source_path#"$PREPARED_GENERATION_ROOT/"}"
    digest="$(sha256_for_file "$source_path")"
    size_bytes="$(wc -c <"$source_path" | tr -d ' ')"
    if ! s3_put_immutable_file \
        "$target_uri" \
        "generations/$PREPARED_GENERATION_ID/$relative_path" \
        "$source_path" \
        "$digest"; then
      rm -f "$pointer_tmp"
      echo "Refusing to overwrite or reuse immutable generation object: $generation_uri/$relative_path" >&2
      return 1
    fi
    s3_object_key "$target_uri" "generations/$PREPARED_GENERATION_ID/$relative_path"
    remote_head="$(aws_cli s3api head-object --bucket "$S3_BUCKET" --key "$S3_OBJECT_KEY")"
    remote_digest="$(python3 -c 'import json, sys; print((json.load(sys.stdin).get("Metadata") or {}).get("sha256") or "")' <<<"$remote_head")"
    remote_size="$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("ContentLength") or 0)' <<<"$remote_head")"
    if [[ "$remote_digest" != "$digest" || "$remote_size" != "$size_bytes" ]]; then
      echo "Remote generation object verification failed: $generation_uri/$relative_path" >&2
      return 1
    fi
  done < <(find "$PREPARED_GENERATION_ROOT" -type f -print0)

  # This single PutObject is the publication commit point after every immutable
  # object and metadata digest was verified. A valid pointer is sufficient for v1
  # readers, so a crash cannot strand a precommit marker without a current shelf.
  pointer_digest="$(sha256_for_file "$prepared_layout_dir/current.json")"
  if ! s3_put_current_pointer \
      "$target_uri" \
      "$prepared_layout_dir/current.json" \
      "$pointer_digest" \
      "$current_etag" \
      "$expect_absent"; then
    # A lost response after a successful conditional PutObject is reconciled by
    # exact pointer bytes. A different pointer is a clean CAS loss.
    if ! aws_cli s3 cp "$target_uri/current.json" "$pointer_tmp" --only-show-errors \
      || ! cmp -s "$prepared_layout_dir/current.json" "$pointer_tmp"; then
      rm -f "$pointer_tmp"
      echo "S3 current.json CAS failed; another publisher won or the commit outcome is unverifiable at $target_uri" >&2
      return 1
    fi
  fi
  # A successful conditional PutObject, or the exact-byte reconciliation above
  # after a lost response, is the publication commit point. Record that truth
  # before any fallible readback, marker, latest-alias, or HTTP verification.
  if [[ "$target_role" == "primary" ]]; then
    PRIMARY_RELEASE_COMMITTED=true
    PRIMARY_COMMITTED_GENERATION="$PREPARED_GENERATION_ID"
  fi
  aws_cli s3 cp "$target_uri/current.json" "$pointer_tmp" --only-show-errors
  if ! cmp -s "$prepared_layout_dir/current.json" "$pointer_tmp"; then
    rm -f "$pointer_tmp"
    echo "Remote current.json differs after activation at $target_uri" >&2
    return 1
  fi
  rm -f "$pointer_tmp"
  # The marker is a durable post-commit "ever crossed" downgrade sentinel. Its
  # failure cannot turn a live committed generation into a safe-to-retry error.
  if marker_head="$(s3_head_or_absent "$target_uri" "$SHELF_LAYOUT_MARKER")"; then
    marker_tmp="$(mktemp)"
    if ! aws_cli s3 cp "$target_uri/$SHELF_LAYOUT_MARKER" "$marker_tmp" --only-show-errors \
      || ! cmp -s "$prepared_layout_dir/$SHELF_LAYOUT_MARKER" "$marker_tmp"; then
      rm -f "$marker_tmp"
      echo "existing S3 layout marker is not byte-identical to the immutable layout-v1 sentinel" >&2
      return 1
    fi
    rm -f "$marker_tmp"
  else
    presence_status=$?
    if [[ "$presence_status" -ne 3 ]]; then
      return "$presence_status"
    fi
    if ! s3_put_immutable_file \
        "$target_uri" \
        "$SHELF_LAYOUT_MARKER" \
        "$prepared_layout_dir/$SHELF_LAYOUT_MARKER" \
        "" \
        "no-store"; then
      marker_tmp="$(mktemp)"
      if ! aws_cli s3 cp "$target_uri/$SHELF_LAYOUT_MARKER" "$marker_tmp" --only-show-errors \
        || ! cmp -s "$prepared_layout_dir/$SHELF_LAYOUT_MARKER" "$marker_tmp"; then
        rm -f "$marker_tmp"
        echo "current.json is committed, but immutable layout marker reconciliation failed at $target_uri" >&2
        return 1
      fi
      rm -f "$marker_tmp"
    fi
  fi
  echo "Activated immutable release shelf generation $PREPARED_GENERATION_ID at $target_uri"
}

replacement_preflight_args=(
  --existing "$VERIFY_URL" \
  --incoming "$CANONICAL_MANIFEST_SOURCE" \
  --selected-files-dir "$filtered_files_dir" \
  --allow-missing-existing
)
if [[ "$EXACT_INCOMING_SCOPE_DECLARED" == "yes" ]]; then
  replacement_preflight_args+=(--exact-incoming-scope "$EXACT_INCOMING_SCOPE")
fi
python3 "$SCRIPT_DIR/verify_release_shelf_replacement.py" "${replacement_preflight_args[@]}"

PRIMARY_TARGET_MODE="$(remote_layout_mode "$S3_TARGET_URI")"
LATEST_TARGET_MODE=""
if [[ -n "$S3_LATEST_URI" ]]; then
  LATEST_TARGET_MODE="$(remote_layout_mode "$S3_LATEST_URI")"
fi

stage_release_shelf_generation
activate_release_shelf_generation "$S3_TARGET_URI" "$PRIMARY_TARGET_MODE" "primary"
if [[ -n "$S3_LATEST_URI" ]]; then
  activate_release_shelf_generation "$S3_LATEST_URI" "$LATEST_TARGET_MODE" "latest"
fi

verify_base="${VERIFY_URL%/}"
case "$verify_base" in
  */RELEASE_CHANNEL.generated.json|*/releases.json|*/current.json)
    verify_base="${verify_base%/*}"
    ;;
esac
CURRENT_VERIFY_URL="${CURRENT_VERIFY_URL:-$verify_base/current.json}"
GENERATION_VERIFY_BASE_URL="${GENERATION_VERIFY_BASE_URL:-$verify_base/g}"
python3 "$RELEASE_SHELF_HELPER" verify-http \
  --pointer-url "$CURRENT_VERIFY_URL" \
  --generation-base-url "$GENERATION_VERIFY_BASE_URL" \
  --expected-generation-id "$PREPARED_GENERATION_ID"

artifact_count="$(find "$filtered_files_dir" -maxdepth 1 -type f \( \
  -name 'chummer-*-installer.exe' -o \
  -name 'chummer-*-installer.deb' -o \
  -name 'chummer-*-installer.pkg' -o \
  -name 'chummer-*-installer.dmg' -o \
  -name 'chummer-*-installer.msix' \
\) | wc -l | tr -d ' ')"
echo "Published ${artifact_count} public desktop artifact(s) to object storage target: $S3_TARGET_URI"
if [[ -n "$S3_LATEST_URI" ]]; then
  echo "Also published latest alias target: $S3_LATEST_URI"
fi
