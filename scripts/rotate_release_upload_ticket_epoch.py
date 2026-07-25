#!/usr/bin/env python3
"""Fail-forward rotation of the public release-upload ticket epoch.

The caller must already own the shared public-edge mutation lease.  Before the
credential boundary moves, this transaction proves the exact pinned portal
under the old epoch.  Once the owner-only Compose environment is atomically
replaced, the old epoch is never restored and every failure is classified as
fail-forward-required.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import hmac
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Protocol
from urllib.parse import urlsplit


CONTRACT_NAME = "chummer.release-upload-ticket-epoch-rotation/v1"
EPOCH_HISTORY_CONTRACT = "chummer.release-upload-ticket-epoch-history/v1"
EPOCH_HISTORY_BOOTSTRAP_AUTHORITY_CONTRACT = (
    "chummer.release-upload-ticket-epoch-history-bootstrap-authority/v1"
)
EPOCH_HISTORY_BOOTSTRAP_MARKER_CONTRACT = (
    "chummer.release-upload-ticket-epoch-history-bootstrap-marker/v1"
)
EPOCH_HISTORY_ABSENT_PIN = "absent"
ZERO_SHA256 = "0" * 64
EPOCH_KEY = "CHUMMER_RELEASE_UPLOAD_TICKET_REVOCATION_EPOCH"
SESSION_ROOT_KEY = "CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"
DIRECT_UPLOAD_KEY = "CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED"
DATA_PROTECTION_ROOT_KEY = "CHUMMER_DATA_PROTECTION_KEYS_PATH"
EXPECTED_SESSION_ROOT = "/release-upload-sessions"
EXPECTED_DATA_PROTECTION_ROOT = "/app/state/data-protection-keys-v2"
EXPECTED_STATE_VOLUME = "chummer6-hub_chummer-run-api-state"
EXPECTED_SESSION_VOLUME = "chummer6-hub_chummer-release-upload-sessions"
PORTAL_SERVICE = "chummer-portal"
CANONICAL_TUNNEL_SERVICES = (
    "chummer-run-cloudflared",
    "chummer-run-cloudflared-replica",
)
LOOPBACK_ROUTES = (
    "/api/ready",
    "/api/ready/publication",
    "/api/ready/install-linking-authority",
)
PUBLIC_GET_PATHS = (
    "/",
    "/downloads/RELEASE_CHANNEL.generated.json",
)
PORTAL_BINARY_PATH = "/app/Chummer.Run.Api.dll"
PROOF_AUTHORITY_PATH = "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json"
PROOF_PUBLIC_PATH = (
    "/app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
)
OLD_TICKET_PROOF_PATH = (
    "/api/internal/releases/upload-ticket-revocation-proof"
)
OLD_TICKET_PROOF_NONCE_HEADER = (
    "X-Chummer-Release-Upload-Revocation-Nonce"
)
OLD_TICKET_PROOF_CONTRACT = (
    "chummer.release-upload-ticket-revocation-proof/v1"
)
OLD_TICKET_DIGEST_AUTHORITY_CONTRACT = (
    "chummer.release-upload-incident-ticket-materialization-authority/v1"
)
LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
SAFE_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SAFE_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SAFE_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
RFC3339_UTC = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z$"
)
CANONICAL_PROJECT_NAME = "chummer6-hub"
CANONICAL_IMAGE_TAG = "chummer-run-api:local"
MAX_ENV_BYTES = 1024 * 1024
MAX_TICKET_BYTES = 16 * 1024
MAX_TICKET_DIGEST_AUTHORITY_BYTES = 8192
MAX_PUBLIC_BODY_BYTES = 4 * 1024 * 1024
MAX_HISTORY_BYTES = 4 * 1024 * 1024
MAX_BOOTSTRAP_AUTHORITY_BYTES = 256 * 1024
MAX_EDGE_WAF_LOCAL_EVIDENCE_BYTES = 4 * 1024 * 1024
ACTIVE_RUNTIME_AUTHORITY_FIELDS = {
    "contractName",
    "generatedAtUtc",
    "portal",
    "status",
}
ENRICHED_ACTIVE_RUNTIME_AUTHORITY_FIELDS = ACTIVE_RUNTIME_AUTHORITY_FIELDS | {
    "installLinkingAuthorityReadinessPath",
    "installLinkingAuthorityReadinessSha256",
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
EPOCH_HISTORY_FIELDS = {
    "contractName",
    "status",
    "updatedAtUtc",
    "generation",
    "headEventSha256",
    "events",
}
EPOCH_HISTORY_EVENT_FIELDS = {
    "sequence",
    "eventType",
    "epochSha256",
    "rotationIntentSha256",
    "previousEventSha256",
    "recordedAtUtc",
    "sourceHead",
    "imageId",
    "eventSha256",
}
EPOCH_HISTORY_BOOTSTRAP_AUTHORITY_FIELDS = {
    "contractName",
    "status",
    "generatedAtUtc",
    "knownLegacyEpochSha256",
}
EPOCH_HISTORY_BOOTSTRAP_MARKER_FIELDS = {
    "contractName",
    "status",
    "generatedAtUtc",
    "bootstrapAuthoritySha256",
    "knownLegacyEpochSha256",
    "initialRotationIntentSha256",
    "epochHistoryPathSha256",
}


def _load_overlay_module():
    module_path = Path(__file__).resolve().with_name(
        "publish_public_edge_portal_overlay.py"
    )
    spec = importlib.util.spec_from_file_location(
        "chummer_release_ticket_epoch_overlay_authority",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("overlay_authority_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


overlay = _load_overlay_module()


class RotationError(RuntimeError):
    def __init__(self, code: str):
        if re.fullmatch(r"[a-z][a-z0-9_]{2,95}", code) is None:
            code = "invalid_failure_code"
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TicketMaterializationAuthority:
    fd: int
    canonical_bytes: bytes = field(repr=False)
    ticket_path_sha256: str
    ticket_sha256: str
    ticket_size_bytes: int
    envelope_sha256: str
    inventory_commitment_sha256: str
    recipient_certificate_sha256: str
    signer_certificate_sha256: str
    openssl_executable_sha256: str
    materialization_openssl_executable_sha256: str
    materialization_transaction_id: str


@dataclass(frozen=True)
class MountEvidence:
    destination: str
    volume_name: str
    read_write: bool


@dataclass(frozen=True)
class PortalEvidence:
    container_id: str
    container_name: str
    image_id: str
    running: bool
    health: str
    restart_policy: str
    epoch_sha256: str
    binary_sha256: str
    proof_authority_sha256: str
    proof_public_sha256: str
    state_volume: MountEvidence
    upload_session_volume: MountEvidence
    upload_session_root: str
    data_protection_root: str
    direct_bundle_upload_enabled: str
    runtime_contract_sha256: str


@dataclass(frozen=True)
class VolumeEvidence:
    name: str
    driver: str
    scope: str
    mountpoint: str
    created_at: str
    options_sha256: str
    labels_sha256: str


@dataclass(frozen=True)
class StorageProbeEvidence:
    path: str
    uid: int
    gid: int
    mode: str
    key_file_count: int
    encrypted_key_file_count: int


@dataclass(frozen=True)
class TunnelEvidence:
    service: str
    container_id: str
    image_id: str
    running: bool
    health: str


class RuntimeAuthority(Protocol):
    def resolve_image_id(self, image_tag: str) -> str: ...

    def portal_container_ids(self) -> tuple[str, ...]: ...

    def independently_enumerated_portal_container_ids(
        self,
    ) -> tuple[str, ...]: ...

    def inspect_portal(self, container_id: str) -> PortalEvidence: ...

    def tunnel_evidence(self) -> tuple[TunnelEvidence, ...]: ...

    def volume_evidence(self, name: str) -> VolumeEvidence: ...

    def storage_probe(
        self,
        container_id: str,
        *,
        path: str,
        require_encrypted_keyring: bool,
    ) -> StorageProbeEvidence: ...

    def verify_loopback(self, container_id: str, route: str) -> str: ...

    def quiesce_portals(self, container_ids: tuple[str, ...]) -> None: ...

    def quiesce_known_portals(
        self,
        container_ids: tuple[str, ...],
    ) -> None: ...

    def assert_portals_stopped(
        self,
        container_ids: tuple[str, ...],
    ) -> None: ...

    def assert_known_portals_stopped(
        self,
        container_ids: tuple[str, ...],
    ) -> None: ...

    def restart_portals(self, container_ids: tuple[str, ...]) -> None: ...

    def quiesce_public_connectors(self) -> None: ...

    def assert_public_connectors_stopped(self) -> None: ...

    def recreate_all_portals(
        self,
        *,
        prior_container_ids: tuple[str, ...],
        container_names: tuple[str, ...],
    ) -> None: ...

    def public_get(self, path: str) -> tuple[int, str]: ...

    def old_ticket_revocation_proof(
        self,
        ticket: str,
        nonce: str,
    ) -> tuple[int, tuple[tuple[str, str], ...], bytes]: ...


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def require_owner_only_directory(path: Path, *, label: str) -> Path:
    normalized = overlay.normalized_absolute_path(path)
    if normalized != path or not path.is_absolute():
        raise RotationError(f"{label}_path_invalid")
    overlay.assert_no_symlink_components(normalized, label=label)
    metadata = normalized.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RotationError(f"{label}_not_owner_only")
    return normalized


def require_trusted_parent_directory(path: Path, *, label: str) -> Path:
    normalized = overlay.normalized_absolute_path(path)
    if normalized != path or not path.is_absolute():
        raise RotationError(f"{label}_path_invalid")
    overlay.assert_no_symlink_components(normalized, label=label)
    metadata = normalized.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise RotationError(f"{label}_directory_not_trusted")
    return normalized


def read_owner_only_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> bytes:
    normalized = overlay.normalized_absolute_path(path)
    if normalized != path or not path.is_absolute():
        raise RotationError(f"{label}_path_invalid")
    overlay.assert_no_symlink_components(normalized, label=label)
    descriptor = os.open(
        normalized,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size > maximum_bytes
        ):
            raise RotationError(f"{label}_not_owner_only")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > maximum_bytes:
                raise RotationError(f"{label}_oversized")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_metadata = normalized.lstat()
    identities = {
        (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
            item.st_mode,
            item.st_nlink,
            item.st_uid,
            item.st_gid,
        )
        for item in (before, after, path_metadata)
    }
    if len(identities) != 1 or len(payload) != before.st_size:
        raise RotationError(f"{label}_changed_during_read")
    return bytes(payload)


def read_trusted_regular_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> bytes:
    normalized = overlay.normalized_absolute_path(path)
    if normalized != path or not path.is_absolute():
        raise RotationError(f"{label}_path_invalid")
    overlay.assert_no_symlink_components(normalized, label=label)
    descriptor = os.open(
        normalized,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) & 0o022
            or before.st_size < 1
            or before.st_size > maximum_bytes
        ):
            raise RotationError(f"{label}_not_trusted")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > maximum_bytes:
                raise RotationError(f"{label}_oversized")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_metadata = normalized.lstat()
    identities = {
        (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
            item.st_mode,
            item.st_nlink,
            item.st_uid,
            item.st_gid,
        )
        for item in (before, after, path_metadata)
    }
    if len(identities) != 1 or len(payload) != before.st_size:
        raise RotationError(f"{label}_changed_during_read")
    return bytes(payload)


def strict_json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RotationError(f"{label}_duplicate_key")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicates,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RotationError(f"{label}_json_invalid") from exc
    if not isinstance(parsed, dict):
        raise RotationError(f"{label}_json_invalid")
    return parsed


def atomic_write_private_json(path: Path, payload: dict[str, Any]) -> str:
    parent = require_owner_only_directory(path.parent, label="receipt_root")
    if path.parent != parent or path.is_symlink():
        raise RotationError("receipt_path_invalid")
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RotationError("receipt_write_stalled")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        fsync_directory(parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise RotationError("receipt_identity_invalid")
    return sha256_bytes(encoded)


def parse_epoch_environment(payload: bytes) -> tuple[str, int]:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise RotationError("environment_not_utf8") from exc
    matches: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines(keepends=True)):
        content = line.rstrip("\r\n")
        if content.startswith(f"{EPOCH_KEY}="):
            matches.append((index, content.split("=", 1)[1]))
    if len(matches) != 1:
        raise RotationError("environment_epoch_must_be_explicit_once")
    index, epoch = matches[0]
    if SAFE_EPOCH.fullmatch(epoch) is None:
        raise RotationError("environment_epoch_invalid")
    return epoch, index


def replace_epoch_environment(
    *,
    path: Path,
    prior_payload: bytes,
    new_epoch: str,
) -> tuple[str, str]:
    if SAFE_EPOCH.fullmatch(new_epoch) is None:
        raise RotationError("new_epoch_invalid")
    require_trusted_parent_directory(
        path.parent,
        label="environment_parent",
    )
    current_payload = read_owner_only_file(
        path,
        label="environment",
        maximum_bytes=MAX_ENV_BYTES,
    )
    if current_payload != prior_payload:
        raise RotationError("environment_changed_before_commit")
    current_epoch, target_index = parse_epoch_environment(current_payload)
    if current_epoch == new_epoch:
        return sha256_bytes(current_payload), sha256_bytes(current_payload)
    lines = current_payload.decode("utf-8", errors="strict").splitlines(keepends=True)
    original = lines[target_index]
    ending = "\n"
    if original.endswith("\r\n"):
        ending = "\r\n"
    elif not original.endswith("\n"):
        ending = ""
    lines[target_index] = f"{EPOCH_KEY}={new_epoch}{ending}"
    replacement = "".join(lines).encode("utf-8")
    before_sha256 = sha256_bytes(current_payload)
    after_sha256 = sha256_bytes(replacement)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.epoch-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(replacement)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RotationError("environment_write_stalled")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    committed = read_owner_only_file(
        path,
        label="environment",
        maximum_bytes=MAX_ENV_BYTES,
    )
    committed_epoch, _ = parse_epoch_environment(committed)
    if committed_epoch != new_epoch or sha256_bytes(committed) != after_sha256:
        raise RotationError("environment_commit_verification_failed")
    return before_sha256, after_sha256


def load_ticket(
    path: Path,
    authority: TicketMaterializationAuthority,
) -> tuple[str, str]:
    if sha256_text(str(path)) != authority.ticket_path_sha256:
        raise RotationError("old_ticket_path_authority_mismatch")
    payload = read_owner_only_file(
        path,
        label="old_ticket",
        maximum_bytes=MAX_TICKET_BYTES,
    )
    actual_sha256 = sha256_bytes(payload)
    if (
        len(payload) != authority.ticket_size_bytes
        or actual_sha256 != authority.ticket_sha256
    ):
        raise RotationError("old_ticket_sha256_mismatch")
    try:
        rendered = payload.decode("ascii", errors="strict")
    except UnicodeError as exc:
        raise RotationError("old_ticket_not_ascii") from exc
    ticket = rendered[:-1] if rendered.endswith("\n") else rendered
    if (
        not ticket
        or len(ticket) > MAX_TICKET_BYTES
        or rendered not in {ticket, ticket + "\n"}
        or any(
            ord(character) < 0x21 or ord(character) > 0x7E
            for character in ticket
        )
    ):
        raise RotationError("old_ticket_invalid")
    return ticket, actual_sha256


def verify_proof_bind_source(request: RotationRequest) -> None:
    payload = read_trusted_regular_file(
        request.proof_bind_source,
        label="proof_bind_source",
        maximum_bytes=4 * 1024 * 1024,
    )
    if sha256_bytes(payload) != request.expected_proof_sha256:
        raise RotationError("proof_bind_source_sha256_mismatch")


def verify_edge_waf_local_evidence_source(
    request: RotationRequest,
) -> str:
    payload = read_trusted_regular_file(
        request.edge_waf_local_evidence_source,
        label="edge_waf_local_evidence_source",
        maximum_bytes=MAX_EDGE_WAF_LOCAL_EVIDENCE_BYTES,
    )
    actual_sha256 = sha256_bytes(payload)
    if actual_sha256 != request.expected_edge_waf_local_evidence_sha256:
        raise RotationError(
            "edge_waf_local_evidence_sha256_mismatch"
        )
    return actual_sha256


def verify_committed_environment(
    request: RotationRequest,
    *,
    expected_sha256: str,
) -> None:
    payload = read_owner_only_file(
        request.env_file,
        label="environment",
        maximum_bytes=MAX_ENV_BYTES,
    )
    epoch, _ = parse_epoch_environment(payload)
    if epoch != request.new_epoch or sha256_bytes(payload) != expected_sha256:
        raise RotationError("committed_environment_drift")


def mount_payload(evidence: PortalEvidence) -> dict[str, Any]:
    return {
        "state": asdict(evidence.state_volume),
        "releaseUploadSessions": asdict(evidence.upload_session_volume),
    }


def portal_payload(evidence: PortalEvidence) -> dict[str, Any]:
    return {
        "containerId": evidence.container_id,
        "containerName": evidence.container_name,
        "imageId": evidence.image_id,
        "running": evidence.running,
        "health": evidence.health,
        "restartPolicy": evidence.restart_policy,
        "epochSha256": evidence.epoch_sha256,
        "binarySha256": evidence.binary_sha256,
        "proofAuthoritySha256": evidence.proof_authority_sha256,
        "proofPublicSha256": evidence.proof_public_sha256,
        "mounts": mount_payload(evidence),
        "releaseUploadSessionRoot": evidence.upload_session_root,
        "dataProtectionRoot": evidence.data_protection_root,
        "directBundleUploadEnabled": evidence.direct_bundle_upload_enabled,
        "runtimeContractSha256": evidence.runtime_contract_sha256,
    }


def tunnel_payload(evidence: TunnelEvidence) -> dict[str, Any]:
    return {
        "service": evidence.service,
        "containerId": evidence.container_id,
        "imageId": evidence.image_id,
        "running": evidence.running,
        "health": evidence.health,
    }


def validate_portal(
    evidence: PortalEvidence,
    *,
    expected_image_id: str,
    expected_epoch_sha256: str,
    expected_proof_sha256: str,
) -> None:
    if (
        CONTAINER_ID.fullmatch(evidence.container_id) is None
        or SAFE_CONTAINER_NAME.fullmatch(evidence.container_name) is None
        or evidence.image_id != expected_image_id
        or not evidence.running
        or evidence.health != "healthy"
        or evidence.restart_policy != "unless-stopped"
        or evidence.epoch_sha256 != expected_epoch_sha256
        or LOWER_SHA256.fullmatch(evidence.binary_sha256) is None
        or evidence.proof_authority_sha256 != expected_proof_sha256
        or evidence.proof_authority_sha256 != evidence.proof_public_sha256
        or evidence.upload_session_root != EXPECTED_SESSION_ROOT
        or evidence.data_protection_root != EXPECTED_DATA_PROTECTION_ROOT
        or evidence.direct_bundle_upload_enabled != "false"
        or LOWER_SHA256.fullmatch(evidence.runtime_contract_sha256) is None
        or evidence.state_volume
        != MountEvidence("/app/state", EXPECTED_STATE_VOLUME, True)
        or evidence.upload_session_volume
        != MountEvidence(
            EXPECTED_SESSION_ROOT,
            EXPECTED_SESSION_VOLUME,
            True,
        )
    ):
        raise RotationError("portal_runtime_contract_invalid")


def inspect_exact_portals(
    runtime: RuntimeAuthority,
    *,
    expected_count: int,
    expected_image_id: str,
    expected_epoch_sha256: str,
    expected_proof_sha256: str,
) -> tuple[PortalEvidence, ...]:
    identities = runtime.portal_container_ids()
    if (
        len(identities) != expected_count
        or len(set(identities)) != expected_count
        or any(CONTAINER_ID.fullmatch(value) is None for value in identities)
    ):
        raise RotationError("portal_replica_count_invalid")
    evidence = tuple(runtime.inspect_portal(identity) for identity in identities)
    for item in evidence:
        validate_portal(
            item,
            expected_image_id=expected_image_id,
            expected_epoch_sha256=expected_epoch_sha256,
            expected_proof_sha256=expected_proof_sha256,
        )
    if len({item.container_name for item in evidence}) != expected_count:
        raise RotationError("portal_replica_names_ambiguous")
    if len({item.binary_sha256 for item in evidence}) != 1:
        raise RotationError("portal_replica_binary_drift")
    return evidence


def validate_tunnels(
    evidence: tuple[TunnelEvidence, ...],
) -> tuple[TunnelEvidence, ...]:
    if (
        len(evidence) != len(CANONICAL_TUNNEL_SERVICES)
        or tuple(item.service for item in evidence) != CANONICAL_TUNNEL_SERVICES
        or len({item.container_id for item in evidence}) != len(evidence)
    ):
        raise RotationError("canonical_tunnel_topology_invalid")
    for item in evidence:
        if (
            CONTAINER_ID.fullmatch(item.container_id) is None
            or IMAGE_ID.fullmatch(item.image_id) is None
            or not item.running
            or item.health != "healthy"
        ):
            raise RotationError("canonical_tunnel_runtime_invalid")
    return evidence


def capture_storage_authority(
    runtime: RuntimeAuthority,
    portal: PortalEvidence,
) -> dict[str, Any]:
    state_volume = runtime.volume_evidence(EXPECTED_STATE_VOLUME)
    session_volume = runtime.volume_evidence(EXPECTED_SESSION_VOLUME)
    if (
        state_volume.name != EXPECTED_STATE_VOLUME
        or session_volume.name != EXPECTED_SESSION_VOLUME
        or state_volume == session_volume
    ):
        raise RotationError("durable_volume_authority_invalid")
    for volume in (state_volume, session_volume):
        if (
            not volume.driver
            or volume.scope not in {"local", "global"}
            or not volume.mountpoint.startswith("/")
            or not volume.created_at
            or LOWER_SHA256.fullmatch(volume.options_sha256) is None
            or LOWER_SHA256.fullmatch(volume.labels_sha256) is None
        ):
            raise RotationError("durable_volume_authority_invalid")
    keyring = runtime.storage_probe(
        portal.container_id,
        path=EXPECTED_DATA_PROTECTION_ROOT,
        require_encrypted_keyring=True,
    )
    sessions = runtime.storage_probe(
        portal.container_id,
        path=EXPECTED_SESSION_ROOT,
        require_encrypted_keyring=False,
    )
    for probe, expected_path in (
        (keyring, EXPECTED_DATA_PROTECTION_ROOT),
        (sessions, EXPECTED_SESSION_ROOT),
    ):
        if (
            probe.path != expected_path
            or probe.uid < 0
            or probe.gid < 0
            or re.fullmatch(r"[0-7]{3,4}", probe.mode) is None
            or int(probe.mode, 8) & 0o022
        ):
            raise RotationError("durable_storage_metadata_invalid")
    if (
        keyring.key_file_count < 1
        or keyring.encrypted_key_file_count != keyring.key_file_count
        or sessions.key_file_count != 0
        or sessions.encrypted_key_file_count != 0
    ):
        raise RotationError("data_protection_keyring_not_certificate_protected")
    return {
        "volumes": {
            "state": asdict(state_volume),
            "releaseUploadSessions": asdict(session_volume),
        },
        "probes": {
            "dataProtectionKeyring": asdict(keyring),
            "releaseUploadSessions": asdict(sessions),
        },
        "localFallbackAbsent": True,
    }


def verify_health(
    runtime: RuntimeAuthority,
    portals: tuple[PortalEvidence, ...],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for portal in portals:
        for route in LOOPBACK_ROUTES:
            response_sha256 = runtime.verify_loopback(portal.container_id, route)
            if LOWER_SHA256.fullmatch(response_sha256) is None:
                raise RotationError("loopback_response_digest_invalid")
            checks.append(
                {
                    "containerId": portal.container_id,
                    "route": route,
                    "httpStatus": 200,
                    "responseSha256": response_sha256,
                }
            )
    return checks


def verify_public_gets(runtime: RuntimeAuthority) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for path in PUBLIC_GET_PATHS:
        status, response_sha256 = runtime.public_get(path)
        if status != 200 or LOWER_SHA256.fullmatch(response_sha256) is None:
            raise RotationError("public_get_verification_failed")
        checks.append(
            {
                "method": "GET",
                "path": path,
                "httpStatus": status,
                "responseSha256": response_sha256,
            }
        )
    return checks


def verify_old_ticket_revocation(
    runtime: RuntimeAuthority,
    *,
    ticket: str,
    expected_epoch_sha256: str,
) -> dict[str, Any]:
    nonce = secrets.token_hex(32)
    if LOWER_SHA256.fullmatch(nonce) is None:
        raise RotationError("old_ticket_proof_nonce_invalid")
    status, raw_headers, body = runtime.old_ticket_revocation_proof(
        ticket,
        nonce,
    )
    if len(body) > MAX_PUBLIC_BODY_BYTES:
        raise RotationError("old_ticket_proof_response_oversized")
    headers: dict[str, list[str]] = {}
    for name, value in raw_headers:
        normalized = name.strip().lower()
        if not normalized:
            raise RotationError("old_ticket_proof_headers_invalid")
        headers.setdefault(normalized, []).append(value.strip())

    required_headers = {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
        "pragma": "no-cache",
        "expires": "0",
        "www-authenticate": "Bearer",
    }
    if status != 401 or any(
        headers.get(name) != [value]
        for name, value in required_headers.items()
    ):
        raise RotationError("old_ticket_not_revoked")

    proof = strict_json_object(body, label="old_ticket_proof")
    expected_nonce_sha256 = sha256_bytes(nonce.encode("ascii"))
    if (
        set(proof)
        != {
            "contractName",
            "status",
            "ticketAccepted",
            "nonceSha256",
            "revocationEpochSha256",
        }
        or proof.get("contractName") != OLD_TICKET_PROOF_CONTRACT
        or proof.get("status") != "pass"
        or proof.get("ticketAccepted") is not False
        or proof.get("nonceSha256") != expected_nonce_sha256
        or proof.get("revocationEpochSha256") != expected_epoch_sha256
    ):
        raise RotationError("old_ticket_revocation_proof_invalid")
    return {
        "supplied": True,
        "httpStatus": status,
        "status": "pass",
        "contractName": OLD_TICKET_PROOF_CONTRACT,
        "responseSha256": sha256_bytes(body),
        "nonceSha256": expected_nonce_sha256,
        "revocationEpochSha256": expected_epoch_sha256,
        "cacheControl": "no-store",
    }


def strict_receipt(path: Path) -> tuple[dict[str, Any], str]:
    payload = read_owner_only_file(
        path,
        label="receipt",
        maximum_bytes=256 * 1024,
    )
    parsed = strict_json_object(payload, label="receipt")
    if parsed.get("contractName") != CONTRACT_NAME:
        raise RotationError("receipt_contract_invalid")
    return parsed, sha256_bytes(payload)


def read_active_runtime_authority(
    path: Path,
) -> tuple[dict[str, Any], str]:
    payload = read_owner_only_file(
        path,
        label="active_runtime_authority",
        maximum_bytes=64 * 1024,
    )
    parsed = strict_json_object(payload, label="active_runtime_authority")
    portal = parsed.get("portal")
    if (
        frozenset(parsed)
        not in {
            frozenset(ACTIVE_RUNTIME_AUTHORITY_FIELDS),
            frozenset(ENRICHED_ACTIVE_RUNTIME_AUTHORITY_FIELDS),
        }
        or parsed.get("contractName")
        != "chummer.public-edge.active-runtime-authority/v1"
        or parsed.get("status") != "pass"
        or not isinstance(parsed.get("generatedAtUtc"), str)
        or not isinstance(portal, dict)
        or set(portal) != ACTIVE_RUNTIME_PORTAL_FIELDS
        or portal.get("existed") is not True
        or portal.get("wasRunning") is not True
        or type(portal.get("containerId")) is not str
        or CONTAINER_ID.fullmatch(portal["containerId"]) is None
        or type(portal.get("containerName")) is not str
        or SAFE_CONTAINER_NAME.fullmatch(portal["containerName"])
        is None
        or type(portal.get("imageId")) is not str
        or IMAGE_ID.fullmatch(portal["imageId"]) is None
        or type(portal.get("proofAuthorityMountSha256")) is not str
        or LOWER_SHA256.fullmatch(portal["proofAuthorityMountSha256"])
        is None
        or type(portal.get("proofPublicMountSha256")) is not str
        or LOWER_SHA256.fullmatch(portal["proofPublicMountSha256"])
        is None
    ):
        raise RotationError("active_runtime_authority_contract_invalid")
    try:
        generated = datetime.fromisoformat(
            parsed["generatedAtUtc"].replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise RotationError("active_runtime_authority_contract_invalid") from exc
    if generated.tzinfo is None:
        raise RotationError("active_runtime_authority_contract_invalid")
    if set(parsed) == ENRICHED_ACTIVE_RUNTIME_AUTHORITY_FIELDS:
        readiness_path = parsed.get("installLinkingAuthorityReadinessPath")
        readiness_sha256 = parsed.get("installLinkingAuthorityReadinessSha256")
        if (
            not isinstance(readiness_path, str)
            or not Path(readiness_path).is_absolute()
            or type(readiness_sha256) is not str
            or LOWER_SHA256.fullmatch(readiness_sha256) is None
        ):
            raise RotationError("active_runtime_authority_contract_invalid")
    return parsed, sha256_bytes(payload)


def active_runtime_static_sha256(authority: dict[str, Any]) -> str:
    static_authority = {
        key: value
        for key, value in authority.items()
        if key not in {"generatedAtUtc", "portal"}
    }
    return sha256_bytes(
        json.dumps(
            static_authority,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def active_runtime_portal_matches(
    portal: dict[str, Any],
    evidence: PortalEvidence,
) -> bool:
    return portal == {
        "existed": True,
        "containerId": evidence.container_id,
        "containerName": evidence.container_name,
        "imageId": evidence.image_id,
        "wasRunning": True,
        "proofAuthorityMountSha256": evidence.proof_authority_sha256,
        "proofPublicMountSha256": evidence.proof_public_sha256,
    }


def canonical_json_sha256(value: Any) -> str:
    return sha256_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def incident_ticket_commitment_sha256(
    request: RotationRequest,
    ticket: str,
) -> str:
    context = json.dumps(
        {
            "contractName": (
                "chummer.release-upload-ticket-incident-commitment/v1"
            ),
            "sourceHead": request.expected_source_head,
            "imageId": request.expected_image_id,
            "newEpochSha256": sha256_text(request.new_epoch),
            "proofBindSourceSha256": request.expected_proof_sha256,
            "opensslExecutableSha256": (
                request.old_ticket_authority.openssl_executable_sha256
            ),
            "materializationOpensslExecutableSha256": (
                request.old_ticket_authority
                .materialization_openssl_executable_sha256
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    ticket_bytes = bytearray(ticket.encode("ascii"))
    try:
        return hmac.new(
            bytes(ticket_bytes),
            context,
            digestmod=hashlib.sha256,
        ).hexdigest()
    finally:
        for index in range(len(ticket_bytes)):
            ticket_bytes[index] = 0


def rotation_intent_sha256(
    request: RotationRequest,
    *,
    incident_ticket_commitment: str,
) -> str:
    if LOWER_SHA256.fullmatch(incident_ticket_commitment) is None:
        raise RotationError("incident_ticket_commitment_invalid")
    return canonical_json_sha256(
        {
            "contractName": CONTRACT_NAME,
            "sourceHead": request.expected_source_head,
            "imageId": request.expected_image_id,
            "proofBindSourceSha256": request.expected_proof_sha256,
            "environmentSha256Before": request.expected_env_sha256_before,
            "newEpochSha256": sha256_text(request.new_epoch),
            "receiptPath": str(request.output),
            "activeRuntimeAuthorityPath": str(
                request.active_runtime_authority
            ),
            "epochHistoryPath": str(request.epoch_history_path),
            "epochHistoryBootstrapAuthoritySha256": (
                request.expected_epoch_history_bootstrap_authority_sha256
            ),
            "epochHistoryBootstrapMarkerPath": str(
                request.epoch_history_bootstrap_marker
            ),
            "edgeWafLocalEvidenceSha256": (
                request.expected_edge_waf_local_evidence_sha256
            ),
            "incidentTicketCommitmentSha256": (
                incident_ticket_commitment
            ),
        }
    )


def _validate_timestamp(value: Any, *, code: str) -> None:
    if type(value) is not str:
        raise RotationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RotationError(code) from exc
    if parsed.tzinfo is None:
        raise RotationError(code)


def load_epoch_history_bootstrap_authority(
    path: Path,
    *,
    expected_sha256: str,
) -> tuple[dict[str, Any], str, tuple[str, ...]]:
    if LOWER_SHA256.fullmatch(expected_sha256) is None:
        raise RotationError(
            "epoch_history_bootstrap_authority_sha256_invalid"
        )
    payload = read_owner_only_file(
        path,
        label="epoch_history_bootstrap_authority",
        maximum_bytes=MAX_BOOTSTRAP_AUTHORITY_BYTES,
    )
    actual_sha256 = sha256_bytes(payload)
    if actual_sha256 != expected_sha256:
        raise RotationError(
            "epoch_history_bootstrap_authority_sha256_mismatch"
        )
    authority = strict_json_object(
        payload,
        label="epoch_history_bootstrap_authority",
    )
    known_legacy = authority.get("knownLegacyEpochSha256")
    if (
        set(authority) != EPOCH_HISTORY_BOOTSTRAP_AUTHORITY_FIELDS
        or authority.get("contractName")
        != EPOCH_HISTORY_BOOTSTRAP_AUTHORITY_CONTRACT
        or authority.get("status") != "approved"
        or not isinstance(known_legacy, list)
        or not known_legacy
        or any(
            type(epoch_sha256) is not str
            or LOWER_SHA256.fullmatch(epoch_sha256) is None
            for epoch_sha256 in known_legacy
        )
        or len(set(known_legacy)) != len(known_legacy)
    ):
        raise RotationError(
            "epoch_history_bootstrap_authority_contract_invalid"
        )
    _validate_timestamp(
        authority.get("generatedAtUtc"),
        code="epoch_history_bootstrap_authority_contract_invalid",
    )
    return authority, actual_sha256, tuple(known_legacy)


def validate_epoch_history_bootstrap_marker(
    marker: dict[str, Any],
    *,
    expected_bootstrap_authority_sha256: str,
) -> None:
    known_legacy = marker.get("knownLegacyEpochSha256")
    if (
        set(marker) != EPOCH_HISTORY_BOOTSTRAP_MARKER_FIELDS
        or marker.get("contractName")
        != EPOCH_HISTORY_BOOTSTRAP_MARKER_CONTRACT
        or marker.get("status") != "initialized"
        or marker.get("bootstrapAuthoritySha256")
        != expected_bootstrap_authority_sha256
        or not isinstance(known_legacy, list)
        or not known_legacy
        or any(
            type(epoch_sha256) is not str
            or LOWER_SHA256.fullmatch(epoch_sha256) is None
            for epoch_sha256 in known_legacy
        )
        or len(set(known_legacy)) != len(known_legacy)
        or type(marker.get("initialRotationIntentSha256")) is not str
        or LOWER_SHA256.fullmatch(
            marker["initialRotationIntentSha256"]
        )
        is None
        or type(marker.get("epochHistoryPathSha256")) is not str
        or LOWER_SHA256.fullmatch(marker["epochHistoryPathSha256"])
        is None
    ):
        raise RotationError(
            "epoch_history_bootstrap_marker_contract_invalid"
        )
    _validate_timestamp(
        marker.get("generatedAtUtc"),
        code="epoch_history_bootstrap_marker_contract_invalid",
    )


def load_epoch_history_bootstrap_marker(
    path: Path,
    *,
    expected_sha256: str,
    expected_bootstrap_authority_sha256: str,
) -> tuple[dict[str, Any] | None, str]:
    require_owner_only_directory(
        path.parent,
        label="epoch_history_bootstrap_marker_root",
    )
    if path.is_symlink():
        raise RotationError("epoch_history_bootstrap_marker_path_invalid")
    if expected_sha256 == EPOCH_HISTORY_ABSENT_PIN:
        if os.path.lexists(path):
            raise RotationError(
                "epoch_history_bootstrap_marker_expected_absent"
            )
        return None, EPOCH_HISTORY_ABSENT_PIN
    if LOWER_SHA256.fullmatch(expected_sha256) is None:
        raise RotationError(
            "epoch_history_bootstrap_marker_expected_sha256_invalid"
        )
    payload = read_owner_only_file(
        path,
        label="epoch_history_bootstrap_marker",
        maximum_bytes=MAX_BOOTSTRAP_AUTHORITY_BYTES,
    )
    actual_sha256 = sha256_bytes(payload)
    if actual_sha256 != expected_sha256:
        raise RotationError(
            "epoch_history_bootstrap_marker_sha256_mismatch"
        )
    marker = strict_json_object(
        payload,
        label="epoch_history_bootstrap_marker",
    )
    validate_epoch_history_bootstrap_marker(
        marker,
        expected_bootstrap_authority_sha256=(
            expected_bootstrap_authority_sha256
        ),
    )
    return marker, actual_sha256


def publish_epoch_history_bootstrap_marker(
    request: RotationRequest,
    *,
    bootstrap_authority_sha256: str,
    known_legacy_epoch_sha256: tuple[str, ...],
    intent_sha256: str,
) -> str:
    marker = {
        "contractName": EPOCH_HISTORY_BOOTSTRAP_MARKER_CONTRACT,
        "status": "initialized",
        "generatedAtUtc": now_iso(),
        "bootstrapAuthoritySha256": bootstrap_authority_sha256,
        "knownLegacyEpochSha256": list(known_legacy_epoch_sha256),
        "initialRotationIntentSha256": intent_sha256,
        "epochHistoryPathSha256": sha256_text(
            str(request.epoch_history_path)
        ),
    }
    validate_epoch_history_bootstrap_marker(
        marker,
        expected_bootstrap_authority_sha256=bootstrap_authority_sha256,
    )
    _prior, prior_sha256 = load_epoch_history_bootstrap_marker(
        request.epoch_history_bootstrap_marker,
        expected_sha256=EPOCH_HISTORY_ABSENT_PIN,
        expected_bootstrap_authority_sha256=bootstrap_authority_sha256,
    )
    assert prior_sha256 == EPOCH_HISTORY_ABSENT_PIN
    marker_sha256 = atomic_write_private_json(
        request.epoch_history_bootstrap_marker,
        marker,
    )
    _verified, verified_sha256 = load_epoch_history_bootstrap_marker(
        request.epoch_history_bootstrap_marker,
        expected_sha256=marker_sha256,
        expected_bootstrap_authority_sha256=bootstrap_authority_sha256,
    )
    return verified_sha256


def _history_event_sha256(event: dict[str, Any]) -> str:
    return canonical_json_sha256(
        {key: value for key, value in event.items() if key != "eventSha256"}
    )


def validate_epoch_history(history: dict[str, Any]) -> None:
    events = history.get("events")
    generation = history.get("generation")
    updated_at = history.get("updatedAtUtc")
    head_event_sha256 = history.get("headEventSha256")
    if (
        set(history) != EPOCH_HISTORY_FIELDS
        or history.get("contractName") != EPOCH_HISTORY_CONTRACT
        or history.get("status") != "active"
        or not isinstance(events, list)
        or not events
        or type(generation) is not int
        or generation != len(events)
        or not isinstance(updated_at, str)
        or not isinstance(head_event_sha256, str)
        or LOWER_SHA256.fullmatch(head_event_sha256) is None
    ):
        raise RotationError("epoch_history_contract_invalid")
    try:
        updated = datetime.fromisoformat(
            updated_at.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise RotationError("epoch_history_contract_invalid") from exc
    if updated.tzinfo is None:
        raise RotationError("epoch_history_contract_invalid")

    seen_epochs: dict[str, str] = {}
    prior_event_sha256 = ZERO_SHA256
    for sequence, raw_event in enumerate(history["events"]):
        if not isinstance(raw_event, dict) or set(raw_event) != (
            EPOCH_HISTORY_EVENT_FIELDS
        ):
            raise RotationError("epoch_history_event_invalid")
        event = raw_event
        event_sequence = event.get("sequence")
        event_type = event.get("eventType")
        epoch_sha256 = event.get("epochSha256")
        intent_sha256 = event.get("rotationIntentSha256")
        previous_event_sha256 = event.get("previousEventSha256")
        recorded_at = event.get("recordedAtUtc")
        source_head = event.get("sourceHead")
        image_id = event.get("imageId")
        event_sha256 = event.get("eventSha256")
        if (
            type(event_sequence) is not int
            or event_sequence != sequence
            or not isinstance(event_type, str)
            or event_type
            not in {
                "legacy_observed",
                "rotation_reserved",
                "rotation_committed",
            }
            or not isinstance(epoch_sha256, str)
            or LOWER_SHA256.fullmatch(epoch_sha256) is None
            or not isinstance(intent_sha256, str)
            or LOWER_SHA256.fullmatch(intent_sha256) is None
            or not isinstance(previous_event_sha256, str)
            or previous_event_sha256 != prior_event_sha256
            or not isinstance(recorded_at, str)
            or not isinstance(source_head, str)
            or re.fullmatch(r"[0-9a-f]{40}", source_head) is None
            or not isinstance(image_id, str)
            or IMAGE_ID.fullmatch(image_id) is None
            or not isinstance(event_sha256, str)
            or LOWER_SHA256.fullmatch(event_sha256) is None
            or _history_event_sha256(event) != event_sha256
        ):
            raise RotationError("epoch_history_event_invalid")
        try:
            recorded = datetime.fromisoformat(
                recorded_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise RotationError("epoch_history_event_invalid") from exc
        if recorded.tzinfo is None:
            raise RotationError("epoch_history_event_invalid")

        if event_type == "legacy_observed":
            if (
                intent_sha256 != ZERO_SHA256
                or any(
                    prior.get("eventType") != "legacy_observed"
                    for prior in history["events"][:sequence]
                )
            ):
                raise RotationError("epoch_history_legacy_invalid")
            if epoch_sha256 in seen_epochs:
                raise RotationError("epoch_history_epoch_reused")
            seen_epochs[epoch_sha256] = ZERO_SHA256
        elif event_type == "rotation_reserved":
            if intent_sha256 == ZERO_SHA256 or epoch_sha256 in seen_epochs:
                raise RotationError("epoch_history_epoch_reused")
            seen_epochs[epoch_sha256] = intent_sha256
        else:
            if (
                sequence == 0
                or history["events"][sequence - 1].get("eventType")
                != "rotation_reserved"
                or history["events"][sequence - 1].get("epochSha256")
                != epoch_sha256
                or history["events"][sequence - 1].get(
                    "rotationIntentSha256"
                )
                != intent_sha256
                or seen_epochs.get(epoch_sha256) != intent_sha256
            ):
                raise RotationError("epoch_history_commit_invalid")
        prior_event_sha256 = event_sha256
    if history["headEventSha256"] != prior_event_sha256:
        raise RotationError("epoch_history_head_invalid")


def load_epoch_history(
    path: Path,
    *,
    expected_sha256: str,
) -> tuple[dict[str, Any] | None, str]:
    require_owner_only_directory(path.parent, label="epoch_history_root")
    if path.is_symlink():
        raise RotationError("epoch_history_path_invalid")
    if expected_sha256 == EPOCH_HISTORY_ABSENT_PIN:
        if os.path.lexists(path):
            raise RotationError("epoch_history_expected_absent")
        return None, EPOCH_HISTORY_ABSENT_PIN
    if LOWER_SHA256.fullmatch(expected_sha256) is None:
        raise RotationError("epoch_history_expected_sha256_invalid")
    payload = read_owner_only_file(
        path,
        label="epoch_history",
        maximum_bytes=MAX_HISTORY_BYTES,
    )
    actual_sha256 = sha256_bytes(payload)
    if actual_sha256 != expected_sha256:
        raise RotationError("epoch_history_sha256_mismatch")
    history = strict_json_object(payload, label="epoch_history")
    validate_epoch_history(history)
    return history, actual_sha256


def _new_history_event(
    *,
    sequence: int,
    event_type: str,
    epoch_sha256: str,
    intent_sha256: str,
    previous_event_sha256: str,
    request: RotationRequest,
) -> dict[str, Any]:
    event = {
        "sequence": sequence,
        "eventType": event_type,
        "epochSha256": epoch_sha256,
        "rotationIntentSha256": intent_sha256,
        "previousEventSha256": previous_event_sha256,
        "recordedAtUtc": now_iso(),
        "sourceHead": request.expected_source_head,
        "imageId": request.expected_image_id,
    }
    event["eventSha256"] = _history_event_sha256(event)
    return event


def _history_with_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    history = {
        "contractName": EPOCH_HISTORY_CONTRACT,
        "status": "active",
        "updatedAtUtc": now_iso(),
        "generation": len(events),
        "headEventSha256": events[-1]["eventSha256"],
        "events": events,
    }
    validate_epoch_history(history)
    return history


def reserve_epoch_history(
    history: dict[str, Any] | None,
    *,
    current_epoch_sha256: str,
    new_epoch_sha256: str,
    intent_sha256: str,
    known_legacy_epoch_sha256: tuple[str, ...],
    request: RotationRequest,
) -> tuple[dict[str, Any], bool]:
    events = [] if history is None else list(history["events"])
    if not events:
        if (
            current_epoch_sha256 not in known_legacy_epoch_sha256
            or new_epoch_sha256 in known_legacy_epoch_sha256
        ):
            raise RotationError(
                "epoch_history_bootstrap_legacy_epochs_invalid"
            )
        for legacy_epoch_sha256 in known_legacy_epoch_sha256:
            events.append(
                _new_history_event(
                    sequence=len(events),
                    event_type="legacy_observed",
                    epoch_sha256=legacy_epoch_sha256,
                    intent_sha256=ZERO_SHA256,
                    previous_event_sha256=(
                        events[-1]["eventSha256"]
                        if events
                        else ZERO_SHA256
                    ),
                    request=request,
                )
            )
    elif not any(
        event["epochSha256"] == current_epoch_sha256 for event in events
    ):
        raise RotationError("epoch_history_current_epoch_missing")

    matching = [
        event for event in events if event["epochSha256"] == new_epoch_sha256
    ]
    if matching:
        if any(
            event["eventType"] in {"rotation_reserved", "rotation_committed"}
            and event["rotationIntentSha256"] == intent_sha256
            for event in matching
        ):
            assert history is not None
            return history, False
        raise RotationError("epoch_history_epoch_reused")
    events.append(
        _new_history_event(
            sequence=len(events),
            event_type="rotation_reserved",
            epoch_sha256=new_epoch_sha256,
            intent_sha256=intent_sha256,
            previous_event_sha256=events[-1]["eventSha256"],
            request=request,
        )
    )
    return _history_with_events(events), True


def commit_epoch_history(
    history: dict[str, Any],
    *,
    new_epoch_sha256: str,
    intent_sha256: str,
    request: RotationRequest,
) -> tuple[dict[str, Any], bool]:
    events = list(history["events"])
    if (
        events[-1]["eventType"] == "rotation_committed"
        and events[-1]["epochSha256"] == new_epoch_sha256
        and events[-1]["rotationIntentSha256"] == intent_sha256
    ):
        return history, False
    if (
        events[-1]["eventType"] != "rotation_reserved"
        or events[-1]["epochSha256"] != new_epoch_sha256
        or events[-1]["rotationIntentSha256"] != intent_sha256
    ):
        raise RotationError("epoch_history_reservation_missing")
    events.append(
        _new_history_event(
            sequence=len(events),
            event_type="rotation_committed",
            epoch_sha256=new_epoch_sha256,
            intent_sha256=intent_sha256,
            previous_event_sha256=events[-1]["eventSha256"],
            request=request,
        )
    )
    return _history_with_events(events), True


def publish_epoch_history(
    path: Path,
    history: dict[str, Any],
    *,
    expected_current_sha256: str,
) -> str:
    load_epoch_history(path, expected_sha256=expected_current_sha256)
    history_sha256 = atomic_write_private_json(path, history)
    _history, verified_sha256 = load_epoch_history(
        path,
        expected_sha256=history_sha256,
    )
    return verified_sha256


def publish_active_runtime_authority(
    path: Path,
    *,
    prior_authority: dict[str, Any],
    portal: PortalEvidence,
) -> str:
    payload = dict(prior_authority)
    payload["generatedAtUtc"] = now_iso()
    payload["portal"] = {
        "existed": True,
        "containerId": portal.container_id,
        "containerName": portal.container_name,
        "imageId": portal.image_id,
        "wasRunning": True,
        "proofAuthorityMountSha256": portal.proof_authority_sha256,
        "proofPublicMountSha256": portal.proof_public_sha256,
    }
    return atomic_write_private_json(path, payload)


def publish_epoch_authority(
    request: RotationRequest,
    *,
    incident_ticket_commitment: str,
    rotation_receipt_sha256: str,
    active_runtime_authority_sha256: str,
    portal: PortalEvidence,
    storage_authority: dict[str, Any],
    environment_sha256_after: str,
    epoch_history_sha256: str,
    epoch_history_head_event_sha256: str,
    epoch_history_bootstrap_marker_sha256: str,
    edge_waf_local_evidence_sha256: str,
) -> str:
    storage_sha256 = sha256_bytes(
        json.dumps(
            storage_authority,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    payload = {
        "contractName": "chummer.release-upload-ticket-epoch-authority/v1",
        "status": "pass",
        "generatedAtUtc": now_iso(),
        "sourceHead": request.expected_source_head,
        "imageId": request.expected_image_id,
        "proofBindSourceSha256": request.expected_proof_sha256,
        "newEpochSha256": sha256_text(request.new_epoch),
        "environmentSha256After": environment_sha256_after,
        "epochHistoryPath": str(request.epoch_history_path),
        "epochHistorySha256": epoch_history_sha256,
        "epochHistoryHeadEventSha256": (
            epoch_history_head_event_sha256
        ),
        "rotationIntentSha256": rotation_intent_sha256(
            request,
            incident_ticket_commitment=incident_ticket_commitment,
        ),
        "epochHistoryBootstrapAuthoritySha256": (
            request.expected_epoch_history_bootstrap_authority_sha256
        ),
        "epochHistoryBootstrapMarkerPath": str(
            request.epoch_history_bootstrap_marker
        ),
        "epochHistoryBootstrapMarkerSha256": (
            epoch_history_bootstrap_marker_sha256
        ),
        "edgeWafLocalEvidenceSha256": (
            edge_waf_local_evidence_sha256
        ),
        "portalContainerId": portal.container_id,
        "portalContainerName": portal.container_name,
        "portalRuntimeContractSha256": portal.runtime_contract_sha256,
        "storageAuthoritySha256": storage_sha256,
        "activeRuntimeAuthorityPath": str(request.active_runtime_authority),
        "activeRuntimeAuthoritySha256": active_runtime_authority_sha256,
        "rotationReceiptPath": str(request.output),
        "rotationReceiptSha256": rotation_receipt_sha256,
        "edgeWafMutationPerformed": False,
        "edgeWafLocalEvidenceStableThroughPostVerification": True,
        "edgeWafLiveControlPlaneVerified": False,
    }
    return atomic_write_private_json(request.epoch_authority_output, payload)


@dataclass(frozen=True)
class RotationRequest:
    env_file: Path
    active_runtime_authority: Path
    output: Path
    expected_env_sha256_before: str
    expected_image_id: str
    expected_proof_sha256: str
    image_tag: str
    expected_source_head: str
    new_epoch: str
    expected_portal_replicas: int
    shared_mutation_lock_token: str
    old_ticket_path: Path | None
    old_ticket_authority: TicketMaterializationAuthority
    proof_bind_source: Path
    expected_existing_receipt_sha256: str
    epoch_authority_output: Path
    epoch_history_path: Path
    expected_epoch_history_sha256: str
    epoch_history_bootstrap_authority: Path
    expected_epoch_history_bootstrap_authority_sha256: str
    epoch_history_bootstrap_marker: Path
    expected_epoch_history_bootstrap_marker_sha256: str
    edge_waf_local_evidence_source: Path
    expected_edge_waf_local_evidence_sha256: str


def _base_receipt(
    request: RotationRequest,
    *,
    incident_ticket_commitment: str,
) -> dict[str, Any]:
    return {
        "contractName": CONTRACT_NAME,
        "status": "in_progress",
        "phase": "initializing",
        "generatedAtUtc": now_iso(),
        "updatedAtUtc": now_iso(),
        "sourceHead": request.expected_source_head,
        "imageTag": request.image_tag,
        "imageId": request.expected_image_id,
        "proofBindSourceSha256": request.expected_proof_sha256,
        "epochAuthorityPath": str(request.epoch_authority_output),
        "epochHistoryPath": str(request.epoch_history_path),
        "epochHistoryExpectedSha256": (
            request.expected_epoch_history_sha256
        ),
        "epochHistorySha256Before": "",
        "epochHistorySha256AfterReservation": "",
        "epochHistorySha256AfterCommit": "",
        "epochHistoryHeadEventSha256": "",
        "epochHistoryBootstrapAuthoritySha256": (
            request.expected_epoch_history_bootstrap_authority_sha256
        ),
        "epochHistoryBootstrapMarkerSha256": "",
        "rotationIntentSha256": rotation_intent_sha256(
            request,
            incident_ticket_commitment=incident_ticket_commitment,
        ),
        "portalReplicaCount": request.expected_portal_replicas,
        "newEpochSha256": sha256_text(request.new_epoch),
        "environmentSha256Before": request.expected_env_sha256_before,
        "environmentSha256After": "",
        "activeRuntimeAuthoritySha256Before": "",
        "activeRuntimeAuthoritySha256After": "",
        "activeRuntimeAuthorityStaticSha256": "",
        "oldEpochSha256": "",
        "preRotationPortals": [],
        "postRotationPortals": [],
        "canonicalTunnelsBefore": [],
        "canonicalTunnelsAfter": [],
        "storageAuthorityBefore": {},
        "storageAuthorityAfter": {},
        "loopbackChecksBefore": [],
        "loopbackChecksAfter": [],
        "publicGetChecksBefore": [],
        "publicGetChecksAfter": [],
        "oldTicketRevocationProof": {
            "supplied": request.old_ticket_path is not None,
            "httpStatus": None,
            "status": "pending" if request.old_ticket_path is not None else "not_supplied",
        },
        "edgeWafLocalEvidence": {
            "evidenceScope": "pinned_local_evidence_only",
            "mutationAuthorized": False,
            "mutationPerformed": False,
            "stableThroughPostVerification": False,
            "sha256Before": (
                request.expected_edge_waf_local_evidence_sha256
            ),
            "sha256After": "",
            "liveControlPlaneVerified": False,
        },
        "recreated": False,
        "failureContainment": {
            "portalQuiescenceProven": False,
            "publicConnectorsStopped": False,
        },
        "rollbackPolicy": "old_epoch_rollback_permanently_forbidden_after_epoch_commit",
        "recreationPolicy": "all_prior_replicas_stopped_and_removed_before_any_recreate",
        "failureCode": "",
    }


def _validate_request(request: RotationRequest) -> None:
    canonical_paths = {
        "environment": request.env_file,
        "active_runtime_authority": request.active_runtime_authority,
        "receipt": request.output,
        "proof_bind_source": request.proof_bind_source,
        "epoch_authority": request.epoch_authority_output,
        "epoch_history": request.epoch_history_path,
        "epoch_history_bootstrap_authority": (
            request.epoch_history_bootstrap_authority
        ),
        "epoch_history_bootstrap_marker": (
            request.epoch_history_bootstrap_marker
        ),
        "edge_waf_local_evidence_source": (
            request.edge_waf_local_evidence_source
        ),
    }
    if request.old_ticket_path is not None:
        canonical_paths["old_ticket"] = request.old_ticket_path
    for label, path in canonical_paths.items():
        if (
            not path.is_absolute()
            or overlay.normalized_absolute_path(path) != path
        ):
            raise RotationError(f"{label}_path_invalid")
    mutation_outputs = {
        request.output,
        request.epoch_authority_output,
        request.epoch_history_path,
        request.epoch_history_bootstrap_marker,
    }
    if len(mutation_outputs) != 4 or mutation_outputs & {
        request.env_file,
        request.active_runtime_authority,
        request.proof_bind_source,
        request.epoch_history_bootstrap_authority,
        request.edge_waf_local_evidence_source,
        request.old_ticket_path,
    }:
        raise RotationError("rotation_authority_paths_overlap")
    if LOWER_SHA256.fullmatch(request.expected_env_sha256_before) is None:
        raise RotationError("expected_environment_sha256_invalid")
    if IMAGE_ID.fullmatch(request.expected_image_id) is None:
        raise RotationError("expected_image_id_invalid")
    if LOWER_SHA256.fullmatch(request.expected_proof_sha256) is None:
        raise RotationError("expected_proof_sha256_invalid")
    if request.image_tag != CANONICAL_IMAGE_TAG:
        raise RotationError("image_tag_not_canonical")
    if request.expected_existing_receipt_sha256 and LOWER_SHA256.fullmatch(
        request.expected_existing_receipt_sha256
    ) is None:
        raise RotationError("expected_existing_receipt_sha256_invalid")
    if (
        request.epoch_authority_output
        in {request.output, request.active_runtime_authority}
    ):
        raise RotationError("epoch_authority_output_invalid")
    if (
        request.epoch_history_path
        in {
            request.output,
            request.active_runtime_authority,
            request.epoch_authority_output,
        }
        or (
            request.expected_epoch_history_sha256
            != EPOCH_HISTORY_ABSENT_PIN
            and LOWER_SHA256.fullmatch(
                request.expected_epoch_history_sha256
            )
            is None
        )
    ):
        raise RotationError("epoch_history_authority_invalid")
    if re.fullmatch(r"[0-9a-f]{40}", request.expected_source_head) is None:
        raise RotationError("expected_source_head_invalid")
    if SAFE_EPOCH.fullmatch(request.new_epoch) is None:
        raise RotationError("new_epoch_invalid")
    if request.expected_portal_replicas != 1:
        # Durable upload sessions use host-filesystem locks. Until a verified
        # cross-host lock exists there must be exactly one portal writer.
        raise RotationError("portal_replica_count_must_be_one")
    if re.fullmatch(r"[0-9a-f]{64}", request.shared_mutation_lock_token) is None:
        raise RotationError("shared_mutation_lock_token_invalid")
    if request.old_ticket_path is None:
        raise RotationError("old_ticket_proof_required")
    ticket_authority = request.old_ticket_authority
    if (
        not isinstance(
            ticket_authority,
            TicketMaterializationAuthority,
        )
        or type(ticket_authority.fd) is not int
        or ticket_authority.fd < 3
        or ticket_authority.fd > 255
        or type(ticket_authority.ticket_size_bytes) is not int
        or ticket_authority.ticket_size_bytes < 1
        or ticket_authority.ticket_size_bytes > MAX_TICKET_BYTES
        or any(
            type(value) is not str
            or LOWER_SHA256.fullmatch(value) is None
            for value in (
                ticket_authority.ticket_path_sha256,
                ticket_authority.ticket_sha256,
                ticket_authority.envelope_sha256,
                ticket_authority.inventory_commitment_sha256,
                ticket_authority.recipient_certificate_sha256,
                ticket_authority.signer_certificate_sha256,
                ticket_authority.openssl_executable_sha256,
                ticket_authority.materialization_openssl_executable_sha256,
            )
        )
        or type(ticket_authority.materialization_transaction_id) is not str
        or SAFE_TRANSACTION_ID.fullmatch(
            ticket_authority.materialization_transaction_id
        )
        is None
    ):
        raise RotationError("old_ticket_authority_invalid")
    if LOWER_SHA256.fullmatch(
        request.expected_epoch_history_bootstrap_authority_sha256
    ) is None:
        raise RotationError(
            "epoch_history_bootstrap_authority_sha256_invalid"
        )
    if (
        request.expected_epoch_history_bootstrap_marker_sha256
        != EPOCH_HISTORY_ABSENT_PIN
        and LOWER_SHA256.fullmatch(
            request.expected_epoch_history_bootstrap_marker_sha256
        )
        is None
    ):
        raise RotationError(
            "epoch_history_bootstrap_marker_sha256_invalid"
        )
    if LOWER_SHA256.fullmatch(
        request.expected_edge_waf_local_evidence_sha256
    ) is None:
        raise RotationError(
            "edge_waf_local_evidence_sha256_invalid"
        )


ROTATION_RECEIPT_FIELDS = {
    "contractName",
    "status",
    "phase",
    "generatedAtUtc",
    "updatedAtUtc",
    "sourceHead",
    "imageTag",
    "imageId",
    "proofBindSourceSha256",
    "epochAuthorityPath",
    "epochHistoryPath",
    "epochHistoryExpectedSha256",
    "epochHistorySha256Before",
    "epochHistorySha256AfterReservation",
    "epochHistorySha256AfterCommit",
    "epochHistoryHeadEventSha256",
    "epochHistoryBootstrapAuthoritySha256",
    "epochHistoryBootstrapMarkerSha256",
    "rotationIntentSha256",
    "portalReplicaCount",
    "newEpochSha256",
    "environmentSha256Before",
    "environmentSha256After",
    "activeRuntimeAuthoritySha256Before",
    "activeRuntimeAuthoritySha256After",
    "activeRuntimeAuthorityStaticSha256",
    "oldEpochSha256",
    "preRotationPortals",
    "postRotationPortals",
    "canonicalTunnelsBefore",
    "canonicalTunnelsAfter",
    "storageAuthorityBefore",
    "storageAuthorityAfter",
    "loopbackChecksBefore",
    "loopbackChecksAfter",
    "publicGetChecksBefore",
    "publicGetChecksAfter",
    "oldTicketRevocationProof",
    "edgeWafLocalEvidence",
    "recreated",
    "failureContainment",
    "rollbackPolicy",
    "recreationPolicy",
    "failureCode",
}
PORTAL_RECEIPT_FIELDS = {
    "containerId",
    "containerName",
    "imageId",
    "running",
    "health",
    "restartPolicy",
    "epochSha256",
    "binarySha256",
    "proofAuthoritySha256",
    "proofPublicSha256",
    "mounts",
    "releaseUploadSessionRoot",
    "dataProtectionRoot",
    "directBundleUploadEnabled",
    "runtimeContractSha256",
}
MOUNT_RECEIPT_FIELDS = {"destination", "volume_name", "read_write"}
TUNNEL_RECEIPT_FIELDS = {
    "service",
    "containerId",
    "imageId",
    "running",
    "health",
}


def _require_receipt_string(
    value: Any,
    *,
    code: str = "receipt_types_invalid",
    pattern: re.Pattern[str] | None = None,
    allow_empty: bool = False,
) -> str:
    if (
        type(value) is not str
        or (not allow_empty and not value)
        or (value and pattern is not None and pattern.fullmatch(value) is None)
    ):
        raise RotationError(code)
    return value


def _validate_portal_receipt_payload(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != PORTAL_RECEIPT_FIELDS:
        raise RotationError("receipt_types_invalid")
    _require_receipt_string(value["containerId"], pattern=CONTAINER_ID)
    _require_receipt_string(value["containerName"], pattern=SAFE_CONTAINER_NAME)
    _require_receipt_string(value["imageId"], pattern=IMAGE_ID)
    if type(value["running"]) is not bool:
        raise RotationError("receipt_types_invalid")
    for key in (
        "health",
        "restartPolicy",
        "releaseUploadSessionRoot",
        "dataProtectionRoot",
        "directBundleUploadEnabled",
    ):
        _require_receipt_string(value[key])
    for key in (
        "epochSha256",
        "binarySha256",
        "proofAuthoritySha256",
        "proofPublicSha256",
        "runtimeContractSha256",
    ):
        _require_receipt_string(value[key], pattern=LOWER_SHA256)
    mounts = value["mounts"]
    if not isinstance(mounts, dict) or set(mounts) != {
        "state",
        "releaseUploadSessions",
    }:
        raise RotationError("receipt_types_invalid")
    for mount in mounts.values():
        if not isinstance(mount, dict) or set(mount) != MOUNT_RECEIPT_FIELDS:
            raise RotationError("receipt_types_invalid")
        _require_receipt_string(mount["destination"])
        _require_receipt_string(mount["volume_name"])
        if type(mount["read_write"]) is not bool:
            raise RotationError("receipt_types_invalid")


def _validate_tunnel_receipt_payload(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != TUNNEL_RECEIPT_FIELDS:
        raise RotationError("receipt_types_invalid")
    _require_receipt_string(value["service"])
    _require_receipt_string(value["containerId"], pattern=CONTAINER_ID)
    _require_receipt_string(value["imageId"], pattern=IMAGE_ID)
    if type(value["running"]) is not bool:
        raise RotationError("receipt_types_invalid")
    _require_receipt_string(value["health"])


def _validate_storage_receipt_payload(value: Any) -> None:
    if value == {}:
        return
    if (
        not isinstance(value, dict)
        or set(value) != {"volumes", "probes", "localFallbackAbsent"}
        or value.get("localFallbackAbsent") is not True
    ):
        raise RotationError("receipt_types_invalid")
    volumes = value["volumes"]
    probes = value["probes"]
    if (
        not isinstance(volumes, dict)
        or set(volumes) != {"state", "releaseUploadSessions"}
        or not isinstance(probes, dict)
        or set(probes)
        != {"dataProtectionKeyring", "releaseUploadSessions"}
    ):
        raise RotationError("receipt_types_invalid")
    volume_fields = {
        "name",
        "driver",
        "scope",
        "mountpoint",
        "created_at",
        "options_sha256",
        "labels_sha256",
    }
    for volume in volumes.values():
        if not isinstance(volume, dict) or set(volume) != volume_fields:
            raise RotationError("receipt_types_invalid")
        for key in ("name", "driver", "scope", "mountpoint", "created_at"):
            _require_receipt_string(volume[key])
        for key in ("options_sha256", "labels_sha256"):
            _require_receipt_string(volume[key], pattern=LOWER_SHA256)
    probe_fields = {
        "path",
        "uid",
        "gid",
        "mode",
        "key_file_count",
        "encrypted_key_file_count",
    }
    for probe in probes.values():
        if not isinstance(probe, dict) or set(probe) != probe_fields:
            raise RotationError("receipt_types_invalid")
        _require_receipt_string(probe["path"])
        _require_receipt_string(probe["mode"])
        for key in (
            "uid",
            "gid",
            "key_file_count",
            "encrypted_key_file_count",
        ):
            if type(probe[key]) is not int or probe[key] < 0:
                raise RotationError("receipt_types_invalid")


def validate_rotation_receipt_types(receipt: dict[str, Any]) -> None:
    if set(receipt) != ROTATION_RECEIPT_FIELDS:
        raise RotationError("receipt_contract_invalid")
    for key in (
        "contractName",
        "status",
        "phase",
        "imageTag",
        "epochAuthorityPath",
        "epochHistoryPath",
        "rollbackPolicy",
        "recreationPolicy",
    ):
        _require_receipt_string(receipt[key])
    for key in ("generatedAtUtc", "updatedAtUtc"):
        _validate_timestamp(receipt[key], code="receipt_types_invalid")
    _require_receipt_string(receipt["sourceHead"])
    if re.fullmatch(r"[0-9a-f]{40}", receipt["sourceHead"]) is None:
        raise RotationError("receipt_types_invalid")
    _require_receipt_string(receipt["imageId"], pattern=IMAGE_ID)
    for key in (
        "proofBindSourceSha256",
        "epochHistoryBootstrapAuthoritySha256",
        "rotationIntentSha256",
        "newEpochSha256",
        "environmentSha256Before",
    ):
        _require_receipt_string(receipt[key], pattern=LOWER_SHA256)
    for key in (
        "epochHistorySha256AfterReservation",
        "epochHistorySha256AfterCommit",
        "epochHistoryHeadEventSha256",
        "epochHistoryBootstrapMarkerSha256",
        "environmentSha256After",
        "activeRuntimeAuthoritySha256Before",
        "activeRuntimeAuthoritySha256After",
        "activeRuntimeAuthorityStaticSha256",
        "oldEpochSha256",
    ):
        _require_receipt_string(
            receipt[key],
            pattern=LOWER_SHA256,
            allow_empty=True,
        )
    history_before = receipt["epochHistorySha256Before"]
    if (
        history_before not in {"", EPOCH_HISTORY_ABSENT_PIN}
        and (
            type(history_before) is not str
            or LOWER_SHA256.fullmatch(history_before) is None
        )
    ):
        raise RotationError("receipt_types_invalid")
    history_expected = receipt["epochHistoryExpectedSha256"]
    if (
        history_expected != EPOCH_HISTORY_ABSENT_PIN
        and (
            type(history_expected) is not str
            or LOWER_SHA256.fullmatch(history_expected) is None
        )
    ):
        raise RotationError("receipt_types_invalid")
    if (
        type(receipt["portalReplicaCount"]) is not int
        or receipt["portalReplicaCount"] != 1
        or type(receipt["recreated"]) is not bool
        or type(receipt["failureCode"]) is not str
    ):
        raise RotationError("receipt_types_invalid")
    for key in ("preRotationPortals", "postRotationPortals"):
        value = receipt[key]
        if not isinstance(value, list):
            raise RotationError("receipt_types_invalid")
        for portal in value:
            _validate_portal_receipt_payload(portal)
    for key in ("canonicalTunnelsBefore", "canonicalTunnelsAfter"):
        value = receipt[key]
        if not isinstance(value, list):
            raise RotationError("receipt_types_invalid")
        for tunnel in value:
            _validate_tunnel_receipt_payload(tunnel)
    for key in ("storageAuthorityBefore", "storageAuthorityAfter"):
        _validate_storage_receipt_payload(receipt[key])
    for key in ("loopbackChecksBefore", "loopbackChecksAfter"):
        value = receipt[key]
        if not isinstance(value, list):
            raise RotationError("receipt_types_invalid")
        for check in value:
            if (
                not isinstance(check, dict)
                or set(check)
                != {
                    "containerId",
                    "route",
                    "httpStatus",
                    "responseSha256",
                }
                or type(check["httpStatus"]) is not int
                or check["httpStatus"] != 200
            ):
                raise RotationError("receipt_types_invalid")
            _require_receipt_string(
                check["containerId"],
                pattern=CONTAINER_ID,
            )
            _require_receipt_string(check["route"])
            _require_receipt_string(
                check["responseSha256"],
                pattern=LOWER_SHA256,
            )
    for key in ("publicGetChecksBefore", "publicGetChecksAfter"):
        value = receipt[key]
        if not isinstance(value, list):
            raise RotationError("receipt_types_invalid")
        for check in value:
            if (
                not isinstance(check, dict)
                or set(check)
                != {"method", "path", "httpStatus", "responseSha256"}
                or check.get("method") != "GET"
                or type(check.get("httpStatus")) is not int
                or check["httpStatus"] != 200
            ):
                raise RotationError("receipt_types_invalid")
            _require_receipt_string(check["path"])
            _require_receipt_string(
                check["responseSha256"],
                pattern=LOWER_SHA256,
            )
    proof = receipt["oldTicketRevocationProof"]
    if not isinstance(proof, dict) or frozenset(proof) not in {
        frozenset({"supplied", "httpStatus", "status"}),
        frozenset(
            {
                "supplied",
                "httpStatus",
                "status",
                "contractName",
                "responseSha256",
                "nonceSha256",
                "revocationEpochSha256",
                "cacheControl",
            }
        ),
    }:
        raise RotationError("receipt_types_invalid")
    if (
        proof.get("supplied") is not True
        or (
            proof.get("httpStatus") is not None
            and type(proof.get("httpStatus")) is not int
        )
    ):
        raise RotationError("receipt_types_invalid")
    _require_receipt_string(proof.get("status"))
    for key in (
        "contractName",
        "responseSha256",
        "nonceSha256",
        "revocationEpochSha256",
        "cacheControl",
    ):
        if key in proof:
            pattern = (
                LOWER_SHA256
                if key
                in {
                    "responseSha256",
                    "nonceSha256",
                    "revocationEpochSha256",
                }
                else None
            )
            _require_receipt_string(proof[key], pattern=pattern)
    edge_waf = receipt["edgeWafLocalEvidence"]
    if (
        not isinstance(edge_waf, dict)
        or set(edge_waf)
        != {
            "evidenceScope",
            "mutationAuthorized",
            "mutationPerformed",
            "stableThroughPostVerification",
            "sha256Before",
            "sha256After",
            "liveControlPlaneVerified",
        }
        or edge_waf["evidenceScope"] != "pinned_local_evidence_only"
        or edge_waf["mutationAuthorized"] is not False
        or edge_waf["mutationPerformed"] is not False
        or type(edge_waf["stableThroughPostVerification"]) is not bool
        or edge_waf["liveControlPlaneVerified"] is not False
    ):
        raise RotationError("receipt_types_invalid")
    _require_receipt_string(
        edge_waf["sha256Before"],
        pattern=LOWER_SHA256,
    )
    _require_receipt_string(
        edge_waf["sha256After"],
        pattern=LOWER_SHA256,
        allow_empty=True,
    )
    containment = receipt["failureContainment"]
    if (
        not isinstance(containment, dict)
        or set(containment)
        != {
            "portalQuiescenceProven",
            "publicConnectorsStopped",
        }
        or type(containment["portalQuiescenceProven"]) is not bool
        or type(containment["publicConnectorsStopped"]) is not bool
    ):
        raise RotationError("receipt_types_invalid")


def _validate_resume_receipt(
    receipt: dict[str, Any],
    request: RotationRequest,
    *,
    incident_ticket_commitment: str,
) -> None:
    validate_rotation_receipt_types(receipt)
    expected = {
        "contractName": CONTRACT_NAME,
        "sourceHead": request.expected_source_head,
        "imageTag": request.image_tag,
        "imageId": request.expected_image_id,
        "proofBindSourceSha256": request.expected_proof_sha256,
        "epochAuthorityPath": str(request.epoch_authority_output),
        "epochHistoryPath": str(request.epoch_history_path),
        "epochHistoryBootstrapAuthoritySha256": (
            request.expected_epoch_history_bootstrap_authority_sha256
        ),
        "rotationIntentSha256": rotation_intent_sha256(
            request,
            incident_ticket_commitment=incident_ticket_commitment,
        ),
        "portalReplicaCount": request.expected_portal_replicas,
        "newEpochSha256": sha256_text(request.new_epoch),
        "environmentSha256Before": request.expected_env_sha256_before,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise RotationError("resume_receipt_authority_mismatch")
    edge_waf = receipt.get("edgeWafLocalEvidence")
    if (
        not isinstance(edge_waf, dict)
        or edge_waf.get("sha256Before")
        != request.expected_edge_waf_local_evidence_sha256
        or edge_waf.get("evidenceScope")
        != "pinned_local_evidence_only"
        or edge_waf.get("liveControlPlaneVerified") is not False
    ):
        raise RotationError("resume_waf_authority_mismatch")
    proof = receipt.get("oldTicketRevocationProof")
    if (
        not isinstance(proof, dict)
        or proof.get("supplied") is not True
    ):
        raise RotationError("resume_ticket_proof_authority_mismatch")


def observe_epoch_boundary(request: RotationRequest) -> tuple[int, str]:
    try:
        environment = read_owner_only_file(
            request.env_file,
            label="environment",
            maximum_bytes=MAX_ENV_BYTES,
        )
        parse_epoch_environment(environment)
    except Exception:
        # An unreadable environment makes the commit boundary uncertain.
        return 76, ""
    environment_sha256 = sha256_bytes(environment)
    if environment_sha256 == request.expected_env_sha256_before:
        return 75, environment_sha256
    return 76, environment_sha256


def fail_closed_contain_precommit_portals(
    runtime: RuntimeAuthority,
    *,
    durable_prior_ids: tuple[str, ...],
) -> dict[str, bool]:
    durable_prior_ids_valid = not (
        not durable_prior_ids
        or len(set(durable_prior_ids)) != len(durable_prior_ids)
        or any(
            CONTAINER_ID.fullmatch(identity) is None
            for identity in durable_prior_ids
        )
    )
    relevant_identities = set(durable_prior_ids)
    last_error: Exception | None = None
    for _attempt in range(3):
        if not durable_prior_ids_valid:
            last_error = RotationError(
                "precommit_durable_portal_identities_invalid"
            )
            break
        try:
            project_identities = runtime.portal_container_ids()
            independent_identities = (
                runtime.independently_enumerated_portal_container_ids()
            )
            observed_identities = (
                *project_identities,
                *independent_identities,
            )
            if any(
                CONTAINER_ID.fullmatch(identity) is None
                for identity in observed_identities
            ):
                raise RotationError(
                    "portal_requiescence_identity_invalid"
                )
            relevant_identities.update(observed_identities)
            ordered_identities = tuple(sorted(relevant_identities))
            runtime.quiesce_known_portals(ordered_identities)
            runtime.assert_known_portals_stopped(ordered_identities)

            project_after = runtime.portal_container_ids()
            independent_after = (
                runtime.independently_enumerated_portal_container_ids()
            )
            after_identities = set((*project_after, *independent_after))
            if any(
                CONTAINER_ID.fullmatch(identity) is None
                for identity in after_identities
            ):
                raise RotationError(
                    "portal_requiescence_identity_invalid"
                )
            newly_observed = after_identities - relevant_identities
            if newly_observed:
                relevant_identities.update(newly_observed)
                continue
            runtime.assert_known_portals_stopped(
                tuple(sorted(relevant_identities))
            )
            return {
                "portalQuiescenceProven": True,
                "publicConnectorsStopped": False,
            }
        except Exception as exc:
            last_error = exc
    try:
        runtime.quiesce_public_connectors()
        runtime.assert_public_connectors_stopped()
        return {
            "portalQuiescenceProven": False,
            "publicConnectorsStopped": True,
        }
    except Exception as exc:
        cause = last_error or exc
        raise RotationError(
            "precommit_emergency_containment_not_proven"
        ) from cause


def run_rotation(
    request: RotationRequest,
    runtime: RuntimeAuthority,
) -> tuple[int, dict[str, Any]]:
    _validate_request(request)
    require_owner_only_directory(request.output.parent, label="receipt_root")
    verify_proof_bind_source(request)
    env_payload = read_owner_only_file(
        request.env_file,
        label="environment",
        maximum_bytes=MAX_ENV_BYTES,
    )
    current_epoch, _ = parse_epoch_environment(env_payload)
    current_env_sha256 = sha256_bytes(env_payload)
    new_epoch_sha256 = sha256_text(request.new_epoch)
    ticket, _ticket_sha256 = load_ticket(
        request.old_ticket_path,
        request.old_ticket_authority,
    )
    incident_ticket_commitment = incident_ticket_commitment_sha256(
        request,
        ticket,
    )
    (
        _bootstrap_authority,
        bootstrap_authority_sha256,
        known_legacy_epoch_sha256,
    ) = load_epoch_history_bootstrap_authority(
        request.epoch_history_bootstrap_authority,
        expected_sha256=(
            request.expected_epoch_history_bootstrap_authority_sha256
        ),
    )
    edge_waf_local_evidence_sha256 = (
        verify_edge_waf_local_evidence_source(request)
    )

    existing_receipt = request.output.exists() or request.output.is_symlink()
    if existing_receipt:
        receipt, receipt_sha256 = strict_receipt(request.output)
        if not request.expected_existing_receipt_sha256:
            raise RotationError("existing_receipt_sha256_required")
        if receipt_sha256 != request.expected_existing_receipt_sha256:
            raise RotationError("existing_receipt_sha256_mismatch")
        _validate_resume_receipt(
            receipt,
            request,
            incident_ticket_commitment=incident_ticket_commitment,
        )
    else:
        if request.expected_existing_receipt_sha256:
            raise RotationError("expected_existing_receipt_missing")
        receipt = _base_receipt(
            request,
            incident_ticket_commitment=incident_ticket_commitment,
        )

    committed = current_epoch == request.new_epoch
    if committed and not existing_receipt:
        raise RotationError("new_epoch_does_not_change_authority")
    if not committed and current_env_sha256 != request.expected_env_sha256_before:
        raise RotationError("environment_drift_before_epoch_commit")
    if committed:
        prior_committed_sha256 = str(
            receipt.get("environmentSha256After") or ""
        )
        if (
            prior_committed_sha256
            and prior_committed_sha256 != current_env_sha256
        ):
            raise RotationError("committed_environment_drift")
        receipt["environmentSha256After"] = current_env_sha256
        receipt["phase"] = "epoch_committed"

    prior_ids_for_recovery: tuple[str, ...] = tuple()
    old_epoch_sha256_for_recovery = str(
        receipt.get("oldEpochSha256") or ""
    )
    prior_receipt_portals = receipt.get("preRotationPortals")
    if (
        existing_receipt
        and isinstance(prior_receipt_portals, list)
        and prior_receipt_portals
    ):
        prior_ids_for_recovery = tuple(
            str(item.get("containerId") or "")
            for item in prior_receipt_portals
            if isinstance(item, dict)
        )
    try:
        with overlay.public_edge_mutation_lock(
            activate=True,
            inherited_token=request.shared_mutation_lock_token,
        ):
            if (
                verify_edge_waf_local_evidence_source(request)
                != edge_waf_local_evidence_sha256
            ):
                raise RotationError(
                    "edge_waf_local_evidence_drift"
                )
            if runtime.resolve_image_id(request.image_tag) != request.expected_image_id:
                raise RotationError("pinned_image_tag_drift")

            held_ticket_authority = revalidate_old_ticket_authority(
                request.old_ticket_authority
            )
            held_ticket, _held_ticket_sha256 = load_ticket(
                request.old_ticket_path,
                held_ticket_authority,
            )
            if not hmac.compare_digest(
                incident_ticket_commitment_sha256(
                    request,
                    held_ticket,
                ),
                incident_ticket_commitment,
            ):
                raise RotationError(
                    "incident_ticket_commitment_changed"
                )
            ticket = held_ticket
            (
                _held_bootstrap_authority,
                held_bootstrap_authority_sha256,
                held_known_legacy_epoch_sha256,
            ) = load_epoch_history_bootstrap_authority(
                request.epoch_history_bootstrap_authority,
                expected_sha256=(
                    request.expected_epoch_history_bootstrap_authority_sha256
                ),
            )
            if (
                held_bootstrap_authority_sha256
                != bootstrap_authority_sha256
                or held_known_legacy_epoch_sha256
                != known_legacy_epoch_sha256
            ):
                raise RotationError(
                    "epoch_history_bootstrap_authority_changed"
                )
            bootstrap_marker, bootstrap_marker_sha256 = (
                load_epoch_history_bootstrap_marker(
                    request.epoch_history_bootstrap_marker,
                    expected_sha256=(
                        request
                        .expected_epoch_history_bootstrap_marker_sha256
                    ),
                    expected_bootstrap_authority_sha256=(
                        bootstrap_authority_sha256
                    ),
                )
            )
            history, history_sha256 = load_epoch_history(
                request.epoch_history_path,
                expected_sha256=request.expected_epoch_history_sha256,
            )
            intent_sha256 = rotation_intent_sha256(
                request,
                incident_ticket_commitment=incident_ticket_commitment,
            )
            if history is None:
                prior_epoch_authority_exists = os.path.lexists(
                    request.epoch_authority_output
                )
                if bootstrap_marker is None:
                    if prior_epoch_authority_exists:
                        raise RotationError(
                            "epoch_history_missing_with_prior_authority"
                        )
                elif (
                    not existing_receipt
                    or bootstrap_marker.get(
                        "initialRotationIntentSha256"
                    )
                    != intent_sha256
                    or bootstrap_marker.get(
                        "epochHistoryPathSha256"
                    )
                    != sha256_text(str(request.epoch_history_path))
                ):
                    raise RotationError(
                        "epoch_history_missing_after_bootstrap"
                    )
            elif bootstrap_marker is None:
                raise RotationError(
                    "epoch_history_bootstrap_marker_missing"
                )
            else:
                marker_legacy = tuple(
                    bootstrap_marker["knownLegacyEpochSha256"]
                )
                history_legacy = tuple(
                    event["epochSha256"]
                    for event in history["events"]
                    if event["eventType"] == "legacy_observed"
                )
                if (
                    marker_legacy != known_legacy_epoch_sha256
                    or history_legacy != known_legacy_epoch_sha256
                ):
                    raise RotationError(
                        "epoch_history_bootstrap_legacy_authority_drift"
                    )
            history_after_reservation, reservation_required = (
                reserve_epoch_history(
                    history,
                    current_epoch_sha256=sha256_text(current_epoch),
                    new_epoch_sha256=new_epoch_sha256,
                    intent_sha256=intent_sha256,
                    known_legacy_epoch_sha256=(
                        known_legacy_epoch_sha256
                    ),
                    request=request,
                )
            )
            matching_history_events = [
                event
                for event in history_after_reservation["events"]
                if event["epochSha256"] == new_epoch_sha256
                and event["rotationIntentSha256"] == intent_sha256
            ]
            if committed and reservation_required:
                raise RotationError(
                    "epoch_history_committed_epoch_untracked"
                )
            if not committed and any(
                event["eventType"] == "rotation_committed"
                for event in matching_history_events
            ):
                raise RotationError(
                    "epoch_history_commit_environment_mismatch"
                )
            if not receipt.get("epochHistorySha256Before"):
                receipt["epochHistorySha256Before"] = history_sha256

            if not committed:
                old_epoch_sha256 = sha256_text(current_epoch)
                old_epoch_sha256_for_recovery = old_epoch_sha256
                if old_epoch_sha256 == new_epoch_sha256:
                    raise RotationError("new_epoch_does_not_change_authority")
                prior_portal_payload = receipt.get("preRotationPortals")
                if (
                    existing_receipt
                    and isinstance(prior_portal_payload, list)
                    and prior_portal_payload
                ):
                    prior_ids_for_recovery = tuple(
                        str(item.get("containerId") or "")
                        for item in prior_portal_payload
                        if isinstance(item, dict)
                    )
                    if len(prior_ids_for_recovery) != (
                        request.expected_portal_replicas
                    ):
                        raise RotationError(
                            "precommit_resume_portal_evidence_invalid"
                        )
                    runtime.restart_portals(prior_ids_for_recovery)
                portals_before = inspect_exact_portals(
                    runtime,
                    expected_count=request.expected_portal_replicas,
                    expected_image_id=request.expected_image_id,
                    expected_epoch_sha256=old_epoch_sha256,
                    expected_proof_sha256=request.expected_proof_sha256,
                )
                prior_ids_for_recovery = tuple(
                    item.container_id for item in portals_before
                )
                tunnels_before = validate_tunnels(runtime.tunnel_evidence())
                storage_before = capture_storage_authority(
                    runtime,
                    portals_before[0],
                )
                authority_before, authority_before_sha256 = (
                    read_active_runtime_authority(
                        request.active_runtime_authority
                    )
                )
                authority_portal = authority_before["portal"]
                if (
                    authority_portal.get("containerId")
                    != portals_before[0].container_id
                    or authority_portal.get("containerName")
                    != portals_before[0].container_name
                    or authority_portal.get("imageId")
                    != portals_before[0].image_id
                    or authority_portal.get("wasRunning") is not True
                    or authority_portal.get("proofAuthorityMountSha256")
                    != request.expected_proof_sha256
                    or authority_portal.get("proofPublicMountSha256")
                    != request.expected_proof_sha256
                ):
                    raise RotationError(
                        "active_runtime_authority_portal_mismatch"
                    )
                receipt.update(
                    {
                        "status": "in_progress",
                        "phase": "old_epoch_verified",
                        "updatedAtUtc": now_iso(),
                        "oldEpochSha256": old_epoch_sha256,
                        "preRotationPortals": [
                            portal_payload(item) for item in portals_before
                        ],
                        "canonicalTunnelsBefore": [
                            tunnel_payload(item) for item in tunnels_before
                        ],
                        "storageAuthorityBefore": storage_before,
                        "activeRuntimeAuthoritySha256Before": (
                            authority_before_sha256
                        ),
                        "activeRuntimeAuthorityStaticSha256": (
                            active_runtime_static_sha256(authority_before)
                        ),
                        "loopbackChecksBefore": verify_health(
                            runtime,
                            portals_before,
                        ),
                        "publicGetChecksBefore": verify_public_gets(runtime),
                        "edgeWafLocalEvidence": {
                            "evidenceScope": (
                                "pinned_local_evidence_only"
                            ),
                            "mutationAuthorized": False,
                            "mutationPerformed": False,
                            "stableThroughPostVerification": False,
                            "sha256Before": (
                                edge_waf_local_evidence_sha256
                            ),
                            "sha256After": "",
                            "liveControlPlaneVerified": False,
                        },
                    }
                )
                atomic_write_private_json(request.output, receipt)
                if bootstrap_marker is None:
                    bootstrap_marker_sha256 = (
                        publish_epoch_history_bootstrap_marker(
                            request,
                            bootstrap_authority_sha256=(
                                bootstrap_authority_sha256
                            ),
                            known_legacy_epoch_sha256=(
                                known_legacy_epoch_sha256
                            ),
                            intent_sha256=intent_sha256,
                        )
                    )
                    bootstrap_marker, verified_marker_sha256 = (
                        load_epoch_history_bootstrap_marker(
                            request.epoch_history_bootstrap_marker,
                            expected_sha256=bootstrap_marker_sha256,
                            expected_bootstrap_authority_sha256=(
                                bootstrap_authority_sha256
                            ),
                        )
                    )
                    assert bootstrap_marker is not None
                    assert (
                        verified_marker_sha256
                        == bootstrap_marker_sha256
                    )
                receipt[
                    "epochHistoryBootstrapMarkerSha256"
                ] = bootstrap_marker_sha256
                atomic_write_private_json(request.output, receipt)
                runtime.quiesce_portals(prior_ids_for_recovery)
                runtime.assert_portals_stopped(prior_ids_for_recovery)
                receipt.update(
                    {
                        "phase": "old_epoch_portals_quiesced",
                        "updatedAtUtc": now_iso(),
                    }
                )
                atomic_write_private_json(request.output, receipt)

                if reservation_required:
                    history_sha256 = publish_epoch_history(
                        request.epoch_history_path,
                        history_after_reservation,
                        expected_current_sha256=history_sha256,
                    )
                receipt.update(
                    {
                        "phase": "epoch_reserved",
                        "updatedAtUtc": now_iso(),
                        "epochHistorySha256AfterReservation": (
                            history_sha256
                        ),
                        "epochHistoryHeadEventSha256": (
                            history_after_reservation[
                                "headEventSha256"
                            ]
                        ),
                    }
                )
                atomic_write_private_json(request.output, receipt)
                load_epoch_history(
                    request.epoch_history_path,
                    expected_sha256=history_sha256,
                )
                runtime.assert_portals_stopped(prior_ids_for_recovery)
                before_sha256, after_sha256 = replace_epoch_environment(
                    path=request.env_file,
                    prior_payload=env_payload,
                    new_epoch=request.new_epoch,
                )
                committed = True
                receipt.update(
                    {
                        "phase": "epoch_committed",
                        "updatedAtUtc": now_iso(),
                        "environmentSha256Before": before_sha256,
                        "environmentSha256After": after_sha256,
                    }
                )
                atomic_write_private_json(request.output, receipt)
            else:
                portals_before_payload = receipt.get("preRotationPortals")
                tunnels_before_payload = receipt.get("canonicalTunnelsBefore")
                storage_before_payload = receipt.get("storageAuthorityBefore")
                if (
                    not isinstance(portals_before_payload, list)
                    or len(portals_before_payload) != request.expected_portal_replicas
                    or not isinstance(tunnels_before_payload, list)
                    or len(tunnels_before_payload)
                    != len(CANONICAL_TUNNEL_SERVICES)
                    or not isinstance(storage_before_payload, dict)
                    or not storage_before_payload
                    or LOWER_SHA256.fullmatch(
                        str(receipt.get("oldEpochSha256") or "")
                    )
                    is None
                    or LOWER_SHA256.fullmatch(
                        str(
                            receipt.get(
                                "activeRuntimeAuthorityStaticSha256"
                            )
                            or ""
                        )
                    )
                    is None
                ):
                    raise RotationError("committed_resume_evidence_incomplete")
                prior_ids_for_recovery = tuple(
                    str(item["containerId"])
                    for item in portals_before_payload
                )
                authority_before, authority_before_sha256 = (
                    read_active_runtime_authority(
                        request.active_runtime_authority
                    )
                )
                if (
                    active_runtime_static_sha256(authority_before)
                    != receipt["activeRuntimeAuthorityStaticSha256"]
                ):
                    raise RotationError(
                        "active_runtime_authority_static_contract_drift"
                    )
                current_ids = runtime.portal_container_ids()
                if current_ids:
                    runtime.quiesce_portals(current_ids)
                    runtime.assert_portals_stopped(current_ids)
                receipt.update(
                    {
                        "phase": "committed_portals_quiesced",
                        "updatedAtUtc": now_iso(),
                    }
                )
                atomic_write_private_json(request.output, receipt)
                if not receipt.get(
                    "epochHistorySha256AfterReservation"
                ):
                    receipt[
                        "epochHistorySha256AfterReservation"
                    ] = history_sha256
                if (
                    receipt.get(
                        "epochHistoryBootstrapMarkerSha256"
                    )
                    != bootstrap_marker_sha256
                ):
                    raise RotationError(
                        "epoch_history_bootstrap_marker_receipt_drift"
                    )

            history_after_commit, history_commit_required = (
                commit_epoch_history(
                    history_after_reservation,
                    new_epoch_sha256=new_epoch_sha256,
                    intent_sha256=intent_sha256,
                    request=request,
                )
            )
            if history_commit_required:
                history_sha256 = publish_epoch_history(
                    request.epoch_history_path,
                    history_after_commit,
                    expected_current_sha256=history_sha256,
                )
            history_head_event_sha256 = history_after_commit[
                "headEventSha256"
            ]
            receipt.update(
                {
                    "phase": "epoch_history_committed",
                    "updatedAtUtc": now_iso(),
                    "epochHistorySha256AfterCommit": history_sha256,
                    "epochHistoryHeadEventSha256": (
                        history_head_event_sha256
                    ),
                }
            )
            atomic_write_private_json(request.output, receipt)

            committed_env_sha256 = str(receipt["environmentSha256After"])
            if LOWER_SHA256.fullmatch(committed_env_sha256) is None:
                raise RotationError("committed_environment_evidence_invalid")
            verify_committed_environment(
                request,
                expected_sha256=committed_env_sha256,
            )
            prior_portal_payload = receipt["preRotationPortals"]
            prior_ids = tuple(str(item["containerId"]) for item in prior_portal_payload)
            prior_names = tuple(
                str(item["containerName"]) for item in prior_portal_payload
            )
            current_ids = runtime.portal_container_ids()
            if current_ids:
                runtime.assert_portals_stopped(current_ids)
            runtime.recreate_all_portals(
                prior_container_ids=current_ids,
                container_names=prior_names,
            )
            recreated = True

            verify_committed_environment(
                request,
                expected_sha256=committed_env_sha256,
            )
            portals_after = inspect_exact_portals(
                runtime,
                expected_count=request.expected_portal_replicas,
                expected_image_id=request.expected_image_id,
                expected_epoch_sha256=new_epoch_sha256,
                expected_proof_sha256=request.expected_proof_sha256,
            )
            if tuple(item.container_name for item in portals_after) != prior_names:
                raise RotationError("post_rotation_portal_names_drifted")
            prior_binary = {
                str(item["binarySha256"]) for item in receipt["preRotationPortals"]
            }
            if {item.binary_sha256 for item in portals_after} != prior_binary:
                raise RotationError("post_rotation_binary_drift")
            prior_runtime_contracts = {
                str(item["runtimeContractSha256"])
                for item in receipt["preRotationPortals"]
            }
            if {
                item.runtime_contract_sha256 for item in portals_after
            } != prior_runtime_contracts:
                raise RotationError("post_rotation_runtime_contract_drift")
            if (
                active_runtime_static_sha256(authority_before)
                != receipt["activeRuntimeAuthorityStaticSha256"]
            ):
                raise RotationError(
                    "active_runtime_authority_static_contract_drift"
                )
            recorded_authority_digests = {
                str(receipt["activeRuntimeAuthoritySha256Before"])
            }
            recorded_after_digest = str(
                receipt.get("activeRuntimeAuthoritySha256After") or ""
            )
            if LOWER_SHA256.fullmatch(recorded_after_digest) is not None:
                recorded_authority_digests.add(recorded_after_digest)
            authority_portal = authority_before["portal"]
            if (
                authority_before_sha256 not in recorded_authority_digests
                and not any(
                    active_runtime_portal_matches(
                        authority_portal,
                        item,
                    )
                    for item in portals_after
                )
            ):
                raise RotationError(
                    "active_runtime_authority_resume_digest_unbound"
                )
            storage_after = capture_storage_authority(
                runtime,
                portals_after[0],
            )
            if storage_after != receipt["storageAuthorityBefore"]:
                raise RotationError("durable_storage_authority_drift")
            tunnels_after = validate_tunnels(runtime.tunnel_evidence())
            if runtime.resolve_image_id(request.image_tag) != request.expected_image_id:
                raise RotationError("pinned_image_tag_drift_after_recreate")
            expected_tunnels = tuple(
                (
                    str(item["service"]),
                    str(item["containerId"]),
                    str(item["imageId"]),
                    item["running"],
                    str(item["health"]),
                )
                for item in receipt["canonicalTunnelsBefore"]
            )
            actual_tunnels = tuple(
                (
                    item.service,
                    item.container_id,
                    item.image_id,
                    item.running,
                    item.health,
                )
                for item in tunnels_after
            )
            if actual_tunnels != expected_tunnels:
                raise RotationError("canonical_tunnels_changed_during_rotation")

            loopback_after = verify_health(runtime, portals_after)
            public_after = verify_public_gets(runtime)
            authority_after_sha256 = publish_active_runtime_authority(
                request.active_runtime_authority,
                prior_authority=authority_before,
                portal=portals_after[0],
            )
            receipt.update(
                {
                    "status": "in_progress",
                    "phase": "post_rotation_runtime_verified",
                    "updatedAtUtc": now_iso(),
                    "postRotationPortals": [
                        portal_payload(item) for item in portals_after
                    ],
                    "canonicalTunnelsAfter": [
                        tunnel_payload(item) for item in tunnels_after
                    ],
                    "storageAuthorityAfter": storage_after,
                    "loopbackChecksAfter": loopback_after,
                    "publicGetChecksAfter": public_after,
                    "activeRuntimeAuthoritySha256After": (
                        authority_after_sha256
                    ),
                    "recreated": recreated,
                }
            )
            atomic_write_private_json(request.output, receipt)
            final_waf_local_evidence_sha256 = (
                verify_edge_waf_local_evidence_source(request)
            )
            if (
                final_waf_local_evidence_sha256
                != edge_waf_local_evidence_sha256
            ):
                raise RotationError(
                    "edge_waf_local_evidence_drift"
                )
            receipt["edgeWafLocalEvidence"] = {
                "evidenceScope": "pinned_local_evidence_only",
                "mutationAuthorized": False,
                "mutationPerformed": False,
                "stableThroughPostVerification": True,
                "sha256Before": (
                    edge_waf_local_evidence_sha256
                ),
                "sha256After": (
                    final_waf_local_evidence_sha256
                ),
                "liveControlPlaneVerified": False,
            }
            atomic_write_private_json(request.output, receipt)
            proof_ticket_authority = revalidate_old_ticket_authority(
                request.old_ticket_authority
            )
            proof_ticket, _proof_ticket_sha256 = load_ticket(
                request.old_ticket_path,
                proof_ticket_authority,
            )
            if not hmac.compare_digest(
                incident_ticket_commitment_sha256(
                    request,
                    proof_ticket,
                ),
                incident_ticket_commitment,
            ):
                raise RotationError(
                    "incident_ticket_commitment_changed"
                )
            ticket = proof_ticket
            old_ticket_proof = dict(receipt["oldTicketRevocationProof"])
            old_ticket_proof = verify_old_ticket_revocation(
                runtime,
                ticket=ticket,
                expected_epoch_sha256=new_epoch_sha256,
            )
            verify_proof_bind_source(request)
            verify_committed_environment(
                request,
                expected_sha256=committed_env_sha256,
            )
            final_history, verified_history_sha256 = load_epoch_history(
                request.epoch_history_path,
                expected_sha256=history_sha256,
            )
            assert final_history is not None
            if (
                verified_history_sha256
                != receipt["epochHistorySha256AfterCommit"]
                or final_history["headEventSha256"]
                != history_head_event_sha256
            ):
                raise RotationError("epoch_history_final_drift")
            _final_bootstrap_marker, verified_marker_sha256 = (
                load_epoch_history_bootstrap_marker(
                    request.epoch_history_bootstrap_marker,
                    expected_sha256=bootstrap_marker_sha256,
                    expected_bootstrap_authority_sha256=(
                        bootstrap_authority_sha256
                    ),
                )
            )
            if (
                verified_marker_sha256
                != receipt["epochHistoryBootstrapMarkerSha256"]
            ):
                raise RotationError(
                    "epoch_history_bootstrap_marker_final_drift"
                )
            receipt.update(
                {
                    "status": "pass",
                    "phase": "post_rotation_verified",
                    "updatedAtUtc": now_iso(),
                    "oldTicketRevocationProof": old_ticket_proof,
                    "edgeWafLocalEvidence": {
                        "evidenceScope": (
                            "pinned_local_evidence_only"
                        ),
                        "mutationAuthorized": False,
                        "mutationPerformed": False,
                        "stableThroughPostVerification": True,
                        "sha256Before": (
                            edge_waf_local_evidence_sha256
                        ),
                        "sha256After": (
                            final_waf_local_evidence_sha256
                        ),
                        "liveControlPlaneVerified": False,
                    },
                    "failureCode": "",
                }
            )
            rotation_receipt_sha256 = atomic_write_private_json(
                request.output,
                receipt,
            )
            publish_epoch_authority(
                request,
                incident_ticket_commitment=incident_ticket_commitment,
                rotation_receipt_sha256=rotation_receipt_sha256,
                active_runtime_authority_sha256=authority_after_sha256,
                portal=portals_after[0],
                storage_authority=storage_after,
                environment_sha256_after=committed_env_sha256,
                epoch_history_sha256=verified_history_sha256,
                epoch_history_head_event_sha256=(
                    history_head_event_sha256
                ),
                epoch_history_bootstrap_marker_sha256=(
                    verified_marker_sha256
                ),
                edge_waf_local_evidence_sha256=(
                    final_waf_local_evidence_sha256
                ),
            )
            return 0, receipt
    except Exception as exc:
        code = exc.code if isinstance(exc, RotationError) else "unexpected_failure"
        failure_status, observed_environment_sha256 = observe_epoch_boundary(
            request
        )
        precommit_recovery_required = (
            not committed and bool(prior_ids_for_recovery)
        )
        restored_old_portal = False
        precommit_portal_quiescence_proven = False
        if precommit_recovery_required and failure_status == 75:
            try:
                runtime.restart_portals(prior_ids_for_recovery)
                inspect_exact_portals(
                    runtime,
                    expected_count=request.expected_portal_replicas,
                    expected_image_id=request.expected_image_id,
                    expected_epoch_sha256=old_epoch_sha256_for_recovery,
                    expected_proof_sha256=request.expected_proof_sha256,
                )
                restored_old_portal = True
            except Exception:
                code = "precommit_portal_restart_failed"
        if precommit_recovery_required and not restored_old_portal:
            failure_status = 76
            try:
                receipt["failureContainment"] = (
                    fail_closed_contain_precommit_portals(
                        runtime,
                        durable_prior_ids=prior_ids_for_recovery,
                    )
                )
                precommit_portal_quiescence_proven = (
                    receipt["failureContainment"].get(
                        "portalQuiescenceProven"
                    )
                    is True
                )
                if not precommit_portal_quiescence_proven:
                    failure_status = 70
                    code = (
                        "precommit_portal_quiescence_unproven_"
                        "connectors_stopped"
                    )
            except Exception:
                failure_status = 70
                code = (
                    "precommit_emergency_containment_not_proven"
                )
        if (
            not committed
            and failure_status == 76
            and not precommit_portal_quiescence_proven
        ):
            try:
                receipt["failureContainment"] = (
                    fail_closed_contain_precommit_portals(
                        runtime,
                        durable_prior_ids=prior_ids_for_recovery,
                    )
                )
                precommit_portal_quiescence_proven = (
                    receipt["failureContainment"].get(
                        "portalQuiescenceProven"
                    )
                    is True
                )
                if not precommit_portal_quiescence_proven:
                    failure_status = 70
                    code = (
                        "precommit_portal_quiescence_unproven_"
                        "connectors_stopped"
                    )
            except Exception:
                failure_status = 70
                code = (
                    "precommit_emergency_containment_not_proven"
                )
        fail_forward_required = failure_status == 76
        if fail_forward_required and observed_environment_sha256:
            receipt["environmentSha256After"] = observed_environment_sha256
        recorded_waf = receipt.get("edgeWafLocalEvidence")
        waf_local_evidence_stable = (
            isinstance(recorded_waf, dict)
            and recorded_waf.get("sha256Before")
            == edge_waf_local_evidence_sha256
            and recorded_waf.get("sha256After")
            == edge_waf_local_evidence_sha256
            and recorded_waf.get("stableThroughPostVerification")
            is True
            and recorded_waf.get("liveControlPlaneVerified") is False
        )
        failure_containment = receipt.get("failureContainment")
        connectors_stopped_containment = (
            isinstance(failure_containment, dict)
            and failure_containment.get("portalQuiescenceProven") is False
            and failure_containment.get("publicConnectorsStopped") is True
        )
        prior_phase = str(receipt.get("phase") or "")
        if fail_forward_required:
            failure_phase = (
                "epoch_commit_outcome_uncertain"
                if prior_phase
                in {
                    "",
                    "initializing",
                    "old_epoch_verified",
                    "old_epoch_portals_quiesced",
                    "epoch_reserved",
                }
                else prior_phase
            )
        elif failure_status == 75:
            failure_phase = "precommit_failed"
        elif connectors_stopped_containment:
            failure_phase = "precommit_public_connectors_stopped"
        else:
            failure_phase = "precommit_emergency_containment_unproven"
        receipt.update(
            {
                "status": (
                    "fail_forward_required"
                    if fail_forward_required
                    else (
                        "failed_before_epoch_commit"
                        if failure_status == 75
                        else (
                            "emergency_public_connectors_stopped"
                            if connectors_stopped_containment
                            else "emergency_containment_unproven"
                        )
                    )
                ),
                "phase": failure_phase,
                "updatedAtUtc": now_iso(),
                "failureCode": code,
                "edgeWafLocalEvidence": {
                    "evidenceScope": "pinned_local_evidence_only",
                    "mutationAuthorized": False,
                    "mutationPerformed": False,
                    "stableThroughPostVerification": (
                        waf_local_evidence_stable
                    ),
                    "sha256Before": (
                        edge_waf_local_evidence_sha256
                    ),
                    "sha256After": (
                        edge_waf_local_evidence_sha256
                        if waf_local_evidence_stable
                        else ""
                    ),
                    "liveControlPlaneVerified": False,
                },
            }
        )
        atomic_write_private_json(request.output, receipt)
        if ticket:
            del ticket
        return failure_status, receipt


class DockerRuntime:
    def __init__(
        self,
        *,
        docker_config_root: Path,
        docker_context: str,
        compose_file: Path,
        env_file: Path,
        project_name: str,
        source_root: Path,
        build_context: Path,
        overlay_root: Path,
        projection_root: Path,
        proof_bind_source: Path,
        published_port: int,
        base_url: str,
    ) -> None:
        canonical_constructor_paths = (
            docker_config_root,
            compose_file,
            env_file,
            source_root,
            build_context,
            overlay_root,
            projection_root,
            proof_bind_source,
        )
        if any(
            not path.is_absolute()
            or overlay.normalized_absolute_path(path) != path
            for path in canonical_constructor_paths
        ):
            raise RotationError("runtime_path_alias_not_canonical")
        if project_name != CANONICAL_PROJECT_NAME:
            raise RotationError("compose_project_not_canonical")
        if docker_context != "default":
            raise RotationError("docker_context_not_canonical")
        self.environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(docker_config_root / "home"),
            "DOCKER_CONFIG": str(docker_config_root / "config"),
            "LANG": "C",
            "LC_ALL": "C",
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(build_context),
            "CHUMMER_RUN_SERVICES_CONTEXT_DIR": str(source_root),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source_root),
            "CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR": str(overlay_root),
            "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": str(projection_root),
            "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": str(
                proof_bind_source
            ),
            "CHUMMER_PUBLIC_EDGE_PORT": str(published_port),
            "ASPNETCORE_ENVIRONMENT": "Production",
            "CHUMMER_PUBLIC_ALLOWED_HOSTS": "chummer.run",
            "CHUMMER_PUBLIC_CANONICAL_ORIGIN": "https://chummer.run",
            "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
            "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
        }
        self.docker_base = [
            "/usr/bin/timeout",
            "--kill-after=5s",
            "60s",
            "/usr/bin/docker",
            "--context",
            docker_context,
        ]
        self.compose_base = [
            *self.docker_base,
            "compose",
            "--env-file",
            str(env_file),
            "-p",
            project_name,
            "-f",
            str(compose_file),
            "--project-directory",
            str(source_root),
        ]
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "chummer.run"
            or parsed.port is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise RotationError("base_url_not_canonical")
        self.base_host = parsed.hostname
        self.project_name = project_name

    def _run(self, command: list[str], *, timeout: int = 90) -> bytes:
        try:
            completed = subprocess.run(
                command,
                env=self.environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RotationError("runtime_command_unavailable") from exc
        if completed.returncode != 0:
            raise RotationError("runtime_command_failed")
        return completed.stdout.rstrip(b"\r\n")

    def _docker(self, *arguments: str, timeout: int = 90) -> bytes:
        return self._run([*self.docker_base, *arguments], timeout=timeout)

    def _compose(self, *arguments: str, timeout: int = 180) -> bytes:
        return self._run([*self.compose_base, *arguments], timeout=timeout)

    def resolve_image_id(self, image_tag: str) -> str:
        value = self._docker(
            "image",
            "inspect",
            image_tag,
            "--format",
            "{{.Id}}",
        ).decode("ascii", errors="strict")
        return value if IMAGE_ID.fullmatch(value) else ""

    def portal_container_ids(self) -> tuple[str, ...]:
        output = self._docker(
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={self.project_name}",
            "--filter",
            f"label=com.docker.compose.service={PORTAL_SERVICE}",
        ).decode("ascii", errors="strict")
        return tuple(line for line in output.splitlines() if line)

    def independently_enumerated_portal_container_ids(
        self,
    ) -> tuple[str, ...]:
        output = self._compose(
            "ps",
            "--all",
            "--quiet",
            PORTAL_SERVICE,
        ).decode("ascii", errors="strict")
        identities = tuple(line for line in output.splitlines() if line)
        if (
            len(set(identities)) != len(identities)
            or any(
                CONTAINER_ID.fullmatch(identity) is None
                for identity in identities
            )
        ):
            raise RotationError(
                "independent_portal_enumeration_invalid"
            )
        return identities

    def _inspect_text(self, container_id: str, template: str) -> str:
        return self._docker(
            "container",
            "inspect",
            "--format",
            template,
            container_id,
        ).decode("utf-8", errors="strict")

    def _container_env(self, container_id: str, key: str) -> str:
        return self._docker(
            "container",
            "exec",
            container_id,
            "/usr/bin/printenv",
            key,
        ).decode("utf-8", errors="strict")

    def _container_file_sha256(self, container_id: str, path: str) -> str:
        output = self._docker(
            "container",
            "exec",
            container_id,
            "/usr/bin/sha256sum",
            "--",
            path,
        ).decode("ascii", errors="strict")
        digest, separator, rendered_path = output.partition("  ")
        if (
            separator != "  "
            or rendered_path != path
            or LOWER_SHA256.fullmatch(digest) is None
        ):
            raise RotationError("portal_file_digest_invalid")
        return digest

    def _runtime_contract_sha256(self, container_id: str) -> str:
        try:
            decoded = json.loads(
                self._docker("container", "inspect", container_id).decode(
                    "utf-8",
                    errors="strict",
                )
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RotationError("portal_inspect_contract_invalid") from exc
        if (
            not isinstance(decoded, list)
            or len(decoded) != 1
            or not isinstance(decoded[0], dict)
        ):
            raise RotationError("portal_inspect_contract_invalid")
        inspected = decoded[0]
        container_name = str(inspected.get("Name") or "").removeprefix("/")
        if SAFE_CONTAINER_NAME.fullmatch(container_name) is None:
            raise RotationError("portal_container_name_invalid")
        config = inspected.get("Config")
        host = inspected.get("HostConfig")
        network_settings = inspected.get("NetworkSettings")
        mounts = inspected.get("Mounts")
        if (
            not isinstance(config, dict)
            or not isinstance(host, dict)
            or not isinstance(network_settings, dict)
            or not isinstance(mounts, list)
        ):
            raise RotationError("portal_inspect_contract_invalid")
        environment: dict[str, str] = {}
        for entry in config.get("Env") or []:
            if not isinstance(entry, str) or "=" not in entry:
                raise RotationError("portal_environment_contract_invalid")
            key, value = entry.split("=", 1)
            if not key or key in environment:
                raise RotationError("portal_environment_contract_invalid")
            environment[key] = (
                "epoch-boundary"
                if key == EPOCH_KEY
                else sha256_text(value)
            )
        labels = dict(config.get("Labels") or {})
        labels.pop("com.docker.compose.slug", None)
        normalized_mounts: list[dict[str, Any]] = []
        for mount in mounts:
            if not isinstance(mount, dict):
                raise RotationError("portal_mounts_invalid")
            normalized_mounts.append(
                {
                    key: mount.get(key)
                    for key in (
                        "Type",
                        "Name",
                        "Source",
                        "Destination",
                        "Driver",
                        "Mode",
                        "RW",
                        "Propagation",
                    )
                }
            )
        networks: dict[str, Any] = {}
        raw_networks = network_settings.get("Networks") or {}
        if not isinstance(raw_networks, dict):
            raise RotationError("portal_network_contract_invalid")
        for name, network in raw_networks.items():
            if not isinstance(name, str) or not isinstance(network, dict):
                raise RotationError("portal_network_contract_invalid")
            raw_aliases = network.get("Aliases") or []
            if (
                not isinstance(raw_aliases, list)
                or any(type(alias) is not str for alias in raw_aliases)
            ):
                raise RotationError("portal_network_aliases_invalid")
            aliases = [
                alias
                for alias in raw_aliases
                if alias not in {container_id, container_id[:12]}
            ]
            if set(aliases) != {PORTAL_SERVICE, container_name}:
                raise RotationError("portal_network_aliases_not_canonical")
            networks[name] = {
                "aliases": sorted(aliases),
                "driverOpts": network.get("DriverOpts") or {},
                "links": sorted(network.get("Links") or []),
            }
        contract = {
            "path": inspected.get("Path"),
            "args": inspected.get("Args") or [],
            "config": {
                "user": config.get("User"),
                "workingDir": config.get("WorkingDir"),
                "entrypoint": config.get("Entrypoint"),
                "cmd": config.get("Cmd"),
                "healthcheck": config.get("Healthcheck"),
                "exposedPorts": sorted((config.get("ExposedPorts") or {}).keys()),
                "labels": labels,
                "environmentValueSha256ByKey": environment,
            },
            "hostConfig": {
                key: host.get(key)
                for key in (
                    "AutoRemove",
                    "Binds",
                    "CapAdd",
                    "CapDrop",
                    "CgroupnsMode",
                    "Devices",
                    "DeviceRequests",
                    "IpcMode",
                    "NetworkMode",
                    "OomKillDisable",
                    "PidMode",
                    "PortBindings",
                    "Privileged",
                    "ReadonlyRootfs",
                    "SecurityOpt",
                    "Tmpfs",
                    "UsernsMode",
                )
            },
            "mounts": sorted(
                normalized_mounts,
                key=lambda item: str(item.get("Destination") or ""),
            ),
            "networks": networks,
            "publishedPorts": network_settings.get("Ports") or {},
        }
        encoded = json.dumps(
            contract,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256_bytes(encoded)

    def inspect_portal(self, container_id: str) -> PortalEvidence:
        canonical_id = self._inspect_text(container_id, "{{.Id}}")
        name = self._inspect_text(container_id, "{{.Name}}").removeprefix("/")
        image_id = self._inspect_text(container_id, "{{.Image}}")
        running = self._inspect_text(container_id, "{{.State.Running}}") == "true"
        health = self._inspect_text(
            container_id,
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
        )
        restart_policy = self._inspect_text(
            container_id,
            "{{.HostConfig.RestartPolicy.Name}}",
        )
        project = self._inspect_text(
            container_id,
            '{{index .Config.Labels "com.docker.compose.project"}}',
        )
        service = self._inspect_text(
            container_id,
            '{{index .Config.Labels "com.docker.compose.service"}}',
        )
        if (
            canonical_id != container_id
            or project != self.project_name
            or service != PORTAL_SERVICE
        ):
            raise RotationError("portal_container_authority_invalid")
        try:
            mounts = json.loads(
                self._inspect_text(container_id, "{{json .Mounts}}")
            )
        except json.JSONDecodeError as exc:
            raise RotationError("portal_mounts_invalid") from exc
        if not isinstance(mounts, list):
            raise RotationError("portal_mounts_invalid")

        def required_mount(destination: str) -> MountEvidence:
            selected = [
                item
                for item in mounts
                if isinstance(item, dict) and item.get("Destination") == destination
            ]
            if len(selected) != 1:
                raise RotationError("portal_required_mount_missing")
            item = selected[0]
            if item.get("Type") != "volume":
                raise RotationError("portal_required_mount_not_volume")
            if type(item.get("RW")) is not bool:
                raise RotationError("portal_required_mount_rw_invalid")
            return MountEvidence(
                destination=destination,
                volume_name=str(item.get("Name") or ""),
                read_write=item["RW"],
            )

        epoch = self._container_env(container_id, EPOCH_KEY)
        return PortalEvidence(
            container_id=container_id,
            container_name=name,
            image_id=image_id,
            running=running,
            health=health,
            restart_policy=restart_policy,
            epoch_sha256=sha256_text(epoch),
            binary_sha256=self._container_file_sha256(
                container_id,
                PORTAL_BINARY_PATH,
            ),
            proof_authority_sha256=self._container_file_sha256(
                container_id,
                PROOF_AUTHORITY_PATH,
            ),
            proof_public_sha256=self._container_file_sha256(
                container_id,
                PROOF_PUBLIC_PATH,
            ),
            state_volume=required_mount("/app/state"),
            upload_session_volume=required_mount(EXPECTED_SESSION_ROOT),
            upload_session_root=self._container_env(container_id, SESSION_ROOT_KEY),
            data_protection_root=self._container_env(
                container_id,
                DATA_PROTECTION_ROOT_KEY,
            ),
            direct_bundle_upload_enabled=self._container_env(
                container_id,
                DIRECT_UPLOAD_KEY,
            ),
            runtime_contract_sha256=self._runtime_contract_sha256(container_id),
        )

    def volume_evidence(self, name: str) -> VolumeEvidence:
        if name not in {EXPECTED_STATE_VOLUME, EXPECTED_SESSION_VOLUME}:
            raise RotationError("durable_volume_name_not_authorized")
        try:
            decoded = json.loads(
                self._docker("volume", "inspect", name).decode(
                    "utf-8",
                    errors="strict",
                )
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RotationError("durable_volume_inspect_invalid") from exc
        if (
            not isinstance(decoded, list)
            or len(decoded) != 1
            or not isinstance(decoded[0], dict)
        ):
            raise RotationError("durable_volume_inspect_invalid")
        item = decoded[0]
        options = item.get("Options") or {}
        labels = item.get("Labels") or {}
        if not isinstance(options, dict) or not isinstance(labels, dict):
            raise RotationError("durable_volume_inspect_invalid")

        def mapping_sha256(value: dict[str, Any]) -> str:
            return sha256_bytes(
                json.dumps(
                    value,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )

        return VolumeEvidence(
            name=str(item.get("Name") or ""),
            driver=str(item.get("Driver") or ""),
            scope=str(item.get("Scope") or ""),
            mountpoint=str(item.get("Mountpoint") or ""),
            created_at=str(item.get("CreatedAt") or ""),
            options_sha256=mapping_sha256(options),
            labels_sha256=mapping_sha256(labels),
        )

    def storage_probe(
        self,
        container_id: str,
        *,
        path: str,
        require_encrypted_keyring: bool,
    ) -> StorageProbeEvidence:
        if path not in {EXPECTED_DATA_PROTECTION_ROOT, EXPECTED_SESSION_ROOT}:
            raise RotationError("storage_probe_path_not_authorized")
        kind = "keyring" if require_encrypted_keyring else "sessions"
        script = r"""
set -eu
target=$1
kind=$2
[ -d "$target" ]
[ ! -L "$target" ]
metadata=$(stat -c '%u|%g|%a' -- "$target")
key_count=0
encrypted_count=0
if [ "$kind" = keyring ]; then
  for candidate in "$target"/key-*.xml; do
    [ -e "$candidate" ] || continue
    [ -f "$candidate" ]
    [ ! -L "$candidate" ]
    key_count=$((key_count + 1))
    if grep -q '<encryptedSecret' "$candidate" \
      && grep -q 'EncryptedXmlDecryptor' "$candidate"; then
      encrypted_count=$((encrypted_count + 1))
    fi
  done
fi
printf '%s|%s|%s|%s\n' "$target" "$metadata" "$key_count" "$encrypted_count"
"""
        rendered = self._docker(
            "container",
            "exec",
            container_id,
            "/bin/sh",
            "-ceu",
            script,
            "storage-probe",
            path,
            kind,
        ).decode("utf-8", errors="strict")
        fields = rendered.split("|")
        if len(fields) != 6:
            raise RotationError("storage_probe_output_invalid")
        rendered_path, uid, gid, mode, key_count, encrypted_count = fields
        try:
            return StorageProbeEvidence(
                path=rendered_path,
                uid=int(uid),
                gid=int(gid),
                mode=mode,
                key_file_count=int(key_count),
                encrypted_key_file_count=int(encrypted_count),
            )
        except ValueError as exc:
            raise RotationError("storage_probe_output_invalid") from exc

    def _canonical_tunnel_container_ids(
        self,
    ) -> tuple[tuple[str, str], ...]:
        results: list[tuple[str, str]] = []
        for service in CANONICAL_TUNNEL_SERVICES:
            output = self._docker(
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={self.project_name}",
                "--filter",
                f"label=com.docker.compose.service={service}",
            ).decode("ascii", errors="strict")
            identities = tuple(line for line in output.splitlines() if line)
            if len(identities) != 1:
                raise RotationError("canonical_tunnel_container_count_invalid")
            identity = identities[0]
            if CONTAINER_ID.fullmatch(identity) is None:
                raise RotationError("canonical_tunnel_container_id_invalid")
            results.append((service, identity))
        return tuple(results)

    def tunnel_evidence(self) -> tuple[TunnelEvidence, ...]:
        results: list[TunnelEvidence] = []
        for service, identity in self._canonical_tunnel_container_ids():
            results.append(
                TunnelEvidence(
                    service=service,
                    container_id=self._inspect_text(identity, "{{.Id}}"),
                    image_id=self._inspect_text(identity, "{{.Image}}"),
                    running=(
                        self._inspect_text(identity, "{{.State.Running}}") == "true"
                    ),
                    health=self._inspect_text(
                        identity,
                        "{{if .State.Health}}{{.State.Health.Status}}"
                        "{{else}}none{{end}}",
                    ),
                )
            )
        return tuple(results)

    def quiesce_public_connectors(self) -> None:
        identities = self._canonical_tunnel_container_ids()
        for _service, container_id in identities:
            running = self._inspect_text(
                container_id,
                "{{.State.Running}}",
            )
            if running == "true":
                self._docker("container", "stop", container_id, timeout=90)
            elif running != "false":
                raise RotationError(
                    "public_connector_quiescence_state_invalid"
                )
        self.assert_public_connectors_stopped()

    def assert_public_connectors_stopped(self) -> None:
        identities = self._canonical_tunnel_container_ids()
        for _service, container_id in identities:
            if (
                self._inspect_text(container_id, "{{.Id}}")
                != container_id
                or self._inspect_text(
                    container_id,
                    "{{.State.Running}}",
                )
                != "false"
            ):
                raise RotationError(
                    "public_connector_quiescence_not_proven"
                )

    def verify_loopback(self, container_id: str, route: str) -> str:
        if route not in LOOPBACK_ROUTES:
            raise RotationError("loopback_route_not_authorized")
        body = self._docker(
            "container",
            "exec",
            container_id,
            "dotnet",
            "/app/loopback-probe/Chummer.Run.LoopbackProbe.dll",
            route,
            timeout=45,
        )
        return sha256_bytes(body)

    def assert_portals_stopped(
        self,
        container_ids: tuple[str, ...],
    ) -> None:
        if (
            not container_ids
            or len(set(container_ids)) != len(container_ids)
            or any(CONTAINER_ID.fullmatch(value) is None for value in container_ids)
            or set(self.portal_container_ids()) != set(container_ids)
        ):
            raise RotationError("portal_quiescence_identity_drift")
        for container_id in container_ids:
            if (
                self._inspect_text(container_id, "{{.Id}}") != container_id
                or self._inspect_text(
                    container_id,
                    "{{.State.Running}}",
                )
                != "false"
            ):
                raise RotationError("portal_quiescence_not_proven")

    def assert_known_portals_stopped(
        self,
        container_ids: tuple[str, ...],
    ) -> None:
        if (
            not container_ids
            or len(set(container_ids)) != len(container_ids)
            or any(
                CONTAINER_ID.fullmatch(value) is None
                for value in container_ids
            )
        ):
            raise RotationError(
                "known_portal_quiescence_identity_invalid"
            )
        for container_id in container_ids:
            if (
                self._inspect_text(container_id, "{{.Id}}")
                != container_id
                or self._inspect_text(
                    container_id,
                    "{{.State.Running}}",
                )
                != "false"
            ):
                raise RotationError(
                    "known_portal_quiescence_not_proven"
                )

    def quiesce_known_portals(
        self,
        container_ids: tuple[str, ...],
    ) -> None:
        if (
            not container_ids
            or len(set(container_ids)) != len(container_ids)
            or any(
                CONTAINER_ID.fullmatch(value) is None
                for value in container_ids
            )
        ):
            raise RotationError(
                "known_portal_quiescence_identity_invalid"
            )
        for container_id in container_ids:
            if self._inspect_text(container_id, "{{.Id}}") != container_id:
                raise RotationError(
                    "known_portal_quiescence_identity_drift"
                )
            running = self._inspect_text(
                container_id,
                "{{.State.Running}}",
            )
            if running == "true":
                self._docker("container", "stop", container_id, timeout=90)
            elif running != "false":
                raise RotationError(
                    "known_portal_quiescence_state_invalid"
                )
        self.assert_known_portals_stopped(container_ids)

    def quiesce_portals(self, container_ids: tuple[str, ...]) -> None:
        if (
            not container_ids
            or len(set(container_ids)) != len(container_ids)
            or any(CONTAINER_ID.fullmatch(value) is None for value in container_ids)
            or set(self.portal_container_ids()) != set(container_ids)
        ):
            raise RotationError("portal_quiescence_identity_drift")
        for container_id in container_ids:
            running = self._inspect_text(
                container_id,
                "{{.State.Running}}",
            )
            if running == "true":
                self._docker("container", "stop", container_id, timeout=90)
            elif running != "false":
                raise RotationError("portal_quiescence_state_invalid")
        self.assert_portals_stopped(container_ids)

    def restart_portals(self, container_ids: tuple[str, ...]) -> None:
        if (
            not container_ids
            or len(set(container_ids)) != len(container_ids)
            or any(CONTAINER_ID.fullmatch(value) is None for value in container_ids)
            or set(self.portal_container_ids()) != set(container_ids)
        ):
            raise RotationError("portal_restart_identity_drift")
        for container_id in container_ids:
            running = self._inspect_text(
                container_id,
                "{{.State.Running}}",
            )
            if running == "false":
                self._docker("container", "start", container_id, timeout=90)
            elif running != "true":
                raise RotationError("portal_restart_state_invalid")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            states = [
                (
                    self._inspect_text(identity, "{{.State.Running}}"),
                    self._inspect_text(
                        identity,
                        "{{if .State.Health}}{{.State.Health.Status}}"
                        "{{else}}none{{end}}",
                    ),
                )
                for identity in container_ids
            ]
            if all(state == ("true", "healthy") for state in states):
                return
            if any(
                running != "true" or health == "unhealthy"
                for running, health in states
            ):
                raise RotationError("portal_restart_unhealthy")
            time.sleep(1)
        raise RotationError("portal_restart_timeout")

    def recreate_all_portals(
        self,
        *,
        prior_container_ids: tuple[str, ...],
        container_names: tuple[str, ...],
    ) -> None:
        if len(container_names) != 1 or any(
            SAFE_CONTAINER_NAME.fullmatch(name) is None for name in container_names
        ):
            raise RotationError("portal_recreate_authority_invalid")
        for container_id in prior_container_ids:
            if CONTAINER_ID.fullmatch(container_id) is None:
                raise RotationError("portal_recreate_container_id_invalid")
            self._docker("container", "stop", container_id, timeout=90)
        for container_id in prior_container_ids:
            self._docker("container", "rm", container_id, timeout=90)
        for name in container_names:
            self._compose(
                "run",
                "-T",
                "-d",
                "--no-deps",
                "--pull",
                "never",
                "--service-ports",
                "--use-aliases",
                "--name",
                name,
                PORTAL_SERVICE,
                timeout=180,
            )
        for container_id in self.portal_container_ids():
            self._docker(
                "container",
                "update",
                "--restart",
                "unless-stopped",
                container_id,
            )
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            identities = self.portal_container_ids()
            if len(identities) == len(container_names):
                states = [
                    (
                        self._inspect_text(identity, "{{.State.Running}}"),
                        self._inspect_text(
                            identity,
                            "{{if .State.Health}}{{.State.Health.Status}}"
                            "{{else}}none{{end}}",
                        ),
                    )
                    for identity in identities
                ]
                if all(state == ("true", "healthy") for state in states):
                    return
                if any(
                    running != "true" or health == "unhealthy"
                    for running, health in states
                ):
                    raise RotationError("portal_recreate_unhealthy")
            time.sleep(1)
        raise RotationError("portal_recreate_timeout")

    def _request(
        self,
        *,
        method: str,
        path: str,
        authorization: str = "",
        revocation_nonce: str = "",
    ) -> tuple[int, tuple[tuple[str, str], ...], bytes]:
        if method not in {"GET", "POST"} or not path.startswith("/"):
            raise RotationError("public_request_not_authorized")
        headers = {
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
            "User-Agent": "chummer-release-ticket-epoch-rotation/1",
        }
        if authorization:
            headers["Authorization"] = authorization
        if revocation_nonce:
            if LOWER_SHA256.fullmatch(revocation_nonce) is None:
                raise RotationError("old_ticket_proof_nonce_invalid")
            headers[OLD_TICKET_PROOF_NONCE_HEADER] = revocation_nonce
        if method == "POST":
            headers["Content-Length"] = "0"
        connection = http.client.HTTPSConnection(
            self.base_host,
            timeout=30,
            context=ssl.create_default_context(),
        )
        try:
            connection.request(method, path, body=None, headers=headers)
            response = connection.getresponse()
            body = response.read(MAX_PUBLIC_BODY_BYTES + 1)
            if len(body) > MAX_PUBLIC_BODY_BYTES:
                raise RotationError("public_response_oversized")
            return (
                response.status,
                tuple(response.getheaders()),
                body,
            )
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise RotationError("public_request_failed") from exc
        finally:
            connection.close()

    def public_get(self, path: str) -> tuple[int, str]:
        if path not in PUBLIC_GET_PATHS:
            raise RotationError("public_get_path_not_authorized")
        status, _headers, body = self._request(method="GET", path=path)
        return status, sha256_bytes(body)

    def old_ticket_revocation_proof(
        self,
        ticket: str,
        nonce: str,
    ) -> tuple[int, tuple[tuple[str, str], ...], bytes]:
        return self._request(
            method="POST",
            path=OLD_TICKET_PROOF_PATH,
            authorization=f"Bearer {ticket}",
            revocation_nonce=nonce,
        )


def read_shared_mutation_lock_token(fd: int) -> str:
    if fd != 0:
        raise RotationError("shared_mutation_lock_fd_invalid")
    payload = bytearray()
    while len(payload) <= 65:
        chunk = os.read(fd, 66 - len(payload))
        if not chunk:
            break
        payload.extend(chunk)
    try:
        token = bytes(payload).decode("ascii", errors="strict").rstrip("\n")
    except UnicodeError as exc:
        raise RotationError("shared_mutation_lock_token_invalid") from exc
    if (
        token.endswith("\r")
        or re.fullmatch(r"[0-9a-f]{64}", token) is None
        or bytes(payload) not in {token.encode("ascii"), (token + "\n").encode("ascii")}
    ):
        raise RotationError("shared_mutation_lock_token_invalid")
    return token


def read_old_ticket_authority(
    fd: int,
) -> TicketMaterializationAuthority:
    if type(fd) is not int or fd < 3 or fd > 255:
        raise RotationError("old_ticket_authority_fd_invalid")
    try:
        before = os.fstat(fd)
    except OSError as exc:
        raise RotationError(
            "old_ticket_authority_fd_invalid"
        ) from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size < 1
        or before.st_size > MAX_TICKET_DIGEST_AUTHORITY_BYTES
    ):
        raise RotationError(
            "old_ticket_authority_not_owner_only"
        )
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        payload = os.read(fd, MAX_TICKET_DIGEST_AUTHORITY_BYTES + 1)
        after = os.fstat(fd)
    except OSError as exc:
        raise RotationError(
            "old_ticket_authority_read_failed"
        ) from exc
    if (
        len(payload) > MAX_TICKET_DIGEST_AUTHORITY_BYTES
        or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_mode,
            before.st_nlink,
            before.st_uid,
            before.st_gid,
        )
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_mode,
            after.st_nlink,
            after.st_uid,
            after.st_gid,
        )
        or len(payload) != before.st_size
    ):
        raise RotationError(
            "old_ticket_authority_changed_during_read"
        )
    authority = strict_json_object(
        payload,
        label="old_ticket_authority",
    )
    expected_fields = {
        "contractName",
        "generatedAtUtc",
        "status",
        "ticketPathSha256",
        "ticketSha256",
        "ticketSizeBytes",
        "envelopeSha256",
        "inventoryCommitmentSha256",
        "recipientCertificateSha256",
        "signerCertificateSha256",
        "opensslExecutableSha256",
        "materializationOpensslExecutableSha256",
        "materializationTransactionId",
        "quarantineStatus",
        "revocationStatus",
    }
    digest_fields = (
        "ticketPathSha256",
        "ticketSha256",
        "envelopeSha256",
        "inventoryCommitmentSha256",
        "recipientCertificateSha256",
        "signerCertificateSha256",
        "opensslExecutableSha256",
        "materializationOpensslExecutableSha256",
    )
    if (
        set(authority) != expected_fields
        or authority.get("contractName")
        != OLD_TICKET_DIGEST_AUTHORITY_CONTRACT
        or authority.get("status") != "materialized_pending_revocation"
        or authority.get("quarantineStatus") != "pending"
        or authority.get("revocationStatus") != "pending"
        or any(
            type(authority.get(key)) is not str
            or LOWER_SHA256.fullmatch(authority[key]) is None
            for key in digest_fields
        )
        or type(authority.get("ticketSizeBytes")) is not int
        or authority["ticketSizeBytes"] < 1
        or authority["ticketSizeBytes"] > MAX_TICKET_BYTES
        or type(authority.get("materializationTransactionId")) is not str
        or SAFE_TRANSACTION_ID.fullmatch(
            authority["materializationTransactionId"]
        )
        is None
        or type(authority.get("generatedAtUtc")) is not str
        or RFC3339_UTC.fullmatch(authority["generatedAtUtc"]) is None
    ):
        raise RotationError(
            "old_ticket_authority_contract_invalid"
        )
    _validate_timestamp(
        authority.get("generatedAtUtc"),
        code="old_ticket_authority_contract_invalid",
    )
    canonical = (
        json.dumps(
            authority,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if not hmac.compare_digest(payload, canonical):
        raise RotationError("old_ticket_authority_not_canonical")
    return TicketMaterializationAuthority(
        fd=fd,
        canonical_bytes=canonical,
        ticket_path_sha256=authority["ticketPathSha256"],
        ticket_sha256=authority["ticketSha256"],
        ticket_size_bytes=authority["ticketSizeBytes"],
        envelope_sha256=authority["envelopeSha256"],
        inventory_commitment_sha256=authority[
            "inventoryCommitmentSha256"
        ],
        recipient_certificate_sha256=authority[
            "recipientCertificateSha256"
        ],
        signer_certificate_sha256=authority[
            "signerCertificateSha256"
        ],
        openssl_executable_sha256=authority[
            "opensslExecutableSha256"
        ],
        materialization_openssl_executable_sha256=authority[
            "materializationOpensslExecutableSha256"
        ],
        materialization_transaction_id=authority[
            "materializationTransactionId"
        ],
    )


def revalidate_old_ticket_authority(
    authority: TicketMaterializationAuthority,
) -> TicketMaterializationAuthority:
    observed = read_old_ticket_authority(authority.fd)
    if not hmac.compare_digest(
        observed.canonical_bytes,
        authority.canonical_bytes,
    ):
        raise RotationError("old_ticket_authority_changed")
    return observed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rotate release-upload ticket epoch under an inherited mutation lease."
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--active-runtime-authority", type=Path, required=True)
    parser.add_argument("--epoch-authority-output", type=Path, required=True)
    parser.add_argument("--epoch-history-path", type=Path, required=True)
    parser.add_argument("--expected-epoch-history-sha256", required=True)
    parser.add_argument(
        "--epoch-history-bootstrap-authority",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--expected-epoch-history-bootstrap-authority-sha256",
        required=True,
    )
    parser.add_argument(
        "--epoch-history-bootstrap-marker",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--expected-epoch-history-bootstrap-marker-sha256",
        required=True,
    )
    parser.add_argument(
        "--edge-waf-local-evidence-source",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--expected-edge-waf-local-evidence-sha256",
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-env-sha256-before", required=True)
    parser.add_argument("--expected-image-id", required=True)
    parser.add_argument("--expected-proof-sha256", required=True)
    parser.add_argument("--expected-existing-receipt-sha256", default="")
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--expected-source-head", required=True)
    parser.add_argument("--new-epoch", required=True)
    parser.add_argument("--expected-portal-replicas", type=int, default=1)
    parser.add_argument("--shared-mutation-lock-fd", type=int, required=True)
    parser.add_argument("--old-ticket-path", type=Path)
    parser.add_argument(
        "--old-ticket-authority-fd",
        type=int,
        required=True,
    )
    parser.add_argument("--docker-config-root", type=Path, required=True)
    parser.add_argument("--docker-context", required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--build-context", type=Path, required=True)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--projection-root", type=Path, required=True)
    parser.add_argument("--proof-bind-source", type=Path, required=True)
    parser.add_argument("--published-port", type=int, required=True)
    parser.add_argument("--base-url", required=True)
    return parser.parse_args(argv)


def canonical_cli_path(path: Path, *, label: str) -> Path:
    if (
        not path.is_absolute()
        or overlay.normalized_absolute_path(path) != path
    ):
        raise RotationError(f"{label}_path_alias_not_canonical")
    return path


def classify_unhandled_failure(request: RotationRequest | None) -> int:
    if request is None:
        return 70
    status, _environment_sha256 = observe_epoch_boundary(request)
    return status


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    request: RotationRequest | None = None
    try:
        request = RotationRequest(
            env_file=canonical_cli_path(
                args.env_file,
                label="environment",
            ),
            active_runtime_authority=canonical_cli_path(
                args.active_runtime_authority,
                label="active_runtime_authority",
            ),
            output=canonical_cli_path(args.output, label="receipt"),
            expected_env_sha256_before=args.expected_env_sha256_before,
            expected_image_id=args.expected_image_id,
            expected_proof_sha256=args.expected_proof_sha256,
            image_tag=args.image_tag,
            expected_source_head=args.expected_source_head,
            new_epoch=args.new_epoch,
            expected_portal_replicas=args.expected_portal_replicas,
            shared_mutation_lock_token=read_shared_mutation_lock_token(
                args.shared_mutation_lock_fd
            ),
            old_ticket_path=(
                canonical_cli_path(
                    args.old_ticket_path,
                    label="old_ticket",
                )
                if args.old_ticket_path is not None
                else None
            ),
            old_ticket_authority=read_old_ticket_authority(
                args.old_ticket_authority_fd
            ),
            proof_bind_source=canonical_cli_path(
                args.proof_bind_source,
                label="proof_bind_source",
            ),
            expected_existing_receipt_sha256=(
                args.expected_existing_receipt_sha256
            ),
            epoch_authority_output=canonical_cli_path(
                args.epoch_authority_output,
                label="epoch_authority",
            ),
            epoch_history_path=canonical_cli_path(
                args.epoch_history_path,
                label="epoch_history",
            ),
            expected_epoch_history_sha256=(
                args.expected_epoch_history_sha256
            ),
            epoch_history_bootstrap_authority=canonical_cli_path(
                args.epoch_history_bootstrap_authority,
                label="epoch_history_bootstrap_authority",
            ),
            expected_epoch_history_bootstrap_authority_sha256=(
                args.expected_epoch_history_bootstrap_authority_sha256
            ),
            epoch_history_bootstrap_marker=canonical_cli_path(
                args.epoch_history_bootstrap_marker,
                label="epoch_history_bootstrap_marker",
            ),
            expected_epoch_history_bootstrap_marker_sha256=(
                args.expected_epoch_history_bootstrap_marker_sha256
            ),
            edge_waf_local_evidence_source=canonical_cli_path(
                args.edge_waf_local_evidence_source,
                label="edge_waf_local_evidence_source",
            ),
            expected_edge_waf_local_evidence_sha256=(
                args.expected_edge_waf_local_evidence_sha256
            ),
        )
        runtime = DockerRuntime(
            docker_config_root=canonical_cli_path(
                args.docker_config_root,
                label="docker_config_root",
            ),
            docker_context=args.docker_context,
            compose_file=canonical_cli_path(
                args.compose_file,
                label="compose_file",
            ),
            env_file=request.env_file,
            project_name=args.project_name,
            source_root=canonical_cli_path(
                args.source_root,
                label="source_root",
            ),
            build_context=canonical_cli_path(
                args.build_context,
                label="build_context",
            ),
            overlay_root=canonical_cli_path(
                args.overlay_root,
                label="overlay_root",
            ),
            projection_root=canonical_cli_path(
                args.projection_root,
                label="projection_root",
            ),
            proof_bind_source=request.proof_bind_source,
            published_port=args.published_port,
            base_url=args.base_url,
        )
        status, receipt = run_rotation(request, runtime)
    except Exception as exc:
        code = exc.code if isinstance(exc, RotationError) else "unexpected_failure"
        failure_status = classify_unhandled_failure(request)
        fail_forward_required = failure_status == 76
        failed_before_epoch_commit = failure_status == 75
        print(
            json.dumps(
                {
                    "contractName": CONTRACT_NAME,
                    "status": (
                        "fail_forward_required"
                        if fail_forward_required
                        else (
                            "failed_before_epoch_commit"
                            if failed_before_epoch_commit
                            else "refused"
                        )
                    ),
                    "failureCode": code,
                },
                sort_keys=True,
            )
        )
        return failure_status
    print(
        json.dumps(
            {
                "contractName": CONTRACT_NAME,
                "status": receipt["status"],
                "phase": receipt["phase"],
                "receiptSha256": sha256_bytes(
                    (
                        json.dumps(
                            receipt,
                            indent=2,
                            sort_keys=True,
                            allow_nan=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                ),
            },
            sort_keys=True,
        )
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
