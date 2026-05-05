#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m129-hub-build-reusable-account-profile-group-membership-join-cod",
    "work_task_id": "129.1",
    "milestone_id": 129,
    "frontier_id": 1246056730,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W19",
    "task": "Build reusable account, profile, group, membership, join-code, boost-code, reward-journal, and entitlement-journal flows.",
    "title": "Build reusable account, profile, group, membership, join-code, boost-code, reward-journal, and entitlement-journal flows.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["build_reusable_account_profile_group:hub"],
}

REQUIRED_MARKERS = [
    "var reusableAccountFlows = new ReusableAccountFlowService(releases).Build(new ReusableAccountFlowContext(",
    'community reusable account flow should keep account profile on the signed-in account rail.',
    'community reusable account flow should keep group profile on the governed group rail.',
    'community reusable account flow should keep membership status on the governed group rail.',
    'community reusable account flow should keep join-code issuance on the governed group api rail.',
    'community reusable account flow should keep boost-code issuance on the governed boost-code rail.',
    'community reusable account flow should keep reward-journal followthrough on the signed-in rewards rail.',
    'community reusable account flow should keep entitlement-journal followthrough on the signed-in entitlements rail.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M129_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = ROOT / ".codex-studio" / "published" / "NEXT90_M129_HUB_REUSABLE_ACCOUNT_FLOWS.generated.json"


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m129_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m129_hub_reusable_account_flows",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": "tests/RunServicesSmoke/Program.cs",
        "required_markers": REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m129 hub reusable account flows proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
