#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_ROOT", DEFAULT_ROOT))
SOURCE = Path(
    os.environ.get(
        "CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_SOURCE",
        ROOT / "tests" / "RunServicesSmoke" / "Program.cs",
    )
)
OUT = Path(
    os.environ.get(
        "CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_OUT",
        ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json",
    )
)

REQUIRED_MARKERS = {
    "build_explain_publish": [
        'accountModel.CampaignSpine.BuildLabHandoffs.Count >= 1',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].NextSafeAction',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].RuntimeCompatibilitySummary',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].SupportClosureSummary',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].TradeoffLines[0].Contains("campaign-safe output"',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].ProgressionOutcomes[0].Contains("25 / 50 / 100 Karma checkpoints"',
        'accountModel.CampaignSpine.BuildLabHandoffs[0].ProgressionOutcomes[1].Contains("recap follow-through"',
        'campaignSpineController.GetMyBuildLabHandoff',
        'campaignSpineController.GetMyRulesNavigatorAnswer',
        'campaignSpineController.GetMyCreatorPublication',
        'workHomeModel.CampaignSpine.CreatorPublications[0].ProvenanceSummary',
    ],
    "campaign_session_recover_recap": [
        'accountModel.CampaignSpine.Workspaces.Count >= 1',
        'accountModel.CampaignSpine.Workspaces[0].ReadinessCues.Count >= 1',
        'accountModel.CampaignSpine.Workspaces[0].RecapShelf.Count >= 1',
        'accountModel.CampaignSpine.Workspaces[0].ActiveSceneSummary',
        'accountModel.CampaignSpine.Workspaces[0].NextSafeAction',
        'accountModel.CampaignSpine.Workspaces[0].ChangePackets?.Count >= 1',
        'campaignSpineController.GetMyCampaignWorkspace',
        'campaignSpineController.GetMyRun',
        'workspacePayload?.ActiveSceneSummary',
        'workspacePayload?.NextSafeAction',
        'workspacePayload?.ChangePackets?.Count >= 1',
        'workspaceServerPlanePayload.WorkspaceState.Status',
        'workspaceServerPlanePayload.PrepLibrary.Packets.Count >= 3',
        'workspaceServerPlanePayload.TravelMode.TravelReadyDeviceCount >= 1',
        'campaignSpineController.GetMyCampaignWorkspacePrepLibrary',
        'prepLibraryPayload.TotalCount >= 1',
        'accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.WorkspaceState.Label',
        'accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.PrepLibrary.Packets.Count >= 3',
        'searchableWorkspaceDetailModel?.SelectedWorkspacePrepLibrarySearch?.TotalCount >= 1',
        'authenticatedHomeModel.LeadWorkspaceServerPlane is not null',
        'authenticatedHomeModel.LeadWorkspaceServerPlane!.WorkspaceState.Status',
        'workHomeModel?.LeadWorkspaceServerPlane?.WorkspaceState.Label',
        'workHomeModel?.LeadWorkspaceServerPlane?.PrepLibrary.Packets.Count >= 3',
        'workHomeModel!.CampaignSpine.Workspaces[0].ReturnSummary',
        'homeSource.Contains("What changed for me"',
        'homeSource.Contains("@workspace.ActiveSceneSummary"',
        'homeSource.Contains("@workspace.NextSafeAction"',
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


def canonical_source_path() -> str:
    try:
        return str(SOURCE.relative_to(ROOT))
    except ValueError:
        return str(SOURCE)


def without_generated_at(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key != "generated_at"}


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
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "source_file": canonical_source_path(),
        "journeys_passed": journeys_passed,
        "required_markers": REQUIRED_MARKERS,
    }

    if OUT.is_file():
        try:
            existing_payload = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_payload = None

        if isinstance(existing_payload, dict) and without_generated_at(existing_payload) == payload:
            print(f"campaign-os local proof unchanged: {OUT}")
            return 0

    payload["generated_at"] = iso_now()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote campaign-os local proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
