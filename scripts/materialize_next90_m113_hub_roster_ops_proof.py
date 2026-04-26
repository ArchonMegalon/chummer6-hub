#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m113-hub-roster-ops",
    "title": "Land crew, roster, and event movement APIs",
    "task": "Make dossiers move between rosters, campaigns, groups, and events with ownership and audit receipts.",
    "frontier_id": 1469041280,
    "milestone_id": 113,
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["crew_roster_ops", "campaign_group_event_movement"],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_ROOT", DEFAULT_ROOT))
SOURCE = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_SOURCE",
        ROOT / "tests" / "RunServicesSmoke" / "Program.cs",
    )
)
OUT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_PROOF_OUT",
        ROOT / ".codex-studio" / "published" / "NEXT90_M113_HUB_ROSTER_OPS.generated.json",
    )
)

REQUIRED_MARKERS = {
    "campaign_group_event_movement": [
        "var dossierMovementPlanResult = await campaignSpineController.GetMyCampaignWorkspaceDossierMovementPlan(workspaceId, CancellationToken.None);",
        "dossierMovementPlanPayload.TargetGroups.Count >= 1",
        'dossierMovementPlanPayload.TargetGroups.SelectMany(item => item.CampaignOptions).Any(item => item.EventOptions.Count >= 1)',
        "var dossierMovementResult = await campaignSpineController.MoveMyDossier(",
        'Assert(dossierMovementPayload is not null && string.Equals(dossierMovementPayload.DossierId, sourceDossier.DossierId, StringComparison.Ordinal)',
        'Assert(dossierMovementPayload!.GroupChanged, "campaign spine dossier-movement api should report when the governed roster group changes.")',
        'Assert(dossierMovementPayload.EventChanged, "campaign spine dossier-movement api should report when the governed run or scene changes.")',
        'string.Equals(dossierMovementPayload.TargetRunTitle, "Dockside handoff", StringComparison.Ordinal)',
        'string.Equals(dossierMovementPayload.TargetSceneTitle, "Pier 3 exchange", StringComparison.Ordinal)',
        'dossierMovementPayload.Receipts.Any(item => string.Equals(item.SourceKind, "target_run", StringComparison.Ordinal))',
        'dossierMovementPayload.Receipts.Any(item => string.Equals(item.SourceKind, "target_scene", StringComparison.Ordinal))',
        "var dossierMovementsResult = await campaignSpineController.GetMyCampaignWorkspaceDossierMovements(workspaceId, CancellationToken.None);",
        'dossierMovementsPayload?.Any(item => string.Equals(item.MovementId, dossierMovementPayload.MovementId, StringComparison.Ordinal)) == true',
        'outsiderDossierMovementsPayload?.Any(item => string.Equals(item.MovementId, dossierMovementPayload.MovementId, StringComparison.Ordinal)) == true',
    ],
    "crew_roster_ops": [
        "var rosterTransferPlanResult = await campaignSpineController.GetMyCampaignWorkspaceRosterTransferPlan(workspaceId, CancellationToken.None);",
        "rosterTransferPlanPayload.TargetGroups.Count >= 1",
        "var rosterTransferResult = await campaignSpineController.TransferMyRoster(",
        'string.Equals(rosterTransferPayload!.CurrentOwnerUserId, transferTargetUser.UserId, StringComparison.Ordinal)',
        'rosterTransferPayload.Summary.Contains("ownership transferred", StringComparison.OrdinalIgnoreCase)',
        'outsiderWorkspace is not null && outsiderWorkspace.RosterTransfers?.Any(item => string.Equals(item.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)) == true',
        'outsiderWorkspaceServerPlanePayload is not null && outsiderWorkspaceServerPlanePayload.RosterTransfers.Any(item => string.Equals(item.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal))',
        'operatorWorkModel?.CampaignSpine.CommunityOperations.Any(item => item.RecentRosterTransfers?.Any(transfer => string.Equals(transfer.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)) == true) == true',
        'postTransferWorkHomeModel?.LeadWorkspaceServerPlane?.RosterTransfers.Any(item => string.Equals(item.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)) == true',
        'postTransferWorkHomeModel?.CampaignSpine.CommunityOperations.Any(item => item.RecentRosterTransfers?.Any(transfer => string.Equals(transfer.TransferId, rosterTransferPayload.TransferId, StringComparison.Ordinal)) == true) == true',
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
    surfaces_passed: list[str] = []

    for surface, markers in REQUIRED_MARKERS.items():
        surface_missing = [marker for marker in markers if marker not in text]
        if surface_missing:
            for marker in surface_missing:
                missing.append(f"{surface}: {marker}")
            continue
        surfaces_passed.append(surface)

    if missing:
        for item in missing:
            print(f"next90_m113_hub_roster_ops_missing: {item}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m113_hub_roster_ops",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": canonical_source_path(),
        "surfaces_passed": surfaces_passed,
        "required_markers": REQUIRED_MARKERS,
    }

    if OUT.is_file():
        try:
            existing_payload = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_payload = None

        if isinstance(existing_payload, dict) and without_generated_at(existing_payload) == payload:
            print(f"next90 m113 hub roster ops proof unchanged: {OUT}")
            return 0

    payload["generated_at"] = iso_now()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m113 hub roster ops proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
