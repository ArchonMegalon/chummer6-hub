from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_PATH = ROOT / "scripts" / "deploy_public_download_only_cutover.py"
GENERATION_ID = "g-20260724T152516Z-6907464d-c779a59"
RELEASE_VERSION = "run-20260723-230227"
ARTIFACT_ID = "avalonia-win-x64-installer"
ARTIFACT_FILE_NAME = "chummer-avalonia-win-x64-installer.exe"
ARTIFACT_SHA256 = "8" * 64
MANIFEST_SHA256 = "a" * 64
DECISION_SHA256 = "b" * 64
SCOPE_SHA256 = "c" * 64
REGISTRY_COMMIT = "d" * 40
DECISION_REGISTRY_COMMIT = "f" * 40


def load_controller() -> Any:
    spec = importlib.util.spec_from_file_location(
        "public_download_manifest_envelope",
        CONTROLLER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_controller()


def prepared_manifest() -> dict[str, Any]:
    return {
        "generationId": GENERATION_ID,
        "version": RELEASE_VERSION,
        "releaseVersion": RELEASE_VERSION,
        "channel": "preview",
        "channelId": "preview",
        "status": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "knownIssueSummary": "Preview remains review-required.",
        "registryCommit": REGISTRY_COMMIT,
        "registry_commit": REGISTRY_COMMIT,
        "artifacts": [
            {
                "artifactId": ARTIFACT_ID,
                "id": ARTIFACT_ID,
                "fileName": ARTIFACT_FILE_NAME,
                "downloadUrl": (
                    f"/downloads/g/{GENERATION_ID}/files/"
                    f"{ARTIFACT_FILE_NAME}"
                ),
                "head": "avalonia",
                "platform": "windows",
                "rid": "win-x64",
                "arch": "x64",
                "sha256": ARTIFACT_SHA256,
                "sizeBytes": 2_734_880,
                "installAccessClass": "open_public",
            }
        ],
    }


def release_truth(
    *,
    manifest_sha256: str = MANIFEST_SHA256,
) -> dict[str, Any]:
    return {
        "contractName": "chummer.release-truth-projection/v1",
        "releaseVersion": RELEASE_VERSION,
        "channel": "preview",
        "releaseStatus": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "avalonia"},
        "artifactCount": 1,
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "Preview remains review-required.",
        "manifestSha256": manifest_sha256,
        "registryCommit": DECISION_REGISTRY_COMMIT,
        "releaseDecisionStatus": "review_required",
        "releaseDecisionSha256": DECISION_SHA256,
        "releaseScopeDecisionSha256": SCOPE_SHA256,
        "artifactHandoff": {
            "contractName": "chummer.public-preview-byte-handoff/v1",
            "status": "approved_public_preview_bytes",
            "sourcePublicationState": "preview",
            "releaseScopeDecisionSha256": SCOPE_SHA256,
            "releaseVersion": RELEASE_VERSION,
            "channel": "preview",
            "artifactId": ARTIFACT_ID,
            "head": "avalonia",
            "platform": "windows",
            "rid": "win-x64",
            "arch": "x64",
            "sha256": ARTIFACT_SHA256,
            "sizeBytes": 2_734_880,
            "artifactAccessClass": "open_public",
            "signingRequirement": "preview_unsigned_allowed",
            "downloadUrl": (
                f"/downloads/g/{GENERATION_ID}/files/"
                f"{ARTIFACT_FILE_NAME}"
            ),
            "publicInstallRoute": f"/downloads/install/{ARTIFACT_ID}",
        },
    }


def release_truth_shelf(
    truth: dict[str, Any],
    *,
    prepared_sha256: str,
    manifest_kind: str,
) -> dict[str, Any]:
    canonical_sha256 = str(truth["manifestSha256"])
    compatibility_sha256 = (
        prepared_sha256
        if manifest_kind == "compatibility"
        else "9" * 64
    )
    if manifest_kind == "canonical":
        assert canonical_sha256 == prepared_sha256
    return {
        "generationId": GENERATION_ID,
        "canonicalMirrorSha256": canonical_sha256,
        "compatibilityMirrorSha256": compatibility_sha256,
        "generationCanonicalSha256": canonical_sha256,
        "generationCompatibilitySha256": compatibility_sha256,
        "releaseCandidateAuthority": {
            "candidateVersion": RELEASE_VERSION,
            "generationId": GENERATION_ID,
            "canonicalManifestSha256": canonical_sha256,
            "releaseScopeDecisionSha256": SCOPE_SHA256,
            "sourceCommits": {"registry": REGISTRY_COMMIT},
            "reviewRequiredReleaseTruth": truth,
            "reviewAuthority": {
                "contractName": (
                    "chummer.review-required-public-byte-authority/v1"
                ),
                "status": "pass",
                "generationId": GENERATION_ID,
                "manifestSha256": canonical_sha256,
                "releaseScopeDecisionSha256": SCOPE_SHA256,
                "authoritySnapshotSha256": "e" * 64,
                "releaseDecisionSha256": DECISION_SHA256,
            },
        }
    }


def probe(
    monkeypatch: pytest.MonkeyPatch,
    *,
    prepared: dict[str, Any],
    served: bytes,
    manifest_kind: str = "canonical",
    generation_header: str = GENERATION_ID,
    expected_truth: dict[str, Any],
    shelf: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prepared_bytes = json.dumps(prepared).encode()
    authority_shelf = shelf or release_truth_shelf(
        expected_truth,
        prepared_sha256=hashlib.sha256(prepared_bytes).hexdigest(),
        manifest_kind=manifest_kind,
    )
    monkeypatch.setattr(
        controller,
        "_http_bytes",
        lambda **_kwargs: (
            200,
            {"x-chummer-release-generation": generation_header},
            served,
        ),
    )
    return controller._probe_exact_manifest(
        scheme="http",
        connect_host="172.17.0.1",
        connect_port=18091,
        request_host="chummer.run",
        path=(
            "/downloads/RELEASE_CHANNEL.generated.json"
            if manifest_kind == "canonical"
            else "/downloads/releases.json"
        ),
        expected=prepared_bytes,
        shelf=authority_shelf,
        generation_id=GENERATION_ID,
    )


@pytest.mark.parametrize(
    "collection",
    ("artifacts", "downloads"),
    ids=("canonical", "sealed-v6-compatibility-null-legacy-aliases"),
)
def test_manifest_envelope_accepts_canonical_and_sealed_v6_compatibility(
    monkeypatch: pytest.MonkeyPatch,
    collection: str,
) -> None:
    prepared = prepared_manifest()
    if collection == "downloads":
        artifact = prepared.pop("artifacts")[0]
        artifact["url"] = artifact["downloadUrl"]
        prepared["publicVersion"] = None
        prepared["channelId"] = None
        prepared["downloads"] = [artifact]
    manifest_kind = (
        "canonical" if collection == "artifacts" else "compatibility"
    )
    prepared_sha256 = hashlib.sha256(
        json.dumps(prepared).encode()
    ).hexdigest()
    truth = release_truth(
        manifest_sha256=(
            prepared_sha256
            if manifest_kind == "canonical"
            else MANIFEST_SHA256
        )
    )
    assert len(truth) == 17
    assert len(truth["artifactHandoff"]) == 17
    served_payload = {
        "releaseTruth": {
            key: truth[key]
            for key in reversed(tuple(truth))
        },
        **{
            key: prepared[key]
            for key in reversed(tuple(prepared))
        },
    }
    served = json.dumps(
        served_payload,
        separators=(",", ":"),
    ).encode()

    receipt = probe(
        monkeypatch,
        prepared=prepared,
        served=served,
        manifest_kind=manifest_kind,
        expected_truth=truth,
    )

    assert receipt["httpStatus"] == 200
    assert receipt["bodySha256"] == hashlib.sha256(served).hexdigest()
    assert receipt["sizeBytes"] == len(served)
    assert receipt["generationId"] == GENERATION_ID


def test_manifest_envelope_rejects_coordinated_authority_generation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = prepared_manifest()
    prepared_sha256 = hashlib.sha256(
        json.dumps(prepared).encode()
    ).hexdigest()
    truth = release_truth(manifest_sha256=prepared_sha256)
    shelf = release_truth_shelf(
        truth,
        prepared_sha256=prepared_sha256,
        manifest_kind="canonical",
    )
    drifted_generation = "g-20260724T152516Z-6907464d-deadbee"
    shelf["generationId"] = drifted_generation
    authority = shelf["releaseCandidateAuthority"]
    authority["generationId"] = drifted_generation
    authority["reviewAuthority"]["generationId"] = drifted_generation

    with pytest.raises(controller.CutoverError):
        probe(
            monkeypatch,
            prepared=prepared,
            served=json.dumps(
                {**prepared, "releaseTruth": truth}
            ).encode(),
            expected_truth=truth,
            shelf=shelf,
        )


@pytest.mark.parametrize(
    "manifest_kind",
    ("canonical", "compatibility"),
)
def test_manifest_envelope_rejects_coordinated_authority_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
    manifest_kind: str,
) -> None:
    prepared = prepared_manifest()
    if manifest_kind == "compatibility":
        artifact = prepared.pop("artifacts")[0]
        artifact["url"] = artifact["downloadUrl"]
        prepared["publicVersion"] = None
        prepared["channelId"] = None
        prepared["downloads"] = [artifact]
    prepared_sha256 = hashlib.sha256(
        json.dumps(prepared).encode()
    ).hexdigest()
    truth = release_truth(
        manifest_sha256=(
            prepared_sha256
            if manifest_kind == "canonical"
            else MANIFEST_SHA256
        )
    )
    shelf = release_truth_shelf(
        truth,
        prepared_sha256=prepared_sha256,
        manifest_kind=manifest_kind,
    )
    drifted_sha256 = "f" * 64
    authority = shelf["releaseCandidateAuthority"]
    if manifest_kind == "canonical":
        drifted_truth = copy.deepcopy(truth)
        drifted_truth["manifestSha256"] = drifted_sha256
        shelf["canonicalMirrorSha256"] = drifted_sha256
        shelf["generationCanonicalSha256"] = drifted_sha256
        authority["canonicalManifestSha256"] = drifted_sha256
        authority["reviewAuthority"]["manifestSha256"] = drifted_sha256
        authority["reviewRequiredReleaseTruth"] = drifted_truth
        truth = drifted_truth
    else:
        shelf["compatibilityMirrorSha256"] = drifted_sha256
        shelf["generationCompatibilitySha256"] = drifted_sha256

    with pytest.raises(controller.CutoverError):
        probe(
            monkeypatch,
            prepared=prepared,
            served=json.dumps(
                {**prepared, "releaseTruth": truth}
            ).encode(),
            manifest_kind=manifest_kind,
            expected_truth=truth,
            shelf=shelf,
        )


@pytest.mark.parametrize(
    "alias_value",
    (0, False, "", " preview ", "stable"),
)
def test_manifest_envelope_rejects_invalid_nonnull_legacy_alias(
    monkeypatch: pytest.MonkeyPatch,
    alias_value: Any,
) -> None:
    prepared = prepared_manifest()
    artifact = prepared.pop("artifacts")[0]
    artifact["url"] = artifact["downloadUrl"]
    prepared["publicVersion"] = None
    prepared["channelId"] = alias_value
    prepared["downloads"] = [artifact]
    truth = release_truth()

    with pytest.raises(controller.CutoverError):
        probe(
            monkeypatch,
            prepared=prepared,
            served=json.dumps(
                {**prepared, "releaseTruth": truth}
            ).encode(),
            manifest_kind="compatibility",
            expected_truth=truth,
        )


@pytest.mark.parametrize(
    "case",
    (
        "missing",
        "extra_truth_field",
        "wrong_handoff_generation",
        "underlying_payload_drift",
        "wrong_expected_authority",
        "generation_header_drift",
    ),
)
def test_manifest_envelope_rejects_missing_extra_or_wrong_contract(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    prepared = prepared_manifest()
    truth = release_truth(
        manifest_sha256=hashlib.sha256(
            json.dumps(prepared).encode()
        ).hexdigest()
    )
    expected_truth = copy.deepcopy(truth)
    served_payload = {**prepared, "releaseTruth": truth}
    generation_header = GENERATION_ID
    if case == "missing":
        served_payload.pop("releaseTruth")
    elif case == "extra_truth_field":
        truth["unexpected"] = "must-fail"
    elif case == "wrong_handoff_generation":
        truth["artifactHandoff"]["downloadUrl"] = (
            "/downloads/g/other-generation/files/"
            f"{ARTIFACT_FILE_NAME}"
        )
        expected_truth = copy.deepcopy(truth)
    elif case == "underlying_payload_drift":
        served_payload["status"] = "revoked"
    elif case == "wrong_expected_authority":
        expected_truth["releaseDecisionSha256"] = "e" * 64
    elif case == "generation_header_drift":
        generation_header = "other-generation"

    with pytest.raises(controller.CutoverError):
        probe(
            monkeypatch,
            prepared=prepared,
            served=json.dumps(served_payload).encode(),
            generation_header=generation_header,
            expected_truth=expected_truth,
        )


@pytest.mark.parametrize(
    "served",
    (
        b"[]",
        b'{"releaseTruth":{},"releaseTruth":{}}',
        b'{"releaseTruth":{},"ReleaseTruth":{}}',
        b'{"releaseTruth":{},"value":NaN}',
        b'{"releaseTruth":{},"value":1e999}',
    ),
)
def test_manifest_envelope_rejects_nonobject_duplicate_and_nonfinite_json(
    monkeypatch: pytest.MonkeyPatch,
    served: bytes,
) -> None:
    prepared = prepared_manifest()
    truth = release_truth(
        manifest_sha256=hashlib.sha256(
            json.dumps(prepared).encode()
        ).hexdigest()
    )
    with pytest.raises(controller.CutoverError):
        probe(
            monkeypatch,
            prepared=prepared,
            served=served,
            expected_truth=truth,
        )
