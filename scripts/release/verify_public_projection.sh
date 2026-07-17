#!/usr/bin/env bash
set -euo pipefail
public_base="${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}"
(
  cd /docker/chummercomplete/chummer.run-services
  python3 scripts/materialize_hub_local_release_proof.py \
    .codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json \
    "$public_base" \
    docker-compose.yml \
    120 \
    true
) >/dev/null
python3 /docker/chummercomplete/chummer.run-services/scripts/verify_next90_m120_hub_public_launch_health.py >/dev/null
python3 /docker/chummercomplete/chummer.run-services/scripts/verify_next90_m125_hub_public_signal_packets.py >/dev/null
python3 /docker/chummercomplete/chummer.run-services/scripts/verify_next90_m126_hub_hosted_proof_contracts.py >/dev/null
python3 /docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py >/dev/null
python3 /docker/chummercomplete/chummer.run-services/scripts/verify_next90_m144_hub_release_truth_alignment.py >/dev/null
python3 /docker/chummercomplete/chummer.run-services/scripts/verify_live_public_windows_installer.py >/dev/null
echo "public projection ok"
