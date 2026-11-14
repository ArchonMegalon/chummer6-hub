"""Bounded existing Hub review-required envelope contract; no authority grant.

Extracted from scripts/deploy_public_download_only_cutover.py for release-shelf
intake validation. This module performs no deployment or authority approval.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

class CutoverError(ValueError):
    pass

SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

SCOPE_BOUND_REVIEW_EVIDENCE_PATHS = (
    "release-evidence/CURRENT.json",
    "release-evidence/RELEASE_DECISION.json",
    "release-evidence/SNAPSHOT.json",
)

SCOPE_BOUND_STARTUP_SMOKE_PATH = (
    "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json"
)

REVIEW_AUTHORITY_CURRENT_FIELDS = frozenset(
    {"releaseVersion", "snapshotSha256", "decisionSha256", "status"}
)

REVIEW_AUTHORITY_SNAPSHOT_FIELDS = frozenset(
    {
        "authorityContract",
        "releaseVersion",
        "channel",
        "status",
        "rolloutState",
        "supportabilityState",
        "availablePlatforms",
        "primaryHeadByPlatform",
        "artifactCount",
        "downloadAccessPosture",
        "knownIssueSummary",
        "manifestSha256",
        "registryRepository",
        "registryCommit",
        "releaseDecisionStatus",
        "releaseDecisionSha256",
        "supportOwner",
        "nextActions",
        "artifacts",
        "manifestPath",
        "releaseDecisionPath",
    }
)

REVIEW_AUTHORITY_ARTIFACT_FIELDS = frozenset(
    {
        "artifactId",
        "head",
        "platform",
        "rid",
        "arch",
        "kind",
        "downloadUrl",
        "sha256",
        "sizeBytes",
        "compatibilityState",
        "promotionState",
        "publicationScope",
        "revokeState",
        "publicInstallRoute",
        "installAccessClass",
    }
)

REVIEW_AUTHORITY_DECISION_FIELDS = frozenset(
    {
        "contractName",
        "generatedAt",
        "status",
        "releaseDecisionStatus",
        "verdict",
        "releaseVersion",
        "releaseScopeDecisionSha256",
        "channel",
        "platforms",
        "primaryHeadByPlatform",
        "fallbackHeadsByPlatform",
        "artifactAccessClass",
        "supportOwner",
        "nextActions",
        "registryCommit",
        "manifestSha256",
        "authoritySnapshotSha256",
        "candidateDecisionStatus",
        "candidateDecisionSha256",
        "manifestGeneratedAt",
        "scorecardSha256",
        "convergenceSha256",
        "blockingFindings",
        "artifactHandoff",
    }
)

REVIEW_AUTHORITY_HANDOFF_FIELDS = frozenset(
    {
        "contractName",
        "status",
        "sourcePublicationState",
        "releaseScopeDecisionSha256",
        "releaseVersion",
        "channel",
        "artifactId",
        "head",
        "platform",
        "rid",
        "arch",
        "sha256",
        "sizeBytes",
        "artifactAccessClass",
        "signingRequirement",
        "downloadUrl",
        "publicInstallRoute",
    }
)

def _strict_json_object_bytes(
    raw: bytes,
    *,
    label: str,
) -> dict[str, Any]:
    def unique_object(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        normalized: set[str] = set()
        for key, value in pairs:
            folded = key.casefold()
            if folded in normalized:
                raise ValueError(f"duplicate JSON key: {key}")
            normalized.add(folded)
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    def finite_decimal(value: str) -> Decimal:
        try:
            binary_value = float(value)
            exact_value = Decimal(value)
        except (InvalidOperation, OverflowError, ValueError) as exc:
            raise ValueError(
                f"invalid finite JSON number: {value}"
            ) from exc
        if not math.isfinite(binary_value) or not exact_value.is_finite():
            raise ValueError(f"non-finite JSON number: {value}")
        return exact_value

    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=finite_decimal,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CutoverError(f"{label} is not strict JSON") from exc
    if not isinstance(parsed, dict):
        raise CutoverError(f"{label} must be a JSON object")
    return parsed

def _json_semantically_equal(actual: Any, expected: Any) -> bool:
    """Compare JSON values without Python's bool/int/Decimal coercions."""

    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(
                _json_semantically_equal(actual[key], expected[key])
                for key in expected
            )
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _json_semantically_equal(actual_item, expected_item)
                for actual_item, expected_item in zip(
                    actual,
                    expected,
                    strict=True,
                )
            )
        )
    return type(actual) is type(expected) and actual == expected

def _validate_scope_bound_startup_smoke(
    raw: bytes,
    *,
    artifact: Mapping[str, Any],
    release_version: str,
) -> dict[str, Any]:
    receipt = _strict_json_object_bytes(
        raw,
        label="scope-bound Windows startup-smoke receipt",
    )
    file_name = str(artifact.get("fileName") or "")
    payload_name = str(artifact.get("payloadFileName") or "")
    sha256 = str(artifact.get("sha256") or "")
    payload_sha256 = str(artifact.get("payloadSha256") or "")
    payload_size = artifact.get("payloadSizeBytes")
    expected = {
        "status": "pass",
        "headId": "avalonia",
        "version": release_version,
        "releaseVersion": release_version,
        "channelId": "preview",
        "platform": "windows",
        "arch": "x64",
        "rid": "win-x64",
        "artifactDigest": f"sha256:{sha256}",
        "artifactSha256": sha256,
        "artifactId": artifact.get("artifactId"),
        "artifactFileName": file_name,
        "fileName": file_name,
        "artifactRelativePath": f"files/{file_name}",
        "bootstrapPayloadSha256": payload_sha256,
        "bootstrapPayloadSizeBytes": payload_size,
        "bootstrapPayloadFileName": payload_name,
    }
    if not _json_semantically_equal(
        {key: receipt.get(key) for key in expected},
        expected,
    ):
        raise CutoverError(
            "scope-bound Windows startup-smoke receipt contradicts "
            "the authenticated artifact bytes"
        )
    return {
        "path": SCOPE_BOUND_STARTUP_SMOKE_PATH,
        "sha256": sha256_bytes(raw),
        "sizeBytes": len(raw),
        "status": "pass",
    }

def _validate_scope_bound_review_authority(
    *,
    canonical_raw: bytes,
    canonical: Mapping[str, Any],
    evidence_bytes: Mapping[str, bytes],
    generation_id: str,
    release_scope_decision_sha256: str,
    candidate_version: str,
) -> dict[str, Any]:
    evidence = {
        path: _strict_json_object_bytes(
            evidence_bytes[path],
            label=f"scope-bound review authority {path}",
        )
        for path in SCOPE_BOUND_REVIEW_EVIDENCE_PATHS
    }
    current = evidence["release-evidence/CURRENT.json"]
    decision = evidence["release-evidence/RELEASE_DECISION.json"]
    snapshot = evidence["release-evidence/SNAPSHOT.json"]
    decision_raw = evidence_bytes[
        "release-evidence/RELEASE_DECISION.json"
    ]
    snapshot_raw = evidence_bytes["release-evidence/SNAPSHOT.json"]
    manifest_sha256 = sha256_bytes(canonical_raw)
    snapshot_sha256 = sha256_bytes(snapshot_raw)
    decision_sha256 = sha256_bytes(decision_raw)

    if (
        set(current) != REVIEW_AUTHORITY_CURRENT_FIELDS
        or not _json_semantically_equal(
            current,
            {
                "releaseVersion": candidate_version,
                "snapshotSha256": snapshot_sha256,
                "decisionSha256": decision_sha256,
                "status": "review_required",
            },
        )
        or set(snapshot) != REVIEW_AUTHORITY_SNAPSHOT_FIELDS
        or set(decision) != REVIEW_AUTHORITY_DECISION_FIELDS
    ):
        raise CutoverError(
            "scope-bound review authority envelope or digest chain drifted"
        )

    artifacts = canonical.get("artifacts")
    if (
        not isinstance(artifacts, list)
        or len(artifacts) != 1
        or not isinstance(artifacts[0], dict)
    ):
        raise CutoverError(
            "scope-bound canonical manifest must contain one artifact"
        )
    artifact = artifacts[0]
    artifact_id = str(artifact.get("artifactId") or "")
    file_name = str(artifact.get("fileName") or "")
    expected_download_url = (
        f"/downloads/g/{generation_id}/files/{file_name}"
    )
    expected_install_route = f"/downloads/install/{artifact_id}"
    release_version = str(
        canonical.get("releaseVersion")
        or canonical.get("version")
        or ""
    )
    channel = str(
        canonical.get("channelId")
        or canonical.get("channel")
        or ""
    )
    manifest_generated_at = str(
        canonical.get("publishedAt")
        or canonical.get("generatedAt")
        or ""
    )
    if (
        not generation_id
        or canonical.get("generationId") != generation_id
        or release_version != candidate_version
        or channel != "preview"
        or canonical.get("status") != "published"
        or canonical.get("rolloutState")
        != "public_release_review_required"
        or canonical.get("supportabilityState") != "review_required"
        or artifact_id != "avalonia-win-x64-installer"
        or artifact.get("head") != "avalonia"
        or artifact.get("platform") != "windows"
        or artifact.get("rid") != "win-x64"
        or artifact.get("arch") != "x64"
        or artifact.get("kind") != "installer"
        or artifact.get("compatibilityState") != "compatible"
        or artifact.get("installAccessClass") != "open_public"
        or artifact.get("downloadUrl") != expected_download_url
        or not file_name
        or Path(file_name).name != file_name
        or SHA256.fullmatch(str(artifact.get("sha256") or "")) is None
        or type(artifact.get("sizeBytes")) is not int
        or artifact["sizeBytes"] <= 0
        or type(artifact.get("payloadSizeBytes")) is not int
        or artifact["payloadSizeBytes"] <= 0
    ):
        raise CutoverError(
            "scope-bound manifest is not the exact review-required "
            "Windows public-byte handoff"
        )

    snapshot_artifacts = snapshot.get("artifacts")
    if (
        snapshot.get("authorityContract")
        != "chummer.release-authority-snapshot/v2"
        or snapshot.get("releaseVersion") != release_version
        or snapshot.get("channel") != "preview"
        or snapshot.get("status") != "published"
        or snapshot.get("rolloutState")
        != "public_release_review_required"
        or snapshot.get("supportabilityState") != "review_required"
        or snapshot.get("availablePlatforms") != ["windows"]
        or snapshot.get("primaryHeadByPlatform")
        != {"windows": "avalonia"}
        or type(snapshot.get("artifactCount")) is not int
        or snapshot["artifactCount"] != 1
        or snapshot.get("downloadAccessPosture") != "open_public"
        or snapshot.get("knownIssueSummary")
        != canonical.get("knownIssueSummary")
        or snapshot.get("manifestSha256") != manifest_sha256
        or snapshot.get("registryRepository")
        != "ArchonMegalon/chummer6-hub-registry"
        or COMMIT.fullmatch(
            str(snapshot.get("registryCommit") or "")
        )
        is None
        or snapshot.get("releaseDecisionStatus") != "review_required"
        or snapshot.get("releaseDecisionSha256") != decision_sha256
        or not isinstance(snapshot.get("supportOwner"), str)
        or not snapshot["supportOwner"]
        or not isinstance(snapshot.get("nextActions"), list)
        or not snapshot["nextActions"]
        or any(
            not isinstance(item, str) or not item.strip()
            for item in snapshot["nextActions"]
        )
        or snapshot.get("manifestPath") != "RELEASE_CHANNEL.json"
        or snapshot.get("releaseDecisionPath")
        != "RELEASE_DECISION.json"
        or not isinstance(snapshot_artifacts, list)
        or len(snapshot_artifacts) != 1
        or not isinstance(snapshot_artifacts[0], dict)
        or set(snapshot_artifacts[0])
        != REVIEW_AUTHORITY_ARTIFACT_FIELDS
    ):
        raise CutoverError(
            "scope-bound review authority snapshot contradicts "
            "the authenticated manifest"
        )
    snapshot_artifact = snapshot_artifacts[0]
    expected_snapshot_artifact = {
        "artifactId": artifact_id,
        "head": "avalonia",
        "platform": "windows",
        "rid": "win-x64",
        "arch": "x64",
        "kind": "installer",
        "downloadUrl": expected_download_url,
        "sha256": artifact["sha256"],
        "sizeBytes": artifact["sizeBytes"],
        "compatibilityState": artifact.get("compatibilityState"),
        "promotionState": "promoted",
        "publicationScope": "signed-in-and-public",
        "revokeState": "not_revoked",
        "publicInstallRoute": expected_install_route,
        "installAccessClass": "open_public",
    }
    if not _json_semantically_equal(
        snapshot_artifact,
        expected_snapshot_artifact,
    ):
        raise CutoverError(
            "scope-bound review authority artifact binding drifted"
        )

    handoff = decision.get("artifactHandoff")
    blocking = decision.get("blockingFindings")
    if (
        decision.get("contractName")
        != "chummer.preview-release-decision/v2"
        or decision.get("status") != "review_required"
        or decision.get("releaseDecisionStatus") != "review_required"
        or decision.get("verdict")
        != "PREVIEW_RELEASE_REVIEW_REQUIRED"
        or decision.get("releaseVersion") != release_version
        or decision.get("releaseScopeDecisionSha256")
        != release_scope_decision_sha256
        or decision.get("channel") != "preview"
        or decision.get("platforms") != ["windows"]
        or decision.get("primaryHeadByPlatform")
        != {"windows": "avalonia"}
        or decision.get("fallbackHeadsByPlatform")
        != {"windows": []}
        or decision.get("artifactAccessClass") != "open_public"
        or decision.get("supportOwner") != snapshot["supportOwner"]
        or decision.get("nextActions") != snapshot["nextActions"]
        or decision.get("registryCommit")
        != snapshot["registryCommit"]
        or decision.get("manifestSha256") != manifest_sha256
        or decision.get("authoritySnapshotSha256") != ""
        or decision.get("candidateDecisionStatus") != ""
        or decision.get("candidateDecisionSha256") != ""
        or decision.get("manifestGeneratedAt") != manifest_generated_at
        or decision.get("scorecardSha256") != ""
        or decision.get("convergenceSha256") != ""
        or not isinstance(decision.get("generatedAt"), str)
        or not decision["generatedAt"]
        or not isinstance(blocking, list)
        or not blocking
        or len(blocking) > 256
        or any(
            not isinstance(item, dict)
            or set(item) != {"id", "severity", "summary"}
            or item.get("severity") != "release_truth"
            or item.get("id") != f"preview_{index}"
            or not isinstance(item.get("summary"), str)
            or not item["summary"]
            or item["summary"] != item["summary"].strip()
            or len(item["summary"].encode("utf-16-le", errors="surrogatepass")) > 1024
            for index, item in enumerate(blocking, start=1)
        )
        or not isinstance(handoff, dict)
        or set(handoff) != REVIEW_AUTHORITY_HANDOFF_FIELDS
    ):
        raise CutoverError(
            "scope-bound review decision posture or closure drifted"
        )
    expected_handoff = {
        "contractName": "chummer.public-preview-byte-handoff/v1",
        "status": "approved_public_preview_bytes",
        "sourcePublicationState": "preview",
        "releaseScopeDecisionSha256": (
            release_scope_decision_sha256
        ),
        "releaseVersion": release_version,
        "channel": "preview",
        "artifactId": artifact_id,
        "head": "avalonia",
        "platform": "windows",
        "rid": "win-x64",
        "arch": "x64",
        "sha256": artifact["sha256"],
        "sizeBytes": artifact["sizeBytes"],
        "artifactAccessClass": "open_public",
        "signingRequirement": "preview_unsigned_allowed",
        "downloadUrl": expected_download_url,
        "publicInstallRoute": expected_install_route,
    }
    if not _json_semantically_equal(handoff, expected_handoff):
        raise CutoverError(
            "scope-bound review decision artifact handoff drifted"
        )

    release_truth = {
        "contractName": "chummer.release-truth-projection/v1",
        "releaseVersion": release_version,
        "channel": "preview",
        "releaseStatus": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "avalonia"},
        "artifactCount": 1,
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": snapshot["knownIssueSummary"],
        "manifestSha256": manifest_sha256,
        "registryCommit": snapshot["registryCommit"],
        "releaseDecisionStatus": "review_required",
        "releaseDecisionSha256": decision_sha256,
        "releaseScopeDecisionSha256": (
            release_scope_decision_sha256
        ),
        "artifactHandoff": expected_handoff,
    }
    return {
        "contractName": "chummer.review-required-public-byte-authority/v1",
        "status": "pass",
        "generationId": generation_id,
        "manifestSha256": manifest_sha256,
        "releaseScopeDecisionSha256": (
            release_scope_decision_sha256
        ),
        "authoritySnapshotSha256": snapshot_sha256,
        "releaseDecisionSha256": decision_sha256,
        "files": [
            {
                "path": path,
                "sha256": sha256_bytes(evidence_bytes[path]),
                "sizeBytes": len(evidence_bytes[path]),
            }
            for path in SCOPE_BOUND_REVIEW_EVIDENCE_PATHS
        ],
        "releaseTruth": release_truth,
    }
