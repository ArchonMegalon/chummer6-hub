#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m110-hub-runsite-orientation-requests"
FRONTIER_ID = 1545739925
MILESTONE_ID = 110
WORK_TASK_ID = "110.1"
PACKAGE_TITLE = "Compose runsite orientation requests from approved runsite packs and route summaries"
PACKAGE_TASK = "Compose governed runsite orientation requests from approved runsite packs, route summaries, and preview-safe pre-session truth."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W10"
OWNED_SURFACES = {"runsite_orientation_requests", "route_summary:artifact_launch"}
ALLOWED_PATHS = {"Chummer.Run.Api", "scripts", "tests"}
COMPLETION_ACTION = "verify_closed_package_only"
DO_NOT_REOPEN_REASON = (
    "M110 chummer6-hub runsite orientation requests are complete; future shards must verify "
    "the governed composition route, generated proof receipts, and queue/registry rows instead "
    "of reopening this package."
)
LOCAL_RELEASE_PROOF_PACKAGE = {
    "package_id": PACKAGE_ID,
    "milestone_id": MILESTONE_ID,
    "frontier_id": FRONTIER_ID,
    "repo": PACKAGE_REPO,
    "status": "complete",
    "completion_action": COMPLETION_ACTION,
    "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
    "title": PACKAGE_TITLE,
    "allowed_paths": sorted(ALLOWED_PATHS),
    "owned_surfaces": sorted(OWNED_SURFACES),
    "exit_criterion": PACKAGE_TASK,
}
LOCAL_RELEASE_PROOF_RECEIPTS = {
    "runsite_orientation_requests": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/api/internal/runsite-orientation/requests",
            "/artifacts/routes/{routeSummaryId}/{routeSegmentId}",
        ],
        "surfaces": [
            "runsite_orientation_requests",
            "runsite_orientation_bundle",
            "preview_safe_truth:pre_session",
        ],
        "summary_markers": [
            "approved runsite packs",
            "preview-safe pre-session truth",
            "governed",
        ],
    },
    "route_summary:artifact_launch": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/api/internal/runsite-orientation/requests",
            "/artifacts/routes/{routeSummaryId}/{routeSegmentId}",
        ],
        "surfaces": [
            "route_summary:artifact_launch",
            "route_preview:inspectable_truth",
            "runsite_orientation_bundle",
        ],
        "summary_markers": [
            "route summaries",
            "route previews",
            "inspectable",
        ],
    },
}
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "active-run helper",
    "operator telemetry",
    "operator/OODA",
    "supervisor status",
    "successor-wave telemetry",
    "task-local telemetry",
    "shard runtime handoff",
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_RUNSITE_ORIENTATION_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_RUNSITE_ORIENTATION_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_RUNSITE_ORIENTATION_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_RUNSITE_ORIENTATION_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_RUNSITE_ORIENTATION_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_RUNSITE_ORIENTATION_SERVED_RELEASE_PROOF",
        str(ROOT / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)

SOURCE_MARKERS = {
    "Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs": [
        'public const string ContractName = "chummer6-hub.runsite_orientation_request.v1";',
        'public const string ContractVersion = "2026-04-23";',
        'public const string PreviewTruthPosture = "pre-session-orientation-only-not-tactical-truth";',
        'public const string RoutePreviewCategory = "runsite/orientation/route-preview";',
        "public sealed record RunsiteOrientationRequestComposeRequest(",
        "public sealed record ApprovedRunsiteOrientationPack(",
        "public sealed record RunsiteRouteSummary(",
        "public sealed record RunsiteRouteSummaryArtifactLaunch(",
        "public sealed record RunsiteOrientationRequestCompositionResult(",
        "ApprovedRunsitePackId: pack.SourcePackId,",
        "RouteSummaryId: routeSummary.RouteSummaryId,",
        "approved runsite pack '{pack.SourcePackId}' must not pre-compose route previews; route_summary:artifact_launch stays governed by the route summary.",
        "approved runsite pack '{pack.SourcePackId}' must contribute at least one host clip template.",
        "preview-safe truth posture must stay",
        "preview-safe truth summary must keep route preview or tour truth inspectable.",
        "preview-safe truth must include inspectable route ref",
        "must stay '{RoutePreviewCategory}' so route_summary:artifact_launch remains route-summary governed.",
        "PreviewSafeTruthSummary: previewSafeTruth.Summary,",
        "PreviewSafeInspectableTruthRefs: previewSafeTruth.InspectableTruthRefs,",
        "EvidenceRefs: pack.EvidenceRefs,",
        "Audience: audience,",
        "Locale: locale));",
        "previewSafeTruthSummary = previewSafeTruth.Summary",
        "previewSafeInspectableTruthRefs = previewSafeTruth.InspectableTruthRefs",
        "provenanceRef = pack.ProvenanceRef",
        "evidenceRefs = pack.EvidenceRefs",
        "must not emit duplicate deduplication key",
        "evidence refs must include route-summary:",
        "evidence refs must include a preview-safe:* anchor.",
        "evidence refs must include a pre-session:* anchor.",
        "audience,",
        "locale,",
        "runsite/orientation/route-preview",
        'Source: $"runsite-orientation-request:{requestedBy}"',
        "AllowPersistentPinning: false",
        'throw new InvalidDataException($"{fieldName} must be valid JSON-shaped preview-safe content.", ex);',
        "RouteSummaryArtifactLaunches: routeSummaryArtifactLaunches",
    ],
    "Chummer.Run.Api/Controllers/InternalRunsiteOrientationController.cs": [
        '[HttpPost("/api/internal/runsite-orientation/requests")]',
        "[ProducesResponseType<RunsiteOrientationRequestCompositionResult>(StatusCodes.Status200OK)]",
        '"runsite orientation request is required."',
        "internal runsite orientation authorization is required.",
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "services.AddSingleton<RunsiteOrientationRequestComposerService>();",
    ],
    "Chummer.Tests/RunsiteOrientationRequestComposerServiceTests.cs": [
        "public sealed class RunsiteOrientationRequestComposerServiceTests",
        "ComposeRejectsRunsitePacksThatTryToOwnRoutePreviewArtifacts",
        "ComposeBuildsRouteSummaryArtifactLaunchesFromRouteSegments",
        "InternalControllerRequiresBearerAuthorization",
        "InternalControllerReturnsComposedOrientationRequestWhenAuthorized",
    ],
    "scripts/verify_runsite_orientation_requests.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        f'COMPLETION_ACTION = "{COMPLETION_ACTION}"',
        "DO_NOT_REOPEN_REASON = (",
        "CHUMMER_RUNSITE_ORIENTATION_DESIGN_QUEUE_STAGING",
        "LOCAL_RELEASE_PROOF_PACKAGE = {",
        "LOCAL_RELEASE_PROOF_RECEIPTS = {",
        "FORBIDDEN_PROOF_MARKERS = [",
        "verify_queue_row(errors, FLEET_QUEUE_STAGING_PATH, label=\"fleet queue\")",
        "verify_queue_row(errors, DESIGN_QUEUE_STAGING_PATH, label=\"design queue\")",
        "verify_release_proof(errors, LOCAL_RELEASE_PROOF_PATH, label=\"repo-local release proof\")",
        "verify_release_proof(errors, SERVED_RELEASE_PROOF_PATH, label=\"served release proof\")",
        "runsite orientation request proof passed",
        "route_summary:artifact_launch",
        "preview-safe pre-session truth",
        "work_task_id",
    ],
    "tests/test_runsite_orientation_requests.py": [
        "verify_runsite_orientation_requests.py",
        "pre-session-orientation-only-not-tactical-truth",
        "route_summary:artifact_launch",
        '[HttpPost("/api/internal/runsite-orientation/requests")]',
        "test_composer_builds_governed_runsite_bundle_request",
        "test_composer_rejects_missing_route_summary_evidence_anchor",
        "test_composer_rejects_missing_preview_safe_evidence_anchor",
        "test_composer_rejects_duplicate_deduplication_keys",
        "test_composer_rejects_route_summary_category_drift",
        "test_verifier_fails_when_queue_frontier_id_is_removed",
        "test_verifier_fails_when_queue_reopen_reason_is_weakened",
        "test_materialized_release_proof_includes_runsite_orientation_package",
        "ApprovedRunsitePackId",
        "PreviewSafeTruthSummary",
        "EvidenceRefs",
        "AllowPersistentPinning",
        "RunsiteOrientationComposerHarness.csproj",
    ],
    "tests/test_hub_local_release_proof_native_support_route.py": [
        "test_materialized_m110_proof_includes_runsite_orientation_receipts",
        "next90-m110-hub-runsite-orientation-requests",
        "route_summary:artifact_launch",
        "/api/internal/runsite-orientation/requests",
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        "next90-m110-hub-runsite-orientation-requests",
        '"frontier_id": 1545739925',
        '"receipt_id": "runsite_orientation_requests"',
        '"receipt_id": "route_summary:artifact_launch"',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_runsite_orientation_requests.py",
        "python3 -m unittest tests/test_runsite_orientation_requests.py",
        "run_slice_safe_dotnet_test RunsiteOrientationRequestComposerServiceTests",
    ],
}


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def verify_source_markers(errors: list[str]) -> None:
    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")


def reject_forbidden_markers(text: str, source: str, errors: list[str]) -> None:
    lowered = text.casefold()
    for marker in FORBIDDEN_PROOF_MARKERS:
        if marker.casefold() in lowered:
            errors.append(f"{source} contains forbidden active-run proof marker: {marker}")


def queue_item_block(text: str, package_id: str) -> str:
    marker = f"package_id: {package_id}"
    package_index = text.find(marker)
    if package_index == -1:
        return ""

    start_candidates = [
        text.rfind("\n- title:", 0, package_index),
        text.rfind("\n  - title:", 0, package_index),
    ]
    block_start = max(start_candidates)
    if block_start < 0:
        if text.startswith("- title:") or text.startswith("  - title:"):
            block_start = 0
        else:
            return ""
    else:
        block_start += 1

    end_candidates = [index for index in (text.find("\n- title:", package_index), text.find("\n  - title:", package_index)) if index >= 0]
    block_end = min(end_candidates) if end_candidates else len(text)

    return text[block_start:block_end]


def load_queue_payload(path: Path) -> dict:
    queue_text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(queue_text)
    except yaml.YAMLError:
        block = queue_item_block(queue_text, PACKAGE_ID)
        if not block:
            raise SystemExit(f"unable to parse queue yaml: {path}")
        payload = yaml.safe_load(block)
        if isinstance(payload, list):
            return {"items": payload}
        raise SystemExit(f"unable to normalize queue staging yaml: {path}")

    if not isinstance(payload, dict):
        raise SystemExit(f"queue payload at {path} is not a mapping")

    return payload


def verify_queue_row(errors: list[str], path: Path, *, label: str) -> None:
    queue_text = path.read_text(encoding="utf-8")
    payload = load_queue_payload(path)
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        errors.append(f"{label} must expose items[]: {path}")
        return

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        errors.append(f"{label} must contain exactly one package row for {PACKAGE_ID}; found {len(matches)}")
        return

    block = queue_item_block(queue_text, PACKAGE_ID)
    if block:
        reject_forbidden_markers(block, f"{label} {path}", errors)

    item = matches[0]
    if item.get("milestone_id") != MILESTONE_ID:
        errors.append(f"{label} {PACKAGE_ID} must stay on milestone {MILESTONE_ID}")
    if str(item.get("work_task_id") or "").strip() != WORK_TASK_ID:
        errors.append(f"{label} {PACKAGE_ID} must stay on work_task_id {WORK_TASK_ID}")
    if item.get("repo") != PACKAGE_REPO:
        errors.append(f"{label} {PACKAGE_ID} repo must stay {PACKAGE_REPO}")
    if item.get("title") != PACKAGE_TITLE:
        errors.append(f"{label} {PACKAGE_ID} title drifted")
    if item.get("task") != PACKAGE_TASK:
        errors.append(f"{label} {PACKAGE_ID} task drifted")
    if item.get("wave") != PACKAGE_WAVE:
        errors.append(f"{label} {PACKAGE_ID} wave must stay {PACKAGE_WAVE}")
    if item.get("frontier_id") != FRONTIER_ID:
        errors.append(f"{label} {PACKAGE_ID} frontier_id must be {FRONTIER_ID}")
    if item.get("status") != "complete":
        errors.append(f"{label} {PACKAGE_ID} status must be complete")
    if item.get("completion_action") != COMPLETION_ACTION:
        errors.append(f"{label} {PACKAGE_ID} completion_action must be {COMPLETION_ACTION}")
    if item.get("do_not_reopen_reason") != DO_NOT_REOPEN_REASON:
        errors.append(f"{label} {PACKAGE_ID} do_not_reopen_reason must be the package-specific closure note")
    if set(item.get("owned_surfaces") or []) != OWNED_SURFACES:
        errors.append(f"{label} {PACKAGE_ID} owned_surfaces must stay {sorted(OWNED_SURFACES)}")
    if set(item.get("allowed_paths") or []) != ALLOWED_PATHS:
        errors.append(f"{label} {PACKAGE_ID} allowed_paths must stay {sorted(ALLOWED_PATHS)}")


def verify_registry_row(errors: list[str]) -> None:
    registry_text = SUCCESSOR_REGISTRY_PATH.read_text(encoding="utf-8")
    payload = yaml.safe_load(registry_text)
    milestones = payload.get("milestones") if isinstance(payload, dict) else None
    if not isinstance(milestones, list):
        errors.append(f"successor registry must expose milestones[]: {SUCCESSOR_REGISTRY_PATH}")
        return

    milestone = next(
        (item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID),
        None,
    )
    if not isinstance(milestone, dict):
        errors.append(f"successor registry missing milestone {MILESTONE_ID}")
        return

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        errors.append(f"successor registry milestone {MILESTONE_ID} must expose work_tasks[]")
        return

    task = next(
        (
            item
            for item in work_tasks
            if isinstance(item, dict)
            and str(item.get("id")).strip() == WORK_TASK_ID
            and item.get("owner") == PACKAGE_REPO
        ),
        None,
    )
    if not isinstance(task, dict):
        errors.append(f"successor registry milestone {MILESTONE_ID} must keep work task {WORK_TASK_ID} owned by {PACKAGE_REPO}")
        return

    if task.get("title") != f"{PACKAGE_TITLE}.":
        errors.append(f"successor registry work task {WORK_TASK_ID} title drifted")
    if task.get("status") != "complete":
        errors.append(f"successor registry work task {WORK_TASK_ID} status must be complete")

    evidence = task.get("evidence")
    if not isinstance(evidence, list):
        errors.append(f"successor registry work task {WORK_TASK_ID} must expose evidence[]")
        return

    required_evidence_markers = [
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InternalRunsiteOrientationController.cs",
        "/docker/chummercomplete/chummer.run-services/scripts/verify_runsite_orientation_requests.py",
        "/docker/chummercomplete/chummer.run-services/tests/test_runsite_orientation_requests.py",
        "/docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
        "python3 -m unittest tests/test_runsite_orientation_requests.py exits 0.",
    ]
    alternative_evidence_markers = [
        [
            "run_slice_safe_dotnet_test RunsiteOrientationRequestComposerServiceTests executes the repo-local .NET test lane or skips cleanly when the repository slice omits the full run-services project tree.",
            "dotnet test Chummer.Tests/Chummer.Tests.csproj --filter RunsiteOrientationRequestComposerServiceTests --no-restore exits 0.",
        ],
    ]
    evidence_text = "\n".join(str(item) for item in evidence)
    reject_forbidden_markers(evidence_text, f"successor registry work task {WORK_TASK_ID}", errors)
    for marker in required_evidence_markers:
        if marker not in evidence_text:
            errors.append(f"successor registry work task {WORK_TASK_ID} missing evidence marker: {marker}")
    for alternatives in alternative_evidence_markers:
        if not any(marker in evidence_text for marker in alternatives):
            errors.append(
                "successor registry work task "
                f"{WORK_TASK_ID} missing evidence marker: one of {alternatives!r}"
            )


def verify_release_proof(errors: list[str], path: Path, *, label: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    packages_by_id = payload.get("successor_queue_packages_by_id")
    if not isinstance(packages_by_id, dict):
        errors.append(f"{label} must expose successor_queue_packages_by_id: {path}")
        return

    package = packages_by_id.get(PACKAGE_ID)
    if not isinstance(package, dict):
        errors.append(f"{label} missing package {PACKAGE_ID}: {path}")
        return

    for key, expected in LOCAL_RELEASE_PROOF_PACKAGE.items():
        actual = package.get(key)
        if key in {"allowed_paths", "owned_surfaces"}:
            if set(actual or []) != set(expected):
                errors.append(f"{label} {PACKAGE_ID}.{key} must be {expected!r}: {path}")
            continue
        if actual != expected:
            errors.append(f"{label} {PACKAGE_ID}.{key} must be {expected!r}: {path}")

    receipts = payload.get("proof_receipts")
    if not isinstance(receipts, list):
        errors.append(f"{label} must expose proof_receipts[]: {path}")
        return

    receipt_by_id = {
        receipt.get("receipt_id"): receipt
        for receipt in receipts
        if isinstance(receipt, dict) and receipt.get("package_id") == PACKAGE_ID
    }
    for receipt_id, expected in LOCAL_RELEASE_PROOF_RECEIPTS.items():
        receipt = receipt_by_id.get(receipt_id)
        if not isinstance(receipt, dict):
            errors.append(f"{label} missing proof receipt {receipt_id}: {path}")
            continue

        for key in ("package_id", "milestone_id", "frontier_id"):
            if receipt.get(key) != expected[key]:
                errors.append(f"{label} receipt {receipt_id}.{key} must be {expected[key]!r}: {path}")

        if receipt.get("routes") != expected["routes"]:
            errors.append(f"{label} receipt {receipt_id}.routes must stay {expected['routes']!r}: {path}")
        if receipt.get("surfaces") != expected["surfaces"]:
            errors.append(f"{label} receipt {receipt_id}.surfaces must stay {expected['surfaces']!r}: {path}")

        summary = str(receipt.get("summary") or "").casefold()
        for marker in expected["summary_markers"]:
            if marker.casefold() not in summary:
                errors.append(f"{label} receipt {receipt_id} summary missing marker {marker!r}: {path}")


def main() -> int:
    errors: list[str] = []
    verify_source_markers(errors)
    verify_queue_row(errors, FLEET_QUEUE_STAGING_PATH, label="fleet queue")
    verify_queue_row(errors, DESIGN_QUEUE_STAGING_PATH, label="design queue")
    verify_registry_row(errors)
    verify_release_proof(errors, LOCAL_RELEASE_PROOF_PATH, label="repo-local release proof")
    verify_release_proof(errors, SERVED_RELEASE_PROOF_PATH, label="served release proof")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("runsite orientation request proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
