#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m122-hub-implement-campaign-adoption-wizard-state-runner-goal-per"
WORK_TASK_ID = "122.1"
FRONTIER_ID = 1630681972
MILESTONE_ID = 122
PACKAGE_TITLE = "Implement campaign adoption wizard state, runner-goal persistence, ResolutionReport approval, and first WorldTick/news item flow."
PACKAGE_TASK = PACKAGE_TITLE
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W15"
PACKAGE_STATUS = "not_started"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["implement_campaign_adoption_wizard_state:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "supervisor status",
    "task-local telemetry",
]

SOURCE_MARKERS = {
    "Chummer.Campaign.Contracts/CampaignContracts.cs": [
        "public sealed record CampaignAdoptionProjection(",
        "public sealed record RunnerGoalProjection(",
        "public sealed record CampaignAdoptionLoopProjection(",
    ],
    "Chummer.Run.Api/Contracts/CampaignAdoptionLoopContracts.cs": [
        "public sealed record CampaignAdoptionUpdateRequest(",
        "public sealed record RunnerGoalUpdateRequest(",
        "public sealed record ResolutionReportApprovalRequest(",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpGet("me/workspaces/{workspaceId}/adoption-loop")]',
        '[HttpPost("me/workspaces/{workspaceId}/campaign-adoption")]',
        '[HttpPost("me/workspaces/{workspaceId}/runner-goals")]',
        '[HttpPost("me/workspaces/{workspaceId}/resolution-report-approvals")]',
        'return BadRequest("campaign adoption payload is required.");',
        'return BadRequest("runner goal payload is required.");',
        'return BadRequest("resolution report approval payload is required.");',
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        "public CampaignAdoptionProjection UpsertCampaignAdoption(",
        "public RunnerGoalProjection UpsertRunnerGoal(",
        "public ResolutionReportApprovalProjection ApproveResolutionReport(",
        'Kind: "campaign_adoption",',
        'Kind: "runner_goal",',
        'Kind: "resolution_report_approval",',
        'Kind: "world_tick",',
        'Kind: "player_safe_news",',
    ],
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs": [
        "public CampaignAdoptionLoopProjection? GetWorkspaceCampaignAdoptionLoop(",
        "public CampaignAdoptionProjection? UpsertCampaignAdoption(",
        "public RunnerGoalProjection? UpsertRunnerGoal(",
        "public ResolutionReportApprovalProjection? ApproveResolutionReport(",
        "CampaignAdoptionLoop: context.Workspace.CampaignAdoptionLoop",
    ],
    "Chummer.Tests/CampaignAdoptionLoopServiceTests.cs": [
        "public void CampaignAdoptionLoopPersistsGoalsWorldTickAndApprovedResolutionReport()",
        'Summary: "Campaign adoption wizard says this workspace is safe to play while unknown provenance stays explicit."',
        'WorldTickSummary: "Dockside courier fallout becomes the first BLACK LEDGER WorldTick for Tacoma."',
        'Assert.Contains(reloadedWorkspace.RecapShelf, item => string.Equals(item.Kind, "player_safe_news", StringComparison.Ordinal));',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var campaignAdoptionResult = await campaignSpineController.UpsertMyCampaignWorkspaceCampaignAdoption(",
        'Label: "Delta-grade wired reflexes fund"',
        "var resolutionReportApprovalResult = await campaignSpineController.ApproveMyCampaignWorkspaceResolutionReport(",
        "var adoptionLoopResult = await campaignSpineController.GetMyCampaignWorkspaceAdoptionLoop(workspaceId, CancellationToken.None);",
        'NewsTitle: "Tacoma grid rumor points to a vanished courier"',
        'campaign spine server plane api should project player-safe news previews onto the bounded what-changed rail.',
        'campaign spine adoption loop should preserve the player-safe news preview across reload.',
    ],
    "scripts/materialize_next90_m122_hub_campaign_adoption_loop_proof.py": [
        '"package_id": "next90-m122-hub-implement-campaign-adoption-wizard-state-runner-goal-per"',
        '"frontier_id": 1630681972',
        '"owned_surfaces": ["implement_campaign_adoption_wizard_state:hub"]',
    ],
    "scripts/verify_next90_m122_hub_campaign_adoption_loop.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m122 hub campaign adoption loop proof passed")',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m122_hub_campaign_adoption_loop_proof.py",
        "python3 scripts/verify_next90_m122_hub_campaign_adoption_loop.py",
        "python3 -m unittest tests/test_next90_m122_hub_campaign_adoption_loop.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M122_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M122_QUEUE_STAGING", "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
DESIGN_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M122_DESIGN_QUEUE_STAGING", "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
PROOF_PATH = ROOT / '.codex-studio' / 'published' / 'NEXT90_M122_HUB_CAMPAIGN_ADOPTION_LOOP.generated.json'


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding='utf-8')
    return yaml.safe_load(text)


def load_queue_staging_yaml(path: Path) -> object:
    text = path.read_text(encoding='utf-8')
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = None
    else:
        if isinstance(payload, dict) and isinstance(payload.get('items'), list):
            return payload

    package_marker = f'package_id: {PACKAGE_ID}'
    package_index = text.find(package_marker)
    if package_index < 0:
        raise ValueError(f'queue staging is missing package_id {PACKAGE_ID}')

    start = text.rfind('\n- title:', 0, package_index)
    if start < 0:
        if not text.startswith('- title:'):
            raise ValueError(f'queue staging is missing the item block for {PACKAGE_ID}')
        start = 0
    else:
        start += 1

    end = text.find('\n- title:', package_index)
    if end < 0:
        end = len(text)

    block = text[start:end].rstrip() + '\n'
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError(f'queue staging package block for {PACKAGE_ID} must parse to exactly one item')
    return {'items': payload}


def verify_queue(path: Path, missing: list[str]) -> None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return
    try:
        payload = load_queue_staging_yaml(path) or {}
    except (ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: unable to load queue staging for {PACKAGE_ID}: {exc}")
        return
    items = payload.get('items') if isinstance(payload, dict) else None
    if not isinstance(items, list):
        missing.append(f"{path}: items is missing")
        return
    matches = [item for item in items if isinstance(item, dict) and item.get('package_id') == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return
    item = matches[0]
    expected = {
        'title': PACKAGE_TITLE,
        'task': PACKAGE_TASK,
        'repo': PACKAGE_REPO,
        'milestone_id': MILESTONE_ID,
        'work_task_id': WORK_TASK_ID,
        'frontier_id': FRONTIER_ID,
        'wave': PACKAGE_WAVE,
        'status': PACKAGE_STATUS,
        'allowed_paths': ALLOWED_PATHS,
        'owned_surfaces': OWNED_SURFACES,
    }
    for key, value in expected.items():
        if item.get(key) != value:
            missing.append(f"{path}: {PACKAGE_ID} {key} must be {value!r}")


def main() -> int:
    missing: list[str] = []
    verify_queue(FLEET_QUEUE_STAGING_PATH, missing)
    verify_queue(DESIGN_QUEUE_STAGING_PATH, missing)

    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: missing marker {marker}")
        if relative_path != "scripts/verify_next90_m122_hub_campaign_adoption_loop.py":
            for forbidden in FORBIDDEN_PROOF_MARKERS:
                if forbidden in text:
                    missing.append(f"{relative_path}: forbidden marker {forbidden}")

    materializer = ROOT / 'scripts' / 'materialize_next90_m122_hub_campaign_adoption_loop_proof.py'
    result = subprocess.run(["python3", str(materializer)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        missing.append(result.stderr.strip() or result.stdout.strip() or "materializer failed")
    elif not PROOF_PATH.is_file():
        missing.append(f"proof file was not written: {PROOF_PATH}")
    else:
        payload = json.loads(PROOF_PATH.read_text(encoding='utf-8'))
        if payload.get('package_proof', {}).get('package_id') != PACKAGE_ID:
            missing.append('proof file package_id drifted')

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m122 hub campaign adoption loop proof passed")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
