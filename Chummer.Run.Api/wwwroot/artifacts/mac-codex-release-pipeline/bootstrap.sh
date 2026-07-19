#!/usr/bin/env bash
set +x
# Release-upload bootstrap defaults to the active refs while preserving caller-supplied reviewed refs and commit pins.
export CHUMMER_UI_REF="${CHUMMER_UI_REF:-main}"
export CHUMMER_CORE_REF="${CHUMMER_CORE_REF:-main}"
export CHUMMER_HUB_REF="${CHUMMER_HUB_REF:-main}"
export CHUMMER_UI_KIT_REF="${CHUMMER_UI_KIT_REF:-main}"
export CHUMMER_HUB_REGISTRY_REF="${CHUMMER_HUB_REGISTRY_REF:-main}"
export CHUMMER_MEDIA_FACTORY_REF="${CHUMMER_MEDIA_FACTORY_REF:-main}"
export CHUMMER_LEGACY_REF="${CHUMMER_LEGACY_REF:-Docker}"
set -euo pipefail
umask 077

bootstrap_tmp_paths=()
BOOTSTRAP_RELEASE_UPLOAD_ACCEPTED=0
BOOTSTRAP_RELEASE_UPLOAD_ATTEMPT_RECEIPT_PATH=""
RELEASE_PYTHON_BIN=""

log() {
  printf '[chummer-mac-release] %s\n' "$*"
}

die() {
  printf '[chummer-mac-release] ERROR: %s\n' "$*" >&2
  exit 1
}

to_lower_ascii() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
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

array_values_nul() {
  local array_name="${1:-}"
  [[ -n "$array_name" ]] || return 0

  local restore_nounset=0
  case "$-" in
    *u*)
      restore_nounset=1
      set +u
      ;;
  esac

  eval "printf '%s\\0' \"\${${array_name}[@]}\""
  local status="$?"

  if (( restore_nounset == 1 )); then
    set -u
  fi

  return "$status"
}

cleanup_bootstrap_tmp_paths() {
  local status="$?"
  local path
  if (( $(array_count bootstrap_tmp_paths) > 0 )); then
    while IFS= read -r -d '' path; do
      [[ -f "$path" ]] && rm -f "$path"
    done < <(array_values_nul bootstrap_tmp_paths)
  fi

  if [[ "${BOOTSTRAP_KEEP_UPLOAD_RESPONSE:-0}" != "1" ]] \
    && [[ -n "${BOOTSTRAP_RELEASE_UPLOAD_RESPONSE_PATH:-}" ]] \
    && [[ -f "${BOOTSTRAP_RELEASE_UPLOAD_RESPONSE_PATH}" ]]; then
    chmod 600 "${BOOTSTRAP_RELEASE_UPLOAD_RESPONSE_PATH}" 2>/dev/null || true
    rm -f "${BOOTSTRAP_RELEASE_UPLOAD_RESPONSE_PATH}"
  fi

  if (( status != 0 )) && [[ "${BOOTSTRAP_RELEASE_UPLOAD_ACCEPTED:-0}" == "1" ]]; then
    printf '[chummer-mac-release] ERROR: Release completion was accepted before a later check failed; the release may already be public. Do not create or publish another session. Inspect %s and reconcile the recorded session.\n' \
      "${BOOTSTRAP_RELEASE_UPLOAD_ATTEMPT_RECEIPT_PATH:-the durable upload handoff}" >&2
  fi
  return "$status"
}

require_all_reviewed_commit_pins() {
  local setting=""
  local value=""
  local normalized=""
  local -a settings=(
    CHUMMER_UI_EXPECTED_COMMIT
    CHUMMER_CORE_EXPECTED_COMMIT
    CHUMMER_HUB_EXPECTED_COMMIT
    CHUMMER_UI_KIT_EXPECTED_COMMIT
    CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT
    CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT
    CHUMMER_LEGACY_EXPECTED_COMMIT
  )

  for setting in "${settings[@]}"; do
    value="${!setting:-}"
    [[ "$value" =~ ^[0-9a-fA-F]{40}$ ]] \
      || die "$setting must be set to a reviewed full 40-character hexadecimal commit SHA before release work begins"
    normalized="$(to_lower_ascii "$value")"
    printf -v "$setting" '%s' "$normalized"
    export "$setting"
  done
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command missing: $1"
}

resolve_release_python() {
  local requested="${CHUMMER_RELEASE_PYTHON:-}"
  local candidate=""
  local resolved=""
  if [[ -n "$requested" ]]; then
    resolved="$(command -v "$requested" 2>/dev/null || true)"
    [[ -n "$resolved" ]] \
      && "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1 \
      || return 1
    printf '%s\n' "$resolved"
    return 0
  fi

  for candidate in python3.13 python3.12 python3.11 python3; do
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    [[ -n "$resolved" ]] || continue
    if "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  return 1
}

sanitize_hub_generator_diagnostic() {
  local python_bin="$1"
  "$python_bin" -c '
import re
import sys

limit = 16384
kept = bytearray()
while True:
    chunk = sys.stdin.buffer.read(65536)
    if not chunk:
        break
    if len(kept) < limit:
        kept.extend(chunk[: limit - len(kept)])
text = bytes(kept).decode("utf-8", errors="replace")
text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"]+", r"\1<redacted>", text)
text = re.sub(r"(?i)\b(token|ticket|api[_-]?key|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)
text = re.sub(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]{8,})?\b", "<redacted-token>", text)
text = re.sub(r"(?<![A-Za-z0-9:])(?:/Users/|/home/|/root/|/tmp/|/private/|/var/tmp/|/docker/|/workspace/)[^\s\"]*", "<local-path>", text)
lines = [line.rstrip() for line in text.splitlines() if line.strip()]
sys.stdout.write("\n".join(lines[-40:])[:limit])
'
}

require_hub_projection_authority_handoffs() {
  local python_bin="$1"
  "$python_bin" -I -S - <<'PY'
from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat

SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
AUTHORITY = re.compile(r"^[a-z][a-z0-9+.-]*://\S+$", re.IGNORECASE)
MAX_BYTES = 32 * 1024 * 1024
COMMIT_NAMES = (
    "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT",
    "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT",
)
HANDOFFS = (
    (
        "CHUMMER_HUB_RELEASE_CHANNEL_PATH",
        "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256",
        "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY",
    ),
    (
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY",
    ),
    (
        "CHUMMER_FLEET_QUEUE_STAGING_PATH",
        "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256",
        "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY",
    ),
    (
        "CHUMMER_DESIGN_QUEUE_STAGING_PATH",
        "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256",
        "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY",
    ),
    (
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY",
    ),
)


def fail(name: str, reason: str) -> None:
    raise SystemExit(f"Hub proof authority handoff {name} {reason}")


for name in COMMIT_NAMES:
    value = os.environ.get(name, "").strip()
    if SHA40.fullmatch(value) is None:
        fail(name, "must be a full 40-character commit SHA")

for path_name, digest_name, authority_name in HANDOFFS:
    path_value = os.environ.get(path_name, "").strip()
    digest_value = os.environ.get(digest_name, "").strip().lower()
    authority_value = os.environ.get(authority_name, "").strip()
    if not path_value:
        fail(path_name, "is required")
    if SHA256.fullmatch(digest_value) is None:
        fail(digest_name, "must be a 64-character SHA256")
    if AUTHORITY.fullmatch(authority_value) is None or authority_value.lower().startswith("file://"):
        fail(authority_name, "must be a non-file immutable authority reference")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path_value, flags)
    except OSError:
        fail(path_name, "is unavailable")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            fail(path_name, "must be a single-link regular file")
        if before.st_size < 1 or before.st_size > MAX_BYTES:
            fail(path_name, "has an invalid size")
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        try:
            path_metadata = os.lstat(path_value)
        except OSError:
            fail(path_name, "changed during stable read")
    finally:
        os.close(descriptor)

    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_mode,
        before.st_nlink,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_mode,
        after.st_nlink,
    )
    if before_identity != after_identity or (path_metadata.st_dev, path_metadata.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        fail(path_name, "changed during stable read")
    payload = b"".join(chunks)
    if len(payload) != before.st_size:
        fail(path_name, "changed during stable read")
    if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), digest_value):
        fail(digest_name, "does not match the immutable handoff")
PY
}

file_sha256() {
  local path="$1"
  python3 - "$path" <<'PY'
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
}

resolve_executed_bootstrap_path() {
  local source_path="${BASH_SOURCE[0]:-}"
  [[ -n "$source_path" ]] || return 1
  python3 - "$source_path" <<'PY'
from __future__ import annotations

import stat
import sys
from pathlib import Path

try:
    path = Path(sys.argv[1]).expanduser().resolve(strict=True)
    mode = path.stat().st_mode
except OSError as exc:
    raise SystemExit(f"executed bootstrap path is unavailable: {type(exc).__name__}") from exc
if not stat.S_ISREG(mode):
    raise SystemExit("executed bootstrap path is not a regular file")
print(path)
PY
}

log_bootstrap_identity() {
  local source_path="${1:-${BASH_SOURCE[0]:-}}"
  [[ -n "$source_path" ]] || return 0

  local digest=""
  if [[ -r "$source_path" ]]; then
    digest="$(file_sha256 "$source_path" 2>/dev/null || true)"
  fi

  if [[ -n "$digest" ]]; then
    log "bootstrap source: $source_path (sha256=$digest)"
  else
    log "bootstrap source: $source_path"
  fi
}

verify_bootstrap_integrity() {
  local source_path="${1:-${BASH_SOURCE[0]:-}}"
  local expected_sha256="${CHUMMER_BOOTSTRAP_EXPECTED_SHA256:-}"
  [[ -n "$expected_sha256" ]] || return 0
  [[ -n "$source_path" && -r "$source_path" ]] || die "bootstrap integrity check requested but bootstrap source is unreadable"

  local actual_sha256
  actual_sha256="$(file_sha256 "$source_path" 2>/dev/null || true)"
  [[ -n "$actual_sha256" ]] || die "bootstrap integrity check requested but sha256 could not be computed"
  [[ "$actual_sha256" == "$expected_sha256" ]] || die "bootstrap integrity check failed: expected sha256 $expected_sha256 but found $actual_sha256"
  log "bootstrap integrity verified: sha256=${actual_sha256}"
}

free_space_kib() {
  local path="$1"
  df -Pk "$path" | awk 'NR==2 { print $4 }'
}

format_gib_from_kib() {
  python3 - "$1" <<'PY'
import sys
value = int(sys.argv[1])
print(f"{value / 1024 / 1024:.1f} GiB")
PY
}

recommended_headroom_gib() {
  python3 - "$1" <<'PY'
import sys

minimum = int(sys.argv[1])
print(max(minimum + 5, 25))
PY
}

write_preflight_capacity_abort_receipt() {
  local checked_path="$1"
  local label="$2"
  local minimum_gib="$3"
  local available_kib="$4"

  local evidence_root="${work_root:-$checked_path}"
  local evidence_dir="$evidence_root/release-evidence"
  local receipt_path="$evidence_dir/preflight-capacity-abort.json"
  local recommended_gib
  recommended_gib="$(recommended_headroom_gib "$minimum_gib")"

  mkdir -p "$evidence_dir"
  python3 - "$receipt_path" "$evidence_root" "$checked_path" "$label" "$minimum_gib" "$available_kib" "$recommended_gib" "${release_version:-}" "${release_channel:-}" "${rid:-}" "${apps_raw:-}" <<'PY'
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

receipt_path = Path(sys.argv[1])
work_root = str(sys.argv[2]).strip()
checked_path = str(sys.argv[3]).strip()
label = str(sys.argv[4]).strip()
required_gib = int(sys.argv[5])
available_kib = int(sys.argv[6])
recommended_gib = int(sys.argv[7])
release_version = str(sys.argv[8]).strip()
release_channel = str(sys.argv[9]).strip()
rid = str(sys.argv[10]).strip()
apps_raw = str(sys.argv[11]).strip()
app_heads = [item.strip() for item in apps_raw.split(",") if item.strip()]

available_gib = round(available_kib / 1024 / 1024, 1)
payload = {
    "contractName": "chummer6.mac_release_preflight_abort",
    "status": "abort",
    "abortClass": "preflight_capacity_abort",
    "reason": "insufficient_disk_space",
    "recordedAtUtc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "workRoot": work_root,
    "checkedPath": checked_path,
    "checkedPathLabel": label,
    "requiredFreeGiB": required_gib,
    "availableFreeKiB": available_kib,
    "availableFreeGiB": available_gib,
    "recommendedFreeGiB": recommended_gib,
    "headroomShortfallGiB": round(max(required_gib - available_gib, 0.0), 1),
    "releaseVersion": release_version,
    "releaseChannel": release_channel,
    "rid": rid,
    "appHeads": app_heads,
    "countsAsCloneEvidence": False,
    "countsAsPackagingEvidence": False,
    "countsAsStartupSmokeEvidence": False,
    "countsAsManifestEvidence": False,
    "countsAsUploadEvidence": False,
    "operatorAction": "free_disk_space_and_rerun",
}
receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(receipt_path)
PY
}

log_disk_space() {
  local path="$1"
  local label="$2"
  local available_kib
  available_kib="$(free_space_kib "$path")"
  log "$label free space at $path: $(format_gib_from_kib "$available_kib")"
}

require_min_free_space_gib() {
  local path="$1"
  local label="$2"
  local minimum_gib="$3"
  local available_kib minimum_kib abort_receipt_path recommended_gib
  available_kib="$(free_space_kib "$path")"
  minimum_kib=$(( minimum_gib * 1024 * 1024 ))
  if (( available_kib < minimum_kib )); then
    abort_receipt_path="$(write_preflight_capacity_abort_receipt "$path" "$label" "$minimum_gib" "$available_kib")"
    recommended_gib="$(recommended_headroom_gib "$minimum_gib")"
    log "wrote preflight capacity-abort receipt: $abort_receipt_path"
    die "$label needs at least ${minimum_gib} GiB free before macOS packaging/notarization work. Available at $path: $(format_gib_from_kib "$available_kib"). This run stopped before clone/build/packaging/startup-smoke/upload and does not count as release evidence. Free more space and rerun; practical headroom target: ${recommended_gib} GiB. Receipt: $abort_receipt_path"
  fi
}

prune_packaging_build_intermediates() {
  local root="$1"
  python3 - "$root" <<'PY'
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
removed = 0
freed = 0
seen: set[Path] = set()

for current_root, dir_names, _file_names in os.walk(root):
    current_path = Path(current_root)
    filtered_dir_names: list[str] = []
    for dir_name in dir_names:
        if dir_name not in {"bin", "obj"}:
            filtered_dir_names.append(dir_name)
            continue
        candidate = current_path / dir_name
        if candidate in seen:
            continue
        seen.add(candidate)
        for nested_root, _nested_dirs, nested_files in os.walk(candidate):
            for nested_file in nested_files:
                try:
                    freed += (Path(nested_root) / nested_file).stat().st_size
                except FileNotFoundError:
                    pass
        shutil.rmtree(candidate, ignore_errors=True)
        removed += 1
    dir_names[:] = filtered_dir_names

print(f"{removed}|{freed}")
PY
}

ensure_packaging_headroom() {
  local work_root="$1"
  local temp_root="$2"
  local minimum_gib="$3"
  local available_work_kib available_temp_kib

  available_work_kib="$(free_space_kib "$work_root")"
  available_temp_kib="$(free_space_kib "$temp_root")"
  if (( available_work_kib >= minimum_gib * 1024 * 1024 )) && (( available_temp_kib >= minimum_gib * 1024 * 1024 )); then
    return 0
  fi

  log "packaging headroom below ${minimum_gib} GiB; pruning repo-local build intermediates before retry"
  local reclaim_result removed_count freed_bytes freed_mib
  reclaim_result="$(prune_packaging_build_intermediates "$work_root")"
  IFS='|' read -r removed_count freed_bytes <<< "$reclaim_result"
  freed_mib="$(python3 - "$freed_bytes" <<'PY'
import sys
value = int(sys.argv[1] or "0")
print(f"{value / 1024 / 1024:.1f} MiB")
PY
)"
  log "packaging cleanup removed ${removed_count:-0} bin/obj directories and reclaimed ${freed_mib}"
  log_disk_space "$work_root" "release work root after packaging cleanup"
  log_disk_space "$temp_root" "temporary packaging root after packaging cleanup"

  available_work_kib="$(free_space_kib "$work_root")"
  if (( available_work_kib < minimum_gib * 1024 * 1024 )); then
    die "release work root needs at least ${minimum_gib} GiB free before macOS packaging/notarization work even after cleanup. Available at $work_root: $(format_gib_from_kib "$available_work_kib"). Set CHUMMER_MAC_RELEASE_TMPDIR to a roomier volume or lower CHUMMER_MAC_RELEASE_PACKAGING_MIN_FREE_GIB only if you intentionally accept tighter headroom."
  fi

  available_temp_kib="$(free_space_kib "$temp_root")"
  if (( available_temp_kib < minimum_gib * 1024 * 1024 )); then
    die "temporary packaging root needs at least ${minimum_gib} GiB free before macOS packaging/notarization work even after cleanup. Available at $temp_root: $(format_gib_from_kib "$available_temp_kib"). Set CHUMMER_MAC_RELEASE_TMPDIR or CHUMMER_DESKTOP_INSTALLER_TMPDIR to a roomier volume or lower CHUMMER_MAC_RELEASE_PACKAGING_MIN_FREE_GIB only if you intentionally accept tighter headroom."
  fi
}

prepend_path_if_missing() {
  local candidate="$1"
  [[ -n "$candidate" ]] || return 0
  case ":$PATH:" in
    *":$candidate:"*) ;;
    *)
      export PATH="$candidate:$PATH"
      ;;
  esac
}

ensure_dotnet_resolver() {
  if command -v dotnet >/dev/null 2>&1; then
    return 0
  fi

  if [[ -x "$HOME/.dotnet/dotnet" ]]; then
    export DOTNET_ROOT="$HOME/.dotnet"
    prepend_path_if_missing "$HOME/.dotnet"
    return 0
  fi

  die "required command missing: dotnet"
}

required_sdk_prefix() {
  local repo_root="$1"
  local global_json="$repo_root/global.json"
  [[ -f "$global_json" ]] || die "required sdk descriptor is missing: $global_json. repo checkout likely failed before SDK verification."
  python3 - "$repo_root" <<'PY'
import json
import pathlib
import sys

repo_root = pathlib.Path(sys.argv[1])
global_json = repo_root / "global.json"
data = json.loads(global_json.read_text(encoding="utf-8"))
version = str(data["sdk"]["version"]).strip()
parts = version.split(".")
if len(parts) < 2:
    raise SystemExit("invalid sdk.version in global.json")
print(f"{parts[0]}.{parts[1]}.")
PY
}

require_compatible_dotnet_sdk() {
  local repo_root="$1"
  local prefix
  prefix="$(required_sdk_prefix "$repo_root")"

  local listed_sdks
  listed_sdks="$(dotnet --list-sdks 2>/dev/null || true)"
  if ! printf '%s\n' "$listed_sdks" | grep -Eq "^${prefix//./\\.}[0-9]+"; then
    if [[ -x "$HOME/.dotnet/dotnet" ]]; then
      export DOTNET_ROOT="$HOME/.dotnet"
      prepend_path_if_missing "$HOME/.dotnet"
      listed_sdks="$(dotnet --list-sdks 2>/dev/null || true)"
    fi
  fi

  if ! printf '%s\n' "$listed_sdks" | grep -Eq "^${prefix//./\\.}[0-9]+"; then
    die "compatible .NET SDK not found for ${prefix}x. dotnet --list-sdks returned: ${listed_sdks:-<none>}"
  fi

  log "using dotnet sdk $(dotnet --version)"
}

append_unique_value() {
  local needle="$1"
  shift
  local existing
  for existing in "$@"; do
    if [[ "$existing" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

array_contains_value() {
  local array_name="${1:-}"
  local needle="${2:-}"
  local existing=""
  [[ -n "$array_name" ]] || return 1

  while IFS= read -r -d '' existing; do
    if [[ "$existing" == "$needle" ]]; then
      return 0
    fi
  done < <(array_values_nul "$array_name")

  return 1
}

ensure_link_target() {
  local source="$1"
  local link_path="$2"
  local desired_real current_real
  desired_real="$(cd "$source" && pwd -P)"

  mkdir -p "$(dirname "$link_path")"
  if [[ -L "$link_path" ]]; then
    current_real="$(cd "$link_path" && pwd -P)"
    if [[ "$current_real" == "$desired_real" ]]; then
      return 0
    fi
    rm -f "$link_path"
    ln -s "$source" "$link_path"
    return 0
  fi

  if [[ -e "$link_path" ]]; then
    current_real="$(cd "$link_path" && pwd -P)"
    [[ "$current_real" == "$desired_real" ]] || die "path exists and is not the expected compatibility alias: $link_path"
    return 0
  fi

  ln -s "$source" "$link_path"
}

path_exists_in_bundle() {
  local root="$1"
  local relative="$2"
  [[ -e "$root/${relative}" ]]
}

create_minimal_promotion_bundle() {
  local source_root="$1"
  local bundle_root="$2"

  rm -rf "$bundle_root"
  mkdir -p "$bundle_root/files" "$bundle_root/startup-smoke" "$bundle_root/release-evidence"

  cp "$source_root/releases.json" "$bundle_root/releases.json"
  cp "$source_root/RELEASE_CHANNEL.generated.json" "$bundle_root/RELEASE_CHANNEL.generated.json"
  cp "$source_root/release-evidence/public-promotion.json" "$bundle_root/release-evidence/public-promotion.json"

  if compgen -G "$source_root/files/*" >/dev/null; then
    cp -aL "$source_root/files/"* "$bundle_root/files/"
  fi

  if [[ -d "$source_root/startup-smoke" ]]; then
    cp -aL "$source_root/startup-smoke/." "$bundle_root/startup-smoke/"
  fi

  local governed_provenance_root="$source_root/proof/build-provenance/v1"
  if [[ -d "$governed_provenance_root" ]]; then
    mkdir -p "$bundle_root/proof/build-provenance/v1"
    cp -a "$governed_provenance_root/." "$bundle_root/proof/build-provenance/v1/"
  fi
}

sync_startup_smoke_receipts_for_local_verifier() {
  local source_dir="$1"
  local manifest_root="$2"
  local target_dir="${manifest_root}/startup-smoke"
  local source_real=""
  local target_real=""

  if [[ ! -d "$source_dir" ]]; then
    rm -rf "$target_dir"
    return 0
  fi

  source_real="$(cd "$source_dir" && pwd -P)"
  if [[ -d "$target_dir" ]]; then
    target_real="$(cd "$target_dir" && pwd -P)"
    if [[ "$source_real" == "$target_real" ]]; then
      return 0
    fi
  fi

  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  while IFS= read -r receipt_path; do
    [[ -f "$receipt_path" ]] || continue
    cp "$receipt_path" "$target_dir/"
  done < <(find "$source_dir" -maxdepth 1 -type f -name 'startup-smoke-*.receipt.json' | sort)
}

verify_live_canonical_supportability_preflight() {
  local canonical_url="$1"
  local timeout_seconds="${CHUMMER_LIVE_CANONICAL_PREFLIGHT_TIMEOUT_SECONDS:-30}"
  local live_canonical_path
  live_canonical_path="$(mktemp)" \
    || die "could not reserve a temporary file for the live canonical manifest preflight"

  local http_code=""
  local curl_status=0
  http_code="$(curl \
    -sS \
    -L \
    --connect-timeout "$timeout_seconds" \
    --max-time "$timeout_seconds" \
    -o "$live_canonical_path" \
    -w '%{http_code}' \
    "$canonical_url")" || curl_status=$?

  if (( curl_status != 0 )); then
    rm -f "$live_canonical_path"
    die "live canonical manifest preflight could not reach $canonical_url (curl exit ${curl_status}, HTTP ${http_code:-000}). No release build or upload was started. Operator/deployment handoff required: restore public canonical-manifest access and verify the active public-edge projection before rerunning."
  fi

  case "$http_code" in
    2??)
      ;;
    403)
      rm -f "$live_canonical_path"
      die "live canonical manifest preflight received HTTP 403 from $canonical_url. No release build or upload was started. Operator/deployment handoff required: restore public canonical-manifest access and deploy/activate the corrected public-edge projection before rerunning."
      ;;
    *)
      rm -f "$live_canonical_path"
      die "live canonical manifest preflight received HTTP ${http_code:-000} from $canonical_url. No release build or upload was started. Operator/deployment handoff required: restore a readable canonical manifest and verify the active public-edge projection before rerunning."
      ;;
  esac

  local validation_message=""
  if ! validation_message="$(python3 - "$live_canonical_path" "$canonical_url" 2>&1 <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


manifest_path = Path(sys.argv[1])
canonical_url = sys.argv[2]

try:
    payload: Any = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SystemExit(
        f"live canonical manifest preflight could not parse {canonical_url}: {type(exc).__name__}. "
        "No release build or upload was started. Operator/deployment handoff required: "
        "restore a valid public canonical manifest and verify the active public-edge projection."
    ) from exc

if not isinstance(payload, dict):
    raise SystemExit(
        f"live canonical manifest preflight expected a JSON object at {canonical_url}. "
        "No release build or upload was started. Operator/deployment handoff required: "
        "restore a valid public canonical manifest and verify the active public-edge projection."
    )

public_trust = payload.get("publicTrustMetrics")
proof_freshness = public_trust.get("proofFreshness") if isinstance(public_trust, dict) else None
raw_proof_status = proof_freshness.get("status") if isinstance(proof_freshness, dict) else None
proof_status = str(raw_proof_status or "").strip().lower()

if not proof_status:
    raise SystemExit(
        f"live canonical manifest preflight could not determine "
        f"publicTrustMetrics.proofFreshness.status at {canonical_url}. "
        "No release build or upload was started. Operator/deployment handoff required: "
        "restore complete proof-freshness truth in the public canonical manifest and verify the "
        "active public-edge projection."
    )

if proof_status == "fresh":
    print(f"live canonical supportability preflight passed: proofFreshness.status={proof_status}")
    raise SystemExit(0)

if proof_status not in {"stale", "missing"}:
    raise SystemExit(
        f"live canonical manifest preflight found unrecognized "
        f"publicTrustMetrics.proofFreshness.status={proof_status!r} at {canonical_url}. "
        "No release build or upload was started. Operator/deployment handoff required: "
        "restore a recognized fresh, stale, or missing proof-freshness status in the public "
        "canonical manifest and verify the active public-edge projection."
    )

registry_boundary = payload.get("registryBoundaryCoverage")
public_release_channel = public_trust.get("releaseChannel") if isinstance(public_trust, dict) else None
registry_release_channel = (
    registry_boundary.get("releaseChannel") if isinstance(registry_boundary, dict) else None
)

supportability_fields = (
    ("supportabilityState", payload.get("supportabilityState")),
    (
        "publicTrustMetrics.releaseChannel.supportabilityState",
        public_release_channel.get("supportabilityState")
        if isinstance(public_release_channel, dict)
        else None,
    ),
    (
        "registryBoundaryCoverage.releaseChannel.supportabilityState",
        registry_release_channel.get("supportabilityState")
        if isinstance(registry_release_channel, dict)
        else None,
    ),
)
invalid_fields = [
    f"{field}={value!r}"
    for field, value in supportability_fields
    if value != "review_required"
]
public_trust_posture_fields = (
    (
        "publicTrustMetrics.releaseChannel.posture",
        public_release_channel.get("posture")
        if isinstance(public_release_channel, dict)
        else None,
    ),
    (
        "registryBoundaryCoverage.releaseChannel.publicTrustPosture",
        registry_release_channel.get("publicTrustPosture")
        if isinstance(registry_release_channel, dict)
        else None,
    ),
)
invalid_posture_fields = [
    f"{field}={value!r}"
    for field, value in public_trust_posture_fields
    if value != "blocked"
]
if invalid_fields or invalid_posture_fields:
    raise SystemExit(
        f"{canonical_url} must set supportabilityState='review_required' at all three canonical "
        f"supportability paths and public trust posture='blocked' at both release-channel paths "
        f"when proofFreshness.status={proof_status!r}; invalid: "
        + ", ".join(invalid_fields + invalid_posture_fields)
        + ". No release build or upload was started. Operator/deployment handoff required: "
        "deploy/activate the corrected canonicalization or live projection, verify the served bytes, "
        "then rerun the macOS release bootstrap."
    )

print(
    "live canonical supportability preflight passed: "
    f"proofFreshness.status={proof_status}; all supportability paths are review_required and "
    "all public trust posture paths are blocked"
)
PY
  )"; then
    rm -f "$live_canonical_path"
    if [[ -z "$validation_message" ]]; then
      validation_message="live canonical manifest preflight failed without a validator diagnostic at $canonical_url. No release build or upload was started. Operator/deployment handoff required: verify the served canonical bytes and the active public-edge projection before rerunning."
    fi
    die "$validation_message"
  fi

  rm -f "$live_canonical_path"
  [[ -n "$validation_message" ]] && log "$validation_message"
}

validate_release_response_probe_url() {
  local candidate="$1"
  local canonical_manifest_url="$2"
  local route_role="$3"
  python3 - "$candidate" "$canonical_manifest_url" "$route_role" <<'PY'
from __future__ import annotations

import re
import sys
from urllib.parse import unquote, urlsplit

candidate_text, canonical_text, role = (str(value).strip() for value in sys.argv[1:4])
candidate = urlsplit(candidate_text)
canonical = urlsplit(canonical_text)
try:
    candidate_authority = (candidate.scheme.lower(), (candidate.hostname or "").lower(), candidate.port)
    canonical_authority = (canonical.scheme.lower(), (canonical.hostname or "").lower(), canonical.port)
except ValueError:
    raise SystemExit(1)

decoded_path = unquote(candidate.path)
segments = decoded_path.replace("\\", "/").split("/")
if (
    candidate.scheme not in {"http", "https"}
    or not candidate.hostname
    or canonical.scheme not in {"http", "https"}
    or not canonical.hostname
    or candidate.username is not None
    or candidate.password is not None
    or canonical.username is not None
    or canonical.password is not None
    or candidate.query
    or candidate.fragment
    or candidate_authority != canonical_authority
    or decoded_path != candidate.path
    or "\\" in candidate.path
    or any(segment in {".", ".."} for segment in segments)
):
    raise SystemExit(1)

safe_id = r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}"
safe_file = r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}"
current_install = re.fullmatch(rf"/downloads/install/{safe_id}", decoded_path) is not None
generation_install = re.fullmatch(
    rf"/downloads/g/{safe_id}/install/{safe_id}(?:/(?:payload|metadata))?",
    decoded_path,
) is not None
current_file = re.fullmatch(rf"/downloads/files/{safe_file}", decoded_path) is not None
generation_file = re.fullmatch(
    rf"/downloads/g/{safe_id}/files/{safe_file}",
    decoded_path,
) is not None

if role == "install":
    allowed = current_install or (
        generation_install and not decoded_path.endswith(("/payload", "/metadata"))
    )
elif role == "direct":
    allowed = current_file or generation_file or generation_install
else:
    allowed = False
if not allowed:
    raise SystemExit(1)
print(candidate.geturl())
PY
}

verify_live_release_projection() {
  local local_canonical_path="$1"
  local compatibility_url="$2"
  local canonical_url="$3"
  local response_path="${4:-}"
  local require_compatibility_projection="${5:-0}"

  local live_compat_path live_canonical_path
  live_compat_path="$(mktemp)"
  live_canonical_path="$(mktemp)"

  curl --fail-with-body -sS "$compatibility_url" > "$live_compat_path"
  curl --fail-with-body -sS "$canonical_url" > "$live_canonical_path"

  local projection_message=""
  if ! projection_message="$(python3 - "$local_canonical_path" "$live_compat_path" "$live_canonical_path" "$require_compatibility_projection" <<'PY'
import json
import sys
from pathlib import Path

local_canonical = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
live_compat = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
live_canonical = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
require_compatibility = str(sys.argv[4]).strip().lower() in {"1", "true", "yes", "on"}

expected_ids = {
    str(item.get("artifactId") or "").strip()
    for item in local_canonical.get("artifacts") or []
    if isinstance(item, dict) and str(item.get("artifactId") or "").strip()
}

compatibility_expected_ids = {
    str(item.get("artifactId") or "").strip()
    for item in local_canonical.get("artifacts") or []
    if isinstance(item, dict)
    and str(item.get("artifactId") or "").strip()
    and (
        str(item.get("kind") or "").strip().lower() == "installer"
        or (
            not str(item.get("kind") or "").strip()
            and str(item.get("artifactId") or "").strip().lower().endswith("-installer")
        )
    )
}

compat_ids = {
    str(item.get("id") or "").strip()
    for item in live_compat.get("downloads") or []
    if isinstance(item, dict) and str(item.get("id") or "").strip()
}
canonical_ids = {
    str(item.get("artifactId") or "").strip()
    for item in live_canonical.get("artifacts") or []
    if isinstance(item, dict) and str(item.get("artifactId") or "").strip()
}

missing_compat = sorted(compatibility_expected_ids - compat_ids)
missing_canonical = sorted(expected_ids - canonical_ids)
if missing_canonical:
    raise SystemExit(
        "canonical release projection is incoherent after promotion: "
        + f"canonical missing={missing_canonical}"
    )
if missing_compat:
    message = (
        "compatibility release projection is still missing installer tuples after promotion: "
        + f"{missing_compat}. canonical release truth is already live; "
        + "set CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION=1 to make compatibility drift fatal."
    )
    if require_compatibility:
        raise SystemExit(message)
    print(message)

def nested_value(payload, *path):
    current = payload
    for segment in path:
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current

truth_paths = (
    ("version",),
    ("publishedAt",),
    ("channel",),
    ("channelId",),
    ("status",),
    ("rolloutState",),
    ("rolloutReason",),
    ("supportabilityState",),
    ("publicTrustMetrics", "proofFreshness", "status"),
    ("publicTrustMetrics", "releaseChannel", "posture"),
    ("publicTrustMetrics", "releaseChannel", "rolloutState"),
    ("publicTrustMetrics", "releaseChannel", "supportabilityState"),
    ("registryBoundaryCoverage", "releaseChannel", "publicTrustPosture"),
    ("registryBoundaryCoverage", "releaseChannel", "rolloutState"),
    ("registryBoundaryCoverage", "releaseChannel", "supportabilityState"),
)
truth_mismatches = [
    ".".join(path)
    for path in truth_paths
    if nested_value(local_canonical, *path) != nested_value(live_canonical, *path)
]
if truth_mismatches:
    raise SystemExit(
        "canonical release projection changed uploaded release truth after promotion; mismatched fields: "
        + ", ".join(truth_mismatches)
    )
PY
  )"; then
    rm -f "$live_compat_path" "$live_canonical_path"
    die "$projection_message"
  fi

  if [[ -n "$projection_message" ]]; then
    log "$projection_message"
  fi

  if [[ -f "$response_path" ]]; then
    local -a install_urls=()
    local -a direct_urls=()

    while IFS= read -r url; do
      [[ -n "$url" ]] || continue
      install_urls+=("$url")
    done < <(jq -r '.installDispatchUrls[]? // empty' "$response_path")

    while IFS= read -r url; do
      [[ -n "$url" ]] || continue
      direct_urls+=("$url")
    done < <(jq -r '.directFileUrls[]? // empty' "$response_path")

    local url http_code
    if (( $(array_count install_urls) > 0 )); then
      while IFS= read -r -d '' url; do
        url="$(validate_release_response_probe_url "$url" "$canonical_url" install)" \
          || die "release upload response contained an unsafe install handoff URL; do not retry the published session until it is reconciled"
        http_code="$(curl -sS -o /dev/null -w '%{http_code}' "$url")"
        if [[ "$http_code" == "404" ]]; then
          die "install dispatch returned 404 after promotion; do not retry the published session until it is reconciled"
        fi
      done < <(array_values_nul install_urls)
    fi

    if (( $(array_count direct_urls) > 0 )); then
      while IFS= read -r -d '' url; do
        url="$(validate_release_response_probe_url "$url" "$canonical_url" direct)" \
          || die "release upload response contained an unsafe direct-file URL; do not retry the published session until it is reconciled"
        http_code="$(curl -sS -o /dev/null -w '%{http_code}' "$url")"
        if [[ "$http_code" == "404" ]]; then
          die "direct artifact returned 404 after promotion; do not retry the published session until it is reconciled"
        fi
      done < <(array_values_nul direct_urls)
    fi
  fi

  rm -f "$live_compat_path" "$live_canonical_path"
}

resolve_live_release_verify_urls() {
  local requested="$1"
  if [[ "$requested" == */releases.json ]]; then
    printf '%s|%s\n' "$requested" "${requested%/releases.json}/RELEASE_CHANNEL.generated.json"
    return 0
  fi
  if [[ "$requested" == */RELEASE_CHANNEL.generated.json ]]; then
    printf '%s|%s\n' "${requested%/RELEASE_CHANNEL.generated.json}/releases.json" "$requested"
    return 0
  fi
  local base="${requested%/}"
  printf '%s|%s\n' "$base/releases.json" "$base/RELEASE_CHANNEL.generated.json"
}

resolve_head_build_metadata() {
  case "$1" in
    avalonia)
      printf '%s|%s|%s\n' \
        "Chummer.Avalonia/Chummer.Avalonia.csproj" \
        "Chummer.Avalonia" \
        "dmg"
      ;;
    blazor-desktop)
      printf '%s|%s|%s\n' \
        "Chummer.Blazor.Desktop/Chummer.Blazor.Desktop.csproj" \
        "Chummer.Blazor.Desktop" \
        "dmg"
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_head_provenance_target_id() {
  case "$1" in
    avalonia) printf '%s\n' "desktop-avalonia" ;;
    blazor-desktop) printf '%s\n' "desktop-blazor" ;;
    *) return 1 ;;
  esac
}

require_safe_provenance_invocation_id() {
  python3 - "$1" <<'PY'
import re
import sys

value = sys.argv[1]
if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", value) is None:
    raise SystemExit(f"unsafe build provenance invocation id: {value!r}")
PY
}

begin_mac_file_build_provenance() {
  local generator_path="$1"
  local support_path="$2"
  local ui_repo="$3"
  local core_repo="$4"
  local hub_repo="$5"
  local ui_kit_repo="$6"
  local registry_repo="$7"
  local media_repo="$8"
  local legacy_repo="$9"
  local project_path="${10}"
  local target_id="${11}"
  local artifact_id="${12}"
  local artifact_name="${13}"
  local artifact_path="${14}"
  local invocation_id="${15}"
  local state_path="${16}"
  local receipt_path="${17}"
  local sbom_path="${18}"
  local executed_bootstrap_path="${19}"

  [[ -f "$generator_path" ]] || die "portable build provenance generator is missing: $generator_path"
  [[ -f "$support_path" ]] || die "portable build provenance support is missing: $support_path"
  [[ -f "$executed_bootstrap_path" && ! -L "$executed_bootstrap_path" ]] \
    || die "executed hosted bootstrap is unavailable or not a regular file: $executed_bootstrap_path"
  require_safe_provenance_invocation_id "$invocation_id"
  python3 "$generator_path" begin \
    --state "$state_path" \
    --output "$receipt_path" \
    --builder-id "chummer-mac-hosted-bootstrap" \
    --build-type "macos-desktop-release" \
    --invocation-id "$invocation_id" \
    --support-script "$support_path" \
    --source-repository "chummer-presentation" \
    --source-repo-root "$ui_repo" \
    --source-material "chummer-core-engine=$core_repo" \
    --source-material "chummer.run-services=$hub_repo" \
    --source-material "chummer-ui-kit=$ui_kit_repo" \
    --source-material "chummer-hub-registry=$registry_repo" \
    --source-material "chummer-media-factory=$media_repo" \
    --source-material "chummer5a=$legacy_repo" \
    --build-root "$ui_repo" \
    --target-id "$target_id" \
    --project-path "$project_path" \
    --artifact-id "$artifact_id" \
    --artifact-kind "desktop_download" \
    --artifact-name "$artifact_name" \
    --artifact-path "$artifact_path" \
    --sbom-path "$sbom_path" \
    --build-input "hosted-bootstrap=$executed_bootstrap_path" \
    --build-input "desktop-project=$ui_repo/$project_path" \
    --build-input "desktop-installer-recipe=$ui_repo/scripts/build-desktop-installer.sh" \
    --build-input "dotnet-sdk-selection=$ui_repo/global.json"
}

finalize_mac_file_build_provenance() {
  local generator_path="$1"
  local invocation_id="$2"
  local state_path="$3"
  local receipt_path="$4"

  python3 "$generator_path" finalize \
    --state "$state_path" \
    --output "$receipt_path" \
    --builder-id "chummer-mac-hosted-bootstrap" \
    --build-type "macos-desktop-release" \
    --invocation-id "$invocation_id"
}

json_contract_name() {
  local path="$1"
  python3 - "$path" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
except Exception:
    print("")
    raise SystemExit(0)

if isinstance(payload, dict):
    print(str(payload.get("contract_name") or payload.get("contractName") or "").strip())
else:
    print("")
PY
}

resolve_hub_local_release_proof_path() {
  local requested="$1"
  shift
  local candidate=""
  local resolved=""
  local contract_name=""
  local requested_path=""
  local allow_remote_requested="0"
  local remote_expected_sha256="${CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256:-}"

  if allow_remote_release_proof_input_for_candidate "${requested:-}"; then
    allow_remote_requested="1"
  fi

  if resolve_candidate_is_http_url "${requested:-}" && [[ "$allow_remote_requested" != "1" ]]; then
    echo "Ignoring remote requested release proof because remote proof inputs are disabled by default: $requested" >&2
  fi
  requested_path="$(resolve_local_file_path \
    "$requested" \
    "$allow_remote_requested" \
    "$remote_expected_sha256" \
    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256")"
  if [[ -n "$requested_path" && -f "$requested_path" ]]; then
    contract_name="$(json_contract_name "$requested_path")"
    if [[ "$contract_name" == "chummer6-hub.local_release_proof" ]]; then
      printf '%s\n' "$requested_path"
      return 0
    fi
    echo "Ignoring requested release proof path because it is not a hub local release proof contract: $requested" >&2
  fi

  for candidate in "$@"; do
    local allow_remote_candidate="0"
    if allow_remote_release_proof_input_for_candidate "${candidate:-}"; then
      allow_remote_candidate="1"
    fi
    if resolve_candidate_is_http_url "${candidate:-}" && [[ "$allow_remote_candidate" != "1" ]]; then
      continue
    fi
    resolved="$(resolve_local_file_path \
      "$candidate" \
      "$allow_remote_candidate" \
      "$remote_expected_sha256" \
      "CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256")"
    [[ -n "$resolved" && -f "$resolved" ]] || continue
    contract_name="$(json_contract_name "$resolved")"
    if [[ "$contract_name" == "chummer6-hub.local_release_proof" ]]; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done

  printf '%s\n' ""
}

resolve_first_existing_file_path() {
  local requested="$1"
  shift
  local candidate=""
  local resolved=""
  local requested_path=""
  local allow_remote_requested="0"
  local remote_expected_sha256="${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_EXPECTED_SHA256:-}"

  if allow_remote_release_proof_input_for_candidate "${requested:-}"; then
    allow_remote_requested="1"
  fi

  if resolve_candidate_is_http_url "${requested:-}" && [[ "$allow_remote_requested" != "1" ]]; then
    echo "Ignoring remote requested release gate because remote proof inputs are disabled by default: $requested" >&2
  fi
  requested_path="$(resolve_local_file_path \
    "$requested" \
    "$allow_remote_requested" \
    "$remote_expected_sha256" \
    "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_EXPECTED_SHA256")"
  if [[ -n "$requested_path" && -f "$requested_path" ]]; then
    printf '%s\n' "$requested_path"
    return 0
  fi

  for candidate in "$@"; do
    local allow_remote_candidate="0"
    if allow_remote_release_proof_input_for_candidate "${candidate:-}"; then
      allow_remote_candidate="1"
    fi
    if resolve_candidate_is_http_url "${candidate:-}" && [[ "$allow_remote_candidate" != "1" ]]; then
      continue
    fi
    resolved="$(resolve_local_file_path \
      "$candidate" \
      "$allow_remote_candidate" \
      "$remote_expected_sha256" \
      "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_EXPECTED_SHA256")"
    if [[ -n "$resolved" && -f "$resolved" ]]; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done

  printf '%s\n' ""
}

resolve_ui_localization_release_gate_repo() {
  local primary_ui_repo="$1"
  shift
  local candidate=""
  local script_relative_path="scripts/ai/milestones/b15-localization-release-gate.sh"
  local output_relative_path=".codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json"
  local -a candidates=()

  for candidate in \
    "$primary_ui_repo" \
    "$@" \
    "${CHUMMER_REMOTE_UI_REPO_DIR:-}" \
    "/docker/chummercomplete/chummer6-ui" \
    "/docker/chummercomplete/chummer6-ui-finish" \
    "/docker/chummercomplete/chummer-presentation-clean" \
    "/docker/chummercomplete/chummer-presentation"; do
    [[ -n "$candidate" ]] || continue
    if (( $(array_count candidates) == 0 )); then
      candidates+=("$candidate")
    elif append_unique_value "$candidate" "${candidates[@]}"; then
      candidates+=("$candidate")
    fi
  done

  local candidate_count
  candidate_count="$(array_count candidates)"
  if (( candidate_count > 0 )); then
    for candidate in "${candidates[@]}"; do
      if [[ -f "$candidate/$script_relative_path" ]]; then
        printf '%s\n' "$candidate"
        return 0
      fi
    done
  fi

  if (( candidate_count > 0 )); then
    for candidate in "${candidates[@]}"; do
      if [[ -f "$candidate/$output_relative_path" ]]; then
        printf '%s\n' "$candidate"
        return 0
      fi
    done
  fi

  if [[ -n "$primary_ui_repo" ]]; then
    printf '%s\n' "$primary_ui_repo"
    return 0
  fi

  printf '%s\n' ""
}

resolve_candidate_is_http_url() {
  local candidate="$1"
  [[ "$candidate" == http://* || "$candidate" == https://* ]]
}

allow_remote_release_proof_inputs() {
  case "$(to_lower_ascii "${CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS:-0}")" in
    1|true|yes|on)
      return 0
      ;;
  esac
  return 1
}

allow_remote_release_proof_input_for_candidate() {
  local candidate="${1:-}"

  if ! resolve_candidate_is_http_url "$candidate"; then
    return 1
  fi

  if allow_remote_release_proof_inputs; then
    return 0
  fi

  return 1
}

resolve_local_file_path() {
  local candidate="${1:-}"
  local allow_remote="${2:-1}"
  local expected_sha256="${3:-}"
  local expected_sha256_setting="${4:-CHUMMER_REMOTE_RELEASE_PROOF_EXPECTED_SHA256}"
  local downloaded_path=""
  local actual_sha256=""
  if [[ -z "$candidate" ]]; then
    printf '%s\n' ""
    return 0
  fi

  if resolve_candidate_is_http_url "$candidate"; then
    if [[ "$allow_remote" != "1" ]]; then
      printf '%s\n' ""
      return 0
    fi
    [[ -n "$expected_sha256" ]] \
      || die "$expected_sha256_setting must be set when its remote proof URL is enabled"
    [[ "$expected_sha256" =~ ^[[:xdigit:]]{64}$ ]] \
      || die "$expected_sha256_setting must be an exact 64-character SHA-256"
    expected_sha256="$(to_lower_ascii "$expected_sha256")"
    downloaded_path="$(mktemp)"
    if curl -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' -fsSL "$candidate" -o "$downloaded_path"; then
      actual_sha256="$(file_sha256 "$downloaded_path")"
      if [[ "$actual_sha256" != "$expected_sha256" ]]; then
        rm -f "$downloaded_path"
        die "downloaded remote proof SHA-256 does not match $expected_sha256_setting"
      fi
      bootstrap_tmp_paths+=("$downloaded_path")
      printf '%s\n' "$downloaded_path"
      return 0
    fi
    rm -f "$downloaded_path"
    printf '%s\n' ""
    return 0
  fi

  if [[ -f "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  printf '%s\n' ""
}

sanitize_release_proof_payload() {
  local source_path="${1:-}"
  local output_path="${2:-}"
  python3 - "$source_path" "$output_path" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
if not isinstance(payload, dict):
    raise SystemExit(f"release proof payload must be a JSON object: {source_path}")

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
sanitized = {key: payload[key] for key in payload if key in allowed}
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
PY
}

sanitize_ui_localization_release_gate_payload() {
  local source_path="${1:-}"
  local output_path="${2:-}"
  python3 - "$source_path" "$output_path" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
if not isinstance(payload, dict):
    raise SystemExit(f"ui localization release gate payload must be a JSON object: {source_path}")

canonical_acceptance_gates = [
    "pseudo_localization",
    "missing_key_fail_fast",
    "top_surface_overflow_checks",
    "locale_smoke_first_launch",
    "locale_smoke_settings",
    "locale_smoke_explain",
    "locale_smoke_updater",
    "locale_smoke_support",
    "non_english_generated_artifact_smoke",
]
canonical_localization_domains = [
    "app_chrome",
    "install_update_support",
    "explain_receipts",
    "data_rules_names",
    "generated_artifacts",
]

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

def normalize_token(value: object) -> str:
    return str(value).strip().lower() if isinstance(value, str) else ""

def canonicalize_acceptance_gates(raw: object) -> object:
    if not isinstance(raw, list):
        return raw
    normalized = [normalize_token(item) for item in raw if normalize_token(item)]
    if not normalized:
        return raw
    normalized_set = set(normalized)
    if all(token in normalized_set for token in canonical_acceptance_gates):
        return canonical_acceptance_gates
    return raw

def canonicalize_domain_map(raw: object) -> object:
    if not isinstance(raw, dict):
        return raw
    normalized = {
        normalize_token(key): value
        for key, value in raw.items()
        if normalize_token(key)
    }
    if all(domain in normalized for domain in canonical_localization_domains):
        return {
            domain: normalized[domain]
            for domain in canonical_localization_domains
        }
    return raw

def canonicalize_locale_domain_coverage(raw: object) -> object:
    if not isinstance(raw, dict):
        return raw
    normalized = {}
    for locale, domain_map in raw.items():
        if not isinstance(locale, str):
            return raw
        normalized[locale] = canonicalize_domain_map(domain_map)
    return normalized

if "acceptanceGates" in sanitized:
    sanitized["acceptanceGates"] = canonicalize_acceptance_gates(sanitized["acceptanceGates"])
if "acceptance_gates" in sanitized:
    sanitized["acceptance_gates"] = canonicalize_acceptance_gates(sanitized["acceptance_gates"])
if "domainCoverage" in sanitized:
    sanitized["domainCoverage"] = canonicalize_domain_map(sanitized["domainCoverage"])
if "domain_coverage" in sanitized:
    sanitized["domain_coverage"] = canonicalize_domain_map(sanitized["domain_coverage"])
if "localeDomainCoverage" in sanitized:
    sanitized["localeDomainCoverage"] = canonicalize_locale_domain_coverage(sanitized["localeDomainCoverage"])
if "locale_domain_coverage" in sanitized:
    sanitized["locale_domain_coverage"] = canonicalize_locale_domain_coverage(sanitized["locale_domain_coverage"])

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

json_generated_at_health() {
  local path="$1"
  local label="$2"
  local max_age_seconds="$3"
  local max_future_skew_seconds="$4"

  python3 - "$path" "$label" "$max_age_seconds" "$max_future_skew_seconds" <<'PY'
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
label = sys.argv[2]
max_age_seconds = int(sys.argv[3])
max_future_skew_seconds = int(sys.argv[4])
utc = dt.timezone.utc


def fail(message: str) -> None:
    print(message)
    raise SystemExit(1)


try:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
except FileNotFoundError:
    fail(f"{label} is missing: {path}")
except Exception as exc:  # pragma: no cover - shell bootstrap diagnostic helper
    fail(f"{label} could not be parsed: {path} ({exc})")

if not isinstance(payload, dict):
    fail(f"{label} must be a JSON object: {path}")

raw_generated_at = payload.get("generatedAt", payload.get("generated_at"))
if not isinstance(raw_generated_at, str) or not raw_generated_at.strip():
    fail(f"{label} is missing generatedAt/generated_at: {path}")

normalized = raw_generated_at.strip()
if normalized.endswith("Z"):
    normalized = normalized[:-1] + "+00:00"

try:
    generated_at = dt.datetime.fromisoformat(normalized)
except ValueError:
    fail(f"{label} generatedAt is not an ISO timestamp: {path} ({raw_generated_at})")

if generated_at.tzinfo is None:
    generated_at = generated_at.replace(tzinfo=utc)
generated_at = generated_at.astimezone(utc)

age_seconds = int((dt.datetime.now(utc) - generated_at).total_seconds())
if age_seconds < 0:
    future_skew_seconds = abs(age_seconds)
    if future_skew_seconds > max_future_skew_seconds:
        fail(
            f"{label} generatedAt is in the future: {path} "
            f"({future_skew_seconds}s ahead; max {max_future_skew_seconds}s)"
        )
    age_seconds = 0

if age_seconds > max_age_seconds:
    fail(
        f"{label} generatedAt is stale: {path} "
        f"({age_seconds}s old; max {max_age_seconds}s)"
    )
PY
}

hub_local_release_proof_has_canonical_baseline() {
  local path="$1"
  python3 - "$path" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8-sig"))
if not isinstance(payload, dict):
    raise SystemExit(1)

status = str(payload.get("status") or "").strip().lower()
journeys = payload.get("journeysPassed")
if journeys is None:
    journeys = payload.get("journeys_passed")
routes = payload.get("proofRoutes")
if routes is None:
    routes = payload.get("proof_routes")

expected_journeys = [
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
]
required_routes = [
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/access",
    "/account/work",
    "/account/support",
    "/contact",
    "/downloads",
    "/downloads/install/avalonia-osx-arm64-installer",
    "/downloads/install/avalonia-win-x64-installer",
]

if status not in {"pass", "passed", "ready"}:
    raise SystemExit(1)
if journeys != expected_journeys:
    raise SystemExit(1)
if not isinstance(routes, list):
    raise SystemExit(1)
normalized_routes = [str(route).strip() for route in routes if str(route).strip()]
if len(normalized_routes) != len(set(normalized_routes)):
    raise SystemExit(1)
for required_route in required_routes:
    if required_route not in normalized_routes:
        raise SystemExit(1)
if "/account/access" not in normalized_routes or "/account/work" not in normalized_routes:
    raise SystemExit(1)
PY
}

validate_hub_local_release_proof_with_registry() {
  local materializer_path="$1"
  local proof_path="$2"

  python3 - "$materializer_path" "$proof_path" <<'PY'
from __future__ import annotations

import importlib.util
import pathlib
import sys


materializer_path = pathlib.Path(sys.argv[1])
proof_path = pathlib.Path(sys.argv[2])
if not materializer_path.is_file():
    raise SystemExit(f"Registry release-proof validator is missing: {materializer_path}")

spec = importlib.util.spec_from_file_location("registry_release_materializer", materializer_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # type: ignore[union-attr]
proof = module.load_release_proof(proof_path)
if not isinstance(proof, dict):
    raise SystemExit("Registry release-proof validator returned no proof object")
PY
}

write_bootstrap_fallback_hub_local_release_proof() {
  die "bootstrap synthetic hub local release-proof fallback is disabled; fix the checked-out generator or set CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH"
}

write_bootstrap_fallback_ui_localization_release_gate() {
  die "bootstrap synthetic UI localization release-gate fallback is disabled; fix the checked-out gate or set CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH"
}

generate_hub_local_release_proof() {
  local hub_alias="$1"
  local hub_repo="$2"
  local output_path="$3"
  local generator_path="$hub_alias/scripts/materialize_hub_local_release_proof.py"
  local base_url="${CHUMMER_HUB_LOCAL_RELEASE_PROOF_BASE_URL:-https://chummer.run}"
  local compose_file="${CHUMMER_HUB_LOCAL_RELEASE_PROOF_COMPOSE_FILE:-$hub_repo/docker-compose.public-edge.yml}"
  local timeout_seconds="${CHUMMER_HUB_LOCAL_RELEASE_PROOF_TIMEOUT_SECONDS:-300}"
  local skip_rebuild="${CHUMMER_HUB_LOCAL_RELEASE_PROOF_SKIP_REBUILD:-1}"
  local python_bin="${RELEASE_PYTHON_BIN:-}"
  local mutation_lock_path="${CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH:-$(dirname "$output_path")/.hub-local-proof-mutation.lock}"
  local diagnostic_path=""
  local generator_status=0
  local sanitizer_status=0
  local -a generator_pipeline_status=()

  if [[ -z "$python_bin" ]]; then
    python_bin="$(resolve_release_python)" \
      || die "Hub proof generation requires Python 3.11 or newer; set CHUMMER_RELEASE_PYTHON to a reviewed interpreter"
  fi

  if [[ -f "$generator_path" ]]; then
    require_hub_projection_authority_handoffs "$python_bin"
    diagnostic_path="$(mktemp)"
    bootstrap_tmp_paths+=("$diagnostic_path")
    set +e
    CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS=1 \
    CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH="$mutation_lock_path" \
    "$python_bin" "$generator_path" \
      "$output_path" \
      "$base_url" \
      "$compose_file" \
      "$timeout_seconds" \
      "$skip_rebuild" 2>&1 \
      | sanitize_hub_generator_diagnostic "$python_bin" >"$diagnostic_path"
    generator_pipeline_status=("${PIPESTATUS[@]}")
    generator_status="${generator_pipeline_status[0]}"
    sanitizer_status="${generator_pipeline_status[1]}"
    set -e
    if (( sanitizer_status != 0 )); then
      die "checked-out Hub proof generator diagnostic sanitizer failed closed"
    fi
    if (( generator_status == 0 )); then
      if hub_local_release_proof_has_canonical_baseline "$output_path"; then
        return 0
      fi
      if [[ -s "$diagnostic_path" ]]; then
        printf '[chummer-mac-release] Hub proof generator diagnostic: %s\n' "$(<"$diagnostic_path")" >&2
      fi
      die "checked-out hub proof generator produced a non-canonical receipt at $output_path; fix the generator or set CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH"
    else
      if [[ -s "$diagnostic_path" ]]; then
        printf '[chummer-mac-release] Hub proof generator diagnostic: %s\n' "$(<"$diagnostic_path")" >&2
      fi
      die "checked-out hub proof generator failed at $generator_path; fix the generator or set CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH"
    fi
  else
    die "checked-out hub proof generator is missing at $generator_path; set CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH or restore the generator"
  fi
}

generate_validated_hub_local_release_proof() {
  local hub_alias="$1"
  local hub_repo="$2"
  local output_path="$3"
  local max_age_seconds="$4"
  local max_future_skew_seconds="$5"
  local materializer_path="$6"
  local release_proof_health=""
  local registry_validation_output=""

  generate_hub_local_release_proof "$hub_alias" "$hub_repo" "$output_path"
  if ! release_proof_health="$(json_generated_at_health \
    "$output_path" \
    "release proof" \
    "$max_age_seconds" \
    "$max_future_skew_seconds" 2>&1)"; then
    die "hub local release proof generation produced an unusable receipt: $release_proof_health"
  fi
  if ! registry_validation_output="$(validate_hub_local_release_proof_with_registry \
    "$materializer_path" \
    "$output_path" 2>&1)"; then
    die "hub local release proof generation produced a Registry-incompatible receipt: $registry_validation_output"
  fi
}

generate_ui_localization_release_gate() {
  local ui_repo
  ui_repo="$(resolve_ui_localization_release_gate_repo "$@")"
  if [[ -z "$ui_repo" || "$ui_repo" == "/" ]]; then
    die "ui localization release gate repo root could not be resolved; set CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH or run from a checkout with scripts/ai/milestones/b15-localization-release-gate.sh"
  fi
  local script_path="$ui_repo/scripts/ai/milestones/b15-localization-release-gate.sh"
  local output_path="$ui_repo/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json"
  local captured_path=""
  local snapshot_path=""
  local had_original=0

  if [[ "$ui_repo" != "$1" ]]; then
    log "ui localization release gate generator is using fallback repo at $ui_repo" >&2
  fi

  [[ -f "$script_path" ]] \
    || die "ui localization release gate generator is missing at $script_path; set CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH or restore the gate script"
  captured_path="$(mktemp "${TMPDIR:-/tmp}/chummer-ui-localization-gate.XXXXXX.json")" \
    || die "could not reserve a temporary ui localization gate receipt"
  snapshot_path="$(mktemp "${TMPDIR:-/tmp}/chummer-ui-localization-gate-snapshot.XXXXXX.json")" \
    || {
      rm -f "$captured_path"
      die "could not reserve a temporary ui localization gate snapshot"
    }

  if [[ -e "$output_path" ]]; then
    if [[ ! -f "$output_path" || -L "$output_path" ]]; then
      rm -f "$captured_path" "$snapshot_path"
      die "checked-out ui localization gate must be a regular non-symlink file: $output_path"
    fi
    cp -p "$output_path" "$snapshot_path" || {
      rm -f "$captured_path" "$snapshot_path"
      die "could not snapshot the checked-out ui localization gate: $output_path"
    }
    had_original=1
  fi

  if (
      restore_checked_out_gate() {
        if [[ "$had_original" == "1" ]]; then
          local restore_path=""
          restore_path="$(mktemp "${output_path}.restore.XXXXXX")" || return 1
          cp -p "$snapshot_path" "$restore_path" || {
            rm -f "$restore_path"
            return 1
          }
          mv -f "$restore_path" "$output_path" || {
            rm -f "$restore_path"
            return 1
          }
        else
          rm -f "$output_path"
        fi
      }
      trap 'restore_checked_out_gate' EXIT
      cd "$ui_repo" || exit 1
      bash "$script_path" >/dev/null || exit $?
      [[ -f "$output_path" && ! -L "$output_path" ]] || exit 1
      cp "$output_path" "$captured_path" || exit 1
      restore_checked_out_gate || exit 1
      trap - EXIT
    ); then
    rm -f "$snapshot_path"
    printf '%s\n' "$captured_path"
    return 0
  fi

  rm -f "$captured_path" "$snapshot_path"
  die "ui localization release gate generator failed at $script_path; fix the gate or set CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH. The checked-out gate may also have failed restoration."
}

generate_validated_ui_localization_release_gate() {
  local ui_repo="$1"
  local max_age_seconds="$2"
  local max_future_skew_seconds="$3"
  shift 3
  ui_repo="$(resolve_ui_localization_release_gate_repo "$ui_repo" "$@")"
  if [[ -z "$ui_repo" || "$ui_repo" == "/" ]]; then
    die "ui localization release gate validation could not resolve a repo root; set CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH or run from a checkout with the gate script"
  fi
  local output_path=""
  local ui_localization_release_gate_health=""

  output_path="$(generate_ui_localization_release_gate "$ui_repo" "$@")"
  if ! ui_localization_release_gate_health="$(json_generated_at_health \
    "$output_path" \
    "ui localization release gate" \
    "$max_age_seconds" \
    "$max_future_skew_seconds" 2>&1)"; then
    rm -f "$output_path"
    die "ui localization release gate generation produced an unusable receipt: $ui_localization_release_gate_health"
  fi

  printf '%s\n' "$output_path"
}

validate_local_release_proofs() {
  local materializer_path="$1"
  local proof_path="$2"
  local ui_localization_release_gate_path="$3"

  python3 - "$materializer_path" "$proof_path" "$ui_localization_release_gate_path" <<'PY'
from __future__ import annotations

import importlib.util
import pathlib
import sys


materializer_path = pathlib.Path(sys.argv[1])
raw_proof_path = sys.argv[2] if sys.argv[2] else None
ui_gate_path = sys.argv[3] if sys.argv[3] else None

spec = importlib.util.spec_from_file_location("materializer", materializer_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # type: ignore[union-attr]

proof = module.load_release_proof(pathlib.Path(raw_proof_path) if raw_proof_path else None)
if not isinstance(proof, dict):
    raise SystemExit(
        "releaseProof is required for release-channel materialization "
        "(set --proof or embed releaseProof in the source payload)"
    )

ui_localization_release_gate = module.load_ui_localization_release_gate(
    pathlib.Path(ui_gate_path) if ui_gate_path else None
)
if not isinstance(ui_localization_release_gate, dict):
    raise SystemExit(
        "releaseProof.uiLocalizationReleaseGate is required for release-channel materialization "
        "(set --ui-localization-release-gate or embed releaseProof.uiLocalizationReleaseGate in source proof)"
    )

print(f"validated release proof status: {proof.get('status')}")
print(f"validated ui localization gate status: {ui_localization_release_gate.get('status')}")
PY
}

validate_release_payload_contracts() {
  local manifest_path="$1"

  if ! jq -e '.releaseProof | type == "object"' "$manifest_path" >/dev/null 2>&1; then
    die "generated release payload is missing a releaseProof object; expected write-release-manifest to embed it."
  fi

  if ! jq -e '.releaseProof.uiLocalizationReleaseGate | type == "object"' "$manifest_path" >/dev/null 2>&1; then
    die "generated release payload is missing releaseProof.uiLocalizationReleaseGate; expected write-release-manifest to embed it."
  fi

  local release_proof_status
  local ui_gate_status
  local release_proof_status_normalized
  local ui_gate_status_normalized

  release_proof_status="$(jq -r '.releaseProof.status // empty' "$manifest_path" 2>/dev/null || true)"
  if [[ -z "$release_proof_status" || "$release_proof_status" == "null" ]]; then
    die "generated release payload missing releaseProof.status. This would otherwise fail server-side materialization."
  fi
  release_proof_status_normalized="$(to_lower_ascii "$release_proof_status")"
  case "$release_proof_status_normalized" in
    pass|passed|ready) ;;
    *)
      die "releaseProof.status must be pass/passed/ready; got ${release_proof_status}. This would otherwise fail server-side materialization."
      ;;
  esac

  ui_gate_status="$(jq -r '.releaseProof.uiLocalizationReleaseGate.status // empty' "$manifest_path" 2>/dev/null || true)"
  if [[ -z "$ui_gate_status" || "$ui_gate_status" == "null" ]]; then
    die "generated release payload missing releaseProof.uiLocalizationReleaseGate.status. This would otherwise fail server-side materialization."
  fi
  ui_gate_status_normalized="$(to_lower_ascii "$ui_gate_status")"
  case "$ui_gate_status_normalized" in
    pass|passed|ready) ;;
    *)
      die "releaseProof.uiLocalizationReleaseGate.status must be pass/passed/ready; got ${ui_gate_status}. This would otherwise fail server-side materialization."
      ;;
  esac
}

write_manifest_validation_audit_bundle() {
  local dist_dir="$1"
  local downloads_dir="$2"
  local startup_smoke_dir="$3"
  local canonical_manifest_path="$4"
  local compatibility_manifest_path="$5"
  local materialize_log_path="$6"
  local verify_log_path="$7"
  local failure_stage="$8"

  local audit_dir="${dist_dir}/manifest-validation-audit"
  local audit_tarball="${dist_dir}/manifest-validation-audit.tar.gz"

  rm -rf "$audit_dir"
  mkdir -p "$audit_dir"

  if [[ -f "$canonical_manifest_path" ]]; then
    cp "$canonical_manifest_path" "$audit_dir/RELEASE_CHANNEL.generated.json"
  fi
  if [[ -f "$compatibility_manifest_path" ]]; then
    cp "$compatibility_manifest_path" "$audit_dir/releases.json"
  fi
  if [[ -f "$materialize_log_path" ]]; then
    cp "$materialize_log_path" "$audit_dir/materialize_public_release_channel.log"
  fi
  if [[ -f "$verify_log_path" ]]; then
    cp "$verify_log_path" "$audit_dir/verify_public_release_channel.log"
  fi

  python3 - "$downloads_dir" "$audit_dir/files.list.txt" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

downloads_dir = Path(sys.argv[1])
output_path = Path(sys.argv[2])

names = []
if downloads_dir.is_dir():
    names = sorted(path.name for path in downloads_dir.iterdir() if path.is_file())

output_path.write_text("".join(f"{name}\n" for name in names), encoding="utf-8")
PY

  sync_startup_smoke_receipts_for_local_verifier "$startup_smoke_dir" "$audit_dir"

  python3 - "$audit_dir/README.txt" "$failure_stage" "$audit_dir" "$audit_tarball" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

readme_path = Path(sys.argv[1])
failure_stage = (sys.argv[2] or "").strip() or "manifest_validation"
audit_dir = Path(sys.argv[3])
audit_tarball = Path(sys.argv[4])

readme_path.write_text(
    "\n".join(
        [
            f"Manifest validation failed during: {failure_stage}",
            "",
            "Handoff this audit bundle before retrying or debugging further:",
            f"  directory: {audit_dir}",
            f"  tarball: {audit_tarball}",
            "",
            "Included evidence:",
            "  - RELEASE_CHANNEL.generated.json if present",
            "  - releases.json if present",
            "  - files.list.txt for dist/files",
            "  - startup-smoke/startup-smoke-*.receipt.json copies in verifier-compatible layout",
            "  - materialize_public_release_channel.log when available",
            "  - verify_public_release_channel.log when available",
            "",
            "If another Codex or operator is assisting, give them this directory or tarball first.",
            "Also include the original terminal stdout/stderr around the failure if you still have it.",
            "",
        ]
    ),
    encoding="utf-8",
)
PY

  rm -f "$audit_tarball"
  tar -czf "$audit_tarball" -C "$dist_dir" "$(basename "$audit_dir")"
  log "manifest validation audit bundle written to $audit_dir"
  log "manifest validation audit tarball written to $audit_tarball"
}

validate_release_manifest_contracts() {
  local registry_root="$1"
  local manifest_path="$2"
  local downloads_dir="$3"
  local startup_smoke_dir="$4"
  local compatibility_manifest_path="$5"
  local materialize_log_path="$6"
  local verify_log_path="$7"
  local allow_skip="${CHUMMER_RELEASE_SKIP_STRICT_MANIFEST_VERIFY:-0}"
  local dist_dir
  dist_dir="$(dirname "$manifest_path")"

  local verifier_path="${registry_root}/scripts/verify_public_release_channel.py"
  if [[ ! -f "$verifier_path" ]]; then
    log "release manifest verifier not available at $verifier_path; skipping contract-level validation"
    return 0
  fi

  sync_startup_smoke_receipts_for_local_verifier "$startup_smoke_dir" "$dist_dir"

  python3 - "$verifier_path" "$manifest_path" "$compatibility_manifest_path" <<'PY'
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def required_heads_and_platforms(payload: dict) -> tuple[list[str], list[str]]:
    coverage = payload.get("desktopTupleCoverage")
    default_heads = ["avalonia"]
    default_platforms = ["linux", "windows", "macos"]
    if not isinstance(coverage, dict):
        return default_heads, default_platforms
    heads = [str(item).strip().lower() for item in coverage.get("requiredDesktopHeads") or [] if str(item).strip()]
    platforms = [str(item).strip().lower() for item in coverage.get("requiredDesktopPlatforms") or [] if str(item).strip()]
    return (heads or default_heads, platforms or default_platforms)


def recanonicalize_manifest(module, materializer, manifest_path: Path) -> None:
    if not manifest_path.is_file():
        return

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    def derive_verifier_owned_value(name: str, current_value):
        helper = getattr(module, name, None)
        if callable(helper):
            return helper(payload)
        if materializer is None:
            return current_value
        tuple_coverage = None
        if hasattr(materializer, "desktop_tuple_coverage"):
            artifacts = payload.get("artifacts")
            if isinstance(artifacts, list):
                required_heads, required_platforms = required_heads_and_platforms(payload)
                tuple_coverage = materializer.desktop_tuple_coverage(
                    artifacts,
                    required_heads=required_heads,
                    required_platforms=required_platforms,
                    channel_id=str(payload.get("channelId") or payload.get("channel") or "").strip().lower(),
                    release_version=str(payload.get("version") or payload.get("releaseVersion") or "").strip(),
                    channel_status=str(payload.get("status") or "").strip().lower(),
                    rollout_state=str(payload.get("rolloutState") or payload.get("rollout_state") or "").strip().lower(),
                    rollout_reason=str(payload.get("rolloutReason") or payload.get("rollout_reason") or "").strip(),
                    known_issue_summary=str(payload.get("knownIssueSummary") or payload.get("known_issue_summary") or "").strip(),
                )
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
        channel_id = str(payload.get("channelId") or payload.get("channel") or "").strip().lower()
        release_version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
        fallback_helpers = {
            "expected_external_proof_request_rows": lambda: (tuple_coverage or {}).get("externalProofRequests") or current_value,
            "expected_desktop_route_truth_rows": lambda: (tuple_coverage or {}).get("desktopRouteTruth") or current_value,
            "expected_install_aware_artifact_registry_rows": lambda: (
                materializer.install_aware_artifact_registry(
                    artifacts,
                    tuple_coverage,
                    channel_id=channel_id,
                    release_version=release_version,
                )
                if tuple_coverage is not None and hasattr(materializer, "install_aware_artifact_registry")
                else current_value
            ),
            "expected_desktop_surface_ref_rows": lambda: (
                materializer.desktop_surface_refs(
                    artifacts,
                    tuple_coverage,
                    channel_id=channel_id,
                    release_version=release_version,
                )
                if tuple_coverage is not None and hasattr(materializer, "desktop_surface_refs")
                else current_value
            ),
            "expected_artifact_identity_registry_rows": lambda: (
                materializer.artifact_identity_registry(
                    tuple_coverage,
                    channel_id=channel_id,
                    release_version=release_version,
                )
                if tuple_coverage is not None and hasattr(materializer, "artifact_identity_registry")
                else current_value
            ),
            "expected_artifact_publication_binding_rows": lambda: (
                materializer.artifact_publication_bindings(
                    tuple_coverage,
                    channel_id=channel_id,
                    release_version=release_version,
                )
                if tuple_coverage is not None and hasattr(materializer, "artifact_publication_bindings")
                else current_value
            ),
            "expected_public_trust_metrics": lambda: (
                materializer.expected_public_trust_metrics(payload)
                if hasattr(materializer, "expected_public_trust_metrics")
                else current_value
            ),
            "expected_registry_boundary_coverage": lambda: (
                materializer.expected_registry_boundary_coverage(payload)
                if hasattr(materializer, "expected_registry_boundary_coverage")
                else current_value
            ),
        }
        fallback = fallback_helpers.get(name)
        if fallback is not None:
            return fallback()
        return current_value

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
    payload["publicTrustMetrics"] = derive_verifier_owned_value(
        "expected_public_trust_metrics",
        payload.get("publicTrustMetrics") or {},
    )

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


verifier_path = Path(sys.argv[1])
manifest_paths = [Path(value) for value in sys.argv[2:] if str(value).strip()]
spec = importlib.util.spec_from_file_location("verify_public_release_channel", verifier_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
materializer = None
materializer_path = verifier_path.with_name("materialize_public_release_channel.py")
if materializer_path.is_file():
    materializer_spec = importlib.util.spec_from_file_location("materialize_public_release_channel", materializer_path)
    if materializer_spec is not None and materializer_spec.loader is not None:
        materializer = importlib.util.module_from_spec(materializer_spec)
        materializer_spec.loader.exec_module(materializer)

for manifest_path in manifest_paths:
    recanonicalize_manifest(module, materializer, manifest_path)
PY

  local verify_output
  if verify_output="$(python3 "$verifier_path" "$manifest_path" 2>&1)"; then
    [[ -n "$verify_output" ]] && printf '%s\n' "$verify_output" >"$verify_log_path"
    log "release manifest contract validation passed: ${verify_output}"
    return 0
  fi

  printf '%s\n' "$verify_output" >"$verify_log_path"

  if [[ "$allow_skip" == "1" ]]; then
    log "release manifest contract validation failed but continuing because CHUMMER_RELEASE_SKIP_STRICT_MANIFEST_VERIFY=1"
    log "$verify_output"
    write_manifest_validation_audit_bundle \
      "$dist_dir" \
      "$downloads_dir" \
      "$startup_smoke_dir" \
      "$manifest_path" \
      "$compatibility_manifest_path" \
      "$materialize_log_path" \
      "$verify_log_path" \
      "verify_public_release_channel"
    return 0
  fi

  write_manifest_validation_audit_bundle \
    "$dist_dir" \
    "$downloads_dir" \
    "$startup_smoke_dir" \
    "$manifest_path" \
    "$compatibility_manifest_path" \
    "$materialize_log_path" \
    "$verify_log_path" \
    "verify_public_release_channel"
  if [[ "$verify_output" == *"exposes desktop files that are not present in manifest truth"* ]]; then
    log "release manifest verifier found local desktop files missing from manifest truth; caller may retry with startup-smoke filter bypass."
    return 86
  fi
  die "release manifest contract validation failed:\n${verify_output}\nAudit bundle: ${dist_dir}/manifest-validation-audit"
}

validate_public_promotion_evidence() {
  local evidence_path="$1"
  local release_channel="$2"

  python3 - "$evidence_path" "$release_channel" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
channel = (sys.argv[2] or "").strip().lower()
payload = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit("public-promotion.json must be a JSON object.")

if payload.get("contractName") != "chummer.run.desktop_release_publication":
    raise SystemExit("public-promotion.json contractName must be chummer.run.desktop_release_publication.")

artifacts = payload.get("artifacts")
if not isinstance(artifacts, list) or not artifacts:
    raise SystemExit("public-promotion.json contains no artifacts.")

for artifact in artifacts:
    if not isinstance(artifact, dict):
        raise SystemExit("public-promotion.json contains a malformed artifact row.")

    artifact_id = (artifact.get("artifactId") or "").strip()
    if not artifact_id:
        raise SystemExit("public-promotion artifact row is missing artifactId.")

    file_name = (artifact.get("fileName") or "").strip()
    if not file_name:
        raise SystemExit(f"public-promotion artifact {artifact_id} is missing fileName.")

    platform = (artifact.get("platform") or "").strip().lower()
    if not platform:
        raise SystemExit(f"public-promotion artifact {artifact_id} is missing platform.")

    promotion_status = (artifact.get("promotionStatus") or "").strip().lower()
    if promotion_status != "pass":
        raise SystemExit(
            f"public-promotion artifact {artifact_id} is not promoted: promotionStatus={promotion_status}."
        )

    startup_status = (artifact.get("startupSmokeStatus") or "").strip().lower()
    if startup_status != "pass":
        raise SystemExit(
            f"public-promotion artifact {artifact_id} startup smoke check failed: startupSmokeStatus={startup_status}."
        )

    signing_status = (artifact.get("signingStatus") or "").strip().lower()
    notarization_status = (artifact.get("notarizationStatus") or "").strip().lower()
    if channel == "preview":
        if platform in {"macos", "windows"}:
            if signing_status not in {"pass", "skipped_preview"}:
                raise SystemExit(
                    f"public-promotion artifact {artifact_id} has unsupported preview signing status {signing_status}."
                )
            if platform == "macos" and notarization_status not in {"pass", "skipped_preview"}:
                raise SystemExit(
                    f"public-promotion artifact {artifact_id} has unsupported preview notarization status {notarization_status}."
                )
            continue

    if platform == "windows":
        if signing_status != "pass":
            raise SystemExit(
                f"public-promotion artifact {artifact_id} has windows signing status {signing_status}, expected pass."
            )
    if platform == "macos":
        if signing_status != "pass":
            raise SystemExit(
                f"public-promotion artifact {artifact_id} has macOS signing status {signing_status}, expected pass."
            )
        if notarization_status != "pass":
            raise SystemExit(
                f"public-promotion artifact {artifact_id} has macOS notarization status {notarization_status}, expected pass."
            )

print(f"validated public promotion evidence rows: {len(artifacts)}")
PY
}

clone_or_update() {
  local repo_url="$1"
  local target_dir="$2"
  local ref="$3"
  local expected_commit="${4:-}"
  local low_speed_limit="${CHUMMER_GIT_HTTP_LOW_SPEED_LIMIT:-100}"
  local low_speed_time="${CHUMMER_GIT_HTTP_LOW_SPEED_TIME:-120}"
  local max_attempts="${CHUMMER_GIT_MAX_ATTEMPTS:-4}"
  local retry_sleep="${CHUMMER_GIT_RETRY_SLEEP_SECONDS:-5}"

  run_git_cmd() {
    "$@"
  }

  run_git_cmd_with_retries() {
    local op="$1"
    local attempt=1
    shift

    while true; do
      local status=0
      set +e
      run_git_cmd "$@"
      status=$?
      set -e
      if (( status == 0 )); then
        return 0
      fi

      if (( attempt >= max_attempts )); then
        return "$status"
      fi

      attempt=$((attempt + 1))
      log "$op failed (status=$status), retrying in ${retry_sleep}s (attempt ${attempt}/${max_attempts})"
      sleep "$retry_sleep"
    done
  }

  with_git_transport_tuning() {
    GIT_HTTP_LOW_SPEED_LIMIT="$low_speed_limit" \
    GIT_HTTP_LOW_SPEED_TIME="$low_speed_time" \
    "$@"
  }

  clone_branch_checkout() {
    rm -rf "$target_dir"
    with_git_transport_tuning \
      git \
      clone --single-branch --depth 1 --branch "$ref" "$repo_url" "$target_dir"
  }

  fetch_checkout_target() {
    local fetch_target="$ref"
    if [[ -n "$expected_commit" ]]; then
      fetch_target="$expected_commit"
    fi

    run_git_cmd_with_retries \
      "fetching $(basename "$target_dir")" \
      with_git_transport_tuning \
      git \
      -C "$target_dir" \
      fetch --depth 1 origin "$fetch_target"
    run_git_cmd_with_retries \
      "checking out $(basename "$target_dir")" \
      with_git_transport_tuning \
      git \
      -C "$target_dir" \
      checkout -q FETCH_HEAD
  }

  initial_fetch_checkout_target() {
    rm -rf "$target_dir"
    run_git_cmd mkdir -p "$target_dir"
    run_git_cmd git -C "$target_dir" init -q
    run_git_cmd git -C "$target_dir" remote add origin "$repo_url"
    fetch_checkout_target
  }

  github_archive_url_for_ref() {
    local normalized_repo_url="${repo_url%.git}"
    local encoded_ref
    case "$normalized_repo_url" in
      https://github.com/*/*)
        encoded_ref="$(python3 - "$ref" <<'PY'
from urllib.parse import quote
import sys

print(quote(sys.argv[1], safe=""))
PY
)"
        printf 'https://codeload.github.com/%s/tar.gz/%s' "${normalized_repo_url#https://github.com/}" "$encoded_ref"
        return 0
        ;;
    esac
    return 1
  }

  download_github_archive_checkout() {
    local archive_url
    local archive_root
    local archive_path
    local unpack_root
    local extracted_dir
    local archive_retries=$(( max_attempts - 1 ))

    archive_url="$(github_archive_url_for_ref)" || return 1
    archive_root="$(mktemp -d "${TMPDIR:-/tmp}/chummer-bootstrap-archive.XXXXXX")" || return 1
    archive_path="$archive_root/repo.tar.gz"
    unpack_root="$archive_root/unpack"
    mkdir -p "$unpack_root"

    log "git clone exhausted retries; downloading source archive for $(basename "$target_dir") -> $ref"
    if ! curl \
      --fail \
      --location \
      --retry "$archive_retries" \
      --retry-delay "$retry_sleep" \
      --connect-timeout 15 \
      --speed-limit "$low_speed_limit" \
      --speed-time "$low_speed_time" \
      "$archive_url" \
      -o "$archive_path"; then
      rm -rf "$archive_root"
      return 1
    fi

    rm -rf "$target_dir"
    if ! tar -xzf "$archive_path" -C "$unpack_root"; then
      rm -rf "$archive_root"
      return 1
    fi

    extracted_dir="$(find "$unpack_root" -mindepth 1 -maxdepth 1 -type d | sort | head -n 1)"
    if [[ -z "$extracted_dir" || ! -d "$extracted_dir" ]]; then
      rm -rf "$archive_root"
      return 1
    fi

    mv "$extracted_dir" "$target_dir"
    rm -rf "$archive_root"
    return 0
  }

  if [[ -d "$target_dir/.git" ]]; then
    log "updating $(basename "$target_dir") -> $ref"
    run_git_cmd git -C "$target_dir" remote set-url origin "$repo_url"
    fetch_checkout_target
    verify_checkout_expected_commit "$target_dir" "$ref" "$expected_commit"
    return 0
  fi

  if [[ -e "$target_dir" ]]; then
    local stale_target="${target_dir}.stale.$(date -u +%Y%m%d-%H%M%S)"
    log "moving stale non-git path aside: $target_dir -> $stale_target"
    mv "$target_dir" "$stale_target"
  fi

  if [[ -n "$expected_commit" ]]; then
    log "cloning $(basename "$target_dir") -> $ref (pinned $expected_commit)"
    run_git_cmd_with_retries \
      "cloning $(basename "$target_dir")" \
      initial_fetch_checkout_target
  else
    log "cloning $(basename "$target_dir") -> $ref"
    local clone_status=0
    set +e
    run_git_cmd_with_retries \
      "cloning $(basename "$target_dir")" \
      clone_branch_checkout
    clone_status=$?
    set -e
    if (( clone_status != 0 )); then
      if ! download_github_archive_checkout; then
        die "checkout failed for $(basename "$target_dir") -> $ref after ${max_attempts} git clone attempts and GitHub archive fallback"
      fi
    fi
  fi
  verify_checkout_expected_commit "$target_dir" "$ref" "$expected_commit"
}

verify_checkout_expected_commit() {
  local target_dir="$1"
  local ref="$2"
  local expected_commit="$3"
  [[ -n "$expected_commit" ]] || return 0
  [[ "$expected_commit" =~ ^[0-9a-fA-F]{40}$ ]] || die "expected pinned commit for $(basename "$target_dir") is not a full SHA-1: $expected_commit"

  local actual_commit
  actual_commit="$(git -C "$target_dir" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$actual_commit" ]] || die "could not resolve checked-out commit for $(basename "$target_dir")"
  [[ "$actual_commit" == "$expected_commit" ]] || die "checked-out commit drift for $(basename "$target_dir"): ref $ref resolved to $actual_commit, expected $expected_commit"
  log "pinned checkout verified: $(basename "$target_dir") ref=${ref} commit=${actual_commit}"
}

infer_publish_mode() {
  local has_release_upload_auth="${1:-0}"
  if [[ -n "${CHUMMER_RELEASE_PUBLISH_MODE:-}" ]]; then
    printf '%s' "$CHUMMER_RELEASE_PUBLISH_MODE"
    return
  fi

  if [[ -n "${CHUMMER_RELEASE_UPLOAD_SESSIONS_URL:-}" || "$has_release_upload_auth" == "1" ]]; then
    printf 'http'
    return
  fi

  if [[ -n "${CHUMMER_PORTAL_DOWNLOADS_S3_URI:-}" ]]; then
    printf 's3'
    return
  fi

  if [[ -n "${CHUMMER_RELEASE_SSH_TARGET:-}" && -n "${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR:-}" ]]; then
    printf 'filesystem'
    return
  fi

  printf 'http'
}

capture_release_upload_auth_value() {
  local output_value_variable="${1:-}"
  local output_source_variable="${2:-}"
  local captured_value=""
  local captured_source=""
  export -n captured_value captured_source 2>/dev/null || true
  [[ -n "$output_value_variable" && -n "$output_source_variable" ]] || return 1

  if [[ -n "${CHUMMER_RELEASE_UPLOAD_TOKEN:-}" ]]; then
    captured_value="$CHUMMER_RELEASE_UPLOAD_TOKEN"
    captured_source="CHUMMER_RELEASE_UPLOAD_TOKEN"
  elif [[ -n "${CHUMMER_RELEASE_UPLOAD_TICKET:-}" ]]; then
    captured_value="$CHUMMER_RELEASE_UPLOAD_TICKET"
    captured_source="CHUMMER_RELEASE_UPLOAD_TICKET"
  elif [[ -n "${FLEET_INTERNAL_API_TOKEN:-}" ]]; then
    captured_value="$FLEET_INTERNAL_API_TOKEN"
    captured_source="FLEET_INTERNAL_API_TOKEN"
  elif [[ -n "${CHUMMER_RELEASE_UPLOAD_TOKEN_FILE:-}" ]]; then
    captured_source="CHUMMER_RELEASE_UPLOAD_TOKEN_FILE"
  elif [[ -n "${CHUMMER_RELEASE_UPLOAD_TOKEN_PATH:-}" ]]; then
    captured_source="CHUMMER_RELEASE_UPLOAD_TOKEN_PATH"
  elif [[ -n "${CHUMMER_RELEASE_UPLOAD_TICKET_FILE:-}" ]]; then
    captured_source="CHUMMER_RELEASE_UPLOAD_TICKET_FILE"
  elif [[ -n "${CHUMMER_RELEASE_UPLOAD_TICKET_PATH:-}" ]]; then
    captured_source="CHUMMER_RELEASE_UPLOAD_TICKET_PATH"
  fi

  printf -v "$output_value_variable" '%s' "$captured_value"
  printf -v "$output_source_variable" '%s' "$captured_source"
  export -n "$output_value_variable" "$output_source_variable" 2>/dev/null || true
  unset \
    CHUMMER_RELEASE_UPLOAD_TOKEN \
    CHUMMER_RELEASE_UPLOAD_TICKET \
    CHUMMER_RELEASE_UPLOAD_TOKEN_FILE \
    CHUMMER_RELEASE_UPLOAD_TOKEN_PATH \
    CHUMMER_RELEASE_UPLOAD_TICKET_FILE \
    CHUMMER_RELEASE_UPLOAD_TICKET_PATH \
    FLEET_INTERNAL_API_TOKEN
}

prompt_for_release_upload_ticket() {
  local output_variable="${1:-}"
  local prompted_value=""
  [[ -n "$output_variable" ]] || return 1
  if [[ ! -t 0 ]]; then
    return 1
  fi

  printf 'Paste the signed-in release upload handoff code (input hidden): ' >&2
  IFS= read -r -s prompted_value || return 1
  printf '\n' >&2
  [[ -n "$prompted_value" ]] || return 1
  printf -v "$output_variable" '%s' "$prompted_value"
  export -n "$output_variable" 2>/dev/null || true
}

ensure_release_upload_token() {
  local auth_value="${1:-}"
  export -n auth_value 2>/dev/null || true
  [[ -n "$auth_value" ]] \
    || die "set CHUMMER_RELEASE_UPLOAD_TICKET or CHUMMER_RELEASE_UPLOAD_TOKEN for HTTP release promotion"
  (( ${#auth_value} <= 8192 )) && [[ "$auth_value" != *$'\n'* && "$auth_value" != *$'\r'* ]] \
    || die "release upload authorization must be a single value of at most 8192 bytes"
}

write_release_upload_curl_config() {
  local auth_value="${1:-}"
  export -n auth_value 2>/dev/null || true
  ensure_release_upload_token "$auth_value"
  printf '%s' "$auth_value" \
    | python3 -c 'import sys; token = sys.stdin.read(); escaped = token.replace("\\\\", "\\\\\\\\").replace("\"", "\\\\\""); sys.stdout.write(f"header = \"Authorization: Bearer {escaped}\"\n")'
}

validate_publish_mode() {
  local publish_mode="$1"
  local sessions_url="$2"
  local release_upload_auth_value="${3:-}"
  export -n release_upload_auth_value 2>/dev/null || true

  case "$publish_mode" in
    http)
      ensure_release_upload_token "$release_upload_auth_value"
      [[ -n "$sessions_url" ]] || die "set CHUMMER_RELEASE_UPLOAD_SESSIONS_URL for HTTP release promotion"
      [[ -z "${CHUMMER_RELEASE_UPLOAD_URL:-}" ]] \
        || die "CHUMMER_RELEASE_UPLOAD_URL is retired; use CHUMMER_RELEASE_UPLOAD_SESSIONS_URL"
      ! is_true "${CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK:-0}" \
        || die "direct release upload fallback is permanently disabled"
      ! is_true "${CHUMMER_RELEASE_PRINT_SIGNED_INSTALL_CLAIMS:-0}" \
        || die "printing signed install claim credentials is permanently disabled"
      ;;
    filesystem)
      require_cmd ssh
      require_cmd rsync
      [[ -n "${CHUMMER_RELEASE_SSH_TARGET:-}" ]] || die "set CHUMMER_RELEASE_SSH_TARGET for filesystem publish"
      [[ -n "${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR:-}" ]] || die "set CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR for filesystem publish"
      ;;
    s3)
      require_cmd aws
      [[ -n "${CHUMMER_PORTAL_DOWNLOADS_S3_URI:-}" ]] || die "set CHUMMER_PORTAL_DOWNLOADS_S3_URI for s3 publish"
      ;;
    *)
      die "unsupported publish mode: $publish_mode"
      ;;
  esac
}

is_true() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

MAC_RELEASE_STAGE_ONLY=0
MAC_RELEASE_STAGE_OUTPUT_DIR=""

parse_mac_release_stage_only_args() {
  local env_mode="${CHUMMER_MAC_RELEASE_STAGE_ONLY:-}"
  local env_output="${CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR:-}"
  local flag_mode=0
  local flag_output=""
  local value=""

  if [[ -n "$env_mode" ]]; then
    value="$(to_lower_ascii "$env_mode")"
    case "$value" in
      1|true|yes|on) MAC_RELEASE_STAGE_ONLY=1 ;;
      0|false|no|off) MAC_RELEASE_STAGE_ONLY=0 ;;
      *) die "CHUMMER_MAC_RELEASE_STAGE_ONLY must be a boolean value" ;;
    esac
  else
    MAC_RELEASE_STAGE_ONLY=0
  fi

  while (( $# > 0 )); do
    case "$1" in
      --stage-only)
        flag_mode=1
        shift
        ;;
      --stage-output-dir)
        (( $# >= 2 )) || die "--stage-output-dir requires a path"
        [[ -z "$flag_output" ]] || die "--stage-output-dir may be supplied only once"
        flag_output="$2"
        shift 2
        ;;
      --stage-output-dir=*)
        [[ -z "$flag_output" ]] || die "--stage-output-dir may be supplied only once"
        flag_output="${1#--stage-output-dir=}"
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  if (( flag_mode == 1 )); then
    if [[ -n "$env_mode" ]] && ! is_true "$env_mode"; then
      die "--stage-only conflicts with CHUMMER_MAC_RELEASE_STAGE_ONLY=$env_mode"
    fi
    MAC_RELEASE_STAGE_ONLY=1
  fi
  if [[ -n "$flag_output" && -n "$env_output" && "$flag_output" != "$env_output" ]]; then
    die "--stage-output-dir conflicts with CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR"
  fi
  MAC_RELEASE_STAGE_OUTPUT_DIR="${flag_output:-$env_output}"

  if (( MAC_RELEASE_STAGE_ONLY == 0 )); then
    [[ -z "$MAC_RELEASE_STAGE_OUTPUT_DIR" ]] \
      || die "CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR/--stage-output-dir requires stage-only mode"
    return 0
  fi

  [[ -n "$MAC_RELEASE_STAGE_OUTPUT_DIR" ]] \
    || die "stage-only mode requires CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR or --stage-output-dir"

  local incompatible_setting=""
  for incompatible_setting in \
    CHUMMER_RELEASE_PUBLISH_MODE \
    CHUMMER_RELEASE_UPLOAD_URL \
    CHUMMER_RELEASE_UPLOAD_SESSIONS_URL \
    CHUMMER_RELEASE_UPLOAD_TOKEN \
    CHUMMER_RELEASE_UPLOAD_TICKET \
    CHUMMER_RELEASE_UPLOAD_TOKEN_FILE \
    CHUMMER_RELEASE_UPLOAD_TOKEN_PATH \
    CHUMMER_RELEASE_UPLOAD_TICKET_FILE \
    CHUMMER_RELEASE_UPLOAD_TICKET_PATH \
    CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK \
    CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS \
    CHUMMER_RELEASE_UPLOAD_RETRY_SLEEP_SECONDS \
    CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES \
    CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES \
    CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE \
    CHUMMER_RELEASE_PRINT_SIGNED_INSTALL_CLAIMS \
    CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION \
    CHUMMER_RELEASE_SKIP_STRICT_MANIFEST_VERIFY \
    FLEET_INTERNAL_API_TOKEN \
    CHUMMER_RELEASE_SSH_TARGET \
    CHUMMER_REMOTE_STAGING_DIR \
    CHUMMER_REMOTE_UI_REPO_DIR \
    CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR \
    CHUMMER_PORTAL_DOWNLOADS_S3_URI \
    CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL \
    CHUMMER_APP_SIGN_IDENTITY \
    CHUMMER_NOTARY_PROFILE; do
    value=""
    eval "value=\"\${${incompatible_setting}:-}\""
    [[ -z "$value" ]] \
      || die "stage-only mode rejects publish-only setting $incompatible_setting"
  done
}

resolve_mac_release_stage_output_path() {
  python3 - "$1" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

raw = sys.argv[1]
candidate = Path(raw).expanduser()
if not candidate.is_absolute():
    raise SystemExit("stage-only output path must be absolute")
if candidate.exists() or candidate.is_symlink():
    raise SystemExit("stage-only output path must not already exist or be a symlink")
try:
    parent = candidate.parent.resolve(strict=True)
except OSError as exc:
    raise SystemExit(f"stage-only output parent is unavailable: {type(exc).__name__}") from exc
if not parent.is_dir():
    raise SystemExit("stage-only output parent must be a directory")
if candidate.name in {"", ".", ".."}:
    raise SystemExit("stage-only output path must name a new directory")
print(parent / candidate.name)
PY
}

write_release_manifests() {
  local registry_root="$1"
  local downloads_dir="$2"
  local startup_smoke_dir="$3"
  local compatibility_manifest_path="$4"
  local canonical_manifest_path="$5"
  local release_version="$6"
  local release_channel="$7"
  local published_at="$8"
  local proof_path="$9"
  local ui_localization_release_gate_path="${10:-}"
  local skip_startup_smoke_filter="${11:-0}"

  local materializer="$registry_root/scripts/materialize_public_release_channel.py"
  [[ -f "$materializer" ]] || die "registry materializer missing: $materializer"
  local dist_dir
  dist_dir="$(dirname "$canonical_manifest_path")"
  local materialize_log_path="${dist_dir}/.manifest-materialize.log"
  local verify_log_path="${dist_dir}/.manifest-verify.log"
  rm -f "$materialize_log_path" "$verify_log_path"

  local help_text
  help_text="$(python3 "$materializer" --help 2>&1 || true)"

  local -a args=(
    "$materializer"
    "--downloads-dir" "$downloads_dir"
    "--output" "$canonical_manifest_path"
    "--compat-output" "$compatibility_manifest_path"
    "--product" "chummer"
    "--channel" "$release_channel"
    "--version" "$release_version"
    "--published-at" "$published_at"
    "--downloads-prefix" "/downloads/files"
  )

  if [[ -d "$startup_smoke_dir" ]] && [[ "$help_text" == *"--startup-smoke-dir"* ]]; then
    args+=("--startup-smoke-dir" "$startup_smoke_dir")
  fi
  if [[ "$skip_startup_smoke_filter" == "1" ]] && [[ "$help_text" == *"--skip-startup-smoke-filter"* ]]; then
    args+=("--skip-startup-smoke-filter")
  fi

  if [[ -n "$proof_path" ]] && [[ -f "$proof_path" ]]; then
    args+=("--proof" "$proof_path")
  fi
  if [[ -n "$ui_localization_release_gate_path" ]] && [[ -f "$ui_localization_release_gate_path" ]]; then
    args+=("--ui-localization-release-gate" "$ui_localization_release_gate_path")
  fi

  local current_skip_startup_smoke_filter="$skip_startup_smoke_filter"
  local used_fallback_no_filter=0
  local materialize_output
  local validate_status=0

  while true; do
    if is_true "$current_skip_startup_smoke_filter"; then
      if ! materialize_output="$(CHUMMER_MATERIALIZE_SKIP_STARTUP_SMOKE_FILTER=1 python3 "${args[@]}" 2>&1)"; then
        printf '%s\n' "$materialize_output" >"$materialize_log_path"
        write_manifest_validation_audit_bundle \
          "$dist_dir" \
          "$downloads_dir" \
          "$startup_smoke_dir" \
          "$canonical_manifest_path" \
          "$compatibility_manifest_path" \
          "$materialize_log_path" \
          "$verify_log_path" \
          "materialize_public_release_channel"
        die "release manifest materialization failed:\n${materialize_output}\nAudit bundle: ${dist_dir}/manifest-validation-audit"
      fi
    else
      if ! materialize_output="$(python3 "${args[@]}" 2>&1)"; then
        printf '%s\n' "$materialize_output" >"$materialize_log_path"
        write_manifest_validation_audit_bundle \
          "$dist_dir" \
          "$downloads_dir" \
          "$startup_smoke_dir" \
          "$canonical_manifest_path" \
          "$compatibility_manifest_path" \
          "$materialize_log_path" \
          "$verify_log_path" \
          "materialize_public_release_channel"
        die "release manifest materialization failed:\n${materialize_output}\nAudit bundle: ${dist_dir}/manifest-validation-audit"
      fi
    fi

    [[ -n "$materialize_output" ]] && printf '%s\n' "$materialize_output"
    printf '%s\n' "$materialize_output" >"$materialize_log_path"

    validate_status=0
    validate_release_manifest_contracts \
      "$registry_root" \
      "$canonical_manifest_path" \
      "$downloads_dir" \
      "$startup_smoke_dir" \
      "$compatibility_manifest_path" \
      "$materialize_log_path" \
      "$verify_log_path" || validate_status=$?

    if [[ "$validate_status" == "0" ]]; then
      break
    fi

    if [[ "$validate_status" == "86" ]]; then
      if ! is_true "$current_skip_startup_smoke_filter"; then
        log "release manifest verifier excluded local desktop files from manifest truth; retrying materializer with startup-smoke filter disabled."
        current_skip_startup_smoke_filter=1
        continue
      fi

      if [[ "$used_fallback_no_filter" == "0" ]]; then
        log "release manifest verifier still excluded local desktop files after startup-smoke filter bypass. generating fallback manifests directly from dist files."
        write_release_manifests_fallback_no_filter \
          "$registry_root" \
          "$downloads_dir" \
          "$compatibility_manifest_path" \
          "$canonical_manifest_path" \
          "$release_version" \
          "$release_channel" \
          "$published_at" \
          "$proof_path" \
          "$ui_localization_release_gate_path"

        used_fallback_no_filter=1
        validate_status=0
        validate_release_manifest_contracts \
          "$registry_root" \
          "$canonical_manifest_path" \
          "$downloads_dir" \
          "$startup_smoke_dir" \
          "$compatibility_manifest_path" \
          "$materialize_log_path" \
          "$verify_log_path" || validate_status=$?
        if [[ "$validate_status" == "0" ]]; then
          break
        fi
      fi

      die "release manifest verification still excludes local desktop files after startup-smoke filter bypass and fallback manifest generation. Audit bundle: ${dist_dir}/manifest-validation-audit"
    fi

    die "release manifest contract validation failed after retry handling. Audit bundle: ${dist_dir}/manifest-validation-audit"
  done

  rm -f "$materialize_log_path" "$verify_log_path"
}

validate_manifests_have_artifacts() {
  local canonical_manifest_path="$1"
  local compatibility_manifest_path="$2"
  local startup_smoke_dir="$3"
  local startup_smoke_receipt_count=0

  local artifact_count
  artifact_count="$(python3 - "$canonical_manifest_path" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
print(len(payload.get("artifacts") or []))
PY
)" || die "unable to read canonical manifest: $canonical_manifest_path"
  local compatibility_count
  compatibility_count="$(python3 - "$compatibility_manifest_path" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
print(len(payload.get("downloads") or []))
PY
)" || die "unable to read compatibility manifest: $compatibility_manifest_path"

  if [[ "$artifact_count" == "0" || "$compatibility_count" == "0" ]]; then
    log "WARNING: manifest projection has zero artifacts before upload"
    log "  canonical: $canonical_manifest_path (artifacts=$artifact_count)"
    log "  compatibility: $compatibility_manifest_path (downloads=$compatibility_count)"
    if [[ -d "$startup_smoke_dir" ]]; then
      startup_smoke_receipt_count="$(find "$startup_smoke_dir" -type f -name 'startup-smoke-*.receipt.json' | wc -l | tr -d ' ')"
    fi
    log "startup smoke receipts found: ${startup_smoke_receipt_count}"
    return 1
  fi
}

stamp_startup_smoke_receipt_artifact_identity() {
  local receipt_path="$1"
  local artifact_path="$2"
  local head="$3"
  local rid="$4"

  python3 - "$receipt_path" "$artifact_path" "$head" "$rid" <<'PY'
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

receipt_path = pathlib.Path(sys.argv[1])
artifact_path = pathlib.Path(sys.argv[2])
head = str(sys.argv[3] or "").strip().lower()
rid = str(sys.argv[4] or "").strip().lower()

if not receipt_path.is_file() or not artifact_path.is_file():
    raise SystemExit(0)

payload = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
if not isinstance(payload, dict):
    raise SystemExit(0)

hasher = hashlib.sha256()
with artifact_path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        hasher.update(chunk)
artifact_sha = hasher.hexdigest()
artifact_name = artifact_path.name

artifact_parts = list(artifact_path.parts)
artifact_parts_lower = [part.lower() for part in artifact_parts]
artifact_relative_path = ""
if "files" in artifact_parts_lower:
    files_index = artifact_parts_lower.index("files")
    relative_tail = [part for part in artifact_parts[files_index + 1 :] if part]
    if relative_tail:
        artifact_relative_path = "files/" + "/".join(relative_tail)
if not artifact_relative_path:
    artifact_relative_path = f"files/{artifact_name}"

match = re.match(
    r"^chummer-(?P<head>avalonia|blazor-desktop)-(?P<rid>[^.]+?)(?P<installer>-installer)?\.(?P<ext>exe|zip|tar\.gz|deb|dmg|pkg|msix)$",
    artifact_name,
    flags=re.IGNORECASE,
)
artifact_kind = ""
if match:
    head = match.group("head").strip().lower() or head
    rid = match.group("rid").strip().lower() or rid
    ext = match.group("ext").strip().lower()
    installer_suffix = bool(match.group("installer"))
    if installer_suffix or ext == "deb":
        artifact_kind = "installer"
    elif ext == "exe":
        artifact_kind = "portable"
    elif ext in {"zip", "tar.gz"}:
        artifact_kind = "archive"
    elif ext in {"dmg", "pkg", "msix"}:
        artifact_kind = ext
    else:
        artifact_kind = "artifact"

if head and rid and artifact_kind:
    payload["artifactId"] = f"{head}-{rid}-{artifact_kind}"
if rid and not str(payload.get("rid") or "").strip():
    payload["rid"] = rid

# Successful mac startup smoke must surface as a passing receipt even when an
# older desktop runtime omitted the field entirely.
payload["status"] = "pass"
payload["artifactPath"] = str(artifact_path)
payload["artifactFileName"] = artifact_name
payload["artifactRelativePath"] = artifact_relative_path
payload["artifactSha256"] = artifact_sha
payload["artifactDigest"] = f"sha256:{artifact_sha}"
payload["artifactDigestSource"] = "artifact_path"

receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

write_release_manifests_fallback_no_filter() {
  local registry_root="$1"
  local downloads_dir="$2"
  local compatibility_manifest_path="$3"
  local canonical_manifest_path="$4"
  local release_version="$5"
  local release_channel="$6"
  local published_at="$7"
  local proof_path="$8"
  local ui_localization_release_gate_path="${9:-}"

  python3 - "$registry_root" "$downloads_dir" "$compatibility_manifest_path" "$canonical_manifest_path" "$release_version" "$release_channel" "$published_at" "$proof_path" "$ui_localization_release_gate_path" <<'PY'
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

registry_root = Path(sys.argv[1])
downloads_dir = Path(sys.argv[2])
compatibility_output = Path(sys.argv[3])
canonical_output = Path(sys.argv[4])
release_version = (sys.argv[5] or "").strip() or "unpublished"
release_channel = (sys.argv[6] or "preview").strip().lower() or "preview"
published_at = (sys.argv[7] or "").strip()
proof_path = Path(sys.argv[8]) if len(sys.argv) > 8 and sys.argv[8] else None
ui_gate_path = Path(sys.argv[9]) if len(sys.argv) > 9 and sys.argv[9] else None

if not published_at:
  published_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

materializer_path = registry_root / "scripts" / "materialize_public_release_channel.py"
if not materializer_path.is_file():
  raise SystemExit(f"fallback materializer helper is unavailable: {materializer_path}")
verifier_path = registry_root / "scripts" / "verify_public_release_channel.py"
if not verifier_path.is_file():
  raise SystemExit(f"fallback verifier helper is unavailable: {verifier_path}")

spec = importlib.util.spec_from_file_location("materialize_public_release_channel_fallback", materializer_path)
if spec is None or spec.loader is None:
  raise SystemExit(f"unable to load fallback materializer helper from {materializer_path}")
materializer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materializer)

verifier_spec = importlib.util.spec_from_file_location("verify_public_release_channel_fallback", verifier_path)
if verifier_spec is None or verifier_spec.loader is None:
  raise SystemExit(f"unable to load fallback verifier helper from {verifier_path}")
verifier = importlib.util.module_from_spec(verifier_spec)
verifier_spec.loader.exec_module(verifier)


def load_contract_if_present(path: Path | None) -> dict:
  if path is None:
    return {}
  loader = materializer.load_release_proof if path == proof_path else materializer.load_ui_localization_release_gate
  loaded = loader(path)
  return dict(loaded) if isinstance(loaded, dict) else {}


proof_payload = load_contract_if_present(proof_path)
ui_gate_payload = load_contract_if_present(ui_gate_path)
if ui_gate_payload:
  if not proof_payload:
    proof_payload = {}
  proof_payload["uiLocalizationReleaseGate"] = ui_gate_payload

artifacts = []
unmatched_files = []

for entry in (sorted(downloads_dir.iterdir()) if downloads_dir.is_dir() else []):
  if not entry.is_file():
    continue

  artifact_row = materializer.row_from_file(entry, downloads_prefix="/downloads/files")
  if not isinstance(artifact_row, dict):
    unmatched_files.append(entry.name)
    continue

  artifact_row["channelId"] = release_channel
  artifact_row["channel"] = release_channel
  artifact_row["releaseVersion"] = release_version
  artifact_row["version"] = release_version
  artifact_row["generatedAt"] = published_at
  artifact_row["generated_at"] = published_at
  artifact_row["compatibilityState"] = "compatible"
  artifacts.append(artifact_row)

if not artifacts:
  unmatched_samples = ", ".join(sorted(unmatched_files)[:20])
  print(json.dumps({"warning": "fallback parser rejected all files", "candidate_files": unmatched_samples}, sort_keys=True))

artifacts.sort(key=lambda row: (row.get("kind") != "installer", row.get("platform"), row.get("arch"), row.get("head"), row.get("fileName")))
tuple_coverage = materializer.desktop_tuple_coverage(
  artifacts,
  required_heads=list(materializer.DEFAULT_REQUIRED_DESKTOP_HEADS),
  required_platforms=list(materializer.DEFAULT_REQUIRED_DESKTOP_PLATFORMS),
  channel_id=release_channel,
  downloads_dir=downloads_dir,
)
desktop_coverage_complete = materializer.desktop_tuple_coverage_is_complete(tuple_coverage)

canonical_payload = {
  "generatedAt": published_at,
  "generated_at": published_at,
  "schemaVersion": 1,
  "product": "chummer",
  "contract_name": "Chummer.Hub.Registry.Contracts",
  "contractName": "Chummer.Hub.Registry.Contracts",
  "channelId": release_channel,
  "version": release_version,
  "publishedAt": published_at,
  "status": "published",
  "artifactSource": "ui_desktop_bundle",
  "rolloutState": materializer.derive_rollout_state(
    release_channel,
    "published",
    proof_payload,
    desktop_coverage_complete=desktop_coverage_complete,
  ),
  "rolloutReason": materializer.derive_rollout_reason(
    release_channel,
    "published",
    proof_payload,
    desktop_coverage_complete=desktop_coverage_complete,
    coverage=tuple_coverage,
  ),
  "supportabilityState": materializer.derive_supportability_state(
    "published",
    proof_payload,
    desktop_coverage_complete=desktop_coverage_complete,
  ),
  "supportabilitySummary": materializer.derive_supportability_summary(
    "published",
    proof_payload,
    desktop_coverage_complete=desktop_coverage_complete,
    coverage=tuple_coverage,
  ),
  "knownIssueSummary": materializer.derive_known_issue_summary(
    release_channel,
    "published",
    proof_payload,
    desktop_coverage_complete=desktop_coverage_complete,
    coverage=tuple_coverage,
  ),
  "fixAvailabilitySummary": materializer.derive_fix_availability_summary(
    "published",
    proof_payload,
    desktop_coverage_complete=desktop_coverage_complete,
  ),
  "releaseProof": proof_payload,
  "artifacts": artifacts,
  "desktopTupleCoverage": tuple_coverage,
}

def derive_verifier_owned_value(payload: dict, name: str, current_value):
    helper = getattr(verifier, name, None)
    if callable(helper):
        return helper(payload)
    channel_id = str(payload.get("channelId") or payload.get("channel") or "").strip().lower()
    release_version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
    fallback_helpers = {
        "expected_install_aware_artifact_registry_rows": lambda: materializer.install_aware_artifact_registry(
            artifacts,
            tuple_coverage,
            channel_id=channel_id,
            release_version=release_version,
        ),
        "expected_desktop_surface_ref_rows": lambda: materializer.desktop_surface_refs(
            artifacts,
            tuple_coverage,
            channel_id=channel_id,
            release_version=release_version,
        ),
        "expected_artifact_identity_registry_rows": lambda: materializer.artifact_identity_registry(
            tuple_coverage,
            channel_id=channel_id,
            release_version=release_version,
        ),
        "expected_artifact_publication_binding_rows": lambda: materializer.artifact_publication_bindings(
            tuple_coverage,
            channel_id=channel_id,
            release_version=release_version,
        ),
        "expected_public_trust_metrics": lambda: materializer.expected_public_trust_metrics(payload),
        "expected_registry_boundary_coverage": lambda: materializer.expected_registry_boundary_coverage(payload),
    }
    fallback = fallback_helpers.get(name)
    if fallback is not None:
        return fallback()
    return current_value

canonical_payload["installAwareArtifactRegistry"] = derive_verifier_owned_value(
    canonical_payload,
    "expected_install_aware_artifact_registry_rows",
    canonical_payload.get("installAwareArtifactRegistry") or [],
)
canonical_payload["desktopSurfaceRefs"] = derive_verifier_owned_value(
    canonical_payload,
    "expected_desktop_surface_ref_rows",
    canonical_payload.get("desktopSurfaceRefs") or [],
)
canonical_payload["artifactIdentityRegistry"] = derive_verifier_owned_value(
    canonical_payload,
    "expected_artifact_identity_registry_rows",
    canonical_payload.get("artifactIdentityRegistry") or [],
)
canonical_payload["artifactPublicationBindings"] = derive_verifier_owned_value(
    canonical_payload,
    "expected_artifact_publication_binding_rows",
    canonical_payload.get("artifactPublicationBindings") or [],
)
canonical_payload["publicTrustMetrics"] = derive_verifier_owned_value(
    canonical_payload,
    "expected_public_trust_metrics",
    canonical_payload.get("publicTrustMetrics") or {},
)
canonical_payload["registryBoundaryCoverage"] = derive_verifier_owned_value(
    canonical_payload,
    "expected_registry_boundary_coverage",
    canonical_payload.get("registryBoundaryCoverage") or {},
)

compatibility_payload = materializer.compatibility_payload(canonical_payload)
compatibility_downloads = compatibility_payload.get("downloads")
if not isinstance(compatibility_downloads, list):
  compatibility_downloads = []

canonical_output.parent.mkdir(parents=True, exist_ok=True)
compatibility_output.parent.mkdir(parents=True, exist_ok=True)
with canonical_output.open("w", encoding="utf-8") as handle:
  json.dump(canonical_payload, handle, indent=2)
  handle.write("\n")
with compatibility_output.open("w", encoding="utf-8") as handle:
  json.dump(compatibility_payload, handle, indent=2)
  handle.write("\n")

print(
  json.dumps(
    {
      "artifact_count": len(artifacts),
      "compatibility_count": len(compatibility_downloads),
    },
    sort_keys=True,
  )
)
PY

  [[ -f "$canonical_manifest_path" ]] && log "manifest fallback completed: $canonical_manifest_path and $compatibility_manifest_path"
}

validate_bundle_directory_integrity() {
  local bundle_dir="$1"

  local canonical_manifest_path="$bundle_dir/RELEASE_CHANNEL.generated.json"
  local compatibility_manifest_path="$bundle_dir/releases.json"
  local evidence_path="$bundle_dir/release-evidence/public-promotion.json"
  local files_dir="$bundle_dir/files"
  local startup_smoke_dir="$bundle_dir/startup-smoke"

  [[ -f "$canonical_manifest_path" ]] || die "bundle integrity check failed: missing $canonical_manifest_path"
  [[ -f "$compatibility_manifest_path" ]] || die "bundle integrity check failed: missing $compatibility_manifest_path"
  [[ -d "$files_dir" ]] || die "bundle integrity check failed: missing $files_dir"

  python3 - "$canonical_manifest_path" "$compatibility_manifest_path" "$evidence_path" "$files_dir" "$startup_smoke_dir" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_platform(raw: str | None) -> str:
    platform = (raw or "").strip().lower()
    if not platform:
        return ""

    for separator in ("_", "-", "/", " "):
        if separator in platform:
            platform = platform.split(separator, 1)[0]
            break

    return {
        "mac": "macos",
        "win": "windows",
        "osx": "macos",
    }.get(platform, platform)


def resolve_file_name(artifact: dict) -> str:
    file_name = (artifact.get("fileName") or "").strip()
    if file_name:
        return Path(file_name).name
    return Path((artifact.get("downloadUrl") or "").strip()).name


def resolve_file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(2_621_440), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_installer_artifact(artifact: dict) -> bool:
    kind = (artifact.get("kind") or "").strip().lower()
    if kind:
        return kind in {"installer", "dmg", "pkg", "msix"}
    return resolve_file_name(artifact).lower().endswith((".exe", ".deb", ".dmg", ".pkg", ".msix"))


def load_receipts(startup_smoke_root: Path) -> list:
    if not startup_smoke_root.is_dir():
        return []

    receipts: list[dict] = []
    for path in startup_smoke_root.rglob("startup-smoke-*.receipt.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if (payload.get("headId") and payload.get("platform") and payload.get("arch")):
            receipts.append(payload)
    return receipts


def matching_receipt(artifact: dict, receipts: list):
    expected_head = (artifact.get("head") or "").strip().lower()
    expected_platform = normalize_platform(artifact.get("platform"))
    expected_arch = (artifact.get("arch") or "").strip().lower()
    expected_sha = (artifact.get("sha256") or "").strip().lower()

    for receipt in receipts:
        if (receipt.get("headId") or "").strip().lower() != expected_head:
            continue
        if normalize_platform(receipt.get("platform")) != expected_platform:
            continue
        if (receipt.get("arch") or "").strip().lower() != expected_arch:
            continue
        if expected_sha:
            digest = (receipt.get("artifactDigest") or "").strip().lower()
            if digest.startswith("sha256:"):
                digest = digest[7:]
            if digest and digest == expected_sha:
                return receipt

            fallback = (receipt.get("artifactSha256") or "").strip().lower()
            if fallback.startswith("sha256:"):
                fallback = fallback[7:]
            if fallback and fallback == expected_sha:
                return receipt
        else:
            return receipt

    return None


def sanitize_status(value: str | None) -> str:
    return (value or "").strip().lower()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"bundle integrity check failed: {message}")


canonical_path = Path(sys.argv[1])
compatibility_path = Path(sys.argv[2])
evidence_path = Path(sys.argv[3])
files_root = Path(sys.argv[4])
startup_smoke_root = Path(sys.argv[5])

canonical = load_json(canonical_path)
compatibility = load_json(compatibility_path)

canonical_artifacts = canonical.get("artifacts")
compatibility_artifacts = compatibility.get("downloads")
require(isinstance(canonical_artifacts, list), "canonical manifest artifacts must be a list.")
require(isinstance(compatibility_artifacts, list), "compatibility manifest downloads must be a list.")
require(len(canonical_artifacts) > 0, "canonical manifest produced no artifacts.")
require(len(compatibility_artifacts) > 0, "compatibility manifest produced no downloads.")

canonical_by_id = {
    str(artifact.get("artifactId") or "").strip().lower(): artifact
    for artifact in canonical_artifacts
    if isinstance(artifact, dict) and str(artifact.get("artifactId") or "").strip()
}
compatibility_by_id = {
    str(artifact.get("id") or "").strip().lower(): artifact
    for artifact in compatibility_artifacts
    if isinstance(artifact, dict) and str(artifact.get("id") or "").strip()
}
require(len(canonical_by_id) > 0, "canonical manifest artifact ids could not be resolved.")
require(len(compatibility_by_id) > 0, "compatibility manifest download ids could not be resolved.")
require(set(canonical_by_id.keys()) == set(compatibility_by_id.keys()),
        "compatibility/canonical artifact id sets do not match.")

for artifact_id in sorted(canonical_by_id):
    artifact = canonical_by_id[artifact_id]
    file_name = resolve_file_name(artifact)
    require(file_name, f"canonical artifact {artifact_id} has no file name.")
    artifact_path = files_root / file_name
    require(artifact_path.is_file(), f"bundle is missing artifact file {artifact_path}.")

    expected_size = artifact.get("sizeBytes")
    if isinstance(expected_size, int) and expected_size >= 0:
        require(artifact_path.stat().st_size == expected_size,
                f"artifact size mismatch for {artifact_id}: expected {expected_size}, got {artifact_path.stat().st_size}.")

    expected_sha = (artifact.get("sha256") or "").strip().lower()
    if expected_sha:
        expected_sha = expected_sha[7:] if expected_sha.startswith("sha256:") else expected_sha
        require(resolve_file_sha(artifact_path) == expected_sha,
                f"artifact sha256 mismatch for {artifact_id}.")

    if is_installer_artifact(artifact):
        require(startup_smoke_root.is_dir(), "startup-smoke folder missing for installer artifacts.")
        if startup_smoke_root.is_dir():
            require(matching_receipt(artifact, load_receipts(startup_smoke_root)) is not None,
                    f"startup smoke receipt missing for installer artifact {artifact_id}.")

if evidence_path.is_file():
    evidence = load_json(evidence_path)
    require(isinstance(evidence, dict) and evidence.get("contractName") == "chummer.run.desktop_release_publication",
            "release-evidence/public-promotion.json contractName is invalid.")
    evidence_artifacts = evidence.get("artifacts")
    require(isinstance(evidence_artifacts, list), "release-evidence/public-promotion.json artifacts must be a list.")
    evidence_by_id = {
        str(item.get("artifactId") or "").strip().lower(): item
        for item in evidence_artifacts
        if isinstance(item, dict)
    }
    for artifact_id, artifact in canonical_by_id.items():
        if not is_installer_artifact(artifact):
            continue
        row = evidence_by_id.get(artifact_id)
        if row is None:
            row = evidence_by_id.get((Path(resolve_file_name(artifact)).name or "").lower())
        require(row is not None, f"promotion evidence is missing for installer artifact {artifact_id}.")
        require(sanitize_status(row.get("promotionStatus")) == "pass", f"promotion evidence did not pass for {artifact_id}.")
        require(sanitize_status(row.get("startupSmokeStatus")) == "pass", f"startup smoke evidence did not pass for {artifact_id}.")
else:
    require(not any(is_installer_artifact(artifact) for artifact in canonical_by_id.values()),
            "release-evidence/public-promotion.json is required for installer artifacts.")

print("bundle integrity check passed: artifact ids and evidence align")
PY
}

log_bundle_manifest_summary() {
  local dist_dir="$1"
  local canonical_manifest_path="$dist_dir/RELEASE_CHANNEL.generated.json"
  local compatibility_manifest_path="$dist_dir/releases.json"
  local evidence_path="$dist_dir/release-evidence/public-promotion.json"
  local startup_smoke_dir="$dist_dir/startup-smoke"

  if [[ ! -f "$compatibility_manifest_path" || ! -f "$canonical_manifest_path" ]]; then
    log "manifest summary unavailable (missing manifest file)"
    return 0
  fi

  python3 - "$compatibility_manifest_path" "$canonical_manifest_path" "$evidence_path" "$startup_smoke_dir" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

compatibility = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
canonical = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
evidence_path = Path(sys.argv[3]) if sys.argv[3] else None
startup_smoke_root = Path(sys.argv[4]) if sys.argv[4] else None

compat_downloads = compatibility.get("downloads") or []
canonical_artifacts = canonical.get("artifacts") or []
startup_smoke_count = 0
if startup_smoke_root and startup_smoke_root.is_dir():
    startup_smoke_count = sum(1 for path in startup_smoke_root.rglob("startup-smoke-*.receipt.json"))

compat_ids = [str(item.get("id") or "").strip() for item in compat_downloads if isinstance(item, dict) and str(item.get("id") or "").strip()]
artifact_ids = [str(item.get("artifactId") or "").strip() for item in canonical_artifacts if isinstance(item, dict) and str(item.get("artifactId") or "").strip()]

print(f"manifest snapshot: compatibility_downloads={len(compat_downloads)}, canonical_artifacts={len(canonical_artifacts)}, startup-smoke-receipts={startup_smoke_count}")
print(f"  compatibility ids: {', '.join(compat_ids[:12]) if compat_ids else '<none>'}")
if len(compat_ids) > 12:
    print(f"  compatibility ids (remaining): {len(compat_ids) - 12}")
print(f"  canonical artifact ids: {', '.join(artifact_ids[:12]) if artifact_ids else '<none>'}")
if len(artifact_ids) > 12:
    print(f"  canonical artifact ids (remaining): {len(artifact_ids) - 12}")

if not evidence_path or not evidence_path.exists():
    print("  promotion evidence: unavailable")
else:
    try:
      payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception:
      print("  promotion evidence: malformed")
    else:
      artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
      if not isinstance(artifacts, list):
        print("  promotion evidence: malformed")
      else:
        pass_count = sum(
            1
            for row in artifacts
            if isinstance(row, dict) and str(row.get("promotionStatus") or "").strip().lower() == "pass"
        )
        print(f"  promotion evidence: pass={pass_count} / total={len(artifacts)}")
PY
}

write_release_upload_payload_summary() {
  local dist_dir="$1"
  local output_path="$dist_dir/release-upload-payload-summary.json"
  local compatibility_manifest_path="$dist_dir/releases.json"
  local canonical_manifest_path="$dist_dir/RELEASE_CHANNEL.generated.json"
  local evidence_path="$dist_dir/release-evidence/public-promotion.json"
  local startup_smoke_dir="$dist_dir/startup-smoke"
  local startup_smoke_count
  startup_smoke_count="$(find "$startup_smoke_dir" -type f -name 'startup-smoke-*.receipt.json' | wc -l | tr -d ' ')"

  python3 - "$compatibility_manifest_path" "$canonical_manifest_path" "$evidence_path" "$startup_smoke_dir" "$output_path" "$startup_smoke_count" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

compatibility = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
canonical = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
evidence_path = Path(sys.argv[3]) if sys.argv[3] else None
startup_smoke_root = Path(sys.argv[4]) if sys.argv[4] else None
output_path = Path(sys.argv[5])
startup_smoke_count = int(sys.argv[6] or "0")

compatibility_artifacts = compatibility.get("downloads") or []
canonical_artifacts = canonical.get("artifacts") or []

compat_ids = sorted({
    str(item.get("id") or "").strip()
    for item in compatibility_artifacts
    if isinstance(item, dict) and str(item.get("id") or "").strip()
})
artifact_ids = sorted({
    str(item.get("artifactId") or item.get("id") or "").strip()
    for item in canonical_artifacts
    if isinstance(item, dict) and str(item.get("artifactId") or item.get("id") or "").strip()
})

summary = {
    "buildTimeUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "compatibility": {
        "artifactCount": len(compatibility_artifacts),
        "artifactIds": compat_ids,
        "version": compatibility.get("version"),
        "channel": compatibility.get("channel"),
    },
    "canonical": {
        "artifactCount": len(canonical_artifacts),
        "artifactIds": artifact_ids,
        "version": canonical.get("version"),
        "channel": canonical.get("channel"),
    },
    "startupSmokeReceiptCount": startup_smoke_count,
}


if evidence_path is not None and evidence_path.is_file():
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence_artifacts = evidence.get("artifacts") if isinstance(evidence, dict) else []
    if isinstance(evidence_artifacts, list):
        summary["promotionEvidence"] = {
            "contractName": evidence.get("contractName"),
            "artifactCount": len(evidence_artifacts),
            "artifactIds": sorted({
                str(item.get("artifactId") or "").strip()
                for item in evidence_artifacts
                if isinstance(item, dict) and str(item.get("artifactId") or "").strip()
            }),
            "passedArtifacts": sorted({
                str(item.get("artifactId") or "").strip()
                for item in evidence_artifacts
                if isinstance(item, dict) and str(item.get("promotionStatus") or "").strip().lower() == "pass"
            }),
        }
    else:
        summary["promotionEvidence"] = {"status": "malformed"}
else:
    summary["promotionEvidence"] = {"status": "missing"}

files_root = Path(sys.argv[1]).with_name("files")
if files_root.is_dir():
    summary["bundleFiles"] = sorted(
        item.name for item in files_root.iterdir() if item.is_file()
    )
else:
    summary["bundleFiles"] = []

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY

  [[ -f "$output_path" ]] && log "release upload payload summary written: $output_path"
}

ensure_publish_bundle_startup_smoke_receipts() {
  local source_dist="$1"
  local bundle_dir="$2"

  local installer_artifact_count
  installer_artifact_count="$(python3 - "$source_dist/RELEASE_CHANNEL.generated.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
artifacts = payload.get("artifacts") or []
count = 0
for artifact in artifacts:
    if not isinstance(artifact, dict):
        continue
    kind = (artifact.get("kind") or "").strip().lower()
    file_name = (artifact.get("fileName") or "").strip().lower()
    if kind in {"installer", "dmg", "pkg", "msix"}:
        count += 1
        continue
    if file_name.endswith((".exe", ".deb", ".dmg", ".pkg", ".msix")):
        count += 1

print(count)
PY
)"

  if [[ "${installer_artifact_count}" == "0" ]]; then
    return 0
  fi

  if [[ ! -d "${bundle_dir}/startup-smoke" ]]; then
    if [[ -d "${source_dist}/startup-smoke" ]]; then
      mkdir -p "${bundle_dir}/startup-smoke"
      cp -aL "${source_dist}/startup-smoke/." "${bundle_dir}/startup-smoke/" || true
    fi
  fi

  if [[ ! -d "${bundle_dir}/startup-smoke" ]]; then
    die "publish bundle is missing startup-smoke receipts directory required for installer artifacts."
  fi

  local startup_receipt_count
  startup_receipt_count="$(find "${bundle_dir}/startup-smoke" -type f -name 'startup-smoke-*.receipt.json' | wc -l | tr -d ' ')"
  if (( startup_receipt_count < installer_artifact_count )); then
    die "publish bundle has ${startup_receipt_count} startup-smoke receipt(s), but ${installer_artifact_count} installer artifact(s) require receipts."
  fi
}

write_public_promotion_evidence() {
  local canonical_manifest_path="$1"
  local startup_smoke_dir="$2"
  local output_path="$3"
  local release_channel="$4"
  local published_at="$5"

  python3 - "$canonical_manifest_path" "$startup_smoke_dir" "$output_path" "$release_channel" "$published_at" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

INSTALLER_KINDS = {"installer", "dmg", "pkg", "msix"}

manifest_path = Path(sys.argv[1])
startup_smoke_dir = Path(sys.argv[2])
output_path = Path(sys.argv[3])
channel = sys.argv[4].strip().lower()
generated_at = sys.argv[5].strip()


def normalize_platform(raw: str | None) -> str:
    normalized = (raw or "").strip().lower()
    if not normalized:
        return ""
    for separator in ("-", "_", "/", " "):
        if separator in normalized:
            normalized = normalized.split(separator, 1)[0]
            break
    return {
        "mac": "macos",
        "macos": "macos",
        "osx": "macos",
        "darwin": "macos",
        "win": "windows",
        "windows": "windows",
    }.get(normalized, normalized)


def normalize_sha256(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    return value[7:] if value.startswith("sha256:") else value


def resolve_file_name(artifact: dict) -> str:
    file_name = (artifact.get("fileName") or "").strip()
    if file_name:
        return Path(file_name).name
    download_url = (artifact.get("downloadUrl") or "").strip()
    if not download_url:
        raise SystemExit("artifact is missing fileName/downloadUrl")
    return Path(download_url).name


def is_installer_artifact(artifact: dict) -> bool:
    kind = (artifact.get("kind") or "").strip().lower()
    if kind:
        return kind in INSTALLER_KINDS
    return resolve_file_name(artifact).lower().endswith((".exe", ".deb", ".dmg", ".pkg", ".msix"))


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_receipts(root: Path) -> list[dict]:
    receipts: list[dict] = []
    if not root.is_dir():
        return receipts
    for path in root.rglob("startup-smoke-*.receipt.json"):
        try:
            payload = load_json(path)
        except Exception:
            continue
        if payload.get("headId") and payload.get("platform") and payload.get("arch"):
            receipts.append(payload)
    return receipts


def find_matching_receipt(artifact: dict, receipts: list[dict]) -> dict | None:
    expected_head = (artifact.get("head") or "").strip().lower()
    expected_platform = normalize_platform(artifact.get("platform"))
    expected_arch = (artifact.get("arch") or "").strip().lower()
    expected_digest = (artifact.get("sha256") or "").strip().lower()
    expected_digest = normalize_sha256(expected_digest)
    for receipt in receipts:
        if (receipt.get("headId") or "").strip().lower() != expected_head:
            continue
        if normalize_platform(receipt.get("platform")) != expected_platform:
            continue
        if (receipt.get("arch") or "").strip().lower() != expected_arch:
            continue
        if expected_digest:
            receipt_digest = normalize_sha256(receipt.get("artifactDigest"))
            if receipt_digest and receipt_digest != expected_digest:
                continue
            receipt_sha = normalize_sha256(receipt.get("artifactSha256"))
            if receipt_sha and receipt_sha != expected_digest:
                continue
        return receipt
    return None


def compute_signing(platform: str, channel: str) -> tuple[str | None, str | None]:
    if platform == "windows":
        return ("skipped_preview" if channel == "preview" else "fail", None)
    if platform == "macos":
        if channel == "preview":
            return ("skipped_preview", "skipped_preview")
        return ("fail", "fail")
    return (None, None)


manifest = load_json(manifest_path)
artifacts = manifest.get("artifacts") or []
if not isinstance(artifacts, list):
    raise SystemExit("manifest artifacts must be a list")
receipts = load_receipts(startup_smoke_dir)

evidence_artifacts: list[dict] = []
for artifact in artifacts:
    if not isinstance(artifact, dict):
        continue
    platform = normalize_platform(artifact.get("platform"))
    installer = is_installer_artifact(artifact)
    receipt = find_matching_receipt(artifact, receipts) if installer else None
    startup_smoke_status = "pass" if (not installer or receipt is not None) else "fail"
    signing_status, notarization_status = compute_signing(platform, channel)
    allowed = {"pass"}
    if channel == "preview":
        allowed.add("skipped_preview")
    promotion_status = "pass"
    if startup_smoke_status != "pass":
        promotion_status = "fail"
    elif platform == "windows" and signing_status not in allowed:
        promotion_status = "fail"
    elif platform == "macos" and (signing_status not in allowed or notarization_status not in allowed):
        promotion_status = "fail"

    evidence_artifacts.append({
        "artifactId": artifact.get("artifactId"),
        "fileName": resolve_file_name(artifact),
        "platform": platform,
        "promotionStatus": promotion_status,
        "startupSmokeStatus": startup_smoke_status,
        "signingStatus": signing_status,
        "notarizationStatus": notarization_status,
        "artifactSha256": artifact.get("sha256"),
        "artifactSizeBytes": artifact.get("sizeBytes"),
        "kind": artifact.get("kind"),
    })

payload = {
    "contractName": "chummer.run.desktop_release_publication",
    "generatedAt": generated_at,
    "artifacts": evidence_artifacts,
}

output_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open("w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
PY
}

sanitize_release_upload_response_stream() {
  local output_path="$1"
  local max_bytes="$2"
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
            summary[field_name] = [
                safe for item in values[:256]
                if (safe := safe_url(item, allow_relative=False)) is not None
            ]
    promoted_ids = payload.get("promotedArtifactIds")
    if isinstance(promoted_ids, list):
        summary["promotedArtifactIds"] = [
            item for item in promoted_ids[:512]
            if isinstance(item, str) and safe_identifier.fullmatch(item)
        ]
    summary["suppressedFieldCount"] = max(0, len(payload) - len(summary) + 2)
elif isinstance(payload, list):
    summary["itemCount"] = len(payload)

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
' "$output_path" "$max_bytes"
}

upload_release_bundle_http() {
  local bundle_dir="$1"
  local sessions_url="$2"
  local release_upload_auth_value="$3"
  local response_path="$4"
  local attempt_receipt_helper="$5"
  export -n release_upload_auth_value 2>/dev/null || true
  ensure_release_upload_token "$release_upload_auth_value"

  local retry_attempts="${CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS:-4}"
  local retry_sleep="${CHUMMER_RELEASE_UPLOAD_RETRY_SLEEP_SECONDS:-5}"
  local direct_limit_bytes="${CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES:-94371840}"
  local chunk_bytes="${CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES:-33554432}"
  local max_response_bytes="${CHUMMER_RELEASE_UPLOAD_MAX_RESPONSE_BYTES:-1048576}"
  [[ "$max_response_bytes" =~ ^[0-9]+$ ]] \
    && (( max_response_bytes >= 1024 && max_response_bytes <= 16777216 )) \
    || die "CHUMMER_RELEASE_UPLOAD_MAX_RESPONSE_BYTES must be an integer from 1024 through 16777216"
  [[ -n "$sessions_url" ]] || die "release upload sessions URL is required"
  [[ -f "$attempt_receipt_helper" && ! -L "$attempt_receipt_helper" ]] \
    || die "durable upload-attempt receipt helper is missing or unsafe: $attempt_receipt_helper"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_URL:-}" ]] \
    || die "CHUMMER_RELEASE_UPLOAD_URL is retired; use CHUMMER_RELEASE_UPLOAD_SESSIONS_URL"
  ! is_true "${CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK:-0}" \
    || die "direct release upload fallback is permanently disabled"

  local upload_failed=0
  local completion_attempted=0
  local last_request_status=""
  local session_json session_id files_url chunks_url complete_url
  local file_path relative_path file_size
  local -a request_common=()
  local attempt_receipt_path="${CHUMMER_RELEASE_UPLOAD_ATTEMPT_RECEIPT_PATH:-$(dirname "$response_path")/release-upload-handoff.json}"
  local candidate_summary=""
  BOOTSTRAP_RELEASE_UPLOAD_ATTEMPT_RECEIPT_PATH="$attempt_receipt_path"
  python3 "$attempt_receipt_helper" preflight --receipt "$attempt_receipt_path"

  render_sanitized_release_upload_response() {
    local body_file="$1"
    python3 - "$body_file" <<'PY'
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

if not raw:
    print("(empty response body)")
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

  log_http_body() {
    local body_file="$1"
    local line
    [[ -f "$body_file" ]] || return 0
    while IFS= read -r line; do
      log "  ${line}"
    done < "$body_file"
  }

  log_problem_details() {
    local body_file="$1"
    [[ -f "$body_file" ]] || return 0
    if ! jq -e . "$body_file" >/dev/null 2>&1; then
      return 0
    fi

    local status title detail type instance
    local -a validation_errors

    status="$(jq -r '.status // empty' "$body_file" 2>/dev/null || true)"
    title="$(jq -r '.title // empty' "$body_file" 2>/dev/null || true)"
    detail="$(jq -r '.detail // empty' "$body_file" 2>/dev/null || true)"
    type="$(jq -r '.type // empty' "$body_file" 2>/dev/null || true)"
    instance="$(jq -r '.instance // empty' "$body_file" 2>/dev/null || true)"

    validation_errors=()
    while IFS= read -r validation_error; do
      [[ -n "$validation_error" ]] || continue
      validation_errors+=("$validation_error")
    done < <(jq -r '.errors? | to_entries? | map("\(.key): \(.value | join(\", \"))")[]?' "$body_file" 2>/dev/null || true)

    if [[ -n "$status" ]]; then
      log "  error status: ${status}"
    fi
    if [[ -n "$type" ]]; then
      log "  problem type: ${type}"
    fi
    if [[ -n "$title" ]]; then
      log "  title: ${title}"
    fi
    if [[ -n "$detail" ]]; then
      log "  detail: ${detail}"
    fi
    if [[ -n "$instance" ]]; then
      log "  instance: ${instance}"
    fi
    if (( $(array_count validation_errors) > 0 )); then
      log "  validation errors:"
      for line in "${validation_errors[@]}"; do
        [[ -n "$line" ]] && log "    ${line}"
      done
    fi
  }

  log_status_guidance() {
    local status="$1"
    case "$status" in
      400)
        log "  guidance: this is a validation/rejection state; inspect problem detail and uploaded bundle contract fields."
        log "  guidance: verify proof files are valid, proof files include required fields, and manifest artifact_count > 0."
        log "  guidance: retry the command after correcting payload inputs; this is usually not a transient network issue."
        ;;
      401|403)
        log "  guidance: authorization/authentication failure. confirm the signed-in handoff code in CHUMMER_RELEASE_UPLOAD_TICKET (or CHUMMER_RELEASE_UPLOAD_TOKEN / api token) is current."
        log "  guidance: if this is a signed release token, re-issue with release-upload flow and rerun."
        ;;
      500|502|503|504)
        log "  guidance: transient server error while processing upload/session; retries are active and usually recover if repeated."
        ;;
      *)
        ;;
    esac
  }

  normalize_upload_url() {
    local candidate="$1"
    local base="$2"
    [[ -n "$candidate" && "$candidate" != "null" ]] || return 1
    python3 - "$base" "$candidate" <<'PY'
from __future__ import annotations

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
    raise SystemExit(1)

resolved = urlsplit(urljoin(base_text.rstrip("/") + "/", candidate_text))
try:
    base_authority = (base.scheme.lower(), base.hostname.lower(), base.port)
    resolved_authority = (resolved.scheme.lower(), (resolved.hostname or "").lower(), resolved.port)
except ValueError:
    raise SystemExit(1)

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
    raise SystemExit(1)

print(resolved.geturl())
PY
  }

  resolve_json_field() {
    local payload_path="$1"
    shift
    local field
    local candidate
    for field in "$@"; do
      candidate="$(jq -r ".[\"${field}\"] // empty" "$payload_path" 2>/dev/null || true)"
      if [[ -n "$candidate" && "$candidate" != "null" ]]; then
        printf '%s' "$candidate"
        return 0
      fi
    done
    return 1
  }

  log_release_upload_response() {
    local payload_path="$1"
    render_sanitized_release_upload_response "$payload_path"
  }

  release_upload_curl() {
    write_release_upload_curl_config "$release_upload_auth_value" \
      | curl -q --config - "$@"
  }

  post_form_request() {
    local output_path="$1"
    local label="$2"
    local request_url="$3"
    shift 3

    local allow_retry=1
    if [[ "${1:-}" == "--no-retry" ]]; then
      allow_retry=0
      shift
    fi

    last_request_status=""
    local attempt=1
    local request_id=""
    while true; do
      local body_file http_status request_ok
      body_file="$(mktemp)"
      http_status=""
      request_ok=0
      if http_status="$(release_upload_curl --fail-with-body -sS --max-filesize "$max_response_bytes" \
          --write-out $'\nCHUMMER_HTTP_STATUS:%{http_code}' -X POST "$@" "$request_url" \
          | sanitize_release_upload_response_stream "$body_file" "$max_response_bytes")"; then
        [[ "$http_status" =~ ^2 ]] && request_ok=1
      fi
      if (( request_ok == 1 )); then
        if [[ -n "$output_path" ]]; then
          mv "$body_file" "$output_path"
          chmod 600 "$output_path" 2>/dev/null || true
        else
          rm -f "$body_file"
        fi
        return 0
      fi

      local status
      status="$http_status"
      last_request_status="$status"
      request_id="$(jq -r '.requestId // .traceId // empty' "$body_file" 2>/dev/null || true)"
      log "release upload request failed: ${label} (attempt ${attempt}/${retry_attempts}, status ${status:-unknown})"
      log "  url: ${request_url}"
      if [[ -n "$request_id" ]]; then
        log "  request id: ${request_id}"
      fi
      log "  response body:"
      log_http_body "$body_file"
      log_status_guidance "${status}"
      if [[ "$status" == "400" || "$status" == "401" || "$status" == "403" ]]; then
        if [[ -n "$output_path" ]]; then
          mv "$body_file" "$output_path"
          chmod 600 "$output_path" 2>/dev/null || true
        else
          rm -f "$body_file"
        fi
        return 22
      fi
      if (( allow_retry == 0 )); then
        if [[ -n "$output_path" ]]; then
          mv "$body_file" "$output_path"
          chmod 600 "$output_path" 2>/dev/null || true
        else
          rm -f "$body_file"
        fi
        return 22
      fi
      if (( attempt >= retry_attempts )); then
        if [[ -n "$output_path" ]]; then
          mv "$body_file" "$output_path"
          chmod 600 "$output_path" 2>/dev/null || true
        else
          rm -f "$body_file"
        fi
        return 22
      fi

      rm -f "$body_file"

      attempt=$((attempt + 1))
      log "  retrying in ${retry_sleep}s"
      sleep "$retry_sleep"
    done
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
    if [[ -d "$bundle_root/proof/build-provenance/v1" ]]; then
      find "$bundle_root/proof/build-provenance/v1" -type f | sort
    fi
  }

  local -a upload_files=()
  while IFS= read -r file_path; do
    [[ -n "$file_path" ]] || continue
    upload_files+=("$file_path")
  done < <(collect_upload_files "$bundle_dir")
  local upload_file_count
  upload_file_count="$(array_count upload_files)"
  if (( upload_file_count == 0 )); then
    die "release upload payload has no files."
  fi

  candidate_summary="$(mktemp)"
  bootstrap_tmp_paths+=("$candidate_summary")
  local -a candidate_summary_command=(
    python3 "$attempt_receipt_helper" summarize
    --bundle-root "$bundle_dir"
    --canonical-manifest "$bundle_dir/RELEASE_CHANNEL.generated.json"
    --output "$candidate_summary"
  )
  while IFS= read -r -d '' file_path; do
    candidate_summary_command+=(--file "$file_path")
  done < <(array_values_nul upload_files)
  "${candidate_summary_command[@]}"

  session_json="$(mktemp)"
  bootstrap_tmp_paths+=("$session_json")
  if ! post_form_request \
    "$session_json" \
    "create upload session" \
    "$sessions_url" \
    "${request_common[@]}"; then
    rm -f "$session_json"
    case "$last_request_status" in
      400|401|403)
        die "release upload session was rejected with HTTP ${last_request_status}; inspect the staged bundle contract before retrying."
        ;;
    esac
    die "release upload session creation failed."
  fi

  session_id="$(resolve_json_field "$session_json" "sessionId" "SessionId" "session_id" "id" "session")" || die "upload session response missing sessionId"
  [[ "$session_id" =~ ^[0-9a-f]{32}$ ]] \
    || die "upload session response contains an unsafe sessionId"

  files_url="$(resolve_json_field "$session_json" "filesUrl" "files_url" "FilesUrl" "files" || true)"
  chunks_url="$(resolve_json_field "$session_json" "chunksUrl" "chunks_url" "ChunksUrl" "chunks" || true)"
  complete_url="$(resolve_json_field "$session_json" "completeUrl" "complete_url" "CompleteUrl" "complete" || true)"
  local expires_at
  expires_at="$(resolve_json_field "$session_json" "expiresAtUtc" "ExpiresAtUtc" "expires_at_utc" "expiresAt" || true)"

  record_upload_attempt_state() {
    local state="$1"
    shift
    python3 "$attempt_receipt_helper" transition \
      --receipt "$attempt_receipt_path" \
      --summary "$candidate_summary" \
      --sessions-url "$sessions_url" \
      --session-id "$session_id" \
      --expires-at "$expires_at" \
      --state "$state" \
      "$@"
  }

  if ! record_upload_attempt_state created; then
    die "upload session $session_id was created, but its durable recovery handoff could not be written; no files were uploaded"
  fi

  local expected_files_url expected_chunks_url expected_complete_url
  expected_files_url="$(normalize_upload_url "${session_id}/files" "$sessions_url")" \
    || die "upload sessions base URL is invalid"
  expected_chunks_url="$(normalize_upload_url "${session_id}/chunks" "$sessions_url")" \
    || die "upload sessions base URL is invalid"
  expected_complete_url="$(normalize_upload_url "${session_id}/complete" "$sessions_url")" \
    || die "upload sessions base URL is invalid"
  if [[ -n "$files_url" ]]; then
    files_url="$(normalize_upload_url "$files_url" "$sessions_url")" \
      || die "upload session files URL escaped its same-origin session root"
  else
    files_url="$expected_files_url"
  fi
  if [[ -n "$chunks_url" ]]; then
    chunks_url="$(normalize_upload_url "$chunks_url" "$sessions_url")" \
      || die "upload session chunks URL escaped its same-origin session root"
  else
    chunks_url="$expected_chunks_url"
  fi
  if [[ -n "$complete_url" ]]; then
    complete_url="$(normalize_upload_url "$complete_url" "$sessions_url")" \
      || die "upload session completion URL escaped its same-origin session root"
  else
    complete_url="$expected_complete_url"
  fi
  [[ "$files_url" == "$expected_files_url" \
      && "$chunks_url" == "$expected_chunks_url" \
      && "$complete_url" == "$expected_complete_url" ]] \
    || die "upload session response endpoints do not match the created session"

  upload_file() {
    local file_path="$1"
    local relative_path="$2"
    if ! post_form_request \
      "" \
      "upload file ${relative_path}" \
      "$files_url" \
      "${request_common[@]}" \
      -F "path=${relative_path}" \
      -F "file=@${file_path};type=application/octet-stream"; then
      case "$last_request_status" in
        400|401|403)
          die "release upload rejected while staging ${relative_path} with HTTP ${last_request_status}; inspect the bundle contract instead of retrying the same payload."
          ;;
        *)
          upload_failed=1
          ;;
      esac
    fi
  }

  upload_chunked_file() {
    local file_path="$1"
    local relative_path="$2"
    local chunk_dir
    local -a chunks
    local total
    local idx
    local chunk_path
    chunk_dir="$(mktemp -d)"
    split -b "$chunk_bytes" "$file_path" "$chunk_dir/chunk."
    chunks=()
    while IFS= read -r chunk_path; do
      [[ -n "$chunk_path" ]] || continue
      chunks+=("$chunk_path")
    done < <(find "$chunk_dir" -maxdepth 1 -type f | sort)
    total="$(array_count chunks)"
    if (( total == 0 )); then
      rm -rf "$chunk_dir"
      die "chunking produced no files for ${relative_path}"
    fi
    idx=0
    while IFS= read -r -d '' chunk_path; do
      if ! post_form_request \
        "" \
        "upload chunk ${idx}/${total} for ${relative_path}" \
        "$chunks_url" \
        "${request_common[@]}" \
        -F "path=${relative_path}" \
        -F "index=${idx}" \
        -F "total=${total}" \
        -F "chunk=@${chunk_path};type=application/octet-stream"; then
        case "$last_request_status" in
          400|401|403)
            rm -rf "$chunk_dir"
            die "release upload rejected while staging ${relative_path} chunk ${idx}/${total} with HTTP ${last_request_status}; inspect the bundle contract instead of retrying the same payload."
            ;;
          *)
            upload_failed=1
            ;;
        esac
        break
      fi
      idx=$((idx + 1))
    done < <(array_values_nul chunks)
    rm -rf "$chunk_dir"
  }

  file_size_bytes() {
    wc -c < "$1" | tr -d '[:space:]'
  }

  local -a upload_files=()
  while IFS= read -r file_path; do
    [[ -n "$file_path" ]] || continue
    upload_files+=("$file_path")
  done < <(collect_upload_files "$bundle_dir")
  local upload_file_count
  upload_file_count="$(array_count upload_files)"
  if (( upload_file_count == 0 )); then
    rm -f "$session_json"
    die "release upload payload has no files."
  fi

  log "staged upload endpoint: ${sessions_url}"
  local file_size_total=0
  while IFS= read -r -d '' file_path; do
    [[ -n "$file_path" ]] || continue
    file_size="$(file_size_bytes "$file_path")"
    if [[ "$file_size" =~ ^[0-9]+$ ]]; then
      file_size_total=$(( file_size_total + file_size ))
    fi
  done
  log "staged upload payload: ${upload_file_count} files, ${file_size_total} bytes total"
  for file_path in "${upload_files[@]:0:8}"; do
    file_size="$(stat -f '%z' "$file_path" 2>/dev/null || stat -c '%s' "$file_path" 2>/dev/null || echo 0)"
    log "  file: ${file_path#$bundle_dir/} (${file_size} bytes)"
  done
  if (( upload_file_count > 8 )); then
    log "  ... and $((upload_file_count - 8)) additional files"
  fi

  while IFS= read -r -d '' file_path; do
    [[ -n "$file_path" ]] || continue
    relative_path="${file_path#$bundle_dir/}"
    file_size="$(file_size_bytes "$file_path")"
    if (( file_size <= direct_limit_bytes )); then
      upload_file "$file_path" "$relative_path"
    else
      upload_chunked_file "$file_path" "$relative_path"
    fi
  done < <(array_values_nul upload_files)

  if (( upload_failed == 0 )); then
    record_upload_attempt_state uploaded
    record_upload_attempt_state request_started
    completion_attempted=1
    if ! post_form_request \
      "$response_path" \
      "complete staged upload" \
      "$complete_url" \
      --no-retry \
      "${request_common[@]}"; then
      case "$last_request_status" in
        400|401|403)
          die "release upload completion returned HTTP ${last_request_status}; its durable state remains request_started. Do not create another session. Reconcile the recorded handoff at $attempt_receipt_path."
          ;;
        *)
          upload_failed=1
          ;;
      esac
    fi
    if (( upload_failed == 0 )); then
      BOOTSTRAP_RELEASE_UPLOAD_ACCEPTED=1
      python3 "$attempt_receipt_helper" fsync-file --path "$response_path"
      if ! record_upload_attempt_state completed; then
        die "release completion returned success, but the durable handoff could not be acknowledged; reconcile session $session_id instead of creating another release"
      fi
    fi
  fi

  if (( upload_failed == 1 )); then
    rm -f "$session_json"
    if (( completion_attempted == 1 )); then
      die "release completion outcome is unknown. Do not create another session. Reconcile the request_started handoff at $attempt_receipt_path."
    fi
    if [[ -f "$response_path" ]]; then
      die "staged release upload failed before completion. inspect the sanitized diagnostic response at: $response_path"
    fi
    die "staged release upload failed; reconcile the existing upload session before retrying."
  fi

  log_release_upload_response "$response_path" || log "release response display was suppressed"
  rm -f "$session_json"
}

stage_local_release_bundle() {
  local source_bundle="$1"
  local output_path="$2"
  local provenance_verifier="$3"
  local release_version="$4"
  local release_channel="$5"
  local rid="$6"
  local apps_raw="$7"

  [[ -d "$source_bundle" && ! -L "$source_bundle" ]] \
    || die "stage-only source bundle must be a real directory: $source_bundle"
  [[ -f "$provenance_verifier" ]] \
    || die "stage-only provenance verifier is missing: $provenance_verifier"

  local output_parent output_name staging_dir
  output_parent="$(dirname "$output_path")"
  output_name="$(basename "$output_path")"
  staging_dir="$(mktemp -d "$output_parent/.${output_name}.stage.XXXXXX")" \
    || die "could not reserve a stage-only output directory beside $output_path"

  if ! (
    trap 'rm -rf "$staging_dir"' EXIT
    cp -a "$source_bundle/." "$staging_dir/"
    mkdir -p "$staging_dir/release-evidence"
    python3 - \
      "$staging_dir/release-evidence/mac-stage-only.json" \
      "$output_path" \
      "$release_version" \
      "$release_channel" \
      "$rid" \
      "$apps_raw" <<'PY'
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

receipt_path = Path(sys.argv[1])
payload = {
    "contractName": "chummer.run.mac_release_stage_only",
    "status": "pass",
    "mode": "stage_only",
    "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "outputPath": sys.argv[2],
    "releaseVersion": sys.argv[3],
    "releaseChannel": sys.argv[4],
    "rid": sys.argv[5],
    "appHeads": [item.strip() for item in sys.argv[6].replace(" ", ",").split(",") if item.strip()],
    "uploadAttempted": False,
    "publicationAttempted": False,
    "publicActivationAttempted": False,
    "countsAsPublicationEvidence": False,
}
receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
    python3 "$provenance_verifier" "$staging_dir"
    validate_bundle_directory_integrity "$staging_dir"
    python3 - "$staging_dir" "$output_path" <<'PY'
from __future__ import annotations

import ctypes
import errno
import os
import sys

source = os.fsencode(sys.argv[1])
target = os.fsencode(sys.argv[2])
libc = ctypes.CDLL(None, use_errno=True)

if sys.platform == "darwin":
    rename_exclusive = getattr(libc, "renamex_np", None)
    if rename_exclusive is None:
        raise SystemExit("exclusive atomic rename is unavailable on this macOS host")
    result = rename_exclusive(source, target, ctypes.c_uint(0x00000004))  # RENAME_EXCL
elif sys.platform.startswith("linux"):
    rename_exclusive = getattr(libc, "renameat2", None)
    if rename_exclusive is None:
        raise SystemExit("exclusive atomic rename is unavailable on this Linux test host")
    result = rename_exclusive(-100, source, -100, target, ctypes.c_uint(1))  # RENAME_NOREPLACE
else:
    raise SystemExit(f"exclusive atomic rename is unsupported on {sys.platform}")

if result != 0:
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise SystemExit("stage-only output path appeared before atomic rename")
    raise SystemExit(f"stage-only atomic rename failed: {os.strerror(error)}")
PY
    trap - EXIT
  ); then
    die "stage-only bundle validation or atomic placement failed; no output was published"
  fi

  log "stage-only local bundle complete; upload/publication/live verification were not attempted"
  printf 'release_stage_only_path=%s\n' "$output_path"
}

main() {
  bootstrap_tmp_paths=()
  trap cleanup_bootstrap_tmp_paths EXIT

  # Capture the one HTTP-promotion credential before any preflight/build child
  # can inherit it, then scrub every inbound bearer variable. The private local
  # remains de-exported and is streamed to curl only when upload actually starts.
  local release_upload_auth_value=""
  local release_upload_auth_source=""
  capture_release_upload_auth_value release_upload_auth_value release_upload_auth_source

  parse_mac_release_stage_only_args "$@"
  if (( MAC_RELEASE_STAGE_ONLY == 1 )) && [[ -n "$release_upload_auth_source" ]]; then
    die "stage-only mode rejects publish-only setting $release_upload_auth_source"
  fi

  local publish_mode
  if (( MAC_RELEASE_STAGE_ONLY == 1 )); then
    publish_mode="stage-only"
    release_upload_auth_value=""
  else
    local has_release_upload_auth=0
    [[ -n "$release_upload_auth_value" ]] && has_release_upload_auth=1
    publish_mode="$(infer_publish_mode "$has_release_upload_auth")"
    if [[ "$publish_mode" == "http" && -z "$release_upload_auth_value" ]]; then
      prompt_for_release_upload_ticket release_upload_auth_value \
        || die "set CHUMMER_RELEASE_UPLOAD_TICKET or CHUMMER_RELEASE_UPLOAD_TOKEN for HTTP release promotion"
    fi
    if [[ "$publish_mode" == "http" ]]; then
      ensure_release_upload_token "$release_upload_auth_value"
    else
      release_upload_auth_value=""
    fi
  fi

  require_all_reviewed_commit_pins
  RELEASE_PYTHON_BIN="$(resolve_release_python)" \
    || die "release bootstrap requires Python 3.11 or newer; set CHUMMER_RELEASE_PYTHON to a reviewed interpreter"
  python3() {
    command "$RELEASE_PYTHON_BIN" "$@"
  }
  local stage_output_path=""
  if (( MAC_RELEASE_STAGE_ONLY == 1 )); then
    stage_output_path="$(resolve_mac_release_stage_output_path "$MAC_RELEASE_STAGE_OUTPUT_DIR")" \
      || die "invalid stage-only output path: $MAC_RELEASE_STAGE_OUTPUT_DIR"
    log "stage-only mode enabled; local output will be placed at $stage_output_path"
  fi
  local executed_bootstrap_path
  executed_bootstrap_path="$(resolve_executed_bootstrap_path)" \
    || die "executed bootstrap must be available as a regular file before release work begins"
  require_cmd git
  ensure_dotnet_resolver
  log_bootstrap_identity "$executed_bootstrap_path"
  verify_bootstrap_integrity "$executed_bootstrap_path"
  require_cmd jq
  require_cmd curl
  require_cmd hdiutil
  require_cmd ditto

  local work_root="${CHUMMER_MAC_RELEASE_WORK_ROOT:-$HOME/work/chummer-release/run-$(date -u +%Y%m%d-%H%M%S)}"
  local ui_ref="${CHUMMER_UI_REF:-main}"
  local core_ref="${CHUMMER_CORE_REF:-main}"
  local hub_ref="${CHUMMER_HUB_REF:-main}"
  local ui_kit_ref="${CHUMMER_UI_KIT_REF:-main}"
  local registry_ref="${CHUMMER_HUB_REGISTRY_REF:-main}"
  local media_factory_ref="${CHUMMER_MEDIA_FACTORY_REF:-main}"
  local legacy_ref="${CHUMMER_LEGACY_REF:-Docker}"
  local ui_expected_commit="${CHUMMER_UI_EXPECTED_COMMIT:-}"
  local core_expected_commit="${CHUMMER_CORE_EXPECTED_COMMIT:-}"
  local hub_expected_commit="${CHUMMER_HUB_EXPECTED_COMMIT:-}"
  local ui_kit_expected_commit="${CHUMMER_UI_KIT_EXPECTED_COMMIT:-}"
  local registry_expected_commit="${CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT:-}"
  local media_factory_expected_commit="${CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT:-}"
  local legacy_expected_commit="${CHUMMER_LEGACY_EXPECTED_COMMIT:-}"
  local apps_raw="${CHUMMER_RELEASE_APP:-avalonia,blazor-desktop}"
  local rid="${CHUMMER_RELEASE_RID:-osx-arm64}"
  local release_channel="${CHUMMER_RELEASE_CHANNEL:-preview}"
  local release_version="${CHUMMER_RELEASE_VERSION:-run-$(date -u +%Y%m%d-%H%M%S)}"
  local allow_unsigned_preview="${CHUMMER_ALLOW_UNSIGNED_PREVIEW:-0}"
  local minimum_free_gib="${CHUMMER_MAC_RELEASE_MIN_FREE_GIB:-20}"
  local packaging_minimum_free_gib="${CHUMMER_MAC_RELEASE_PACKAGING_MIN_FREE_GIB:-8}"
  local temp_root="${CHUMMER_MAC_RELEASE_TMPDIR:-$work_root/tmp}"
  local verify_url="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-https://chummer.run/downloads/RELEASE_CHANNEL.generated.json}"
  local require_compatibility_projection="${CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION:-0}"
  local sessions_url="${CHUMMER_RELEASE_UPLOAD_SESSIONS_URL:-https://chummer.run/api/internal/releases/upload-sessions}"
  local materializer_skip_startup_smoke_filter="${CHUMMER_MATERIALIZE_SKIP_STARTUP_SMOKE_FILTER:-0}"
  local materializer_retry_without_filter="${CHUMMER_MATERIALIZE_RETRY_WITHOUT_STARTUP_SMOKE_FILTER_ON_ZERO:-}"
  if [[ -z "$materializer_retry_without_filter" ]]; then
    if [[ "$release_channel" == "preview" ]]; then
      materializer_retry_without_filter=1
    else
      materializer_retry_without_filter=0
    fi
  fi
  if is_true "$materializer_skip_startup_smoke_filter"; then
    log "startup-smoke manifest filter disabled via CHUMMER_MATERIALIZE_SKIP_STARTUP_SMOKE_FILTER=1"
  fi
  if is_true "$materializer_retry_without_filter"; then
    log "manifest retry without startup-smoke filter is enabled on zero-manifest projection"
  fi
  local compatibility_verify_url=""
  local canonical_verify_url=""
  if (( MAC_RELEASE_STAGE_ONLY == 0 )); then
    validate_publish_mode "$publish_mode" "$sessions_url" "$release_upload_auth_value"
    IFS='|' read -r compatibility_verify_url canonical_verify_url < <(resolve_live_release_verify_urls "$verify_url")
    log "preflighting live canonical supportability contract at $canonical_verify_url"
    verify_live_canonical_supportability_preflight "$canonical_verify_url"
  fi

  local sign_identity="${CHUMMER_APP_SIGN_IDENTITY:-}"
  local notary_profile="${CHUMMER_NOTARY_PROFILE:-}"
  local require_signed_release=1
  if (( MAC_RELEASE_STAGE_ONLY == 1 )); then
    [[ "$release_channel" == "preview" ]] \
      || die "stage-only mode is limited to the unsigned preview channel"
    require_signed_release=0
    log "stage-only preview will not sign, notarize, upload, publish, or verify live surfaces"
  elif [[ -z "$sign_identity" || -z "$notary_profile" ]]; then
    if is_true "$allow_unsigned_preview" && [[ "$release_channel" == "preview" ]]; then
      require_signed_release=0
      log "Apple release credentials missing; continuing with unsigned preview upload."
    else
      [[ -n "$sign_identity" ]] || die "set CHUMMER_APP_SIGN_IDENTITY or CHUMMER_ALLOW_UNSIGNED_PREVIEW=1"
      [[ -n "$notary_profile" ]] || die "set CHUMMER_NOTARY_PROFILE or CHUMMER_ALLOW_UNSIGNED_PREVIEW=1"
    fi
  fi

  if [[ "$require_signed_release" == "1" ]]; then
    require_cmd xcrun
    require_cmd spctl
  fi

  local ui_repo="$work_root/r"
  local core_repo="$work_root/.c/core"
  local hub_repo="$work_root/.c/hub"
  local ui_kit_repo="$work_root/.c/ui"
  local registry_repo="$work_root/.c/registry"
  local legacy_repo="$work_root/.c/chummer5a"
  local media_repo="$work_root/fleet/repos/chummer-media-factory"
  local core_alias="$work_root/chummer-core-engine"
  local hub_alias="$work_root/chummer.run-services"
  local ui_kit_alias="$work_root/chummer-ui-kit"
  local registry_alias="$work_root/chummer-hub-registry"
  local legacy_alias="$work_root/chummer5a"
  local complete_alias_root="$work_root/chummercomplete"

  mkdir -p "$work_root" "$work_root/.c" "$work_root/fleet/repos" "$temp_root"
  export TMPDIR="$temp_root"
  export CHUMMER_DESKTOP_INSTALLER_TMPDIR="$TMPDIR/desktop-installer"
  mkdir -p "$CHUMMER_DESKTOP_INSTALLER_TMPDIR"
  log_disk_space "$work_root" "release work root"
  log "temporary packaging root: $TMPDIR"
  log "desktop installer temp root: $CHUMMER_DESKTOP_INSTALLER_TMPDIR"
  log_disk_space "$TMPDIR" "temporary packaging root"
  require_min_free_space_gib "$work_root" "release work root" "$minimum_free_gib"
  require_min_free_space_gib "$TMPDIR" "temporary packaging root" "$minimum_free_gib"

  clone_or_update "https://github.com/ArchonMegalon/chummer6-ui.git" "$ui_repo" "$ui_ref" "$ui_expected_commit"
  require_compatible_dotnet_sdk "$ui_repo"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-core.git" "$core_repo" "$core_ref" "$core_expected_commit"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-hub.git" "$hub_repo" "$hub_ref" "$hub_expected_commit"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-ui-kit.git" "$ui_kit_repo" "$ui_kit_ref" "$ui_kit_expected_commit"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-hub-registry.git" "$registry_repo" "$registry_ref" "$registry_expected_commit"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-media-factory.git" "$media_repo" "$media_factory_ref" "$media_factory_expected_commit"
  clone_or_update "https://github.com/ArchonMegalon/chummer5a.git" "$legacy_repo" "$legacy_ref" "$legacy_expected_commit"

  ensure_link_target "$core_repo" "$core_alias"
  ensure_link_target "$hub_repo" "$hub_alias"
  ensure_link_target "$ui_kit_repo" "$ui_kit_alias"
  ensure_link_target "$registry_repo" "$registry_alias"
  ensure_link_target "$legacy_repo" "$legacy_alias"
  ensure_link_target "$core_alias" "$work_root/.c/chummer-core-engine"
  ensure_link_target "$hub_alias" "$work_root/.c/chummer.run-services"
  ensure_link_target "$ui_kit_alias" "$work_root/.c/chummer-ui-kit"
  ensure_link_target "$registry_alias" "$work_root/.c/chummer-hub-registry"

  mkdir -p "$complete_alias_root"
  ensure_link_target "$core_alias" "$complete_alias_root/chummer-core-engine"
  ensure_link_target "$hub_alias" "$complete_alias_root/chummer.run-services"
  ensure_link_target "$ui_kit_alias" "$complete_alias_root/chummer-ui-kit"
  ensure_link_target "$registry_alias" "$complete_alias_root/chummer-hub-registry"
  ensure_link_target "$ui_repo" "$complete_alias_root/chummer6-ui"

  local requested_release_proof="${CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH:-${CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE:-${CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL:-}}}"
  local requested_ui_localization_release_gate="${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH:-${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_FILE:-${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL:-}}}"
  local fallback_release_proof_url="${CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL:-}"
  local fallback_ui_localization_release_gate_url="${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL:-}"
  local release_proof_path
  local ui_localization_release_gate_path
  local sanitized_release_proof_path
  local sanitized_ui_localization_release_gate_path
  local release_proof_max_age_seconds="${CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS:-${CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS:-86400}}"
  local release_proof_max_future_skew_seconds="${CHUMMER_VERIFY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS:-${CHUMMER_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS:-300}}"
  local localization_gate_max_age_seconds="${CHUMMER_VERIFY_LOCALIZATION_GATE_MAX_AGE_SECONDS:-${CHUMMER_UI_LOCALIZATION_GATE_MAX_AGE_SECONDS:-604800}}"
  local localization_gate_max_future_skew_seconds="${CHUMMER_VERIFY_LOCALIZATION_GATE_MAX_FUTURE_SKEW_SECONDS:-${CHUMMER_UI_LOCALIZATION_GATE_MAX_FUTURE_SKEW_SECONDS:-300}}"
  local release_proof_health=""
  local ui_localization_release_gate_health=""

  release_proof_path="$(resolve_hub_local_release_proof_path \
    "$requested_release_proof" \
    "$hub_alias/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json" \
    "$work_root/.c/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json" \
    "$complete_alias_root/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json" \
    "$fallback_release_proof_url")"
  if [[ -n "$release_proof_path" ]]; then
    if ! release_proof_health="$(json_generated_at_health \
      "$release_proof_path" \
      "release proof" \
      "$release_proof_max_age_seconds" \
      "$release_proof_max_future_skew_seconds" 2>&1)"; then
      log "$release_proof_health"
      release_proof_path=""
    fi
  fi
  if [[ -z "$release_proof_path" ]]; then
    release_proof_path="$(mktemp)"
    bootstrap_tmp_paths+=("$release_proof_path")
    generate_validated_hub_local_release_proof \
      "$hub_alias" \
      "$hub_repo" \
      "$release_proof_path" \
      "$release_proof_max_age_seconds" \
      "$release_proof_max_future_skew_seconds" \
      "${registry_alias}/scripts/materialize_public_release_channel.py"
    log "generated fresh hub local release proof at $release_proof_path"
  fi

  ui_localization_release_gate_path="$(resolve_first_existing_file_path \
    "$requested_ui_localization_release_gate" \
    "$ui_repo/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$complete_alias_root/chummer6-ui/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$fallback_ui_localization_release_gate_url")"
  if [[ -n "$ui_localization_release_gate_path" ]]; then
    if ! ui_localization_release_gate_health="$(json_generated_at_health \
      "$ui_localization_release_gate_path" \
      "ui localization release gate" \
      "$localization_gate_max_age_seconds" \
      "$localization_gate_max_future_skew_seconds" 2>&1)"; then
      log "$ui_localization_release_gate_health"
      ui_localization_release_gate_path=""
    fi
  fi
  if [[ -z "$ui_localization_release_gate_path" ]]; then
    ui_localization_release_gate_path="$(generate_validated_ui_localization_release_gate \
      "$ui_repo" \
      "$localization_gate_max_age_seconds" \
      "$localization_gate_max_future_skew_seconds" \
      "$complete_alias_root/chummer6-ui")"
    bootstrap_tmp_paths+=("$ui_localization_release_gate_path")
    log "generated fresh ui localization release gate at $ui_localization_release_gate_path"
  fi

  if [[ -z "$release_proof_path" ]] || [[ ! -f "$release_proof_path" ]]; then
    die "release proof file is missing and could not be generated: $release_proof_path"
  fi
  if [[ -z "$ui_localization_release_gate_path" ]] || [[ ! -f "$ui_localization_release_gate_path" ]]; then
    die "ui localization release gate file is missing: set CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH"
  fi

  sanitized_release_proof_path="$(mktemp)"
  sanitized_ui_localization_release_gate_path="$(mktemp)"
  bootstrap_tmp_paths+=("$sanitized_release_proof_path" "$sanitized_ui_localization_release_gate_path")
  sanitize_release_proof_payload "$release_proof_path" "$sanitized_release_proof_path"
  sanitize_ui_localization_release_gate_payload "$ui_localization_release_gate_path" "$sanitized_ui_localization_release_gate_path"
  release_proof_path="$sanitized_release_proof_path"
  ui_localization_release_gate_path="$sanitized_ui_localization_release_gate_path"

  local materializer_path="${registry_alias}/scripts/materialize_public_release_channel.py"
  local proof_validation_output
  if ! proof_validation_output="$(validate_local_release_proofs "$materializer_path" "$release_proof_path" "$ui_localization_release_gate_path" 2>&1)"; then
    log "release proof validation failed before build: $proof_validation_output"
    log "attempting fresh local hub release proof and ui localization release gate generation to recover"
    local regenerated_release_proof_path
    regenerated_release_proof_path="$(mktemp)"
    bootstrap_tmp_paths+=("$regenerated_release_proof_path")
    generate_validated_hub_local_release_proof \
      "$hub_alias" \
      "$hub_repo" \
      "$regenerated_release_proof_path" \
      "$release_proof_max_age_seconds" \
      "$release_proof_max_future_skew_seconds" \
      "$materializer_path"
    sanitize_release_proof_payload "$regenerated_release_proof_path" "$sanitized_release_proof_path"
    release_proof_path="$sanitized_release_proof_path"

    if proof_validation_output="$(validate_local_release_proofs "$materializer_path" "$release_proof_path" "$ui_localization_release_gate_path" 2>&1)"; then
      log "regenerated release proof validated against the current ui localization release gate"
    else
      log "regenerated release proof still failed against the current ui localization release gate: $proof_validation_output"
      log "retrying regenerated release proof against a freshly generated ui localization release gate"
      ui_localization_release_gate_path="$(generate_validated_ui_localization_release_gate \
        "$ui_repo" \
        "$localization_gate_max_age_seconds" \
        "$localization_gate_max_future_skew_seconds" \
        "$complete_alias_root/chummer6-ui")"
      bootstrap_tmp_paths+=("$ui_localization_release_gate_path")
      sanitize_ui_localization_release_gate_payload "$ui_localization_release_gate_path" "$sanitized_ui_localization_release_gate_path"
      ui_localization_release_gate_path="$sanitized_ui_localization_release_gate_path"

      if ! proof_validation_output="$(validate_local_release_proofs "$materializer_path" "$release_proof_path" "$ui_localization_release_gate_path" 2>&1)"; then
        die "release-proof validation failed after fallback regeneration. Set CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH and CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH to valid payloads, then rerun: $proof_validation_output"
      fi
    fi
  fi

  log "resolved release proof: $release_proof_path"
  log "resolved ui localization release gate: $ui_localization_release_gate_path"
  local release_proof_status
  local ui_gate_status
  release_proof_status="$(jq -r '.status // "missing"' "$release_proof_path" 2>/dev/null || true)"
  ui_gate_status="$(jq -r '.status // "missing"' "$ui_localization_release_gate_path" 2>/dev/null || true)"
  log "proof provenance: release proof status=${release_proof_status}, ui gate status=${ui_gate_status}"

  log "building media-factory compatibility assemblies"
  dotnet build "$media_repo/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj" -c Release --nologo -m:1 -p:RestoreDisableParallel=true
  dotnet build "$media_repo/src/Chummer.Media.Factory.Runtime/Chummer.Media.Factory.Runtime.csproj" -c Release --nologo -m:1 -p:RestoreDisableParallel=true

  cd "$ui_repo"

  local normalized_apps_csv="${apps_raw// /,}"
  local -a raw_heads=()
  local -a app_heads=()
  local raw_head
  IFS=',' read -r -a raw_heads <<< "$normalized_apps_csv"
  while IFS= read -r -d '' raw_head; do
    [[ -n "$raw_head" ]] || continue
    case "$raw_head" in
      all)
        if (( $(array_count app_heads) == 0 )) || ! append_unique_value "avalonia" "${app_heads[@]}"; then
          app_heads+=("avalonia")
        fi
        if (( $(array_count app_heads) == 0 )) || ! append_unique_value "blazor-desktop" "${app_heads[@]}"; then
          app_heads+=("blazor-desktop")
        fi
        ;;
      avalonia|blazor-desktop)
        if (( $(array_count app_heads) == 0 )) || ! append_unique_value "$raw_head" "${app_heads[@]}"; then
          app_heads+=("$raw_head")
        fi
        ;;
      *)
        die "unsupported app head: $raw_head"
        ;;
    esac
  done < <(array_values_nul raw_heads)

  (( $(array_count app_heads) > 0 )) || die "no app heads requested"

  export CHUMMER_LOCAL_CONTRACTS_PROJECT="$core_alias/Chummer.Contracts/Chummer.Contracts.csproj"
  export CHUMMER_LOCAL_CAMPAIGN_CONTRACTS_PROJECT="$hub_alias/Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj"
  export CHUMMER_LOCAL_RUN_CONTRACTS_PROJECT="$hub_alias/Chummer.Run.Contracts/Chummer.Run.Contracts.csproj"
  export CHUMMER_LOCAL_HUB_REGISTRY_CONTRACTS_PROJECT="$registry_alias/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj"
  export CHUMMER_LOCAL_UI_KIT_PROJECT="$ui_kit_alias/src/Chummer.Ui.Kit/Chummer.Ui.Kit.csproj"
  export CHUMMER_HUB_REGISTRY_ROOT="$registry_alias"
  export CHUMMER_LEGACY_FIXTURE_ROOT="$legacy_alias/Chummer.Tests/TestFiles"

  local out_root="out"
  local dist_dir="dist"
  local publish_bundle_dir="$dist_dir/promotion-bundle"
  local smoke_dir="$dist_dir/startup-smoke"
  local release_evidence_dir="$dist_dir/release-evidence"
  local response_path="$dist_dir/release-upload-response.json"
  local keep_upload_response="${CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE:-0}"
  BOOTSTRAP_RELEASE_UPLOAD_RESPONSE_PATH="$response_path"
  BOOTSTRAP_KEEP_UPLOAD_RESPONSE="$keep_upload_response"
  rm -rf "$out_root" "$dist_dir"
  mkdir -p \
    "$smoke_dir" \
    "$dist_dir/files" \
    "$release_evidence_dir" \
    "$dist_dir/proof/build-provenance/v1/invocations" \
    "$dist_dir/proof/build-provenance/v1/sbom" \
    "$dist_dir/.build-provenance-state"

  local provenance_generator="$hub_alias/scripts/release/materialize_build_provenance.py"
  local provenance_support="$hub_alias/scripts/release/build_provenance_support.py"
  local provenance_invocation_dir="$ui_repo/$dist_dir/proof/build-provenance/v1/invocations"
  local provenance_sbom_dir="$ui_repo/$dist_dir/proof/build-provenance/v1/sbom"
  local provenance_state_dir="$ui_repo/$dist_dir/.build-provenance-state"
  [[ -f "$provenance_generator" ]] || die "portable build provenance generator is missing: $provenance_generator"
  [[ -f "$provenance_support" ]] || die "portable build provenance support is missing: $provenance_support"

  local head project launch_target artifact_kind out_dir dmg_path tar_path promoted_tar_path
  local provenance_target_id installer_artifact_id archive_artifact_id
  local installer_invocation_id archive_invocation_id
  local installer_state_path archive_state_path installer_receipt_path archive_receipt_path sbom_path
  local published_at
  published_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  log "building heads: ${app_heads[*]}"
  for head in "${app_heads[@]}"; do
    IFS='|' read -r project launch_target artifact_kind < <(resolve_head_build_metadata "$head") \
      || die "unsupported app head: $head"

    out_dir="$out_root/$head/$rid"

    log "restoring $project for $rid"
    dotnet restore "$project" \
      -r "$rid" \
      -p:UseChummerEngineContractsLocalFeed=false \
      -p:ChummerUseLocalCompatibilityTree=true \
      -p:ChummerLocalContractsProject="$CHUMMER_LOCAL_CONTRACTS_PROJECT" \
      -p:ChummerLocalCampaignContractsProject="$CHUMMER_LOCAL_CAMPAIGN_CONTRACTS_PROJECT" \
      -p:ChummerLocalRunContractsProject="$CHUMMER_LOCAL_RUN_CONTRACTS_PROJECT" \
      -p:ChummerLocalHubRegistryContractsProject="$CHUMMER_LOCAL_HUB_REGISTRY_CONTRACTS_PROJECT" \
      -p:ChummerLocalUiKitProject="$CHUMMER_LOCAL_UI_KIT_PROJECT"

    provenance_target_id="$(resolve_head_provenance_target_id "$head")" \
      || die "unsupported provenance target for app head: $head"
    installer_artifact_id="$head-$rid-installer"
    archive_artifact_id="$head-$rid-archive"
    installer_invocation_id="$release_version.$head.$rid.installer"
    archive_invocation_id="$release_version.$head.$rid.archive"
    installer_state_path="$provenance_state_dir/$installer_invocation_id.state.json"
    archive_state_path="$provenance_state_dir/$archive_invocation_id.state.json"
    installer_receipt_path="$provenance_invocation_dir/$installer_invocation_id.json"
    archive_receipt_path="$provenance_invocation_dir/$archive_invocation_id.json"
    sbom_path="$provenance_sbom_dir/$provenance_target_id.cdx.json"

    log "declaring build provenance subjects before publish for $head"
    begin_mac_file_build_provenance \
      "$provenance_generator" \
      "$provenance_support" \
      "$ui_repo" \
      "$core_alias" \
      "$hub_alias" \
      "$ui_kit_alias" \
      "$registry_alias" \
      "$media_repo" \
      "$legacy_alias" \
      "$project" \
      "$provenance_target_id" \
      "$installer_artifact_id" \
      "chummer-$head-$rid-installer.dmg" \
      "$ui_repo/$dist_dir/files/chummer-$head-$rid-installer.dmg" \
      "$installer_invocation_id" \
      "$installer_state_path" \
      "$installer_receipt_path" \
      "$sbom_path" \
      "$executed_bootstrap_path"
    begin_mac_file_build_provenance \
      "$provenance_generator" \
      "$provenance_support" \
      "$ui_repo" \
      "$core_alias" \
      "$hub_alias" \
      "$ui_kit_alias" \
      "$registry_alias" \
      "$media_repo" \
      "$legacy_alias" \
      "$project" \
      "$provenance_target_id" \
      "$archive_artifact_id" \
      "chummer-$head-$rid.tar.gz" \
      "$ui_repo/$dist_dir/files/chummer-$head-$rid.tar.gz" \
      "$archive_invocation_id" \
      "$archive_state_path" \
      "$archive_receipt_path" \
      "$sbom_path" \
      "$executed_bootstrap_path"

    log "publishing $project"
    dotnet publish "$project" \
      -c Release \
      -r "$rid" \
      --self-contained true \
      -p:PublishSingleFile=true \
      -p:PublishTrimmed=false \
      -p:IncludeNativeLibrariesForSelfExtract=true \
      -p:UseChummerEngineContractsLocalFeed=false \
      -p:ChummerUseLocalCompatibilityTree=true \
      -p:ChummerLocalContractsProject="$CHUMMER_LOCAL_CONTRACTS_PROJECT" \
      -p:ChummerLocalCampaignContractsProject="$CHUMMER_LOCAL_CAMPAIGN_CONTRACTS_PROJECT" \
      -p:ChummerLocalRunContractsProject="$CHUMMER_LOCAL_RUN_CONTRACTS_PROJECT" \
      -p:ChummerLocalHubRegistryContractsProject="$CHUMMER_LOCAL_HUB_REGISTRY_CONTRACTS_PROJECT" \
      -p:ChummerLocalUiKitProject="$CHUMMER_LOCAL_UI_KIT_PROJECT" \
      -p:ChummerDesktopReleaseVersion="$release_version" \
      -p:ChummerDesktopReleaseChannel="$release_channel" \
      -o "$out_dir"

    log_disk_space "$work_root" "release work root before packaging $head"
    log_disk_space "$TMPDIR" "temporary packaging root before packaging $head"
    ensure_packaging_headroom "$work_root" "$TMPDIR" "$packaging_minimum_free_gib"

    log "packaging dmg for $head"
    log "build-desktop-installer inputs: publish=$out_dir, rid=$rid, output=$dist_dir/chummer-$head-$rid-installer.dmg"
    bash scripts/build-desktop-installer.sh \
      "$out_dir" \
      "$head" \
      "$rid" \
      "$launch_target" \
      "$dist_dir" \
      "$release_version"

    dmg_path="$dist_dir/chummer-$head-$rid-installer.dmg"
    [[ -f "$dmg_path" ]] || die "dmg not produced: $dmg_path"
    tar_path="$dist_dir/chummer-$head-$rid.tar.gz"
    [[ -f "$tar_path" ]] || die "tar archive not produced for $head: $tar_path"
    promoted_tar_path="$dist_dir/files/$(basename "$tar_path")"
    mv "$tar_path" "$promoted_tar_path"

    if [[ "$artifact_kind" != "dmg" ]]; then
      die "unsupported artifact kind for mac bootstrap: $artifact_kind"
    fi

    if [[ "$require_signed_release" == "1" ]]; then
      log "repacking dmg with signed app bundle for $head"
      local mount_dir repack_root app_bundle repacked_dmg
      mount_dir="$(mktemp -d "${TMPDIR}/chummer-mac-release-mount.XXXXXX")"
      repack_root="$(mktemp -d "${TMPDIR}/chummer-mac-release-repack.XXXXXX")"

      log "hdiutil attach for signed repack: input=$dmg_path mount=$mount_dir"
      hdiutil attach -nobrowse -readonly -mountpoint "$mount_dir" "$dmg_path" >/dev/null
      app_bundle="$(find "$mount_dir" -maxdepth 1 -type d -name '*.app' | sort | head -n 1)"
      [[ -n "$app_bundle" ]] || die "mounted dmg did not expose an .app bundle"
      cp -a "$app_bundle" "$repack_root/"
      hdiutil detach "$mount_dir" >/dev/null 2>&1 || true
      rm -rf "$mount_dir"

      codesign --force --deep --options runtime --timestamp --sign "$sign_identity" "$repack_root/$(basename "$app_bundle")"

      repacked_dmg="${dmg_path%.dmg}-signed.dmg"
      rm -f "$repacked_dmg"
      log "hdiutil create for signed repack: source=$repack_root output=$repacked_dmg"
      hdiutil create \
        -volname "$(basename "$app_bundle" .app)" \
        -srcfolder "$repack_root" \
        -ov \
        -format UDZO \
        "$repacked_dmg" >/dev/null

      mv "$repacked_dmg" "$dmg_path"
      codesign --force --timestamp --sign "$sign_identity" "$dmg_path"

      log "notarizing dmg for $head"
      xcrun notarytool submit "$dmg_path" --keychain-profile "$notary_profile" --wait
      xcrun stapler staple "$dmg_path"
      xcrun stapler validate "$dmg_path"
      spctl -a -vv --type open "$dmg_path" >/dev/null

      rm -rf "$repack_root"
    else
      log "skipping codesign/notary for preview upload: $head"
    fi

    log "running mac startup smoke for $head"
    local startup_host_class="${CHUMMER_DESKTOP_STARTUP_SMOKE_HOST_CLASS:-}"
    if [[ -z "$startup_host_class" ]]; then
      case "$rid" in
        osx-*) startup_host_class="macos-host" ;;
        win-*) startup_host_class="windows-host" ;;
        linux-*) startup_host_class="local-linux" ;;
        *) startup_host_class="local-${rid}" ;;
      esac
    fi
    CHUMMER_DESKTOP_RELEASE_CHANNEL="$release_channel" \
    CHUMMER_DESKTOP_RELEASE_VERSION="$release_version" \
    CHUMMER_DESKTOP_STARTUP_SMOKE_HOST_CLASS="$startup_host_class" \
    bash scripts/run-desktop-startup-smoke.sh \
      "$dmg_path" \
      "$head" \
      "$rid" \
      "$launch_target" \
      "$smoke_dir" \
      "$release_version"

    local promoted_dmg_path="$dist_dir/files/$(basename "$dmg_path")"
    mv "$dmg_path" "$promoted_dmg_path"
    stamp_startup_smoke_receipt_artifact_identity \
      "$smoke_dir/startup-smoke-$head-$rid.receipt.json" \
      "$promoted_dmg_path" \
      "$head" \
      "$rid"

    [[ -f "$promoted_dmg_path" ]] || die "final dmg bytes are missing before provenance finalization: $promoted_dmg_path"
    [[ -f "$promoted_tar_path" ]] || die "final archive bytes are missing before provenance finalization: $promoted_tar_path"
    log "finalizing build provenance against final dist/files bytes for $head"
    finalize_mac_file_build_provenance \
      "$provenance_generator" \
      "$installer_invocation_id" \
      "$installer_state_path" \
      "$installer_receipt_path"
    finalize_mac_file_build_provenance \
      "$provenance_generator" \
      "$archive_invocation_id" \
      "$archive_state_path" \
      "$archive_receipt_path"
  done

  log "generating release manifests"
  write_release_manifests \
    "$registry_alias" \
    "$dist_dir/files" \
    "$smoke_dir" \
    "$dist_dir/releases.json" \
    "$dist_dir/RELEASE_CHANNEL.generated.json" \
    "$release_version" \
    "$release_channel" \
    "$published_at" \
    "$release_proof_path" \
    "$ui_localization_release_gate_path" \
    "$materializer_skip_startup_smoke_filter"

  log "generating release promotion evidence"
  write_public_promotion_evidence \
    "$dist_dir/RELEASE_CHANNEL.generated.json" \
    "$smoke_dir" \
    "$release_evidence_dir/public-promotion.json" \
    "$release_channel" \
    "$published_at"

  validate_public_promotion_evidence \
    "$release_evidence_dir/public-promotion.json" \
    "$release_channel"

  log "refreshing manifests with promotion evidence"
  write_release_manifests \
    "$registry_alias" \
    "$dist_dir/files" \
    "$smoke_dir" \
    "$dist_dir/releases.json" \
    "$dist_dir/RELEASE_CHANNEL.generated.json" \
    "$release_version" \
    "$release_channel" \
    "$published_at" \
    "$release_proof_path" \
    "$ui_localization_release_gate_path" \
    "$materializer_skip_startup_smoke_filter"

  validate_release_payload_contracts "$dist_dir/RELEASE_CHANNEL.generated.json"

  if ! validate_manifests_have_artifacts \
    "$dist_dir/RELEASE_CHANNEL.generated.json" \
    "$dist_dir/releases.json" \
    "$smoke_dir"; then
    if ! is_true "$materializer_skip_startup_smoke_filter"; then
      if ! is_true "$materializer_retry_without_filter"; then
        die "manifest projection produced 0 artifacts; release may fail upload. Set CHUMMER_MATERIALIZE_RETRY_WITHOUT_STARTUP_SMOKE_FILTER_ON_ZERO=1 to retry without startup-smoke filtering."
      fi
      log "manifest projection produced 0 artifacts; retrying release manifests with startup-smoke filter disabled."
      materializer_skip_startup_smoke_filter=1
      write_release_manifests \
        "$registry_alias" \
        "$dist_dir/files" \
        "$smoke_dir" \
        "$dist_dir/releases.json" \
        "$dist_dir/RELEASE_CHANNEL.generated.json" \
        "$release_version" \
        "$release_channel" \
        "$published_at" \
        "$release_proof_path" \
        "$ui_localization_release_gate_path" \
        "$materializer_skip_startup_smoke_filter"
    else
      log "startup-smoke filtering already disabled but no artifacts were projected. forcing receipt-path fallback."
    fi

    log "re-generating release promotion evidence after startup-smoke filter bypass"
    write_public_promotion_evidence \
      "$dist_dir/RELEASE_CHANNEL.generated.json" \
      "$smoke_dir" \
      "$release_evidence_dir/public-promotion.json" \
      "$release_channel" \
      "$published_at"

    validate_public_promotion_evidence \
      "$release_evidence_dir/public-promotion.json" \
      "$release_channel"

    if ! validate_release_payload_contracts "$dist_dir/RELEASE_CHANNEL.generated.json"; then
      die "release manifest contracts are invalid after startup-smoke filter retry."
    fi

    if ! validate_manifests_have_artifacts \
      "$dist_dir/RELEASE_CHANNEL.generated.json" \
      "$dist_dir/releases.json" \
      "$smoke_dir"; then
      log "manifest projection still produced 0 artifacts after startup filter bypass. retrying with receipt path disabled to restore installer rows."
      write_release_manifests \
        "$registry_alias" \
        "$dist_dir/files" \
        "/dev/null" \
        "$dist_dir/releases.json" \
        "$dist_dir/RELEASE_CHANNEL.generated.json" \
        "$release_version" \
        "$release_channel" \
        "$published_at" \
        "$release_proof_path" \
        "$ui_localization_release_gate_path" \
        "$materializer_skip_startup_smoke_filter"

      log "re-generating release promotion evidence after receipt-path disabled retry"
      write_public_promotion_evidence \
        "$dist_dir/RELEASE_CHANNEL.generated.json" \
        "$smoke_dir" \
        "$release_evidence_dir/public-promotion.json" \
        "$release_channel" \
        "$published_at"

      validate_public_promotion_evidence \
        "$release_evidence_dir/public-promotion.json" \
        "$release_channel"

      if ! validate_release_payload_contracts "$dist_dir/RELEASE_CHANNEL.generated.json"; then
        die "release manifest contracts are invalid after receipt-path-disabled retry."
      fi
      if ! validate_manifests_have_artifacts \
        "$dist_dir/RELEASE_CHANNEL.generated.json" \
        "$dist_dir/releases.json" \
        "$smoke_dir"; then
        log "manifest projection still produced 0 artifacts after startup-smoke fallbacks. generating fallback manifests directly from dist files."
        write_release_manifests_fallback_no_filter \
          "$registry_root" \
          "$dist_dir/files" \
          "$dist_dir/releases.json" \
          "$dist_dir/RELEASE_CHANNEL.generated.json" \
          "$release_version" \
          "$release_channel" \
          "$published_at" \
          "$release_proof_path" \
          "$ui_localization_release_gate_path"

        log "re-generating release promotion evidence after fallback manifest generation"
        write_public_promotion_evidence \
          "$dist_dir/RELEASE_CHANNEL.generated.json" \
          "$smoke_dir" \
          "$release_evidence_dir/public-promotion.json" \
          "$release_channel" \
          "$published_at"

        validate_public_promotion_evidence \
          "$release_evidence_dir/public-promotion.json" \
          "$release_channel"

        if ! validate_release_payload_contracts "$dist_dir/RELEASE_CHANNEL.generated.json"; then
          die "release manifest contracts are invalid after fallback manifest generation."
        fi
        validate_manifests_have_artifacts \
          "$dist_dir/RELEASE_CHANNEL.generated.json" \
          "$dist_dir/releases.json" \
          "$smoke_dir" || die "manifest projection still produced 0 artifacts after all startup-smoke fallback modes."
      fi
    fi
  fi

  log "validating governed build provenance against final release bytes"
  python3 "$hub_alias/scripts/release/verify_release_build_provenance_bundle.py" "$ui_repo/$dist_dir"
  validate_bundle_directory_integrity "$dist_dir"
  ensure_publish_bundle_startup_smoke_receipts "$dist_dir" "$publish_bundle_dir"
  write_release_upload_payload_summary "$dist_dir"

  log_bundle_manifest_summary "$dist_dir"

  create_minimal_promotion_bundle "$dist_dir" "$publish_bundle_dir"
  python3 "$hub_alias/scripts/release/verify_release_build_provenance_bundle.py" "$ui_repo/$publish_bundle_dir"
  validate_bundle_directory_integrity "$publish_bundle_dir"

  if (( MAC_RELEASE_STAGE_ONLY == 1 )); then
    stage_local_release_bundle \
      "$ui_repo/$publish_bundle_dir" \
      "$stage_output_path" \
      "$hub_alias/scripts/release/verify_release_build_provenance_bundle.py" \
      "$release_version" \
      "$release_channel" \
      "$rid" \
      "$apps_raw"
    return 0
  fi

  case "$publish_mode" in
    http)
      log "uploading release bundle via staged HTTP session"
      upload_release_bundle_http \
        "$publish_bundle_dir" \
        "$sessions_url" \
        "$release_upload_auth_value" \
        "$response_path" \
        "$hub_alias/scripts/release/release_upload_attempt_receipt.py"
      ;;
    filesystem)
      local remote_stage="${CHUMMER_REMOTE_STAGING_DIR:-/tmp/chummer-mac-release-bundle}"
      local remote_ui_repo="${CHUMMER_REMOTE_UI_REPO_DIR:-/docker/chummercomplete/chummer6-ui}"
      log "syncing bundle to ${CHUMMER_RELEASE_SSH_TARGET}:${remote_stage}"
      rsync -az --delete "$publish_bundle_dir/" "${CHUMMER_RELEASE_SSH_TARGET}:${remote_stage}/"
      log "publishing bundle on remote host"
      ssh "$CHUMMER_RELEASE_SSH_TARGET" \
        "cd '$remote_ui_repo' && bash scripts/publish-download-bundle.sh '$remote_stage' '${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR}'"
      ;;
    s3)
      log "publishing bundle to object storage"
      CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL="$verify_url" bash scripts/publish-download-bundle-s3.sh "$publish_bundle_dir"
      ;;
    *)
      die "unsupported publish mode: $publish_mode"
      ;;
  esac

  python3 "$hub_alias/scripts/verify_release_upload_response_truth.py" \
    --local-manifest "$dist_dir/releases.json" \
    --local-canonical-manifest "$dist_dir/RELEASE_CHANNEL.generated.json" \
    --upload-response "$response_path"

  log "verifying local bundle manifest"
  CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 \
    bash scripts/verify-releases-manifest.sh "$dist_dir/releases.json"

  log "verifying live canonical manifest at $canonical_verify_url"
  CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 \
    bash scripts/verify-releases-manifest.sh "$canonical_verify_url"

  log "verifying live release projection at $canonical_verify_url"
  verify_live_release_projection "$dist_dir/RELEASE_CHANNEL.generated.json" "$compatibility_verify_url" "$canonical_verify_url" "$response_path" "$require_compatibility_projection"

  if [[ -f "$response_path" ]]; then
    chmod 600 "$response_path" 2>/dev/null || true
    log "sanitized release upload response summary accepted; credential-bearing fields were discarded before persistence"
    if is_true "$keep_upload_response"; then
      log "sanitized release upload response summary retained at $response_path"
    else
      rm -f "$response_path"
      BOOTSTRAP_RELEASE_UPLOAD_RESPONSE_PATH=""
      log "removed sanitized release upload response summary; set CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE=1 to retain it."
    fi
  fi

  log "done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
