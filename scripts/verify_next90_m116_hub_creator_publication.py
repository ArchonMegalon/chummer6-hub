#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m116-hub-creator-publication"
TITLE = "Build creator publication discovery and moderation orchestration"
TASK = "Make creator publication discovery, submission, moderation, trust ranking, and correction flows run from approved manifests."
FRONTIER_ID = 3131897979
MILESTONE_ID = 116
WORK_TASK_ID = "116.1"
WORK_TASK_TITLE = "Build creator publication discovery, moderation, and submission orchestration from approved artifact manifests."
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["creator_publication:discovery", "creator_publication:moderation"]
EXPECTED_STATUS = "in_progress"

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Controllers/AccountsController.cs": [
        '[HttpPost("/account/work/publications/{publicationId}/submit")]',
        '[HttpPost("/account/work/publications/{publicationId}/approve")]',
        '[HttpPost("/account/work/publications/{publicationId}/publish")]',
        '[HttpPost("/account/work/publications/{publicationId}/reject")]',
        "static (bridge, user, publication, workspace, mutationNotes) => bridge.RejectReview(user, publication, workspace, mutationNotes));",
    ],
    "Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs": [
        "public CreatorPublicationRegistryProjection SubmitForReview(",
        "public CreatorPublicationRegistryProjection ApproveReview(",
        "public CreatorPublicationRegistryProjection RejectReview(",
        "public CreatorPublicationRegistryProjection Publish(",
        "EnsureManifestAuthority(publication, workspace);",
        '"Creator publication moderation requires an approved manifest-backed audit receipt before submission, correction, approval, or publication."',
        'NormalizeOptional(notes) ?? $"{publication.Title} entered governed shared-publication review."',
        'NormalizeOptional(notes) ?? $"{publication.Title} needs revision before governed shared-publication review can continue."',
        'NormalizeOptional(notes) ?? $"{publication.Title} is live on governed shared-publication discovery."',
        '"Publication kind: {ResolvePublicationKindLabel(publication, linkedShelfEntry)}"',
        '"Manifest authority: {BuildManifestAuthority(publication, workspace, linkedShelfEntry)}"',
        'return $"approved-shared-publication-manifest; workspace:{workspaceId}; artifact:{artifactId}; audit:{approvedAuditSummary}";',
        'return "missing-audit-receipt";',
    ],
    "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs": [
        "public IReadOnlyList<CreatorPublicationProjection> ListDiscoverable(int limit = 3)",
        "public CreatorPublicationProjection? GetDiscoverable(string publicationId)",
        "HasApprovedManifestAuthority(item.Draft, item.Detail)",
        ".OrderByDescending(item => RankTrustBand(item.TrustBand))",
        ".ThenByDescending(static item => item.UpdatedAtUtc)",
        "RankTrustBand(item.TrustBand)",
        'description.Contains("Manifest authority: approved-shared-publication-manifest;", StringComparison.Ordinal)',
        '!description.Contains("Manifest authority: missing-audit-receipt", StringComparison.Ordinal);',
    ],
    "Chummer.Run.Api/Views/Accounts/Account.cshtml": [
        "Correction notes",
        "Resubmit corrected packet",
        "State what changed so this corrected packet can re-enter governed moderation without losing provenance or lineage.",
        "Request changes",
        "Publish on public shelf",
    ],
    "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml": [
        "Why this publication is live",
        "This page keeps discovery, trust, comparison, lineage, moderation, and the next step together instead of scattering them across separate routes.",
        '<span class="tag">Trust</span>',
        '<span class="tag">Discovery</span>',
        '<span class="tag">Moderation</span>',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'Assert(accountPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Description?.Contains("Manifest authority: approved-shared-publication-manifest;", StringComparison.Ordinal) == true, "account publication detail route should carry approved manifest authority into the registry draft description before moderation begins.");',
        'Assert(accountSource.Contains("Resubmit corrected packet", StringComparison.Ordinal), "account publication detail should expose an explicit correction resubmission action after review requests changes.");',
        'var rejectDossierPublicationResult = await accountController.RejectCreatorPublication(dossierPublicationId, "Dossier packet needs a clearer correction pass before governed moderation can continue.", CancellationToken.None);',
        'Assert(string.Equals(rejectedDossierPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.Rejected, StringComparison.Ordinal), "rejected dossier publications should surface the requested-changes review posture on the account detail route.");',
        'var resubmitDossierPublicationResult = await accountController.SubmitCreatorPublication(dossierPublicationId, "Correction pass refreshed the dossier packet provenance and return summary for governed moderation.", CancellationToken.None);',
        'Assert(string.Equals(resubmittedDossierPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.PendingReview, StringComparison.Ordinal), "resubmitted dossier publications should re-enter the registry moderation queue after a correction pass.");',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m116_hub_creator_publication.py",
        "python3 -m unittest tests/test_next90_m116_hub_creator_publication.py",
    ],
    "tests/test_next90_m116_hub_creator_publication.py": [
        "class Next90M116HubCreatorPublicationTests(unittest.TestCase):",
        'self.assertIn("Resubmit corrected packet", result.stderr)',
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
        "work_task_id": 116.1,
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

    if milestone.get("title") != "Creator publication discovery, lineage, moderation, and trust ranking":
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
    verify_queue_authority(missing, DESIGN_QUEUE_STAGING_PATH)
    verify_successor_registry(missing, SUCCESSOR_REGISTRY_PATH)
    verify_source_markers(missing)

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m116 hub creator publication proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
