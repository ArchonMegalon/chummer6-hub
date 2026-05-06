#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m115-hub-dossier-federation-orchestration"
TITLE = "Orchestrate campaign federation and replay or recap package flows from governed source packs"
TASK = "Orchestrate campaign federation and replay or recap package flows from governed source packs."
FRONTIER_ID = 1955524661
MILESTONE_ID = 115
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["dossier_federation:hub", "replay_package_federation", "recap_package_federation"]
LANDED_COMMIT = "9c25a2b2"
COMPLETION_ACTION = "verify_closed_package_only"
DO_NOT_REOPEN_REASON = (
    "M115 chummer6-hub dossier federation orchestration is complete; future shards must verify this receipt, "
    "registry row, queue row, and design-queue row instead of reopening the campaign federation source-pack package."
)
PROOF_MARKERS = [
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Contracts/CampaignFederationContracts.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Community/CampaignFederationOrchestrationService.cs",
    "/docker/chummercomplete/chummer.run-services/tests/RunServicesSmoke/Program.cs",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_next90_m115_hub_dossier_federation.py",
    "/docker/chummercomplete/chummer.run-services/tests/test_next90_m115_hub_dossier_federation.py",
    "/docker/chummercomplete/chummer.run-services commit 9c25a2b2 adds campaign federation source-pack orchestration.",
    "python3 scripts/verify_next90_m115_hub_dossier_federation.py",
    "python3 -m unittest tests/test_next90_m115_hub_dossier_federation.py",
    "bash scripts/ai/run_services_smoke.sh",
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M115_HUB_DOSSIER_FEDERATION_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M115_HUB_DOSSIER_FEDERATION_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M115_HUB_DOSSIER_FEDERATION_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M115_HUB_DOSSIER_FEDERATION_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Contracts/CampaignFederationContracts.cs": [
        "public sealed record CampaignFederationBatchRequest(",
        "public sealed record CampaignFederationSourcePackProjection(",
        "public sealed record CampaignFederationBatchProjection(",
        "ArtifactFactoryJobBatchLaunchResult Batch",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpPost("me/workspaces/{workspaceId}/federation-batches")]',
        "LaunchMyCampaignWorkspaceFederationBatch(",
        'return BadRequest("campaign federation payload is required.");',
        "_campaignFederation.LaunchWorkspaceFederationBatch(user, workspaceId, request, installLinking);",
    ],
    "Chummer.Run.Api/Services/Community/CampaignFederationOrchestrationService.cs": [
        "public CampaignFederationBatchProjection? LaunchWorkspaceFederationBatch(",
        'RequiredFamilies: ["publication"]',
        'RequestedBy: "hub.campaign-federation"',
        'sourcePackKind = candidate.IsReplay || candidate.IsRecap',
        '? "campaign_recap"',
        ': "creator_publication";',
        'string publicShelfRef = $"/artifacts/publications/{Uri.EscapeDataString(candidate.PublicationId)}";',
        '"replay:{candidate.EntryId}"',
        '"recap:{candidate.EntryId}"',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var campaignFederation = new CampaignFederationOrchestrationService(campaignSpine, new ArtifactFactoryOrchestrationService());",
        "LaunchMyCampaignWorkspaceFederationBatch(",
        "new CampaignFederationBatchRequest(",
        'replayTimelinePayload.PackageId',
        'federationBatchPayload.Batch.Families.Contains("publication", StringComparer.OrdinalIgnoreCase)',
        'federationBatchPayload.Batch.RequiredReceiptRefs.Any(item => item.StartsWith("replay:", StringComparison.Ordinal))',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m115_hub_dossier_federation.py",
        "python3 -m unittest tests/test_next90_m115_hub_dossier_federation.py",
    ],
    "tests/test_next90_m115_hub_dossier_federation.py": [
        "class Next90M115HubDossierFederationTests(unittest.TestCase):",
        'self.assertIn(\'[HttpPost("me/workspaces/{workspaceId}/federation-batches")]\', result.stderr)',
        'self.assertIn("campaign_recap", result.stderr)',
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
    }
    for key, value in expected_fields.items():
        if item.get(key) != value:
            missing.append(f"{path}: {PACKAGE_ID} {key} must be {value!r}")

    if "frontier_id" in item and item.get("frontier_id") != FRONTIER_ID:
        missing.append(f"{path}: {PACKAGE_ID} frontier_id must be {FRONTIER_ID!r} when present")
    if item.get("status") != "complete":
        missing.append(f"{path}: {PACKAGE_ID} status must be 'complete'")
    if item.get("landed_commit") != LANDED_COMMIT:
        missing.append(f"{path}: {PACKAGE_ID} landed_commit must be {LANDED_COMMIT!r}")
    if item.get("completion_action") != COMPLETION_ACTION:
        missing.append(f"{path}: {PACKAGE_ID} completion_action must be {COMPLETION_ACTION!r}")
    if item.get("do_not_reopen_reason") != DO_NOT_REOPEN_REASON:
        missing.append(f"{path}: {PACKAGE_ID} do_not_reopen_reason drifted")
    if item.get("allowed_paths") != ALLOWED_PATHS:
        missing.append(f"{path}: allowed_paths must be {ALLOWED_PATHS!r}")
    if item.get("owned_surfaces") != OWNED_SURFACES:
        missing.append(f"{path}: owned_surfaces must be {OWNED_SURFACES!r}")

    proof = item.get("proof")
    if not isinstance(proof, list):
        missing.append(f"{path}: {PACKAGE_ID} proof must be a list")
        return

    for marker in PROOF_MARKERS:
        if marker not in proof:
            missing.append(f"{path}: {PACKAGE_ID} proof is missing {marker!r}")

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

    if milestone.get("title") != "Portable dossier, campaign federation, replay, recap, and external exchange":
        missing.append(f"{path}: milestone {MILESTONE_ID} title drifted")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        missing.append(f"{path}: milestone {MILESTONE_ID} work_tasks is missing")
        return

    task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == "115.2"), None)
    if task is None:
        missing.append(f"{path}: work task 115.2 is missing")
        return

    if task.get("owner") != "chummer6-hub":
        missing.append(f"{path}: work task 115.2 owner drifted")
    if task.get("title") != "Orchestrate campaign federation and replay or recap package flows from governed source packs.":
        missing.append(f"{path}: work task 115.2 title drifted")


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
<<<<<<< HEAD
    verify_queue_authority(missing, DESIGN_QUEUE_STAGING_PATH)
=======
>>>>>>> 9c25a2b2 (Add campaign federation source-pack orchestration)
    verify_successor_registry(missing, SUCCESSOR_REGISTRY_PATH)
    verify_source_markers(missing)

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m115 hub dossier federation proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
