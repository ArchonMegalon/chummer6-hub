#!/usr/bin/env python3
"""Seal one upload candidate behind fresh finalized native-Windows proof.

This command has no network or publication behavior.  It authenticates the
candidate tree and the exact finalized UI evidence already in operator custody,
then emits a bounded authority document whose embedded bytes can be placed in a
digest-bound public-projection snapshot.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Iterable


AUTHORITY_CONTRACT = "chummer.release-upload.candidate-import-authority/v2"
UNSIGNED_AUTHORITY_CONTRACT = "chummer.release-upload.candidate-import-authority/v3"
INVENTORY_CONTRACT = "chummer.release-upload.candidate-inventory/v1"
CAPTURE_CONTRACT = "chummer6-ui.preview-nightly-native-windows-capture"
CAPTURE_INVENTORY_CONTRACT = "chummer6-ui.preview-nightly-native-windows-capture-inventory"
FINALIZATION_CONTRACT = "chummer6-ui.preview-nightly-native-windows-finalization"
FINALIZED_INVENTORY_CONTRACT = "chummer6-ui.preview-nightly-native-windows-finalized-inventory"
VISUAL_PROOF_CONTRACT = "chummer6-ui.windows_installer_visual_proof"
NATIVE_HOST_CONTRACT = "chummer6-ui.native_windows_host_evidence"
CANDIDATE_CONTENT_INVENTORY_CONTRACT = "chummer6-ui.preview-nightly-candidate-content-inventory"
CANDIDATE_EXPORT_CONTRACT = "chummer6-ui.preview-nightly-candidate-export"
CAPTURE_FILE = "WINDOWS_NATIVE_CAPTURE.generated.json"
CAPTURE_INVENTORY_FILE = "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
FINALIZATION_FILE = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
FINALIZED_INVENTORY_FILE = "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"
CANDIDATE_PROVENANCE_INVENTORY = (
    "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"
)
CANDIDATE_PROVENANCE_EXPORT = (
    "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
)
CANDIDATE_UPLOAD_CONTENT_INVENTORY = (
    "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"
)
CANDIDATE_UPLOAD_EXPORT = "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
PROMOTED_HEADS = ("avalonia",)
RETAINED_DESKTOP_HEADS = frozenset((*PROMOTED_HEADS, "blazor-desktop"))
CAPTURE_WORKFLOW = ".github/workflows/windows-native-evidence-capture.yml"
FINALIZE_WORKFLOW = ".github/workflows/windows-native-evidence-finalize.yml"
PRODUCER_WORKFLOW = ".github/workflows/preview-nightly-candidate-export.yml"
UI_REPOSITORY = "ArchonMegalon/chummer6-ui"
PRODUCER_REF = "refs/heads/main"
RID = "win-x64"
EXACT_SCOPE_TUPLE = "avalonia:windows:win-x64"
PUBLICATION_SCOPE_CONTRACT = "chummer6-ui.preview-nightly-windows-publication-scope"
PUBLICATION_SCOPE_FILE = "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json"
UNSIGNED_PUBLICATION_SCOPE_CONTRACT = (
    "chummer6-ui.preview-nightly-unsigned-publication-scope"
)
UNSIGNED_PUBLICATION_SCOPE_FILE = "PREVIEW_NIGHTLY_UNSIGNED_SCOPE.proposed.json"
REGISTRY_CANDIDATE_CONTRACT = "chummer.registry.preview-publication-delta-candidate"
REGISTRY_AUTHORITY_CONTRACT = "chummer.registry.preview-publication-delta-authority"
REGISTRY_FINALIZE_CONTRACT = "chummer.registry.preview-publication-delta-finalize"
REGISTRY_CANDIDATE_FILE = "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json"
REGISTRY_AUTHORITY_FILE = "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json"
REGISTRY_FINALIZE_CUSTODY_FILE = "PREVIEW_PUBLICATION_DELTA_FINALIZE.json"
UNSIGNED_COMPOSITION_FILE = "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json"
UNSIGNED_COMPOSITION_CONTRACT = (
    "chummer6-ui.preview-nightly-unsigned-composition-request"
)
SIGNING_CONTRACT = "chummer6-ui.desktop_artifact_signing"
AUTHENTICODE_CONTRACT = "chummer6-ui.windows-authenticode-verification"
AUTHENTICODE_RECEIPT_PATH = (
    "proof/windows-native/authenticode/"
    "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"
)
NATIVE_WRAPPER_CONTRACT = "chummer6-ui.preview-nightly-native-windows-evidence"
NATIVE_WRAPPER_FILE = "NATIVE_WINDOWS_EVIDENCE.generated.json"
NATIVE_FINALIZATION_V2_FILE = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
NATIVE_VISUAL_FILE = f"WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-{RID}.generated.json"
NATIVE_AUTHENTICODE_SOURCE_PATH = (
    "authenticode/AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"
)
NATIVE_SCOPE_APPROVAL_FILE = (
    "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json"
)
NATIVE_CONTRACT_REFERENCE_KEYS = {
    "contractName",
    "contractVersion",
    "path",
    "sha256",
    "sizeBytes",
}
NATIVE_COMPOSITE_KEYS = {
    "authenticodeVerification",
    "nativeFinalization",
    "visualProof",
    "wrapper",
}
NATIVE_WRAPPER_KEYS = {
    "archivePath",
    "archiveSha256",
    "authenticodeVerification",
    "candidateProvenance",
    "captureInventorySha256",
    "captureSource",
    "contractName",
    "contractVersion",
    "fileCount",
    "finalizationSha256",
    "finalizationSource",
    "finalizedInventorySha256",
    "githubActionsProvenance",
    "nativeFinalization",
    "progressLogSha256",
    "release",
    "scopeApproval",
    "startupReceiptSha256",
    "status",
    "treeSha256",
    "visualProof",
    "visualProofSha256",
    "visualReviewers",
}
NATIVE_WORKFLOW_SOURCE_KEYS = {
    "actor",
    "artifactName",
    "ref",
    "repository",
    "runAttempt",
    "runId",
    "sha",
    "workflow",
}
NATIVE_AUTHENTICODE_BINDING_KEYS = {
    "path",
    "sha256",
    "signerCertificateSha256",
    "signerSpkiSha256",
    "sizeBytes",
    "timestampUtc",
}
NATIVE_FINALIZATION_V2_KEYS = {
    "authenticodeVerification",
    "captureInventorySha256",
    "captureSource",
    "contractName",
    "contractVersion",
    "finalizationSource",
    "generatedAt",
    "humanReviewConfirmed",
    "proofs",
    "reviewer",
    "reviewerWasCaptureActor",
    "scopeApproval",
    "status",
}
NATIVE_PORTABLE_VISUAL_KEYS = {
    "artifactDigest",
    "artifactFileName",
    "authenticodeVerification",
    "captureBinding",
    "channel",
    "channelId",
    "checks",
    "clippingReview",
    "contractName",
    "contractVersion",
    "contrastReview",
    "finalizationBinding",
    "generatedAt",
    "head",
    "headId",
    "platform",
    "readabilityReview",
    "releaseVersion",
    "review",
    "rid",
    "screenshots",
    "status",
    "version",
}
REGISTRY_CANDIDATE_KEYS = {
    "canonicalManifest",
    "channel",
    "compatibilityManifest",
    "compositionInput",
    "compositionInputDocument",
    "contractName",
    "contractVersion",
    "deltaPlatforms",
    "deployAuthority",
    "evidencePlatforms",
    "fullShelfInventory",
    "fullShelfInventorySha256",
    "incumbentDesktopTupleSetSha256",
    "incumbentCanonicalManifestBytesBase64",
    "incumbentSnapshotSha256",
    "nonPublishedEvidenceTupleSetSha256",
    "postPublicationTupleSetSha256",
    "publicationDeltaTupleSetSha256",
    "publicationEligible",
    "publicationStatus",
    "registryProjectionInputs",
    "releaseUploadAuthority",
    "routeAuthority",
    "releaseVersion",
    "retainedPlatforms",
    "retainedTupleSetSha256",
    "shelfPlatforms",
}
REGISTRY_AUTHORITY_KEYS = {
    "candidateImportAuthority",
    "candidateReceipt",
    "candidateReviewAuthority",
    "canonicalManifest",
    "channel",
    "compatibilityManifest",
    "compositionInputSha256",
    "contractName",
    "contractVersion",
    "deltaPlatforms",
    "deployAuthority",
    "dispositions",
    "evidence",
    "evidencePlatforms",
    "fullShelfInventorySha256",
    "incumbentSnapshotSha256",
    "nonPublishedEvidenceTupleSetSha256",
    "postPublicationTupleSetSha256",
    "publicationDeltaTupleSetSha256",
    "publicationEligible",
    "releaseUploadAuthority",
    "releaseVersion",
    "retainedPlatforms",
    "retainedTupleSetSha256",
    "routeAuthority",
    "scope",
    "shelfPlatforms",
    "sourceScope",
}
REGISTRY_FINALIZE_KEYS = {
    "authority",
    "candidateBytesMutated",
    "candidateImportAuthority",
    "candidateReceipt",
    "candidateReviewAuthority",
    "canonicalManifest",
    "channel",
    "compatibilityManifest",
    "contractName",
    "contractVersion",
    "deployAuthority",
    "fullShelfInventorySha256",
    "publicationEligible",
    "releaseUploadAuthority",
    "releaseVersion",
    "routeAuthority",
    "sourceScope",
    "verificationStatus",
}
REGISTRY_AUTHORITY_V2_KEYS = {
    "candidateImportAuthority",
    "candidateReceipt",
    "candidateReviewAuthority",
    "canonicalManifest",
    "channel",
    "codeDeploymentAuthority",
    "compatibilityManifest",
    "compositionRequest",
    "contractName",
    "contractVersion",
    "crossRunBitReproducible",
    "deltaPlatforms",
    "deployAuthority",
    "evidencePlatforms",
    "fullShelfInventorySha256",
    "incumbentInventorySha256",
    "incumbentSnapshotSha256",
    "mixedVersionGraph",
    "platformScope",
    "projectionInputs",
    "proposedDirectoryModesSha256",
    "provenance",
    "publicationAuthorized",
    "publicationEligible",
    "releaseUploadAuthority",
    "releaseVersion",
    "retainedInventorySha256",
    "retainedPlatforms",
    "routeAuthority",
    "shelfPlatforms",
    "signaturePolicy",
    "sourceScope",
    "sourceSha",
    "windowsDelta",
}
REGISTRY_FINALIZE_V2_KEYS = {
    "authority",
    "candidateBytesMutated",
    "candidateImportAuthority",
    "candidateReceipt",
    "candidateReviewAuthority",
    "canonicalManifest",
    "channel",
    "codeDeploymentAuthority",
    "compatibilityManifest",
    "compositionRequest",
    "contractName",
    "contractVersion",
    "deployAuthority",
    "fullShelfInventorySha256",
    "mixedVersionGraph",
    "platformScope",
    "provenance",
    "publicationAuthorized",
    "publicationEligible",
    "releaseUploadAuthority",
    "releaseVersion",
    "routeAuthority",
    "signaturePolicy",
    "sourceScope",
    "verificationStatus",
    "windowsDelta",
}
REGISTRY_CANDIDATE_V2_KEYS = {
    "canonicalManifest",
    "channel",
    "codeDeploymentAuthority",
    "compatibilityManifest",
    "compositionInput",
    "compositionInputDocument",
    "contractName",
    "contractVersion",
    "crossRunBitReproducible",
    "deltaPlatforms",
    "deployAuthority",
    "evidencePlatforms",
    "fullShelfInventory",
    "fullShelfInventorySha256",
    "incumbentDirectoryModesSha256",
    "incumbentInventorySha256",
    "incumbentSnapshotSha256",
    "platformScope",
    "projectionInputs",
    "proposedDirectoryModesSha256",
    "provenance",
    "publicationAuthorized",
    "publicationEligible",
    "publicationStatus",
    "releaseUploadAuthority",
    "releaseVersion",
    "retainedInventorySha256",
    "retainedPlatforms",
    "routeAuthority",
    "shelfPlatforms",
    "signaturePolicy",
    "sourceSha",
    "windowsDelta",
}
UNSIGNED_COMPOSITION_KEYS = {
    "contractName",
    "contractVersion",
    "crossRunBitReproducible",
    "deployAuthorized",
    "freshDelta",
    "incumbentSnapshot",
    "platformScope",
    "proposedCanonicalManifest",
    "proposedCompatibilityManifest",
    "proposedDirectoryModes",
    "proposedDirectoryModesSha256",
    "proposedShelfInventory",
    "proposedShelfInventorySha256",
    "provenance",
    "publicationAuthorized",
    "release",
    "retainedFromIncumbent",
    "signature",
    "sourceSha",
    "status",
    "uploadAuthorized",
}
SCOPE_TUPLE_KEYS = {
    "artifactRole",
    "consumerCommit",
    "fileName",
    "head",
    "manifestRowSha256",
    "path",
    "platform",
    "rid",
    "sha256",
    "sizeBytes",
    "sourceReceipt",
}
PUBLICATION_SCOPE_KEYS = {
    "approval",
    "approvalIndependent",
    "authenticodeRequired",
    "authenticodeVerificationSha256",
    "buildEvidenceTuples",
    "contractName",
    "contractVersion",
    "deployAuthorized",
    "fullShelfCompatibilityManifestSha256",
    "fullShelfInventory",
    "fullShelfInventorySha256",
    "fullShelfManifestSha256",
    "incumbentSnapshot",
    "incumbentSnapshotSha256",
    "macosSoak",
    "nativeEvidenceComposite",
    "nativeEvidenceSha256",
    "nonPublishedEvidenceTuples",
    "postPublicationShelfTuples",
    "publicationDeltaTuples",
    "publicationEligible",
    "registryPrepare",
    "registryFinalizeEligible",
    "release",
    "retainedTuples",
    "scopeDecision",
    "scopeDecisionSha256",
    "signingReceipt",
    "signingReceiptSha256",
    "status",
    "uploadAuthorized",
    "visualApprovalSha256",
}
UNSIGNED_PUBLICATION_SCOPE_KEYS = {
    "compatibilityManifest",
    "contractName",
    "contractVersion",
    "crossRunBitReproducible",
    "deployAuthorized",
    "freshDelta",
    "fullShelfInventory",
    "fullShelfInventorySha256",
    "incumbentInventorySha256",
    "platformScope",
    "provenance",
    "publicationAuthorized",
    "publicationManifest",
    "release",
    "retainedFromIncumbent",
    "signature",
    "sourceSha",
    "status",
    "uploadAuthorized",
}
UNSIGNED_PROVENANCE_PATHS = {
    "packagePlaneLock": "provenance/config/package-plane.lock.json",
    "packagePlaneReceipt": "provenance/UI_FRESH_PACKAGE_PLANE.generated.json",
    "retainedManifest": (
        "provenance/retained-windows-publish-closure/manifest.json"
    ),
    "nativeToolchainLock": (
        "provenance/config/windows-native-bootstrap-toolchain.lock.json"
    ),
}
UNSIGNED_PACKAGE_PLANE_LOCK_BINDING_PATH = "config/package-plane.lock.json"
UNSIGNED_RETAINED_POINTER_KEYS = {
    "atomicallyRetained",
    "authority",
    "bundleInventoryCount",
    "bundleInventorySha256",
    "consumerCommit",
    "contractName",
    "contractVersion",
    "manifest",
    "manifestIsAuthoritative",
    "release",
    "status",
    "targetPath",
}
UNSIGNED_SIGNATURE_POLICY = {
    "required": False,
    "status": "unsigned",
    "policy": "preview_policy",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REVIEWER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,38})$")
GITHUB_LOGIN_RE = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?|github-actions\[bot\])$"
)
POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$")
GITHUB_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
EXPORT_RUNNER_LABEL_RE = re.compile(r"^chummer-preview-nightly-export-[a-z0-9]{12,64}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$")
HEAD_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_EVIDENCE_FILES = 512
MAX_AUTHORITY_LIFETIME_SECONDS = 6 * 60 * 60
DEFAULT_MAX_PROOF_AGE_SECONDS = 24 * 60 * 60


class CandidateAuthorityBlocked(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise CandidateAuthorityBlocked(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _plain_file(path: Path, *, label: str, maximum_bytes: int | None = None) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CandidateAuthorityBlocked(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size < 1
        or (maximum_bytes is not None and metadata.st_size > maximum_bytes)
    ):
        _fail(f"{label} must be a bounded single-link regular file")
    return path


def _strict_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    path = _plain_file(path, label=label, maximum_bytes=MAX_JSON_BYTES)
    payload = path.read_bytes()

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateAuthorityBlocked(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must contain a JSON object")
    return value, payload


def _strict_json_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateAuthorityBlocked(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must contain a JSON object")
    return value


class _JsonNumber:
    __slots__ = ("raw",)

    def __init__(self, raw: str) -> None:
        self.raw = raw


def _json_semantic_object(payload: bytes, *, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> object:
        raise ValueError(f"non-JSON numeric constant {value!r}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            parse_int=_JsonNumber,
            parse_float=_JsonNumber,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateAuthorityBlocked(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must contain a JSON object")
    return value


def _json_semantic_equal(left: object, right: object) -> bool:
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and set(left) == set(right)
            and all(
                _json_semantic_equal(left[key], right[key])
                for key in left
            )
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(
                _json_semantic_equal(left_item, right_item)
                for left_item, right_item in zip(left, right)
            )
        )
    if isinstance(left, _JsonNumber) or isinstance(right, _JsonNumber):
        return (
            isinstance(left, _JsonNumber)
            and isinstance(right, _JsonNumber)
            and left.raw == right.raw
        )
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left is right
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    return False


def _sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(f"{label} must be an exact lowercase SHA-256")
    return value


def _positive_int(value: object, *, label: str, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{label} is invalid")
    return value


def _timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateAuthorityBlocked(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fail(f"{label} must be expressed in UTC")
    return parsed.astimezone(timezone.utc)


def _fresh_timestamp(
    value: object,
    *,
    label: str,
    now: datetime,
    max_age: timedelta,
) -> datetime:
    parsed = _timestamp(value, label=label)
    if parsed > now + timedelta(minutes=5) or now - parsed > max_age:
        _fail(f"{label} is stale or future-dated")
    return parsed


def _identity_material(candidate: dict[str, Any]) -> bytes:
    identity = {
        key: candidate[key]
        for key in (
            "version",
            "canonicalManifestSha256",
            "inventorySha256",
            "fileCount",
            "totalBytes",
        )
    }
    return json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "version",
        "canonicalManifestSha256",
        "inventorySha256",
        "fileCount",
        "totalBytes",
        "bundleIdentitySha256",
    }
    if set(candidate) != expected or not isinstance(candidate.get("version"), str):
        _fail("candidate summary property set drifted")
    if VERSION_RE.fullmatch(candidate["version"]) is None:
        _fail("candidate version is invalid")
    for name in (
        "canonicalManifestSha256",
        "inventorySha256",
        "bundleIdentitySha256",
    ):
        _sha256(candidate.get(name), label=f"candidate {name}")
    _positive_int(candidate.get("fileCount"), label="candidate fileCount")
    _positive_int(candidate.get("totalBytes"), label="candidate totalBytes", allow_zero=True)
    expected_identity = hashlib.sha256(_identity_material(candidate)).hexdigest()
    if candidate["bundleIdentitySha256"] != expected_identity:
        _fail("candidate bundle identity does not bind its exact summary")
    return candidate


def _inventory_digest(rows: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        encoded = row["path"].encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(row["sizeBytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(row["sha256"]))
    return digest.hexdigest()


def _validate_relative_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        _fail(f"{label} is not a canonical relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} or ":" in part for part in parts):
        _fail(f"{label} is not a canonical relative path")
    return value


def _validate_absolute_posix_path(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.endswith("/")
        or "\\" in value
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in value
        )
    ):
        _fail(f"{label} is not a canonical absolute path")
    if any(part in {"", ".", ".."} for part in value.split("/")[1:]):
        _fail(f"{label} is not a canonical absolute path")
    return value


def _inventory_rows(
    value: object,
    *,
    label: str,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, list)
        or not allow_empty
        and not value
        or len(value) > 100_000
    ):
        qualifier = "bounded list" if allow_empty else "bounded non-empty list"
        _fail(f"{label} must be a {qualifier}")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {"path", "sha256", "sizeBytes"}:
            _fail(f"{label} row {index} drifted")
        rows.append(
            {
                "path": _validate_relative_path(raw.get("path"), label=f"{label} path"),
                "sha256": _sha256(raw.get("sha256"), label=f"{label} sha256"),
                "sizeBytes": _positive_int(
                    raw.get("sizeBytes"), label=f"{label} sizeBytes", allow_zero=True
                ),
            }
        )
    if rows != sorted(rows, key=lambda row: row["path"]) or len(
        {row["path"] for row in rows}
    ) != len(rows):
        _fail(f"{label} is not uniquely sorted")
    return rows


def _validate_bundle_inventory(
    bundle_root: Path,
    inventory: dict[str, Any],
    candidate: dict[str, Any],
    *,
    allow_root_ancillary_files: bool = False,
) -> tuple[
    list[dict[str, Any]],
    dict[str, int],
    list[dict[str, Any]],
    dict[str, bytes],
]:
    if (
        inventory.get("contractName") != INVENTORY_CONTRACT
        or type(inventory.get("contractVersion")) is not int
        or inventory.get("contractVersion") != 1
        or set(inventory) != {"contractName", "contractVersion", "files"}
    ):
        _fail("candidate upload inventory contract drifted")
    rows = _inventory_rows(inventory.get("files"), label="candidate upload inventory")
    root_paths = {row["path"] for row in rows if "/" not in row["path"]}
    required_root_paths = {"RELEASE_CHANNEL.generated.json", "releases.json"}
    if (
        not required_root_paths.issubset(root_paths)
        or not allow_root_ancillary_files
        and root_paths != required_root_paths
    ):
        _fail("candidate upload root must contain only the two finalized shelf manifests")
    actual_rows, file_modes, directory_modes, captured = _scan_bundle_tree(
        bundle_root
    )
    if rows != actual_rows:
        _fail("candidate upload inventory does not match exact bundle bytes")
    if (
        len(rows) != candidate["fileCount"]
        or sum(row["sizeBytes"] for row in rows) != candidate["totalBytes"]
        or _inventory_digest(rows) != candidate["inventorySha256"]
    ):
        _fail("candidate upload inventory summary drifted")
    return rows, file_modes, directory_modes, captured


def _scan_bundle_tree(
    bundle_root: Path,
) -> tuple[
    list[dict[str, Any]],
    dict[str, int],
    list[dict[str, Any]],
    dict[str, bytes],
]:
    """Read one exact physical upload tree without following any link."""

    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    close_flag = getattr(os, "O_CLOEXEC", 0)
    if directory_flag == 0 or nofollow_flag == 0:
        _fail("exact candidate tree custody requires openat no-follow support")
    root_flags = os.O_RDONLY | directory_flag | nofollow_flag | close_flag

    def stable_identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    try:
        root_lstat = bundle_root.lstat()
        if not stat.S_ISDIR(root_lstat.st_mode) or stat.S_ISLNK(root_lstat.st_mode):
            _fail("candidate bundle root must be one physical directory")
        root_descriptor = os.open(bundle_root, root_flags)
    except OSError as exc:
        raise CandidateAuthorityBlocked(
            "candidate bundle root cannot be opened without following links"
        ) from exc

    files: list[dict[str, Any]] = []
    file_modes: dict[str, int] = {}
    directories: list[dict[str, Any]] = []
    captured: dict[str, bytes] = {}
    capture_paths = {"RELEASE_CHANNEL.generated.json", "releases.json"}

    def scan_directory(descriptor: int, prefix: str) -> None:
        before = os.fstat(descriptor)
        if not stat.S_ISDIR(before.st_mode):
            _fail("candidate bundle directory identity drifted")
        try:
            names = sorted(os.listdir(descriptor))
        except OSError as exc:
            raise CandidateAuthorityBlocked(
                "candidate bundle directory cannot be enumerated"
            ) from exc
        for name in names:
            if (
                not isinstance(name, str)
                or name in {"", ".", ".."}
                or "/" in name
                or "\\" in name
                or ":" in name
            ):
                _fail("candidate bundle contains a non-canonical entry name")
            try:
                name.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise CandidateAuthorityBlocked(
                    "candidate bundle contains a non-UTF-8 entry name"
                ) from exc
            relative = f"{prefix}/{name}" if prefix else name
            if len(files) + len(directories) >= 100_000:
                _fail("candidate bundle tree is unbounded")
            try:
                entry_before = os.stat(
                    name,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise CandidateAuthorityBlocked(
                    "candidate bundle entry changed during enumeration"
                ) from exc
            if stat.S_ISLNK(entry_before.st_mode):
                _fail("candidate bundle contains a symbolic link")
            if stat.S_ISDIR(entry_before.st_mode):
                try:
                    child = os.open(name, root_flags, dir_fd=descriptor)
                except OSError as exc:
                    raise CandidateAuthorityBlocked(
                        "candidate bundle directory changed during open"
                    ) from exc
                try:
                    opened = os.fstat(child)
                    if stable_identity(opened) != stable_identity(entry_before):
                        _fail("candidate bundle directory changed during open")
                    directories.append(
                        {
                            "mode": stat.S_IMODE(opened.st_mode),
                            "path": relative,
                        }
                    )
                    scan_directory(child, relative)
                    child_after = os.fstat(child)
                finally:
                    os.close(child)
                try:
                    path_after = os.stat(
                        name,
                        dir_fd=descriptor,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise CandidateAuthorityBlocked(
                        "candidate bundle directory changed during validation"
                    ) from exc
                if (
                    stable_identity(child_after) != stable_identity(opened)
                    or stable_identity(path_after) != stable_identity(opened)
                ):
                    _fail("candidate bundle directory changed during validation")
                continue
            if not stat.S_ISREG(entry_before.st_mode) or entry_before.st_nlink != 1:
                _fail("candidate bundle contains a special or hard-linked file")
            file_flags = os.O_RDONLY | nofollow_flag | close_flag
            try:
                file_descriptor = os.open(name, file_flags, dir_fd=descriptor)
            except OSError as exc:
                raise CandidateAuthorityBlocked(
                    "candidate bundle file changed during open"
                ) from exc
            digest = hashlib.sha256()
            captured_chunks: list[bytes] | None = (
                [] if relative in capture_paths else None
            )
            try:
                opened = os.fstat(file_descriptor)
                if (
                    stable_identity(opened) != stable_identity(entry_before)
                    or not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                ):
                    _fail("candidate bundle file changed during open")
                while True:
                    chunk = os.read(file_descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    if captured_chunks is not None:
                        if sum(len(item) for item in captured_chunks) + len(
                            chunk
                        ) > MAX_JSON_BYTES:
                            _fail("candidate manifest exceeds its size bound")
                        captured_chunks.append(chunk)
                file_after = os.fstat(file_descriptor)
            finally:
                os.close(file_descriptor)
            try:
                path_after = os.stat(
                    name,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise CandidateAuthorityBlocked(
                    "candidate bundle file changed during validation"
                ) from exc
            if (
                stable_identity(file_after) != stable_identity(opened)
                or stable_identity(path_after) != stable_identity(opened)
            ):
                _fail("candidate bundle file changed during validation")
            files.append(
                {
                    "path": relative,
                    "sha256": digest.hexdigest(),
                    "sizeBytes": opened.st_size,
                }
            )
            file_modes[relative] = stat.S_IMODE(opened.st_mode)
            if captured_chunks is not None:
                captured[relative] = b"".join(captured_chunks)
        after = os.fstat(descriptor)
        if stable_identity(after) != stable_identity(before):
            _fail("candidate bundle directory changed during enumeration")

    try:
        root_opened = os.fstat(root_descriptor)
        if stable_identity(root_opened) != stable_identity(root_lstat):
            _fail("candidate bundle root changed during open")
        scan_directory(root_descriptor, "")
        root_after = os.fstat(root_descriptor)
    finally:
        os.close(root_descriptor)
    try:
        root_path_after = bundle_root.lstat()
    except OSError as exc:
        raise CandidateAuthorityBlocked(
            "candidate bundle root changed during validation"
        ) from exc
    if (
        stable_identity(root_after) != stable_identity(root_opened)
        or stable_identity(root_path_after) != stable_identity(root_opened)
    ):
        _fail("candidate bundle root changed during validation")
    files.sort(key=lambda row: row["path"])
    directories.sort(key=lambda row: row["path"])
    return files, file_modes, directories, captured


def _matching_alias(value: dict[str, Any], first: str, second: str, *, label: str) -> str:
    if first in value and not isinstance(value[first], str):
        _fail(f"{label} alias type drifted")
    if second in value and not isinstance(value[second], str):
        _fail(f"{label} alias type drifted")
    first_value = value.get(first)
    second_value = value.get(second)
    if first_value is not None and second_value is not None and first_value != second_value:
        _fail(f"{label} aliases disagree")
    selected = first_value if first_value is not None else second_value
    if not isinstance(selected, str) or not selected:
        _fail(f"{label} is missing")
    return selected


def _canonical_windows_scope(
    manifest: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    *,
    allow_ancillary_files: bool = False,
    expected_channel: str | None = None,
) -> dict[str, Any]:
    version = _matching_alias(
        manifest, "version", "releaseVersion", label="candidate release version"
    )
    channel = _matching_alias(
        manifest, "channelId", "channel", label="candidate release channel"
    )
    if expected_channel is not None and channel != expected_channel:
        _fail("candidate release channel differs from its authority identity")
    coverage = manifest.get("desktopTupleCoverage")
    heads_value = coverage.get("requiredDesktopHeads") if isinstance(coverage, dict) else None
    if heads_value != list(PROMOTED_HEADS) or any(
        not isinstance(head, str) or HEAD_RE.fullmatch(head) is None
        for head in heads_value or []
    ):
        _fail("candidate requiredDesktopHeads differs from the promoted Avalonia head")
    heads = tuple(heads_value)
    artifacts_value = manifest.get("artifacts")
    if not isinstance(artifacts_value, list) or not artifacts_value:
        _fail("candidate release manifest has no artifacts")
    windows_artifacts: list[dict[str, Any]] = []
    candidate_by_path = {row["path"]: row for row in candidate_rows}
    expected_file_paths: set[str] = set()
    non_windows_kinds = (
        {"installer", "archive"} if allow_ancillary_files else {"installer"}
    )
    for artifact in artifacts_value:
        if not isinstance(artifact, dict):
            _fail("candidate release manifest contains a non-object artifact")
        head = artifact.get("head")
        platform = artifact.get("platform")
        rid = artifact.get("rid")
        kind = artifact.get("kind")
        if not isinstance(head, str) or HEAD_RE.fullmatch(head) is None:
            _fail("candidate release manifest contains an invalid desktop artifact head")
        if allow_ancillary_files and head not in RETAINED_DESKTOP_HEADS:
            _fail("candidate release manifest contains an unknown retained desktop head")
        if head not in heads and (platform == "windows" or not allow_ancillary_files):
            _fail(
                "candidate release manifest contains a desktop artifact outside "
                "requiredDesktopHeads"
            )
        if (
            platform == "windows"
            and (rid != RID or kind != "installer")
            or platform == "linux"
            and (rid != "linux-x64" or kind not in non_windows_kinds)
            or platform == "macos"
            and (
                rid not in {"osx-arm64", "osx-x64"}
                or kind not in non_windows_kinds
            )
            or platform not in {"linux", "macos", "windows"}
        ):
            _fail(
                "candidate release manifest contains an artifact outside the exact "
                "finalized desktop shelf scope"
            )
        file_name = artifact.get("fileName")
        digest = artifact.get("sha256")
        size = artifact.get("sizeBytes")
        if (
            not isinstance(file_name, str)
            or not file_name
            or "/" in file_name
            or "\\" in file_name
            or SHA256_RE.fullmatch(str(digest or "")) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 1
        ):
            _fail("candidate desktop artifact metadata is invalid")
        path = f"files/{file_name}"
        if path in expected_file_paths or candidate_by_path.get(path) != {
            "path": path,
            "sha256": digest,
            "sizeBytes": size,
        }:
            _fail("candidate desktop artifact differs from the upload inventory")
        expected_file_paths.add(path)
        if platform == "windows":
            windows_artifacts.append(artifact)
    scope_by_head: dict[str, dict[str, Any]] = {}
    for head in heads:
        matching = [artifact for artifact in windows_artifacts if artifact.get("head") == head]
        if len(matching) != 1:
            _fail(f"candidate manifest must name one Windows installer row for {head}")
        installer_row = matching[0]
        if (
            installer_row.get("installerMode") != "bootstrap"
            or installer_row.get("payloadAcquisitionMode") != "download"
        ):
            _fail(f"candidate {head} installer delivery mode is invalid")
        scope_by_head[head] = {}
        for role, file_key, digest_key, size_key in (
            ("installer", "fileName", "sha256", "sizeBytes"),
            ("payload", "payloadFileName", "payloadSha256", "payloadSizeBytes"),
        ):
            file_name = installer_row.get(file_key)
            digest = installer_row.get(digest_key)
            size = installer_row.get(size_key)
            if (
                not isinstance(file_name, str)
                or not file_name
                or "/" in file_name
                or "\\" in file_name
                or SHA256_RE.fullmatch(str(digest or "")) is None
                or isinstance(size, bool)
                or not isinstance(size, int)
                or size < 1
                or role == "installer"
                and not file_name.lower().endswith(".exe")
            ):
                _fail(f"candidate {head} {role} artifact metadata is invalid")
            path = f"files/{file_name}"
            candidate_row = candidate_by_path.get(path)
            if candidate_row != {"path": path, "sha256": digest, "sizeBytes": size}:
                _fail(f"candidate {head} {role} manifest bytes differ from upload inventory")
            scope_by_head[head][role] = {
                "path": path,
                "fileName": file_name,
                "sha256": digest,
                "sizeBytes": size,
            }
    expected_file_paths.update(
        artifact["path"]
        for head in heads
        for artifact in scope_by_head[head].values()
    )
    expected_candidate_paths = {
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        *expected_file_paths,
    }
    actual_candidate_paths = {row["path"] for row in candidate_rows}
    if (
        (not allow_ancillary_files and actual_candidate_paths != expected_candidate_paths)
        or (
            allow_ancillary_files
            and not expected_candidate_paths.issubset(actual_candidate_paths)
        )
    ):
        _fail(
            "candidate upload inventory differs from the exact finalized desktop shelf"
        )
    return {
        "version": version,
        "channel": channel,
        "heads": heads,
        "artifacts": scope_by_head,
        "manifestArtifactPaths": sorted(expected_file_paths),
    }


def _exact_tree_rows(root: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            _fail("finalized native-Windows evidence contains a symbolic link")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            _fail("finalized native-Windows evidence contains a non-regular file")
        relative = path.relative_to(root).as_posix()
        if relative in exclude:
            continue
        rows.append(
            {"path": relative, "sha256": _sha256_file(path), "sizeBytes": metadata.st_size}
        )
        if len(rows) > MAX_EVIDENCE_FILES:
            _fail("finalized native-Windows evidence file count is unbounded")
    return rows


def _source(value: object, *, label: str, workflow: str) -> dict[str, Any]:
    required = {
        "repository",
        "workflow",
        "runId",
        "runAttempt",
        "ref",
        "sha",
        "actor",
        "artifactName",
    }
    if not isinstance(value, dict) or set(value) != required:
        _fail(f"{label} property set drifted")
    if value.get("repository") != UI_REPOSITORY or value.get("workflow") != workflow:
        _fail(f"{label} repository/workflow drifted")
    if value.get("ref") != PRODUCER_REF or not isinstance(value.get("sha"), str) or COMMIT_RE.fullmatch(value["sha"]) is None:
        _fail(f"{label} source revision drifted")
    run_id = _github_positive_integer(value.get("runId"), label=f"{label} runId")
    run_attempt = _github_positive_integer(
        value.get("runAttempt"), label=f"{label} runAttempt"
    )
    actor = value.get("actor")
    artifact_name = value.get("artifactName")
    actor_pattern = GITHUB_LOGIN_RE if workflow == CAPTURE_WORKFLOW else REVIEWER_RE
    if not isinstance(actor, str) or actor_pattern.fullmatch(actor) is None:
        _fail(f"{label} actor is invalid")
    expected_artifact_name = (
        f"windows-native-evidence-{run_id}-{run_attempt}"
        if workflow == CAPTURE_WORKFLOW
        else f"windows-native-evidence-finalized-{run_id}-{run_attempt}"
    )
    if artifact_name != expected_artifact_name:
        _fail(f"{label} artifact identity drifted")
    return value


def _github_positive_integer(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or POSITIVE_INTEGER_RE.fullmatch(value) is None
        or int(value) > 9_007_199_254_740_991
    ):
        _fail(f"{label} must be an exact positive GitHub integer string")
    return value


def _github_timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or GITHUB_TIMESTAMP_RE.fullmatch(value) is None:
        _fail(f"{label} must be an exact UTC GitHub timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise CandidateAuthorityBlocked(f"{label} is invalid") from exc


def _capture_document_binding(
    value: object,
    *,
    label: str,
    expected_path: str,
    expected_sha256: str,
    expected_size: int,
) -> None:
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "sizeBytes"}:
        _fail(f"{label} property set drifted")
    if (
        value.get("path") != expected_path
        or _sha256(value.get("sha256"), label=f"{label} sha256") != expected_sha256
        or _positive_int(value.get("sizeBytes"), label=f"{label} sizeBytes")
        != expected_size
    ):
        _fail(f"{label} differs from preserved provenance")


def _expected_export_heads(scope: dict[str, Any]) -> list[dict[str, Any]]:
    def binding(artifact: dict[str, Any]) -> dict[str, Any]:
        return {
            "relativePath": artifact["path"],
            "fileName": artifact["fileName"],
            "sha256": artifact["sha256"],
            "sizeBytes": artifact["sizeBytes"],
        }

    return [
        {
            "headId": head,
            "rid": RID,
            "installer": binding(scope["artifacts"][head]["installer"]),
            "payload": binding(scope["artifacts"][head]["payload"]),
        }
        for head in scope["heads"]
    ]


def _validate_export_artifact_binding(
    value: object,
    *,
    expected: dict[str, Any],
    label: str,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "relativePath",
        "fileName",
        "sha256",
        "sizeBytes",
    }:
        _fail(f"{label} property set drifted")
    size = value.get("sizeBytes")
    if (
        value.get("relativePath") != expected["relativePath"]
        or value.get("fileName") != expected["fileName"]
        or value.get("sha256") != expected["sha256"]
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size != expected["sizeBytes"]
    ):
        _fail(f"{label} drifted")


def _validate_export_heads(
    value: object,
    *,
    scope: dict[str, Any],
    label: str,
) -> None:
    expected_heads = _expected_export_heads(scope)
    if not isinstance(value, list) or len(value) != len(expected_heads):
        _fail(f"{label} scope drifted")
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {
            "headId",
            "rid",
            "installer",
            "payload",
        }:
            _fail(f"{label} head property set drifted")
        expected = expected_heads[index]
        if raw.get("headId") != expected["headId"] or raw.get("rid") != expected["rid"]:
            _fail(f"{label} scope drifted")
        _validate_export_artifact_binding(
            raw.get("installer"),
            expected=expected["installer"],
            label=f"{label} installer",
        )
        _validate_export_artifact_binding(
            raw.get("payload"),
            expected=expected["payload"],
            label=f"{label} payload",
        )


def _validate_capture_candidate_binding(
    value: object,
    *,
    canonical_manifest_sha256: str,
    capture_source: dict[str, Any],
    provenance_bytes: bytes,
    export_bytes: bytes,
    capture_generated_at: datetime,
    windows_only: bool,
) -> dict[str, Any]:
    required = {
        "actor",
        "artifactCreatedAt",
        "artifactExpiresAt",
        "artifactId",
        "artifactName",
        "artifactSha256",
        "authenticatedApiSha256",
        "contentInventory",
        "contentInventorySha256",
        "exportReceipt",
        "exportReceiptSha256",
        "handoffSha256",
        "manifestPath",
        "manifestSha256",
        "ref",
        "repository",
        "runAttempt",
        "runId",
        "sha",
        "workflow",
    }
    if windows_only:
        required.update(
            {
                "fullShelfCompatibilityManifest",
                "fullShelfCompatibilityManifestPath",
                "fullShelfCompatibilityManifestSha256",
                "fullShelfManifest",
                "fullShelfManifestPath",
                "fullShelfManifestSha256",
                "publicationScope",
                "publicationScopePath",
                "publicationScopeSha256",
                "registryPrepareFiles",
                "registryPrepareSha256",
                "scopeDecisionSha256",
                "signingReceipt",
                "signingReceiptPath",
                "signingReceiptSha256",
                "supplyChain",
            }
        )
    if not isinstance(value, dict) or set(value) != required:
        _fail("native-Windows capture candidate binding property set drifted")
    if (
        value.get("repository") != UI_REPOSITORY
        or value.get("workflow") != PRODUCER_WORKFLOW
        or value.get("ref") != PRODUCER_REF
        or not isinstance(value.get("sha"), str)
        or COMMIT_RE.fullmatch(value["sha"]) is None
        or not isinstance(value.get("actor"), str)
        or GITHUB_LOGIN_RE.fullmatch(value["actor"]) is None
    ):
        _fail("native-Windows capture candidate producer provenance drifted")
    for name in ("runId", "runAttempt", "artifactId"):
        _github_positive_integer(value.get(name), label=f"capture candidate {name}")
    if value.get("artifactName") != (
        f"preview-nightly-candidate-{value['runId']}-{value['runAttempt']}"
    ):
        _fail("native-Windows capture candidate artifact name drifted")
    for name in (
        "artifactSha256",
        "authenticatedApiSha256",
        "contentInventorySha256",
        "exportReceiptSha256",
        "handoffSha256",
        "manifestSha256",
    ):
        _sha256(value.get(name), label=f"capture candidate {name}")
    if windows_only:
        for name in (
            "fullShelfCompatibilityManifestSha256",
            "fullShelfManifestSha256",
            "publicationScopeSha256",
            "registryPrepareSha256",
            "scopeDecisionSha256",
            "signingReceiptSha256",
        ):
            _sha256(value.get(name), label=f"capture candidate {name}")
        for name in (
            "fullShelfCompatibilityManifest",
            "fullShelfManifest",
            "publicationScope",
            "signingReceipt",
        ):
            path_name = f"{name}Path"
            digest_name = f"{name}Sha256"
            path = _validate_relative_path(
                value.get(path_name), label=f"capture candidate {path_name}"
            )
            binding = value.get(name)
            if (
                not isinstance(binding, dict)
                or set(binding) != {"path", "sha256", "sizeBytes"}
                or binding.get("path") != f"candidate-provenance/{path}"
                or binding.get("sha256") != value.get(digest_name)
                or _positive_int(
                    binding.get("sizeBytes"),
                    label=f"capture candidate {name} sizeBytes",
                )
                < 1
            ):
                _fail(f"capture candidate {name} binding drifted")
        if not isinstance(value.get("registryPrepareFiles"), list) or not isinstance(
            value.get("supplyChain"), dict
        ):
            _fail("capture candidate Windows-only provenance drifted")
    provenance_sha256 = hashlib.sha256(provenance_bytes).hexdigest()
    export_sha256 = hashlib.sha256(export_bytes).hexdigest()
    if (
        value.get("manifestPath") != "RELEASE_CHANNEL.generated.json"
        or value.get("manifestSha256") != canonical_manifest_sha256
        or value.get("contentInventorySha256") != provenance_sha256
        or value.get("exportReceiptSha256") != export_sha256
    ):
        _fail("native-Windows capture candidate digest chain drifted")
    created_at = _github_timestamp(
        value.get("artifactCreatedAt"), label="capture candidate artifactCreatedAt"
    )
    expires_at = _github_timestamp(
        value.get("artifactExpiresAt"), label="capture candidate artifactExpiresAt"
    )
    if (
        created_at >= expires_at
        or created_at > capture_generated_at + timedelta(minutes=5)
        or expires_at <= capture_generated_at
    ):
        _fail("native-Windows capture candidate artifact lifetime drifted")
    if any(
        value.get(name) != capture_source.get(name)
        for name in ("repository", "ref", "sha")
    ):
        _fail("native-Windows capture candidate revision differs from capture source")
    _capture_document_binding(
        value.get("contentInventory"),
        label="capture candidate contentInventory",
        expected_path=CANDIDATE_PROVENANCE_INVENTORY,
        expected_sha256=provenance_sha256,
        expected_size=len(provenance_bytes),
    )
    _capture_document_binding(
        value.get("exportReceipt"),
        label="capture candidate exportReceipt",
        expected_path=CANDIDATE_PROVENANCE_EXPORT,
        expected_sha256=export_sha256,
        expected_size=len(export_bytes),
    )
    return value


def _validate_candidate_export_receipt(
    receipt: dict[str, Any],
    *,
    receipt_semantic: dict[str, Any],
    candidate_binding: dict[str, Any],
    candidate_binding_semantic: dict[str, Any],
    canonical_manifest_sha256: str,
    scope: dict[str, Any],
    windows_only: bool,
) -> None:
    required = {
        "candidateManifest",
        "contentInventory",
        "contractName",
        "contractVersion",
        "heads",
        "release",
        "source",
        "status",
    }
    if windows_only:
        required.update(
            {"publicationScope", "supplyChain", "supplyChainVerification"}
        )
    if not isinstance(receipt, dict) or set(receipt) != required:
        _fail("native-Windows candidate export receipt property set drifted")
    if (
        receipt.get("contractName") != CANDIDATE_EXPORT_CONTRACT
        or type(receipt.get("contractVersion")) is not int
        or receipt.get("contractVersion") != (2 if windows_only else 1)
        or receipt.get("status") != "exported"
        or not _json_semantic_equal(
            receipt_semantic.get("release"),
            {"channel": scope["channel"], "version": scope["version"]},
        )
        or not _json_semantic_equal(
            receipt_semantic.get("candidateManifest"),
            {
                "path": "RELEASE_CHANNEL.generated.json",
                "sha256": canonical_manifest_sha256,
            },
        )
        or not _json_semantic_equal(
            receipt_semantic.get("contentInventory"),
            {
                "path": CANDIDATE_PROVENANCE_INVENTORY.rsplit("/", 1)[-1],
                "sha256": candidate_binding["contentInventorySha256"],
            },
        )
    ):
        _fail("native-Windows candidate export release or byte binding drifted")
    if windows_only:
        if (
            not _json_semantic_equal(
                receipt_semantic.get("publicationScope"),
                {
                    "registryPrepareSha256": candidate_binding[
                        "registryPrepareSha256"
                    ]
                },
            )
            or not _json_semantic_equal(
                receipt_semantic.get("supplyChain"),
                candidate_binding_semantic.get("supplyChain"),
            )
            or not _json_semantic_equal(
                receipt_semantic.get("supplyChainVerification"),
                {
                    "mode": "release_authoritative",
                    "releaseAuthoritative": True,
                },
            )
        ):
            _fail("native-Windows candidate export Windows-only authority drifted")
    _validate_export_heads(
        receipt.get("heads"),
        scope=scope,
        label="native-Windows candidate export required-head",
    )
    source_value = receipt.get("source")
    required_source = {
        "actor",
        "artifactName",
        "ref",
        "repository",
        "runAttempt",
        "runId",
        "runnerLabel",
        "sha",
        "workflow",
    }
    if not isinstance(source_value, dict) or set(source_value) != required_source:
        _fail("native-Windows candidate export source property set drifted")
    for name in (
        "actor",
        "artifactName",
        "ref",
        "repository",
        "runAttempt",
        "runId",
        "sha",
        "workflow",
    ):
        if source_value.get(name) != candidate_binding[name] or not isinstance(
            source_value.get(name), str
        ):
            _fail("native-Windows candidate export source differs from capture authority")
    if (
        not isinstance(source_value.get("runnerLabel"), str)
        or EXPORT_RUNNER_LABEL_RE.fullmatch(source_value["runnerLabel"]) is None
    ):
        _fail("native-Windows candidate export runner label drifted")


def _validate_candidate_provenance(
    root: Path,
    *,
    bundle_root: Path,
    canonical_manifest_sha256: str,
    scope: dict[str, Any],
    windows_only: bool,
) -> tuple[dict[str, Any], bytes]:
    inventory, inventory_bytes = _strict_json(
        root / CANDIDATE_PROVENANCE_INVENTORY,
        label="native-Windows candidate provenance inventory",
    )
    if (
        inventory.get("contractName") != CANDIDATE_CONTENT_INVENTORY_CONTRACT
        or type(inventory.get("contractVersion")) is not int
        or inventory.get("contractVersion") != (2 if windows_only else 1)
        or inventory.get("release")
        != {"channel": scope["channel"], "version": scope["version"]}
        or inventory.get("manifest")
        != {"path": "RELEASE_CHANNEL.generated.json", "sha256": canonical_manifest_sha256}
    ):
        _fail("native-Windows candidate provenance inventory release binding drifted")
    required_paths = [
        "RELEASE_CHANNEL.generated.json",
        *(["releases.json"] if windows_only else []),
        *[
            artifact["path"]
            for head in scope["heads"]
            for artifact in (
                scope["artifacts"][head]["installer"],
                scope["artifacts"][head]["payload"],
            )
        ],
    ]
    rows = _inventory_rows(inventory.get("files"), label="native-Windows candidate content inventory")
    by_path = {row["path"]: row for row in rows}
    if (
        (windows_only and not set(required_paths).issubset(by_path))
        or (not windows_only and [row["path"] for row in rows] != sorted(required_paths))
    ):
        _fail("native-Windows proof does not bind the exact required-head candidate content set")
    for relative in required_paths:
        row = by_path[relative]
        path = bundle_root / row["path"]
        _plain_file(path, label=f"native-Windows candidate byte {row['path']}")
        if row["sha256"] != _sha256_file(path) or row["sizeBytes"] != path.stat().st_size:
            _fail("native-Windows proof candidate bytes differ from the upload candidate")
    return inventory, inventory_bytes


def _validate_capture_heads(
    value: object,
    *,
    scope: dict[str, Any],
    finalized_by_path: dict[str, dict[str, Any]],
    windows_only: bool,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(PROMOTED_HEADS):
        _fail("native-Windows capture must contain exactly one Avalonia head")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(value):
        expected_head_keys = {
            "headId",
            "rid",
            "installer",
            "payload",
            "receipt",
            "progressLog",
            "screenshots",
        }
        if windows_only:
            expected_head_keys.add("authenticodeVerification")
        if not isinstance(raw, dict) or set(raw) != expected_head_keys:
            _fail("native-Windows capture head property set drifted")
        head = PROMOTED_HEADS[index]
        if raw.get("headId") != head or raw.get("rid") != RID or head in result:
            _fail("native-Windows capture head scope drifted")
        expected_export = _expected_export_heads(scope)[index]
        _validate_export_artifact_binding(
            raw.get("installer"),
            expected=expected_export["installer"],
            label="native-Windows capture installer binding",
        )
        _validate_export_artifact_binding(
            raw.get("payload"),
            expected=expected_export["payload"],
            label="native-Windows capture payload binding",
        )

        for property_name, expected_path in (
            ("receipt", f"startup-smoke/startup-smoke-{head}-{RID}.receipt.json"),
            (
                "progressLog",
                f"startup-smoke/windows-installer-progress-{head}-{RID}.log",
            ),
        ):
            binding = raw.get(property_name)
            if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
                _fail(f"native-Windows capture {property_name} binding drifted")
            digest = _sha256(
                binding.get("sha256"),
                label=f"native-Windows capture {property_name} sha256",
            )
            inventory_row = finalized_by_path.get(expected_path)
            if (
                binding.get("path") != expected_path
                or inventory_row is None
                or inventory_row["sha256"] != digest
                or inventory_row["sizeBytes"] < 1
            ):
                _fail(
                    f"native-Windows capture {property_name} differs from finalized inventory"
                )

        screenshots = raw.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) != 2:
            _fail("native-Windows capture screenshot set drifted")
        expected_screenshots: list[dict[str, Any]] = []
        digests: set[str] = set()
        for screenshot_index, role in enumerate(("progress", "completion")):
            screenshot = screenshots[screenshot_index]
            if not isinstance(screenshot, dict) or set(screenshot) != {
                "role",
                "path",
                "sha256",
                "width",
                "height",
            }:
                _fail("native-Windows capture screenshot binding drifted")
            expected_path = f"screenshots/windows-installer-{head}-{RID}-{role}.png"
            digest = _sha256(
                screenshot.get("sha256"),
                label=f"native-Windows capture {role} screenshot sha256",
            )
            width = _positive_int(
                screenshot.get("width"),
                label=f"native-Windows capture {role} screenshot width",
            )
            height = _positive_int(
                screenshot.get("height"),
                label=f"native-Windows capture {role} screenshot height",
            )
            inventory_row = finalized_by_path.get(expected_path)
            if (
                screenshot.get("role") != role
                or screenshot.get("path") != expected_path
                or not 320 <= width <= 16_384
                or not 200 <= height <= 16_384
                or inventory_row is None
                or inventory_row["sha256"] != digest
                or inventory_row["sizeBytes"] < 1
                or digest in digests
            ):
                _fail("native-Windows capture screenshot differs from finalized inventory")
            digests.add(digest)
            expected_screenshots.append(
                {"role": role, "path": expected_path, "sha256": digest}
            )
        result[head] = {"screenshots": expected_screenshots}
        if windows_only:
            authenticode = raw.get("authenticodeVerification")
            if (
                not isinstance(authenticode, dict)
                or set(authenticode) != NATIVE_AUTHENTICODE_BINDING_KEYS
                or authenticode.get("path") != NATIVE_AUTHENTICODE_SOURCE_PATH
                or finalized_by_path.get(NATIVE_AUTHENTICODE_SOURCE_PATH)
                != {
                    "path": NATIVE_AUTHENTICODE_SOURCE_PATH,
                    "sha256": authenticode.get("sha256"),
                    "sizeBytes": authenticode.get("sizeBytes"),
                }
            ):
                _fail("native-Windows capture Authenticode binding drifted")
    return result


def _validate_native_evidence(
    root: Path,
    *,
    bundle_root: Path,
    canonical_manifest_sha256: str,
    scope: dict[str, Any],
    now: datetime,
    max_age: timedelta,
) -> tuple[
    dict[str, Any],
    datetime,
    list[tuple[str, bytes]],
    dict[str, Any],
]:
    if root.is_symlink() or not root.is_dir():
        _fail("finalized native-Windows evidence root must be a real directory")
    finalized_inventory, finalized_inventory_bytes = _strict_json(
        root / FINALIZED_INVENTORY_FILE,
        label="finalized native-Windows inventory",
    )
    if (
        set(finalized_inventory)
        != {"contractName", "contractVersion", "captureInventorySha256", "files"}
        or
        finalized_inventory.get("contractName") != FINALIZED_INVENTORY_CONTRACT
        or type(finalized_inventory.get("contractVersion")) is not int
        or finalized_inventory.get("contractVersion") != 1
    ):
        _fail("finalized native-Windows inventory contract drifted")
    finalized_rows = _inventory_rows(
        finalized_inventory.get("files"), label="finalized native-Windows inventory"
    )
    if finalized_rows != _exact_tree_rows(root, exclude={FINALIZED_INVENTORY_FILE}):
        _fail("finalized native-Windows inventory does not match its exact artifact tree")
    finalized_by_path = {row["path"]: row for row in finalized_rows}

    capture, capture_bytes = _strict_json(
        root / CAPTURE_FILE, label="native-Windows capture receipt"
    )
    raw_candidate = capture.get("candidate")
    windows_only = isinstance(raw_candidate, dict) and "publicationScope" in raw_candidate
    expected_native_version = 2 if windows_only else 1
    if not windows_only:
        _fail("candidate import requires Windows-only native evidence v2")
    finalization, finalization_bytes = _strict_json(
        root / FINALIZATION_FILE, label="native-Windows finalization receipt"
    )
    if (
        set(finalization) != NATIVE_FINALIZATION_V2_KEYS
        or
        finalization.get("contractName") != FINALIZATION_CONTRACT
        or type(finalization.get("contractVersion")) is not int
        or finalization.get("contractVersion") != expected_native_version
        or finalization.get("status") != "passed"
        or finalization.get("humanReviewConfirmed") is not True
        or finalization.get("reviewerWasCaptureActor") is not False
    ):
        _fail("native-Windows finalization is not a protected human pass")
    finalized_at = _fresh_timestamp(
        finalization.get("generatedAt"),
        label="native-Windows finalization generatedAt",
        now=now,
        max_age=max_age,
    )
    reviewer = finalization.get("reviewer")
    if not isinstance(reviewer, str) or REVIEWER_RE.fullmatch(reviewer) is None:
        _fail("native-Windows finalization reviewer provenance is invalid")
    capture_source = _source(
        finalization.get("captureSource"),
        label="native-Windows capture source",
        workflow=CAPTURE_WORKFLOW,
    )
    finalization_source = _source(
        finalization.get("finalizationSource"),
        label="native-Windows finalization source",
        workflow=FINALIZE_WORKFLOW,
    )
    if (
        capture_source["actor"] != "github-actions[bot]"
        or finalization_source["actor"] != reviewer
        or reviewer == capture_source["actor"]
        or capture_source["sha"] != finalization_source["sha"]
    ):
        _fail("native-Windows protected reviewer provenance drifted")

    if (
        set(capture)
        != {
            "authenticodeVerification",
            "candidate",
            "captureMode",
            "channelId",
            "contractName",
            "contractVersion",
            "generatedAt",
            "heads",
            "source",
            "status",
            "version",
        }
        or
        capture.get("contractName") != CAPTURE_CONTRACT
        or type(capture.get("contractVersion")) is not int
        or capture.get("contractVersion") != expected_native_version
        or capture.get("status") != "captured"
        or capture.get("captureMode") != "interactive"
        or capture.get("source") != capture_source
    ):
        _fail("native-Windows capture receipt drifted")
    captured_at = _fresh_timestamp(
        capture.get("generatedAt"),
        label="native-Windows capture generatedAt",
        now=now,
        max_age=max_age,
    )
    version = str(capture.get("version") or "")
    channel = str(capture.get("channelId") or "")
    if (
        version != scope["version"]
        or channel != scope["channel"]
        or VERSION_RE.fullmatch(version) is None
    ):
        _fail("native-Windows capture release identity is invalid")
    capture_heads = _validate_capture_heads(
        capture.get("heads"),
        scope=scope,
        finalized_by_path=finalized_by_path,
        windows_only=windows_only,
    )
    provenance_inventory, provenance_bytes = _validate_candidate_provenance(
        root,
        bundle_root=bundle_root,
        canonical_manifest_sha256=canonical_manifest_sha256,
        scope=scope,
        windows_only=windows_only,
    )
    export_receipt, export_bytes = _strict_json(
        root / CANDIDATE_PROVENANCE_EXPORT,
        label="native-Windows candidate export receipt",
    )
    candidate_binding = _validate_capture_candidate_binding(
        capture.get("candidate"),
        canonical_manifest_sha256=canonical_manifest_sha256,
        capture_source=capture_source,
        provenance_bytes=provenance_bytes,
        export_bytes=export_bytes,
        capture_generated_at=captured_at,
        windows_only=windows_only,
    )
    _validate_candidate_export_receipt(
        export_receipt,
        receipt_semantic=_json_semantic_object(
            export_bytes,
            label="native-Windows candidate export receipt",
        ),
        candidate_binding=candidate_binding,
        candidate_binding_semantic=_json_semantic_object(
            capture_bytes,
            label="native-Windows capture receipt",
        )["candidate"],
        canonical_manifest_sha256=canonical_manifest_sha256,
        scope=scope,
        windows_only=windows_only,
    )

    capture_inventory, capture_inventory_bytes = _strict_json(
        root / CAPTURE_INVENTORY_FILE, label="native-Windows capture inventory"
    )
    if (
        set(capture_inventory)
        != {
            "contractName",
            "contractVersion",
            "captureContract",
            "captureManifestSha256",
            "files",
        }
        or
        capture_inventory.get("contractName") != CAPTURE_INVENTORY_CONTRACT
        or type(capture_inventory.get("contractVersion")) is not int
        or capture_inventory.get("contractVersion") != expected_native_version
        or capture_inventory.get("captureContract") != CAPTURE_CONTRACT
        or capture_inventory.get("captureManifestSha256")
        != hashlib.sha256(capture_bytes).hexdigest()
    ):
        _fail("native-Windows capture inventory binding drifted")
    capture_rows = _inventory_rows(
        capture_inventory.get("files"),
        label="native-Windows capture inventory",
    )
    if any(
        finalized_by_path.get(row["path"]) != row for row in capture_rows
    ):
        _fail("native-Windows capture inventory differs from its finalized capture tree")
    capture_inventory_sha256 = hashlib.sha256(capture_inventory_bytes).hexdigest()
    if (
        finalization.get("captureInventorySha256") != capture_inventory_sha256
        or finalized_inventory.get("captureInventorySha256")
        != capture_inventory_sha256
    ):
        _fail("native-Windows finalization capture inventory binding drifted")

    proof_rows = finalization.get("proofs")
    if not isinstance(proof_rows, list) or len(proof_rows) != len(scope["heads"]):
        _fail("native-Windows finalization must bind every required-head visual proof exactly once")
    proof_by_head: dict[str, tuple[str, bytes, dict[str, Any]]] = {}
    custody: list[tuple[str, bytes]] = [
        (CAPTURE_FILE, capture_bytes),
        (CAPTURE_INVENTORY_FILE, capture_inventory_bytes),
        (FINALIZATION_FILE, finalization_bytes),
        (FINALIZED_INVENTORY_FILE, finalized_inventory_bytes),
        (CANDIDATE_PROVENANCE_INVENTORY, provenance_bytes),
        (CANDIDATE_PROVENANCE_EXPORT, export_bytes),
    ]
    for row in proof_rows:
        if not isinstance(row, dict) or set(row) != {"headId", "path", "sha256"}:
            _fail("native-Windows finalization proof binding drifted")
        head = row.get("headId")
        if head not in scope["heads"] or head in proof_by_head:
            _fail("native-Windows finalization proof head drifted")
        relative = _validate_relative_path(row.get("path"), label="native-Windows visual proof path")
        proof, proof_bytes = _strict_json(root / relative, label=f"{head} visual proof")
        if row.get("sha256") != hashlib.sha256(proof_bytes).hexdigest():
            _fail("native-Windows visual proof digest drifted")
        finalized_row = finalized_by_path.get(relative)
        if finalized_row != {
            "path": relative,
            "sha256": row["sha256"],
            "sizeBytes": len(proof_bytes),
        }:
            _fail("native-Windows visual proof finalized inventory binding drifted")
        proof_by_head[head] = (relative, proof_bytes, proof)
        custody.append((relative, proof_bytes))

    expected_finalized_paths = {
        *(row["path"] for row in capture_rows),
        CAPTURE_INVENTORY_FILE,
        FINALIZATION_FILE,
        *(relative for relative, _proof_bytes, _proof in proof_by_head.values()),
    }
    if windows_only:
        expected_finalized_paths.add(NATIVE_SCOPE_APPROVAL_FILE)
    if set(finalized_by_path) != expected_finalized_paths:
        _fail("finalized native-Windows inventory file scope drifted")

    non_capture_paths = {
        CAPTURE_INVENTORY_FILE,
        FINALIZATION_FILE,
        *(relative for relative, _proof_bytes, _proof in proof_by_head.values()),
    }
    if windows_only:
        non_capture_paths.add(NATIVE_SCOPE_APPROVAL_FILE)
    expected_capture_rows = [
        row for row in finalized_rows if row["path"] not in non_capture_paths
    ]
    if capture_rows != expected_capture_rows:
        _fail("native-Windows capture inventory differs from its exact pre-finalization tree")

    for head in scope["heads"]:
        relative, _proof_bytes, proof = proof_by_head[head]
        installer_artifact = scope["artifacts"][head]["installer"]
        payload_artifact = scope["artifacts"][head]["payload"]
        installer_name = installer_artifact["fileName"]
        payload_name = payload_artifact["fileName"]
        installer = bundle_root / installer_artifact["path"]
        payload = bundle_root / payload_artifact["path"]
        startup_relative = f"startup-smoke/startup-smoke-{head}-{RID}.receipt.json"
        startup, startup_bytes = _strict_json(
            root / startup_relative, label=f"{head} native startup receipt"
        )
        if finalized_by_path.get(startup_relative) != {
            "path": startup_relative,
            "sha256": hashlib.sha256(startup_bytes).hexdigest(),
            "sizeBytes": len(startup_bytes),
        }:
            _fail(f"{head} startup proof finalized inventory binding drifted")
        native = startup.get("nativeHostEvidence")
        if (
            startup.get("status") != "pass"
            or startup.get("readyCheckpoint") != "pre_ui_event_loop"
            or startup.get("executionEnvironment") != "native_windows"
            or startup.get("headId") != head
            or startup.get("platform") != "windows"
            or startup.get("rid") != RID
            or startup.get("releaseVersion") != version
            or startup.get("channelId") != channel
            or startup.get("artifactFileName") != installer_name
            or startup.get("artifactDigest") != f"sha256:{installer_artifact['sha256']}"
            or startup.get("bootstrapPayloadAcquisitionMode") != "download"
            or startup.get("bootstrapPayloadFileName") != payload_name
            or startup.get("bootstrapPayloadSha256") != payload_artifact["sha256"]
            or isinstance(startup.get("bootstrapPayloadSizeBytes"), bool)
            or not isinstance(startup.get("bootstrapPayloadSizeBytes"), int)
            or startup.get("bootstrapPayloadSizeBytes") != payload_artifact["sizeBytes"]
            or not isinstance(native, dict)
            or native.get("contractName") != NATIVE_HOST_CONTRACT
            or native.get("status") != "verified"
            or native.get("isNativeWindows") is not True
            or native.get("hostPlatform") != "windows"
            or not isinstance(native.get("runner"), str)
            or not native["runner"].strip()
            or "wine" in str(native.get("runner") or "").lower()
        ):
            _fail(f"{head} startup proof is not exact native-Windows evidence")
        _fresh_timestamp(
            proof.get("generatedAt"),
            label=f"{head} visual proof generatedAt",
            now=now,
            max_age=max_age,
        )
        screenshots = proof.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) != 2:
            _fail(f"{head} visual proof screenshot set drifted")
        screenshot_roles: set[str] = set()
        for screenshot in screenshots:
            if not isinstance(screenshot, dict) or set(screenshot) != {"role", "path", "sha256"}:
                _fail(f"{head} visual proof screenshot binding drifted")
            role = screenshot.get("role")
            path = _validate_relative_path(
                screenshot.get("path"), label=f"{head} visual proof screenshot path"
            )
            digest = _sha256(
                screenshot.get("sha256"), label=f"{head} visual proof screenshot digest"
            )
            if role not in {"progress", "completion"} or role in screenshot_roles:
                _fail(f"{head} visual proof screenshot role drifted")
            screenshot_roles.add(role)
            finalized_row = finalized_by_path.get(path)
            if finalized_row is None or finalized_row["sha256"] != digest:
                _fail(f"{head} visual proof screenshot finalized inventory binding drifted")
        if screenshots != capture_heads[head]["screenshots"]:
            _fail(f"{head} visual proof screenshots differ from the capture head")
        checks = proof.get("checks")
        review = proof.get("review")
        capture_binding = proof.get("captureBinding")
        expected_capture_binding = {
            key: capture_source[key]
            for key in (
                "repository",
                "workflow",
                "runId",
                "runAttempt",
                "ref",
                "sha",
                "artifactName",
            )
        }
        expected_capture_binding["inventorySha256"] = hashlib.sha256(
            capture_inventory_bytes
        ).hexdigest()
        if (
            set(proof) != NATIVE_PORTABLE_VISUAL_KEYS
            or
            proof.get("contractName") != VISUAL_PROOF_CONTRACT
            or type(proof.get("contractVersion")) is not int
            or proof["contractVersion"] != 1
            or proof.get("status") != "passed"
            or proof.get("version") != version
            or proof.get("headId") != head
            or proof.get("head") != head
            or proof.get("platform") != "windows"
            or proof.get("rid") != RID
            or proof.get("releaseVersion") != version
            or proof.get("channel") != channel
            or proof.get("channelId") != channel
            or proof.get("artifactFileName") != installer_name
            or proof.get("artifactDigest") != f"sha256:{installer_artifact['sha256']}"
            or not isinstance(checks, dict)
            or set(checks) != {"capture_mode", "human_review_confirmed"}
            or checks.get("capture_mode") != "interactive"
            or checks.get("human_review_confirmed") is not True
            or proof.get("readabilityReview")
            != {"status": "passed", "reviewer": reviewer}
            or proof.get("contrastReview")
            != {"status": "passed", "reviewer": reviewer}
            or proof.get("clippingReview")
            != {"status": "passed", "reviewer": reviewer}
            or review
            != {
                "authenticatedReviewer": reviewer,
                "captureActor": capture_source["actor"],
                "allowlistSource": "repository variable plus protected environment",
                "explicitConfirmations": {
                    "readability": "passed",
                    "contrast": "passed",
                    "clipping": "passed",
                },
            }
            or capture_binding != expected_capture_binding
            or proof.get("finalizationBinding") != finalization_source
        ):
            _fail(f"{head} visual proof is not an exact finalized human pass")
        if windows_only:
            expected_auth = finalization.get("authenticodeVerification")
            if (
                not isinstance(expected_auth, dict)
                or set(expected_auth) != NATIVE_AUTHENTICODE_BINDING_KEYS
                or expected_auth.get("path") != NATIVE_AUTHENTICODE_SOURCE_PATH
                or proof.get("authenticodeVerification") != expected_auth
            ):
                _fail(f"{head} visual proof Authenticode binding drifted")
        custody.append((startup_relative, startup_bytes))

    evidence_summary = {
        "status": "passed",
        "captureGeneratedAtUtc": captured_at.isoformat().replace("+00:00", "Z"),
        "finalizationGeneratedAtUtc": finalized_at.isoformat().replace("+00:00", "Z"),
        "reviewer": reviewer,
        "captureSource": capture_source,
        "finalizationSource": finalization_source,
        "candidateContentInventorySha256": hashlib.sha256(provenance_bytes).hexdigest(),
        "candidateContentInventory": provenance_inventory,
    }
    oldest = min(captured_at, finalized_at)
    native_package = {
        "candidate": candidate_binding,
        "captureInventorySha256": capture_inventory_sha256,
        "finalizationBytes": finalization_bytes,
        "visualProofs": {
            head: proof for head, (_path, _raw, proof) in proof_by_head.items()
        },
    }
    return evidence_summary, oldest, custody, native_package


def _canonical_sha256(value: object, *, trailing_lf: bool = False) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if trailing_lf:
        rendered += b"\n"
    return hashlib.sha256(rendered).hexdigest()


def _ui_compact_sha256(value: object) -> str:
    """Match UI/Registry v3 compact sorted JSON hashing exactly."""
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _byte_reference(
    value: object,
    *,
    label: str,
    expected_path: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "sizeBytes"}:
        _fail(f"{label} byte reference drifted")
    path = _validate_relative_path(value.get("path"), label=f"{label} path")
    digest = _sha256(value.get("sha256"), label=f"{label} sha256")
    size = _positive_int(value.get("sizeBytes"), label=f"{label} sizeBytes")
    if expected_path is not None and path != expected_path:
        _fail(f"{label} path drifted")
    return {"path": path, "sha256": digest, "sizeBytes": size}


def _bound_stage_file(
    root: Path,
    reference: object,
    *,
    label: str,
    expected_path: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    binding = _byte_reference(reference, label=label, expected_path=expected_path)
    candidate = root.joinpath(*binding["path"].split("/"))
    try:
        parent = candidate.parent.resolve(strict=True)
        parent.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CandidateAuthorityBlocked(f"{label} escapes the publication stage root") from exc
    payload, raw = _strict_json(candidate, label=label)
    if len(raw) != binding["sizeBytes"] or _sha256_file(candidate) != binding["sha256"]:
        _fail(f"{label} bytes differ from their binding")
    return binding, payload, raw


def _sha_values(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            result.update(_sha_values(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_sha_values(child))
    elif isinstance(value, str):
        candidate = value.removeprefix("sha256:")
        if SHA256_RE.fullmatch(candidate):
            result.add(candidate)
    return result


def _scope_tuple(
    value: object,
    *,
    label: str,
    allow_evidence_path: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SCOPE_TUPLE_KEYS:
        _fail(f"{label} tuple property set drifted")
    if (
        value.get("head") != "avalonia"
        or value.get("platform") not in {"linux", "macos", "windows"}
        or value.get("artifactRole") not in {"installer", "payload"}
        or not isinstance(value.get("consumerCommit"), str)
        or COMMIT_RE.fullmatch(value["consumerCommit"]) is None
    ):
        _fail(f"{label} tuple identity drifted")
    platform = value["platform"]
    rid = value.get("rid")
    role = value["artifactRole"]
    if (
        platform == "windows"
        and rid != RID
        or platform == "linux"
        and rid != "linux-x64"
        or platform == "macos"
        and rid not in {"osx-arm64", "osx-x64"}
        or platform != "windows"
        and role != "installer"
    ):
        _fail(f"{label} tuple platform scope drifted")
    file_name = value.get("fileName")
    path = _validate_relative_path(value.get("path"), label=f"{label} tuple path")
    expected_paths = {f"files/{file_name}"}
    if allow_evidence_path and platform == "linux" and role == "installer":
        expected_paths.add(f"release-evidence/non-published/files/{file_name}")
    if (
        not isinstance(file_name, str)
        or not file_name
        or "/" in file_name
        or "\\" in file_name
        or path not in expected_paths
    ):
        _fail(f"{label} tuple file binding drifted")
    _sha256(value.get("sha256"), label=f"{label} tuple sha256")
    _sha256(value.get("manifestRowSha256"), label=f"{label} manifest row sha256")
    _positive_int(value.get("sizeBytes"), label=f"{label} tuple sizeBytes")
    source = value.get("sourceReceipt")
    if not isinstance(source, dict) or set(source) != {
        "contractName",
        "contractVersion",
        "path",
        "sha256",
    }:
        _fail(f"{label} tuple source receipt drifted")
    if (
        not isinstance(source.get("contractName"), str)
        or not source["contractName"]
        or isinstance(source.get("contractVersion"), bool)
        or not isinstance(source.get("contractVersion"), int)
        or source["contractVersion"] < 1
    ):
        _fail(f"{label} tuple source receipt is invalid")
    _validate_relative_path(source.get("path"), label=f"{label} source receipt path")
    _sha256(source.get("sha256"), label=f"{label} source receipt sha256")
    return value


def _scope_tuples(
    value: object,
    *,
    label: str,
    allow_evidence_path: bool = False,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > 32:
        qualifier = "bounded tuple set" if allow_empty else "bounded non-empty tuple set"
        _fail(f"{label} must be a {qualifier}")
    rows = [
        _scope_tuple(row, label=label, allow_evidence_path=allow_evidence_path)
        for row in value
    ]
    keys = [
        (
            row["head"],
            row["platform"],
            row["rid"],
            row["artifactRole"],
            row["fileName"],
        )
        for row in rows
    ]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        _fail(f"{label} tuple ordering or uniqueness drifted")
    return rows


def _scope_inventory(value: object, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 4096:
        _fail(f"{label} must be a bounded non-empty inventory")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {
            "mode",
            "path",
            "sha256",
            "sizeBytes",
        }:
            _fail(f"{label} row {index} drifted")
        mode = raw.get("mode")
        if isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0o7777:
            _fail(f"{label} row mode drifted")
        rows.append(
            {
                "mode": mode,
                "path": _validate_relative_path(raw.get("path"), label=f"{label} path"),
                "sha256": _sha256(raw.get("sha256"), label=f"{label} sha256"),
                "sizeBytes": _positive_int(
                    raw.get("sizeBytes"), label=f"{label} sizeBytes", allow_zero=True
                ),
            }
        )
    if rows != sorted(rows, key=lambda row: row["path"]) or len(
        {row["path"] for row in rows}
    ) != len(rows):
        _fail(f"{label} is not uniquely sorted")
    return rows


def _tuple_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        row[key]
        for key in (
            "artifactRole",
            "consumerCommit",
            "fileName",
            "head",
            "manifestRowSha256",
            "platform",
            "rid",
            "sha256",
            "sizeBytes",
        )
    )


def _stage_json_digest_binding(
    root: Path,
    *,
    relative_path: object,
    expected_sha256: object,
    label: str,
) -> tuple[str, dict[str, Any], bytes]:
    path = _validate_relative_path(relative_path, label=f"{label} path")
    digest = _sha256(expected_sha256, label=f"{label} sha256")
    candidate = root.joinpath(*path.split("/"))
    try:
        candidate.parent.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise CandidateAuthorityBlocked(f"{label} escapes the publication stage root") from exc
    payload, raw = _strict_json(candidate, label=label)
    if hashlib.sha256(raw).hexdigest() != digest:
        _fail(f"{label} digest binding drifted")
    return path, payload, raw


def _validate_signing_receipt_v2(
    receipt: dict[str, Any],
    *,
    version: str,
    delta: list[dict[str, Any]],
) -> None:
    if (
        receipt.get("contractName") != SIGNING_CONTRACT
        or type(receipt.get("contractVersion")) is not int
        or receipt.get("contractVersion") != 2
        or receipt.get("platform") != "windows"
        or receipt.get("app") != "avalonia"
        or receipt.get("rid") != RID
        or receipt.get("releaseChannel") != "preview"
        or receipt.get("releaseVersion") != version
        or receipt.get("signingStatus") != "pass"
    ):
        _fail("final Windows signing receipt is not an exact v2 pass")
    candidate_bindings = receipt.get("candidateBindings")
    if not isinstance(candidate_bindings, list) or len(candidate_bindings) != 2:
        _fail("final Windows signing receipt candidate binding drifted")
    expected = {
        (
            row["artifactRole"],
            row["fileName"],
            row["sha256"],
            row["sizeBytes"],
            "pass" if row["artifactRole"] == "installer" else "not_applicable_payload",
        )
        for row in delta
    }
    actual: set[tuple[object, ...]] = set()
    for row in candidate_bindings:
        if not isinstance(row, dict) or set(row) != {
            "artifactRole",
            "authenticodeStatus",
            "fileName",
            "sha256",
            "sizeBytes",
        }:
            _fail("final Windows signing receipt candidate row drifted")
        actual.add(
            (
                row.get("artifactRole"),
                row.get("fileName"),
                row.get("sha256"),
                row.get("sizeBytes"),
                row.get("authenticodeStatus"),
            )
        )
    if actual != expected:
        _fail("final Windows signing receipt binds different candidate bytes")
    installer = next(row for row in delta if row["artifactRole"] == "installer")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or len(
        [
            row
            for row in artifacts
            if isinstance(row, dict)
            and row.get("fileName") == installer["fileName"]
            and row.get("sha256") == installer["sha256"]
            and row.get("signingStatus") == "pass"
        ]
    ) != 1:
        _fail("final Windows signing receipt lacks one passing installer row")


def _validate_authenticode_receipt(
    receipt: dict[str, Any],
    *,
    installer: dict[str, Any],
    native: dict[str, Any],
) -> None:
    if (
        set(receipt)
        != {
            "artifact",
            "contractName",
            "contractVersion",
            "generatedAt",
            "policy",
            "signature",
            "signer",
            "source",
            "status",
            "timestamp",
            "verifier",
        }
        or receipt.get("contractName") != AUTHENTICODE_CONTRACT
        or type(receipt.get("contractVersion")) is not int
        or receipt.get("contractVersion") != 1
        or receipt.get("status") != "verified"
        or receipt.get("artifact")
        != {
            "fileName": installer["fileName"],
            "sha256": installer["sha256"],
            "sizeBytes": installer["sizeBytes"],
        }
        or receipt.get("signature")
        != {
            "codeSigningEkuOid": "1.3.6.1.5.5.7.3.3",
            "cryptographicVerification": "passed",
            "status": "valid",
            "type": "authenticode",
        }
    ):
        _fail("independent Authenticode verification receipt is not an exact pass")
    source = receipt.get("source")
    capture_source = native.get("captureSource")
    if not isinstance(source, dict) or not isinstance(capture_source, dict) or any(
        source.get(key) != capture_source.get(key)
        for key in ("actor", "ref", "repository", "runAttempt", "runId", "sha", "workflow")
    ):
        _fail("independent Authenticode verifier source differs from native capture")
    policy = receipt.get("policy")
    signer = receipt.get("signer")
    timestamp = receipt.get("timestamp")
    if (
        not isinstance(policy, dict)
        or set(policy) != {"signerCertificateSha256", "signerSpkiSha256"}
        or not isinstance(signer, dict)
        or not isinstance(timestamp, dict)
    ):
        _fail("independent Authenticode signer policy drifted")
    certificate = _sha256(
        policy.get("signerCertificateSha256"), label="Authenticode signer certificate"
    )
    spki = _sha256(policy.get("signerSpkiSha256"), label="Authenticode signer SPKI")
    if signer.get("certificateSha256") != certificate or signer.get("spkiSha256") != spki:
        _fail("independent Authenticode signer identity differs from policy")
    for label, chain in (
        ("Authenticode signer chain", signer.get("chain")),
        ("RFC3161 timestamp chain", timestamp.get("chain")),
    ):
        if (
            not isinstance(chain, dict)
            or chain.get("trusted") is not True
            or chain.get("status") != []
            or chain.get("revocationFlag") != "entire_chain"
            or chain.get("revocationMode") != "online"
            or chain.get("verificationFlags") != "no_flag"
        ):
            _fail(f"{label} is not a trusted online whole-chain result")
    if (
        timestamp.get("format") != "rfc3161"
        or timestamp.get("status") != "verified"
        or timestamp.get("timestampingEkuOid") != "1.3.6.1.5.5.7.3.8"
        or timestamp.get("attributeOid") != "1.2.840.113549.1.9.16.2.14"
        or timestamp.get("messageImprintAlgorithmOid") != "2.16.840.1.101.3.4.2.1"
    ):
        _fail("independent Authenticode RFC3161 timestamp is not exact")


def _native_contract_reference(
    value: object,
    *,
    label: str,
    contract_name: str,
    contract_version: int,
    path: str,
    raw: bytes,
) -> None:
    expected = {
        "contractName": contract_name,
        "contractVersion": contract_version,
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
    }
    if not isinstance(value, dict) or set(value) != NATIVE_CONTRACT_REFERENCE_KEYS:
        _fail(f"{label} is not an exact contract-aware file reference")
    if (
        type(value.get("contractVersion")) is not int
        or type(value.get("sizeBytes")) is not int
    ):
        _fail(f"{label} contract version or size type drifted")
    if value != expected:
        _fail(f"{label} differs from held bytes")


def _native_workflow_source(
    value: object,
    *,
    label: str,
    workflow: str,
    artifact_prefix: str,
) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != NATIVE_WORKFLOW_SOURCE_KEYS:
        _fail(f"{label} workflow source property set drifted")
    if any(not isinstance(value.get(key), str) or not value[key] for key in value):
        _fail(f"{label} workflow source contains an invalid value")
    source = value
    if (
        source["workflow"] != workflow
        or POSITIVE_INTEGER_RE.fullmatch(source["runId"]) is None
        or POSITIVE_INTEGER_RE.fullmatch(source["runAttempt"]) is None
        or not source["ref"].startswith(("refs/heads/", "refs/tags/"))
        or any(character.isspace() for character in source["ref"])
        or COMMIT_RE.fullmatch(source["sha"]) is None
        or "/" not in source["repository"]
        or GITHUB_LOGIN_RE.fullmatch(source["actor"]) is None
        or source["artifactName"]
        != f"{artifact_prefix}-{source['runId']}-{source['runAttempt']}"
    ):
        _fail(f"{label} workflow source identity drifted")
    return source


def _validate_final_native_composite(
    *,
    scope_payload: dict[str, Any],
    native: dict[str, Any],
    native_bytes: bytes,
    finalization: dict[str, Any],
    finalization_bytes: bytes,
    authenticode_bytes: bytes,
    approval: dict[str, Any],
    approval_bytes: bytes,
    visual: dict[str, Any],
    visual_bytes: bytes,
    candidate_version: str,
    installer: dict[str, Any],
    native_package: dict[str, Any],
) -> tuple[str, str, str]:
    composite = scope_payload.get("nativeEvidenceComposite")
    if not isinstance(composite, dict) or set(composite) != NATIVE_COMPOSITE_KEYS:
        _fail("final UI native evidence composite property set drifted")
    _native_contract_reference(
        composite.get("wrapper"),
        label="native evidence wrapper reference",
        contract_name=NATIVE_WRAPPER_CONTRACT,
        contract_version=1,
        path=NATIVE_WRAPPER_FILE,
        raw=native_bytes,
    )
    _native_contract_reference(
        composite.get("nativeFinalization"),
        label="native finalization reference",
        contract_name=FINALIZATION_CONTRACT,
        contract_version=2,
        path=NATIVE_FINALIZATION_V2_FILE,
        raw=finalization_bytes,
    )
    _native_contract_reference(
        composite.get("visualProof"),
        label="Windows visual proof reference",
        contract_name=VISUAL_PROOF_CONTRACT,
        contract_version=1,
        path=NATIVE_VISUAL_FILE,
        raw=visual_bytes,
    )
    _native_contract_reference(
        composite.get("authenticodeVerification"),
        label="Authenticode verification reference",
        contract_name=AUTHENTICODE_CONTRACT,
        contract_version=1,
        path=AUTHENTICODE_RECEIPT_PATH,
        raw=authenticode_bytes,
    )

    if (
        set(native) != NATIVE_WRAPPER_KEYS
        or native.get("contractName") != NATIVE_WRAPPER_CONTRACT
        or type(native.get("contractVersion")) is not int
        or native.get("contractVersion") != 1
        or native.get("status") != "passed"
        or native.get("release")
        != {"channel": "preview", "version": candidate_version}
        or native.get("captureInventorySha256")
        != native_package.get("captureInventorySha256")
        or finalization_bytes != native_package.get("finalizationBytes")
    ):
        _fail("final native Windows wrapper contract or release identity drifted")
    for key in (
        "archiveSha256",
        "captureInventorySha256",
        "finalizationSha256",
        "finalizedInventorySha256",
        "treeSha256",
    ):
        _sha256(native.get(key), label=f"native wrapper {key}")
    _positive_int(native.get("fileCount"), label="native wrapper fileCount")
    _validate_relative_path(native.get("archivePath"), label="native wrapper archive path")
    if native.get("nativeFinalization") != {
        "path": NATIVE_FINALIZATION_V2_FILE,
        "sha256": hashlib.sha256(finalization_bytes).hexdigest(),
        "sizeBytes": len(finalization_bytes),
    } or native.get("visualProof") != {
        "path": NATIVE_VISUAL_FILE,
        "sha256": hashlib.sha256(visual_bytes).hexdigest(),
        "sizeBytes": len(visual_bytes),
    }:
        _fail("native wrapper finalization or visual byte reference drifted")
    if native.get("finalizationSha256") != hashlib.sha256(finalization_bytes).hexdigest():
        _fail("native wrapper finalization digest alias drifted")

    capture_source = _native_workflow_source(
        native.get("captureSource"),
        label="native capture",
        workflow=CAPTURE_WORKFLOW,
        artifact_prefix="windows-native-evidence",
    )
    finalization_source = _native_workflow_source(
        native.get("finalizationSource"),
        label="native finalization",
        workflow=FINALIZE_WORKFLOW,
        artifact_prefix="windows-native-evidence-finalized",
    )
    if (
        capture_source["repository"] != finalization_source["repository"]
        or capture_source["sha"] != finalization_source["sha"]
        or capture_source["actor"].lower() == finalization_source["actor"].lower()
    ):
        _fail("native wrapper capture/finalization authority drifted")

    wrapper_auth = native.get("authenticodeVerification")
    if (
        not isinstance(wrapper_auth, dict)
        or set(wrapper_auth) != NATIVE_AUTHENTICODE_BINDING_KEYS
        or wrapper_auth.get("path") != AUTHENTICODE_RECEIPT_PATH
        or wrapper_auth.get("sha256") != hashlib.sha256(authenticode_bytes).hexdigest()
        or wrapper_auth.get("sizeBytes") != len(authenticode_bytes)
    ):
        _fail("native wrapper Authenticode reference drifted")
    _sha256(wrapper_auth.get("signerCertificateSha256"), label="native signer certificate")
    _sha256(wrapper_auth.get("signerSpkiSha256"), label="native signer SPKI")
    _timestamp(wrapper_auth.get("timestampUtc"), label="native Authenticode timestamp")

    if (
        set(finalization) != NATIVE_FINALIZATION_V2_KEYS
        or finalization.get("contractName") != FINALIZATION_CONTRACT
        or type(finalization.get("contractVersion")) is not int
        or finalization.get("contractVersion") != 2
        or finalization.get("status") != "passed"
        or finalization.get("humanReviewConfirmed") is not True
        or finalization.get("reviewerWasCaptureActor") is not False
        or finalization.get("captureInventorySha256")
        != native.get("captureInventorySha256")
        or finalization.get("captureSource") != capture_source
        or finalization.get("finalizationSource") != finalization_source
        or finalization.get("reviewer") != finalization_source["actor"]
    ):
        _fail("native finalization v2 contract or authority drifted")
    _timestamp(finalization.get("generatedAt"), label="native finalization generatedAt")
    raw_auth = finalization.get("authenticodeVerification")
    if (
        not isinstance(raw_auth, dict)
        or set(raw_auth) != NATIVE_AUTHENTICODE_BINDING_KEYS
        or raw_auth.get("path") != NATIVE_AUTHENTICODE_SOURCE_PATH
        or any(
            raw_auth.get(key) != wrapper_auth.get(key)
            for key in NATIVE_AUTHENTICODE_BINDING_KEYS - {"path"}
        )
    ):
        _fail("native finalization Authenticode binding drifted")

    proofs = finalization.get("proofs")
    if (
        not isinstance(proofs, list)
        or len(proofs) != 1
        or not isinstance(proofs[0], dict)
        or set(proofs[0]) != {"headId", "path", "sha256"}
        or proofs[0].get("headId") != "avalonia"
        or proofs[0].get("path") != NATIVE_VISUAL_FILE
        or SHA256_RE.fullmatch(str(proofs[0].get("sha256") or "")) is None
    ):
        _fail("native finalization visual proof binding drifted")
    raw_scope = finalization.get("scopeApproval")
    wrapper_scope = native.get("scopeApproval")
    if (
        not isinstance(raw_scope, dict)
        or set(raw_scope) != {"approver", "path", "scopeDecisionSha256", "sha256"}
        or not isinstance(wrapper_scope, dict)
        or set(wrapper_scope)
        != {"approver", "path", "payload", "scopeDecisionSha256", "sha256"}
        or any(wrapper_scope.get(key) != raw_scope.get(key) for key in raw_scope)
        or wrapper_scope.get("payload") != approval
        or raw_scope.get("path")
        != "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json"
        or raw_scope.get("approver") != finalization_source["actor"]
        or raw_scope.get("sha256") != hashlib.sha256(approval_bytes).hexdigest()
        or raw_scope.get("scopeDecisionSha256")
        != scope_payload.get("scopeDecisionSha256")
    ):
        _fail("native finalization scope approval binding drifted")

    provenance = native.get("candidateProvenance")
    provenance_candidate = provenance.get("candidate") if isinstance(provenance, dict) else None
    registry_prepare_sha = _canonical_sha256(scope_payload.get("registryPrepare"))
    if (
        not isinstance(provenance, dict)
        or not isinstance(provenance_candidate, dict)
        or provenance.get("registryPrepareSha256") != registry_prepare_sha
        or provenance_candidate.get("registryPrepareSha256") != registry_prepare_sha
        or not isinstance(provenance.get("publicationScope"), dict)
        or provenance["publicationScope"].get("registryPrepareSha256")
        != registry_prepare_sha
        or provenance_candidate != native_package.get("candidate")
    ):
        _fail("native wrapper candidate provenance Registry PREPARE binding drifted")
    candidate_actor = provenance_candidate.get("actor")
    if set(visual) != NATIVE_PORTABLE_VISUAL_KEYS:
        _fail("portable Windows visual proof property set drifted")
    visual_review = visual.get("review")
    visual_actor = (
        visual_review.get("authenticatedReviewer")
        if isinstance(visual_review, dict)
        else None
    )
    if (
        not isinstance(candidate_actor, str)
        or GITHUB_LOGIN_RE.fullmatch(candidate_actor) is None
        or not isinstance(visual_actor, str)
        or GITHUB_LOGIN_RE.fullmatch(visual_actor) is None
        or native.get("visualProofSha256")
        != {"avalonia": hashlib.sha256(visual_bytes).hexdigest()}
        or native.get("visualReviewers") != {"avalonia": visual_actor}
        or visual.get("contractName") != VISUAL_PROOF_CONTRACT
        or type(visual.get("contractVersion")) is not int
        or visual.get("contractVersion") != 1
        or visual.get("status") != "passed"
        or visual.get("version") != candidate_version
        or visual.get("releaseVersion") != candidate_version
        or visual.get("channel") != "preview"
        or visual.get("channelId") != "preview"
        or visual.get("platform") != "windows"
        or visual.get("head") != "avalonia"
        or visual.get("headId") != "avalonia"
        or visual.get("rid") != RID
        or visual.get("artifactFileName") != installer.get("fileName")
        or visual.get("artifactDigest") != f"sha256:{installer.get('sha256')}"
        or visual_actor != finalization_source["actor"]
        or visual.get("authenticodeVerification") != wrapper_auth
        or visual.get("finalizationBinding") != finalization_source
    ):
        _fail("native wrapper visual/candidate authority binding drifted")

    _timestamp(visual.get("generatedAt"), label="portable visual proof generatedAt")
    checks = visual.get("checks")
    if checks != {"capture_mode": "interactive", "human_review_confirmed": True}:
        _fail("portable Windows visual proof checks drifted")
    for review_name in ("readabilityReview", "contrastReview", "clippingReview"):
        if visual.get(review_name) != {
            "status": "passed",
            "reviewer": visual_actor,
        }:
            _fail(f"portable Windows visual proof {review_name} drifted")
    if visual_review != {
        "allowlistSource": "repository variable plus protected environment",
        "authenticatedReviewer": visual_actor,
        "captureActor": capture_source["actor"],
        "explicitConfirmations": {
            "clipping": "passed",
            "contrast": "passed",
            "readability": "passed",
        },
    }:
        _fail("portable Windows visual proof review provenance drifted")
    expected_capture_binding = {
        key: capture_source[key]
        for key in (
            "repository",
            "workflow",
            "runId",
            "runAttempt",
            "ref",
            "sha",
            "artifactName",
        )
    }
    expected_capture_binding["inventorySha256"] = native["captureInventorySha256"]
    if visual.get("captureBinding") != expected_capture_binding:
        _fail("portable Windows visual proof capture binding drifted")
    screenshots = visual.get("screenshots")
    if not isinstance(screenshots, list) or len(screenshots) != 2:
        _fail("portable Windows visual proof screenshot set drifted")
    screenshot_digests: set[str] = set()
    raw_visuals = native_package.get("visualProofs")
    raw_visual = raw_visuals.get("avalonia") if isinstance(raw_visuals, dict) else None
    raw_screenshots = raw_visual.get("screenshots") if isinstance(raw_visual, dict) else None
    if not isinstance(raw_screenshots, list) or len(raw_screenshots) != 2:
        _fail("raw Windows visual proof screenshot set drifted")
    for screenshot, role in zip(screenshots, ("progress", "completion"), strict=True):
        expected_path = (
            f"proof/windows-native/screenshots/"
            f"windows-installer-avalonia-{RID}-{role}.png"
        )
        if (
            not isinstance(screenshot, dict)
            or set(screenshot) != {"path", "role", "sha256"}
            or screenshot.get("role") != role
            or screenshot.get("path") != expected_path
            or not isinstance(raw_screenshots[0 if role == "progress" else 1], dict)
            or raw_screenshots[0 if role == "progress" else 1].get("role") != role
            or raw_screenshots[0 if role == "progress" else 1].get("sha256")
            != screenshot.get("sha256")
        ):
            _fail("portable Windows visual proof screenshot binding drifted")
        digest = _sha256(
            screenshot.get("sha256"),
            label=f"portable Windows visual proof {role} screenshot",
        )
        if digest in screenshot_digests:
            _fail("portable Windows visual proof reuses screenshot bytes")
        screenshot_digests.add(digest)
    return candidate_actor, capture_source["actor"], visual_actor


def _validate_final_publication_scope(
    stage_root: Path,
    scope_payload: dict[str, Any],
    scope_bytes: bytes,
    *,
    candidate: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    canonical_bytes: bytes,
    compatibility_bytes: bytes,
    canonical_scope: dict[str, Any],
    native_package: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    if (
        set(scope_payload) != PUBLICATION_SCOPE_KEYS
        or scope_payload.get("contractName") != PUBLICATION_SCOPE_CONTRACT
        or type(scope_payload.get("contractVersion")) is not int
        or scope_payload.get("contractVersion") != 2
        or scope_payload.get("status") != "validated"
        or scope_payload.get("approvalIndependent") is not True
        or scope_payload.get("authenticodeRequired") is not True
        or scope_payload.get("publicationEligible") is not False
        or scope_payload.get("registryFinalizeEligible") is not True
        or scope_payload.get("uploadAuthorized") is not False
        or scope_payload.get("deployAuthorized") is not False
    ):
        _fail("final UI publication scope is not an exact fail-closed v2 decision")
    release = scope_payload.get("release")
    if release != {"channel": "preview", "version": candidate["version"]}:
        _fail("final UI publication scope release identity drifted")
    macos_soak = scope_payload.get("macosSoak")
    if not isinstance(macos_soak, dict) or macos_soak.get("required") is not False:
        _fail("final UI publication scope does not keep macOS soak nonblocking")
    decision = scope_payload.get("scopeDecision")
    if not isinstance(decision, dict):
        _fail("final UI publication scope decision binding drifted")
    delta = _scope_tuples(
        scope_payload.get("publicationDeltaTuples"), label="publication delta"
    )
    if [
        (row["head"], row["platform"], row["rid"], row["artifactRole"])
        for row in delta
    ] != [
        ("avalonia", "windows", RID, "installer"),
        ("avalonia", "windows", RID, "payload"),
    ]:
        _fail("final UI publication scope is not the exact Windows installer/payload pair")
    expected_delta = canonical_scope["artifacts"]["avalonia"]
    for row in delta:
        expected = expected_delta[row["artifactRole"]]
        if any(row[key] != expected[key] for key in ("path", "fileName", "sha256", "sizeBytes")):
            _fail("final UI publication delta differs from the upload manifest")
    retained = _scope_tuples(
        scope_payload.get("retainedTuples"),
        label="retained incumbent shelf",
        allow_empty=True,
    )
    non_published = _scope_tuples(
        scope_payload.get("nonPublishedEvidenceTuples"),
        label="non-published evidence",
        allow_evidence_path=True,
    )
    build = _scope_tuples(
        scope_payload.get("buildEvidenceTuples"),
        label="build evidence",
        allow_evidence_path=True,
    )
    if (
        len(non_published) != 1
        or (
            non_published[0]["platform"],
            non_published[0]["rid"],
            non_published[0]["artifactRole"],
        )
        != ("linux", "linux-x64", "installer")
        or non_published[0]["path"]
        != f"release-evidence/non-published/files/{non_published[0]['fileName']}"
        or any(row["platform"] == "windows" for row in retained)
        or {_tuple_identity(row) for row in build}
        != {
            *(_tuple_identity(row) for row in delta),
            *(_tuple_identity(row) for row in non_published),
        }
    ):
        _fail("final UI publication scope build/retained/evidence partition drifted")
    post = _scope_tuples(
        scope_payload.get("postPublicationShelfTuples"), label="post-publication shelf"
    )
    expected_post = sorted(
        [*retained, *delta],
        key=lambda row: (
            row["head"],
            row["platform"],
            row["rid"],
            row["artifactRole"],
            row["fileName"],
        ),
    )
    if post != expected_post:
        _fail("final UI post-publication shelf is not retained union Windows delta")
    expected_upload_paths = {
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        *(row["path"] for row in post),
    }
    candidate_by_path = {row["path"]: row for row in candidate_rows}
    if set(candidate_by_path) != expected_upload_paths:
        _fail("candidate upload inventory differs from the final UI Run upload allowlist")
    full_inventory = _scope_inventory(
        scope_payload.get("fullShelfInventory"), label="final UI full shelf inventory"
    )
    full_by_path = {row["path"]: row for row in full_inventory}
    for path, row in candidate_by_path.items():
        full = full_by_path.get(path)
        if full is None or any(full[key] != row[key] for key in ("sha256", "sizeBytes")):
            _fail("candidate upload byte differs from the final UI full shelf inventory")
    expected_decision = {
        "channel": "preview",
        "fullShelfCompatibilityManifestSha256": hashlib.sha256(
            compatibility_bytes
        ).hexdigest(),
        "fullShelfInventorySha256": _canonical_sha256(full_inventory),
        "fullShelfManifestSha256": hashlib.sha256(canonical_bytes).hexdigest(),
        "incumbentSnapshotSha256": scope_payload.get("incumbentSnapshotSha256"),
        "publicationDeltaSha256": _canonical_sha256(delta),
        "releaseVersion": candidate["version"],
        "scope": "windows_only",
    }
    if decision != expected_decision:
        _fail("final UI publication scope decision binding drifted")
    if (
        scope_payload.get("fullShelfInventorySha256") != _canonical_sha256(full_inventory)
        or scope_payload.get("fullShelfManifestSha256")
        != hashlib.sha256(canonical_bytes).hexdigest()
        or scope_payload.get("fullShelfCompatibilityManifestSha256")
        != hashlib.sha256(compatibility_bytes).hexdigest()
        or decision.get("fullShelfManifestSha256")
        != scope_payload["fullShelfManifestSha256"]
        or decision.get("fullShelfCompatibilityManifestSha256")
        != scope_payload["fullShelfCompatibilityManifestSha256"]
        or decision.get("fullShelfInventorySha256")
        != scope_payload["fullShelfInventorySha256"]
        or scope_payload.get("scopeDecisionSha256") != _canonical_sha256(decision)
    ):
        _fail("final UI publication scope shelf digest graph drifted")

    signing_binding = scope_payload.get("signingReceipt")
    if not isinstance(signing_binding, dict) or set(signing_binding) != {"path", "sha256"}:
        _fail("final UI signing receipt binding drifted")
    signing_path, signing, signing_bytes = _stage_json_digest_binding(
        stage_root,
        relative_path=signing_binding.get("path"),
        expected_sha256=signing_binding.get("sha256"),
        label="final Windows signing receipt",
    )
    if signing_binding["sha256"] != scope_payload.get("signingReceiptSha256"):
        _fail("final UI signing receipt digest aliases disagree")
    _validate_signing_receipt_v2(signing, version=candidate["version"], delta=delta)

    native_path, native, native_bytes = _stage_json_digest_binding(
        stage_root,
        relative_path=NATIVE_WRAPPER_FILE,
        expected_sha256=scope_payload.get("nativeEvidenceSha256"),
        label="final native Windows evidence",
    )
    if native.get("status") not in {"pass", "passed"} or not {
        row["sha256"] for row in delta
    }.issubset(_sha_values(native)):
        _fail("final native Windows evidence does not bind the Windows delta")
    native_composite = scope_payload.get("nativeEvidenceComposite")
    finalization_reference = (
        native_composite.get("nativeFinalization")
        if isinstance(native_composite, dict)
        else None
    )
    if (
        not isinstance(native_composite, dict)
        or set(native_composite) != NATIVE_COMPOSITE_KEYS
        or not isinstance(finalization_reference, dict)
        or set(finalization_reference) != NATIVE_CONTRACT_REFERENCE_KEYS
        or finalization_reference.get("path") != NATIVE_FINALIZATION_V2_FILE
    ):
        _fail("final UI native evidence composite is malformed")
    finalization_path, finalization, finalization_bytes = _stage_json_digest_binding(
        stage_root,
        relative_path=NATIVE_FINALIZATION_V2_FILE,
        expected_sha256=finalization_reference.get("sha256"),
        label="root native Windows finalization v2",
    )
    authenticode_binding = native.get("authenticodeVerification")
    if not isinstance(authenticode_binding, dict) or set(authenticode_binding) != {
        "path",
        "sha256",
        "signerCertificateSha256",
        "signerSpkiSha256",
        "sizeBytes",
        "timestampUtc",
    }:
        _fail("final native Windows Authenticode binding drifted")
    auth_path, authenticode, authenticode_bytes = _stage_json_digest_binding(
        stage_root,
        relative_path=authenticode_binding.get("path"),
        expected_sha256=authenticode_binding.get("sha256"),
        label="independent Authenticode verification",
    )
    if (
        auth_path != AUTHENTICODE_RECEIPT_PATH
        or authenticode_binding.get("sizeBytes") != len(authenticode_bytes)
        or authenticode_binding.get("sha256")
        != scope_payload.get("authenticodeVerificationSha256")
    ):
        _fail("final UI Authenticode verification digest drifted")
    installer = next(row for row in delta if row["artifactRole"] == "installer")
    _validate_authenticode_receipt(authenticode, installer=installer, native=native)

    approval_binding = scope_payload.get("approval")
    if not isinstance(approval_binding, dict) or set(approval_binding) != {
        "approver",
        "path",
        "sha256",
    }:
        _fail("final UI approval binding drifted")
    approver = approval_binding.get("approver")
    if not isinstance(approver, str) or GITHUB_LOGIN_RE.fullmatch(approver) is None:
        _fail("final UI approver identity is invalid")
    approval_path, approval, approval_bytes = _stage_json_digest_binding(
        stage_root,
        relative_path=approval_binding.get("path"),
        expected_sha256=approval_binding.get("sha256"),
        label="independent publication scope approval",
    )
    if (
        approval.get("contractName")
        != "chummer6-ui.preview-nightly-windows-publication-approval"
        or type(approval.get("contractVersion")) is not int
        or approval.get("contractVersion") != 2
        or approval.get("status") != "approved"
        or approval.get("approver") != approver
        or approval.get("signingReceiptSha256")
        != scope_payload.get("signingReceiptSha256")
        or approval.get("scopeDecisionSha256")
        != scope_payload.get("scopeDecisionSha256")
        or approval.get("authenticodeVerificationSha256")
        != authenticode_binding["sha256"]
    ):
        _fail("independent publication scope approval digest graph drifted")
    visual_files: list[tuple[str, bytes]] = []
    visual_digests = scope_payload.get("visualApprovalSha256")
    if not isinstance(visual_digests, list) or len(visual_digests) != 1:
        _fail("final UI scope must bind exactly one Avalonia Windows visual approval")
    visual_path = f"WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-{RID}.generated.json"
    visual_path, visual, visual_bytes = _stage_json_digest_binding(
        stage_root,
        relative_path=visual_path,
        expected_sha256=visual_digests[0],
        label="final Windows visual approval",
    )
    review = visual.get("review")
    visual_actor = review.get("authenticatedReviewer") if isinstance(review, dict) else None
    candidate_actor, capture_actor, exact_visual_actor = _validate_final_native_composite(
        scope_payload=scope_payload,
        native=native,
        native_bytes=native_bytes,
        finalization=finalization,
        finalization_bytes=finalization_bytes,
        authenticode_bytes=authenticode_bytes,
        approval=approval,
        approval_bytes=approval_bytes,
        visual=visual,
        visual_bytes=visual_bytes,
        candidate_version=candidate["version"],
        installer=installer,
        native_package=native_package,
    )
    if (
        visual.get("status") not in {"pass", "passed"}
        or installer["sha256"] not in _sha_values(visual)
        or not isinstance(candidate_actor, str)
        or GITHUB_LOGIN_RE.fullmatch(candidate_actor) is None
        or not isinstance(capture_actor, str)
        or GITHUB_LOGIN_RE.fullmatch(capture_actor) is None
        or not isinstance(visual_actor, str)
        or GITHUB_LOGIN_RE.fullmatch(visual_actor) is None
        or visual_actor != exact_visual_actor
        or visual_actor.lower() != approver.lower()
        or candidate_actor.lower() == approver.lower()
        or capture_actor.lower() == approver.lower()
    ):
        _fail(
            "final UI evidence lacks the independent producer/capture/"
            "authenticated-review owner actor policy"
        )
    visual_files.append((visual_path, visual_bytes))
    evidence_files = [
        (PUBLICATION_SCOPE_FILE, scope_bytes),
        (signing_path, signing_bytes),
        (native_path, native_bytes),
        (finalization_path, finalization_bytes),
        (auth_path, authenticode_bytes),
        (approval_path, approval_bytes),
        *visual_files,
    ]
    evidence = {
        "status": "passed",
        "exactIncomingDesktopScope": EXACT_SCOPE_TUPLE,
        "publicationScopeSha256": hashlib.sha256(scope_bytes).hexdigest(),
        "scopeDecisionSha256": scope_payload["scopeDecisionSha256"],
        "signingReceiptSha256": hashlib.sha256(signing_bytes).hexdigest(),
        "nativeEvidenceSha256": hashlib.sha256(native_bytes).hexdigest(),
        "authenticodeVerificationSha256": hashlib.sha256(
            authenticode_bytes
        ).hexdigest(),
        "approvalSha256": hashlib.sha256(approval_bytes).hexdigest(),
        "visualApprovalSha256": [hashlib.sha256(visual_bytes).hexdigest()],
        "actors": {
            "candidateProducer": candidate_actor,
            "nativeCapture": capture_actor,
            "visualReviewer": visual_actor,
            "scopeApprover": approver,
        },
    }
    return evidence, evidence_files


def _stage_bytes_reference(
    root: Path,
    value: object,
    *,
    expected_path: str,
    label: str,
) -> tuple[str, bytes]:
    reference = _byte_reference(
        value,
        label=label,
        expected_path=expected_path,
    )
    candidate = root.joinpath(*expected_path.split("/"))
    try:
        candidate.parent.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise CandidateAuthorityBlocked(
            f"{label} escapes the publication stage root"
        ) from exc
    candidate = _plain_file(candidate, label=label, maximum_bytes=MAX_JSON_BYTES)
    raw = candidate.read_bytes()
    if reference != {
        "path": expected_path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
    }:
        _fail(f"{label} differs from exact held bytes")
    return expected_path, raw


def _stage_opaque_bytes_reference(
    root: Path,
    value: object,
    *,
    expected_path: str,
    label: str,
) -> tuple[str, bytes]:
    if not isinstance(value, dict) or set(value) != {"sha256", "sizeBytes"}:
        _fail(f"{label} opaque binding property set drifted")
    digest = _sha256(value.get("sha256"), label=f"{label} sha256")
    size = _positive_int(value.get("sizeBytes"), label=f"{label} sizeBytes")
    candidate = root.joinpath(*expected_path.split("/"))
    try:
        candidate.parent.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise CandidateAuthorityBlocked(
            f"{label} escapes the publication stage root"
        ) from exc
    candidate = _plain_file(candidate, label=label, maximum_bytes=MAX_JSON_BYTES)
    raw = candidate.read_bytes()
    if digest != hashlib.sha256(raw).hexdigest() or size != len(raw):
        _fail(f"{label} differs from exact held bytes")
    return expected_path, raw


def _validate_unsigned_provenance_documents(
    held_files: list[tuple[str, bytes]],
    *,
    source_sha: str,
    release_version: str,
) -> None:
    held = dict(held_files)

    def document(name: str, label: str) -> tuple[dict[str, Any], bytes]:
        path = UNSIGNED_PROVENANCE_PATHS[name]
        raw = held.get(path)
        if raw is None:
            _fail(f"{label} is absent from unsigned UI custody")
        return _strict_json_bytes(raw, label=label), raw

    package_lock, package_lock_raw = document(
        "packagePlaneLock", "unsigned package-plane lock"
    )
    if (
        set(package_lock)
        != {
            "approvedPackageSources",
            "canonicalOwnerFeed",
            "consumer",
            "contractName",
            "contractVersion",
            "currentOwnerContractFeed",
            "externalPackages",
            "owners",
            "packages",
            "sdkArchive",
            "sdkVersion",
        }
        or package_lock.get("contractName")
        != "chummer6-ui.fresh-package-plane-lock"
        or type(package_lock.get("contractVersion")) is not int
        or package_lock.get("contractVersion") != 8
        or package_lock.get("approvedPackageSources")
        != ["same-run-local-feed"]
        or not isinstance(package_lock.get("consumer"), dict)
        or set(package_lock["consumer"])
        != {"buildProjects", "sourceFiles", "testProjects"}
        or not isinstance(package_lock.get("externalPackages"), list)
        or not isinstance(package_lock.get("packages"), list)
        or not isinstance(package_lock.get("sdkArchive"), dict)
    ):
        _fail("unsigned package-plane lock contract or source policy drifted")

    package_receipt, _package_receipt_raw = document(
        "packagePlaneReceipt", "unsigned package-plane receipt"
    )
    if (
        package_receipt.get("contractName")
        != "chummer6-ui.fresh-package-plane-verification"
        or type(package_receipt.get("contractVersion")) is not int
        or package_receipt.get("contractVersion") != 8
        or package_receipt.get("status") != "passed"
        or package_receipt.get("consumerCommit") != source_sha
        or package_receipt.get("mode") != "integration"
        or package_receipt.get("localCompatibilityTree") is not False
        or package_receipt.get("packageCacheWasFresh") is not True
        or package_receipt.get("stubPackagesAllowed") is not False
        or package_receipt.get("packageSources") != ["same-run-local-feed"]
    ):
        _fail("unsigned package-plane receipt authority drifted")

    retained, retained_raw = document(
        "retainedManifest", "unsigned retained-Windows manifest"
    )
    expected_release = {"channel": "preview", "version": release_version}
    publish = retained.get("publish")
    release_eligibility = retained.get("releaseEligibility")
    if (
        retained.get("contractName")
        != "chummer6-ui.retained-windows-publish-closure"
        or type(retained.get("contractVersion")) is not int
        or retained.get("contractVersion") != 2
        or retained.get("status") != "passed"
        or retained.get("consumerCommit") != source_sha
        or retained.get("release") != expected_release
        or retained.get("atomicallyRetained") is not True
        or retained.get("authoritative") is not True
        or retained.get("deterministicRepacking") is not False
        or not isinstance(release_eligibility, dict)
        or release_eligibility.get("eligible") is not False
        or not isinstance(publish, dict)
        or publish.get("status") != "passed"
        or publish.get("releaseChannel") != "preview"
        or publish.get("releaseVersion") != release_version
    ):
        _fail("unsigned retained-Windows manifest authority drifted")

    def exact_byte_binding(
        value: object,
        raw: bytes,
        *,
        path: str,
        label: str,
    ) -> None:
        expected = {
            "path": path,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sizeBytes": len(raw),
        }
        if value != expected:
            _fail(f"{label} differs from exact held bytes")

    exact_byte_binding(
        package_receipt.get("consumerPackagePlaneLock"),
        package_lock_raw,
        path=UNSIGNED_PACKAGE_PLANE_LOCK_BINDING_PATH,
        label="unsigned package receipt lock binding",
    )
    exact_byte_binding(
        retained.get("packagePlaneLock"),
        package_lock_raw,
        path=UNSIGNED_PACKAGE_PLANE_LOCK_BINDING_PATH,
        label="unsigned retained manifest lock binding",
    )
    pointer = package_receipt.get("retainedWindowsBundle")
    if (
        not isinstance(pointer, dict)
        or set(pointer) != UNSIGNED_RETAINED_POINTER_KEYS
        or pointer.get("contractName")
        != "chummer6-ui.retained-windows-publish-closure-pointer"
        or type(pointer.get("contractVersion")) is not int
        or pointer.get("contractVersion") != 2
        or pointer.get("status") != "passed"
        or pointer.get("consumerCommit") != source_sha
        or pointer.get("release") != expected_release
        or pointer.get("atomicallyRetained") is not True
        or pointer.get("authority") is not False
        or pointer.get("manifestIsAuthoritative") is not True
        or type(pointer.get("bundleInventoryCount")) is not int
        or pointer["bundleInventoryCount"] < 1
        or not isinstance(pointer.get("bundleInventorySha256"), str)
        or SHA256_RE.fullmatch(pointer["bundleInventorySha256"]) is None
    ):
        _fail("unsigned retained bundle pointer authority drifted")
    pointer_target = _validate_absolute_posix_path(
        pointer.get("targetPath"),
        label="unsigned retained bundle pointer target path",
    )
    retained_target = _validate_absolute_posix_path(
        retained.get("targetPath"),
        label="unsigned retained manifest target path",
    )
    if pointer_target != retained_target:
        _fail("unsigned retained bundle target path drifted")
    exact_byte_binding(
        pointer.get("manifest"),
        retained_raw,
        path=f"{pointer_target}/manifest.json",
        label="unsigned retained bundle pointer manifest binding",
    )

    native, _native_raw = document(
        "nativeToolchainLock", "unsigned native toolchain lock"
    )
    container_image = native.get("container_image")
    snapshot = native.get("debian_snapshot")
    packages = native.get("packages")
    if (
        set(native)
        != {
            "container_image",
            "contract_name",
            "debian_snapshot",
            "packages",
            "platform",
            "schema_version",
        }
        or native.get("contract_name")
        != "chummer6-ui.windows_native_bootstrap_toolchain_lock"
        or type(native.get("schema_version")) is not int
        or native.get("schema_version") != 1
        or native.get("platform") != {"architecture": "amd64", "os": "linux"}
        or not isinstance(container_image, dict)
        or set(container_image)
        != {"index_digest", "platform_manifest_digest", "reference"}
        or not isinstance(snapshot, dict)
        or set(snapshot)
        != {
            "archive_base_url",
            "component",
            "include_recommends",
            "install_roots",
            "metadata_url",
            "suite",
            "timestamp",
        }
        or snapshot.get("install_roots") != ["nsis", "p7zip-full"]
        or snapshot.get("include_recommends") is not False
        or not isinstance(packages, list)
        or not packages
    ):
        _fail("unsigned native toolchain lock contract drifted")
    prefixed_sha256 = re.compile(r"^sha256:[0-9a-f]{64}$")
    if (
        prefixed_sha256.fullmatch(str(container_image.get("index_digest") or ""))
        is None
        or prefixed_sha256.fullmatch(
            str(container_image.get("platform_manifest_digest") or "")
        )
        is None
        or not isinstance(container_image.get("reference"), str)
        or "@sha256:" not in container_image["reference"]
    ):
        _fail("unsigned native toolchain image identity drifted")
    package_keys = {
        "architecture",
        "dependencies",
        "name",
        "path",
        "sha256",
        "size",
        "url",
        "version",
    }
    for index, package in enumerate(packages):
        if (
            not isinstance(package, dict)
            or set(package) != package_keys
            or SHA256_RE.fullmatch(str(package.get("sha256") or "")) is None
            or isinstance(package.get("size"), bool)
            or not isinstance(package.get("size"), int)
            or package["size"] < 1
            or not isinstance(package.get("dependencies"), list)
            or any(
                not isinstance(package.get(key), str) or not package[key]
                for key in ("architecture", "name", "path", "url", "version")
            )
        ):
            _fail(f"unsigned native toolchain package {index} drifted")


def _unsigned_retained_rows(
    value: object,
    *,
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 100_000:
        _fail(f"{label} must be a bounded inventory")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {
            "mode",
            "path",
            "retentionKind",
            "sha256",
            "sizeBytes",
        }:
            _fail(f"{label} row {index} drifted")
        mode = raw.get("mode")
        retention_kind = raw.get("retentionKind")
        if (
            isinstance(mode, bool)
            or not isinstance(mode, int)
            or not 0 <= mode <= 0o7777
            or retention_kind not in {"managed_artifact", "ancillary"}
        ):
            _fail(f"{label} row {index} policy drifted")
        rows.append(
            {
                "mode": mode,
                "path": _validate_relative_path(
                    raw.get("path"), label=f"{label} path"
                ),
                "retentionKind": retention_kind,
                "sha256": _sha256(raw.get("sha256"), label=f"{label} sha256"),
                "sizeBytes": _positive_int(
                    raw.get("sizeBytes"),
                    label=f"{label} sizeBytes",
                    allow_zero=True,
                ),
            }
        )
    if rows != sorted(rows, key=lambda row: row["path"]) or len(
        {row["path"] for row in rows}
    ) != len(rows):
        _fail(f"{label} is not uniquely sorted")
    return rows


def _validate_unsigned_publication_scope_v3(
    stage_root: Path,
    candidate_file_modes: dict[str, int],
    scope_payload: dict[str, Any],
    scope_bytes: bytes,
    *,
    candidate: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    canonical_bytes: bytes,
    compatibility_bytes: bytes,
    canonical_scope: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    expected_scope_bytes = (
        json.dumps(scope_payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if (
        set(scope_payload) != UNSIGNED_PUBLICATION_SCOPE_KEYS
        or scope_payload.get("contractName") != UNSIGNED_PUBLICATION_SCOPE_CONTRACT
        or type(scope_payload.get("contractVersion")) is not int
        or scope_payload.get("contractVersion") != 3
        or scope_payload.get("status") != "prepared"
        or scope_payload.get("platformScope") != "windows_only"
        or scope_payload.get("crossRunBitReproducible") is not False
        or scope_payload.get("signature") != UNSIGNED_SIGNATURE_POLICY
        or any(
            scope_payload.get(key) is not False
            for key in (
                "publicationAuthorized",
                "uploadAuthorized",
                "deployAuthorized",
            )
        )
        or scope_bytes != expected_scope_bytes
    ):
        _fail("unsigned UI publication scope is not the exact inert v3 policy")
    if scope_payload.get("release") != {
        "channel": "preview",
        "version": candidate["version"],
    }:
        _fail("unsigned UI publication scope release identity drifted")
    source_sha = scope_payload.get("sourceSha")
    if not isinstance(source_sha, str) or COMMIT_RE.fullmatch(source_sha) is None:
        _fail("unsigned UI publication scope sourceSha is not an exact commit")

    publication_path, held_canonical = _stage_bytes_reference(
        stage_root,
        scope_payload.get("publicationManifest"),
        expected_path="RELEASE_CHANNEL.generated.json",
        label="unsigned publication manifest",
    )
    compatibility_path, held_compatibility = _stage_bytes_reference(
        stage_root,
        scope_payload.get("compatibilityManifest"),
        expected_path="releases.json",
        label="unsigned compatibility manifest",
    )
    if held_canonical != canonical_bytes or held_compatibility != compatibility_bytes:
        _fail("unsigned UI scope publication manifests differ from candidate custody")

    provenance = scope_payload.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != set(
        UNSIGNED_PROVENANCE_PATHS
    ):
        _fail("unsigned UI publication scope provenance property set drifted")
    held_files: list[tuple[str, bytes]] = [
        (UNSIGNED_PUBLICATION_SCOPE_FILE, scope_bytes),
        (publication_path, held_canonical),
        (compatibility_path, held_compatibility),
    ]
    for name, expected_path in UNSIGNED_PROVENANCE_PATHS.items():
        held_files.append(
            _stage_opaque_bytes_reference(
                stage_root,
                provenance.get(name),
                expected_path=expected_path,
                label=f"unsigned publication {name}",
            )
        )
    _validate_unsigned_provenance_documents(
        held_files,
        source_sha=source_sha,
        release_version=candidate["version"],
    )

    full_inventory = _scope_inventory(
        scope_payload.get("fullShelfInventory"),
        label="unsigned UI full shelf inventory",
    )
    if scope_payload.get("fullShelfInventorySha256") != _ui_compact_sha256(
        full_inventory
    ):
        _fail("unsigned UI full shelf inventory digest drifted")
    _sha256(
        scope_payload.get("incumbentInventorySha256"),
        label="unsigned UI incumbent inventory",
    )
    expected_full = [
        {
            "mode": row["mode"],
            "path": row["path"],
            "sha256": row["sha256"],
            "sizeBytes": row["sizeBytes"],
        }
        for row in full_inventory
    ]
    candidate_by_path = {row["path"]: row for row in candidate_rows}
    full_by_path = {row["path"]: row for row in expected_full}
    if set(full_by_path) != set(candidate_by_path) or any(
        {
            "path": row["path"],
            "sha256": row["sha256"],
            "sizeBytes": row["sizeBytes"],
        }
        != candidate_by_path[path]
        for path, row in full_by_path.items()
    ):
        _fail("unsigned UI full shelf inventory differs from candidate bytes")
    for path, row in full_by_path.items():
        if candidate_file_modes.get(path) != row["mode"]:
            _fail("unsigned UI full shelf inventory mode differs from candidate bytes")

    delta_value = scope_payload.get("freshDelta")
    if not isinstance(delta_value, list) or len(delta_value) != 2:
        _fail("unsigned UI fresh delta is not the exact Windows pair")
    expected_delta = canonical_scope["artifacts"]["avalonia"]
    delta: list[dict[str, Any]] = []
    for index, (scope_role, canonical_role) in enumerate(
        (("installer", "installer"), ("bootstrap_payload", "payload"))
    ):
        raw = delta_value[index]
        if not isinstance(raw, dict) or set(raw) != {
            "artifactRole",
            "fileName",
            "head",
            "mode",
            "path",
            "platform",
            "rid",
            "sha256",
            "sizeBytes",
        }:
            _fail("unsigned UI fresh delta row property set drifted")
        expected = expected_delta[canonical_role]
        full = full_by_path.get(expected["path"])
        if full is None:
            _fail("unsigned UI fresh delta is absent from the full inventory")
        exact = {
            "artifactRole": scope_role,
            "fileName": expected["fileName"],
            "head": "avalonia",
            "mode": full["mode"],
            "path": expected["path"],
            "platform": "windows",
            "rid": RID,
            "sha256": expected["sha256"],
            "sizeBytes": expected["sizeBytes"],
        }
        if raw != exact:
            _fail("unsigned UI fresh delta differs from candidate Windows bytes")
        delta.append(exact)
    if [row["fileName"] for row in delta] != [
        "chummer-avalonia-win-x64-installer.exe",
        "chummer-avalonia-win-x64-payload.zip",
    ]:
        _fail("unsigned UI fresh delta filenames drifted")

    retained = _unsigned_retained_rows(
        scope_payload.get("retainedFromIncumbent"),
        label="unsigned UI retained incumbent inventory",
    )
    retained_by_path = {row["path"]: row for row in retained}
    reserved_paths = {
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        *(row["path"] for row in delta),
    }
    if set(retained_by_path) & reserved_paths or set(full_by_path) != {
        *reserved_paths,
        *retained_by_path,
    }:
        _fail("unsigned UI retained/fresh/root inventory partition drifted")
    managed_paths = set(canonical_scope.get("manifestArtifactPaths", [])) - {
        row["path"] for row in delta
    }
    for path, row in retained_by_path.items():
        full = full_by_path[path]
        if any(full[key] != row[key] for key in ("mode", "sha256", "sizeBytes")):
            _fail("unsigned UI retained incumbent byte binding drifted")
        expected_kind = "managed_artifact" if path in managed_paths else "ancillary"
        if row["retentionKind"] != expected_kind:
            _fail("unsigned UI retained incumbent classification drifted")
    if not managed_paths.issubset(retained_by_path):
        _fail("unsigned UI scope omits a retained non-Windows manifest artifact")

    evidence = {
        "status": "passed",
        "exactIncomingDesktopScope": EXACT_SCOPE_TUPLE,
        "publicationScopeSha256": hashlib.sha256(scope_bytes).hexdigest(),
        "platformScope": "windows_only",
        "crossRunBitReproducible": False,
        "signaturePolicy": {
            "signatureStatus": "unsigned",
            "signingRequired": False,
            "unsignedReason": "preview_policy",
        },
        "sourceSha": source_sha,
        "incumbentInventorySha256": scope_payload["incumbentInventorySha256"],
        "fullShelfInventorySha256": scope_payload["fullShelfInventorySha256"],
        "retainedInventorySha256": _ui_compact_sha256(retained),
        "freshDeltaSha256": _ui_compact_sha256(delta),
        "provenance": provenance,
    }
    return evidence, held_files


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _registry_inventory(value: object, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 4096:
        _fail(f"{label} must be a bounded non-empty inventory")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {
            "mode",
            "path",
            "sha256",
            "sizeBytes",
        }:
            _fail(f"{label} row {index} drifted")
        mode = raw.get("mode")
        if not isinstance(mode, str) or re.fullmatch(r"[0-7]{4}", mode) is None:
            _fail(f"{label} row mode drifted")
        rows.append(
            {
                "mode": mode,
                "path": _validate_relative_path(raw.get("path"), label=f"{label} path"),
                "sha256": _sha256(raw.get("sha256"), label=f"{label} sha256"),
                "sizeBytes": _positive_int(
                    raw.get("sizeBytes"), label=f"{label} sizeBytes", allow_zero=True
                ),
            }
        )
    if rows != sorted(rows, key=lambda row: row["path"]) or len(
        {row["path"] for row in rows}
    ) != len(rows):
        _fail(f"{label} is not uniquely sorted")
    return rows


def _expect_reference(
    value: object,
    *,
    path: str,
    raw: bytes,
    label: str,
) -> dict[str, Any]:
    reference = _byte_reference(value, label=label, expected_path=path)
    expected = {
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
    }
    if reference != expected:
        _fail(f"{label} differs from exact held bytes")
    return reference


def _read_stage_input(
    stage_root: Path,
    value: object,
    *,
    expected_name: str,
    label: str,
    require_canonical: bool = True,
) -> tuple[str, dict[str, Any], bytes]:
    if not isinstance(value, str) or not value:
        _fail(f"{label} path is missing")
    path = _plain_file(Path(value), label=label, maximum_bytes=MAX_JSON_BYTES)
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(stage_root).as_posix()
    except ValueError as exc:
        raise CandidateAuthorityBlocked(f"{label} is outside the publication stage root") from exc
    if resolved.name != expected_name:
        _fail(f"{label} filename must be {expected_name}")
    payload, raw = _strict_json(resolved, label=label)
    if require_canonical and raw != _canonical_json_bytes(payload):
        _fail(f"{label} must be canonical compact JSON plus LF")
    return relative, payload, raw


def _validate_registry_prepare_binding_v2(
    value: object,
    *,
    candidate_receipt_raw: bytes,
    canonical_raw: bytes,
    compatibility_raw: bytes,
    candidate: dict[str, Any],
) -> None:
    expected_keys = {
        "candidateReceiptSha256",
        "composition",
        "contractName",
        "contractVersion",
        "deployAuthority",
        "finalizeAvailable",
        "finalizeReceipt",
        "inputRoots",
        "outputInventory",
        "outputInventorySha256",
        "projectionInputs",
        "publicationEligible",
        "registryCommit",
        "releaseUploadAuthority",
        "routeAuthority",
        "status",
        "wholeDirectoryVerified",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        _fail("final UI Registry PREPARE binding property set drifted")
    if (
        value.get("contractName") != "chummer6-ui.registry-preview-prepare-binding"
        or type(value.get("contractVersion")) is not int
        or value.get("contractVersion") != 1
        or value.get("status") != "review_required"
        or value.get("wholeDirectoryVerified") is not True
        or value.get("finalizeAvailable") is not True
        or value.get("finalizeReceipt") is not None
        or any(
            value.get(key) is not False
            for key in (
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
            )
        )
        or value.get("candidateReceiptSha256")
        != hashlib.sha256(candidate_receipt_raw).hexdigest()
        or value.get("projectionInputs") != candidate.get("registryProjectionInputs")
    ):
        _fail("final UI Registry PREPARE binding is not an exact fail-closed receipt")
    rows = _registry_inventory(value.get("outputInventory"), label="Registry PREPARE output")
    expected = sorted(
        [
            {
                "mode": "0644",
                "path": "RELEASE_CHANNEL.generated.json",
                "sha256": hashlib.sha256(canonical_raw).hexdigest(),
                "sizeBytes": len(canonical_raw),
            },
            {
                "mode": "0644",
                "path": "releases.json",
                "sha256": hashlib.sha256(compatibility_raw).hexdigest(),
                "sizeBytes": len(compatibility_raw),
            },
            {
                "mode": "0644",
                "path": REGISTRY_CANDIDATE_FILE,
                "sha256": hashlib.sha256(candidate_receipt_raw).hexdigest(),
                "sizeBytes": len(candidate_receipt_raw),
            },
        ],
        key=lambda row: row["path"],
    )
    if rows != expected or value.get("outputInventorySha256") != _canonical_sha256(rows):
        _fail("final UI Registry PREPARE output inventory differs from the exact triplet")


def _validate_registry_candidate_receipt(
    receipt: dict[str, Any],
    raw: bytes,
    *,
    canonical_raw: bytes,
    compatibility_raw: bytes,
    candidate_summary: dict[str, Any],
    scope: dict[str, Any],
) -> None:
    if (
        set(receipt) != REGISTRY_CANDIDATE_KEYS
        or receipt.get("contractName") != REGISTRY_CANDIDATE_CONTRACT
        or type(receipt.get("contractVersion")) is not int
        or receipt.get("contractVersion") != 1
        or receipt.get("channel") != "preview"
        or receipt.get("releaseVersion") != candidate_summary["version"]
        or receipt.get("publicationStatus") != "review_required"
        or receipt.get("deltaPlatforms") != ["windows"]
        or receipt.get("evidencePlatforms") != ["linux"]
        or any(
            receipt.get(key) is not False
            for key in (
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
            )
        )
    ):
        _fail("Registry PREPARE candidate receipt identity or authority drifted")
    _expect_reference(
        receipt.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="Registry candidate canonical manifest",
    )
    _expect_reference(
        receipt.get("compatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="Registry candidate compatibility manifest",
    )
    composition = receipt.get("compositionInputDocument")
    composition_reference = _byte_reference(
        receipt.get("compositionInput"), label="Registry candidate composition"
    )
    if not isinstance(composition, dict) or set(composition) != {
        "channel",
        "contractName",
        "contractVersion",
        "incumbentSnapshot",
        "nonPublishedEvidenceTupleSetSha256",
        "nonPublishedEvidenceTuples",
        "policy",
        "producerCommits",
        "publicationDeltaTupleSetSha256",
        "publicationDeltaTuples",
        "releaseVersion",
    }:
        _fail("Registry candidate embedded composition property set drifted")
    composition_raw = _canonical_json_bytes(composition)
    if (
        "/" in composition_reference["path"]
        or composition_reference["sha256"] != hashlib.sha256(composition_raw).hexdigest()
        or composition_reference["sizeBytes"] != len(composition_raw)
        or composition.get("contractName")
        != "chummer.registry.preview-publication-delta-composition"
        or type(composition.get("contractVersion")) is not int
        or composition.get("contractVersion") != 1
        or composition.get("channel") != "preview"
        or composition.get("releaseVersion") != candidate_summary["version"]
        or composition.get("policy")
        != {
            "allowIncumbentRemoval": False,
            "deltaPlatforms": ["windows"],
            "evidencePlatforms": ["linux"],
            "producerDeployAuthority": False,
            "producerReleaseUploadAuthority": False,
            "retainAllIncumbent": True,
            "scope": "windows_only",
        }
    ):
        _fail("Registry candidate embedded composition binding drifted")
    delta = _scope_tuples(
        composition.get("publicationDeltaTuples"), label="Registry composition delta"
    )
    evidence = _scope_tuples(
        composition.get("nonPublishedEvidenceTuples"),
        label="Registry composition evidence",
        allow_evidence_path=True,
    )
    if (
        [(row["platform"], row["rid"], row["artifactRole"]) for row in delta]
        != [
            ("windows", RID, "installer"),
            ("windows", RID, "payload"),
        ]
        or len(evidence) != 1
        or (
            evidence[0]["platform"],
            evidence[0]["rid"],
            evidence[0]["artifactRole"],
        )
        != ("linux", "linux-x64", "installer")
        or composition.get("publicationDeltaTupleSetSha256") != _canonical_sha256(delta)
        or composition.get("nonPublishedEvidenceTupleSetSha256")
        != _canonical_sha256(evidence)
    ):
        _fail("Registry candidate composition is not the exact Windows/Linux policy")
    incumbent = composition.get("incumbentSnapshot")
    if not isinstance(incumbent, dict):
        _fail("Registry candidate incumbent snapshot is missing")
    incumbent_tuples = _scope_tuples(
        incumbent.get("desktopTuples"), label="Registry incumbent tuples"
    )
    incumbent_inventory = _registry_inventory(
        incumbent.get("fullInventory"), label="Registry incumbent inventory"
    )
    held_incumbent = receipt.get("incumbentCanonicalManifestBytesBase64")
    try:
        held_incumbent_raw = base64.b64decode(held_incumbent, validate=True)
    except (TypeError, ValueError) as exc:
        raise CandidateAuthorityBlocked(
            "Registry candidate incumbent canonical bytes are not strict base64"
        ) from exc
    incumbent_canonical = _byte_reference(
        incumbent.get("canonicalManifest"),
        label="Registry incumbent canonical manifest",
        expected_path="RELEASE_CHANNEL.generated.json",
    )
    if (
        not held_incumbent_raw
        or incumbent_canonical["sha256"]
        != hashlib.sha256(held_incumbent_raw).hexdigest()
        or incumbent_canonical["sizeBytes"] != len(held_incumbent_raw)
        or incumbent.get("desktopTupleSetSha256") != _canonical_sha256(incumbent_tuples)
        or incumbent.get("fullInventorySha256") != _canonical_sha256(incumbent_inventory)
        or receipt.get("incumbentDesktopTupleSetSha256")
        != incumbent.get("desktopTupleSetSha256")
        or receipt.get("incumbentSnapshotSha256") != incumbent.get("snapshotSha256")
    ):
        _fail("Registry candidate incumbent snapshot digest graph drifted")
    full_inventory = _registry_inventory(
        receipt.get("fullShelfInventory"), label="Registry candidate full shelf inventory"
    )
    ui_inventory = scope.get("fullShelfInventory")
    expected_registry_inventory = [
        {
            "mode": f"{row['mode']:04o}",
            "path": row["path"],
            "sha256": row["sha256"],
            "sizeBytes": row["sizeBytes"],
        }
        for row in ui_inventory
    ] if isinstance(ui_inventory, list) else []
    if (
        full_inventory != expected_registry_inventory
        or receipt.get("fullShelfInventorySha256") != _canonical_sha256(full_inventory)
        or receipt.get("publicationDeltaTupleSetSha256") != _canonical_sha256(delta)
        or receipt.get("nonPublishedEvidenceTupleSetSha256")
        != _canonical_sha256(evidence)
        or receipt.get("postPublicationTupleSetSha256")
        != _canonical_sha256(scope.get("postPublicationShelfTuples"))
        or receipt.get("retainedTupleSetSha256")
        != _canonical_sha256(scope.get("retainedTuples"))
        or receipt.get("incumbentSnapshotSha256")
        != scope.get("incumbentSnapshotSha256")
    ):
        _fail("Registry candidate and final UI shelf digest graphs disagree")
    expected_retained_platforms = sorted(
        {row["platform"] for row in scope.get("retainedTuples", [])}
    )
    expected_shelf_platforms = sorted(
        {row["platform"] for row in scope.get("postPublicationShelfTuples", [])}
    )
    if (
        receipt.get("retainedPlatforms") != expected_retained_platforms
        or receipt.get("shelfPlatforms") != expected_shelf_platforms
    ):
        _fail("Registry candidate platform disposition drifted")
    projection = receipt.get("registryProjectionInputs")
    if not isinstance(projection, dict) or set(projection) != {
        "materializer",
        "releaseChannelMaterializer",
        "schema",
        "verifier",
    }:
        _fail("Registry candidate projection input property set drifted")
    expected_projection_paths = {
        "materializer": "scripts/materialize_preview_publication_delta.py",
        "releaseChannelMaterializer": "scripts/materialize_public_release_channel.py",
        "schema": "contracts/preview-publication-delta-v1.schema.json",
        "verifier": "scripts/verify_public_release_channel.py",
    }
    for key, path in expected_projection_paths.items():
        _byte_reference(projection.get(key), label=f"Registry projection {key}", expected_path=path)
    _validate_registry_prepare_binding_v2(
        scope.get("registryPrepare"),
        candidate_receipt_raw=raw,
        canonical_raw=canonical_raw,
        compatibility_raw=compatibility_raw,
        candidate=receipt,
    )


def _validate_dispositions(
    value: object,
    *,
    canonical: dict[str, Any],
    canonical_raw: bytes,
    candidate: dict[str, Any],
) -> None:
    if not isinstance(value, list) or not value or len(value) > 32:
        _fail("Registry authority dispositions are unbounded or empty")
    artifacts = canonical.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(value):
        _fail("Registry authority dispositions do not cover every public artifact")
    by_id: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            _fail("candidate canonical manifest artifact drifted")
        artifact_id = artifact.get("artifactId", artifact.get("id"))
        if not isinstance(artifact_id, str) or not artifact_id or artifact_id in by_id:
            _fail("candidate canonical artifact identity drifted")
        by_id[artifact_id] = artifact
    seen: set[str] = set()
    delta_count = 0
    for row in value:
        if not isinstance(row, dict) or set(row) != {
            "artifactId",
            "disposition",
            "head",
            "platform",
            "rid",
            "sha256",
            "sizeBytes",
            "sourceManifestSha256",
            "sourceReleaseVersion",
            "sourceSnapshotSha256",
        }:
            _fail("Registry authority disposition row property set drifted")
        artifact_id = row.get("artifactId")
        artifact = by_id.get(artifact_id) if isinstance(artifact_id, str) else None
        if artifact is None or artifact_id in seen:
            _fail("Registry authority disposition artifact identity drifted")
        seen.add(artifact_id)
        if any(
            row.get(key) != artifact.get(key)
            for key in ("head", "platform", "rid", "sha256", "sizeBytes")
        ):
            _fail("Registry authority disposition differs from candidate manifest")
        disposition = row.get("disposition")
        if disposition == "delta":
            delta_count += 1
            expected_source = (
                hashlib.sha256(canonical_raw).hexdigest(),
                candidate["releaseVersion"],
                candidate["fullShelfInventorySha256"],
            )
            if row.get("platform") != "windows" or row.get("rid") != RID:
                _fail("Registry authority delta disposition is not exact Windows")
        elif disposition == "retained_incumbent":
            expected_source = (
                artifact.get("sourceManifestSha256"),
                artifact.get("sourceReleaseVersion"),
                artifact.get("sourceSnapshotSha256"),
            )
            if row.get("platform") not in {"linux", "macos"}:
                _fail("Registry authority retained disposition is not non-Windows")
        else:
            _fail("Registry authority disposition is invalid")
        if (
            row.get("sourceManifestSha256"),
            row.get("sourceReleaseVersion"),
            row.get("sourceSnapshotSha256"),
        ) != expected_source:
            _fail("Registry authority disposition source lineage drifted")
    if seen != set(by_id) or delta_count != 1:
        _fail("Registry authority must cover every artifact with one Windows delta")


def _validate_registry_finalize_graph(
    authority: dict[str, Any],
    authority_raw: bytes,
    finalize: dict[str, Any],
    finalize_raw: bytes,
    *,
    registry_candidate: dict[str, Any],
    registry_candidate_raw: bytes,
    canonical: dict[str, Any],
    canonical_raw: bytes,
    compatibility_raw: bytes,
    scope: dict[str, Any],
    scope_raw: bytes,
    stage_evidence_files: list[tuple[str, bytes]],
) -> dict[str, Any]:
    if (
        set(authority) != REGISTRY_AUTHORITY_KEYS
        or authority.get("contractName") != REGISTRY_AUTHORITY_CONTRACT
        or type(authority.get("contractVersion")) is not int
        or authority.get("contractVersion") != 1
        or authority.get("channel") != "preview"
        or authority.get("releaseVersion") != registry_candidate["releaseVersion"]
        or authority.get("candidateImportAuthority") is not True
        or authority.get("candidateReviewAuthority") is not True
        or authority.get("deltaPlatforms") != ["windows"]
        or authority.get("evidencePlatforms") != ["linux"]
        or authority.get("scope") != "windows_only"
        or any(
            authority.get(key) is not False
            for key in (
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
            )
        )
    ):
        _fail("Registry FINALIZE authority identity or bounded authority drifted")
    _expect_reference(
        authority.get("candidateReceipt"),
        path=REGISTRY_CANDIDATE_FILE,
        raw=registry_candidate_raw,
        label="Registry authority candidate receipt",
    )
    _expect_reference(
        authority.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="Registry authority canonical manifest",
    )
    _expect_reference(
        authority.get("compatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="Registry authority compatibility manifest",
    )
    _expect_reference(
        authority.get("sourceScope"),
        path=PUBLICATION_SCOPE_FILE,
        raw=scope_raw,
        label="Registry authority source scope",
    )
    composition_raw = _canonical_json_bytes(registry_candidate["compositionInputDocument"])
    aliases = (
        "fullShelfInventorySha256",
        "incumbentSnapshotSha256",
        "nonPublishedEvidenceTupleSetSha256",
        "postPublicationTupleSetSha256",
        "publicationDeltaTupleSetSha256",
        "retainedPlatforms",
        "retainedTupleSetSha256",
        "shelfPlatforms",
    )
    if (
        authority.get("compositionInputSha256")
        != hashlib.sha256(composition_raw).hexdigest()
        or any(authority.get(key) != registry_candidate.get(key) for key in aliases)
    ):
        _fail("Registry FINALIZE authority digest aliases differ from PREPARE")
    _validate_dispositions(
        authority.get("dispositions"),
        canonical=canonical,
        canonical_raw=canonical_raw,
        candidate=registry_candidate,
    )
    evidence = authority.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {
        "approval",
        "nativeEvidence",
        "signingReceipt",
        "visualEvidence",
    }:
        _fail("Registry FINALIZE evidence property set drifted")
    stage_by_path = dict(stage_evidence_files)
    expected_paths = {
        "approval": scope["approval"]["path"],
        "nativeEvidence": "NATIVE_WINDOWS_EVIDENCE.generated.json",
        "signingReceipt": scope["signingReceipt"]["path"],
    }
    for key, path in expected_paths.items():
        raw = stage_by_path.get(path)
        if raw is None:
            _fail(f"Registry FINALIZE {key} is absent from finalized UI custody")
        _expect_reference(evidence.get(key), path=path, raw=raw, label=f"Registry evidence {key}")
    visual_paths = [
        f"WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-{RID}.generated.json"
    ]
    visuals = evidence.get("visualEvidence")
    if not isinstance(visuals, list) or len(visuals) != len(visual_paths):
        _fail("Registry FINALIZE visual evidence set drifted")
    for reference, path in zip(visuals, visual_paths, strict=True):
        raw = stage_by_path.get(path)
        if raw is None:
            _fail("Registry FINALIZE visual evidence is absent from finalized UI custody")
        _expect_reference(reference, path=path, raw=raw, label="Registry visual evidence")

    if (
        set(finalize) != REGISTRY_FINALIZE_KEYS
        or finalize.get("contractName") != REGISTRY_FINALIZE_CONTRACT
        or type(finalize.get("contractVersion")) is not int
        or finalize.get("contractVersion") != 1
        or finalize.get("channel") != "preview"
        or finalize.get("releaseVersion") != registry_candidate["releaseVersion"]
        or finalize.get("verificationStatus") != "finalized"
        or finalize.get("candidateBytesMutated") is not False
        or finalize.get("candidateImportAuthority") is not True
        or finalize.get("candidateReviewAuthority") is not True
        or any(
            finalize.get(key) is not False
            for key in (
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
            )
        )
        or finalize.get("fullShelfInventorySha256")
        != registry_candidate["fullShelfInventorySha256"]
    ):
        _fail("Registry FINALIZE receipt identity or bounded authority drifted")
    for key, path, held in (
        ("authority", REGISTRY_AUTHORITY_FILE, authority_raw),
        ("candidateReceipt", REGISTRY_CANDIDATE_FILE, registry_candidate_raw),
        ("canonicalManifest", "RELEASE_CHANNEL.generated.json", canonical_raw),
        ("compatibilityManifest", "releases.json", compatibility_raw),
        ("sourceScope", PUBLICATION_SCOPE_FILE, scope_raw),
    ):
        _expect_reference(finalize.get(key), path=path, raw=held, label=f"Registry finalize {key}")
    return {
        "status": "finalized",
        "candidateImportAuthority": True,
        "candidateReviewAuthority": True,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": False,
        "scope": "windows_only",
        "exactIncomingDesktopScope": EXACT_SCOPE_TUPLE,
        "candidateReceiptSha256": hashlib.sha256(registry_candidate_raw).hexdigest(),
        "authoritySha256": hashlib.sha256(authority_raw).hexdigest(),
        "finalizeReceiptSha256": hashlib.sha256(finalize_raw).hexdigest(),
    }


def _pretty_canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()


def _directory_mode_rows(value: object, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 100_000:
        _fail(f"{label} must be a bounded non-empty list")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {"mode", "path"}:
            _fail(f"{label} row {index} drifted")
        mode = raw.get("mode")
        if isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0o777:
            _fail(f"{label} row {index} mode drifted")
        rows.append(
            {
                "mode": mode,
                "path": _validate_relative_path(
                    raw.get("path"), label=f"{label} path"
                ),
            }
        )
    if rows != sorted(rows, key=lambda row: row["path"]) or len(
        {row["path"] for row in rows}
    ) != len(rows):
        _fail(f"{label} is not uniquely sorted")
    return rows


def _validate_unsigned_composition_v3(
    stage_root: Path,
    composition: object,
    composition_reference: object,
    *,
    canonical: dict[str, Any],
    canonical_raw: bytes,
    compatibility_raw: bytes,
    candidate_summary: dict[str, Any],
    candidate_directory_modes: list[dict[str, Any]],
    scope: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    if not isinstance(composition, dict):
        _fail("Registry PREPARE v2 embedded composition request is missing")
    expected_raw = (
        json.dumps(composition, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _composition_path, held_raw = _stage_bytes_reference(
        stage_root,
        composition_reference,
        expected_path=UNSIGNED_COMPOSITION_FILE,
        label="unsigned composition request",
    )
    if held_raw != expected_raw:
        _fail("unsigned composition request bytes are not pretty sorted JSON plus LF")
    if (
        set(composition) != UNSIGNED_COMPOSITION_KEYS
        or composition.get("contractName") != UNSIGNED_COMPOSITION_CONTRACT
        or type(composition.get("contractVersion")) is not int
        or composition.get("contractVersion") != 3
        or composition.get("status") != "prepared"
        or composition.get("release")
        != {"channel": "preview", "version": candidate_summary["version"]}
        or composition.get("platformScope") != "windows_only"
        or composition.get("crossRunBitReproducible") is not False
        or composition.get("signature") != UNSIGNED_SIGNATURE_POLICY
        or composition.get("sourceSha") != scope.get("sourceSha")
        or any(
            composition.get(key) is not False
            for key in (
                "publicationAuthorized",
                "uploadAuthorized",
                "deployAuthorized",
            )
        )
    ):
        _fail("unsigned composition request identity or posture drifted")
    _expect_reference(
        composition.get("proposedCanonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="unsigned composition canonical manifest",
    )
    _expect_reference(
        composition.get("proposedCompatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="unsigned composition compatibility manifest",
    )
    proposed_inventory = _scope_inventory(
        composition.get("proposedShelfInventory"),
        label="unsigned composition proposed inventory",
    )
    scope_inventory = _scope_inventory(
        scope.get("fullShelfInventory"), label="unsigned UI full shelf inventory"
    )
    proposed_modes = _directory_mode_rows(
        composition.get("proposedDirectoryModes"),
        label="unsigned composition proposed directory modes",
    )
    if (
        proposed_inventory != scope_inventory
        or proposed_modes != candidate_directory_modes
        or composition.get("proposedShelfInventorySha256")
        != _ui_compact_sha256(proposed_inventory)
        or composition.get("proposedDirectoryModesSha256")
        != _ui_compact_sha256(proposed_modes)
    ):
        _fail("unsigned composition proposed shelf digest graph drifted")

    incumbent = composition.get("incumbentSnapshot")
    incumbent_keys = {
        "canonicalManifest",
        "compatibilityManifest",
        "directoryModes",
        "directoryModesSha256",
        "fullShelfInventory",
        "fullShelfInventorySha256",
        "snapshotSha256",
    }
    if not isinstance(incumbent, dict) or set(incumbent) != incumbent_keys:
        _fail("unsigned composition incumbent snapshot property set drifted")
    incumbent_inventory = _scope_inventory(
        incumbent.get("fullShelfInventory"),
        label="unsigned composition incumbent inventory",
    )
    incumbent_modes = _directory_mode_rows(
        incumbent.get("directoryModes"),
        label="unsigned composition incumbent directory modes",
    )
    snapshot_body = {
        key: incumbent[key]
        for key in incumbent_keys
        if key != "snapshotSha256"
    }
    if (
        incumbent.get("fullShelfInventorySha256")
        != _ui_compact_sha256(incumbent_inventory)
        or incumbent.get("directoryModesSha256")
        != _ui_compact_sha256(incumbent_modes)
        or incumbent.get("snapshotSha256") != _ui_compact_sha256(snapshot_body)
        or scope.get("incumbentInventorySha256")
        != incumbent.get("fullShelfInventorySha256")
    ):
        _fail("unsigned composition incumbent snapshot digest graph drifted")
    for name in ("canonicalManifest", "compatibilityManifest"):
        _byte_reference(
            incumbent.get(name),
            label=f"unsigned composition incumbent {name}",
            expected_path=(
                "RELEASE_CHANNEL.generated.json"
                if name == "canonicalManifest"
                else "releases.json"
            ),
        )

    retained = _unsigned_retained_rows(
        composition.get("retainedFromIncumbent"),
        label="unsigned composition retained inventory",
    )
    if retained != _unsigned_retained_rows(
        scope.get("retainedFromIncumbent"),
        label="unsigned UI retained inventory",
    ):
        _fail("unsigned composition/UI retained inventory drifted")
    incumbent_by_path = {row["path"]: row for row in incumbent_inventory}
    proposed_by_path = {row["path"]: row for row in proposed_inventory}
    for row in retained:
        exact = {
            key: row[key] for key in ("mode", "path", "sha256", "sizeBytes")
        }
        if incumbent_by_path.get(row["path"]) != exact or proposed_by_path.get(
            row["path"]
        ) != exact:
            _fail("unsigned composition retained byte differs across shelves")

    fresh = composition.get("freshDelta")
    scope_fresh = scope.get("freshDelta")
    if (
        not isinstance(fresh, list)
        or len(fresh) != 2
        or not isinstance(scope_fresh, list)
        or len(scope_fresh) != 2
    ):
        _fail("unsigned composition fresh delta cardinality drifted")
    artifacts = canonical.get("artifacts")
    windows_rows = [
        row
        for row in artifacts or []
        if isinstance(row, dict)
        and row.get("head") == "avalonia"
        and row.get("platform") == "windows"
        and row.get("rid") == RID
    ]
    if len(windows_rows) != 1:
        _fail("unsigned composition canonical Windows row drifted")
    manifest_row_sha256 = _ui_compact_sha256(windows_rows[0])
    for composition_row, scope_row in zip(fresh, scope_fresh, strict=True):
        if (
            not isinstance(composition_row, dict)
            or set(composition_row)
            != {
                "artifactRole",
                "fileName",
                "head",
                "manifestRowSha256",
                "mode",
                "path",
                "platform",
                "rid",
                "sha256",
                "sizeBytes",
            }
            or composition_row.get("manifestRowSha256") != manifest_row_sha256
            or {
                key: value
                for key, value in composition_row.items()
                if key != "manifestRowSha256"
            }
            != scope_row
        ):
            _fail("unsigned composition/UI fresh delta graph drifted")

    provenance = composition.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != set(
        UNSIGNED_PROVENANCE_PATHS
    ):
        _fail("unsigned composition provenance property set drifted")
    for name, expected_path in UNSIGNED_PROVENANCE_PATHS.items():
        _path, held = _stage_bytes_reference(
            stage_root,
            provenance.get(name),
            expected_path=expected_path,
            label=f"unsigned composition provenance {name}",
        )
        if scope.get("provenance", {}).get(name) != {
            "sha256": hashlib.sha256(held).hexdigest(),
            "sizeBytes": len(held),
        }:
            _fail("unsigned composition/UI provenance byte graph drifted")
    return composition, held_raw


def _validate_registry_candidate_receipt_unsigned_v3(
    receipt: dict[str, Any],
    raw: bytes,
    *,
    stage_root: Path,
    canonical: dict[str, Any],
    canonical_raw: bytes,
    compatibility_raw: bytes,
    candidate_summary: dict[str, Any],
    candidate_directory_modes: list[dict[str, Any]],
    scope: dict[str, Any],
) -> dict[str, Any]:
    signature_policy = {
        "signatureStatus": "unsigned",
        "signingRequired": False,
        "unsignedReason": "preview_policy",
    }
    if (
        set(receipt) != REGISTRY_CANDIDATE_V2_KEYS
        or receipt.get("contractName") != REGISTRY_CANDIDATE_CONTRACT
        or type(receipt.get("contractVersion")) is not int
        or receipt.get("contractVersion") != 2
        or receipt.get("channel") != "preview"
        or receipt.get("releaseVersion") != candidate_summary["version"]
        or receipt.get("publicationStatus") != "review_required"
        or receipt.get("platformScope") != "windows_only"
        or receipt.get("crossRunBitReproducible") is not False
        or receipt.get("signaturePolicy") != signature_policy
        or receipt.get("sourceSha") != scope.get("sourceSha")
        or receipt.get("deltaPlatforms") != ["windows"]
        or receipt.get("evidencePlatforms") != []
        or any(
            receipt.get(key) is not False
            for key in (
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
                "codeDeploymentAuthority",
            )
        )
    ):
        _fail("Registry PREPARE v2 candidate identity or authority drifted")
    _expect_reference(
        receipt.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="Registry candidate canonical manifest",
    )
    _expect_reference(
        receipt.get("compatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="Registry candidate compatibility manifest",
    )
    full_inventory = _scope_inventory(
        receipt.get("fullShelfInventory"),
        label="Registry candidate full shelf inventory",
    )
    scope_inventory = _scope_inventory(
        scope.get("fullShelfInventory"),
        label="unsigned UI full shelf inventory",
    )
    if (
        full_inventory != scope_inventory
        or receipt.get("fullShelfInventorySha256")
        != _ui_compact_sha256(full_inventory)
    ):
        _fail("Registry PREPARE v2 inventory differs from unsigned UI custody")

    composition, composition_raw = _validate_unsigned_composition_v3(
        stage_root,
        receipt.get("compositionInputDocument"),
        receipt.get("compositionInput"),
        canonical=canonical,
        canonical_raw=canonical_raw,
        compatibility_raw=compatibility_raw,
        candidate_summary=candidate_summary,
        candidate_directory_modes=candidate_directory_modes,
        scope=scope,
    )
    fresh = scope.get("freshDelta")
    if not isinstance(fresh, list) or len(fresh) != 2:
        _fail("Registry PREPARE v2 Windows delta cardinality drifted")
    expected_windows_delta = {
        row["artifactRole"]: {
            "path": row["path"],
            "sha256": row["sha256"],
            "sizeBytes": row["sizeBytes"],
        }
        for row in fresh
    }
    if receipt.get("windowsDelta") != expected_windows_delta:
        _fail("Registry PREPARE v2 Windows delta differs from UI custody")

    incumbent = composition.get("incumbentSnapshot")
    if not isinstance(incumbent, dict):
        _fail("Registry PREPARE v2 incumbent snapshot is missing")
    retained = _unsigned_retained_rows(
        scope.get("retainedFromIncumbent"),
        label="unsigned UI retained inventory",
    )
    if (
        receipt.get("incumbentInventorySha256")
        != incumbent.get("fullShelfInventorySha256")
        or receipt.get("incumbentInventorySha256")
        != scope.get("incumbentInventorySha256")
        or receipt.get("incumbentSnapshotSha256")
        != incumbent.get("snapshotSha256")
        or receipt.get("incumbentDirectoryModesSha256")
        != incumbent.get("directoryModesSha256")
        or receipt.get("proposedDirectoryModesSha256")
        != composition.get("proposedDirectoryModesSha256")
        or receipt.get("retainedInventorySha256")
        != _ui_compact_sha256(retained)
    ):
        _fail("Registry PREPARE v2 incumbent/retained digest graph drifted")

    retained_platforms = receipt.get("retainedPlatforms")
    shelf_platforms = receipt.get("shelfPlatforms")
    allowed_platforms = {"linux", "macos", "windows"}
    artifacts = canonical.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _fail("Registry PREPARE v2 canonical artifact set is missing")
    canonical_platforms = {
        artifact.get("platform")
        for artifact in artifacts
        if isinstance(artifact, dict)
    }
    if (
        any(not isinstance(artifact, dict) for artifact in artifacts)
        or len(canonical_platforms) > len(allowed_platforms)
        or not canonical_platforms.issubset(allowed_platforms)
        or not isinstance(retained_platforms, list)
        or retained_platforms != sorted(canonical_platforms - {"windows"})
        or not isinstance(shelf_platforms, list)
        or shelf_platforms != sorted(canonical_platforms)
    ):
        _fail("Registry PREPARE v2 platform custody drifted")

    _validate_registry_projection_inputs_v2(receipt.get("projectionInputs"))
    provenance = receipt.get("provenance")
    if provenance != composition.get("provenance"):
        _fail("Registry PREPARE v2 provenance differs from composition custody")
    return {
        "composition": composition,
        "compositionRaw": composition_raw,
        "fullInventory": full_inventory,
        "retainedInventory": retained,
        "windowsDelta": expected_windows_delta,
    }


def _validate_registry_projection_inputs_v2(value: object) -> None:
    expected_paths = {
        "materializer": "scripts/materialize_unsigned_preview_publication_delta.py",
        "schema": "contracts/preview-publication-delta-v2.schema.json",
    }
    if not isinstance(value, dict) or set(value) != set(expected_paths):
        _fail("Registry unsigned v2 projection input property set drifted")
    for name, path in expected_paths.items():
        _byte_reference(
            value.get(name),
            label=f"Registry unsigned v2 projection input {name}",
            expected_path=path,
        )


def _validate_registry_finalize_graph_v2(
    authority: dict[str, Any],
    authority_raw: bytes,
    finalize: dict[str, Any],
    finalize_raw: bytes,
    *,
    registry_candidate: dict[str, Any],
    registry_candidate_raw: bytes,
    candidate_validation: dict[str, Any],
    canonical: dict[str, Any],
    canonical_raw: bytes,
    compatibility_raw: bytes,
    scope: dict[str, Any],
    scope_raw: bytes,
    stage_evidence_files: list[tuple[str, bytes]],
) -> dict[str, Any]:
    mixed_graph = {
        "authorityContractVersion": 2,
        "candidateReceiptContractVersion": 2,
        "compositionRequestContractVersion": 3,
        "finalizeReceiptContractVersion": 2,
        "sourceScopeContractVersion": 3,
    }
    signature_policy = {
        "signatureStatus": "unsigned",
        "signingRequired": False,
        "unsignedReason": "preview_policy",
    }
    if (
        set(authority) != REGISTRY_AUTHORITY_V2_KEYS
        or authority.get("contractName") != REGISTRY_AUTHORITY_CONTRACT
        or type(authority.get("contractVersion")) is not int
        or authority.get("contractVersion") != 2
        or authority.get("channel") != "preview"
        or authority.get("releaseVersion") != registry_candidate["releaseVersion"]
        or authority.get("candidateImportAuthority") is not True
        or authority.get("candidateReviewAuthority") is not True
        or authority.get("deltaPlatforms") != ["windows"]
        or authority.get("evidencePlatforms") != []
        or authority.get("platformScope") != "windows_only"
        or authority.get("crossRunBitReproducible") is not False
        or authority.get("mixedVersionGraph") != mixed_graph
        or authority.get("signaturePolicy") != signature_policy
        or authority.get("sourceSha") != scope.get("sourceSha")
        or any(
            authority.get(key) is not False
            for key in (
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
                "codeDeploymentAuthority",
            )
        )
    ):
        _fail("Registry unsigned FINALIZE authority identity or posture drifted")
    _expect_reference(
        authority.get("candidateReceipt"),
        path=REGISTRY_CANDIDATE_FILE,
        raw=registry_candidate_raw,
        label="Registry unsigned authority candidate receipt",
    )
    _expect_reference(
        authority.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=canonical_raw,
        label="Registry unsigned authority canonical manifest",
    )
    _expect_reference(
        authority.get("compatibilityManifest"),
        path="releases.json",
        raw=compatibility_raw,
        label="Registry unsigned authority compatibility manifest",
    )
    _expect_reference(
        authority.get("sourceScope"),
        path=UNSIGNED_PUBLICATION_SCOPE_FILE,
        raw=scope_raw,
        label="Registry unsigned authority source scope",
    )
    _expect_reference(
        authority.get("compositionRequest"),
        path=UNSIGNED_COMPOSITION_FILE,
        raw=candidate_validation["compositionRaw"],
        label="Registry unsigned authority composition request",
    )
    for name in (
        "fullShelfInventorySha256",
        "incumbentInventorySha256",
        "incumbentSnapshotSha256",
        "proposedDirectoryModesSha256",
        "retainedPlatforms",
        "retainedInventorySha256",
        "shelfPlatforms",
    ):
        if authority.get(name) != registry_candidate.get(name):
            _fail("Registry unsigned FINALIZE/PREPARE digest graph drifted")
    if authority.get("retainedInventorySha256") != _ui_compact_sha256(
        scope.get("retainedFromIncumbent")
    ):
        _fail("Registry unsigned retained/incumbent inventory graph drifted")
    _validate_registry_projection_inputs_v2(authority.get("projectionInputs"))
    if authority.get("projectionInputs") != registry_candidate.get("projectionInputs"):
        _fail("Registry unsigned FINALIZE/PREPARE projection inputs drifted")
    expected_windows_delta = candidate_validation["windowsDelta"]
    if authority.get("windowsDelta") != expected_windows_delta:
        _fail("Registry unsigned Windows delta binding drifted")
    held_by_path = dict(stage_evidence_files)
    provenance = authority.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != set(
        UNSIGNED_PROVENANCE_PATHS
    ):
        _fail("Registry unsigned provenance property set drifted")
    if provenance != registry_candidate.get("provenance"):
        _fail("Registry unsigned FINALIZE/PREPARE provenance graph drifted")
    for name, path in UNSIGNED_PROVENANCE_PATHS.items():
        raw = held_by_path.get(path)
        if raw is None:
            _fail("Registry unsigned provenance is absent from UI custody")
        _expect_reference(
            provenance.get(name),
            path=path,
            raw=raw,
            label=f"Registry unsigned provenance {name}",
        )

    if (
        set(finalize) != REGISTRY_FINALIZE_V2_KEYS
        or finalize.get("contractName") != REGISTRY_FINALIZE_CONTRACT
        or type(finalize.get("contractVersion")) is not int
        or finalize.get("contractVersion") != 2
        or finalize.get("verificationStatus") != "finalized"
        or finalize.get("candidateBytesMutated") is not False
        or finalize.get("candidateImportAuthority") is not True
        or finalize.get("candidateReviewAuthority") is not True
        or finalize.get("channel") != "preview"
        or finalize.get("releaseVersion") != registry_candidate["releaseVersion"]
        or finalize.get("platformScope") != "windows_only"
        or finalize.get("mixedVersionGraph") != mixed_graph
        or finalize.get("signaturePolicy") != signature_policy
        or finalize.get("windowsDelta") != expected_windows_delta
        or finalize.get("provenance") != provenance
        or finalize.get("fullShelfInventorySha256")
        != registry_candidate["fullShelfInventorySha256"]
        or any(
            finalize.get(key) is not False
            for key in (
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "deployAuthority",
                "routeAuthority",
                "codeDeploymentAuthority",
            )
        )
    ):
        _fail("Registry unsigned FINALIZE receipt identity or posture drifted")
    for key, path, held in (
        ("authority", REGISTRY_AUTHORITY_FILE, authority_raw),
        ("candidateReceipt", REGISTRY_CANDIDATE_FILE, registry_candidate_raw),
        ("canonicalManifest", "RELEASE_CHANNEL.generated.json", canonical_raw),
        ("compatibilityManifest", "releases.json", compatibility_raw),
        (
            "compositionRequest",
            UNSIGNED_COMPOSITION_FILE,
            candidate_validation["compositionRaw"],
        ),
        ("sourceScope", UNSIGNED_PUBLICATION_SCOPE_FILE, scope_raw),
    ):
        _expect_reference(
            finalize.get(key), path=path, raw=held, label=f"Registry unsigned finalize {key}"
        )
    return {
        "status": "finalized",
        "candidateImportAuthority": True,
        "candidateReviewAuthority": True,
        "publicationAuthorized": False,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": False,
        "codeDeploymentAuthority": False,
        "scope": "windows_only",
        "exactIncomingDesktopScope": EXACT_SCOPE_TUPLE,
        "signaturePolicy": signature_policy,
        "candidateReceiptSha256": hashlib.sha256(registry_candidate_raw).hexdigest(),
        "authoritySha256": hashlib.sha256(authority_raw).hexdigest(),
        "finalizeReceiptSha256": hashlib.sha256(finalize_raw).hexdigest(),
    }


def _embedded(path: str, payload: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "sizeBytes": len(payload),
        "base64": base64.b64encode(payload).decode("ascii"),
    }


def _atomic_write(path: Path, payload: bytes) -> None:
    parent = path.parent.resolve(strict=True)
    if path.exists() or path.is_symlink():
        _fail("candidate import authority output must not already exist")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    bundle_root = Path(args.bundle_root).resolve(strict=True)
    if not bundle_root.is_dir() or bundle_root.is_symlink():
        _fail("candidate bundle root must be a real directory")
    stage_root = Path(args.publication_stage_root).resolve(strict=True)
    if not stage_root.is_dir() or stage_root.is_symlink():
        _fail("publication stage root must be a real directory")
    publication_scope_name = Path(args.publication_scope).name
    if publication_scope_name == PUBLICATION_SCOPE_FILE:
        unsigned_preview = False
    elif publication_scope_name == UNSIGNED_PUBLICATION_SCOPE_FILE:
        unsigned_preview = True
    else:
        _fail("UI publication scope filename is not a supported exact contract")
    candidate, _ = _strict_json(Path(args.candidate_summary), label="candidate summary")
    _validate_candidate(candidate)
    inventory, inventory_bytes = _strict_json(
        Path(args.candidate_inventory), label="candidate upload inventory"
    )
    (
        candidate_rows,
        candidate_file_modes,
        candidate_directory_modes,
        captured_bundle_files,
    ) = _validate_bundle_inventory(
        bundle_root,
        inventory,
        candidate,
        allow_root_ancillary_files=unsigned_preview,
    )
    canonical_manifest = _plain_file(
        Path(args.canonical_manifest), label="candidate canonical manifest", maximum_bytes=MAX_JSON_BYTES
    )
    canonical_bytes = captured_bundle_files.get("RELEASE_CHANNEL.generated.json")
    if canonical_bytes is None:
        _fail("candidate canonical manifest is absent from exact tree custody")
    canonical = _strict_json_bytes(
        canonical_bytes, label="candidate canonical manifest"
    )
    canonical_digest = hashlib.sha256(canonical_bytes).hexdigest()
    if canonical_digest != candidate["canonicalManifestSha256"]:
        _fail("candidate canonical manifest digest differs from its summary")
    if canonical_manifest.resolve() != (bundle_root / "RELEASE_CHANNEL.generated.json").resolve():
        _fail("candidate canonical manifest must be the upload tree RELEASE_CHANNEL.generated.json")
    compatibility_bytes = captured_bundle_files.get("releases.json")
    if compatibility_bytes is None:
        _fail("candidate compatibility manifest is absent from exact tree custody")
    compatibility = _strict_json_bytes(
        compatibility_bytes, label="candidate compatibility manifest"
    )
    _scope_relative, publication_scope, publication_scope_bytes = _read_stage_input(
        stage_root,
        args.publication_scope,
        expected_name=publication_scope_name,
        label=(
            "unsigned UI publication scope"
            if unsigned_preview
            else "final UI publication scope"
        ),
        require_canonical=False,
    )
    scope = _canonical_windows_scope(
        canonical,
        candidate_rows,
        allow_ancillary_files=unsigned_preview,
        expected_channel="preview" if unsigned_preview else None,
    )
    if scope["version"] != candidate["version"]:
        _fail("candidate release version differs from its upload summary")
    compatibility_version = _matching_alias(
        compatibility,
        "version",
        "releaseVersion",
        label="candidate compatibility release version",
    )
    compatibility_channel = _matching_alias(
        compatibility,
        "channelId",
        "channel",
        label="candidate compatibility release channel",
    )
    if (
        compatibility_version != scope["version"]
        or compatibility_channel != scope["channel"]
    ):
        _fail("candidate compatibility release identity differs from canonical custody")

    now = (
        _timestamp(args.now, label="materialization time")
        if args.now
        else datetime.now(timezone.utc)
    )
    max_age_seconds = _positive_int(
        args.max_proof_age_seconds, label="max proof age seconds"
    )
    lifetime_seconds = _positive_int(
        args.authority_lifetime_seconds, label="authority lifetime seconds"
    )
    if (
        max_age_seconds > DEFAULT_MAX_PROOF_AGE_SECONDS
        or lifetime_seconds > MAX_AUTHORITY_LIFETIME_SECONDS
    ):
        _fail("candidate authority freshness budget exceeds its hard maximum")

    native_evidence: dict[str, Any] | None = None
    native_custody_files: list[tuple[str, bytes]] = []
    if unsigned_preview:
        expires_at = now + timedelta(seconds=lifetime_seconds)
        publication_evidence, publication_files = (
            _validate_unsigned_publication_scope_v3(
                stage_root,
                candidate_file_modes,
                publication_scope,
                publication_scope_bytes,
                candidate=candidate,
                candidate_rows=candidate_rows,
                canonical_bytes=canonical_bytes,
                compatibility_bytes=compatibility_bytes,
                canonical_scope=scope,
            )
        )
    else:
        if not args.windows_finalized_root:
            _fail("signed v2 authority requires Windows finalized evidence")
        stage_native_root = stage_root / "proof" / "windows-native"
        if stage_native_root.is_symlink():
            _fail("publication-stage Windows native evidence root must not be a symlink")
        stage_native_root = stage_native_root.resolve(strict=True)
        configured_native_root = Path(args.windows_finalized_root).resolve(strict=True)
        if configured_native_root != stage_native_root:
            _fail(
                "Windows finalized root must be publication-stage proof/windows-native"
            )
        (
            native_evidence,
            oldest_proof,
            native_custody_files,
            native_package,
        ) = _validate_native_evidence(
            stage_native_root,
            bundle_root=bundle_root,
            canonical_manifest_sha256=canonical_digest,
            scope=scope,
            now=now,
            max_age=timedelta(seconds=max_age_seconds),
        )
        expires_at = min(
            now + timedelta(seconds=lifetime_seconds),
            oldest_proof + timedelta(seconds=max_age_seconds),
        )
        if expires_at <= now + timedelta(minutes=1):
            _fail(
                "fresh native-Windows evidence has insufficient remaining "
                "authority lifetime"
            )
        publication_evidence, publication_files = _validate_final_publication_scope(
            stage_root,
            publication_scope,
            publication_scope_bytes,
            candidate=candidate,
            candidate_rows=candidate_rows,
            canonical_bytes=canonical_bytes,
            compatibility_bytes=compatibility_bytes,
            canonical_scope=scope,
            native_package=native_package,
        )
    _registry_candidate_relative, registry_candidate, registry_candidate_bytes = (
        _read_stage_input(
            stage_root,
            args.registry_candidate_receipt,
            expected_name=REGISTRY_CANDIDATE_FILE,
            label="Registry PREPARE candidate receipt",
        )
    )
    if unsigned_preview:
        candidate_validation = _validate_registry_candidate_receipt_unsigned_v3(
            registry_candidate,
            registry_candidate_bytes,
            stage_root=stage_root,
            canonical=canonical,
            canonical_raw=canonical_bytes,
            compatibility_raw=compatibility_bytes,
            candidate_summary=candidate,
            candidate_directory_modes=candidate_directory_modes,
            scope=publication_scope,
        )
    else:
        _validate_registry_candidate_receipt(
            registry_candidate,
            registry_candidate_bytes,
            canonical_raw=canonical_bytes,
            compatibility_raw=compatibility_bytes,
            candidate_summary=candidate,
            scope=publication_scope,
        )
    _registry_authority_relative, registry_authority, registry_authority_bytes = (
        _read_stage_input(
            stage_root,
            args.registry_finalize_authority,
            expected_name=REGISTRY_AUTHORITY_FILE,
            label="Registry FINALIZE authority",
        )
    )
    _registry_finalize_relative, registry_finalize, registry_finalize_bytes = (
        _read_stage_input(
            stage_root,
            args.registry_finalize_receipt,
            expected_name=REGISTRY_FINALIZE_CUSTODY_FILE,
            label="Registry FINALIZE receipt",
        )
    )
    if unsigned_preview:
        registry_finalization = _validate_registry_finalize_graph_v2(
            registry_authority,
            registry_authority_bytes,
            registry_finalize,
            registry_finalize_bytes,
            registry_candidate=registry_candidate,
            registry_candidate_raw=registry_candidate_bytes,
            candidate_validation=candidate_validation,
            canonical=canonical,
            canonical_raw=canonical_bytes,
            compatibility_raw=compatibility_bytes,
            scope=publication_scope,
            scope_raw=publication_scope_bytes,
            stage_evidence_files=publication_files,
        )
    else:
        registry_finalization = _validate_registry_finalize_graph(
            registry_authority,
            registry_authority_bytes,
            registry_finalize,
            registry_finalize_bytes,
            registry_candidate=registry_candidate,
            registry_candidate_raw=registry_candidate_bytes,
            canonical=canonical,
            canonical_raw=canonical_bytes,
            compatibility_raw=compatibility_bytes,
            scope=publication_scope,
            scope_raw=publication_scope_bytes,
            stage_evidence_files=publication_files,
        )

    (
        final_candidate_rows,
        final_candidate_file_modes,
        final_candidate_directory_modes,
        final_captured_bundle_files,
    ) = _scan_bundle_tree(bundle_root)
    if (
        final_candidate_rows != candidate_rows
        or final_candidate_file_modes != candidate_file_modes
        or final_candidate_directory_modes != candidate_directory_modes
        or final_captured_bundle_files != captured_bundle_files
    ):
        _fail("candidate bundle changed before authority sealing")

    custody: dict[str, Any] = {
        "canonicalManifest": _embedded(
            "RELEASE_CHANNEL.generated.json", canonical_bytes
        ),
        "compatibilityManifest": _embedded("releases.json", compatibility_bytes),
        "inventory": _embedded(
            "CANDIDATE_UPLOAD_INVENTORY.generated.json", inventory_bytes
        ),
        "registryPrepareCandidateReceipt": _embedded(
            REGISTRY_CANDIDATE_FILE, registry_candidate_bytes
        ),
        "registryFinalizeAuthority": _embedded(
            REGISTRY_AUTHORITY_FILE, registry_authority_bytes
        ),
        "registryFinalizeReceipt": _embedded(
            REGISTRY_FINALIZE_CUSTODY_FILE, registry_finalize_bytes
        ),
        "registryFinalization": registry_finalization,
    }
    if unsigned_preview:
        custody["unsignedPublicationEvidence"] = {
            **publication_evidence,
            "files": [
                _embedded(path, payload)
                for path, payload in sorted(publication_files)
            ],
        }
    else:
        if native_evidence is None:
            _fail("signed v2 native evidence disappeared before custody sealing")
        custody["nativeWindowsFinalizedEvidence"] = {
            **native_evidence,
            "files": [
                _embedded(path, payload)
                for path, payload in sorted(native_custody_files)
            ],
        }
        custody["finalizedPublicationEvidence"] = {
            **publication_evidence,
            "files": [
                _embedded(path, payload)
                for path, payload in sorted(publication_files)
            ],
        }

    authority: dict[str, Any] = {
        "contractName": (
            UNSIGNED_AUTHORITY_CONTRACT if unsigned_preview else AUTHORITY_CONTRACT
        ),
        "contractVersion": 3 if unsigned_preview else 2,
        "status": "candidate_import_ready",
        "candidateImportAuthority": True,
        "candidateReviewAuthority": True,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": False,
        "exactIncomingDesktopScope": EXACT_SCOPE_TUPLE,
        "generatedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "expiresAtUtc": expires_at.isoformat().replace("+00:00", "Z"),
        "candidate": candidate,
        "custody": custody,
    }
    if unsigned_preview:
        authority.update(
            {
                "publicationAuthorized": False,
                "codeDeploymentAuthority": False,
                "platformScope": "windows_only",
                "crossRunBitReproducible": False,
                "signaturePolicy": {
                    "signatureStatus": "unsigned",
                    "signingRequired": False,
                    "unsignedReason": "preview_policy",
                },
            }
        )
    rendered = (
        json.dumps(authority, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    _atomic_write(Path(args.output), rendered)
    return authority


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize one fresh, exact candidate-import authority."
    )
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--canonical-manifest", required=True)
    parser.add_argument("--candidate-summary", required=True)
    parser.add_argument("--candidate-inventory", required=True)
    parser.add_argument("--windows-finalized-root", default="")
    parser.add_argument("--publication-stage-root", required=True)
    parser.add_argument("--publication-scope", required=True)
    parser.add_argument("--registry-candidate-receipt", required=True)
    parser.add_argument("--registry-finalize-authority", required=True)
    parser.add_argument("--registry-finalize-receipt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--max-proof-age-seconds", type=int, default=DEFAULT_MAX_PROOF_AGE_SECONDS
    )
    parser.add_argument(
        "--authority-lifetime-seconds", type=int, default=MAX_AUTHORITY_LIFETIME_SECONDS
    )
    parser.add_argument("--now", default="", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    if tuple(__import__("sys").version_info) < (3, 11):
        print("candidate import authority requires Python 3.11 or newer", file=__import__("sys").stderr)
        return 2
    args = _parser().parse_args(argv)
    try:
        authority = materialize(args)
    except (CandidateAuthorityBlocked, OSError, ValueError) as exc:
        print(f"candidate import authority blocked: {exc}", file=__import__("sys").stderr)
        return 1
    print(
        json.dumps(
            {
                "status": authority["status"],
                "bundleIdentitySha256": authority["candidate"]["bundleIdentitySha256"],
                "expiresAtUtc": authority["expiresAtUtc"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
