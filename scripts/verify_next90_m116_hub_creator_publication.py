#!/usr/bin/env python3
from __future__ import annotations

import json
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
EXPECTED_STATUS = "complete"
EXPECTED_WAVE = "W13"
PACKAGE_COMPLETION_ACTION = "verify_closed_package_only"
PACKAGE_DO_NOT_REOPEN_REASON = (
    "M116 chummer6-hub creator publication discovery and moderation orchestration is complete; future shards must "
    "verify approved-manifest authority discovery, correction, moderation, public artifact shelf contracts, and registry-facing "
    "proof evidence from this package instead of reopening this slice."
)
REQUIRED_PROOF = [
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/AccountsController.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml",
    "/docker/chummercomplete/chummer.run-services/tests/RunServicesSmoke/Program.cs",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_next90_m116_hub_creator_publication.py",
    "/docker/chummercomplete/chummer.run-services/tests/test_next90_m116_hub_creator_publication.py",
    "/docker/chummercomplete/chummer.run-services/.codex-studio/published/NEXT90_M116_HUB_CREATOR_PUBLICATION.generated.json",
    "python3 scripts/verify_next90_m116_hub_creator_publication.py",
    "python3 -m unittest tests/test_next90_m116_hub_creator_publication.py",
    "bash scripts/ai/verify.sh",
]
GENERATED_PROOF_REQUIRED_FILES = [
    required_file
    for required_file in REQUIRED_PROOF
    if required_file.startswith("/docker/chummercomplete/chummer.run-services/")
    and "/.codex-studio/published/" not in required_file
]

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
LOCAL_MIRROR_SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_LOCAL_MIRROR_SUCCESSOR_REGISTRY",
        str(ROOT / ".codex-design/product/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"),
    )
)
GENERATED_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_GENERATED_PROOF",
        str(ROOT / ".codex-studio/published/NEXT90_M116_HUB_CREATOR_PUBLICATION.generated.json"),
    )
)
GENERATED_PROOF_CONTRACT = "chummer6-hub.next90_m116_hub_creator_publication"
GENERATED_PROOF_EVIDENCE = {
    "packageId": PACKAGE_ID,
    "workTaskId": WORK_TASK_ID,
    "frontierId": FRONTIER_ID,
    "milestoneId": MILESTONE_ID,
    "wave": EXPECTED_WAVE,
    "repo": "chummer6-hub",
    "task": TITLE,
    "title": TITLE,
    "status": EXPECTED_STATUS,
    "completionAction": PACKAGE_COMPLETION_ACTION,
    "doNotReopenReason": PACKAGE_DO_NOT_REOPEN_REASON,
    "allowedPaths": ALLOWED_PATHS,
    "ownedSurfaces": OWNED_SURFACES,
}
GENERATED_PROOF_COMMANDS = {
    "verifyScript": "python3 scripts/verify_next90_m116_hub_creator_publication.py",
    "targetedTests": "python3 -m unittest tests/test_next90_m116_hub_creator_publication.py",
    "aggregateVerify": "bash scripts/ai/verify.sh",
}
REGISTRY_EVIDENCE_MARKERS = [
    "PublicLandingController.cs and /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs now keep governed public discovery and detail routes restricted to approved-manifest-backed creator publications while preserving sibling packet navigation and the public artifact shelf contracts.",
    "AccountsController.cs, /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/Accounts/Account.cshtml, and /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs now keep submission, rejection, correction resubmission, approval, and publication on one approved-manifest moderation lane and fail closed without approved audit authority.",
    "tests/RunServicesSmoke/Program.cs proves correction-pass resubmission notes, fail-closed public detail routes for rejected packets, and governed public shelf/detail contracts on discoverable creator publications.",
    "scripts/verify_next90_m116_hub_creator_publication.py, /docker/chummercomplete/chummer.run-services/tests/test_next90_m116_hub_creator_publication.py, and /docker/chummercomplete/chummer.run-services/.codex-studio/published/NEXT90_M116_HUB_CREATOR_PUBLICATION.generated.json keep the closed-package queue, registry, generated-proof, and source-marker receipt executable inside the repo.",
    "python3 scripts/verify_next90_m116_hub_creator_publication.py exits 0, python3 -m unittest tests/test_next90_m116_hub_creator_publication.py exits 0, and bash scripts/ai/verify.sh keeps the dedicated M116 verifier in the shared verify lane.",
]

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": [
        'contractName = "chummer.run.public_artifact_shelf.v2"',
        "publicCreatorPublications = filteredPublicCreatorPublications.Select(publication =>",
        'contractName = "chummer.run.public_artifact_shelf.publication.v1"',
        'IReadOnlyList<CreatorPublicationProjection> siblings = _publicCreatorDiscovery.ListDiscoverable(limit: 12)',
        'publication = BuildArtifactShelfCreatorPublicationPayload(',
    ],
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
        'Assert(rejectedDossierPublicationDetailModel?.SelectedCreatorPublication?.ModerationSummary?.Contains("requires revision", StringComparison.OrdinalIgnoreCase) == true, "rejected dossier publications should explain that governed moderation requires a correction pass.");',
        'var resubmitDossierPublicationResult = await accountController.SubmitCreatorPublication(dossierPublicationId, "Correction pass refreshed the dossier packet provenance and return summary for governed moderation.", CancellationToken.None);',
        'Assert(string.Equals(resubmittedDossierPublicationDetailModel?.SelectedCreatorPublicationReceipt?.ReviewState, Chummer.Hub.Registry.Contracts.HubReviewStates.PendingReview, StringComparison.Ordinal), "resubmitted dossier publications should re-enter the registry moderation queue after a correction pass.");',
        'Assert(string.Equals(resubmittedDossierPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.Moderation?.State, Chummer.Hub.Registry.Contracts.HubModerationStates.PendingReview, StringComparison.Ordinal), "resubmitted dossier publications should surface a fresh pending moderation case after correction.");',
        'Assert(artifactsModel.PublicCreatorPublications?.Count > 0, "guest artifacts shelf should surface governed public creator discovery once a creator packet is actually published.");',
        'Assert(publicCreatorDetailModel is not null, "guest creator-publication detail should render through the MVC view layer.");',
        'Assert(publicCreatorDetailModel.TrustPulse is not null, "guest creator-publication detail should surface the shared public trust pulse.");',
        'Assert(authenticatedCreatorDetailModel?.SignedInStatus is not null, "authenticated creator-publication detail should project the shared signed-in trust status.");',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m116_hub_creator_publication.py",
        "python3 -m unittest tests/test_next90_m116_hub_creator_publication.py",
    ],
    "tests/test_next90_m116_hub_creator_publication.py": [
        "class Next90M116HubCreatorPublicationTests(unittest.TestCase):",
        'self.assertIn("Resubmit corrected packet", result.stderr)',
        'self.assertIn("fresh pending moderation case after correction", result.stderr)',
        'self.assertIn("governed public creator discovery", result.stderr)',
        'self.assertIn("shared signed-in trust status", result.stderr)',
    ],
}


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        return handle.read()


def load_yaml(path: Path) -> object:
    return yaml.safe_load(read_text(path))


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_queue_staging_yaml(path: Path) -> object:
    text = read_text(path)
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = None
    else:
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload

    package_marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(package_marker)
    if package_index < 0:
        raise ValueError(f"queue staging is missing package_id {PACKAGE_ID}")

    start = text.rfind("\n- title:", 0, package_index)
    if start < 0:
        if not text.startswith("- title:"):
            raise ValueError(f"queue staging is missing the item block for {PACKAGE_ID}")
        start = 0
    else:
        start += 1

    end = text.find("\n- title:", package_index)
    if end < 0:
        end = len(text)

    block = text[start:end].rstrip() + "\n"
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError(f"queue staging package block for {PACKAGE_ID} must parse to exactly one item")
    return {"items": payload}


def load_queue_row(missing: list[str], path: Path) -> dict[str, object] | None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return None

    try:
        payload = load_queue_staging_yaml(path) or {}
    except (ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: {exc}")
        return None
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        missing.append(f"{path}: items is missing")
        return None

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return None

    return matches[0]


def verify_queue_authority(missing: list[str], path: Path) -> dict[str, object] | None:
    item = load_queue_row(missing, path)
    if item is None:
        return None

    expected_fields = {
        "title": TITLE,
        "task": TASK,
        "repo": "chummer6-hub",
        "milestone_id": MILESTONE_ID,
        "work_task_id": 116.1,
        "frontier_id": FRONTIER_ID,
        "status": EXPECTED_STATUS,
        "wave": EXPECTED_WAVE,
        "completion_action": PACKAGE_COMPLETION_ACTION,
        "do_not_reopen_reason": PACKAGE_DO_NOT_REOPEN_REASON,
    }
    for key, value in expected_fields.items():
        if item.get(key) != value:
            missing.append(f"{path}: {PACKAGE_ID} {key} must be {value!r}")

    if item.get("allowed_paths") != ALLOWED_PATHS:
        missing.append(f"{path}: {PACKAGE_ID} allowed_paths must be {ALLOWED_PATHS!r}")
    if item.get("owned_surfaces") != OWNED_SURFACES:
        missing.append(f"{path}: {PACKAGE_ID} owned_surfaces must be {OWNED_SURFACES!r}")

    proof = item.get("proof")
    if not isinstance(proof, list) or not proof:
        missing.append(f"{path}: {PACKAGE_ID} must define a non-empty proof list")
    else:
        if proof != REQUIRED_PROOF:
            missing.append(f"{path}: {PACKAGE_ID} proof must match the closed-package receipt exactly")

    return item


def verify_queue_parity(
    missing: list[str],
    queue_row: dict[str, object] | None,
    design_queue_row: dict[str, object] | None,
) -> None:
    if queue_row is None or design_queue_row is None:
        return

    if queue_row != design_queue_row:
        missing.append("fleet and design queue rows for next90-m116-hub-creator-publication must match exactly")


def verify_successor_registry(missing: list[str], path: Path) -> dict[str, object] | None:
    if not path.is_file():
        missing.append(f"missing successor registry file: {path}")
        return None

    payload = load_yaml(path) or {}
    milestones = payload.get("milestones") if isinstance(payload, dict) else None
    if not isinstance(milestones, list):
        missing.append(f"{path}: milestones is missing")
        return None

    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if milestone is None:
        missing.append(f"{path}: milestone {MILESTONE_ID} is missing")
        return None

    if milestone.get("title") != "Creator publication discovery, lineage, moderation, and trust ranking":
        missing.append(f"{path}: milestone {MILESTONE_ID} title drifted")
    if milestone.get("status") != EXPECTED_STATUS:
        missing.append(f"{path}: milestone {MILESTONE_ID} status must be {EXPECTED_STATUS!r}")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        missing.append(f"{path}: milestone {MILESTONE_ID} work_tasks is missing")
        return None

    task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == WORK_TASK_ID), None)
    if task is None:
        missing.append(f"{path}: work task {WORK_TASK_ID} is missing")
        return None

    if task.get("owner") != "chummer6-hub":
        missing.append(f"{path}: work task {WORK_TASK_ID} owner drifted")
    if task.get("title") != WORK_TASK_TITLE:
        missing.append(f"{path}: work task {WORK_TASK_ID} title drifted")
    if task.get("status") != EXPECTED_STATUS:
        missing.append(f"{path}: work task {WORK_TASK_ID} status must be {EXPECTED_STATUS!r}")

    evidence = task.get("evidence")
    if not isinstance(evidence, list):
        missing.append(f"{path}: work task {WORK_TASK_ID} evidence must be a list")
    else:
        evidence_text = "\n".join(str(item) for item in evidence)
        for marker in REGISTRY_EVIDENCE_MARKERS:
            if marker not in evidence_text:
                missing.append(f"{path}: work task {WORK_TASK_ID} evidence missing marker {marker!r}")

    return task


def verify_successor_registry_parity(
    missing: list[str],
    canonical_task: dict[str, object] | None,
    mirror_task: dict[str, object] | None,
) -> None:
    if canonical_task is None or mirror_task is None:
        return

    if canonical_task != mirror_task:
        missing.append("canonical and repo-local successor registry work task 116.1 must match exactly")


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


def verify_generated_proof(missing: list[str], path: Path) -> None:
    if not path.is_file():
        missing.append(f"missing generated proof: {path}")
        return

    payload = load_json(path)
    if not isinstance(payload, dict):
        missing.append(f"{path}: payload must be a JSON object")
        return

    if payload.get("status") != "pass":
        missing.append(f"{path}: status must be 'pass'")
    if payload.get("contract_name") != GENERATED_PROOF_CONTRACT:
        missing.append(f"{path}: contract_name must be {GENERATED_PROOF_CONTRACT!r}")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        missing.append(f"{path}: evidence must be a JSON object")
        return

    for key, value in GENERATED_PROOF_EVIDENCE.items():
        if evidence.get(key) != value:
            missing.append(f"{path}: evidence.{key} must be {value!r}")

    proof_files = evidence.get("proofFiles")
    if not isinstance(proof_files, list):
        missing.append(f"{path}: evidence.proofFiles must be a list")
    elif proof_files != GENERATED_PROOF_REQUIRED_FILES:
        missing.append(f"{path}: evidence.proofFiles must match the closed-package receipt exactly")

    proof_commands = evidence.get("proofCommands")
    if not isinstance(proof_commands, dict):
        missing.append(f"{path}: evidence.proofCommands must be a JSON object")
        return

    for key, value in GENERATED_PROOF_COMMANDS.items():
        if proof_commands.get(key) != value:
            missing.append(f"{path}: evidence.proofCommands.{key} must be {value!r}")


def main() -> int:
    missing: list[str] = []
    queue_row = verify_queue_authority(missing, QUEUE_STAGING_PATH)
    design_queue_row = verify_queue_authority(missing, DESIGN_QUEUE_STAGING_PATH)
    verify_queue_parity(missing, queue_row, design_queue_row)
    registry_task = verify_successor_registry(missing, SUCCESSOR_REGISTRY_PATH)
    local_mirror_registry_task = verify_successor_registry(missing, LOCAL_MIRROR_SUCCESSOR_REGISTRY_PATH)
    verify_successor_registry_parity(missing, registry_task, local_mirror_registry_task)
    verify_generated_proof(missing, GENERATED_PROOF_PATH)
    verify_source_markers(missing)

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m116 hub creator publication proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
