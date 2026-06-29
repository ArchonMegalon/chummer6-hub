#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml


PACKAGE_ID = "next90-m144-hub-keep-public-and-signed-in-shelf-bytes-proof-routes-and-release-truth-ali"
WORK_TASK_ID = "144.3"
MILESTONE_ID = 144
PACKAGE_TITLE = "Keep public and signed-in shelf bytes, proof routes, and release truth aligned with the same promoted tuple receipts."
PACKAGE_TASK = PACKAGE_TITLE
EXPECTED_REPO = "chummer6-hub"
EXPECTED_ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
EXPECTED_OWNED_SURFACES = ["keep_public_and_signed_in_shelf_bytes_proof_routes_and_r:hub"]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M144_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M144_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M144_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M144_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M144_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M144_SERVED_RELEASE_PROOF",
        str(ROOT / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
RELEASE_CHANNEL_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M144_RELEASE_CHANNEL",
        str(ROOT / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"),
    )
)
STARTUP_SMOKE_ROOT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M144_STARTUP_SMOKE_ROOT",
        str(ROOT / "Chummer.Portal/downloads/startup-smoke"),
    )
)

SOURCE_MARKERS = {
    "Chummer.Run.Api/Services/PublicReleaseManifestService.cs": [
        'DesktopTupleCoverage = parsed.DesktopTupleCoverage is JsonElement desktopTupleCoverage',
        'string tupleId = $"{artifact.Head}:{artifact.Platform}:{artifact.Rid}";',
        'return "required desktop tuple coverage is unavailable";',
        '? "required desktop tuple coverage is complete"',
    ],
    "Chummer.Run.Api/Services/SignedInTrustStatusService.cs": [
        '"Current linked build",',
        '"Who can get it now",',
        'new("Release proof", BuildReleaseProofSummary(manifest)),',
        "Downloads, support, and recovery are all using the same claimed install context right now.",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'Assert(authenticatedHorizonsModel?.SignedInStatus is not null, "authenticated horizons page should project the shared signed-in trust status.");',
        'Assert(publicArtifactsModel?.SignedInCreatorPublications?.All(static item => item.Discoverable && string.Equals(item.PublicationStatus, "published", StringComparison.OrdinalIgnoreCase)) == true, "public artifact view should keep only discoverable published creator-publication cards on the signed-in public rail.");',
        'Assert(publicArtifactsModel?.SignedInRecapShelf?.Count == 0, "public artifact view should not blend private recap artifacts into the signed-in public publication rail.");',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m144_hub_release_truth_alignment.py",
        "python3 -m unittest tests/test_next90_m144_hub_release_truth_alignment.py",
    ],
}


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def load_yaml_with_optional_preamble(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        if f"package_id: {PACKAGE_ID}" not in text:
            raise
        payload = load_target_queue_payload(text, path)

    if not isinstance(payload, dict):
        raise SystemExit(f"yaml payload at {path} is not a mapping")

    return payload


def load_target_queue_payload(text: str, path: Path) -> dict[str, Any]:
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


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing json file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid json file at {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SystemExit(f"json payload at {path} is not an object")

    return payload


def stable_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: stable_json(subvalue)
            for key, subvalue in value.items()
            if key not in {"generated_at", "generatedAt"}
        }
    if isinstance(value, list):
        return [stable_json(item) for item in value]
    return value


def normalize(value: Any) -> str:
    return str(value or "").strip()


def find_queue_item(payload: dict[str, Any], *, path: Path) -> dict[str, Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise SystemExit(f"queue payload at {path} is missing items[]")

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        raise SystemExit(f"queue payload at {path} must contain exactly one {PACKAGE_ID} row")

    return matches[0]


def assert_equal(actual: Any, expected: Any, message: str, errors: list[str]) -> None:
    if actual != expected:
        errors.append(f"{message}: expected {expected!r}, got {actual!r}")


def verify_queue_and_registry(errors: list[str]) -> None:
    fleet_queue = load_yaml_with_optional_preamble(FLEET_QUEUE_STAGING_PATH)
    design_queue = load_yaml_with_optional_preamble(DESIGN_QUEUE_STAGING_PATH)
    fleet_item = find_queue_item(fleet_queue, path=FLEET_QUEUE_STAGING_PATH)
    design_item = find_queue_item(design_queue, path=DESIGN_QUEUE_STAGING_PATH)

    comparable_keys = [
        "title",
        "task",
        "package_id",
        "milestone_id",
        "repo",
        "allowed_paths",
        "owned_surfaces",
        "frontier_id",
    ]
    for key in comparable_keys:
        if fleet_item.get(key) != design_item.get(key):
            errors.append(f"fleet and design queue rows differ for {key}")

    assert_equal(fleet_item.get("title"), PACKAGE_TITLE, "queue title drifted", errors)
    assert_equal(fleet_item.get("task"), PACKAGE_TASK, "queue task drifted", errors)
    assert_equal(fleet_item.get("milestone_id"), MILESTONE_ID, "queue milestone_id drifted", errors)
    assert_equal(fleet_item.get("repo"), EXPECTED_REPO, "queue repo drifted", errors)
    assert_equal(fleet_item.get("allowed_paths"), EXPECTED_ALLOWED_PATHS, "queue allowed_paths drifted", errors)
    assert_equal(fleet_item.get("owned_surfaces"), EXPECTED_OWNED_SURFACES, "queue owned_surfaces drifted", errors)

    registry = load_yaml_with_optional_preamble(SUCCESSOR_REGISTRY_PATH)
    milestones = registry.get("milestones")
    if not isinstance(milestones, list):
        errors.append(f"successor registry at {SUCCESSOR_REGISTRY_PATH} is missing milestones[]")
        return

    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if milestone is None:
        errors.append(f"successor registry missing milestone {MILESTONE_ID}")
        return

    if normalize(milestone.get("title")) != "Desktop executable release integrity and publishable flagship-route closure":
        errors.append("milestone 144 title drifted")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        errors.append("milestone 144 is missing work_tasks[]")
        return

    work_task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == WORK_TASK_ID), None)
    if work_task is None:
        errors.append("milestone 144 is missing work task 144.3")
        return

    assert_equal(work_task.get("owner"), EXPECTED_REPO, "work task 144.3 owner drifted", errors)
    assert_equal(work_task.get("title"), PACKAGE_TITLE, "work task 144.3 title drifted", errors)


def verify_local_and_served_proof(errors: list[str]) -> None:
    local_payload = load_json(LOCAL_RELEASE_PROOF_PATH)
    served_payload = load_json(SERVED_RELEASE_PROOF_PATH)

    if stable_json(local_payload) != stable_json(served_payload):
        errors.append("local and served HUB_LOCAL_RELEASE_PROOF payloads drifted")

    proof_routes = local_payload.get("proof_routes")
    if not isinstance(proof_routes, list):
        errors.append("local release proof is missing proof_routes[]")
        return

    public_surface = local_payload.get("publicTrustSurface")
    if not isinstance(public_surface, dict):
        errors.append("local release proof is missing publicTrustSurface")
        return

    expected_public_routes = {
        "statusRoute": "/status",
        "currentReleaseRoute": "/now",
        "downloadsRoute": "/downloads",
        "proofShelfRoute": "/artifacts",
    }
    for key, expected in expected_public_routes.items():
        if public_surface.get(key) != expected:
            errors.append(f"publicTrustSurface {key} drifted")

    summary = normalize(public_surface.get("summary"))
    if "governor-visible trust surface bundle" not in summary:
        errors.append("publicTrustSurface summary no longer describes the shared trust surface bundle")

    proof_receipts = local_payload.get("proof_receipts")
    if not isinstance(proof_receipts, list):
        errors.append("local release proof is missing proof_receipts[]")
        return

    receipt_ids = [normalize(item.get("receipt_id")) for item in proof_receipts if isinstance(item, dict)]
    for required_receipt_id in ("artifact_shelf:v2", "public_trust_surface:v3", "launch_health:public"):
        if receipt_ids.count(required_receipt_id) != 1:
            errors.append(f"receipt id {required_receipt_id} must appear exactly once in proof_receipts")

    release_bundle_receipts = [
        item
        for item in proof_receipts
        if isinstance(item, dict) and normalize(item.get("receipt_id")) == "public_proof_shelf:release_bundles"
    ]
    if len(release_bundle_receipts) != 1:
        errors.append("receipt id public_proof_shelf:release_bundles must appear exactly once in proof_receipts")
    else:
        release_bundle_routes = {
            normalize(route)
            for route in release_bundle_receipts[0].get("routes", [])
            if normalize(route)
        }
        for required_route in (
            "/downloads/install/avalonia-linux-x64-installer",
            "/downloads/install/avalonia-win-x64-installer",
        ):
            if required_route not in release_bundle_routes:
                errors.append(f"public_proof_shelf:release_bundles receipt missing required route {required_route}")

    route_set = {normalize(route) for route in proof_routes}
    for required_route in ("/downloads", "/downloads/install/avalonia-win-x64-installer"):
        if required_route not in route_set:
            errors.append(f"proof_routes missing required route {required_route}")

    if public_surface.get("proofShelfRoute") != "/artifacts":
        errors.append("publicTrustSurface proofShelfRoute drifted away from /artifacts")
    if public_surface.get("statusRoute") != "/status":
        errors.append("publicTrustSurface statusRoute drifted away from /status")


def verify_release_channel_alignment(errors: list[str]) -> None:
    payload = load_json(RELEASE_CHANNEL_PATH)

    coverage = payload.get("desktopTupleCoverage")
    if not isinstance(coverage, dict):
        errors.append("release channel is missing desktopTupleCoverage")
        return

    route_truth = coverage.get("desktopRouteTruth")
    if not isinstance(route_truth, list) or not route_truth:
        errors.append("desktopTupleCoverage.desktopRouteTruth must contain tuple route truth")
        return

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("release channel is missing artifacts[]")
        return

    artifact_by_id = {
        normalize(item.get("artifactId") or item.get("id")): item
        for item in artifacts
        if isinstance(item, dict) and normalize(item.get("artifactId") or item.get("id"))
    }
    identity_registry = payload.get("artifactIdentityRegistry")
    install_registry = payload.get("installAwareArtifactRegistry")
    if not isinstance(identity_registry, list):
        errors.append("release channel is missing artifactIdentityRegistry[]")
        return
    if not isinstance(install_registry, list):
        errors.append("release channel is missing installAwareArtifactRegistry[]")
        return

    if not identity_registry:
        errors.append("artifactIdentityRegistry must contain tuple rows")
    if not install_registry:
        errors.append("installAwareArtifactRegistry must contain tuple rows")

    identity_by_tuple = {
        normalize(item.get("tupleId")): item
        for item in identity_registry
        if isinstance(item, dict) and normalize(item.get("tupleId"))
    }
    install_by_tuple = {
        normalize(item.get("tupleId")): item
        for item in install_registry
        if isinstance(item, dict) and normalize(item.get("tupleId"))
    }

    route_truth_by_tuple = {
        normalize(route_entry.get("tupleId")): route_entry
        for route_entry in route_truth
        if isinstance(route_entry, dict) and normalize(route_entry.get("tupleId"))
    }

    for entry in identity_registry:
        if not isinstance(entry, dict):
            errors.append("artifactIdentityRegistry contains a non-object row")
            continue
        tuple_id = normalize(entry.get("tupleId"))
        if not tuple_id:
            errors.append("artifactIdentityRegistry contains row without tupleId")
            continue
        route_entry = route_truth_by_tuple.get(tuple_id)
        if route_entry is None:
            errors.append(f"artifactIdentityRegistry tuple {tuple_id} has no matching desktopRouteTruth row")
            continue
        if normalize(entry.get("publicInstallRoute")) != normalize(route_entry.get("publicInstallRoute")):
            errors.append(f"artifactIdentityRegistry tuple {tuple_id} drifted from desktopRouteTruth publicInstallRoute")
        if not normalize(entry.get("signedInShelfRef")).startswith("shelf:signed-in:"):
            errors.append(f"artifactIdentityRegistry tuple {tuple_id} is missing signedInShelfRef")
        if not normalize(entry.get("publicShelfRef")).startswith("shelf:public:"):
            errors.append(f"artifactIdentityRegistry tuple {tuple_id} is missing publicShelfRef")

    for entry in install_registry:
        if not isinstance(entry, dict):
            errors.append("installAwareArtifactRegistry contains a non-object row")
            continue
        tuple_id = normalize(entry.get("tupleId"))
        if not tuple_id:
            errors.append("installAwareArtifactRegistry contains row without tupleId")
            continue
        route_entry = route_truth_by_tuple.get(tuple_id)
        if route_entry is None:
            errors.append(f"installAwareArtifactRegistry tuple {tuple_id} has no matching desktopRouteTruth row")
            continue
        recovery_refs = entry.get("recoveryProofRefs")
        if not isinstance(recovery_refs, list):
            errors.append(f"installAwareArtifactRegistry tuple {tuple_id} is missing recoveryProofRefs[]")
            continue

        marker = f"desktopTupleCoverage.desktopRouteTruth[{tuple_id}]"
        public_install_route = normalize(route_entry.get("publicInstallRoute"))
        if public_install_route not in {normalize(ref) for ref in recovery_refs}:
            errors.append(f"installAwareArtifactRegistry tuple {tuple_id} recoveryProofRefs missing {public_install_route}")
        if marker not in {normalize(ref) for ref in recovery_refs}:
            errors.append(f"installAwareArtifactRegistry tuple {tuple_id} recoveryProofRefs missing {marker}")

    missing_tuple_receipts = {
        normalize(item)
        for item in coverage.get("missingRequiredPlatformHeadRidTuples", [])
        if normalize(item)
    }

    for route_entry in route_truth:
        if not isinstance(route_entry, dict):
            continue

        tuple_id = normalize(route_entry.get("tupleId"))
        public_install_route = normalize(route_entry.get("publicInstallRoute"))
        artifact_id = normalize(route_entry.get("artifactId"))
        promotion_state = normalize(route_entry.get("promotionState"))
        install_posture = normalize(route_entry.get("installPosture"))
        if not artifact_id and (promotion_state == "proof_required" or install_posture == "proof_capture_required"):
            # Fallback lanes are still route-truth rows, but they do not get
            # artifact identity/install registry rows until artifact bytes and
            # startup verification exists for that fallback tuple.
            continue

        if not tuple_id:
            errors.append("desktopRouteTruth entry is missing tupleId")
            continue
        if not public_install_route.startswith("/downloads/install/"):
            errors.append(f"desktopRouteTruth[{tuple_id}] has invalid publicInstallRoute {public_install_route!r}")

        identity = identity_by_tuple.get(tuple_id)
        if identity is None:
            errors.append(f"artifactIdentityRegistry is missing tuple {tuple_id}")
        else:
            if normalize(identity.get("publicInstallRoute")) != public_install_route:
                errors.append(f"artifactIdentityRegistry tuple {tuple_id} drifted from desktopRouteTruth publicInstallRoute")
            if not normalize(identity.get("signedInShelfRef")).startswith("shelf:signed-in:"):
                errors.append(f"artifactIdentityRegistry tuple {tuple_id} is missing signedInShelfRef")
            if not normalize(identity.get("publicShelfRef")).startswith("shelf:public:"):
                errors.append(f"artifactIdentityRegistry tuple {tuple_id} is missing publicShelfRef")

        install_entry = install_by_tuple.get(tuple_id)
        if install_entry is None:
            errors.append(f"installAwareArtifactRegistry is missing tuple {tuple_id}")
        else:
            recovery_refs = install_entry.get("recoveryProofRefs")
            if not isinstance(recovery_refs, list):
                errors.append(f"installAwareArtifactRegistry tuple {tuple_id} is missing recoveryProofRefs[]")
            else:
                marker = f"desktopTupleCoverage.desktopRouteTruth[{tuple_id}]"
                if public_install_route not in recovery_refs:
                    errors.append(f"installAwareArtifactRegistry tuple {tuple_id} recoveryProofRefs missing {public_install_route}")
                if marker not in recovery_refs:
                    errors.append(f"installAwareArtifactRegistry tuple {tuple_id} recoveryProofRefs missing {marker}")

        artifact = artifact_by_id.get(artifact_id)
        if not artifact_id:
            if promotion_state == "proof_required" or install_posture == "proof_capture_required":
                continue
            errors.append(f"desktopRouteTruth[{tuple_id}] is missing artifactId")
            continue
        if artifact is None:
            errors.append(f"desktopRouteTruth[{tuple_id}] references unknown artifact {artifact_id!r}")
            continue

        receipt_path = STARTUP_SMOKE_ROOT / f"startup-smoke-{normalize(route_entry.get('head'))}-{normalize(route_entry.get('rid'))}.receipt.json"
        if not receipt_path.is_file():
            continue

        receipt = load_json(receipt_path)
        release_sha = normalize(
            artifact.get("sha256") or artifact.get("artifactSha256") or artifact.get("artifactDigest")
        ).removeprefix("sha256:")
        receipt_sha = normalize(receipt.get("artifactSha256") or receipt.get("artifactDigest") or receipt.get("artifactDigest")).removeprefix("sha256:")
        if receipt_sha and release_sha and release_sha != receipt_sha:
            supportability_state = normalize(payload.get("supportabilityState"))
            rollout_state = normalize(payload.get("rolloutState"))
            message = normalize(payload.get("message"))
            if supportability_state != "review_required":
                errors.append(f"release channel must stay review_required when tuple {tuple_id} startup-smoke digest drifts")
            if rollout_state != "coverage_incomplete":
                errors.append(f"release channel must stay coverage_incomplete when tuple {tuple_id} startup-smoke digest drifts")
            if "startup verification" not in message.lower():
                errors.append(f"release channel message must mention startup verification when tuple {tuple_id} digest drifts")


def verify_source_markers(errors: list[str]) -> None:
    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative_path} is missing required marker: {marker}")


def main() -> int:
    errors: list[str] = []
    verify_queue_and_registry(errors)
    verify_local_and_served_proof(errors)
    verify_release_channel_alignment(errors)
    verify_source_markers(errors)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("next90 m144 hub release truth alignment proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
