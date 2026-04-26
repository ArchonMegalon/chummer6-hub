#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from base64 import a85decode, b32decode, b64decode, b85decode
from binascii import Error as BinasciiError
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import unquote
from zlib import decompress, error as ZlibError

import yaml


PACKAGE_ID = "next90-m112-hub-campaign-consequence-truth"
TITLE = "Promote campaign consequence state into governed campaign APIs"
TASK = "Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions."
FRONTIER_ID = 4730880976
MILESTONE_ID = 112
LANDED_COMMIT = "f2b0b5a6"
COMPLETION_ACTION = "verify_closed_package_only"
DO_NOT_REOPEN_REASON = (
    "M112 chummer6-hub campaign consequence truth is complete; future shards must verify the governed "
    "campaign consequence proof, local release proof receipts, registry row, queue row, and design queue "
    "row instead of reopening this package."
)
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["campaign_memory:consequence_truth", "downtime_aftermath:api"]
PACKAGE_PROOF = {
    "package_id": PACKAGE_ID,
    "title": TITLE,
    "task": TASK,
    "frontier_id": FRONTIER_ID,
    "milestone_id": MILESTONE_ID,
    "allowed_paths": ALLOWED_PATHS,
    "owned_surfaces": OWNED_SURFACES,
}
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "active-run helper",
    "active-run helper command",
    "active-run helper commands",
    "operator telemetry",
    "operator/OODA loop",
    "run_ooda_design_supervisor_until_quiet",
    "ooda_design_supervisor.py",
    "supervisor status",
    "supervisor eta",
    "status query",
    "status_query_supported",
    "polling_disabled",
    "task-local telemetry",
    "shard runtime handoff",
    "first_commands",
    "frontier_briefs",
    "successor frontier detail",
    "assigned successor queue package",
    "execution rules inside this run",
    "required order",
    "successor-wave telemetry",
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_PROOF",
        ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json",
    )
)
RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_RELEASE_PROOF",
        ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpGet("me/workspaces/{workspaceId}/consequences")]',
        "GetMyCampaignWorkspaceConsequences(",
        '_workspaceServerPlane.GetWorkspaceConsequences(user, workspaceId, installLinking);',
        '[HttpGet("me/workspaces/{workspaceId}/consequence-truth")]',
        "GetMyCampaignWorkspaceConsequenceTruth(",
        '_workspaceServerPlane.GetWorkspaceConsequenceTruth(user, workspaceId, installLinking);',
        '[HttpGet("me/workspaces/{workspaceId}/aftermath-recap-packages")]',
        "GetMyCampaignWorkspaceAftermathRecapPackages(",
        '_workspaceServerPlane.GetWorkspaceAftermathRecapPackages(user, workspaceId, installLinking);',
        '[HttpGet("me/workspaces/{workspaceId}/downtime-aftermath")]',
        "GetMyCampaignWorkspaceDowntimeAftermath(",
        '_workspaceServerPlane.GetWorkspaceDowntimeAftermath(user, workspaceId, installLinking);',
        '[HttpGet("me/workspaces/{workspaceId}/campaign-memory")]',
        "GetMyCampaignWorkspaceCampaignMemory(",
        '_workspaceServerPlane.GetWorkspaceCampaignMemory(user, workspaceId, installLinking);',
        '[HttpGet("me/workspaces/{workspaceId}/next-session-carry-forward")]',
        "GetMyCampaignWorkspaceNextSessionCarryForward(",
        '_workspaceServerPlane.GetWorkspaceNextSessionCarryForward(user, workspaceId, installLinking);',
        '[HttpPost("me/workspaces/{workspaceId}/aftermath-recap-packages")]',
        "GenerateMyCampaignWorkspaceAftermathRecapPackage(",
        'return BadRequest("aftermath recap payload is required.");',
        '[HttpPost("me/workspaces/{workspaceId}/consequences")]',
        "UpsertMyCampaignWorkspaceConsequence(",
        'return BadRequest("campaign consequence payload is required.");',
        "_workspaceServerPlane.GenerateAftermathRecapPackage(user, workspaceId, request, installLinking);",
        "_workspaceServerPlane.UpsertCampaignConsequence(user, workspaceId, request, installLinking);",
    ],
    "Chummer.Run.Api/Contracts/CampaignWorkspaceServerPlaneContracts.cs": [
        "IReadOnlyList<CampaignConsequenceProjection> Consequences,",
        "IReadOnlyList<AftermathRecapPackageProjection> AftermathPackages,",
        "CampaignMemoryProjection? CampaignMemory,",
        "NextSessionCarryForwardProjection? NextSessionCarryForward,",
        "public sealed record CampaignConsequenceTruthProjection(",
        "public sealed record GovernedCampaignConsequenceStateProjection(",
        "public sealed record DowntimeAftermathApiProjection(",
        "public sealed record CampaignConsequenceUpdateRequest(",
        "string Kind,",
        "string State,",
        "string Summary,",
        "string? ReturnLoopAction,",
        "string? ReturnLoopRoute,",
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        'private const string GovernedConsequenceUpdateSourceKind = "governed_consequence_update";',
        'private const string ReturnLoopActionSourceKind = "return_loop_action";',
        'private const string ReturnLoopRouteSourceKind = "return_loop_route";',
        'private const string GovernedAftermathPackageSourceKind = "governed_aftermath_package";',
        "CampaignConsequenceProjection? aftermathConsequence = BuildAftermathConsequenceProjection(workspace, run, package);",
        "Consequences = UpsertGovernedCampaignConsequence(campaign.Consequences, aftermathConsequence),",
        "CampaignConsequenceProjection consequence = BuildGovernedCampaignConsequenceProjection(",
        'Summary: $"{consequences.Length} governed faction, heat, contact, and reputation signal(s) stay attached to the shared campaign view with receipt-backed evidence and explicit return-loop actions."',
        'ReceiptId: StableId("consequence-update", $"{workspace.WorkspaceId}:{normalizedKind}:{observedAtUtc.ToUnixTimeMilliseconds()}"),',
        'SourceKind: GovernedConsequenceUpdateSourceKind,',
        'SourceKind: ReturnLoopActionSourceKind,',
        'SourceKind: ReturnLoopRouteSourceKind,',
        "string? normalizedRoute = NormalizeGovernedConsequenceReturnLoopRoute(normalizedKind, returnLoopRoute);",
        '\"downtime\" or \"aftermath\" => \"/account/work#aftermath-packages\",',
        'throw new InvalidOperationException($"campaign consequence return-loop route must stay on the governed local route {canonicalRoute} for {consequenceKind}.");',
        '"downtime_brief" => "downtime",',
        '"session_recap" or "after_action_report" or "replay_timeline" => "aftermath",',
        '"Return-loop route: /account/work#aftermath-packages."',
        'ReceiptId: "/account/work#aftermath-packages",',
        'if (string.Equals(normalizedKind, "downtime", StringComparison.OrdinalIgnoreCase)',
        '|| string.Equals(normalizedKind, "aftermath", StringComparison.OrdinalIgnoreCase))',
    ],
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs": [
        "BuildWorkspaceConsequenceTruthProjection(",
        "BuildGovernedCampaignConsequenceStateProjection(",
        "BuildWorkspaceDowntimeAftermathProjection(",
        "ResolveConsequenceReturnLoopAction(",
        "ResolveConsequenceReturnLoopRoute(",
    ],
    "tests/RunServicesVerification/CampaignSpineRestoreVerification.cs": [
        "Governed campaign consequence updates should survive a community-store reload with durable heat, faction, contact, reputation, and downtime return-loop receipts.",
        "Downtime package generation should mint a durable governed downtime consequence that survives reload.",
        "Workspace server plane should keep governed consequence return-loop evidence attached to campaign memory and next-session carry-forward after reload.",
        "Workspace server plane should project the reloaded governed heat consequence on the campaign API surface.",
        "Workspace server plane should keep downtime consequence routes pinned to the governed aftermath return rail.",
        "CampaignConsequenceTruthProjection consequenceTruth = reloadedWorkspaceServerPlane.GetWorkspaceConsequenceTruth(user, reloadedWorkspace.WorkspaceId)",
        "DowntimeAftermathApiProjection downtimeAftermath = reloadedWorkspaceServerPlane.GetWorkspaceDowntimeAftermath(user, reloadedWorkspace.WorkspaceId)",
        "Governed consequence truth API should summarize promoted heat, faction, contact, reputation, downtime, and aftermath state with explicit return-loop posture.",
        "Downtime aftermath API should keep downtime receipts, consequence state, and return-loop evidence on the governed aftermath rail.",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var downtimeBriefResult = await campaignSpineController.GenerateMyCampaignWorkspaceAftermathRecapPackage(",
        'Assert(downtimeBriefPayload!.Summary.Contains("downtime brief", StringComparison.OrdinalIgnoreCase), "campaign spine downtime brief api should describe the governed downtime packet it generated.");',
        "var consequenceUpdateResult = await campaignSpineController.UpsertMyCampaignWorkspaceConsequence(",
        'Assert(consequenceUpdatePayload.Receipts.Any(item => string.Equals(item.SourceKind, "governed_consequence_update", StringComparison.Ordinal)), "campaign spine consequence api should emit a durable governed consequence update receipt.");',
        'Assert(consequenceUpdatePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(item.ReceiptId, "/account/work", StringComparison.Ordinal)), "campaign spine consequence api should attach a governed return-loop route receipt.");',
        "var factionConsequenceResult = await campaignSpineController.UpsertMyCampaignWorkspaceConsequence(",
        'Assert(factionConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Confirm faction standing", StringComparison.Ordinal)), "campaign spine consequence api should derive a governed faction return-loop action when the caller does not override it.");',
        "var contactConsequenceResult = await campaignSpineController.UpsertMyCampaignWorkspaceConsequence(",
        'Assert(contactConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Review contact fallout", StringComparison.Ordinal)), "campaign spine consequence api should derive a governed contact return-loop action when the caller does not override it.");',
        "var downtimeConsequenceResult = await campaignSpineController.UpsertMyCampaignWorkspaceConsequence(",
        'Assert(downtimeConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(item.ReceiptId, "/account/work#aftermath-packages", StringComparison.Ordinal)), "campaign spine consequence api should default downtime return-loop routes onto the governed aftermath rail.");',
        "var reputationConsequenceResult = await campaignSpineController.UpsertMyCampaignWorkspaceConsequence(",
        'Assert(reputationConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Review reputation fallout", StringComparison.Ordinal)), "campaign spine consequence api should derive a governed reputation return-loop action when the caller does not override it.");',
        "var invalidRouteConsequenceResult = await campaignSpineController.UpsertMyCampaignWorkspaceConsequence(",
        'Assert(invalidRouteStatusCode == StatusCodes.Status400BadRequest, $"campaign spine consequence api should reject non-canonical governed return-loop routes. status={invalidRouteStatusCode?.ToString() ?? "<null>"} detail={invalidRouteProblemDetail ?? "<none>"}");',
        'Assert(refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "downtime", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true, "campaign spine server plane api should promote downtime brief packages into durable governed downtime consequences.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "aftermath", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true, "campaign spine server plane api should promote aftermath packages into durable governed aftermath consequences.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "heat", StringComparison.Ordinal) && string.Equals(item.State, "high", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_consequence_update", StringComparison.Ordinal))) == true, "campaign spine server plane api should project governed consequence updates back onto the shared campaign workspace.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "faction", StringComparison.Ordinal) && string.Equals(item.State, "strained", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Confirm faction standing", StringComparison.Ordinal))) == true, "campaign spine server plane api should project governed faction updates with explicit return-loop action receipts.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "contact", StringComparison.Ordinal) && string.Equals(item.State, "fragile", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review contact fallout", StringComparison.Ordinal))) == true, "campaign spine server plane api should project governed contact updates with explicit return-loop action receipts.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "downtime", StringComparison.Ordinal) && string.Equals(item.State, "queued", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(receipt.ReceiptId, "/account/work#aftermath-packages", StringComparison.Ordinal))) == true, "campaign spine server plane api should project governed downtime return-loop routes back onto the shared campaign workspace.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "reputation", StringComparison.Ordinal) && string.Equals(item.State, "under_review", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review reputation fallout", StringComparison.Ordinal))) == true, "campaign spine server plane api should project governed reputation updates with explicit return-loop action receipts.");',
        "var consequencesListResult = await campaignSpineController.GetMyCampaignWorkspaceConsequences(workspaceId, CancellationToken.None);",
        'Assert(consequencesListPayload?.Any(item => string.Equals(item.Kind, "aftermath", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true, "campaign spine consequence listing api should surface aftermath consequence truth with durable package receipts.");',
        'Assert(consequencesListPayload?.Any(item => string.Equals(item.Kind, "downtime", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(receipt.ReceiptId, "/account/work#aftermath-packages", StringComparison.Ordinal))) == true, "campaign spine consequence listing api should keep downtime return-loop routes on the governed aftermath rail.");',
        'Assert(consequencesListPayload?.Any(item => string.Equals(item.Kind, "heat", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_consequence_update", StringComparison.Ordinal))) == true, "campaign spine consequence listing api should surface heat consequence truth with governed update receipts.");',
        'Assert(consequencesListPayload?.Any(item => string.Equals(item.Kind, "faction", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Confirm faction standing", StringComparison.Ordinal))) == true, "campaign spine consequence listing api should surface faction consequence truth with explicit return-loop actions.");',
        'Assert(consequencesListPayload?.Any(item => string.Equals(item.Kind, "contact", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review contact fallout", StringComparison.Ordinal))) == true, "campaign spine consequence listing api should surface contact consequence truth with explicit return-loop actions.");',
        'Assert(consequencesListPayload?.Any(item => string.Equals(item.Kind, "reputation", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review reputation fallout", StringComparison.Ordinal))) == true, "campaign spine consequence listing api should surface reputation consequence truth with explicit return-loop actions.");',
        "var consequenceTruthResult = await campaignSpineController.GetMyCampaignWorkspaceConsequenceTruth(workspaceId, CancellationToken.None);",
        'Assert(consequenceTruthPayload is not null && string.Equals(consequenceTruthPayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine consequence-truth api should expose a governed consequence summary for the selected workspace.");',
        'Assert(consequenceTruthPayload!.ConsequenceCount >= 6, "campaign spine consequence-truth api should summarize the promoted heat, faction, contact, reputation, downtime, and aftermath states.");',
        'Assert(consequenceTruthPayload.States.Any(item => string.Equals(item.Kind, "heat", StringComparison.Ordinal) && string.Equals(item.ReturnLoopRoute, "/account/work", StringComparison.Ordinal)), "campaign spine consequence-truth api should keep heat state pinned to the governed workspace return rail.");',
        'Assert(consequenceTruthPayload.ReturnLoopActions.Any(item => item.Contains("Review downtime obligations", StringComparison.Ordinal)), "campaign spine consequence-truth api should surface downtime return-loop actions on the governed summary.");',
        "var aftermathPackagesListResult = await campaignSpineController.GetMyCampaignWorkspaceAftermathRecapPackages(workspaceId, CancellationToken.None);",
        'Assert(aftermathPackagesListPayload?.Any(item => string.Equals(item.PackageId, aftermathPackagePayload.PackageId, StringComparison.Ordinal) && string.Equals(item.ArtifactKind, "RecapPackage", StringComparison.Ordinal)) == true, "campaign spine aftermath listing api should surface governed recap packages with registry-backed artifact posture.");',
        'Assert(aftermathPackagesListPayload?.Any(item => string.Equals(item.PackageId, downtimeBriefPayload.PackageId, StringComparison.Ordinal) && item.EvidenceLines.Any(line => line.StartsWith("Registry artifact:", StringComparison.OrdinalIgnoreCase))) == true, "campaign spine aftermath listing api should surface downtime packages with registry artifact evidence.");',
        'Assert(aftermathPackagesListPayload?.Any(item => string.Equals(item.PackageId, replayTimelinePayload.PackageId, StringComparison.Ordinal) && string.Equals(item.ArtifactKind, "ReplayPackage", StringComparison.Ordinal)) == true, "campaign spine aftermath listing api should surface replay packages on the same governed aftermath rail.");',
        "var downtimeAftermathResult = await campaignSpineController.GetMyCampaignWorkspaceDowntimeAftermath(workspaceId, CancellationToken.None);",
        'Assert(downtimeAftermathPayload is not null && string.Equals(downtimeAftermathPayload.WorkspaceId, workspaceId, StringComparison.Ordinal), "campaign spine downtime-aftermath api should expose a governed downtime and aftermath summary for the selected workspace.");',
        'Assert(string.Equals(downtimeAftermathPayload.ReturnLoopRoute, "/account/work#aftermath-packages", StringComparison.Ordinal), "campaign spine downtime-aftermath api should pin the governed return route to the aftermath rail.");',
        'Assert(downtimeAftermathPayload.ReturnLoopActions.Any(item => item.Contains("Review downtime obligations", StringComparison.Ordinal)), "campaign spine downtime-aftermath api should surface downtime return-loop actions.");',
        "var campaignMemoryResult = await campaignSpineController.GetMyCampaignWorkspaceCampaignMemory(workspaceId, CancellationToken.None);",
        'Assert(campaignMemoryPayload?.EvidenceLines.Any(item => item.Contains("Review heat fallout", StringComparison.Ordinal) || item.Contains("Review reputation fallout", StringComparison.Ordinal)) == true, "campaign spine campaign-memory api should surface governed consequence return-loop evidence.");',
        'Assert(campaignMemoryPayload?.EvidenceLines.Any(item => item.Contains("Review downtime obligations", StringComparison.Ordinal)) == true, "campaign spine campaign-memory api should keep downtime consequence truth attached to the return lane.");',
        "var carryForwardResult = await campaignSpineController.GetMyCampaignWorkspaceNextSessionCarryForward(workspaceId, CancellationToken.None);",
        'Assert(carryForwardPayload?.EvidenceLines.Any(item => item.Contains("Review heat fallout", StringComparison.Ordinal) || item.Contains("Review reputation fallout", StringComparison.Ordinal)) == true, "campaign spine carry-forward api should surface governed consequence return-loop evidence.");',
        'Assert(carryForwardPayload?.EvidenceLines.Any(item => item.Contains("Review downtime obligations", StringComparison.Ordinal)) == true, "campaign spine carry-forward api should keep downtime consequence truth attached to the next-session return.");',
    ],
    "scripts/materialize_campaign_os_local_proof.py": [
        'consequenceUpdatePayload is not null && string.Equals(consequenceUpdatePayload.Kind, "heat", StringComparison.Ordinal)',
        'consequenceUpdatePayload.Receipts.Any(item => string.Equals(item.SourceKind, "governed_consequence_update", StringComparison.Ordinal))',
        'consequenceUpdatePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Review heat fallout", StringComparison.Ordinal))',
        'consequenceUpdatePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(item.ReceiptId, "/account/work", StringComparison.Ordinal))',
        'factionConsequencePayload is not null && string.Equals(factionConsequencePayload.Kind, "faction", StringComparison.Ordinal)',
        'factionConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Confirm faction standing", StringComparison.Ordinal))',
        'contactConsequencePayload is not null && string.Equals(contactConsequencePayload.Kind, "contact", StringComparison.Ordinal)',
        'contactConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Review contact fallout", StringComparison.Ordinal))',
        'downtimeConsequencePayload is not null && string.Equals(downtimeConsequencePayload.Kind, "downtime", StringComparison.Ordinal)',
        'downtimeConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(item.ReceiptId, "/account/work#aftermath-packages", StringComparison.Ordinal))',
        'reputationConsequencePayload is not null && string.Equals(reputationConsequencePayload.Kind, "reputation", StringComparison.Ordinal)',
        'reputationConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Review reputation fallout", StringComparison.Ordinal))',
        'refreshedWorkspaceServerPlanePayload?.AftermathPackages.Any(item => string.Equals(item.PackageId, downtimeBriefPayload.PackageId, StringComparison.Ordinal)) == true',
        'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "downtime", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true',
        'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "aftermath", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true',
        'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "heat", StringComparison.Ordinal) && string.Equals(item.State, "high", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_consequence_update", StringComparison.Ordinal))) == true',
        'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "faction", StringComparison.Ordinal) && string.Equals(item.State, "strained", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Confirm faction standing", StringComparison.Ordinal))) == true',
        'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "contact", StringComparison.Ordinal) && string.Equals(item.State, "fragile", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review contact fallout", StringComparison.Ordinal))) == true',
        'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "downtime", StringComparison.Ordinal) && string.Equals(item.State, "queued", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(receipt.ReceiptId, "/account/work#aftermath-packages", StringComparison.Ordinal))) == true',
        'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "reputation", StringComparison.Ordinal) && string.Equals(item.State, "under_review", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review reputation fallout", StringComparison.Ordinal))) == true',
        "var consequencesListResult = await campaignSpineController.GetMyCampaignWorkspaceConsequences(workspaceId, CancellationToken.None);",
        'consequencesListPayload?.Any(item => string.Equals(item.Kind, "aftermath", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true',
        'consequencesListPayload?.Any(item => string.Equals(item.Kind, "reputation", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review reputation fallout", StringComparison.Ordinal))) == true',
        "var aftermathPackagesListResult = await campaignSpineController.GetMyCampaignWorkspaceAftermathRecapPackages(workspaceId, CancellationToken.None);",
        'aftermathPackagesListPayload?.Any(item => string.Equals(item.PackageId, replayTimelinePayload.PackageId, StringComparison.Ordinal) && string.Equals(item.ArtifactKind, "ReplayPackage", StringComparison.Ordinal)) == true',
        "var campaignMemoryResult = await campaignSpineController.GetMyCampaignWorkspaceCampaignMemory(workspaceId, CancellationToken.None);",
        'campaignMemoryPayload?.EvidenceLines.Any(item => item.Contains("Review downtime obligations", StringComparison.Ordinal)) == true',
        "var carryForwardResult = await campaignSpineController.GetMyCampaignWorkspaceNextSessionCarryForward(workspaceId, CancellationToken.None);",
        'carryForwardPayload?.EvidenceLines.Any(item => item.Contains("Review downtime obligations", StringComparison.Ordinal)) == true',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_campaign_consequence_truth.py",
        "python3 -m unittest tests/test_campaign_consequence_truth.py",
    ],
}

PROOF_MARKERS = [
    'consequenceUpdatePayload is not null && string.Equals(consequenceUpdatePayload.Kind, "heat", StringComparison.Ordinal)',
    'consequenceUpdatePayload.Receipts.Any(item => string.Equals(item.SourceKind, "governed_consequence_update", StringComparison.Ordinal))',
    'consequenceUpdatePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(item.ReceiptId, "/account/work", StringComparison.Ordinal))',
    'factionConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Confirm faction standing", StringComparison.Ordinal))',
    'contactConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Review contact fallout", StringComparison.Ordinal))',
    'reputationConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", StringComparison.Ordinal) && item.Summary.Contains("Review reputation fallout", StringComparison.Ordinal))',
    'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "downtime", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true',
    'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "aftermath", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true',
    'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "heat", StringComparison.Ordinal) && string.Equals(item.State, "high", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_consequence_update", StringComparison.Ordinal))) == true',
    'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "faction", StringComparison.Ordinal) && string.Equals(item.State, "strained", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Confirm faction standing", StringComparison.Ordinal))) == true',
    'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "contact", StringComparison.Ordinal) && string.Equals(item.State, "fragile", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review contact fallout", StringComparison.Ordinal))) == true',
    'refreshedWorkspaceServerPlanePayload?.Consequences.Any(item => string.Equals(item.Kind, "reputation", StringComparison.Ordinal) && string.Equals(item.State, "under_review", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "return_loop_action", StringComparison.Ordinal) && receipt.Summary.Contains("Review reputation fallout", StringComparison.Ordinal))) == true',
    'consequencesListPayload?.Any(item => string.Equals(item.Kind, "aftermath", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true',
    'campaignMemoryPayload?.EvidenceLines.Any(item => item.Contains("Review downtime obligations", StringComparison.Ordinal)) == true',
    'carryForwardPayload?.EvidenceLines.Any(item => item.Contains("Review downtime obligations", StringComparison.Ordinal)) == true',
]


def main() -> int:
    missing: list[str] = []
    fleet_queue_item: dict[str, object] | None = None
    design_queue_item: dict[str, object] | None = None
    for relative_path, markers in SOURCE_MARKERS.items():
        path = ROOT / relative_path
        if not path.is_file():
            missing.append(f"missing file: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: missing marker {marker!r}")

    fleet_queue_item = verify_queue_authority(missing, QUEUE_STAGING_PATH, "Fleet queue")
    design_queue_item = verify_queue_authority(missing, DESIGN_QUEUE_STAGING_PATH, "design queue")
    registry_task = verify_successor_registry(missing, SUCCESSOR_REGISTRY_PATH)
    verify_queue_parity(missing, fleet_queue_item, design_queue_item)
    verify_completion_parity(missing, fleet_queue_item, design_queue_item, registry_task)
    verify_proof(missing, PROOF_PATH)
    verify_release_proof(missing, RELEASE_PROOF_PATH, fleet_queue_item, design_queue_item, registry_task)

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("campaign consequence truth proof passed")
    return 0


def verify_queue_authority(missing: list[str], path: Path, label: str) -> dict[str, object] | None:
    if not path.is_file():
        missing.append(f"{label} is missing: {path}")
        return None
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = payload.get("items")
    if not isinstance(items, list):
        missing.append(f"{label} items must be a list: {path}")
        return None
    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{label} must contain exactly one {PACKAGE_ID} row: {path}")
        return None
    item = matches[0]
    expected = {
        "repo": "chummer6-hub",
        "work_task_id": 112.1,
        "milestone_id": MILESTONE_ID,
        "wave": "W11",
        "title": TITLE,
        "task": TASK,
        "allowed_paths": ALLOWED_PATHS,
        "owned_surfaces": OWNED_SURFACES,
    }
    for key, value in expected.items():
        if item.get(key) != value:
            missing.append(f"{label} {PACKAGE_ID} {key} must be {value!r}: {path}")
    if item.get("frontier_id") != FRONTIER_ID:
        missing.append(f"{label} {PACKAGE_ID} frontier_id must be {FRONTIER_ID}: {path}")
    verify_no_forbidden_proof_markers(missing, item, f"{label} {PACKAGE_ID}")
    return item


def verify_successor_registry(missing: list[str], path: Path) -> dict[str, object] | None:
    if not path.is_file():
        missing.append(f"successor registry is missing: {path}")
        return None
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    milestones = payload.get("milestones")
    if not isinstance(milestones, list):
        missing.append(f"successor registry milestones must be a list: {path}")
        return None
    matches = [item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID]
    if len(matches) != 1:
        missing.append(f"successor registry must contain exactly one milestone {MILESTONE_ID}: {path}")
        return None
    milestone = matches[0]
    if milestone.get("title") != "Campaign memory, downtime, heat, faction, and contact truth":
        missing.append(f"successor registry milestone {MILESTONE_ID} title drifted: {path}")
    tasks = milestone.get("work_tasks")
    if not isinstance(tasks, list):
        missing.append(f"successor registry milestone {MILESTONE_ID} work_tasks must be a list: {path}")
        return None
    task_matches = [
        item
        for item in tasks
        if isinstance(item, dict)
        and item.get("id") == 112.1
        and item.get("owner") == "chummer6-hub"
    ]
    if len(task_matches) != 1:
        missing.append(f"successor registry must contain exactly one chummer6-hub work task 112.1: {path}")
        return None
    task = task_matches[0]
    if task.get("title") != "Promote downtime, aftermath, heat, faction, contact, and reputation state into governed campaign APIs and receipts.":
        missing.append(f"successor registry task 112.1 title drifted: {path}")
    verify_no_forbidden_proof_markers(missing, task, "successor registry task 112.1")
    return task


def verify_queue_parity(
    missing: list[str],
    fleet_queue_item: dict[str, object] | None,
    design_queue_item: dict[str, object] | None,
) -> None:
    if fleet_queue_item is None or design_queue_item is None:
        return
    fleet_summary = normalize_queue_item_for_parity(fleet_queue_item)
    design_summary = normalize_queue_item_for_parity(design_queue_item)
    if fleet_summary != design_summary:
        missing.append("Fleet queue and design queue package rows drifted for next90-m112-hub-campaign-consequence-truth.")


def verify_completion_parity(
    missing: list[str],
    fleet_queue_item: dict[str, object] | None,
    design_queue_item: dict[str, object] | None,
    registry_task: dict[str, object] | None,
) -> None:
    if fleet_queue_item is None or design_queue_item is None or registry_task is None:
        return

    fleet_status = normalize_optional_text(fleet_queue_item.get("status"))
    design_status = normalize_optional_text(design_queue_item.get("status"))
    registry_status = normalize_optional_text(registry_task.get("status"))
    any_complete = any(status == "complete" for status in (fleet_status, design_status, registry_status))
    if not any_complete:
        return

    statuses = {
        "Fleet queue": fleet_status,
        "design queue": design_status,
        "successor registry": registry_status,
    }
    for label, status in statuses.items():
        if status != "complete":
            missing.append(f"{label} must mark {PACKAGE_ID} complete when any successor source closes the package.")

    completion_actions = {
        "Fleet queue": normalize_optional_text(fleet_queue_item.get("completion_action")),
        "design queue": normalize_optional_text(design_queue_item.get("completion_action")),
        "successor registry": normalize_optional_text(registry_task.get("completion_action")),
    }
    for label, action in completion_actions.items():
        if action != COMPLETION_ACTION:
            missing.append(f"{label} completion_action must be {COMPLETION_ACTION!r} for completed package {PACKAGE_ID}.")

    do_not_reopen_reasons = {
        "Fleet queue": normalize_optional_text(fleet_queue_item.get("do_not_reopen_reason")),
        "design queue": normalize_optional_text(design_queue_item.get("do_not_reopen_reason")),
        "successor registry": normalize_optional_text(registry_task.get("do_not_reopen_reason")),
    }
    for label, reason in do_not_reopen_reasons.items():
        if reason != DO_NOT_REOPEN_REASON:
            missing.append(f"{label} do_not_reopen_reason must match the package-specific closure note for {PACKAGE_ID}.")

    landed_commits = {
        "Fleet queue": normalize_optional_text(fleet_queue_item.get("landed_commit")),
        "design queue": normalize_optional_text(design_queue_item.get("landed_commit")),
        "successor registry": normalize_optional_text(registry_task.get("landed_commit")),
    }
    if len({value for value in landed_commits.values() if value}) != 1:
        missing.append(f"{PACKAGE_ID} landed_commit must match across Fleet queue, design queue, and successor registry when the package is complete.")
    for label, commit in landed_commits.items():
        if not commit:
            missing.append(f"{label} must record landed_commit for completed package {PACKAGE_ID}.")
        elif commit != LANDED_COMMIT:
            missing.append(f"{label} landed_commit must be {LANDED_COMMIT!r} for completed package {PACKAGE_ID}.")


def verify_proof(missing: list[str], path: Path) -> None:
    if not path.is_file():
        missing.append(f"campaign os proof is missing: {path}")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract_name") != "chummer6-hub.campaign_os_local_proof":
        missing.append(f"campaign os proof contract_name drifted: {path}")
    if payload.get("status") != "passed":
        missing.append(f"campaign os proof status must be 'passed': {path}")
    if payload.get("package_proof") != PACKAGE_PROOF:
        missing.append(f"campaign os proof package_proof drifted: {path}")
    if payload.get("source_file") != "tests/RunServicesSmoke/Program.cs":
        missing.append(f"campaign os proof source_file drifted: {path}")
    markers = (((payload.get("required_markers") or {}).get("campaign_session_recover_recap")) or [])
    if not isinstance(markers, list):
        missing.append(f"campaign os proof campaign_session_recover_recap markers must be a list: {path}")
        return
    for marker in PROOF_MARKERS:
        if marker not in markers:
            missing.append(f"{path}: missing proof marker {marker!r}")
    verify_no_forbidden_proof_markers(missing, markers, f"campaign os proof {path}")


def verify_release_proof(
    missing: list[str],
    path: Path,
    fleet_queue_item: dict[str, object] | None,
    design_queue_item: dict[str, object] | None,
    registry_task: dict[str, object] | None,
) -> None:
    statuses = (
        normalize_optional_text((fleet_queue_item or {}).get("status")),
        normalize_optional_text((design_queue_item or {}).get("status")),
        normalize_optional_text((registry_task or {}).get("status")),
    )
    if "complete" not in statuses:
        return
    if not path.is_file():
        missing.append(f"hub local release proof is missing: {path}")
        return

    payload = json.loads(path.read_text(encoding="utf-8"))
    packages = payload.get("successor_queue_packages_by_id")
    if not isinstance(packages, dict):
        missing.append(f"{path}: successor_queue_packages_by_id must be a mapping")
        return

    package = packages.get(PACKAGE_ID)
    if not isinstance(package, dict):
        missing.append(f"{path}: successor_queue_packages_by_id must include {PACKAGE_ID}")
    else:
        expected_package = {
            "package_id": PACKAGE_ID,
            "milestone_id": MILESTONE_ID,
            "frontier_id": FRONTIER_ID,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": COMPLETION_ACTION,
            "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
            "landed_commit": LANDED_COMMIT,
            "title": TITLE,
            "task": TASK,
            "wave": "W11",
            "allowed_paths": ALLOWED_PATHS,
            "owned_surfaces": OWNED_SURFACES,
            "exit_criterion": "Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.",
        }
        for key, expected in expected_package.items():
            if package.get(key) != expected:
                missing.append(f"{path}: successor_queue_packages_by_id[{PACKAGE_ID}].{key} must be {expected!r}")
        verify_no_forbidden_proof_markers(missing, package, f"hub local release proof {PACKAGE_ID}")

    receipts = payload.get("proof_receipts")
    if not isinstance(receipts, list):
        missing.append(f"{path}: proof_receipts must be a list")
        return

    expected_receipts = {
        "campaign_memory:consequence_truth": {
            "routes": ["/api/v1/campaign-spine/me/workspaces/{workspaceId}/campaign-memory", "/api/v1/campaign-spine/me/workspaces/{workspaceId}/consequence-truth", "/account/work#campaign-consequences"],
            "surfaces": ["campaign_memory:consequence_truth", "campaign_consequence_truth", "campaign_return_loop"],
        },
        "downtime_aftermath:api": {
            "routes": ["/api/v1/campaign-spine/me/workspaces/{workspaceId}/aftermath-recap-packages", "/api/v1/campaign-spine/me/workspaces/{workspaceId}/downtime-aftermath", "/account/work#aftermath-packages"],
            "surfaces": ["downtime_aftermath:api", "governed_aftermath_package", "return_loop_action"],
        },
    }
    package_receipts = [
        receipt for receipt in receipts if isinstance(receipt, dict) and receipt.get("package_id") == PACKAGE_ID
    ]
    for receipt_id, expected in expected_receipts.items():
        matching = [receipt for receipt in package_receipts if receipt.get("receipt_id") == receipt_id]
        if len(matching) != 1:
            missing.append(f"{path}: proof_receipts must contain exactly one {receipt_id}")
            continue
        receipt = matching[0]
        if receipt.get("milestone_id") != MILESTONE_ID:
            missing.append(f"{path}: proof_receipts[{receipt_id}].milestone_id must be {MILESTONE_ID}")
        if receipt.get("frontier_id") != FRONTIER_ID:
            missing.append(f"{path}: proof_receipts[{receipt_id}].frontier_id must be {FRONTIER_ID}")
        for route in expected["routes"]:
            if route not in receipt.get("routes", []):
                missing.append(f"{path}: proof_receipts[{receipt_id}] must include route {route}")
        for surface in expected["surfaces"]:
            if surface not in receipt.get("surfaces", []):
                missing.append(f"{path}: proof_receipts[{receipt_id}] must include surface {surface}")
        verify_no_forbidden_proof_markers(missing, receipt, f"hub local release proof receipt {receipt_id}")


def verify_no_forbidden_proof_markers(missing: list[str], value: object, label: str) -> None:
    for marker in forbidden_markers_in_value(value):
        missing.append(f"{label} has forbidden active-run proof marker: {marker}")


def forbidden_markers_in_value(value: object) -> list[str]:
    if isinstance(value, dict):
        markers: list[str] = []
        for child in value.values():
            markers.extend(forbidden_markers_in_value(child))
        return sorted(set(markers), key=str.casefold)
    if isinstance(value, list):
        markers: list[str] = []
        for child in value:
            markers.extend(forbidden_markers_in_value(child))
        return sorted(set(markers), key=str.casefold)
    if isinstance(value, str):
        return forbidden_markers_in_text(value)
    return []


def forbidden_markers_in_text(value: str) -> list[str]:
    matches: list[str] = []
    for decoded in decoded_marker_texts(value):
        folded = decoded.casefold()
        normalized = normalize_marker_text(decoded)
        for marker in FORBIDDEN_PROOF_MARKERS:
            marker_folded = marker.casefold()
            if marker_folded in folded or normalize_marker_text(marker) in normalized:
                matches.append(marker)
    return sorted(set(matches), key=str.casefold)


def decoded_marker_texts(value: str) -> list[str]:
    candidates = [value, unescape(value), unquote(value)]
    for text in list(candidates):
        compact = re.sub(r"\s+", "", text)
        if len(compact) < 12:
            continue
        for decoder in (decode_base64_bytes, decode_base32_bytes, decode_base85_bytes, decode_ascii85_bytes):
            decoded = decoder(compact)
            if decoded is not None:
                decoded_text = bytes_to_marker_text(decoded)
                if decoded_text is not None:
                    candidates.append(decoded_text)
                decompressed_text = decompress_marker_bytes(decoded)
                if decompressed_text is not None:
                    candidates.append(decompressed_text)
    return candidates


def decode_base64_bytes(value: str) -> bytes | None:
    padded = value + ("=" * (-len(value) % 4))
    return decode_bytes(lambda: b64decode(padded, validate=True))


def decode_base32_bytes(value: str) -> bytes | None:
    padded = value + ("=" * (-len(value) % 8))
    return decode_bytes(lambda: b32decode(padded, casefold=True))


def decode_base85_bytes(value: str) -> bytes | None:
    return decode_bytes(lambda: b85decode(value))


def decode_ascii85_bytes(value: str) -> bytes | None:
    return decode_bytes(lambda: a85decode(value))


def decode_bytes(factory: Callable[[], bytes]) -> bytes | None:
    try:
        return factory()
    except (BinasciiError, ValueError):
        return None


def bytes_to_marker_text(value: bytes) -> str | None:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if is_plausible_marker_text(text) else None


def decompress_marker_bytes(value: bytes) -> str | None:
    try:
        decoded = decompress(value)
    except ZlibError:
        return None
    return bytes_to_marker_text(decoded)


def is_plausible_marker_text(value: str) -> bool:
    if not value:
        return False
    printable = sum(1 for ch in value if ch.isprintable() or ch.isspace())
    return printable / len(value) > 0.9


def normalize_marker_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def normalize_queue_item_for_parity(item: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key in (
        "package_id",
        "frontier_id",
        "work_task_id",
        "milestone_id",
        "wave",
        "repo",
        "title",
        "task",
        "allowed_paths",
        "owned_surfaces",
        "status",
        "landed_commit",
        "completion_action",
        "do_not_reopen_reason",
        "proof",
    ):
        if key in item:
            normalized[key] = item[key]
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
