#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m122-hub-implement-campaign-adoption-wizard-state-runner-goal-per"
WORK_TASK_ID = "122.1"
TITLE = "Implement campaign adoption wizard state, runner-goal persistence, ResolutionReport approval, and first WorldTick/news item flow."
TASK = TITLE
FRONTIER_ID = 1630681972
MILESTONE_ID = 122
WAVE = "W15"
STATUS = "not_started"
REPO = "chummer6-hub"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["implement_campaign_adoption_wizard_state:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "task-local telemetry",
    "shard runtime handoff",
    "supervisor status",
    "supervisor eta",
    "operator telemetry",
]
PACKAGE_PROOF = {
    "package_id": PACKAGE_ID,
    "work_task_id": WORK_TASK_ID,
    "title": TITLE,
    "task": TASK,
    "frontier_id": FRONTIER_ID,
    "milestone_id": MILESTONE_ID,
    "wave": WAVE,
    "repo": REPO,
    "status": STATUS,
    "allowed_paths": ALLOWED_PATHS,
    "owned_surfaces": OWNED_SURFACES,
}
EXPECTED_SURFACES = [
    "implement_campaign_adoption_wizard_state:hub",
    "runner_goal_persistence:hub",
    "resolution_report_approval_world_tick_news:hub",
]

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Contracts/CampaignAdoptionContracts.cs": [
        "public sealed record CampaignAdoptionWizardRequest(",
        "public sealed record RunnerGoalUpsertRequest(",
        "public sealed record CampaignAdoptionResolutionReportApprovalRequest(",
        "public sealed record CampaignAdoptionWorldTickProjection(",
        "public sealed record PlayerSafeNewsItemProjection(",
        "public sealed record CampaignAdoptionResolutionReportProjection(",
        "public sealed record CampaignAdoptionWorkspaceStateProjection(",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpPost("me/workspaces/{workspaceId}/campaign-adoption")]',
        "UpsertMyCampaignWorkspaceCampaignAdoption(",
        '[HttpPost("me/workspaces/{workspaceId}/runner-goals")]',
        "UpsertMyCampaignWorkspaceRunnerGoal(",
        '[HttpPost("me/workspaces/{workspaceId}/resolution-report-approvals")]',
        "ApproveMyCampaignWorkspaceResolutionReport(",
    ],
    "Chummer.Run.Api/Services/Community/CommunityStore.cs": [
        "public List<CampaignAdoptionProjection> CampaignAdoptions { get; } = new();",
        "public List<RunnerGoalProjection> RunnerGoals { get; } = new();",
        "public List<ResolutionReportApprovalProjection> ResolutionReportApprovals { get; } = new();",
        "public List<WorldTickProjection> WorldTicks { get; } = new();",
        "public List<PlayerSafeNewsProjection> PlayerSafeNews { get; } = new();",
        "CampaignAdoptions: CampaignAdoptions.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),",
        "RunnerGoals: RunnerGoals.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),",
        "ResolutionReportApprovals: ResolutionReportApprovals.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),",
        "WorldTicks: WorldTicks.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),",
        "PlayerSafeNews: PlayerSafeNews.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),",
        "CampaignAdoptions.Clear();",
        "RunnerGoals.Clear();",
        "ResolutionReportApprovals.Clear();",
        "WorldTicks.Clear();",
        "PlayerSafeNews.Clear();",
        "CampaignAdoptions.AddRange(snapshot.CampaignAdoptions ?? Array.Empty<CampaignAdoptionProjection>());",
        "RunnerGoals.AddRange(snapshot.RunnerGoals ?? Array.Empty<RunnerGoalProjection>());",
        "ResolutionReportApprovals.AddRange(snapshot.ResolutionReportApprovals ?? Array.Empty<ResolutionReportApprovalProjection>());",
        "WorldTicks.AddRange(snapshot.WorldTicks ?? Array.Empty<WorldTickProjection>());",
        "PlayerSafeNews.AddRange(snapshot.PlayerSafeNews ?? Array.Empty<PlayerSafeNewsProjection>());",
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        "public CampaignAdoptionLoopProjection? GetCampaignAdoptionLoop(",
        "public CampaignAdoptionWorkspaceStateProjection? GetWorkspaceCampaignState(",
        "public CampaignAdoptionProjection UpsertCampaignAdoption(",
        "public RunnerGoalProjection UpsertRunnerGoal(",
        "public ResolutionReportApprovalProjection ApproveResolutionReport(",
        'private const string CampaignAdoptionSourceKind = "campaign_adoption";',
        'private const string RunnerGoalSourceKind = "runner_goal";',
        'private const string ResolutionReportApprovalSourceKind = "resolution_report_approval";',
        'private const string WorldTickSourceKind = "world_tick";',
        'private const string PlayerSafeNewsSourceKind = "player_safe_news";',
        'Summary = $"{storedRun.Title} keeps an approved ResolutionReport, first WorldTick, and player-safe news item on the governed hub lane.",',
        'Kind: "player_safe_news",',
        'anchors.Add("player-safe news");',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var campaignAdoptionResult = await campaignSpineController.UpsertMyCampaignWorkspaceCampaignAdoption(",
        "new CampaignAdoptionUpdateRequest(",
        'Assert(campaignAdoptionPayload is not null && campaignAdoptionPayload.SafeToPlay, "campaign spine campaign-adoption api should persist the adoption wizard posture for the governed workspace.");',
        "var runnerGoalResult = await campaignSpineController.UpsertMyCampaignWorkspaceRunnerGoal(",
        "new RunnerGoalUpdateRequest(",
        'Assert(runnerGoalPayload is not null && string.Equals(runnerGoalPayload.TargetReference, "wired_reflexes_delta", StringComparison.Ordinal), "campaign spine runner-goals api should persist the governed runner goal pin for the selected dossier.");',
        "var resolutionReportApprovalResult = await campaignSpineController.ApproveMyCampaignWorkspaceResolutionReport(",
        "new ResolutionReportApprovalRequest(",
        'Assert(!string.IsNullOrWhiteSpace(resolutionReportApprovalPayload.WorldTickId), "campaign spine resolution-report-approvals api should project the first WorldTick receipt.");',
        'Assert(!string.IsNullOrWhiteSpace(resolutionReportApprovalPayload.NewsId), "campaign spine resolution-report-approvals api should project the first player-safe news receipt.");',
        "var adoptionLoopResult = await campaignSpineController.GetMyCampaignWorkspaceAdoptionLoop(workspaceId, CancellationToken.None);",
        'Assert(adoptionLoopPayload.PlayerSafeNews.Any(item => string.Equals(item.NewsId, resolutionReportApprovalPayload.NewsId, StringComparison.Ordinal)), "campaign spine adoption-loop api should surface the player-safe news preview without turning it into world truth.");',
        'Assert(m122WorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "player_safe_news", StringComparison.Ordinal)) == true, "campaign spine server plane api should project player-safe news previews onto the bounded what-changed rail.");',
        'Assert(reloadedAdoptionLoop.PlayerSafeNews.Any(item => item.Title.Contains("Tacoma grid rumor", StringComparison.Ordinal)), "campaign spine adoption loop should preserve the player-safe news preview across reload.");',
    ],
    "scripts/materialize_next90_m122_hub_campaign_adoption_proof.py": [
        f'"package_id": "{PACKAGE_ID}"',
        f'"frontier_id": {FRONTIER_ID}',
        '"implement_campaign_adoption_wizard_state:hub": [',
        '"runner_goal_persistence:hub": [',
        '"resolution_report_approval_world_tick_news:hub": [',
        '"contract_name": "chummer6-hub.next90_m122_hub_campaign_adoption"',
    ],
    "scripts/verify_next90_m122_hub_campaign_adoption.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m122 hub campaign-adoption proof passed")',
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M122_HUB_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M122_HUB_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M122_HUB_DESIGN_QUEUE_STAGING",
        str(ROOT / ".codex-design" / "product" / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"),
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M122_HUB_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M122_HUB_PROOF",
        ROOT / ".codex-studio" / "published" / "NEXT90_M122_HUB_CAMPAIGN_ADOPTION.generated.json",
    )
)


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return load_target_queue_yaml(text, path)


def load_target_queue_yaml(text: str, path: Path) -> object:
    marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(marker)
    if package_index < 0:
        raise SystemExit(f"unable to parse yaml file: {path}")

    start_candidates = [
        text.rfind("\n- title:", 0, package_index),
        text.rfind("\n  - title:", 0, package_index),
    ]
    block_start = max(start_candidates)
    if block_start < 0:
        if text.startswith("- title:") or text.startswith("  - title:"):
            block_start = 0
        else:
            raise SystemExit(f"unable to isolate queue block in {path}")
    else:
        block_start += 1

    end_candidates = [
        index
        for index in (text.find("\n- title:", package_index), text.find("\n  - title:", package_index))
        if index >= 0
    ]
    block_end = min(end_candidates) if end_candidates else len(text)
    block = text[block_start:block_end].rstrip() + "\n"
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise SystemExit(f"unable to normalize queue staging yaml: {path}")

    return {"items": payload}


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def reject_forbidden_markers(text: str, source: str, errors: list[str]) -> None:
    lowered = text.casefold()
    for marker in FORBIDDEN_PROOF_MARKERS:
        if marker.casefold() in lowered:
            errors.append(f"{source} contains forbidden active-run proof marker: {marker}")


def verify_source_markers(errors: list[str]) -> None:
    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        if relative_path != "scripts/verify_next90_m122_hub_campaign_adoption.py":
            reject_forbidden_markers(text, relative_path, errors)
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")


def verify_queue_authority(errors: list[str], path: Path) -> None:
    if not path.is_file():
        if path == DESIGN_QUEUE_STAGING_PATH:
            return
        errors.append(f"missing queue staging file: {path}")
        return

    payload = load_yaml(path) or {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        errors.append(f"{path}: items is missing")
        return

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        errors.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return

    item = matches[0]
    expected_fields = {
        "title": TITLE,
        "task": TASK,
        "work_task_id": WORK_TASK_ID,
        "frontier_id": FRONTIER_ID,
        "milestone_id": MILESTONE_ID,
        "status": STATUS,
        "wave": WAVE,
        "repo": REPO,
    }
    for key, value in expected_fields.items():
        if item.get(key) != value:
            errors.append(f"{path}: {PACKAGE_ID} {key} must be {value!r}")
    if item.get("allowed_paths") != ALLOWED_PATHS:
        errors.append(f"{path}: allowed_paths must be {ALLOWED_PATHS!r}")
    if item.get("owned_surfaces") != OWNED_SURFACES:
        errors.append(f"{path}: owned_surfaces must be {OWNED_SURFACES!r}")


def verify_successor_registry(errors: list[str], path: Path) -> None:
    if not path.is_file():
        errors.append(f"missing successor registry file: {path}")
        return

    payload = load_yaml(path) or {}
    milestones = payload.get("milestones") if isinstance(payload, dict) else None
    if not isinstance(milestones, list):
        errors.append(f"{path}: milestones is missing")
        return

    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if milestone is None:
        errors.append(f"{path}: missing milestone {MILESTONE_ID}")
        return

    if milestone.get("title") != "Campaign adoption, runner goals, and first BLACK LEDGER consequence":
        errors.append(f"{path}: milestone {MILESTONE_ID} title drifted")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        errors.append(f"{path}: milestone {MILESTONE_ID} work_tasks is missing")
        return

    task_row = next((item for item in work_tasks if isinstance(item, dict) and item.get("id") == WORK_TASK_ID), None)
    if task_row is None:
        errors.append(f"{path}: missing work task {WORK_TASK_ID}")
        return
    if task_row.get("owner") != REPO:
        errors.append(f"{path}: work task {WORK_TASK_ID} owner must be {REPO!r}")
    if task_row.get("title") != TITLE:
        errors.append(f"{path}: work task {WORK_TASK_ID} title must be {TITLE!r}")


def verify_generated_proof(errors: list[str], path: Path) -> None:
    if not path.is_file():
        errors.append(f"missing generated proof: {path}")
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid json ({exc})")
        return

    reject_forbidden_markers(json.dumps(payload, sort_keys=True), str(path), errors)

    if payload.get("contract_name") != "chummer6-hub.next90_m122_hub_campaign_adoption":
        errors.append(f"{path}: contract_name drifted")
    if payload.get("status") != "passed":
        errors.append(f"{path}: status must be 'passed'")
    if payload.get("proof_kind") != "source_backed_local_smoke_contract":
        errors.append(f"{path}: proof_kind drifted")
    if payload.get("package_proof") != PACKAGE_PROOF:
        errors.append(f"{path}: package_proof drifted")

    required_markers = payload.get("required_markers")
    if not isinstance(required_markers, dict):
        errors.append(f"{path}: required_markers is missing")
        return

    for surface, markers in required_markers.items():
        if surface not in EXPECTED_SURFACES:
            errors.append(f"{path}: unexpected required_markers surface {surface!r}")
        if not isinstance(markers, list) or not markers:
            errors.append(f"{path}: {surface} required_markers must be a non-empty list")

    if payload.get("missing_markers") not in ({}, None):
        errors.append(f"{path}: missing_markers must stay empty for a passed proof")
    if payload.get("surfaces_passed") != EXPECTED_SURFACES:
        errors.append(f"{path}: surfaces_passed must be {EXPECTED_SURFACES!r}")


def main() -> int:
    errors: list[str] = []
    verify_source_markers(errors)
    verify_queue_authority(errors, FLEET_QUEUE_STAGING_PATH)
    verify_queue_authority(errors, DESIGN_QUEUE_STAGING_PATH)
    verify_successor_registry(errors, SUCCESSOR_REGISTRY_PATH)
    verify_generated_proof(errors, PROOF_PATH)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("next90 m122 hub campaign-adoption proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
