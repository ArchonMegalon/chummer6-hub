from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_live_release_convergence.py"
AUTHORITY_SNAPSHOT_SHA256 = "d" * 64


def load_module():
    spec = importlib.util.spec_from_file_location("verify_live_release_convergence", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def projection(**overrides):
    payload = {
        "contractName": "chummer.release-truth-projection/v1",
        "releaseVersion": "6.2.0",
        "channel": "public_stable",
        "releaseStatus": "published",
        "rolloutState": "public_stable",
        "supportabilityState": "gold_supported",
        "availablePlatforms": ["linux", "windows"],
        "primaryHeadByPlatform": {"linux": "avalonia", "windows": "avalonia"},
        "artifactCount": 2,
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "No blocking issue is published.",
        "manifestSha256": "a" * 64,
        "registryCommit": "b" * 40,
        "releaseDecisionStatus": "stable_ready",
        "releaseDecisionSha256": "c" * 64,
    }
    payload.update(overrides)
    return payload


def encode_header(payload) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_required_fields_and_matching_routes_pass() -> None:
    module = load_module()
    authority = projection()

    result = module.verify_route_projections(
        authority,
        {"/downloads": projection(), "/status": projection()},
        authority_snapshot_sha256=AUTHORITY_SNAPSHOT_SHA256,
        route_authority_snapshot_sha256={
            "/downloads": AUTHORITY_SNAPSHOT_SHA256,
            "/status": AUTHORITY_SNAPSHOT_SHA256,
        },
    )

    assert result["status"] == "pass"
    assert result["contractName"] == "chummer.live-release-convergence/v1"
    assert result["contractVersion"] == 1
    assert result["mismatchCount"] == 0
    assert result["failureCount"] == 0
    assert result["mismatches"] == []
    assert result["failures"] == []
    assert result["checkedRouteCount"] == 2
    assert result["comparedFields"] == list(module.REQUIRED_FIELDS)
    assert result["releaseTruth"]["contractName"] == "chummer.release-truth-projection/v1"
    assert result["authoritySnapshotSha256"] == AUTHORITY_SNAPSHOT_SHA256


def test_missing_required_field_fails_closed() -> None:
    module = load_module()
    incomplete = projection()
    incomplete.pop("releaseDecisionSha256")

    with pytest.raises(module.ConvergenceError, match="releaseDecisionSha256"):
        module.canonicalize_projection(incomplete, source="/status")


def test_contradictory_route_reports_exact_field() -> None:
    module = load_module()

    with pytest.raises(module.ConvergenceError, match=r"/status: rolloutState"):
        module.verify_route_projections(
            projection(),
            {"/downloads": projection(), "/status": projection(rolloutState="review_required")},
            authority_snapshot_sha256=AUTHORITY_SNAPSHOT_SHA256,
            route_authority_snapshot_sha256={
                "/downloads": AUTHORITY_SNAPSHOT_SHA256,
                "/status": AUTHORITY_SNAPSHOT_SHA256,
            },
        )


def test_contradictory_authority_snapshot_digest_is_rejected() -> None:
    module = load_module()

    with pytest.raises(module.ConvergenceError, match="authoritySnapshotSha256"):
        module.verify_route_projections(
            projection(),
            {"/downloads": projection(), "/status": projection()},
            authority_snapshot_sha256=AUTHORITY_SNAPSHOT_SHA256,
            route_authority_snapshot_sha256={
                "/downloads": AUTHORITY_SNAPSHOT_SHA256,
                "/status": "e" * 64,
            },
        )


def test_body_and_header_contradiction_is_rejected() -> None:
    module = load_module()
    header_projection = projection()
    body_projection = projection(artifactCount=3)
    body = (
        '<script id="chummer-release-truth" type="application/json">'
        + json.dumps(body_projection)
        + "</script>"
    ).encode()

    with pytest.raises(module.ConvergenceError, match="artifactCount"):
        module.extract_route_projection(
            route="/downloads",
            headers={module.PROJECTION_HEADER: encode_header(header_projection)},
            body=body,
            content_type="text/html",
        )


def test_status_alias_is_accepted_but_normalized_to_release_status() -> None:
    module = load_module()
    aliased = projection()
    aliased["status"] = aliased.pop("releaseStatus")

    normalized = module.canonicalize_projection(aliased, source="manifest")

    assert normalized["releaseStatus"] == "published"


def test_invalid_decision_literal_is_rejected() -> None:
    module = load_module()

    with pytest.raises(module.ConvergenceError, match="releaseDecisionStatus"):
        module.canonicalize_projection(
            projection(releaseDecisionStatus="approved"),
            source="authority",
        )


def test_empty_shelf_requires_review_and_unavailable_posture() -> None:
    module = load_module()
    valid = projection(
        availablePlatforms=[],
        primaryHeadByPlatform={},
        artifactCount=0,
        downloadAccessPosture="unavailable",
        releaseDecisionStatus="review_required",
    )

    normalized = module.canonicalize_projection(valid, source="authority")

    assert normalized["artifactCount"] == 0
    with pytest.raises(module.ConvergenceError, match="empty shelf"):
        module.canonicalize_projection(
            {**valid, "releaseDecisionStatus": "stable_ready"},
            source="authority",
        )


def test_nonempty_shelf_cannot_claim_unavailable_posture() -> None:
    module = load_module()

    with pytest.raises(module.ConvergenceError, match="non-empty shelf"):
        module.canonicalize_projection(
            projection(downloadAccessPosture="unavailable"),
            source="authority",
        )


def test_projection_rejects_unknown_fields_and_short_registry_commit() -> None:
    module = load_module()

    with pytest.raises(module.ConvergenceError, match="unknown release-truth fields"):
        module.canonicalize_projection(
            projection(registryRepository="ArchonMegalon/chummer6-hub-registry"),
            source="authority",
        )
    with pytest.raises(module.ConvergenceError, match="registryCommit"):
        module.canonicalize_projection(
            projection(registryCommit="b" * 7),
            source="authority",
        )


def test_committed_generation_routes_are_independent_of_current() -> None:
    module = load_module()

    routes = module.generation_routes("candidate-20260718.1")

    assert routes == (
        "/api/public/release-truth/g/candidate-20260718.1",
        "/downloads/g/candidate-20260718.1/releases.json",
        "/downloads/g/candidate-20260718.1/RELEASE_CHANNEL.generated.json",
    )
    with pytest.raises(module.ConvergenceError, match="traversal-safe"):
        module.generation_routes("../current")


def test_default_routes_cover_help_and_release_concierges() -> None:
    module = load_module()

    assert "/help" in module.DEFAULT_ROUTES
    assert "/downloads/concierge" in module.DEFAULT_ROUTES
    assert "/now/concierge" in module.DEFAULT_ROUTES
