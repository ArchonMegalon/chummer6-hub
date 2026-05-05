#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m117-hub-artifact-shelf-v2"
TITLE = "Build artifact shelf APIs and audience filters"
TASK = "Serve personal, campaign, creator, and public artifact shelves with proof, preview, captions, sibling packets, audience, locale, retention, and publication state."
FRONTIER_ID = 4041187890
MILESTONE_ID = 117
WORK_TASK_ID = "117.1"
WORK_TASK_TITLE = "Build artifact shelf APIs and audience filters for personal, campaign, creator, and public views."
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["artifact_shelf:v2", "artifact_audience_filters"]
EXPECTED_STATUS = "in_progress"

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": [
        '[HttpGet("/artifacts")]',
        'var signedInArtifactView = NormalizeSignedInArtifactView(Request.Query["view"].ToString());',
        "signedInRecapShelf = FilterSignedInArtifactShelfEntries(",
        "signedInCreatorPublications = FilterSignedInCreatorPublications(",
        "private static IReadOnlyList<RecapShelfEntry> FilterSignedInArtifactShelfEntries(",
        "private static IReadOnlyList<CreatorPublicationProjection> FilterSignedInCreatorPublications(",
        "private static string NormalizeSignedInArtifactView(string? rawView)",
        '"personal" => "personal",',
        '"campaign" => "campaign",',
        '"creator" => "creator",',
        '"public" => "public",',
        "return AudienceContains(item.Audience, signedInArtifactView);",
    ],
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs": [
        "Audience: creatorLinked",
        "? DescribeRecapShelfAudience(item, creatorLinked)",
        "PublicationState: creatorLinked",
        "? creatorPublication!.PublicationStatus",
        '? "personal,campaign,creator"',
        ': "campaign,creator";',
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        "Audience = creatorLinked",
        "? DescribeRecapShelfAudience(item, creatorLinked)",
        "PublicationState = creatorLinked",
        "? creatorPublication!.PublicationStatus",
        '? "personal,campaign,creator"',
        ': "campaign,creator";',
    ],
    "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs": [
        ".Where(static item => HasApprovedManifestAuthority(item.Draft, item.Detail))",
        "item.Discoverable",
        '&& string.Equals(item.PublicationStatus, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase)',
        "return publication is { Discoverable: true }",
    ],
    "Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs": [
        'throw new InvalidOperationException("Creator publication moderation requires an approved manifest-backed audit receipt before submission, correction, approval, or publication.");',
        '$"Status: {HumanizeValue(publication.PublicationStatus, "Preview ready")}",',
        'lines.Add($"Manifest authority: {BuildManifestAuthority(publication, workspace, linkedShelfEntry)}")',
        'return $"approved-shared-publication-manifest; workspace:{workspaceId}; artifact:{artifactId}; audit:{approvedAuditSummary}";',
    ],
    "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml": [
        'static string ArtifactViewTitle(string view) => view switch',
        '"Personal view"',
        '"Campaign view"',
        '"Creator view"',
        '"Public view"',
        "@PublicSurfaceStatus.AudienceLabel(item.Audience)",
        '@HumanizeStatus(item.PublicationState, "Ready")',
        "CreatorPublicationHref(linkedPublication, item.CreatorPublicationId)",
        "CreatorPublicationLinkLabel(linkedPublication)",
        "rankedPublicCreatorPublications",
        '@HumanizeStatus(publication.PublicationStatus, "Published")',
        "Open public publication",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'Assert(string.Equals(personalArtifactsModel?.SignedInArtifactView, "personal", StringComparison.Ordinal), "authenticated artifacts shelf should honor the explicit personal view filter.");',
        'Assert(personalArtifactsModel?.SignedInRecapShelf?.Count > 0 && personalArtifactsModel.SignedInRecapShelf.All(static item => item.Audience.Contains("personal", StringComparison.OrdinalIgnoreCase)), "personal artifact view should keep only artifacts that are governable on the personal rail.");',
        'Assert(string.Equals(campaignArtifactsModel?.SignedInArtifactView, "campaign", StringComparison.Ordinal), "authenticated artifacts shelf should honor the explicit campaign view filter.");',
        'Assert(campaignArtifactsModel?.SignedInRecapShelf?.Count > 0 && campaignArtifactsModel.SignedInRecapShelf.All(static item => item.Audience.Contains("campaign", StringComparison.OrdinalIgnoreCase)), "campaign artifact view should keep only artifacts that are governable on the campaign rail.");',
        'Assert(string.Equals(creatorArtifactsModel?.SignedInArtifactView, "creator", StringComparison.Ordinal), "authenticated artifacts shelf should honor the explicit creator view filter.");',
        'Assert(creatorArtifactsModel?.SignedInRecapShelf?.All(static item => item.Audience.Contains("creator", StringComparison.OrdinalIgnoreCase) || !string.IsNullOrWhiteSpace(item.CreatorPublicationId)) == true, "creator artifact view should keep only creator-linked artifact lineage on the recap shelf.");',
        'Assert(string.Equals(publicArtifactsModel?.SignedInArtifactView, "public", StringComparison.Ordinal), "authenticated artifacts shelf should honor the explicit public view filter.");',
        'Assert(publicArtifactsModel?.SignedInCreatorPublications?.All(static item => item.Discoverable && string.Equals(item.PublicationStatus, "published", StringComparison.OrdinalIgnoreCase)) == true, "public artifact view should keep only discoverable published creator-publication cards on the signed-in public rail.");',
        'Assert(publicArtifactsModel?.SignedInRecapShelf?.Count == 0, "public artifact view should not blend private recap artifacts into the signed-in public publication rail.");',
        'Assert(string.Equals(fallbackArtifactsModel?.SignedInArtifactView, "all", StringComparison.Ordinal), "unknown artifact view filters should fall back to the all-views shelf instead of breaking the route.");',
        'Assert(artifactsModel.PublicCreatorPublications?.Count > 0, "guest artifacts shelf should surface governed public creator discovery once a creator packet is actually published.");',
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        '"package_id": "next90-m117-hub-artifact-shelf-v2"',
        '"receipt_id": "artifact_shelf:v2"',
        '"receipt_id": "artifact_audience_filters"',
        '"/artifacts/publications/{publicationId}",',
        '"creator_publication_detail",',
        "manifest-authority-backed before the shared shelf surfaces it.",
        '"artifact_view:public"',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m117_hub_artifact_shelf_v2.py",
        "python3 -m unittest tests/test_next90_m117_hub_artifact_shelf_v2.py",
    ],
    "tests/test_next90_m117_hub_artifact_shelf_v2.py": [
        "class Next90M117HubArtifactShelfV2Tests(unittest.TestCase):",
        'self.assertIn("status must be \'in_progress\'", result.stderr)',
        'self.assertIn(\'"Creator view"\', result.stderr)',
        'self.assertIn("return AudienceContains(item.Audience, signedInArtifactView);", result.stderr)',
        'self.assertIn("HasApprovedManifestAuthority(item.Draft, item.Detail)", result.stderr)',
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
        "work_task_id": 117.1,
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

    if milestone.get("title") != "Artifact shelf v2 for personal, campaign, creator, and public views":
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

    print("next90 m117 hub artifact shelf v2 proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
