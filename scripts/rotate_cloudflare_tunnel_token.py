#!/usr/bin/env python3
"""Rotate the Chummer Cloudflare Tunnel token without exposing secret material.

This operator tool has two modes:

* audit (the default) performs the complete read-only preflight;
* ``--execute`` performs the rotation only with the exact confirmation phrase.

The live mutation path deliberately overlaps two incumbent connectors with a
new-token canary. It will not remove or recreate an incumbent connector until
the canary has remained healthy for ten minutes. Before that commit point, any
failure rotates the Cloudflare secret back and restores the incumbent token
file. After the commit point, failures preserve the canary and the remaining
connector for operator recovery.

Tunnel tokens and Cloudflare credentials are read only from owner-only files.
They are never placed in argv, subprocess environments, logs, receipts, or Git.
The tool never calls Cloudflare's connection-delete endpoint.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
import datetime as dt
import fcntl
import grp
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import subprocess
import sys
import time
from typing import Any, Protocol
import urllib.error
import urllib.parse
import urllib.request
import uuid


CONTRACT = "chummer.cloudflare-tunnel-token-rotation/v1"
CONFIRMATION = "ROTATE_CHUMMER_RUN_CLOUDFLARE_TOKEN_ZERO_DOWNTIME"
PINNED_IMAGE = (
    "cloudflare/cloudflared:2026.7.0@"
    "sha256:8c70a8c2d373e93caac1ee79fcc615908a49ccf3f3975775d1e10d24e41327af"
)
PINNED_CLOUDFLARED_VERSION = "2026.7.0"
PINNED_PLATFORM = "linux/amd64"
COMPOSE_PROJECT_NAME = "chummer6-hub"
RUNTIME_LOCK_ROOT = Path("/run/user") / str(os.geteuid())
PRIMARY_SERVICE = "chummer-run-cloudflared"
REPLICA_SERVICE = "chummer-run-cloudflared-replica"
CANARY_CONTAINER = "chummer-run-cloudflared-rotation-canary"
MIGRATION_CANARY_CONTAINERS = (
    "chummer-run-cloudflared-migration-canary-a",
    "chummer-run-cloudflared-migration-canary-b",
)
# The actual legacy container occupies the future canonical primary name.
LEGACY_CONTAINER = PRIMARY_SERVICE
TOKEN_TARGET = "/run/secrets/chummer-run-cloudflared.token"
DEFAULT_NETWORK = "chummer5a_default"
MINIMUM_ACTIVE_CONNECTORS = 2
MINIMUM_EDGE_CONNECTIONS = 4
MANDATORY_DWELL_SECONDS = 600
MIGRATION_DWELL_SECONDS = MANDATORY_DWELL_SECONDS
MONITOR_INTERVAL_SECONDS = 15
CONNECTOR_JOIN_TIMEOUT_SECONDS = 180
CONTAINER_HEALTH_TIMEOUT_SECONDS = 180
MAX_SECRET_FILE_BYTES = 4096
MAX_CREDENTIAL_FILE_BYTES = 1024 * 1024
MAX_COMPOSE_ENV_BYTES = 1024 * 1024
MAX_HTTP_BODY_BYTES = 2 * 1024 * 1024
MAX_API_BODY_BYTES = 2 * 1024 * 1024
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
ACCOUNT_ID = re.compile(r"^[0-9a-f]{32}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


class RotationError(RuntimeError):
    """A fail-closed error whose code is safe to place in a receipt."""

    def __init__(self, code: str) -> None:
        if not re.fullmatch(r"[a-z0-9_]{3,96}", code):
            code = "unsafe_error_code"
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class SecretText:
    value: str

    def __repr__(self) -> str:
        return "SecretText(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()

    def matches(self, other: "SecretText") -> bool:
        return hmac.compare_digest(self.value, other.value)


@dataclass(frozen=True, repr=False)
class CloudflareCredentials:
    email: SecretText
    global_api_key: SecretText

    def __repr__(self) -> str:
        return "CloudflareCredentials(<redacted>)"

    @property
    def secret_values(self) -> tuple[str, str]:
        return (self.email.value, self.global_api_key.value)


@dataclass(frozen=True)
class TunnelTokenMetadata:
    account_id: str
    tunnel_id: str
    tunnel_secret: SecretText


@dataclass(frozen=True)
class Connector:
    connector_id: str
    version: str
    active_edge_count: int
    pending_edge_count: int

    @property
    def active(self) -> bool:
        return self.active_edge_count >= MINIMUM_EDGE_CONNECTIONS


@dataclass(frozen=True)
class ApiSnapshot:
    tunnel_id: str
    tunnel_name: str
    status: str
    config_source: str
    config_version: int
    config_sha256: str
    connectors: tuple[Connector, ...]

    @property
    def active_connector_ids(self) -> frozenset[str]:
        return frozenset(
            connector.connector_id
            for connector in self.connectors
            if connector.active
        )


@dataclass(frozen=True)
class ProbeSpec:
    url: str
    expected_statuses: frozenset[int]
    stable_body: bool = False


DEFAULT_PROBES = (
    ProbeSpec("https://chummer.run/", frozenset({200})),
    ProbeSpec("https://www.chummer.run/", frozenset({200})),
    ProbeSpec(
        "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json",
        frozenset({200}),
        stable_body=True,
    ),
    ProbeSpec("https://home.girschele.com/", frozenset({302})),
    ProbeSpec("https://mymedia.girschele.com/", frozenset({302})),
)


@dataclass(frozen=True)
class ProbeResult:
    url: str
    status: int
    body_sha256: str

    def receipt_payload(self, *, include_digest: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "url": self.url,
            "httpStatus": self.status,
        }
        if include_digest:
            payload["bodySha256"] = self.body_sha256
        return payload


@dataclass(frozen=True)
class ComposeEnvironment:
    token_file: Path
    runtime_uid: int
    runtime_gid: int
    network: str


@dataclass(frozen=True)
class LegacyComposeMigration:
    original_bytes: bytes
    rewritten_bytes: bytes
    old_token: SecretText
    environment: ComposeEnvironment


@dataclass(frozen=True)
class RotationInputs:
    repository_root: Path
    compose_file: Path
    compose_env_file: Path
    credentials_file: Path
    token_file: Path
    receipt_file: Path
    tunnel_id: str
    tunnel_name: str

    @property
    def lock_file(self) -> Path:
        return canonical_rotation_lock_path(
            self.compose_env_file,
            self.tunnel_id,
        )


def canonical_rotation_lock_path(
    compose_env_file: Path,
    tunnel_id: str,
) -> Path:
    """Return the sole runtime mutex for one deployment authority and tunnel."""
    if not compose_env_file.is_absolute():
        raise RotationError("compose_env_path_not_absolute")
    try:
        parsed_tunnel_id = uuid.UUID(tunnel_id)
    except ValueError as exc:
        raise RotationError("cloudflare_tunnel_id_invalid") from exc
    authority = (
        f"{compose_env_file}\0{parsed_tunnel_id}".encode("utf-8")
    )
    authority_digest = hashlib.sha256(authority).hexdigest()[:32]
    return RUNTIME_LOCK_ROOT / (
        f"chummer-cloudflare-rotation-{authority_digest}.lock"
    )


@dataclass
class ReceiptState:
    run_id: str
    mode: str
    phase: str = "initialized"
    status: str = "running"
    started_at: str = field(default_factory=lambda: utc_now())
    completed_at: str = ""
    tunnel_id: str = ""
    tunnel_name: str = ""
    account_id_sha256: str = ""
    before_token_sha256: str = ""
    after_token_sha256: str = ""
    config_version: int = 0
    config_sha256: str = ""
    baseline_connector_ids: list[str] = field(default_factory=list)
    final_connector_ids: list[str] = field(default_factory=list)
    checks: list[dict[str, object]] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)
    failure_code: str = ""
    rollback_status: str = "not_required"
    migration_status: str = "not_required"
    migration_commit_started: bool = False
    rotation_commit_started: bool = False
    legacy_container_removed: bool = False

    def event(self, name: str, **fields: object) -> None:
        payload: dict[str, object] = {
            "name": name,
            "recordedAt": utc_now(),
        }
        payload.update(fields)
        self.events.append(payload)

    def payload(self) -> dict[str, object]:
        return {
            "contract": CONTRACT,
            "runId": self.run_id,
            "mode": self.mode,
            "phase": self.phase,
            "status": self.status,
            "startedAt": self.started_at,
            "completedAt": self.completed_at or None,
            "tunnel": {
                "id": self.tunnel_id,
                "name": self.tunnel_name,
                "accountIdSha256": self.account_id_sha256,
                "configurationVersion": self.config_version,
                "configurationSha256": self.config_sha256,
            },
            "tokenFingerprints": {
                "beforeSha256": self.before_token_sha256,
                "afterSha256": self.after_token_sha256 or None,
            },
            "baselineConnectorIds": self.baseline_connector_ids,
            "finalConnectorIds": self.final_connector_ids,
            "checks": self.checks,
            "events": self.events,
            "failureCode": self.failure_code or None,
            "rollbackStatus": self.rollback_status,
            "legacyMigrationStatus": self.migration_status,
            "legacyMigrationCommitStarted": self.migration_commit_started,
            "rotationCommitStarted": self.rotation_commit_started,
            "legacyContainerRemoved": self.legacy_container_removed,
            "cloudflareConnectionsDeleteCalled": False,
            "secretsExposed": False,
        }


def utc_now() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _bounded_read(descriptor: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(65536, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise RotationError("owner_only_file_too_large")
    return b"".join(chunks)


def _assert_immediate_parent_safe(path: Path) -> None:
    parent = path.parent
    try:
        resolved = parent.resolve(strict=True)
        parent_stat = resolved.stat()
    except OSError as exc:
        raise RotationError("unsafe_parent_directory") from exc
    if resolved != parent:
        raise RotationError("symlinked_parent_directory")
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise RotationError("unsafe_parent_directory")
    if parent_stat.st_uid != os.geteuid():
        raise RotationError("parent_directory_wrong_owner")
    mode = stat.S_IMODE(parent_stat.st_mode)
    if mode & 0o002:
        raise RotationError("parent_directory_world_writable")
    if mode & 0o020:
        try:
            current_user = pwd.getpwuid(os.geteuid()).pw_name
            group = grp.getgrgid(parent_stat.st_gid)
            group_principals = {
                entry.pw_name
                for entry in pwd.getpwall()
                if entry.pw_gid == parent_stat.st_gid
            }
            group_principals.update(group.gr_mem)
        except (KeyError, OSError) as exc:
            raise RotationError("parent_directory_group_unsafe") from exc
        if (
            parent_stat.st_gid != os.getegid()
            or group_principals != {current_user}
        ):
            raise RotationError("parent_directory_group_unsafe")


def _assert_strict_private_parent(path: Path) -> None:
    _assert_immediate_parent_safe(path)
    mode = stat.S_IMODE(path.parent.stat().st_mode)
    if mode & 0o022:
        raise RotationError("parent_directory_not_private")


def read_owner_only_file(path: Path, *, limit: int) -> bytes:
    if not path.is_absolute():
        raise RotationError("owner_only_path_not_absolute")
    _assert_immediate_parent_safe(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RotationError("owner_only_file_open_failed") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RotationError("owner_only_file_not_regular")
        if before.st_uid != os.geteuid():
            raise RotationError("owner_only_file_wrong_owner")
        if stat.S_IMODE(before.st_mode) != 0o600:
            raise RotationError("owner_only_file_wrong_mode")
        if before.st_nlink != 1:
            raise RotationError("owner_only_file_hardlinked")
        content = _bounded_read(descriptor, limit)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise RotationError("owner_only_file_changed_during_read")
        return content
    finally:
        os.close(descriptor)


def _strict_text(content: bytes, code: str) -> str:
    try:
        text = content.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RotationError(code) from exc
    if "\x00" in text or "\r" in text:
        raise RotationError(code)
    return text


def parse_credentials_file(path: Path) -> CloudflareCredentials:
    text = _strict_text(
        read_owner_only_file(path, limit=MAX_CREDENTIAL_FILE_BYTES),
        "credentials_invalid_encoding",
    )
    values: dict[str, str] = {}
    allowed = {"CLOUDFLARE_EMAIL", "CLOUDFLARE_GLOBAL_API_KEY"}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RotationError("credentials_invalid_shape")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        if key not in allowed:
            continue
        if key in values or not value:
            raise RotationError("credentials_invalid_shape")
        values[key] = value
    if set(values) != allowed:
        raise RotationError("credentials_invalid_shape")
    if not EMAIL.fullmatch(values["CLOUDFLARE_EMAIL"]):
        raise RotationError("credentials_email_invalid")
    key = values["CLOUDFLARE_GLOBAL_API_KEY"]
    if not 20 <= len(key) <= 256 or any(character.isspace() for character in key):
        raise RotationError("credentials_key_invalid")
    return CloudflareCredentials(
        email=SecretText(values["CLOUDFLARE_EMAIL"]),
        global_api_key=SecretText(key),
    )


def parse_tunnel_token(token: SecretText) -> TunnelTokenMetadata:
    if not token.value or any(character.isspace() for character in token.value):
        raise RotationError("tunnel_token_invalid")
    try:
        padding = "=" * ((4 - len(token.value) % 4) % 4)
        decoded = base64.urlsafe_b64decode(token.value + padding)
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RotationError("tunnel_token_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"a", "s", "t"}:
        raise RotationError("tunnel_token_invalid")
    account_id = str(payload.get("a") or "")
    tunnel_id = str(payload.get("t") or "")
    tunnel_secret = str(payload.get("s") or "")
    try:
        uuid.UUID(tunnel_id)
    except ValueError as exc:
        raise RotationError("tunnel_token_invalid") from exc
    if not ACCOUNT_ID.fullmatch(account_id) or not tunnel_secret:
        raise RotationError("tunnel_token_invalid")
    return TunnelTokenMetadata(
        account_id=account_id,
        tunnel_id=tunnel_id,
        tunnel_secret=SecretText(tunnel_secret),
    )


def read_token_file(path: Path) -> SecretText:
    text = _strict_text(
        read_owner_only_file(path, limit=MAX_SECRET_FILE_BYTES),
        "tunnel_token_invalid_encoding",
    )
    if text.endswith("\n"):
        text = text[:-1]
    if "\n" in text:
        raise RotationError("tunnel_token_invalid_shape")
    token = SecretText(text)
    parse_tunnel_token(token)
    return token


def parse_compose_environment(
    path: Path,
    *,
    expected_token_file: Path,
    token_stat: os.stat_result,
) -> ComposeEnvironment:
    text = _strict_text(
        read_owner_only_file(path, limit=MAX_COMPOSE_ENV_BYTES),
        "compose_env_invalid_encoding",
    )
    target_keys = {
        "CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE",
        "CHUMMER_RUN_CF_TUNNEL_TOKEN",
        "CHUMMER_CLOUDFLARED_RUNTIME_UID",
        "CHUMMER_CLOUDFLARED_RUNTIME_GID",
        "CHUMMER_RUN_TUNNEL_NETWORK",
    }
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in target_keys:
            continue
        if key in values:
            raise RotationError("compose_env_duplicate_rotation_key")
        values[key] = value.strip().strip('"').strip("'")
    if "CHUMMER_RUN_CF_TUNNEL_TOKEN" in values:
        raise RotationError("legacy_tunnel_token_still_in_compose_env")
    configured_path = Path(values.get("CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE", ""))
    if (
        not configured_path.is_absolute()
        or configured_path.resolve(strict=False)
        != expected_token_file.resolve(strict=False)
    ):
        raise RotationError("compose_env_token_file_mismatch")
    try:
        runtime_uid = int(values.get("CHUMMER_CLOUDFLARED_RUNTIME_UID", "1000"))
        runtime_gid = int(values.get("CHUMMER_CLOUDFLARED_RUNTIME_GID", "1000"))
    except ValueError as exc:
        raise RotationError("compose_env_runtime_identity_invalid") from exc
    if runtime_uid != token_stat.st_uid or runtime_gid != token_stat.st_gid:
        raise RotationError("compose_env_runtime_identity_mismatch")
    network = values.get("CHUMMER_RUN_TUNNEL_NETWORK", DEFAULT_NETWORK)
    if not SAFE_IDENTIFIER.fullmatch(network):
        raise RotationError("compose_env_network_invalid")
    return ComposeEnvironment(
        token_file=expected_token_file,
        runtime_uid=runtime_uid,
        runtime_gid=runtime_gid,
        network=network,
    )


def prepare_legacy_compose_migration(
    path: Path,
    *,
    token_file: Path,
) -> LegacyComposeMigration:
    """Prepare, but do not write, the one-time legacy dotenv migration."""

    original = read_owner_only_file(path, limit=MAX_COMPOSE_ENV_BYTES)
    text = _strict_text(original, "compose_env_invalid_encoding")
    target_keys = {
        "CHUMMER_RUN_CF_TUNNEL_TOKEN",
        "CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE",
        "CHUMMER_CLOUDFLARED_RUNTIME_UID",
        "CHUMMER_CLOUDFLARED_RUNTIME_GID",
        "CHUMMER_RUN_TUNNEL_NETWORK",
    }
    values: dict[str, str] = {}
    retained_lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line or raw_line.startswith("#"):
            retained_lines.append(raw_line)
            continue
        key, separator, value = raw_line.partition("=")
        if not separator:
            if any(target in raw_line for target in target_keys):
                raise RotationError("legacy_compose_env_ambiguous")
            retained_lines.append(raw_line)
            continue
        if key not in target_keys:
            if any(target in key for target in target_keys):
                raise RotationError("legacy_compose_env_ambiguous")
            retained_lines.append(raw_line)
            continue
        if key in values:
            raise RotationError("compose_env_duplicate_rotation_key")
        if value != value.strip():
            raise RotationError("legacy_compose_env_ambiguous")
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        if not value:
            raise RotationError("legacy_compose_env_ambiguous")
        values[key] = value

    raw_token = values.get("CHUMMER_RUN_CF_TUNNEL_TOKEN")
    if raw_token is None:
        raise RotationError("legacy_tunnel_token_missing")
    if "CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE" in values:
        raise RotationError("legacy_and_token_file_configuration_mixed")
    old_token = SecretText(raw_token)
    parse_tunnel_token(old_token)
    if original.count(raw_token.encode("utf-8")) != 1:
        raise RotationError("legacy_tunnel_token_duplicated")
    if not token_file.is_absolute():
        raise RotationError("owner_only_path_not_absolute")
    _assert_immediate_parent_safe(token_file)
    if token_file.exists():
        raise RotationError("bootstrap_token_file_already_exists")

    network = values.get("CHUMMER_RUN_TUNNEL_NETWORK", DEFAULT_NETWORK)
    if not SAFE_IDENTIFIER.fullmatch(network):
        raise RotationError("compose_env_network_invalid")
    runtime_uid = os.geteuid()
    runtime_gid = os.getegid()
    canonical_lines = [
        *retained_lines,
        f"CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE={token_file}",
        f"CHUMMER_CLOUDFLARED_RUNTIME_UID={runtime_uid}",
        f"CHUMMER_CLOUDFLARED_RUNTIME_GID={runtime_gid}",
        f"CHUMMER_RUN_TUNNEL_NETWORK={network}",
    ]
    rewritten = ("\n".join(canonical_lines).rstrip("\n") + "\n").encode(
        "utf-8"
    )
    if raw_token.encode("utf-8") in rewritten:
        raise RotationError("legacy_tunnel_token_scrub_failed")
    return LegacyComposeMigration(
        original_bytes=original,
        rewritten_bytes=rewritten,
        old_token=old_token,
        environment=ComposeEnvironment(
            token_file=token_file,
            runtime_uid=runtime_uid,
            runtime_gid=runtime_gid,
            network=network,
        ),
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_owner_only(
    path: Path,
    content: bytes,
    *,
    replace: bool,
) -> None:
    _assert_immediate_parent_safe(path)
    if not replace and path.exists():
        raise RotationError("owner_only_output_already_exists")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        view = memoryview(content)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise RotationError("owner_only_output_write_failed")
            written += count
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if replace:
            if path.exists():
                current = path.lstat()
                if (
                    not stat.S_ISREG(current.st_mode)
                    or current.st_uid != os.geteuid()
                    or stat.S_IMODE(current.st_mode) != 0o600
                    or current.st_nlink != 1
                ):
                    raise RotationError("owner_only_replace_target_unsafe")
            os.replace(temporary, path)
        else:
            os.link(temporary, path, follow_symlinks=False)
            os.unlink(temporary)
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        raise RotationError("owner_only_output_already_exists") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def secure_unlink(path: Path) -> None:
    try:
        file_stat = path.lstat()
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_uid != os.geteuid()
        or stat.S_IMODE(file_stat.st_mode) != 0o600
        or file_stat.st_nlink != 1
    ):
        raise RotationError("temporary_secret_file_unsafe")
    path.unlink()
    _fsync_directory(path.parent)


class RotationLock(AbstractContextManager["RotationLock"]):
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self.descriptor = -1

    def __enter__(self) -> "RotationLock":
        if not self.path.is_absolute():
            raise RotationError("lock_path_not_absolute")
        _assert_strict_private_parent(self.path)
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            self.descriptor = os.open(self.path, flags, 0o600)
            os.fchmod(self.descriptor, 0o600)
            lock_stat = os.fstat(self.descriptor)
            if (
                not stat.S_ISREG(lock_stat.st_mode)
                or lock_stat.st_uid != os.geteuid()
                or lock_stat.st_nlink != 1
            ):
                raise RotationError("rotation_lock_unsafe")
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(self.descriptor, 0)
            os.write(
                self.descriptor,
                f"{self.run_id}\n".encode("ascii"),
            )
            os.fsync(self.descriptor)
        except BlockingIOError as exc:
            self._close()
            raise RotationError("rotation_already_running") from exc
        except BaseException:
            self._close()
            raise
        return self

    def _close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def __exit__(self, *args: object) -> None:
        if self.descriptor >= 0:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        self._close()


class ReceiptWriter:
    def __init__(self, path: Path, forbidden_secrets: Iterable[str]) -> None:
        if not path.is_absolute():
            raise RotationError("receipt_path_not_absolute")
        _assert_immediate_parent_safe(path)
        if path.exists():
            raise RotationError("receipt_already_exists")
        self.path = path
        self.forbidden = tuple(
            secret.encode("utf-8")
            for secret in forbidden_secrets
            if secret
        )
        self.initialized = False

    def add_forbidden(self, *secrets_to_add: str) -> None:
        self.forbidden = (
            *self.forbidden,
            *(
                secret.encode("utf-8")
                for secret in secrets_to_add
                if secret
            ),
        )

    def write(self, state: ReceiptState) -> None:
        content = (
            json.dumps(
                state.payload(),
                indent=2,
                sort_keys=True,
                separators=(",", ": "),
            )
            + "\n"
        ).encode("utf-8")
        if any(secret in content for secret in self.forbidden):
            raise RotationError("receipt_secret_leak_blocked")
        atomic_write_owner_only(
            self.path,
            content,
            replace=self.initialized,
        )
        self.initialized = True


class HttpTransport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_DIRECT_API_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _NoRedirect(),
)


def urllib_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        method=method,
        headers=dict(headers),
        data=body,
    )
    try:
        with _DIRECT_API_OPENER.open(request, timeout=30) as response:
            if 300 <= response.status < 400:
                raise RotationError("cloudflare_redirect_forbidden")
            payload = response.read(MAX_API_BODY_BYTES + 1)
            if len(payload) > MAX_API_BODY_BYTES:
                raise RotationError("cloudflare_response_too_large")
            return response.status, payload
    except urllib.error.HTTPError as exc:
        # Drain a bounded response, then discard it. Error bodies are never
        # interpolated into exceptions because providers may echo input.
        exc.read(MAX_API_BODY_BYTES + 1)
        if 300 <= exc.code < 400:
            raise RotationError("cloudflare_redirect_forbidden") from exc
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RotationError("cloudflare_transport_failed") from exc


class CloudflareClient:
    def __init__(
        self,
        *,
        account_id: str,
        tunnel_id: str,
        credentials: CloudflareCredentials,
        transport: HttpTransport = urllib_transport,
    ) -> None:
        if not ACCOUNT_ID.fullmatch(account_id):
            raise RotationError("cloudflare_account_id_invalid")
        try:
            uuid.UUID(tunnel_id)
        except ValueError as exc:
            raise RotationError("cloudflare_tunnel_id_invalid") from exc
        self.account_id = account_id
        self.tunnel_id = tunnel_id
        self.credentials = credentials
        self.transport = transport
        self.base = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account_id}/cfd_tunnel/{tunnel_id}"
        )

    def _request(
        self,
        method: str,
        suffix: str = "",
        payload: Mapping[str, object] | None = None,
    ) -> object:
        if method not in {"GET", "PATCH"}:
            raise RotationError("cloudflare_method_forbidden")
        headers = {
            "Accept": "application/json",
            "X-Auth-Email": self.credentials.email.value,
            "X-Auth-Key": self.credentials.global_api_key.value,
        }
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        status, raw = self.transport(method, self.base + suffix, headers, body)
        if status < 200 or status >= 300:
            raise RotationError(f"cloudflare_http_{status}")
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RotationError("cloudflare_response_invalid") from exc
        if not isinstance(document, dict) or document.get("success") is not True:
            raise RotationError("cloudflare_response_unsuccessful")
        return document.get("result")

    def get_token(self) -> SecretText:
        result = self._request("GET", "/token")
        if not isinstance(result, str) or not result:
            raise RotationError("cloudflare_token_response_invalid")
        return SecretText(result)

    def get_snapshot(self) -> ApiSnapshot:
        tunnel = self._request("GET")
        configuration = self._request("GET", "/configurations")
        connections = self._request("GET", "/connections")
        if (
            not isinstance(tunnel, dict)
            or not isinstance(configuration, dict)
            or not isinstance(connections, list)
        ):
            raise RotationError("cloudflare_snapshot_invalid")
        config = configuration.get("config")
        if not isinstance(config, dict):
            raise RotationError("cloudflare_configuration_invalid")
        config_bytes = json.dumps(
            config,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        connectors: list[Connector] = []
        for raw_connector in connections:
            if not isinstance(raw_connector, dict):
                raise RotationError("cloudflare_connections_invalid")
            connector_id = str(raw_connector.get("id") or "")
            try:
                uuid.UUID(connector_id)
            except ValueError as exc:
                raise RotationError("cloudflare_connections_invalid") from exc
            edges = raw_connector.get("conns") or []
            if not isinstance(edges, list):
                raise RotationError("cloudflare_connections_invalid")
            active_edges = 0
            pending_edges = 0
            for edge in edges:
                if not isinstance(edge, dict):
                    raise RotationError("cloudflare_connections_invalid")
                pending_reconnect = edge.get("is_pending_reconnect")
                if not isinstance(pending_reconnect, bool):
                    raise RotationError("cloudflare_connections_invalid")
                if pending_reconnect:
                    pending_edges += 1
                else:
                    active_edges += 1
            connectors.append(
                Connector(
                    connector_id=connector_id,
                    version=str(raw_connector.get("version") or ""),
                    active_edge_count=active_edges,
                    pending_edge_count=pending_edges,
                )
            )
        try:
            config_version = int(configuration.get("version"))
        except (TypeError, ValueError) as exc:
            raise RotationError("cloudflare_configuration_invalid") from exc
        return ApiSnapshot(
            tunnel_id=str(tunnel.get("id") or ""),
            tunnel_name=str(tunnel.get("name") or ""),
            status=str(tunnel.get("status") or ""),
            config_source=str(
                tunnel.get("config_src")
                or ("cloudflare" if tunnel.get("remote_config") is True else "")
            ),
            config_version=config_version,
            config_sha256=hashlib.sha256(config_bytes).hexdigest(),
            connectors=tuple(connectors),
        )

    def rotate_secret(
        self,
        *,
        tunnel_name: str,
        tunnel_secret: SecretText,
    ) -> SecretText:
        result = self._request(
            "PATCH",
            payload={
                "name": tunnel_name,
                "tunnel_secret": tunnel_secret.value,
            },
        )
        if not isinstance(result, dict):
            raise RotationError("cloudflare_rotate_response_invalid")
        token = result.get("token")
        if not isinstance(token, str) or not token:
            # Cloudflare's GET endpoint is the recovery authority if PATCH
            # succeeds without returning the token field.
            return self.get_token()
        return SecretText(token)


def _safe_subprocess_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "HOME",
        "DOCKER_HOST",
        "DOCKER_CONFIG",
        "XDG_RUNTIME_DIR",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


class SafeRunner:
    def __init__(self, forbidden_secrets: Iterable[str]) -> None:
        self.forbidden = tuple(secret for secret in forbidden_secrets if secret)

    def add_forbidden(self, *secrets_to_add: str) -> None:
        self.forbidden = (
            *self.forbidden,
            *(secret for secret in secrets_to_add if secret),
        )

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: int = 180,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        material = "\0".join(argv)
        environment = _safe_subprocess_environment()
        combined_environment = "\0".join(
            f"{key}={value}" for key, value in sorted(environment.items())
        )
        if any(
            secret in material or secret in combined_environment
            for secret in self.forbidden
        ):
            raise RotationError("subprocess_secret_leak_blocked")
        try:
            completed = subprocess.run(
                list(argv),
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RotationError("subprocess_execution_failed") from exc
        combined_output = completed.stdout + completed.stderr
        if any(secret in combined_output for secret in self.forbidden):
            raise RotationError("subprocess_output_secret_leak_blocked")
        if check and completed.returncode != 0:
            raise RotationError("subprocess_nonzero")
        return completed


class DockerClient:
    def __init__(
        self,
        *,
        runner: SafeRunner,
        inputs: RotationInputs,
        environment: ComposeEnvironment,
        run_id: str,
    ) -> None:
        self.runner = runner
        self.inputs = inputs
        self.environment = environment
        self.run_id = run_id
        self._expected_image_id: str | None = None

    def _compose_command(
        self,
        *,
        include_environment: bool,
    ) -> tuple[str, ...]:
        command = [
            "docker",
            "compose",
            "--project-name",
            COMPOSE_PROJECT_NAME,
            "--project-directory",
            str(self.inputs.compose_env_file.parent),
        ]
        if include_environment:
            command.extend(
                (
                    "--env-file",
                    str(self.inputs.compose_env_file),
                )
            )
        command.extend(("-f", str(self.inputs.compose_file)))
        return tuple(command)

    def validate_host_and_compose(
        self,
        *,
        require_rendered: bool = True,
    ) -> None:
        architecture = self.runner.run(
            ("docker", "info", "--format", "{{.Architecture}}")
        ).stdout.strip()
        if architecture not in {"x86_64", "amd64"}:
            raise RotationError("docker_architecture_not_amd64")
        if require_rendered:
            self.runner.run(
                (
                    *self._compose_command(include_environment=True),
                    "config",
                    "-q",
                )
            )
        rendered = self.runner.run(
            (
                *self._compose_command(include_environment=False),
                "config",
                "--no-interpolate",
                "--format",
                "json",
            )
        ).stdout
        try:
            payload = json.loads(rendered)
        except json.JSONDecodeError as exc:
            raise RotationError("compose_contract_invalid") from exc
        if not isinstance(payload, dict) or (
            payload.get("name") != COMPOSE_PROJECT_NAME
        ):
            raise RotationError("compose_project_contract_mismatch")
        services = payload.get("services") if isinstance(payload, dict) else None
        if not isinstance(services, dict):
            raise RotationError("compose_contract_invalid")
        for service_name, container_name in (
            (PRIMARY_SERVICE, PRIMARY_SERVICE),
            (REPLICA_SERVICE, REPLICA_SERVICE),
        ):
            service = services.get(service_name)
            if not isinstance(service, dict):
                raise RotationError("compose_connector_missing")
            if (
                service.get("image") != PINNED_IMAGE
                or service.get("platform") != PINNED_PLATFORM
                or service.get("container_name") != container_name
                or service.get("restart") != "unless-stopped"
                or service.get("read_only") is not True
                or "ALL" not in (service.get("cap_drop") or [])
                or "no-new-privileges:true"
                not in (service.get("security_opt") or [])
            ):
                raise RotationError("compose_connector_contract_mismatch")
            command = service.get("command")
            if not isinstance(command, list):
                raise RotationError("compose_connector_contract_mismatch")
            if (
                "--token-file" not in command
                or "--token" in command
                or TOKEN_TARGET not in command
            ):
                raise RotationError("compose_connector_uses_unsafe_token")
            healthcheck = service.get("healthcheck") or {}
            health_test = (
                healthcheck.get("test")
                if isinstance(healthcheck, dict)
                else None
            )
            if (
                not isinstance(health_test, list)
                or "ready" not in health_test
                or "127.0.0.1:2000" not in health_test
            ):
                raise RotationError("compose_connector_healthcheck_invalid")
            environment = service.get("environment") or {}
            if any(
                "TOKEN" in str(key).upper() for key in dict(environment)
            ):
                raise RotationError("compose_connector_uses_unsafe_token")
            volumes = service.get("volumes")
            if not isinstance(volumes, list):
                raise RotationError("compose_connector_token_mount_invalid")
            token_mounts = [
                volume
                for volume in volumes
                if isinstance(volume, dict)
                and volume.get("target") == TOKEN_TARGET
            ]
            if len(token_mounts) != 1:
                raise RotationError("compose_connector_token_mount_invalid")
            token_mount = token_mounts[0]
            bind = token_mount.get("bind") or {}
            if (
                token_mount.get("type") != "bind"
                or token_mount.get("read_only") is not True
                or not isinstance(bind, dict)
                or bind.get("create_host_path") is not False
                or "CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE"
                not in str(token_mount.get("source") or "")
            ):
                raise RotationError("compose_connector_token_mount_invalid")

    def _inspect_raw(self, name: str, *, allow_missing: bool = False) -> dict[str, Any] | None:
        result = self.runner.run(
            ("docker", "inspect", name),
            check=False,
        )
        if result.returncode != 0:
            if allow_missing:
                return None
            raise RotationError("docker_container_missing")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RotationError("docker_inspect_invalid") from exc
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise RotationError("docker_inspect_invalid")
        return payload[0]

    def verify_connector_container(self, name: str) -> None:
        payload = self._inspect_raw(name)
        assert payload is not None
        state = payload.get("State") or {}
        if state.get("Status") != "running":
            raise RotationError("docker_connector_not_running")
        health = state.get("Health")
        if isinstance(health, dict) and health.get("Status") != "healthy":
            raise RotationError("docker_connector_not_healthy")
        self._verify_token_file_container(
            payload,
            expected_source=self.inputs.token_file,
            expected_service=name,
        )

    def _pinned_image_id(self) -> str:
        if self._expected_image_id is None:
            image_id = self.runner.run(
                (
                    "docker",
                    "image",
                    "inspect",
                    "--format",
                    "{{.Id}}",
                    PINNED_IMAGE,
                )
            ).stdout.strip()
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                raise RotationError("docker_pinned_image_id_invalid")
            self._expected_image_id = image_id
        return self._expected_image_id

    def _verify_token_file_container(
        self,
        payload: Mapping[str, Any],
        *,
        expected_source: Path,
        expected_service: str | None = None,
    ) -> None:
        config = payload.get("Config") or {}
        host_config = payload.get("HostConfig") or {}
        state = payload.get("State") or {}
        command = [str(value) for value in (config.get("Cmd") or [])]
        environment = [str(value) for value in (config.get("Env") or [])]
        mounts = payload.get("Mounts") or []
        networks = (payload.get("NetworkSettings") or {}).get("Networks") or {}
        if config.get("Image") != PINNED_IMAGE:
            raise RotationError("docker_connector_image_mismatch")
        if payload.get("Image") != self._pinned_image_id():
            raise RotationError("docker_connector_image_id_mismatch")
        if (
            "--token-file" not in command
            or "--token" in command
            or TOKEN_TARGET not in command
        ):
            raise RotationError("docker_connector_uses_unsafe_token")
        if any(
            "TOKEN" in value.partition("=")[0].upper()
            for value in environment
        ):
            raise RotationError("docker_connector_uses_unsafe_token")
        if str(config.get("User") or "") != (
            f"{self.environment.runtime_uid}:{self.environment.runtime_gid}"
        ):
            raise RotationError("docker_connector_identity_mismatch")
        if host_config.get("ReadonlyRootfs") is not True:
            raise RotationError("docker_connector_rootfs_writable")
        if (host_config.get("RestartPolicy") or {}).get("Name") != "unless-stopped":
            raise RotationError("docker_connector_restart_policy_invalid")
        cap_drop = {
            str(value).upper()
            for value in (host_config.get("CapDrop") or [])
        }
        security_options = {
            str(value) for value in (host_config.get("SecurityOpt") or [])
        }
        if "ALL" not in cap_drop:
            raise RotationError("docker_connector_capabilities_invalid")
        if not any(
            value.startswith("no-new-privileges")
            for value in security_options
        ):
            raise RotationError("docker_connector_security_options_invalid")
        health = state.get("Health")
        health_test = (config.get("Healthcheck") or {}).get("Test")
        if (
            not isinstance(health, dict)
            or health.get("Status") != "healthy"
            or not isinstance(health_test, list)
            or "ready" not in health_test
        ):
            raise RotationError("docker_connector_healthcheck_invalid")
        labels = config.get("Labels") or {}
        if expected_service is not None and (
            labels.get("com.docker.compose.service") != expected_service
            or labels.get("com.docker.compose.project")
            != COMPOSE_PROJECT_NAME
            or labels.get("com.docker.compose.project.working_dir")
            != str(self.inputs.compose_env_file.parent)
            or labels.get("com.docker.compose.project.config_files")
            != str(self.inputs.compose_file)
        ):
            raise RotationError("compose_connector_ownership_mismatch")
        expected_source_text = str(expected_source.resolve(strict=True))
        matching_mounts = [
            mount
            for mount in mounts
            if mount.get("Destination") == TOKEN_TARGET
        ]
        if len(matching_mounts) != 1:
            raise RotationError("docker_connector_token_mount_invalid")
        mount = matching_mounts[0]
        if (
            mount.get("Type") != "bind"
            or
            mount.get("RW") is not False
            or str(Path(str(mount.get("Source") or "")).resolve(strict=True))
            != expected_source_text
        ):
            raise RotationError("docker_connector_token_mount_invalid")
        if self.environment.network not in networks:
            raise RotationError("docker_connector_network_invalid")

    def ensure_connector_absent(self, name: str) -> None:
        if name not in {PRIMARY_SERVICE, REPLICA_SERVICE}:
            raise RotationError("compose_service_forbidden")
        if self._inspect_raw(name, allow_missing=True) is not None:
            raise RotationError("bootstrap_canonical_connector_already_exists")

    def verify_legacy_container(self, expected_token: SecretText) -> None:
        # Full inspect is intentionally captured only in-process because the
        # legacy argv contains the token. It is never returned through
        # SafeRunner, logs, receipts, or exception text.
        try:
            completed = subprocess.run(
                ["docker", "inspect", LEGACY_CONTAINER],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                env=_safe_subprocess_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RotationError("legacy_connector_inspect_failed") from exc
        if completed.returncode != 0 or len(completed.stdout) > MAX_API_BODY_BYTES:
            raise RotationError("legacy_connector_inspect_failed")
        try:
            decoded = completed.stdout.decode("utf-8", "strict")
            document = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RotationError("legacy_connector_inspect_invalid") from exc
        if (
            not isinstance(document, list)
            or len(document) != 1
            or not isinstance(document[0], dict)
        ):
            raise RotationError("legacy_connector_inspect_invalid")
        payload = document[0]
        config = payload.get("Config") or {}
        state = payload.get("State") or {}
        command = [str(value) for value in (config.get("Cmd") or [])]
        token_indexes = [
            index for index, value in enumerate(command) if value == "--token"
        ]
        token_matches = (
            len(token_indexes) == 1
            and token_indexes[0] + 1 < len(command)
            and hmac.compare_digest(
                command[token_indexes[0] + 1],
                expected_token.value,
            )
        )
        environment = [str(value) for value in (config.get("Env") or [])]
        labels = config.get("Labels") or {}
        networks = (payload.get("NetworkSettings") or {}).get("Networks") or {}
        canonical_working_dir = self.inputs.compose_env_file.parent
        canonical_legacy_compose = (
            canonical_working_dir / "docker-compose.public-edge.yml"
        )
        if (
            payload.get("Name") != f"/{LEGACY_CONTAINER}"
            or state.get("Status") != "running"
            or not str(config.get("Image") or "").startswith(
                "cloudflare/cloudflared:"
            )
            or not token_matches
            or "--token-file" in command
            or any(
                "TOKEN" in value.partition("=")[0].upper()
                for value in environment
            )
            or labels.get("com.docker.compose.service") != PRIMARY_SERVICE
            or labels.get("com.docker.compose.project")
            != COMPOSE_PROJECT_NAME
            or labels.get("com.docker.compose.project.working_dir")
            != str(canonical_working_dir)
            or labels.get("com.docker.compose.project.config_files")
            != str(canonical_legacy_compose)
            or not isinstance(networks, dict)
            or self.environment.network not in networks
        ):
            raise RotationError("legacy_connector_contract_failed")

    def ensure_canary_absent(self) -> None:
        if self._inspect_raw(CANARY_CONTAINER, allow_missing=True) is not None:
            raise RotationError("rotation_canary_already_exists")
        if (
            any(
                self._inspect_raw(name, allow_missing=True) is not None
                for name in MIGRATION_CANARY_CONTAINERS
            )
        ):
            raise RotationError("migration_canary_already_exists")

    def _start_canary(
        self,
        *,
        name: str,
        token_file: Path,
        label_key: str,
    ) -> None:
        self.runner.run(
            (
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--restart",
                "unless-stopped",
                "--network",
                self.environment.network,
                "--add-host",
                "host.docker.internal:host-gateway",
                "--user",
                f"{self.environment.runtime_uid}:{self.environment.runtime_gid}",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--health-cmd",
                (
                    "cloudflared tunnel --metrics 127.0.0.1:2000 ready"
                ),
                "--health-interval",
                "15s",
                "--health-timeout",
                "5s",
                "--health-retries",
                "3",
                "--health-start-period",
                "15s",
                "--mount",
                (
                    "type=bind,source="
                    f"{token_file},target={TOKEN_TARGET},readonly"
                ),
                "--label",
                f"{label_key}={self.run_id}",
                PINNED_IMAGE,
                "tunnel",
                "--no-autoupdate",
                "--metrics",
                "0.0.0.0:2000",
                "run",
                "--token-file",
                TOKEN_TARGET,
            )
        )

    def start_canary(self, token_file: Path) -> None:
        self._start_canary(
            name=CANARY_CONTAINER,
            token_file=token_file,
            label_key="run.chummer.cloudflare-rotation",
        )

    def start_migration_canary(
        self,
        name: str,
        token_file: Path,
    ) -> None:
        if name not in MIGRATION_CANARY_CONTAINERS:
            raise RotationError("migration_canary_name_forbidden")
        self._start_canary(
            name=name,
            token_file=token_file,
            label_key="run.chummer.cloudflare-migration",
        )

    def _verify_canary_running(
        self,
        *,
        name: str,
        token_file: Path,
        label_key: str,
    ) -> None:
        payload = self._inspect_raw(name)
        assert payload is not None
        labels = (payload.get("Config") or {}).get("Labels") or {}
        if labels.get(label_key) != self.run_id:
            raise RotationError("rotation_canary_ownership_mismatch")
        if (payload.get("State") or {}).get("Status") != "running":
            raise RotationError("rotation_canary_not_running")
        self._verify_token_file_container(
            payload,
            expected_source=token_file,
        )

    def verify_canary_running(self) -> None:
        self._verify_canary_running(
            name=CANARY_CONTAINER,
            token_file=Path(
                self.inputs.token_file.parent
                / f".{self.inputs.token_file.name}.rotation-{self.run_id}.next"
            ),
            label_key="run.chummer.cloudflare-rotation",
        )

    def verify_migration_canary_running(self, name: str) -> None:
        if name not in MIGRATION_CANARY_CONTAINERS:
            raise RotationError("migration_canary_name_forbidden")
        self._verify_canary_running(
            name=name,
            token_file=self.inputs.token_file,
            label_key="run.chummer.cloudflare-migration",
        )

    def _remove_canary(self, *, name: str, label_key: str) -> None:
        payload = self._inspect_raw(name, allow_missing=True)
        if payload is None:
            return
        labels = (payload.get("Config") or {}).get("Labels") or {}
        if labels.get(label_key) != self.run_id:
            raise RotationError("rotation_canary_ownership_mismatch")
        self.runner.run(
            ("docker", "stop", "--time", "30", name),
            check=False,
        )
        self.runner.run(("docker", "rm", name))

    def remove_canary(self) -> None:
        self._remove_canary(
            name=CANARY_CONTAINER,
            label_key="run.chummer.cloudflare-rotation",
        )

    def remove_migration_canary(self, name: str) -> None:
        if name not in MIGRATION_CANARY_CONTAINERS:
            raise RotationError("migration_canary_name_forbidden")
        self._remove_canary(
            name=name,
            label_key="run.chummer.cloudflare-migration",
        )

    def recreate_service(self, service_name: str) -> None:
        if service_name not in {PRIMARY_SERVICE, REPLICA_SERVICE}:
            raise RotationError("compose_service_forbidden")
        self.runner.run(
            (
                *self._compose_command(include_environment=True),
                "up",
                "-d",
                "--no-deps",
                "--force-recreate",
                service_name,
            ),
            timeout=CONTAINER_HEALTH_TIMEOUT_SECONDS,
        )

    def remove_compose_service(self, service_name: str) -> None:
        if service_name not in {PRIMARY_SERVICE, REPLICA_SERVICE}:
            raise RotationError("compose_service_forbidden")
        payload = self._inspect_raw(service_name, allow_missing=True)
        if payload is None:
            return
        labels = (payload.get("Config") or {}).get("Labels") or {}
        if (
            labels.get("com.docker.compose.service") != service_name
            or labels.get("com.docker.compose.project")
            != COMPOSE_PROJECT_NAME
            or labels.get("com.docker.compose.project.working_dir")
            != str(self.inputs.compose_env_file.parent)
            or labels.get("com.docker.compose.project.config_files")
            != str(self.inputs.compose_file)
        ):
            raise RotationError("compose_connector_ownership_mismatch")
        self.runner.run(
            (
                *self._compose_command(include_environment=True),
                "rm",
                "--stop",
                "--force",
                service_name,
            )
        )
        if self._inspect_raw(service_name, allow_missing=True) is not None:
            raise RotationError("compose_connector_remove_failed")

    def retire_legacy_container(self, expected_token: SecretText) -> None:
        self.verify_legacy_container(expected_token)
        self.runner.run(
            ("docker", "stop", "--time", "30", LEGACY_CONTAINER)
        )
        stopped = self.runner.run(
            (
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}}",
                LEGACY_CONTAINER,
            )
        ).stdout.strip()
        if stopped != "exited":
            raise RotationError("legacy_connector_stop_failed")
        self.runner.run(("docker", "rm", LEGACY_CONTAINER))


class PublicProber:
    def __init__(self, specs: Sequence[ProbeSpec] = DEFAULT_PROBES) -> None:
        self.specs = tuple(specs)
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirect(),
        )

    def probe(self) -> tuple[ProbeResult, ...]:
        results: list[ProbeResult] = []
        for spec in self.specs:
            request = urllib.request.Request(
                spec.url,
                headers={"User-Agent": "Chummer-Cloudflare-Rotation/1"},
            )
            try:
                with self.opener.open(request, timeout=30) as response:
                    status = response.status
                    body = response.read(MAX_HTTP_BODY_BYTES + 1)
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read(MAX_HTTP_BODY_BYTES + 1)
            except (urllib.error.URLError, TimeoutError) as exc:
                raise RotationError("public_probe_transport_failed") from exc
            if len(body) > MAX_HTTP_BODY_BYTES:
                raise RotationError("public_probe_body_too_large")
            lowered = body[:65536].lower()
            if (
                status not in spec.expected_statuses
                or b"error 1033" in lowered
                or b"cloudflare tunnel error" in lowered
            ):
                raise RotationError("public_probe_failed")
            results.append(
                ProbeResult(
                    url=spec.url,
                    status=status,
                    body_sha256=hashlib.sha256(body).hexdigest(),
                )
            )
        return tuple(results)

    def verify_stable(
        self,
        baseline: Sequence[ProbeResult],
    ) -> tuple[ProbeResult, ...]:
        current = self.probe()
        baseline_by_url = {result.url: result for result in baseline}
        for spec, result in zip(self.specs, current, strict=True):
            previous = baseline_by_url.get(spec.url)
            if previous is None:
                raise RotationError("public_probe_baseline_missing")
            if spec.stable_body and result.body_sha256 != previous.body_sha256:
                raise RotationError("stable_public_body_changed")
        return current


class Timing:
    def wait_for(
        self,
        verifier: Callable[[], Any],
        *,
        timeout_seconds: int,
        failure_code: str,
    ) -> Any:
        deadline = time.monotonic() + timeout_seconds
        last_error: RotationError | None = None
        while True:
            try:
                return verifier()
            except RotationError as exc:
                last_error = exc
            if time.monotonic() >= deadline:
                raise RotationError(failure_code) from last_error
            time.sleep(min(MONITOR_INTERVAL_SECONDS, max(0.1, deadline - time.monotonic())))

    def dwell_for(
        self,
        seconds: int,
        verifier: Callable[[], Any],
    ) -> None:
        deadline = time.monotonic() + seconds
        while True:
            verifier()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(MONITOR_INTERVAL_SECONDS, remaining))

    def dwell(self, verifier: Callable[[], Any]) -> None:
        self.dwell_for(MANDATORY_DWELL_SECONDS, verifier)


class LegacyBootstrapEngine:
    """Migrate the exact one-connector legacy state into token-file HA."""

    def __init__(
        self,
        *,
        inputs: RotationInputs,
        migration: LegacyComposeMigration,
        token_metadata: TunnelTokenMetadata,
        api: CloudflareClient,
        docker: DockerClient,
        prober: PublicProber,
        timing: Timing,
        receipt: ReceiptWriter,
        state: ReceiptState,
    ) -> None:
        self.inputs = inputs
        self.migration = migration
        self.token_metadata = token_metadata
        self.api = api
        self.docker = docker
        self.prober = prober
        self.timing = timing
        self.receipt = receipt
        self.state = state
        self.baseline_snapshot: ApiSnapshot | None = None
        self.baseline_probes: tuple[ProbeResult, ...] = ()
        self.token_file_created = False
        self.started_canaries: list[str] = []
        self.environment_rewritten = False
        self.primary_started = False
        self.replica_started = False
        self.commit_started = False

    def _checkpoint(self, phase: str) -> None:
        self.state.phase = phase
        self.receipt.write(self.state)

    def _validate_snapshot(
        self,
        snapshot: ApiSnapshot,
        *,
        minimum_connectors: int,
        required_ids: Iterable[str] = (),
        forbidden_ids: Iterable[str] = (),
    ) -> None:
        if (
            snapshot.tunnel_id != self.inputs.tunnel_id
            or snapshot.tunnel_name != self.inputs.tunnel_name
            or snapshot.status != "healthy"
            or snapshot.config_source != "cloudflare"
        ):
            raise RotationError("tunnel_snapshot_contract_failed")
        if self.baseline_snapshot is not None and (
            snapshot.config_version != self.baseline_snapshot.config_version
            or snapshot.config_sha256 != self.baseline_snapshot.config_sha256
        ):
            raise RotationError("tunnel_configuration_changed")
        active = snapshot.active_connector_ids
        if len(active) < minimum_connectors:
            raise RotationError("insufficient_active_connectors")
        if not set(required_ids).issubset(active):
            raise RotationError("required_connector_disappeared")
        if set(forbidden_ids) & active:
            raise RotationError("retired_connector_still_active")

    def _health(
        self,
        *,
        minimum_connectors: int,
        required_ids: Iterable[str] = (),
        forbidden_ids: Iterable[str] = (),
    ) -> ApiSnapshot:
        snapshot = self.api.get_snapshot()
        self._validate_snapshot(
            snapshot,
            minimum_connectors=minimum_connectors,
            required_ids=required_ids,
            forbidden_ids=forbidden_ids,
        )
        self.prober.verify_stable(self.baseline_probes)
        return snapshot

    def _precommit_health(
        self,
        *,
        minimum_connectors: int,
        required_ids: Iterable[str] = (),
    ) -> ApiSnapshot:
        if not self.api.get_token().matches(self.migration.old_token):
            raise RotationError("migration_remote_token_changed")
        return self._health(
            minimum_connectors=minimum_connectors,
            required_ids=required_ids,
        )

    def _wait_for_new_connector(
        self,
        previous_ids: frozenset[str],
        *,
        required_ids: Iterable[str],
        container_verifier: Callable[[], None],
        failure_code: str,
    ) -> tuple[ApiSnapshot, str]:
        def verifier() -> tuple[ApiSnapshot, str]:
            container_verifier()
            snapshot = self._health(
                minimum_connectors=len(set(required_ids)) + 1,
                required_ids=required_ids,
            )
            added = sorted(snapshot.active_connector_ids - previous_ids)
            if len(added) != 1:
                raise RotationError("new_connector_identity_ambiguous")
            return snapshot, added[0]

        return self.timing.wait_for(
            verifier,
            timeout_seconds=CONNECTOR_JOIN_TIMEOUT_SECONDS,
            failure_code=failure_code,
        )

    def _preflight(self) -> None:
        self.state.migration_status = "preflight"
        self._checkpoint("legacy_migration_preflight")
        self.docker.validate_host_and_compose(require_rendered=False)
        self.docker.ensure_connector_absent(REPLICA_SERVICE)
        self.docker.ensure_canary_absent()
        self.docker.verify_legacy_container(self.migration.old_token)
        remote_token = self.api.get_token()
        if not remote_token.matches(self.migration.old_token):
            raise RotationError("local_remote_token_mismatch")
        snapshot = self.api.get_snapshot()
        self.baseline_snapshot = snapshot
        self._validate_snapshot(snapshot, minimum_connectors=1)
        if len(snapshot.active_connector_ids) != 1:
            raise RotationError("legacy_connector_count_invalid")
        self.baseline_probes = self.prober.probe()
        self.state.tunnel_id = snapshot.tunnel_id
        self.state.tunnel_name = snapshot.tunnel_name
        self.state.account_id_sha256 = hashlib.sha256(
            self.token_metadata.account_id.encode("ascii")
        ).hexdigest()
        self.state.before_token_sha256 = self.migration.old_token.sha256
        self.state.config_version = snapshot.config_version
        self.state.config_sha256 = snapshot.config_sha256
        self.state.baseline_connector_ids = sorted(
            snapshot.active_connector_ids
        )
        self.state.checks = [
            result.receipt_payload(
                include_digest=next(
                    spec.stable_body
                    for spec in self.prober.specs
                    if spec.url == result.url
                )
            )
            for result in self.baseline_probes
        ]
        self.state.event(
            "legacy_baseline_verified",
            activeConnectorCount=len(snapshot.active_connector_ids),
        )
        self._checkpoint("legacy_migration_baseline_verified")

    def audit(self) -> None:
        self._preflight()
        self.state.status = "audit_passed"
        self.state.migration_status = "audit_passed"
        self.state.completed_at = utc_now()
        self.state.event("legacy_migration_audit_passed")
        self._checkpoint("completed")

    def execute(self) -> None:
        self._preflight()
        assert self.baseline_snapshot is not None
        legacy_ids = self.baseline_snapshot.active_connector_ids
        try:
            self.token_file_created = True
            atomic_write_owner_only(
                self.inputs.token_file,
                (self.migration.old_token.value + "\n").encode("ascii"),
                replace=False,
            )
            self.state.event("owner_only_token_file_staged")
            self._checkpoint("legacy_token_file_staged")

            overlap_ids = set(legacy_ids)
            canary_ids: set[str] = set()
            canary_connector_ids: dict[str, str] = {}
            for index, canary_name in enumerate(
                MIGRATION_CANARY_CONTAINERS,
                start=1,
            ):
                previous = self.api.get_snapshot().active_connector_ids
                self.started_canaries.append(canary_name)
                self.docker.start_migration_canary(
                    canary_name,
                    self.inputs.token_file,
                )
                canary_snapshot, canary_id = self._wait_for_new_connector(
                    previous,
                    required_ids=overlap_ids,
                    container_verifier=lambda name=canary_name: (
                        self.docker.verify_migration_canary_running(name)
                    ),
                    failure_code=(
                        f"migration_canary_{index}_join_timeout"
                    ),
                )
                canary_ids.add(canary_id)
                canary_connector_ids[canary_name] = canary_id
                overlap_ids.add(canary_id)
                self.state.event(
                    "old_token_migration_canary_joined",
                    slot=index,
                    connectorId=canary_id,
                    activeConnectorCount=len(
                        canary_snapshot.active_connector_ids
                    ),
                )
                self._checkpoint(
                    f"legacy_migration_canary_{index}_joined"
                )
            self.timing.dwell_for(
                MIGRATION_DWELL_SECONDS,
                lambda: self._precommit_health(
                    minimum_connectors=len(overlap_ids),
                    required_ids=overlap_ids,
                ),
            )
            self.state.event(
                "legacy_migration_overlap_proved",
                dwellSeconds=MIGRATION_DWELL_SECONDS,
            )
            self._checkpoint("legacy_migration_overlap_proved")

            self.environment_rewritten = True
            atomic_write_owner_only(
                self.inputs.compose_env_file,
                self.migration.rewritten_bytes,
                replace=True,
            )
            parsed_environment = parse_compose_environment(
                self.inputs.compose_env_file,
                expected_token_file=self.inputs.token_file,
                token_stat=self.inputs.token_file.stat(),
            )
            if parsed_environment != self.migration.environment:
                raise RotationError("compose_env_migration_verification_failed")
            self.state.event("legacy_dotenv_token_scrubbed")
            self._checkpoint("legacy_dotenv_scrubbed")
            self.docker.validate_host_and_compose(require_rendered=True)

            previous = self.api.get_snapshot().active_connector_ids
            self.replica_started = True
            self.docker.recreate_service(REPLICA_SERVICE)
            replica_snapshot, replica_id = self._wait_for_new_connector(
                previous,
                required_ids=overlap_ids,
                container_verifier=lambda: (
                    self.docker.verify_connector_container(REPLICA_SERVICE)
                ),
                failure_code="migration_replica_join_timeout",
            )
            precommit_ids = set(overlap_ids)
            precommit_ids.add(replica_id)
            self.state.event(
                "token_file_replica_joined",
                connectorId=replica_id,
                activeConnectorCount=len(
                    replica_snapshot.active_connector_ids
                ),
            )
            self._checkpoint("legacy_migration_replica_joined")
            self.timing.dwell_for(
                MIGRATION_DWELL_SECONDS,
                lambda: self._precommit_health(
                    minimum_connectors=len(precommit_ids),
                    required_ids=precommit_ids,
                ),
            )
            self.state.event(
                "token_file_ha_overlap_proved",
                dwellSeconds=MIGRATION_DWELL_SECONDS,
            )
            self._checkpoint("legacy_migration_ha_proved")

            self._checkpoint("legacy_migration_ready_to_retire_legacy")
            if not self.api.get_token().matches(self.migration.old_token):
                raise RotationError("migration_remote_token_changed")

            # Migration commit: two pinned temporary token-file connectors and
            # the canonical replica are proven before the legacy process gives
            # up the canonical primary name.
            self.state.migration_commit_started = True
            self._checkpoint("legacy_migration_commit_started")
            self.commit_started = True
            self.docker.retire_legacy_container(
                self.migration.old_token
            )
            self.state.legacy_container_removed = True
            takeover_required = set(canary_ids)
            takeover_required.add(replica_id)
            self.timing.wait_for(
                lambda: self._health(
                    minimum_connectors=len(takeover_required),
                    required_ids=takeover_required,
                    forbidden_ids=legacy_ids,
                ),
                timeout_seconds=CONNECTOR_JOIN_TIMEOUT_SECONDS,
                failure_code="legacy_connector_retirement_timeout",
            )

            previous = self.api.get_snapshot().active_connector_ids
            self.primary_started = True
            self.docker.recreate_service(PRIMARY_SERVICE)
            primary_snapshot, primary_id = self._wait_for_new_connector(
                previous,
                required_ids=takeover_required,
                container_verifier=lambda: (
                    self.docker.verify_connector_container(PRIMARY_SERVICE)
                ),
                failure_code="migration_primary_join_timeout",
            )
            permanent_ids = {primary_id, replica_id}
            with_primary = set(takeover_required)
            with_primary.add(primary_id)
            self.state.event(
                "token_file_primary_joined",
                connectorId=primary_id,
                activeConnectorCount=len(
                    primary_snapshot.active_connector_ids
                ),
            )
            self._checkpoint("legacy_migration_primary_joined")
            self.timing.dwell_for(
                MIGRATION_DWELL_SECONDS,
                lambda: self._health(
                    minimum_connectors=len(with_primary),
                    required_ids=with_primary,
                    forbidden_ids=legacy_ids,
                ),
            )
            self.state.event(
                "canonical_token_file_ha_proved",
                dwellSeconds=MIGRATION_DWELL_SECONDS,
            )
            self._checkpoint("legacy_migration_canonical_ha_proved")

            retired_canary_ids: set[str] = set()
            remaining_canary_ids = set(canary_ids)
            for canary_name in MIGRATION_CANARY_CONTAINERS:
                canary_id = canary_connector_ids[canary_name]
                self.docker.remove_migration_canary(canary_name)
                retired_canary_ids.add(canary_id)
                remaining_canary_ids.remove(canary_id)
                required = permanent_ids | remaining_canary_ids
                self.timing.wait_for(
                    lambda required_ids=set(required),
                    forbidden=set(retired_canary_ids) | set(legacy_ids): (
                        self._health(
                            minimum_connectors=len(required_ids),
                            required_ids=required_ids,
                            forbidden_ids=forbidden,
                        )
                    ),
                    timeout_seconds=CONNECTOR_JOIN_TIMEOUT_SECONDS,
                    failure_code="migration_canary_retirement_timeout",
                )
            final_snapshot = self.api.get_snapshot()
            self._validate_snapshot(
                final_snapshot,
                minimum_connectors=MINIMUM_ACTIVE_CONNECTORS,
                required_ids=permanent_ids,
                forbidden_ids=set(legacy_ids) | canary_ids,
            )
            self.prober.verify_stable(self.baseline_probes)
            if final_snapshot.active_connector_ids != permanent_ids:
                raise RotationError("unexpected_connector_after_migration")
            self.docker.verify_connector_container(PRIMARY_SERVICE)
            self.docker.verify_connector_container(REPLICA_SERVICE)
            self.state.final_connector_ids = sorted(permanent_ids)
            self.state.migration_status = "passed"
            self.state.event("legacy_token_file_ha_migration_completed")
            self._checkpoint("legacy_migration_completed")
        except BaseException:
            if not self.commit_started:
                self._rollback()
            raise

    def _rollback(self) -> None:
        self.state.migration_status = "rolling_back"
        self.state.event("legacy_migration_rollback_started")
        try:
            self.receipt.write(self.state)
        except BaseException:
            pass
        try:
            if self.replica_started:
                self.docker.remove_compose_service(REPLICA_SERVICE)
            for canary_name in reversed(self.started_canaries):
                self.docker.remove_migration_canary(canary_name)
            if self.environment_rewritten:
                atomic_write_owner_only(
                    self.inputs.compose_env_file,
                    self.migration.original_bytes,
                    replace=True,
                )
            if self.token_file_created:
                secure_unlink(self.inputs.token_file)
            self.docker.verify_legacy_container(self.migration.old_token)
            if not self.api.get_token().matches(self.migration.old_token):
                raise RotationError("migration_rollback_remote_token_mismatch")
            assert self.baseline_snapshot is not None
            self._health(
                minimum_connectors=1,
                required_ids=self.baseline_snapshot.active_connector_ids,
            )
            self.state.migration_status = "rolled_back"
            self.state.migration_commit_started = False
            self.state.rollback_status = "passed"
            self.state.event("legacy_migration_rollback_completed")
            self.receipt.write(self.state)
        except BaseException as exc:
            self.state.migration_status = "rollback_failed"
            self.state.rollback_status = "failed"
            self.state.failure_code = "migration_rollback_failed"
            self.state.event("legacy_migration_rollback_failed")
            try:
                self.receipt.write(self.state)
            except BaseException:
                pass
            raise RotationError("migration_rollback_failed") from exc


class RotationEngine:
    def __init__(
        self,
        *,
        inputs: RotationInputs,
        old_token: SecretText,
        token_metadata: TunnelTokenMetadata,
        api: CloudflareClient,
        docker: DockerClient,
        prober: PublicProber,
        timing: Timing,
        receipt: ReceiptWriter,
        state: ReceiptState,
        secret_factory: Callable[[], bytes] = lambda: secrets.token_bytes(32),
    ) -> None:
        self.inputs = inputs
        self.old_token = old_token
        self.token_metadata = token_metadata
        self.api = api
        self.docker = docker
        self.prober = prober
        self.timing = timing
        self.receipt = receipt
        self.state = state
        self.secret_factory = secret_factory
        self.baseline_snapshot: ApiSnapshot | None = None
        self.baseline_probes: tuple[ProbeResult, ...] = ()
        self.stage_file = (
            inputs.token_file.parent
            / f".{inputs.token_file.name}.rotation-{state.run_id}.next"
        )
        self.new_token: SecretText | None = None
        self.canary_id: str | None = None
        self.commit_started = False
        self.rotation_applied = False

    def _checkpoint(self, phase: str) -> None:
        self.state.phase = phase
        self.receipt.write(self.state)

    def _validate_snapshot(
        self,
        snapshot: ApiSnapshot,
        *,
        minimum_connectors: int,
        required_ids: Iterable[str] = (),
    ) -> None:
        if (
            snapshot.tunnel_id != self.inputs.tunnel_id
            or snapshot.tunnel_name != self.inputs.tunnel_name
            or snapshot.status != "healthy"
            or snapshot.config_source != "cloudflare"
        ):
            raise RotationError("tunnel_snapshot_contract_failed")
        if self.baseline_snapshot is not None and (
            snapshot.config_version != self.baseline_snapshot.config_version
            or snapshot.config_sha256 != self.baseline_snapshot.config_sha256
        ):
            raise RotationError("tunnel_configuration_changed")
        active = snapshot.active_connector_ids
        if any(
            connector.active
            and connector.version != PINNED_CLOUDFLARED_VERSION
            for connector in snapshot.connectors
        ):
            raise RotationError("active_connector_version_mismatch")
        if len(active) < minimum_connectors:
            raise RotationError("insufficient_active_connectors")
        if not set(required_ids).issubset(active):
            raise RotationError("required_connector_disappeared")

    def _api_and_public_health(
        self,
        *,
        minimum_connectors: int,
        required_ids: Iterable[str] = (),
    ) -> ApiSnapshot:
        snapshot = self.api.get_snapshot()
        self._validate_snapshot(
            snapshot,
            minimum_connectors=minimum_connectors,
            required_ids=required_ids,
        )
        self.prober.verify_stable(self.baseline_probes)
        return snapshot

    def _wait_for_new_connector(
        self,
        previous_ids: frozenset[str],
        *,
        required_ids: Iterable[str] = (),
    ) -> tuple[ApiSnapshot, str]:
        def verifier() -> tuple[ApiSnapshot, str]:
            self.docker.verify_canary_running()
            snapshot = self._api_and_public_health(
                minimum_connectors=MINIMUM_ACTIVE_CONNECTORS,
                required_ids=required_ids,
            )
            added = sorted(snapshot.active_connector_ids - previous_ids)
            if len(added) != 1:
                raise RotationError("new_connector_identity_ambiguous")
            return snapshot, added[0]

        return self.timing.wait_for(
            verifier,
            timeout_seconds=CONNECTOR_JOIN_TIMEOUT_SECONDS,
            failure_code="new_connector_join_timeout",
        )

    def audit(self) -> None:
        self._preflight()
        self.state.status = "audit_passed"
        self.state.completed_at = utc_now()
        self.state.event("audit_passed")
        self._checkpoint("completed")

    def _preflight(self) -> None:
        self._checkpoint("preflight")
        self.docker.validate_host_and_compose()
        self.docker.verify_connector_container(PRIMARY_SERVICE)
        self.docker.verify_connector_container(REPLICA_SERVICE)
        self.docker.ensure_canary_absent()
        remote_token = self.api.get_token()
        if not remote_token.matches(self.old_token):
            raise RotationError("local_remote_token_mismatch")
        snapshot = self.api.get_snapshot()
        self.baseline_snapshot = snapshot
        self._validate_snapshot(
            snapshot,
            minimum_connectors=MINIMUM_ACTIVE_CONNECTORS,
        )
        if len(snapshot.active_connector_ids) != MINIMUM_ACTIVE_CONNECTORS:
            raise RotationError("unexpected_active_connector_topology")
        self.baseline_probes = self.prober.probe()
        self.state.tunnel_id = snapshot.tunnel_id
        self.state.tunnel_name = snapshot.tunnel_name
        self.state.account_id_sha256 = hashlib.sha256(
            self.token_metadata.account_id.encode("ascii")
        ).hexdigest()
        self.state.before_token_sha256 = self.old_token.sha256
        self.state.config_version = snapshot.config_version
        self.state.config_sha256 = snapshot.config_sha256
        self.state.baseline_connector_ids = sorted(snapshot.active_connector_ids)
        self.state.checks = [
            result.receipt_payload(
                include_digest=next(
                    spec.stable_body
                    for spec in self.prober.specs
                    if spec.url == result.url
                )
            )
            for result in self.baseline_probes
        ]
        self.state.event(
            "baseline_verified",
            activeConnectorCount=len(snapshot.active_connector_ids),
        )
        self._checkpoint("baseline_verified")

    def execute(self) -> None:
        self._preflight()
        assert self.baseline_snapshot is not None
        baseline_ids = self.baseline_snapshot.active_connector_ids
        try:
            self._rotate_and_prove_canary(baseline_ids)
            self._promote_new_token(baseline_ids)
        except BaseException:
            if self.rotation_applied and not self.commit_started:
                self._rollback_before_commit(baseline_ids)
            raise
        self.state.status = "passed"
        self.state.completed_at = utc_now()
        self.state.rollback_status = "not_required"
        self.state.event("rotation_completed")
        self._checkpoint("completed")

    def _rotate_and_prove_canary(
        self,
        baseline_ids: frozenset[str],
    ) -> None:
        raw_secret = self.secret_factory()
        if len(raw_secret) < 32:
            raise RotationError("generated_tunnel_secret_too_short")
        new_secret = SecretText(base64.b64encode(raw_secret).decode("ascii"))
        self.receipt.add_forbidden(new_secret.value)
        self.docker.runner.add_forbidden(new_secret.value)
        try:
            new_token = self.api.rotate_secret(
                tunnel_name=self.inputs.tunnel_name,
                tunnel_secret=new_secret,
            )
        except BaseException as original_error:
            try:
                observed_token = self.api.get_token()
                self.receipt.add_forbidden(observed_token.value)
                self.docker.runner.add_forbidden(observed_token.value)
            except BaseException:
                # PATCH transport failure is mutation-ambiguous. Conservatively
                # drive the old secret back through the rollback path.
                self.rotation_applied = True
                raise original_error
            if observed_token.matches(self.old_token):
                raise original_error
            try:
                observed_metadata = parse_tunnel_token(observed_token)
            except RotationError as exc:
                self.rotation_applied = True
                raise RotationError("rotation_outcome_unknown") from exc
            expected_new_token = (
                observed_metadata.account_id
                == self.token_metadata.account_id
                and observed_metadata.tunnel_id
                == self.token_metadata.tunnel_id
                and observed_metadata.tunnel_secret.matches(new_secret)
            )
            self.rotation_applied = True
            if not expected_new_token:
                raise RotationError("rotation_outcome_unknown")
            if not isinstance(original_error, RotationError):
                raise original_error
            new_token = observed_token
            self.state.event("cloudflare_patch_response_reconciled")
        else:
            self.rotation_applied = True
            self.receipt.add_forbidden(new_token.value)
            self.docker.runner.add_forbidden(new_token.value)
        metadata = parse_tunnel_token(new_token)
        if (
            metadata.account_id != self.token_metadata.account_id
            or metadata.tunnel_id != self.token_metadata.tunnel_id
            or new_token.matches(self.old_token)
        ):
            raise RotationError("rotated_tunnel_token_invalid")
        remote = self.api.get_token()
        if not remote.matches(new_token):
            raise RotationError("rotated_remote_token_mismatch")
        self.new_token = new_token
        self.state.after_token_sha256 = new_token.sha256
        atomic_write_owner_only(
            self.stage_file,
            (new_token.value + "\n").encode("ascii"),
            replace=False,
        )
        self.state.event("cloudflare_secret_rotated")
        self._checkpoint("cloudflare_secret_rotated")
        self.docker.start_canary(self.stage_file)
        canary_snapshot, canary_id = self._wait_for_new_connector(
            baseline_ids,
            required_ids=baseline_ids,
        )
        self.canary_id = canary_id
        required = set(baseline_ids)
        required.add(canary_id)
        self.state.event(
            "new_token_canary_joined",
            connectorId=canary_id,
            activeConnectorCount=len(canary_snapshot.active_connector_ids),
        )
        self._checkpoint("canary_joined")
        self.timing.dwell(
            lambda: self._new_token_health(
                minimum_connectors=len(required),
                required_ids=required,
            )
        )
        self.state.event(
            "canary_dwell_completed",
            dwellSeconds=MANDATORY_DWELL_SECONDS,
        )
        self._checkpoint("canary_dwell_completed")

    def _promote_new_token(self, baseline_ids: frozenset[str]) -> None:
        assert self.new_token is not None
        before_promotion = self.api.get_snapshot()
        self._validate_snapshot(
            before_promotion,
            minimum_connectors=len(baseline_ids) + 1,
            required_ids=baseline_ids,
        )
        canary_ids = before_promotion.active_connector_ids - baseline_ids
        if (
            self.canary_id is None
            or canary_ids != {self.canary_id}
        ):
            raise RotationError("canary_connector_missing_before_commit")
        if not self.api.get_token().matches(self.new_token):
            raise RotationError("rotated_remote_token_mismatch")
        atomic_write_owner_only(
            self.inputs.token_file,
            (self.new_token.value + "\n").encode("ascii"),
            replace=True,
        )
        if not read_token_file(self.inputs.token_file).matches(self.new_token):
            raise RotationError("canonical_token_replace_failed")
        self.state.event("canonical_token_file_replaced")
        self._checkpoint("ready_to_replace_first_incumbent")

        # This is the irreversible operational commit point. From here on a
        # failure preserves the canary and whichever canonical connector remains.
        self.state.rotation_commit_started = True
        self._checkpoint("rotation_commit_started")
        self.commit_started = True
        previous = before_promotion.active_connector_ids
        self.docker.recreate_service(PRIMARY_SERVICE)
        self.timing.wait_for(
            lambda: self.docker.verify_connector_container(PRIMARY_SERVICE),
            timeout_seconds=CONTAINER_HEALTH_TIMEOUT_SECONDS,
            failure_code="primary_container_health_timeout",
        )
        after_primary = self.timing.wait_for(
            lambda: self._wait_for_service_connector(
                previous,
                required_ids=canary_ids,
            ),
            timeout_seconds=CONNECTOR_JOIN_TIMEOUT_SECONDS,
            failure_code="primary_connector_join_timeout",
        )
        primary_snapshot, primary_id = after_primary
        required_after_primary = set(canary_ids)
        required_after_primary.add(primary_id)
        if not (baseline_ids & primary_snapshot.active_connector_ids):
            raise RotationError("last_incumbent_missing_before_second_dwell")
        self.state.event(
            "primary_connector_replaced",
            connectorId=primary_id,
        )
        self._checkpoint("primary_replaced")
        self.timing.dwell(
            lambda: self._verify_primary_dwell(
                required_after_primary,
                baseline_ids,
            )
        )
        self.state.event(
            "primary_dwell_completed",
            dwellSeconds=MANDATORY_DWELL_SECONDS,
        )
        self._checkpoint("primary_dwell_completed")

        previous = self.api.get_snapshot().active_connector_ids
        self.docker.recreate_service(REPLICA_SERVICE)
        self.timing.wait_for(
            lambda: self.docker.verify_connector_container(REPLICA_SERVICE),
            timeout_seconds=CONTAINER_HEALTH_TIMEOUT_SECONDS,
            failure_code="replica_container_health_timeout",
        )
        final_with_canary, replica_id = self.timing.wait_for(
            lambda: self._wait_for_service_connector(
                previous,
                required_ids=required_after_primary,
            ),
            timeout_seconds=CONNECTOR_JOIN_TIMEOUT_SECONDS,
            failure_code="replica_connector_join_timeout",
        )
        permanent_ids = {primary_id, replica_id}
        if not permanent_ids.issubset(final_with_canary.active_connector_ids):
            raise RotationError("permanent_connectors_not_active")
        self.prober.verify_stable(self.baseline_probes)
        self.state.event(
            "replica_connector_replaced",
            connectorId=replica_id,
        )
        self._checkpoint("replica_replaced")
        final_overlap_ids = set(permanent_ids) | set(canary_ids)
        self.timing.dwell(
            lambda: self._api_and_public_health(
                minimum_connectors=len(final_overlap_ids),
                required_ids=final_overlap_ids,
            )
        )
        self.state.event(
            "replica_dwell_completed",
            dwellSeconds=MANDATORY_DWELL_SECONDS,
        )
        self._checkpoint("replica_dwell_completed")

        self.docker.remove_canary()
        final_snapshot = self.timing.wait_for(
            lambda: self._final_verification(permanent_ids),
            timeout_seconds=CONNECTOR_JOIN_TIMEOUT_SECONDS,
            failure_code="final_connector_verification_timeout",
        )
        self.state.final_connector_ids = sorted(
            final_snapshot.active_connector_ids
        )
        secure_unlink(self.stage_file)
        self._checkpoint("final_verified")

    def _wait_for_service_connector(
        self,
        previous_ids: frozenset[str],
        *,
        required_ids: Iterable[str],
    ) -> tuple[ApiSnapshot, str]:
        snapshot = self._api_and_public_health(
            minimum_connectors=MINIMUM_ACTIVE_CONNECTORS,
            required_ids=required_ids,
        )
        added = sorted(snapshot.active_connector_ids - previous_ids)
        if len(added) != 1:
            raise RotationError("replacement_connector_identity_ambiguous")
        return snapshot, added[0]

    def _verify_primary_dwell(
        self,
        required_new_ids: set[str],
        baseline_ids: frozenset[str],
    ) -> ApiSnapshot:
        snapshot = self._api_and_public_health(
            minimum_connectors=len(required_new_ids) + 1,
            required_ids=required_new_ids,
        )
        if not (snapshot.active_connector_ids & baseline_ids):
            raise RotationError("last_incumbent_missing_during_dwell")
        return snapshot

    def _new_token_health(
        self,
        *,
        minimum_connectors: int,
        required_ids: Iterable[str],
    ) -> ApiSnapshot:
        if self.new_token is None or not self.api.get_token().matches(
            self.new_token
        ):
            raise RotationError("rotated_remote_token_mismatch")
        return self._api_and_public_health(
            minimum_connectors=minimum_connectors,
            required_ids=required_ids,
        )

    def _final_verification(self, permanent_ids: set[str]) -> ApiSnapshot:
        self.docker.verify_connector_container(PRIMARY_SERVICE)
        self.docker.verify_connector_container(REPLICA_SERVICE)
        snapshot = self._api_and_public_health(
            minimum_connectors=MINIMUM_ACTIVE_CONNECTORS,
            required_ids=permanent_ids,
        )
        if snapshot.active_connector_ids != permanent_ids:
            raise RotationError("unexpected_active_connector_topology")
        assert self.new_token is not None
        if not self.api.get_token().matches(self.new_token):
            raise RotationError("final_remote_token_mismatch")
        if not read_token_file(self.inputs.token_file).matches(self.new_token):
            raise RotationError("final_local_token_mismatch")
        return snapshot

    def _rollback_before_commit(
        self,
        baseline_ids: frozenset[str],
    ) -> None:
        self.state.phase = "rollback_before_incumbent_removal"
        self.state.event("rollback_started")
        try:
            self.receipt.write(self.state)
        except BaseException:
            pass
        try:
            restored = self.api.rotate_secret(
                tunnel_name=self.inputs.tunnel_name,
                tunnel_secret=self.token_metadata.tunnel_secret,
            )
            if not restored.matches(self.old_token):
                raise RotationError("rollback_remote_token_mismatch")
            if not self.api.get_token().matches(self.old_token):
                raise RotationError("rollback_remote_token_mismatch")
            if not read_token_file(self.inputs.token_file).matches(self.old_token):
                atomic_write_owner_only(
                    self.inputs.token_file,
                    (self.old_token.value + "\n").encode("ascii"),
                    replace=True,
                )
            self._api_and_public_health(
                minimum_connectors=MINIMUM_ACTIVE_CONNECTORS,
                required_ids=baseline_ids,
            )
            self.docker.remove_canary()
            secure_unlink(self.stage_file)
            self.state.rollback_status = "passed"
            self.state.rotation_commit_started = False
            self.state.event("rollback_completed")
            self.receipt.write(self.state)
        except BaseException as exc:
            self.state.rollback_status = "failed"
            self.state.failure_code = (
                exc.code
                if isinstance(exc, RotationError)
                else "rollback_interrupted"
            )
            self.state.event("rollback_failed")
            try:
                self.receipt.write(self.state)
            except BaseException:
                pass
            raise RotationError("rollback_failed") from exc


def _validate_inputs(inputs: RotationInputs) -> tuple[
    CloudflareCredentials,
    SecretText,
    TunnelTokenMetadata,
    ComposeEnvironment,
]:
    canonical_compose_file = (
        inputs.repository_root / "docker-compose.public-edge.yml"
    )
    if inputs.compose_file != canonical_compose_file:
        raise RotationError("compose_file_not_canonical")
    if inputs.compose_env_file.name != ".env":
        raise RotationError("compose_env_file_not_canonical")
    _assert_strict_private_parent(inputs.token_file)
    for path, code in (
        (inputs.repository_root, "repository_root_invalid"),
        (inputs.compose_file, "compose_file_invalid"),
        (inputs.compose_env_file, "compose_env_file_invalid"),
    ):
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise RotationError(code) from exc
        if resolved != path:
            raise RotationError(code)
    if not inputs.compose_file.is_file():
        raise RotationError("compose_file_invalid")
    credentials = parse_credentials_file(inputs.credentials_file)
    old_token = read_token_file(inputs.token_file)
    metadata = parse_tunnel_token(old_token)
    if metadata.tunnel_id != inputs.tunnel_id:
        raise RotationError("requested_tunnel_id_mismatch")
    try:
        token_resolved = inputs.token_file.resolve(strict=True)
        repository_resolved = inputs.repository_root.resolve(strict=True)
        token_resolved.relative_to(repository_resolved)
    except ValueError:
        pass
    else:
        raise RotationError("token_file_inside_repository")
    token_stat = inputs.token_file.stat()
    compose_environment = parse_compose_environment(
        inputs.compose_env_file,
        expected_token_file=inputs.token_file,
        token_stat=token_stat,
    )
    return credentials, old_token, metadata, compose_environment


def _validate_legacy_bootstrap_inputs(
    inputs: RotationInputs,
) -> tuple[
    CloudflareCredentials,
    SecretText,
    TunnelTokenMetadata,
    LegacyComposeMigration,
]:
    canonical_compose_file = (
        inputs.repository_root / "docker-compose.public-edge.yml"
    )
    if inputs.compose_file != canonical_compose_file:
        raise RotationError("compose_file_not_canonical")
    if inputs.compose_env_file.name != ".env":
        raise RotationError("compose_env_file_not_canonical")
    _assert_strict_private_parent(inputs.token_file)
    for path, code in (
        (inputs.repository_root, "repository_root_invalid"),
        (inputs.compose_file, "compose_file_invalid"),
        (inputs.compose_env_file, "compose_env_file_invalid"),
    ):
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise RotationError(code) from exc
        if resolved != path:
            raise RotationError(code)
    if not inputs.compose_file.is_file():
        raise RotationError("compose_file_invalid")
    try:
        token_candidate = inputs.token_file.resolve(strict=False)
        repository_resolved = inputs.repository_root.resolve(strict=True)
        token_candidate.relative_to(repository_resolved)
    except ValueError:
        pass
    else:
        raise RotationError("token_file_inside_repository")
    credentials = parse_credentials_file(inputs.credentials_file)
    migration = prepare_legacy_compose_migration(
        inputs.compose_env_file,
        token_file=inputs.token_file,
    )
    metadata = parse_tunnel_token(migration.old_token)
    if metadata.tunnel_id != inputs.tunnel_id:
        raise RotationError("requested_tunnel_id_mismatch")
    return credentials, migration.old_token, metadata, migration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit or execute the fail-closed Chummer Cloudflare Tunnel "
            "token rotation."
        )
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--bootstrap-legacy",
        action="store_true",
        help=(
            "Migrate the exact single legacy chummer-run-cloudflared "
            "raw-dotenv/argv-token state into token-file HA before rotating."
        ),
    )
    parser.add_argument("--confirm", default="")
    parser.add_argument("--credentials-file", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--compose-env-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--tunnel-id", required=True)
    parser.add_argument("--tunnel-name", default="chummer-run")
    return parser


def classify_failure_status(state: ReceiptState) -> str:
    post_commit_phases = {
        "legacy_migration_commit_started",
        "legacy_migration_completed",
        "rotation_commit_started",
        "primary_replaced",
        "primary_dwell_completed",
        "replica_replaced",
        "replica_dwell_completed",
        "final_verified",
    }
    action_required = (
        state.rollback_status == "failed"
        or state.migration_status == "rollback_failed"
        or state.migration_commit_started
        or state.rotation_commit_started
        or state.legacy_container_removed
        or state.phase in post_commit_phases
    )
    return "action_required" if action_required else "failed"


def validate_execution_authority(
    inputs: RotationInputs,
    *,
    execute: bool,
) -> None:
    if execute and inputs.repository_root != inputs.compose_env_file.parent:
        raise RotationError("execute_requires_canonical_repository")


def run(
    argv: Sequence[str] | None = None,
    *,
    transport: HttpTransport = urllib_transport,
    prober: PublicProber | None = None,
    timing: Timing | None = None,
    secret_factory: Callable[[], bytes] = lambda: secrets.token_bytes(32),
) -> int:
    args = build_parser().parse_args(argv)
    if args.execute and args.confirm != CONFIRMATION:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "failureCode": "exact_confirmation_required",
                    "requiredConfirmation": CONFIRMATION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    if not args.execute and args.confirm:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "failureCode": "confirmation_without_execute",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    repository_root = Path(__file__).resolve().parents[1]
    inputs = RotationInputs(
        repository_root=repository_root,
        compose_file=repository_root / "docker-compose.public-edge.yml",
        compose_env_file=args.compose_env_file.absolute(),
        credentials_file=args.credentials_file.absolute(),
        token_file=args.token_file.absolute(),
        receipt_file=args.receipt.absolute(),
        tunnel_id=args.tunnel_id,
        tunnel_name=args.tunnel_name,
    )
    run_id = uuid.uuid4().hex
    state = ReceiptState(
        run_id=run_id,
        mode="execute" if args.execute else "audit",
    )
    writer: ReceiptWriter | None = None
    try:
        validate_execution_authority(inputs, execute=args.execute)
        migration: LegacyComposeMigration | None = None
        if args.bootstrap_legacy:
            (
                credentials,
                old_token,
                metadata,
                migration,
            ) = _validate_legacy_bootstrap_inputs(inputs)
            compose_environment = migration.environment
        else:
            (
                credentials,
                old_token,
                metadata,
                compose_environment,
            ) = _validate_inputs(inputs)
        forbidden = (
            *credentials.secret_values,
            old_token.value,
            metadata.tunnel_secret.value,
        )
        writer = ReceiptWriter(inputs.receipt_file, forbidden)
        writer.write(state)
        with RotationLock(inputs.lock_file, run_id):
            api = CloudflareClient(
                account_id=metadata.account_id,
                tunnel_id=metadata.tunnel_id,
                credentials=credentials,
                transport=transport,
            )
            runner = SafeRunner(forbidden)
            docker = DockerClient(
                runner=runner,
                inputs=inputs,
                environment=compose_environment,
                run_id=run_id,
            )
            engine = RotationEngine(
                inputs=inputs,
                old_token=old_token,
                token_metadata=metadata,
                api=api,
                docker=docker,
                prober=prober or PublicProber(),
                timing=timing or Timing(),
                receipt=writer,
                state=state,
                secret_factory=secret_factory,
            )
            if migration is not None:
                bootstrap = LegacyBootstrapEngine(
                    inputs=inputs,
                    migration=migration,
                    token_metadata=metadata,
                    api=api,
                    docker=docker,
                    prober=prober or PublicProber(),
                    timing=timing or Timing(),
                    receipt=writer,
                    state=state,
                )
                if args.execute:
                    bootstrap.execute()
                    engine.execute()
                else:
                    bootstrap.audit()
            elif args.execute:
                engine.execute()
            else:
                engine.audit()
        print(
            json.dumps(
                {
                    "status": state.status,
                    "phase": state.phase,
                    "receipt": str(inputs.receipt_file),
                    "secretsExposed": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except BaseException as exc:
        state.status = classify_failure_status(state)
        if isinstance(exc, RotationError):
            state.failure_code = exc.code
        elif isinstance(exc, KeyboardInterrupt):
            state.failure_code = "operator_interrupt"
        elif isinstance(exc, SystemExit):
            state.failure_code = "system_exit"
        else:
            state.failure_code = "unexpected_local_failure"
        state.completed_at = utc_now()
        if writer is not None:
            try:
                writer.write(state)
            except BaseException:
                pass
        print(
            json.dumps(
                {
                    "status": state.status,
                    "phase": state.phase,
                    "failureCode": state.failure_code,
                    "receipt": str(inputs.receipt_file),
                    "secretsExposed": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        if isinstance(exc, SystemExit):
            raise
        if isinstance(exc, KeyboardInterrupt):
            return 130
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
