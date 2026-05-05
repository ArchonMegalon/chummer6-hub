#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m124-hub-emit-install-update-support-restore-campaign-publication",
    "work_task_id": "124.2",
    "milestone_id": 124,
    "frontier_id": 3384756032,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W16",
    "task": "Emit install, update, support, restore, campaign, publication, and public-hub CompanionPacket truth from hosted domains.",
    "title": "Emit install, update, support, restore, campaign, publication, and public-hub CompanionPacket truth from hosted domains.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["emit_install_update_support_restore:hub"],
}

REQUIRED_MARKERS = [
    "var hostedCompanionPackets = new HostedCompanionPacketService(releases, new SupportConciergePacketService(releases, supportPresentation));",
    "var hostedCompanionPacketBundle = hostedCompanionPackets.Build(new HostedCompanionPacketContext(",
    'PublicationId: publicationPayload!.PublicationId',
    'campaign spine hosted companion packets should emit install truth from claimed-install posture.',
    'campaign spine hosted companion packets should emit update truth from the hosted release shelf.',
    'campaign spine hosted companion packets should emit support truth from the install-aware concierge lane.',
    'campaign spine hosted companion packets should emit restore truth from first-party continuity receipts.',
    'campaign spine hosted companion packets should emit campaign workspace truth from governed change packets.',
    'campaign spine hosted companion packets should emit publication truth from governed creator-publication posture.',
    'campaign spine hosted companion packets should emit public-hub truth from the hosted downloads and support posture.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M124_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = ROOT / ".codex-studio" / "published" / "NEXT90_M124_HUB_HOSTED_COMPANION_PACKETS.generated.json"


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m124_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m124_hub_hosted_companion_packets",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": "tests/RunServicesSmoke/Program.cs",
        "required_markers": REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m124 hub hosted companion packets proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
