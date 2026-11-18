from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import struct
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_shelf_generation.py"
SPEC = importlib.util.spec_from_file_location("release_shelf_generation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FRESHNESS_EVALUATED_AT = datetime(
    2026,
    7,
    24,
    12,
    40,
    tzinfo=timezone.utc,
)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _proof_age_seconds(later: datetime, earlier: datetime) -> int:
    return 0 if later <= earlier else int((later - earlier).total_seconds() // 1)


def _create_localization_gate(generated_at: datetime) -> dict[str, object]:
    locales = ["en-us", "de-de", "fr-fr", "ja-jp", "pt-br", "zh-cn"]
    domains = [
        "app_chrome",
        "install_update_support",
        "explain_receipts",
        "data_rules_names",
        "generated_artifacts",
    ]
    return {
        "status": "pass",
        "generatedAt": _format_utc(generated_at),
        "defaultKeyCount": 441,
        "explicitFallbackRuntime": "pass",
        "signoffSmokeRunnerStatus": "pass",
        "shippingLocales": locales,
        "acceptanceGates": [
            "pseudo_localization",
            "missing_key_fail_fast",
            "top_surface_overflow_checks",
            "locale_smoke_first_launch",
            "locale_smoke_settings",
            "locale_smoke_explain",
            "locale_smoke_updater",
            "locale_smoke_support",
            "non_english_generated_artifact_smoke",
        ],
        "domainCoverage": {domain: "pass" for domain in domains},
        "localeDomainCoverage": {
            locale: {domain: "pass" for domain in domains}
            for locale in locales
        },
        "blockingFindingsCount": 0,
        "blockingFindings": [],
        "translationBacklogFindingsCount": 0,
        "translationBacklogFindings": [],
        "localeSummary": [
            {
                "locale": locale,
                "untranslatedKeyCount": 0,
                "overrideCount": 441,
                "minimumOverrideCount": 441 if locale == "en-us" else 40,
                "missingReleaseSeedKeys": [],
                "legacyXmlPresent": True,
                "legacyDataXmlPresent": True,
            }
            for locale in locales
        ],
    }


def _create_flagship_readiness(
    generated_at: datetime,
) -> dict[str, object]:
    digest_material: dict[str, object] = {
        "contractName": "chummer.flagship_product_readiness_gate.v1",
        "coverageGapKeys": [],
        "desktopClientReady": True,
        "generatedAt": _format_utc(generated_at),
        "launchBlockers": [],
        "reason": "Flagship product readiness proof is green.",
        "sourceSha256": (
            "sha256:"
            "0123456789abcdef0123456789abcdef"
            "0123456789abcdef0123456789abcdef"
        ),
        "status": "pass",
    }
    return {
        **digest_material,
        "snapshotSha256": (
            "sha256:"
            + hashlib.sha256(
                MODULE.canonical_json_bytes(digest_material)
            ).hexdigest()
        ),
    }


def _create_release_proof(generated_at: datetime) -> dict[str, object]:
    return {
        "status": "passed",
        "generatedAt": _format_utc(generated_at),
        "baseUrl": "https://chummer.run",
        "journeysPassed": [
            "install_claim_restore_continue",
            "build_explain_publish",
            "campaign_session_recover_recap",
            "report_cluster_release_notify",
            "organize_community_and_close_loop",
        ],
        "proofRoutes": [
            "/downloads/install/avalonia-linux-x64-installer",
            "/home/access",
            "/home/work",
            "/account/access",
            "/account/work",
            "/account/support",
            "/contact",
            "/downloads",
        ],
        "uiLocalizationReleaseGate": _create_localization_gate(generated_at),
        "flagshipReadiness": _create_flagship_readiness(generated_at),
    }


def _create_freshness_facts(
    release_proof: dict[str, object],
    published_at: datetime,
) -> dict[str, object]:
    release_generated_at = datetime.fromisoformat(
        str(release_proof["generatedAt"]).replace("Z", "+00:00")
    )
    localization = release_proof["uiLocalizationReleaseGate"]
    readiness = release_proof["flagshipReadiness"]
    assert isinstance(localization, dict)
    assert isinstance(readiness, dict)
    localization_generated_at = datetime.fromisoformat(
        str(localization["generatedAt"]).replace("Z", "+00:00")
    )
    readiness_generated_at = datetime.fromisoformat(
        str(readiness["generatedAt"]).replace("Z", "+00:00")
    )
    return {
        "status": "fresh",
        "releaseProofGeneratedAt": _format_utc(release_generated_at),
        "releaseProofAgeSeconds": _proof_age_seconds(
            published_at,
            release_generated_at,
        ),
        "releaseProofMaxAgeSeconds": MODULE.RELEASE_PROOF_MAXIMUM_AGE_SECONDS,
        "uiLocalizationGeneratedAt": _format_utc(localization_generated_at),
        "uiLocalizationAgeSeconds": _proof_age_seconds(
            published_at,
            localization_generated_at,
        ),
        "uiLocalizationMaxAgeSeconds": (
            MODULE.RELEASE_PROOF_MAXIMUM_AGE_SECONDS
        ),
        "flagshipReadinessGeneratedAt": _format_utc(
            readiness_generated_at
        ),
        "flagshipReadinessAgeSeconds": _proof_age_seconds(
            published_at,
            readiness_generated_at,
        ),
        "flagshipReadinessMaxAgeSeconds": (
            MODULE.RELEASE_PROOF_MAXIMUM_AGE_SECONDS
        ),
        "flagshipReadinessStatus": readiness["status"],
        "flagshipReadinessCoverageGapKeys": copy.deepcopy(
            readiness["coverageGapKeys"]
        ),
        "flagshipDesktopClientReady": readiness["desktopClientReady"],
        "flagshipReadinessSnapshotSha256": readiness["snapshotSha256"],
    }


def _create_fresh_release_payload(
    *,
    generated_at: datetime = FRESHNESS_EVALUATED_AT,
    published_at: datetime = FRESHNESS_EVALUATED_AT,
) -> dict[str, object]:
    release_proof = _create_release_proof(generated_at)
    return {
        "version": "run-proof-freshness",
        "channel": "preview",
        "publishedAt": _format_utc(published_at),
        "status": "published",
        "rolloutState": "public_stable",
        "supportabilityState": "gold_supported",
        "releaseProof": release_proof,
        "publicTrustMetrics": {
            "proofFreshness": _create_freshness_facts(
                release_proof,
                published_at,
            ),
        },
    }


def _clear_privacy_contract() -> dict[str, object]:
    contract = MODULE.load_privacy_launch_gate_contract()
    contract["status"] = "documented"
    contract["reviewRequired"] = False
    contract["blocksLaunch"] = False
    return contract


def _write_fresh_manifest_pair(
    root: Path,
    payload: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    canonical_path = root / MODULE.CANONICAL_MANIFEST
    compatibility_path = root / MODULE.COMPATIBILITY_MANIFEST
    common = copy.deepcopy(payload or _create_fresh_release_payload())
    canonical = {
        **copy.deepcopy(common),
        "artifacts": [
            {
                "artifactId": "avalonia-win-x64-installer",
                "fileName": "chummer.exe",
                "downloadUrl": "/downloads/files/chummer.exe",
                "installAccessClass": "open_public",
            }
        ],
    }
    compatibility = {
        **copy.deepcopy(common),
        "downloads": [
            {
                "id": "avalonia-win-x64-installer",
                "fileName": "chummer.exe",
                "url": "/downloads/files/chummer.exe",
                "installAccessClass": "open_public",
            }
        ],
    }
    canonical_path.write_text(json.dumps(canonical), encoding="utf-8")
    compatibility_path.write_text(
        json.dumps(compatibility),
        encoding="utf-8",
    )
    return canonical_path, compatibility_path


def _materialized_freshness_status(
    payload: dict[str, object],
    evaluated_at: datetime = FRESHNESS_EVALUATED_AT,
) -> str:
    projected = MODULE.apply_current_release_supportability_floor(
        payload,
        _clear_privacy_contract(),
        evaluated_at,
    )
    return projected["publicTrustMetrics"]["proofFreshness"]["status"]


def test_fresh_claim_without_release_proof_materializes_missing() -> None:
    payload = _create_fresh_release_payload()
    del payload["releaseProof"]

    assert _materialized_freshness_status(payload) == "missing"


def test_fresh_claim_missing_required_fact_materializes_missing() -> None:
    payload = _create_fresh_release_payload()
    proof_freshness = payload["publicTrustMetrics"]["proofFreshness"]
    del proof_freshness["flagshipReadinessSnapshotSha256"]

    assert _materialized_freshness_status(payload) == "missing"


def test_invalid_digest_bound_readiness_evidence_materializes_missing() -> None:
    payload = _create_fresh_release_payload()
    readiness = payload["releaseProof"]["flagshipReadiness"]
    readiness["snapshotSha256"] = "sha256:" + ("f" * 64)

    assert _materialized_freshness_status(payload) == "missing"


def test_freshness_timestamp_mismatch_materializes_stale() -> None:
    payload = _create_fresh_release_payload()
    proof_freshness = payload["publicTrustMetrics"]["proofFreshness"]
    proof_freshness["releaseProofGeneratedAt"] = _format_utc(
        FRESHNESS_EVALUATED_AT - timedelta(seconds=1)
    )
    proof_freshness["releaseProofAgeSeconds"] = 1

    assert _materialized_freshness_status(payload) == "stale"


@pytest.mark.parametrize(
    ("future_seconds", "expected_status"),
    ((300, "fresh"), (301, "stale")),
)
def test_freshness_future_skew_matches_runtime_boundary(
    future_seconds: int,
    expected_status: str,
) -> None:
    payload = _create_fresh_release_payload(
        generated_at=FRESHNESS_EVALUATED_AT
        + timedelta(seconds=future_seconds)
    )

    assert _materialized_freshness_status(payload) == expected_status


@pytest.mark.parametrize(
    ("elapsed_seconds", "expected_status"),
    (
        (MODULE.RELEASE_PROOF_MAXIMUM_AGE_SECONDS, "fresh"),
        (MODULE.RELEASE_PROOF_MAXIMUM_AGE_SECONDS + 1, "stale"),
    ),
)
def test_freshness_expiry_matches_runtime_boundary(
    elapsed_seconds: int,
    expected_status: str,
) -> None:
    generated_at = FRESHNESS_EVALUATED_AT - timedelta(
        seconds=MODULE.RELEASE_PROOF_MAXIMUM_AGE_SECONDS
    )
    payload = _create_fresh_release_payload(
        generated_at=generated_at,
        published_at=FRESHNESS_EVALUATED_AT,
    )

    assert (
        _materialized_freshness_status(
            payload,
            generated_at + timedelta(seconds=elapsed_seconds),
        )
        == expected_status
    )


def test_malformed_freshness_fact_materializes_stale() -> None:
    payload = _create_fresh_release_payload()
    payload["publicTrustMetrics"]["proofFreshness"][
        "uiLocalizationAgeSeconds"
    ] = "not-an-integer"

    assert _materialized_freshness_status(payload) == "stale"


def test_fresh_evidence_applies_only_the_current_privacy_blocker() -> None:
    payload = _create_fresh_release_payload()

    blocked = MODULE.apply_current_release_supportability_floor(
        payload,
        MODULE.load_privacy_launch_gate_contract(),
        FRESHNESS_EVALUATED_AT,
    )
    clear = MODULE.apply_current_release_supportability_floor(
        payload,
        _clear_privacy_contract(),
        FRESHNESS_EVALUATED_AT,
    )

    assert blocked["publicTrustMetrics"]["proofFreshness"]["status"] == "fresh"
    assert "Hosted Build privacy" in blocked["knownIssueSummary"]
    assert "stale or incomplete proof receipts" not in blocked["knownIssueSummary"]
    assert clear["publicTrustMetrics"]["proofFreshness"]["status"] == "fresh"
    assert clear["rolloutState"] == "public_stable"
    assert clear["supportabilityState"] == "gold_supported"
    assert "knownIssueSummary" not in clear


def test_project_manifest_pair_rejects_release_proof_evidence_disagreement_atomically(
    tmp_path: Path,
) -> None:
    canonical_path, compatibility_path = _write_fresh_manifest_pair(tmp_path)
    compatibility = json.loads(
        compatibility_path.read_text(encoding="utf-8")
    )
    compatibility["publicTrustMetrics"]["proofFreshness"][
        "releaseProofAgeSeconds"
    ] = 1
    compatibility_path.write_text(
        json.dumps(compatibility),
        encoding="utf-8",
    )
    before = canonical_path.read_bytes(), compatibility_path.read_bytes()

    with pytest.raises(
        MODULE.ReleaseShelfError,
        match="same release-proof freshness evidence",
    ):
        MODULE.project_manifest_pair(
            canonical_path,
            compatibility_path,
            "g-release-proof-evidence-disagreement",
            evaluated_at=FRESHNESS_EVALUATED_AT,
        )

    assert (canonical_path.read_bytes(), compatibility_path.read_bytes()) == before


def test_project_manifest_pair_is_byte_idempotent_at_one_evaluation_instant(
    tmp_path: Path,
) -> None:
    canonical_path, compatibility_path = _write_fresh_manifest_pair(tmp_path)

    first_receipt = MODULE.project_manifest_pair(
        canonical_path,
        compatibility_path,
        "g-fresh-byte-idempotence",
        evaluated_at=FRESHNESS_EVALUATED_AT,
    )
    first_bytes = canonical_path.read_bytes(), compatibility_path.read_bytes()
    second_receipt = MODULE.project_manifest_pair(
        canonical_path,
        compatibility_path,
        "g-fresh-byte-idempotence",
        evaluated_at=FRESHNESS_EVALUATED_AT,
    )

    assert (canonical_path.read_bytes(), compatibility_path.read_bytes()) == (
        first_bytes
    )
    assert second_receipt == first_receipt
    assert first_receipt["supportabilityFloorEvaluatedAt"] == _format_utc(
        FRESHNESS_EVALUATED_AT
    )


def test_privacy_contract_snapshot_binds_projection_and_receipt_without_post_replace_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_path, compatibility_path = _write_fresh_manifest_pair(tmp_path)
    source_contract_path = MODULE.PRIVACY_LAUNCH_GATE_CONTRACT
    contract_path = tmp_path / "PRIVACY_LAUNCH_GATE.json"
    contract_a_bytes = source_contract_path.read_bytes()
    contract_a = json.loads(contract_a_bytes.decode("utf-8"))
    contract_path.write_bytes(contract_a_bytes)
    contract_b = copy.deepcopy(contract_a)
    contract_b["reason"] = contract_b["reason"] + " Mutation sentinel."
    contract_b_bytes = (
        json.dumps(contract_b, indent=2, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )
    monkeypatch.setattr(MODULE, "PRIVACY_LAUNCH_GATE_CONTRACT", contract_path)

    original_read_bytes = Path.read_bytes
    original_open = Path.open
    contract_reads = 0
    contract_mutated = False

    def fail_on_contract_reread(path: Path) -> bytes:
        nonlocal contract_reads
        if path == contract_path:
            contract_reads += 1
            if contract_reads > 1:
                raise OSError("privacy contract was read after projection began")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_on_contract_reread)

    def fail_on_post_replace_contract_open(
        path: Path,
        *args: object,
        **kwargs: object,
    ):
        if path == contract_path and contract_mutated:
            raise OSError("privacy contract was opened after manifest replacement")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_on_post_replace_contract_open)
    original_replace = MODULE.os.replace

    def mutate_contract_after_first_destination_replace(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
    ) -> None:
        nonlocal contract_mutated
        original_replace(source, destination)
        if Path(destination) == canonical_path and not contract_mutated:
            contract_path.write_bytes(contract_b_bytes)
            contract_mutated = True

    monkeypatch.setattr(
        MODULE.os,
        "replace",
        mutate_contract_after_first_destination_replace,
    )

    receipt = MODULE.project_manifest_pair(
        canonical_path,
        compatibility_path,
        "g-privacy-snapshot-binding",
        evaluated_at=FRESHNESS_EVALUATED_AT,
    )

    assert contract_mutated
    assert contract_reads == 1
    assert receipt["privacyLaunchGateContractSha256"] == hashlib.sha256(
        contract_a_bytes
    ).hexdigest()
    assert receipt["privacyLaunchGateContractSha256"] != hashlib.sha256(
        contract_b_bytes
    ).hexdigest()
    for path in (canonical_path, compatibility_path):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["publicTrustMetrics"]["privacyReadiness"] == contract_a


def test_project_manifest_pair_binds_exact_generation_without_copying_artifacts(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    compatibility_path = tmp_path / "releases.json"
    source = {
        "version": "run-20260720-nightly",
        "channel": "preview",
        "publishedAt": "2026-07-20T20:00:00Z",
        "downloads": [
            {
                "id": "avalonia-osx-arm64",
                "fileName": "chummer.dmg",
                "url": "/downloads/files/chummer.dmg",
                "installAccessClass": "open_public",
            }
        ],
    }
    canonical_path.write_text(json.dumps(source), encoding="utf-8")
    compatibility_path.write_text(json.dumps(source), encoding="utf-8")

    receipt = MODULE.project_manifest_pair(
        canonical_path,
        compatibility_path,
        "gen-run-20260720-nightly-abcdef0123456789",
    )

    expected_route = (
        "/downloads/g/gen-run-20260720-nightly-abcdef0123456789/"
        "files/chummer.dmg"
    )
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    assert canonical == compatibility
    assert canonical["generationId"] == receipt["generationId"]
    assert canonical["downloads"][0]["url"] == expected_route
    assert receipt["canonicalManifestSha256"] == MODULE.sha256_file(canonical_path)
    assert receipt["compatibilityManifestSha256"] == MODULE.sha256_file(
        compatibility_path
    )
    assert stat.S_IMODE(canonical_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(compatibility_path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".*.generation-*"))


def test_project_manifest_pair_rejects_release_identity_drift_without_mutation(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    compatibility_path = tmp_path / "releases.json"
    canonical_path.write_text(
        json.dumps(
            {
                "version": "run-one",
                "channel": "preview",
                "publishedAt": "2026-07-20T20:00:00Z",
                "downloads": [],
            }
        ),
        encoding="utf-8",
    )
    compatibility_path.write_text(
        json.dumps(
            {
                "version": "run-two",
                "channel": "preview",
                "publishedAt": "2026-07-20T20:00:00Z",
                "downloads": [],
            }
        ),
        encoding="utf-8",
    )
    before = (canonical_path.read_bytes(), compatibility_path.read_bytes())

    with pytest.raises(MODULE.ReleaseShelfError, match="same release identity"):
        MODULE.project_manifest_pair(
            canonical_path,
            compatibility_path,
            "gen-release-identity-drift",
        )

    assert (canonical_path.read_bytes(), compatibility_path.read_bytes()) == before


def _write_supportability_projection_pair(
    root: Path,
    *,
    proof_freshness_status: str = "missing",
    rollout_state: str = "public_release_review_required",
    rollout_reason: str = "Proof receipts are stale.",
    supportability_state: str = "review_required",
    supportability_summary: str = "Proof receipts require review.",
    known_issue_summary: str = (
        "Known issue: stale or incomplete proof receipts still block "
        "launch-readiness claims."
    ),
    fix_availability_summary: str = "Wait for current proof receipts.",
) -> tuple[Path, Path]:
    canonical_path = root / MODULE.CANONICAL_MANIFEST
    compatibility_path = root / MODULE.COMPATIBILITY_MANIFEST
    common = {
        "version": "run-supportability-floor",
        "channel": "preview",
        "publishedAt": "2026-07-24T12:40:00Z",
        "status": "published",
        "rolloutState": rollout_state,
        "rolloutReason": rollout_reason,
        "supportabilityState": supportability_state,
        "supportabilitySummary": supportability_summary,
        "knownIssueSummary": known_issue_summary,
        "fixAvailabilitySummary": fix_availability_summary,
        "publicTrustMetrics": {
            "proofFreshness": {
                "status": proof_freshness_status,
                "stableFact": "unchanged",
            },
            "releaseChannel": {
                "rolloutState": rollout_state,
                "supportabilityState": supportability_state,
                "posture": "blocked",
                "summary": "Proof receipts require review.",
                "stableCount": 7,
            },
            "stableMetric": {"value": "unchanged"},
        },
        "registryBoundaryCoverage": {
            "releaseChannel": {
                "rolloutState": rollout_state,
                "supportabilityState": supportability_state,
                "publicTrustPosture": "blocked",
                "summary": "Registry proof receipts require review.",
                "stableCount": 11,
            },
            "stableBoundary": True,
        },
        "stableUnrelated": {
            "text": "unchanged",
            "count": 42,
            "enabled": True,
        },
    }
    canonical = {
        **common,
        "artifacts": [
            {
                "artifactId": "avalonia-win-x64-installer",
                "fileName": "chummer.exe",
                "downloadUrl": "/downloads/files/chummer.exe",
                "installAccessClass": "open_public",
                "stableArtifactFact": "unchanged",
            }
        ],
    }
    compatibility = {
        **common,
        "downloads": [
            {
                "id": "avalonia-win-x64-installer",
                "fileName": "chummer.exe",
                "url": "/downloads/files/chummer.exe",
                "installAccessClass": "open_public",
                "stableArtifactFact": "unchanged",
            }
        ],
    }
    canonical_path.write_text(json.dumps(canonical), encoding="utf-8")
    compatibility_path.write_text(json.dumps(compatibility), encoding="utf-8")
    return canonical_path, compatibility_path


def _mark_pair_as_bounded_preview_ready(
    paths: tuple[Path, Path],
) -> None:
    release_version = "run-supportability-floor"
    registry_commit = "a" * 40
    readiness = {
        "contractName": "chummer.registry.preview-publication-readiness/v1",
        "contractVersion": 1,
        "generatedAtUtc": "2026-07-24T12:40:00Z",
        "localizationGateSha256": "1" * 64,
        "nativeWindowsEvidenceSha256": "2" * 64,
        "platforms": ["linux", "windows"],
        "registryCommit": registry_commit,
        "releaseProofSha256": "3" * 64,
        "releaseVersion": release_version,
        "sourceCandidateAuthoritySha256": "4" * 64,
        "sourceCanonicalManifestSha256": "5" * 64,
        "sourceCompatibilityManifestSha256": "6" * 64,
        "status": "preview_ready",
    }
    primary_rows = [
        {
            "head": "avalonia",
            "platform": "linux",
            "promotionState": "promoted",
            "publicationState": "published",
            "revokeState": "not_revoked",
            "rid": "linux-x64",
            "routeAuthority": True,
            "routeRole": "primary",
            "tupleId": "avalonia:linux:linux-x64",
            "updateEligibility": "eligible",
        },
        {
            "head": "avalonia",
            "platform": "windows",
            "promotionState": "promoted",
            "publicationState": "published",
            "revokeState": "not_revoked",
            "rid": "win-x64",
            "routeAuthority": True,
            "routeRole": "primary",
            "tupleId": "avalonia:windows:win-x64",
            "updateEligibility": "eligible",
        },
    ]
    promoted = [
        {
            "head": row["head"],
            "kind": "installer",
            "platform": row["platform"],
            "tupleId": row["tupleId"],
        }
        for row in primary_rows
    ]
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(
            {
                "version": release_version,
                "releaseVersion": release_version,
                "channelId": "preview",
                "projectionProfile": "v4_unsigned_windows_preview_ready",
                "rolloutState": "promoted_preview",
                "supportabilityState": "preview_supported",
                "publicationEligible": True,
                "routeAuthority": True,
                "releaseUploadAuthority": False,
                "deployAuthority": False,
                "registryCommit": registry_commit,
                "previewPublicationReadiness": copy.deepcopy(readiness),
                "desktopTupleCoverage": {
                    "complete": True,
                    "desktopRouteTruth": copy.deepcopy(primary_rows),
                    "externalProofRequests": [],
                    "missingRequiredHeads": [],
                    "missingRequiredPlatformHeadPairs": [],
                    "missingRequiredPlatformHeadRidTuples": [],
                    "missingRequiredPlatforms": [],
                    "promotedInstallerTuples": copy.deepcopy(promoted),
                    "requiredDesktopHeads": ["avalonia"],
                    "requiredDesktopPlatforms": ["linux", "windows"],
                    "routeAuthority": True,
                },
            }
        )
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_generation_projection_preserves_exact_bounded_preview_ready_posture(
    tmp_path: Path,
) -> None:
    paths = _write_supportability_projection_pair(tmp_path)
    _mark_pair_as_bounded_preview_ready(paths)
    source_trust_metrics = [
        copy.deepcopy(json.loads(path.read_text(encoding="utf-8"))["publicTrustMetrics"])
        for path in paths
    ]

    receipt = MODULE.project_manifest_pair(
        *paths,
        "g-bounded-preview-ready",
        evaluated_at=FRESHNESS_EVALUATED_AT,
    )

    for path, expected_trust_metrics in zip(paths, source_trust_metrics, strict=True):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["rolloutState"] == "promoted_preview"
        assert manifest["supportabilityState"] == "preview_supported"
        assert manifest["publicationEligible"] is True
        assert manifest["routeAuthority"] is True
        assert manifest["releaseUploadAuthority"] is False
        assert manifest["deployAuthority"] is False
        assert manifest["publicTrustMetrics"] == expected_trust_metrics
        assert "privacyReadiness" not in manifest["publicTrustMetrics"]
    assert receipt["supportabilityFloorApplied"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("releaseUploadAuthority", True),
        ("routeAuthority", False),
    ),
)
def test_generation_projection_rejects_broadened_bounded_preview_profile(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    paths = _write_supportability_projection_pair(tmp_path)
    _mark_pair_as_bounded_preview_ready(paths)
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload[field] = value
        path.write_text(json.dumps(payload), encoding="utf-8")

    MODULE.project_manifest_pair(
        *paths,
        "g-bounded-preview-broadened",
        evaluated_at=FRESHNESS_EVALUATED_AT,
    )

    for path in paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["rolloutState"] == "public_release_review_required"
        assert manifest["supportabilityState"] == "review_required"


def test_project_manifest_pair_materializes_exact_runtime_privacy_floor(
    tmp_path: Path,
) -> None:
    canonical_path, compatibility_path = _write_supportability_projection_pair(
        tmp_path
    )

    receipt = MODULE.project_manifest_pair(
        canonical_path,
        compatibility_path,
        "g-runtime-privacy-floor",
    )

    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    expected_blocker = (
        "stale or incomplete proof receipts and Hosted Build privacy, retention, "
        "recovery, and erasure review still block launch-readiness claims"
    )
    expected_known_issue = f"Known issue: {expected_blocker}."
    expected_privacy = json.loads(
        MODULE.PRIVACY_LAUNCH_GATE_CONTRACT.read_text(encoding="utf-8")
    )

    for manifest in (canonical, compatibility):
        assert manifest["rolloutState"] == "public_release_review_required"
        assert manifest["supportabilityState"] == "review_required"
        assert manifest["knownIssueSummary"] == expected_known_issue
        assert manifest["rolloutReason"] == (
            "Current shelf is published, but release posture stays review-required "
            f"because {expected_blocker}."
        )
        assert manifest["supportabilitySummary"] == (
            f"Treat the current release as review-required because {expected_blocker}."
        )
        assert manifest["publicTrustMetrics"]["privacyReadiness"] == expected_privacy
        assert (
            manifest["publicTrustMetrics"]["releaseChannel"]["summary"]
            == f"Release channel remains review-required because {expected_blocker}."
        )
        assert (
            manifest["registryBoundaryCoverage"]["releaseChannel"]["summary"]
            == "Release-channel truth remains review-required because "
            f"{expected_blocker}."
        )
        assert manifest["stableUnrelated"] == {
            "text": "unchanged",
            "count": 42,
            "enabled": True,
        }
        assert manifest["publicTrustMetrics"]["stableMetric"] == {
            "value": "unchanged"
        }
        assert manifest["publicTrustMetrics"]["proofFreshness"]["stableFact"] == (
            "unchanged"
        )

    assert MODULE._supportability_floor_projection(
        canonical
    ) == MODULE._supportability_floor_projection(compatibility)
    assert (
        canonical["artifacts"][0]["stableArtifactFact"]
        == compatibility["downloads"][0]["stableArtifactFact"]
        == "unchanged"
    )
    assert receipt["supportabilityFloorApplied"] is True
    assert (
        receipt["privacyLaunchGateContractName"]
        == expected_privacy["contractName"]
    )
    assert receipt["privacyLaunchGateContractVersion"] == 2
    assert receipt["privacyLaunchGateContractSha256"] == MODULE.sha256_file(
        MODULE.PRIVACY_LAUNCH_GATE_CONTRACT
    )


def test_current_release_supportability_floor_is_idempotent_without_duplicates() -> None:
    contract = MODULE.load_privacy_launch_gate_contract()
    source = {
        "status": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "publicTrustMetrics": {
            "proofFreshness": {"status": "missing"},
        },
    }

    once = MODULE.apply_current_release_supportability_floor(source, contract)
    twice = MODULE.apply_current_release_supportability_floor(once, contract)

    assert twice == once
    for field in (
        "rolloutReason",
        "supportabilitySummary",
        "knownIssueSummary",
    ):
        assert once[field].count("Hosted Build privacy") == 1
        assert once[field].count("stale or incomplete proof receipts") == 1
    assert (
        once["publicTrustMetrics"]["releaseChannel"]["summary"].count(
            "Hosted Build privacy"
        )
        == 1
    )
    assert (
        once["registryBoundaryCoverage"]["releaseChannel"]["summary"].count(
            "Hosted Build privacy"
        )
        == 1
    )


def test_project_manifest_pair_preserves_stronger_blocker_narratives(
    tmp_path: Path,
) -> None:
    narratives = {
        "rollout_reason": "Required desktop coverage is incomplete.",
        "supportability_summary": "The Windows installer is still missing.",
        "known_issue_summary": "Windows remains unavailable.",
        "fix_availability_summary": "Wait for the Windows candidate.",
    }
    canonical_path, compatibility_path = _write_supportability_projection_pair(
        tmp_path,
        rollout_state="coverage_incomplete",
        **narratives,
    )
    for path, public_summary, registry_summary in (
        (
            canonical_path,
            "Public channel coverage is incomplete.",
            "Registry coverage is incomplete.",
        ),
        (
            compatibility_path,
            "Public channel coverage is incomplete.",
            "Registry coverage is incomplete.",
        ),
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["publicTrustMetrics"]["releaseChannel"]["summary"] = public_summary
        payload["registryBoundaryCoverage"]["releaseChannel"][
            "summary"
        ] = registry_summary
        path.write_text(json.dumps(payload), encoding="utf-8")

    MODULE.project_manifest_pair(
        canonical_path,
        compatibility_path,
        "g-stronger-supportability-blocker",
    )

    for path in (canonical_path, compatibility_path):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["rolloutState"] == "coverage_incomplete"
        assert manifest["rolloutReason"] == narratives["rollout_reason"]
        assert (
            manifest["supportabilitySummary"]
            == narratives["supportability_summary"]
        )
        assert manifest["knownIssueSummary"] == narratives["known_issue_summary"]
        assert (
            manifest["fixAvailabilitySummary"]
            == narratives["fix_availability_summary"]
        )
        assert (
            manifest["publicTrustMetrics"]["releaseChannel"]["summary"]
            == "Public channel coverage is incomplete."
        )
        assert (
            manifest["registryBoundaryCoverage"]["releaseChannel"]["summary"]
            == "Registry coverage is incomplete."
        )
        assert manifest["publicTrustMetrics"]["privacyReadiness"][
            "blocksLaunch"
        ]


def test_project_manifest_pair_rejects_supportability_projection_drift_atomically(
    tmp_path: Path,
) -> None:
    canonical_path, compatibility_path = _write_supportability_projection_pair(
        tmp_path
    )
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical["rolloutState"] = "security_hold"
    canonical["knownIssueSummary"] = "Security review remains open."
    canonical_path.write_text(json.dumps(canonical), encoding="utf-8")
    before = canonical_path.read_bytes(), compatibility_path.read_bytes()

    with pytest.raises(
        MODULE.ReleaseShelfError,
        match="same runtime supportability-floor projection",
    ):
        MODULE.project_manifest_pair(
            canonical_path,
            compatibility_path,
            "g-supportability-projection-drift",
        )

    assert (canonical_path.read_bytes(), compatibility_path.read_bytes()) == before


def install_fake_conditional_s3_cli(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_aws = fake_bin / "aws"
    fake_aws.write_text(
        """#!/usr/bin/env python3
import fcntl
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

remote = Path(os.environ["FAKE_AWS_ROOT"])
public = Path(os.environ["FAKE_PUBLIC_ROOT"])
latest_public = Path(os.environ["FAKE_LATEST_PUBLIC_ROOT"])
log = Path(os.environ["FAKE_AWS_LOG"])
args = sys.argv[1:]
remote.mkdir(parents=True, exist_ok=True)

def option(name):
    return args[args.index(name) + 1]

def s3_path(uri):
    raw = uri[len("s3://"):]
    bucket, _, key = raw.partition("/")
    return remote / bucket / key, bucket, key

def etag(path):
    return '"' + hashlib.sha256(path.read_bytes()).hexdigest() + '"'

def record(text):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(text + "\\n")
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

def mirror_public(source, key):
    target = None
    if "/generations/" in key:
        prefix, relative = key.split("/generations/", 1)
        generation_id, _, generation_relative = relative.partition("/")
        if prefix == "downloads":
            target = public / "g" / generation_id / generation_relative
        elif prefix == "latest":
            target = latest_public / "g" / generation_id / generation_relative
    elif key == "downloads/current.json":
        target = public / "current.json"
    elif key == "latest/current.json":
        target = latest_public / "current.json"
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + f".tmp-{os.getpid()}")
        shutil.copy2(source, temp)
        os.replace(temp, target)

if args[:2] == ["s3api", "head-object"]:
    bucket = option("--bucket")
    key = option("--key")
    path = remote / bucket / key
    record(f"HEAD {key}")
    if not path.is_file():
        raise SystemExit(255)
    metadata_path = Path(str(path) + ".metadata.json")
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    print(json.dumps({"ContentLength": path.stat().st_size, "Metadata": metadata, "ETag": etag(path)}))
    raise SystemExit(0)

if args[:2] == ["s3api", "list-objects-v2"]:
    bucket = option("--bucket")
    prefix = option("--prefix")
    max_keys = int(option("--max-keys"))
    bucket_root = remote / bucket
    inject_key = os.environ.get("FAKE_AWS_INJECT_ON_SECOND_ROOT_LIST", "")
    inject_prefix = os.environ.get("FAKE_AWS_ROOT_INVENTORY_PREFIX", "downloads")
    if inject_key and prefix == inject_prefix:
        counter_path = remote / ".root-inventory-count"
        with counter_path.open("a+b") as counter:
            fcntl.flock(counter.fileno(), fcntl.LOCK_EX)
            counter.seek(0)
            raw_count = counter.read().decode("ascii")
            count = int(raw_count or "0") + 1
            counter.seek(0)
            counter.truncate()
            counter.write(str(count).encode("ascii"))
            counter.flush()
            if count == 2:
                injected = remote / bucket / inject_key
                injected.parent.mkdir(parents=True, exist_ok=True)
                injected.write_bytes(b"concurrent legacy object")
            fcntl.flock(counter.fileno(), fcntl.LOCK_UN)
    contents = []
    if bucket_root.is_dir():
        for child in sorted(bucket_root.rglob("*")):
            if not child.is_file() or child.name.endswith(".metadata.json") or ".tmp-" in child.name:
                continue
            key = child.relative_to(bucket_root).as_posix()
            if key.startswith(prefix):
                contents.append({"Key": key})
    record(f"LIST {prefix}")
    selected = contents[:max_keys]
    print(json.dumps({
        "Contents": selected,
        "IsTruncated": len(contents) > len(selected),
        "KeyCount": len(selected),
    }))
    raise SystemExit(0)

if args[:2] == ["s3api", "put-object"]:
    bucket = option("--bucket")
    key = option("--key")
    source = Path(option("--body"))
    destination = remote / bucket / key
    fail_prefix = os.environ.get("FAKE_AWS_FAIL_PUT_PREFIX", "")
    if fail_prefix and key.startswith(fail_prefix):
        record(f"PUT_FAIL {key}")
        raise SystemExit(42)
    delay_ms = int(os.environ.get("FAKE_AWS_PUT_DELAY_MS", "0"))
    if delay_ms:
        time.sleep(delay_ms / 1000)
    lock_path = remote / ".conditional-put.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if "--if-none-match" in args and destination.exists():
            record(f"PUT_CONDITION_FAILED {key}")
            raise SystemExit(255)
        if "--if-match" in args:
            expected = option("--if-match")
            if not destination.is_file() or etag(destination) != expected:
                record(f"PUT_CONDITION_FAILED {key}")
                raise SystemExit(255)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name(destination.name + f".tmp-{os.getpid()}")
        shutil.copy2(source, temp)
        os.replace(temp, destination)
        metadata = {}
        if "--metadata" in args:
            raw = option("--metadata")
            metadata = dict(item.split("=", 1) for item in raw.split(",") if "=" in item)
        metadata_path = Path(str(destination) + ".metadata.json")
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        record(f"PUT {key}")
        mirror_public(destination, key)
        response_etag = etag(destination)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    print(json.dumps({"ETag": response_etag}))
    raise SystemExit(0)

if args[:2] == ["s3", "cp"]:
    source, destination = args[2], args[3]
    if not source.startswith("s3://"):
        raise SystemExit(f"legacy upload is forbidden in fake conditional S3: {args}")
    source_path, _, key = s3_path(source)
    if key == os.environ.get("FAKE_AWS_FAIL_GET_KEY", ""):
        record(f"GET_FAIL {key}")
        raise SystemExit(43)
    record(f"GET {key}")
    if not source_path.is_file():
        raise SystemExit(1)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    raise SystemExit(0)

raise SystemExit(f"unsupported fake aws invocation: {args}")
""",
        encoding="utf-8",
    )
    fake_aws.chmod(0o755)
    remote_root = tmp_path / "remote"
    public_root = tmp_path / "public"
    latest_public_root = tmp_path / "latest-public"
    log_path = tmp_path / "aws.log"
    return fake_bin, remote_root, public_root, latest_public_root, log_path


def write_s3_publish_bundle(
    root: Path,
    *,
    version: str,
    published_at: str,
    payload: bytes,
) -> Path:
    files = root / "files"
    files.mkdir(parents=True)
    artifact = files / "chummer-avalonia-osx-arm64-installer.dmg"
    artifact.write_bytes(payload)
    digest = MODULE.sha256_file(artifact)
    canonical = {
        "version": version,
        "releaseVersion": version,
        "channel": "preview",
        "publishedAt": published_at,
        "artifacts": [
            {
                "artifactId": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platform": "macos",
                "rid": "osx-arm64",
                "kind": "dmg",
                "fileName": artifact.name,
                "downloadUrl": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
            }
        ],
    }
    compatibility = {
        "version": version,
        "channel": "preview",
        "publishedAt": published_at,
        "downloads": [
            {
                "id": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platformId": "macos",
                "rid": "osx-arm64",
                "kind": "dmg",
                "fileName": artifact.name,
                "url": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
            }
        ],
    }
    (root / MODULE.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
    )
    (root / MODULE.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility, indent=2) + "\n", encoding="utf-8"
    )
    return root


def test_inventory_digest_matches_cross_language_golden_fixture() -> None:
    fixture = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "atomic_release_shelf_inventory_digest_v1.json"
        ).read_text(encoding="utf-8")
    )

    canonical = MODULE.canonical_json_bytes(fixture["inventory"])

    assert canonical == fixture["canonicalJson"].encode("utf-8")
    assert MODULE.inventory_digest(fixture["inventory"]) == fixture["sha256"]


def test_inventory_rejects_nonportable_unicode_paths_before_activation(tmp_path: Path) -> None:
    generation = tmp_path / "generation"
    files = generation / "files"
    files.mkdir(parents=True)
    (files / "über.bin").write_bytes(b"fixture")

    with pytest.raises(MODULE.ReleaseShelfError, match="not portable ASCII"):
        MODULE.build_inventory(generation)


def write_candidate(root: Path, version: str = "release-1", artifact: bytes = b"artifact-a") -> Path:
    files = root / "files"
    proof = root / "proof"
    smoke = root / "startup-smoke"
    evidence = root / "release-evidence"
    files.mkdir(parents=True)
    proof.mkdir()
    smoke.mkdir()
    evidence.mkdir()
    artifact_path = files / "chummer-test-installer.exe"
    artifact_path.write_bytes(artifact)
    digest = MODULE.sha256_file(artifact_path)
    published_at = "2026-07-15T12:00:00Z"
    canonical = {
        "version": version,
        "releaseVersion": version,
        "channel": "preview",
        "publishedAt": published_at,
        "artifacts": [
            {
                "artifactId": "test-installer",
                "fileName": artifact_path.name,
                "downloadUrl": f"/downloads/files/{artifact_path.name}",
                "sha256": digest,
                "sizeBytes": len(artifact),
                "installAccessClass": "open_public",
            }
        ],
        "proofUrl": "/downloads/proof/local.json",
        "smokeUrl": "/downloads/startup-smoke/test.json",
        "evidenceUrl": "/downloads/release-evidence/test.json",
    }
    compatibility = {
        "version": version,
        "channel": "preview",
        "publishedAt": "2026-07-15T12:00:00+00:00",
        "downloads": [
            {
                "id": "test-installer",
                "fileName": artifact_path.name,
                "url": f"/downloads/files/{artifact_path.name}",
                "sha256": digest,
                "sizeBytes": len(artifact),
                "installAccessClass": "open_public",
            }
        ],
    }
    (root / MODULE.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
    )
    (root / MODULE.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility, indent=2) + "\n", encoding="utf-8"
    )
    (proof / "local.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    (smoke / "test.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    (evidence / "test.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    return root


def _bootstrap_trailer(sidecar: dict[str, object]) -> bytes:
    # Literal contract from finalize-windows-bootstrap-installer.py, independent
    # of the shelf helper's validator. The ZIP is embedded by NSIS, not appended.
    return b"\nCHUMMER6_BOOTSTRAP_METADATA\n" + (
        f"payloadFileName={sidecar['fileName']}\n"
        f"payloadDownloadUrl={sidecar['downloadUrl']}\n"
        f"payloadSha256={sidecar['sha256']}\n"
        f"payloadSizeBytes={sidecar['sizeBytes']}\n"
        f"payloadAcquisitionMode={sidecar['payloadAcquisitionMode']}\n"
    ).encode("utf-8")


@pytest.mark.parametrize(
    ("acquisition_mode", "finalized"),
    [("download", False), (None, False), ("download", True), ("embedded", True)],
)
def test_prepare_sidecar_accepts_exact_owner_read_only_five_file_candidate_without_source_mutation(
    tmp_path: Path,
    acquisition_mode: str | None,
    finalized: bool,
) -> None:
    candidate = tmp_path / "candidate"
    files = candidate / "files"
    files.mkdir(parents=True)
    installer_name = "chummer-avalonia-win-x64-installer.exe"
    payload_name = "chummer-avalonia-win+x64-payload.zip"
    metadata_name = f"{payload_name}.json"
    installer = files / installer_name
    payload = files / payload_name
    metadata = files / metadata_name
    installer.write_bytes(b"fixture installer")
    payload.write_bytes(b"fixture payload")
    source_sidecar = {
        "contractName": MODULE.PAYLOAD_SIDECAR_CONTRACT,
        "fileName": payload_name,
        "downloadUrl": (
            f"https://chummer.run/downloads/files/{payload_name}"
        ),
        "sha256": MODULE.sha256_file(payload),
        "sizeBytes": payload.stat().st_size,
        "installerFileName": installer_name,
        "releaseVersion": "run-read-only-five-file",
        "payloadAcquisitionMode": acquisition_mode,
    }
    metadata.write_text(
        json.dumps(source_sidecar, indent=2) + "\n",
        encoding="utf-8",
    )
    if finalized:
        installer.write_bytes(installer.read_bytes() + _bootstrap_trailer(source_sidecar))

    artifact = {
        "artifactId": "avalonia-win-x64-installer",
        "fileName": installer_name,
        "downloadUrl": f"/downloads/files/{installer_name}",
        "sha256": MODULE.sha256_file(installer),
        "sizeBytes": installer.stat().st_size,
        "installAccessClass": "open_public",
        "payloadFileName": payload_name,
        "payloadDownloadUrl": f"/downloads/files/{payload_name}",
        "payloadSha256": MODULE.sha256_file(payload),
        "payloadSizeBytes": payload.stat().st_size,
        "payloadMetadataFileName": metadata_name,
        "payloadMetadataUrl": f"/downloads/files/{metadata_name}",
    }
    if finalized:
        artifact.update(installerMode="bootstrap", payloadAcquisitionMode=acquisition_mode)
    canonical = {
        "version": "run-read-only-five-file",
        "releaseVersion": "run-read-only-five-file",
        "channel": "preview",
        "publishedAt": "2026-07-24T08:00:00Z",
        "artifacts": [artifact],
    }
    compatibility_artifact = dict(artifact)
    compatibility_artifact["id"] = compatibility_artifact.pop("artifactId")
    compatibility_artifact["url"] = compatibility_artifact.pop("downloadUrl")
    compatibility = {
        "version": "run-read-only-five-file",
        "channel": "preview",
        "publishedAt": "2026-07-24T08:00:00Z",
        "downloads": [compatibility_artifact],
    }
    (candidate / MODULE.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical, indent=2) + "\n",
        encoding="utf-8",
    )
    (candidate / MODULE.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility, indent=2) + "\n",
        encoding="utf-8",
    )

    source_files = sorted(path for path in candidate.rglob("*") if path.is_file())
    assert {
        path.relative_to(candidate).as_posix() for path in source_files
    } == {
        MODULE.CANONICAL_MANIFEST,
        MODULE.COMPATIBILITY_MANIFEST,
        f"files/{installer_name}",
        f"files/{payload_name}",
        f"files/{metadata_name}",
    }
    for path in source_files:
        path.chmod(0o400)
    files.chmod(0o700)
    candidate.chmod(0o700)
    source_entries = [candidate, *sorted(candidate.rglob("*"))]
    source_snapshot = {
        path.relative_to(candidate).as_posix(): (
            path.is_dir(),
            path.read_bytes() if path.is_file() else None,
            MODULE.sha256_file(path) if path.is_file() else None,
            stat.S_IMODE(path.stat().st_mode),
            path.stat().st_mtime_ns,
            path.stat().st_ino,
        )
        for path in source_entries
    }

    prepared = tmp_path / "prepared"
    receipt = MODULE.prepare_sidecar_active_layout(
        candidate,
        prepared,
        generation_id="generation-read-only-five-file",
        activated_at="2026-07-24T08:30:00Z",
        activation_receipt_id="receipt-read-only-five-file",
    )

    pointer = receipt["pointer"]
    generation = (
        prepared
        / MODULE.GENERATIONS_DIRECTORY
        / "generation-read-only-five-file"
    )
    MODULE.verify_generation(generation, pointer)
    state, resolved, resolved_pointer = MODULE.resolve_shelf_root(prepared)
    assert state == "generation"
    assert resolved == generation
    assert resolved_pointer == pointer
    assert pointer["manifests"]["canonical"]["sha256"] == MODULE.sha256_file(
        generation / MODULE.CANONICAL_MANIFEST
    )
    assert pointer["manifests"]["compatibility"]["sha256"] == MODULE.sha256_file(
        generation / MODULE.COMPATIBILITY_MANIFEST
    )
    assert MODULE.sha256_file(generation / "files" / installer_name) == MODULE.sha256_file(
        installer
    )
    assert MODULE.sha256_file(generation / "files" / payload_name) == MODULE.sha256_file(
        payload
    )
    generation_sidecar = generation / "files" / metadata_name
    expected_payload_url = (
        "https://chummer.run/downloads/g/"
        f"generation-read-only-five-file/files/{payload_name}"
    )
    expected_sidecar = {
        **source_sidecar,
        "payloadAcquisitionMode": acquisition_mode or "download",
        "downloadUrl": (
            source_sidecar["downloadUrl"] if acquisition_mode == "embedded" else expected_payload_url
        ),
    }
    assert generation_sidecar.read_bytes() == (
        json.dumps(expected_sidecar, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    assert (MODULE.sha256_file(generation_sidecar) == MODULE.sha256_file(metadata)) == (
        acquisition_mode == "embedded"
    )

    projected_canonical = json.loads(
        (generation / MODULE.CANONICAL_MANIFEST).read_text(encoding="utf-8")
    )
    projected_compatibility = json.loads(
        (generation / MODULE.COMPATIBILITY_MANIFEST).read_text(encoding="utf-8")
    )
    expected_relative_payload_url = expected_payload_url.removeprefix(
        MODULE.CANONICAL_PUBLIC_ORIGIN
    )
    assert (
        projected_canonical["artifacts"][0]["payloadDownloadUrl"]
        == expected_relative_payload_url
    )
    assert (
        projected_compatibility["downloads"][0]["payloadDownloadUrl"]
        == expected_relative_payload_url
    )

    activation_candidate = json.loads(
        (generation / MODULE.ACTIVATION_CANDIDATE).read_text(encoding="utf-8")
    )
    sidecar_inventory = next(
        row
        for row in activation_candidate["inventory"]
        if row["path"] == f"files/{metadata_name}"
    )
    assert sidecar_inventory["sha256"] == MODULE.sha256_file(
        generation_sidecar
    )

    assert stat.S_IMODE(candidate.stat().st_mode) == 0o700
    assert stat.S_IMODE(files.stat().st_mode) == 0o700
    assert {
        path.relative_to(candidate).as_posix(): (
            path.is_dir(),
            path.read_bytes() if path.is_file() else None,
            MODULE.sha256_file(path) if path.is_file() else None,
            stat.S_IMODE(path.stat().st_mode),
            path.stat().st_mtime_ns,
            path.stat().st_ino,
        )
        for path in source_entries
    } == source_snapshot
    assert all(
        stat.S_IMODE(path.stat().st_mode) == MODULE.SEALED_DIRECTORY_MODE
        for path in (generation, generation / "files")
    )
    assert all(
        stat.S_IMODE((generation / name).stat().st_mode)
        == MODULE.PUBLIC_METADATA_FILE_MODE
        for name in (
            MODULE.ACTIVATION_CANDIDATE,
            MODULE.CANONICAL_MANIFEST,
            MODULE.COMPATIBILITY_MANIFEST,
        )
    )
    assert all(
        stat.S_IMODE((generation / "files" / name).stat().st_mode)
        == MODULE.SEALED_FILE_MODE
        for name in (installer_name, payload_name, metadata_name)
    )
    assert receipt["canonicalMirrorSha256"] == MODULE.sha256_file(
        candidate / MODULE.CANONICAL_MANIFEST
    )
    assert receipt["compatibilityMirrorSha256"] == MODULE.sha256_file(
        candidate / MODULE.COMPATIBILITY_MANIFEST
    )
    MODULE.verify_generation(generation, pointer)
    generation_sidecar.chmod(0o600)
    generation_sidecar.write_bytes(generation_sidecar.read_bytes() + b" ")
    generation_sidecar.chmod(MODULE.SEALED_FILE_MODE)
    with pytest.raises(MODULE.ReleaseShelfError, match="inventory"):
        MODULE.verify_generation(generation, pointer)


def _write_embedded_bootstrap_candidate(root: Path) -> Path:
    candidate = write_candidate(root)
    files = candidate / "files"
    installer = files / "chummer-test-installer.exe"
    payload = files / "test-payload.zip"
    payload.write_bytes(b"fixture ZIP identity")
    sidecar = {
        "contractName": MODULE.PAYLOAD_SIDECAR_CONTRACT,
        "fileName": payload.name,
        "downloadUrl": f"https://chummer.run/downloads/files/{payload.name}",
        "sha256": MODULE.sha256_file(payload),
        "sizeBytes": payload.stat().st_size,
        "installerFileName": installer.name,
        "releaseVersion": "release-1",
        "payloadAcquisitionMode": "embedded",
    }
    installer.write_bytes(b"fixture NSIS bytes" + _bootstrap_trailer(sidecar))
    (files / f"{payload.name}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    for name, collection in (
        (MODULE.CANONICAL_MANIFEST, "artifacts"),
        (MODULE.COMPATIBILITY_MANIFEST, "downloads"),
    ):
        manifest_path = candidate / name
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest[collection][0].update(
            sha256=MODULE.sha256_file(installer), sizeBytes=installer.stat().st_size,
            installerMode="bootstrap", payloadAcquisitionMode="embedded",
            installAccessClass="open_public", payloadFileName=payload.name,
            payloadDownloadUrl=f"/downloads/files/{payload.name}",
            payloadSha256=sidecar["sha256"], payloadSizeBytes=sidecar["sizeBytes"],
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return candidate


@pytest.mark.parametrize("mutation", [
    "sidecar-mode", "compatibility-mode", "canonical-mode", "relabel-as-download",
    "binary-mode", "binary-digest", "binary-size", "missing-trailer", "duplicate-trailer",
    "trailing-bytes", "sidecar-digest", "sidecar-size", "sidecar-float-size",
    "sidecar-private-field", "sidecar-duplicate-field", "sidecar-oversize",
    "sidecar-relative-url", "sidecar-foreign-url",
    "sidecar-query", "sidecar-encoded-path", "sidecar-generation-url",
    "sidecar-installer-name", "sidecar-version", "payload-traversal",
    "corrupt-installer", "corrupt-payload", "canonical-payload-identity",
])
def test_generation_rejects_embedded_bootstrap_identity_or_metadata_rewrite(
    tmp_path: Path, mutation: str,
) -> None:
    candidate = _write_embedded_bootstrap_candidate(tmp_path / "candidate")
    files = candidate / "files"
    installer = files / "chummer-test-installer.exe"
    sidecar_path = files / "test-payload.zip.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    canonical = json.loads((candidate / MODULE.CANONICAL_MANIFEST).read_text(encoding="utf-8"))
    compatibility = json.loads((candidate / MODULE.COMPATIBILITY_MANIFEST).read_text(encoding="utf-8"))
    canonical_row, compatibility_row = canonical["artifacts"][0], compatibility["downloads"][0]
    if mutation in ("sidecar-mode", "relabel-as-download"):
        sidecar["payloadAcquisitionMode"] = "download"
    if mutation in ("compatibility-mode", "relabel-as-download"):
        compatibility_row["payloadAcquisitionMode"] = "download"
    if mutation in ("canonical-mode", "relabel-as-download"):
        canonical_row["payloadAcquisitionMode"] = "download"
    if mutation.startswith("binary-"):
        trailer_sidecar = dict(sidecar)
        field, value = {
            "binary-mode": ("payloadAcquisitionMode", "download"),
            "binary-digest": ("sha256", "a" * 64),
            "binary-size": ("sizeBytes", sidecar["sizeBytes"] + 1),
        }[mutation]
        trailer_sidecar[field] = value
        installer.write_bytes(b"fixture NSIS bytes" + _bootstrap_trailer(trailer_sidecar))
    if mutation == "missing-trailer":
        installer.write_bytes(b"fixture NSIS bytes")
    if mutation == "duplicate-trailer":
        installer.write_bytes(installer.read_bytes() + _bootstrap_trailer(sidecar))
    if mutation == "trailing-bytes":
        installer.write_bytes(installer.read_bytes() + b"unexpected suffix")
    # Bind the edited binary, so trailer tests cannot pass via an unrelated SHA failure.
    if mutation.startswith("binary-") or mutation in ("missing-trailer", "duplicate-trailer", "trailing-bytes"):
        for row in (canonical_row, compatibility_row):
            row.update(sha256=MODULE.sha256_file(installer), sizeBytes=installer.stat().st_size)
    sidecar_changes = {
        "sidecar-digest": ("sha256", "a" * 64),
        "sidecar-size": ("sizeBytes", sidecar["sizeBytes"] + 1),
        "sidecar-float-size": ("sizeBytes", float(sidecar["sizeBytes"])),
        "sidecar-private-field": ("privateEvidence", "must not be projected"),
        "sidecar-relative-url": ("downloadUrl", "/downloads/files/test-payload.zip"),
        "sidecar-foreign-url": ("downloadUrl", "https://example.invalid/downloads/files/test-payload.zip"),
        "sidecar-query": ("downloadUrl", sidecar["downloadUrl"] + "?token=fixture"),
        "sidecar-encoded-path": ("downloadUrl", "https://chummer.run/downloads/files/%74est-payload.zip"),
        "sidecar-generation-url": ("downloadUrl", "https://chummer.run/downloads/g/other/files/test-payload.zip"),
        "sidecar-installer-name": ("installerFileName", "different.exe"),
        "sidecar-version": ("releaseVersion", "different-version"),
    }
    if mutation in sidecar_changes:
        field, value = sidecar_changes[mutation]
        sidecar[field] = value
    if mutation == "payload-traversal":
        for row in (canonical_row, compatibility_row):
            row["payloadFileName"] = "../test-payload.zip"
        sidecar["fileName"] = "../test-payload.zip"
    if mutation == "corrupt-installer":
        installer.write_bytes(b"X" + installer.read_bytes()[1:])
    if mutation == "corrupt-payload":
        (files / "test-payload.zip").write_bytes(b"corrupt ZIP identity!")
    if mutation == "canonical-payload-identity":
        canonical_row["payloadSha256"] = "b" * 64
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    if mutation == "sidecar-duplicate-field":
        sidecar_path.write_text(
            '{"releaseVersion":"must not be projected",' + json.dumps(sidecar)[1:],
            encoding="utf-8",
        )
    if mutation == "sidecar-oversize":
        sidecar_path.write_text(json.dumps(sidecar) + " " * (64 * 1024), encoding="utf-8")
    for name, manifest in (
        (MODULE.CANONICAL_MANIFEST, canonical), (MODULE.COMPATIBILITY_MANIFEST, compatibility),
    ):
        (candidate / name).write_text(json.dumps(manifest), encoding="utf-8")
    source_snapshot = {path: path.read_bytes() for path in candidate.rglob("*") if path.is_file()}
    output = tmp_path / "prepared"
    expected_error = "sidecar"
    if mutation.startswith("binary-") or mutation in (
        "missing-trailer", "duplicate-trailer", "trailing-bytes", "relabel-as-download",
    ):
        expected_error = "trailer"
    elif mutation == "canonical-mode":
        expected_error = "mode disagrees"
    elif mutation == "canonical-payload-identity":
        expected_error = "identity disagrees"
    elif mutation == "payload-traversal":
        expected_error = "unsafe payloadFileName"
    elif mutation in ("corrupt-installer", "corrupt-payload"):
        expected_error = "SHA-256 mismatch|size mismatch"
    with pytest.raises(MODULE.ReleaseShelfError, match=expected_error):
        MODULE.prepare_layout(candidate, output, generation_id="generation-rejected")
    assert not (output / MODULE.CURRENT_POINTER).exists()
    assert all(path.read_bytes() == contents for path, contents in source_snapshot.items())


def test_generation_rewrite_keeps_account_required_sidecar_bytes_unchanged(
    tmp_path: Path,
) -> None:
    generation = tmp_path / "generation"
    files = generation / "files"
    files.mkdir(parents=True)
    payload_name = "protected-payload.zip"
    sidecar_path = files / f"{payload_name}.json"
    original = (
        b'{"contractName":"protected-sidecar","opaque":"unchanged"}\n'
    )
    sidecar_path.write_bytes(original)
    compatibility = {
        "version": "run-protected-sidecar",
        "downloads": [
            {
                "id": "protected-installer",
                "fileName": "protected-installer.exe",
                "installAccessClass": "account_required",
                "payloadFileName": payload_name,
                "payloadDownloadUrl": (
                    "/downloads/files/protected-payload.zip"
                ),
                "payloadSha256": "a" * 64,
                "payloadSizeBytes": 10,
            }
        ],
    }
    routes = MODULE._artifact_routes(
        compatibility,
        "generation-protected",
    )

    MODULE.rewrite_payload_sidecars_for_generation(
        generation,
        compatibility,
        routes,
    )

    assert sidecar_path.read_bytes() == original


def test_manifest_normalization_replace_failure_preserves_original_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / MODULE.CANONICAL_MANIFEST
    manifest.write_text(
        json.dumps(
            {
                "version": "release-replace-failure",
                "channel": "preview",
                "publishedAt": "2026-07-24T08:00:00Z",
                "artifacts": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.chmod(0o400)
    before = (
        manifest.read_bytes(),
        stat.S_IMODE(manifest.stat().st_mode),
        manifest.stat().st_mtime_ns,
        manifest.stat().st_ino,
    )

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(MODULE.os, "replace", fail_replace)
    with pytest.raises(MODULE.ReleaseShelfError, match="failed to atomically replace"):
        MODULE.normalize_manifest(manifest, "generation-replace-failure")

    assert (
        manifest.read_bytes(),
        stat.S_IMODE(manifest.stat().st_mode),
        manifest.stat().st_mtime_ns,
        manifest.stat().st_ino,
    ) == before
    assert not list(tmp_path.glob(f".{manifest.name}.normalize-*"))


@pytest.mark.parametrize("mode", (0o400, 0o600))
def test_manifest_normalization_preserves_existing_permission_bits(
    tmp_path: Path,
    mode: int,
) -> None:
    manifest = tmp_path / MODULE.CANONICAL_MANIFEST
    manifest.write_text(
        json.dumps(
            {
                "version": "release-mode-preservation",
                "channel": "preview",
                "publishedAt": "2026-07-24T08:00:00Z",
                "artifacts": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.chmod(mode)
    original_inode = manifest.stat().st_ino

    normalized = MODULE.normalize_manifest(
        manifest,
        "generation-mode-preservation",
    )

    assert normalized["generationId"] == "generation-mode-preservation"
    assert manifest.stat().st_ino != original_inode
    assert stat.S_IMODE(manifest.stat().st_mode) == mode
    assert not list(tmp_path.glob(f".{manifest.name}.normalize-*"))


def test_prepare_rejects_manifest_and_nested_file_symlinks(tmp_path: Path) -> None:
    manifest_candidate = write_candidate(tmp_path / "manifest-candidate")
    canonical = manifest_candidate / MODULE.CANONICAL_MANIFEST
    external_manifest = tmp_path / "external-manifest.json"
    external_manifest.write_bytes(canonical.read_bytes())
    canonical.unlink()
    canonical.symlink_to(external_manifest)

    with pytest.raises(MODULE.ReleaseShelfError, match="candidate file is invalid"):
        MODULE.prepare_layout(
            manifest_candidate,
            tmp_path / "manifest-prepared",
            generation_id="generation-manifest-symlink",
        )

    nested_candidate = write_candidate(tmp_path / "nested-candidate")
    nested_link = nested_candidate / "files" / "nested-installer-link.exe"
    nested_link.symlink_to(
        nested_candidate / "files" / "chummer-test-installer.exe"
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="symbolic links"):
        MODULE.prepare_layout(
            nested_candidate,
            tmp_path / "nested-prepared",
            generation_id="generation-nested-symlink",
        )


def test_prepare_binds_every_shelf_url_and_records_complete_inventory(tmp_path: Path) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    prepared = tmp_path / "prepared"

    pointer = MODULE.prepare_layout(
        candidate,
        prepared,
        generation_id="generation-a",
        activated_at="2026-07-15T13:00:00Z",
        activation_receipt_id="receipt-a",
    )

    generation = prepared / "generations" / "generation-a"
    canonical = json.loads((generation / MODULE.CANONICAL_MANIFEST).read_text(encoding="utf-8"))
    compatibility = json.loads(
        (generation / MODULE.COMPATIBILITY_MANIFEST).read_text(encoding="utf-8")
    )
    candidate_record = json.loads(
        (generation / MODULE.ACTIVATION_CANDIDATE).read_text(encoding="utf-8")
    )
    assert canonical["generationId"] == "generation-a"
    assert compatibility["generationId"] == "generation-a"
    assert canonical["artifacts"][0]["downloadUrl"].startswith(
        "/downloads/g/generation-a/files/"
    )
    assert compatibility["downloads"][0]["url"].startswith(
        "/downloads/g/generation-a/files/"
    )
    assert canonical["proofUrl"] == "/downloads/g/generation-a/proof/local.json"
    assert canonical["smokeUrl"] == "/downloads/g/generation-a/startup-smoke/test.json"
    assert canonical["evidenceUrl"] == "/downloads/g/generation-a/release-evidence/test.json"
    assert pointer["manifests"] == {
        "canonical": {
            "path": "/downloads/g/generation-a/RELEASE_CHANNEL.generated.json",
            "sha256": MODULE.sha256_file(generation / MODULE.CANONICAL_MANIFEST),
        },
        "compatibility": {
            "path": "/downloads/g/generation-a/releases.json",
            "sha256": MODULE.sha256_file(generation / MODULE.COMPATIBILITY_MANIFEST),
        },
    }
    assert candidate_record["releaseVersion"] == pointer["releaseVersion"]
    assert candidate_record["channel"] == pointer["channel"]
    assert candidate_record["publishedAt"] == pointer["publishedAt"]
    assert candidate_record["manifests"] == pointer["manifests"]
    assert candidate_record["inventoryDigest"] == pointer["inventoryDigest"]
    assert pointer["inventoryDigest"] == f"sha256:{MODULE.inventory_digest(candidate_record['inventory'])}"
    assert {row["path"] for row in candidate_record["inventory"]} >= {
        "files/chummer-test-installer.exe",
        "proof/local.json",
        "startup-smoke/test.json",
        "release-evidence/test.json",
    }
    MODULE.verify_generation(generation, pointer)


def test_prepare_sidecar_active_layout_binds_current_generation_without_fabricated_journal(
    tmp_path: Path,
) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    prepared = tmp_path / "prepared"

    receipt = MODULE.prepare_sidecar_active_layout(
        candidate,
        prepared,
        generation_id="generation-sidecar",
        activated_at="2026-07-24T01:00:00Z",
        activation_receipt_id="activation-sidecar",
    )

    pointer_bytes = (prepared / MODULE.CURRENT_POINTER).read_bytes()
    pointer = json.loads(pointer_bytes)
    assert (prepared / MODULE.LAYOUT_MARKER).read_bytes() == b"v1\n"
    assert json.loads((prepared / MODULE.WRITER_POLICY).read_bytes()) == {
        "schemaVersion": MODULE.SERVER_WRITER_POLICY_SCHEMA,
        "mode": MODULE.SIDECAR_WRITER_POLICY_MODE,
    }
    assert not (prepared / ".release-shelf-activation-journal").exists()
    assert not (prepared / MODULE.PROMOTION_LOCK).exists()
    assert receipt["pointer"] == pointer
    assert receipt["pointerSha256"] == MODULE.sha256_file(
        prepared / MODULE.CURRENT_POINTER
    )
    assert (
        (prepared / MODULE.CANONICAL_MANIFEST).read_bytes()
        == (candidate / MODULE.CANONICAL_MANIFEST).read_bytes()
    )
    assert (
        (prepared / MODULE.COMPATIBILITY_MANIFEST).read_bytes()
        == (candidate / MODULE.COMPATIBILITY_MANIFEST).read_bytes()
    )
    assert receipt["canonicalMirrorSha256"] == MODULE.sha256_file(
        prepared / MODULE.CANONICAL_MANIFEST
    )
    assert receipt["compatibilityMirrorSha256"] == MODULE.sha256_file(
        prepared / MODULE.COMPATIBILITY_MANIFEST
    )


def test_filesystem_writer_refuses_server_journal_policy_before_staging(tmp_path: Path) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    shelf = tmp_path / "downloads"
    shelf.mkdir()
    (shelf / MODULE.WRITER_POLICY).write_text(
        json.dumps(
            {
                "schemaVersion": MODULE.SERVER_WRITER_POLICY_SCHEMA,
                "mode": MODULE.SERVER_WRITER_POLICY_MODE,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="staged HTTP server journal"):
        MODULE.activate_filesystem(candidate, shelf, initialize_layout=True)

    assert not (shelf / MODULE.CURRENT_POINTER).exists()
    assert not (shelf / MODULE.GENERATIONS_DIRECTORY).exists()
    assert not list(shelf.glob(".release-shelf-stage-*"))


def test_filesystem_writer_refuses_read_only_sidecar_policy_before_staging(
    tmp_path: Path,
) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    shelf = tmp_path / "downloads"
    shelf.mkdir()
    (shelf / MODULE.WRITER_POLICY).write_text(
        json.dumps(
            {
                "schemaVersion": MODULE.SERVER_WRITER_POLICY_SCHEMA,
                "mode": MODULE.SIDECAR_WRITER_POLICY_MODE,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="unsupported"):
        MODULE.activate_filesystem(candidate, shelf, initialize_layout=True)

    assert not (shelf / MODULE.CURRENT_POINTER).exists()
    assert not (shelf / MODULE.GENERATIONS_DIRECTORY).exists()
    assert not list(shelf.glob(".release-shelf-stage-*"))


def test_prepared_filesystem_writer_refuses_server_journal_policy_before_rename(
    tmp_path: Path,
) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    prepared = tmp_path / "prepared"
    MODULE.prepare_layout(candidate, prepared, generation_id="generation-policy")
    shelf = tmp_path / "downloads"
    shelf.mkdir()
    (shelf / MODULE.WRITER_POLICY).write_text(
        json.dumps(
            {
                "schemaVersion": MODULE.SERVER_WRITER_POLICY_SCHEMA,
                "mode": MODULE.SERVER_WRITER_POLICY_MODE,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="staged HTTP server journal"):
        MODULE.activate_prepared_filesystem(prepared, shelf, initialize_layout=True)

    assert (prepared / MODULE.GENERATIONS_DIRECTORY / "generation-policy").is_dir()
    assert not (shelf / MODULE.CURRENT_POINTER).exists()
    assert not (shelf / MODULE.GENERATIONS_DIRECTORY).exists()


def test_manifest_normalizer_projects_artifact_routes_by_access_and_omits_mutable_facts(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / MODULE.CANONICAL_MANIFEST
    manifest_path.write_text(
        json.dumps(
            {
                "version": "release-routes",
                "channel": "preview",
                "publishedAt": "2026-07-15T12:00:00Z",
                "artifacts": [
                    {
                        "artifactId": "open-installer",
                        "fileName": "open.bin",
                        "installAccessClass": "open_public",
                        "downloadUrl": "/downloads/files/open.bin",
                        "payloadFileName": "open-payload.zip",
                        "payloadDownloadUrl": "/downloads/files/open-payload.zip",
                    },
                    {
                        "artifactId": "protected-installer",
                        "fileName": "protected.bin",
                        "installAccessClass": "account_required",
                        "downloadUrl": "/downloads/install/protected-installer",
                        "payloadFileName": "protected-payload.zip",
                        "payloadDownloadUrl": "/downloads/files/protected-payload.zip",
                    },
                ],
                "openFact": "/downloads/get/open-installer",
                "openPayloadFact": "/downloads/files/open-payload.zip",
                "openMetadataFact": "/downloads/files/open-payload.zip.json",
                "protectedFact": "/downloads/file/protected-installer",
                "protectedPayloadFact": "/downloads/files/protected-payload.zip",
                "protectedMetadataFact": "/downloads/files/protected-payload.zip.json",
                "absentFact": "/downloads/install/missing-installer",
                "mutableContinuation": "/downloads/install/protected-installer/claim",
                "proofRoutes": [
                    "/downloads/install/avalonia-linux-x64-installer",
                    "/downloads/install/protected-installer",
                ],
                "releaseProof": {
                    "proofRoutes": [
                        "/downloads/install/avalonia-linux-x64-installer",
                        "/downloads/install/protected-installer",
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    normalized = MODULE.normalize_manifest(manifest_path, "generation-routes")

    assert normalized["artifacts"][0]["downloadUrl"] == (
        "/downloads/g/generation-routes/files/open.bin"
    )
    assert normalized["artifacts"][0]["payloadDownloadUrl"] == (
        "/downloads/g/generation-routes/files/open-payload.zip"
    )
    assert normalized["artifacts"][1]["downloadUrl"] == (
        "/downloads/g/generation-routes/install/protected-installer"
    )
    assert normalized["artifacts"][1]["payloadDownloadUrl"] == (
        "/downloads/g/generation-routes/install/protected-installer/payload"
    )
    assert normalized["openFact"] == "/downloads/g/generation-routes/files/open.bin"
    assert normalized["openPayloadFact"] == (
        "/downloads/g/generation-routes/files/open-payload.zip"
    )
    assert normalized["openMetadataFact"] == (
        "/downloads/g/generation-routes/files/open-payload.zip.json"
    )
    assert normalized["protectedFact"] == (
        "/downloads/g/generation-routes/install/protected-installer"
    )
    assert normalized["protectedPayloadFact"] == (
        "/downloads/g/generation-routes/install/protected-installer/payload"
    )
    assert normalized["protectedMetadataFact"] == (
        "/downloads/g/generation-routes/install/protected-installer/metadata"
    )
    assert "absentFact" not in normalized
    assert "mutableContinuation" not in normalized
    assert normalized["proofRoutes"] == [
        "/downloads/g/generation-routes/install/protected-installer",
    ]
    assert normalized["releaseProof"]["proofRoutes"] == [
        "/downloads/install/avalonia-linux-x64-installer",
        "/downloads/install/protected-installer",
    ]
    MODULE.validate_manifest_routes(normalized, "generation-routes", "fixture")


def test_registry_generation_projection_matches_cross_language_golden_bytes(
    tmp_path: Path,
) -> None:
    source = {
        "version": "release-parity",
        "channel": "preview",
        "publishedAt": "2026-07-17T20:00:00Z",
        "downloads": [
            {
                "id": "open",
                "fileName": "open.bin",
                "url": "/downloads/files/open.bin",
                "installAccessClass": "open_public",
                "payloadFileName": "open.zip",
                "payloadDownloadUrl": "/downloads/files/open.zip",
            },
            {
                "id": "protected",
                "fileName": "protected.bin",
                "url": "/downloads/files/protected.bin",
                "installAccessClass": "account_required",
                "payloadFileName": "protected.zip",
                "payloadDownloadUrl": "/downloads/files/protected.zip",
            },
        ],
        "artifactIdentityRegistry": [
            {"publicInstallRoute": "/downloads/install/open"},
            {"publicInstallRoute": "/downloads/install/protected"},
        ],
        "artifactPublicationBindings": [
            {"publicInstallRoute": "/downloads/install/open"}
        ],
        "desktopSurfaceRefs": [
            {"publicInstallRoute": "/downloads/install/open"}
        ],
        "desktopTupleCoverage": {
            "desktopRouteTruth": [
                {"publicInstallRoute": "/downloads/install/open"},
                {"publicInstallRoute": "/downloads/install/missing"},
            ]
        },
        "installAwareArtifactRegistry": [
            {
                "conciergeAssetRefs": {
                    "publicTrustWrapper": "/downloads/install/open"
                },
                "recoveryProofRefs": [
                    "/downloads/install/open",
                    "startup-smoke/startup-smoke-open.receipt.json",
                ],
            }
        ],
        "publicTrustMetrics": {
            "revocationFacts": {
                "activeRevocations": [
                    {"publicInstallRoute": "/downloads/install/open"}
                ]
            }
        },
        "extension": {
            "publicInstallRoute": "/downloads/install/open",
            "unknownPublicInstallRoute": "/downloads/install/missing",
        },
        "releaseProof": {"proofRoutes": ["/downloads/install/protected"]},
    }
    manifest_path = tmp_path / MODULE.COMPATIBILITY_MANIFEST
    manifest_path.write_text(json.dumps(source), encoding="utf-8")

    MODULE.normalize_manifest(manifest_path, "generation-parity")

    expected = (
        b'{"artifactIdentityRegistry":[{"publicInstallRoute":"/downloads/install/open"},'
        b'{"publicInstallRoute":"/downloads/g/generation-parity/install/protected"}],'
        b'"artifactPublicationBindings":[{"publicInstallRoute":"/downloads/install/open"}],'
        b'"channel":"preview","desktopSurfaceRefs":[{"publicInstallRoute":"/downloads/install/open"}],'
        b'"desktopTupleCoverage":{"desktopRouteTruth":[{"publicInstallRoute":"/downloads/install/open"},'
        b'{"publicInstallRoute":"/downloads/install/missing"}]},'
        b'"downloads":[{"fileName":"open.bin","id":"open",'
        b'"installAccessClass":"open_public",'
        b'"payloadDownloadUrl":"/downloads/g/generation-parity/files/open.zip",'
        b'"payloadFileName":"open.zip","url":"/downloads/g/generation-parity/files/open.bin"},'
        b'{"fileName":"protected.bin","id":"protected","installAccessClass":"account_required",'
        b'"payloadDownloadUrl":"/downloads/g/generation-parity/install/protected/payload",'
        b'"payloadFileName":"protected.zip","url":"/downloads/g/generation-parity/install/protected"}],'
        b'"extension":{"publicInstallRoute":"/downloads/g/generation-parity/files/open.bin"},'
        b'"generationId":"generation-parity","installAwareArtifactRegistry":[{"conciergeAssetRefs":'
        b'{"publicTrustWrapper":"/downloads/install/open"},"recoveryProofRefs":'
        b'["/downloads/install/open","startup-smoke/startup-smoke-open.receipt.json"]}],'
        b'"publicTrustMetrics":{"revocationFacts":{"activeRevocations":'
        b'[{"publicInstallRoute":"/downloads/install/open"}]}},'
        b'"publishedAt":"2026-07-17T20:00:00Z",'
        b'"releaseProof":{"proofRoutes":["/downloads/install/protected"]},'
        b'"version":"release-parity"}\n'
    )
    assert manifest_path.read_bytes() == expected


@pytest.mark.parametrize(
    "route",
    (
        "/downloads/files/open.bin?ticket=secret",
        "/downloads/files/open.bin#fragment",
        "/downloads/files%2Fopen.bin",
        "/downloads/files/nested/open.bin",
        "https://chummer.run/downloads/files/open.bin",
        "//chummer.run/downloads/files/open.bin",
    ),
)
def test_registry_generation_projection_rejects_noncanonical_source_routes(
    tmp_path: Path,
    route: str,
) -> None:
    manifest_path = tmp_path / MODULE.COMPATIBILITY_MANIFEST
    manifest_path.write_text(
        json.dumps(
            {
                "version": "release-invalid-route",
                "channel": "preview",
                "publishedAt": "2026-07-17T20:00:00Z",
                "downloads": [
                    {
                        "id": "open",
                        "fileName": "open.bin",
                        "url": route,
                        "installAccessClass": "open_public",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="canonical|plain"):
        MODULE.normalize_manifest(manifest_path, "generation-invalid-route")


def test_registry_generation_projection_rejects_nested_release_proof_lookalike(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / MODULE.COMPATIBILITY_MANIFEST
    manifest_path.write_text(
        json.dumps(
            {
                "version": "release-lookalike",
                "channel": "preview",
                "publishedAt": "2026-07-17T20:00:00Z",
                "downloads": [],
                "extension": {
                    "releaseProof": {
                        "proofRoutes": ["/downloads/install/shadow"]
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="nested"):
        MODULE.normalize_manifest(manifest_path, "generation-lookalike")


@pytest.mark.parametrize(
    "url",
    (
        "/downloads/g/generation-routes/",
        "/downloads/g/generation-routes/files/nested/open.bin",
        "/downloads/g/generation-routes/install/protected-installer/claim",
        "/downloads/g/generation-routes/install/protected-installer?ticket=x",
        "/downloads/g/generation-routes/install/protected-installer#claim",
        "/downloads/g/generation-routes/install/protected-installer%2Fclaim",
    ),
)
def test_manifest_validator_rejects_non_exact_generation_install_routes(url: str) -> None:
    with pytest.raises(
        MODULE.ReleaseShelfError,
        match="unsafe generation URL|noncanonical route shape|canonical unencoded site path",
    ):
        MODULE.validate_manifest_routes(
            {"generationId": "generation-routes", "url": url},
            "generation-routes",
            "fixture",
        )


def test_shared_helper_accepts_cross_language_contract_fixture(
    tmp_path: Path,
) -> None:
    source = ROOT / "tests" / "fixtures" / "atomic_release_shelf_v1"
    fixture = tmp_path / "atomic-release-shelf-v1"
    shutil.copytree(source, fixture)
    (fixture / MODULE.CURRENT_POINTER).chmod(MODULE.PUBLIC_METADATA_FILE_MODE)
    (fixture / MODULE.LAYOUT_MARKER).chmod(MODULE.PUBLIC_METADATA_FILE_MODE)
    pointer = MODULE.load_pointer(fixture / MODULE.CURRENT_POINTER)
    MODULE._normalize_public_generation_modes(
        fixture
        / MODULE.GENERATIONS_DIRECTORY
        / str(pointer["generationId"])
    )

    state, generation_root, pointer = MODULE.resolve_shelf_root(fixture)

    assert state == "generation"
    assert pointer is not None
    assert generation_root.name == pointer["generationId"]
    MODULE.verify_generation(generation_root, pointer)


@pytest.mark.parametrize(
    "generation_id",
    ("../escape", "/absolute", "with/slash", "", ".", "bad generation", "bad..generation"),
)
def test_generation_id_must_be_opaque_and_traversal_safe(generation_id: str) -> None:
    with pytest.raises(MODULE.ReleaseShelfError, match="traversal-safe opaque token"):
        MODULE.validate_generation_id(generation_id)


def test_filesystem_activation_requires_explicit_initialization_and_preserves_generations(
    tmp_path: Path,
) -> None:
    shelf = tmp_path / "shelf"
    first = write_candidate(tmp_path / "first")

    with pytest.raises(MODULE.ReleaseShelfError, match="explicit layout initialization"):
        MODULE.activate_filesystem(
            first,
            shelf,
            initialize_layout=False,
            generation_id="generation-a",
        )
    assert not (shelf / MODULE.LAYOUT_MARKER).exists()
    assert not (shelf / MODULE.CURRENT_POINTER).exists()

    pointer_a = MODULE.activate_filesystem(
        first,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
        activated_at="2026-07-15T13:00:00Z",
        activation_receipt_id="receipt-a",
    )
    first_bytes = (shelf / "generations" / "generation-a" / "files" / "chummer-test-installer.exe").read_bytes()
    second = write_candidate(tmp_path / "second", version="release-2", artifact=b"artifact-b")
    pointer_b = MODULE.activate_filesystem(
        second,
        shelf,
        initialize_layout=False,
        generation_id="generation-b",
        activated_at="2026-07-15T14:00:00Z",
        activation_receipt_id="receipt-b",
    )

    current = MODULE.load_pointer(shelf / MODULE.CURRENT_POINTER)
    assert pointer_a["generationId"] == "generation-a"
    assert pointer_b["generationId"] == current["generationId"] == "generation-b"
    assert (
        shelf / "generations" / "generation-a" / "files" / "chummer-test-installer.exe"
    ).read_bytes() == first_bytes
    state, resolved, _ = MODULE.resolve_shelf_root(shelf)
    assert state == "generation"
    assert resolved == shelf / "generations" / "generation-b"


def test_activation_publishes_runtime_bytes_for_a_distinct_uid_without_widening_source_candidate(
    tmp_path: Path,
) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    candidate_entries = [candidate, *candidate.rglob("*")]
    for path in reversed(candidate_entries):
        path.chmod(0o700 if path.is_dir() else 0o600)
    shelf = tmp_path / "shelf"

    pointer = MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-public-modes",
        activated_at="2026-07-23T12:00:00Z",
        activation_receipt_id="receipt-public-modes",
    )

    generation = (
        shelf / MODULE.GENERATIONS_DIRECTORY / pointer["generationId"]
    )
    shared_directories = [
        shelf,
        shelf / MODULE.GENERATIONS_DIRECTORY,
    ]
    sealed_directories = [
        generation,
        *[path for path in generation.rglob("*") if path.is_dir()],
    ]
    public_metadata = [
        shelf / MODULE.CURRENT_POINTER,
        shelf / MODULE.LAYOUT_MARKER,
        *[
            generation / name
            for name in (
                MODULE.ACTIVATION_CANDIDATE,
                MODULE.CANONICAL_MANIFEST,
                MODULE.COMPATIBILITY_MANIFEST,
            )
        ],
    ]
    sealed_files = [
        path
        for path in generation.rglob("*")
        if path.is_file() and path not in public_metadata
    ]
    for directory in shared_directories:
        assert stat.S_IMODE(directory.stat().st_mode) == 0o2770
    for directory in sealed_directories:
        assert stat.S_IMODE(directory.stat().st_mode) == 0o555
    for path in public_metadata:
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
    for path in sealed_files:
        assert stat.S_IMODE(path.stat().st_mode) == 0o444
    assert stat.S_IMODE((shelf / MODULE.PROMOTION_LOCK).stat().st_mode) == 0o660
    assert stat.S_IMODE(candidate.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
        for path in candidate.rglob("*")
    )

    runtime_uid = shelf.stat().st_uid + 100_000
    runtime_gid = shelf.stat().st_gid

    def permission_bits(path: Path) -> int:
        metadata = path.stat()
        mode = stat.S_IMODE(metadata.st_mode)
        if metadata.st_uid == runtime_uid:
            return (mode >> 6) & 0o7
        if metadata.st_gid == runtime_gid:
            return (mode >> 3) & 0o7
        return mode & 0o7

    assert all(permission_bits(path) & 0o3 == 0o3 for path in shared_directories)
    assert all(permission_bits(path) & 0o1 for path in sealed_directories)
    assert all(permission_bits(path) & 0o4 for path in public_metadata)
    assert all(permission_bits(path) & 0o4 for path in sealed_files)

    sealed_files[-1].chmod(0o600)
    with pytest.raises(MODULE.ReleaseShelfError, match="non-public mode"):
        MODULE.verify_generation(generation, pointer)


def test_same_intent_recovery_repairs_authenticated_prepatch_private_modes(
    tmp_path: Path,
) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    shelf = tmp_path / "shelf"
    pointer = MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-private-mode-recovery",
        activated_at="2026-07-23T12:00:00Z",
        activation_receipt_id="receipt-private-mode-recovery",
        allow_orphan_generation_recovery=True,
    )
    generation = (
        shelf / MODULE.GENERATIONS_DIRECTORY / pointer["generationId"]
    )
    generation_entries = [generation, *generation.rglob("*")]
    for path in reversed(generation_entries):
        path.chmod(0o700 if path.is_dir() else 0o600)
    (shelf / MODULE.GENERATIONS_DIRECTORY).chmod(0o700)
    (shelf / MODULE.CURRENT_POINTER).chmod(0o600)
    (shelf / MODULE.LAYOUT_MARKER).chmod(0o600)
    shelf.chmod(0o700)

    recovered = MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-private-mode-recovery",
        activated_at="2026-07-23T12:00:00Z",
        activation_receipt_id="receipt-private-mode-recovery",
        allow_orphan_generation_recovery=True,
    )

    assert recovered == pointer
    assert stat.S_IMODE(shelf.stat().st_mode) == 0o2770
    assert stat.S_IMODE(
        (shelf / MODULE.GENERATIONS_DIRECTORY).stat().st_mode
    ) == 0o2770
    assert stat.S_IMODE(generation.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o555
        for path in generation.rglob("*")
        if path.is_dir()
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode)
        == (
            0o644
            if path.relative_to(generation).as_posix()
            in {
                MODULE.ACTIVATION_CANDIDATE,
                MODULE.CANONICAL_MANIFEST,
                MODULE.COMPATIBILITY_MANIFEST,
            }
            else 0o444
        )
        for path in generation.rglob("*")
        if path.is_file()
    )
    assert stat.S_IMODE((shelf / MODULE.CURRENT_POINTER).stat().st_mode) == 0o644
    assert stat.S_IMODE((shelf / MODULE.LAYOUT_MARKER).stat().st_mode) == 0o644
    assert stat.S_IMODE((shelf / MODULE.PROMOTION_LOCK).stat().st_mode) == 0o660


def test_marker_or_pointer_inconsistency_fails_closed_without_legacy_fallback(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    legacy_manifest = shelf / MODULE.CANONICAL_MANIFEST
    legacy_manifest.write_text('{"version":"legacy"}\n', encoding="utf-8")
    (shelf / MODULE.LAYOUT_MARKER).write_text("1\n", encoding="utf-8")

    with pytest.raises(MODULE.ReleaseShelfError, match="refusing legacy fallback"):
        MODULE.resolve_shelf_root(shelf)
    assert legacy_manifest.read_text(encoding="utf-8") == '{"version":"legacy"}\n'



def test_valid_pointer_is_authoritative_before_postcommit_marker_exists(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
    )
    (shelf / MODULE.LAYOUT_MARKER).unlink()

    state, generation_root, pointer = MODULE.resolve_shelf_root(shelf)

    assert state == "generation"
    assert generation_root.name == "generation-a"
    assert pointer is not None and pointer["generationId"] == "generation-a"


def test_manifest_mutation_is_rejected_by_pointer_and_candidate_bindings(tmp_path: Path) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    prepared = tmp_path / "prepared"
    pointer = MODULE.prepare_layout(candidate, prepared, generation_id="generation-a")
    generation = prepared / MODULE.GENERATIONS_DIRECTORY / "generation-a"
    (generation / MODULE.CANONICAL_MANIFEST).write_text("{}\n", encoding="utf-8")

    with pytest.raises(MODULE.ReleaseShelfError, match="SHA-256|identity|generationId mismatch"):
        MODULE.verify_generation(generation, pointer)


def test_materializer_rejects_unreferenced_nested_and_case_colliding_files(tmp_path: Path) -> None:
    nested_candidate = write_candidate(tmp_path / "nested")
    nested = nested_candidate / "files" / "nested"
    nested.mkdir()
    (nested / "chummer-test-installer.exe").write_bytes(b"shadow")
    with pytest.raises(MODULE.ReleaseShelfError, match="unreferenced bytes"):
        MODULE.prepare_layout(
            nested_candidate,
            tmp_path / "nested-prepared",
            generation_id="generation-nested",
        )

    case_candidate = write_candidate(tmp_path / "case")
    (case_candidate / "files" / "CHUMMER-TEST-INSTALLER.EXE").write_bytes(b"shadow")
    with pytest.raises(MODULE.ReleaseShelfError, match="unreferenced bytes|case-colliding"):
        MODULE.prepare_layout(
            case_candidate,
            tmp_path / "case-prepared",
            generation_id="generation-case",
        )


def test_missing_or_corrupt_generation_fails_closed(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
    )
    artifact = shelf / "generations" / "generation-a" / "files" / "chummer-test-installer.exe"
    artifact.chmod(0o644)
    artifact.write_bytes(b"tampered")
    artifact.chmod(MODULE.SEALED_FILE_MODE)

    with pytest.raises(MODULE.ReleaseShelfError, match="mismatch"):
        MODULE.resolve_shelf_root(shelf)


def test_generation_id_cannot_be_reused_even_with_identical_bytes(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="already been used"):
        MODULE.activate_filesystem(
            candidate,
            shelf,
            initialize_layout=False,
            generation_id="generation-a",
        )


def test_same_intent_retry_recovers_generation_rename_before_pointer_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    original_write = MODULE._atomic_write_json
    failed = False

    def crash_before_pointer(path: Path, payload: dict[str, object]) -> None:
        nonlocal failed
        if path.name == MODULE.CURRENT_POINTER and not failed:
            failed = True
            raise RuntimeError("simulated pointer-write crash")
        original_write(path, payload)

    monkeypatch.setattr(MODULE, "_atomic_write_json", crash_before_pointer)
    with pytest.raises(RuntimeError, match="pointer-write crash"):
        MODULE.activate_filesystem(
            candidate,
            shelf,
            initialize_layout=True,
            generation_id="generation-retry",
            activated_at="2026-07-23T12:00:00Z",
            activation_receipt_id="receipt-retry",
            allow_orphan_generation_recovery=True,
        )

    assert not (shelf / MODULE.CURRENT_POINTER).exists()
    assert (shelf / MODULE.LAYOUT_MARKER).read_bytes() == b"v1\n"
    assert (
        shelf / MODULE.GENERATIONS_DIRECTORY / "generation-retry"
    ).is_dir()
    assert len(
        [
            path
            for path in shelf.iterdir()
            if path.name.startswith(MODULE.ACTIVATION_STAGE_PREFIX)
        ]
    ) == 1

    monkeypatch.setattr(MODULE, "_atomic_write_json", original_write)
    pointer = MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-retry",
        activated_at="2026-07-23T12:00:00Z",
        activation_receipt_id="receipt-retry",
        allow_orphan_generation_recovery=True,
    )

    assert pointer["generationId"] == "generation-retry"
    assert MODULE.load_pointer(shelf / MODULE.CURRENT_POINTER) == pointer
    assert not any(
        path.name.startswith(MODULE.ACTIVATION_STAGE_PREFIX)
        for path in shelf.iterdir()
    )


def test_same_intent_retry_recovers_marker_commit_before_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    original_marker = MODULE._create_layout_marker
    failed = False

    def crash_after_marker(root: Path) -> None:
        nonlocal failed
        original_marker(root)
        if not failed:
            failed = True
            raise RuntimeError("simulated marker crash")

    monkeypatch.setattr(MODULE, "_create_layout_marker", crash_after_marker)
    with pytest.raises(RuntimeError, match="marker crash"):
        MODULE.activate_filesystem(
            candidate,
            shelf,
            initialize_layout=True,
            generation_id="generation-marker-retry",
            activated_at="2026-07-23T12:00:00Z",
            activation_receipt_id="receipt-marker-retry",
            allow_orphan_generation_recovery=True,
        )
    assert (shelf / MODULE.LAYOUT_MARKER).read_bytes() == b"v1\n"
    assert not (shelf / MODULE.CURRENT_POINTER).exists()

    monkeypatch.setattr(MODULE, "_create_layout_marker", original_marker)
    MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-marker-retry",
        activated_at="2026-07-23T12:00:00Z",
        activation_receipt_id="receipt-marker-retry",
        allow_orphan_generation_recovery=True,
    )

    assert (
        MODULE.load_pointer(shelf / MODULE.CURRENT_POINTER)["generationId"]
        == "generation-marker-retry"
    )


def test_unknown_or_partial_activation_stage_residue_fails_closed(
    tmp_path: Path,
) -> None:
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    candidate = write_candidate(tmp_path / "candidate")
    residue = shelf / f"{MODULE.ACTIVATION_STAGE_PREFIX}unknown"
    residue.mkdir()
    (residue / "partial").write_text("not a transaction\n", encoding="utf-8")

    with pytest.raises(
        MODULE.ReleaseShelfError,
        match="unknown release shelf activation stage residue",
    ):
        MODULE.activate_filesystem(
            candidate,
            shelf,
            initialize_layout=True,
            generation_id="generation-stage-reject",
            activation_receipt_id="receipt-stage-reject",
            allow_orphan_generation_recovery=True,
        )

    assert not (shelf / MODULE.CURRENT_POINTER).exists()
    assert residue.is_dir()


def test_committed_stage_is_atomically_retired_before_best_effort_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    original_rmtree = MODULE.shutil.rmtree

    def fail_retired_cleanup(path: Path, *args, **kwargs) -> None:
        if "-retired-activation-stage-" in Path(path).name:
            raise OSError("simulated retired cleanup failure")
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(MODULE.shutil, "rmtree", fail_retired_cleanup)
    pointer = MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-retired-cleanup",
        activation_receipt_id="receipt-retired-cleanup",
        allow_orphan_generation_recovery=True,
    )

    assert MODULE.load_pointer(shelf / MODULE.CURRENT_POINTER) == pointer
    assert not any(
        path.name.startswith(MODULE.ACTIVATION_STAGE_PREFIX)
        for path in shelf.iterdir()
    )
    retired = [
        path
        for path in shelf.parent.iterdir()
        if "-retired-activation-stage-" in path.name
    ]
    assert len(retired) == 1
    original_rmtree(retired[0])


def test_internal_promotion_lock_remains_held_through_stage_retirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    original_retire = MODULE._retire_activation_stage
    observed_lock = False

    def assert_lock_then_retire(stage_root: Path, shelf_root: Path) -> Path:
        nonlocal observed_lock
        descriptor = os.open(
            shelf_root / MODULE.PROMOTION_LOCK,
            os.O_RDWR,
        )
        try:
            with pytest.raises(BlockingIOError):
                MODULE.fcntl.flock(
                    descriptor,
                    MODULE.fcntl.LOCK_EX | MODULE.fcntl.LOCK_NB,
                )
            observed_lock = True
        finally:
            os.close(descriptor)
        return original_retire(stage_root, shelf_root)

    monkeypatch.setattr(
        MODULE,
        "_retire_activation_stage",
        assert_lock_then_retire,
    )
    MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-lock-retirement",
        activation_receipt_id="receipt-lock-retirement",
    )

    assert observed_lock is True


def test_retry_after_process_death_during_retired_stage_cleanup_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    original_rmtree = MODULE.shutil.rmtree

    class SimulatedProcessDeath(BaseException):
        pass

    def die_during_retired_cleanup(path: Path, *args, **kwargs) -> None:
        if "-retired-activation-stage-" in Path(path).name:
            raise SimulatedProcessDeath()
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(MODULE.shutil, "rmtree", die_during_retired_cleanup)
    with pytest.raises(SimulatedProcessDeath):
        MODULE.activate_filesystem(
            candidate,
            shelf,
            initialize_layout=True,
            generation_id="generation-retired-crash",
            activated_at="2026-07-23T12:00:00Z",
            activation_receipt_id="receipt-retired-crash",
            allow_orphan_generation_recovery=True,
        )
    assert (shelf / MODULE.CURRENT_POINTER).is_file()
    assert not any(
        path.name.startswith(MODULE.ACTIVATION_STAGE_PREFIX)
        for path in shelf.iterdir()
    )

    monkeypatch.setattr(MODULE.shutil, "rmtree", original_rmtree)
    pointer = MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-retired-crash",
        activation_receipt_id="receipt-retired-crash",
        allow_orphan_generation_recovery=True,
    )

    assert pointer["generationId"] == "generation-retired-crash"
    for path in shelf.parent.iterdir():
        if "-retired-activation-stage-" in path.name:
            original_rmtree(path)


def test_concurrent_pointer_readers_observe_only_complete_generation_a_or_b(
    tmp_path: Path,
) -> None:
    shelf = tmp_path / "shelf"
    first = write_candidate(tmp_path / "first", version="release-a", artifact=b"artifact-a")
    MODULE.activate_filesystem(
        first,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
    )
    second = write_candidate(tmp_path / "second", version="release-b", artifact=b"artifact-b")
    stop = threading.Event()
    observed_b = threading.Event()
    failures: list[str] = []
    observed: set[str] = set()

    def read_current() -> None:
        while not stop.is_set():
            try:
                pointer_bytes = (shelf / MODULE.CURRENT_POINTER).read_bytes()
                pointer = json.loads(pointer_bytes)
                generation_id = pointer["generationId"]
                observed.add(generation_id)
                generation = shelf / MODULE.GENERATIONS_DIRECTORY / generation_id
                manifest = generation / MODULE.CANONICAL_MANIFEST
                expected = pointer["manifests"]["canonical"]["sha256"]
                if not manifest.is_file() or MODULE.sha256_file(manifest) != expected:
                    failures.append(f"mixed or incomplete generation observed: {generation_id}")
                    return
                if generation_id == "generation-b":
                    observed_b.set()
            except Exception as exc:  # pragma: no cover - failure detail for stress loop
                failures.append(str(exc))
                return

    reader = threading.Thread(target=read_current, daemon=True)
    reader.start()
    MODULE.activate_filesystem(
        second,
        shelf,
        initialize_layout=False,
        generation_id="generation-b",
    )
    assert observed_b.wait(timeout=2)
    time.sleep(0.01)
    stop.set()
    reader.join(timeout=2)

    assert not failures
    assert observed <= {"generation-a", "generation-b"}
    assert "generation-b" in observed


def test_publishers_use_one_shared_generation_primitive_and_keep_legacy_guard() -> None:
    filesystem = (ROOT / "scripts" / "publish-download-bundle.sh").read_text(encoding="utf-8")
    object_storage = (ROOT / "scripts" / "publish-download-bundle-s3.sh").read_text(
        encoding="utf-8"
    )
    # These assertions become effective alongside the publisher migration patch and
    # prevent either lane from drifting back to top-level activation.
    for script in (filesystem, object_storage):
        assert "release_shelf_generation.py" in script
        assert ".release-shelf-layout-v1" in script
        assert "current.json" in script
    assert "activate-filesystem" in filesystem
    assert "generations/" in object_storage


def test_manifest_generator_refuses_direct_output_to_activated_shelf(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    (shelf / MODULE.LAYOUT_MARKER).write_text("v1\n", encoding="utf-8")
    registry = tmp_path / "registry"
    materializer = registry / "scripts" / "materialize_public_release_channel.py"
    materializer.parent.mkdir(parents=True)
    materializer.write_text("# guard test placeholder\n", encoding="utf-8")
    portal = tmp_path / "portal"
    authoritative = tmp_path / "published"
    env = os.environ.copy()
    env.update(
        {
            "CHUMMER_HUB_REGISTRY_ROOT": str(registry),
            "CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISHED_ROOT": str(authoritative),
            "DOWNLOADS_DIR": str(shelf / "files"),
            "MANIFEST_PATH": str(shelf / MODULE.COMPATIBILITY_MANIFEST),
            "CANONICAL_MANIFEST_PATH": str(shelf / MODULE.CANONICAL_MANIFEST),
            "PORTAL_MANIFEST_PATH": str(portal / MODULE.COMPATIBILITY_MANIFEST),
            "PORTAL_CANONICAL_MANIFEST_PATH": str(portal / MODULE.CANONICAL_MANIFEST),
            "PORTAL_DOWNLOADS_DIR": str(portal),
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "generate-releases-manifest.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "direct manifest generation is forbidden" in result.stderr
    assert not (shelf / MODULE.COMPATIBILITY_MANIFEST).exists()
    assert not portal.exists()


def test_s3_publisher_uploads_immutable_objects_before_single_pointer_put_without_network(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    files = bundle / "files"
    files.mkdir(parents=True)
    artifact = files / "chummer-avalonia-osx-arm64-installer.dmg"
    artifact.write_bytes(b"fixture installer")
    digest = MODULE.sha256_file(artifact)
    published_at = "2026-07-15T12:00:00Z"
    canonical = {
        "version": "release-s3",
        "releaseVersion": "release-s3",
        "channel": "preview",
        "publishedAt": published_at,
        "artifacts": [
            {
                "artifactId": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platform": "macos",
                "rid": "osx-arm64",
                "kind": "dmg",
                "fileName": artifact.name,
                "downloadUrl": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
            }
        ],
    }
    compatibility = {
        "version": "release-s3",
        "channel": "preview",
        "publishedAt": published_at,
        "downloads": [
            {
                "id": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platformId": "macos",
                "rid": "osx-arm64",
                "kind": "dmg",
                "fileName": artifact.name,
                "url": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
            }
        ],
    }
    (bundle / MODULE.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
    )
    (bundle / MODULE.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility, indent=2) + "\n", encoding="utf-8"
    )

    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (public_root / "current.json").as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (public_root / "g").as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-s3",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    operations = log_path.read_text(encoding="utf-8").splitlines()
    puts = [row for row in operations if row.startswith("PUT ")]
    assert puts[-2:] == ["PUT downloads/current.json", "PUT downloads/.release-shelf-layout-v1"]
    assert "PUT downloads/.release-shelf-layout-v1" in puts
    assert all(
        row.startswith("PUT downloads/generations/generation-s3/")
        for row in puts[: puts.index("PUT downloads/current.json")]
    )
    assert not any(
        row in {
            "PUT downloads/releases.json",
            "PUT downloads/RELEASE_CHANNEL.generated.json",
        }
        or row.startswith("PUT downloads/files/")
        for row in puts
    )
    pointer = json.loads((public_root / "current.json").read_text(encoding="utf-8"))
    assert pointer["generationId"] == "generation-s3"


@pytest.mark.parametrize(
    "existing_keys",
    (
        ("downloads",),
        ("downloads/releases.json",),
        ("downloads/files/legacy-installer.exe",),
        ("downloads/generations/orphan/activation-candidate.json",),
        ("downloads/.partial-upload",),
        ("downloads-a", "downloads-b", "downloads-c"),
    ),
    ids=(
        "root-object",
        "legacy-manifest",
        "legacy-file",
        "orphan-generation",
        "partial-object",
        "truncated-ambiguous-prefix",
    ),
)
def test_s3_first_generation_requires_bounded_empty_root_inventory(
    tmp_path: Path,
    existing_keys: tuple[str, ...],
) -> None:
    bundle = write_s3_publish_bundle(
        tmp_path / "bundle",
        version="release-nonempty-root",
        published_at="2026-07-15T12:30:00Z",
        payload=b"nonempty root artifact",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    for key in existing_keys:
        path = remote_root / "fixture" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preexisting object")
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-nonempty-root",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "non-empty or ambiguous" in result.stderr
    assert "PRIMARY_RELEASE_NOT_COMMITTED" in result.stderr
    operations = log_path.read_text(encoding="utf-8").splitlines()
    assert not any(row.startswith("PUT ") for row in operations)


def test_s3_first_generation_rechecks_empty_root_before_first_upload(
    tmp_path: Path,
) -> None:
    bundle = write_s3_publish_bundle(
        tmp_path / "bundle",
        version="release-root-race",
        published_at="2026-07-15T12:45:00Z",
        payload=b"root race artifact",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "FAKE_AWS_INJECT_ON_SECOND_ROOT_LIST": "downloads/releases.json",
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-root-race",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "non-empty or ambiguous" in result.stderr
    assert (remote_root / "fixture" / "downloads" / "releases.json").is_file()
    operations = log_path.read_text(encoding="utf-8").splitlines()
    assert operations.count("LIST downloads") == 2
    assert not any(row.startswith("PUT ") for row in operations)


def test_s3_concurrent_publishers_cannot_overwrite_current_pointer(
    tmp_path: Path,
) -> None:
    published_at = "2026-07-15T13:00:00Z"
    bundle_a = write_s3_publish_bundle(
        tmp_path / "bundle-a",
        version="release-concurrent-a",
        published_at=published_at,
        payload=b"concurrent artifact a",
    )
    bundle_b = write_s3_publish_bundle(
        tmp_path / "bundle-b",
        version="release-concurrent-b",
        published_at=published_at,
        payload=b"concurrent artifact b",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    common_env = os.environ.copy()
    common_env.update(
        {
            "PATH": f"{fake_bin}:{common_env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "FAKE_AWS_PUT_DELAY_MS": "15",
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
        }
    )
    env_a = common_env | {"CHUMMER_RELEASE_GENERATION_ID": "generation-concurrent-a"}
    env_b = common_env | {"CHUMMER_RELEASE_GENERATION_ID": "generation-concurrent-b"}
    command = ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh")]
    process_a = subprocess.Popen(
        command + [str(bundle_a)],
        cwd=ROOT,
        env=env_a,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    process_b = subprocess.Popen(
        command + [str(bundle_b)],
        cwd=ROOT,
        env=env_b,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout_a, stderr_a = process_a.communicate(timeout=60)
    stdout_b, stderr_b = process_b.communicate(timeout=60)

    outcomes = [process_a.returncode, process_b.returncode]
    assert outcomes.count(0) == 1, (
        f"publisher A status={process_a.returncode}\n{stdout_a}{stderr_a}\n"
        f"publisher B status={process_b.returncode}\n{stdout_b}{stderr_b}"
    )
    assert sum(status != 0 for status in outcomes) == 1
    pointer_bytes = (remote_root / "fixture" / "downloads" / "current.json").read_bytes()
    assert pointer_bytes == (public_root / "current.json").read_bytes()
    pointer = json.loads(pointer_bytes)
    assert pointer["generationId"] in {
        "generation-concurrent-a",
        "generation-concurrent-b",
    }
    operations = log_path.read_text(encoding="utf-8").splitlines()
    assert operations.count("PUT downloads/current.json") == 1


def test_s3_latest_failure_reports_primary_pointer_as_committed(
    tmp_path: Path,
) -> None:
    bundle = write_s3_publish_bundle(
        tmp_path / "bundle",
        version="release-latest-failure",
        published_at="2026-07-15T14:00:00Z",
        payload=b"latest failure artifact",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "FAKE_AWS_FAIL_PUT_PREFIX": "latest/generations/",
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_S3_LATEST_URI": "s3://fixture/latest",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-latest-failure",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "PRIMARY_RELEASE_COMMITTED generation=generation-latest-failure" in result.stderr
    )
    assert "PRIMARY_RELEASE_NOT_COMMITTED" not in result.stderr
    pointer = json.loads((public_root / "current.json").read_text(encoding="utf-8"))
    assert pointer["generationId"] == "generation-latest-failure"
    assert not (latest_public_root / "current.json").exists()


def test_s3_pointer_readback_failure_reports_primary_pointer_as_committed(
    tmp_path: Path,
) -> None:
    bundle = write_s3_publish_bundle(
        tmp_path / "bundle",
        version="release-readback-failure",
        published_at="2026-07-15T15:00:00Z",
        payload=b"readback failure artifact",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "FAKE_AWS_FAIL_GET_KEY": "downloads/current.json",
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-readback-failure",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "PRIMARY_RELEASE_COMMITTED generation=generation-readback-failure"
        in result.stderr
    )
    assert "PRIMARY_RELEASE_NOT_COMMITTED" not in result.stderr
    pointer = json.loads(
        (remote_root / "fixture" / "downloads" / "current.json").read_text(
            encoding="utf-8"
        )
    )
    assert pointer["generationId"] == "generation-readback-failure"


def test_runtime_generation_routes_and_production_downgrade_sentinel_are_wired() -> None:
    controller = (ROOT / "Chummer.Run.Api" / "Controllers" / "DownloadsCompatibilityController.cs").read_text(
        encoding="utf-8"
    )
    program = (ROOT / "Chummer.Run.Api" / "Program.cs").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(encoding="utf-8")
    appsettings = json.loads((ROOT / "Chummer.Run.Api" / "appsettings.json").read_text(encoding="utf-8"))
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md").read_text(encoding="utf-8")

    assert "LoadGenerationCompatibilityManifestBytes(snapshot)" in controller
    assert "LoadGenerationCanonicalManifestBytes(snapshot)" in controller
    assert 'HttpGet("/downloads/g/{generationId}/aur-packages.json")' in controller
    assert 'snapshot.OpenVerifiedFile($"release-evidence/{path}")' in program
    assert 'snapshot.OpenVerifiedFile($"proof/{path}")' in program
    assert 'snapshot.OpenVerifiedFile($"startup-smoke/{path}")' in program
    assert "static context => !IsGovernedReleaseStaticPath(context.Request.Path)" in program
    governed_gate = program[program.index("static bool IsGovernedReleaseStaticPath(") :]
    for governed_path in (
        "/downloads/RELEASE_CHANNEL.generated.json",
        "/downloads/releases.json",
        "/downloads/g",
        "/downloads/files",
        "/downloads/file",
        "/downloads/install",
        "/downloads/proof",
        "/downloads/startup-smoke",
        "/downloads/release-evidence",
    ):
        assert governed_path in governed_gate
    assert "/downloads/release-upload" not in governed_gate
    assert 'CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED: "${CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED:?' in compose
    assert 'CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED: "${CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED:?' in compose
    assert appsettings["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] is False
    assert "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED=true" in env_example
    assert "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED=false" in env_example
    assert "downgrade sentinel" in runbook
    assert "initial-release-shelf-cutover" in runbook
    assert "explicit first-shelf cutover uses `false/true`" in runbook
    assert "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED=false" in runbook
    assert "matching committed intent/outcome receipt" in runbook


def test_runtime_bounded_reader_uses_one_descriptor_and_checks_for_growth() -> None:
    source = (ROOT / "Chummer.Run.Api" / "Services" / "ReleaseShelfGenerationStore.cs").read_text(
        encoding="utf-8"
    )
    start = source.index("private static byte[] ReadBoundedFile(")
    end = source.index("private static JsonElement ParseJsonObject", start)
    body = source[start:end]

    assert "new FileStream(" in body
    assert "stream.Length" in body
    assert "stream.ReadExactly(bytes)" in body
    assert "stream.ReadByte() != -1" in body
    assert "File.ReadAllBytes" not in body


def test_layout_v1_reader_exposes_no_verify_then_reopen_path_api() -> None:
    offenders = []
    for source_path in (ROOT / "Chummer.Run.Api").rglob("*.cs"):
        source = source_path.read_text(encoding="utf-8")
        if ".ResolveExistingFile(" in source:
            offenders.append(source_path.relative_to(ROOT).as_posix())

    assert offenders == []


# Portable preview-contract fixtures. All receipts and authority statuses below
# are TEST_ONLY synthetic protocol data, never native or publication evidence.
_PREVIEW_AUTHORITY = MODULE.preview_authority
_PREVIEW_INSTALLER = "chummer-avalonia-win-x64-installer.exe"
_PREVIEW_PAYLOAD = "chummer-avalonia-win-x64-payload.zip"
_PREVIEW_GENERATION_ID = "synthetic-test-only-not-publication"
_PREVIEW_VERSION = "synthetic-test-only"
_PREVIEW_STAMP = "2026-11-14T09:00:00Z"
_PREVIEW_FOOTER_MARKER = b"CHUMMER6PAYLOAD1"


@pytest.mark.parametrize("declared_size", [0, 10, 11, 2**64 - 1])
def test_windows_unsigned_preview_footer_bounds_independent_of_sidecar(
    tmp_path: Path, declared_size: int,
) -> None:
    # The sidecar agrees with the footer, so only the independent byte bounds
    # can reject an empty payload or one consuming/overrunning the entire stub.
    installer = tmp_path / "fixture.exe"
    installer.write_bytes(b"MZ12345678" + declared_size.to_bytes(8, "little") + _PREVIEW_FOOTER_MARKER)
    sidecar = _preview_sidecar(b"fixture")
    sidecar["sizeBytes"] = declared_size
    with pytest.raises(MODULE.ReleaseShelfError, match="length or identity is invalid"):
        MODULE._validate_bootstrap_payload_trailer(installer, sidecar, "embedded")


@pytest.mark.parametrize("privacy_blocked", [False, True])
def test_windows_unsigned_preview_known_issue_matches_independent_expected_sentence(
    tmp_path: Path, privacy_blocked: bool,
) -> None:
    candidate = _write_unsigned_preview_candidate(tmp_path / "candidate")
    privacy = (
        json.loads(MODULE.PRIVACY_LAUNCH_GATE_CONTRACT.read_text(encoding="utf-8"))
        if privacy_blocked else _clear_privacy_contract()
    )
    expected = (
        "Known issue: stale or incomplete proof receipts and Hosted Build privacy, "
        "retention, recovery, and erasure review still block launch-readiness claims."
        if privacy_blocked else
        "Known issue: stale or incomplete proof receipts still block launch-readiness claims."
    )
    for name in (MODULE.CANONICAL_MANIFEST, MODULE.COMPATIBILITY_MANIFEST):
        manifest = json.loads((candidate / name).read_text(encoding="utf-8"))
        projected = MODULE.apply_current_release_supportability_floor(
            manifest, privacy, evaluated_at=_PREVIEW_STAMP,
        )
        assert projected["knownIssueSummary"] == expected
        disclosure = projected["message"].strip()
        assert "Unsigned Windows-only preview" in disclosure
        for field in ("rolloutReason", "supportabilitySummary", "fixAvailabilitySummary"):
            assert disclosure in projected[field]


def _preview_digest(data):
    return hashlib.sha256(data).hexdigest()


def _preview_write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    MODULE.write_json(path, obj)


def _preview_sidecar(data, version=_PREVIEW_VERSION):
    return dict(contractName=MODULE.PAYLOAD_SIDECAR_CONTRACT, fileName=_PREVIEW_PAYLOAD,
                downloadUrl=f'https://chummer.run/downloads/files/{_PREVIEW_PAYLOAD}',
                sha256=_preview_digest(data), sizeBytes=len(data), payloadAcquisitionMode='embedded',
                installerFileName=_PREVIEW_INSTALLER, releaseVersion=version)



@pytest.mark.parametrize('mutation', ['hash','length','zero','oversized','truncated-footer','truncated-body','tampered','boolean-length','missing-stub'])
def test_windows_unsigned_preview_embedded_invalid_bytes_fail(tmp_path, mutation):
    data = b'PK\x03\x04synthetic-payload-only'
    metadata = _preview_sidecar(data)
    exe = b'MZsynthetic-stub' + data + struct.pack('<Q', len(data)) + _PREVIEW_FOOTER_MARKER
    if mutation == 'hash': metadata['sha256'] = '0' * 64
    if mutation == 'length': metadata['sizeBytes'] += 1
    if mutation == 'zero': exe = exe[:-(8+len(_PREVIEW_FOOTER_MARKER))] + struct.pack('<Q',0) + _PREVIEW_FOOTER_MARKER
    if mutation == 'oversized': exe = exe[:-(8+len(_PREVIEW_FOOTER_MARKER))] + struct.pack('<Q',2**64-1) + _PREVIEW_FOOTER_MARKER
    if mutation == 'truncated-footer': exe = exe[:-1]
    if mutation == 'truncated-body': exe = exe[:20] + exe[25:]
    if mutation == 'tampered': exe = exe.replace(b'synthetic-payload', b'Synthetic-payload')
    if mutation == 'boolean-length': metadata['sizeBytes'] = True
    if mutation == 'missing-stub': exe = exe[len(b'MZsynthetic-stub'):]
    p = tmp_path / 'fixture.exe'; p.write_bytes(exe)
    with pytest.raises(MODULE.ReleaseShelfError): MODULE._validate_bootstrap_payload_trailer(p, metadata, 'embedded')


def _write_unsigned_preview_candidate(root):
    data=b'PK\x03\x04SYNTHETIC TEST PAYLOAD, NEVER PUBLISH'
    exe=b'MZ TEST ONLY'+data+struct.pack('<Q',len(data))+_PREVIEW_FOOTER_MARKER
    (root/'files').mkdir(parents=True)
    (root/'files'/_PREVIEW_INSTALLER).write_bytes(exe); (root/'files'/_PREVIEW_PAYLOAD).write_bytes(data)
    _preview_write_json(root/'files'/f'{_PREVIEW_PAYLOAD}.json',_preview_sidecar(data))
    artifact=dict(artifactId='avalonia-win-x64-installer', id='avalonia-win-x64-installer',
        head='avalonia', platform='windows',rid='win-x64',arch='x64',kind='installer',
        fileName=_PREVIEW_INSTALLER,downloadUrl=f'/downloads/files/{_PREVIEW_INSTALLER}',sha256=_preview_digest(exe),sizeBytes=len(exe),
        compatibilityState='compatible',installAccessClass='open_public',installerMode='bootstrap',
        payloadAcquisitionMode='embedded',payloadFileName=_PREVIEW_PAYLOAD,payloadDownloadUrl=f'/downloads/files/{_PREVIEW_PAYLOAD}',
        payloadSha256=_preview_digest(data),payloadSizeBytes=len(data))
    common=dict(version=_PREVIEW_VERSION,releaseVersion=_PREVIEW_VERSION,channel='preview',channelId='preview',status='published',
        publishedAt=_PREVIEW_STAMP,generatedAt=_PREVIEW_STAMP,publicationProfile='windows_unsigned_preview_v1',
        platformScope='windows_only',publicationScope={'signingStatus':'unsigned','sr6Qualification':'incomplete'},
        supportabilityState='review_required',rolloutState='public_release_review_required',
        message='Unsigned Windows-only preview. TEST_ONLY: SYNTHETIC FIXTURE; qualification incomplete; strict H1/H2 unrun.',
        knownIssueSummary='TEST_ONLY: SYNTHETIC FIXTURE. Native Windows not executed.',
        releaseProof={'status':'review_required','journeysPassed':[], 'proofRoutes':['/downloads']})
    _preview_write_json(root/MODULE.CANONICAL_MANIFEST, dict(common,artifacts=[artifact]))
    compat=copy.deepcopy(artifact); compat['url']=compat.pop('downloadUrl')
    _preview_write_json(root/MODULE.COMPATIBILITY_MANIFEST,dict(common,downloads=[compat]))
    # Reuse the real projector before binding authority to exact manifest bytes.
    MODULE.project_manifest_pair(root/MODULE.CANONICAL_MANIFEST,root/MODULE.COMPATIBILITY_MANIFEST,_PREVIEW_GENERATION_ID,evaluated_at=_PREVIEW_STAMP)
    canonical=json.loads((root/MODULE.CANONICAL_MANIFEST).read_text()); artifact=canonical['artifacts'][0]
    receipt=dict(status='pass',headId='avalonia',version=_PREVIEW_VERSION,releaseVersion=_PREVIEW_VERSION,channelId='preview',
        platform='windows',arch='x64',rid='win-x64',artifactDigest='sha256:'+artifact['sha256'],
        artifactSha256=artifact['sha256'],artifactId=artifact['artifactId'],artifactFileName=_PREVIEW_INSTALLER,
        fileName=_PREVIEW_INSTALLER,artifactRelativePath='files/'+_PREVIEW_INSTALLER,bootstrapPayloadSha256=artifact['payloadSha256'],
        bootstrapPayloadSizeBytes=artifact['payloadSizeBytes'],bootstrapPayloadFileName=_PREVIEW_PAYLOAD,
        testOnly='TEST_ONLY: SYNTHETIC FIXTURE. NOT NATIVE EVIDENCE OR PUBLICATION AUTHORITY.')
    _preview_write_json(root/_PREVIEW_AUTHORITY.SCOPE_BOUND_STARTUP_SMOKE_PATH,receipt)
    _write_test_preview_envelope(root,canonical)
    return root


def _write_test_preview_envelope(root,c):
    a=c['artifacts'][0]; manifest_digest=MODULE.sha256_file(root/MODULE.CANONICAL_MANIFEST)
    scope=_preview_digest(b'SYNTHETIC TEST SCOPE - NO AUTHORITY')
    handoff=dict(contractName='chummer.public-preview-byte-handoff/v1',status='approved_public_preview_bytes',
        sourcePublicationState='preview',releaseScopeDecisionSha256=scope,releaseVersion=_PREVIEW_VERSION,channel='preview',
        artifactId=a['artifactId'],head='avalonia',platform='windows',rid='win-x64',arch='x64',sha256=a['sha256'],
        sizeBytes=a['sizeBytes'],artifactAccessClass='open_public',signingRequirement='preview_unsigned_allowed',
        downloadUrl=a['downloadUrl'],publicInstallRoute='/downloads/install/'+a['artifactId'])
    decision=dict(contractName='chummer.preview-release-decision/v2',generatedAt=_PREVIEW_STAMP,status='review_required',
        releaseDecisionStatus='review_required',verdict='PREVIEW_RELEASE_REVIEW_REQUIRED',releaseVersion=_PREVIEW_VERSION,
        releaseScopeDecisionSha256=scope,channel='preview',platforms=['windows'],primaryHeadByPlatform={'windows':'avalonia'},
        fallbackHeadsByPlatform={'windows':[]},artifactAccessClass='open_public',supportOwner='synthetic-test-only',
        nextActions=['TEST_ONLY: SYNTHETIC FIXTURE. Never publish.'],registryCommit='1'*40,manifestSha256=manifest_digest,
        authoritySnapshotSha256='',candidateDecisionStatus='',candidateDecisionSha256='',manifestGeneratedAt=_PREVIEW_STAMP,
        scorecardSha256='',convergenceSha256='',blockingFindings=[dict(id='preview_1',severity='release_truth',summary='TEST_ONLY: synthetic finding; never publish.')],
        artifactHandoff=handoff)
    ep=root/'release-evidence'; _preview_write_json(ep/'RELEASE_DECISION.json',decision)
    sa={k:a[k] for k in ['artifactId','head','platform','rid','arch','kind','downloadUrl','sha256','sizeBytes','compatibilityState','installAccessClass']}
    sa.update(promotionState='promoted',publicationScope='signed-in-and-public',revokeState='not_revoked',publicInstallRoute='/downloads/install/'+a['artifactId'])
    snapshot=dict(authorityContract='chummer.release-authority-snapshot/v2',releaseVersion=_PREVIEW_VERSION,channel='preview',
        status='published',rolloutState='public_release_review_required',supportabilityState='review_required',availablePlatforms=['windows'],
        primaryHeadByPlatform={'windows':'avalonia'},artifactCount=1,downloadAccessPosture='open_public',knownIssueSummary=c['knownIssueSummary'],
        manifestSha256=manifest_digest,registryRepository='ArchonMegalon/chummer6-hub-registry',registryCommit='1'*40,
        releaseDecisionStatus='review_required',releaseDecisionSha256=MODULE.sha256_file(ep/'RELEASE_DECISION.json'),
        supportOwner=decision['supportOwner'],nextActions=decision['nextActions'],artifacts=[sa],manifestPath='RELEASE_CHANNEL.json',
        releaseDecisionPath='RELEASE_DECISION.json')
    _preview_write_json(ep/'SNAPSHOT.json',snapshot)
    _preview_write_json(ep/'CURRENT.json',dict(releaseVersion=_PREVIEW_VERSION,status='review_required',
        snapshotSha256=MODULE.sha256_file(ep/'SNAPSHOT.json'),decisionSha256=MODULE.sha256_file(ep/'RELEASE_DECISION.json')))


def _prepare_unsigned_preview(candidate,tmp):
    p=MODULE.prepare_layout(candidate,tmp/'prepared',generation_id=_PREVIEW_GENERATION_ID,activated_at=_PREVIEW_STAMP,activation_receipt_id='synthetic-test-only')
    generation=tmp/'prepared/generations'/_PREVIEW_GENERATION_ID
    MODULE.verify_generation(generation,p)
    return generation,p


def test_windows_unsigned_preview_mandatory_bound_metadata_prepares_and_verifies(tmp_path):
    candidate=_write_unsigned_preview_candidate(tmp_path/'candidate')
    generation,pointer=_prepare_unsigned_preview(candidate,tmp_path)
    inventory=json.loads((generation/MODULE.ACTIVATION_CANDIDATE).read_text())['inventory']
    assert set(_PREVIEW_AUTHORITY.SCOPE_BOUND_REVIEW_EVIDENCE_PATHS).issubset({x['path'] for x in inventory})
    assert json.loads((generation/MODULE.CANONICAL_MANIFEST).read_text())['publicationProfile']=='windows_unsigned_preview_v1'


def _replace_preview_findings(candidate, findings):
    # Rebind TEST_ONLY hashes so rejection tests the decision contract, not a
    # stale outer checksum. These receipts never establish native acceptance.
    evidence = candidate / 'release-evidence'
    decision_path = evidence / 'RELEASE_DECISION.json'
    decision = json.loads(decision_path.read_text())
    decision['blockingFindings'] = findings
    _preview_write_json(decision_path, decision)
    snapshot_path = evidence / 'SNAPSHOT.json'
    snapshot = json.loads(snapshot_path.read_text())
    snapshot['releaseDecisionSha256'] = MODULE.sha256_file(decision_path)
    _preview_write_json(snapshot_path, snapshot)
    pointer_path = evidence / 'CURRENT.json'
    pointer = json.loads(pointer_path.read_text())
    pointer['decisionSha256'] = MODULE.sha256_file(decision_path)
    pointer['snapshotSha256'] = MODULE.sha256_file(snapshot_path)
    _preview_write_json(pointer_path, pointer)


@pytest.fixture(scope='module')
def preview_cutover_controller():
    import sys
    spec = importlib.util.spec_from_file_location(
        'preview_finding_cutover_test', ROOT / 'scripts/deploy_public_download_only_cutover.py')
    assert spec is not None and spec.loader is not None
    controller = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = controller
    spec.loader.exec_module(controller)
    return controller


def _validate_preview_at_cutover(candidate, controller):
    raw = (candidate / MODULE.CANONICAL_MANIFEST).read_bytes()
    return controller._validate_scope_bound_review_authority(
        canonical_raw=raw, canonical=json.loads(raw),
        evidence_bytes={name: (candidate / name).read_bytes()
                        for name in controller.SCOPE_BOUND_REVIEW_EVIDENCE_PATHS},
        generation_id=_PREVIEW_GENERATION_ID,
        release_scope_decision_sha256=_preview_digest(b'SYNTHETIC TEST SCOPE - NO AUTHORITY'),
        candidate_version=_PREVIEW_VERSION,
    )


@pytest.mark.parametrize('mutation', [
    'old-arbitrary-id', 'wrong-order', 'duplicate-id', 'wrong-severity',
    'empty-summary', 'padded-summary', 'long-summary', 'long-utf16-summary',
    'too-many-findings',
])
def test_windows_unsigned_preview_rejects_http_incompatible_findings(tmp_path, mutation, preview_cutover_controller):
    candidate = _write_unsigned_preview_candidate(tmp_path / 'candidate')
    findings = [dict(id='preview_1', severity='release_truth', summary='TEST_ONLY')]
    if mutation == 'old-arbitrary-id': findings[0]['id'] = 'synthetic'
    if mutation == 'wrong-order': findings[0]['id'] = 'preview_2'
    if mutation == 'duplicate-id': findings.append(dict(findings[0]))
    if mutation == 'wrong-severity': findings[0]['severity'] = 'warning'
    if mutation == 'empty-summary': findings[0]['summary'] = ''
    if mutation == 'padded-summary': findings[0]['summary'] = ' TEST_ONLY '
    if mutation == 'long-summary': findings[0]['summary'] = 'x' * 513
    if mutation == 'long-utf16-summary': findings[0]['summary'] = '\U0001f600' * 257
    if mutation == 'too-many-findings':
        findings = [dict(id=f'preview_{index}', severity='release_truth', summary='TEST_ONLY')
                    for index in range(1, 258)]
    _replace_preview_findings(candidate, findings)
    with pytest.raises(preview_cutover_controller.CutoverError):
        _validate_preview_at_cutover(candidate, preview_cutover_controller)
    with pytest.raises(MODULE.ReleaseShelfError):
        _prepare_unsigned_preview(candidate, tmp_path)


@pytest.mark.parametrize('boundary', ['512-utf16-units', '256-findings'])
def test_windows_unsigned_preview_accepts_http_finding_boundaries(tmp_path, boundary, preview_cutover_controller):
    candidate = _write_unsigned_preview_candidate(tmp_path / 'candidate')
    findings = ([dict(id='preview_1', severity='release_truth', summary='\U0001f600' * 256)]
                if boundary == '512-utf16-units' else
                [dict(id=f'preview_{index}', severity='release_truth', summary='TEST_ONLY')
                 for index in range(1, 257)])
    _replace_preview_findings(candidate, findings)
    _validate_preview_at_cutover(candidate, preview_cutover_controller)
    _prepare_unsigned_preview(candidate, tmp_path)



@pytest.mark.parametrize('mutation',['extra-file','extra-evidence','extra-directory','missing-proof','corrupt-proof','missing-smoke','wrong-smoke',
    'path-escape','symlink-file','symlink-directory','duplicate-json','manifest-drift','unknown-field','boolean-count','broader-posture'])
def test_windows_unsigned_preview_preparation_rejects_invalid_selected_tree(tmp_path,mutation):
    c=_write_unsigned_preview_candidate(tmp_path/'candidate'); ep=c/'release-evidence'
    if mutation=='extra-file': (c/'files/private.txt').write_text('private')
    if mutation=='extra-evidence': (ep/'private.json').write_text('{}')
    if mutation=='extra-directory': (ep/'unselected').mkdir()
    if mutation=='missing-proof': (ep/'SNAPSHOT.json').unlink()
    if mutation=='corrupt-proof': (ep/'RELEASE_DECISION.json').write_bytes(b'{}')
    if mutation=='missing-smoke': (c/_PREVIEW_AUTHORITY.SCOPE_BOUND_STARTUP_SMOKE_PATH).unlink()
    if mutation=='wrong-smoke': (c/_PREVIEW_AUTHORITY.SCOPE_BOUND_STARTUP_SMOKE_PATH).write_bytes(b'{}')
    if mutation=='symlink-file':
        (ep/'SNAPSHOT.json').rename(tmp_path/'outside'); (ep/'SNAPSHOT.json').symlink_to(tmp_path/'outside')
    if mutation=='symlink-directory':
        ep.rename(tmp_path/'outside'); ep.symlink_to(tmp_path/'outside',target_is_directory=True)
    if mutation=='duplicate-json':
        p=ep/'CURRENT.json';p.write_text(p.read_text().replace('{','{"status":"review_required",',1))
    if mutation=='manifest-drift':
        p=c/MODULE.CANONICAL_MANIFEST;d=json.loads(p.read_text());d['knownIssueSummary']+=' drift';_preview_write_json(p,d)
    if mutation in ('path-escape','unknown-field','boolean-count','broader-posture'):
        p=ep/'SNAPSHOT.json';d=json.loads(p.read_text())
        if mutation=='path-escape': d['releaseDecisionPath']='../../outside.json'
        if mutation=='unknown-field': d['privateMetadata']='never admit'
        if mutation=='boolean-count': d['artifactCount']=True
        if mutation=='broader-posture': d['supportabilityState']='gold_supported'
        _preview_write_json(p,d)
        pointer=json.loads((ep/'CURRENT.json').read_text());pointer['snapshotSha256']=MODULE.sha256_file(p);_preview_write_json(ep/'CURRENT.json',pointer)
    with pytest.raises(MODULE.ReleaseShelfError): _prepare_unsigned_preview(c,tmp_path)



@pytest.mark.parametrize('missing',list(_PREVIEW_AUTHORITY.SCOPE_BOUND_REVIEW_EVIDENCE_PATHS))
def test_windows_unsigned_preview_each_authority_sibling_required_once_selected(tmp_path,missing):
    c=_write_unsigned_preview_candidate(tmp_path/'candidate'); (c/missing).unlink()
    with pytest.raises(MODULE.ReleaseShelfError): _prepare_unsigned_preview(c,tmp_path)


def test_windows_unsigned_preview_verify_rejects_corrupted_proof(tmp_path):
    c=_write_unsigned_preview_candidate(tmp_path/'candidate'); generation,pointer=_prepare_unsigned_preview(c,tmp_path)
    proof=generation/'release-evidence/SNAPSHOT.json';proof.chmod(0o644);proof.write_bytes(b'{}')
    with pytest.raises(MODULE.ReleaseShelfError): MODULE.verify_generation(generation,pointer,require_sealed_modes=False)


def test_windows_unsigned_preview_no_envelope_is_separate_runtime_supported_route(tmp_path):
    c=_write_unsigned_preview_candidate(tmp_path/'candidate')
    for p in _PREVIEW_AUTHORITY.SCOPE_BOUND_REVIEW_EVIDENCE_PATHS: (c/p).unlink()
    # A newly selected six-file contract, not deletion of a required old proof.
    (c/'release-evidence').rmdir()
    _prepare_unsigned_preview(c,tmp_path)


def test_windows_unsigned_preview_no_envelope_still_requires_candidate_bound_smoke(tmp_path):
    c=_write_unsigned_preview_candidate(tmp_path/'candidate')
    for p in _PREVIEW_AUTHORITY.SCOPE_BOUND_REVIEW_EVIDENCE_PATHS: (c/p).unlink()
    smoke=c/_PREVIEW_AUTHORITY.SCOPE_BOUND_STARTUP_SMOKE_PATH
    receipt=json.loads(smoke.read_text());receipt['artifactSha256']='0'*64;_preview_write_json(smoke,receipt)
    with pytest.raises(MODULE.ReleaseShelfError,match='startup-smoke receipt contradicts'):
        _prepare_unsigned_preview(c,tmp_path)



@pytest.mark.parametrize('mutation',['proof-digest','unselected-file','unselected-generated-metadata','path-escape'])
def test_windows_unsigned_preview_verify_rechecks_contract_even_if_outer_inventory_rebound(tmp_path,mutation):
    c=_write_unsigned_preview_candidate(tmp_path/'candidate');g,pointer=_prepare_unsigned_preview(c,tmp_path)
    for p in [g,*g.rglob('*')]:p.chmod(0o755 if p.is_dir() else 0o644)
    if mutation=='unselected-file':(g/'release-evidence/private.json').write_bytes(b'{}')
    elif mutation=='unselected-generated-metadata':(g/MODULE.PUBLICATION_SCOPE).write_bytes(b'{}')
    else:
        p=g/'release-evidence/SNAPSHOT.json';d=json.loads(p.read_text())
        if mutation=='proof-digest':d['knownIssueSummary']='tampered'
        else:d['releaseDecisionPath']='../../escape.json'
        _preview_write_json(p,d)
        if mutation=='path-escape':
            p=g/'release-evidence/CURRENT.json';d=json.loads(p.read_text());d['snapshotSha256']=MODULE.sha256_file(g/'release-evidence/SNAPSHOT.json');_preview_write_json(p,d)
    activation=json.loads((g/MODULE.ACTIVATION_CANDIDATE).read_text())
    activation['inventory']=MODULE.build_inventory(g)
    activation['inventoryDigest']='sha256:'+MODULE.inventory_digest(activation['inventory'])
    pointer['inventoryDigest']=activation['inventoryDigest'];_preview_write_json(g/MODULE.ACTIVATION_CANDIDATE,activation)
    with pytest.raises(MODULE.ReleaseShelfError):MODULE.verify_generation(g,pointer,require_sealed_modes=False)


def test_windows_unsigned_preview_footer_magic_in_payload_is_not_a_second_footer(tmp_path):
    data=b'PK\x03\x04'+_PREVIEW_FOOTER_MARKER+b'synthetic fixture'
    p=tmp_path/'fixture.exe';p.write_bytes(b'MZ stub'+data+struct.pack('<Q',len(data))+_PREVIEW_FOOTER_MARKER)
    MODULE._validate_bootstrap_payload_trailer(p,_preview_sidecar(data),'embedded')
