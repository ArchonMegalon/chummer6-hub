#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$script_dir/_env.sh" ]]; then
  source "$script_dir/_env.sh"
fi

ROOT_DIR="$(cd "$script_dir/../.." && pwd)"
cd "$ROOT_DIR"

resolve_writable_tmp_root() {
  local candidate=""
  for candidate in \
    "${TMPDIR:-}" \
    "$ROOT_DIR/.tmp" \
    "/tmp"
  do
    [[ -n "$candidate" ]] || continue
    mkdir -p "$candidate" 2>/dev/null || true
    if [[ -d "$candidate" && -w "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

TMP_ROOT="$(resolve_writable_tmp_root)"

BASE_URL="${CHUMMER_FLAGSHIP_PUBLIC_EDGE_BASE_URL:-https://chummer.run}"
OUTPUT_DIR="${CHUMMER_FLAGSHIP_PUBLIC_EDGE_OUTPUT_DIR:-}"
TIMEOUT_SECONDS="${CHUMMER_FLAGSHIP_PUBLIC_EDGE_TIMEOUT_SECONDS:-240}"
SKIP_PREFLIGHT_OVERRIDE="${CHUMMER_FLAGSHIP_PUBLIC_EDGE_SKIP_PREFLIGHT:-auto}"
INCLUDE_HORIZONS="${CHUMMER_FLAGSHIP_PUBLIC_EDGE_INCLUDE_HORIZONS:-1}"
RELEASE_CHANNEL_RECEIPT="${CHUMMER_FLAGSHIP_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT:-$ROOT_DIR/../chummer-hub-registry/.codex-studio/published/RELEASE_CHANNEL.generated.json}"
EXPECTED_BUILD_INFO="${CHUMMER_FLAGSHIP_PUBLIC_EDGE_EXPECTED_BUILD_INFO:-${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:-$ROOT_DIR/.state/public-edge-portal-overlay/app}/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json}"
EXPECTED_PWA_ASSET_INVENTORY_SHA256="${CHUMMER_FLAGSHIP_PUBLIC_EDGE_EXPECTED_PWA_ASSET_INVENTORY_SHA256:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="${2:?--base-url requires a value}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?--output-dir requires a value}"
      shift 2
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="${2:?--timeout-seconds requires a value}"
      shift 2
      ;;
    --expected-build-info)
      EXPECTED_BUILD_INFO="${2:?--expected-build-info requires a value}"
      shift 2
      ;;
    --expected-pwa-asset-inventory-sha256)
      EXPECTED_PWA_ASSET_INVENTORY_SHA256="${2:?--expected-pwa-asset-inventory-sha256 requires a value}"
      shift 2
      ;;
    --skip-preflight)
      SKIP_PREFLIGHT_OVERRIDE="true"
      shift
      ;;
    --include-horizons)
      INCLUDE_HORIZONS="1"
      shift
      ;;
    --skip-horizons)
      INCLUDE_HORIZONS="0"
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# The build-info lives at <overlay>/.codex-studio/runtime/<file>. Derive the same
# overlay root that the trusted digest loader validates and pass it to postdeploy;
# otherwise a custom --expected-build-info could be cross-checked against the
# unrelated environment/default overlay.
EXPECTED_OVERLAY_ROOT="$(dirname -- "$(dirname -- "$(dirname -- "$EXPECTED_BUILD_INFO")")")"

to_bool() {
  local value=""
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

default_skip_preflight() {
  printf 'false\n'
}

if [[ -z "$OUTPUT_DIR" ]]; then
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT_DIR="${TMP_ROOT}/flagship-public-edge-verification-${stamp}"
fi
mkdir -p "$OUTPUT_DIR"

POSTDEPLOY_ARTIFACT_DIR="$OUTPUT_DIR/public-edge-browser-proofs"
DOWNLOADS_BROWSER_DIR="$POSTDEPLOY_ARTIFACT_DIR/downloads-status"
MOBILE_VIEWPORT_DIR="$POSTDEPLOY_ARTIFACT_DIR/mobile-viewport"
OFFLINE_CACHE_DIR="$POSTDEPLOY_ARTIFACT_DIR/offline-cache"
FRONTDOOR_DIR="$POSTDEPLOY_ARTIFACT_DIR/frontdoor-navigation"
mkdir -p "$DOWNLOADS_BROWSER_DIR" "$MOBILE_VIEWPORT_DIR" "$OFFLINE_CACHE_DIR" "$FRONTDOOR_DIR"

SKIP_PREFLIGHT="$(default_skip_preflight "$BASE_URL")"
if [[ "$SKIP_PREFLIGHT_OVERRIDE" != "auto" ]]; then
  SKIP_PREFLIGHT="$SKIP_PREFLIGHT_OVERRIDE"
fi

if to_bool "$INCLUDE_HORIZONS"; then
  python3 scripts/verify_all_horizons_preview_routes.py
  HORIZON_COMPLETION_DIR="$ROOT_DIR/../_completion/all_horizons_missed_potential"
  HORIZON_OUTPUT_DIR="$OUTPUT_DIR/horizons"
  mkdir -p "$HORIZON_OUTPUT_DIR"
  for file_name in \
    HORIZON_STATUS_MATRIX.generated.yaml \
    FINAL_ALL_HORIZONS_FLAGSHIP_VERDICT.md \
    ALL_HORIZONS_IMPLEMENTATION_REPORT.md \
    FRONT_DOOR_TRUST_VERDICT.md
  do
    if [[ -f "$HORIZON_COMPLETION_DIR/$file_name" ]]; then
      cp "$HORIZON_COMPLETION_DIR/$file_name" "$HORIZON_OUTPUT_DIR/$file_name"
    fi
  done
fi

EXPECTED_FULL_DEPLOYMENT_DIGEST_SHA256="$(
  python3 - "$EXPECTED_BUILD_INFO" "$ROOT_DIR" <<'PY'
import os
from pathlib import Path
import sys

from scripts.verify_public_edge_postdeploy_gate import (
    load_expected_full_deployment_digest,
)

build_info_path = Path(os.path.abspath(os.fspath(Path(sys.argv[1]).expanduser())))
source_root = Path(
    os.environ.get("CHUMMER_RUN_SERVICES_SOURCE") or sys.argv[2]
)
sys.stdout.write(
    load_expected_full_deployment_digest(
        build_info_path,
        source_root=source_root,
        overlay_root=build_info_path.parents[2],
    )
)
PY
)"

python3 scripts/verify_mobile_pwa_ledger_boundary.py \
  --base-url "$BASE_URL" \
  --timeout-seconds "$TIMEOUT_SECONDS" \
  --output "$OUTPUT_DIR/MOBILE_PWA_LEDGER_BOUNDARY.generated.json"

python3 scripts/verify_ready_mobile_handoff_contract.py \
  --base-url "$BASE_URL" \
  --timeout-seconds "$TIMEOUT_SECONDS" \
  --output "$OUTPUT_DIR/READY_MOBILE_HANDOFF.generated.json"

python3 scripts/verify_participate_iframe_shell.py \
  --base-url "$BASE_URL" \
  --timeout-seconds "$TIMEOUT_SECONDS" \
  --output "$OUTPUT_DIR/PARTICIPATE_IFRAME_SHELL.generated.json"

python3 scripts/verify_live_surface_parity.py \
  --base-url "$BASE_URL" \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --output "$OUTPUT_DIR/LIVE_SURFACE_PARITY.generated.json"

postdeploy_args=(
  --base-url "$BASE_URL"
  --timeout-seconds "$TIMEOUT_SECONDS"
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT"
  --overlay-root "$EXPECTED_OVERLAY_ROOT"
  --expected-build-info "$EXPECTED_BUILD_INFO"
  --expected-full-deployment-digest-sha256 "$EXPECTED_FULL_DEPLOYMENT_DIGEST_SHA256"
  --require-downloads-status-playwright
  --playwright-artifact-dir "$DOWNLOADS_BROWSER_DIR"
  --require-mobile-pwa-viewport-playwright
  --mobile-pwa-viewport-artifact-dir "$MOBILE_VIEWPORT_DIR"
  --require-pwa-offline-cache-playwright
  --pwa-offline-cache-artifact-dir "$OFFLINE_CACHE_DIR"
  --require-frontdoor-navigation-playwright
  --frontdoor-navigation-artifact-dir "$FRONTDOOR_DIR"
  --output "$OUTPUT_DIR/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
)
if to_bool "$SKIP_PREFLIGHT"; then
  if [[ ! "$EXPECTED_PWA_ASSET_INVENTORY_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
    echo "Skipping preflight requires a sealed expected PWA asset inventory SHA-256." >&2
    exit 2
  fi
  postdeploy_args+=(--skip-preflight)
  postdeploy_args+=(--expected-pwa-asset-inventory-sha256 "$EXPECTED_PWA_ASSET_INVENTORY_SHA256")
fi

python3 scripts/verify_public_edge_postdeploy_gate.py "${postdeploy_args[@]}"

python3 - "$OUTPUT_DIR/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json" "$OUTPUT_DIR/PUBLIC_PWA_STATIC_ASSETS.generated.json" <<'PY'
import json
import sys
from pathlib import Path

postdeploy_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
postdeploy = json.loads(postdeploy_path.read_text(encoding="utf-8"))
children = postdeploy.get("childReceipts")
pwa = children.get("pwaStatic") if isinstance(children, dict) else None
if not isinstance(pwa, dict):
    raise SystemExit("postdeploy receipt does not contain the PWA static child receipt")
output_path.write_text(json.dumps(pwa, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

python3 - "$OUTPUT_DIR" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
paths = [
    output_dir / "PUBLIC_PWA_STATIC_ASSETS.generated.json",
    output_dir / "MOBILE_PWA_LEDGER_BOUNDARY.generated.json",
    output_dir / "READY_MOBILE_HANDOFF.generated.json",
    output_dir / "PARTICIPATE_IFRAME_SHELL.generated.json",
    output_dir / "LIVE_SURFACE_PARITY.generated.json",
    output_dir / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
]

print(f"flagship public-edge verification receipts: {output_dir}")
for path in paths:
    if not path.is_file():
        print(f"- {path.name}: missing")
        continue
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(f"- {path.name}: {payload.get('status', '<missing>')}")
PY
