#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUNDLE_DIR="${1:-$REPO_ROOT/dist}"
DEPLOY_DIR="${2:-$REPO_ROOT/Docker/Downloads}"
PORTAL_MANIFEST_PATH="${PORTAL_MANIFEST_PATH:-}"
PORTAL_DOWNLOADS_DIR="${PORTAL_DOWNLOADS_DIR:-}"
DEPLOY_MODE="${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_ENABLED:-false}"
LIVE_VERIFY_TARGET="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}"
MANIFEST_SOURCE="$BUNDLE_DIR/releases.json"
FILES_SOURCE="$BUNDLE_DIR/files"
RELEASE_PROOF_PATH="${RELEASE_PROOF_PATH:-}"
STARTUP_SMOKE_SOURCE="${STARTUP_SMOKE_SOURCE:-$BUNDLE_DIR/startup-smoke}"
PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-false}"
CHUMMER_MACOS_PUBLIC_SHELF_ENABLED="${CHUMMER_MACOS_PUBLIC_SHELF_ENABLED:-false}"

to_bool() {
  local value
  value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

is_public_artifact() {
  local artifact_name
  artifact_name="$(basename "$1")"
  if ! to_bool "$CHUMMER_MACOS_PUBLIC_SHELF_ENABLED" && [[ "$artifact_name" == chummer-*-osx-*installer.dmg || "$artifact_name" == chummer-*-osx-*installer.pkg ]]; then
    return 1
  fi
  return 0
}

bundle_manifest_matches_files() {
  local manifest_path="$1"
  local files_root="$2"
  python3 - "$manifest_path" "$files_root" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
files_root = Path(sys.argv[2])

payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
downloads = payload.get("downloads") or []
failures: list[str] = []
seen: set[str] = set()

for artifact in downloads:
    if not isinstance(artifact, dict):
        continue
    url = str(artifact.get("url") or "").strip()
    file_name = Path(url).name if url else ""
    if not file_name:
        continue
    seen.add(file_name)
    file_path = files_root / file_name
    if not file_path.is_file():
        failures.append(f"manifest references missing file {file_name}")
        continue
    actual_size = file_path.stat().st_size
    expected_size = int(artifact.get("sizeBytes") or 0)
    if expected_size and expected_size != actual_size:
        failures.append(f"{file_name}: size {actual_size} != manifest {expected_size}")
    expected_sha = str(artifact.get("sha256") or "").strip().lower()
    if expected_sha:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if digest != expected_sha:
            failures.append(f"{file_name}: sha256 {digest} != manifest {expected_sha}")

for file_path in sorted(files_root.iterdir()):
    if not file_path.is_file():
        continue
    if file_path.name not in seen:
        failures.append(f"bundle contains extra file not present in manifest: {file_path.name}")

if failures:
    print("false")
    for failure in failures:
        print(failure)
else:
    print("true")
PY
}

if [[ -z "$PORTAL_MANIFEST_PATH" ]]; then
  if [[ "$(realpath "$DEPLOY_DIR")" == "$(realpath "$REPO_ROOT/Docker/Downloads")" ]]; then
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

artifacts=()
while IFS= read -r artifact_path; do
  [[ -n "$artifact_path" ]] || continue
  artifacts+=("$artifact_path")
done < <(find "$FILES_SOURCE" -maxdepth 1 -type f \
  \( -name "chummer-avalonia-*.exe" -o -name "chummer-avalonia-*.zip" -o \
     -name "chummer-avalonia-*.tar.gz" -o -name "chummer-avalonia-*-installer.exe" -o -name "chummer-avalonia-*-installer.deb" -o \
     -name "chummer-avalonia-*-installer.pkg" -o -name "chummer-avalonia-*-installer.dmg" -o \
     -name "chummer-avalonia-*-installer.msix" -o -name "chummer-blazor-desktop-*.exe" -o -name "chummer-blazor-desktop-*.zip" -o \
     -name "chummer-blazor-desktop-*.tar.gz" -o -name "chummer-blazor-desktop-*-installer.exe" -o \
     -name "chummer-blazor-desktop-*-installer.deb" -o -name "chummer-blazor-desktop-*-installer.pkg" -o \
     -name "chummer-blazor-desktop-*-installer.dmg" -o -name "chummer-blazor-desktop-*-installer.msix" \) \
  | sort)

if [[ "${#artifacts[@]}" -eq 0 ]]; then
  echo "No desktop artifacts found under $FILES_SOURCE" >&2
  exit 1
fi

sync_source_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$sync_source_dir"
}
trap cleanup EXIT

append_unique_downloads_mirror_dir() {
  local candidate="$1"
  local resolved_candidate=""
  local existing=""

  [[ -n "$candidate" ]] || return 0
  resolved_candidate="$(realpath -m "$candidate")"
  for existing in "${live_downloads_mirror_dirs[@]:-}"; do
    if [[ "$(realpath -m "$existing")" == "$resolved_candidate" ]]; then
      return 0
    fi
  done
  live_downloads_mirror_dirs+=("$candidate")
}

discover_live_downloads_mirror_dirs() {
  local configured="${CHUMMER_PUBLIC_EDGE_DOWNLOADS_MIRROR_DIRS:-}"
  local candidate=""
  local sibling_root=""

  if [[ -n "$configured" ]]; then
    IFS=',' read -r -a configured_dirs <<<"$configured"
    for candidate in "${configured_dirs[@]}"; do
      candidate="${candidate#"${candidate%%[![:space:]]*}"}"
      candidate="${candidate%"${candidate##*[![:space:]]}"}"
      [[ -n "$candidate" ]] || continue
      append_unique_downloads_mirror_dir "$candidate"
    done
  fi

  for sibling_root in \
    "$REPO_ROOT/../chummer.run-services/Chummer.Portal/downloads" \
    "$REPO_ROOT/../chummer6-hub/Chummer.Portal/downloads" \
    "$REPO_ROOT/../chummer-presentation/Docker/Downloads"
  do
    if [[ -d "$(dirname "$sibling_root")" ]]; then
      append_unique_downloads_mirror_dir "$sibling_root"
    fi
  done
}

sync_live_downloads_mirror_dir() {
  local target_dir="$1"
  local target_label="$2"
  local resolved_target_dir=""
  local resolved_deploy_dir=""
  local resolved_portal_dir=""
  local files_dir=""
  local startup_smoke_dir=""
  local source_path=""
  local file_name=""

  resolved_target_dir="$(realpath -m "$target_dir")"
  resolved_deploy_dir="$(realpath -m "$DEPLOY_DIR")"
  resolved_portal_dir="$(realpath -m "$PORTAL_DOWNLOADS_DIR")"

  if [[ "$resolved_target_dir" == "$resolved_deploy_dir" || "$resolved_target_dir" == "$resolved_portal_dir" ]]; then
    return 0
  fi

  mkdir -p "$target_dir"
  cp "$DEPLOY_DIR/releases.json" "$target_dir/releases.json"
  cp "$DEPLOY_DIR/RELEASE_CHANNEL.generated.json" "$target_dir/RELEASE_CHANNEL.generated.json"

  startup_smoke_dir="$target_dir/startup-smoke"
  mkdir -p "$startup_smoke_dir"
  find "$startup_smoke_dir" -maxdepth 1 -type f -name 'startup-smoke-*.receipt.json' -exec rm -f -- {} +
  if [[ -d "$DEPLOY_DIR/startup-smoke" ]] && find "$DEPLOY_DIR/startup-smoke" -maxdepth 1 -type f -name 'startup-smoke-*.receipt.json' | grep -q .; then
    cp -f "$DEPLOY_DIR"/startup-smoke/startup-smoke-*.receipt.json "$startup_smoke_dir"/
  fi

  files_dir="$target_dir/files"
  mkdir -p "$files_dir"
  find "$files_dir" -maxdepth 1 -type f \
    \( -name "chummer-avalonia-*.exe" -o -name "chummer-avalonia-*.zip" -o -name "chummer-avalonia-*.tar.gz" -o \
       -name "chummer-avalonia-*-installer.exe" -o -name "chummer-avalonia-*-installer.deb" -o \
       -name "chummer-avalonia-*-installer.pkg" -o -name "chummer-avalonia-*-installer.dmg" -o \
       -name "chummer-avalonia-*-installer.msix" -o -name "chummer-blazor-desktop-*.exe" -o -name "chummer-blazor-desktop-*.zip" -o \
       -name "chummer-blazor-desktop-*.tar.gz" -o -name "chummer-blazor-desktop-*-installer.exe" -o \
       -name "chummer-blazor-desktop-*-installer.deb" -o -name "chummer-blazor-desktop-*-installer.pkg" -o \
       -name "chummer-blazor-desktop-*-installer.dmg" -o -name "chummer-blazor-desktop-*-installer.msix" -o \
       -name "chummer-6-*.exe" -o -name "chummer-6-*.zip" -o -name "chummer-6-*.tar.gz" -o -name "chummer-6-*-installer.exe" -o \
       -name "chummer-6-*-installer.deb" -o -name "chummer-6-*-installer.pkg" -o -name "chummer-6-*-installer.dmg" -o \
       -name "chummer-6-*-installer.msix" \) \
    -delete

  for file_name in "${promoted_file_names[@]}"; do
    source_path="$DEPLOY_DIR/files/$file_name"
    if [[ ! -f "$source_path" ]]; then
      echo "promoted artifact missing from deploy root for $target_label mirror: $source_path" >&2
      exit 1
    fi
    cp "$source_path" "$files_dir/"
  done

  bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$target_dir/RELEASE_CHANNEL.generated.json" >/dev/null
  echo "synced ${#promoted_file_names[@]} promoted artifact(s) -> $target_label mirror $target_dir"
}

for artifact in "${artifacts[@]}"; do
  if is_public_artifact "$artifact"; then
    cp "$artifact" "$sync_source_dir/"
  fi
done

release_version="${RELEASE_VERSION:-}"
release_channel="${RELEASE_CHANNEL:-}"
release_published_at="${RELEASE_PUBLISHED_AT:-}"
default_published_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ -f "$MANIFEST_SOURCE" ]]; then
  manifest_meta_file="$(mktemp)"
  python3 - "$MANIFEST_SOURCE" <<'PY' >"$manifest_meta_file"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
print(str(data.get("version", "unpublished")))
print(str(data.get("channel", "docker")))
print(str(data.get("publishedAt", "")))
PY
  manifest_meta=()
  while IFS= read -r line; do
    manifest_meta+=("$line")
  done <"$manifest_meta_file"
  rm -f "$manifest_meta_file"

  manifest_integrity_file="$(mktemp)"
  bundle_manifest_matches_files "$MANIFEST_SOURCE" "$FILES_SOURCE" >"$manifest_integrity_file"
  manifest_integrity=()
  while IFS= read -r line; do
    manifest_integrity+=("$line")
  done <"$manifest_integrity_file"
  rm -f "$manifest_integrity_file"
  manifest_matches_files="${manifest_integrity[0]:-false}"

  if [[ "$manifest_matches_files" != "true" && -z "${RELEASE_VERSION:-}" ]]; then
    echo "Bundle files no longer match $MANIFEST_SOURCE, so reusing its release version would be dishonest." >&2
    printf '%s\n' "${manifest_integrity[@]:1}" >&2
    echo "Set RELEASE_VERSION and RELEASE_PUBLISHED_AT explicitly for this republish." >&2
    exit 1
  fi

  if [[ -z "$release_version" && -n "${manifest_meta[0]:-}" ]]; then
    release_version="${manifest_meta[0]}"
  fi
  if [[ -z "$release_channel" && -n "${manifest_meta[1]:-}" ]]; then
    release_channel="${manifest_meta[1]}"
  fi
  if [[ -z "$release_published_at" && -n "${manifest_meta[2]:-}" ]]; then
    release_published_at="${manifest_meta[2]}"
  fi
fi

release_version="${release_version:-unpublished}"
release_channel="${release_channel:-docker}"
release_published_at="${release_published_at:-$default_published_at}"
live_downloads_mirror_dirs=()
discover_live_downloads_mirror_dirs

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
CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS="${CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS:-}" \
CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-false}" \
CHUMMER_EXTERNAL_PROOF_BASE_URL="${CHUMMER_EXTERNAL_PROOF_BASE_URL:-https://chummer.run}" \
bash "$SCRIPT_DIR/generate-releases-manifest.sh"

promoted_file_names=()
while IFS= read -r file_name; do
  [[ -n "$file_name" ]] || continue
  promoted_file_names+=("$file_name")
done < <(python3 - "$DEPLOY_DIR/RELEASE_CHANNEL.generated.json" <<'PY'
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
     -name "chummer-blazor-desktop-*-installer.dmg" -o -name "chummer-blazor-desktop-*-installer.msix" -o \
     -name "chummer-6-*.exe" -o -name "chummer-6-*.zip" -o -name "chummer-6-*.tar.gz" -o -name "chummer-6-*-installer.exe" -o \
     -name "chummer-6-*-installer.deb" -o \
     -name "chummer-6-*-installer.pkg" -o -name "chummer-6-*-installer.dmg" -o \
     -name "chummer-6-*-installer.msix" \) \
  -delete

for file_name in "${promoted_file_names[@]}"; do
  source_path="$sync_source_dir/$file_name"
  if [[ ! -f "$source_path" ]]; then
    echo "promoted artifact missing from bundle source: $source_path" >&2
    exit 1
  fi
  cp "$source_path" "$DEPLOY_DIR/files/"
done

for mirror_dir in "${live_downloads_mirror_dirs[@]:-}"; do
  sync_live_downloads_mirror_dir "$mirror_dir" "public-edge"
done

if [[ -d "$STARTUP_SMOKE_SOURCE" ]]; then
  verified_startup_smoke_tmp="$(mktemp)"
  if ! python3 - "$DEPLOY_DIR/RELEASE_CHANNEL.generated.json" "$STARTUP_SMOKE_SOURCE" "$DEPLOY_DIR/files" >"$verified_startup_smoke_tmp" <<'PY'
import os
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PASSING_STATUSES = {"pass", "passed", "ready"}
INSTALL_MEDIA_KINDS = {"installer", "dmg", "pkg", "msix"}
STARTUP_SMOKE_MAX_AGE_SECONDS = int(
    os.environ.get("CHUMMER_PUBLISH_STARTUP_SMOKE_MAX_AGE_SECONDS")
    or os.environ.get("CHUMMER_DESKTOP_STARTUP_SMOKE_MAX_AGE_SECONDS")
    or "604800"
)
STARTUP_SMOKE_MAX_FUTURE_SKEW_SECONDS = int(
    os.environ.get("CHUMMER_PUBLISH_STARTUP_SMOKE_MAX_FUTURE_SKEW_SECONDS")
    or os.environ.get("CHUMMER_DESKTOP_STARTUP_SMOKE_MAX_FUTURE_SKEW_SECONDS")
    or "300"
)
PUBLIC_SKIP_STARTUP_SMOKE_FILTER = (
    str(os.environ.get("CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER") or "").strip().lower()
    in {"1", "true", "yes", "on"}
)

release_channel_path = Path(sys.argv[1])
startup_smoke_root = Path(sys.argv[2])
files_root = Path(sys.argv[3])

payload = json.loads(release_channel_path.read_text(encoding="utf-8-sig"))
artifacts = payload.get("artifacts") or []
errors: list[str] = []
verified_receipts: list[str] = []
seen: set[str] = set()

def normalize(value: Any) -> str:
    return str(value or "").strip().lower()

def expected_host_class_platform_tokens(platform: str) -> tuple[str, ...]:
    normalized = normalize(platform)
    if normalized == "windows":
        return ("win", "windows")
    if normalized == "macos":
        return ("osx", "macos")
    if normalized == "linux":
        return ("linux",)
    return (normalized,) if normalized else ()

def host_class_matches_platform(host_class: str, platform: str) -> bool:
    normalized_host = normalize(host_class)
    expected_tokens = expected_host_class_platform_tokens(platform)
    if not normalized_host or not expected_tokens:
        return False
    host_tokens = [token for token in normalized_host.split("-") if token]
    return any(token in host_tokens for token in expected_tokens)

def rid_to_arch(rid: str) -> str:
    token = normalize(rid)
    if token.startswith("win-") or token.startswith("linux-") or token.startswith("osx-"):
        _, _, arch = token.partition("-")
        return arch
    return token

def parse_iso_utc(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

for artifact in artifacts:
    if not isinstance(artifact, dict):
        continue
    kind = normalize(artifact.get("kind"))
    if kind not in INSTALL_MEDIA_KINDS:
        continue
    head = normalize(artifact.get("head"))
    platform = normalize(artifact.get("platform"))
    rid = normalize(artifact.get("rid"))
    file_name = str(artifact.get("fileName") or "").strip()
    if not head or not platform or not rid or not file_name:
        errors.append(f"promoted install-medium artifact is missing required tuple fields (head/platform/rid/fileName): {artifact}")
        continue
    receipt_name = f"startup-smoke-{head}-{rid}.receipt.json"
    if receipt_name in seen:
        continue
    seen.add(receipt_name)
    receipt_path = startup_smoke_root / receipt_name
    if not receipt_path.is_file():
        errors.append(f"startup-smoke receipt missing for promoted install medium {head}/{platform}/{rid}: {receipt_name}")
        continue
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # pragma: no cover - shell guard
        errors.append(f"startup-smoke receipt is unreadable for promoted install medium {head}/{platform}/{rid}: {receipt_path} ({exc})")
        continue
    status = normalize(receipt.get("status"))
    if status not in PASSING_STATUSES:
        errors.append(f"startup-smoke receipt status is not passing for promoted install medium {head}/{platform}/{rid}: {status or 'missing'}")
    checkpoint = normalize(receipt.get("readyCheckpoint"))
    if checkpoint != "pre_ui_event_loop":
        errors.append(f"startup-smoke receipt readyCheckpoint is not pre_ui_event_loop for promoted install medium {head}/{platform}/{rid}.")
    receipt_head = normalize(receipt.get("headId"))
    receipt_platform = normalize(receipt.get("platform"))
    receipt_arch = normalize(receipt.get("arch"))
    receipt_rid = normalize(receipt.get("rid"))
    receipt_host_class = normalize(receipt.get("hostClass"))
    receipt_operating_system = str(receipt.get("operatingSystem") or "").strip()
    expected_arch = rid_to_arch(rid)
    if receipt_head != head:
        errors.append(f"startup-smoke receipt headId mismatch for promoted install medium {head}/{platform}/{rid}: {receipt_head or 'missing'}")
    if receipt_platform != platform:
        errors.append(f"startup-smoke receipt platform mismatch for promoted install medium {head}/{platform}/{rid}: {receipt_platform or 'missing'}")
    if not receipt_host_class:
        errors.append(f"startup-smoke receipt hostClass is missing for promoted install medium {head}/{platform}/{rid}.")
    elif not host_class_matches_platform(receipt_host_class, platform):
        errors.append(f"startup-smoke receipt hostClass does not identify the {platform} host for promoted install medium {head}/{platform}/{rid}.")
    if not receipt_operating_system:
        errors.append(f"startup-smoke receipt operatingSystem is missing for promoted install medium {head}/{platform}/{rid}.")
    if expected_arch and receipt_arch != expected_arch:
        errors.append(f"startup-smoke receipt arch mismatch for promoted install medium {head}/{platform}/{rid}: {receipt_arch or 'missing'}")
    if not receipt_rid:
        errors.append(f"startup-smoke receipt rid is missing for promoted install medium {head}/{platform}/{rid}.")
    elif receipt_rid != rid:
        errors.append(f"startup-smoke receipt rid mismatch for promoted install medium {head}/{platform}/{rid}: {receipt_rid}")
    promoted_file_path = files_root / file_name
    expected_sha = normalize(artifact.get("sha256"))
    if promoted_file_path.is_file():
        expected_sha = hashlib.sha256(promoted_file_path.read_bytes()).hexdigest().lower()
    expected_digest = f"sha256:{expected_sha}" if expected_sha else ""
    receipt_digest = normalize(receipt.get("artifactDigest"))
    if expected_digest and receipt_digest != expected_digest:
        errors.append(f"startup-smoke receipt artifactDigest mismatch for promoted install medium {head}/{platform}/{rid}.")
    recorded_at_raw = (
        receipt.get("completedAtUtc")
        or receipt.get("recordedAtUtc")
        or receipt.get("startedAtUtc")
    )
    recorded_at = parse_iso_utc(recorded_at_raw)
    if recorded_at is None:
        errors.append(
            f"startup-smoke receipt timestamp is missing/invalid for promoted install medium {head}/{platform}/{rid}."
        )
    else:
        now_utc = datetime.now(timezone.utc)
        age_delta_seconds = int((now_utc - recorded_at).total_seconds())
        if age_delta_seconds < 0:
            future_skew_seconds = abs(age_delta_seconds)
            if future_skew_seconds > STARTUP_SMOKE_MAX_FUTURE_SKEW_SECONDS:
                errors.append(
                    "startup-smoke receipt timestamp is in the future for promoted install medium "
                    f"{head}/{platform}/{rid}: {future_skew_seconds}s ahead (max {STARTUP_SMOKE_MAX_FUTURE_SKEW_SECONDS}s)."
                )
        elif age_delta_seconds > STARTUP_SMOKE_MAX_AGE_SECONDS and not PUBLIC_SKIP_STARTUP_SMOKE_FILTER:
            errors.append(
                "startup-smoke receipt is stale for promoted install medium "
                f"{head}/{platform}/{rid}: {age_delta_seconds}s old (max {STARTUP_SMOKE_MAX_AGE_SECONDS}s)."
            )
    verified_receipts.append(str(receipt_path))

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    raise SystemExit(1)

for verified in sorted(verified_receipts):
    print(verified)
PY
  then
    rm -f "$verified_startup_smoke_tmp"
    exit 1
  fi
  verified_startup_smoke_receipts=()
  while IFS= read -r receipt_path; do
    [[ -n "$receipt_path" ]] || continue
    verified_startup_smoke_receipts+=("$receipt_path")
  done <"$verified_startup_smoke_tmp"
  rm -f "$verified_startup_smoke_tmp"

  startup_smoke_deploy_dir="$DEPLOY_DIR/startup-smoke"
  startup_smoke_stage_dir="$(mktemp -d)"
  startup_smoke_deploy_dir_real="$(realpath -m "$startup_smoke_deploy_dir")"
  deploy_files_dir_real="$(realpath -m "$DEPLOY_DIR/files")"
  mkdir -p "$startup_smoke_deploy_dir"
  startup_smoke_fallback_dir="$PORTAL_DOWNLOADS_DIR/startup-smoke"
  run_services_startup_smoke_dir="$REPO_ROOT/../chummer.run-services/Chummer.Portal/downloads/startup-smoke"
  python3 - "$startup_smoke_stage_dir" "$startup_smoke_deploy_dir_real" "$deploy_files_dir_real" "$release_channel" "$release_version" "$startup_smoke_fallback_dir" "$run_services_startup_smoke_dir" "${verified_startup_smoke_receipts[@]}" <<'PY'
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

stage_root = Path(sys.argv[1])
final_root = Path(sys.argv[2])
files_root = Path(sys.argv[3])
release_channel = str(sys.argv[4]).strip()
release_version = str(sys.argv[5]).strip()
fallback_roots = [Path(item) for item in sys.argv[6:8] if str(item).strip()]
receipt_paths = [Path(item) for item in sys.argv[8:]]


def resolve_companion(source_root: Path, value: object) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    token = Path(raw)
    candidates: list[Path] = []
    if token.is_absolute():
        candidates.append(token)
    else:
        candidates.append(source_root / token)
    candidates.append(source_root / token.name)
    for fallback_root in fallback_roots:
        candidates.append(fallback_root / token.name)

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve(strict=False)
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    return None


def copy_companion(source_root: Path, value: object) -> str:
    source_path = resolve_companion(source_root, value)
    if source_path is None:
        return ""

    stage_path = stage_root / source_path.name
    final_path = final_root / source_path.name
    if source_path.resolve() != stage_path.resolve():
        shutil.copy2(source_path, stage_path)
    return str(final_path)


def rewrite_install_verification(stage_verification_path: Path, source_root: Path) -> None:
    payload = json.loads(stage_verification_path.read_text(encoding="utf-8-sig"))
    for key in (
        "dpkgLogPath",
        "installedLaunchCapturePath",
        "wrapperCapturePath",
        "desktopEntryCapturePath",
    ):
        copied = copy_companion(source_root, payload.get(key))
        if copied:
            payload[key] = copied
    stage_verification_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


for receipt_path in receipt_paths:
    source_root = receipt_path.parent
    payload = json.loads(receipt_path.read_text(encoding="utf-8-sig"))

    if release_channel:
        payload["channelId"] = release_channel
        payload["channel"] = release_channel
    if release_version:
        payload["releaseVersion"] = release_version
        payload["version"] = release_version

    verification_dest = copy_companion(source_root, payload.get("artifactInstallVerificationPath"))
    if verification_dest:
        payload["artifactInstallVerificationPath"] = verification_dest
        rewrite_install_verification(stage_root / Path(verification_dest).name, source_root)

    for key in (
        "artifactInstallDpkgLogPath",
        "artifactInstallLaunchCapturePath",
        "artifactInstallWrapperCapturePath",
        "artifactInstallDesktopEntryCapturePath",
    ):
        copied = copy_companion(source_root, payload.get(key))
        if copied:
            payload[key] = copied

    artifact_name = Path(str(payload.get("artifactPath") or "").strip()).name
    if artifact_name:
        published_artifact = files_root / artifact_name
        if published_artifact.is_file():
            payload["artifactPath"] = str(published_artifact)

    (stage_root / receipt_path.name).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
PY
  find "$startup_smoke_deploy_dir" -maxdepth 1 -type f \( \
    -name "startup-smoke-*.receipt.json" -o \
    -name "install-verification-*.json" -o \
    -name "dpkg-*.log" -o \
    -name "installed-launch-*" -o \
    -name "installed-wrapper-*" -o \
    -name "installed-desktop-entry-*" \
  \) -exec rm -f -- {} +
  if find "$startup_smoke_stage_dir" -mindepth 1 -maxdepth 1 -type f | grep -q .; then
    cp "$startup_smoke_stage_dir"/* "$startup_smoke_deploy_dir"/
  fi
  rm -rf "$startup_smoke_stage_dir"
fi

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

echo "Published ${#promoted_file_names[@]} desktop artifact(s) into $DEPLOY_DIR"
