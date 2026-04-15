#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_ARTIFACT_FACTORY_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_ARTIFACT_FACTORY_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_ARTIFACT_FACTORY_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_ARTIFACT_FACTORY_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
    "scripts/verify_artifact_factory_orchestration.py": [
        "CHUMMER_ARTIFACT_FACTORY_DESIGN_QUEUE_STAGING",
        "DESIGN_QUEUE_STAGING_PATH",
        '"frontier_id": 1421219975',
        "verify_queue_authority(missing, queue_path)",
        "queue staging must contain exactly one package_id",
        "successor registry must contain exactly one milestone",
        "successor registry must contain exactly one work task",
        "FORBIDDEN_PROOF_MARKERS",
        "reject_forbidden_proof_markers(",
        "item_lower = item.lower()",
        "marker.lower() in item_lower",
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_artifact_factory_orchestration.py",
        "python3 -m unittest tests/test_artifact_factory_orchestration.py",
    ],
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs": [
        'private const string ContractName = "chummer.run.artifact_factory.recipe_job.v1";',
        '["release"] = new(',
        'RecipeId: "release-proof-shelf-bundle"',
        '["fix"] = new(',
        'RecipeId: "fix-followthrough-bundle"',
        '["support"] = new(',
        'RecipeId: "support-case-proof-packet"',
        '["publication"] = new(',
        'RecipeId: "publication-proof-shelf-bundle"',
        'RequiredReceiptPrefixes: ["release", "promotion", "public-shelf"]',
        'RequiredReceiptPrefixes: ["fix", "install", "support"]',
        'RequiredReceiptPrefixes: ["support", "privacy", "install"]',
        'RequiredReceiptPrefixes: ["publication", "moderation", "public-shelf"]',
        'RejectProviderSpecificRef(sourcePack.SourcePackId, evidenceRef, "evidenceRef");',
        'RejectNonLocalPublicShelfRef(sourcePack.SourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");',
        'RejectPublicShelfRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, sourcePack.PublicShelfRef, "publicShelfRef");',
        'RejectNonLocalPublicShelfEvidenceRef(sourcePack.SourcePackId, evidenceRef);',
        'RejectPublicShelfEvidenceRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, evidenceRef);',
        "string normalizedSourcePackId = sourcePack.SourcePackId.Trim();",
        "if (!sourcePackIds.Add(normalizedSourcePackId))",
        'throw new InvalidDataException($"duplicate source pack id \'{normalizedSourcePackId}\' is not allowed.");',
        "SourcePackId: normalizedSourcePackId,",
        "private static int FirstRefPrefixSeparatorIndex(string normalized)",
        "int slashIndex = normalized.IndexOf('/');",
        "private static void RejectPublicShelfRefOutsideRecipeRoutes(string sourcePackId, string family, string value, string fieldName)",
        "private static void RejectUnsafePublicShelfRef(string sourcePackId, string publicShelfRef, string fieldName)",
        "artifact factory bundle refs must be stable shelf paths without query strings or fragments.",
        "artifact factory bundle refs must not contain traversal or encoded path separators.",
        '"/downloads/install/", "/artifacts/release-bundles/"',
        '"/account/support/", "/account/support-packets/"',
        '"/artifacts/publications/"',
        "outside recipe {family} shelf routes",
        "artifact factory output refs must stay on the Chummer public proof shelf.",
        'artifact factory jobs must launch from approved source-pack receipts instead of one-off provider flows.',
        "private static ArtifactFactoryMediaSourcePack SelectOutputAnchor(",
        '"release" => !string.IsNullOrWhiteSpace(pack.ReleaseArtifactId)',
        '|| !string.IsNullOrWhiteSpace(pack.PublicShelfRef),',
        'return $"/artifacts/release-bundles/{Uri.EscapeDataString(anchor.ReleaseArtifactId)}";',
        'return $"/account/{supportPath}/{Uri.EscapeDataString(anchor.SupportCaseId)}";',
        'return $"/artifacts/publications/{Uri.EscapeDataString(anchor.PublicationId)}/bundles";',
        "publicProofShelfRefs.AddRange(BuildOutputShelfRefs(outputBindings));",
        "private static IEnumerable<string> BuildOutputShelfRefs(IReadOnlyList<ArtifactFactoryOutputBinding> outputBindings)",
        "yield return binding.PublicRef[..separatorIndex];",
        'string shelfRef = anchor.PublicShelfRef.Trim().TrimEnd(\'/\');',
        '&& TryBuildReleaseBundleRefFromDownloadShelfRef(shelfRef, out string? releaseBundleRef)',
        "private static bool TryBuildReleaseBundleRefFromDownloadShelfRef(string shelfRef, out string releaseBundleRef)",
        'const string downloadInstallPrefix = "/downloads/install/";',
        'return shelfRef.EndsWith("/bundles", StringComparison.OrdinalIgnoreCase)',
    ],
    "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs": [
        '[HttpPost("/api/internal/artifact-factory/jobs")]',
        "RequireInternalAutomationAuth();",
        '"FLEET_INTERNAL_API_TOKEN"',
        "CryptographicOperations.FixedTimeEquals",
        'https://chummer.run/problems/artifact-factory/rejected',
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "public static IServiceCollection AddHubInstallAndOrchestrationAdapters(this IServiceCollection services)",
        "services.AddSingleton<ArtifactFactoryOrchestrationService>();",
    ],
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs": [
        "LaunchJobBuildsReleaseRecipeFromApprovedSourcePacks",
        "LaunchJobBuildsPublicationProofShelfRoute",
        "LaunchJobBindsOutputsToApprovedAnchoredPackWhenSourcePacksAreMixed",
        "LaunchJobBuildsSupportAndFixJobsFromAnchoredApprovedPacks",
        "LaunchJobRejectsDuplicateSourcePackIds",
        "LaunchJobRejectsWhitespacePaddedDuplicateSourcePackIds",
        "LaunchJobBindsReleaseOutputsToApprovedPublicShelfRefWhenArtifactIdIsAbsent",
        "LaunchJobBindsReleaseDownloadShelfAnchorToReleaseBundleShelf",
        "LaunchJobBindsPublicationOutputsToApprovedPublicShelfRefWhenPublicationIdIsAbsent",
        "ControllerLaunchJobRequiresInternalToken",
        "LaunchJobRejectsProviderSpecificEvidenceRefs",
        "LaunchJobRejectsProviderSpecificSlashEvidenceRefs",
        "LaunchJobRejectsExternalPublicShelfRefs",
        "LaunchJobRejectsExternalPublicShelfEvidenceRefs",
        "LaunchJobRejectsCrossRecipePublicShelfRefs",
        "LaunchJobRejectsCrossRecipePublicShelfEvidenceRefs",
        "LaunchJobRejectsUnsafePublicShelfRefs",
        "LaunchJobRejectsUnsafePublicShelfEvidenceRefs",
        "LaunchJobRejectsRecipeWhenApprovedPackLacksRequiredReceiptEvidence",
        'Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", result.MediaFactoryRequest.ContractName);',
        'string.Equals(binding.PublicRef, "/artifacts/release-bundles/avalonia-osx-arm64-installer/preview_card", StringComparison.Ordinal)',
        'Assert.Contains("/account/support/11709", support.PublicProofShelfRefs);',
        'Assert.Contains("/account/support/11709", fix.MediaFactoryRequest.PublicProofShelfRefs);',
        'Assert.Contains("/artifacts/release-bundles/avalonia-osx-arm64-installer", result.MediaFactoryRequest.PublicProofShelfRefs);',
        'Assert.Contains("/artifacts/release-bundles/avalonia-linux-x64-installer", result.MediaFactoryRequest.PublicProofShelfRefs);',
    ],
    "tests/test_artifact_factory_orchestration.py": [
        "test_verifier_fails_closed_when_queue_package_is_duplicated",
        "test_verifier_fails_closed_when_structured_frontier_id_is_missing",
        "test_verifier_fails_closed_when_duplicate_source_pack_guard_is_removed",
        "test_verifier_fails_closed_when_normalized_duplicate_source_pack_guard_is_removed",
        "test_verifier_fails_closed_when_queue_guard_commit_pin_is_missing",
        "test_verifier_fails_closed_when_current_duplicate_queue_guard_proof_is_missing",
        "commit cfd5d208",
        "commit 60125d9e",
        "commit c98a49f2",
        "commit 28d3e13f",
        "commit 76b0c410",
        "commit e5e2e57f",
        "commit f0bdfcb9",
        "commit 66b1a1c7",
        "commit 51623cd3",
        "commit 2b8a9431",
        "commit a20aa910",
        "commit 7ce86602",
        "commit 326db197",
        "commit bd67b5ff",
        "commit 6851982b",
        "commit 5b901df5",
        "commit cbae3cdd",
        "commit f0142482",
        "commit a66a06bb",
        "commit 9a8e56f0",
        "commit a929cc7d",
        "commit ff3100b4",
        "commit 94f0c9e1",
        "commit f22ce5a5",
        "test_verifier_fails_closed_when_proof_commit_anchor_is_not_on_current_branch",
        "test_verifier_fails_closed_when_branch_guard_commit_pin_is_missing",
        "test_verifier_fails_closed_when_output_shelf_pin_commit_is_missing",
        "test_verifier_fails_closed_when_current_output_shelf_proof_pin_is_missing",
        "test_verifier_fails_closed_when_current_artifact_shelf_proof_floor_is_missing",
        "test_verifier_fails_closed_when_current_duplicate_queue_proof_guard_is_missing",
        "test_verifier_fails_closed_when_current_m107_guard_floor_is_missing",
    ],
}

QUEUE_MARKERS = [
    "package_id: next90-m107-hub-artifact-factory",
    "milestone_id: 107",
    "status: complete",
    "landed_commit: b9e6b52e",
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
    "dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
    "artifact_factory:orchestration",
    "public_proof_shelf:release_bundles",
    "/docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards",
    "/docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution",
    "/docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof",
    "/docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence",
    "/docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard",
    "/docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof",
    "/docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard",
    "/docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs",
    "/docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard",
    "/docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard",
    "/docker/chummercomplete/chummer.run-services commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard",
    "/docker/chummercomplete/chummer.run-services commit 51623cd3 pins M107 artifact factory duplicate queue guard proof",
    "/docker/chummercomplete/chummer.run-services commit 2b8a9431 tightens the current M107 duplicate queue proof guard",
    "/docker/chummercomplete/chummer.run-services commit a20aa910 tightens M107 artifact factory public shelf ref safety",
    "/docker/chummercomplete/chummer.run-services commit 7ce86602 pins M107 artifact factory shelf safety proof",
    "/docker/chummercomplete/chummer.run-services commit 326db197 tightens M107 artifact factory source-pack proof",
    "/docker/chummercomplete/chummer.run-services commit bd67b5ff tightens M107 artifact factory structured frontier proof",
    "/docker/chummercomplete/chummer.run-services commit 6851982b tightens M107 artifact factory proof hygiene",
    "/docker/chummercomplete/chummer.run-services commit 5b901df5 tightens M107 artifact factory proof branch guard",
    "/docker/chummercomplete/chummer.run-services commit cbae3cdd tightens M107 artifact factory output shelf proof",
    "/docker/chummercomplete/chummer.run-services commit f0142482 pins M107 artifact factory output shelf proof",
    "/docker/chummercomplete/chummer.run-services commit a66a06bb tightens M107 artifact output shelf proof pin",
    "/docker/chummercomplete/chummer.run-services commit 9a8e56f0 tightens M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer.run-services commit a929cc7d pins M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer.run-services commit ff3100b4 requires the current M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer.run-services commit 94f0c9e1 pins M107 current duplicate queue guard",
    "/docker/chummercomplete/chummer.run-services commit f22ce5a5 tightens M107 artifact factory source-pack id normalization",
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention",
]

SUCCESSOR_REGISTRY_MARKERS = [
    "program_wave: next_90_day_product_advance",
    "  - id: 107",
    "title: Artifact factory and public proof shelf",
    "      - id: 107.1",
    "owner: chummer6-hub",
    "title: Orchestrate recipe-backed artifact jobs from approved release, support, and publication packs.",
    "status: complete",
    "/docker/chummercomplete/chummer.run-services commit e25842ac tightens mixed source-pack output anchoring",
    "/docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards",
    "/docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution",
    "/docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring",
    "/docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence",
    "/docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard",
    "/docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof",
    "/docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard",
    "/docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs",
    "/docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard",
    "/docker/chummercomplete/chummer.run-services commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard",
    "/docker/chummercomplete/chummer.run-services commit 51623cd3 pins M107 artifact factory duplicate queue guard proof",
    "/docker/chummercomplete/chummer.run-services commit 2b8a9431 tightens the current M107 duplicate queue proof guard",
    "/docker/chummercomplete/chummer.run-services commit a20aa910 tightens M107 artifact factory public shelf ref safety",
    "/docker/chummercomplete/chummer.run-services commit 7ce86602 pins M107 artifact factory shelf safety proof",
    "/docker/chummercomplete/chummer.run-services commit 326db197 tightens M107 artifact factory source-pack proof",
    "/docker/chummercomplete/chummer.run-services commit bd67b5ff tightens M107 artifact factory structured frontier proof",
    "/docker/chummercomplete/chummer.run-services commit 5b901df5 tightens M107 artifact factory proof branch guard",
    "/docker/chummercomplete/chummer.run-services commit cbae3cdd tightens M107 artifact factory output shelf proof",
    "/docker/chummercomplete/chummer.run-services commit f0142482 pins M107 artifact factory output shelf proof",
    "/docker/chummercomplete/chummer.run-services commit a66a06bb tightens M107 artifact output shelf proof pin",
    "/docker/chummercomplete/chummer.run-services commit 9a8e56f0 tightens M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer.run-services commit a929cc7d pins M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer.run-services commit ff3100b4 requires the current M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer.run-services commit 94f0c9e1 pins M107 current duplicate queue guard",
    "/docker/chummercomplete/chummer.run-services commit f22ce5a5 tightens M107 artifact factory source-pack id normalization",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs rejects unapproved or provider-specific source packs",
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention",
    "python3 /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py exits 0.",
    "python3 -m unittest /docker/chummercomplete/chummer.run-services/tests/test_artifact_factory_orchestration.py exits 0.",
    "dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore exits 0.",
]

PACKAGE_ID = "next90-m107-hub-artifact-factory"
MILESTONE_ID = 107
WORK_TASK_ID = 107.1
REQUIRED_QUEUE_FIELDS = {
    "title": "Stand up artifact-factory orchestration for release, support, and publication bundles",
    "task": "Launch recipe-backed release, fix, support, and publication artifact jobs from approved source packs instead of one-off provider flows.",
    "repo": "chummer6-hub",
    "status": "complete",
    "landed_commit": "b9e6b52e",
    "frontier_id": 1421219975,
}
REQUIRED_ALLOWED_PATHS = {"Chummer.Run.Api", "scripts", "tests"}
REQUIRED_OWNED_SURFACES = {"artifact_factory:orchestration", "public_proof_shelf:release_bundles"}
REQUIRED_QUEUE_PROOF = {
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py",
    "python3 /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py",
    "python3 -m unittest /docker/chummercomplete/chummer.run-services/tests/test_artifact_factory_orchestration.py",
    "dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
    "/docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
    "/docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
    "/docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
    "/docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
    "/docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
    "/docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
    "/docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
    "/docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
    "/docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
    "/docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
    "/docker/chummercomplete/chummer.run-services commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
    "/docker/chummercomplete/chummer.run-services commit 51623cd3 pins M107 artifact factory duplicate queue guard proof.",
    "/docker/chummercomplete/chummer.run-services commit 2b8a9431 tightens the current M107 duplicate queue proof guard.",
    "/docker/chummercomplete/chummer.run-services commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
    "/docker/chummercomplete/chummer.run-services commit 7ce86602 pins M107 artifact factory shelf safety proof.",
    "/docker/chummercomplete/chummer.run-services commit 326db197 tightens M107 artifact factory source-pack proof.",
    "/docker/chummercomplete/chummer.run-services commit bd67b5ff tightens M107 artifact factory structured frontier proof.",
    "/docker/chummercomplete/chummer.run-services commit 6851982b tightens M107 artifact factory proof hygiene.",
    "/docker/chummercomplete/chummer.run-services commit 5b901df5 tightens M107 artifact factory proof branch guard.",
    "/docker/chummercomplete/chummer.run-services commit cbae3cdd tightens M107 artifact factory output shelf proof.",
    "/docker/chummercomplete/chummer.run-services commit f0142482 pins M107 artifact factory output shelf proof.",
    "/docker/chummercomplete/chummer.run-services commit a66a06bb tightens M107 artifact output shelf proof pin.",
    "/docker/chummercomplete/chummer.run-services commit 9a8e56f0 tightens M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer.run-services commit a929cc7d pins M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer.run-services commit ff3100b4 requires the current M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 94f0c9e1 pins M107 current duplicate queue guard.",
    "/docker/chummercomplete/chummer.run-services commit f22ce5a5 tightens M107 artifact factory source-pack id normalization.",
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
}
REQUIRED_REGISTRY_EVIDENCE = {
    "/docker/chummercomplete/chummer.run-services commit cda8849a binds release, fix, support, and publication recipe jobs to stable public proof shelf output refs.",
    "/docker/chummercomplete/chummer.run-services commit e25842ac tightens mixed source-pack output anchoring so release bundle refs always bind to an approved artifact-bearing source pack.",
    "/docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards so approved local refs cannot cross from release or publication recipes onto the wrong shelf family.",
    "/docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution so stale file or commit anchors cannot keep the completed package green.",
    "/docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
    "/docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
    "/docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
    "/docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
    "/docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
    "/docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
    "/docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
    "/docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
    "/docker/chummercomplete/chummer.run-services commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
    "/docker/chummercomplete/chummer.run-services commit 51623cd3 pins M107 artifact factory duplicate queue guard proof.",
    "/docker/chummercomplete/chummer.run-services commit 2b8a9431 tightens the current M107 duplicate queue proof guard.",
    "/docker/chummercomplete/chummer.run-services commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
    "/docker/chummercomplete/chummer.run-services commit 7ce86602 pins M107 artifact factory shelf safety proof.",
    "/docker/chummercomplete/chummer.run-services commit 326db197 tightens M107 artifact factory source-pack proof.",
    "/docker/chummercomplete/chummer.run-services commit bd67b5ff tightens M107 artifact factory structured frontier proof.",
    "/docker/chummercomplete/chummer.run-services commit 6851982b tightens M107 artifact factory proof hygiene.",
    "/docker/chummercomplete/chummer.run-services commit 5b901df5 tightens M107 artifact factory proof branch guard.",
    "/docker/chummercomplete/chummer.run-services commit cbae3cdd tightens M107 artifact factory output shelf proof.",
    "/docker/chummercomplete/chummer.run-services commit f0142482 pins M107 artifact factory output shelf proof.",
    "/docker/chummercomplete/chummer.run-services commit a66a06bb tightens M107 artifact output shelf proof pin.",
    "/docker/chummercomplete/chummer.run-services commit 9a8e56f0 tightens M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer.run-services commit a929cc7d pins M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer.run-services commit ff3100b4 requires the current M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 94f0c9e1 pins M107 current duplicate queue guard.",
    "/docker/chummercomplete/chummer.run-services commit f22ce5a5 tightens M107 artifact factory source-pack id normalization.",
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs rejects unapproved or provider-specific source packs and emits media-factory output bindings for preview, caption, packet, audio, and video formats.",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs and Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs bind the recipe-backed job launcher to the internal authenticated Hub orchestration endpoint.",
    "/docker/chummercomplete/chummer.run-services/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs proves release, support, fix, and publication bundles route through approved source-pack receipts.",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py fail-closes missing recipe families, internal endpoint auth, public proof shelf bundle refs, and anchored source-pack output selection.",
    "python3 /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py exits 0.",
    "python3 -m unittest /docker/chummercomplete/chummer.run-services/tests/test_artifact_factory_orchestration.py exits 0.",
    "dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore exits 0.",
}
REPO_ABSOLUTE_PREFIX = "/docker/chummercomplete/chummer.run-services/"
FORBIDDEN_PROOF_MARKERS = [
    "/var/lib/codex-fleet",
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "active-run helper",
    "operator telemetry",
    "run_ooda_design_supervisor_until_quiet",
    "ooda_design_supervisor.py",
]


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8")


def load_yaml(path: Path) -> object:
    return yaml.safe_load(read_text(path))


def find_queue_item(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("queue staging root must be a mapping.")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("queue staging is missing an items list.")

    matches = [
        item
        for item in items
        if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID
    ]
    if not matches:
        raise ValueError(f"queue staging is missing package_id {PACKAGE_ID}.")
    if len(matches) > 1:
        raise ValueError(
            f"queue staging must contain exactly one package_id {PACKAGE_ID}; found {len(matches)}."
        )
    return matches[0]


def find_successor_task(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("successor registry root must be a mapping.")
    milestones = data.get("milestones")
    if not isinstance(milestones, list):
        raise ValueError("successor registry is missing a milestones list.")

    matching_milestones = [
        item
        for item in milestones
        if isinstance(item, dict) and item.get("id") == MILESTONE_ID
    ]
    if not matching_milestones:
        raise ValueError(f"successor registry is missing milestone {MILESTONE_ID}.")
    if len(matching_milestones) > 1:
        raise ValueError(
            f"successor registry must contain exactly one milestone {MILESTONE_ID}; found {len(matching_milestones)}."
        )
    milestone = matching_milestones[0]

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        raise ValueError(f"milestone {MILESTONE_ID} is missing work_tasks.")

    matching_tasks = [
        item
        for item in work_tasks
        if isinstance(item, dict) and float(item.get("id", -1)) == WORK_TASK_ID
    ]
    if not matching_tasks:
        raise ValueError(f"milestone {MILESTONE_ID} is missing work task {WORK_TASK_ID}.")
    if len(matching_tasks) > 1:
        raise ValueError(
            f"successor registry must contain exactly one work task {WORK_TASK_ID} under milestone {MILESTONE_ID}; found {len(matching_tasks)}."
        )
    return matching_tasks[0]


def require_exact_set(missing: list[str], label: str, actual: object, expected: set[str]) -> None:
    if not isinstance(actual, list):
        missing.append(f"{label}: expected list")
        return
    actual_set = {str(item) for item in actual}
    for item in sorted(expected - actual_set):
        missing.append(f"{label}: missing {item}")
    for item in sorted(actual_set - expected):
        missing.append(f"{label}: unexpected {item}")


def require_contains_set(missing: list[str], label: str, actual: object, expected: set[str]) -> None:
    if not isinstance(actual, list):
        missing.append(f"{label}: expected list")
        return
    actual_set = {str(item) for item in actual}
    for item in sorted(expected - actual_set):
        missing.append(f"{label}: missing {item}")


def repo_relative_anchor_path(proof_item: str) -> Path | None:
    candidate = proof_item.strip().split(maxsplit=1)[0].rstrip(".,")
    if not candidate.startswith(REPO_ABSOLUTE_PREFIX):
        return None
    return ROOT / candidate.removeprefix(REPO_ABSOLUTE_PREFIX)


def commit_anchor(proof_item: str) -> str | None:
    prefix = f"{REPO_ABSOLUTE_PREFIX.rstrip('/')} commit "
    if not proof_item.startswith(prefix):
        return None
    remainder = proof_item.removeprefix(prefix).strip()
    if not remainder:
        return None
    return remainder.split(maxsplit=1)[0].rstrip(".,")


def verify_proof_anchors_resolve(missing: list[str], label: str, proof_items: object) -> None:
    if not isinstance(proof_items, list):
        missing.append(f"{label}: expected list")
        return

    for raw_item in proof_items:
        item = str(raw_item)
        anchor_path = repo_relative_anchor_path(item)
        if anchor_path is not None and not anchor_path.is_file():
            missing.append(f"{label}: proof anchor does not resolve: {item}")

        commit = commit_anchor(item)
        if commit is None or not (ROOT / ".git").exists():
            continue
        result = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            missing.append(f"{label}: commit proof anchor does not resolve: {item}")
            continue

        result = subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            missing.append(f"{label}: commit proof anchor is not on the current branch: {item}")


def reject_forbidden_proof_markers(missing: list[str], label: str, proof_items: object) -> None:
    if not isinstance(proof_items, list):
        return

    for raw_item in proof_items:
        item = str(raw_item)
        item_lower = item.lower()
        for marker in FORBIDDEN_PROOF_MARKERS:
            if marker.lower() in item_lower:
                missing.append(f"{label}: forbidden active-run proof marker: {marker}")


def verify_queue_authority(missing: list[str], path: Path) -> None:
    try:
        item = find_queue_item(load_yaml(path))
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: {exc}")
        return

    if item.get("milestone_id") != MILESTONE_ID:
        missing.append(f"{path}: {PACKAGE_ID} milestone_id must be {MILESTONE_ID}")
    for field, expected in REQUIRED_QUEUE_FIELDS.items():
        if item.get(field) != expected:
            missing.append(f"{path}: {PACKAGE_ID} {field} must be {expected!r}")
    require_exact_set(missing, f"{path}: {PACKAGE_ID} allowed_paths", item.get("allowed_paths"), REQUIRED_ALLOWED_PATHS)
    require_exact_set(missing, f"{path}: {PACKAGE_ID} owned_surfaces", item.get("owned_surfaces"), REQUIRED_OWNED_SURFACES)
    require_contains_set(missing, f"{path}: {PACKAGE_ID} proof", item.get("proof"), REQUIRED_QUEUE_PROOF)
    reject_forbidden_proof_markers(missing, f"{path}: {PACKAGE_ID} proof", item.get("proof"))
    verify_proof_anchors_resolve(missing, f"{path}: {PACKAGE_ID} proof", item.get("proof"))


def verify_successor_registry_authority(missing: list[str], path: Path) -> None:
    try:
        task = find_successor_task(load_yaml(path))
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: {exc}")
        return

    if task.get("owner") != "chummer6-hub":
        missing.append(f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} owner must be chummer6-hub")
    if task.get("status") != "complete":
        missing.append(f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} status must be complete")
    if task.get("title") != "Orchestrate recipe-backed artifact jobs from approved release, support, and publication packs.":
        missing.append(f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} title drifted")
    require_contains_set(
        missing,
        f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} evidence",
        task.get("evidence"),
        REQUIRED_REGISTRY_EVIDENCE,
    )
    reject_forbidden_proof_markers(
        missing,
        f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} evidence",
        task.get("evidence"),
    )
    verify_proof_anchors_resolve(
        missing,
        f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} evidence",
        task.get("evidence"),
    )


def main() -> int:
    missing: list[str] = []

    for relative_path, markers in SOURCE_MARKERS.items():
        try:
            text = read_text(ROOT / relative_path)
        except FileNotFoundError as exc:
            missing.append(str(exc))
            continue

        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: {marker}")

    queue_paths: list[Path] = []
    for queue_path in (QUEUE_STAGING_PATH, DESIGN_QUEUE_STAGING_PATH):
        if queue_path not in queue_paths:
            queue_paths.append(queue_path)

    for queue_path in queue_paths:
        try:
            queue_text = read_text(queue_path)
        except FileNotFoundError as exc:
            missing.append(str(exc))
        else:
            for marker in QUEUE_MARKERS:
                if marker not in queue_text:
                    missing.append(f"{queue_path}: {marker}")
            verify_queue_authority(missing, queue_path)

    try:
        registry_text = read_text(SUCCESSOR_REGISTRY_PATH)
    except FileNotFoundError as exc:
        missing.append(str(exc))
    else:
        for marker in SUCCESSOR_REGISTRY_MARKERS:
            if marker not in registry_text:
                missing.append(f"{SUCCESSOR_REGISTRY_PATH}: {marker}")
        verify_successor_registry_authority(missing, SUCCESSOR_REGISTRY_PATH)

    if missing:
        for item in missing:
            print(f"artifact_factory_orchestration_missing: {item}", file=sys.stderr)
        return 1

    print("artifact factory orchestration proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
