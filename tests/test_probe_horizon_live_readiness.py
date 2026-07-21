from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import materialize_horizon_readiness as materializer
import probe_horizon_live_readiness as probe
import verify_horizon_live_readiness as verifier
import verify_live_release_convergence as convergence


NOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
GENERATED_AT = "2026-07-21T08:00:00Z"
GENERATION_ID = "generation-20260721"
AUTHORITY_SHA = "d" * 64


def release_truth(**overrides):
    value = {
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
    value.update(overrides)
    return value


def expected_binding():
    return verifier.expected_binding("6.2.0", GENERATION_ID, "a" * 64, "c" * 64, AUTHORITY_SHA)


def generation_manifest_bytes():
    payload = {
        "downloads": [
            {
                "id": "chummer-linux",
                "platform": "linux",
                "head": "avalonia",
                "installAccessClass": "open_public",
            },
            {
                "id": "chummer-windows",
                "platform": "windows",
                "head": "avalonia",
                "installAccessClass": "open_public",
            },
        ]
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def source_payload():
    return materializer.build_readiness(
        ROOT,
        ROOT / ".codex-design/product/HORIZON_REGISTRY.yaml",
        ROOT / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs",
        generated_at_utc=GENERATED_AT,
    )


def convergence_receipt():
    routes = {
        f"/api/public/release-truth/g/{GENERATION_ID}",
        f"/downloads/g/{GENERATION_ID}/releases.json",
        f"/downloads/g/{GENERATION_ID}/RELEASE_CHANNEL.generated.json",
        f"/downloads/g/{GENERATION_ID}/releases.json/",
        f"/downloads/g/{GENERATION_ID}/install/chummer-linux",
    }
    value = convergence.verify_route_projections(
        release_truth(),
        {route: release_truth() for route in routes},
        authority_snapshot_sha256=AUTHORITY_SHA,
        route_authority_snapshot_sha256={route: AUTHORITY_SHA for route in routes},
        authority_route=f"/api/v1/public/release-truth/g/{GENERATION_ID}",
        generated_at_utc=GENERATED_AT,
    )
    value["verificationMode"] = "committed_public"
    return value


def encoded_truth(value) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def capability_catalog(source, *, operational="unverified", public_only=False):
    rows = []
    for row in source["capabilities"]:
        if public_only and not row["public_visible"]:
            continue
        rows.append(
            {
                "horizonId": row["horizon_id"],
                "capabilityId": row["capability_id"],
                "artifactKind": row["artifact_kind"],
                "publicLabel": row["public_label"],
                "capabilitySlot": row["capability_slot"],
                "status": "configured",
                "internalProviderLane": None,
                "requiresAuthentication": row["requires_authentication"],
                "publicVisible": row["public_visible"],
                "freeWeeklyLimit": 1,
                "supporterWeeklyLimit": 2,
                "costClass": "low",
                "quotaTracked": row["quota_tracked"],
                "allowanceWindowKind": "weekly",
                "configurationEnabled": True,
                "operationalReadiness": operational,
            }
        )
    return {"publicSafe": True, "capabilities": rows}


class MockTransport:
    def __init__(self, source, *, drift=False):
        self.source = source
        self.drift = drift
        self.calls = []
        self.current_calls = 0

    def __call__(self, url, headers, timeout, max_bytes):
        self.calls.append((url, dict(headers), timeout, max_bytes))
        route = url.removeprefix(verifier.PRODUCTION_ORIGIN)
        if route == probe.CURRENT_ROUTE:
            self.current_calls += 1
            truth = release_truth(
                knownIssueSummary=(
                    "Changed during probe."
                    if self.drift and self.current_calls == 2
                    else "No blocking issue is published."
                )
            )
            body = json.dumps(truth, separators=(",", ":")).encode()
            return probe.Response(
                200,
                {
                    "Content-Type": "application/json",
                    convergence.PROJECTION_HEADER: encoded_truth(truth),
                    convergence.AUTHORITY_SNAPSHOT_SHA256_HEADER: AUTHORITY_SHA,
                    probe.DECISION_STATUS_HEADER: truth["releaseDecisionStatus"],
                },
                body,
                url,
            )
        if route == probe.CAPABILITY_ROUTE:
            body = json.dumps(capability_catalog(self.source), separators=(",", ":")).encode()
            return probe.Response(200, {"Content-Type": "application/json"}, body, url)
        if route == probe.PUBLIC_CAPABILITY_ROUTE:
            body = json.dumps(
                capability_catalog(self.source, public_only=True),
                separators=(",", ":"),
            ).encode()
            return probe.Response(200, {"Content-Type": "application/json"}, body, url)
        if route in verifier.HORIZON_ROUTES.values():
            return probe.Response(200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>Horizon</html>", url)
        raise AssertionError(f"unexpected request: {url}")


def build_with_mock(*, drift=False):
    source = source_payload()
    convergence_value = convergence_receipt()
    source_bytes = (json.dumps(source, indent=2, sort_keys=True) + "\n").encode()
    convergence_bytes = (json.dumps(convergence_value, indent=2) + "\n").encode()
    manifest_bytes = generation_manifest_bytes()
    transport = MockTransport(source, drift=drift)
    receipt = probe.build_receipt(
        origin=verifier.PRODUCTION_ORIGIN,
        source=source,
        source_sha256=verifier.sha256_bytes(source_bytes),
        convergence_receipt=convergence_value,
        convergence_sha256=verifier.sha256_bytes(convergence_bytes),
        generation_manifest_file_sha256=verifier.sha256_bytes(manifest_bytes),
        expected=expected_binding(),
        token="x" * 32,
        timeout=2,
        max_response_bytes=1024 * 1024,
        generated_at_utc=GENERATED_AT,
        transport=transport,
    )
    return receipt, source, convergence_value, source_bytes, convergence_bytes, transport


def test_probe_is_get_only_exact_15_20_and_does_not_infer_operational_ready():
    receipt, _, _, _, _, transport = build_with_mock()

    assert len(receipt["horizons"]) == 15
    assert len(receipt["capabilities"]) == 20
    assert receipt["operationalReadinessClaimAllowed"] is False
    assert receipt["status"] == "attention_required"
    assert receipt["summary"]["configurationConfiguredCount"] == 20
    assert receipt["summary"]["operationalReadyCount"] == 0
    assert len(transport.calls) == 19
    assert all("Authorization" not in headers for url, headers, _, _ in transport.calls if probe.CAPABILITY_ROUTE not in url)
    catalog_headers = next(headers for url, headers, _, _ in transport.calls if probe.CAPABILITY_ROUTE in url)
    assert catalog_headers["Authorization"] == "Bearer " + "x" * 32
    serialized = verifier.canonical_json_bytes(receipt)
    assert b"Bearer" not in serialized and b"internalProviderLane" not in serialized
    assert receipt["probePolicy"]["mutationsPerformed"] is False
    assert receipt["probePolicy"]["providerCallsPerformed"] is False
    assert receipt["probePolicy"]["quotaConsumed"] is False
    assert receipt["probePolicy"]["baseOrigin"] == verifier.PRODUCTION_ORIGIN
    assert receipt["catalogObservations"]["public"]["rowCount"] == sum(
        row["public_visible"] for row in source_payload()["capabilities"]
    )
    assert all(row["deploymentStatus"] == "raw_http_reachable" for row in receipt["horizons"])
    assert all(row["identityBindingStatus"] == "not_exposed" for row in receipt["capabilities"])


def test_probe_rejects_pre_post_current_drift():
    with pytest.raises(probe.ProbeError, match="CURRENT|drifted"):
        build_with_mock(drift=True)


@pytest.mark.parametrize(
    "value",
    [
        "http://example.test",
        "https://user@example.test",
        "https://example.test/path",
        "https://example.test?x=1",
        "https://example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://singlelabel",
    ],
)
def test_base_origin_is_https_origin_only(value):
    with pytest.raises(probe.ProbeError):
        probe.validate_base_origin(value)


def test_only_exact_production_origin_is_accepted():
    assert probe.validate_base_origin(verifier.PRODUCTION_ORIGIN) == verifier.PRODUCTION_ORIGIN


def test_token_requires_owned_mode_0600_regular_file(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("z" * 32 + "\n", encoding="ascii")
    token_file.chmod(0o600)
    assert probe.read_token_file(token_file) == "z" * 32
    token_file.chmod(0o640)
    with pytest.raises(probe.ProbeError, match="0600"):
        probe.read_token_file(token_file)


def test_token_fifo_is_rejected_without_blocking(tmp_path):
    fifo = tmp_path / "token.fifo"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(probe.ProbeError, match="ownership/type"):
        probe.read_token_file(fifo)


def test_output_is_canonical_mode_0600_and_create_new(tmp_path):
    receipt, *_ = build_with_mock()
    output = tmp_path / "receipt.json"
    probe.write_new_receipt(output, receipt)
    assert output.read_bytes() == verifier.canonical_json_bytes(receipt)
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(probe.ProbeError, match="new file"):
        probe.write_new_receipt(output, receipt)


def test_catalog_rejects_sensitive_provider_metadata():
    source = source_payload()
    payload = capability_catalog(source)
    payload["capabilities"][0]["internalProviderLane"] = "secret provider"
    body = json.dumps(payload, separators=(",", ":")).encode()
    response = probe.Response(200, {"Content-Type": "application/json"}, body, verifier.PRODUCTION_ORIGIN + probe.CAPABILITY_ROUTE)
    with pytest.raises(probe.ProbeError, match="sensitive"):
        probe._catalog_snapshot(
            response,
            source,
            route=probe.CAPABILITY_ROUTE,
            public_only=False,
            expected=expected_binding(),
            expected_truth=release_truth(),
        )


def test_catalog_rejects_unknown_dto_keys_and_bool_allowances():
    source = source_payload()
    payload = capability_catalog(source)
    payload["capabilities"][0]["unexpected"] = "drift"
    payload["capabilities"][1]["freeWeeklyLimit"] = True
    body = json.dumps(payload, separators=(",", ":")).encode()
    response = probe.Response(
        200,
        {"Content-Type": "application/json"},
        body,
        verifier.PRODUCTION_ORIGIN + probe.CAPABILITY_ROUTE,
    )
    with pytest.raises(probe.ProbeError, match="DTO"):
        probe._catalog_snapshot(
            response,
            source,
            route=probe.CAPABILITY_ROUTE,
            public_only=False,
            expected=expected_binding(),
            expected_truth=release_truth(),
        )


def test_partial_release_markers_are_rejected_on_raw_horizon_responses():
    with pytest.raises(probe.ProbeError, match="partial"):
        probe._response_identity_binding(
            {convergence.PROJECTION_HEADER: encoded_truth(release_truth())},
            expected_binding(),
            release_truth(),
        )


def test_probe_cli_attention_is_nonzero_unless_observation_mode(
    tmp_path, monkeypatch, capsys
):
    receipt, _, _, source_bytes, convergence_bytes, _ = build_with_mock()
    manifest_bytes = generation_manifest_bytes()
    source_path = tmp_path / "source.json"
    convergence_path = tmp_path / "convergence.json"
    manifest_path = tmp_path / "releases.json"
    token_path = tmp_path / "token"
    source_path.write_bytes(source_bytes)
    convergence_path.write_bytes(convergence_bytes)
    manifest_path.write_bytes(manifest_bytes)
    token_path.write_text("z" * 32 + "\n", encoding="ascii")
    token_path.chmod(0o600)
    monkeypatch.setattr(probe, "build_receipt", lambda **_: receipt)
    monkeypatch.setattr(probe, "write_new_receipt", lambda *_: None)
    monkeypatch.setattr(probe.source_verifier, "verify_payload", lambda *_, **__: (True, []))
    monkeypatch.setattr(probe.source_verifier, "source_working_claim_allowed", lambda *_: True)
    monkeypatch.setattr(verifier, "_timestamp_issues", lambda *_, **__: [])
    args = [
        "--source-readiness", str(source_path),
        "--expected-source-readiness-sha256", verifier.sha256_bytes(source_bytes),
        "--committed-public-convergence", str(convergence_path),
        "--expected-committed-public-convergence-sha256", verifier.sha256_bytes(convergence_bytes),
        "--generation-manifest", str(manifest_path),
        "--expected-generation-manifest-file-sha256", verifier.sha256_bytes(manifest_bytes),
        "--expected-release-version", "6.2.0",
        "--expected-generation-id", GENERATION_ID,
        "--expected-manifest-sha256", "a" * 64,
        "--expected-release-decision-sha256", "c" * 64,
        "--expected-authority-snapshot-sha256", AUTHORITY_SHA,
        "--internal-token-file", str(token_path),
        "--output", str(tmp_path / "receipt.json"),
        "--repo-root", str(ROOT),
    ]
    assert probe.main(args) == 1
    assert probe.main([*args, "--allow-attention-required"]) == 0
    output = capsys.readouterr().out
    assert '"status": "attention_required"' in output
    assert '"release_gate_passed": false' in output
