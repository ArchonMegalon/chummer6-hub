#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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

CANONICAL_PROOF_MAX_AGE_SECONDS = 7 * 24 * 3600
CANONICAL_PROOF_FRESHNESS_STATUSES = {"fresh", "stale", "missing"}

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


def normalized_token(value: Any) -> str:
    return normalize(value).lower()


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_utc_timestamp(value: Any) -> Optional[datetime]:
    raw = normalize(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def projection_age_seconds(projection_generated_at: datetime, evidence_generated_at: datetime) -> int:
    return int((projection_generated_at - evidence_generated_at).total_seconds())


def exact_non_negative_int(
    payload: dict[str, Any],
    key: str,
    *,
    errors: list[str],
) -> Optional[int]:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"publicTrustMetrics.proofFreshness.{key} must be a non-negative integer")
        return None
    return value


def verify_unique_tuple_ids(
    rows: list[Any],
    *,
    label: str,
    errors: list[str],
) -> bool:
    valid = True
    first_index_by_tuple: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{label}[{index}] must be an object before tuple aggregation")
            valid = False
            continue
        tuple_id = normalize(row.get("tupleId"))
        if not tuple_id:
            errors.append(f"{label}[{index}] is missing tupleId before tuple aggregation")
            valid = False
            continue
        first_index = first_index_by_tuple.get(tuple_id)
        if first_index is not None:
            errors.append(
                f"{label} contains duplicate tupleId {tuple_id!r} at indexes "
                f"{first_index} and {index}"
            )
            valid = False
            continue
        first_index_by_tuple[tuple_id] = index
    return valid


def derive_proof_freshness_status(
    payload: dict[str, Any],
    proof_freshness: dict[str, Any],
    errors: list[str],
) -> str:
    """Derive freshness from authority-bound evidence; metrics.status is assertion-only."""

    declared_status = normalized_token(proof_freshness.get("status"))
    if not declared_status:
        errors.append("publicTrustMetrics.proofFreshness.status is missing")
    elif declared_status not in CANONICAL_PROOF_FRESHNESS_STATUSES:
        errors.append("publicTrustMetrics.proofFreshness.status is not canonical")

    projection_generated_at = parse_utc_timestamp(
        payload.get("generatedAt") or payload.get("generated_at")
    )
    if projection_generated_at is None:
        errors.append("release channel generatedAt is missing or is not an offset-aware ISO-8601 timestamp")

    release_proof = payload.get("releaseProof")
    if not isinstance(release_proof, dict):
        errors.append("release channel is missing releaseProof for independent freshness derivation")
        release_proof = {}
    ui_localization = release_proof.get("uiLocalizationReleaseGate")
    if not isinstance(ui_localization, dict):
        errors.append("releaseProof is missing uiLocalizationReleaseGate for independent freshness derivation")
        ui_localization = {}
    flagship_readiness = release_proof.get("flagshipReadiness")
    if not isinstance(flagship_readiness, dict):
        errors.append("releaseProof is missing flagshipReadiness for independent freshness derivation")
        flagship_readiness = {}

    evidence_fields = (
        (
            "releaseProof",
            release_proof.get("generatedAt") or release_proof.get("generated_at"),
            "releaseProofGeneratedAt",
            "releaseProofAgeSeconds",
            "releaseProofMaxAgeSeconds",
        ),
        (
            "releaseProof.uiLocalizationReleaseGate",
            ui_localization.get("generatedAt") or ui_localization.get("generated_at"),
            "uiLocalizationGeneratedAt",
            "uiLocalizationAgeSeconds",
            "uiLocalizationMaxAgeSeconds",
        ),
        (
            "releaseProof.flagshipReadiness",
            flagship_readiness.get("generatedAt") or flagship_readiness.get("generated_at"),
            "flagshipReadinessGeneratedAt",
            "flagshipReadinessAgeSeconds",
            "flagshipReadinessMaxAgeSeconds",
        ),
    )

    derived_ages: list[int] = []
    evidence_missing = projection_generated_at is None
    for source_path, source_timestamp_value, timestamp_key, age_key, max_age_key in evidence_fields:
        source_timestamp = parse_utc_timestamp(source_timestamp_value)
        projected_timestamp = parse_utc_timestamp(proof_freshness.get(timestamp_key))
        if source_timestamp is None:
            errors.append(f"{source_path}.generatedAt is missing or invalid")
            evidence_missing = True
        if projected_timestamp is None:
            errors.append(
                f"publicTrustMetrics.proofFreshness.{timestamp_key} is missing or invalid"
            )
        elif source_timestamp is not None and projected_timestamp != source_timestamp:
            errors.append(
                f"publicTrustMetrics.proofFreshness.{timestamp_key} drifted from canonical "
                f"{source_path}.generatedAt"
            )

        declared_age = exact_non_negative_int(proof_freshness, age_key, errors=errors)
        declared_max_age = exact_non_negative_int(proof_freshness, max_age_key, errors=errors)
        if declared_max_age is not None and declared_max_age != CANONICAL_PROOF_MAX_AGE_SECONDS:
            errors.append(
                f"publicTrustMetrics.proofFreshness.{max_age_key} must equal canonical "
                f"{CANONICAL_PROOF_MAX_AGE_SECONDS}"
            )

        if projection_generated_at is None or source_timestamp is None:
            continue
        if source_timestamp > projection_generated_at:
            errors.append(
                f"{source_path}.generatedAt must not be later than release channel generatedAt"
            )
            evidence_missing = True
            continue
        derived_age = projection_age_seconds(projection_generated_at, source_timestamp)
        derived_ages.append(derived_age)
        if declared_age is not None and declared_age != derived_age:
            errors.append(
                f"publicTrustMetrics.proofFreshness.{age_key} is inconsistent with canonical timestamps: "
                f"expected {derived_age}, got {declared_age}"
            )

    embedded_desktop_ready = flagship_readiness.get("desktopClientReady")
    if flagship_readiness and not isinstance(embedded_desktop_ready, bool):
        errors.append("releaseProof.flagshipReadiness.desktopClientReady must be boolean")
    projected_desktop_ready = proof_freshness.get("flagshipDesktopClientReady")
    if not isinstance(projected_desktop_ready, bool):
        errors.append("publicTrustMetrics.proofFreshness.flagshipDesktopClientReady must be boolean")
    elif isinstance(embedded_desktop_ready, bool) and projected_desktop_ready != embedded_desktop_ready:
        errors.append(
            "publicTrustMetrics.proofFreshness.flagshipDesktopClientReady drifted from "
            "releaseProof.flagshipReadiness.desktopClientReady"
        )

    embedded_readiness_status = normalized_token(flagship_readiness.get("status"))
    projected_readiness_status = normalized_token(proof_freshness.get("flagshipReadinessStatus"))
    if not projected_readiness_status:
        errors.append("publicTrustMetrics.proofFreshness.flagshipReadinessStatus is missing")
    elif embedded_readiness_status and projected_readiness_status != embedded_readiness_status:
        errors.append(
            "publicTrustMetrics.proofFreshness.flagshipReadinessStatus drifted from "
            "releaseProof.flagshipReadiness.status"
        )

    if evidence_missing or len(derived_ages) != len(evidence_fields):
        derived_status = "missing"
    elif any(age > CANONICAL_PROOF_MAX_AGE_SECONDS for age in derived_ages):
        derived_status = "stale"
    elif embedded_desktop_ready is not True:
        derived_status = "stale"
    else:
        derived_status = "fresh"

    if declared_status in CANONICAL_PROOF_FRESHNESS_STATUSES and declared_status != derived_status:
        errors.append(
            "publicTrustMetrics.proofFreshness.status is inconsistent with canonical "
            f"timestamps, age budgets, and flagship readiness: expected {derived_status!r}, "
            f"got {declared_status!r}"
        )
    return derived_status


def route_truth_is_revoked(row: dict[str, Any]) -> bool:
    return normalized_token(row.get("revokeState")) == "revoked" or normalized_token(row.get("promotionState")) == "revoked"


def route_truth_is_recommended_primary(row: dict[str, Any]) -> bool:
    return (
        normalized_token(row.get("routeRole")) == "primary"
        and normalized_token(row.get("promotionState")) == "promoted"
        and not route_truth_is_revoked(row)
    )


def route_truth_is_fallback_recovery(row: dict[str, Any]) -> bool:
    return (
        normalized_token(row.get("routeRole")) == "fallback"
        and normalized_token(row.get("promotionState")) == "promoted"
        and not route_truth_is_revoked(row)
    )


def route_truth_is_blocked(row: dict[str, Any]) -> bool:
    return (
        normalized_token(row.get("promotionState")) == "proof_required"
        and not route_truth_is_revoked(row)
        and not (
            normalized_token(row.get("routeRole")) == "fallback"
            and normalized_token(row.get("parityPosture")) == "explicit_fallback"
        )
    )


def output_readiness_publication_state(
    publication_state: str,
    *,
    proof_freshness_status: str,
) -> str:
    normalized_state = normalized_token(publication_state)
    if (
        normalized_token(proof_freshness_status) in {"stale", "missing"}
        and normalized_state in {"published", "retained"}
    ):
        return "preview"
    return normalized_state


def route_truth_publication_state(
    row: dict[str, Any],
    *,
    proof_freshness_status: str,
) -> str:
    explicit_state = normalized_token(row.get("publicationState") or row.get("publication_state"))
    if explicit_state in {"preview", "published", "revoked", "retained"}:
        return output_readiness_publication_state(
            explicit_state,
            proof_freshness_status=proof_freshness_status,
        )
    if normalized_token(row.get("revokeState")) == "revoked":
        return "revoked"
    if normalized_token(row.get("promotionState")) == "promoted":
        return output_readiness_publication_state(
            "published",
            proof_freshness_status=proof_freshness_status,
        )
    if normalized_token(row.get("routeRole")) == "fallback":
        return output_readiness_publication_state(
            "retained",
            proof_freshness_status=proof_freshness_status,
        )
    return "preview"


def summary_requires(summary: str, marker: str, errors: list[str], label: str) -> None:
    if marker not in normalize(summary):
        errors.append(f"{label} summary is missing {marker!r}")


def verify_public_trust_metrics(
    payload: dict[str, Any],
    route_truth: list[Any],
    artifact_by_id: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    if not verify_unique_tuple_ids(
        route_truth,
        label="desktopTupleCoverage.desktopRouteTruth",
        errors=errors,
    ):
        return

    metrics = payload.get("publicTrustMetrics")
    if not isinstance(metrics, dict):
        errors.append("release channel is missing publicTrustMetrics")
        return

    release_channel = metrics.get("releaseChannel")
    adoption_health = metrics.get("adoptionHealth")
    proof_freshness = metrics.get("proofFreshness")
    revocation_facts = metrics.get("revocationFacts")
    if not isinstance(release_channel, dict):
        errors.append("publicTrustMetrics is missing releaseChannel")
        return
    if not isinstance(adoption_health, dict):
        errors.append("publicTrustMetrics is missing adoptionHealth")
        return
    if not isinstance(proof_freshness, dict):
        errors.append("publicTrustMetrics is missing proofFreshness")
        return
    if not isinstance(revocation_facts, dict):
        errors.append("publicTrustMetrics is missing revocationFacts")
        return

    proof_freshness_status = derive_proof_freshness_status(payload, proof_freshness, errors)
    promoted_primary_routes = [row for row in route_truth if route_truth_is_recommended_primary(row)]
    promoted_fallback_routes = [row for row in route_truth if route_truth_is_fallback_recovery(row)]
    recommended_routes = [
        row
        for row in promoted_primary_routes
        if route_truth_publication_state(
            row,
            proof_freshness_status=proof_freshness_status,
        )
        == "published"
    ]
    fallback_routes = [
        row
        for row in promoted_fallback_routes
        if route_truth_publication_state(
            row,
            proof_freshness_status=proof_freshness_status,
        )
        == "retained"
    ]
    blocked_routes = [row for row in route_truth if route_truth_is_blocked(row)]
    for row in [*promoted_primary_routes, *promoted_fallback_routes]:
        if row not in recommended_routes and row not in fallback_routes:
            blocked_routes.append(row)
    revoked_routes = [row for row in route_truth if route_truth_is_revoked(row)]

    expected_primary = len(recommended_routes)
    expected_fallback = len(fallback_routes)
    expected_blocked = len(blocked_routes)
    expected_revoked = len(revoked_routes)

    public_install_count = 0
    account_linked_install_count = 0
    for row in recommended_routes:
        artifact_id = normalize(row.get("artifactId"))
        artifact = artifact_by_id.get(artifact_id)
        install_access_class = normalized_token((artifact or {}).get("installAccessClass"))
        if install_access_class == "account_required":
            account_linked_install_count += 1
        else:
            public_install_count += 1

    if int_value(release_channel.get("recommendedRouteCount")) != expected_primary:
        errors.append("publicTrustMetrics.releaseChannel.recommendedRouteCount drifted from desktopRouteTruth")
    fallback_route_count = release_channel.get("fallbackRecoveryRouteCount")
    if fallback_route_count is not None and int_value(fallback_route_count) != expected_fallback:
        errors.append("publicTrustMetrics.releaseChannel.fallbackRecoveryRouteCount drifted from desktopRouteTruth")
    if int_value(release_channel.get("blockedRouteCount")) != expected_blocked:
        errors.append("publicTrustMetrics.releaseChannel.blockedRouteCount drifted from desktopRouteTruth")
    if int_value(release_channel.get("revokedRouteCount")) != expected_revoked:
        errors.append("publicTrustMetrics.releaseChannel.revokedRouteCount drifted from desktopRouteTruth")

    if int_value(adoption_health.get("primaryPromotedCount")) != expected_primary:
        errors.append("publicTrustMetrics.adoptionHealth.primaryPromotedCount drifted from desktopRouteTruth")
    if int_value(adoption_health.get("fallbackRecoveryCount")) != expected_fallback:
        errors.append("publicTrustMetrics.adoptionHealth.fallbackRecoveryCount drifted from desktopRouteTruth")
    if int_value(adoption_health.get("blockedRouteCount")) != expected_blocked:
        errors.append("publicTrustMetrics.adoptionHealth.blockedRouteCount drifted from desktopRouteTruth")
    if int_value(adoption_health.get("revokedRouteCount")) != expected_revoked:
        errors.append("publicTrustMetrics.adoptionHealth.revokedRouteCount drifted from desktopRouteTruth")
    if int_value(adoption_health.get("publicInstallCount")) != public_install_count:
        errors.append("publicTrustMetrics.adoptionHealth.publicInstallCount drifted from recommended route install access")
    if int_value(adoption_health.get("accountLinkedInstallCount")) != account_linked_install_count:
        errors.append("publicTrustMetrics.adoptionHealth.accountLinkedInstallCount drifted from recommended route install access")

    if int_value(revocation_facts.get("activeRevocationCount")) != expected_revoked:
        errors.append("publicTrustMetrics.revocationFacts.activeRevocationCount drifted from desktopRouteTruth")
    active_revocations = revocation_facts.get("activeRevocations")
    if isinstance(active_revocations, list) and len(active_revocations) != expected_revoked:
        errors.append("publicTrustMetrics.revocationFacts.activeRevocations length drifted from desktopRouteTruth")

    summary_requires(
        release_channel.get("summary") or "",
        f"{expected_fallback} promoted fallback recovery routes",
        errors,
        "publicTrustMetrics.releaseChannel",
    )
    summary_requires(
        release_channel.get("summary") or "",
        f"{expected_primary} recommended primary routes",
        errors,
        "publicTrustMetrics.releaseChannel",
    )
    summary_requires(
        release_channel.get("summary") or "",
        f"{expected_blocked} blocked routes",
        errors,
        "publicTrustMetrics.releaseChannel",
    )
    summary_requires(
        release_channel.get("summary") or "",
        f"{expected_revoked} active revocations",
        errors,
        "publicTrustMetrics.releaseChannel",
    )

    summary_requires(
        adoption_health.get("summary") or "",
        f"{expected_fallback} fallback recovery routes are promoted",
        errors,
        "publicTrustMetrics.adoptionHealth",
    )
    summary_requires(
        adoption_health.get("summary") or "",
        f"{public_install_count} are guest-readable",
        errors,
        "publicTrustMetrics.adoptionHealth",
    )
    summary_requires(
        adoption_health.get("summary") or "",
        f"{account_linked_install_count} require account-linked install handoff",
        errors,
        "publicTrustMetrics.adoptionHealth",
    )
    summary_requires(
        adoption_health.get("summary") or "",
        f"{expected_blocked} routes are still blocked on proof",
        errors,
        "publicTrustMetrics.adoptionHealth",
    )


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

    tuple_registries_are_unique = verify_unique_tuple_ids(
        identity_registry,
        label="artifactIdentityRegistry",
        errors=errors,
    )
    tuple_registries_are_unique = (
        verify_unique_tuple_ids(
            install_registry,
            label="installAwareArtifactRegistry",
            errors=errors,
        )
        and tuple_registries_are_unique
    )
    if not tuple_registries_are_unique:
        return

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

    verify_public_trust_metrics(
        payload,
        route_truth,
        artifact_by_id,
        errors,
    )

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
