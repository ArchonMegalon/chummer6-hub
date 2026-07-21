from __future__ import annotations

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
import verify_horizon_live_readiness as verifier
import verify_live_release_convergence as convergence


GENERATION_ID = "generation-20260721"
AUTHORITY_SHA = "d" * 64


def timestamp_now():
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def release_truth():
    return {
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


def fixture_values():
    generated = timestamp_now()
    source = materializer.build_readiness(
        ROOT,
        ROOT / ".codex-design/product/HORIZON_REGISTRY.yaml",
        ROOT / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs",
        generated_at_utc=generated,
    )
    checked_routes = {
        f"/api/public/release-truth/g/{GENERATION_ID}",
        f"/downloads/g/{GENERATION_ID}/releases.json",
        f"/downloads/g/{GENERATION_ID}/RELEASE_CHANNEL.generated.json",
        f"/downloads/g/{GENERATION_ID}/releases.json/",
        f"/downloads/g/{GENERATION_ID}/install/chummer-linux",
    }
    convergence_receipt = convergence.verify_route_projections(
        release_truth(),
        {route: release_truth() for route in checked_routes},
        authority_snapshot_sha256=AUTHORITY_SHA,
        route_authority_snapshot_sha256={route: AUTHORITY_SHA for route in checked_routes},
        authority_route=f"/api/v1/public/release-truth/g/{GENERATION_ID}",
        generated_at_utc=generated,
    )
    convergence_receipt["verificationMode"] = "committed_public"
    source_bytes = (json.dumps(source, indent=2, sort_keys=True) + "\n").encode()
    convergence_bytes = (json.dumps(convergence_receipt, indent=2) + "\n").encode()
    source_sha = verifier.sha256_bytes(source_bytes)
    convergence_sha = verifier.sha256_bytes(convergence_bytes)
    manifest_bytes = generation_manifest_bytes()
    manifest_sha = verifier.sha256_bytes(manifest_bytes)
    expected = verifier.expected_binding("6.2.0", GENERATION_ID, "a" * 64, "c" * 64, AUTHORITY_SHA)
    horizons = []
    for row in source["horizons"]:
        horizons.append(
            {
                "horizonId": row["horizon_id"],
                "route": verifier.HORIZON_ROUTES[row["horizon_id"]],
                "sourceStatus": row["source_status"],
                "deploymentStatus": "raw_http_reachable",
                "configurationStatus": "not_applicable",
                "operationalStatus": row["runtime_status"],
                "governanceStatus": row["governance_status"],
                "httpStatus": 200,
                "contentType": "text/html",
                "responseSha256": "e" * 64,
                "identityBindingStatus": "not_exposed",
            }
        )
    capabilities = []
    for row in source["capabilities"]:
        capabilities.append(
            {
                "horizonId": row["horizon_id"],
                "capabilityId": row["capability_id"],
                "sourceStatus": row["source_status"],
                "deploymentStatus": "raw_http_observed",
                "configurationStatus": "configured",
                "operationalStatus": "unverified",
                "governanceStatus": row["governance_status"],
                "httpStatus": 200,
                "responseSha256": "f" * 64,
                "identityBindingStatus": "not_exposed",
                "publicCatalogObserved": row["public_visible"],
            }
        )
    fence_snapshot = {
        "route": "/api/v1/public/release-truth",
        "releaseVersion": "6.2.0",
        "manifestSha256": "a" * 64,
        "releaseDecisionSha256": "c" * 64,
        "releaseDecisionStatus": "stable_ready",
        "authoritySnapshotSha256": AUTHORITY_SHA,
        "releaseTruthSha256": verifier.sha256_bytes(
            verifier.canonical_json_bytes(release_truth())
        ),
        "responseSha256": "1" * 64,
    }
    receipt = {
        "contractName": verifier.CONTRACT_NAME,
        "contractVersion": 1,
        "generatedAtUtc": generated,
        "status": "attention_required",
        "operationalReadinessClaimAllowed": False,
        "releaseBinding": {**expected, "releaseDecisionStatus": "stable_ready"},
        "inputBindings": {
            "sourceReadinessSha256": source_sha,
            "committedPublicConvergenceSha256": convergence_sha,
            "generationManifestFileSha256": manifest_sha,
        },
        "probePolicy": {
            "baseOrigin": verifier.PRODUCTION_ORIGIN,
            "methods": ["GET"],
            "sameOriginOnly": True,
            "redirectsFollowed": False,
            "runtimeRequestsPerformed": True,
            "providerCallsPerformed": False,
            "quotaConsumed": False,
            "mutationsPerformed": False,
            "secretRedacted": True,
        },
        "currentFence": {
            "preCurrent": dict(fence_snapshot),
            "postCurrent": dict(fence_snapshot),
            "stable": True,
        },
        "catalogObservations": {
            "internalPublicSafe": {
                "route": verifier.INTERNAL_CAPABILITY_ROUTE,
                "httpStatus": 200,
                "contentType": "application/json",
                "responseSha256": "f" * 64,
                "identityBindingStatus": "not_exposed",
                "rowCount": 20,
            },
            "public": {
                "route": verifier.PUBLIC_CAPABILITY_ROUTE,
                "httpStatus": 200,
                "contentType": "application/json",
                "responseSha256": "9" * 64,
                "identityBindingStatus": "not_exposed",
                "rowCount": sum(row["public_visible"] for row in source["capabilities"]),
            },
        },
        "summary": {
            "horizonCount": 15,
            "capabilityCount": 20,
            "deploymentReachableCount": 15,
            "configurationConfiguredCount": 20,
            "configurationDisabledCount": 0,
            "operationalReadyCount": 0,
            "governanceClearedCount": sum(row["governanceStatus"] in {"cleared", "not_required"} for row in capabilities),
            "publicCapabilityCount": sum(row["publicCatalogObserved"] for row in capabilities),
        },
        "horizons": horizons,
        "capabilities": capabilities,
    }
    return (
        receipt,
        source,
        convergence_receipt,
        source_bytes,
        convergence_bytes,
        expected,
        manifest_bytes,
    )


def verify(values):
    receipt, source, convergence_receipt, source_bytes, convergence_bytes, expected, manifest_bytes = values
    return verifier.verify_receipt(
        receipt,
        source,
        convergence_receipt,
        source_sha256=verifier.sha256_bytes(source_bytes),
        convergence_sha256=verifier.sha256_bytes(convergence_bytes),
        generation_manifest_sha256=verifier.sha256_bytes(manifest_bytes),
        generation_manifest_bytes=manifest_bytes,
        expected=expected,
        repo_root=ROOT,
        now_utc=datetime.now(UTC),
    )


def test_offline_verifier_accepts_exact_attention_required_receipt():
    ok, issues = verify(fixture_values())
    assert ok, issues


def test_exact_15_20_denominators_fail_closed():
    values = fixture_values()
    values[0]["capabilities"].pop()
    ok, issues = verify(values)
    assert not ok
    assert "receipt:capabilities:id_set_mismatch" in issues


def test_generation_and_input_digest_replay_are_rejected():
    values = fixture_values()
    values[0]["releaseBinding"]["generationId"] = "older-generation"
    values[0]["inputBindings"]["sourceReadinessSha256"] = "0" * 64
    ok, issues = verify(values)
    assert not ok
    assert "releaseBinding:generationId:mismatch" in issues
    assert "inputBindings:sourceReadinessSha256:mismatch" in issues


def test_manifest_derived_install_handoff_is_exact():
    values = list(fixture_values())
    changed_manifest = json.loads(values[6])
    changed_manifest["downloads"][0]["id"] = "different-installer"
    values[6] = (
        json.dumps(changed_manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    values[0]["inputBindings"]["generationManifestFileSha256"] = verifier.sha256_bytes(
        values[6]
    )
    ok, issues = verify(values)
    assert not ok
    assert "convergence:checked_routes:generation_mismatch" in issues


def test_staged_or_failed_convergence_is_not_authority():
    values = fixture_values()
    values[2]["verificationMode"] = "staged_private"
    ok, issues = verify(values)
    assert not ok
    assert "convergence:verificationMode:mismatch" in issues


def test_convergence_must_be_fresh_and_release_ready():
    values = fixture_values()
    values[2]["generatedAtUtc"] = "2020-01-01T00:00:00Z"
    values[2]["releaseDecisionStatus"] = "review_required"
    values[2]["releaseTruth"]["releaseDecisionStatus"] = "review_required"
    ok, issues = verify(values)
    assert not ok
    assert "convergence:generatedAtUtc:stale" in issues
    assert "convergence:releaseDecisionStatus:not_release_ready" in issues


def test_preview_ready_is_an_explicit_publishable_decision():
    values = fixture_values()
    values[2]["releaseDecisionStatus"] = "preview_ready"
    values[2]["releaseTruth"]["releaseDecisionStatus"] = "preview_ready"
    values[0]["releaseBinding"]["releaseDecisionStatus"] = "preview_ready"
    values[0]["currentFence"]["preCurrent"]["releaseDecisionStatus"] = "preview_ready"
    values[0]["currentFence"]["postCurrent"]["releaseDecisionStatus"] = "preview_ready"
    truth_sha = verifier.sha256_bytes(
        verifier.canonical_json_bytes(values[2]["releaseTruth"])
    )
    values[0]["currentFence"]["preCurrent"]["releaseTruthSha256"] = truth_sha
    values[0]["currentFence"]["postCurrent"]["releaseTruthSha256"] = truth_sha
    ok, issues = verify(values)
    assert ok, issues


def test_http_200_and_configured_do_not_authorize_operational_claim():
    values = fixture_values()
    values[0]["operationalReadinessClaimAllowed"] = True
    values[0]["status"] = "ready"
    ok, issues = verify(values)
    assert not ok
    assert "receipt:operationalReadinessClaimAllowed:mismatch" in issues
    assert "receipt:status:mismatch" in issues


def test_current_fence_body_drift_is_rejected():
    values = fixture_values()
    values[0]["currentFence"]["postCurrent"]["responseSha256"] = "2" * 64
    ok, issues = verify(values)
    assert not ok
    assert "currentFence:pre_post_drift" in issues


def test_receipt_reader_rejects_noncanonical_and_duplicate_json(tmp_path):
    values = fixture_values()
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(values[0], indent=2) + "\n", encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="noncanonical"):
        verifier.read_json_object(path, label="receipt", require_canonical=True)
    path.write_text('{"contractName":"a","contractName":"b"}\n', encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="invalid_json"):
        verifier.read_json_object(path, label="receipt")


def test_receipt_reader_rejects_symlink_and_writable_input(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    target.chmod(0o666)
    with pytest.raises(verifier.VerificationError, match="unsafe_file_metadata"):
        verifier.read_json_object(target, label="receipt")
    target.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(verifier.VerificationError, match="unsafe_or_unreadable"):
        verifier.read_json_object(link, label="receipt")
    fifo = tmp_path / "receipt.fifo"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(verifier.VerificationError, match="unsafe_file_metadata"):
        verifier.read_json_object(fifo, label="receipt")


def cli_fixture(tmp_path):
    receipt, _, _, source_bytes, convergence_bytes, expected, manifest_bytes = fixture_values()
    receipt_path = tmp_path / "receipt.json"
    source_path = tmp_path / "source.json"
    convergence_path = tmp_path / "convergence.json"
    manifest_path = tmp_path / "releases.json"
    receipt_path.write_bytes(verifier.canonical_json_bytes(receipt))
    source_path.write_bytes(source_bytes)
    convergence_path.write_bytes(convergence_bytes)
    manifest_path.write_bytes(manifest_bytes)
    args = [
        "--receipt", str(receipt_path),
        "--source-readiness", str(source_path),
        "--committed-public-convergence", str(convergence_path),
        "--generation-manifest", str(manifest_path),
        "--expected-source-readiness-sha256", verifier.sha256_bytes(source_bytes),
        "--expected-committed-public-convergence-sha256", verifier.sha256_bytes(convergence_bytes),
        "--expected-generation-manifest-file-sha256", verifier.sha256_bytes(manifest_bytes),
        "--expected-release-version", expected["releaseVersion"],
        "--expected-generation-id", expected["generationId"],
        "--expected-manifest-sha256", expected["manifestSha256"],
        "--expected-release-decision-sha256", expected["releaseDecisionSha256"],
        "--expected-authority-snapshot-sha256", expected["authoritySnapshotSha256"],
        "--repo-root", str(ROOT),
    ]
    return args, receipt, expected


def test_cli_require_operational_ready_fails_without_network(tmp_path, capsys):
    args, _, _ = cli_fixture(tmp_path)
    assert verifier.main(args) == 1
    assert verifier.main([*args, "--allow-attention-required"]) == 0
    assert verifier.main([*args, "--require-operational-ready"]) == 1
    output = capsys.readouterr().out
    assert '"status": "attention_required"' in output
    assert '"status": "pass"' in output
    assert "operational_readiness_not_allowed" in output


@pytest.mark.parametrize(
    "included",
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, False),
        (True, False, True),
        (False, True, True),
    ],
)
def test_evidence_cli_options_are_all_or_none(tmp_path, included, capsys):
    args, _, _ = cli_fixture(tmp_path)
    values = (
        ("--evidence-output", str(tmp_path / "evidence.json")),
        ("--evidence-id", "horizon-check-20260721"),
        ("--expected-target-pointer-sha256", "7" * 64),
    )
    extras = [item for present, pair in zip(included, values) if present for item in pair]

    assert verifier.main([*args, *extras]) == 1
    assert not (tmp_path / "evidence.json").exists()
    assert "evidence_export:all_options_required" in capsys.readouterr().out


def test_verified_receipt_exports_canonical_attention_evidence_before_gate(
    tmp_path,
    capsys,
):
    args, receipt, expected = cli_fixture(tmp_path)
    receipt_bytes = verifier.canonical_json_bytes(receipt)
    output = tmp_path / "horizon-evidence.json"
    target_pointer_sha256 = "7" * 64
    evidence_args = [
        "--evidence-output", str(output),
        "--evidence-id", "horizon-check-20260721",
        "--expected-target-pointer-sha256", target_pointer_sha256,
    ]

    # The normal release gate remains non-zero, but verified attention evidence
    # is still materialized for the offline post-activation aggregator.
    assert verifier.main([*args, *evidence_args]) == 1
    assert '"status": "attention_required"' in capsys.readouterr().out
    raw = output.read_bytes()
    envelope = json.loads(raw)
    assert raw == verifier.canonical_json_bytes(envelope)
    assert stat_mode(output) == 0o600
    assert set(envelope) == {
        "contractName",
        "contractVersion",
        "evidenceKind",
        "evidenceId",
        "generatedAtUtc",
        "status",
        "secretRedacted",
        "operationalReadinessClaimAllowed",
        "releaseBinding",
        "claims",
    }
    assert envelope["contractName"] == "chummer.post-activation-evidence/v1"
    assert envelope["contractVersion"] == 1
    assert envelope["evidenceKind"] == "horizon_live_readiness"
    assert envelope["evidenceId"] == "horizon-check-20260721"
    assert envelope["generatedAtUtc"] == receipt["generatedAtUtc"]
    assert envelope["status"] == "attention_required"
    assert envelope["secretRedacted"] is True
    assert envelope["operationalReadinessClaimAllowed"] is False
    assert envelope["releaseBinding"] == {
        "releaseVersion": expected["releaseVersion"],
        "generationId": expected["generationId"],
        "manifestSha256": expected["manifestSha256"],
        "decisionSha256": expected["releaseDecisionSha256"],
        "snapshotSha256": expected["authoritySnapshotSha256"],
        "targetPointerSha256": target_pointer_sha256,
    }
    assert envelope["claims"] == [
        {
            "claimId": "horizon_live_readiness_v1",
            "status": "attention_required",
            "evidenceSha256": verifier.sha256_bytes(receipt_bytes),
        }
    ]
    lowered = raw.lower()
    assert str(tmp_path).encode() not in raw
    assert b"authorization" not in lowered
    assert b"bearer" not in lowered
    assert b"credential" not in lowered
    assert b"password" not in lowered
    assert b"token" not in lowered

    allowed_output = tmp_path / "allowed-horizon-evidence.json"
    allowed_args = [
        "--evidence-output", str(allowed_output),
        "--evidence-id", "horizon-check-allowed-20260721",
        "--expected-target-pointer-sha256", target_pointer_sha256,
        "--allow-attention-required",
    ]
    assert verifier.main([*args, *allowed_args]) == 0
    assert allowed_output.exists()
    assert '"status": "pass"' in capsys.readouterr().out


def stat_mode(path):
    return os.stat(path, follow_symlinks=False).st_mode & 0o777


def test_evidence_output_is_create_exclusive_and_preserves_existing_file(
    tmp_path,
    capsys,
):
    args, _, _ = cli_fixture(tmp_path)
    output = tmp_path / "existing-evidence.json"
    output.write_bytes(b"existing\n")
    output.chmod(0o600)

    assert verifier.main(
        [
            *args,
            "--evidence-output", str(output),
            "--evidence-id", "horizon-existing-20260721",
            "--expected-target-pointer-sha256", "7" * 64,
            "--allow-attention-required",
        ]
    ) == 1
    assert output.read_bytes() == b"existing\n"
    assert "evidence_output:must_be_new" in capsys.readouterr().out


def test_evidence_adapter_cannot_widen_v1_to_ready():
    receipt = fixture_values()[0]
    envelope = verifier.build_post_activation_evidence(
        receipt,
        verifier.canonical_json_bytes(receipt),
        evidence_id="horizon-attention-only",
        target_pointer_sha256="7" * 64,
    )
    assert envelope["status"] == "attention_required"
    assert envelope["operationalReadinessClaimAllowed"] is False
    assert envelope["claims"][0]["status"] == "attention_required"

    receipt["status"] = "ready"
    receipt["operationalReadinessClaimAllowed"] = True
    with pytest.raises(verifier.VerificationError, match="not_attention_required"):
        verifier.build_post_activation_evidence(
            receipt,
            verifier.canonical_json_bytes(receipt),
            evidence_id="horizon-ready-refused",
            target_pointer_sha256="7" * 64,
        )


@pytest.mark.parametrize(
    "evidence_id",
    ["../escape", "has/slash", "has space", "x" * 129],
)
def test_evidence_adapter_rejects_unsafe_evidence_id(evidence_id):
    receipt = fixture_values()[0]
    with pytest.raises(verifier.VerificationError, match="evidence_id:invalid"):
        verifier.build_post_activation_evidence(
            receipt,
            verifier.canonical_json_bytes(receipt),
            evidence_id=evidence_id,
            target_pointer_sha256="7" * 64,
        )
