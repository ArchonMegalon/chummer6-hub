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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
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
LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
SAFE_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SAFE_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_ENV_BYTES = 1024 * 1024
MAX_TICKET_BYTES = 16 * 1024
MAX_PUBLIC_BODY_BYTES = 4 * 1024 * 1024
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


def load_ticket(path: Path, expected_sha256: str) -> tuple[str, str]:
    if LOWER_SHA256.fullmatch(expected_sha256) is None:
        raise RotationError("old_ticket_sha256_invalid")
    payload = read_owner_only_file(
        path,
        label="old_ticket",
        maximum_bytes=MAX_TICKET_BYTES,
    )
    actual_sha256 = sha256_bytes(payload)
    if actual_sha256 != expected_sha256:
        raise RotationError("old_ticket_sha256_mismatch")
    try:
        ticket = payload.decode("ascii", errors="strict").strip()
    except UnicodeError as exc:
        raise RotationError("old_ticket_not_ascii") from exc
    if (
        not ticket
        or len(ticket) > MAX_TICKET_BYTES
        or any(character.isspace() for character in ticket)
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
    ticket_sha256: str,
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
        "ticketSha256": ticket_sha256,
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
        or CONTAINER_ID.fullmatch(str(portal.get("containerId") or "")) is None
        or SAFE_CONTAINER_NAME.fullmatch(
            str(portal.get("containerName") or "")
        )
        is None
        or IMAGE_ID.fullmatch(str(portal.get("imageId") or "")) is None
        or LOWER_SHA256.fullmatch(
            str(portal.get("proofAuthorityMountSha256") or "")
        )
        is None
        or LOWER_SHA256.fullmatch(
            str(portal.get("proofPublicMountSha256") or "")
        )
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
            or LOWER_SHA256.fullmatch(str(readiness_sha256 or "")) is None
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
    rotation_receipt_sha256: str,
    active_runtime_authority_sha256: str,
    portal: PortalEvidence,
    storage_authority: dict[str, Any],
    environment_sha256_after: str,
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
        "portalContainerId": portal.container_id,
        "portalContainerName": portal.container_name,
        "portalRuntimeContractSha256": portal.runtime_contract_sha256,
        "storageAuthoritySha256": storage_sha256,
        "activeRuntimeAuthorityPath": str(request.active_runtime_authority),
        "activeRuntimeAuthoritySha256": active_runtime_authority_sha256,
        "rotationReceiptPath": str(request.output),
        "rotationReceiptSha256": rotation_receipt_sha256,
        "edgeWafMutationPerformed": False,
        "edgeWafPreservedThroughPostVerification": True,
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
    old_ticket_sha256: str
    proof_bind_source: Path
    expected_existing_receipt_sha256: str
    epoch_authority_output: Path


def _base_receipt(request: RotationRequest) -> dict[str, Any]:
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
            "ticketSha256": request.old_ticket_sha256,
            "httpStatus": None,
            "status": "pending" if request.old_ticket_path is not None else "not_supplied",
        },
        "edgeWaf": {
            "mutationAuthorized": False,
            "mutationPerformed": False,
            "preservedThroughPostVerification": False,
        },
        "rollbackPolicy": "old_epoch_rollback_permanently_forbidden_after_epoch_commit",
        "recreationPolicy": "all_prior_replicas_stopped_and_removed_before_any_recreate",
        "failureCode": "",
    }


def _validate_request(request: RotationRequest) -> None:
    if LOWER_SHA256.fullmatch(request.expected_env_sha256_before) is None:
        raise RotationError("expected_environment_sha256_invalid")
    if IMAGE_ID.fullmatch(request.expected_image_id) is None:
        raise RotationError("expected_image_id_invalid")
    if LOWER_SHA256.fullmatch(request.expected_proof_sha256) is None:
        raise RotationError("expected_proof_sha256_invalid")
    if (
        not request.proof_bind_source.is_absolute()
        or overlay.normalized_absolute_path(request.proof_bind_source)
        != request.proof_bind_source
    ):
        raise RotationError("proof_bind_source_path_invalid")
    if request.expected_existing_receipt_sha256 and LOWER_SHA256.fullmatch(
        request.expected_existing_receipt_sha256
    ) is None:
        raise RotationError("expected_existing_receipt_sha256_invalid")
    if (
        not request.epoch_authority_output.is_absolute()
        or overlay.normalized_absolute_path(request.epoch_authority_output)
        != request.epoch_authority_output
        or request.epoch_authority_output
        in {request.output, request.active_runtime_authority}
    ):
        raise RotationError("epoch_authority_output_invalid")
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
    if (request.old_ticket_path is None) != (not request.old_ticket_sha256):
        raise RotationError("old_ticket_proof_arguments_incomplete")
    if request.old_ticket_sha256 and LOWER_SHA256.fullmatch(
        request.old_ticket_sha256
    ) is None:
        raise RotationError("old_ticket_sha256_invalid")


def _validate_resume_receipt(
    receipt: dict[str, Any],
    request: RotationRequest,
) -> None:
    expected = {
        "contractName": CONTRACT_NAME,
        "sourceHead": request.expected_source_head,
        "imageTag": request.image_tag,
        "imageId": request.expected_image_id,
        "proofBindSourceSha256": request.expected_proof_sha256,
        "epochAuthorityPath": str(request.epoch_authority_output),
        "portalReplicaCount": request.expected_portal_replicas,
        "newEpochSha256": sha256_text(request.new_epoch),
        "environmentSha256Before": request.expected_env_sha256_before,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise RotationError("resume_receipt_authority_mismatch")
    proof = receipt.get("oldTicketRevocationProof")
    if (
        not isinstance(proof, dict)
        or proof.get("supplied") != (request.old_ticket_path is not None)
        or proof.get("ticketSha256") != request.old_ticket_sha256
    ):
        raise RotationError("resume_ticket_proof_authority_mismatch")


def observe_epoch_boundary(request: RotationRequest) -> tuple[int, str]:
    try:
        environment = read_owner_only_file(
            request.env_file,
            label="environment",
            maximum_bytes=MAX_ENV_BYTES,
        )
        observed_epoch, _ = parse_epoch_environment(environment)
    except Exception:
        # An unreadable environment makes the commit boundary uncertain.
        return 76, ""
    environment_sha256 = sha256_bytes(environment)
    if environment_sha256 == request.expected_env_sha256_before:
        return 75, environment_sha256
    return (
        76 if observed_epoch == request.new_epoch else 75,
        environment_sha256,
    )


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

    existing_receipt = request.output.exists() or request.output.is_symlink()
    if existing_receipt:
        receipt, receipt_sha256 = strict_receipt(request.output)
        if (
            request.expected_existing_receipt_sha256
            and receipt_sha256 != request.expected_existing_receipt_sha256
        ):
            raise RotationError("existing_receipt_sha256_mismatch")
        _validate_resume_receipt(receipt, request)
    else:
        if request.expected_existing_receipt_sha256:
            raise RotationError("expected_existing_receipt_missing")
        receipt = _base_receipt(request)

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

    try:
        with overlay.public_edge_mutation_lock(
            activate=True,
            inherited_token=request.shared_mutation_lock_token,
        ):
            if runtime.resolve_image_id(request.image_tag) != request.expected_image_id:
                raise RotationError("pinned_image_tag_drift")

            if not committed:
                old_epoch_sha256 = sha256_text(current_epoch)
                if old_epoch_sha256 == new_epoch_sha256:
                    raise RotationError("new_epoch_does_not_change_authority")
                portals_before = inspect_exact_portals(
                    runtime,
                    expected_count=request.expected_portal_replicas,
                    expected_image_id=request.expected_image_id,
                    expected_epoch_sha256=old_epoch_sha256,
                    expected_proof_sha256=request.expected_proof_sha256,
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
                    }
                )
                atomic_write_private_json(request.output, receipt)
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
                portals_before = tuple()
                tunnels_before = tuple()
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
            recreated = False
            try:
                current_portals = tuple(
                    runtime.inspect_portal(identity) for identity in current_ids
                )
                if len(current_portals) != request.expected_portal_replicas:
                    raise RotationError("portal_recreate_required")
                for item in current_portals:
                    validate_portal(
                        item,
                        expected_image_id=request.expected_image_id,
                        expected_epoch_sha256=new_epoch_sha256,
                        expected_proof_sha256=request.expected_proof_sha256,
                    )
                if tuple(item.container_name for item in current_portals) != prior_names:
                    raise RotationError("portal_recreate_required")
            except RotationError:
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
                    bool(item["running"]),
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
            old_ticket_proof = dict(receipt["oldTicketRevocationProof"])
            if request.old_ticket_path is not None:
                ticket, ticket_sha256 = load_ticket(
                    request.old_ticket_path,
                    request.old_ticket_sha256,
                )
                try:
                    old_ticket_proof = verify_old_ticket_revocation(
                        runtime,
                        ticket=ticket,
                        ticket_sha256=ticket_sha256,
                        expected_epoch_sha256=new_epoch_sha256,
                    )
                finally:
                    del ticket
            verify_proof_bind_source(request)
            verify_committed_environment(
                request,
                expected_sha256=committed_env_sha256,
            )
            receipt.update(
                {
                    "status": "pass",
                    "phase": "post_rotation_verified",
                    "updatedAtUtc": now_iso(),
                    "oldTicketRevocationProof": old_ticket_proof,
                    "edgeWaf": {
                        "mutationAuthorized": False,
                        "mutationPerformed": False,
                        "preservedThroughPostVerification": True,
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
                rotation_receipt_sha256=rotation_receipt_sha256,
                active_runtime_authority_sha256=authority_after_sha256,
                portal=portals_after[0],
                storage_authority=storage_after,
                environment_sha256_after=committed_env_sha256,
            )
            return 0, receipt
    except Exception as exc:
        code = exc.code if isinstance(exc, RotationError) else "unexpected_failure"
        failure_status, observed_environment_sha256 = observe_epoch_boundary(
            request
        )
        fail_forward_required = failure_status == 76
        if fail_forward_required and observed_environment_sha256:
            receipt["environmentSha256After"] = observed_environment_sha256
        waf_preserved_through_postverification = receipt.get("phase") in {
            "post_rotation_runtime_verified",
            "post_rotation_verified",
        }
        prior_phase = str(receipt.get("phase") or "")
        if fail_forward_required:
            failure_phase = (
                "epoch_commit_outcome_uncertain"
                if prior_phase in {"", "initializing", "old_epoch_verified"}
                else prior_phase
            )
        else:
            failure_phase = "precommit_failed"
        receipt.update(
            {
                "status": (
                    "fail_forward_required"
                    if fail_forward_required
                    else "failed_before_epoch_commit"
                ),
                "phase": failure_phase,
                "updatedAtUtc": now_iso(),
                "failureCode": code,
                "edgeWaf": {
                    "mutationAuthorized": False,
                    "mutationPerformed": False,
                    "preservedThroughPostVerification": (
                        waf_preserved_through_postverification
                    ),
                },
            }
        )
        atomic_write_private_json(request.output, receipt)
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
            aliases = [
                alias
                for alias in (network.get("Aliases") or [])
                if isinstance(alias, str)
                and alias not in {container_id, container_id[:12]}
            ]
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
            return MountEvidence(
                destination=destination,
                volume_name=str(item.get("Name") or ""),
                read_write=bool(item.get("RW")),
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

    def tunnel_evidence(self) -> tuple[TunnelEvidence, ...]:
        results: list[TunnelEvidence] = []
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rotate release-upload ticket epoch under an inherited mutation lease."
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--active-runtime-authority", type=Path, required=True)
    parser.add_argument("--epoch-authority-output", type=Path, required=True)
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
    parser.add_argument("--old-ticket-sha256", default="")
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
            env_file=overlay.normalized_absolute_path(args.env_file),
            active_runtime_authority=overlay.normalized_absolute_path(
                args.active_runtime_authority
            ),
            output=overlay.normalized_absolute_path(args.output),
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
                overlay.normalized_absolute_path(args.old_ticket_path)
                if args.old_ticket_path is not None
                else None
            ),
            old_ticket_sha256=args.old_ticket_sha256,
            proof_bind_source=overlay.normalized_absolute_path(
                args.proof_bind_source
            ),
            expected_existing_receipt_sha256=(
                args.expected_existing_receipt_sha256
            ),
            epoch_authority_output=overlay.normalized_absolute_path(
                args.epoch_authority_output
            ),
        )
        runtime = DockerRuntime(
            docker_config_root=overlay.normalized_absolute_path(
                args.docker_config_root
            ),
            docker_context=args.docker_context,
            compose_file=overlay.normalized_absolute_path(args.compose_file),
            env_file=request.env_file,
            project_name=args.project_name,
            source_root=overlay.normalized_absolute_path(args.source_root),
            build_context=overlay.normalized_absolute_path(args.build_context),
            overlay_root=overlay.normalized_absolute_path(args.overlay_root),
            projection_root=overlay.normalized_absolute_path(args.projection_root),
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
