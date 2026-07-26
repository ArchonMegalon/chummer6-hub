#!/usr/bin/env python3
"""Snapshot and restore the exact active public-edge overlay under the shared lock."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _load_overlay_publisher():
    publisher_path = Path(__file__).resolve().with_name(
        "publish_public_edge_portal_overlay.py"
    )
    spec = importlib.util.spec_from_file_location(
        "chummer_public_edge_overlay_publisher",
        publisher_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load the public-edge overlay publisher")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    publisher_directory = str(publisher_path.parent)
    sys.path.insert(0, publisher_directory)
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(publisher_directory)
        except ValueError:
            pass
    return module


overlay = _load_overlay_publisher()


CONTRACT_NAME = "chummer.public-edge.overlay-transaction/v1"
ACTIVE_RUNTIME_AUTHORITY_CONTRACT_NAME = (
    "chummer.public-edge.active-runtime-authority/v1"
)
INSTALL_LINKING_AUTHORITY_READINESS_CONTRACT_NAME = (
    "chummer.install_linking_postgres_runtime_authority_readiness.v1"
)
INSTALL_LINKING_AUTHORITY_READINESS_FIELDS = {
    "authorityIdentitySha256",
    "checkedAtUtc",
    "code",
    "contractName",
    "currentRoleMatches",
    "leastPrivilegeValid",
    "ready",
    "runtimeRoleSha256",
    "status",
}
ACTIVE_RUNTIME_AUTHORITY_FIELDS = {
    "contractName",
    "generatedAtUtc",
    "installLinkingAuthorityReadinessPath",
    "installLinkingAuthorityReadinessSha256",
    "portal",
    "status",
}
PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE = "public-download-only"
FULL_RUNTIME_PROFILE = "full"
PUBLIC_DOWNLOAD_ONLY_ACTIVE_RUNTIME_AUTHORITY_FIELDS = {
    "contractName",
    "deploymentOperation",
    "generatedAtUtc",
    "portal",
    "publicProjectionManifestSha256",
    "publicProjectionSnapshotId",
    "publicProjectionSnapshotSha256",
    "runtimeProfile",
    "sourceHead",
    "status",
}
ACTIVE_RUNTIME_PORTAL_FIELDS = {
    "containerId",
    "containerName",
    "existed",
    "imageId",
    "proofAuthorityMountSha256",
    "proofPublicMountSha256",
    "wasRunning",
}
LOWERCASE_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_INSTALL_LINKING_AUTHORITY_READINESS_BYTES = 16 * 1024
TRANSACTION_PHASES = (
    "prepared",
    "image_build_started",
    "image_built",
    "tunnel_drained",
    "portal_stopped",
    "overlay_activated",
    "portal_candidate_started",
    "tunnel_started",
)
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LEGACY_RUNTIME_PRIOR_STATE_FIELDS = {
    "candidatePortalContainerName",
    "expectedRuntimeProofBindSourceSha256",
    "publicProjectionManifestSha256",
    "publicProjectionSnapshotId",
    "publicProjectionSnapshotSha256",
    "priorImageTagId",
    "priorToolImageTagId",
    "priorPortalContainerId",
    "priorPortalContainerName",
    "priorPortalImageId",
    "priorPortalProofAuthorityMountSha256",
    "priorPortalProofPublicMountSha256",
    "priorPortalExisted",
    "priorPortalWasRunning",
    "priorTunnelContainerId",
    "priorTunnelImageId",
    "priorTunnelExisted",
    "priorTunnelWasRunning",
}
RUNTIME_PRIOR_STATE_FIELDS = LEGACY_RUNTIME_PRIOR_STATE_FIELDS | {
    "priorTunnelReplicaContainerId",
    "priorTunnelReplicaImageId",
    "priorTunnelReplicaExisted",
    "priorTunnelReplicaWasRunning",
}
DEPLOY_OVERLAY_AUTHORITY_FIELDS = {
    "activationReceipt",
    "backupRoot",
    "candidateProofBindSourceSnapshot",
    "priorPortalProofAuthoritySnapshot",
    "priorPortalProofPublicSnapshot",
    "proofBindSourcePath",
    "stagingRoot",
}
PUBLIC_DOWNLOAD_DEPLOY_OVERLAY_AUTHORITY_FIELDS = (
    DEPLOY_OVERLAY_AUTHORITY_FIELDS
    | {
        "priorActiveRuntimeAuthorityExisted",
        "priorActiveRuntimeAuthoritySnapshotPath",
        "priorActiveRuntimeAuthoritySnapshotSha256",
    }
)
SOURCE_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DEPLOYMENT_OPERATION_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)
FULL_SNAPSHOT_FIELDS = {
    "activeExisted",
    "activeRoot",
    "contractName",
    "deployOverlayAuthority",
    "operation",
    "phase",
    "priorActiveFingerprint",
    "priorActiveIdentity",
    "runtimePriorState",
    "sourceRoot",
    "status",
}
PUBLIC_DOWNLOAD_SNAPSHOT_FIELDS = FULL_SNAPSHOT_FIELDS | {
    "deploymentOperation",
    "runtimeProfile",
    "sourceHead",
}

APPARENT_SECRET_PATTERNS = (
    re.compile(
        rb"(?i)(?:password|passwd|pwd|token|secret|credential|account[_ -]?key|"
        rb"accountkey|shared[_ -]?access[_ -]?(?:key|signature)|"
        rb"client[_ -]?secret|private[_ -]?key|authorization|api[_ -]?key|"
        rb"access[_ -]?key|sas[_ -]?key)\s*[:=]"
    ),
    re.compile(rb"://[^/\s:@]+:[^@\s/]+@"),
    re.compile(rb"(?i)\bpostgres(?:ql)?://"),
    re.compile(
        rb"(?i)[?&](?:access_token|api[_-]?key|client_secret|password|"
        rb"sharedaccesssignature|sig|token)="
    ),
    re.compile(
        rb"(?i)-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY|CERTIFICATE)-----"
    ),
    re.compile(rb"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(rb"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}"),
    re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\."
        rb"[A-Za-z0-9_-]{8,}\b"
    ),
)


def validate_runtime_prior_state(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) not in (
        LEGACY_RUNTIME_PRIOR_STATE_FIELDS,
        RUNTIME_PRIOR_STATE_FIELDS,
    ):
        raise RuntimeError("overlay transaction runtime prior-state fields are invalid")
    state = dict(value)
    if set(state) == LEGACY_RUNTIME_PRIOR_STATE_FIELDS:
        # Absence was never observed by these journals.  Synthesizing it would
        # let recovery delete a live canonical replica that the old writer did
        # not know to snapshot.
        raise RuntimeError(
            "legacy overlay transaction lacks canonical tunnel replica authority"
        )
    expected_proof_sha256 = state["expectedRuntimeProofBindSourceSha256"]
    if (
        not isinstance(expected_proof_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_proof_sha256) is None
    ):
        raise RuntimeError(
            "overlay transaction expected runtime proof bind-source SHA-256 is invalid"
        )
    snapshot_id = state["publicProjectionSnapshotId"]
    snapshot_sha256 = state["publicProjectionSnapshotSha256"]
    manifest_sha256 = state["publicProjectionManifestSha256"]
    if (
        not isinstance(snapshot_id, str)
        or re.fullmatch(r"public-projection-[0-9a-f]{64}", snapshot_id) is None
        or not isinstance(snapshot_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256) is None
        or snapshot_id != f"public-projection-{snapshot_sha256}"
        or not isinstance(manifest_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
    ):
        raise RuntimeError(
            "overlay transaction public projection generation identity is invalid"
        )
    candidate_name = state["candidatePortalContainerName"]
    if (
        not isinstance(candidate_name, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,127}", candidate_name) is None
    ):
        raise RuntimeError("overlay transaction candidate portal name is invalid")
    for field in ("priorImageTagId", "priorToolImageTagId"):
        image_id = state[field]
        if not isinstance(image_id, str) or (
            image_id and IMAGE_ID_PATTERN.fullmatch(image_id) is None
        ):
            raise RuntimeError(f"overlay transaction {field} is invalid")
    for prefix in ("Portal", "Tunnel", "TunnelReplica"):
        existed = state[f"prior{prefix}Existed"]
        was_running = state[f"prior{prefix}WasRunning"]
        container_id = state[f"prior{prefix}ContainerId"]
        image_id = state[f"prior{prefix}ImageId"]
        if not isinstance(existed, bool) or not isinstance(was_running, bool):
            raise RuntimeError(
                f"overlay transaction prior {prefix.lower()} state flags are invalid"
            )
        if not isinstance(container_id, str) or not isinstance(image_id, str):
            raise RuntimeError(
                f"overlay transaction prior {prefix.lower()} identities are invalid"
            )
        if existed:
            if (
                CONTAINER_ID_PATTERN.fullmatch(container_id) is None
                or IMAGE_ID_PATTERN.fullmatch(image_id) is None
            ):
                raise RuntimeError(
                    f"overlay transaction prior {prefix.lower()} identities are invalid"
                )
        elif container_id or image_id or was_running:
            raise RuntimeError(
                f"absent prior {prefix.lower()} cannot claim identity or running state"
            )
    prior_portal_name = state["priorPortalContainerName"]
    if not isinstance(prior_portal_name, str) or (
        prior_portal_name
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", prior_portal_name)
        is None
    ):
        raise RuntimeError("overlay transaction prior portal name is invalid")
    if state["priorPortalExisted"] != bool(prior_portal_name):
        raise RuntimeError("prior portal name does not match its existence state")
    if prior_portal_name and candidate_name == prior_portal_name:
        raise RuntimeError("candidate portal name must differ from the prior portal")
    authority_digest = state["priorPortalProofAuthorityMountSha256"]
    public_digest = state["priorPortalProofPublicMountSha256"]
    for field, digest in (
        ("priorPortalProofAuthorityMountSha256", authority_digest),
        ("priorPortalProofPublicMountSha256", public_digest),
    ):
        if not isinstance(digest, str) or (
            digest and re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise RuntimeError(f"overlay transaction {field} is invalid")
    if state["priorPortalWasRunning"]:
        if not authority_digest or not public_digest:
            raise RuntimeError(
                "running prior portal requires both proof mount digests"
            )
        if authority_digest != public_digest:
            raise RuntimeError(
                "prior portal proof mounts cannot be recreated from one bind source"
            )
    elif authority_digest or public_digest:
        raise RuntimeError(
            "stopped or absent prior portal cannot claim mounted proof digests"
        )
    return state


def active_runtime_authority_payload(
    *,
    portal_existed: bool,
    portal_container_id: str,
    portal_container_name: str,
    portal_image_id: str,
    portal_was_running: bool,
    proof_authority_mount_sha256: str,
    proof_public_mount_sha256: str,
) -> dict[str, Any]:
    synthetic_state = {
        "candidatePortalContainerName": "authority-validation-placeholder",
        "expectedRuntimeProofBindSourceSha256": "0" * 64,
        "publicProjectionManifestSha256": "0" * 64,
        "publicProjectionSnapshotId": "public-projection-" + "0" * 64,
        "publicProjectionSnapshotSha256": "0" * 64,
        "priorImageTagId": "",
        "priorToolImageTagId": "",
        "priorPortalContainerId": portal_container_id,
        "priorPortalContainerName": portal_container_name,
        "priorPortalImageId": portal_image_id,
        "priorPortalProofAuthorityMountSha256": proof_authority_mount_sha256,
        "priorPortalProofPublicMountSha256": proof_public_mount_sha256,
        "priorPortalExisted": portal_existed,
        "priorPortalWasRunning": portal_was_running,
        "priorTunnelContainerId": "",
        "priorTunnelImageId": "",
        "priorTunnelExisted": False,
        "priorTunnelWasRunning": False,
        "priorTunnelReplicaContainerId": "",
        "priorTunnelReplicaImageId": "",
        "priorTunnelReplicaExisted": False,
        "priorTunnelReplicaWasRunning": False,
    }
    validate_runtime_prior_state(synthetic_state)
    return {
        "contractName": ACTIVE_RUNTIME_AUTHORITY_CONTRACT_NAME,
        "status": "pass",
        "generatedAtUtc": overlay.now_iso(),
        "portal": {
            "existed": portal_existed,
            "containerId": portal_container_id,
            "containerName": portal_container_name,
            "imageId": portal_image_id,
            "wasRunning": portal_was_running,
            "proofAuthorityMountSha256": proof_authority_mount_sha256,
            "proofPublicMountSha256": proof_public_mount_sha256,
        },
    }


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    payload, _metadata = overlay.read_stable_regular_bytes(path, label=label)
    return overlay.strict_json_object_bytes(payload, label=label)


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _reject_apparent_secret_values(payload: object, *, label: str) -> None:
    if isinstance(payload, dict):
        values = payload.values()
    elif isinstance(payload, list):
        values = payload
    else:
        values = ()
    for value in values:
        if isinstance(value, (dict, list)):
            _reject_apparent_secret_values(value, label=label)
        elif isinstance(value, str):
            encoded = value.encode("utf-8", "strict")
            if any(pattern.search(encoded) for pattern in APPARENT_SECRET_PATTERNS):
                raise RuntimeError(f"{label} contains apparent secret material")


def _require_utc_timestamp(value: object, *, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "T" not in value
        or not (value.endswith("Z") or value.endswith("+00:00"))
    ):
        raise RuntimeError(f"{label} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{label} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise RuntimeError(f"{label} timestamp is not UTC")


def _validate_owner_only_evidence_root(path: Path, *, label: str) -> Path:
    normalized = overlay.normalized_absolute_path(path)
    if path != normalized:
        raise RuntimeError(f"{label} must be an exact canonical absolute path")
    overlay.assert_no_symlink_components(normalized, label=label)
    try:
        metadata = normalized.lstat()
    except OSError as exc:
        raise RuntimeError(f"unable to inspect {label} {normalized}: {exc}") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError(f"{label} must be a caller-owned mode-0700 directory")
    return normalized


def _read_owner_only_canonical_json(
    path: Path,
    *,
    label: str,
    evidence_root: Path,
    maximum_bytes: int,
) -> tuple[dict[str, Any], str]:
    normalized = overlay.normalized_absolute_path(path)
    if path != normalized or not path.is_absolute():
        raise RuntimeError(f"{label} path must be exact, canonical, and absolute")
    normalized_root = _validate_owner_only_evidence_root(
        evidence_root,
        label="active runtime evidence root",
    )
    if normalized.parent != normalized_root:
        raise RuntimeError(f"{label} must remain in the active runtime evidence root")
    payload_bytes, metadata = overlay.read_stable_regular_bytes(
        normalized,
        label=label,
        maximum_bytes=maximum_bytes,
    )
    if (
        metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise RuntimeError(
            f"{label} must be a caller-owned mode-0600 single-link regular file"
        )
    try:
        path_metadata = normalized.lstat()
    except OSError as exc:
        raise RuntimeError(f"unable to re-inspect {label} {normalized}: {exc}") from exc
    descriptor_identity = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
    )
    path_identity = (
        path_metadata.st_dev,
        path_metadata.st_ino,
        path_metadata.st_size,
        path_metadata.st_mtime_ns,
        path_metadata.st_ctime_ns,
        path_metadata.st_mode,
        path_metadata.st_nlink,
        path_metadata.st_uid,
        path_metadata.st_gid,
    )
    if descriptor_identity != path_identity:
        raise RuntimeError(f"{label} changed identity while it was being read")
    payload = overlay.strict_json_object_bytes(payload_bytes, label=label)
    if payload_bytes != _canonical_json_bytes(payload):
        raise RuntimeError(f"{label} is not canonical JSON")
    _reject_apparent_secret_values(payload, label=label)
    return payload, hashlib.sha256(payload_bytes).hexdigest()


def validate_install_linking_authority_readiness(
    path: Path,
    *,
    expected_sha256: str,
    evidence_root: Path,
) -> tuple[Path, str, dict[str, Any]]:
    if (
        not isinstance(expected_sha256, str)
        or LOWERCASE_SHA256_PATTERN.fullmatch(expected_sha256) is None
    ):
        raise RuntimeError(
            "InstallLinking authority readiness SHA-256 pin is invalid"
        )
    payload, actual_sha256 = _read_owner_only_canonical_json(
        path,
        label="InstallLinking authority readiness",
        evidence_root=evidence_root,
        maximum_bytes=MAX_INSTALL_LINKING_AUTHORITY_READINESS_BYTES,
    )
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "InstallLinking authority readiness SHA-256 does not match its pin"
        )
    if (
        set(payload) != INSTALL_LINKING_AUTHORITY_READINESS_FIELDS
        or payload.get("contractName")
        != INSTALL_LINKING_AUTHORITY_READINESS_CONTRACT_NAME
        or payload.get("code") != "runtime_role_least_privilege"
        or payload.get("status") != "pass"
        or payload.get("ready") is not True
        or payload.get("currentRoleMatches") is not True
        or payload.get("leastPrivilegeValid") is not True
        or not isinstance(payload.get("authorityIdentitySha256"), str)
        or LOWERCASE_SHA256_PATTERN.fullmatch(
            payload["authorityIdentitySha256"]
        )
        is None
        or not isinstance(payload.get("runtimeRoleSha256"), str)
        or LOWERCASE_SHA256_PATTERN.fullmatch(
            payload["runtimeRoleSha256"]
        )
        is None
    ):
        raise RuntimeError("InstallLinking authority readiness contract is invalid")
    _require_utc_timestamp(
        payload.get("checkedAtUtc"),
        label="InstallLinking authority readiness",
    )
    return overlay.normalized_absolute_path(path), actual_sha256, payload


def _stable_file_sha256(path: Path, *, label: str) -> str:
    payload, _metadata = overlay.read_stable_regular_bytes(path, label=label)
    return hashlib.sha256(payload).hexdigest()


def _same_path(left: object, right: Path) -> bool:
    try:
        return overlay.normalized_absolute_path(Path(str(left))) == right
    except (OSError, RuntimeError, ValueError):
        return False


def _fingerprint_matches(expected: object, actual: dict[str, Any]) -> bool:
    return isinstance(expected, dict) and overlay.fingerprint_envelope_matches(
        expected,
        actual,
    )


def _identity_matches(expected: object, actual: dict[str, int]) -> bool:
    if not isinstance(expected, dict):
        return False
    return expected == actual


def _current_state(active_root: Path) -> tuple[bool, dict[str, Any], dict[str, int]]:
    try:
        active_root.lstat()
    except FileNotFoundError:
        return False, {}, {}
    overlay.assert_regular_overlay_tree(active_root, label="active root")
    return (
        True,
        overlay.overlay_tree_fingerprint(active_root, label="active root"),
        overlay.directory_identity(active_root, label="active root"),
    )


def _state_matches(
    *,
    expected_existed: bool,
    expected_fingerprint: object,
    expected_identity: object,
    active_root: Path,
) -> bool:
    actual_existed, actual_fingerprint, actual_identity = _current_state(active_root)
    if actual_existed != expected_existed:
        return False
    if not expected_existed:
        return True
    return _fingerprint_matches(
        expected_fingerprint,
        actual_fingerprint,
    ) and _identity_matches(expected_identity, actual_identity)


def snapshot(
    *,
    source_root: Path,
    active_root: Path,
    output: Path,
    shared_mutation_lock_token: str,
    runtime_prior_state: dict[str, Any] | None = None,
    staging_root: Path | None = None,
    backup_root: Path | None = None,
    activation_receipt: Path | None = None,
    proof_bind_source: Path | None = None,
    candidate_proof_bind_source_snapshot: Path | None = None,
    prior_portal_proof_authority_snapshot: Path | None = None,
    prior_portal_proof_public_snapshot: Path | None = None,
    runtime_profile: str = FULL_RUNTIME_PROFILE,
    deployment_operation: str = "deploy",
    source_head: str = "",
    prior_active_runtime_authority_existed: bool | None = None,
    prior_active_runtime_authority_snapshot: Path | None = None,
    prior_active_runtime_authority_snapshot_sha256: str | None = None,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    active_root = overlay.normalized_absolute_path(active_root)
    output = overlay.normalized_absolute_path(output)
    with overlay.public_edge_mutation_lock(
        activate=True,
        inherited_token=shared_mutation_lock_token,
    ):
        with overlay.overlay_publish_lock(source_root, active_root):
            overlay.assert_no_incomplete_activation_transaction(active_root)
            existed, fingerprint, identity = _current_state(active_root)
            prior_runtime = dict(runtime_prior_state or {})
            deploy_authority: dict[str, Any] = {}
            if runtime_profile not in {
                FULL_RUNTIME_PROFILE,
                PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE,
            }:
                raise RuntimeError("overlay transaction runtime profile is invalid")
            if (
                runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE
                and DEPLOYMENT_OPERATION_PATTERN.fullmatch(
                    deployment_operation
                )
                is None
            ):
                raise RuntimeError(
                    "public-download transaction deployment operation is invalid"
                )
            if (
                runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE
                and prior_runtime
                and SOURCE_HEAD_PATTERN.fullmatch(source_head) is None
            ):
                raise RuntimeError(
                    "public-download deploy transaction requires an exact source HEAD"
                )
            if (
                runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE
                and source_head
                and SOURCE_HEAD_PATTERN.fullmatch(
                source_head
                )
                is None
            ):
                raise RuntimeError("overlay transaction source HEAD is invalid")
            if prior_runtime:
                prior_runtime = validate_runtime_prior_state(prior_runtime)
                if (
                    staging_root is None
                    or backup_root is None
                    or activation_receipt is None
                    or proof_bind_source is None
                    or candidate_proof_bind_source_snapshot is None
                ):
                    raise RuntimeError(
                        "deploy overlay authority paths are required with runtime prior state"
                    )
                normalized_staging_root = overlay.normalized_absolute_path(staging_root)
                normalized_backup_root = overlay.normalized_absolute_path(backup_root)
                normalized_activation_receipt = overlay.normalized_absolute_path(
                    activation_receipt
                )
                normalized_proof_bind_source = overlay.normalized_absolute_path(
                    proof_bind_source
                )
                normalized_candidate_proof_snapshot = (
                    overlay.normalized_absolute_path(
                        candidate_proof_bind_source_snapshot
                    )
                )
                expected_candidate_digest = prior_runtime[
                    "expectedRuntimeProofBindSourceSha256"
                ]
                if _stable_file_sha256(
                    normalized_proof_bind_source,
                    label="runtime proof bind source",
                ) != expected_candidate_digest or _stable_file_sha256(
                    normalized_candidate_proof_snapshot,
                    label="candidate runtime proof snapshot",
                ) != expected_candidate_digest:
                    raise RuntimeError(
                        "candidate runtime proof bytes do not match sealed authority"
                    )
                normalized_prior_authority_snapshot: Path | None = None
                normalized_prior_public_snapshot: Path | None = None
                if prior_runtime["priorPortalWasRunning"]:
                    if (
                        prior_portal_proof_authority_snapshot is None
                        or prior_portal_proof_public_snapshot is None
                    ):
                        raise RuntimeError(
                            "running prior portal requires both proof snapshots"
                        )
                    normalized_prior_authority_snapshot = (
                        overlay.normalized_absolute_path(
                            prior_portal_proof_authority_snapshot
                        )
                    )
                    normalized_prior_public_snapshot = (
                        overlay.normalized_absolute_path(
                            prior_portal_proof_public_snapshot
                        )
                    )
                    if _stable_file_sha256(
                        normalized_prior_authority_snapshot,
                        label="prior authority proof snapshot",
                    ) != prior_runtime[
                        "priorPortalProofAuthorityMountSha256"
                    ] or _stable_file_sha256(
                        normalized_prior_public_snapshot,
                        label="prior public proof snapshot",
                    ) != prior_runtime["priorPortalProofPublicMountSha256"]:
                        raise RuntimeError(
                            "prior portal proof snapshots do not match mounted authority"
                        )
                elif (
                    prior_portal_proof_authority_snapshot is not None
                    or prior_portal_proof_public_snapshot is not None
                ):
                    raise RuntimeError(
                        "stopped or absent prior portal cannot claim proof snapshots"
                    )
                if normalized_staging_root == active_root:
                    raise RuntimeError("deploy staging and active roots must be distinct")
                overlay.assert_no_symlink_components(
                    normalized_staging_root,
                    label="deploy staging root",
                )
                overlay.assert_no_symlink_components(
                    normalized_backup_root,
                    label="deploy backup root",
                )
                overlay.assert_no_symlink_components(
                    normalized_activation_receipt.parent,
                    label="deploy activation receipt parent",
                )
                deploy_authority = {
                    "stagingRoot": str(normalized_staging_root),
                    "backupRoot": str(normalized_backup_root),
                    "activationReceipt": str(normalized_activation_receipt),
                    "proofBindSourcePath": str(normalized_proof_bind_source),
                    "candidateProofBindSourceSnapshot": str(
                        normalized_candidate_proof_snapshot
                    ),
                    "priorPortalProofAuthoritySnapshot": str(
                        normalized_prior_authority_snapshot or ""
                    ),
                    "priorPortalProofPublicSnapshot": str(
                        normalized_prior_public_snapshot or ""
                    ),
                }
                if runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE:
                    if not isinstance(
                        prior_active_runtime_authority_existed,
                        bool,
                    ):
                        raise RuntimeError(
                            "public-download transaction requires prior active "
                            "runtime authority existence"
                        )
                    normalized_prior_runtime_snapshot: Path | None = None
                    if prior_active_runtime_authority_existed:
                        if (
                            prior_active_runtime_authority_snapshot is None
                            or prior_active_runtime_authority_snapshot_sha256 is None
                            or re.fullmatch(
                                r"[0-9a-f]{64}",
                                prior_active_runtime_authority_snapshot_sha256,
                            )
                            is None
                        ):
                            raise RuntimeError(
                                "public-download transaction prior runtime "
                                "authority snapshot is invalid"
                            )
                        normalized_prior_runtime_snapshot = (
                            overlay.normalized_absolute_path(
                                prior_active_runtime_authority_snapshot
                            )
                        )
                        if _stable_file_sha256(
                            normalized_prior_runtime_snapshot,
                            label="prior active runtime authority snapshot",
                        ) != prior_active_runtime_authority_snapshot_sha256:
                            raise RuntimeError(
                                "prior active runtime authority snapshot changed"
                            )
                    elif (
                        prior_active_runtime_authority_snapshot is not None
                        or prior_active_runtime_authority_snapshot_sha256
                        not in (None, "")
                    ):
                        raise RuntimeError(
                            "absent prior runtime authority cannot claim a snapshot"
                        )
                    deploy_authority.update(
                        {
                            "priorActiveRuntimeAuthorityExisted": (
                                prior_active_runtime_authority_existed
                            ),
                            "priorActiveRuntimeAuthoritySnapshotPath": str(
                                normalized_prior_runtime_snapshot or ""
                            ),
                            "priorActiveRuntimeAuthoritySnapshotSha256": (
                                prior_active_runtime_authority_snapshot_sha256 or ""
                            ),
                        }
                    )
                elif any(
                    value is not None
                    for value in (
                        prior_active_runtime_authority_existed,
                        prior_active_runtime_authority_snapshot,
                        prior_active_runtime_authority_snapshot_sha256,
                    )
                ):
                    raise RuntimeError(
                        "full runtime transaction refuses public-only authority fields"
                    )
            elif any(
                value is not None
                for value in (
                    staging_root,
                    backup_root,
                    activation_receipt,
                    proof_bind_source,
                    candidate_proof_bind_source_snapshot,
                    prior_portal_proof_authority_snapshot,
                    prior_portal_proof_public_snapshot,
                )
            ):
                raise RuntimeError(
                    "deploy overlay authority paths require runtime prior state"
                )
            payload: dict[str, Any] = {
                "contractName": CONTRACT_NAME,
                "operation": "snapshot",
                "status": "pass",
                "phase": "prepared",
                "sourceRoot": str(source_root),
                "activeRoot": str(active_root),
                "activeExisted": existed,
                "priorActiveFingerprint": fingerprint,
                "priorActiveIdentity": identity,
                "runtimePriorState": prior_runtime,
                "deployOverlayAuthority": deploy_authority,
            }
            if runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE:
                payload.update(
                    {
                        "runtimeProfile": runtime_profile,
                        "deploymentOperation": deployment_operation,
                        "sourceHead": source_head,
                    }
                )
            overlay.atomic_write_json(output, payload)
            return payload


def _validated_snapshot(
    path: Path,
    *,
    source_root: Path,
    active_root: Path,
    expected_runtime_profile: str | None = None,
    expected_source_head: str | None = None,
    expected_deployment_operation: str | None = None,
) -> dict[str, Any]:
    payload = _load_object(path, label="overlay transaction snapshot")
    fields = set(payload)
    if fields == FULL_SNAPSHOT_FIELDS:
        runtime_profile = FULL_RUNTIME_PROFILE
        deployment_operation = "deploy"
        source_head = ""
    elif fields == PUBLIC_DOWNLOAD_SNAPSHOT_FIELDS:
        runtime_profile = payload.get("runtimeProfile")
        deployment_operation = payload.get("deploymentOperation")
        source_head = payload.get("sourceHead")
    else:
        raise RuntimeError("overlay transaction snapshot contract is invalid")
    if (
        payload.get("contractName") != CONTRACT_NAME
        or payload.get("operation") != "snapshot"
        or payload.get("status") != "pass"
        or runtime_profile not in {
            FULL_RUNTIME_PROFILE,
            PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE,
        }
        or not isinstance(deployment_operation, str)
        or DEPLOYMENT_OPERATION_PATTERN.fullmatch(deployment_operation) is None
        or not isinstance(source_head, str)
        or (
            runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE
            and bool(payload.get("runtimePriorState"))
            and SOURCE_HEAD_PATTERN.fullmatch(source_head) is None
        )
        or (
            source_head
            and SOURCE_HEAD_PATTERN.fullmatch(source_head) is None
        )
        or not _same_path(payload.get("sourceRoot"), source_root)
        or not _same_path(payload.get("activeRoot"), active_root)
        or not isinstance(payload.get("activeExisted"), bool)
        or not isinstance(payload.get("priorActiveFingerprint"), dict)
        or not isinstance(payload.get("priorActiveIdentity"), dict)
        or payload.get("phase") not in TRANSACTION_PHASES
        or not isinstance(payload.get("runtimePriorState"), dict)
        or not isinstance(payload.get("deployOverlayAuthority", {}), dict)
    ):
        raise RuntimeError("overlay transaction snapshot contract is invalid")
    if (
        expected_runtime_profile is not None
        and runtime_profile != expected_runtime_profile
    ):
        raise RuntimeError("overlay transaction runtime profile conflicts with caller")
    if expected_source_head is not None and source_head != expected_source_head:
        raise RuntimeError("overlay transaction source HEAD conflicts with caller")
    if (
        expected_deployment_operation is not None
        and deployment_operation != expected_deployment_operation
    ):
        raise RuntimeError(
            "overlay transaction deployment operation conflicts with caller"
        )
    if payload["activeExisted"]:
        fingerprint = payload["priorActiveFingerprint"]
        identity = payload["priorActiveIdentity"]
        if (
            fingerprint.get("algorithm") != overlay.SOURCE_FINGERPRINT_ALGORITHM
            or not isinstance(fingerprint.get("aggregateSha256"), str)
            or len(fingerprint["aggregateSha256"]) != 64
            or not isinstance(fingerprint.get("fileCount"), int)
            or not identity
        ):
            raise RuntimeError("overlay transaction snapshot identity is invalid")
    elif payload["priorActiveFingerprint"] or payload["priorActiveIdentity"]:
        raise RuntimeError("absent prior overlay must not claim an identity")
    return payload


def validated_deploy_snapshot(
    path: Path,
    *,
    source_root: Path,
    active_root: Path,
    expected_runtime_profile: str | None = None,
    expected_source_head: str | None = None,
    expected_deployment_operation: str | None = None,
) -> dict[str, Any]:
    payload = _validated_snapshot(
        path,
        source_root=source_root.resolve(),
        active_root=overlay.normalized_absolute_path(active_root),
        expected_runtime_profile=expected_runtime_profile,
        expected_source_head=expected_source_head,
        expected_deployment_operation=expected_deployment_operation,
    )
    payload["runtimePriorState"] = validate_runtime_prior_state(
        payload["runtimePriorState"]
    )
    authority = payload.get("deployOverlayAuthority")
    runtime_profile = payload.get("runtimeProfile", FULL_RUNTIME_PROFILE)
    authority_fields = (
        PUBLIC_DOWNLOAD_DEPLOY_OVERLAY_AUTHORITY_FIELDS
        if runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE
        else DEPLOY_OVERLAY_AUTHORITY_FIELDS
    )
    if not isinstance(authority, dict) or set(authority) != authority_fields:
        raise RuntimeError("deploy overlay authority contract is invalid")
    normalized_authority: dict[str, Any] = {}
    optional_prior_snapshot_fields = {
        "priorPortalProofAuthoritySnapshot",
        "priorPortalProofPublicSnapshot",
    }
    for field in DEPLOY_OVERLAY_AUTHORITY_FIELDS:
        value = authority[field]
        if field in optional_prior_snapshot_fields and value == "":
            normalized_authority[field] = ""
            continue
        if not isinstance(value, str) or not value or not Path(value).is_absolute():
            raise RuntimeError(f"deploy overlay authority {field} is invalid")
        try:
            normalized = overlay.normalized_absolute_path(Path(value))
        except (OSError, RuntimeError, ValueError) as exc:
            raise RuntimeError(f"deploy overlay authority {field} is invalid") from exc
        if str(normalized) != value:
            raise RuntimeError(f"deploy overlay authority {field} is not canonical")
        normalized_authority[field] = value
    if runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE:
        prior_authority_existed = authority["priorActiveRuntimeAuthorityExisted"]
        prior_authority_snapshot = authority[
            "priorActiveRuntimeAuthoritySnapshotPath"
        ]
        prior_authority_sha256 = authority[
            "priorActiveRuntimeAuthoritySnapshotSha256"
        ]
        if not isinstance(prior_authority_existed, bool):
            raise RuntimeError(
                "public-download prior runtime authority existence is invalid"
            )
        if prior_authority_existed:
            if (
                not isinstance(prior_authority_snapshot, str)
                or not prior_authority_snapshot
                or not Path(prior_authority_snapshot).is_absolute()
                or not isinstance(prior_authority_sha256, str)
                or LOWERCASE_SHA256_PATTERN.fullmatch(prior_authority_sha256)
                is None
            ):
                raise RuntimeError(
                    "public-download prior runtime authority snapshot is invalid"
                )
            normalized_snapshot = overlay.normalized_absolute_path(
                Path(prior_authority_snapshot)
            )
            if str(normalized_snapshot) != prior_authority_snapshot:
                raise RuntimeError(
                    "public-download prior runtime authority snapshot is not canonical"
                )
            if _stable_file_sha256(
                normalized_snapshot,
                label="prior active runtime authority snapshot",
            ) != prior_authority_sha256:
                raise RuntimeError(
                    "prior active runtime authority snapshot changed after snapshot"
                )
        elif prior_authority_snapshot != "" or prior_authority_sha256 != "":
            raise RuntimeError(
                "absent prior runtime authority claims snapshot authority"
            )
        normalized_authority.update(
            {
                "priorActiveRuntimeAuthorityExisted": prior_authority_existed,
                "priorActiveRuntimeAuthoritySnapshotPath": prior_authority_snapshot,
                "priorActiveRuntimeAuthoritySnapshotSha256": prior_authority_sha256,
            }
        )
    if normalized_authority["stagingRoot"] == str(
        overlay.normalized_absolute_path(active_root)
    ):
        raise RuntimeError("deploy staging and active roots must be distinct")
    prior = payload["runtimePriorState"]
    expected_candidate_digest = prior["expectedRuntimeProofBindSourceSha256"]
    if _stable_file_sha256(
        Path(normalized_authority["candidateProofBindSourceSnapshot"]),
        label="candidate runtime proof snapshot",
    ) != expected_candidate_digest:
        raise RuntimeError("candidate runtime proof authority changed after snapshot")
    if prior["priorPortalWasRunning"]:
        for field, digest_field in (
            (
                "priorPortalProofAuthoritySnapshot",
                "priorPortalProofAuthorityMountSha256",
            ),
            (
                "priorPortalProofPublicSnapshot",
                "priorPortalProofPublicMountSha256",
            ),
        ):
            if not normalized_authority[field] or _stable_file_sha256(
                Path(normalized_authority[field]),
                label="prior portal proof snapshot",
            ) != prior[digest_field]:
                raise RuntimeError("prior portal proof authority changed after snapshot")
    elif any(normalized_authority[field] for field in optional_prior_snapshot_fields):
        raise RuntimeError("stopped or absent prior portal claims proof snapshots")
    payload["deployOverlayAuthority"] = normalized_authority
    return payload


def prior_overlay_matches_snapshot(
    payload: dict[str, Any],
    *,
    active_root: Path,
) -> bool:
    activation_journal = overlay.activation_transaction_journal_path(
        overlay.normalized_absolute_path(active_root)
    )
    if activation_journal.exists() or activation_journal.is_symlink():
        return False
    return _state_matches(
        expected_existed=bool(payload["activeExisted"]),
        expected_fingerprint=payload["priorActiveFingerprint"],
        expected_identity=payload["priorActiveIdentity"],
        active_root=overlay.normalized_absolute_path(active_root),
    )


def mark_phase(
    *,
    source_root: Path,
    active_root: Path,
    journal_path: Path,
    phase: str,
    shared_mutation_lock_token: str,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    active_root = overlay.normalized_absolute_path(active_root)
    journal_path = overlay.normalized_absolute_path(journal_path)
    if phase not in TRANSACTION_PHASES:
        raise RuntimeError("public-edge overlay transaction phase is invalid")
    with overlay.public_edge_mutation_lock(
        activate=True,
        inherited_token=shared_mutation_lock_token,
    ):
        with overlay.overlay_publish_lock(source_root, active_root):
            payload = _validated_snapshot(
                journal_path,
                source_root=source_root,
                active_root=active_root,
            )
            current_phase = str(payload.get("phase") or "")
            current_index = TRANSACTION_PHASES.index(current_phase)
            requested_index = TRANSACTION_PHASES.index(phase)
            if requested_index < current_index:
                raise RuntimeError("public-edge overlay transaction phase cannot move backward")
            if requested_index > current_index + 1:
                raise RuntimeError("public-edge overlay transaction phase cannot skip forward")
            payload["phase"] = phase
            overlay.atomic_write_json(journal_path, payload)
            return payload


def _portal_identity_matches_candidate(
    payload: dict[str, Any],
    *,
    candidate_portal_container_id: str,
    candidate_portal_container_name: str,
    candidate_portal_image_id: str,
) -> bool:
    portal = payload.get("portal")
    return bool(
        isinstance(portal, dict)
        and portal.get("containerId") == candidate_portal_container_id
        and portal.get("containerName") == candidate_portal_container_name
        and portal.get("imageId") == candidate_portal_image_id
    )


def _validate_candidate_active_runtime_authority(
    payload: dict[str, Any],
    *,
    candidate_portal_container_id: str,
    candidate_portal_container_name: str,
    candidate_portal_image_id: str,
    proof_mount_sha256: str,
    readiness_path: Path | None,
    readiness_sha256: str | None,
    runtime_profile: str,
    source_head: str = "",
    deployment_operation: str = "",
    public_projection_snapshot_id: str = "",
    public_projection_snapshot_sha256: str = "",
    public_projection_manifest_sha256: str = "",
) -> None:
    portal = payload.get("portal")
    if runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE:
        authority_fields = PUBLIC_DOWNLOAD_ONLY_ACTIVE_RUNTIME_AUTHORITY_FIELDS
        readiness_binding_valid = (
            payload.get("runtimeProfile")
            == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE
            and payload.get("sourceHead") == source_head
            and payload.get("deploymentOperation") == deployment_operation
            and payload.get("publicProjectionSnapshotId")
            == public_projection_snapshot_id
            and payload.get("publicProjectionSnapshotSha256")
            == public_projection_snapshot_sha256
            and payload.get("publicProjectionManifestSha256")
            == public_projection_manifest_sha256
        )
    else:
        authority_fields = ACTIVE_RUNTIME_AUTHORITY_FIELDS
        readiness_binding_valid = (
            readiness_path is not None
            and readiness_sha256 is not None
            and payload.get("installLinkingAuthorityReadinessPath")
            == str(readiness_path)
            and payload.get("installLinkingAuthorityReadinessSha256")
            == readiness_sha256
        )
    if (
        set(payload) != authority_fields
        or payload.get("contractName") != ACTIVE_RUNTIME_AUTHORITY_CONTRACT_NAME
        or payload.get("status") != "pass"
        or not readiness_binding_valid
        or not isinstance(portal, dict)
        or set(portal) != ACTIVE_RUNTIME_PORTAL_FIELDS
        or portal.get("existed") is not True
        or portal.get("wasRunning") is not True
        or portal.get("containerId") != candidate_portal_container_id
        or portal.get("containerName") != candidate_portal_container_name
        or portal.get("imageId") != candidate_portal_image_id
        or portal.get("proofAuthorityMountSha256") != proof_mount_sha256
        or portal.get("proofPublicMountSha256") != proof_mount_sha256
    ):
        raise RuntimeError(
            "active runtime authority conflicts with the candidate readiness binding"
        )
    _require_utc_timestamp(
        payload.get("generatedAtUtc"),
        label="active runtime authority",
    )


def complete_transaction(
    *,
    source_root: Path,
    active_root: Path,
    journal_path: Path,
    runtime_authority_output: Path,
    candidate_portal_container_id: str,
    candidate_portal_container_name: str,
    candidate_portal_image_id: str,
    install_linking_authority_readiness: Path | None,
    install_linking_authority_readiness_sha256: str | None,
    shared_mutation_lock_token: str,
    runtime_profile: str = FULL_RUNTIME_PROFILE,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    active_root = overlay.normalized_absolute_path(active_root)
    journal_path = overlay.normalized_absolute_path(journal_path)
    normalized_runtime_authority_output = overlay.normalized_absolute_path(
        runtime_authority_output
    )
    if runtime_authority_output != normalized_runtime_authority_output:
        raise RuntimeError(
            "active runtime authority output must be an exact canonical path"
        )
    runtime_authority_output = normalized_runtime_authority_output
    runtime_evidence_root = _validate_owner_only_evidence_root(
        runtime_authority_output.parent,
        label="active runtime evidence root",
    )
    with overlay.public_edge_mutation_lock(
        activate=True,
        inherited_token=shared_mutation_lock_token,
    ):
        with overlay.overlay_publish_lock(source_root, active_root):
            payload = validated_deploy_snapshot(
                journal_path,
                source_root=source_root,
                active_root=active_root,
                expected_runtime_profile=runtime_profile,
            )
            if payload.get("phase") != "tunnel_started":
                raise RuntimeError(
                    "public-edge overlay transaction cannot complete before tunnel start"
                )
            overlay.assert_no_incomplete_activation_transaction(active_root)
            prior = payload["runtimePriorState"]
            if (
                candidate_portal_container_name
                != prior["candidatePortalContainerName"]
                or CONTAINER_ID_PATTERN.fullmatch(candidate_portal_container_id)
                is None
                or IMAGE_ID_PATTERN.fullmatch(candidate_portal_image_id) is None
            ):
                raise RuntimeError(
                    "candidate portal authority conflicts with deployment journal"
                )
            if runtime_profile == FULL_RUNTIME_PROFILE:
                if (
                    install_linking_authority_readiness is None
                    or install_linking_authority_readiness_sha256 is None
                ):
                    raise RuntimeError(
                        "full runtime completion requires InstallLinking "
                        "authority readiness"
                    )
                readiness_evidence_root = _validate_owner_only_evidence_root(
                    install_linking_authority_readiness.parent,
                    label="private cutover evidence root",
                )
                readiness_path, readiness_sha256, _readiness = (
                    validate_install_linking_authority_readiness(
                        install_linking_authority_readiness,
                        expected_sha256=(
                            install_linking_authority_readiness_sha256
                        ),
                        evidence_root=readiness_evidence_root,
                    )
                )
                if readiness_path in {journal_path, runtime_authority_output}:
                    raise RuntimeError(
                        "InstallLinking authority readiness path conflicts with "
                        "transaction authority paths"
                    )
            elif runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE:
                if (
                    install_linking_authority_readiness is not None
                    or install_linking_authority_readiness_sha256 is not None
                ):
                    raise RuntimeError(
                        "public-download-only completion refuses an "
                        "InstallLinking authority readiness binding"
                    )
                readiness_path = None
                readiness_sha256 = None
            else:
                raise RuntimeError("active runtime profile is unsupported")
            proof_mount_sha256 = prior[
                "expectedRuntimeProofBindSourceSha256"
            ]
            source_head = str(payload.get("sourceHead") or "")
            deployment_operation = str(
                payload.get("deploymentOperation") or "deploy"
            )
            public_projection_snapshot_id = str(
                prior["publicProjectionSnapshotId"]
            )
            public_projection_snapshot_sha256 = str(
                prior["publicProjectionSnapshotSha256"]
            )
            public_projection_manifest_sha256 = str(
                prior["publicProjectionManifestSha256"]
            )
            existing_authority: dict[str, Any] | None = None
            if (
                runtime_authority_output.exists()
                or runtime_authority_output.is_symlink()
            ):
                existing_authority, _existing_sha256 = (
                    _read_owner_only_canonical_json(
                        runtime_authority_output,
                        label="active runtime authority",
                        evidence_root=runtime_evidence_root,
                        maximum_bytes=MAX_INSTALL_LINKING_AUTHORITY_READINESS_BYTES,
                    )
                )
            if existing_authority is not None and _portal_identity_matches_candidate(
                existing_authority,
                candidate_portal_container_id=candidate_portal_container_id,
                candidate_portal_container_name=candidate_portal_container_name,
                candidate_portal_image_id=candidate_portal_image_id,
            ):
                _validate_candidate_active_runtime_authority(
                    existing_authority,
                    candidate_portal_container_id=candidate_portal_container_id,
                    candidate_portal_container_name=candidate_portal_container_name,
                    candidate_portal_image_id=candidate_portal_image_id,
                    proof_mount_sha256=proof_mount_sha256,
                    readiness_path=readiness_path,
                    readiness_sha256=readiness_sha256,
                    runtime_profile=runtime_profile,
                    source_head=source_head,
                    deployment_operation=deployment_operation,
                    public_projection_snapshot_id=public_projection_snapshot_id,
                    public_projection_snapshot_sha256=(
                        public_projection_snapshot_sha256
                    ),
                    public_projection_manifest_sha256=(
                        public_projection_manifest_sha256
                    ),
                )
            else:
                active_authority = active_runtime_authority_payload(
                    portal_existed=True,
                    portal_container_id=candidate_portal_container_id,
                    portal_container_name=candidate_portal_container_name,
                    portal_image_id=candidate_portal_image_id,
                    portal_was_running=True,
                    proof_authority_mount_sha256=proof_mount_sha256,
                    proof_public_mount_sha256=proof_mount_sha256,
                )
                if runtime_profile == FULL_RUNTIME_PROFILE:
                    active_authority.update(
                        {
                            "installLinkingAuthorityReadinessPath": str(
                                readiness_path
                            ),
                            "installLinkingAuthorityReadinessSha256": readiness_sha256,
                        }
                    )
                else:
                    active_authority.update(
                        {
                            "deploymentOperation": deployment_operation,
                            "publicProjectionManifestSha256": (
                                public_projection_manifest_sha256
                            ),
                            "publicProjectionSnapshotId": (
                                public_projection_snapshot_id
                            ),
                            "publicProjectionSnapshotSha256": (
                                public_projection_snapshot_sha256
                            ),
                            "runtimeProfile": PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE,
                            "sourceHead": source_head,
                        }
                    )
                overlay.atomic_write_json(
                    runtime_authority_output,
                    active_authority,
                )
            published_authority, _published_sha256 = (
                _read_owner_only_canonical_json(
                    runtime_authority_output,
                    label="active runtime authority",
                    evidence_root=runtime_evidence_root,
                    maximum_bytes=MAX_INSTALL_LINKING_AUTHORITY_READINESS_BYTES,
                )
            )
            _validate_candidate_active_runtime_authority(
                published_authority,
                candidate_portal_container_id=candidate_portal_container_id,
                candidate_portal_container_name=candidate_portal_container_name,
                candidate_portal_image_id=candidate_portal_image_id,
                proof_mount_sha256=proof_mount_sha256,
                readiness_path=readiness_path,
                readiness_sha256=readiness_sha256,
                runtime_profile=runtime_profile,
                source_head=source_head,
                deployment_operation=deployment_operation,
                public_projection_snapshot_id=public_projection_snapshot_id,
                public_projection_snapshot_sha256=(
                    public_projection_snapshot_sha256
                ),
                public_projection_manifest_sha256=(
                    public_projection_manifest_sha256
                ),
            )
            journal_path.unlink()
            overlay.fsync_directory(journal_path.parent)
    result = {
        "contractName": CONTRACT_NAME,
        "operation": "complete",
        "status": "pass",
        "journalRetired": True,
        "activeRuntimeAuthority": str(runtime_authority_output),
    }
    if runtime_profile == PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE:
        result["runtimeProfile"] = PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE
    return result


def _activation_receipt_backup_hint(
    activation_receipt: Path,
    *,
    active_root: Path,
    backup_root: Path,
) -> Path | None:
    try:
        payload = _load_object(activation_receipt, label="overlay activation receipt")
    except (FileNotFoundError, OSError, RuntimeError):
        return None
    if (
        payload.get("contractName") != overlay.CONTRACT_NAME
        or payload.get("activateRequested") is not True
        or payload.get("activationAtomicCutover") is not True
        or not _same_path(payload.get("activeRoot"), active_root)
        or not _same_path(payload.get("backupRoot"), backup_root)
        or (payload.get("sharedMutationLock") or {}).get("status") != "held"
        or (payload.get("sharedMutationLock") or {}).get("inherited") is not True
    ):
        return None
    backup_value = str(payload.get("backupPath") or "").strip()
    if not backup_value:
        return None
    backup_path = overlay.normalized_absolute_path(Path(backup_value))
    try:
        relative = backup_path.relative_to(backup_root)
    except ValueError:
        return None
    if len(relative.parts) != 2 or relative.parts[-1] != "app":
        return None
    return backup_path


def _validated_backup_path(
    activation_receipt: Path,
    *,
    active_root: Path,
    backup_root: Path,
    expected_fingerprint: object,
    expected_identity: object,
) -> Path:
    # The durable prior-state journal, not a later success receipt, is rollback
    # authority. A crash after the atomic exchange can precede every publisher
    # receipt write, so locate the unique preserved inode under the fixed backup
    # root and treat a receipt path only as a non-authoritative hint.
    overlay.assert_no_symlink_components(backup_root, label="backup root")
    try:
        backup_root_stat = backup_root.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("preserved overlay backup root is missing") from exc
    if not stat.S_ISDIR(backup_root_stat.st_mode) or stat.S_ISLNK(
        backup_root_stat.st_mode
    ):
        raise RuntimeError("preserved overlay backup root is unsafe")

    hint = _activation_receipt_backup_hint(
        activation_receipt,
        active_root=active_root,
        backup_root=backup_root,
    )
    candidates: list[Path] = []
    for transaction_root in backup_root.iterdir():
        transaction_stat = transaction_root.lstat()
        if not stat.S_ISDIR(transaction_stat.st_mode) or stat.S_ISLNK(
            transaction_stat.st_mode
        ):
            raise RuntimeError("preserved overlay backup root contains an unsafe entry")
        candidate = transaction_root / "app"
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        overlay.assert_regular_overlay_tree(
            candidate,
            label="preserved prior active root",
        )
        candidate_fingerprint = overlay.overlay_tree_fingerprint(
            candidate,
            label="preserved prior active root",
        )
        candidate_identity = overlay.directory_identity(
            candidate,
            label="preserved prior active root",
        )
        if _fingerprint_matches(
            expected_fingerprint,
            candidate_fingerprint,
        ) and _identity_matches(expected_identity, candidate_identity):
            candidates.append(candidate)

    if len(candidates) != 1:
        raise RuntimeError(
            "could not resolve one exact preserved prior overlay from the durable snapshot"
        )
    selected = candidates[0]
    if hint is not None and hint != selected:
        raise RuntimeError("overlay activation receipt backup hint conflicts with durable state")
    return selected


def _path_disposition(
    path: Path,
    *,
    prior_fingerprint: object,
    prior_identity: object,
    candidate_fingerprint: object,
    candidate_identity: object,
) -> str:
    try:
        path.lstat()
    except FileNotFoundError:
        return "missing"
    overlay.assert_regular_overlay_tree(path, label="activation recovery tree")
    fingerprint = overlay.overlay_tree_fingerprint(
        path,
        label="activation recovery tree",
    )
    identity = overlay.directory_identity(path, label="activation recovery tree")
    if _fingerprint_matches(prior_fingerprint, fingerprint) and _identity_matches(
        prior_identity,
        identity,
    ):
        return "prior"
    if _fingerprint_matches(candidate_fingerprint, fingerprint) and _identity_matches(
        candidate_identity,
        identity,
    ):
        return "candidate"
    return "unknown"


def _remove_recovery_candidate(path: Path) -> None:
    shutil.rmtree(path)
    overlay.fsync_directory(path.parent)
    try:
        path.parent.rmdir()
    except OSError:
        return
    overlay.fsync_directory(path.parent.parent)


def _recover_interrupted_activation_to_prior(
    *,
    snapshot: dict[str, Any],
    active_root: Path,
    staging_root: Path,
    backup_root: Path,
) -> str:
    overlay.assert_no_symlink_components(staging_root, label="deploy staging root")
    overlay.assert_no_symlink_components(backup_root, label="deploy backup root")
    journal_path = overlay.activation_transaction_journal_path(active_root)
    if not journal_path.exists() and not journal_path.is_symlink():
        return "not_required"
    activation = _load_object(
        journal_path,
        label="overlay activation transaction journal",
    )
    expected_existed = bool(snapshot["activeExisted"])
    prior_fingerprint = snapshot["priorActiveFingerprint"]
    prior_identity = snapshot["priorActiveIdentity"]
    candidate_fingerprint = activation.get("candidateFingerprint")
    candidate_identity = activation.get("candidateIdentity")
    if (
        activation.get("contractName")
        != overlay.ACTIVATION_TRANSACTION_CONTRACT_NAME
        or activation.get("status") != "prepared"
        or activation.get("mode") != "copy"
        or activation.get("preserveOldTree") is not True
        or activation.get("activeExisted") is not expected_existed
        or not _same_path(activation.get("activeRoot"), active_root)
        or not _same_path(activation.get("stagingRoot"), staging_root)
        or not _same_path(activation.get("candidateRoot"), staging_root)
        or not isinstance(candidate_fingerprint, dict)
        or not isinstance(candidate_identity, dict)
        or activation.get("priorActiveFingerprint") != prior_fingerprint
        or activation.get("priorActiveIdentity") != prior_identity
    ):
        raise RuntimeError(
            "overlay activation journal conflicts with durable prior-state authority"
        )

    old_destination_value = str(activation.get("oldTreeDestination") or "")
    old_destination: Path | None = None
    if expected_existed:
        if not old_destination_value:
            raise RuntimeError("overlay activation journal omitted its prior-tree destination")
        old_destination = overlay.normalized_absolute_path(
            Path(old_destination_value)
        )
        try:
            relative = old_destination.relative_to(backup_root)
        except ValueError as exc:
            raise RuntimeError(
                "overlay activation prior-tree destination escaped its backup root"
            ) from exc
        if len(relative.parts) != 2 or relative.parts[-1] != "app":
            raise RuntimeError(
                "overlay activation prior-tree destination is not canonical"
            )
        overlay.assert_no_symlink_components(
            old_destination,
            label="overlay activation prior-tree destination",
        )
    elif old_destination_value:
        raise RuntimeError(
            "overlay activation journal claims a prior-tree destination for prior absence"
        )

    locations = [active_root, staging_root]
    if old_destination is not None:
        locations.append(old_destination)

    def disposition(path: Path) -> str:
        return _path_disposition(
            path,
            prior_fingerprint=prior_fingerprint,
            prior_identity=prior_identity,
            candidate_fingerprint=candidate_fingerprint,
            candidate_identity=candidate_identity,
        )

    states = {path: disposition(path) for path in locations}
    if "unknown" in states.values():
        raise RuntimeError(
            "overlay activation recovery found a tree outside journal authority"
        )

    if expected_existed:
        prior_locations = [path for path, state in states.items() if state == "prior"]
        if len(prior_locations) != 1:
            raise RuntimeError(
                "overlay activation recovery could not resolve one exact prior tree"
            )
        prior_location = prior_locations[0]
        if prior_location != active_root:
            if states[active_root] != "candidate":
                raise RuntimeError(
                    "overlay activation recovery cannot exchange an unauthorised active tree"
                )
            overlay.atomic_exchange_overlay_roots(prior_location, active_root)
        if not _state_matches(
            expected_existed=True,
            expected_fingerprint=prior_fingerprint,
            expected_identity=prior_identity,
            active_root=active_root,
        ):
            raise RuntimeError(
                "overlay activation recovery did not restore the exact prior tree"
            )
    else:
        active_state = states[active_root]
        if active_state == "candidate":
            if states[staging_root] != "missing":
                raise RuntimeError(
                    "overlay activation recovery staging root is unexpectedly occupied"
                )
            overlay.atomic_move_overlay_root(active_root, staging_root)
        elif active_state != "missing":
            raise RuntimeError(
                "overlay activation recovery cannot restore prior active-root absence"
            )
        if active_root.exists() or active_root.is_symlink():
            raise RuntimeError(
                "overlay activation recovery did not restore prior active-root absence"
            )

    for path in locations:
        if path == active_root:
            continue
        current = disposition(path)
        if current == "candidate":
            _remove_recovery_candidate(path)
        elif current not in {"missing"}:
            raise RuntimeError(
                "overlay activation recovery retained an unexpected non-active tree"
            )

    journal_path.unlink()
    overlay.fsync_directory(journal_path.parent)
    overlay.assert_no_incomplete_activation_transaction(active_root)
    return "exact_prior_activation_state_restored"


def restore(
    *,
    source_root: Path,
    active_root: Path,
    backup_root: Path,
    snapshot_path: Path,
    activation_receipt: Path,
    output: Path,
    shared_mutation_lock_token: str,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    active_root = overlay.normalized_absolute_path(active_root)
    backup_root = overlay.normalized_absolute_path(backup_root)
    output = overlay.normalized_absolute_path(output)
    prior = _validated_snapshot(
        snapshot_path,
        source_root=source_root,
        active_root=active_root,
    )
    deploy_authority: dict[str, str] | None = None
    if prior["runtimePriorState"]:
        prior = validated_deploy_snapshot(
            snapshot_path,
            source_root=source_root,
            active_root=active_root,
        )
        deploy_authority = prior["deployOverlayAuthority"]
        authoritative_backup_root = overlay.normalized_absolute_path(
            Path(deploy_authority["backupRoot"])
        )
        if backup_root != authoritative_backup_root:
            raise RuntimeError("overlay recovery backup root conflicts with its journal")
        backup_root = authoritative_backup_root
        activation_receipt = overlay.normalized_absolute_path(
            Path(deploy_authority["activationReceipt"])
        )
    expected_existed = bool(prior["activeExisted"])
    expected_fingerprint = prior["priorActiveFingerprint"]
    expected_identity = prior["priorActiveIdentity"]
    action = "already_restored"
    retired_cleanup_status = "not_applicable"

    with overlay.public_edge_mutation_lock(
        activate=True,
        inherited_token=shared_mutation_lock_token,
    ):
        with overlay.overlay_publish_lock(source_root, active_root):
            activation_recovery = "not_applicable"
            if deploy_authority is not None:
                activation_recovery = _recover_interrupted_activation_to_prior(
                    snapshot=prior,
                    active_root=active_root,
                    staging_root=overlay.normalized_absolute_path(
                        Path(deploy_authority["stagingRoot"])
                    ),
                    backup_root=backup_root,
                )
            if not _state_matches(
                expected_existed=expected_existed,
                expected_fingerprint=expected_fingerprint,
                expected_identity=expected_identity,
                active_root=active_root,
            ):
                if expected_existed:
                    backup_path = _validated_backup_path(
                        activation_receipt,
                        active_root=active_root,
                        backup_root=backup_root,
                        expected_fingerprint=expected_fingerprint,
                        expected_identity=expected_identity,
                    )
                    activation = overlay.activate_overlay_tree(
                        backup_path,
                        active_root,
                        mode="copy",
                        backup_root=None,
                    )
                    if activation.get("transactionCleanupStatus") != "complete":
                        raise RuntimeError(
                            "overlay rollback committed with an incomplete transaction journal"
                        )
                    action = "exact_prior_tree_restored"
                else:
                    existed, _fingerprint, _identity = _current_state(active_root)
                    if existed:
                        retired_path = overlay.retired_overlay_path(active_root)
                        overlay.require_same_filesystem(active_root, retired_path.parent)
                        overlay.atomic_move_overlay_root(active_root, retired_path)
                        overlay.fsync_directory(active_root.parent)
                        action = "prior_absence_restored"
                        try:
                            shutil.rmtree(retired_path)
                            retired_path.parent.rmdir()
                            overlay.fsync_directory(active_root.parent)
                            retired_cleanup_status = "removed"
                        except OSError:
                            retired_cleanup_status = "retained_for_manual_cleanup"

            overlay.assert_no_incomplete_activation_transaction(active_root)
            if not _state_matches(
                expected_existed=expected_existed,
                expected_fingerprint=expected_fingerprint,
                expected_identity=expected_identity,
                active_root=active_root,
            ):
                raise RuntimeError("overlay rollback did not restore the exact prior state")

            payload = {
                "contractName": CONTRACT_NAME,
                "operation": "restore",
                "status": "pass",
                "sourceRoot": str(source_root),
                "activeRoot": str(active_root),
                "priorActiveExisted": expected_existed,
                "action": action,
                "retiredCleanupStatus": retired_cleanup_status,
                "activationRecovery": activation_recovery,
                "exactPriorStateRestored": True,
            }
            overlay.atomic_write_json(output, payload)
            return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Snapshot or restore the exact public-edge overlay transaction boundary."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    phase_parser = subparsers.add_parser("mark-phase")
    restore_parser = subparsers.add_parser("restore")
    complete_parser = subparsers.add_parser("complete")
    for command in (snapshot_parser, phase_parser, restore_parser, complete_parser):
        command.add_argument("--source-root", type=Path, required=True)
        command.add_argument("--active-root", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--shared-mutation-lock-token", required=True)
    restore_parser.add_argument("--backup-root", type=Path, required=True)
    restore_parser.add_argument("--snapshot", type=Path, required=True)
    restore_parser.add_argument("--activation-receipt", type=Path, required=True)
    snapshot_parser.add_argument("--prior-image-tag-id", default="")
    snapshot_parser.add_argument(
        "--expected-runtime-proof-bind-source-sha256",
        required=True,
    )
    snapshot_parser.add_argument(
        "--public-projection-snapshot-id",
        required=True,
    )
    snapshot_parser.add_argument(
        "--public-projection-snapshot-sha256",
        required=True,
    )
    snapshot_parser.add_argument(
        "--public-projection-manifest-sha256",
        required=True,
    )
    snapshot_parser.add_argument("--candidate-portal-container-name", required=True)
    snapshot_parser.add_argument("--prior-tool-image-tag-id", default="")
    snapshot_parser.add_argument("--prior-portal-container-id", default="")
    snapshot_parser.add_argument("--prior-portal-container-name", default="")
    snapshot_parser.add_argument("--prior-portal-image-id", default="")
    snapshot_parser.add_argument(
        "--prior-portal-proof-authority-mount-sha256",
        default="",
    )
    snapshot_parser.add_argument(
        "--prior-portal-proof-public-mount-sha256",
        default="",
    )
    snapshot_parser.add_argument("--prior-portal-existed", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-portal-was-running", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-tunnel-container-id", default="")
    snapshot_parser.add_argument("--prior-tunnel-image-id", default="")
    snapshot_parser.add_argument("--prior-tunnel-existed", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-tunnel-was-running", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-tunnel-replica-container-id", default="")
    snapshot_parser.add_argument("--prior-tunnel-replica-image-id", default="")
    snapshot_parser.add_argument(
        "--prior-tunnel-replica-existed",
        choices=("0", "1"),
        required=True,
    )
    snapshot_parser.add_argument(
        "--prior-tunnel-replica-was-running",
        choices=("0", "1"),
        required=True,
    )
    snapshot_parser.add_argument("--staging-root", type=Path, required=True)
    snapshot_parser.add_argument("--backup-root", type=Path, required=True)
    snapshot_parser.add_argument("--activation-receipt", type=Path, required=True)
    snapshot_parser.add_argument("--proof-bind-source", type=Path, required=True)
    snapshot_parser.add_argument(
        "--candidate-proof-bind-source-snapshot",
        type=Path,
        required=True,
    )
    snapshot_parser.add_argument("--prior-portal-proof-authority-snapshot", default="")
    snapshot_parser.add_argument("--prior-portal-proof-public-snapshot", default="")
    snapshot_parser.add_argument(
        "--runtime-profile",
        choices=(FULL_RUNTIME_PROFILE, PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE),
        default=FULL_RUNTIME_PROFILE,
    )
    snapshot_parser.add_argument("--deployment-operation", default="deploy")
    snapshot_parser.add_argument("--source-head", default="")
    snapshot_parser.add_argument(
        "--prior-active-runtime-authority-existed",
        choices=("0", "1"),
    )
    snapshot_parser.add_argument(
        "--prior-active-runtime-authority-snapshot",
        default="",
    )
    snapshot_parser.add_argument(
        "--prior-active-runtime-authority-snapshot-sha256",
        default="",
    )
    complete_parser.add_argument(
        "--runtime-authority-output",
        type=Path,
        required=True,
    )
    complete_parser.add_argument("--candidate-portal-container-id", required=True)
    complete_parser.add_argument("--candidate-portal-container-name", required=True)
    complete_parser.add_argument("--candidate-portal-image-id", required=True)
    complete_parser.add_argument(
        "--install-linking-authority-readiness",
        type=Path,
    )
    complete_parser.add_argument(
        "--install-linking-authority-readiness-sha256",
    )
    complete_parser.add_argument(
        "--runtime-profile",
        choices=(FULL_RUNTIME_PROFILE, PUBLIC_DOWNLOAD_ONLY_RUNTIME_PROFILE),
        default=FULL_RUNTIME_PROFILE,
    )
    phase_parser.add_argument("--phase", choices=TRANSACTION_PHASES, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.operation == "snapshot":
            payload = snapshot(
                source_root=args.source_root,
                active_root=args.active_root,
                output=args.output,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
                runtime_prior_state={
                    "candidatePortalContainerName": (
                        args.candidate_portal_container_name
                    ),
                    "expectedRuntimeProofBindSourceSha256": (
                        args.expected_runtime_proof_bind_source_sha256
                    ),
                    "publicProjectionManifestSha256": (
                        args.public_projection_manifest_sha256
                    ),
                    "publicProjectionSnapshotId": (
                        args.public_projection_snapshot_id
                    ),
                    "publicProjectionSnapshotSha256": (
                        args.public_projection_snapshot_sha256
                    ),
                    "priorImageTagId": args.prior_image_tag_id,
                    "priorToolImageTagId": args.prior_tool_image_tag_id,
                    "priorPortalContainerId": args.prior_portal_container_id,
                    "priorPortalContainerName": args.prior_portal_container_name,
                    "priorPortalImageId": args.prior_portal_image_id,
                    "priorPortalProofAuthorityMountSha256": (
                        args.prior_portal_proof_authority_mount_sha256
                    ),
                    "priorPortalProofPublicMountSha256": (
                        args.prior_portal_proof_public_mount_sha256
                    ),
                    "priorPortalExisted": args.prior_portal_existed == "1",
                    "priorPortalWasRunning": args.prior_portal_was_running == "1",
                    "priorTunnelContainerId": args.prior_tunnel_container_id,
                    "priorTunnelImageId": args.prior_tunnel_image_id,
                    "priorTunnelExisted": args.prior_tunnel_existed == "1",
                    "priorTunnelWasRunning": args.prior_tunnel_was_running == "1",
                    "priorTunnelReplicaContainerId": (
                        args.prior_tunnel_replica_container_id
                    ),
                    "priorTunnelReplicaImageId": (
                        args.prior_tunnel_replica_image_id
                    ),
                    "priorTunnelReplicaExisted": (
                        args.prior_tunnel_replica_existed == "1"
                    ),
                    "priorTunnelReplicaWasRunning": (
                        args.prior_tunnel_replica_was_running == "1"
                    ),
                },
                staging_root=args.staging_root,
                backup_root=args.backup_root,
                activation_receipt=args.activation_receipt,
                proof_bind_source=args.proof_bind_source,
                candidate_proof_bind_source_snapshot=(
                    args.candidate_proof_bind_source_snapshot
                ),
                prior_portal_proof_authority_snapshot=(
                    Path(args.prior_portal_proof_authority_snapshot)
                    if args.prior_portal_proof_authority_snapshot
                    else None
                ),
                prior_portal_proof_public_snapshot=(
                    Path(args.prior_portal_proof_public_snapshot)
                    if args.prior_portal_proof_public_snapshot
                    else None
                ),
                runtime_profile=args.runtime_profile,
                deployment_operation=args.deployment_operation,
                source_head=args.source_head,
                prior_active_runtime_authority_existed=(
                    args.prior_active_runtime_authority_existed == "1"
                    if args.prior_active_runtime_authority_existed is not None
                    else None
                ),
                prior_active_runtime_authority_snapshot=(
                    Path(args.prior_active_runtime_authority_snapshot)
                    if args.prior_active_runtime_authority_snapshot
                    else None
                ),
                prior_active_runtime_authority_snapshot_sha256=(
                    args.prior_active_runtime_authority_snapshot_sha256 or None
                ),
            )
        elif args.operation == "mark-phase":
            payload = mark_phase(
                source_root=args.source_root,
                active_root=args.active_root,
                journal_path=args.output,
                phase=args.phase,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
            )
        elif args.operation == "complete":
            payload = complete_transaction(
                source_root=args.source_root,
                active_root=args.active_root,
                journal_path=args.output,
                runtime_authority_output=args.runtime_authority_output,
                candidate_portal_container_id=args.candidate_portal_container_id,
                candidate_portal_container_name=args.candidate_portal_container_name,
                candidate_portal_image_id=args.candidate_portal_image_id,
                install_linking_authority_readiness=(
                    args.install_linking_authority_readiness
                ),
                install_linking_authority_readiness_sha256=(
                    args.install_linking_authority_readiness_sha256
                ),
                runtime_profile=args.runtime_profile,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
            )
        else:
            payload = restore(
                source_root=args.source_root,
                active_root=args.active_root,
                backup_root=args.backup_root,
                snapshot_path=args.snapshot,
                activation_receipt=args.activation_receipt,
                output=args.output,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
            )
    except Exception as exc:
        payload = {
            "contractName": CONTRACT_NAME,
            "operation": args.operation,
            "status": "fail",
            "exactPriorStateRestored": False,
            "warning": str(exc),
        }
        if args.operation not in {"mark-phase", "complete"}:
            try:
                overlay.atomic_write_json(
                    overlay.normalized_absolute_path(args.output),
                    payload,
                )
            except Exception:
                pass
    print(json.dumps(payload, sort_keys=True, allow_nan=False))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
