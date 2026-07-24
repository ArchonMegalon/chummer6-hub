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


def release_truth() -> dict[str, Any]:
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
        "manifestSha256": MANIFEST_SHA256,
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
) -> dict[str, Any]:
    return {
        "releaseCandidateAuthority": {
            "candidateVersion": RELEASE_VERSION,
            "generationId": GENERATION_ID,
            "canonicalManifestSha256": MANIFEST_SHA256,
            "releaseScopeDecisionSha256": SCOPE_SHA256,
            "sourceCommits": {"registry": REGISTRY_COMMIT},
            "reviewRequiredReleaseTruth": truth,
            "reviewAuthority": {
                "contractName": (
                    "chummer.review-required-public-byte-authority/v1"
                ),
                "status": "pass",
                "generationId": GENERATION_ID,
                "manifestSha256": MANIFEST_SHA256,
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
    generation_header: str = GENERATION_ID,
    expected_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        path="/downloads/RELEASE_CHANNEL.generated.json",
        expected=json.dumps(prepared).encode(),
        shelf=release_truth_shelf(
            release_truth() if expected_truth is None else expected_truth
        ),
        generation_id=GENERATION_ID,
    )


@pytest.mark.parametrize("collection", ("artifacts", "downloads"))
def test_manifest_envelope_accepts_only_release_truth_and_semantic_ordering(
    monkeypatch: pytest.MonkeyPatch,
    collection: str,
) -> None:
    prepared = prepared_manifest()
    if collection == "downloads":
        artifact = prepared.pop("artifacts")[0]
        artifact["url"] = artifact["downloadUrl"]
        prepared["publicVersion"] = RELEASE_VERSION
        prepared["downloads"] = [artifact]
    truth = release_truth()
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
    )

    assert receipt["httpStatus"] == 200
    assert receipt["bodySha256"] == hashlib.sha256(served).hexdigest()
    assert receipt["sizeBytes"] == len(served)
    assert receipt["generationId"] == GENERATION_ID


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
    truth = release_truth()
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
    with pytest.raises(controller.CutoverError):
        probe(
            monkeypatch,
            prepared=prepared_manifest(),
            served=served,
        )
