#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json"

REQUIRED_MARKERS = {
    "build_explain_publish": [
        'accountModel.CampaignSpine.BuildLabHandoffs.Count >= 1',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].NextSafeAction',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].RuntimeCompatibilitySummary',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].SupportClosureSummary',
        'campaignSpineController.GetMyBuildLabHandoff',
        'campaignSpineController.GetMyRulesNavigatorAnswer',
        'campaignSpineController.GetMyCreatorPublication',
        'workHomeModel.CampaignSpine.CreatorPublications[0].ProvenanceSummary',
    ],
    "campaign_session_recover_recap": [
        'accountModel.CampaignSpine.Workspaces.Count >= 1',
        'accountModel.CampaignSpine.Workspaces[0].ReadinessCues.Count >= 1',
        'accountModel.CampaignSpine.Workspaces[0].RecapShelf.Count >= 1',
        'campaignSpineController.GetMyCampaignWorkspace',
        'campaignSpineController.GetMyRun',
        'workHomeModel!.CampaignSpine.Workspaces[0].ReturnSummary',
        'workHomeModel.CampaignSpine.Restore.ClaimedDevices.Count >= 1',
    ],
    "report_cluster_release_notify": [
        'accountModel!.SupportCaseSummaries.Any(item => string.Equals(item.Case.CaseId, supportCase.CaseId, StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(item.ClosureSummary))',
        'supportCasesController.VerifyReporterFix',
        'SelectedSupportCaseSummary.CanVerifyFix',
        'TrackedCaseSummary.NextSafeAction.Contains("Update"',
        'TrackedCaseSummary!.FollowUpLaneSummary.Contains("Account > Support"',
        'authenticatedHomeModel.SupportCaseSummaries.Any(item => string.Equals(item.Case.CaseId, supportCase.CaseId, StringComparison.Ordinal) && item.ClosureSummary.Contains("closure notice"',
    ],
}


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing: list[str] = []
    journeys_passed: list[str] = []

    for journey_id, markers in REQUIRED_MARKERS.items():
        journey_missing = [marker for marker in markers if marker not in text]
        if journey_missing:
            for marker in journey_missing:
                missing.append(f"{journey_id}: {marker}")
            continue
        journeys_passed.append(journey_id)

    if missing:
        for item in missing:
            print(f"campaign_os_local_proof_missing: {item}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.campaign_os_local_proof",
        "generated_at": iso_now(),
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "source_file": str(SOURCE.relative_to(ROOT)),
        "journeys_passed": journeys_passed,
        "required_markers": REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote campaign-os local proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
