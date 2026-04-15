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
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_ARTIFACT_FACTORY_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
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
        'RejectNonLocalPublicShelfRef(sourcePack.SourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");',
        'RejectPublicShelfRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, sourcePack.PublicShelfRef, "publicShelfRef");',
        'RejectNonLocalPublicShelfEvidenceRef(sourcePack.SourcePackId, evidenceRef);',
        'RejectPublicShelfEvidenceRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, evidenceRef);',
        "private static int FirstRefPrefixSeparatorIndex(string normalized)",
        "int slashIndex = normalized.IndexOf('/');",
        "private static void RejectPublicShelfRefOutsideRecipeRoutes(string sourcePackId, string family, string value, string fieldName)",
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
        'string shelfRef = anchor.PublicShelfRef.Trim().TrimEnd(\'/\');',
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
        "LaunchJobBindsReleaseOutputsToApprovedPublicShelfRefWhenArtifactIdIsAbsent",
        "LaunchJobBindsPublicationOutputsToApprovedPublicShelfRefWhenPublicationIdIsAbsent",
        "ControllerLaunchJobRequiresInternalToken",
        "LaunchJobRejectsProviderSpecificEvidenceRefs",
        "LaunchJobRejectsProviderSpecificSlashEvidenceRefs",
        "LaunchJobRejectsExternalPublicShelfRefs",
        "LaunchJobRejectsExternalPublicShelfEvidenceRefs",
        "LaunchJobRejectsCrossRecipePublicShelfRefs",
        "LaunchJobRejectsCrossRecipePublicShelfEvidenceRefs",
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
    "landed_commit: b9e6b52e",
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
    "dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
    "artifact_factory:orchestration",
    "public_proof_shelf:release_bundles",
    "/docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards",
    "/docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution",
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
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
}
REQUIRED_REGISTRY_EVIDENCE = {
    "/docker/chummercomplete/chummer.run-services commit cda8849a binds release, fix, support, and publication recipe jobs to stable public proof shelf output refs.",
    "/docker/chummercomplete/chummer.run-services commit e25842ac tightens mixed source-pack output anchoring so release bundle refs always bind to an approved artifact-bearing source pack.",
    "/docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards so approved local refs cannot cross from release or publication recipes onto the wrong shelf family.",
    "/docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution so stale file or commit anchors cannot keep the completed package green.",
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

    for item in items:
        if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID:
            return item
    raise ValueError(f"queue staging is missing package_id {PACKAGE_ID}.")


def find_successor_task(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("successor registry root must be a mapping.")
    milestones = data.get("milestones")
    if not isinstance(milestones, list):
        raise ValueError("successor registry is missing a milestones list.")

    milestone = next(
        (
            item
            for item in milestones
            if isinstance(item, dict) and item.get("id") == MILESTONE_ID
        ),
        None,
    )
    if not isinstance(milestone, dict):
        raise ValueError(f"successor registry is missing milestone {MILESTONE_ID}.")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        raise ValueError(f"milestone {MILESTONE_ID} is missing work_tasks.")

    task = next(
        (
            item
            for item in work_tasks
            if isinstance(item, dict) and float(item.get("id", -1)) == WORK_TASK_ID
        ),
        None,
    )
    if not isinstance(task, dict):
        raise ValueError(f"milestone {MILESTONE_ID} is missing work task {WORK_TASK_ID}.")
    return task


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

    try:
        queue_text = read_text(QUEUE_STAGING_PATH)
    except FileNotFoundError as exc:
        missing.append(str(exc))
    else:
        for marker in QUEUE_MARKERS:
            if marker not in queue_text:
                missing.append(f"{QUEUE_STAGING_PATH}: {marker}")
        verify_queue_authority(missing, QUEUE_STAGING_PATH)

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
