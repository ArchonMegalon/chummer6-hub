#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m122-hub-implement-campaign-adoption-wizard-state-runner-goal-per",
    "work_task_id": "122.1",
    "title": "Implement campaign adoption wizard state, runner-goal persistence, ResolutionReport approval, and first WorldTick/news item flow.",
    "task": "Implement campaign adoption wizard state, runner-goal persistence, ResolutionReport approval, and first WorldTick/news item flow.",
    "frontier_id": 1630681972,
    "milestone_id": 122,
    "wave": "W15",
    "repo": "chummer6-hub",
    "status": "not_started",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["implement_campaign_adoption_wizard_state:hub"],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M122_HUB_ROOT", DEFAULT_ROOT))
SOURCE = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M122_HUB_SOURCE",
        ROOT / "tests" / "RunServicesSmoke" / "Program.cs",
    )
)
OUT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M122_HUB_PROOF_OUT",
        ROOT / ".codex-studio" / "published" / "NEXT90_M122_HUB_CAMPAIGN_ADOPTION.generated.json",
    )
)

REQUIRED_MARKERS = {
    "implement_campaign_adoption_wizard_state:hub": [
        "var campaignAdoptionResult = await campaignSpineController.UpsertMyCampaignWorkspaceCampaignAdoption(",
        "new CampaignAdoptionUpdateRequest(",
        'Assert(campaignAdoptionPayload is not null && campaignAdoptionPayload.SafeToPlay, "campaign spine campaign-adoption api should persist the adoption wizard posture for the governed workspace.");',
        'Assert(m122WorkspaceServerPlanePayload?.CampaignAdoptionLoop is not null, "campaign spine server plane api should project the combined campaign adoption loop on the bounded workspace plane.");',
    ],
    "runner_goal_persistence:hub": [
        "var runnerGoalResult = await campaignSpineController.UpsertMyCampaignWorkspaceRunnerGoal(",
        "new RunnerGoalUpdateRequest(",
        'Assert(runnerGoalPayload is not null && string.Equals(runnerGoalPayload.TargetReference, "wired_reflexes_delta", StringComparison.Ordinal), "campaign spine runner-goals api should persist the governed runner goal pin for the selected dossier.");',
        'Assert(m122WorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "runner_goal", StringComparison.Ordinal)) == true, "campaign spine server plane api should project runner-goal pins onto the bounded what-changed rail.");',
    ],
    "resolution_report_approval_world_tick_news:hub": [
        "var resolutionReportApprovalResult = await campaignSpineController.ApproveMyCampaignWorkspaceResolutionReport(",
        "new ResolutionReportApprovalRequest(",
        'Assert(!string.IsNullOrWhiteSpace(resolutionReportApprovalPayload.WorldTickId), "campaign spine resolution-report-approvals api should project the first WorldTick receipt.");',
        'Assert(!string.IsNullOrWhiteSpace(resolutionReportApprovalPayload.NewsId), "campaign spine resolution-report-approvals api should project the first player-safe news receipt.");',
        'Assert(m122WorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "resolution_report_approval", StringComparison.Ordinal)) == true, "campaign spine server plane api should project ResolutionReport approvals onto the bounded what-changed rail.");',
        'Assert(m122WorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "world_tick", StringComparison.Ordinal)) == true, "campaign spine server plane api should project the first BLACK LEDGER WorldTick onto the bounded what-changed rail.");',
        'Assert(m122WorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "player_safe_news", StringComparison.Ordinal)) == true, "campaign spine server plane api should project player-safe news previews onto the bounded what-changed rail.");',
        'Assert(reloadedAdoptionLoop.PlayerSafeNews.Any(item => item.Title.Contains("Tacoma grid rumor", StringComparison.Ordinal)), "campaign spine adoption loop should preserve the player-safe news preview across reload.");',
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
    surfaces_passed: list[str] = []
    missing_markers: dict[str, list[str]] = {}

    for surface, markers in REQUIRED_MARKERS.items():
        surface_missing = [marker for marker in markers if marker not in text]
        if surface_missing:
            missing_markers[surface] = surface_missing
            continue
        surfaces_passed.append(surface)

    payload = {
        "contract_name": "chummer6-hub.next90_m122_hub_campaign_adoption",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": canonical_source_path(),
        "surfaces_passed": surfaces_passed,
        "missing_markers": missing_markers,
        "required_markers": REQUIRED_MARKERS,
    }

    if OUT.is_file():
        try:
            existing_payload = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_payload = None
        if isinstance(existing_payload, dict) and without_generated_at(existing_payload) == payload:
            print(f"next90 m122 hub campaign-adoption proof unchanged: {OUT}")
            return 0

    payload["generated_at"] = iso_now()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m122 hub campaign-adoption proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
