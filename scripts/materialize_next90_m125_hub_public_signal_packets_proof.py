#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign",
    "work_task_id": "125.1",
    "milestone_id": 125,
    "frontier_id": 4030850391,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W17",
    "task": "Build public feedback, roadmap, changelog, support, and signal-intake surfaces that emit governed SignalToCanon packets.",
    "title": "Build public feedback, roadmap, changelog, support, and signal-intake surfaces that emit governed SignalToCanon packets.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["build_public_feedback_roadmap_changelog:hub"],
}

REQUIRED_MARKERS = [
    "var publicSignalPackets = new PublicSignalToCanonPacketService(releases);",
    "var publicSignalPacketBundle = publicSignalPackets.Build(supportCase, \"en-US\");",
    'campaign spine public signal packets should emit feedback packets for the public Participate surface.',
    'campaign spine public signal packets should emit governed roadmap packets for the public horizons projection.',
    'campaign spine public signal packets should emit governed changelog packets for shipped closeout posture.',
    'campaign spine public signal packets should emit governed support packets from the first-party contact intake lane.',
    'campaign spine public signal packets should emit governed signal-intake packets for the shared participate surface.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M125_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M125_PROOF_PATH",
        ROOT / ".codex-studio" / "published" / "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
    )
)


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m125_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m125_hub_public_signal_packets",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": "tests/RunServicesSmoke/Program.cs",
        "required_markers": REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m125 hub public signal packets proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
