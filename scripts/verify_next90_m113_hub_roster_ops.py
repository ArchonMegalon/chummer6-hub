#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m113-hub-roster-ops"
TITLE = "Land crew, roster, and event movement APIs"
TASK = "Make dossiers move between rosters, campaigns, groups, and events with ownership and audit receipts."
FRONTIER_ID = 1469041280
MILESTONE_ID = 113
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["crew_roster_ops", "campaign_group_event_movement"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "run_ooda_design_supervisor_until_quiet",
    "ooda_design_supervisor.py",
    "supervisor status",
    "supervisor eta",
    "status_query_supported",
    "polling_disabled",
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_PROOF",
        ROOT / ".codex-studio" / "published" / "NEXT90_M113_HUB_ROSTER_OPS.generated.json",
    )
)
PACKAGE_PROOF = {
    "package_id": PACKAGE_ID,
    "title": TITLE,
    "task": TASK,
    "frontier_id": FRONTIER_ID,
    "milestone_id": MILESTONE_ID,
    "allowed_paths": ALLOWED_PATHS,
    "owned_surfaces": OWNED_SURFACES,
}

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Contracts/CampaignMovementContracts.cs": [
        "public sealed record DossierMovementRequest(",
        "public sealed record DossierMovementPlannerProjection(",
        "public sealed record DossierMovementReceiptProjection(",
        "bool EventChanged,",
        "RosterTransferProjection TransferReceipt);",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpGet("me/workspaces/{workspaceId}/dossier-movement-plan")]',
        "GetMyCampaignWorkspaceDossierMovementPlan(",
        '_campaignSpine.GetDossierMovementPlan(user, workspaceId, installLinking);',
        '[HttpGet("me/workspaces/{workspaceId}/dossier-movements")]',
        "GetMyCampaignWorkspaceDossierMovements(",
        "_campaignSpine.GetDossierMovements(user, workspaceId, installLinking)",
        '[HttpPost("me/dossier-movements")]',
        "MoveMyDossier(",
        'return BadRequest("dossier-movement payload is required.");',
        "return Ok(_campaignSpine.MoveDossier(user, request));",
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        "public DossierMovementPlannerProjection? GetDossierMovementPlan(",
        "public IReadOnlyList<DossierMovementReceiptProjection> GetDossierMovements(",
        "public DossierMovementReceiptProjection MoveDossier(",
        "MovementResolution movement = ExecuteDossierMovementLocked(",
        "MovementTargetEvent targetEvent = ResolveOrCreateMovementTargetEventLocked(",
        "bool eventChanged = !string.Equals(sourceRun?.RunId, targetEvent.Run.RunId, StringComparison.OrdinalIgnoreCase)",
        'SourceKind: "target_run",',
        'SourceKind: "target_scene",',
        "private sealed record DossierMovementCommand(",
        "private sealed record MovementResolution(",
    ],
    "Chummer.Tests/CampaignMovementServiceTests.cs": [
        "MoveDossierPersistsTargetEventOwnershipAndAuditReceipts",
        'TargetRunTitle: "Dockside handoff",',
        'TargetSceneTitle: "Pier 3 exchange",',
        'Assert.Equal("Dockside handoff", movement.TargetRunTitle);',
        'Assert.Equal("Pier 3 exchange", movement.TargetSceneTitle);',
        'Assert.Contains(workspaceReceipts, item => string.Equals(item.MovementId, movement.MovementId, StringComparison.OrdinalIgnoreCase));',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var dossierMovementPlanResult = await campaignSpineController.GetMyCampaignWorkspaceDossierMovementPlan(workspaceId, CancellationToken.None);",
        'dossierMovementPlanPayload.TargetGroups.SelectMany(item => item.CampaignOptions).Any(item => item.EventOptions.Count >= 1)',
        "var dossierMovementResult = await campaignSpineController.MoveMyDossier(",
        'string.Equals(dossierMovementPayload.TargetRunTitle, "Dockside handoff", StringComparison.Ordinal)',
        'string.Equals(dossierMovementPayload.TargetSceneTitle, "Pier 3 exchange", StringComparison.Ordinal)',
        'dossierMovementPayload.Receipts.Any(item => string.Equals(item.SourceKind, "target_run", StringComparison.Ordinal))',
        'dossierMovementPayload.Receipts.Any(item => string.Equals(item.SourceKind, "target_scene", StringComparison.Ordinal))',
        "var dossierMovementsResult = await campaignSpineController.GetMyCampaignWorkspaceDossierMovements(workspaceId, CancellationToken.None);",
        'dossierMovementsPayload?.Any(item => string.Equals(item.MovementId, dossierMovementPayload.MovementId, StringComparison.Ordinal)) == true',
        'outsiderDossierMovementsPayload?.Any(item => string.Equals(item.MovementId, dossierMovementPayload.MovementId, StringComparison.Ordinal)) == true',
    ],
    "scripts/materialize_campaign_os_local_proof.py": [
        'campaignSpineController.GetMyCampaignWorkspaceDossierMovementPlan',
        'dossierMovementPlanPayload.TargetGroups.Count >= 1',
        'var dossierMovementResult = await campaignSpineController.MoveMyDossier(',
        'dossierMovementPayload.Receipts.Any(item => string.Equals(item.SourceKind, "target_run", StringComparison.Ordinal))',
        'dossierMovementsPayload?.Any(item => string.Equals(item.MovementId, dossierMovementPayload.MovementId, StringComparison.Ordinal)) == true',
    ],
    "scripts/materialize_next90_m113_hub_roster_ops_proof.py": [
        '"package_id": "next90-m113-hub-roster-ops"',
        '"frontier_id": 1469041280',
        '"milestone_id": 113',
        '"owned_surfaces": ["crew_roster_ops", "campaign_group_event_movement"]',
        '"contract_name": "chummer6-hub.next90_m113_hub_roster_ops"',
        '"campaign_group_event_movement": [',
        '"crew_roster_ops": [',
        '"var dossierMovementResult = await campaignSpineController.MoveMyDossier("',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m113_hub_roster_ops_proof.py",
        "python3 scripts/verify_next90_m113_hub_roster_ops.py",
        "python3 -m unittest tests/test_next90_m113_hub_roster_ops.py",
        "run_slice_safe_dotnet_test CampaignMovementServiceTests",
    ],
}

PROOF_MARKERS = [
    "var dossierMovementPlanResult = await campaignSpineController.GetMyCampaignWorkspaceDossierMovementPlan(workspaceId, CancellationToken.None);",
    "dossierMovementPlanPayload.TargetGroups.Count >= 1",
    'dossierMovementPlanPayload.TargetGroups.SelectMany(item => item.CampaignOptions).Any(item => item.EventOptions.Count >= 1)',
    'var dossierMovementResult = await campaignSpineController.MoveMyDossier(',
    'Assert(dossierMovementPayload is not null && string.Equals(dossierMovementPayload.DossierId, sourceDossier.DossierId, StringComparison.Ordinal)',
    'Assert(dossierMovementPayload!.GroupChanged, "campaign spine dossier-movement api should report when the governed roster group changes.")',
    'Assert(dossierMovementPayload.EventChanged, "campaign spine dossier-movement api should report when the governed run or scene changes.")',
    'string.Equals(dossierMovementPayload.TargetRunTitle, "Dockside handoff", StringComparison.Ordinal)',
    'string.Equals(dossierMovementPayload.TargetSceneTitle, "Pier 3 exchange", StringComparison.Ordinal)',
    'dossierMovementPayload.Receipts.Any(item => string.Equals(item.SourceKind, "target_run", StringComparison.Ordinal))',
    'dossierMovementPayload.Receipts.Any(item => string.Equals(item.SourceKind, "target_scene", StringComparison.Ordinal))',
    'dossierMovementsPayload?.Any(item => string.Equals(item.MovementId, dossierMovementPayload.MovementId, StringComparison.Ordinal)) == true',
    'outsiderDossierMovementsPayload?.Any(item => string.Equals(item.MovementId, dossierMovementPayload.MovementId, StringComparison.Ordinal)) == true',
]


def normalize_legacy_queue_payload(raw: str) -> str:
    """Normalize legacy malformed queue YAML so strict parsing can proceed."""

    marker = raw.find("items:")
    if marker >= 0:
        raw = raw[marker:]

    def is_key_line(candidate: str) -> bool:
        text = candidate.lstrip()
        if not text or text.startswith(("-", "?")):
            return False
        if ":" not in text:
            return False
        key, _, _ = text.partition(":")
        return bool(key) and " " not in key and "\t" not in key

    normalized: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            normalized.append("")
            continue
        if (
            normalized
            and line.startswith(" ")
            and not line.lstrip().startswith("-")
            and not is_key_line(line)
            and not line.strip().startswith("?")
        ):
            normalized[-1] = f"{normalized[-1]} {line.strip()}"
        else:
            normalized.append(line)

    return "\n".join(normalized) + "\n"


def load_queue_payload(path: Path) -> object:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(raw)
        if payload is not None:
            return payload
    except yaml.YAMLError:
        payload = yaml.safe_load(normalize_legacy_queue_payload(raw))
        if payload is not None:
            return payload
    return {}


def load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def verify_queue_authority(missing: list[str], path: Path) -> None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return

    payload = load_queue_payload(path) or {}
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

    if milestone.get("title") != "Crew, roster, opposition packets, and GM prep library":
        missing.append(f"{path}: milestone {MILESTONE_ID} title drifted")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        missing.append(f"{path}: milestone {MILESTONE_ID} work_tasks is missing")
        return

    task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == "113.1"), None)
    if task is None:
        missing.append(f"{path}: work task 113.1 is missing")
        return

    if task.get("owner") != "chummer6-hub":
        missing.append(f"{path}: work task 113.1 owner drifted")
    if task.get("title") != "Land crew, roster, campaign-group, and event movement APIs with ownership and audit posture.":
        missing.append(f"{path}: work task 113.1 title drifted")


def verify_proof(missing: list[str], path: Path) -> None:
    if not path.is_file():
        missing.append(f"missing generated proof: {path}")
        return

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract_name") != "chummer6-hub.next90_m113_hub_roster_ops":
        missing.append(f"{path}: contract_name drifted")
    if payload.get("package_proof") != PACKAGE_PROOF:
        missing.append(f"{path}: package_proof drifted")

    required_markers = payload.get("required_markers")
    if not isinstance(required_markers, dict):
        missing.append(f"{path}: required_markers is missing")
        return

    proof_markers = []
    for section_name in ("campaign_group_event_movement", "crew_roster_ops"):
        section_markers = required_markers.get(section_name)
        if not isinstance(section_markers, list):
            missing.append(f"{path}: {section_name} markers are missing")
            continue
        proof_markers.extend(section_markers)

    for marker in PROOF_MARKERS:
        if marker not in proof_markers:
            missing.append(f"{path}: missing proof marker {marker!r}")

    encoded_blob = json.dumps(payload, sort_keys=True)
    lowered = encoded_blob.lower()
    for marker in FORBIDDEN_PROOF_MARKERS:
        if marker.lower() in lowered:
            missing.append(f"{path}: forbidden active-run proof marker: {marker}")


def main() -> int:
    missing: list[str] = []
    for relative_path, markers in SOURCE_MARKERS.items():
        path = ROOT / relative_path
        if not path.is_file():
            missing.append(f"missing file: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: missing marker {marker!r}")

    verify_queue_authority(missing, QUEUE_STAGING_PATH)
    verify_successor_registry(missing, SUCCESSOR_REGISTRY_PATH)
    verify_proof(missing, PROOF_PATH)

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m113 hub roster ops proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
