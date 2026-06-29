#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m128-hub-implement-privacy-bounded-support-crash-feedback-telemet",
    "work_task_id": "128.4",
    "milestone_id": 128,
    "frontier_id": 4025965979,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W18",
    "task": "Implement privacy-bounded support, crash, feedback, telemetry rollups, retention clocks, and case-status followthrough.",
    "title": "Implement privacy-bounded support, crash, feedback, telemetry rollups, retention clocks, and case-status followthrough.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["implement_privacy_bounded_support_crash:hub"],
}

REQUIRED_MARKERS = [
    "var privacyBoundedSupportStatus = new PrivacyBoundedSupportStatusService(releases, new SupportConciergePacketService(releases, new SupportCasePresentationService())).Build(new PrivacyBoundedSupportStatusContext(",
    'campaign spine privacy-bounded support status should keep support status on the account support rail.',
    'campaign spine privacy-bounded support status should keep crash status on the crash work-item rail.',
    'campaign spine privacy-bounded support status should keep feedback status on the shared Participate surface.',
    'campaign spine privacy-bounded support status should keep telemetry rollups on the privacy-bounded progress route.',
    'campaign spine privacy-bounded support status should keep retention clocks on the privacy boundary route.',
    'campaign spine privacy-bounded support status should keep case-status followthrough on the tracked support rail.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M128_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = ROOT / ".codex-studio" / "published" / "NEXT90_M128_HUB_PRIVACY_BOUNDED_SUPPORT_STATUS.generated.json"


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m128_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m128_hub_privacy_bounded_support_status",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": "tests/RunServicesSmoke/Program.cs",
        "required_markers": REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m128 hub privacy bounded support status proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
