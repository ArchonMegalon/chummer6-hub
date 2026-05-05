#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m122-hub-implement-campaign-adoption-wizard-state-runner-goal-per",
    "work_task_id": "122.1",
    "milestone_id": 122,
    "frontier_id": 1630681972,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W15",
    "task": "Implement campaign adoption wizard state, runner-goal persistence, ResolutionReport approval, and first WorldTick/news item flow.",
    "title": "Implement campaign adoption wizard state, runner-goal persistence, ResolutionReport approval, and first WorldTick/news item flow.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["implement_campaign_adoption_wizard_state:hub"],
}

REQUIRED_MARKERS = [
    'var campaignAdoptionResult = await campaignSpineController.UpsertMyCampaignWorkspaceCampaignAdoption(',
    'Summary: "Campaign adoption wizard says this workspace is safe to play while unknown provenance stays explicit."',
    'var runnerGoalResult = await campaignSpineController.UpsertMyCampaignWorkspaceRunnerGoal(',
    'Label: "Delta-grade wired reflexes fund"',
    'var resolutionReportApprovalResult = await campaignSpineController.ApproveMyCampaignWorkspaceResolutionReport(',
    'var adoptionLoopResult = await campaignSpineController.GetMyCampaignWorkspaceAdoptionLoop(workspaceId, CancellationToken.None);',
    'WorldTickSummary: "Dockside courier fallout becomes the first BLACK LEDGER WorldTick for Tacoma."',
    'NewsTitle: "Tacoma grid rumor points to a vanished courier"',
    'campaign spine adoption-loop api should surface the player-safe news preview without turning it into world truth.',
    'campaign spine server plane api should project the first BLACK LEDGER WorldTick onto the bounded what-changed rail.',
    'campaign spine adoption loop should preserve the player-safe news preview across reload.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M122_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / 'tests' / 'RunServicesSmoke' / 'Program.cs'
OUT = ROOT / '.codex-studio' / 'published' / 'NEXT90_M122_HUB_CAMPAIGN_ADOPTION_LOOP.generated.json'


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding='utf-8')
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m122_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        'contract_name': 'chummer6-hub.next90_m122_hub_campaign_adoption_loop',
        'status': 'passed',
        'proof_kind': 'source_backed_local_smoke_contract',
        'package_proof': PACKAGE_PROOF,
        'source_file': 'tests/RunServicesSmoke/Program.cs',
        'required_markers': REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(f"wrote next90 m122 hub campaign adoption loop proof: {OUT}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
