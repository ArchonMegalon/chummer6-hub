#!/usr/bin/env python3
from __future__ import annotations

import json
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
EXPECTED_STATUS = "complete"
EXPECTED_WAVE = "W13"
LANDED_COMMIT = "TO_BE_FILLED_M117_COMMIT"
COMPLETION_ACTION = "verify_closed_package_only"
DO_NOT_REOPEN_REASON = (
    "M117 chummer6-hub artifact shelf APIs and audience filters are complete; future shards must verify the "
    "artifact-shelf release-proof receipts, canonical registry row, Fleet queue row, and design queue row instead of "
    "reopening the signed-in and public artifact shelf slice."
)
PROOF = [
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml",
    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs",
    "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m117_hub_artifact_shelf_v2.py",
    "/docker/chummercomplete/chummer6-hub/tests/test_next90_m117_hub_artifact_shelf_v2.py",
    "python3 scripts/verify_next90_m117_hub_artifact_shelf_v2.py",
    "python3 -m unittest tests/test_next90_m117_hub_artifact_shelf_v2.py",
    "bash scripts/ai/run_services_smoke.sh",
]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "active-run helper",
    "operator telemetry",
    "supervisor status",
    "task-local telemetry",
    "shard runtime handoff",
]

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
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_SERVED_RELEASE_PROOF",
        str(ROOT / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)

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
    "landed_commit": LANDED_COMMIT,
    "completion_action": COMPLETION_ACTION,
    "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
    "allowed_paths": ALLOWED_PATHS,
    "owned_surfaces": OWNED_SURFACES,
    "exit_criterion": TASK,
    "proof": PROOF,
}
LOCAL_RELEASE_PROOF_RECEIPTS = {
    "artifact_shelf:v2": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/artifacts",
            "/api/v1/public/artifacts/shelf",
            "/artifacts/publications/{publicationId}",
            "/api/v1/public/artifacts/publications/{publicationId}",
            "/home/work",
            "/account/work",
        ],
        "surfaces": [
            "artifact_shelf:v2",
            "artifact_shelf_api",
            "signed_in_return_shelf",
            "public_creator_discovery",
            "creator_publication_detail",
        ],
        "summary_markers": [
            "personal, campaign, creator, and public views",
            "publication state",
            "public publication detail",
        ],
        "evidence_markers": [
            "PublicLandingController.cs serves the governed artifact shelf",
            "PublicCreatorPublicationDiscoveryService.cs keeps public creator discovery published-only and manifest-authority-backed",
            "RunServicesSmoke/Program.cs proves personal, campaign, creator, and public artifact views",
        ],
    },
    "artifact_audience_filters": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/artifacts",
            "/home/work",
            "/account/work",
        ],
        "surfaces": [
            "artifact_audience_filters",
            "artifact_view:all",
            "artifact_view:personal",
            "artifact_view:campaign",
            "artifact_view:creator",
            "artifact_view:public",
        ],
        "summary_markers": [
            "fail closed",
            "personal, campaign, creator, or public",
            "audience and publication posture",
        ],
        "evidence_markers": [
            "PublicLandingController.cs normalizes the signed-in view query",
            "CampaignWorkspaceServerPlaneService.cs and CampaignSpineService.cs stamp creator-linked recap entries",
            "verify_next90_m117_hub_artifact_shelf_v2.py fail-closes queue, registry, and source-proof drift",
        ],
    },
}

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": [
        '[HttpGet("/artifacts")]',
        '[HttpGet("artifacts/shelf")]',
        '[HttpGet("/api/v1/public/artifacts/shelf")]',
        '[HttpGet("/api/public/artifacts/shelf")]',
        'contractName = "chummer.run.public_artifact_shelf.v2"',
        'requestedView = signedInArtifactView,',
        'BuildArtifactShelfViewPayload("all", viewCounts),',
        'BuildArtifactShelfViewPayload("public", viewCounts)',
        'BuildArtifactShelfCreatorPublicationPayload(',
        'BuildArtifactShelfRecapPayload(',
        '[HttpGet("artifacts/publications/{publicationId}")]',
        '[HttpGet("/api/v1/public/artifacts/publications/{publicationId}")]',
        '[HttpGet("/api/public/artifacts/publications/{publicationId}")]',
        'contractName = "chummer.run.public_artifact_shelf.publication.v1"',
        "ResolveArtifactShelfLocale(locale, Request.Headers.AcceptLanguage.ToString())",
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
        'int guestAllCount = FilterGuestArtifactShelfCards(guestCards, "all").Count',
        'int guestCreatorCount = FilterGuestArtifactShelfPublications(publicCreatorPublications, "creator").Count;',
        'int guestPublicCount = FilterGuestArtifactShelfCards(guestCards, "public").Count',
        "return AudienceContains(item.Audience, signedInArtifactView);",
        'audienceLabel = PublicSurfaceStatus.AudienceLabel(string.Join(",", audience)),',
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
        'var guestArtifactShelfApiResult = await controller.ArtifactShelfApi(view: null, locale: "de-at", CancellationToken.None) as OkObjectResult;',
        'guestArtifactShelfApiDocument.RootElement.GetProperty("contractName").GetString(), "chummer.run.public_artifact_shelf.v2"',
        'guestArtifactShelfApiDocument.RootElement.GetProperty("guestShelf").GetProperty("publicCreatorPublications").EnumerateArray().Any(item => item.GetProperty("siblingPackets").GetArrayLength() > 0)',
        'guestArtifactShelfApiDocument.RootElement.GetProperty("guestShelf").GetProperty("publicCreatorPublications").EnumerateArray().All(item => item.TryGetProperty("audienceLabel", out JsonElement audienceLabel) && !string.IsNullOrWhiteSpace(audienceLabel.GetString()))',
        'guestArtifactShelfApiDocument.RootElement.GetProperty("availableViews").EnumerateArray().Select(item => item.GetProperty("view").GetString()).SequenceEqual(new[] { "all", "personal", "campaign", "creator", "public" }, StringComparer.Ordinal)',
        'var authenticatedArtifactShelfApiResult = await authenticatedLandingController.ArtifactShelfApi(view: "creator", locale: null, CancellationToken.None) as OkObjectResult;',
        'authenticatedArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("creatorPublications").EnumerateArray().All(item => item.TryGetProperty("publicationState", out _) && item.TryGetProperty("siblingPackets", out _))',
        'authenticatedArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("creatorPublications").EnumerateArray().All(item => item.TryGetProperty("audienceLabel", out JsonElement audienceLabel) && !string.IsNullOrWhiteSpace(audienceLabel.GetString()))',
        'Assert(authenticatedArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("creatorPublications").EnumerateArray().All(item =>\n            item.TryGetProperty("caption", out JsonElement caption)',
        'Assert(authenticatedCreatorViewCount == authenticatedArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("recapItems").GetArrayLength() + authenticatedArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("creatorPublications").GetArrayLength() + authenticatedArtifactShelfApiDocument.RootElement.GetProperty("guestShelf").GetProperty("publicCreatorPublications").GetArrayLength(), "artifact shelf api creator view count should include signed-in creator lineage and the public creator-discovery rail that still renders while signed in.");',
        'string.Equals(creatorLocale.GetString(), "en-US", StringComparison.Ordinal)',
        'var publicArtifactShelfApiResult = await authenticatedLandingController.ArtifactShelfApi(view: "public", locale: "es_es", CancellationToken.None) as OkObjectResult;',
        'publicArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("creatorPublications").EnumerateArray().All(item =>',
        'item.GetProperty("audience").EnumerateArray().All(token => string.Equals(token.GetString(), "public", StringComparison.OrdinalIgnoreCase))',
        'string.Equals(creatorLocale.GetString(), "es-ES", StringComparison.Ordinal)',
        'Assert(authenticatedPublicViewCount == publicArtifactShelfApiDocument.RootElement.GetProperty("guestShelf").GetProperty("cards").GetArrayLength() + publicArtifactShelfApiDocument.RootElement.GetProperty("guestShelf").GetProperty("publicCreatorPublications").GetArrayLength() + publicArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("creatorPublications").GetArrayLength(), "artifact shelf api public view count should include public proof cards, public creator discovery, and signed-in published creator packets together.");',
        'Assert(authenticatedAllViewCount == publicArtifactShelfApiDocument.RootElement.GetProperty("guestShelf").GetProperty("cards").GetArrayLength() + publicArtifactShelfApiDocument.RootElement.GetProperty("guestShelf").GetProperty("publicCreatorPublications").GetArrayLength() + publicArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("recapItems").GetArrayLength() + publicArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("creatorPublications").GetArrayLength(), "artifact shelf api all-view count should include both the signed-in shelf overlays and the public guest shelf material that still renders while signed in.");',
        'var fallbackArtifactShelfApiResult = await authenticatedLandingController.ArtifactShelfApi(view: "shadow", locale: null, CancellationToken.None) as OkObjectResult;',
        'Assert(string.Equals(fallbackArtifactShelfApiDocument.RootElement.GetProperty("requestedView").GetString(), "all", StringComparison.Ordinal), "artifact shelf api should fail closed to the all view when callers request an unknown shelf filter.");',
        'var publicCreatorDetailApiResult = await controller.CreatorPublicationDetailApi(publicationId, locale: "fr-fr", CancellationToken.None) as OkObjectResult;',
        'publicCreatorDetailApiDocument.RootElement.GetProperty("contractName").GetString(), "chummer.run.public_artifact_shelf.publication.v1"',
        'publicCreatorDetailApiDocument.RootElement.GetProperty("locale").GetString(), "fr-FR"',
        'publicCreatorDetailApiDocument.RootElement.GetProperty("retention").GetProperty("domains").EnumerateArray().Any(item => string.Equals(item.GetProperty("id").GetString(), "survey_follow_up", StringComparison.Ordinal))',
        'publicCreatorDetailApiDocument.RootElement.GetProperty("publication").GetProperty("audience").EnumerateArray().Any(item => string.Equals(item.GetString(), "public", StringComparison.OrdinalIgnoreCase))',
        '!string.IsNullOrWhiteSpace(publicCreatorDetailApiDocument.RootElement.GetProperty("publication").GetProperty("audienceLabel").GetString())',
        '!string.IsNullOrWhiteSpace(publicCreatorDetailApiDocument.RootElement.GetProperty("publication").GetProperty("caption").GetString())',
        'publicCreatorDetailApiDocument.RootElement.GetProperty("publication").GetProperty("proof").GetArrayLength() > 0',
        'publicCreatorDetailApiDocument.RootElement.GetProperty("publication").GetProperty("siblingPackets").GetArrayLength() > 0',
        'publicCreatorDetailApiDocument.RootElement.GetProperty("publication").GetProperty("publicationState").GetString(), "published"',
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
        '"/api/v1/public/artifacts/shelf",',
        '"/api/v1/public/artifacts/publications/{publicationId}",',
        '"artifact_shelf_api",',
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
        'self.assertIn("status must be \'complete\'", result.stderr)',
        'self.assertIn("milestone 117 status must be \'complete\'", result.stderr)',
        'self.assertIn("work task 117.1 title drifted", result.stderr)',
        'self.assertIn(\'"Creator view"\', result.stderr)',
        'self.assertIn("return AudienceContains(item.Audience, signedInArtifactView);", result.stderr)',
        'self.assertIn(\'Assert(authenticatedArtifactShelfApiDocument.RootElement.GetProperty("signedInShelf").GetProperty("creatorPublications").EnumerateArray().All(item =>',
        'self.assertIn(\'string.Equals(creatorLocale.GetString(), "es-ES", StringComparison.Ordinal)\', result.stderr)',
        'self.assertIn("repo-local and served release proof package rows for next90-m117-hub-artifact-shelf-v2 must match exactly", result.stderr)',
        'self.assertIn("HasApprovedManifestAuthority(item.Draft, item.Detail)", result.stderr)',
    ],
}


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        normalized = normalize_staged_queue_yaml(text)
        if normalized != text:
            return yaml.safe_load(normalized)
        raise


def normalize_staged_queue_yaml(text: str) -> str:
    mode_index = text.find("\nmode:")
    items_index = text.find("\nitems:")
    if mode_index > 0 and items_index > mode_index:
        return text[mode_index + 1 :]

    return text


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

    payload = load_yaml(path) or {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        missing.append(f"{path}: items is missing")
        return None

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return None

    item = matches[0]
    expected_fields = {
        "title": TITLE,
        "task": TASK,
        "repo": "chummer6-hub",
        "milestone_id": MILESTONE_ID,
        "work_task_id": 117.1,
        "status": EXPECTED_STATUS,
        "wave": EXPECTED_WAVE,
        "landed_commit": LANDED_COMMIT,
        "completion_action": COMPLETION_ACTION,
        "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
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
    if item.get("proof") != PROOF:
        missing.append(f"{path}: proof must be {PROOF!r}")
    reject_forbidden_markers(json.dumps(item, sort_keys=True), str(path), missing)
    return item


def verify_queue_parity(
    missing: list[str],
    queue_row: dict[str, object] | None,
    design_queue_row: dict[str, object] | None,
) -> None:
    if queue_row is None or design_queue_row is None:
        return
    if queue_row != design_queue_row:
        missing.append("fleet and design queue rows for next90-m117-hub-artifact-shelf-v2 must match exactly")


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
    if milestone.get("status") != EXPECTED_STATUS:
        missing.append(f"{path}: milestone {MILESTONE_ID} status must be {EXPECTED_STATUS!r}")

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
            missing.append("repo-local and served release proof package rows for next90-m117-hub-artifact-shelf-v2 must match exactly")

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
            missing.append(f"repo-local and served release proof receipt {receipt_id!r} for next90-m117-hub-artifact-shelf-v2 must match exactly")


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

    print("next90 m117 hub artifact shelf v2 proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
