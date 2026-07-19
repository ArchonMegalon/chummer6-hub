#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/../.." && pwd -P)"
public_base="${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}"
release_channel_input="${CHUMMER_HUB_RELEASE_CHANNEL_PATH:-${CHUMMER_RELEASE_CHANNEL_PATH:-}}"
flagship_readiness_input="${CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH:-${CHUMMER_FLEET_FLAGSHIP_READINESS_PATH:-}}"

if [[ -z "$release_channel_input" ]]; then
  echo "public projection requires an explicit immutable release-channel handoff via CHUMMER_HUB_RELEASE_CHANNEL_PATH or CHUMMER_RELEASE_CHANNEL_PATH" >&2
  exit 2
fi
if [[ "$release_channel_input" = /* ]]; then
  release_channel_path="$release_channel_input"
else
  release_channel_path="${repo_root}/${release_channel_input}"
fi
if [[ ! -f "$release_channel_path" ]]; then
  echo "public projection release-channel handoff is missing: $release_channel_path" >&2
  exit 2
fi
if [[ -z "$flagship_readiness_input" ]]; then
  echo "public projection requires an explicit flagship-readiness handoff via CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH or CHUMMER_FLEET_FLAGSHIP_READINESS_PATH" >&2
  exit 2
fi
if [[ "$flagship_readiness_input" = /* ]]; then
  flagship_readiness_path="$flagship_readiness_input"
else
  flagship_readiness_path="${repo_root}/${flagship_readiness_input}"
fi
if [[ ! -f "$flagship_readiness_path" ]]; then
  echo "public projection flagship-readiness handoff is missing: $flagship_readiness_path" >&2
  exit 2
fi

export CHUMMER_HUB_RELEASE_CHANNEL_PATH="$release_channel_path"
export CHUMMER_NEXT90_M144_RELEASE_CHANNEL="$release_channel_path"
export CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH="$flagship_readiness_path"
export CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS=1

cd -- "$repo_root"
python3 scripts/materialize_hub_local_release_proof.py \
  .codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json \
  "$public_base" \
  docker-compose.yml \
  120 \
  true \
  >/dev/null
python3 scripts/verify_next90_m120_hub_public_launch_health.py >/dev/null
python3 scripts/verify_next90_m125_hub_public_signal_packets.py >/dev/null
python3 scripts/verify_next90_m126_hub_hosted_proof_contracts.py >/dev/null
python3 scripts/verify_desktop_native_trust_receipts.py >/dev/null
python3 scripts/verify_next90_m144_hub_release_truth_alignment.py >/dev/null
python3 scripts/verify_live_public_windows_installer.py >/dev/null
echo "public projection ok"
