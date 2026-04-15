#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_ARTIFACT_FACTORY_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_ARTIFACT_FACTORY_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
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
        'artifact factory jobs must launch from approved source-pack receipts instead of one-off provider flows.',
        "private static ArtifactFactoryMediaSourcePack SelectOutputAnchor(",
        '"release" => !string.IsNullOrWhiteSpace(pack.ReleaseArtifactId),',
        'return $"/artifacts/release-bundles/{Uri.EscapeDataString(anchor.ReleaseArtifactId)}";',
        'return $"/account/{supportPath}/{Uri.EscapeDataString(anchor.SupportCaseId)}";',
        'return $"/artifacts/publications/{Uri.EscapeDataString(anchor.PublicationId)}/bundles";',
    ],
    "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs": [
        '[HttpPost("/api/internal/artifact-factory/jobs")]',
        "RequireInternalAutomationAuth();",
        '"FLEET_INTERNAL_API_TOKEN"',
        "CryptographicOperations.FixedTimeEquals",
        'https://chummer.run/problems/artifact-factory/rejected',
    ],
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs": [
        "LaunchJobBuildsReleaseRecipeFromApprovedSourcePacks",
        "LaunchJobBuildsPublicationProofShelfRoute",
        "LaunchJobBindsOutputsToApprovedAnchoredPackWhenSourcePacksAreMixed",
        "LaunchJobBuildsSupportAndFixJobsFromAnchoredApprovedPacks",
        "ControllerLaunchJobRequiresInternalToken",
        "LaunchJobRejectsProviderSpecificEvidenceRefs",
        "LaunchJobRejectsRecipeWhenApprovedPackLacksRequiredReceiptEvidence",
        'Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", result.MediaFactoryRequest.ContractName);',
        'string.Equals(binding.PublicRef, "/artifacts/release-bundles/avalonia-osx-arm64-installer/preview_card", StringComparison.Ordinal)',
        'Assert.Contains("/account/support/11709", support.PublicProofShelfRefs);',
        'Assert.Contains("/account/support/11709", fix.MediaFactoryRequest.PublicProofShelfRefs);',
    ],
}

QUEUE_MARKERS = [
    "package_id: next90-m107-hub-artifact-factory",
    "milestone_id: 107",
    "status: complete",
    "landed_commit: cda8849a",
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
    "dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
    "artifact_factory:orchestration",
    "public_proof_shelf:release_bundles",
]


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8")


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

    try:
        queue_text = read_text(QUEUE_STAGING_PATH)
    except FileNotFoundError as exc:
        missing.append(str(exc))
    else:
        for marker in QUEUE_MARKERS:
            if marker not in queue_text:
                missing.append(f"{QUEUE_STAGING_PATH}: {marker}")

    if missing:
        for item in missing:
            print(f"artifact_factory_orchestration_missing: {item}", file=sys.stderr)
        return 1

    print("artifact factory orchestration proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
