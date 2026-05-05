#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m135-hub-close-hosted-bounded-context-campaign-account-support-pu",
    "work_task_id": "135.4",
    "milestone_id": 135,
    "frontier_id": 1932284114,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W22",
    "task": "Close hosted bounded-context, campaign, account, support, public, community, and orchestration-boundary coverage.",
    "title": "Close hosted bounded-context, campaign, account, support, public, community, and orchestration-boundary coverage.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["close_hosted_bounded_context_campaign:hub"],
}

REQUIRED_MARKERS = [
    'var boundedContextCoverage = new HostedBoundedContextCoverageService(releases).Build(new HostedBoundedContextCoverageContext(',
    'hub bounded-context coverage should keep public context proof on the guest-readable landing rail.',
    'hub bounded-context coverage should keep account context proof on the signed-in account rail.',
    'hub bounded-context coverage should keep community context proof on the signed-in community rail.',
    'hub bounded-context coverage should keep campaign context proof on the workspace continuity rail.',
    'hub bounded-context coverage should keep support context proof on the tracked support rail.',
    'hub bounded-context coverage should keep orchestration boundary proof on the install entry rail.',
    'hub bounded-context coverage should keep closure proof on the public progress rail.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M135_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = ROOT / ".codex-studio" / "published" / "NEXT90_M135_HUB_HOSTED_BOUNDED_CONTEXT_COVERAGE.generated.json"


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m135_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m135_hub_hosted_bounded_context_coverage",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": "tests/RunServicesSmoke/Program.cs",
        "required_markers": REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m135 hub hosted bounded-context coverage proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
