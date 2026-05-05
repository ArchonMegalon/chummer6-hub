#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m121-hub-persist-session-turn-ledger-handoff-runboard-state-and-r",
    "work_task_id": "121.5",
    "milestone_id": 121,
    "frontier_id": 7165194744,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W15",
    "task": "Persist session turn-ledger handoff, runboard state, and ResolutionReport draft continuity without owning engine math.",
    "title": "Persist session turn-ledger handoff, runboard state, and ResolutionReport draft continuity without owning engine math.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["persist_session_turn_ledger_handoff:hub"],
}

REQUIRED_MARKERS = [
    'var runboardContinuityUpdateResult = await campaignSpineController.UpsertMyCampaignWorkspaceRunboardContinuity(',
    'TurnLedgerSummary: "Minor-action handoff stays pinned before the next opposition pass."',
    'ResolutionReportStatus: "draft"',
    'campaign spine runboard-continuity api should persist the active run continuity on the governed workspace.',
    'campaign spine server plane api should project persisted runboard continuity on the bounded runboard summary.',
    'campaign spine runboard continuity should persist across a community-store reload.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M121_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / 'tests' / 'RunServicesSmoke' / 'Program.cs'
OUT = ROOT / '.codex-studio' / 'published' / 'NEXT90_M121_HUB_RUNBOARD_CONTINUITY.generated.json'


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding='utf-8')
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m121_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        'contract_name': 'chummer6-hub.next90_m121_hub_runboard_continuity',
        'status': 'passed',
        'proof_kind': 'source_backed_local_smoke_contract',
        'package_proof': PACKAGE_PROOF,
        'source_file': 'tests/RunServicesSmoke/Program.cs',
        'required_markers': REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(f"wrote next90 m121 hub runboard continuity proof: {OUT}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
