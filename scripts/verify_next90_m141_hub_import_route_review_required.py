#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the"
WORK_TASK_ID = "141.3"
FRONTIER_ID = 4062147200
MILESTONE_ID = 141
PACKAGE_TITLE = "Keep route, support, and publication surfaces from claiming parity for these routes unless the direct proof receipts are current."
PACKAGE_TASK = "Keep route, support, and publication surfaces from claiming parity for these routes unless the direct proof receipts are current."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W22P"
PACKAGE_STATUS = "complete"
COMPLETION_ACTION = "verify_closed_package_only"
DO_NOT_REOPEN_REASON = (
    "M141 chummer6-hub import-route review-required guard is complete; future shards must verify "
    "the route/support/publication proof receipt, canonical registry row, queue mirrors, and local+served "
    "Hub proof instead of reopening this slice."
)
OWNED_SURFACES = ["keep_route_support_and_publication_surfaces_from_claimin:hub"]
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
RECEIPT_ID = "keep_route_support_and_publication_surfaces_from_claimin:hub"
RECEIPT_ROUTES = [
    "/downloads",
    "/status",
    "/contact",
    "/account/support",
    "/artifacts",
    "/artifacts/publications/{publicationId}",
    "/api/v1/public/artifacts/publications/{publicationId}",
]
RECEIPT_SURFACES = [
    "keep_route_support_and_publication_surfaces_from_claimin:hub",
    "public_trust_surface:v3",
    "support_followthrough:install_truth",
    "artifact_shelf:v2",
]
PACKAGE_PROOF = [
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ImportRouteParityProofGuardService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/PublicReleaseManifestService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/PublicTrustPulseService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/SignedInTrustStatusService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/DownloadsCompatibilityController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml",
    "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m141_hub_import_route_review_required.py",
    "/docker/chummercomplete/chummer6-hub/tests/test_next90_m141_hub_import_route_review_required.py",
    "/docker/chummercomplete/chummer6-hub/tests/test_hub_local_release_proof_native_support_route.py",
    "/docker/chummercomplete/chummer6-hub/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "python3 scripts/verify_next90_m141_hub_import_route_review_required.py",
    "python3 -m unittest tests/test_next90_m141_hub_import_route_review_required.py",
    "python3 -m unittest tests/test_hub_local_release_proof_native_support_route.py",
    "bash scripts/ai/verify.sh",
]
SOURCE_MARKERS = {
    "Chummer.Run.Api/Services/ImportRouteParityProofGuardService.cs": [
        '"menu:translator"',
        '"menu:xml_editor"',
        '"menu:hero_lab_importer"',
        '"workflow:import_oracle"',
        "the current local release-proof package does not publish direct proof receipts for translator, XML amendment, Hero Lab, and adjacent import routes",
    ],
    "Chummer.Run.Api/Services/PublicTrustPulseService.cs": [
        "Import-route parity claims stay review-required because",
        "ParityClaimsReviewRequired: parityClaimsReviewRequired",
        "Hold parity claims on public routes, support surfaces, and publication lanes because",
    ],
    "Chummer.Run.Api/Services/PublicReleaseManifestService.cs": [
        "ApplyImportRouteParityGuard(",
        "Translator, XML amendment, Hero Lab, and adjacent import parity receipts are not current yet",
    ],
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": [
        'pulse?.ParityClaimsReviewRequired == true ? "review_required" : null',
        "ImportRouteParityProofGuardService(configuration)",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        "ImportRouteParityProofGuardService(configuration)",
    ],
    "Chummer.Run.Api/Controllers/DownloadsCompatibilityController.cs": [
        "ImportRouteParityProofGuardService(configuration)",
    ],
    "Chummer.Run.Api/Services/SignedInTrustStatusService.cs": [
        "(pulse?.ParityClaimsReviewRequired ?? false)",
    ],
    "Chummer.Run.Api/ViewModels/SiteViewModels.cs": [
        "bool ParityClaimsReviewRequired = false,",
    ],
    "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml": [
        "Model.TrustPulse?.ParityClaimsReviewRequired == true",
        "current direct parity proof receipts still hold public parity claims on the review-required lane",
    ],
    "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml": [
        "Model.TrustPulse?.ParityClaimsReviewRequired == true",
        "public parity claims remain review-required until current direct parity proof receipts are green",
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        f'"package_id": "{PACKAGE_ID}"',
        f'"receipt_id": "{RECEIPT_ID}"',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m141_hub_import_route_review_required.py",
        "python3 -m unittest tests/test_next90_m141_hub_import_route_review_required.py",
    ],
}
DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M141_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M141_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M141_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M141_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M141_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M141_SERVED_RELEASE_PROOF",
        str(ROOT / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def require_contains(path: Path, needle: str, issues: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        issues.append(f"{path.name} is missing required M141 review guard marker: {needle}")


def load_queue_payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        mode_index = text.find("\nmode:")
        if mode_index < 0 and not text.startswith("mode:"):
            raise
        normalized_text = text if text.startswith("mode:") else text[mode_index + 1 :]
        sanitized_lines: list[str] = []
        previous_sequence_indent: int | None = None
        for line in normalized_text.splitlines():
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if (
                sanitized_lines
                and previous_sequence_indent is not None
                and stripped
                and not stripped.startswith("- ")
                and ":" not in stripped
                and indent == previous_sequence_indent
            ):
                sanitized_lines[-1] = f"{sanitized_lines[-1]} {stripped}"
                continue

            sanitized_lines.append(line)
            previous_sequence_indent = indent if stripped.startswith("- ") else None

        payload = yaml.safe_load("\n".join(sanitized_lines) + "\n")

    if not isinstance(payload, dict):
        raise TypeError(f"queue payload at {path} is not a YAML mapping")

    return payload


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"json payload at {path} is not an object")
    return payload


def find_queue_row(queue_payload: dict, path: Path, issues: list[str]) -> dict | None:
    items = queue_payload.get("items")
    if not isinstance(items, list):
        issues.append(f"{path} does not contain an items list")
        return None

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        issues.append(f"{path} must contain exactly one {PACKAGE_ID} row")
        return None

    return matches[0]


def verify_queue_row(row: dict, path: Path, issues: list[str]) -> None:
    if row.get("status") != PACKAGE_STATUS:
        issues.append(f"{path}: status must be '{PACKAGE_STATUS}'")
    if row.get("completion_action") != COMPLETION_ACTION:
        issues.append(f"{path}: completion_action must be '{COMPLETION_ACTION}'")
    if row.get("work_task_id") != WORK_TASK_ID:
        issues.append(f"{path}: work_task_id must be '{WORK_TASK_ID}'")
    if row.get("frontier_id") != FRONTIER_ID:
        issues.append(f"{path}: frontier_id must be {FRONTIER_ID}")
    if row.get("milestone_id") != MILESTONE_ID:
        issues.append(f"{path}: milestone_id must be {MILESTONE_ID}")
    if row.get("wave") != PACKAGE_WAVE:
        issues.append(f"{path}: wave must be '{PACKAGE_WAVE}'")
    if row.get("repo") != PACKAGE_REPO:
        issues.append(f"{path}: repo must be '{PACKAGE_REPO}'")
    if row.get("title") != PACKAGE_TITLE:
        issues.append(f"{path}: title drifted")
    if row.get("task") != PACKAGE_TASK:
        issues.append(f"{path}: task drifted")
    if row.get("do_not_reopen_reason") != DO_NOT_REOPEN_REASON:
        issues.append(f"{path}: do_not_reopen_reason drifted")
    if row.get("allowed_paths") != ALLOWED_PATHS:
        issues.append(f"{path}: allowed_paths drifted")
    if row.get("owned_surfaces") != OWNED_SURFACES:
        issues.append(f"{path}: owned_surfaces drifted")
    if row.get("proof") != PACKAGE_PROOF:
        issues.append(f"{path}: proof drifted")


def verify_registry(issues: list[str]) -> None:
    payload = yaml.safe_load(SUCCESSOR_REGISTRY_PATH.read_text(encoding="utf-8"))
    milestones = payload.get("milestones") if isinstance(payload, dict) else None
    if not isinstance(milestones, list):
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} does not contain milestones")
        return

    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if milestone is None:
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} is missing milestone {MILESTONE_ID}")
        return

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} milestone {MILESTONE_ID} is missing work_tasks")
        return

    work_task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == WORK_TASK_ID), None)
    if work_task is None:
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} is missing work task {WORK_TASK_ID}")
        return

    if work_task.get("owner") != PACKAGE_REPO:
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} work task {WORK_TASK_ID} owner drifted")
    if work_task.get("title") != PACKAGE_TITLE:
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} work task {WORK_TASK_ID} title drifted")
    if work_task.get("status") != PACKAGE_STATUS:
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} work task {WORK_TASK_ID} status must be '{PACKAGE_STATUS}'")
    if work_task.get("completion_action") != COMPLETION_ACTION:
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} work task {WORK_TASK_ID} completion_action drifted")
    if work_task.get("do_not_reopen_reason") != DO_NOT_REOPEN_REASON:
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} work task {WORK_TASK_ID} do_not_reopen_reason drifted")

    evidence = work_task.get("evidence")
    if not isinstance(evidence, list):
        issues.append(f"{SUCCESSOR_REGISTRY_PATH} work task {WORK_TASK_ID} evidence is missing")
        return

    required_markers = [
        "ImportRouteParityProofGuardService.cs",
        "PublicReleaseManifestService.cs, PublicTrustPulseService.cs, and SignedInTrustStatusService.cs",
        "PublicLandingController.cs, DownloadsCompatibilityController.cs, CampaignSpineController.cs",
        "verify_next90_m141_hub_import_route_review_required.py",
    ]
    for marker in required_markers:
        if not any(marker in str(item) for item in evidence):
            issues.append(f"{SUCCESSOR_REGISTRY_PATH} work task {WORK_TASK_ID} evidence is missing marker: {marker}")


def verify_release_proof(path: Path, issues: list[str]) -> None:
    payload = load_json(path)
    packages = payload.get("successor_queue_packages")
    package_by_id = payload.get("successor_queue_packages_by_id")
    receipts = payload.get("proof_receipts")

    if not isinstance(packages, list):
        issues.append(f"{path}: successor_queue_packages is missing")
        return
    if not isinstance(package_by_id, dict):
        issues.append(f"{path}: successor_queue_packages_by_id is missing")
        return
    if not isinstance(receipts, list):
        issues.append(f"{path}: proof_receipts is missing")
        return

    package_rows = [item for item in packages if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(package_rows) != 1:
        issues.append(f"{path}: successor_queue_packages must contain exactly one {PACKAGE_ID} row")
    package_row = package_by_id.get(PACKAGE_ID)
    if not isinstance(package_row, dict):
        issues.append(f"{path}: successor_queue_packages_by_id is missing {PACKAGE_ID}")
        return

    for key, expected in {
        "package_id": PACKAGE_ID,
        "work_task_id": WORK_TASK_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "repo": PACKAGE_REPO,
        "status": PACKAGE_STATUS,
        "completion_action": COMPLETION_ACTION,
        "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
        "wave": PACKAGE_WAVE,
        "task": PACKAGE_TASK,
        "title": PACKAGE_TITLE,
        "allowed_paths": ALLOWED_PATHS,
        "owned_surfaces": OWNED_SURFACES,
        "proof": PACKAGE_PROOF,
        "exit_criterion": PACKAGE_TASK,
    }.items():
        if package_row.get(key) != expected:
            issues.append(f"{path}: package field {key} drifted")

    matching_receipts = [
        item
        for item in receipts
        if isinstance(item, dict)
        and item.get("package_id") == PACKAGE_ID
        and item.get("receipt_id") == RECEIPT_ID
    ]
    if len(matching_receipts) != 1:
        issues.append(f"{path}: receipt id {RECEIPT_ID} must appear exactly once in proof_receipts")
        return

    receipt = matching_receipts[0]
    if receipt.get("milestone_id") != MILESTONE_ID:
        issues.append(f"{path}: receipt {RECEIPT_ID} milestone drifted")
    if receipt.get("frontier_id") != FRONTIER_ID:
        issues.append(f"{path}: receipt {RECEIPT_ID} frontier drifted")
    if receipt.get("routes") != RECEIPT_ROUTES:
        issues.append(f"{path}: receipt {RECEIPT_ID} routes drifted")
    if receipt.get("surfaces") != RECEIPT_SURFACES:
        issues.append(f"{path}: receipt {RECEIPT_ID} surfaces drifted")

    summary = str(receipt.get("summary") or "")
    if "direct translator, XML amendment, Hero Lab, and adjacent import-route receipts" not in summary:
        issues.append(f"{path}: receipt {RECEIPT_ID} summary drifted")

    evidence = receipt.get("evidence")
    if not isinstance(evidence, list):
        issues.append(f"{path}: receipt {RECEIPT_ID} evidence is missing")
        return

    required_markers = [
        "ImportRouteParityProofGuardService.cs requires current local release-proof receipts",
        "PublicReleaseManifestService.cs, PublicTrustPulseService.cs, and SignedInTrustStatusService.cs",
        "PublicLandingController.cs, DownloadsCompatibilityController.cs, CampaignSpineController.cs",
        "verify_next90_m141_hub_import_route_review_required.py and tests/test_next90_m141_hub_import_route_review_required.py",
    ]
    for marker in required_markers:
        if not any(marker in str(item) for item in evidence):
            issues.append(f"{path}: receipt {RECEIPT_ID} evidence is missing marker: {marker}")


def main() -> int:
    issues: list[str] = []

    for relative_path, markers in SOURCE_MARKERS.items():
        path = ROOT / relative_path
        if not path.is_file():
            issues.append(f"missing required source file: {path}")
            continue
        for marker in markers:
            require_contains(path, marker, issues)

    fleet_queue = load_queue_payload(FLEET_QUEUE_STAGING_PATH)
    design_queue = load_queue_payload(DESIGN_QUEUE_STAGING_PATH)
    fleet_row = find_queue_row(fleet_queue, FLEET_QUEUE_STAGING_PATH, issues)
    design_row = find_queue_row(design_queue, DESIGN_QUEUE_STAGING_PATH, issues)
    if fleet_row is not None:
        verify_queue_row(fleet_row, FLEET_QUEUE_STAGING_PATH, issues)
    if design_row is not None:
        verify_queue_row(design_row, DESIGN_QUEUE_STAGING_PATH, issues)
    if fleet_row is not None and design_row is not None and fleet_row != design_row:
        issues.append(f"fleet and design queue rows for {PACKAGE_ID} must match exactly")

    verify_registry(issues)
    verify_release_proof(LOCAL_RELEASE_PROOF_PATH, issues)
    verify_release_proof(SERVED_RELEASE_PROOF_PATH, issues)

    if issues:
        print("next90 m141 hub import-route review-required verifier failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    print("next90 m141 hub import-route review-required proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
