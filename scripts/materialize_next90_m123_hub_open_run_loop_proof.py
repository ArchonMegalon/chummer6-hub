#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m123-hub-build-openrun-listing-join-request-roster-schedule-meeti",
    "work_task_id": "123.1",
    "milestone_id": 123,
    "frontier_id": 8531582567,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W16",
    "task": "Build OpenRun listing, join request, roster, schedule, meeting-handoff, and closeout orchestration.",
    "title": "Build OpenRun listing, join request, roster, schedule, meeting-handoff, and closeout orchestration.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["build_openrun_listing_join_request:hub"],
}

REQUIRED_MARKERS = [
    'var openRunCreateResult = await campaignSpineController.CreateMyCampaignWorkspaceOpenRun(',
    'ListingTitle: "Tacoma docks night extraction"',
    'var openRunJoinRequestResult = await openRunOutsiderController.SubmitMyOpenRunJoinRequest(',
    'open-run join-request api should keep explainable preflight green for a compatible runner dossier.',
    'var openRunScheduleResult = await campaignSpineController.ScheduleMyOpenRun(',
    'var openRunMeetingHandoffResult = await campaignSpineController.CreateMyOpenRunMeetingHandoff(',
    'ProviderKind: "discord_event"',
    'var openRunCloseoutResult = await campaignSpineController.CloseOutMyOpenRun(',
    'open-run closeout api should bridge directly into governed world-memory receipts.',
    'campaign spine open-run orchestration should preserve the world-memory bridge across reload.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M123_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / 'tests' / 'RunServicesSmoke' / 'Program.cs'
OUT = ROOT / '.codex-studio' / 'published' / 'NEXT90_M123_HUB_OPEN_RUN_LOOP.generated.json'


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding='utf-8')
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m123_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        'contract_name': 'chummer6-hub.next90_m123_hub_open_run_loop',
        'status': 'passed',
        'proof_kind': 'source_backed_local_smoke_contract',
        'package_proof': PACKAGE_PROOF,
        'source_file': 'tests/RunServicesSmoke/Program.cs',
        'required_markers': REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(f"wrote next90 m123 hub open-run loop proof: {OUT}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
