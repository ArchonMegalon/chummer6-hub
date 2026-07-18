from __future__ import annotations

import base64
import io
import importlib.util
import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

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


def test_legacy_status_alias_is_rejected() -> None:
    module = load_module()
    aliased = projection()
    aliased["status"] = aliased.pop("releaseStatus")

    with pytest.raises(module.ConvergenceError, match="unknown release-truth fields"):
        module.canonicalize_projection(aliased, source="manifest")


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("application/json", b'{"version":"6.1.0","status":"published"}'),
        ("text/html", b"<html><body>Current stable release.</body></html>"),
        ("image/svg+xml", b"<svg><text>Current stable release.</text></svg>"),
    ],
)
def test_textual_body_without_embedded_release_truth_is_rejected(
    content_type: str,
    body: bytes,
) -> None:
    module = load_module()

    with pytest.raises(module.ConvergenceError, match="missing embedded releaseTruth"):
        module.extract_route_projection(
            route="/downloads/releases.json",
            headers={module.PROJECTION_HEADER: encode_header(projection())},
            body=body,
            content_type=content_type,
        )


def test_native_manifest_cannot_contradict_header_by_omitting_projection() -> None:
    module = load_module()
    stale_manifest = {
        "version": "6.1.0",
        "channel": "public_stable",
        "status": "published",
        "rolloutState": "public_stable",
    }

    with pytest.raises(module.ConvergenceError, match="missing embedded releaseTruth"):
        module.extract_route_projection(
            route="/downloads/RELEASE_CHANNEL.generated.json",
            headers={module.PROJECTION_HEADER: encode_header(projection())},
            body=json.dumps(stale_manifest).encode(),
            content_type="application/json",
        )


def test_embedded_projection_cannot_mask_stale_native_manifest_claims() -> None:
    module = load_module()
    current = projection()
    stale_manifest = {
        "version": "6.1.0",
        "channel": current["channel"],
        "status": current["releaseStatus"],
        "rolloutState": current["rolloutState"],
        "supportabilityState": current["supportabilityState"],
        "knownIssueSummary": current["knownIssueSummary"],
        "downloads": [
            {
                "id": "only-one",
                "platform": "windows",
                "head": "avalonia",
                "installAccessClass": "open_public",
            }
        ],
        "releaseTruth": current,
    }

    with pytest.raises(module.ConvergenceError, match=r"native body/releaseTruth drift"):
        module.extract_route_projection(
            route="/downloads/releases.json",
            headers={module.PROJECTION_HEADER: encode_header(current)},
            body=json.dumps(stale_manifest).encode(),
            content_type="application/json",
        )


@pytest.mark.parametrize(
    ("downloads", "expected_field"),
    [
        (
            [
                {"platform": "windows", "head": "avalonia", "installAccessClass": "open_public"},
                {"platform": "windows", "head": "avalonia", "installAccessClass": "open_public"},
            ],
            "availablePlatforms",
        ),
        (
            [
                {"platform": "linux", "head": "legacy", "installAccessClass": "open_public"},
                {"platform": "windows", "head": "legacy", "installAccessClass": "open_public"},
            ],
            "primaryHeadByPlatform",
        ),
        (
            [
                {"platform": "linux", "head": "avalonia", "installAccessClass": "account_required"},
                {"platform": "windows", "head": "avalonia", "installAccessClass": "open_public"},
            ],
            "downloadAccessPosture",
        ),
    ],
)
def test_same_count_native_shelf_cannot_mask_projection_drift(
    downloads,
    expected_field: str,
) -> None:
    module = load_module()
    current = projection()
    payload = {"downloads": downloads, "releaseTruth": current}

    with pytest.raises(module.ConvergenceError, match=expected_field):
        module.extract_route_projection(
            route="/downloads/releases.json",
            headers={module.PROJECTION_HEADER: encode_header(current)},
            body=json.dumps(payload).encode(),
            content_type="application/json",
        )


def test_compatibility_manifest_prefers_canonical_platform_id_over_display_label() -> None:
    module = load_module()
    current = projection()
    payload = {
        "downloads": [
            {
                "platform": "Avalonia Desktop Linux Installer",
                "platformId": "linux",
                "head": "avalonia",
                "installAccessClass": "open_public",
            },
            {
                "platform": "Avalonia Desktop Windows X64 Installer",
                "platformId": "windows",
                "head": "avalonia",
                "installAccessClass": "open_public",
            },
        ],
        "releaseTruth": current,
    }

    assert module.extract_route_projection(
        route="/downloads/releases.json",
        headers={module.PROJECTION_HEADER: encode_header(current)},
        body=json.dumps(payload).encode(),
        content_type="application/json",
    ) == current


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
        "/downloads/g/candidate-20260718.1/releases.json/",
    )
    with pytest.raises(module.ConvergenceError, match="traversal-safe"):
        module.generation_routes("../current")


def test_default_routes_cover_help_and_release_concierges() -> None:
    module = load_module()

    assert "/help" in module.DEFAULT_ROUTES
    assert "/downloads/concierge" in module.DEFAULT_ROUTES
    assert "/now/concierge" in module.DEFAULT_ROUTES
    assert "/now/concierge/read_notes" in module.DEFAULT_ROUTES
    assert "/Now/" in module.DEFAULT_ROUTES
    assert "/Help/" in module.DEFAULT_ROUTES
    assert "/api/v1/install-linking/continuation" in module.DEFAULT_ROUTES
    assert "/api/v1/install-linking/continuation/support" in module.DEFAULT_ROUTES
    assert "/api/v1/install-linking/continuation/update" in module.DEFAULT_ROUTES
    assert "/api/v1/install-linking/continuation/rollback" in module.DEFAULT_ROUTES


def test_dynamic_install_routes_are_discovered_for_current_and_generation() -> None:
    module = load_module()
    body = json.dumps(
        {
            "downloads": [
                {"id": "private", "installAccessClass": "account_required"},
                {"id": "public-win-x64", "installAccessClass": "open_public"},
            ]
        }
    ).encode()

    assert module.discover_install_route(body) == "/downloads/install/public-win-x64"
    assert module.discover_install_route(
        body,
        generation_id="candidate-20260718.1",
    ) == "/downloads/g/candidate-20260718.1/install/public-win-x64"


def test_redirecting_installer_source_hop_is_captured_with_head_only() -> None:
    module = load_module()
    current = projection()
    headers = Message()
    headers[module.PROJECTION_HEADER] = encode_header(current)
    headers[module.AUTHORITY_SNAPSHOT_SHA256_HEADER] = AUTHORITY_SNAPSHOT_SHA256
    headers["Content-Type"] = "text/html"

    class RedirectingOpener:
        method = None

        def open(self, request, timeout):
            self.method = request.get_method()
            raise HTTPError(
                request.full_url,
                302,
                "Found",
                headers,
                io.BytesIO(b""),
            )

    opener = RedirectingOpener()
    observed_headers, body, content_type = module.fetch_route(
        opener,
        "https://chummer.run/",
        "/downloads/install/public-win-x64",
        1.0,
        method="HEAD",
        accept_redirect_response=True,
    )

    assert opener.method == "HEAD"
    assert body == b""
    assert content_type == "text/html"
    assert module.extract_route_projection(
        route="/downloads/install/public-win-x64",
        headers=observed_headers,
        body=body,
        content_type=content_type,
        require_body_projection=False,
    ) == current


def test_review_required_installer_source_hop_accepts_governed_409_head_only() -> None:
    module = load_module()
    current = projection(releaseDecisionStatus="review_required")
    headers = Message()
    headers[module.PROJECTION_HEADER] = encode_header(current)
    headers[module.AUTHORITY_SNAPSHOT_SHA256_HEADER] = AUTHORITY_SNAPSHOT_SHA256
    headers["Content-Type"] = "application/json"

    class ReviewRequiredOpener:
        method = None

        def open(self, request, timeout):
            self.method = request.get_method()
            raise HTTPError(
                request.full_url,
                409,
                "Conflict",
                headers,
                io.BytesIO(b""),
            )

    opener = ReviewRequiredOpener()
    with pytest.raises(module.ConvergenceError, match="HTTP 409"):
        module.fetch_route(
            opener,
            "https://chummer.run/",
            "/status",
            1.0,
        )

    observed_headers, body, content_type = module.fetch_route(
        opener,
        "https://chummer.run/",
        "/downloads/install/public-win-x64",
        1.0,
        method="HEAD",
        accept_redirect_response=True,
        accepted_error_statuses=module._accepted_handoff_error_statuses(current),
    )

    assert opener.method == "HEAD"
    assert body == b""
    assert content_type == "application/json"
    assert module.extract_route_projection(
        route="/downloads/install/public-win-x64",
        headers=observed_headers,
        body=body,
        content_type=content_type,
        require_body_projection=False,
    ) == current


def test_stable_installer_source_hop_rejects_governed_409() -> None:
    module = load_module()
    current = projection()
    headers = Message()
    headers[module.PROJECTION_HEADER] = encode_header(current)
    headers[module.AUTHORITY_SNAPSHOT_SHA256_HEADER] = AUTHORITY_SNAPSHOT_SHA256
    headers["Content-Type"] = "application/json"

    class ConflictingStableOpener:
        def open(self, request, timeout):
            raise HTTPError(
                request.full_url,
                409,
                "Conflict",
                headers,
                io.BytesIO(b""),
            )

    with pytest.raises(module.ConvergenceError, match="HTTP 409"):
        module.fetch_route(
            ConflictingStableOpener(),
            "https://chummer.run/",
            "/downloads/install/public-win-x64",
            1.0,
            method="HEAD",
            accept_redirect_response=True,
            accepted_error_statuses=module._accepted_handoff_error_statuses(current),
        )


def test_failure_receipt_has_the_exact_sixteen_field_contract() -> None:
    module = load_module()

    receipt = module.build_failure_receipt("/help: missing embedded releaseTruth")

    assert set(receipt) == {
        "contractName",
        "contractVersion",
        "status",
        "mismatchCount",
        "failureCount",
        "mismatches",
        "failures",
        "authorityRoute",
        "checkedRouteCount",
        "checkedRoutes",
        "comparedFields",
        "releaseTruth",
        "manifestSha256",
        "releaseDecisionStatus",
        "releaseDecisionSha256",
        "authoritySnapshotSha256",
    }
    assert "error" not in receipt


def test_generation_failure_receipt_names_generation_authority_route(
    monkeypatch,
    capsys,
) -> None:
    module = load_module()

    def fail_verification(*args, **kwargs):
        raise module.ConvergenceError("generation route drift")

    monkeypatch.setattr(module, "verify_live", fail_verification)

    assert module.main(["--generation-id", "candidate-20260718.1"]) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["authorityRoute"] == (
        "/api/v1/public/release-truth/g/candidate-20260718.1"
    )
