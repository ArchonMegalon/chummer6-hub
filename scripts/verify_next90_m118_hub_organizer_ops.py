#!/usr/bin/env python3
from __future__ import annotations

import json
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
EXPECTED_WAVE = "W13"
EXPECTED_STATUS = "complete"
PACKAGE_COMPLETION_ACTION = "verify_closed_package_only"
PACKAGE_DO_NOT_REOPEN_REASON = (
    "M118 chummer6-hub organizer, league, convention, and season contracts are complete; future shards must verify "
    "the organizer operations release-proof receipts, canonical registry row, Fleet queue row, and design queue row "
    "instead of reopening this governed community-operations slice."
)
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["organizer_ops", "league_convention_season_ops"]
EXPECTED_DEPENDENCIES = [112, 113, 116, 117]
EXPECTED_EXIT_CRITERIA = [
    "Organizer, league, convention, and season workflows can manage groups, rosters, events, permissions, artifact publication, and support escalation from one governed operations lane.",
    "Community operations remain auditable and bounded instead of becoming operator-only spreadsheets.",
    "Fleet and EA can compile operator packets and followthrough from the same governed state.",
]
REQUIRED_PROOF = [
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Contracts/OrganizerOpsContracts.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Campaign.Contracts/CampaignContracts.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml",
    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs",
    "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m118_hub_organizer_ops.py",
    "/docker/chummercomplete/chummer6-hub/tests/test_next90_m118_hub_organizer_ops.py",
    "/docker/chummercomplete/chummer6-hub/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "python3 scripts/verify_next90_m118_hub_organizer_ops.py",
    "python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py",
    "bash scripts/ai/verify.sh",
]
REGISTRY_EVIDENCE = [
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Contracts/OrganizerOpsContracts.cs and /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs now publish one governed organizer-operations dashboard contract and API route for organizer, league, convention, and season work.",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs now composes organizer roles, permissions, roster movement, season lanes, artifact publication posture, and support-escalation posture from the shared campaign/community truth instead of separate operator notes.",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml and /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml now keep organizer publication and support posture visible on the signed-in work rails without splitting it away from the governed operations card.",
    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves organizer role assignments, permissions, roster movement, season lanes, artifact publication posture, and tracked support escalation survive the shared hub API and signed-in surfaces.",
    "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py, /docker/chummercomplete/chummer6-hub/scripts/verify_next90_m118_hub_organizer_ops.py, and /docker/chummercomplete/chummer6-hub/tests/test_next90_m118_hub_organizer_ops.py keep the closed-package queue, registry, and release-proof receipts executable inside the repo.",
    "python3 scripts/verify_next90_m118_hub_organizer_ops.py exits 0, python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py exits 0, and bash scripts/ai/verify.sh keeps the dedicated M118 verifier in the shared verify lane.",
]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "task-local telemetry",
    "shard runtime handoff",
    "operator telemetry",
    "supervisor status",
    "supervisor eta",
    "worker_model_output_stalled",
]
LOCAL_RELEASE_PROOF_PACKAGE = {
    "package_id": PACKAGE_ID,
    "work_task_id": WORK_TASK_ID,
    "milestone_id": MILESTONE_ID,
    "frontier_id": FRONTIER_ID,
    "repo": "chummer6-hub",
    "status": EXPECTED_STATUS,
    "wave": EXPECTED_WAVE,
    "task": TASK,
    "title": TITLE,
    "completion_action": PACKAGE_COMPLETION_ACTION,
    "do_not_reopen_reason": PACKAGE_DO_NOT_REOPEN_REASON,
    "allowed_paths": ALLOWED_PATHS,
    "owned_surfaces": OWNED_SURFACES,
    "exit_criterion": TASK,
}
LOCAL_RELEASE_PROOF_RECEIPTS = {
    "organizer_ops": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/api/v1/campaign-spine/me/organizer-ops",
            "/home/work",
            "/account/roster",
        ],
        "surfaces": [
            "organizer_ops",
            "organizer_roles",
            "organizer_permissions",
            "organizer_roster_contracts",
        ],
        "summary_markers": [
            "governed organizer operations",
            "roles",
            "roster",
            "account rail",
        ],
        "evidence_markers": [
            "CampaignSpineController.cs now serves the organizer operations dashboard",
            "CampaignSpineService.cs now composes organizer roles, permissions, and roster movement",
            "RunServicesSmoke/Program.cs proves organizer role assignments, permissions, and governed roster movement",
        ],
    },
    "league_convention_season_ops": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/api/v1/campaign-spine/me/organizer-ops",
            "/home/work",
            "/account/roster",
        ],
        "surfaces": [
            "league_convention_season_ops",
            "season_event_lanes",
            "artifact_publication:organizer",
            "support_escalation:organizer",
        ],
        "summary_markers": [
            "season lanes",
            "artifact publication",
            "support escalation",
            "governed operations lane",
        ],
        "evidence_markers": [
            "CampaignSpineService.cs now keeps season lanes, artifact publication posture, and tracked support escalation on the same organizer dashboard",
            "Views/Accounts/Account.cshtml and /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml surface organizer artifact-publication and support-escalation posture on the shared operator rails",
            "RunServicesSmoke/Program.cs proves governed season lanes, artifact publication receipts, and tracked support escalation survive the organizer contract",
        ],
    },
}

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Contracts/OrganizerOpsContracts.cs": [
        "public sealed record OrganizerOperationsDashboardProjection(",
        "public sealed record OrganizerOperationProjection(",
        "public sealed record OrganizerRoleAssignmentProjection(",
        "public sealed record OrganizerPermissionProjection(",
        "public sealed record OrganizerRosterContractProjection(",
        "public sealed record OrganizerEventRailContractProjection(",
        "public sealed record OrganizerSeasonLaneProjection(",
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
        "BuildOrganizerRoleAssignmentsLocked(group);",
        "BuildOrganizerPermissions(operation);",
        'Summary: $"{operation.OperationsSummary} {operation.CampaignReturnSummary}",',
        'Summary: $"{operation.LeagueOperationsSummary} {operation.SeasonEventSummary}",',
        "new OrganizerArtifactPublicationContractProjection(",
        "new OrganizerSupportEscalationContractProjection(",
        '"can_manage_members" => "Manage organizer roles, roster authority, and member recovery on the same governed account rail."',
        '"support_closure" => "Keep human escalation and tracked support closure visible on the same operator contract.",',
        '"Roles: {operation.OperatorRole} across {operation.MemberCount} member(s).",',
        '"Permissions: {(operation.Capabilities.Count == 0 ? "none" : string.Join(", ", operation.Capabilities))}.",',
        '"Roster: {(operation.RecentRosterTransfers?.Count ?? 0)} recent transfer(s) across {operation.ActiveCampaignCount} active campaign(s).",',
        '"Events: {operation.SeasonBoardEntries.Count} season lane(s) and {operation.RecentEventSummaries.Count} recent event summary line(s).",',
        "ArtifactPublicationSummary: ResolveGroupArtifactPublicationSummary(groupWorkspaces),",
        "SupportEscalationSummary: ResolveGroupSupportEscalationSummary(user));",
        "private static string ResolveGroupArtifactPublicationSummary(IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)",
        'return "No governed artifact publication receipt is attached to this maintainer path yet.";',
        "private string ResolveGroupSupportEscalationSummary(HubUserDto user)",
        'return "No tracked support escalation is blocking this maintainer path right now.";',
        "SupportCaseStatuses.UserNotified",
    ],
    "Chummer.Run.Api/Views/Accounts/Account.cshtml": [
        "<span>Publication</span>",
        "<strong>@op.ArtifactPublicationSummary</strong>",
        "<span>Support path</span>",
        "<strong>@op.SupportEscalationSummary</strong>",
        "<li>Publication: @op.ArtifactPublicationSummary</li>",
        "<li>Support path: @op.SupportEscalationSummary</li>",
        '<p class="muted-copy">@op.SupportEscalationSummary</p>',
    ],
    "Chummer.Run.Api/Views/PublicLanding/Home.cshtml": [
        "<span> Shared: @HomeText(leadCommunityOperation.ArtifactPublicationSummary)</span>",
        "<span> Support: @PublicText(leadCommunityOperation.SupportEscalationSummary)</span>",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var organizerOpsResult = await campaignSpineController.GetMyOrganizerOperations(CancellationToken.None);",
        "campaign spine api should return the organizer operations dashboard.",
        "organizer operations api should surface explicit organizer role assignments.",
        "organizer operations api should surface explicit organizer permissions.",
        "organizer operations api should surface recent governed roster movement on the operator contract.",
        "organizer operations api should surface governed season and event lanes.",
        "organizer operations api should surface artifact publication receipts on the operator contract.",
        "organizer operations api should keep tracked support escalation cases on the operator contract.",
        'Assert(homeSource.Contains("Publication: @leadCommunityOperation.ArtifactPublicationSummary", StringComparison.Ordinal), "home work should surface explicit organizer artifact-publication posture on the same operator card.");',
        'Assert(homeSource.Contains("Support: @leadCommunityOperation.SupportEscalationSummary", StringComparison.Ordinal), "home work should surface explicit organizer support-escalation posture on the same operator card.");',
        'Assert(accountSource.Contains("@op.ArtifactPublicationSummary", StringComparison.Ordinal), "account teams and permissions should surface organizer artifact-publication posture directly from the shared projection.");',
        'Assert(accountSource.Contains("@op.SupportEscalationSummary", StringComparison.Ordinal), "account teams and permissions should surface organizer support-escalation posture directly from the shared projection.");',
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        '"package_id": "next90-m118-hub-organizer-ops"',
        '"work_task_id": "118.1"',
        '"receipt_id": "organizer_ops"',
        '"receipt_id": "league_convention_season_ops"',
    ],
    "scripts/verify_next90_m118_hub_organizer_ops.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        "LOCAL_RELEASE_PROOF_RECEIPTS = {",
        "verify_release_proof(missing, LOCAL_RELEASE_PROOF_PATH, label=\"repo-local release proof\")",
        "verify_release_proof(missing, SERVED_RELEASE_PROOF_PATH, label=\"served release proof\")",
        "next90 m118 hub organizer ops proof passed",
    ],
    "tests/test_next90_m118_hub_organizer_ops.py": [
        "test_verifier_accepts_repo_local_organizer_ops",
        "test_materialized_release_proof_includes_m118_organizer_receipts",
        "next90-m118-hub-organizer-ops",
        "status must be 'complete'",
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m118_hub_organizer_ops.py",
        "python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_SERVED_RELEASE_PROOF",
        str(ROOT / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_queue_staging_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = None
    else:
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload

    package_marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(package_marker)
    if package_index < 0:
        raise ValueError(f"queue staging is missing package_id {PACKAGE_ID}")

    start = text.rfind("\n- title:", 0, package_index)
    if start < 0:
        if not text.startswith("- title:"):
            raise ValueError(f"queue staging is missing the item block for {PACKAGE_ID}")
        start = 0
    else:
        start += 1

    end = text.find("\n- title:", package_index)
    if end < 0:
        end = len(text)

    block = text[start:end].rstrip() + "\n"
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError(f"queue staging package block for {PACKAGE_ID} must parse to exactly one item")
    return {"items": payload}


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def reject_forbidden_markers(text: str, source: str, missing: list[str]) -> None:
    lowered = text.casefold()
    for marker in FORBIDDEN_PROOF_MARKERS:
        if marker.casefold() in lowered:
            missing.append(f"{source}: contains forbidden active-run proof marker {marker!r}")


def verify_queue_authority(missing: list[str], path: Path) -> dict[str, object] | None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return None

    try:
        payload = load_queue_staging_yaml(path) or {}
    except (ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: unable to load queue staging for {PACKAGE_ID}: {exc}")
        return None
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        missing.append(f"{path}: items is missing")
        return None

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return None

    item = matches[0]
    reject_forbidden_markers(yaml.safe_dump(item, sort_keys=False), f"{path}:{PACKAGE_ID}", missing)
    expected_fields = {
        "title": TITLE,
        "task": TASK,
        "repo": "chummer6-hub",
        "milestone_id": MILESTONE_ID,
        "work_task_id": 118.1,
        "status": EXPECTED_STATUS,
        "wave": EXPECTED_WAVE,
        "completion_action": PACKAGE_COMPLETION_ACTION,
        "do_not_reopen_reason": PACKAGE_DO_NOT_REOPEN_REASON,
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
    proof = item.get("proof")
    if not isinstance(proof, list) or not proof:
        missing.append(f"{path}: {PACKAGE_ID} must define a non-empty proof list")
    elif proof != REQUIRED_PROOF:
        missing.append(f"{path}: {PACKAGE_ID} proof must match the closed-package receipt exactly")
    return dict(item)


def verify_queue_parity(missing: list[str], fleet_row: dict[str, object] | None, design_row: dict[str, object] | None) -> None:
    if fleet_row is None or design_row is None:
        return
    if fleet_row != design_row:
        missing.append(f"fleet and design queue rows for {PACKAGE_ID} must match exactly")


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

    reject_forbidden_markers(yaml.safe_dump(milestone, sort_keys=False), f"{path}:milestone-{MILESTONE_ID}", missing)
    if milestone.get("title") != "Organizer, league, convention, and season operations":
        missing.append(f"{path}: milestone {MILESTONE_ID} title drifted")
    if milestone.get("status") != "in_progress":
        missing.append(f"{path}: milestone {MILESTONE_ID} status must stay 'in_progress' until sibling work closes")
    if milestone.get("dependencies") != EXPECTED_DEPENDENCIES:
        missing.append(f"{path}: milestone {MILESTONE_ID} dependencies must be {EXPECTED_DEPENDENCIES!r}")
    if milestone.get("exit_criteria") != EXPECTED_EXIT_CRITERIA:
        missing.append(f"{path}: milestone {MILESTONE_ID} exit_criteria drifted")

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
    if task.get("status") != EXPECTED_STATUS:
        missing.append(f"{path}: work task {WORK_TASK_ID} status must be {EXPECTED_STATUS!r}")
    evidence = task.get("evidence")
    if not isinstance(evidence, list):
        missing.append(f"{path}: work task {WORK_TASK_ID} evidence must be a list")
    elif evidence != REGISTRY_EVIDENCE:
        missing.append(f"{path}: work task {WORK_TASK_ID} evidence must match the closed-package receipt exactly")


def verify_release_proof(missing: list[str], path: Path, *, label: str) -> None:
    if not path.is_file():
        missing.append(f"missing {label}: {path}")
        return

    payload = load_json(path)
    if not isinstance(payload, dict):
        missing.append(f"{label}: payload must be a JSON object")
        return

    reject_forbidden_markers(json.dumps(payload, sort_keys=True), label, missing)
    packages = payload.get("successor_queue_packages_by_id")
    if not isinstance(packages, dict):
        missing.append(f"{label}: successor_queue_packages_by_id is missing")
        return

    package = packages.get(PACKAGE_ID)
    if not isinstance(package, dict):
        missing.append(f"{label}: missing successor package {PACKAGE_ID}")
    else:
        for key, value in LOCAL_RELEASE_PROOF_PACKAGE.items():
            if package.get(key) != value:
                missing.append(f"{label}: {PACKAGE_ID} {key} must be {value!r}")

    receipts = payload.get("proof_receipts")
    if not isinstance(receipts, list):
        missing.append(f"{label}: proof_receipts is missing")
        return

    for receipt_id, expected in LOCAL_RELEASE_PROOF_RECEIPTS.items():
        matches = [
            receipt
            for receipt in receipts
            if isinstance(receipt, dict)
            and receipt.get("package_id") == PACKAGE_ID
            and receipt.get("receipt_id") == receipt_id
        ]
        if len(matches) != 1:
            missing.append(f"{label}: expected exactly one {PACKAGE_ID} receipt {receipt_id!r}, found {len(matches)}")
            continue
        receipt = matches[0]
        for key in ("package_id", "milestone_id", "frontier_id"):
            if receipt.get(key) != expected[key]:
                missing.append(f"{label}: {receipt_id} {key} must be {expected[key]!r}")
        for route in expected["routes"]:
            if route not in receipt.get("routes", []):
                missing.append(f"{label}: {receipt_id} route missing {route!r}")
        for surface in expected["surfaces"]:
            if surface not in receipt.get("surfaces", []):
                missing.append(f"{label}: {receipt_id} surface missing {surface!r}")
        summary = str(receipt.get("summary") or "")
        for marker in expected["summary_markers"]:
            if marker not in summary:
                missing.append(f"{label}: {receipt_id} summary missing marker {marker!r}")
        evidence = "\n".join(receipt.get("evidence", [])) if isinstance(receipt.get("evidence"), list) else ""
        for marker in expected["evidence_markers"]:
            if marker not in evidence:
                missing.append(f"{label}: {receipt_id} evidence missing marker {marker!r}")


def verify_release_proof_parity(missing: list[str]) -> None:
    if not LOCAL_RELEASE_PROOF_PATH.is_file() or not SERVED_RELEASE_PROOF_PATH.is_file():
        return

    local_payload = load_json(LOCAL_RELEASE_PROOF_PATH)
    served_payload = load_json(SERVED_RELEASE_PROOF_PATH)
    if not isinstance(local_payload, dict) or not isinstance(served_payload, dict):
        return

    local_packages = local_payload.get("successor_queue_packages_by_id")
    served_packages = served_payload.get("successor_queue_packages_by_id")
    if isinstance(local_packages, dict) and isinstance(served_packages, dict):
        if local_packages.get(PACKAGE_ID) != served_packages.get(PACKAGE_ID):
            missing.append(f"repo-local and served release proof package rows for {PACKAGE_ID} must match exactly")

    local_receipts = local_payload.get("proof_receipts")
    served_receipts = served_payload.get("proof_receipts")
    if not isinstance(local_receipts, list) or not isinstance(served_receipts, list):
        return

    for receipt_id in LOCAL_RELEASE_PROOF_RECEIPTS:
        local_match = next(
            (
                receipt
                for receipt in local_receipts
                if isinstance(receipt, dict)
                and receipt.get("package_id") == PACKAGE_ID
                and receipt.get("receipt_id") == receipt_id
            ),
            None,
        )
        served_match = next(
            (
                receipt
                for receipt in served_receipts
                if isinstance(receipt, dict)
                and receipt.get("package_id") == PACKAGE_ID
                and receipt.get("receipt_id") == receipt_id
            ),
            None,
        )
        if local_match != served_match:
            missing.append(f"repo-local and served release proof receipt {receipt_id!r} for {PACKAGE_ID} must match exactly")


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
    queue_row = verify_queue_authority(missing, QUEUE_STAGING_PATH)
    design_queue_row = verify_queue_authority(missing, DESIGN_QUEUE_STAGING_PATH)
    verify_queue_parity(missing, queue_row, design_queue_row)
    verify_successor_registry(missing, SUCCESSOR_REGISTRY_PATH)
    verify_release_proof(missing, LOCAL_RELEASE_PROOF_PATH, label="repo-local release proof")
    verify_release_proof(missing, SERVED_RELEASE_PROOF_PATH, label="served release proof")
    verify_release_proof_parity(missing)
    verify_source_markers(missing)

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m118 hub organizer ops proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
