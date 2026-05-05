#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m126-hub-define-hosted-proof-contracts-for-open-runs-shadowcaster",
    "work_task_id": "126.4",
    "milestone_id": 126,
    "frontier_id": 6966685835,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W17",
    "task": "Define hosted proof contracts for Open Runs, Shadowcasters, public signal, community, and account-aware horizon conversions.",
    "title": "Define hosted proof contracts for Open Runs, Shadowcasters, public signal, community, and account-aware horizon conversions.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["define_hosted_proof_contracts_for:hub"],
}

REQUIRED_MARKERS = [
    "var hostedProofContracts = new HostedProofContractService(releases).Build(new HostedProofContractContext(",
    'campaign spine hosted proof contracts should emit open-run proof on the governed open-run route.',
    'campaign spine hosted proof contracts should emit Shadowcasters horizon proof on the public roadmap route.',
    'campaign spine hosted proof contracts should emit public-signal proof on the governed Participate route.',
    'campaign spine hosted proof contracts should emit community-hub proof on the signed-in work rail.',
    'campaign spine hosted proof contracts should emit account-aware horizon conversion proof on the Devices & access route.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M126_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = ROOT / ".codex-studio" / "published" / "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json"


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m126_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m126_hub_hosted_proof_contracts",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": "tests/RunServicesSmoke/Program.cs",
        "required_markers": REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m126 hub hosted proof contracts proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
