#!/usr/bin/env python3
"""Seal one upload candidate behind exact publication and native-Windows proof.

This command has no network or publication behavior.  It authenticates the
candidate tree and the exact finalized UI evidence already in operator custody,
then emits a bounded authority document whose embedded bytes can be placed in a
digest-bound public-projection snapshot. Unsigned publication without a native
root remains the stage-only v3 contract; an exact unsigned finalized native
root emits the narrowly privileged owner-finalization v4 contract. A v5 bridge
additionally proves that the final upload manifests are the exact deterministic
generation projection of the Registry-reviewed v4 source and binds the three
review-required native-stage authority-seed files.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Iterable
import zipfile
import zlib


AUTHORITY_CONTRACT = "chummer.release-upload.candidate-import-authority/v2"
UNSIGNED_AUTHORITY_CONTRACT = "chummer.release-upload.candidate-import-authority/v3"
UNSIGNED_NATIVE_AUTHORITY_CONTRACT = (
    "chummer.release-upload.candidate-import-authority/v4"
)
UNSIGNED_NATIVE_GENERATION_AUTHORITY_CONTRACT = (
    "chummer.release-upload.candidate-import-authority/v5"
)
GENERATION_PROJECTION_CONTRACT = (
    "chummer.release-upload.native-stage-generation-projection/v1"
)
NATIVE_STAGE_AUTHORITY_SEED_PATHS = (
    "release-evidence/CURRENT.json",
    "release-evidence/RELEASE_DECISION.json",
    "release-evidence/SNAPSHOT.json",
)
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
UNSIGNED_CAPTURE_WORKFLOW = (
    ".github/workflows/unsigned-windows-preview-native-evidence-capture.yml"
)
UNSIGNED_FINALIZE_WORKFLOW = (
    ".github/workflows/unsigned-windows-preview-native-evidence-finalize.yml"
)
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
UNSIGNED_V3_PROJECTION_PROFILE = "v3_unsigned_windows_fresh_delta"
UNSIGNED_PAYLOAD_SIDECAR_NAME = "chummer-avalonia-win-x64-payload.zip.json"
UNSIGNED_SOURCE_CANONICAL_PATH = (
    "transport/source-publication/RELEASE_CHANNEL.generated.json"
)
UNSIGNED_SOURCE_COMPATIBILITY_PATH = "transport/source-publication/releases.json"
UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE = (
    "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZED_EVIDENCE.generated.json"
)
UNSIGNED_NATIVE_CAPTURE_FILE = (
    "UNSIGNED_WINDOWS_PREVIEW_NATIVE_CAPTURE.generated.json"
)
UNSIGNED_NATIVE_CAPTURE_INVENTORY_FILE = (
    "UNSIGNED_WINDOWS_PREVIEW_NATIVE_CAPTURE_INVENTORY.generated.json"
)
UNSIGNED_NATIVE_FINALIZATION_FILE = (
    "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZATION.generated.json"
)
UNSIGNED_NATIVE_FINALIZED_INVENTORY_FILE = (
    "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZED_INVENTORY.generated.json"
)
UNSIGNED_CANDIDATE_PROVENANCE_INVENTORY = (
    "candidate-provenance/"
    "PREVIEW_NIGHTLY_UNSIGNED_CANDIDATE_CONTENT_INVENTORY.generated.json"
)
UNSIGNED_CANDIDATE_PROVENANCE_EXPORT = (
    "candidate-provenance/PREVIEW_NIGHTLY_UNSIGNED_CANDIDATE_EXPORT.generated.json"
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
REGISTRY_AUTHORITY_PROFILE_KEYS = REGISTRY_AUTHORITY_V2_KEYS | {
    "codeDeployCurrentShelfAuthority",
    "privacyLaunchGateSnapshot",
    "privacyLaunchGateSnapshotSha256",
    "projectionProfile",
    "registryCommit",
    "registry_commit",
    "retainedIncumbentProvenance",
    "sourceCanonicalManifest",
    "sourceCompatibilityManifest",
    "sourceShelfInventorySha256",
}
REGISTRY_FINALIZE_PROFILE_KEYS = REGISTRY_FINALIZE_V2_KEYS | {
    "codeDeployCurrentShelfAuthority",
    "privacyLaunchGateSnapshot",
    "privacyLaunchGateSnapshotSha256",
    "projectionProfile",
    "registryCommit",
    "registry_commit",
    "retainedIncumbentProvenance",
    "sourceCanonicalManifest",
    "sourceCompatibilityManifest",
    "sourceShelfInventorySha256",
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
REGISTRY_CANDIDATE_PROFILE_KEYS = REGISTRY_CANDIDATE_V2_KEYS | {
    "codeDeployCurrentShelfAuthority",
    "privacyLaunchGateSnapshot",
    "privacyLaunchGateSnapshotSha256",
    "projectionProfile",
    "registryCommit",
    "registry_commit",
    "retainedIncumbentProvenance",
    "sourceCanonicalManifest",
    "sourceCompatibilityManifest",
    "sourceShelfInventorySha256",
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
UNSIGNED_PROFILE_COMPOSITION_KEYS = UNSIGNED_COMPOSITION_KEYS | {
    "projectionProfile"
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
UNSIGNED_PROFILE_PUBLICATION_SCOPE_KEYS = UNSIGNED_PUBLICATION_SCOPE_KEYS | {
    "projectionProfile"
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
UNSIGNED_PRIVACY_LAUNCH_GATE_SNAPSHOT = {
    "blockedClaims": [
        "flagship_launch",
        "public_release_supportability",
        "hosted_build_recovery_and_erasure",
    ],
    "blocksLaunch": True,
    "capabilityContractName": "chummer.hosted_build_privacy_lifecycle",
    "capabilityContractVersion": 1,
    "contractName": "chummer.privacy_launch_gate",
    "contractVersion": 1,
    "facts": [
        "active-record-delete",
        "memory-only-recovery",
        "no-delete-replay",
        "no-owner-erasure",
        "production-recovery-unverified",
    ],
    "prohibitedClaims": [
        "permanent-delete",
        "durable-recovery",
        "account-erasure",
    ],
    "reason": (
        "Hosted Build backup and point-in-time-recovery retention, tombstone or "
        "lineage retention, deletion replay, and whole-account erasure are not "
        "launch-approved or production-verified."
    ),
    "reviewRequired": True,
    "scope": "flagship_launch_and_release_supportability",
    "status": "review_required",
}
UNSIGNED_CODE_DEPLOY_REVIEW_KEYS = {
    "authority",
    "contract",
    "evaluatedAt",
    "incumbentSnapshotSha256",
    "projectedArtifactCount",
    "projectedArtifactInventorySha256",
    "projectionProfile",
    "registryCommit",
    "sourceCanonicalManifestSha256",
    "sourceCompatibilityManifestSha256",
    "sourceShelfInventorySha256",
    "status",
}
UNSIGNED_RETAINED_PROVENANCE_KEYS = {
    "contractName",
    "contractVersion",
    "incumbentCanonicalManifestSha256",
    "incumbentCompatibilityManifestSha256",
    "incumbentFullShelfInventorySha256",
    "incumbentSnapshotSha256",
    "retainedArtifactBindings",
    "retainedArtifactBindingsSha256",
    "retainedCompatibilityBindings",
    "retainedCompatibilityBindingsSha256",
    "retainedInventorySha256",
}
UNSIGNED_RETAINED_ARTIFACT_BINDING_KEYS = {
    "artifactId",
    "manifestRowSha256",
    "sha256",
    "sizeBytes",
}
UNSIGNED_RETAINED_ARTIFACT_IDS = [
    "avalonia-osx-arm64-installer",
    "blazor-desktop-osx-arm64-installer",
    "avalonia-osx-arm64-archive",
    "blazor-desktop-osx-arm64-archive",
]
UNSIGNED_RETAINED_LINUX_ARTIFACT_IDS = [
    "avalonia-linux-x64-installer",
]
UNSIGNED_PROFILE_AUTHORITY_FIELDS = {
    "authority",
    "authoritative",
    "candidateImportAuthority",
    "candidateReviewAuthority",
    "codeDeploymentAuthority",
    "deployAuthority",
    "deployAuthorized",
    "manifestIsAuthoritative",
    "publicationAuthority",
    "publicationAuthorized",
    "publicationEligible",
    "releaseUploadAuthority",
    "releaseUploadAuthorized",
    "routeAuthority",
    "routeAuthorized",
    "uploadAuthority",
    "uploadAuthorized",
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


def _unsigned_profile_enabled(value: dict[str, Any], *, label: str) -> bool:
    profile = value.get("projectionProfile")
    if profile is None:
        return False
    if profile != UNSIGNED_V3_PROJECTION_PROFILE:
        _fail(f"{label} projectionProfile is unsupported")
    return True


def _validate_unsigned_profile_recursive_authority(
    value: object, *, label: str
) -> None:
    pending: list[tuple[object, str]] = [(value, label)]
    while pending:
        current, current_label = pending.pop()
        if isinstance(current, dict):
            for field, child in current.items():
                child_label = f"{current_label} {field}"
                if field in UNSIGNED_PROFILE_AUTHORITY_FIELDS and child is not False:
                    _fail(f"{child_label} must be exactly false")
                if isinstance(child, (dict, list)):
                    pending.append((child, child_label))
        elif isinstance(current, list):
            pending.extend(
                (child, f"{current_label}[{index}]")
                for index, child in enumerate(current)
                if isinstance(child, (dict, list))
            )


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


def _derive_unsigned_payload_executable(
    bundle_root: Path,
    *,
    payload_path: str,
    payload_row: dict[str, Any],
) -> dict[str, Any]:
    parts = _validate_relative_path(
        payload_path,
        label="unsigned candidate payload path",
    ).split("/")
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    close_flag = getattr(os, "O_CLOEXEC", 0)
    if directory_flag == 0 or nofollow_flag == 0:
        _fail("payload ZIP custody requires openat no-follow support")
    directory_descriptors: list[int] = []
    payload_descriptor = -1
    try:
        current = os.open(
            bundle_root,
            os.O_RDONLY | directory_flag | nofollow_flag | close_flag,
        )
        directory_descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(
                part,
                os.O_RDONLY | directory_flag | nofollow_flag | close_flag,
                dir_fd=current,
            )
            directory_descriptors.append(current)
        payload_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | nofollow_flag | close_flag,
            dir_fd=current,
        )
        before = os.fstat(payload_descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size != payload_row["sizeBytes"]
        ):
            _fail("unsigned candidate payload ZIP identity drifted")
        digest = hashlib.sha256()
        os.lseek(payload_descriptor, 0, os.SEEK_SET)
        while True:
            chunk = os.read(payload_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if digest.hexdigest() != payload_row["sha256"]:
            _fail("unsigned candidate payload ZIP bytes drifted")

        with os.fdopen(os.dup(payload_descriptor), "rb") as payload_handle:
            try:
                with zipfile.ZipFile(payload_handle, mode="r") as archive:
                    executable_entries = [
                        info
                        for info in archive.infolist()
                        if info.filename == "Chummer.Avalonia.exe"
                    ]
                    if len(executable_entries) != 1:
                        _fail(
                            "unsigned candidate payload ZIP must contain one "
                            "exact Chummer.Avalonia.exe entry"
                        )
                    executable = executable_entries[0]
                    if (
                        executable.is_dir()
                        or executable.flag_bits & 0x1
                        or executable.file_size < 1
                        or executable.file_size > 512 * 1024 * 1024
                    ):
                        _fail(
                            "unsigned candidate payload executable entry drifted"
                        )
                    executable_digest = hashlib.sha256()
                    executable_size = 0
                    with archive.open(executable, mode="r") as entry:
                        while True:
                            chunk = entry.read(1024 * 1024)
                            if not chunk:
                                break
                            executable_size += len(chunk)
                            if executable_size > executable.file_size:
                                _fail(
                                    "unsigned candidate payload executable "
                                    "expanded beyond ZIP metadata"
                                )
                            executable_digest.update(chunk)
                    if executable_size != executable.file_size:
                        _fail(
                            "unsigned candidate payload executable size drifted"
                        )
            except zipfile.BadZipFile as exc:
                raise CandidateAuthorityBlocked(
                    "unsigned candidate payload is not a valid ZIP"
                ) from exc
        after = os.fstat(payload_descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail("unsigned candidate payload ZIP changed during inspection")
        return {
            "fileName": "Chummer.Avalonia.exe",
            "payloadEntry": "Chummer.Avalonia.exe",
            "sha256": executable_digest.hexdigest(),
            "sizeBytes": executable_size,
        }
    except OSError as exc:
        raise CandidateAuthorityBlocked(
            "unsigned candidate payload ZIP could not be opened safely"
        ) from exc
    finally:
        if payload_descriptor >= 0:
            os.close(payload_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)


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


def _profile_artifact_inventory_rows(
    manifest: dict[str, Any], *, label: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _fail(f"{label} artifacts are missing")
    inventory: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            _fail(f"{label} artifact[{index}] is invalid")
        artifact_id = artifact.get("artifactId") or artifact.get("id")
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or artifact_id != artifact_id.strip().lower()
            or artifact_id in seen_ids
        ):
            _fail(f"{label} artifact[{index}] identity is invalid")
        if "artifactId" in artifact and artifact.get("artifactId") != artifact_id:
            _fail(f"{label} artifact[{index}] artifactId alias drifted")
        if "id" in artifact and artifact.get("id") != artifact_id:
            _fail(f"{label} artifact[{index}] id alias drifted")
        file_name = artifact.get("fileName")
        digest = artifact.get("sha256")
        size_bytes = artifact.get("sizeBytes")
        tokens: dict[str, str] = {}
        for name in ("head", "platform", "rid", "arch", "kind"):
            value = artifact.get(name)
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip().lower()
            ):
                _fail(f"{label} artifact[{index}] {name} is invalid")
            tokens[name] = value
        if (
            not isinstance(file_name, str)
            or not file_name
            or file_name != file_name.strip()
            or file_name in seen_files
            or SHA256_RE.fullmatch(str(digest or "")) is None
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 1
        ):
            _fail(f"{label} artifact[{index}] byte identity is invalid")
        seen_ids.add(artifact_id)
        seen_files.add(file_name)
        inventory_row: dict[str, Any] = {
            "artifactId": artifact_id,
            **tokens,
            "fileName": file_name,
            "sha256": digest,
            "sizeBytes": size_bytes,
        }
        payload_values = {
            "payloadFileName": artifact.get("payloadFileName"),
            "payloadSha256": artifact.get("payloadSha256"),
            "payloadSizeBytes": artifact.get("payloadSizeBytes"),
        }
        present_payload_fields = {
            name for name, value in payload_values.items() if value is not None
        }
        if present_payload_fields:
            if (
                present_payload_fields != set(payload_values)
                or not isinstance(payload_values["payloadFileName"], str)
                or not payload_values["payloadFileName"]
                or payload_values["payloadFileName"]
                != payload_values["payloadFileName"].strip()
                or SHA256_RE.fullmatch(
                    str(payload_values["payloadSha256"] or "")
                )
                is None
                or isinstance(payload_values["payloadSizeBytes"], bool)
                or not isinstance(payload_values["payloadSizeBytes"], int)
                or payload_values["payloadSizeBytes"] < 1
            ):
                _fail(f"{label} artifact[{index}] payload identity is invalid")
            inventory_row.update(payload_values)
        inventory.append(inventory_row)
    return artifacts, inventory


def _validate_profile_retained_provenance(
    canonical: dict[str, Any],
    compatibility: dict[str, Any],
    provenance: object,
    *,
    review: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if (
        not isinstance(provenance, dict)
        or set(provenance) != UNSIGNED_RETAINED_PROVENANCE_KEYS
        or provenance.get("contractName")
        != "chummer.registry.retained-incumbent-provenance"
        or type(provenance.get("contractVersion")) is not int
        or provenance.get("contractVersion") != 1
        or provenance.get("incumbentSnapshotSha256")
        != review.get("incumbentSnapshotSha256")
    ):
        _fail("projected retained incumbent provenance shape drifted")
    for field in (
        "incumbentCanonicalManifestSha256",
        "incumbentCompatibilityManifestSha256",
        "incumbentFullShelfInventorySha256",
        "incumbentSnapshotSha256",
        "retainedArtifactBindingsSha256",
        "retainedCompatibilityBindingsSha256",
        "retainedInventorySha256",
    ):
        if SHA256_RE.fullmatch(str(provenance.get(field) or "")) is None:
            _fail(f"projected retained incumbent provenance {field} is invalid")

    artifacts, _inventory = _profile_artifact_inventory_rows(
        canonical, label="projected canonical manifest"
    )
    retained_artifacts = [
        artifact for artifact in artifacts if artifact.get("platform") != "windows"
    ]
    bindings = provenance.get("retainedArtifactBindings")
    if (
        not isinstance(bindings, list)
        or len(bindings) != len(retained_artifacts)
        or provenance.get("retainedArtifactBindingsSha256")
        != _ui_compact_sha256(bindings)
    ):
        _fail("projected retained artifact binding set drifted")
    retained_ids: list[str] = []
    retained_by_file: dict[str, dict[str, Any]] = {}
    for index, (binding, artifact) in enumerate(
        zip(bindings, retained_artifacts, strict=True)
    ):
        artifact_id = artifact.get("artifactId") or artifact.get("id")
        if (
            not isinstance(binding, dict)
            or set(binding) != UNSIGNED_RETAINED_ARTIFACT_BINDING_KEYS
            or binding.get("artifactId") != artifact_id
            or binding.get("manifestRowSha256") != _ui_compact_sha256(artifact)
            or binding.get("sha256") != artifact.get("sha256")
            or binding.get("sizeBytes") != artifact.get("sizeBytes")
            or artifact_id in retained_ids
        ):
            _fail(f"projected retained artifact binding[{index}] drifted")
        retained_ids.append(str(artifact_id))
        retained_by_file[str(artifact.get("fileName"))] = artifact
    if retained_ids not in (
        [],
        UNSIGNED_RETAINED_ARTIFACT_IDS,
        UNSIGNED_RETAINED_LINUX_ARTIFACT_IDS,
    ):
        _fail("projected retained artifact identities or order drifted")
    expected_retained_platform = (
        "macos"
        if retained_ids == UNSIGNED_RETAINED_ARTIFACT_IDS
        else "linux"
        if retained_ids == UNSIGNED_RETAINED_LINUX_ARTIFACT_IDS
        else None
    )
    if any(
        artifact.get("platform") != expected_retained_platform
        for artifact in retained_artifacts
    ):
        _fail("projected retained artifact platform differs from its exact profile")
    compatibility_rows = compatibility.get("downloads")
    if not isinstance(compatibility_rows, list):
        _fail("projected compatibility retained artifact rows are missing")
    canonical_ids = [
        str(artifact.get("artifactId") or artifact.get("id"))
        for artifact in artifacts
    ]
    compatibility_ids_in_order: list[str] = []
    for index, row in enumerate(compatibility_rows):
        if not isinstance(row, dict):
            _fail(f"projected compatibility artifact[{index}] is invalid")
        artifact_id = row.get("artifactId") or row.get("id")
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or artifact_id in compatibility_ids_in_order
            or row.get("id") != artifact_id
            or row.get("artifactId") not in (None, artifact_id)
        ):
            _fail(f"projected compatibility artifact[{index}] identity drifted")
        compatibility_ids_in_order.append(artifact_id)
    if compatibility_ids_in_order != canonical_ids:
        _fail("projected canonical/compatibility artifact identities drifted")
    retained_compatibility = [
        row
        for row in compatibility_rows
        if isinstance(row, dict) and row.get("fileName") in retained_by_file
    ]
    compatibility_bindings = provenance.get("retainedCompatibilityBindings")
    if (
        not isinstance(compatibility_bindings, list)
        or len(retained_compatibility) != len(retained_artifacts)
        or len(compatibility_bindings) != len(retained_compatibility)
        or provenance.get("retainedCompatibilityBindingsSha256")
        != _ui_compact_sha256(compatibility_bindings)
    ):
        _fail("projected retained compatibility binding set drifted")
    compatibility_ids: set[str] = set()
    for index, (binding, row) in enumerate(
        zip(compatibility_bindings, retained_compatibility, strict=True)
    ):
        canonical_row = retained_by_file[str(row.get("fileName"))]
        artifact_id = canonical_row.get("artifactId") or canonical_row.get("id")
        if (
            not isinstance(binding, dict)
            or set(binding) != UNSIGNED_RETAINED_ARTIFACT_BINDING_KEYS
            or binding.get("artifactId") != artifact_id
            or binding.get("manifestRowSha256") != _ui_compact_sha256(row)
            or binding.get("sha256") != row.get("sha256")
            or binding.get("sizeBytes") != row.get("sizeBytes")
            or row.get("sha256") != canonical_row.get("sha256")
            or row.get("sizeBytes") != canonical_row.get("sizeBytes")
            or not isinstance(artifact_id, str)
            or artifact_id in compatibility_ids
        ):
            _fail(f"projected retained compatibility binding[{index}] drifted")
        compatibility_ids.add(artifact_id)
    if compatibility_ids != set(retained_ids):
        _fail("projected retained canonical/compatibility bindings are not bijective")
    return provenance, retained_ids


def _validate_unsigned_profile_manifest_pair(
    canonical: dict[str, Any],
    compatibility: dict[str, Any],
) -> dict[str, Any]:
    registry_commit: str | None = None
    release_version: str | None = None
    release_proof: dict[str, Any] | None = None
    code_deploy_review: dict[str, Any] | None = None
    retained_provenance: dict[str, Any] | None = None
    retained_artifact_ids: list[str] | None = None
    for label, manifest in (
        ("canonical", canonical),
        ("compatibility", compatibility),
    ):
        if not _unsigned_profile_enabled(manifest, label=f"projected {label} manifest"):
            _fail(f"projected {label} manifest profile is missing")
        _validate_unsigned_profile_recursive_authority(
            manifest, label=f"projected {label} manifest"
        )
        manifest_version = _matching_alias(
            manifest,
            "version",
            "releaseVersion",
            label=f"projected {label} release version",
        )
        manifest_channel = _matching_alias(
            manifest,
            "channel",
            "channelId",
            label=f"projected {label} release channel",
        )
        if (
            manifest_channel != "preview"
            or manifest.get("previewPolicy") != "preview_policy"
            or manifest.get("platformScope") != "windows_only"
            or manifest.get("crossRunBitReproducible") is not False
            or manifest.get("signature") != UNSIGNED_SIGNATURE_POLICY
        ):
            _fail(f"projected {label} root preview identity drifted")
        if release_version is not None and manifest_version != release_version:
            _fail("projected manifest release versions disagree")
        release_version = manifest_version
        commit = _matching_alias(
            manifest,
            "registryCommit",
            "registry_commit",
            label=f"projected {label} Registry commit",
        )
        if COMMIT_RE.fullmatch(commit) is None:
            _fail(f"projected {label} Registry commit is invalid")
        if registry_commit is not None and commit != registry_commit:
            _fail("projected manifest Registry commits disagree")
        registry_commit = commit
        proof = manifest.get("releaseProof")
        generated_at = _matching_alias(
            manifest,
            "generatedAt",
            "generated_at",
            label=f"projected {label} generated time",
        )
        if (
            manifest.get("projectionStage") != "prepared_candidate"
            or manifest.get("status") != "published"
            or manifest.get("releaseDecisionStatus") != "review_required"
            or manifest.get("rolloutState") != "coverage_incomplete"
            or manifest.get("supportabilityState") != "review_required"
            or manifest.get("platformScope") != "windows_only"
            or manifest.get("crossRunBitReproducible") is not False
            or manifest.get("signature") != UNSIGNED_SIGNATURE_POLICY
            or any(
                manifest.get(key) is not False
                for key in (
                    "publicationAuthorized",
                    "publicationEligible",
                    "releaseUploadAuthority",
                    "deployAuthority",
                    "deployAuthorized",
                    "uploadAuthorized",
                    "routeAuthority",
                    "codeDeploymentAuthority",
                )
            )
            or not isinstance(proof, dict)
            or set(proof)
            != {"baseUrl", "generatedAt", "journeysPassed", "proofRoutes", "status"}
            or proof.get("baseUrl") != "https://chummer.run"
            or proof.get("status") != "review_required"
            or proof.get("journeysPassed") != []
            or proof.get("proofRoutes") != []
        ):
            _fail(f"projected {label} manifest review-required posture drifted")
        _timestamp(proof.get("generatedAt"), label=f"projected {label} proof time")
        if proof.get("generatedAt") != generated_at:
            _fail(f"projected {label} proof/generated time drifted")
        if release_proof is not None and proof != release_proof:
            _fail("projected manifest releaseProof documents disagree")
        release_proof = proof

        review = manifest.get("codeDeployCurrentShelfAuthority")
        if (
            not isinstance(review, dict)
            or set(review) != UNSIGNED_CODE_DEPLOY_REVIEW_KEYS
            or review.get("authority") is not False
            or review.get("contract")
            != "chummer.registry.preview-publication-delta-code-deploy-review/v1"
            or review.get("evaluatedAt") != generated_at
            or review.get("projectionProfile") != UNSIGNED_V3_PROJECTION_PROFILE
            or review.get("registryCommit") != commit
            or review.get("status") != "review_required"
            or isinstance(review.get("projectedArtifactCount"), bool)
            or not isinstance(review.get("projectedArtifactCount"), int)
            or review.get("projectedArtifactCount") < 1
        ):
            _fail(f"projected {label} code-deploy review posture drifted")
        for field in (
            "incumbentSnapshotSha256",
            "projectedArtifactInventorySha256",
            "sourceCanonicalManifestSha256",
            "sourceCompatibilityManifestSha256",
            "sourceShelfInventorySha256",
        ):
            if SHA256_RE.fullmatch(str(review.get(field) or "")) is None:
                _fail(f"projected {label} code-deploy review {field} is invalid")
        if code_deploy_review is not None and review != code_deploy_review:
            _fail("projected manifest code-deploy review documents disagree")
        code_deploy_review = review

        provenance = manifest.get("retainedIncumbentProvenance")
        if retained_provenance is not None and provenance != retained_provenance:
            _fail("projected retained incumbent provenance documents disagree")
        if label == "canonical":
            retained_provenance, retained_artifact_ids = (
                _validate_profile_retained_provenance(
                    canonical, compatibility, provenance, review=review
                )
            )
        else:
            if not isinstance(provenance, dict):
                _fail("projected compatibility retained incumbent provenance is invalid")
            retained_provenance = provenance

    retains_macos = retained_artifact_ids == UNSIGNED_RETAINED_ARTIFACT_IDS
    retains_linux = (
        retained_artifact_ids == UNSIGNED_RETAINED_LINUX_ARTIFACT_IDS
    )
    expected_required_platforms = (
        ["macos", "windows"]
        if retains_macos
        else ["linux", "windows"]
        if retains_linux
        else ["windows"]
    )
    expected_required_tuples = (
        ["avalonia:osx-arm64:macos", "avalonia:win-x64:windows"]
        if retains_macos
        else ["avalonia:linux-x64:linux", "avalonia:win-x64:windows"]
        if retains_linux
        else ["avalonia:win-x64:windows"]
    )
    expected_missing_heads = [] if retains_macos or retains_linux else ["avalonia"]
    expected_promoted_platform_tuples = (
        [
            "avalonia:osx-arm64:macos",
            "blazor-desktop:osx-arm64:macos",
        ]
        if retains_macos
        else ["avalonia:linux-x64:linux"]
        if retains_linux
        else []
    )
    expected_promoted_platform_heads = (
        {"macos": ["avalonia", "blazor-desktop"], "windows": []}
        if retains_macos
        else {"linux": ["avalonia"], "windows": []}
        if retains_linux
        else {"windows": []}
    )
    coverage = canonical.get("desktopTupleCoverage")
    if (
        not isinstance(coverage, dict)
        or coverage.get("requiredDesktopPlatforms") != expected_required_platforms
        or coverage.get("requiredDesktopHeads") != ["avalonia"]
        or coverage.get("requiredDesktopPlatformHeadRidTuples")
        != expected_required_tuples
        or coverage.get("missingRequiredHeads") != expected_missing_heads
        or coverage.get("missingRequiredPlatforms") != ["windows"]
        or coverage.get("missingRequiredPlatformHeadPairs") != ["avalonia:windows"]
        or coverage.get("missingRequiredPlatformHeadRidTuples")
        != ["avalonia:win-x64:windows"]
        or coverage.get("promotedPlatformHeadRidTuples")
        != expected_promoted_platform_tuples
        or coverage.get("promotedPlatformHeads")
        != expected_promoted_platform_heads
        or coverage.get("publicationDeltaPlatforms") != ["windows"]
        or coverage.get("complete") is not False
        or coverage.get("routeAuthority") is not False
    ):
        _fail("projected canonical desktop coverage posture drifted")
    promoted_installer_tuples = coverage.get("promotedInstallerTuples")
    if (
        not isinstance(promoted_installer_tuples, list)
        or (
            [
                row.get("artifactId")
                for row in promoted_installer_tuples
                if isinstance(row, dict)
            ]
            != (
                [
                    "avalonia-osx-arm64-installer",
                    "blazor-desktop-osx-arm64-installer",
                ]
                if retains_macos
                else ["avalonia-linux-x64-installer"]
                if retains_linux
                else []
            )
        )
        or any(not isinstance(row, dict) for row in promoted_installer_tuples)
    ):
        _fail("projected canonical promoted installer coverage drifted")
    route_rows = coverage.get("desktopRouteTruth")
    if not isinstance(route_rows, list):
        _fail("projected canonical desktop route truth is missing")
    route_by_tuple = {
        row.get("tupleId"): row for row in route_rows if isinstance(row, dict)
    }
    expected_route_tuples = {
        "avalonia:windows:win-x64",
        "blazor-desktop:windows:win-x64",
    }
    if retains_macos:
        expected_route_tuples.update(
            {
                "avalonia:macos:osx-arm64",
                "blazor-desktop:macos:osx-arm64",
            }
        )
    elif retains_linux:
        expected_route_tuples.update(
            {
                "avalonia:linux:linux-x64",
                "blazor-desktop:linux:linux-x64",
            }
        )
    if (
        any(not isinstance(row, dict) for row in route_rows)
        or len(route_rows) != len(expected_route_tuples)
        or set(route_by_tuple) != expected_route_tuples
    ):
        _fail("projected canonical desktop route tuple set drifted")
    windows_route = route_by_tuple.get("avalonia:windows:win-x64")
    if (
        not isinstance(windows_route, dict)
        or windows_route.get("promotionState") != "proof_required"
        or windows_route.get("routeAuthority") is not False
        or windows_route.get("publicInstallRoute") is not None
        or windows_route.get("installPosture") != "proof_capture_required"
        or windows_route.get("updateEligibility") != "blocked_missing_proof"
    ):
        _fail("projected canonical Windows route is not proof-required")
    for tuple_id in (
        (
            "avalonia:macos:osx-arm64",
            "blazor-desktop:macos:osx-arm64",
        )
        if retains_macos
        else ("avalonia:linux:linux-x64",)
        if retains_linux
        else ()
    ):
        row = route_by_tuple.get(tuple_id)
        if (
            not isinstance(row, dict)
            or row.get("promotionState") != "promoted"
            or row.get("routeAuthority") is not False
            or not isinstance(row.get("publicInstallRoute"), str)
        ):
            _fail("projected canonical retained route posture drifted")
    artifacts = canonical.get("artifacts")
    windows = [
        row
        for row in artifacts or []
        if isinstance(row, dict)
        and row.get("head") == "avalonia"
        and row.get("platform") == "windows"
        and row.get("rid") == RID
    ]
    if len(windows) != 1:
        _fail("projected canonical Windows artifact cardinality drifted")
    windows_artifact = windows[0]
    if (
        release_version is None
        or windows_artifact.get("artifactId")
        != "avalonia-win-x64-installer"
        or windows_artifact.get("id") != "avalonia-win-x64-installer"
        or windows_artifact.get("head") != "avalonia"
        or windows_artifact.get("platform") != "windows"
        or windows_artifact.get("rid") != RID
        or windows_artifact.get("arch") != "x64"
        or windows_artifact.get("kind") != "installer"
        or windows_artifact.get("fileName")
        != "chummer-avalonia-win-x64-installer.exe"
        or windows_artifact.get("payloadFileName")
        != "chummer-avalonia-win-x64-payload.zip"
        or windows_artifact.get("installerMode") != "bootstrap"
        or windows_artifact.get("payloadAcquisitionMode") != "download"
        or windows_artifact.get("channel") != "preview"
        or windows_artifact.get("channelId") != "preview"
        or windows_artifact.get("version") != release_version
        or windows_artifact.get("releaseVersion") != release_version
        or windows_artifact.get("platformScope") != "windows_only"
        or windows_artifact.get("previewPolicy") != "preview_policy"
        or windows_artifact.get("crossRunBitReproducible") is not False
        or windows_artifact.get("signature") != UNSIGNED_SIGNATURE_POLICY
        or windows_artifact.get("publicationDisposition") != "delta"
        or windows_artifact.get("installAccessClass") != "open_public"
        or windows_artifact.get("artifactByteVisibility") != "public"
        or windows_artifact.get("downloadUrl")
        != "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        or windows_artifact.get("payloadDownloadUrl")
        != "/downloads/files/chummer-avalonia-win-x64-payload.zip"
    ):
        _fail("projected canonical Windows public-byte posture drifted")
    compatibility_downloads = compatibility.get("downloads")
    compatibility_windows = [
        row
        for row in compatibility_downloads or []
        if isinstance(row, dict)
        and (row.get("artifactId") or row.get("id"))
        == "avalonia-win-x64-installer"
    ]
    if (
        not isinstance(compatibility_downloads, list)
        or len(compatibility_windows) != 1
        or compatibility_windows[0].get("artifactId")
        != "avalonia-win-x64-installer"
        or compatibility_windows[0].get("id") != "avalonia-win-x64-installer"
        or compatibility_windows[0].get("head") != "avalonia"
        or compatibility_windows[0].get("platform") != "windows"
        or compatibility_windows[0].get("platformId") != "windows-x64"
        or compatibility_windows[0].get("arch") != "x64"
        or compatibility_windows[0].get("kind") != "installer"
        or compatibility_windows[0].get("channel") != "preview"
        or compatibility_windows[0].get("channelId") != "preview"
        or compatibility_windows[0].get("version") != release_version
        or compatibility_windows[0].get("releaseVersion") != release_version
        or compatibility_windows[0].get("platformScope") != "windows_only"
        or compatibility_windows[0].get("previewPolicy") != "preview_policy"
        or compatibility_windows[0].get("crossRunBitReproducible") is not False
        or compatibility_windows[0].get("signature") != UNSIGNED_SIGNATURE_POLICY
        or compatibility_windows[0].get("publicationDisposition") != "delta"
        or compatibility_windows[0].get("url")
        != "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        or compatibility_windows[0].get("downloadUrl")
        != "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        or compatibility_windows[0].get("payloadDownloadUrl")
        != "/downloads/files/chummer-avalonia-win-x64-payload.zip"
        or compatibility_windows[0].get("fileName")
        != "chummer-avalonia-win-x64-installer.exe"
        or compatibility_windows[0].get("payloadFileName")
        != "chummer-avalonia-win-x64-payload.zip"
        or compatibility_windows[0].get("installAccessClass") != "open_public"
        or compatibility_windows[0].get("sha256")
        != windows_artifact.get("sha256")
        or compatibility_windows[0].get("sizeBytes")
        != windows_artifact.get("sizeBytes")
        or compatibility_windows[0].get("payloadSha256")
        != windows_artifact.get("payloadSha256")
        or compatibility_windows[0].get("payloadSizeBytes")
        != windows_artifact.get("payloadSizeBytes")
    ):
        _fail("projected compatibility Windows public-byte posture drifted")
    _artifacts, projected_inventory = _profile_artifact_inventory_rows(
        canonical, label="projected canonical manifest"
    )
    if (
        registry_commit is None
        or code_deploy_review is None
        or retained_provenance is None
        or retained_artifact_ids is None
        or code_deploy_review.get("projectedArtifactCount")
        != len(projected_inventory)
        or code_deploy_review.get("projectedArtifactInventorySha256")
        != _ui_compact_sha256(projected_inventory)
    ):
        _fail("projected manifest artifact inventory review binding drifted")
    return {
        "registryCommit": registry_commit,
        "codeDeployReview": code_deploy_review,
        "retainedProvenance": retained_provenance,
        "retainedArtifactIds": retained_artifact_ids,
    }


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


def _unsigned_native_source(
    value: object,
    *,
    label: str,
    workflow: str,
) -> dict[str, Any]:
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
    if (
        value.get("repository") != UI_REPOSITORY
        or value.get("workflow") != workflow
        or value.get("ref") != PRODUCER_REF
        or not isinstance(value.get("sha"), str)
        or COMMIT_RE.fullmatch(value["sha"]) is None
    ):
        _fail(f"{label} repository/workflow/source revision drifted")
    run_id = _github_positive_integer(value.get("runId"), label=f"{label} runId")
    run_attempt = _github_positive_integer(
        value.get("runAttempt"), label=f"{label} runAttempt"
    )
    actor = value.get("actor")
    artifact_name = value.get("artifactName")
    if workflow == UNSIGNED_CAPTURE_WORKFLOW:
        if actor != "github-actions[bot]":
            _fail(f"{label} actor is invalid")
        expected_artifact = (
            f"unsigned-windows-preview-native-evidence-{run_id}-{run_attempt}"
        )
    else:
        if not isinstance(actor, str) or REVIEWER_RE.fullmatch(actor) is None:
            _fail(f"{label} actor is invalid")
        expected_artifact = (
            "unsigned-windows-preview-native-evidence-finalized-"
            f"{run_id}-{run_attempt}"
        )
    if artifact_name != expected_artifact:
        _fail(f"{label} artifact identity drifted")
    return value


def _decode_unsigned_native_files(
    value: object,
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > MAX_EVIDENCE_FILES
    ):
        _fail("unsigned native finalized files must be a bounded non-empty list")
    rows: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for index, row in enumerate(value):
        if not isinstance(row, dict) or set(row) != {
            "path",
            "sha256",
            "sizeBytes",
            "bytesBase64",
        }:
            _fail(f"unsigned native finalized file row {index} drifted")
        path = _validate_relative_path(
            row.get("path"),
            label=f"unsigned native finalized file row {index} path",
        )
        digest = _sha256(
            row.get("sha256"),
            label=f"unsigned native finalized file row {index} sha256",
        )
        size = _positive_int(
            row.get("sizeBytes"),
            label=f"unsigned native finalized file row {index} sizeBytes",
            allow_zero=True,
        )
        encoded = row.get("bytesBase64")
        if not isinstance(encoded, str):
            _fail(f"unsigned native finalized file row {index} bytes are missing")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise CandidateAuthorityBlocked(
                f"unsigned native finalized file row {index} is not strict base64"
            ) from exc
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
            _fail(
                f"unsigned native finalized file row {index} byte binding drifted"
            )
        if path in payloads:
            _fail("unsigned native finalized file paths are not unique")
        rows.append({"path": path, "sha256": digest, "sizeBytes": size})
        payloads[path] = payload
    if rows != sorted(rows, key=lambda row: row["path"]):
        _fail("unsigned native finalized file rows are not sorted")
    return rows, payloads


def _derive_embedded_unsigned_native_installed_executable(
    evidence: object,
    *,
    scope: dict[str, Any],
) -> dict[str, Any]:
    """Derive the sealed executable identity from exact embedded v4 custody."""

    if (
        not isinstance(evidence, dict)
        or scope.get("heads") != ("avalonia",)
        or not isinstance(scope.get("artifacts"), dict)
        or set(scope["artifacts"]) != {"avalonia"}
    ):
        _fail("unsigned embedded startup executable scope drifted")
    artifacts = scope["artifacts"]["avalonia"]
    if (
        not isinstance(artifacts, dict)
        or set(artifacts) != {"installer", "payload"}
        or not isinstance(artifacts.get("installer"), dict)
        or not isinstance(artifacts.get("payload"), dict)
        or artifacts["installer"].get("path")
        != "files/chummer-avalonia-win-x64-installer.exe"
        or artifacts["installer"].get("fileName")
        != "chummer-avalonia-win-x64-installer.exe"
        or artifacts["payload"].get("path")
        != "files/chummer-avalonia-win-x64-payload.zip"
        or artifacts["payload"].get("fileName")
        != "chummer-avalonia-win-x64-payload.zip"
    ):
        _fail("unsigned embedded startup executable scope drifted")

    _rows, payloads = _decode_unsigned_native_files(evidence.get("files"))
    capture = _native_json(
        payloads,
        UNSIGNED_NATIVE_CAPTURE_FILE,
        label="unsigned embedded native capture manifest",
    )
    native_evidence = capture.get("nativeEvidence")
    startup_visual_binding = (
        native_evidence.get("startupVisual")
        if isinstance(native_evidence, dict)
        else None
    )
    capture_executable = (
        startup_visual_binding.get("installedExecutable")
        if isinstance(startup_visual_binding, dict)
        else None
    )
    startup_visual_path = (
        "startup-visual/"
        "windows-application-avalonia-win-x64-startup.receipt.json"
    )
    startup_visual = _native_json(
        payloads,
        startup_visual_path,
        label="unsigned embedded startup visual receipt",
    )
    receipt_executable = startup_visual.get("installedExecutable")

    expected_keys = {"fileName", "payloadEntry", "sha256", "sizeBytes"}
    for value, label in (
        (capture_executable, "capture manifest"),
        (receipt_executable, "startup visual receipt"),
    ):
        if (
            not isinstance(value, dict)
            or set(value) != expected_keys
            or value.get("fileName") != "Chummer.Avalonia.exe"
            or value.get("payloadEntry") != "Chummer.Avalonia.exe"
        ):
            _fail(f"unsigned embedded {label} executable identity drifted")
        _sha256(
            value.get("sha256"),
            label=f"unsigned embedded {label} executable sha256",
        )
        _positive_int(
            value.get("sizeBytes"),
            label=f"unsigned embedded {label} executable sizeBytes",
        )
    if capture_executable != receipt_executable:
        _fail("unsigned embedded startup executable custody copies differ")
    return dict(capture_executable)


def _native_json(
    payloads: dict[str, bytes],
    path: str,
    *,
    label: str,
) -> dict[str, Any]:
    payload = payloads.get(path)
    if payload is None:
        _fail(f"{label} is absent from finalized native custody")
    return _strict_json_bytes(payload, label=label)


def _native_payload_row(
    payloads: dict[str, bytes],
    path: str,
) -> dict[str, Any]:
    payload = payloads[path]
    return {
        "path": path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "sizeBytes": len(payload),
    }


def _validate_native_policy(value: object, *, label: str) -> None:
    if value != {
        "authenticodeRequired": False,
        "evidenceOnly": True,
        "releaseChannel": "preview",
        "signingRequirement": "preview_unsigned_allowed",
    }:
        _fail(f"{label} policy drifted")


def _validate_native_no_authority(value: dict[str, Any], *, label: str) -> None:
    if any(
        value.get(field) is not False
        for field in (
            "deployAuthorized",
            "publicationAuthorized",
            "uiUploadAuthorized",
            "uploadAuthorized",
        )
    ):
        _fail(f"{label} gained publication authority")


def _validate_native_full_source(
    value: object,
    projection: dict[str, Any],
    *,
    label: str,
    expected_actor: str,
) -> dict[str, Any]:
    expected_keys = set(projection) | {"rerunPolicy", "triggeringActor"}
    if not isinstance(value, dict) or set(value) != expected_keys:
        _fail(f"{label} source property set drifted")
    if any(value.get(key) != projection[key] for key in projection):
        _fail(f"{label} source differs from finalized provenance")
    if (
        value.get("rerunPolicy") != "same-actor-only"
        or value.get("actor") != expected_actor
        or value.get("triggeringActor") != expected_actor
    ):
        _fail(f"{label} actor or rerun policy drifted")
    return value


def _validate_native_byte_reference(
    value: object,
    *,
    expected_path: str,
    payloads: dict[str, bytes],
    label: str,
) -> dict[str, Any]:
    reference = _byte_reference(
        value,
        label=label,
        expected_path=expected_path,
    )
    if reference != _native_payload_row(payloads, expected_path):
        _fail(f"{label} bytes drifted")
    return reference


def _validate_native_digest_reference(
    value: object,
    *,
    expected_path: str,
    payloads: dict[str, bytes],
    label: str,
) -> None:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        _fail(f"{label} reference drifted")
    if (
        value.get("path") != expected_path
        or _sha256(value.get("sha256"), label=f"{label} sha256")
        != hashlib.sha256(payloads[expected_path]).hexdigest()
    ):
        _fail(f"{label} bytes drifted")


def _validate_native_authenticode_reference(
    value: object,
    *,
    expected_path: str,
    payloads: dict[str, bytes],
    label: str,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "path",
        "sha256",
        "signatureStatus",
        "signingRequired",
        "sizeBytes",
        "unsignedReason",
    }:
        _fail(f"{label} reference drifted")
    if (
        value.get("signatureStatus") != "unsigned"
        or value.get("signingRequired") is not False
        or value.get("unsignedReason") != "preview_policy"
    ):
        _fail(f"{label} unsigned policy drifted")
    _validate_native_byte_reference(
        {
            key: value[key]
            for key in ("path", "sha256", "sizeBytes")
        },
        expected_path=expected_path,
        payloads=payloads,
        label=label,
    )


def _validate_png(payload: bytes, *, label: str) -> tuple[int, int]:
    if len(payload) < 57 or payload[:8] != b"\x89PNG\r\n\x1a\n":
        _fail(f"{label} screenshot is not a complete PNG")
    offset = 8
    width = height = 0
    bit_depth = color_type = -1
    saw_ihdr = saw_idat = saw_iend = False
    compressed = bytearray()
    while offset < len(payload):
        if offset + 12 > len(payload):
            _fail(f"{label} PNG chunk framing drifted")
        length = int.from_bytes(payload[offset : offset + 4], "big")
        chunk_type = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            _fail(f"{label} PNG chunk length drifted")
        chunk_data = payload[data_start:data_end]
        expected_crc = int.from_bytes(payload[data_end:crc_end], "big")
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            _fail(f"{label} PNG chunk CRC drifted")
        if not saw_ihdr:
            if chunk_type != b"IHDR" or length != 13:
                _fail(f"{label} PNG IHDR drifted")
            width = int.from_bytes(chunk_data[0:4], "big")
            height = int.from_bytes(chunk_data[4:8], "big")
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
            if (
                chunk_data[10] != 0
                or chunk_data[11] != 0
                or chunk_data[12] != 0
            ):
                _fail(f"{label} PNG encoding mode drifted")
            saw_ihdr = True
        elif chunk_type == b"IHDR":
            _fail(f"{label} PNG repeats IHDR")
        elif chunk_type == b"IDAT":
            if saw_iend:
                _fail(f"{label} PNG data follows IEND")
            saw_idat = True
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            if length != 0 or not saw_idat or crc_end != len(payload):
                _fail(f"{label} PNG IEND drifted")
            saw_iend = True
        offset = crc_end
    if not saw_ihdr or not saw_idat or not saw_iend:
        _fail(f"{label} PNG is incomplete")
    if not 320 <= width <= 16_384 or not 200 <= height <= 16_384:
        _fail(f"{label} screenshot PNG dimensions drifted")
    channel_counts = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    valid_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if color_type not in channel_counts or bit_depth not in valid_depths[color_type]:
        _fail(f"{label} PNG color encoding drifted")
    row_bytes = (
        width * channel_counts[color_type] * bit_depth + 7
    ) // 8
    expected_decoded_size = (row_bytes + 1) * height
    if expected_decoded_size > 256 * 1024 * 1024:
        _fail(f"{label} PNG decoded size is unbounded")
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(
            bytes(compressed),
            expected_decoded_size + 1,
        )
        if (
            len(decoded) > expected_decoded_size
            or decompressor.unconsumed_tail
        ):
            _fail(f"{label} PNG decoded data exceeds its IHDR")
        decoded += decompressor.flush(
            expected_decoded_size + 1 - len(decoded)
        )
    except zlib.error as exc:
        raise CandidateAuthorityBlocked(
            f"{label} PNG image data is invalid"
        ) from exc
    if (
        not decompressor.eof
        or decompressor.unused_data
        or len(decoded) != expected_decoded_size
        or any(
            decoded[offset] > 4
            for offset in range(0, len(decoded), row_bytes + 1)
        )
    ):
        _fail(f"{label} PNG decoded scanlines drifted")
    return width, height


def _validate_native_screenshot(
    value: object,
    *,
    expected_path: str,
    expected_role: str | None,
    payloads: dict[str, bytes],
    label: str,
    include_dimensions: bool,
) -> None:
    expected_keys = {"path", "sha256"}
    if expected_role is not None:
        expected_keys.add("role")
    if include_dimensions:
        expected_keys.update({"width", "height"})
    if not isinstance(value, dict) or set(value) != expected_keys:
        _fail(f"{label} screenshot binding drifted")
    if (
        value.get("path") != expected_path
        or _sha256(value.get("sha256"), label=f"{label} sha256")
        != hashlib.sha256(payloads[expected_path]).hexdigest()
        or expected_role is not None
        and value.get("role") != expected_role
    ):
        _fail(f"{label} screenshot bytes drifted")
    actual_width, actual_height = _validate_png(
        payloads[expected_path],
        label=label,
    )
    if include_dimensions:
        width = _positive_int(value.get("width"), label=f"{label} width")
        height = _positive_int(value.get("height"), label=f"{label} height")
        if width != actual_width or height != actual_height:
            _fail(f"{label} screenshot dimensions drifted")


def _validate_native_host(
    value: object,
    *,
    label: str,
    expected_evidence_sources: frozenset[str] = frozenset(
        {"GitHub-hosted windows-latest"}
    ),
) -> None:
    if not isinstance(value, dict) or set(value) not in (
        {
            "contractName",
            "evidenceSource",
            "hostPlatform",
            "isNativeWindows",
            "runner",
            "status",
        },
        {
            "contractName",
            "evidenceSource",
            "hostKernel",
            "hostPlatform",
            "isNativeWindows",
            "runner",
            "status",
        },
    ):
        _fail(f"{label} native-host property set drifted")
    if (
        value.get("contractName") != "chummer6-ui.native_windows_host_evidence"
        or value.get("evidenceSource") not in expected_evidence_sources
        or value.get("hostPlatform") != "windows"
        or value.get("isNativeWindows") is not True
        or value.get("runner") not in {"pwsh", "powershell.exe"}
        or value.get("status") != "verified"
    ):
        _fail(f"{label} is not exact native-Windows evidence")
    if "hostKernel" in value and (
        not isinstance(value["hostKernel"], str) or not value["hostKernel"].strip()
    ):
        _fail(f"{label} native host kernel drifted")
    if value.get("evidenceSource") == "host_kernel_and_runner_selection":
        if (
            "hostKernel" not in value
            or value.get("runner") != "pwsh"
            or re.fullmatch(
                r"(?:MINGW64|MSYS|CYGWIN)_NT-[0-9]+\.[0-9]+"
                r"(?:-[0-9]+)?",
                value["hostKernel"],
            )
            is None
        ):
            _fail(f"{label} current native host kernel drifted")


def _validate_native_inventory(
    document: dict[str, Any],
    *,
    expected_contract: str,
    expected_status: str,
    expected_paths: set[str],
    payloads: dict[str, bytes],
    label: str,
    extra_keys: set[str],
) -> list[dict[str, Any]]:
    if set(document) != {
        "contractName",
        "contractVersion",
        "deployAuthorized",
        "files",
        "policy",
        "publicationAuthorized",
        "status",
        "uiUploadAuthorized",
        "uploadAuthorized",
        *extra_keys,
    }:
        _fail(f"{label} property set drifted")
    if (
        document.get("contractName") != expected_contract
        or type(document.get("contractVersion")) is not int
        or document.get("contractVersion") != 1
        or document.get("status") != expected_status
    ):
        _fail(f"{label} identity drifted")
    _validate_native_policy(document.get("policy"), label=label)
    _validate_native_no_authority(document, label=label)
    rows = _inventory_rows(document.get("files"), label=label)
    expected_rows = [
        _native_payload_row(payloads, path)
        for path in sorted(expected_paths)
    ]
    if rows != expected_rows:
        _fail(f"{label} differs from exact finalized leaf bytes")
    return rows


def _validate_unsigned_native_logs(
    payloads: dict[str, bytes],
    *,
    head: str,
) -> None:
    startup_path = f"startup-smoke/startup-smoke-{head}-{RID}.log"
    startup_receipt_path = (
        f"startup-smoke/startup-smoke-{head}-{RID}.receipt.json"
    )
    payload_http_path = (
        f"startup-smoke/startup-smoke-payload-http-{head}-{RID}.log"
    )
    startup_receipt = _native_json(
        payloads,
        startup_receipt_path,
        label="unsigned native startup receipt",
    )
    current_dialect = "verificationScope" in startup_receipt
    paths_and_markers = {
        startup_path: [],
        payload_http_path: [],
        f"startup-smoke/windows-installer-progress-{head}-{RID}.log": [
            "Bootstrap temp root:",
            "Payload download target:",
            "Downloading application files",
            "Verifying payload size",
            "Verifying payload checksum",
            "Extracting application files",
            "Install complete",
        ],
    }
    for path, markers in paths_and_markers.items():
        payload = payloads[path]
        if not payload.endswith(b"\n") or len(payload) > 1024 * 1024:
            _fail(f"unsigned native log {path} framing drifted")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidateAuthorityBlocked(
                f"unsigned native log {path} is not UTF-8"
            ) from exc
        if any(
            ord(character) < 0x20 and character not in "\r\n\t"
            for character in text
        ):
            _fail(f"unsigned native log {path} contains control bytes")
        lines = text.splitlines()
        if path == startup_path:
            expected_marker = (
                f"startup smoke ready: head={head} platform=windows "
                "arch=x64 checkpoint=pre_ui_event_loop"
                if current_dialect
                else "native startup passed"
            )
            if expected_marker not in lines:
                _fail(
                    f"unsigned native log {path} omits a recognized "
                    "startup-ready marker"
                )
        if path == payload_http_path:
            if current_dialect:
                current_pattern = re.compile(
                    r"127\.0\.0\.1 - - "
                    r"\[[0-9]{2}/[A-Z][a-z]{2}/[0-9]{4} "
                    r"[0-9]{2}:[0-9]{2}:[0-9]{2}\] "
                    rf'"GET /chummer-{re.escape(head)}-{RID}-payload\.zip '
                    r'HTTP/1\.1" 200 -'
                )
                payload_download_passed = any(
                    current_pattern.fullmatch(line) is not None
                    for line in lines
                )
            else:
                payload_download_passed = (
                    "candidate payload download passed" in lines
                )
            if not payload_download_passed:
                _fail(
                    f"unsigned native log {path} omits a recognized "
                    "payload-download success marker"
                )
        offset = 0
        for marker in markers:
            marker_offset = text.find(marker, offset)
            if marker_offset < 0:
                _fail(f"unsigned native log {path} omits {marker!r}")
            offset = marker_offset + len(marker)


def _validate_unsigned_native_startup_receipt(
    startup: dict[str, Any],
    *,
    head: str,
    scope: dict[str, Any],
    expected_installed_executable: dict[str, Any] | None,
    now: datetime,
    max_age: timedelta,
) -> None:
    legacy_keys = {
        "artifactDigest",
        "artifactFileName",
        "bootstrapPayloadAcquisitionMode",
        "bootstrapPayloadFileName",
        "bootstrapPayloadSha256",
        "bootstrapPayloadSizeBytes",
        "channelId",
        "executionEnvironment",
        "headId",
        "nativeHostEvidence",
        "platform",
        "readyCheckpoint",
        "releaseVersion",
        "rid",
        "status",
    }
    current_keys = legacy_keys | {
        "arch",
        "artifactDigestSource",
        "artifactId",
        "artifactInstallMode",
        "artifactPath",
        "artifactPathDisclosure",
        "artifactRelativePath",
        "artifactSha256",
        "bootstrapPayloadDownloadUrl",
        "completedAtUtc",
        "fileName",
        "framework",
        "hostClass",
        "installLinkingInstallationId",
        "installLinkingLaunchCount",
        "installLinkingPromptReason",
        "installLinkingPromptRequired",
        "installLinkingStatus",
        "operatingSystem",
        "processPath",
        "processPathDisclosure",
        "recordedAtUtc",
        "startedAtUtc",
        "verificationScope",
        "version",
    }
    startup_keys = set(startup)
    if startup_keys not in (legacy_keys, current_keys):
        _fail("unsigned native startup receipt property set drifted")

    artifacts = scope["artifacts"][head]
    installer = artifacts["installer"]
    payload = artifacts["payload"]
    if (
        startup.get("status") != "pass"
        or startup.get("readyCheckpoint") != "pre_ui_event_loop"
        or startup.get("executionEnvironment") != "native_windows"
        or startup.get("headId") != head
        or startup.get("platform") != "windows"
        or startup.get("rid") != RID
        or startup.get("releaseVersion") != scope["version"]
        or startup.get("channelId") != scope["channel"]
        or startup.get("artifactFileName") != installer["fileName"]
        or startup.get("artifactDigest")
        != f"sha256:{installer['sha256']}"
        or startup.get("bootstrapPayloadAcquisitionMode") != "download"
        or startup.get("bootstrapPayloadFileName") != payload["fileName"]
        or startup.get("bootstrapPayloadSha256") != payload["sha256"]
        or startup.get("bootstrapPayloadSizeBytes") != payload["sizeBytes"]
    ):
        _fail("unsigned native startup receipt drifted")

    if startup_keys == current_keys:
        installer_path = f"files/{installer['fileName']}"
        payload_url = startup.get("bootstrapPayloadDownloadUrl")
        payload_url_match = (
            re.fullmatch(
                rf"http://127\.0\.0\.1:([1-9][0-9]{{0,4}})/"
                rf"{re.escape(payload['fileName'])}",
                payload_url,
            )
            if isinstance(payload_url, str)
            else None
        )
        expected_process = (
            expected_installed_executable.get("fileName")
            if isinstance(expected_installed_executable, dict)
            else None
        )
        if (
            not isinstance(expected_process, str)
            or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.exe",
                expected_process,
                flags=re.IGNORECASE,
            )
            is None
            or startup.get("arch") != "x64"
            or startup.get("version") != scope["version"]
            or startup.get("hostClass")
            != "github-hosted-windows-latest-native"
            or startup.get("verificationScope") != "native_windows_startup"
            or startup.get("artifactDigestSource") != "environment"
            or startup.get("artifactInstallMode")
            != "nsis_bootstrap_installer"
            or startup.get("artifactPath") != installer_path
            or startup.get("artifactPathDisclosure")
            != "artifact_shelf_relative_path"
            or startup.get("artifactRelativePath") != installer_path
            or startup.get("artifactSha256") != installer["sha256"]
            or startup.get("fileName") != installer["fileName"]
            or startup.get("artifactId") != f"{head}-{RID}-installer"
            or payload_url_match is None
            or int(payload_url_match.group(1)) > 65535
            or startup.get("processPathDisclosure") != "file_name_only"
            or startup.get("processPath") != expected_process
            or not isinstance(startup.get("framework"), str)
            or re.fullmatch(
                r"\.NET [0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?",
                startup["framework"],
            )
            is None
            or not isinstance(startup.get("operatingSystem"), str)
            or re.fullmatch(
                r"Microsoft Windows [0-9]+(?:\.[0-9]+){1,3}",
                startup["operatingSystem"],
            )
            is None
            or startup.get("installLinkingStatus") != "guest"
            or startup.get("installLinkingPromptRequired") is not True
            or startup.get("installLinkingPromptReason") != "claim_required"
            or type(startup.get("installLinkingLaunchCount")) is not int
            or startup.get("installLinkingLaunchCount") != 1
            or not isinstance(
                startup.get("installLinkingInstallationId"), str
            )
            or re.fullmatch(
                r"ins-[0-9a-f]{32}",
                startup["installLinkingInstallationId"],
            )
            is None
        ):
            _fail("unsigned native current startup receipt drifted")
        started = _fresh_timestamp(
            startup.get("startedAtUtc"),
            label="unsigned native startup startedAtUtc",
            now=now,
            max_age=max_age,
        )
        recorded = _fresh_timestamp(
            startup.get("recordedAtUtc"),
            label="unsigned native startup recordedAtUtc",
            now=now,
            max_age=max_age,
        )
        completed = _fresh_timestamp(
            startup.get("completedAtUtc"),
            label="unsigned native startup completedAtUtc",
            now=now,
            max_age=max_age,
        )
        if (
            not started <= recorded <= completed
            or completed - started > timedelta(minutes=10)
        ):
            _fail("unsigned native startup timestamp sequence drifted")
        expected_sources = frozenset({"host_kernel_and_runner_selection"})
    else:
        expected_sources = frozenset({"GitHub-hosted windows-latest"})

    _validate_native_host(
        startup.get("nativeHostEvidence"),
        label="unsigned startup receipt",
        expected_evidence_sources=expected_sources,
    )


def _validate_unsigned_native_graph(
    *,
    payloads: dict[str, bytes],
    scope: dict[str, Any],
    content_rows: list[dict[str, Any]],
    capture_source: dict[str, Any],
    finalization_source: dict[str, Any],
    reviewer: str,
    capture_generated_at: object,
    finalization_generated_at: object,
    publication_source_sha: str,
    expected_installed_executable: dict[str, Any] | None,
    now: datetime,
    max_age: timedelta,
) -> dict[str, Any]:
    capture = _native_json(
        payloads,
        UNSIGNED_NATIVE_CAPTURE_FILE,
        label="unsigned native capture manifest",
    )
    capture_inventory = _native_json(
        payloads,
        UNSIGNED_NATIVE_CAPTURE_INVENTORY_FILE,
        label="unsigned native capture inventory",
    )
    finalization = _native_json(
        payloads,
        UNSIGNED_NATIVE_FINALIZATION_FILE,
        label="unsigned native finalization",
    )
    finalized_inventory = _native_json(
        payloads,
        UNSIGNED_NATIVE_FINALIZED_INVENTORY_FILE,
        label="unsigned native finalized inventory",
    )
    visual_paths = {
        f"UNSIGNED_WINDOWS_PREVIEW_VISUAL_PROOF-{head}-{RID}.generated.json"
        for head in scope["heads"]
    }
    for head in scope["heads"]:
        _validate_unsigned_native_logs(payloads, head=head)
    finalized_paths = set(payloads) - {
        UNSIGNED_NATIVE_FINALIZED_INVENTORY_FILE
    }
    _validate_native_inventory(
        finalized_inventory,
        expected_contract=(
            "chummer6-ui.unsigned-preview-native-windows-finalized-inventory"
        ),
        expected_status="passed",
        expected_paths=finalized_paths,
        payloads=payloads,
        label="unsigned native finalized inventory",
        extra_keys={"captureInventorySha256", "finalization"},
    )
    capture_inventory_digest = hashlib.sha256(
        payloads[UNSIGNED_NATIVE_CAPTURE_INVENTORY_FILE]
    ).hexdigest()
    if (
        _sha256(
            finalized_inventory.get("captureInventorySha256"),
            label="unsigned finalized capture inventory sha256",
        )
        != capture_inventory_digest
    ):
        _fail("unsigned finalized inventory capture binding drifted")
    _validate_native_byte_reference(
        finalized_inventory.get("finalization"),
        expected_path=UNSIGNED_NATIVE_FINALIZATION_FILE,
        payloads=payloads,
        label="unsigned finalized finalization",
    )

    capture_paths = finalized_paths - {
        UNSIGNED_NATIVE_CAPTURE_INVENTORY_FILE,
        UNSIGNED_NATIVE_FINALIZATION_FILE,
        *visual_paths,
    }
    _validate_native_inventory(
        capture_inventory,
        expected_contract=(
            "chummer6-ui.unsigned-preview-native-windows-capture-inventory"
        ),
        expected_status="captured",
        expected_paths=capture_paths,
        payloads=payloads,
        label="unsigned native capture inventory",
        extra_keys={"captureManifest"},
    )
    _validate_native_byte_reference(
        capture_inventory.get("captureManifest"),
        expected_path=UNSIGNED_NATIVE_CAPTURE_FILE,
        payloads=payloads,
        label="unsigned capture manifest",
    )

    finalization_keys = {
        "accountableReviewConfirmed",
        "authenticodeVerification",
        "captureArtifact",
        "captureInventorySha256",
        "captureSource",
        "confirmations",
        "contractName",
        "contractVersion",
        "deployAuthorized",
        "finalizationSource",
        "generatedAt",
        "policy",
        "proofs",
        "publicationAuthorized",
        "reviewer",
        "reviewerKind",
        "reviewerWasCaptureActor",
        "status",
        "uiUploadAuthorized",
        "uploadAuthorized",
    }
    if set(finalization) != finalization_keys:
        _fail("unsigned native finalization property set drifted")
    if (
        finalization.get("contractName")
        != "chummer6-ui.unsigned-preview-native-windows-finalization"
        or type(finalization.get("contractVersion")) is not int
        or finalization.get("contractVersion") != 1
        or finalization.get("status") != "passed"
        or finalization.get("accountableReviewConfirmed") is not True
        or finalization.get("reviewer") != reviewer
        or finalization.get("reviewerKind")
        != "authenticated_account_owner_delegated_operator"
        or finalization.get("reviewerWasCaptureActor") is not False
        or finalization.get("generatedAt") != finalization_generated_at
        or finalization.get("confirmations")
        != {
            "clipping": "passed",
            "completion": "passed",
            "contrast": "passed",
            "progress": "passed",
            "readability": "passed",
            "startup": "passed",
        }
    ):
        _fail("unsigned native accountable finalization drifted")
    _validate_native_policy(finalization.get("policy"), label="unsigned finalization")
    _validate_native_no_authority(finalization, label="unsigned finalization")
    _validate_native_full_source(
        finalization.get("captureSource"),
        capture_source,
        label="unsigned finalization capture",
        expected_actor="github-actions[bot]",
    )
    _validate_native_full_source(
        finalization.get("finalizationSource"),
        finalization_source,
        label="unsigned finalization reviewer",
        expected_actor=reviewer,
    )
    if (
        _sha256(
            finalization.get("captureInventorySha256"),
            label="unsigned finalization capture inventory sha256",
        )
        != capture_inventory_digest
    ):
        _fail("unsigned finalization capture inventory binding drifted")
    capture_artifact = finalization.get("captureArtifact")
    if (
        not isinstance(capture_artifact, dict)
        or set(capture_artifact) != {"id", "name", "sha256"}
        or _positive_int(
            int(capture_artifact["id"])
            if isinstance(capture_artifact.get("id"), str)
            and capture_artifact["id"].isdigit()
            else capture_artifact.get("id"),
            label="unsigned capture artifact id",
        )
        < 1
        or capture_artifact.get("name") != capture_source["artifactName"]
    ):
        _fail("unsigned finalization capture artifact drifted")
    _sha256(
        capture_artifact.get("sha256"),
        label="unsigned capture artifact sha256",
    )
    auth_path = (
        "authenticode/"
        "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"
    )
    _validate_native_authenticode_reference(
        finalization.get("authenticodeVerification"),
        expected_path=auth_path,
        payloads=payloads,
        label="unsigned finalization Authenticode",
    )
    proofs = finalization.get("proofs")
    if not isinstance(proofs, list) or len(proofs) != len(scope["heads"]):
        _fail("unsigned finalization visual proof scope drifted")
    for proof, head in zip(proofs, scope["heads"], strict=True):
        expected_path = (
            f"UNSIGNED_WINDOWS_PREVIEW_VISUAL_PROOF-{head}-{RID}.generated.json"
        )
        if not isinstance(proof, dict) or set(proof) != {
            "headId",
            "path",
            "sha256",
        }:
            _fail("unsigned finalization visual proof binding drifted")
        if (
            proof.get("headId") != head
            or proof.get("path") != expected_path
            or _sha256(
                proof.get("sha256"),
                label="unsigned finalization visual proof sha256",
            )
            != hashlib.sha256(payloads[expected_path]).hexdigest()
        ):
            _fail("unsigned finalization visual proof bytes drifted")

    capture_keys = {
        "authenticodeVerification",
        "candidate",
        "captureMode",
        "contractName",
        "contractVersion",
        "deployAuthorized",
        "generatedAt",
        "heads",
        "nativeEvidence",
        "policy",
        "preservedCandidateFiles",
        "publicationAuthorized",
        "source",
        "status",
        "uiUploadAuthorized",
        "uploadAuthorized",
    }
    if set(capture) != capture_keys:
        _fail("unsigned native capture property set drifted")
    if (
        capture.get("contractName")
        != "chummer6-ui.unsigned-preview-native-windows-capture"
        or type(capture.get("contractVersion")) is not int
        or capture.get("contractVersion") != 1
        or capture.get("status") != "captured"
        or capture.get("captureMode") != "hosted_native_windows"
        or capture.get("generatedAt") != capture_generated_at
    ):
        _fail("unsigned native capture identity drifted")
    _validate_native_policy(capture.get("policy"), label="unsigned capture")
    _validate_native_no_authority(capture, label="unsigned capture")
    capture_full_source = _validate_native_full_source(
        capture.get("source"),
        capture_source,
        label="unsigned capture",
        expected_actor="github-actions[bot]",
    )
    _validate_native_authenticode_reference(
        capture.get("authenticodeVerification"),
        expected_path=auth_path,
        payloads=payloads,
        label="unsigned capture Authenticode",
    )

    content_by_path = {row["path"]: row for row in content_rows}
    capture_candidate = capture.get("candidate")
    if not isinstance(capture_candidate, dict) or set(capture_candidate) != {
        "artifact",
        "compositionRequest",
        "contentInventory",
        "exportReceipt",
        "installer",
        "manifest",
        "payload",
        "platformScope",
        "release",
        "signature",
        "source",
        "sourceSha",
        "validatedInventoryFileCount",
        "validatedProposalSha256",
        "validatedProposalSourceSha",
    }:
        _fail("unsigned capture candidate binding drifted")
    if (
        capture_candidate.get("platformScope") != "windows_only"
        or capture_candidate.get("release")
        != {"channel": scope["channel"], "version": scope["version"]}
        or capture_candidate.get("signature") != UNSIGNED_SIGNATURE_POLICY
        or capture_candidate.get("sourceSha") != publication_source_sha
        or capture_candidate.get("validatedProposalSourceSha")
        != publication_source_sha
        or capture_candidate.get("source")
        != _native_json(
            payloads,
            UNSIGNED_CANDIDATE_PROVENANCE_EXPORT,
            label="unsigned native candidate export receipt",
        ).get("source")
        or _positive_int(
            capture_candidate.get("validatedInventoryFileCount"),
            label="unsigned capture validated file count",
        )
        != len(content_rows)
    ):
        _fail("unsigned capture candidate identity drifted")
    composition_row = content_by_path[UNSIGNED_COMPOSITION_FILE]
    if (
        capture_candidate.get("compositionRequest") != composition_row
        or capture_candidate.get("validatedProposalSha256")
        != composition_row["sha256"]
    ):
        _fail("unsigned capture composition custody drifted")
    for property_name, document_path, binding_path in (
        (
            "contentInventory",
            UNSIGNED_CANDIDATE_PROVENANCE_INVENTORY,
            "PREVIEW_NIGHTLY_UNSIGNED_CANDIDATE_CONTENT_INVENTORY.generated.json",
        ),
        (
            "exportReceipt",
            UNSIGNED_CANDIDATE_PROVENANCE_EXPORT,
            "PREVIEW_NIGHTLY_UNSIGNED_CANDIDATE_EXPORT.generated.json",
        ),
    ):
        expected = _native_payload_row(payloads, document_path)
        expected["path"] = binding_path
        if capture_candidate.get(property_name) != expected:
            _fail(f"unsigned capture {property_name} custody drifted")
    for property_name, content_path in (
        (
            "installer",
            "publication/files/chummer-avalonia-win-x64-installer.exe",
        ),
        (
            "payload",
            "publication/files/chummer-avalonia-win-x64-payload.zip",
        ),
    ):
        expected = {
            **content_by_path[content_path],
            "fileName": content_path.rsplit("/", 1)[1],
        }
        if capture_candidate.get(property_name) != expected:
            _fail(f"unsigned capture candidate {property_name} drifted")
    if (
        capture_candidate.get("manifest")
        != content_by_path["publication/RELEASE_CHANNEL.generated.json"]
    ):
        _fail("unsigned capture candidate source manifest drifted")

    preserved = capture.get("preservedCandidateFiles")
    expected_preserved = [
        _native_payload_row(payloads, path)
        for path in (
            UNSIGNED_CANDIDATE_PROVENANCE_INVENTORY,
            UNSIGNED_CANDIDATE_PROVENANCE_EXPORT,
        )
    ]
    if preserved != expected_preserved:
        _fail("unsigned capture preserved candidate files drifted")

    heads = capture.get("heads")
    if not isinstance(heads, list) or len(heads) != len(scope["heads"]):
        _fail("unsigned capture head scope drifted")
    captured_screenshots: dict[str, list[dict[str, Any]]] = {}
    for head_binding, head in zip(heads, scope["heads"], strict=True):
        if not isinstance(head_binding, dict) or set(head_binding) != {
            "authenticodeVerification",
            "headId",
            "installer",
            "payload",
            "progressLog",
            "receipt",
            "rid",
            "screenshots",
        }:
            _fail("unsigned capture head property set drifted")
        artifacts = scope["artifacts"][head]
        if (
            head_binding.get("headId") != head
            or head_binding.get("rid") != RID
            or head_binding.get("installer")
            != {
                key: artifacts["installer"][key]
                for key in ("fileName", "sha256", "sizeBytes")
            }
            or head_binding.get("payload")
            != {
                key: artifacts["payload"][key]
                for key in ("fileName", "sha256", "sizeBytes")
            }
        ):
            _fail("unsigned capture head artifact binding drifted")
        _validate_native_authenticode_reference(
            head_binding.get("authenticodeVerification"),
            expected_path=auth_path,
            payloads=payloads,
            label="unsigned capture head Authenticode",
        )
        receipt_path = f"startup-smoke/startup-smoke-{head}-{RID}.receipt.json"
        progress_log_path = (
            f"startup-smoke/windows-installer-progress-{head}-{RID}.log"
        )
        _validate_native_digest_reference(
            head_binding.get("receipt"),
            expected_path=receipt_path,
            payloads=payloads,
            label="unsigned capture startup receipt",
        )
        _validate_native_digest_reference(
            head_binding.get("progressLog"),
            expected_path=progress_log_path,
            payloads=payloads,
            label="unsigned capture progress log",
        )
        screenshots = head_binding.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) != 2:
            _fail("unsigned capture installer screenshots drifted")
        captured_screenshots[head] = screenshots
        for screenshot, role in zip(
            screenshots,
            ("progress", "completion"),
            strict=True,
        ):
            _validate_native_screenshot(
                screenshot,
                expected_path=(
                    f"screenshots/windows-installer-{head}-{RID}-{role}.png"
                ),
                expected_role=role,
                payloads=payloads,
                label=f"unsigned capture {role}",
                include_dimensions=True,
            )

    native_evidence = capture.get("nativeEvidence")
    if not isinstance(native_evidence, dict) or set(native_evidence) != {
        "authenticodeVerification",
        "head",
        "payloadHttpLog",
        "screenshots",
        "startupLog",
        "startupVisual",
    }:
        _fail("unsigned capture native evidence property set drifted")
    _validate_native_authenticode_reference(
        native_evidence.get("authenticodeVerification"),
        expected_path=auth_path,
        payloads=payloads,
        label="unsigned capture native Authenticode",
    )
    if native_evidence.get("head") != heads[0]:
        _fail("unsigned capture native head differs from capture head")
    head = scope["heads"][0]
    for property_name, expected_path in (
        (
            "startupLog",
            f"startup-smoke/startup-smoke-{head}-{RID}.log",
        ),
        (
            "payloadHttpLog",
            f"startup-smoke/startup-smoke-payload-http-{head}-{RID}.log",
        ),
    ):
        _validate_native_byte_reference(
            native_evidence.get(property_name),
            expected_path=expected_path,
            payloads=payloads,
            label=f"unsigned capture {property_name}",
        )
    native_screenshots = native_evidence.get("screenshots")
    if not isinstance(native_screenshots, list) or len(native_screenshots) != 3:
        _fail("unsigned capture native screenshot scope drifted")
    for screenshot, role, expected_path in zip(
        native_screenshots,
        ("startup", "progress", "completion"),
        (
            f"screenshots/windows-application-{head}-{RID}-startup.png",
            f"screenshots/windows-installer-{head}-{RID}-progress.png",
            f"screenshots/windows-installer-{head}-{RID}-completion.png",
        ),
        strict=True,
    ):
        _validate_native_screenshot(
            screenshot,
            expected_path=expected_path,
            expected_role=role,
            payloads=payloads,
            label=f"unsigned capture native {role}",
            include_dimensions=True,
        )
    if native_screenshots[1:] != captured_screenshots[head]:
        _fail("unsigned capture native screenshots differ from head custody")
    startup_visual_binding = native_evidence.get("startupVisual")
    if not isinstance(startup_visual_binding, dict) or set(
        startup_visual_binding
    ) != {"installedExecutable", "receipt", "screenshot"}:
        _fail("unsigned capture startup visual binding drifted")
    startup_visual_path = (
        f"startup-visual/windows-application-{head}-{RID}-startup.receipt.json"
    )
    _validate_native_byte_reference(
        startup_visual_binding.get("receipt"),
        expected_path=startup_visual_path,
        payloads=payloads,
        label="unsigned capture startup visual receipt",
    )
    expected_startup_visual_screenshot = {
        key: native_screenshots[0][key]
        for key in ("height", "path", "sha256", "width")
    }
    if (
        startup_visual_binding.get("screenshot")
        != expected_startup_visual_screenshot
    ):
        _fail("unsigned capture startup visual screenshot drifted")

    authenticode = _native_json(
        payloads,
        auth_path,
        label="unsigned Authenticode receipt",
    )
    if set(authenticode) != {
        "artifact",
        "contractName",
        "contractVersion",
        "generatedAt",
        "nativeHostEvidence",
        "signatureStatus",
        "signingRequired",
        "source",
        "status",
        "unsignedReason",
        "verifier",
    }:
        _fail("unsigned Authenticode receipt property set drifted")
    expected_installer = content_by_path[
        "publication/files/chummer-avalonia-win-x64-installer.exe"
    ]
    if (
        authenticode.get("contractName")
        != "chummer6-ui.unsigned-preview-windows-authenticode-verification"
        or type(authenticode.get("contractVersion")) is not int
        or authenticode.get("contractVersion") != 1
        or authenticode.get("status") != "verified"
        or authenticode.get("signatureStatus") != "unsigned"
        or authenticode.get("signingRequired") is not False
        or authenticode.get("unsignedReason") != "preview_policy"
        or authenticode.get("artifact")
        != {
            **expected_installer,
            "fileName": expected_installer["path"].rsplit("/", 1)[1],
        }
    ):
        _fail("unsigned Authenticode artifact or policy drifted")
    _fresh_timestamp(
        authenticode.get("generatedAt"),
        label="unsigned Authenticode generatedAt",
        now=now,
        max_age=max_age,
    )
    _validate_native_full_source(
        authenticode.get("source"),
        capture_source,
        label="unsigned Authenticode",
        expected_actor="github-actions[bot]",
    )
    _validate_native_host(
        authenticode.get("nativeHostEvidence"),
        label="unsigned Authenticode",
    )
    if authenticode.get("verifier") != {
        "authenticodeStatus": "NotSigned",
        "implementation": "scripts/verify_unsigned_windows_preview_authenticode.ps1",
        "platform": "windows",
        "securityDirectoryEmpty": True,
    }:
        _fail("unsigned Authenticode verifier drifted")

    startup = _native_json(
        payloads,
        f"startup-smoke/startup-smoke-{head}-{RID}.receipt.json",
        label="unsigned native startup receipt",
    )
    _validate_unsigned_native_startup_receipt(
        startup,
        head=head,
        scope=scope,
        expected_installed_executable=expected_installed_executable,
        now=now,
        max_age=max_age,
    )

    startup_visual = _native_json(
        payloads,
        startup_visual_path,
        label="unsigned startup visual receipt",
    )
    if set(startup_visual) != {
        "candidate",
        "contractName",
        "contractVersion",
        "generatedAtUtc",
        "installedExecutable",
        "nativeHostEvidence",
        "source",
        "startupScreenshot",
        "status",
    }:
        _fail("unsigned startup visual property set drifted")
    if (
        startup_visual.get("contractName")
        != "chummer6-ui.unsigned-preview-windows-startup-visual"
        or type(startup_visual.get("contractVersion")) is not int
        or startup_visual.get("contractVersion") != 1
        or startup_visual.get("status") != "captured"
    ):
        _fail("unsigned startup visual identity drifted")
    _fresh_timestamp(
        startup_visual.get("generatedAtUtc"),
        label="unsigned startup visual generatedAtUtc",
        now=now,
        max_age=max_age,
    )
    _validate_native_full_source(
        startup_visual.get("source"),
        capture_source,
        label="unsigned startup visual",
        expected_actor="github-actions[bot]",
    )
    _validate_native_host(
        startup_visual.get("nativeHostEvidence"),
        label="unsigned startup visual",
    )
    startup_candidate = startup_visual.get("candidate")
    if not isinstance(startup_candidate, dict) or set(startup_candidate) != {
        "installer",
        "payload",
        "release",
        "signature",
        "sourceSha",
    } or (
        startup_candidate.get("installer") != capture_candidate["installer"]
        or startup_candidate.get("payload") != capture_candidate["payload"]
        or startup_candidate.get("release") != capture_candidate["release"]
        or startup_candidate.get("signature") != capture_candidate["signature"]
        or startup_candidate.get("sourceSha") != publication_source_sha
    ):
        _fail("unsigned startup visual candidate binding drifted")
    _validate_native_screenshot(
        startup_visual.get("startupScreenshot"),
        expected_path=f"screenshots/windows-application-{head}-{RID}-startup.png",
        expected_role=None,
        payloads=payloads,
        label="unsigned startup visual",
        include_dimensions=True,
    )
    installed_executable = startup_visual.get("installedExecutable")
    if (
        not isinstance(installed_executable, dict)
        or set(installed_executable)
        != {"fileName", "payloadEntry", "sha256", "sizeBytes"}
        or not isinstance(installed_executable.get("fileName"), str)
        or not installed_executable["fileName"]
        or installed_executable.get("payloadEntry")
        != installed_executable["fileName"]
    ):
        _fail("unsigned startup visual installed executable drifted")
    _sha256(
        installed_executable.get("sha256"),
        label="unsigned startup executable sha256",
    )
    _positive_int(
        installed_executable.get("sizeBytes"),
        label="unsigned startup executable sizeBytes",
    )
    if (
        expected_installed_executable is not None
        and installed_executable != expected_installed_executable
    ):
        _fail(
            "unsigned startup executable differs from exact candidate payload ZIP"
        )
    if startup_visual_binding.get("installedExecutable") != installed_executable:
        _fail("unsigned capture startup executable binding drifted")

    visual = _native_json(
        payloads,
        next(iter(visual_paths)),
        label="unsigned native visual proof",
    )
    visual_keys = {
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
    if set(visual) != visual_keys or (
        visual.get("contractName")
        != "chummer6-ui.unsigned-preview-windows-installer-visual-proof"
        or type(visual.get("contractVersion")) is not int
        or visual.get("contractVersion") != 1
        or visual.get("status") != "passed"
        or visual.get("head") != head
        or visual.get("headId") != head
        or visual.get("platform") != "windows"
        or visual.get("rid") != RID
        or visual.get("version") != scope["version"]
        or visual.get("releaseVersion") != scope["version"]
        or visual.get("channel") != scope["channel"]
        or visual.get("channelId") != scope["channel"]
        or visual.get("artifactFileName")
        != artifacts["installer"]["fileName"]
        or visual.get("artifactDigest")
        != f"sha256:{artifacts['installer']['sha256']}"
        or visual.get("generatedAt") != finalization_generated_at
    ):
        _fail("unsigned native visual proof identity drifted")
    if visual.get("checks") != {
        "accountable_review_confirmed": True,
        "capture_mode": "hosted_native_windows",
    }:
        _fail("unsigned native visual checks drifted")
    for property_name in (
        "clippingReview",
        "contrastReview",
        "readabilityReview",
    ):
        if visual.get(property_name) != {
            "reviewer": reviewer,
            "status": "passed",
        }:
            _fail(f"unsigned native {property_name} drifted")
    review = visual.get("review")
    if not isinstance(review, dict) or set(review) != {
        "allowlistSource",
        "authenticatedReviewer",
        "captureActor",
        "explicitConfirmations",
    } or (
        review.get("allowlistSource")
        != "pinned contract identity plus protected environment and authenticated workflow actor"
        or review.get("authenticatedReviewer") != reviewer
        or review.get("captureActor") != "github-actions[bot]"
        or review.get("explicitConfirmations") != finalization["confirmations"]
    ):
        _fail("unsigned native visual review authority drifted")
    capture_binding = visual.get("captureBinding")
    expected_capture_binding = {
        key: capture_full_source[key]
        for key in (
            "artifactName",
            "ref",
            "repository",
            "rerunPolicy",
            "runAttempt",
            "runId",
            "sha",
            "triggeringActor",
            "workflow",
        )
    }
    expected_capture_binding["inventorySha256"] = capture_inventory_digest
    if capture_binding != expected_capture_binding:
        _fail("unsigned visual capture binding drifted")
    if visual.get("finalizationBinding") != finalization["finalizationSource"]:
        _fail("unsigned visual finalization binding drifted")
    _validate_native_authenticode_reference(
        visual.get("authenticodeVerification"),
        expected_path=auth_path,
        payloads=payloads,
        label="unsigned visual Authenticode",
    )
    visual_screenshots = visual.get("screenshots")
    if not isinstance(visual_screenshots, list) or len(visual_screenshots) != 3:
        _fail("unsigned visual screenshot scope drifted")
    for screenshot, role, expected_path in zip(
        visual_screenshots,
        ("startup", "progress", "completion"),
        (
            f"screenshots/windows-application-{head}-{RID}-startup.png",
            f"screenshots/windows-installer-{head}-{RID}-progress.png",
            f"screenshots/windows-installer-{head}-{RID}-completion.png",
        ),
        strict=True,
    ):
        _validate_native_screenshot(
            screenshot,
            expected_path=expected_path,
            expected_role=role,
            payloads=payloads,
            label=f"unsigned visual {role}",
            include_dimensions=False,
        )
    return {
        "capture": capture,
        "captureInventory": capture_inventory,
        "finalization": finalization,
        "finalizedInventory": finalized_inventory,
        "authenticode": authenticode,
        "startup": startup,
        "startupVisual": startup_visual,
        "visualProof": visual,
    }


def _validate_unsigned_native_evidence(
    root: Path,
    *,
    candidate_rows: list[dict[str, Any]],
    source_canonical_bytes: bytes,
    source_compatibility_bytes: bytes,
    expected_content_rows: list[dict[str, Any]] | None = None,
    expected_installed_executable: dict[str, Any] | None = None,
    scope: dict[str, Any],
    publication_source_sha: str,
    now: datetime,
    max_age: timedelta,
) -> tuple[dict[str, Any], datetime]:
    if root.is_symlink() or not root.is_dir():
        _fail("unsigned finalized native-Windows evidence root must be a real directory")
    outer, outer_bytes = _strict_json(
        root / UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE,
        label="unsigned finalized native-Windows evidence",
    )
    if set(outer) != {
        "status",
        "captureGeneratedAtUtc",
        "finalizationGeneratedAtUtc",
        "reviewer",
        "captureSource",
        "finalizationSource",
        "candidateContentInventorySha256",
        "candidateContentInventory",
        "files",
    } or outer.get("status") != "passed":
        _fail("unsigned finalized native-Windows evidence contract drifted")

    captured_at = _fresh_timestamp(
        outer.get("captureGeneratedAtUtc"),
        label="unsigned native captureGeneratedAtUtc",
        now=now,
        max_age=max_age,
    )
    finalized_at = _fresh_timestamp(
        outer.get("finalizationGeneratedAtUtc"),
        label="unsigned native finalizationGeneratedAtUtc",
        now=now,
        max_age=max_age,
    )
    if finalized_at < captured_at:
        _fail("unsigned native finalization predates capture")
    reviewer = outer.get("reviewer")
    if (
        not isinstance(reviewer, str)
        or REVIEWER_RE.fullmatch(reviewer) is None
        or reviewer != UI_REPOSITORY.split("/", 1)[0]
    ):
        _fail("unsigned native reviewer is invalid")
    capture_source = _unsigned_native_source(
        outer.get("captureSource"),
        label="unsigned native capture source",
        workflow=UNSIGNED_CAPTURE_WORKFLOW,
    )
    finalization_source = _unsigned_native_source(
        outer.get("finalizationSource"),
        label="unsigned native finalization source",
        workflow=UNSIGNED_FINALIZE_WORKFLOW,
    )
    if (
        finalization_source["actor"] != reviewer
        or capture_source["actor"] == reviewer
        or capture_source["sha"] != finalization_source["sha"]
    ):
        _fail("unsigned native finalized source/reviewer authority drifted")

    rows, payloads = _decode_unsigned_native_files(outer.get("files"))
    expected_paths = {
        UNSIGNED_NATIVE_CAPTURE_FILE,
        UNSIGNED_NATIVE_CAPTURE_INVENTORY_FILE,
        UNSIGNED_NATIVE_FINALIZATION_FILE,
        UNSIGNED_NATIVE_FINALIZED_INVENTORY_FILE,
        UNSIGNED_CANDIDATE_PROVENANCE_INVENTORY,
        UNSIGNED_CANDIDATE_PROVENANCE_EXPORT,
    }
    for head in scope["heads"]:
        expected_paths.update(
            {
                f"UNSIGNED_WINDOWS_PREVIEW_VISUAL_PROOF-{head}-{RID}.generated.json",
                f"authenticode/AUTHENTICODE_VERIFICATION-{head}-{RID}.generated.json",
                f"screenshots/windows-application-{head}-{RID}-startup.png",
                f"screenshots/windows-installer-{head}-{RID}-completion.png",
                f"screenshots/windows-installer-{head}-{RID}-progress.png",
                f"startup-smoke/startup-smoke-{head}-{RID}.log",
                f"startup-smoke/startup-smoke-{head}-{RID}.receipt.json",
                f"startup-smoke/startup-smoke-payload-http-{head}-{RID}.log",
                f"startup-smoke/windows-installer-progress-{head}-{RID}.log",
                f"startup-visual/windows-application-{head}-{RID}-startup.receipt.json",
            }
        )
    if set(payloads) != expected_paths:
        _fail("unsigned native finalized evidence file scope drifted")

    actual_tree = _exact_tree_rows(root, exclude=set())
    expected_tree = sorted(
        [
            *rows,
            {
                "path": UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE,
                "sha256": hashlib.sha256(outer_bytes).hexdigest(),
                "sizeBytes": len(outer_bytes),
            },
        ],
        key=lambda row: row["path"],
    )
    if actual_tree != expected_tree:
        _fail("unsigned native finalized evidence differs from its exact disk tree")

    inventory_path = UNSIGNED_CANDIDATE_PROVENANCE_INVENTORY
    inventory_raw = payloads[inventory_path]
    inventory_digest = hashlib.sha256(inventory_raw).hexdigest()
    if (
        _sha256(
            outer.get("candidateContentInventorySha256"),
            label="unsigned native candidate content inventory sha256",
        )
        != inventory_digest
    ):
        _fail("unsigned native candidate content inventory digest drifted")
    content_inventory = _strict_json_bytes(
        inventory_raw,
        label="unsigned native candidate content inventory",
    )
    if outer.get("candidateContentInventory") != content_inventory:
        _fail("unsigned native candidate content inventory document drifted")
    if (
        set(content_inventory)
        != {
            "contractName",
            "contractVersion",
            "crossRunBitReproducible",
            "files",
            "platformScope",
            "release",
            "signature",
            "sourceSha",
        }
        or content_inventory.get("contractName")
        != "chummer6-ui.preview-nightly-unsigned-candidate-content-inventory"
        or type(content_inventory.get("contractVersion")) is not int
        or content_inventory.get("contractVersion") != 1
        or content_inventory.get("crossRunBitReproducible") is not False
        or content_inventory.get("platformScope") != "windows_only"
        or content_inventory.get("release")
        != {"channel": scope["channel"], "version": scope["version"]}
        or content_inventory.get("signature") != UNSIGNED_SIGNATURE_POLICY
        or content_inventory.get("sourceSha") != publication_source_sha
    ):
        _fail("unsigned native candidate content inventory contract drifted")
    content_rows = _inventory_rows(
        content_inventory.get("files"),
        label="unsigned native candidate content inventory",
    )
    content_by_path = {row["path"]: row for row in content_rows}
    candidate_by_path = {row["path"]: row for row in candidate_rows}
    expected_content_paths = {
        UNSIGNED_COMPOSITION_FILE,
        *UNSIGNED_PROVENANCE_PATHS.values(),
        "publication/RELEASE_CHANNEL.generated.json",
        "publication/releases.json",
    }
    for head in scope["heads"]:
        installer = scope["artifacts"][head]["installer"]["path"]
        payload = scope["artifacts"][head]["payload"]["path"]
        expected_content_paths.update(
            {
                f"publication/{installer}",
                f"publication/{payload}",
                f"publication/{payload}.json",
            }
        )
    if set(content_by_path) != expected_content_paths:
        _fail("unsigned native candidate content path scope drifted")
    if expected_content_rows is not None:
        validated_expected_content_rows = _inventory_rows(
            expected_content_rows,
            label="expected unsigned native candidate content",
        )
        if content_rows != validated_expected_content_rows:
            _fail(
                "unsigned native candidate content differs from exact v3 "
                "and candidate custody"
            )
    expected_source_mapping: dict[str, bytes] = {
        "publication/RELEASE_CHANNEL.generated.json": source_canonical_bytes,
        "publication/releases.json": source_compatibility_bytes,
    }
    for content_path, source_bytes in expected_source_mapping.items():
        if content_by_path.get(content_path) != {
            "path": content_path,
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "sizeBytes": len(source_bytes),
        }:
            _fail(
                "unsigned native evidence differs from preserved source "
                "publication bytes"
            )
    expected_candidate_mapping: dict[str, str] = {}
    for head in scope["heads"]:
        installer = scope["artifacts"][head]["installer"]["path"]
        payload = scope["artifacts"][head]["payload"]["path"]
        expected_candidate_mapping[f"publication/{installer}"] = installer
        expected_candidate_mapping[f"publication/{payload}"] = payload
        expected_candidate_mapping[f"publication/{payload}.json"] = f"{payload}.json"
    for content_path, candidate_path in expected_candidate_mapping.items():
        candidate_row = candidate_by_path.get(candidate_path)
        if candidate_row is None or content_by_path.get(content_path) != {
            "path": content_path,
            "sha256": candidate_row["sha256"],
            "sizeBytes": candidate_row["sizeBytes"],
        }:
            _fail("unsigned native evidence differs from candidate upload bytes")

    export_raw = payloads[UNSIGNED_CANDIDATE_PROVENANCE_EXPORT]
    export = _strict_json_bytes(
        export_raw,
        label="unsigned native candidate export receipt",
    )
    exported_rows = _inventory_rows(
        export.get("exportedContent"),
        label="unsigned native candidate export content",
    )
    if (
        set(export)
        != {
            "compositionRequest",
            "contractName",
            "contractVersion",
            "crossRunBitReproducible",
            "deployAuthorized",
            "exportedContent",
            "githubArtifactTransport",
            "inventory",
            "platformScope",
            "publicationAuthorized",
            "release",
            "runnerNonce",
            "signature",
            "source",
            "status",
            "uiUploadAuthorized",
            "uploadAuthorized",
        }
        or export.get("contractName")
        != "chummer6-ui.preview-nightly-unsigned-candidate-export"
        or type(export.get("contractVersion")) is not int
        or export.get("contractVersion") != 1
        or export.get("status") != "exported"
        or export.get("crossRunBitReproducible") is not False
        or export.get("platformScope") != "windows_only"
        or export.get("release")
        != {"channel": scope["channel"], "version": scope["version"]}
        or export.get("signature") != UNSIGNED_SIGNATURE_POLICY
        or exported_rows != content_rows
        or export.get("githubArtifactTransport") != "ephemeral_candidate_only"
        or any(
            export.get(field) is not False
            for field in (
                "deployAuthorized",
                "publicationAuthorized",
                "uiUploadAuthorized",
                "uploadAuthorized",
            )
        )
    ):
        _fail("unsigned native candidate export receipt contract drifted")
    inventory_reference = export.get("inventory")
    if (
        not isinstance(inventory_reference, dict)
        or set(inventory_reference) != {"path", "sha256", "sizeBytes"}
        or inventory_reference.get("path")
        != "PREVIEW_NIGHTLY_UNSIGNED_CANDIDATE_CONTENT_INVENTORY.generated.json"
        or _sha256(
            inventory_reference.get("sha256"),
            label="unsigned native candidate export inventory sha256",
        )
        != inventory_digest
        or _positive_int(
            inventory_reference.get("sizeBytes"),
            label="unsigned native candidate export inventory sizeBytes",
        )
        != len(inventory_raw)
    ):
        _fail("unsigned native candidate export inventory binding drifted")
    export_source = export.get("source")
    if (
        not isinstance(export_source, dict)
        or set(export_source)
        != {"actor", "ref", "repository", "runAttempt", "runId", "sha", "workflow"}
        or export_source.get("repository") != UI_REPOSITORY
        or export_source.get("ref") != PRODUCER_REF
        or export_source.get("workflow")
        != ".github/workflows/unsigned-windows-preview-nightly-candidate-export.yml"
        or not isinstance(export_source.get("actor"), str)
        or REVIEWER_RE.fullmatch(export_source["actor"]) is None
        or not isinstance(export_source.get("sha"), str)
        or COMMIT_RE.fullmatch(export_source["sha"]) is None
        or content_inventory.get("sourceSha") != export_source["sha"]
        or export_source["sha"] != publication_source_sha
    ):
        _fail("unsigned native candidate export source drifted")
    _github_positive_integer(
        export_source.get("runId"),
        label="unsigned native candidate export source runId",
    )
    _github_positive_integer(
        export_source.get("runAttempt"),
        label="unsigned native candidate export source runAttempt",
    )
    runner_nonce = export.get("runnerNonce")
    if (
        not isinstance(runner_nonce, str)
        or re.fullmatch(r"^[a-z0-9]{12,64}$", runner_nonce) is None
    ):
        _fail("unsigned native candidate export runner nonce drifted")
    composition_reference = export.get("compositionRequest")
    composition_row = content_by_path[UNSIGNED_COMPOSITION_FILE]
    if composition_reference != composition_row:
        _fail("unsigned native candidate export composition custody drifted")
    validated_graph = _validate_unsigned_native_graph(
        payloads=payloads,
        scope=scope,
        content_rows=content_rows,
        capture_source=capture_source,
        finalization_source=finalization_source,
        reviewer=reviewer,
        capture_generated_at=outer.get("captureGeneratedAtUtc"),
        finalization_generated_at=outer.get("finalizationGeneratedAtUtc"),
        publication_source_sha=publication_source_sha,
        expected_installed_executable=expected_installed_executable,
        now=now,
        max_age=max_age,
    )
    if (
        validated_graph["capture"].get("status") != "captured"
        or validated_graph["finalization"].get("status") != "passed"
        or validated_graph["visualProof"].get("status") != "passed"
    ):
        _fail("unsigned native validated graph lost its terminal posture")
    return outer, min(captured_at, finalized_at)


def _validate_embedded_unsigned_native_evidence(
    evidence: object,
    *,
    candidate_rows: list[dict[str, Any]],
    source_canonical_bytes: bytes,
    source_compatibility_bytes: bytes,
    expected_content_rows: list[dict[str, Any]] | None = None,
    expected_installed_executable: dict[str, Any] | None = None,
    scope: dict[str, Any],
    publication_source_sha: str,
    now: datetime,
    max_age: timedelta,
) -> tuple[dict[str, Any], datetime]:
    """Revalidate an embedded v4 native graph through the disk-tree validator.

    A v4 candidate authority carries the finalized native evidence as JSON
    custody rather than as an independently selected directory. Rehydrate only
    the already digest-checked embedded rows into a new private directory, then
    reuse the same exact-tree and semantic validator used at materialization.
    """

    if not isinstance(evidence, dict):
        _fail("unsigned finalized native-Windows evidence custody is unavailable")
    _rows, payloads = _decode_unsigned_native_files(evidence.get("files"))
    try:
        outer_raw = (
            json.dumps(
                evidence,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CandidateAuthorityBlocked(
            "unsigned finalized native-Windows evidence is not canonical JSON"
        ) from exc

    def write_private_file(root: Path, relative: str, payload: bytes) -> None:
        target = root.joinpath(*relative.split("/"))
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        ancestor = target.parent
        while ancestor != root:
            os.chmod(ancestor, 0o700, follow_symlinks=False)
            ancestor = ancestor.parent
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(target, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    _fail(
                        "unsigned finalized native-Windows evidence "
                        "rehydration made no progress"
                    )
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    with tempfile.TemporaryDirectory(
        prefix="chummer-unsigned-native-authority-"
    ) as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        for relative, payload in sorted(payloads.items()):
            write_private_file(root, relative, payload)
        write_private_file(
            root,
            UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE,
            outer_raw,
        )
        return _validate_unsigned_native_evidence(
            root,
            candidate_rows=candidate_rows,
            source_canonical_bytes=source_canonical_bytes,
            source_compatibility_bytes=source_compatibility_bytes,
            expected_content_rows=expected_content_rows,
            expected_installed_executable=expected_installed_executable,
            scope=scope,
            publication_source_sha=publication_source_sha,
            now=now,
            max_age=max_age,
        )


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
    profile_enabled = _unsigned_profile_enabled(
        scope_payload, label="unsigned UI publication scope"
    )
    expected_scope_keys = (
        UNSIGNED_PROFILE_PUBLICATION_SCOPE_KEYS
        if profile_enabled
        else UNSIGNED_PUBLICATION_SCOPE_KEYS
    )
    expected_scope_bytes = (
        json.dumps(scope_payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if (
        set(scope_payload) != expected_scope_keys
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
    expected_roles = [
        ("installer", "installer"),
        ("bootstrap_payload", "payload"),
    ]
    if profile_enabled:
        expected_roles.append(("bootstrap_payload_sidecar", None))
    if not isinstance(delta_value, list) or len(delta_value) != len(expected_roles):
        _fail("unsigned UI fresh delta cardinality drifted")
    expected_delta = canonical_scope["artifacts"]["avalonia"]
    delta: list[dict[str, Any]] = []
    for index, (scope_role, canonical_role) in enumerate(
        expected_roles
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
        expected = (
            expected_delta[canonical_role]
            if canonical_role is not None
            else {
                "fileName": UNSIGNED_PAYLOAD_SIDECAR_NAME,
                "path": f"files/{UNSIGNED_PAYLOAD_SIDECAR_NAME}",
                "sha256": full_by_path.get(
                    f"files/{UNSIGNED_PAYLOAD_SIDECAR_NAME}", {}
                ).get("sha256"),
                "sizeBytes": full_by_path.get(
                    f"files/{UNSIGNED_PAYLOAD_SIDECAR_NAME}", {}
                ).get("sizeBytes"),
            }
        )
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
    expected_file_names = [
        "chummer-avalonia-win-x64-installer.exe",
        "chummer-avalonia-win-x64-payload.zip",
    ]
    if profile_enabled:
        expected_file_names.append(UNSIGNED_PAYLOAD_SIDECAR_NAME)
    if [row["fileName"] for row in delta] != expected_file_names:
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
    if profile_enabled:
        evidence["projectionProfile"] = UNSIGNED_V3_PROJECTION_PROFILE
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
    source_canonical_raw: bytes | None = None,
    source_compatibility_raw: bytes | None = None,
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
    profile_enabled = _unsigned_profile_enabled(
        composition, label="unsigned composition request"
    )
    if profile_enabled != _unsigned_profile_enabled(
        scope, label="unsigned UI publication scope"
    ):
        _fail("unsigned composition/UI projection profiles drifted")
    expected_composition_keys = (
        UNSIGNED_PROFILE_COMPOSITION_KEYS
        if profile_enabled
        else UNSIGNED_COMPOSITION_KEYS
    )
    if (
        set(composition) != expected_composition_keys
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
        raw=(
            source_canonical_raw
            if profile_enabled and source_canonical_raw is not None
            else canonical_raw
        ),
        label="unsigned composition canonical manifest",
    )
    _expect_reference(
        composition.get("proposedCompatibilityManifest"),
        path="releases.json",
        raw=(
            source_compatibility_raw
            if profile_enabled and source_compatibility_raw is not None
            else compatibility_raw
        ),
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
        proposed_modes != candidate_directory_modes
        or composition.get("proposedShelfInventorySha256")
        != _ui_compact_sha256(proposed_inventory)
        or composition.get("proposedDirectoryModesSha256")
        != _ui_compact_sha256(proposed_modes)
    ):
        _fail("unsigned composition proposed shelf digest graph drifted")
    if profile_enabled:
        if source_canonical_raw is None or source_compatibility_raw is None:
            _fail("unsigned profile source manifests are absent from custody")
        proposed_by_path = {row["path"]: row for row in proposed_inventory}
        scope_by_path = {row["path"]: row for row in scope_inventory}
        if set(proposed_by_path) != set(scope_by_path):
            _fail("unsigned profile source/projected shelf paths drifted")
        for path in set(proposed_by_path) - {
            "RELEASE_CHANNEL.generated.json",
            "releases.json",
        }:
            if proposed_by_path[path] != scope_by_path[path]:
                _fail("unsigned profile changed a non-manifest shelf byte")
        for path, source_raw, projected_raw in (
            (
                "RELEASE_CHANNEL.generated.json",
                source_canonical_raw,
                canonical_raw,
            ),
            ("releases.json", source_compatibility_raw, compatibility_raw),
        ):
            source = proposed_by_path[path]
            projected = scope_by_path[path]
            if (
                source["mode"] != projected["mode"]
                or source["sha256"] != hashlib.sha256(source_raw).hexdigest()
                or source["sizeBytes"] != len(source_raw)
                or projected["sha256"] != hashlib.sha256(projected_raw).hexdigest()
                or projected["sizeBytes"] != len(projected_raw)
                or source["sha256"] == projected["sha256"]
            ):
                _fail("unsigned profile source/projected manifest custody drifted")
    elif proposed_inventory != scope_inventory:
        _fail("unsigned composition proposed shelf differs from UI custody")

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
        or len(fresh) != (3 if profile_enabled else 2)
        or not isinstance(scope_fresh, list)
        or len(scope_fresh) != (3 if profile_enabled else 2)
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
    if profile_enabled:
        if source_canonical_raw is None:
            _fail("unsigned profile source canonical manifest is absent")
        source_canonical = _strict_json_bytes(
            source_canonical_raw, label="unsigned source canonical manifest"
        )
        source_windows_rows = [
            row
            for row in source_canonical.get("artifacts") or []
            if isinstance(row, dict)
            and row.get("head") == "avalonia"
            and row.get("platform") == "windows"
            and row.get("rid") == RID
        ]
        if len(source_windows_rows) != 1:
            _fail("unsigned composition source Windows row drifted")
        manifest_row_sha256 = _ui_compact_sha256(source_windows_rows[0])
        if windows_rows[0].get("sourceManifestRowSha256") != manifest_row_sha256:
            _fail("unsigned projected Windows row lost its source-row custody")
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
    profile_enabled = _unsigned_profile_enabled(
        scope, label="unsigned UI publication scope"
    )
    expected_candidate_keys = (
        REGISTRY_CANDIDATE_PROFILE_KEYS
        if profile_enabled
        else REGISTRY_CANDIDATE_V2_KEYS
    )
    signature_policy = {
        "signatureStatus": "unsigned",
        "signingRequired": False,
        "unsignedReason": "preview_policy",
    }
    if (
        set(receipt) != expected_candidate_keys
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
    source_files: list[tuple[str, bytes]] = []
    source_canonical_raw: bytes | None = None
    source_compatibility_raw: bytes | None = None
    registry_commit: str | None = None
    if profile_enabled:
        _validate_unsigned_profile_recursive_authority(
            receipt, label="Registry PREPARE profile"
        )
        if receipt.get("projectionProfile") != UNSIGNED_V3_PROJECTION_PROFILE:
            _fail("Registry PREPARE projection profile drifted")
        registry_commit = _matching_alias(
            receipt,
            "registryCommit",
            "registry_commit",
            label="Registry PREPARE Registry commit",
        )
        if COMMIT_RE.fullmatch(registry_commit) is None:
            _fail("Registry PREPARE Registry commit is invalid")
        manifest_profile = _validate_unsigned_profile_manifest_pair(
            canonical,
            _strict_json_bytes(
                compatibility_raw,
                label="Registry-projected compatibility manifest",
            ),
        )
        if registry_commit != manifest_profile["registryCommit"]:
            _fail("Registry PREPARE/manifest Registry commits disagree")
        source_canonical_path, source_canonical_raw = _stage_bytes_reference(
            stage_root,
            receipt.get("sourceCanonicalManifest"),
            expected_path=UNSIGNED_SOURCE_CANONICAL_PATH,
            label="Registry PREPARE source canonical manifest",
        )
        source_compatibility_path, source_compatibility_raw = _stage_bytes_reference(
            stage_root,
            receipt.get("sourceCompatibilityManifest"),
            expected_path=UNSIGNED_SOURCE_COMPATIBILITY_PATH,
            label="Registry PREPARE source compatibility manifest",
        )
        source_files.extend(
            (
                (source_canonical_path, source_canonical_raw),
                (source_compatibility_path, source_compatibility_raw),
            )
        )
        if (
            receipt.get("privacyLaunchGateSnapshot")
            != UNSIGNED_PRIVACY_LAUNCH_GATE_SNAPSHOT
            or receipt.get("privacyLaunchGateSnapshotSha256")
            != _ui_compact_sha256(UNSIGNED_PRIVACY_LAUNCH_GATE_SNAPSHOT)
        ):
            _fail("Registry PREPARE privacy launch-gate snapshot drifted")
        if (
            receipt.get("codeDeployCurrentShelfAuthority")
            != manifest_profile["codeDeployReview"]
            or receipt.get("retainedIncumbentProvenance")
            != manifest_profile["retainedProvenance"]
        ):
            _fail("Registry PREPARE projected review/provenance custody drifted")
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
        source_canonical_raw=source_canonical_raw,
        source_compatibility_raw=source_compatibility_raw,
    )
    fresh = scope.get("freshDelta")
    if not isinstance(fresh, list) or len(fresh) != (3 if profile_enabled else 2):
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
    if (
        profile_enabled
        and receipt.get("sourceShelfInventorySha256")
        != composition.get("proposedShelfInventorySha256")
    ):
        _fail("Registry PREPARE source shelf inventory digest drifted")

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
    if profile_enabled:
        if source_canonical_raw is None or source_compatibility_raw is None:
            _fail("Registry PREPARE profile source manifests are missing")
        review = manifest_profile["codeDeployReview"]
        retained_provenance = manifest_profile["retainedProvenance"]
        if (
            review.get("sourceCanonicalManifestSha256")
            != hashlib.sha256(source_canonical_raw).hexdigest()
            or review.get("sourceCompatibilityManifestSha256")
            != hashlib.sha256(source_compatibility_raw).hexdigest()
            or review.get("sourceShelfInventorySha256")
            != receipt.get("sourceShelfInventorySha256")
            or review.get("incumbentSnapshotSha256")
            != incumbent.get("snapshotSha256")
            or retained_provenance.get("incumbentCanonicalManifestSha256")
            != incumbent.get("canonicalManifest", {}).get("sha256")
            or retained_provenance.get("incumbentCompatibilityManifestSha256")
            != incumbent.get("compatibilityManifest", {}).get("sha256")
            or retained_provenance.get("incumbentFullShelfInventorySha256")
            != incumbent.get("fullShelfInventorySha256")
            or retained_provenance.get("retainedInventorySha256")
            != receipt.get("retainedInventorySha256")
        ):
            _fail("Registry PREPARE profile review/incumbent digest graph drifted")
        retained_ids = manifest_profile["retainedArtifactIds"]
        projected_compatibility = _strict_json_bytes(
            compatibility_raw,
            label="Registry-projected compatibility manifest",
        )
        source_canonical = _strict_json_bytes(
            source_canonical_raw,
            label="Registry source canonical manifest",
        )
        source_compatibility = _strict_json_bytes(
            source_compatibility_raw,
            label="Registry source compatibility manifest",
        )
        for label, source_manifest, projected_manifest in (
            ("canonical", source_canonical, canonical),
            ("compatibility", source_compatibility, projected_compatibility),
        ):
            source_rows = source_manifest.get(
                "artifacts" if label == "canonical" else "downloads"
            )
            projected_rows = projected_manifest.get(
                "artifacts" if label == "canonical" else "downloads"
            )
            if not isinstance(source_rows, list) or not isinstance(projected_rows, list):
                _fail(f"Registry {label} retained artifact rows are missing")
            source_retained = [
                row
                for row in source_rows
                if isinstance(row, dict)
                and (row.get("artifactId") or row.get("id")) in retained_ids
            ]
            projected_retained = [
                row
                for row in projected_rows
                if isinstance(row, dict)
                and (row.get("artifactId") or row.get("id")) in retained_ids
            ]
            if (
                len(source_retained) != len(retained_ids)
                or len(projected_retained) != len(retained_ids)
                or source_retained != projected_retained
            ):
                _fail(
                    f"Registry projected retained {label} artifacts differ from source custody"
                )

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
    if profile_enabled:
        profile_retains_macos = (
            manifest_profile["retainedArtifactIds"]
            == UNSIGNED_RETAINED_ARTIFACT_IDS
        )
        profile_retains_linux = (
            manifest_profile["retainedArtifactIds"]
            == UNSIGNED_RETAINED_LINUX_ARTIFACT_IDS
        )
        expected_retained_platforms = (
            ["macos"]
            if profile_retains_macos
            else ["linux"]
            if profile_retains_linux
            else []
        )
        expected_shelf_platforms = (
            ["macos", "windows"]
            if profile_retains_macos
            else ["linux", "windows"]
            if profile_retains_linux
            else ["windows"]
        )
        expected_canonical_platforms = (
            {"macos", "windows"}
            if profile_retains_macos
            else {"linux", "windows"}
            if profile_retains_linux
            else {"windows"}
        )
        if (
            retained_platforms != expected_retained_platforms
            or shelf_platforms != expected_shelf_platforms
            or canonical_platforms != expected_canonical_platforms
        ):
            _fail("Registry PREPARE profile shelf platform set drifted")

    _validate_registry_projection_inputs_v2(
        receipt.get("projectionInputs"), profile_enabled=profile_enabled
    )
    provenance = receipt.get("provenance")
    if provenance != composition.get("provenance"):
        _fail("Registry PREPARE v2 provenance differs from composition custody")
    return {
        "composition": composition,
        "compositionRaw": composition_raw,
        "fullInventory": full_inventory,
        "retainedInventory": retained,
        "windowsDelta": expected_windows_delta,
        "profileEnabled": profile_enabled,
        "registryCommit": registry_commit,
        "sourceFiles": source_files,
    }


def _validate_registry_projection_inputs_v2(
    value: object, *, profile_enabled: bool = False
) -> None:
    expected_paths = {
        "materializer": "scripts/materialize_unsigned_preview_publication_delta.py",
        "schema": "contracts/preview-publication-delta-v2.schema.json",
    }
    if profile_enabled:
        expected_paths.update(
            {
                "releaseChannelMaterializer": (
                    "scripts/materialize_public_release_channel.py"
                ),
                "releaseChannelVerifier": (
                    "scripts/verify_public_release_channel.py"
                ),
            }
        )
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
    profile_enabled = candidate_validation.get("profileEnabled") is True
    expected_authority_keys = (
        REGISTRY_AUTHORITY_PROFILE_KEYS
        if profile_enabled
        else REGISTRY_AUTHORITY_V2_KEYS
    )
    expected_finalize_keys = (
        REGISTRY_FINALIZE_PROFILE_KEYS
        if profile_enabled
        else REGISTRY_FINALIZE_V2_KEYS
    )
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
        set(authority) != expected_authority_keys
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
    if profile_enabled:
        registry_commit = _matching_alias(
            authority,
            "registryCommit",
            "registry_commit",
            label="Registry unsigned FINALIZE authority Registry commit",
        )
        source_files = dict(candidate_validation.get("sourceFiles") or [])
        source_canonical = source_files.get(UNSIGNED_SOURCE_CANONICAL_PATH)
        source_compatibility = source_files.get(UNSIGNED_SOURCE_COMPATIBILITY_PATH)
        if (
            authority.get("projectionProfile") != UNSIGNED_V3_PROJECTION_PROFILE
            or registry_commit != candidate_validation.get("registryCommit")
            or authority.get("codeDeployCurrentShelfAuthority")
            != registry_candidate.get("codeDeployCurrentShelfAuthority")
            or authority.get("retainedIncumbentProvenance")
            != registry_candidate.get("retainedIncumbentProvenance")
            or authority.get("privacyLaunchGateSnapshot")
            != UNSIGNED_PRIVACY_LAUNCH_GATE_SNAPSHOT
            or authority.get("privacyLaunchGateSnapshotSha256")
            != _ui_compact_sha256(UNSIGNED_PRIVACY_LAUNCH_GATE_SNAPSHOT)
            or authority.get("sourceShelfInventorySha256")
            != registry_candidate.get("sourceShelfInventorySha256")
            or source_canonical is None
            or source_compatibility is None
        ):
            _fail("Registry unsigned FINALIZE authority profile graph drifted")
        _expect_reference(
            authority.get("sourceCanonicalManifest"),
            path=UNSIGNED_SOURCE_CANONICAL_PATH,
            raw=source_canonical,
            label="Registry unsigned authority source canonical manifest",
        )
        _expect_reference(
            authority.get("sourceCompatibilityManifest"),
            path=UNSIGNED_SOURCE_COMPATIBILITY_PATH,
            raw=source_compatibility,
            label="Registry unsigned authority source compatibility manifest",
        )
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
    _validate_registry_projection_inputs_v2(
        authority.get("projectionInputs"), profile_enabled=profile_enabled
    )
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
        set(finalize) != expected_finalize_keys
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
    if profile_enabled:
        finalize_registry_commit = _matching_alias(
            finalize,
            "registryCommit",
            "registry_commit",
            label="Registry unsigned FINALIZE receipt Registry commit",
        )
        source_files = dict(candidate_validation.get("sourceFiles") or [])
        source_canonical = source_files.get(UNSIGNED_SOURCE_CANONICAL_PATH)
        source_compatibility = source_files.get(UNSIGNED_SOURCE_COMPATIBILITY_PATH)
        if (
            finalize.get("projectionProfile") != UNSIGNED_V3_PROJECTION_PROFILE
            or finalize_registry_commit != candidate_validation.get("registryCommit")
            or finalize.get("codeDeployCurrentShelfAuthority")
            != registry_candidate.get("codeDeployCurrentShelfAuthority")
            or finalize.get("retainedIncumbentProvenance")
            != registry_candidate.get("retainedIncumbentProvenance")
            or finalize.get("privacyLaunchGateSnapshot")
            != UNSIGNED_PRIVACY_LAUNCH_GATE_SNAPSHOT
            or finalize.get("privacyLaunchGateSnapshotSha256")
            != _ui_compact_sha256(UNSIGNED_PRIVACY_LAUNCH_GATE_SNAPSHOT)
            or finalize.get("sourceShelfInventorySha256")
            != registry_candidate.get("sourceShelfInventorySha256")
            or source_canonical is None
            or source_compatibility is None
        ):
            _fail("Registry unsigned FINALIZE receipt profile graph drifted")
        _expect_reference(
            finalize.get("sourceCanonicalManifest"),
            path=UNSIGNED_SOURCE_CANONICAL_PATH,
            raw=source_canonical,
            label="Registry unsigned finalize source canonical manifest",
        )
        _expect_reference(
            finalize.get("sourceCompatibilityManifest"),
            path=UNSIGNED_SOURCE_COMPATIBILITY_PATH,
            raw=source_compatibility,
            label="Registry unsigned finalize source compatibility manifest",
        )
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


def _generation_projector() -> Any:
    path = Path(__file__).resolve().parents[1] / "release_shelf_generation.py"
    spec = importlib.util.spec_from_file_location(
        "chummer_candidate_authority_generation_projector",
        path,
    )
    if spec is None or spec.loader is None:
        _fail("generation projector cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _authority_seed_reference(
    bundle_root: Path,
    candidate_rows: list[dict[str, Any]],
    relative: str,
) -> tuple[dict[str, Any], bytes]:
    path = _plain_file(
        bundle_root / relative,
        label=f"native-stage authority seed {relative}",
        maximum_bytes=MAX_JSON_BYTES,
    )
    raw = path.read_bytes()
    expected = {
        "path": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
    }
    indexed = {row["path"]: row for row in candidate_rows}
    if indexed.get(relative) != expected:
        _fail(f"native-stage authority seed {relative} differs from candidate inventory")
    return expected, raw


def _validate_generation_projection_bridge(
    *,
    preprojection_bundle_root: Path,
    bundle_root: Path,
    candidate_rows: list[dict[str, Any]],
    candidate_file_modes: dict[str, int],
    candidate_directory_modes: list[dict[str, Any]],
    canonical: dict[str, Any],
    canonical_bytes: bytes,
    compatibility: dict[str, Any],
    compatibility_bytes: bytes,
    evaluated_at: str,
) -> dict[str, Any]:
    if (
        not preprojection_bundle_root.is_dir()
        or preprojection_bundle_root.is_symlink()
        or preprojection_bundle_root == bundle_root
    ):
        _fail("preprojection bundle root must be one distinct physical directory")
    (
        source_rows,
        source_file_modes,
        source_directory_modes,
        source_files,
    ) = _scan_bundle_tree(preprojection_bundle_root)
    source_canonical_bytes = source_files.get("RELEASE_CHANNEL.generated.json")
    source_compatibility_bytes = source_files.get("releases.json")
    if source_canonical_bytes is None or source_compatibility_bytes is None:
        _fail("preprojection bundle omits its manifest pair")
    source_canonical = _strict_json_bytes(
        source_canonical_bytes,
        label="preprojection canonical manifest",
    )
    source_compatibility = _strict_json_bytes(
        source_compatibility_bytes,
        label="preprojection compatibility manifest",
    )
    generation_id = canonical.get("generationId")
    if (
        not isinstance(generation_id, str)
        or re.fullmatch(r"[A-Za-z0-9._-]+", generation_id) is None
        or generation_id in {".", ".."}
        or ".." in generation_id
        or compatibility.get("generationId") != generation_id
        or source_canonical.get("generationId") is not None
        or source_compatibility.get("generationId") is not None
    ):
        _fail("generation projection identity is invalid or already consumed")
    projection_time = _timestamp(
        evaluated_at,
        label="generation projection evaluation time",
    )

    source_by_path = {row["path"]: row for row in source_rows}
    candidate_by_path = {row["path"]: row for row in candidate_rows}
    if set(candidate_by_path) != {
        *source_by_path,
        *NATIVE_STAGE_AUTHORITY_SEED_PATHS,
    }:
        _fail("generation-projected candidate has extra or missing authority-seed files")
    for relative, source_row in source_by_path.items():
        if relative in {"RELEASE_CHANNEL.generated.json", "releases.json"}:
            continue
        if (
            candidate_by_path.get(relative) != source_row
            or candidate_file_modes.get(relative) != source_file_modes.get(relative)
        ):
            _fail("generation projection changed a non-manifest candidate byte")
    expected_directories = [
        *source_directory_modes,
        {"mode": candidate_directory_modes_by_path(candidate_directory_modes).get(
            "release-evidence"
        ), "path": "release-evidence"},
    ]
    if (
        expected_directories[-1]["mode"] is None
        or sorted(expected_directories, key=lambda row: row["path"])
        != candidate_directory_modes
    ):
        _fail("generation-projected candidate directory set drifted")

    projector = _generation_projector()
    with tempfile.TemporaryDirectory(prefix="candidate-generation-projection-") as name:
        root = Path(name)
        source_canonical_path = root / "RELEASE_CHANNEL.generated.json"
        source_compatibility_path = root / "releases.json"
        source_canonical_path.write_bytes(source_canonical_bytes)
        source_compatibility_path.write_bytes(source_compatibility_bytes)
        projector.project_manifest_pair(
            source_canonical_path,
            source_compatibility_path,
            generation_id,
            evaluated_at=projection_time,
        )
        if (
            source_canonical_path.read_bytes() != canonical_bytes
            or source_compatibility_path.read_bytes() != compatibility_bytes
        ):
            _fail("candidate manifests are not the exact deterministic generation projection")

    seed_references: dict[str, dict[str, Any]] = {}
    seed_payloads: dict[str, dict[str, Any]] = {}
    seed_raws: dict[str, bytes] = {}
    for relative in NATIVE_STAGE_AUTHORITY_SEED_PATHS:
        reference, raw = _authority_seed_reference(
            bundle_root,
            candidate_rows,
            relative,
        )
        seed_references[relative.rsplit("/", 1)[-1]] = reference
        seed_raws[relative] = raw
        seed_payloads[relative] = _strict_json_bytes(
            raw,
            label=f"native-stage authority seed {relative}",
        )
    current = seed_payloads["release-evidence/CURRENT.json"]
    decision_raw = seed_raws["release-evidence/RELEASE_DECISION.json"]
    snapshot_raw = seed_raws["release-evidence/SNAPSHOT.json"]
    decision = seed_payloads["release-evidence/RELEASE_DECISION.json"]
    snapshot = seed_payloads["release-evidence/SNAPSHOT.json"]
    if (
        current.get("status") != "review_required"
        or snapshot.get("releaseDecisionStatus") != "review_required"
        or decision.get("releaseDecisionStatus") != "review_required"
        or snapshot.get("manifestSha256") != hashlib.sha256(canonical_bytes).hexdigest()
        or decision.get("manifestSha256") != hashlib.sha256(canonical_bytes).hexdigest()
        or current.get("snapshotSha256") != hashlib.sha256(snapshot_raw).hexdigest()
        or current.get("decisionSha256") != hashlib.sha256(decision_raw).hexdigest()
        or snapshot.get("releaseDecisionSha256")
        != hashlib.sha256(decision_raw).hexdigest()
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(decision.get("releaseScopeDecisionSha256") or ""),
        ) is None
    ):
        _fail("native-stage authority seed does not bind the projected review posture")

    return {
        "contractName": GENERATION_PROJECTION_CONTRACT,
        "contractVersion": 1,
        "status": "passed",
        "generationId": generation_id,
        "evaluatedAtUtc": projection_time.isoformat().replace("+00:00", "Z"),
        "sourceCanonicalManifestSha256": hashlib.sha256(
            source_canonical_bytes
        ).hexdigest(),
        "sourceCompatibilityManifestSha256": hashlib.sha256(
            source_compatibility_bytes
        ).hexdigest(),
        "projectedCanonicalManifestSha256": hashlib.sha256(
            canonical_bytes
        ).hexdigest(),
        "projectedCompatibilityManifestSha256": hashlib.sha256(
            compatibility_bytes
        ).hexdigest(),
        "authoritySeed": seed_references,
        "source": {
            "rows": source_rows,
            "fileModes": source_file_modes,
            "directoryModes": source_directory_modes,
            "canonical": source_canonical,
            "canonicalBytes": source_canonical_bytes,
            "compatibility": source_compatibility,
            "compatibilityBytes": source_compatibility_bytes,
        },
    }


def candidate_directory_modes_by_path(
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    return {row["path"]: row["mode"] for row in rows}


def _build_candidate_authority(
    *,
    unsigned_preview: bool,
    unsigned_native_bridge: bool,
    unsigned_native_generation_bridge: bool,
    now: datetime,
    expires_at: datetime,
    candidate: dict[str, Any],
    custody: dict[str, Any],
) -> dict[str, Any]:
    if unsigned_native_bridge and not unsigned_preview:
        _fail("owner native finalization bridge requires unsigned preview authority")
    if unsigned_native_generation_bridge and not unsigned_native_bridge:
        _fail("native generation bridge requires owner native finalization authority")
    authority: dict[str, Any] = {
        "contractName": (
            UNSIGNED_NATIVE_GENERATION_AUTHORITY_CONTRACT
            if unsigned_native_generation_bridge
            else UNSIGNED_NATIVE_AUTHORITY_CONTRACT
            if unsigned_native_bridge
            else UNSIGNED_AUTHORITY_CONTRACT
            if unsigned_preview
            else AUTHORITY_CONTRACT
        ),
        "contractVersion": (
            5
            if unsigned_native_generation_bridge
            else 4
            if unsigned_native_bridge
            else 3
            if unsigned_preview
            else 2
        ),
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
        if unsigned_native_bridge:
            authority["ownerNativeFinalizationBridgeAuthority"] = True
        if unsigned_native_generation_bridge:
            authority["ownerNativeStageAuthoritySeedBridgeAuthority"] = True
    return authority


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
    profile_enabled = (
        _unsigned_profile_enabled(
            publication_scope, label="unsigned UI publication scope"
        )
        if unsigned_preview
        else False
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

    preprojection_value = str(args.preprojection_bundle_root).strip()
    projection_time_value = str(args.generation_projection_evaluated_at).strip()
    if bool(preprojection_value) != bool(projection_time_value):
        _fail(
            "generation projection requires both preprojection bundle root and evaluated-at"
        )
    generation_projection: dict[str, Any] | None = None
    validation_rows = candidate_rows
    validation_file_modes = candidate_file_modes
    validation_directory_modes = candidate_directory_modes
    validation_canonical = canonical
    validation_canonical_bytes = canonical_bytes
    validation_compatibility_bytes = compatibility_bytes
    validation_scope = scope
    if preprojection_value:
        generation_projection = _validate_generation_projection_bridge(
            preprojection_bundle_root=Path(preprojection_value).resolve(strict=True),
            bundle_root=bundle_root,
            candidate_rows=candidate_rows,
            candidate_file_modes=candidate_file_modes,
            candidate_directory_modes=candidate_directory_modes,
            canonical=canonical,
            canonical_bytes=canonical_bytes,
            compatibility=compatibility,
            compatibility_bytes=compatibility_bytes,
            evaluated_at=projection_time_value,
        )
        source = generation_projection.pop("source")
        validation_rows = source["rows"]
        validation_file_modes = source["fileModes"]
        validation_directory_modes = source["directoryModes"]
        validation_canonical = source["canonical"]
        validation_canonical_bytes = source["canonicalBytes"]
        validation_compatibility_bytes = source["compatibilityBytes"]
        validation_scope = _canonical_windows_scope(
            validation_canonical,
            validation_rows,
            allow_ancillary_files=True,
            expected_channel="preview",
        )
        if validation_scope["version"] != scope["version"]:
            _fail("preprojection and projected release identities differ")

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

    unsigned_native_bridge = (
        unsigned_preview
        and bool(str(args.windows_finalized_root).strip())
    )
    unsigned_native_generation_bridge = generation_projection is not None
    if unsigned_native_generation_bridge and not unsigned_native_bridge:
        _fail("generation projection authority requires native finalization custody")
    native_evidence: dict[str, Any] | None = None
    native_custody_files: list[tuple[str, bytes]] = []
    if unsigned_preview:
        expires_at = now + timedelta(seconds=lifetime_seconds)
        publication_evidence, publication_files = (
            _validate_unsigned_publication_scope_v3(
                stage_root,
                validation_file_modes,
                publication_scope,
                publication_scope_bytes,
                candidate=candidate,
                candidate_rows=validation_rows,
                canonical_bytes=validation_canonical_bytes,
                compatibility_bytes=validation_compatibility_bytes,
                canonical_scope=validation_scope,
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
            canonical=validation_canonical,
            canonical_raw=validation_canonical_bytes,
            compatibility_raw=validation_compatibility_bytes,
            candidate_summary=candidate,
            candidate_directory_modes=validation_directory_modes,
            scope=publication_scope,
        )
        publication_files.extend(candidate_validation["sourceFiles"])
        if unsigned_native_bridge:
            publication_file_by_path = dict(publication_files)
            source_canonical_bytes = publication_file_by_path.get(
                UNSIGNED_SOURCE_CANONICAL_PATH
            )
            source_compatibility_bytes = publication_file_by_path.get(
                UNSIGNED_SOURCE_COMPATIBILITY_PATH
            )
            if (
                source_canonical_bytes is None
                or source_compatibility_bytes is None
            ):
                _fail(
                    "unsigned v4 authority requires preserved source "
                    "publication manifests"
                )
            expected_content_bytes: dict[str, bytes] = {
                UNSIGNED_COMPOSITION_FILE: candidate_validation["compositionRaw"],
                "publication/RELEASE_CHANNEL.generated.json":
                    source_canonical_bytes,
                "publication/releases.json": source_compatibility_bytes,
            }
            for provenance_path in UNSIGNED_PROVENANCE_PATHS.values():
                provenance_bytes = publication_file_by_path.get(provenance_path)
                if provenance_bytes is None:
                    _fail(
                        "unsigned v4 authority requires exact candidate "
                        f"provenance bytes for {provenance_path}"
                    )
                expected_content_bytes[provenance_path] = provenance_bytes
            expected_content_rows = [
                {
                    "path": path,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "sizeBytes": len(payload),
                }
                for path, payload in expected_content_bytes.items()
            ]
            candidate_row_by_path = {
                row["path"]: row
                for row in candidate_rows
            }
            for head in scope["heads"]:
                installer_path = scope["artifacts"][head]["installer"]["path"]
                payload_path = scope["artifacts"][head]["payload"]["path"]
                for candidate_path in (
                    installer_path,
                    payload_path,
                    f"{payload_path}.json",
                ):
                    candidate_row = candidate_row_by_path.get(candidate_path)
                    if candidate_row is None:
                        _fail(
                            "unsigned v4 authority requires exact candidate "
                            f"bytes for {candidate_path}"
                        )
                    expected_content_rows.append(
                        {
                            **candidate_row,
                            "path": f"publication/{candidate_path}",
                        }
                    )
            expected_content_rows.sort(key=lambda row: row["path"])
            payload_path = scope["artifacts"][scope["heads"][0]]["payload"][
                "path"
            ]
            expected_installed_executable = _derive_unsigned_payload_executable(
                bundle_root,
                payload_path=payload_path,
                payload_row=candidate_row_by_path[payload_path],
            )
            stage_native_root = stage_root / "proof" / "windows-native"
            if stage_native_root.is_symlink():
                _fail(
                    "publication-stage unsigned Windows native evidence root "
                    "must not be a symlink"
                )
            stage_native_root = stage_native_root.resolve(strict=True)
            configured_native_root = Path(args.windows_finalized_root).resolve(
                strict=True
            )
            if configured_native_root != stage_native_root:
                _fail(
                    "unsigned Windows finalized root must be publication-stage "
                    "proof/windows-native"
                )
            native_evidence, oldest_native_proof = (
                _validate_unsigned_native_evidence(
                    stage_native_root,
                    candidate_rows=candidate_rows,
                    source_canonical_bytes=source_canonical_bytes,
                    source_compatibility_bytes=source_compatibility_bytes,
                    expected_content_rows=expected_content_rows,
                    expected_installed_executable=(
                        expected_installed_executable
                    ),
                    scope=scope,
                    publication_source_sha=publication_evidence["sourceSha"],
                    now=now,
                    max_age=timedelta(seconds=max_age_seconds),
                )
            )
            expires_at = min(
                expires_at,
                oldest_native_proof + timedelta(seconds=max_age_seconds),
            )
            if expires_at <= now + timedelta(minutes=1):
                _fail(
                    "fresh unsigned native-Windows evidence has insufficient "
                    "remaining authority lifetime"
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
            canonical=validation_canonical,
            canonical_raw=validation_canonical_bytes,
            compatibility_raw=validation_compatibility_bytes,
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
    if unsigned_native_bridge:
        publication_files.append(
            (
                UNSIGNED_COMPOSITION_FILE,
                candidate_validation["compositionRaw"],
            )
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
    if generation_projection is not None:
        custody["generationProjection"] = generation_projection
    if unsigned_preview:
        custody["unsignedPublicationEvidence"] = {
            **publication_evidence,
            "files": [
                _embedded(path, payload)
                for path, payload in sorted(publication_files)
            ],
        }
        if unsigned_native_bridge:
            if native_evidence is None:
                _fail(
                    "unsigned v4 native evidence disappeared before custody sealing"
                )
            custody["nativeWindowsFinalizedEvidence"] = native_evidence
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

    authority = _build_candidate_authority(
        unsigned_preview=unsigned_preview,
        unsigned_native_bridge=unsigned_native_bridge,
        unsigned_native_generation_bridge=unsigned_native_generation_bridge,
        now=now,
        expires_at=expires_at,
        candidate=candidate,
        custody=custody,
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
    parser.add_argument(
        "--windows-finalized-root",
        default="",
        help=(
            "exact publication-stage proof/windows-native root; omit only for "
            "stage-only unsigned v3 authority"
        ),
    )
    parser.add_argument("--publication-stage-root", required=True)
    parser.add_argument(
        "--preprojection-bundle-root",
        default="",
        help=(
            "exact Registry-reviewed bundle before deterministic generation "
            "projection; requires --generation-projection-evaluated-at"
        ),
    )
    parser.add_argument(
        "--generation-projection-evaluated-at",
        default="",
        help="exact UTC instant used by the deterministic generation projector",
    )
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
