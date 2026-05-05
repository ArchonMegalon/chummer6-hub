#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m118-hub-organizer-ops"
TITLE = "Land organizer, league, convention, and season contracts"
TASK = "Add roles, rosters, events, permissions, artifact publication, and support escalation contracts for community-scale operations."
FRONTIER_ID = 3207603971
MILESTONE_ID = 118
WORK_TASK_ID = "118.1"
WORK_TASK_TITLE = "Land organizer, league, convention, and season operation contracts with roles, rosters, events, and audit receipts."
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["organizer_ops", "league_convention_season_ops"]
EXPECTED_STATUS = "in_progress"

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Contracts/OrganizerOpsContracts.cs": [
        "public sealed record OrganizerOperationsDashboardProjection(",
        "public sealed record OrganizerOperationProjection(",
        "public sealed record OrganizerArtifactPublicationContractProjection(",
        "public sealed record OrganizerSupportEscalationContractProjection(",
    ],
    "Chummer.Campaign.Contracts/CampaignContracts.cs": [
        "string? ArtifactPublicationSummary = null,",
        "string? SupportEscalationSummary = null);",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpGet("me/organizer-ops")]',
        "[ProducesResponseType<OrganizerOperationsDashboardProjection>(StatusCodes.Status200OK)]",
        "GetMyOrganizerOperations(CancellationToken cancellationToken)",
        "return Ok(_campaignSpine.GetOrganizerOperations(user, installLinking));",
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        "public OrganizerOperationsDashboardProjection GetOrganizerOperations(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)",
        "BuildOrganizerOperationProjectionLocked(user, summary, operation, supportCases)",
        "new OrganizerArtifactPublicationContractProjection(",
        "new OrganizerSupportEscalationContractProjection(",
        "ArtifactPublicationSummary: ResolveGroupArtifactPublicationSummary(groupWorkspaces),",
        "SupportEscalationSummary: ResolveGroupSupportEscalationSummary(user));",
        "private static string ResolveGroupArtifactPublicationSummary(IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)",
        'return "No governed artifact publication receipt is attached to this operator rail yet.";',
        "private string ResolveGroupSupportEscalationSummary(HubUserDto user)",
        'return "No tracked support escalation is blocking this operator rail right now.";',
        "SupportCaseStatuses.UserNotified",
    ],
    "Chummer.Run.Api/Views/Accounts/Account.cshtml": [
        "<span>Artifact publication</span>",
        "<strong>@op.ArtifactPublicationSummary</strong>",
        "<span>Support escalation</span>",
        "<strong>@op.SupportEscalationSummary</strong>",
        "<li>Artifact publication: @op.ArtifactPublicationSummary</li>",
        "<li>Support escalation: @op.SupportEscalationSummary</li>",
        '<p class="muted-copy">@op.SupportEscalationSummary</p>',
    ],
    "Chummer.Run.Api/Views/PublicLanding/Home.cshtml": [
        "<span> Publication: @leadCommunityOperation.ArtifactPublicationSummary</span>",
        "<span> Support: @leadCommunityOperation.SupportEscalationSummary</span>",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var organizerOpsResult = await campaignSpineController.GetMyOrganizerOperations(CancellationToken.None);",
        "campaign spine api should return the organizer operations dashboard.",
        "organizer operations api should surface explicit organizer role assignments.",
        "organizer operations api should surface artifact publication receipts on the operator contract.",
        "organizer operations api should keep tracked support escalation cases on the operator contract.",
        'Assert(homeSource.Contains("Publication: @leadCommunityOperation.ArtifactPublicationSummary", StringComparison.Ordinal), "home work should surface explicit organizer artifact-publication posture on the same operator card.");',
        'Assert(homeSource.Contains("Support: @leadCommunityOperation.SupportEscalationSummary", StringComparison.Ordinal), "home work should surface explicit organizer support-escalation posture on the same operator card.");',
        'Assert(accountSource.Contains("Artifact publication", StringComparison.Ordinal), "account teams and permissions should surface explicit organizer artifact-publication posture on the operator rail.");',
        'Assert(accountSource.Contains("@op.ArtifactPublicationSummary", StringComparison.Ordinal), "account teams and permissions should surface organizer artifact-publication posture directly from the shared projection.");',
        'Assert(accountSource.Contains("Support escalation", StringComparison.Ordinal), "account teams and permissions should surface explicit organizer support-escalation posture on the operator rail.");',
        'Assert(accountSource.Contains("@op.SupportEscalationSummary", StringComparison.Ordinal), "account teams and permissions should surface organizer support-escalation posture directly from the shared projection.");',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m118_hub_organizer_ops.py",
        "python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py",
    ],
    "tests/test_next90_m118_hub_organizer_ops.py": [
        "class Next90M118HubOrganizerOpsTests(unittest.TestCase):",
        "self.assertIn(\"status must be 'in_progress'\", result.stderr)",
        'self.assertIn("GetMyOrganizerOperations", result.stderr)',
        'self.assertIn("@op.ArtifactPublicationSummary", result.stderr)',
        'self.assertIn("@leadCommunityOperation.SupportEscalationSummary", result.stderr)',
    ],
}


def load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def verify_queue_authority(missing: list[str], path: Path) -> None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return

    payload = load_yaml(path) or {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        missing.append(f"{path}: items is missing")
        return

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return

    item = matches[0]
    expected_fields = {
        "title": TITLE,
        "task": TASK,
        "repo": "chummer6-hub",
        "milestone_id": MILESTONE_ID,
        "work_task_id": 118.1,
        "status": EXPECTED_STATUS,
    }
    for key, value in expected_fields.items():
        if item.get(key) != value:
            missing.append(f"{path}: {PACKAGE_ID} {key} must be {value!r}")

    if "frontier_id" in item and item.get("frontier_id") != FRONTIER_ID:
        missing.append(f"{path}: {PACKAGE_ID} frontier_id must be {FRONTIER_ID!r} when present")
    if item.get("allowed_paths") != ALLOWED_PATHS:
        missing.append(f"{path}: allowed_paths must be {ALLOWED_PATHS!r}")
    if item.get("owned_surfaces") != OWNED_SURFACES:
        missing.append(f"{path}: owned_surfaces must be {OWNED_SURFACES!r}")


def verify_successor_registry(missing: list[str], path: Path) -> None:
    if not path.is_file():
        missing.append(f"missing successor registry file: {path}")
        return

    payload = load_yaml(path) or {}
    milestones = payload.get("milestones") if isinstance(payload, dict) else None
    if not isinstance(milestones, list):
        missing.append(f"{path}: milestones is missing")
        return

    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if milestone is None:
        missing.append(f"{path}: milestone {MILESTONE_ID} is missing")
        return

    if milestone.get("title") != "Organizer, league, convention, and season operations":
        missing.append(f"{path}: milestone {MILESTONE_ID} title drifted")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        missing.append(f"{path}: milestone {MILESTONE_ID} work_tasks is missing")
        return

    task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == WORK_TASK_ID), None)
    if task is None:
        missing.append(f"{path}: work task {WORK_TASK_ID} is missing")
        return

    if task.get("owner") != "chummer6-hub":
        missing.append(f"{path}: work task {WORK_TASK_ID} owner drifted")
    if task.get("title") != WORK_TASK_TITLE:
        missing.append(f"{path}: work task {WORK_TASK_ID} title drifted")


def verify_source_markers(missing: list[str]) -> None:
    for relative_path, markers in SOURCE_MARKERS.items():
        path = ROOT / relative_path
        if not path.is_file():
            missing.append(f"missing source file: {path}")
            continue

        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                missing.append(f"{path}: missing marker {marker!r}")


def main() -> int:
    missing: list[str] = []
    verify_queue_authority(missing, QUEUE_STAGING_PATH)
    verify_successor_registry(missing, SUCCESSOR_REGISTRY_PATH)
    verify_source_markers(missing)

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m118 hub organizer ops proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
