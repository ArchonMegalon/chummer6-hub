#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m143-hub-bind-exchange-and-outward-facing-output-routes-to-visible-receipt-or-bou"
RECEIPT_ID = "bind_exchange_and_outward_facing_output_routes_to_visibl:hub"
TITLE = "Bind exchange and outward-facing output routes to visible receipt or bounded-failure posture instead of silent optimistic claims."
TASK = TITLE
WORK_TASK_ID = "143.3"
MILESTONE_ID = 143
FRONTIER_ID = 4032374688
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = [RECEIPT_ID]
EXPECTED_ROUTES = [
    "/downloads/install/{artifactId}/claim.json",
    "/downloads/install/{artifactId}/continue.json",
    "/api/v1/install-linking/continuation",
    "/api/v1/install-linking/continuation/support",
    "/api/v1/install-linking/continuation/update",
    "/api/v1/install-linking/continuation/rollback",
    "/artifacts/release-bundles/{releaseArtifactId}",
    "/artifacts/release-bundles/{releaseArtifactId}/{format}",
    "/artifacts/publications/{publicationId}",
    "/api/v1/public/artifacts/publications/{publicationId}",
    "/api/public/artifacts/publications/{publicationId}",
    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/federation-batches",
]
EXPECTED_SURFACES = [
    RECEIPT_ID,
    "desktop_native_claim_and_recovery",
    "support_followthrough:install_truth",
    "public_proof_shelf:release_bundles",
    "creator_publication_detail",
    "campaign_federation_exchange",
]
SUMMARY_MARKERS = [
    "visible receipt",
    "bounded-failure posture",
    "silent optimistic claims",
    "output readiness",
]
EVIDENCE_MARKERS = [
    "PublicLandingController.cs binds install recovery exchange, release-bundle proof, and creator-publication detail routes to route receipts or bounded review posture.",
    "InstallLinkingController.cs keeps native claimed-install continuation, support, update, and rollback routes on the same route-receipt or bounded-review contract.",
    "CampaignFederationOrchestrationService.cs keeps federation batches bounded until every outward-facing source pack carries a live publication-shelf receipt.",
    "Views/PublicLanding/PublicCreatorPublication.cshtml surfaces the creator-publication route receipt or bounded review posture directly on the public detail page.",
    "RunServicesSmoke/Program.cs proves native continuation, release-bundle proof, creator-publication detail, and campaign federation routes expose route receipts or bounded review posture instead of silent claims.",
    "verify_next90_m143_hub_exchange_output_receipts.py and tests/test_next90_m143_hub_exchange_output_receipts.py fail closed when exchange/output route proof, queue truth, or release-proof receipts drift.",
]
FORBIDDEN_MARKERS = [
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
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M143_HUB_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_SERVED_RELEASE_PROOF",
        str(ROOT / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
CONTROLLER = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_PUBLIC_LANDING_CONTROLLER",
        str(ROOT / "Chummer.Run.Api/Controllers/PublicLandingController.cs"),
    )
)
INSTALL_LINKING = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_INSTALL_LINKING_CONTROLLER",
        str(ROOT / "Chummer.Run.Api/Controllers/InstallLinkingController.cs"),
    )
)
CAMPAIGN_SPINE = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_CAMPAIGN_SPINE_CONTROLLER",
        str(ROOT / "Chummer.Run.Api/Controllers/CampaignSpineController.cs"),
    )
)
CAMPAIGN_FEDERATION = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_CAMPAIGN_FEDERATION_SERVICE",
        str(ROOT / "Chummer.Run.Api/Services/Community/CampaignFederationOrchestrationService.cs"),
    )
)
SMOKE = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_SMOKE_PROGRAM",
        str(ROOT / "tests/RunServicesSmoke/Program.cs"),
    )
)
MATERIALIZER = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_PROOF_MATERIALIZER",
        str(ROOT / "scripts/materialize_hub_local_release_proof.py"),
    )
)
CREATOR_PUBLICATION_VIEW = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_CREATOR_PUBLICATION_VIEW",
        str(ROOT / "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml"),
    )
)
VERIFY_SCRIPT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M143_HUB_VERIFY_SCRIPT",
        str(ROOT / "scripts/ai/verify.sh"),
    )
)
ROUTE_SOURCE_MARKERS: dict[Path, tuple[str, ...]] = {
    CONTROLLER: (
        '[HttpGet("/downloads/install/{artifactId}/claim.json")]',
        '[HttpGet("/downloads/install/{artifactId}/continue.json")]',
        '[HttpGet("/artifacts/release-bundles/{releaseArtifactId}")]',
        '[HttpGet("/artifacts/release-bundles/{releaseArtifactId}/{format}")]',
        '[HttpGet("/artifacts/publications/{publicationId}")]',
        '[HttpGet("/api/v1/public/artifacts/publications/{publicationId}")]',
        '[HttpGet("/api/public/artifacts/publications/{publicationId}")]',
    ),
    INSTALL_LINKING: (
        'private const string NativeContinuationHref = "/api/v1/install-linking/continuation";',
        'private const string NativeSupportHref = "/api/v1/install-linking/continuation/support";',
        'private const string NativeUpdateHref = "/api/v1/install-linking/continuation/update";',
        'private const string NativeRollbackHref = "/api/v1/install-linking/continuation/rollback";',
    ),
    CAMPAIGN_SPINE: (
        '[HttpPost("me/workspaces/{workspaceId}/federation-batches")]',
    ),
}


def load_queue_payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = load_target_queue_payload(text, path)

    if not isinstance(payload, dict):
        raise TypeError(f"queue payload at {path} is not a YAML mapping")

    return payload


def load_target_queue_payload(text: str, path: Path) -> dict:
    marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(marker)
    if package_index < 0:
        raise SystemExit(f"unable to parse yaml file: {path}")

    start_candidates = [
        text.rfind("\n- title:", 0, package_index),
        text.rfind("\n  - title:", 0, package_index),
    ]
    block_start = max(start_candidates)
    if block_start < 0:
        if text.startswith("- title:") or text.startswith("  - title:"):
            block_start = 0
        else:
            raise SystemExit(f"unable to isolate queue block in {path}")
    else:
        block_start += 1

    end_candidates = [index for index in (text.find("\n- title:", package_index), text.find("\n  - title:", package_index)) if index >= 0]
    block_end = min(end_candidates) if end_candidates else len(text)
    block = text[block_start:block_end].rstrip() + "\n"
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise SystemExit(f"unable to normalize queue staging yaml: {path}")

    return {"items": payload}


def require_contains(path: Path, needle: str, issues: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        issues.append(f"{path.name} is missing required guard: {needle}")


def verify_route_source_markers(issues: list[str]) -> None:
    for path, markers in ROUTE_SOURCE_MARKERS.items():
        for marker in markers:
            require_contains(path, marker, issues)


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} did not contain a JSON object")
    return payload


def find_queue_item(payload: dict) -> dict | None:
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and str(item.get("package_id") or "") == PACKAGE_ID:
            return item
    return None


def verify_queue_item(path: Path, issues: list[str]) -> None:
    payload = load_queue_payload(path)
    item = find_queue_item(payload)
    if item is None:
        issues.append(f"queue staging is missing package row {PACKAGE_ID}: {path}")
        return

    if str(item.get("work_task_id") or "") != WORK_TASK_ID:
        issues.append(f"queue staging work_task_id must be {WORK_TASK_ID!r}: {path}")
    if int(item.get("milestone_id") or -1) != MILESTONE_ID:
        issues.append(f"queue staging milestone_id must be {MILESTONE_ID}: {path}")
    if int(item.get("frontier_id") or -1) != FRONTIER_ID:
        issues.append(f"queue staging frontier_id must be {FRONTIER_ID}: {path}")
    if str(item.get("title") or "") != TITLE:
        issues.append(f"queue staging title drifted for {PACKAGE_ID}: {path}")
    if list(item.get("allowed_paths") or []) != ALLOWED_PATHS:
        issues.append(f"queue staging allowed_paths drifted for {PACKAGE_ID}: {path}")
    if list(item.get("owned_surfaces") or []) != OWNED_SURFACES:
        issues.append(f"queue staging owned_surfaces drifted for {PACKAGE_ID}: {path}")


def verify_registry(path: Path, issues: list[str]) -> None:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        issues.append(f"successor registry is not a YAML mapping: {path}")
        return

    milestones = payload.get("milestones")
    if not isinstance(milestones, list):
        issues.append(f"successor registry milestones block is missing: {path}")
        return

    milestone = next((item for item in milestones if isinstance(item, dict) and int(item.get("id") or -1) == MILESTONE_ID), None)
    if milestone is None:
        issues.append(f"successor registry is missing milestone {MILESTONE_ID}: {path}")
        return

    tasks = milestone.get("work_tasks")
    if not isinstance(tasks, list):
        issues.append(f"successor registry milestone {MILESTONE_ID} is missing work_tasks: {path}")
        return

    task = next((item for item in tasks if isinstance(item, dict) and str(item.get("id") or "") == WORK_TASK_ID), None)
    if task is None:
        issues.append(f"successor registry is missing work task {WORK_TASK_ID}: {path}")
        return

    if str(task.get("owner") or "") != "chummer6-hub":
        issues.append(f"successor registry work task {WORK_TASK_ID} owner drifted: {path}")
    if str(task.get("title") or "") != TITLE:
        issues.append(f"successor registry work task {WORK_TASK_ID} title drifted: {path}")


def verify_proof_receipt(path: Path, issues: list[str], *, compare_to: dict | None = None) -> dict | None:
    payload = load_json(path)
    receipts = payload.get("proof_receipts")
    if not isinstance(receipts, list):
        issues.append(f"{path}: proof_receipts must be a list")
        return None

    matches = [
        receipt
        for receipt in receipts
        if isinstance(receipt, dict)
        and str(receipt.get("package_id") or "") == PACKAGE_ID
        and str(receipt.get("receipt_id") or "") == RECEIPT_ID
    ]
    if len(matches) != 1:
        issues.append(f"{path}: proof_receipts must contain exactly one {PACKAGE_ID}/{RECEIPT_ID} row; found {len(matches)}")
        return None

    receipt = matches[0]
    if int(receipt.get("milestone_id") or -1) != MILESTONE_ID:
        issues.append(f"{path}: {RECEIPT_ID}.milestone_id must be {MILESTONE_ID}")
    if int(receipt.get("frontier_id") or -1) != FRONTIER_ID:
        issues.append(f"{path}: {RECEIPT_ID}.frontier_id must be {FRONTIER_ID}")
    if list(receipt.get("routes") or []) != EXPECTED_ROUTES:
        issues.append(f"{path}: {RECEIPT_ID}.routes drifted")
    if list(receipt.get("surfaces") or []) != EXPECTED_SURFACES:
        issues.append(f"{path}: {RECEIPT_ID}.surfaces drifted")

    summary = str(receipt.get("summary") or "")
    for marker in SUMMARY_MARKERS:
        if marker not in summary:
            issues.append(f"{path}: {RECEIPT_ID}.summary missing marker {marker!r}")

    evidence = receipt.get("evidence")
    if not isinstance(evidence, list):
        issues.append(f"{path}: {RECEIPT_ID}.evidence must be a list")
    else:
        evidence_text = "\n".join(str(item) for item in evidence)
        for marker in EVIDENCE_MARKERS:
            if marker not in evidence_text:
                issues.append(f"{path}: {RECEIPT_ID}.evidence missing marker {marker!r}")
        lowered = evidence_text.casefold()
        for marker in FORBIDDEN_MARKERS:
            if marker.casefold() in lowered:
                issues.append(f"{path}: {RECEIPT_ID}.evidence contains forbidden marker {marker!r}")

    if compare_to is not None and receipt != compare_to:
        issues.append(f"{path}: {RECEIPT_ID} must match the repo-local proof receipt exactly")

    return receipt


def main() -> int:
    issues: list[str] = []

    verify_queue_item(QUEUE_STAGING_PATH, issues)
    verify_registry(SUCCESSOR_REGISTRY_PATH, issues)
    verify_route_source_markers(issues)

    local_receipt = verify_proof_receipt(LOCAL_RELEASE_PROOF_PATH, issues)
    verify_proof_receipt(SERVED_RELEASE_PROOF_PATH, issues, compare_to=local_receipt)

    require_contains(
        CONTROLLER,
        'status = routeClaim.State,',
        issues,
    )
    require_contains(
        CONTROLLER,
        'state = routeClaim.State,',
        issues,
    )
    require_contains(
        CONTROLLER,
        'routeReceipt = BuildRouteReceiptPayload(routeLookup.ReceiptMatch),',
        issues,
    )
    require_contains(
        CONTROLLER,
        'missingReceiptReason: "No current local release-proof receipt is attached to this install recovery exchange route for the requested artifact."',
        issues,
    )
    require_contains(
        CONTROLLER,
        'missingReceiptReason: "No current local release-proof receipt is attached to the public creator-publication detail route."',
        issues,
    )
    require_contains(
        CONTROLLER,
        "RouteState: routeClaim.State",
        issues,
    )
    require_contains(
        CONTROLLER,
        "RouteReceipt: BuildRouteReceiptPayload(routeLookup.ReceiptMatch)",
        issues,
    )
    require_contains(
        CONTROLLER,
        '"public-shelf:/artifacts/publications/{publicationId}"',
        issues,
    )
    require_contains(
        CONTROLLER,
        'missingReceiptReason: "No current local release-proof receipt is attached to this release-bundle route or format."',
        issues,
    )
    require_contains(
        INSTALL_LINKING,
        "BuildNativeRouteProofStatus(",
        issues,
    )
    require_contains(
        INSTALL_LINKING,
        "routeLookup.CurrentnessFailureReason",
        issues,
    )
    require_contains(
        INSTALL_LINKING,
        'RouteState: nativeRouteProof.State',
        issues,
    )
    require_contains(
        INSTALL_LINKING,
        'RouteReceipt: nativeRouteProof.RouteReceipt',
        issues,
    )
    require_contains(
        INSTALL_LINKING,
        'BoundedFailureReason: nativeRouteProof.BoundedFailureReason',
        issues,
    )
    require_contains(
        INSTALL_LINKING,
        'Current direct route receipt is attached, but parity claims stay review-required because',
        issues,
    )
    require_contains(
        INSTALL_LINKING,
        'readiness?.MissingDesktopClientCoverage == true',
        issues,
    )
    require_contains(
        INSTALL_LINKING,
        '!importRouteGuard.IsCurrent',
        issues,
    )
    require_contains(
        CAMPAIGN_FEDERATION,
        'string routeState = allSourcePacksPublished ? "queued" : "bounded_failure";',
        issues,
    )
    require_contains(
        CAMPAIGN_FEDERATION,
        'RouteState: routeState,',
        issues,
    )
    require_contains(
        CAMPAIGN_FEDERATION,
        'RouteReceipt: null,',
        issues,
    )
    require_contains(
        CAMPAIGN_FEDERATION,
        'BoundedFailureReason: boundedFailureReason,',
        issues,
    )
    require_contains(
        CAMPAIGN_FEDERATION,
        'One or more governed source packs are not published on the outward-facing shelf yet, so this exchange batch stays bounded until visible source receipts are live.',
        issues,
    )
    require_contains(
        SMOKE,
        'native claimed-install continuation api should expose the governing route receipt or bounded review posture.',
        issues,
    )
    require_contains(
        SMOKE,
        'release-bundle public proof route should expose the governing proof receipt or bounded review posture.',
        issues,
    )
    require_contains(
        SMOKE,
        'creator publication detail api should expose the governing route receipt or bounded review posture.',
        issues,
    )
    require_contains(
        SMOKE,
        'guest creator-publication detail should expose the governing route receipt or bounded review posture on the HTML route.',
        issues,
    )
    require_contains(
        CREATOR_PUBLICATION_VIEW,
        'var routeStateLabel = HumanizeStatus(Model.RouteState, "Bounded failure");',
        issues,
    )
    require_contains(
        CREATOR_PUBLICATION_VIEW,
        'Receipt @Model.RouteReceipt.ReceiptId via @Model.RouteReceipt.MatchedRoute',
        issues,
    )
    require_contains(
        CREATOR_PUBLICATION_VIEW,
        'This publication stays bounded until a current outward-facing receipt is attached.',
        issues,
    )
    require_contains(
        SMOKE,
        'campaign federation api should surface batch route posture instead of optimistic launch claims when source-pack receipts are not all live.',
        issues,
    )
    require_contains(
        SMOKE,
        'campaign federation api should keep unpublished replay source packs on bounded-failure posture until a public shelf receipt exists.',
        issues,
    )
    require_contains(
        CAMPAIGN_FEDERATION,
        'ReceiptId: $"public-shelf:{publicShelfRef}",',
        issues,
    )
    require_contains(
        CAMPAIGN_FEDERATION,
        'stays {moderationState.Replace(\'_\', \' \')} until outward-facing publication review promotes a live shelf receipt.',
        issues,
    )
    require_contains(
        MATERIALIZER,
        f'"receipt_id": "{RECEIPT_ID}"',
        issues,
    )
    require_contains(
        MATERIALIZER,
        f'"package_id": "{PACKAGE_ID}"',
        issues,
    )
    require_contains(
        VERIFY_SCRIPT,
        "python3 scripts/verify_next90_m143_hub_exchange_output_receipts.py",
        issues,
    )
    require_contains(
        VERIFY_SCRIPT,
        "python3 -m unittest tests/test_next90_m143_hub_exchange_output_receipts.py",
        issues,
    )

    if issues:
        print("next90 m143 hub exchange/output receipt verifier failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    print("next90 m143 hub exchange/output receipt proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
