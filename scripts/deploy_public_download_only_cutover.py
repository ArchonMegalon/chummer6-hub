#!/usr/bin/env python3
"""Run the fail-closed isolated-sidecar public-download release cutover.

This controller is intentionally callable only from the authenticated public-edge
wrapper while that wrapper owns the shared mutation lock.  The incumbent shelf
inputs are attestation-only; only a separately authenticated sealed release
candidate may populate the sidecar shelf.  The controller never tags either
canonical application image and never starts PostgreSQL.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
from dataclasses import dataclass, replace as dataclass_replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import errno
import hashlib
import http.client
import io
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import secrets
import signal
import shutil
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import Request, urlopen


CONTRACT_NAME = "chummer.public-download-only-deployment/v1"
RUNTIME_PROFILE = "public-download-only"
OPERATIONS = {
    "initial-release-shelf-public-download-cutover",
    "initial-release-shelf-public-download-cutover-recover",
    "initial-release-shelf-public-download-cutover-retire",
}
RECOVERY_OPERATION = "initial-release-shelf-public-download-cutover-recover"
CUTOVER_OPERATION = "initial-release-shelf-public-download-cutover"
RETIRE_OPERATION = "initial-release-shelf-public-download-cutover-retire"
CANONICAL_PROJECT = "chummer6-hub"
CANONICAL_PORT = 8091
CANONICAL_STATE_VOLUME = "chummer6-hub_chummer-run-api-state"
CANONICAL_PORTAL_TAG = "chummer-run-api:local"
CANONICAL_TOOL_TAG = "chummer-install-linking-postgres-tool:local"
PORTAL_SERVICE = "chummer-portal"
TUNNEL_SERVICE = "chummer-run-cloudflared"
# Run.Api requires more than seven full days of validity at load time. Keep the
# operation-bound certificate short-lived while leaving margin for the cutover.
SIDECAR_CERTIFICATE_VALIDITY_DAYS = 30
SIDECAR_CERTIFICATE_MINIMUM_REMAINING_SECONDS = 7 * 24 * 60 * 60
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{7,127}$")
CANONICAL_RELEASE_SHELF_ROOT = Path(
    "/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads"
)
SHELF_MUTATION_MAY_HAVE_BEGUN = False
PUBLIC_ACTIVE_RUNTIME_AUTHORITY_FIELDS = {
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


class CutoverError(RuntimeError):
    pass


class RecoveryUncertain(CutoverError):
    pass


class _RetirementInterrupted(BaseException):
    def __init__(self, signal_number: int) -> None:
        super().__init__(
            f"retirement interrupted by signal {signal_number}"
        )
        self.signal_number = signal_number


def _safe_stderr_summary(value: bytes) -> str:
    """Return a bounded, non-verbatim classification of command stderr."""
    if not value:
        return "stderr was empty"
    lowered = value.lower()
    if b"required variable" in lowered and b"is missing a value" in lowered:
        return "Compose required-variable validation failed"
    if (
        b"only one connection allowed" in lowered
        or b"error while dialing" in lowered
        or b"cannot connect to the docker daemon" in lowered
    ):
        return "Docker daemon connection was unavailable"
    return "stderr content redacted; correlate by SHA-256"


class CommandFailure(CutoverError):
    """A subprocess failure whose durable evidence never contains raw output."""

    def __init__(
        self,
        *,
        label: str,
        failure_kind: str,
        status: int | None,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ) -> None:
        suffix = f" with status {status}" if status is not None else ""
        super().__init__(f"{label} {failure_kind}{suffix}")
        self.evidence = {
            "contractName": "chummer.public-download-command-failure/v1",
            "stage": label,
            "failureKind": failure_kind,
            "exitStatus": status,
            "stdoutSha256": sha256_bytes(stdout),
            "stdoutSizeBytes": len(stdout),
            "stderrSha256": sha256_bytes(stderr),
            "stderrSizeBytes": len(stderr),
            "safeStderrSummary": _safe_stderr_summary(stderr),
        }


def _find_command_failure(error: BaseException) -> CommandFailure | None:
    observed: set[int] = set()
    pending: list[BaseException] = [error]
    while pending and len(observed) < 8:
        current = pending.pop(0)
        if id(current) in observed:
            continue
        if isinstance(current, CommandFailure):
            return current
        observed.add(id(current))
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_regular_bytes(
    path: Path,
    *,
    label: str,
    maximum_bytes: int | None = 16 * 1024 * 1024,
    owner_only: bool = False,
) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise CutoverError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or (owner_only and stat.S_IMODE(before.st_mode) & 0o077)
        or stat.S_IMODE(before.st_mode) & 0o022
        or (maximum_bytes is not None and before.st_size > maximum_bytes)
    ):
        raise CutoverError(f"{label} metadata is unsafe")
    try:
        value = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise CutoverError(f"{label} changed while read") from exc
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_uid,
        item.st_gid,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )
    if identity(before) != identity(after) or len(value) != before.st_size:
        raise CutoverError(f"{label} changed while read")
    return value


def private_directory(path: Path, *, create: bool) -> Path:
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CutoverError(f"private directory is unavailable: {path}") from exc
    if (
        resolved != path
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise CutoverError(f"private directory is unsafe: {path}")
    return path


def atomic_private_write(path: Path, value: bytes, *, replace: bool) -> None:
    private_directory(path.parent, create=False)
    if not replace and (path.exists() or path.is_symlink()):
        raise CutoverError(f"private receipt already exists: {path.name}")
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(raw_temporary)
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path, follow_symlinks=False)
        published = True
    finally:
        temporary.unlink(missing_ok=True)
    if published:
        descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def write_private_json(path: Path, payload: dict[str, Any], *, replace: bool = False) -> None:
    body = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    atomic_private_write(path, body, replace=replace)


def load_module(path: Path, name: str) -> Any:
    if not path.is_file() or path.is_symlink():
        raise CutoverError(f"audited controller dependency is unavailable: {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CutoverError(f"could not load audited dependency: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Config:
    operation: str
    source_root: Path
    source_head: str
    shared_lock_token: str
    shelf_root: Path
    migration_state_root: Path
    migration_candidate_root: Path
    migration_authority: Path
    migration_authority_sha256: str
    release_channel_receipt: Path
    release_channel_receipt_sha256: str
    projection_snapshot_root: Path
    projection_snapshot_id: str
    projection_snapshot_sha256: str
    projection_manifest_sha256: str
    runtime_proof_source: Path
    runtime_proof_sha256: str
    certificate_file: Path
    certificate_password_file: Path
    overlay_root: Path
    overlay_staging_root: Path
    overlay_backup_root: Path
    overlay_build_root: Path
    transaction_journal: Path
    active_runtime_authority: Path
    docker_config_root: Path
    env_file: Path
    receipt_root: Path
    base_url: str
    build_context: Path
    fleet_media_contracts: Path
    design_product_root: Path
    ready_timeout_seconds: int


class Runner:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.base_environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(config.docker_config_root / "home"),
            "DOCKER_CONFIG": str(config.docker_config_root / "config"),
            "LANG": "C",
            "LC_ALL": "C",
        }

    def run(
        self,
        command: list[str],
        *,
        label: str,
        timeout: int = 300,
        input_bytes: bytes | None = None,
        environment: dict[str, str] | None = None,
    ) -> bytes:
        env = dict(self.base_environment)
        if environment:
            env.update(environment)
        try:
            completed = subprocess.run(
                command,
                env=env,
                input=input_bytes,
                stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CutoverError(f"{label} could not execute") from exc
        if completed.returncode != 0:
            raise CutoverError(f"{label} failed with status {completed.returncode}")
        return completed.stdout

    def python(
        self,
        script: Path,
        arguments: list[str],
        *,
        label: str,
        timeout: int = 300,
        input_bytes: bytes | None = None,
    ) -> bytes:
        return self.run(
            ["/usr/bin/python3", "-I", str(script), *arguments],
            label=label,
            timeout=timeout,
            input_bytes=input_bytes,
        )

    def docker(
        self,
        arguments: list[str],
        *,
        label: str,
        timeout: int = 300,
        input_bytes: bytes | None = None,
    ) -> bytes:
        return self.run(
            ["/usr/bin/docker", "--context", "default", *arguments],
            label=label,
            timeout=timeout,
            input_bytes=input_bytes,
        )

    def compose_environment(self, overlay_root: Path) -> dict[str, str]:
        return {
            "COMPOSE_DISABLE_ENV_FILE": "1",
            "CHUMMER_DATA_PROTECTION_CERTIFICATE_FILE": str(
                self.config.certificate_file
            ),
            "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE": str(
                self.config.certificate_password_file
            ),
            "CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR": str(overlay_root),
            "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": str(
                self.config.projection_snapshot_root
            ),
            "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": str(
                self.config.runtime_proof_source
            ),
            "CHUMMER_PUBLIC_EDGE_PORT": str(CANONICAL_PORT),
            "CHUMMER_RUN_TUNNEL_NETWORK": "chummer5a_default",
            "CHUMMER_FLEET_NETWORK": "codex-fleet-net",
            "CHUMMER_EA_NETWORK": "ea_default",
            "CHUMMER_PORTAL_UID": "1654",
            "CHUMMER_PORTAL_GID": "1654",
        }

    def compose(
        self,
        compose_file: Path,
        arguments: list[str],
        *,
        label: str,
        overlay_root: Path,
        timeout: int = 300,
    ) -> bytes:
        return self.run(
            [
                "/usr/bin/docker",
                "--context",
                "default",
                "compose",
                "--env-file",
                "/dev/null",
                "-p",
                CANONICAL_PROJECT,
                "-f",
                str(compose_file),
                "--project-directory",
                str(self.config.source_root),
                "--profile",
                "public-downloads",
                *arguments,
            ],
            label=label,
            timeout=timeout,
            environment=self.compose_environment(overlay_root),
        )


def validate_config(config: Config) -> None:
    if config.operation not in OPERATIONS:
        raise CutoverError("public-download cutover operation is invalid")
    if COMMIT.fullmatch(config.source_head) is None:
        raise CutoverError("source HEAD must be a lowercase full commit")
    if re.fullmatch(r"[0-9a-f]{64}", config.shared_lock_token) is None:
        raise CutoverError("shared mutation lock token is invalid")
    for value, label in (
        (config.migration_authority_sha256, "migration authority SHA-256"),
        (config.release_channel_receipt_sha256, "release receipt SHA-256"),
        (config.projection_snapshot_sha256, "projection snapshot SHA-256"),
        (config.projection_manifest_sha256, "projection manifest SHA-256"),
        (config.runtime_proof_sha256, "runtime proof SHA-256"),
    ):
        if SHA256.fullmatch(value) is None:
            raise CutoverError(f"{label} is invalid")
    if (
        config.projection_snapshot_id
        != f"public-projection-{config.projection_snapshot_sha256}"
    ):
        raise CutoverError("public projection snapshot identity is invalid")
    if config.base_url.rstrip("/") != "https://chummer.run":
        raise CutoverError("public-download cutover origin is not canonical")
    try:
        observed_head = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(config.source_root),
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ],
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CutoverError("source HEAD could not be verified") from exc
    if observed_head != config.source_head:
        raise CutoverError("checked-out source does not match source HEAD")
    for path, label, digest, owner_only in (
        (
            config.migration_authority,
            "migration authority",
            config.migration_authority_sha256,
            False,
        ),
        (
            config.release_channel_receipt,
            "release-channel receipt",
            config.release_channel_receipt_sha256,
            False,
        ),
        (
            config.runtime_proof_source,
            "runtime proof source",
            config.runtime_proof_sha256,
            False,
        ),
        (config.certificate_file, "data-protection certificate", "", True),
        (
            config.certificate_password_file,
            "data-protection certificate password",
            "",
            True,
        ),
    ):
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise CutoverError(f"{label} path is not exact and canonical")
        value = stable_regular_bytes(path, label=label, owner_only=owner_only)
        if digest and sha256_bytes(value) != digest:
            raise CutoverError(f"{label} does not match its independent SHA-256")
    private_directory(config.receipt_root, create=True)
    private_directory(config.active_runtime_authority.parent, create=False)
    private_directory(config.docker_config_root, create=False)
    private_directory(config.docker_config_root / "home", create=False)
    private_directory(config.docker_config_root / "config", create=False)


def validate_journal_recovery_config(config: Config) -> None:
    """Validate only inputs that recovery consumes; never resolve CURRENT."""

    if config.operation != RECOVERY_OPERATION:
        raise CutoverError("journal recovery operation is invalid")
    if COMMIT.fullmatch(config.source_head) is None:
        raise CutoverError("journal recovery source HEAD is invalid")
    if SHA256.fullmatch(config.shared_lock_token) is None:
        raise CutoverError("shared mutation lock token is invalid")
    if (
        config.shelf_root != CANONICAL_RELEASE_SHELF_ROOT
        or config.shelf_root.resolve(strict=True) != config.shelf_root
        or config.shelf_root.is_symlink()
    ):
        raise CutoverError("journal recovery shelf root is not canonical")
    if (
        not config.transaction_journal.is_file()
        or config.transaction_journal.is_symlink()
    ):
        raise CutoverError("journal recovery transaction is unavailable")
    try:
        observed_head = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(config.source_root),
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ],
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CutoverError("journal recovery source HEAD could not be verified") from exc
    if observed_head != config.source_head:
        raise CutoverError("journal recovery source checkout changed")
    private_directory(config.receipt_root, create=False)
    private_directory(config.active_runtime_authority.parent, create=False)
    private_directory(config.docker_config_root, create=False)
    private_directory(config.docker_config_root / "home", create=False)
    private_directory(config.docker_config_root / "config", create=False)


def docker_inspect_json(runner: Runner, kind: str, identity: str) -> dict[str, Any]:
    raw = runner.docker(
        [kind, "inspect", identity],
        label=f"inspect exact Docker {kind}",
    )
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CutoverError(f"Docker {kind} inspection was malformed") from exc
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise CutoverError(f"Docker {kind} inspection was ambiguous")
    return payload[0]


def resolve_image_tag(runner: Runner, tag: str) -> str:
    try:
        payload = docker_inspect_json(runner, "image", tag)
    except CutoverError:
        return ""
    identity = str(payload.get("Id") or "")
    if IMAGE_ID.fullmatch(identity) is None:
        raise CutoverError("Docker image tag resolved to an invalid identity")
    return identity


def service_container(
    runner: Runner,
    service: str,
    *,
    oneoff: bool,
) -> str:
    raw = runner.docker(
        [
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={CANONICAL_PROJECT}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        ],
        label=f"resolve exact {service} container",
    )
    candidates: list[str] = []
    for identity in raw.decode("ascii", errors="strict").splitlines():
        if CONTAINER_ID.fullmatch(identity) is None:
            raise CutoverError(f"{service} container identity is malformed")
        inspection = docker_inspect_json(runner, "container", identity)
        labels = inspection.get("Config", {}).get("Labels") or {}
        observed_oneoff = str(labels.get("com.docker.compose.oneoff") or "").lower()
        if observed_oneoff == ("true" if oneoff else "false"):
            candidates.append(identity)
    if len(candidates) > 1:
        raise CutoverError(f"{service} container authority is ambiguous")
    return candidates[0] if candidates else ""


def container_runtime(runner: Runner, identity: str) -> dict[str, Any]:
    if not identity:
        return {
            "existed": False,
            "containerId": "",
            "containerName": "",
            "imageId": "",
            "wasRunning": False,
        }
    inspection = docker_inspect_json(runner, "container", identity)
    canonical_id = str(inspection.get("Id") or "")
    image_id = str(inspection.get("Image") or "")
    name = str(inspection.get("Name") or "").removeprefix("/")
    running = inspection.get("State", {}).get("Running")
    if (
        canonical_id != identity
        or IMAGE_ID.fullmatch(image_id) is None
        or SAFE_NAME.fullmatch(name) is None
        or not isinstance(running, bool)
    ):
        raise CutoverError("container runtime identity is invalid")
    return {
        "existed": True,
        "containerId": identity,
        "containerName": name,
        "imageId": image_id,
        "wasRunning": running,
    }


def require_incumbent_runtime(runner: Runner) -> tuple[dict[str, Any], dict[str, Any]]:
    portal = container_runtime(
        runner,
        service_container(runner, PORTAL_SERVICE, oneoff=False),
    )
    tunnel = container_runtime(
        runner,
        service_container(runner, TUNNEL_SERVICE, oneoff=False),
    )
    if not portal["existed"] or not portal["wasRunning"]:
        raise CutoverError("incumbent portal must be running for serving continuity")
    if not tunnel["existed"] or not tunnel["wasRunning"]:
        raise CutoverError("incumbent tunnel must be running for serving continuity")
    return portal, tunnel


def require_container_running(runner: Runner, identity: str, label: str) -> None:
    runtime = container_runtime(runner, identity)
    if not runtime["existed"] or not runtime["wasRunning"]:
        raise CutoverError(f"{label} stopped before serving continuity was proved")


def copy_container_file(
    runner: Runner,
    container_id: str,
    source: str,
    destination: Path,
) -> str:
    if destination.exists() or destination.is_symlink():
        raise CutoverError("container proof snapshot destination already exists")
    runner.docker(
        ["container", "cp", f"{container_id}:{source}", str(destination)],
        label="capture prior runtime proof mount",
    )
    destination.chmod(0o600)
    return sha256_bytes(
        stable_regular_bytes(
            destination,
            label="prior runtime proof snapshot",
            owner_only=True,
        )
    )


def http_manifest_observation(
    *,
    base_url: str,
    manifest_root: Path,
    portal_id: str,
    runner: Runner,
    phase: str,
) -> dict[str, Any]:
    require_container_running(runner, portal_id, "incumbent portal")
    results: list[dict[str, Any]] = []
    for name in ("RELEASE_CHANNEL.generated.json", "releases.json"):
        local = stable_regular_bytes(
            manifest_root / name,
            label=f"incumbent {name}",
            maximum_bytes=8 * 1024 * 1024,
        )
        url = urljoin(base_url.rstrip("/") + "/", f"downloads/{name}")
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "User-Agent": "chummer-public-download-cutover/1",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                remote = response.read(8 * 1024 * 1024 + 1)
                status_code = int(response.status)
                final_url = response.geturl()
        except OSError as exc:
            raise CutoverError(f"incumbent manifest was not served during {phase}") from exc
        if (
            status_code != 200
            or final_url != url
            or len(remote) > 8 * 1024 * 1024
            or remote != local
        ):
            raise CutoverError(
                f"incumbent manifest serving bytes changed during {phase}"
            )
        results.append(
            {
                "name": name,
                "sha256": sha256_bytes(local),
                "sizeBytes": len(local),
                "httpStatus": status_code,
            }
        )
    require_container_running(runner, portal_id, "incumbent portal")
    return {
        "phase": phase,
        "observedAtUtc": utc_now(),
        "portalContainerId": portal_id,
        "manifests": results,
    }


def fsync_candidate_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file() and not path.is_symlink():
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for path in sorted(
        [root, *(item for item in root.rglob("*") if item.is_dir())],
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def materialize_incumbent_candidate(
    *,
    attestor: Any,
    shelf_root: Path,
    candidate_root: Path,
    manifest_closure_restorations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Consume only the exact candidate created by the audited preflight."""

    parent = private_directory(candidate_root.parent, create=False)
    if not candidate_root.exists() or candidate_root.is_symlink():
        raise CutoverError(
            "audited preflight migration candidate is unavailable"
        )
    try:
        with attestor.anchored_directory(
            shelf_root,
            "release shelf root",
        ) as shelf, attestor.anchored_directory(
            candidate_root,
            "public-download migration candidate",
        ) as candidate:
            snapshot = attestor.capture_legacy_snapshot_fd(
                shelf,
                allow_aborted_history=False,
            )
            candidate_snapshot = attestor._capture_public_download_candidate(
                candidate,
                shelf=shelf,
                shelf_snapshot=snapshot,
                manifest_closure_restorations=(
                    manifest_closure_restorations
                ),
            )
    except Exception as exc:
        quarantine = parent / (
            f".quarantine-{candidate_root.name}-{secrets.token_hex(8)}"
        )
        try:
            os.rename(candidate_root, quarantine)
            descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as quarantine_error:
            raise CutoverError(
                "unattested migration candidate is invalid and quarantine failed"
            ) from quarantine_error
        raise CutoverError(
            f"invalid migration candidate quarantined as {quarantine.name}"
        ) from exc
    return {
        "resumedExactCandidate": True,
        "candidateInventoryDigest": candidate_snapshot["inventory"]["digest"],
        "copiedPaths": [
            str(row["path"])
            for row in candidate_snapshot["inventory"]["files"]
        ],
        "excludedUnreferencedFiles": [
            str(row["path"])
            for row in candidate_snapshot["excludedLegacyFiles"]
        ],
        "manifestClosureRestorations": manifest_closure_restorations,
        "governedIncumbentClosureRepair": bool(
            manifest_closure_restorations
        ),
    }


def migrate_shelf(
    config: Config,
    *,
    attestor: Any,
    generation: Any,
) -> tuple[dict[str, Any], Path, Path]:
    global SHELF_MUTATION_MAY_HAVE_BEGUN
    SHELF_MUTATION_MAY_HAVE_BEGUN = True
    with generation.promotion_lock(config.shelf_root) as lease:
        prestate_path = config.migration_state_root / attestor.PRESTATE_NAME
        start_path = config.migration_state_root / attestor.START_NAME
        pointer_path = config.shelf_root / generation.CURRENT_POINTER
        copy_receipt: dict[str, Any] = {"resumed": True}
        if not prestate_path.exists():
            if config.migration_state_root.exists():
                existing = tuple(config.migration_state_root.iterdir())
                if existing:
                    raise CutoverError("migration state exists without a valid prestate")
            manifest_closure_restorations = (
                attestor.public_download_manifest_closure_restorations(
                    config.shelf_root,
                    config.migration_authority,
                    config.migration_authority_sha256,
                )
            )
            copy_receipt = materialize_incumbent_candidate(
                attestor=attestor,
                shelf_root=config.shelf_root,
                candidate_root=config.migration_candidate_root,
                manifest_closure_restorations=(
                    manifest_closure_restorations
                ),
            )
            generation_id = generation.new_generation_id()
            activation_receipt_id = generation.new_activation_receipt_id()
            prestate = attestor.prepare_public_download_migration(
                config.shelf_root,
                config.migration_state_root,
                config.migration_candidate_root,
                config.migration_authority,
                config.migration_authority_sha256,
                config.source_head,
                generation_id,
                activation_receipt_id,
            )
        else:
            if not config.migration_candidate_root.is_dir():
                raise CutoverError("resumed migration candidate is unavailable")
            prestate = json.loads(
                stable_regular_bytes(
                    prestate_path,
                    label="public-download migration prestate",
                    maximum_bytes=8 * 1024 * 1024,
                )
            )
            generation_id = str(prestate.get("generationId") or "")
            activation_receipt_id = str(prestate.get("activationReceiptId") or "")
            stage = generation.reconcile_activation_stage_residue(
                config.migration_candidate_root,
                config.shelf_root,
                generation_id=generation_id,
                activation_receipt_id=activation_receipt_id,
            )
            prestate = attestor.validate_public_download_migration_resume(
                config.shelf_root,
                config.migration_state_root,
                config.migration_candidate_root,
                source_head=config.source_head,
                ignored_activation_stage_name=stage.name if stage else "",
            )
        if pointer_path.exists() and not start_path.exists():
            raise CutoverError(
                "migration pointer committed without its start authority"
            )
        if not start_path.exists():
            attestor.request_public_download_migration_start(
                config.shelf_root,
                config.migration_state_root,
                config.migration_candidate_root,
            )
        poststate_path = (
            config.migration_state_root / attestor.POSTSTATE_NAME
        )
        marker_path = config.shelf_root / generation.LAYOUT_MARKER
        if (
            not poststate_path.exists()
            or not pointer_path.exists()
            or not marker_path.exists()
        ):
            generation.activate_filesystem(
                config.migration_candidate_root,
                config.shelf_root,
                initialize_layout=True,
                generation_id=generation_id,
                activation_receipt_id=activation_receipt_id,
                promotion_lease=lease,
                allow_orphan_generation_recovery=True,
            )
        poststate = attestor.verify_public_download_migration(
            config.shelf_root,
            config.migration_state_root,
            config.migration_candidate_root,
        )
        lease.validate_for(config.shelf_root)
    generation_root = config.shelf_root / "generations" / generation_id
    return (
        {
            "copy": copy_receipt,
            "prestateContract": prestate.get("contractName"),
            "poststate": poststate,
            "promotionLockHeldAcrossCaptureVerificationAndActivation": True,
        },
        generation_root / "releases.json",
        generation_root / "RELEASE_CHANNEL.generated.json",
    )


def stage_overlay(config: Config, runner: Runner, receipt_dir: Path) -> Path:
    output = receipt_dir / "overlay-stage.json"
    runner.python(
        config.source_root / "scripts/publish_public_edge_portal_overlay.py",
        [
            "--source-root",
            str(config.source_root),
            "--active-root",
            str(config.overlay_root),
            "--staging-root",
            str(config.overlay_staging_root),
            "--backup-root",
            str(config.overlay_backup_root),
            "--build-root",
            str(config.overlay_build_root),
            "--release-channel-receipt",
            str(config.release_channel_receipt),
            "--release-channel-receipt-sha256",
            config.release_channel_receipt_sha256,
            "--output",
            str(output),
        ],
        label="stage verified public-edge overlay",
        timeout=3600,
    )
    return output


def _snapshot_context_entries(
    source_root: Path,
    destination_root: Path,
    *,
    selected_entries: tuple[str, ...] | None,
    label: str,
) -> dict[str, Any]:
    try:
        source_metadata = source_root.lstat()
    except OSError as exc:
        raise CutoverError(f"{label} source is unavailable") from exc
    if (
        not source_root.is_absolute()
        or source_root.resolve(strict=True) != source_root
        or not stat.S_ISDIR(source_metadata.st_mode)
        or stat.S_ISLNK(source_metadata.st_mode)
    ):
        raise CutoverError(f"{label} source root is unsafe")
    destination_root.mkdir(mode=0o700)

    def copy_path(source: Path, destination: Path, relative: str) -> None:
        metadata = source.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise CutoverError(f"{label} contains a symbolic link: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.mkdir(mode=0o700)
            names = sorted(item.name for item in os.scandir(source))
            for name in names:
                if name in ("", ".", "..") or "/" in name or "\\" in name:
                    raise CutoverError(f"{label} contains an unsafe entry name")
                child_relative = f"{relative}/{name}" if relative else name
                copy_path(source / name, destination / name, child_relative)
            after = source.lstat()
            if (
                after.st_dev,
                after.st_ino,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ) != (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            ):
                raise CutoverError(f"{label} directory changed during snapshot")
            destination.chmod(stat.S_IMODE(metadata.st_mode) & 0o777)
            return
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise CutoverError(f"{label} contains a non-regular entry: {relative}")
        raw = stable_regular_bytes(
            source,
            label=f"{label} file",
            maximum_bytes=None,
        )
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            view = memoryview(raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise CutoverError(f"{label} snapshot write made no progress")
                view = view[written:]
            os.fchmod(descriptor, stat.S_IMODE(metadata.st_mode) & 0o777)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    entries = (
        selected_entries
        if selected_entries is not None
        else tuple(sorted(item.name for item in os.scandir(source_root)))
    )
    for relative in entries:
        if (
            not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise CutoverError(f"{label} selected path is unsafe")
        source = source_root / relative
        if not source.exists() or source.is_symlink():
            raise CutoverError(f"{label} selected path is unavailable: {relative}")
        copy_path(source, destination_root / relative, relative)
    destination_root.chmod(stat.S_IMODE(source_metadata.st_mode) & 0o777)
    rows, digest = _context_inventory(
        destination_root,
        label=f"{label} snapshot",
    )
    return {
        "sourceRoot": str(source_root),
        "snapshotRoot": str(destination_root),
        "algorithm": "sha256-canonical-file-inventory-v1",
        "digest": digest,
        "fileCount": len(rows),
        "files": rows,
    }


def _snapshot_inventory(root: Path, *, label: str) -> str:
    _rows, digest = _context_inventory(root, label=label)
    return digest


def _context_inventory(
    root: Path,
    *,
    label: str,
) -> tuple[list[dict[str, Any]], str]:
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise CutoverError(f"{label} root is unavailable") from exc
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
    ):
        raise CutoverError(f"{label} root is unsafe")
    rows: list[dict[str, Any]] = []
    def walk(path: Path, relative: str) -> None:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise CutoverError(f"{label} contains a symbolic link: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            rows.append(
                {
                    "path": relative,
                    "type": "directory",
                    "mode": stat.S_IMODE(metadata.st_mode) & 0o777,
                }
            )
            try:
                entries = sorted(os.scandir(path), key=lambda item: item.name)
            except OSError as exc:
                raise CutoverError(f"{label} directory is unreadable") from exc
            for entry in entries:
                child_relative = (
                    entry.name if relative == "." else f"{relative}/{entry.name}"
                )
                walk(path / entry.name, child_relative)
            after = path.lstat()
            if (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ) != (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            ):
                raise CutoverError(f"{label} directory changed during inventory")
            return
        if stat.S_ISREG(metadata.st_mode):
            if metadata.st_nlink != 1:
                raise CutoverError(f"{label} contains a multi-link file")
            raw = stable_regular_bytes(
                path,
                label=f"{label} file",
                maximum_bytes=None,
            )
            rows.append(
                {
                    "path": relative,
                    "type": "file",
                    "mode": stat.S_IMODE(metadata.st_mode) & 0o777,
                    "sha256": sha256_bytes(raw),
                    "sizeBytes": len(raw),
                }
            )
            return
        raise CutoverError(f"{label} contains a special entry: {relative}")

    walk(root, ".")
    rows.sort(key=lambda row: (str(row["path"]), str(row["type"])))
    digest = sha256_bytes(
        json.dumps(
            rows,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    )
    return rows, digest


def _snapshot_git_context_entries(
    source_root: Path,
    source_head: str,
    destination_root: Path,
    *,
    selected_entries: tuple[str, ...],
    label: str,
) -> dict[str, Any]:
    """Materialize build bytes from the pinned Git object tree, never the worktree."""

    if COMMIT.fullmatch(source_head) is None:
        raise CutoverError(f"{label} source commit is invalid")
    if (
        not source_root.is_absolute()
        or source_root.resolve(strict=True) != source_root
        or source_root.is_symlink()
        or not source_root.is_dir()
    ):
        raise CutoverError(f"{label} source root is unsafe")
    for relative in selected_entries:
        pure = PurePosixPath(relative)
        if (
            not relative
            or pure.is_absolute()
            or any(part in ("", ".", "..") for part in pure.parts)
        ):
            raise CutoverError(f"{label} selected path is unsafe")
    try:
        archived = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(source_root),
                "archive",
                "--format=tar",
                source_head,
                "--",
                *selected_entries,
            ],
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "GIT_NO_REPLACE_OBJECTS": "1",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=300,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise CutoverError(
            f"{label} could not be materialized from the source commit"
        ) from exc

    destination_root.mkdir(mode=0o700)
    seen: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archived), mode="r:") as archive:
            members = archive.getmembers()
            for member in members:
                pure = PurePosixPath(member.name)
                relative = pure.as_posix()
                if (
                    not relative
                    or pure.is_absolute()
                    or any(part in ("", ".", "..") for part in pure.parts)
                    or relative in seen
                ):
                    raise CutoverError(f"{label} Git archive path is unsafe")
                if member.isdir():
                    seen[relative] = "directory"
                elif member.isfile():
                    seen[relative] = "file"
                else:
                    raise CutoverError(
                        f"{label} Git archive contains a non-regular entry: "
                        f"{relative}"
                    )
            for selected in selected_entries:
                if not any(
                    path == selected or path.startswith(f"{selected}/")
                    for path in seen
                ):
                    raise CutoverError(
                        f"{label} selected path is absent from the source commit: "
                        f"{selected}"
                    )
            for member in sorted(
                members,
                key=lambda item: (
                    len(PurePosixPath(item.name).parts),
                    item.name,
                ),
            ):
                relative = PurePosixPath(member.name)
                destination = destination_root.joinpath(*relative.parts)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                    if (
                        destination.is_symlink()
                        or not destination.is_dir()
                    ):
                        raise CutoverError(
                            f"{label} Git archive directory collided"
                        )
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise CutoverError(f"{label} Git archive file is unreadable")
                raw = extracted.read(member.size + 1)
                if len(raw) != member.size:
                    raise CutoverError(f"{label} Git archive file size changed")
                descriptor = os.open(
                    destination,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                try:
                    view = memoryview(raw)
                    while view:
                        written = os.write(descriptor, view)
                        if written <= 0:
                            raise CutoverError(
                                f"{label} Git snapshot write made no progress"
                            )
                        view = view[written:]
                    os.fchmod(
                        descriptor,
                        0o755 if member.mode & 0o111 else 0o644,
                    )
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
    except (tarfile.TarError, OSError) as exc:
        raise CutoverError(f"{label} Git archive is malformed") from exc

    directories = [
        path
        for path in destination_root.rglob("*")
        if path.is_dir() and not path.is_symlink()
    ]
    for directory in sorted(
        directories,
        key=lambda path: len(path.relative_to(destination_root).parts),
        reverse=True,
    ):
        directory.chmod(0o755)
    destination_root.chmod(0o755)
    rows, digest = _context_inventory(
        destination_root,
        label=f"{label} Git snapshot",
    )
    return {
        "sourceRoot": str(source_root),
        "sourceCommit": source_head,
        "sourceKind": "git-object-tree",
        "snapshotRoot": str(destination_root),
        "algorithm": "sha256-canonical-file-inventory-v1",
        "digest": digest,
        "fileCount": len(rows),
        "files": rows,
    }


def prepare_immutable_build_contexts(
    config: Config,
    receipt_dir: Path,
) -> tuple[dict[str, Path], dict[str, str], Path]:
    snapshots_root = receipt_dir / "immutable-build-contexts"
    snapshots_root.mkdir(mode=0o700)
    source_entries = (
        ".codex-design",
        "Chummer.Campaign.Contracts",
        "Chummer.Control.Contracts",
        "Chummer.InstallLinking.Postgres.Tool",
        "Chummer.Play.Contracts",
        "Chummer.Run.Api",
        "Chummer.Run.Contracts",
        "Chummer.Run.LoopbackProbe",
        "Chummer.World.Contracts",
        "Directory.Build.props",
        "eng/NuGet.Container.Config",
        "eng/package-plane.lock.json",
        "global.json",
        "scripts/ai/bootstrap-hub-package-feed.py",
        "scripts/generate_public_play_worker_projection.py",
        "scripts/initialize-public-edge-volumes.sh",
        "scripts/validate_public_pwa_proof_authority.py",
        "scripts/verify_public_pwa_static_assets.py",
    )
    definitions = (
        (
            "default",
            config.source_root,
            ("Chummer.Run.Api/Dockerfile",),
            "default Docker build context",
        ),
        (
            "run-services",
            config.source_root,
            source_entries,
            "run-services build context",
        ),
        (
            "hub-registry",
            config.build_context / "chummer-hub-registry",
            ("black-ledger",),
            "hub-registry build context",
        ),
        (
            "fleet-media",
            config.fleet_media_contracts,
            None,
            "fleet media contracts build context",
        ),
        (
            "design-product",
            config.design_product_root,
            ("products/chummer",),
            "design product build context",
        ),
    )
    contexts: dict[str, Path] = {}
    digests: dict[str, str] = {}
    receipts: dict[str, Any] = {}
    for name, source, selected, label in definitions:
        destination = snapshots_root / name
        if source == config.source_root:
            if selected is None:
                raise CutoverError(
                    f"{label} requires an explicit Git object-tree closure"
                )
            receipt = _snapshot_git_context_entries(
                source,
                config.source_head,
                destination,
                selected_entries=selected,
                label=label,
            )
        else:
            receipt = _snapshot_context_entries(
                source,
                destination,
                selected_entries=selected,
                label=label,
            )
        contexts[name] = destination
        digests[name] = str(receipt["digest"])
        receipts[name] = receipt
    receipt_path = receipt_dir / "immutable-build-contexts.json"
    write_private_json(
        receipt_path,
        {
            "contractName": (
                "chummer.public-download-only-build-context-snapshots/v1"
            ),
            "status": "pass",
            "sourceHead": config.source_head,
            "contexts": receipts,
        },
    )
    return contexts, digests, receipt_path


def build_candidate_image(
    config: Config,
    runner: Runner,
    *,
    contexts: dict[str, Path] | None = None,
    context_digests: dict[str, str] | None = None,
    unique_tag: str | None = None,
    on_built: Callable[[str, str], None] | None = None,
) -> tuple[str, str]:
    if contexts is None:
        contexts = {
            "default": config.build_context,
            "run-services": config.source_root,
            "hub-registry": config.build_context / "chummer-hub-registry",
            "fleet-media": config.fleet_media_contracts,
            "design-product": config.design_product_root,
        }
    if context_digests is None:
        context_digests = {
            name: _snapshot_inventory(path, label=f"{name} build context")
            for name, path in contexts.items()
        }
    before_digests = {
        name: _snapshot_inventory(path, label=f"{name} immutable build context")
        for name, path in contexts.items()
    }
    if before_digests != context_digests:
        raise CutoverError("immutable build context changed before image build")
    if unique_tag is None:
        unique_tag = (
            f"chummer-run-api:public-download-{config.source_head[:16]}-"
            f"{secrets.token_hex(4)}"
        )
    tag_match = CANDIDATE_IMAGE_TAG.fullmatch(unique_tag)
    if tag_match is None or tag_match.group(1) != config.source_head[:16]:
        raise CutoverError("candidate image tag is invalid")
    runner.docker(
        [
            "buildx",
            "build",
            "--load",
            "--progress",
            "plain",
            "--file",
            str(contexts["default"] / "Chummer.Run.Api/Dockerfile"),
            "--build-context",
            f"run-services-source={contexts['run-services']}",
            "--build-context",
            "hub-registry-source="
            + str(contexts["hub-registry"]),
            "--build-context",
            f"fleet-media-factory-contracts={contexts['fleet-media']}",
            "--build-context",
            f"design-product={contexts['design-product']}",
            "--build-arg",
            "CHUMMER_BUILD_CONCURRENCY=1",
            "--build-arg",
            "CHUMMER_RUNTIME_UID=1654",
            "--build-arg",
            "CHUMMER_RUNTIME_GID=1654",
            "--label",
            f"org.opencontainers.image.revision={config.source_head}",
            "--label",
            f"run.chummer.runtime-profile={RUNTIME_PROFILE}",
            *[
                item
                for name in sorted(context_digests)
                for item in (
                    "--label",
                    "run.chummer.build-context."
                    f"{name}.sha256={context_digests[name]}",
                )
            ],
            "--tag",
            unique_tag,
            str(contexts["default"]),
        ],
        label="build unique public-download portal image",
        timeout=3600,
    )
    inspection = docker_inspect_json(runner, "image", unique_tag)
    image_id = str(inspection.get("Id") or "")
    labels = inspection.get("Config", {}).get("Labels") or {}
    after_digests = {
        name: _snapshot_inventory(path, label=f"{name} immutable build context")
        for name, path in contexts.items()
    }
    if (
        IMAGE_ID.fullmatch(image_id) is None
        or labels.get("org.opencontainers.image.revision") != config.source_head
        or labels.get("run.chummer.runtime-profile") != RUNTIME_PROFILE
        or after_digests != context_digests
        or any(
            labels.get(f"run.chummer.build-context.{name}.sha256") != digest
            for name, digest in context_digests.items()
        )
    ):
        raise CutoverError("candidate image identity or source labels are invalid")
    if on_built is not None:
        on_built(unique_tag, image_id)
    return unique_tag, image_id


def materialize_compose(
    config: Config,
    runner: Runner,
    receipt_dir: Path,
    image_id: str,
) -> tuple[Path, Path]:
    compose = receipt_dir / "public-download-runtime.json"
    materialization = receipt_dir / "public-download-materialization.json"
    attestation = receipt_dir / "public-download-compose-runtime-attestation.json"
    materializer = config.source_root / "scripts/materialize_public_download_only_compose.py"
    validator = (
        config.source_root / "scripts/validate_public_download_only_compose_runtime.py"
    )
    runner.python(
        materializer,
        [
            "--source-root",
            str(config.source_root),
            "--source-head",
            config.source_head,
            "--source",
            str(config.source_root / "docker-compose.public-edge.yml"),
            "--profile-source",
            str(config.source_root / "docker-compose.public-downloads.yml"),
            "--output",
            str(compose),
            "--receipt-output",
            str(materialization),
            "--candidate-image-id",
            image_id,
            "--operation",
            config.operation,
        ],
        label="materialize revision-bound public-download Compose",
    )
    rendered = runner.compose(
        compose,
        ["config", "--format", "json"],
        label="render public-download Compose",
        overlay_root=config.overlay_root,
    )
    runner.python(
        validator,
        [
            "--operation",
            config.operation,
            "--source-root",
            str(config.source_root),
            "--source-head",
            config.source_head,
            "--materialized-compose",
            str(compose),
            "--materialization-receipt",
            str(materialization),
            "--candidate-image-id",
            image_id,
            "--certificate-source",
            str(config.certificate_file),
            "--certificate-password-source",
            str(config.certificate_password_file),
            "--runtime-proof-source",
            str(config.runtime_proof_source),
            "--output",
            str(attestation),
        ],
        label="attest rendered public-download Compose",
        input_bytes=rendered,
    )
    return compose, attestation


def wait_healthy(
    runner: Runner,
    container_id: str,
    *,
    expected_image: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    while time.monotonic() < deadline:
        inspection = docker_inspect_json(runner, "container", container_id)
        if str(inspection.get("Image") or "") != expected_image:
            raise CutoverError("candidate container image identity changed")
        state = inspection.get("State") or {}
        if state.get("Running") is not True:
            raise CutoverError("candidate portal stopped before becoming healthy")
        last_status = str((state.get("Health") or {}).get("Status") or "")
        if last_status == "healthy":
            return {
                "containerId": container_id,
                "imageId": expected_image,
                "health": "healthy",
                "observedAtUtc": utc_now(),
            }
        time.sleep(2)
    raise CutoverError(
        f"candidate portal did not become healthy (last status {last_status or 'missing'})"
    )


def start_oneoff_portal(
    config: Config,
    runner: Runner,
    compose: Path,
    *,
    name: str,
    overlay_root: Path,
    service_ports: bool,
    image_id: str,
) -> str:
    arguments = ["run", "-T", "-d", "--no-deps"]
    if service_ports:
        arguments.extend(["--service-ports", "--use-aliases"])
    arguments.extend(["--name", name, PORTAL_SERVICE])
    raw = runner.compose(
        compose,
        arguments,
        label="start immutable public-download portal candidate",
        overlay_root=overlay_root,
        timeout=300,
    )
    candidate_id = raw.decode("ascii", errors="strict").strip()
    if CONTAINER_ID.fullmatch(candidate_id) is None:
        raise CutoverError("candidate portal container identity is invalid")
    inspection = docker_inspect_json(runner, "container", candidate_id)
    labels = inspection.get("Config", {}).get("Labels") or {}
    if (
        str(inspection.get("Name") or "").removeprefix("/") != name
        or str(inspection.get("Image") or "") != image_id
        or labels.get("com.docker.compose.project") != CANONICAL_PROJECT
        or labels.get("com.docker.compose.service") != PORTAL_SERVICE
        or str(labels.get("com.docker.compose.oneoff") or "").lower() != "true"
    ):
        raise CutoverError("candidate portal Compose authority is invalid")
    return candidate_id


def stop_container(runner: Runner, identity: str, label: str) -> None:
    runner.docker(["container", "stop", identity], label=f"stop exact {label}")
    if container_runtime(runner, identity)["wasRunning"]:
        raise CutoverError(f"{label} remained running after stop")


def start_container(runner: Runner, identity: str, label: str) -> None:
    runner.docker(["container", "start", identity], label=f"start exact {label}")
    if not container_runtime(runner, identity)["wasRunning"]:
        raise CutoverError(f"{label} did not start")


def remove_oneoff(runner: Runner, identity: str, name: str) -> None:
    inspection = docker_inspect_json(runner, "container", identity)
    labels = inspection.get("Config", {}).get("Labels") or {}
    if (
        str(inspection.get("Name") or "").removeprefix("/") != name
        or labels.get("com.docker.compose.project") != CANONICAL_PROJECT
        or labels.get("com.docker.compose.service") != PORTAL_SERVICE
        or str(labels.get("com.docker.compose.oneoff") or "").lower() != "true"
    ):
        raise CutoverError("temporary portal is outside cleanup authority")
    runner.docker(
        ["container", "rm", "--force", identity],
        label="remove exact temporary portal",
    )


def remove_oneoff_by_exact_name(runner: Runner, name: str) -> bool:
    raw = runner.docker(
        [
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"name=^/{name}$",
        ],
        label="resolve exact temporary portal by name",
    )
    identities = tuple(
        line
        for line in raw.decode("ascii", errors="strict").splitlines()
        if line
    )
    if len(identities) > 1 or any(
        CONTAINER_ID.fullmatch(identity) is None for identity in identities
    ):
        raise CutoverError("temporary portal name resolved ambiguously")
    if not identities:
        return False
    remove_oneoff(runner, identities[0], name)
    return True


def warm_oneoff_portal(
    config: Config,
    runner: Runner,
    compose: Path,
    *,
    name: str,
    overlay_root: Path,
    image_id: str,
) -> dict[str, Any]:
    candidate_id = ""
    start_attempted = False
    try:
        start_attempted = True
        candidate_id = start_oneoff_portal(
            config,
            runner,
            compose,
            name=name,
            overlay_root=overlay_root,
            service_ports=False,
            image_id=image_id,
        )
        return wait_healthy(
            runner,
            candidate_id,
            expected_image=image_id,
            timeout_seconds=config.ready_timeout_seconds,
        )
    finally:
        if candidate_id:
            remove_oneoff(runner, candidate_id, name)
        elif start_attempted:
            remove_oneoff_by_exact_name(runner, name)


def install_linking_inventory(
    config: Config,
    runner: Runner,
    *,
    image_id: str,
    output: Path,
    before: Path | None,
    operation: str | None = None,
) -> dict[str, Any]:
    name = f"chummer-install-link-inventory-{secrets.token_hex(6)}"
    created = runner.docker(
        [
            "container",
            "create",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--mount",
            f"type=volume,src={CANONICAL_STATE_VOLUME},dst=/state,readonly",
            image_id,
        ],
        label="create stopped InstallLinking inventory inspector",
    ).decode("ascii", errors="strict").strip()
    if CONTAINER_ID.fullmatch(created) is None:
        raise CutoverError("InstallLinking inventory inspector identity is invalid")
    try:
        archive = runner.docker(
            ["container", "cp", f"{created}:/state/.", "-"],
            label="capture exact InstallLinking namespace archive",
            timeout=600,
        )
    finally:
        runner.docker(
            ["container", "rm", created],
            label="remove stopped InstallLinking inventory inspector",
        )
    command = "compare" if before is not None else "snapshot"
    arguments = [
        command,
        "--operation",
        operation or config.operation,
        "--source-head",
        config.source_head,
        "--volume",
        CANONICAL_STATE_VOLUME,
        "--output",
        str(output),
    ]
    if before is not None:
        arguments.extend(["--before", str(before)])
    runner.python(
        config.source_root / "scripts/attest_install_linking_state_inventory.py",
        arguments,
        label=f"{command} InstallLinking namespace inventory",
        input_bytes=archive,
        timeout=600,
    )
    return json.loads(
        stable_regular_bytes(
            output,
            label="InstallLinking inventory receipt",
            owner_only=True,
        )
    )


def snapshot_active_authority(config: Config, receipt_dir: Path) -> dict[str, Any]:
    state_path = receipt_dir / "prior-active-runtime-authority-state.json"
    snapshot_path = receipt_dir / "prior-active-runtime-authority.json"
    if config.active_runtime_authority.exists():
        raw = stable_regular_bytes(
            config.active_runtime_authority,
            label="prior active runtime authority",
            owner_only=True,
        )
        atomic_private_write(snapshot_path, raw, replace=False)
        payload = {
            "contractName": "chummer.public-download-only-prior-runtime-authority/v1",
            "status": "pass",
            "existed": True,
            "snapshot": str(snapshot_path),
            "sha256": sha256_bytes(raw),
        }
    else:
        payload = {
            "contractName": "chummer.public-download-only-prior-runtime-authority/v1",
            "status": "pass",
            "existed": False,
            "snapshot": "",
            "sha256": "",
        }
    write_private_json(state_path, payload)
    return payload


def restore_active_authority(config: Config, receipt_dir: Path) -> None:
    state = json.loads(
        stable_regular_bytes(
            receipt_dir / "prior-active-runtime-authority-state.json",
            label="prior active runtime authority state",
            owner_only=True,
        )
    )
    if state.get("existed") is True:
        snapshot = Path(str(state.get("snapshot") or ""))
        raw = stable_regular_bytes(
            snapshot,
            label="prior active runtime authority snapshot",
            owner_only=True,
        )
        if sha256_bytes(raw) != state.get("sha256"):
            raise RecoveryUncertain("prior runtime authority snapshot changed")
        atomic_private_write(config.active_runtime_authority, raw, replace=True)
    elif state.get("existed") is False:
        if config.active_runtime_authority.exists() or config.active_runtime_authority.is_symlink():
            config.active_runtime_authority.unlink()
    else:
        raise RecoveryUncertain("prior runtime authority state is malformed")


def run_recovery(config: Config, runner: Runner) -> dict[str, Any]:
    if not config.transaction_journal.exists():
        return {"status": "pass", "disposition": "no_transaction"}
    transaction = load_module(
        config.source_root / "scripts/public_edge_overlay_transaction.py",
        "chummer_public_download_recovery_transaction",
    )
    journal = transaction.validated_deploy_snapshot(
        config.transaction_journal,
        source_root=config.source_root,
        active_root=config.overlay_root,
        expected_runtime_profile=RUNTIME_PROFILE,
        expected_source_head=config.source_head,
        expected_deployment_operation=CUTOVER_OPERATION,
    )
    authority = journal["deployOverlayAuthority"]
    receipt_dir = Path(authority["activationReceipt"]).parent
    compose = receipt_dir / "public-download-runtime.json"
    output = receipt_dir / "public-download-recovery.json"
    rollback = receipt_dir / "public-download-overlay-rollback.json"
    runner.python(
        config.source_root / "scripts/public_edge_deploy_recovery.py",
        [
            "--source-root",
            str(config.source_root),
            "--active-root",
            str(config.overlay_root),
            "--backup-root",
            str(config.overlay_backup_root),
            "--snapshot",
            str(config.transaction_journal),
            "--activation-receipt",
            authority["activationReceipt"],
            "--overlay-rollback-output",
            str(rollback),
            "--output",
            str(output),
            "--runtime-authority-output",
            str(config.active_runtime_authority),
            "--shared-mutation-lock-token",
            config.shared_lock_token,
            "--docker-config-root",
            str(config.docker_config_root),
            "--docker-context",
            "default",
            "--compose-file",
            str(compose),
            "--env-file",
            str(config.env_file),
            "--project-name",
            CANONICAL_PROJECT,
            "--build-context",
            str(config.build_context),
            "--public-projection-snapshot-root",
            str(config.projection_snapshot_root),
            "--published-port",
            str(CANONICAL_PORT),
            "--portal-image-tag",
            CANONICAL_PORTAL_TAG,
            "--tool-image-tag",
            CANONICAL_TOOL_TAG,
            "--runtime-profile",
            RUNTIME_PROFILE,
        ],
        label="reconcile interrupted public-download cutover",
        timeout=900,
    )
    receipt = json.loads(
        stable_regular_bytes(
            output,
            label="public-download recovery receipt",
            owner_only=True,
        )
    )
    if receipt.get("status") != "pass" or receipt.get("exactPriorStateRestored") is not True:
        raise RecoveryUncertain("public-download recovery did not restore exact prior state")
    before_inventory = receipt_dir / "install-linking-before.json"
    if before_inventory.exists():
        before_payload = json.loads(
            stable_regular_bytes(
                before_inventory,
                label="pre-interruption InstallLinking inventory",
                owner_only=True,
            )
        )
        original_operation = str(before_payload.get("operation") or "")
        if original_operation not in OPERATIONS:
            raise RecoveryUncertain(
                "pre-interruption InstallLinking operation is invalid"
            )
        prior_image = str(journal["runtimePriorState"]["priorPortalImageId"])
        install_linking_inventory(
            config,
            runner,
            image_id=prior_image,
            output=(
                receipt_dir
                / f"install-linking-after-recovery-{secrets.token_hex(4)}.json"
            ),
            before=before_inventory,
            operation=original_operation,
        )
    return receipt


def activate_overlay(config: Config, runner: Runner, output: Path) -> None:
    runner.python(
        config.source_root / "scripts/publish_public_edge_portal_overlay.py",
        [
            "--source-root",
            str(config.source_root),
            "--active-root",
            str(config.overlay_root),
            "--staging-root",
            str(config.overlay_staging_root),
            "--backup-root",
            str(config.overlay_backup_root),
            "--build-root",
            str(config.overlay_build_root),
            "--release-channel-receipt",
            str(config.release_channel_receipt),
            "--release-channel-receipt-sha256",
            config.release_channel_receipt_sha256,
            "--output",
            str(output),
            "--activate",
            "--reuse-staging",
            "--shared-mutation-lock-token",
            config.shared_lock_token,
        ],
        label="activate verified public-edge overlay",
        timeout=900,
    )


def final_postdeploy(
    config: Config,
    runner: Runner,
    *,
    manifest: Path,
    canonical_manifest: Path,
    output: Path,
) -> dict[str, Any]:
    runner.python(
        config.source_root / "scripts/verify_public_download_only_postdeploy.py",
        [
            "--base-url",
            config.base_url,
            "--source-root",
            str(config.source_root),
            "--local-manifest",
            str(manifest),
            "--local-canonical-manifest",
            str(canonical_manifest),
            "--delivery-phase",
            "bootstrap",
            "--output",
            str(output),
        ],
        label="verify public-download-only external serving contract",
        timeout=300,
    )
    return json.loads(
        stable_regular_bytes(
            output,
            label="public-download postdeploy receipt",
            owner_only=True,
        )
    )


def active_public_runtime(config: Config, runner: Runner) -> dict[str, Any] | None:
    if not config.active_runtime_authority.exists():
        return None
    try:
        payload = json.loads(
            stable_regular_bytes(
                config.active_runtime_authority,
                label="active runtime authority",
                owner_only=True,
            )
        )
    except (CutoverError, json.JSONDecodeError):
        return None
    portal = payload.get("portal")
    if (
        set(payload) != PUBLIC_ACTIVE_RUNTIME_AUTHORITY_FIELDS
        or payload.get("contractName")
        != "chummer.public-edge.active-runtime-authority/v1"
        or payload.get("status") != "pass"
        or payload.get("runtimeProfile") != RUNTIME_PROFILE
        or payload.get("sourceHead") != config.source_head
        or payload.get("deploymentOperation") != CUTOVER_OPERATION
        or payload.get("publicProjectionSnapshotId")
        != config.projection_snapshot_id
        or payload.get("publicProjectionSnapshotSha256")
        != config.projection_snapshot_sha256
        or payload.get("publicProjectionManifestSha256")
        != config.projection_manifest_sha256
        or not isinstance(portal, dict)
        or set(portal) != ACTIVE_RUNTIME_PORTAL_FIELDS
        or portal.get("existed") is not True
        or portal.get("wasRunning") is not True
        or portal.get("proofAuthorityMountSha256")
        != config.runtime_proof_sha256
        or portal.get("proofPublicMountSha256")
        != config.runtime_proof_sha256
    ):
        return None
    container_id = str(portal.get("containerId") or "")
    image_id = str(portal.get("imageId") or "")
    if (
        CONTAINER_ID.fullmatch(container_id) is None
        or IMAGE_ID.fullmatch(image_id) is None
        or SAFE_NAME.fullmatch(str(portal.get("containerName") or "")) is None
    ):
        return None
    runtime = container_runtime(runner, container_id)
    if not runtime["wasRunning"] or runtime["imageId"] != image_id:
        return None
    return payload


def _retired_topology_a_execute(config: Config) -> dict[str, Any]:
    journal_was_present = (
        config.transaction_journal.exists()
        or config.transaction_journal.is_symlink()
    )
    if config.operation == RECOVERY_OPERATION and journal_was_present:
        validate_journal_recovery_config(config)
    else:
        validate_config(config)
    runner = Runner(config)
    scripts = config.source_root / "scripts"
    attestor = load_module(
        scripts / "attest_initial_release_shelf_cutover.py",
        "chummer_public_download_migration_attestor",
    )
    generation = load_module(
        scripts / "release_shelf_generation.py",
        "chummer_public_download_release_generation",
    )
    transaction = load_module(
        scripts / "public_edge_overlay_transaction.py",
        "chummer_public_download_overlay_transaction",
    )

    recovery_receipt: dict[str, Any] | None = None
    if journal_was_present:
        try:
            recovery_receipt = run_recovery(config, runner)
        except Exception as exc:
            raise RecoveryUncertain("interrupted public-download cutover is not recoverable") from exc

    if config.operation == RECOVERY_OPERATION and journal_was_present:
        return {
            "contractName": CONTRACT_NAME,
            "status": "pass",
            "operation": config.operation,
            "runtimeProfile": RUNTIME_PROFILE,
            "disposition": "interrupted_cutover_recovered_to_exact_prior_state",
            "recovery": recovery_receipt,
        }

    if config.operation == RECOVERY_OPERATION:
        if active_public_runtime(config, runner) is None:
            raise CutoverError(
                "recovery-only operation found neither a journal nor an exact "
                "source-and-projection-bound active public runtime"
            )
        required_committed_migration_paths = (
            config.migration_state_root / attestor.PRESTATE_NAME,
            config.migration_state_root / attestor.START_NAME,
            config.migration_state_root / attestor.POSTSTATE_NAME,
            config.shelf_root / generation.CURRENT_POINTER,
            config.shelf_root / generation.LAYOUT_MARKER,
        )
        if not all(path.is_file() and not path.is_symlink() for path in required_committed_migration_paths):
            raise CutoverError(
                "recovery-only operation refuses to begin or repair an "
                "uncommitted release-shelf migration"
            )
        migration, generation_manifest, generation_canonical = migrate_shelf(
            config,
            attestor=attestor,
            generation=generation,
        )
        receipt_dir = Path(
            tempfile.mkdtemp(prefix="public-download.recovery.", dir=config.receipt_root)
        )
        receipt_dir.chmod(0o700)
        postdeploy = final_postdeploy(
            config,
            runner,
            manifest=generation_manifest,
            canonical_manifest=generation_canonical,
            output=receipt_dir / "public-download-postdeploy.json",
        )
        result = {
            "contractName": CONTRACT_NAME,
            "status": "pass",
            "operation": config.operation,
            "runtimeProfile": RUNTIME_PROFILE,
            "disposition": "already_committed_and_serving",
            "migration": migration,
            "recovery": recovery_receipt,
            "postdeploy": postdeploy,
        }
        write_private_json(receipt_dir / "deployment.json", result)
        return result

    incumbent_portal, incumbent_tunnel = require_incumbent_runtime(runner)
    serving_before = http_manifest_observation(
        base_url=config.base_url,
        manifest_root=config.shelf_root,
        portal_id=incumbent_portal["containerId"],
        runner=runner,
        phase="before-pointer-activation",
    )
    migration, generation_manifest, generation_canonical = migrate_shelf(
        config,
        attestor=attestor,
        generation=generation,
    )
    # The preserved top-level manifests must still be served by the exact
    # incumbent after the incumbent-equivalent pointer commit.
    serving_after_migration = http_manifest_observation(
        base_url=config.base_url,
        manifest_root=generation_manifest.parent,
        portal_id=incumbent_portal["containerId"],
        runner=runner,
        phase="after-pointer-activation",
    )

    receipt_dir = Path(
        tempfile.mkdtemp(prefix="public-download.", dir=config.receipt_root)
    )
    receipt_dir.chmod(0o700)
    activation_receipt = receipt_dir / "overlay-activation.json"
    stage_receipt = stage_overlay(config, runner, receipt_dir)
    prior_portal_tag = resolve_image_tag(runner, CANONICAL_PORTAL_TAG)
    prior_tool_tag = resolve_image_tag(runner, CANONICAL_TOOL_TAG)
    build_contexts, build_context_digests, build_context_receipt = (
        prepare_immutable_build_contexts(config, receipt_dir)
    )
    unique_tag, candidate_image_id = build_candidate_image(
        config,
        runner,
        contexts=build_contexts,
        context_digests=build_context_digests,
    )
    compose, compose_attestation = materialize_compose(
        config,
        runner,
        receipt_dir,
        candidate_image_id,
    )
    if resolve_image_tag(runner, unique_tag) != candidate_image_id:
        raise CutoverError("candidate image tag changed before runtime use")

    before_inventory_path = receipt_dir / "install-linking-before.json"
    before_inventory = install_linking_inventory(
        config,
        runner,
        image_id=candidate_image_id,
        output=before_inventory_path,
        before=None,
    )
    warm_name = f"chummer-public-download-warm-{secrets.token_hex(5)}"
    warm_health = warm_oneoff_portal(
        config,
        runner,
        compose,
        name=warm_name,
        overlay_root=config.overlay_staging_root,
        image_id=candidate_image_id,
    )
    serving_after_warm = http_manifest_observation(
        base_url=config.base_url,
        manifest_root=generation_manifest.parent,
        portal_id=incumbent_portal["containerId"],
        runner=runner,
        phase="after-replacement-warmup-healthy",
    )

    proof_snapshot = receipt_dir / "candidate-proof-bind-source.json"
    atomic_private_write(
        proof_snapshot,
        stable_regular_bytes(
            config.runtime_proof_source,
            label="candidate runtime proof source",
        ),
        replace=False,
    )
    prior_authority_snapshot = receipt_dir / "prior-proof-authority-mount.json"
    prior_public_snapshot = receipt_dir / "prior-proof-public-mount.json"
    prior_authority_sha = copy_container_file(
        runner,
        incumbent_portal["containerId"],
        "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json",
        prior_authority_snapshot,
    )
    prior_public_sha = copy_container_file(
        runner,
        incumbent_portal["containerId"],
        "/app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
        prior_public_snapshot,
    )
    if prior_authority_sha != prior_public_sha:
        raise CutoverError("incumbent proof mounts cannot be restored from one source")
    candidate_name = f"chummer-public-edge-candidate-{secrets.token_hex(6)}"
    prior_runtime_state = {
        "candidatePortalContainerName": candidate_name,
        "expectedRuntimeProofBindSourceSha256": config.runtime_proof_sha256,
        "publicProjectionManifestSha256": config.projection_manifest_sha256,
        "publicProjectionSnapshotId": config.projection_snapshot_id,
        "publicProjectionSnapshotSha256": config.projection_snapshot_sha256,
        "priorImageTagId": prior_portal_tag,
        "priorToolImageTagId": prior_tool_tag,
        "priorPortalContainerId": incumbent_portal["containerId"],
        "priorPortalContainerName": incumbent_portal["containerName"],
        "priorPortalImageId": incumbent_portal["imageId"],
        "priorPortalProofAuthorityMountSha256": prior_authority_sha,
        "priorPortalProofPublicMountSha256": prior_public_sha,
        "priorPortalExisted": True,
        "priorPortalWasRunning": True,
        "priorTunnelContainerId": incumbent_tunnel["containerId"],
        "priorTunnelImageId": incumbent_tunnel["imageId"],
        "priorTunnelExisted": True,
        "priorTunnelWasRunning": True,
    }
    prior_active_authority = snapshot_active_authority(config, receipt_dir)
    transaction.snapshot(
        source_root=config.source_root,
        active_root=config.overlay_root,
        output=config.transaction_journal,
        shared_mutation_lock_token=config.shared_lock_token,
        runtime_prior_state=prior_runtime_state,
        staging_root=config.overlay_staging_root,
        backup_root=config.overlay_backup_root,
        activation_receipt=activation_receipt,
        proof_bind_source=config.runtime_proof_source,
        candidate_proof_bind_source_snapshot=proof_snapshot,
        prior_portal_proof_authority_snapshot=prior_authority_snapshot,
        prior_portal_proof_public_snapshot=prior_public_snapshot,
        runtime_profile=RUNTIME_PROFILE,
        deployment_operation=config.operation,
        source_head=config.source_head,
        prior_active_runtime_authority_existed=prior_active_authority["existed"],
        prior_active_runtime_authority_snapshot=(
            Path(prior_active_authority["snapshot"])
            if prior_active_authority["existed"]
            else None
        ),
        prior_active_runtime_authority_snapshot_sha256=(
            prior_active_authority["sha256"]
            if prior_active_authority["existed"]
            else None
        ),
    )

    candidate_id = ""
    try:
        for phase in ("image_build_started", "image_built"):
            transaction.mark_phase(
                source_root=config.source_root,
                active_root=config.overlay_root,
                journal_path=config.transaction_journal,
                phase=phase,
                shared_mutation_lock_token=config.shared_lock_token,
            )
        stop_container(runner, incumbent_tunnel["containerId"], "incumbent tunnel")
        transaction.mark_phase(
            source_root=config.source_root,
            active_root=config.overlay_root,
            journal_path=config.transaction_journal,
            phase="tunnel_drained",
            shared_mutation_lock_token=config.shared_lock_token,
        )
        stop_container(runner, incumbent_portal["containerId"], "incumbent portal")
        transaction.mark_phase(
            source_root=config.source_root,
            active_root=config.overlay_root,
            journal_path=config.transaction_journal,
            phase="portal_stopped",
            shared_mutation_lock_token=config.shared_lock_token,
        )
        activate_overlay(config, runner, activation_receipt)
        transaction.mark_phase(
            source_root=config.source_root,
            active_root=config.overlay_root,
            journal_path=config.transaction_journal,
            phase="overlay_activated",
            shared_mutation_lock_token=config.shared_lock_token,
        )
        if resolve_image_tag(runner, unique_tag) != candidate_image_id:
            raise CutoverError("candidate image identity changed before portal start")
        candidate_id = start_oneoff_portal(
            config,
            runner,
            compose,
            name=candidate_name,
            overlay_root=config.overlay_root,
            service_ports=True,
            image_id=candidate_image_id,
        )
        candidate_health = wait_healthy(
            runner,
            candidate_id,
            expected_image=candidate_image_id,
            timeout_seconds=config.ready_timeout_seconds,
        )
        transaction.mark_phase(
            source_root=config.source_root,
            active_root=config.overlay_root,
            journal_path=config.transaction_journal,
            phase="portal_candidate_started",
            shared_mutation_lock_token=config.shared_lock_token,
        )
        start_container(runner, incumbent_tunnel["containerId"], "incumbent tunnel")
        transaction.mark_phase(
            source_root=config.source_root,
            active_root=config.overlay_root,
            journal_path=config.transaction_journal,
            phase="tunnel_started",
            shared_mutation_lock_token=config.shared_lock_token,
        )
        postdeploy = final_postdeploy(
            config,
            runner,
            manifest=generation_manifest,
            canonical_manifest=generation_canonical,
            output=receipt_dir / "public-download-postdeploy.json",
        )
        after_inventory = install_linking_inventory(
            config,
            runner,
            image_id=candidate_image_id,
            output=receipt_dir / "install-linking-after.json",
            before=before_inventory_path,
        )
        if (
            resolve_image_tag(runner, CANONICAL_PORTAL_TAG) != prior_portal_tag
            or resolve_image_tag(runner, CANONICAL_TOOL_TAG) != prior_tool_tag
        ):
            raise CutoverError("canonical portal or tool image tag changed")
        transaction.complete_transaction(
            source_root=config.source_root,
            active_root=config.overlay_root,
            journal_path=config.transaction_journal,
            runtime_authority_output=config.active_runtime_authority,
            candidate_portal_container_id=candidate_id,
            candidate_portal_container_name=candidate_name,
            candidate_portal_image_id=candidate_image_id,
            install_linking_authority_readiness=None,
            install_linking_authority_readiness_sha256=None,
            shared_mutation_lock_token=config.shared_lock_token,
            runtime_profile=RUNTIME_PROFILE,
        )
    except Exception as original:
        try:
            run_recovery(config, runner)
        except Exception as recovery_error:
            raise RecoveryUncertain(
                "public-download cutover failed and exact recovery is uncertain"
            ) from recovery_error
        raise CutoverError("public-download cutover failed after exact recovery") from original

    result = {
        "contractName": CONTRACT_NAME,
        "status": "pass",
        "operation": config.operation,
        "runtimeProfile": RUNTIME_PROFILE,
        "sourceHead": config.source_head,
        "candidateImageId": candidate_image_id,
        "candidatePortalContainerId": candidate_id,
        "candidatePortalHealth": candidate_health,
        "canonicalPortalImageTagUnchanged": True,
        "canonicalToolImageTagUnchanged": True,
        "postgresServiceStarted": False,
        "initializerServiceStarted": False,
        "migration": migration,
        "overlayStageReceipt": str(stage_receipt),
        "immutableBuildContextReceipt": str(build_context_receipt),
        "immutableBuildContextDigests": build_context_digests,
        "composeAttestation": str(compose_attestation),
        "postdeploy": postdeploy,
        "installLinkingBefore": before_inventory,
        "installLinkingAfter": after_inventory,
        "servingContinuity": {
            "incumbentPortalContainerId": incumbent_portal["containerId"],
            "incumbentTunnelContainerId": incumbent_tunnel["containerId"],
            "incumbentEquivalentGenerationActivated": True,
            "legacyTopLevelManifestBytesPreserved": True,
            "incumbentRemainedRunningUntilReplacementWarmupHealthy": True,
            "replacementWarmup": warm_health,
            "observations": [
                serving_before,
                serving_after_migration,
                serving_after_warm,
            ],
        },
        "completedAtUtc": utc_now(),
    }
    write_private_json(receipt_dir / "deployment.json", result)
    return result


def _retired_topology_a_parse_args(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=tuple(sorted(OPERATIONS)), required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--shared-mutation-lock-token", required=True)
    parser.add_argument("--shelf-root", type=Path, required=True)
    parser.add_argument("--migration-state-root", type=Path, required=True)
    parser.add_argument("--migration-candidate-root", type=Path, required=True)
    parser.add_argument("--migration-authority", type=Path, required=True)
    parser.add_argument("--migration-authority-sha256", required=True)
    parser.add_argument("--release-candidate-root", type=Path, required=True)
    parser.add_argument(
        "--candidate-import-authority",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--candidate-import-authority-sha256",
        required=True,
    )
    parser.add_argument("--direct-import-receipt", type=Path, required=True)
    parser.add_argument("--direct-import-receipt-sha256", required=True)
    parser.add_argument("--release-channel-receipt", type=Path, required=True)
    parser.add_argument("--release-channel-receipt-sha256", required=True)
    parser.add_argument("--projection-snapshot-root", type=Path, required=True)
    parser.add_argument("--projection-snapshot-id", required=True)
    parser.add_argument("--projection-snapshot-sha256", required=True)
    parser.add_argument(
        "--projection-snapshot-tree-sha256",
        dest="projection_source_tree_sha256",
        required=True,
    )
    parser.add_argument("--projection-manifest-sha256", required=True)
    parser.add_argument("--runtime-proof-source", type=Path, required=True)
    parser.add_argument("--runtime-proof-sha256", required=True)
    parser.add_argument("--certificate-file", type=Path, required=True)
    parser.add_argument("--certificate-password-file", type=Path, required=True)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--overlay-staging-root", type=Path, required=True)
    parser.add_argument("--overlay-backup-root", type=Path, required=True)
    parser.add_argument("--overlay-build-root", type=Path, required=True)
    parser.add_argument("--transaction-journal", type=Path, required=True)
    parser.add_argument("--active-runtime-authority", type=Path, required=True)
    parser.add_argument("--docker-config-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--build-context", type=Path, required=True)
    parser.add_argument("--fleet-media-contracts", type=Path, required=True)
    parser.add_argument("--design-product-root", type=Path, required=True)
    parser.add_argument("--ready-timeout-seconds", type=int, default=180)
    args = parser.parse_args(argv)
    raw_shelf_root = args.shelf_root
    try:
        shelf_metadata = raw_shelf_root.lstat()
        resolved_shelf_root = raw_shelf_root.resolve(strict=True)
    except OSError as exc:
        raise CutoverError("canonical release shelf is unavailable") from exc
    if (
        raw_shelf_root != CANONICAL_RELEASE_SHELF_ROOT
        or resolved_shelf_root != raw_shelf_root
        or not stat.S_ISDIR(shelf_metadata.st_mode)
        or stat.S_ISLNK(shelf_metadata.st_mode)
    ):
        raise CutoverError(
            "release shelf must be the exact non-symlink canonical shelf root"
        )
    journal_recovery = (
        args.operation == RECOVERY_OPERATION
        and (
            args.transaction_journal.exists()
            or args.transaction_journal.is_symlink()
        )
    )

    def exact_input(path: Path) -> Path:
        return path if journal_recovery else path.resolve(strict=True)

    return Config(
        operation=args.operation,
        source_root=args.source_root.resolve(strict=True),
        source_head=args.source_head,
        shared_lock_token=args.shared_mutation_lock_token,
        shelf_root=raw_shelf_root,
        migration_state_root=args.migration_state_root,
        migration_candidate_root=args.migration_candidate_root,
        migration_authority=exact_input(args.migration_authority),
        migration_authority_sha256=args.migration_authority_sha256,
        release_candidate_root=cutover_input(
            args.release_candidate_root,
            "sealed release candidate",
        ),
        candidate_import_authority=cutover_input(
            args.candidate_import_authority,
            "candidate import authority",
        ),
        candidate_import_authority_sha256=(
            args.candidate_import_authority_sha256
        ),
        direct_import_receipt=cutover_input(
            args.direct_import_receipt,
            "sealed direct-import receipt",
        ),
        direct_import_receipt_sha256=args.direct_import_receipt_sha256,
        release_channel_receipt=exact_input(args.release_channel_receipt),
        release_channel_receipt_sha256=args.release_channel_receipt_sha256,
        projection_snapshot_root=args.projection_snapshot_root.resolve(strict=True),
        projection_snapshot_id=args.projection_snapshot_id,
        projection_snapshot_sha256=args.projection_snapshot_sha256,
        projection_source_tree_sha256=(
            args.projection_source_tree_sha256
        ),
        projection_manifest_sha256=args.projection_manifest_sha256,
        runtime_proof_source=exact_input(args.runtime_proof_source),
        runtime_proof_sha256=args.runtime_proof_sha256,
        certificate_file=exact_input(args.certificate_file),
        certificate_password_file=exact_input(
            args.certificate_password_file
        ),
        overlay_root=args.overlay_root,
        overlay_staging_root=args.overlay_staging_root,
        overlay_backup_root=args.overlay_backup_root,
        overlay_build_root=args.overlay_build_root,
        transaction_journal=args.transaction_journal,
        active_runtime_authority=args.active_runtime_authority,
        docker_config_root=args.docker_config_root.resolve(strict=True),
        env_file=exact_input(args.env_file),
        receipt_root=args.receipt_root,
        base_url=args.base_url,
        build_context=exact_input(args.build_context),
        fleet_media_contracts=exact_input(args.fleet_media_contracts),
        design_product_root=exact_input(args.design_product_root),
        ready_timeout_seconds=args.ready_timeout_seconds,
    )


TOPOLOGY_B_CONTRACT = "chummer.public-download-only-topology-b/v1"
TOPOLOGY_B_OPERATION_SCHEMA = "chummer.public-download-only-operation/v1"
TOPOLOGY_B_ACTIVE_SCHEMA = "chummer.public-download-only-active-runtime/v1"
TOPOLOGY_B_PUBLIC_RETIREMENT_CONTRACT = (
    "chummer6-hub.topology-b-committed-retirement.v1"
)
TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME = (
    "TOPOLOGY_B_RETIREMENT.generated.json"
)
TOPOLOGY_B_PUBLIC_RETIREMENT_MATERIALIZATION_CONTRACT = (
    "chummer.public-download-topology-b-retirement-proof-materialization/v2"
)
TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY = "topology-b-retirement"
TOPOLOGY_B_SOURCE_REPOSITORY = "ArchonMegalon/chummer6-hub"
TOPOLOGY_B_SOURCE_REF = "refs/heads/main"
TOPOLOGY_B_CANONICAL_UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-"
    r"(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)
CANONICAL_DOWNLOADS_BASE_URL = "https://chummer.run/downloads"
CANONICAL_DOWNLOADS_MANIFEST_URL = (
    f"{CANONICAL_DOWNLOADS_BASE_URL}/RELEASE_CHANNEL.generated.json"
)
CANONICAL_DOWNLOADS_PUBLISHER_PATH = (
    "scripts/publish-download-bundle-http.sh"
)
SCOPE_BOUND_EXISTING_BYTES_PROFILE = (
    "v3_scope_bound_existing_windows_bytes"
)
SCOPE_BOUND_SOURCE_COMMIT_POSTURE = {
    "hub": "cutover_source_head_required",
    "registry": "bound_to_sealed_manifest_aliases",
    "ui": "caller_asserted_unverified_informational",
}
SCOPE_BOUND_SOURCE_COMMIT_VERIFICATION = {
    "hub": "verified_against_cutover_source_head",
    "registry": "verified_against_manifest_aliases",
    "ui": "caller_asserted_unverified_informational",
}
SCOPE_BOUND_REVIEW_EVIDENCE_PATHS = (
    "release-evidence/CURRENT.json",
    "release-evidence/RELEASE_DECISION.json",
    "release-evidence/SNAPSHOT.json",
)
SCOPE_BOUND_STARTUP_SMOKE_PATH = (
    "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json"
)
SCOPE_BOUND_CANDIDATE_ADJUNCT_PATHS = frozenset(
    {
        *SCOPE_BOUND_REVIEW_EVIDENCE_PATHS,
        SCOPE_BOUND_STARTUP_SMOKE_PATH,
    }
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
SIDECAR_ORIGIN = "http://172.17.0.1:18091"
SIDECAR_ADDRESS = "172.17.0.1"
SIDECAR_PORT = 18091
SIDECAR_HOSTS = ("chummer.run", "www.chummer.run")
CF_ACCOUNT_ID = re.compile(r"^[0-9a-f]{32}$")
CF_TUNNEL_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SIDECAR_PROJECT = re.compile(r"^chummer-public-download-[a-z0-9-]{8,80}$")
CANDIDATE_IMAGE_TAG = re.compile(
    r"^chummer-run-api:public-download-([0-9a-f]{16})-([0-9a-f]{8})$"
)
CANDIDATE_BUILD_CONTEXT_NAMES = frozenset(
    {
        "default",
        "run-services",
        "hub-registry",
        "fleet-media",
        "design-product",
    }
)
SIDECAR_LOGICAL_VOLUMES = (
    "public-download-app",
    "public-download-fleet",
    "public-download-state",
    "public-download-upload-sessions",
    "public-download-windows-proof",
    "public-download-windows-proof-upload",
    "public-download-runtime-secrets",
    "public-download-projection",
    "public-download-proofs",
    "public-download-shelf",
)
SIDECAR_VOLUME_ENVIRONMENT = {
    "public-download-app": "CHUMMER_PUBLIC_DOWNLOAD_APP_VOLUME",
    "public-download-fleet": "CHUMMER_PUBLIC_DOWNLOAD_FLEET_VOLUME",
    "public-download-state": "CHUMMER_PUBLIC_DOWNLOAD_STATE_VOLUME",
    "public-download-upload-sessions": (
        "CHUMMER_PUBLIC_DOWNLOAD_UPLOAD_SESSIONS_VOLUME"
    ),
    "public-download-windows-proof": (
        "CHUMMER_PUBLIC_DOWNLOAD_WINDOWS_PROOF_VOLUME"
    ),
    "public-download-windows-proof-upload": (
        "CHUMMER_PUBLIC_DOWNLOAD_WINDOWS_PROOF_UPLOAD_VOLUME"
    ),
    "public-download-runtime-secrets": (
        "CHUMMER_PUBLIC_DOWNLOAD_RUNTIME_SECRETS_VOLUME"
    ),
    "public-download-projection": "CHUMMER_PUBLIC_DOWNLOAD_PROJECTION_VOLUME",
    "public-download-proofs": "CHUMMER_PUBLIC_DOWNLOAD_PROOFS_VOLUME",
    "public-download-shelf": "CHUMMER_PUBLIC_DOWNLOAD_SHELF_VOLUME",
}
PLAYWRIGHT_PYTHON_DISTRIBUTION_ENTRIES = (
    "greenlet",
    "greenlet-3.5.2.dist-info",
    "playwright",
    "playwright-1.60.0.dist-info",
    "pyee",
    "pyee-13.0.1.dist-info",
    "typing_extensions.py",
    "typing_extensions-4.15.0.dist-info",
)
PLAYWRIGHT_PYTHON_DISTRIBUTION_VERSIONS = {
    "greenlet-3.5.2.dist-info": "3.5.2",
    "playwright-1.60.0.dist-info": "1.60.0",
    "pyee-13.0.1.dist-info": "13.0.1",
    "typing_extensions-4.15.0.dist-info": "4.15.0",
}
PLAYWRIGHT_BROWSER_EXECUTABLES = (
    Path("chromium_headless_shell-1223")
    / "chrome-headless-shell-linux64"
    / "chrome-headless-shell",
)


@dataclass(frozen=True)
class SidecarConfig:
    operation: str
    source_root: Path
    source_head: str
    shared_lock_token: str
    shelf_root: Path
    migration_candidate_root: Path
    migration_authority: Path
    migration_authority_sha256: str
    release_candidate_root: Path
    candidate_import_authority: Path
    candidate_import_authority_sha256: str
    direct_import_receipt: Path
    direct_import_receipt_sha256: str
    manifest_closure_restoration_spec: Path
    manifest_closure_restoration_spec_sha256: str
    release_channel_receipt: Path
    release_channel_receipt_sha256: str
    projection_snapshot_root: Path
    projection_snapshot_id: str
    projection_snapshot_sha256: str
    projection_source_tree_sha256: str
    projection_manifest_sha256: str
    runtime_proof_source: Path
    runtime_proof_sha256: str
    final_gold_source: Path
    final_gold_sha256: str
    fleet_source: Path
    fleet_sha256: str
    operation_root: Path
    active_runtime_authority: Path
    docker_config_root: Path
    cloudflare_credentials_file: Path
    cloudflare_account_id: str
    cloudflare_tunnel_id: str
    cloudflare_api_base: str
    receipt_root: Path
    base_url: str
    build_context: Path
    fleet_media_contracts: Path
    design_product_root: Path
    delivery_phase: str
    ready_timeout_seconds: int
    controller_source_head: str = ""
    canonical_publisher_sha256: str = ""

    @property
    def project_name(self) -> str:
        return self.operation_root.name

    @property
    def bind_address(self) -> str:
        return SIDECAR_ADDRESS

    @property
    def bind_port(self) -> int:
        return SIDECAR_PORT

    @property
    def canonical_project(self) -> str:
        return CANONICAL_PROJECT

    @property
    def canonical_shelf_root(self) -> Path:
        return self.shelf_root

    @property
    def sidecar_dp_certificate(self) -> Path:
        return self.sidecar_certificate

    @property
    def sidecar_dp_password(self) -> Path:
        return self.sidecar_certificate_password

    @property
    def operation_journal(self) -> Path:
        return self.receipt_root / f"{self.project_name}.operation.json"

    @property
    def shelf_source(self) -> Path:
        return self.operation_root / "release-shelf"

    @property
    def overlay_root(self) -> Path:
        return self.operation_root / "overlay-active-unused" / "app"

    @property
    def overlay_staging_root(self) -> Path:
        return self.operation_root / "app-overlay"

    @property
    def overlay_backup_root(self) -> Path:
        return self.operation_root / "overlay-backups-unused"

    @property
    def overlay_build_root(self) -> Path:
        return self.operation_root / "overlay-build"

    @property
    def host_build_root(self) -> Path:
        return self.operation_root / "host-build"

    @property
    def playwright_python_root(self) -> Path:
        return self.host_build_root / "playwright-python"

    @property
    def compose_file(self) -> Path:
        return self.operation_root / "public-download-runtime.json"

    @property
    def materialization_receipt(self) -> Path:
        return self.operation_root / "compose-materialization.json"

    @property
    def runtime_attestation(self) -> Path:
        return self.operation_root / "compose-runtime-attestation.json"

    @property
    def cloudflare_journal(self) -> Path:
        return self.operation_root / "cloudflare-transaction.json"

    @property
    def cloudflare_lock(self) -> Path:
        return self.operation_root / "cloudflare-transaction.lock"

    @property
    def cloudflare_committed_evidence(self) -> Path:
        return self.operation_root / "cloudflare-committed.json"

    @property
    def cloudflare_rollback_evidence(self) -> Path:
        return self.operation_root / "cloudflare-rolled-back.json"

    @property
    def cloudflare_retirement_evidence(self) -> Path:
        return self.operation_root / "cloudflare-retirement-committed.json"

    @property
    def retired_active_authority(self) -> Path:
        return self.operation_root / "retired-active-runtime-authority.json"

    @property
    def retirement_receipt(self) -> Path:
        return self.operation_root / "topology-b-retirement.json"

    @property
    def public_retirement_proof(self) -> Path:
        return (
            self.operation_root
            / "topology-b-public-retirement-proof.json"
        )

    @property
    def public_retirement_materialization_receipt(self) -> Path:
        return (
            self.operation_root
            / "topology-b-public-retirement-proof-materialization.json"
        )

    @property
    def external_probe_receipt(self) -> Path:
        return self.operation_root / "cloudflare-external-probe.json"

    @property
    def prepared_active_authority(self) -> Path:
        return self.operation_root / "prepared-active-runtime.json"

    @property
    def sidecar_certificate(self) -> Path:
        return self.operation_root / "sidecar-data-protection.pfx"

    @property
    def sidecar_certificate_password(self) -> Path:
        return self.operation_root / "sidecar-data-protection.password"

    @property
    def volume_names(self) -> dict[str, str]:
        return {
            logical: (
                f"{self.project_name}-"
                f"{logical.removeprefix('public-download-')}"
            )
            for logical in SIDECAR_LOGICAL_VOLUMES
        }


def _validate_playwright_python_closure(root: Path) -> None:
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise CutoverError(
            "operation-private Playwright Python closure root is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
        or root.resolve(strict=True) != root
    ):
        raise CutoverError(
            "operation-private Playwright Python closure root is unsafe"
        )
    try:
        entries = {entry.name for entry in os.scandir(root)}
    except OSError as exc:
        raise CutoverError(
            "operation-private Playwright Python closure is unavailable"
        ) from exc
    if entries != set(PLAYWRIGHT_PYTHON_DISTRIBUTION_ENTRIES):
        raise CutoverError(
            "operation-private Playwright Python closure has an unexpected file set"
        )
    for directory, directory_names, file_names in os.walk(
        root,
        followlinks=False,
    ):
        parent = Path(directory)
        for name in [*directory_names, *file_names]:
            candidate = parent / name
            try:
                metadata = candidate.lstat()
            except OSError as exc:
                raise CutoverError(
                    "operation-private Playwright Python closure changed"
                ) from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise CutoverError(
                    "operation-private Playwright Python closure contains a symlink"
                )
            if candidate.name.endswith(".pth"):
                raise CutoverError(
                    "operation-private Playwright Python closure contains a path hook"
                )
            if metadata.st_uid != os.getuid():
                raise CutoverError(
                    "operation-private Playwright Python closure has a foreign owner"
                )
            if stat.S_ISDIR(metadata.st_mode):
                if stat.S_IMODE(metadata.st_mode) != 0o700:
                    raise CutoverError(
                        "operation-private Playwright Python directory is not private"
                    )
            elif stat.S_ISREG(metadata.st_mode):
                if metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) & 0o077:
                    raise CutoverError(
                        "operation-private Playwright Python file is not private"
                    )
            else:
                raise CutoverError(
                    "operation-private Playwright Python closure contains a special entry"
                )
    for distribution, expected_version in (
        PLAYWRIGHT_PYTHON_DISTRIBUTION_VERSIONS.items()
    ):
        metadata = stable_regular_bytes(
            root / distribution / "METADATA",
            label=f"{distribution} metadata",
        ).decode("utf-8")
        versions = [
            line.removeprefix("Version: ").strip()
            for line in metadata.splitlines()
            if line.startswith("Version: ")
        ]
        if versions != [expected_version]:
            raise CutoverError(
                "operation-private Playwright Python distribution version drifted"
            )


def prepare_operation_host_build(
    config: SidecarConfig,
) -> dict[str, Any]:
    host_build_root = private_directory(config.host_build_root, create=True)
    private_paths = {
        name: private_directory(host_build_root / name, create=True)
        for name in (
            "home",
            "dotnet-cli",
            "nuget-packages",
            "nuget-http-cache",
            "tmp",
            "sdk",
        )
    }
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)
    source_python_root = (
        account_home
        / ".local"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    if not source_python_root.is_dir() or source_python_root.is_symlink():
        raise CutoverError("host Playwright Python authority is unavailable")
    browser_root = private_directory(
        account_home / ".cache" / "ms-playwright",
        create=False,
    )
    for relative_executable in PLAYWRIGHT_BROWSER_EXECUTABLES:
        executable = browser_root / relative_executable
        try:
            metadata = executable.lstat()
        except OSError as exc:
            raise CutoverError(
                "host Playwright browser authority is incomplete"
            ) from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or not os.access(executable, os.X_OK)
        ):
            raise CutoverError("host Playwright browser executable is unsafe")

    closure_root = config.playwright_python_root
    if not closure_root.exists() and not closure_root.is_symlink():
        temporary_root = Path(
            tempfile.mkdtemp(
                prefix=".playwright-python.",
                dir=host_build_root,
            )
        )
        try:
            temporary_root.chmod(0o700)
            for entry_name in PLAYWRIGHT_PYTHON_DISTRIBUTION_ENTRIES:
                source = source_python_root / entry_name
                if not source.exists() or source.is_symlink():
                    raise CutoverError(
                        "host Playwright Python authority is incomplete"
                    )
                destination = temporary_root / entry_name
                if source.is_dir():
                    shutil.copytree(source, destination, symlinks=True)
                elif source.is_file():
                    shutil.copy2(source, destination, follow_symlinks=False)
                else:
                    raise CutoverError(
                        "host Playwright Python authority contains a special entry"
                    )
            for directory, _directory_names, file_names in os.walk(
                temporary_root,
                followlinks=False,
            ):
                parent = Path(directory)
                parent.chmod(0o700)
                for file_name in file_names:
                    file_path = parent / file_name
                    metadata = file_path.lstat()
                    if stat.S_ISLNK(metadata.st_mode):
                        raise CutoverError(
                            "host Playwright Python authority contains a symlink"
                        )
                    file_path.chmod(
                        0o700 if stat.S_IMODE(metadata.st_mode) & 0o100 else 0o600
                    )
            os.replace(temporary_root, closure_root)
        finally:
            if temporary_root.exists():
                shutil.rmtree(temporary_root)
    _validate_playwright_python_closure(closure_root)

    operation_browser_root = private_directory(
        host_build_root / "playwright-browsers",
        create=True,
    )
    browser_revision_root = operation_browser_root / "chromium_headless_shell-1223"
    if not browser_revision_root.exists() and not browser_revision_root.is_symlink():
        temporary_browser_root = Path(
            tempfile.mkdtemp(
                prefix=".chromium-headless-shell.",
                dir=host_build_root,
            )
        )
        try:
            temporary_browser_root.chmod(0o700)
            source_revision_root = browser_root / "chromium_headless_shell-1223"
            shutil.copytree(
                source_revision_root,
                temporary_browser_root / "chromium_headless_shell-1223",
                symlinks=True,
            )
            copied_revision_root = (
                temporary_browser_root / "chromium_headless_shell-1223"
            )
            for directory, _directory_names, file_names in os.walk(
                copied_revision_root,
                followlinks=False,
            ):
                parent = Path(directory)
                if parent.is_symlink():
                    raise CutoverError(
                        "host Playwright browser authority contains a symlink"
                    )
                parent.chmod(0o700)
                for file_name in file_names:
                    file_path = parent / file_name
                    metadata = file_path.lstat()
                    if stat.S_ISLNK(metadata.st_mode):
                        raise CutoverError(
                            "host Playwright browser authority contains a symlink"
                        )
                    if not stat.S_ISREG(metadata.st_mode):
                        raise CutoverError(
                            "host Playwright browser authority contains a special entry"
                        )
                    file_path.chmod(
                        0o700 if stat.S_IMODE(metadata.st_mode) & 0o100 else 0o600
                    )
            os.replace(copied_revision_root, browser_revision_root)
        finally:
            if temporary_browser_root.exists():
                shutil.rmtree(temporary_browser_root)
    operation_browser_executable = (
        operation_browser_root / PLAYWRIGHT_BROWSER_EXECUTABLES[0]
    )
    if not operation_browser_executable.is_file() or not os.access(
        operation_browser_executable,
        os.X_OK,
    ):
        raise CutoverError(
            "operation-private Playwright browser authority is incomplete"
        )
    python_tree_sha256 = tree_sha256_file_stream(
        closure_root,
        label="operation-private Playwright Python closure",
    )
    browser_tree_sha256 = tree_sha256_file_stream(
        browser_revision_root,
        label="operation-private Playwright browser closure",
    )
    authority = {
        "contractName": "chummer.operation-private-playwright-authority/v1",
        "pythonAbi": f"cp{sys.version_info.major}{sys.version_info.minor}",
        "playwrightVersion": "1.60.0",
        "chromiumRevision": "1223",
        "pythonRoot": str(closure_root),
        "pythonTreeSha256": python_tree_sha256,
        "browsersRoot": str(operation_browser_root),
        "browserRevisionRoot": str(browser_revision_root),
        "browserTreeSha256": browser_tree_sha256,
        "browserExecutableRelativePath": str(
            PLAYWRIGHT_BROWSER_EXECUTABLES[0]
        ),
    }
    authority_path = host_build_root / "playwright-authority.json"
    write_private_json(authority_path, authority, replace=True)
    authority_bytes = stable_regular_bytes(
        authority_path,
        label="operation-private Playwright authority",
    )
    return {
        "hostBuildRoot": str(host_build_root),
        "home": str(private_paths["home"]),
        "dotnetCliHome": str(private_paths["dotnet-cli"]),
        "nugetPackages": str(private_paths["nuget-packages"]),
        "nugetHttpCache": str(private_paths["nuget-http-cache"]),
        "tmp": str(private_paths["tmp"]),
        "sdk": str(private_paths["sdk"]),
        "playwrightPythonRoot": str(closure_root),
        "playwrightPythonTreeSha256": python_tree_sha256,
        "playwrightBrowsersRoot": str(operation_browser_root),
        "playwrightBrowserTreeSha256": browser_tree_sha256,
        "playwrightAuthority": str(authority_path),
        "playwrightAuthoritySha256": sha256_bytes(authority_bytes),
    }


class TopologyBRunner:
    def __init__(self, config: SidecarConfig) -> None:
        self.config = config
        self.base_environment = {
            "PATH": "/usr/bin:/bin",
            "DOCKER_CONFIG": str(config.docker_config_root / "config"),
            "LANG": "C",
            "LC_ALL": "C",
        }

    def run(
        self,
        command: list[str],
        *,
        label: str,
        timeout: int = 300,
        input_bytes: bytes | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> bytes:
        process_environment = dict(self.base_environment)
        if environment:
            process_environment.update(environment)
        try:
            completed = subprocess.run(
                command,
                env=process_environment,
                input=input_bytes,
                stdin=(
                    None
                    if input_bytes is not None
                    else subprocess.DEVNULL
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
            stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
            raise CommandFailure(
                label=label,
                failure_kind="timed out",
                status=None,
                stdout=stdout,
                stderr=stderr,
            ) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise CommandFailure(
                label=label,
                failure_kind="could not execute",
                status=None,
            ) from exc
        if completed.returncode != 0:
            stdout = (
                completed.stdout
                if isinstance(completed.stdout, bytes)
                else b""
            )
            stderr = (
                completed.stderr
                if isinstance(completed.stderr, bytes)
                else b""
            )
            exit_status = (
                completed.returncode
                if completed.returncode > 0
                else 128 + min(abs(completed.returncode), 127)
            )
            raise CommandFailure(
                label=label,
                failure_kind="failed",
                status=exit_status,
                stdout=stdout,
                stderr=stderr,
            )
        return completed.stdout

    def python(
        self,
        script: Path,
        arguments: list[str],
        *,
        label: str,
        timeout: int = 300,
        input_bytes: bytes | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> bytes:
        return self.run(
            ["/usr/bin/python3", "-I", str(script), *arguments],
            label=label,
            timeout=timeout,
            input_bytes=input_bytes,
            environment=environment,
        )

    def docker(
        self,
        arguments: list[str],
        *,
        label: str,
        timeout: int = 300,
    ) -> bytes:
        return self.run(
            ["/usr/bin/docker", "--context", "default", *arguments],
            label=label,
            timeout=timeout,
        )

    def compose(
        self,
        arguments: list[str],
        *,
        environment: Mapping[str, str],
        label: str,
        timeout: int = 300,
    ) -> bytes:
        return self.run(
            [
                "/usr/bin/docker",
                "--context",
                "default",
                "compose",
                "--env-file",
                "/dev/null",
                "--project-name",
                self.config.project_name,
                "--file",
                str(self.config.compose_file),
                "--project-directory",
                str(self.config.operation_root),
                "--profile",
                "public-downloads",
                *arguments,
            ],
            environment={
                "COMPOSE_DISABLE_ENV_FILE": "1",
                **dict(environment),
            },
            label=label,
            timeout=timeout,
        )


def _tree_file_bytes(path: Path, label: str) -> bytes:
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
        ):
            raise CutoverError(f"{label} contains an unsafe file")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise CutoverError(f"{label} changed while hashed") from exc
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )
    if identity(before) != identity(after) or len(raw) != before.st_size:
        raise CutoverError(f"{label} changed while hashed")
    return raw


def tree_sha256_file_stream(root: Path, *, label: str) -> str:
    """Implement the initializer's exact ``sha256-file-tree-v1`` stream."""

    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise CutoverError(f"{label} root is unavailable") from exc
    if (
        not root.is_absolute()
        or root.resolve(strict=True) != root
        or not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
    ):
        raise CutoverError(f"{label} root is unsafe")
    files: list[tuple[bytes, str, Path]] = []

    def walk(directory: Path, relative: str) -> None:
        before = directory.lstat()
        if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
            raise CutoverError(f"{label} contains an unsafe directory")
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise CutoverError(f"{label} directory is unreadable") from exc
        for entry in entries:
            if "\n" in entry.name or "\r" in entry.name:
                raise CutoverError(f"{label} contains an unsafe path name")
            child = directory / entry.name
            child_relative = (
                entry.name if not relative else f"{relative}/{entry.name}"
            )
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise CutoverError(f"{label} contains a symbolic link")
            if stat.S_ISDIR(metadata.st_mode):
                walk(child, child_relative)
            elif stat.S_ISREG(metadata.st_mode):
                if metadata.st_nlink != 1:
                    raise CutoverError(f"{label} contains a multi-link file")
                display = f"./{child_relative}"
                files.append((os.fsencode(display), display, child))
            else:
                raise CutoverError(f"{label} contains a special entry")
        after = directory.lstat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise CutoverError(f"{label} directory changed while hashed")

    walk(root, "")
    stream = hashlib.sha256()
    for _sort_key, display, path in sorted(files, key=lambda row: row[0]):
        digest = hashlib.sha256(_tree_file_bytes(path, label)).hexdigest()
        stream.update(f"{digest}  {display}\n".encode("utf-8"))
    return stream.hexdigest()


def _require_digest_file(path: Path, expected: str, label: str) -> bytes:
    if SHA256.fullmatch(expected) is None:
        raise CutoverError(f"{label} SHA-256 is invalid")
    raw = stable_regular_bytes(path, label=label, maximum_bytes=None)
    if sha256_bytes(raw) != expected:
        raise CutoverError(f"{label} does not match its independent SHA-256")
    return raw


def _load_restoration_spec(config: SidecarConfig) -> list[dict[str, Any]]:
    raw = _require_digest_file(
        config.manifest_closure_restoration_spec,
        config.manifest_closure_restoration_spec_sha256,
        "manifest-closure restoration spec",
    )
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CutoverError("manifest-closure restoration spec is malformed") from exc
    if not isinstance(payload, (list, dict)):
        raise CutoverError("manifest-closure restoration spec has invalid shape")
    if isinstance(payload, dict):
        rows = payload.get("restorations")
        if not isinstance(rows, list):
            raise CutoverError(
                "manifest-closure restoration spec omits restorations"
            )
    else:
        rows = payload
    if not all(isinstance(row, dict) for row in rows):
        raise CutoverError("manifest-closure restoration rows are malformed")
    return [dict(row) for row in rows]


def generate_sidecar_data_protection(
    config: SidecarConfig,
    runner: TopologyBRunner,
) -> dict[str, Any]:
    def validated_pair(certificate_path: Path, password_path: Path) -> dict[str, Any]:
        certificate_bytes = stable_regular_bytes(
            certificate_path,
            label="operation-bound data-protection certificate",
            maximum_bytes=1024 * 1024,
            owner_only=True,
        )
        password_bytes = stable_regular_bytes(
            password_path,
            label="operation-bound data-protection password",
            maximum_bytes=4096,
            owner_only=True,
        )
        runner.run(
            [
                "/usr/bin/openssl",
                "pkcs12",
                "-in",
                str(certificate_path),
                "-passin",
                f"file:{password_path}",
                "-noout",
            ],
            label="validate operation-bound data-protection PKCS#12",
        )
        public_certificate = runner.run(
            [
                "/usr/bin/openssl",
                "pkcs12",
                "-in",
                str(certificate_path),
                "-passin",
                f"file:{password_path}",
                "-clcerts",
                "-nokeys",
            ],
            label="extract operation-bound data-protection public certificate",
        )
        runner.run(
            [
                "/usr/bin/openssl",
                "x509",
                "-checkend",
                str(SIDECAR_CERTIFICATE_MINIMUM_REMAINING_SECONDS),
                "-noout",
            ],
            label="validate operation-bound data-protection certificate lifetime",
            input_bytes=public_certificate,
        )
        return {
            "authority": "operation-bound-sidecar-only",
            "certificatePath": str(config.sidecar_certificate),
            "certificateSha256": sha256_bytes(certificate_bytes),
            "passwordPath": str(config.sidecar_certificate_password),
            "passwordSha256": sha256_bytes(password_bytes),
        }

    certificate_exists = (
        config.sidecar_certificate.exists()
        or config.sidecar_certificate.is_symlink()
    )
    password_exists = (
        config.sidecar_certificate_password.exists()
        or config.sidecar_certificate_password.is_symlink()
    )
    if certificate_exists and password_exists:
        try:
            return validated_pair(
                config.sidecar_certificate,
                config.sidecar_certificate_password,
            )
        except (CutoverError, OSError) as exc:
            raise RecoveryUncertain(
                "existing sidecar data-protection pair is invalid"
            ) from exc
    if certificate_exists and not password_exists:
        raise RecoveryUncertain(
            "sidecar data-protection certificate exists without its password"
        )
    if password_exists:
        password = stable_regular_bytes(
            config.sidecar_certificate_password,
            label="operation-bound data-protection password",
            maximum_bytes=4096,
            owner_only=True,
        )
    else:
        password = secrets.token_urlsafe(48).encode("ascii") + b"\n"
        atomic_private_write(
            config.sidecar_certificate_password,
            password,
            replace=False,
        )
    key = config.operation_root / ".sidecar-data-protection.key"
    certificate = config.operation_root / ".sidecar-data-protection.crt"
    pending = config.operation_root / ".sidecar-data-protection.pfx.pending"
    key.unlink(missing_ok=True)
    certificate.unlink(missing_ok=True)
    pending.unlink(missing_ok=True)
    try:
        runner.run(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-sha256",
                "-nodes",
                "-subj",
                "/CN=chummer-public-download-sidecar",
                "-days",
                str(SIDECAR_CERTIFICATE_VALIDITY_DAYS),
                "-keyout",
                str(key),
                "-out",
                str(certificate),
            ],
            label="generate operation-bound data-protection certificate",
        )
        runner.run(
            [
                "/usr/bin/openssl",
                "pkcs12",
                "-export",
                "-out",
                str(pending),
                "-inkey",
                str(key),
                "-in",
                str(certificate),
                "-passout",
                f"file:{config.sidecar_certificate_password}",
            ],
            label="seal operation-bound data-protection PKCS#12",
        )
        pending.chmod(0o600)
        validated_pair(
            pending,
            config.sidecar_certificate_password,
        )
        descriptor = os.open(
            pending,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(pending, config.sidecar_certificate)
        directory = os.open(
            config.operation_root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return validated_pair(
            config.sidecar_certificate,
            config.sidecar_certificate_password,
        )
    finally:
        key.unlink(missing_ok=True)
        certificate.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)


def _parse_credentials_file(path: Path) -> dict[str, str]:
    raw = stable_regular_bytes(
        path,
        label="Cloudflare credentials file",
        maximum_bytes=1024 * 1024,
        owner_only=True,
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise CutoverError("Cloudflare credentials file is not UTF-8") from exc
    accepted = {
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_EMAIL",
        "CLOUDFLARE_GLOBAL_API_KEY",
    }
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or key not in accepted:
            continue
        if key in values:
            raise CutoverError(
                f"Cloudflare credentials file repeats {key}"
            )
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        if not value or "\x00" in value or "\r" in value or "\n" in value:
            raise CutoverError(
                f"Cloudflare credentials file has invalid {key}"
            )
        values[key] = value
    return values


def _http_bytes(
    *,
    scheme: str,
    connect_host: str,
    connect_port: int,
    request_host: str,
    path: str,
    timeout: float,
    maximum_bytes: int = 8 * 1024 * 1024,
) -> tuple[int, dict[str, str], bytes]:
    if (
        scheme not in {"http", "https"}
        or request_host not in SIDECAR_HOSTS
        or not path.startswith("/")
        or "?" in path
        or "#" in path
    ):
        raise CutoverError("HTTP probe target is outside the audited boundary")
    if scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            connect_host,
            connect_port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
    else:
        connection = http.client.HTTPConnection(
            connect_host,
            connect_port,
            timeout=timeout,
        )
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Host": request_host,
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": "chummer-public-download-cutover/1",
            },
        )
        response = connection.getresponse()
        response_headers: dict[str, str] = {}
        forbidden_headers = {
            "authentication-info",
            "location",
            "proxy-authenticate",
            "proxy-authentication-info",
            "set-cookie",
            "set-cookie2",
            "www-authenticate",
        }
        for key, value in response.getheaders():
            lowered = key.lower()
            if lowered in forbidden_headers:
                raise CutoverError(
                    "HTTP probe exposed credential or redirect state"
                )
            if lowered == "content-length" and lowered in response_headers:
                if response_headers[lowered].strip() != value.strip():
                    raise CutoverError(
                        "HTTP probe returned conflicting Content-Length headers"
                    )
                continue
            if lowered in response_headers:
                response_headers[lowered] += f", {value}"
            else:
                response_headers[lowered] = value
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = response.read(min(64 * 1024, maximum_bytes + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > maximum_bytes:
                raise CutoverError("HTTP probe body exceeded its bound")
        return int(response.status), response_headers, b"".join(chunks)
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise CutoverError("HTTP probe failed") from exc
    finally:
        connection.close()


def _open_probe_connection(
    *,
    scheme: str,
    connect_host: str,
    connect_port: int,
    timeout: float,
) -> http.client.HTTPConnection:
    if scheme == "https":
        return http.client.HTTPSConnection(
            connect_host,
            connect_port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
    if scheme == "http":
        return http.client.HTTPConnection(
            connect_host,
            connect_port,
            timeout=timeout,
        )
    raise CutoverError("HTTP probe scheme is outside the audited boundary")


def _validate_download_probe_target(
    *,
    request_host: str,
    path: str,
) -> None:
    parsed = urlsplit(path)
    if (
        request_host not in SIDECAR_HOSTS
        or not path.startswith("/downloads/")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.path != path
    ):
        raise CutoverError("download probe target is outside the audited boundary")


def _probe_request_headers(request_host: str) -> dict[str, str]:
    return {
        "Host": request_host,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "chummer-public-download-cutover/1",
    }


def _response_header_values(
    response: http.client.HTTPResponse,
) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for key, value in response.getheaders():
        values.setdefault(key.lower(), []).append(value)
    return values


def _reject_download_response_state(
    headers: Mapping[str, list[str]],
    *,
    allow_location: bool,
) -> None:
    forbidden = {
        "authorization",
        "authentication-info",
        "proxy-authenticate",
        "proxy-authentication-info",
        "proxy-authorization",
        "refresh",
        "set-cookie",
        "set-cookie2",
        "www-authenticate",
    }
    if not allow_location:
        forbidden.add("location")
    exposed = sorted(forbidden.intersection(headers))
    if exposed:
        raise CutoverError(
            "download probe exposed credential, cookie, or redirect state"
        )
    encodings = headers.get("content-encoding", [])
    if len(encodings) > 1 or (
        encodings and encodings[0].strip().lower() != "identity"
    ):
        raise CutoverError("download probe returned unexpected Content-Encoding")


def _stream_exact_download(
    *,
    scheme: str,
    connect_host: str,
    connect_port: int,
    request_host: str,
    path: str,
    expected_sha256: str,
    expected_size_bytes: int,
    generation_id: str,
    timeout: float = 30,
) -> dict[str, Any]:
    _validate_download_probe_target(request_host=request_host, path=path)
    if (
        SHA256.fullmatch(expected_sha256) is None
        or isinstance(expected_size_bytes, bool)
        or expected_size_bytes <= 0
        or not generation_id
    ):
        raise CutoverError("download probe expectation is invalid")
    request_headers = _probe_request_headers(request_host)
    if {
        "authorization",
        "cookie",
        "proxy-authorization",
    }.intersection(key.lower() for key in request_headers):
        raise CutoverError("download probe request is not anonymous")

    connection = _open_probe_connection(
        scheme=scheme,
        connect_host=connect_host,
        connect_port=connect_port,
        timeout=timeout,
    )
    try:
        connection.request("GET", path, headers=request_headers)
        response = connection.getresponse()
        headers = _response_header_values(response)
        _reject_download_response_state(headers, allow_location=False)
        if response.status != 200:
            raise CutoverError(
                f"download probe expected HTTP 200, got {response.status}"
            )
        lengths = headers.get("content-length", [])
        if len(lengths) != 1:
            raise CutoverError(
                "download probe requires exactly one Content-Length"
            )
        try:
            content_length = int(lengths[0])
        except ValueError as exc:
            raise CutoverError(
                "download probe returned invalid Content-Length"
            ) from exc
        if content_length != expected_size_bytes:
            raise CutoverError(
                "download probe Content-Length differs from fresh authority"
            )
        generations = headers.get(
            "x-chummer-release-generation",
            [],
        )
        if generations != [generation_id]:
            raise CutoverError("download probe generation header drifted")

        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            if size > expected_size_bytes:
                raise CutoverError(
                    "download probe streamed more bytes than expected"
                )
        observed_sha256 = digest.hexdigest()
        if size != content_length or size != expected_size_bytes:
            raise CutoverError(
                "download probe streamed size differs from fresh authority"
            )
        if observed_sha256 != expected_sha256:
            raise CutoverError(
                "download probe streamed SHA-256 differs from fresh authority"
            )
        return {
            "method": "GET",
            "endpoint": f"{scheme}://{request_host}{path}",
            "httpStatus": 200,
            "contentLength": content_length,
            "sizeBytes": size,
            "sha256": observed_sha256,
            "generationId": generation_id,
            "anonymous": True,
            "redirectsFollowed": 0,
        }
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise CutoverError("streaming download probe failed") from exc
    finally:
        connection.close()


def _fresh_delta_rows(shelf: Mapping[str, Any]) -> list[dict[str, Any]]:
    authority = shelf.get("releaseCandidateAuthority")
    fresh = authority.get("freshDelta") if isinstance(authority, dict) else None
    expected_paths = (
        "files/chummer-avalonia-win-x64-installer.exe",
        "files/chummer-avalonia-win-x64-payload.zip",
        "files/chummer-avalonia-win-x64-payload.zip.json",
    )
    if (
        not isinstance(fresh, list)
        or len(fresh) != len(expected_paths)
        or tuple(
            str(row.get("path") or "")
            for row in fresh
            if isinstance(row, dict)
        )
        != expected_paths
    ):
        raise CutoverError("fresh download authority path closure drifted")
    result: list[dict[str, Any]] = []
    for path, row in zip(expected_paths, fresh, strict=True):
        if not isinstance(row, dict):
            raise CutoverError("fresh download authority row is malformed")
        sha256 = str(row.get("sha256") or "").strip().lower()
        size = row.get("sizeBytes")
        if (
            SHA256.fullmatch(sha256) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
        ):
            raise CutoverError("fresh download authority digest or size drifted")
        result.append(
            {
                "kind": (
                    "installer"
                    if path.endswith("-installer.exe")
                    else "sidecar"
                    if path.endswith(".json")
                    else "payload"
                ),
                "path": f"/downloads/{path}",
                "sha256": sha256,
                "sizeBytes": size,
            }
        )
    return result


def _strict_prepared_manifest(
    generation_root: Path,
    name: str,
    label: str,
) -> dict[str, Any]:
    raw = stable_regular_bytes(
        generation_root / name,
        label=label,
        maximum_bytes=8 * 1024 * 1024,
    )

    def unique_object(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    try:
        manifest = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CutoverError(f"{label} is malformed") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("generationId") != generation_root.name
    ):
        raise CutoverError(
            f"{label} does not bind the prepared generation"
        )
    return manifest


def _prepared_download_path(
    raw: Any,
    *,
    label: str,
) -> str:
    if (
        not isinstance(raw, str)
        or not raw
        or raw != raw.strip()
        or "\\" in raw
        or "%" in raw
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in raw
        )
    ):
        raise CutoverError(f"{label} is not a canonical download URL")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise CutoverError(f"{label} is not a canonical download URL") from exc
    if parsed.query or parsed.fragment:
        raise CutoverError(f"{label} is not a canonical download URL")
    if parsed.scheme or parsed.netloc:
        raise CutoverError(f"{label} has an unauthorized origin")
    if not parsed.path.startswith("/downloads/"):
        raise CutoverError(f"{label} is not a download URL")
    return parsed.path


def _prepared_artifact_id(
    row: Mapping[str, Any],
    *,
    label: str,
) -> str:
    aliases = [
        row[key]
        for key in ("artifactId", "id")
        if key in row
    ]
    if not aliases:
        raise CutoverError(f"{label} artifact identity is unavailable")
    if any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        for value in aliases
    ):
        raise CutoverError(f"{label} artifact identity is malformed")
    artifact_id = str(aliases[0])
    if (
        any(value != artifact_id for value in aliases[1:])
        or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
            artifact_id,
        )
        is None
        or ".." in artifact_id
    ):
        raise CutoverError(f"{label} artifact identity is ambiguous")
    return artifact_id


def _prepared_role(
    row: Mapping[str, Any],
    *,
    artifact_id: str,
    generation_id: str,
    access_class: str,
    role: str,
    file_key: str,
    sha256_key: str,
    size_key: str,
    url_keys: tuple[str, ...],
) -> dict[str, Any]:
    label = f"prepared artifact {artifact_id} {role}"
    file_name = row.get(file_key)
    sha256 = row.get(sha256_key)
    size = row.get(size_key)
    if (
        not isinstance(file_name, str)
        or not file_name
        or file_name != file_name.strip()
        or Path(file_name).name != file_name
        or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}",
            file_name,
        )
        is None
        or not isinstance(sha256, str)
        or sha256 != sha256.strip().lower()
        or SHA256.fullmatch(sha256) is None
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size <= 0
    ):
        raise CutoverError(f"{label} byte contract is malformed")
    raw_urls = [row[key] for key in url_keys if key in row]
    if not raw_urls:
        raise CutoverError(f"{label} URL is unavailable")
    paths = {
        _prepared_download_path(
            raw_url,
            label=f"{label} URL",
        )
        for raw_url in raw_urls
    }
    if len(paths) != 1:
        raise CutoverError(f"{label} URL aliases disagree")
    manifest_path = paths.pop()
    if role == "primary":
        generation_path = (
            f"/downloads/g/{generation_id}/files/{file_name}"
            if access_class == "open_public"
            else (
                f"/downloads/g/{generation_id}/install/"
                f"{artifact_id}"
            )
        )
    else:
        generation_path = (
            f"/downloads/g/{generation_id}/install/"
            f"{artifact_id}/payload"
        )
    if manifest_path != generation_path:
        raise CutoverError(f"{label} URL shape drifted")
    return {
        "role": role,
        "fileName": file_name,
        "sha256": sha256,
        "sizeBytes": size,
        "manifestPath": manifest_path,
    }


def _normalized_prepared_artifacts(
    manifest: Mapping[str, Any],
    *,
    collection_name: str,
    label: str,
    generation_id: str,
) -> dict[str, dict[str, Any]]:
    unexpected_collection = (
        "downloads"
        if collection_name == "artifacts"
        else "artifacts"
    )
    if unexpected_collection in manifest:
        raise CutoverError(
            f"{label} contains unexpected {unexpected_collection}"
        )
    rows = manifest.get(collection_name)
    if not isinstance(rows, list):
        raise CutoverError(f"{label} {collection_name} are unavailable")
    artifacts: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, dict):
            raise CutoverError(f"{label} artifact row {index} is malformed")
        artifact_id = _prepared_artifact_id(
            raw_row,
            label=f"{label} row {index}",
        )
        if artifact_id in artifacts:
            raise CutoverError(f"{label} contains duplicate artifact identity")
        access_aliases = [
            raw_row[key]
            for key in (
                "installAccessClass",
                "install_access_class",
            )
            if key in raw_row
        ]
        if (
            not access_aliases
            or any(
                not isinstance(value, str)
                or value not in {
                    "open_public",
                    "account_required",
                }
                for value in access_aliases
            )
            or len(set(access_aliases)) != 1
        ):
            raise CutoverError(
                f"{label} artifact access class is missing or malformed"
            )
        access_class = str(access_aliases[0])
        primary = _prepared_role(
            raw_row,
            artifact_id=artifact_id,
            generation_id=generation_id,
            access_class=access_class,
            role="primary",
            file_key="fileName",
            sha256_key="sha256",
            size_key="sizeBytes",
            url_keys=("downloadUrl", "url"),
        )
        payload_fields = {
            "payloadFileName",
            "payloadSha256",
            "payloadSizeBytes",
            "payloadDownloadUrl",
            "payloadMetadataFileName",
            "payloadMetadataUrl",
        }
        roles = [primary]
        if any(key in raw_row for key in payload_fields):
            payload = _prepared_role(
                raw_row,
                artifact_id=artifact_id,
                generation_id=generation_id,
                access_class=access_class,
                role="payload",
                file_key="payloadFileName",
                sha256_key="payloadSha256",
                size_key="payloadSizeBytes",
                url_keys=("payloadDownloadUrl",),
            )
            sidecar_name = f"{payload['fileName']}.json"
            if (
                "payloadMetadataFileName" in raw_row
                and raw_row.get("payloadMetadataFileName")
                != sidecar_name
            ):
                raise CutoverError(
                    f"prepared artifact {artifact_id} sidecar name drifted"
                )
            metadata_path = ""
            if "payloadMetadataUrl" in raw_row:
                metadata_path = _prepared_download_path(
                    raw_row.get("payloadMetadataUrl"),
                    label=(
                        f"prepared artifact {artifact_id} sidecar URL"
                    ),
                )
                if metadata_path != (
                    f"/downloads/g/{generation_id}/install/"
                    f"{artifact_id}/metadata"
                ):
                    raise CutoverError(
                        f"prepared artifact {artifact_id} sidecar URL shape drifted"
                    )
            roles.extend(
                (
                    payload,
                    {
                        "role": "sidecar",
                        "fileName": sidecar_name,
                        "manifestPath": metadata_path,
                    },
                )
            )
        for role in roles:
            file_name = str(role["fileName"])
            if file_name in paths:
                raise CutoverError(
                    f"{label} artifact file path closure is ambiguous"
                )
            paths.add(file_name)
        artifacts[artifact_id] = {
            "artifactId": artifact_id,
            "installAccessClass": access_class,
            "platform": raw_row.get("platform"),
            "rid": raw_row.get("rid"),
            "roles": roles,
        }
    return artifacts


def _retained_account_required_bindings(
    *,
    config: SidecarConfig,
    generation_root: Path,
    fresh_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    del config
    canonical = _strict_prepared_manifest(
        generation_root,
        "RELEASE_CHANNEL.generated.json",
        "prepared generation canonical manifest",
    )
    compatibility = _strict_prepared_manifest(
        generation_root,
        "releases.json",
        "prepared generation compatibility manifest",
    )
    canonical_artifacts = _normalized_prepared_artifacts(
        canonical,
        collection_name="artifacts",
        label="prepared canonical manifest",
        generation_id=generation_root.name,
    )
    compatibility_artifacts = _normalized_prepared_artifacts(
        compatibility,
        collection_name="downloads",
        label="prepared compatibility manifest",
        generation_id=generation_root.name,
    )
    if canonical_artifacts != compatibility_artifacts:
        raise CutoverError(
            "prepared canonical and compatibility artifact contracts disagree"
        )

    fresh_by_name: dict[str, dict[str, Any]] = {}
    for row in fresh_rows:
        path = str(row["path"])
        file_name = Path(path).name
        if (
            path != f"/downloads/files/{file_name}"
            or file_name in fresh_by_name
        ):
            raise CutoverError("fresh download authority is ambiguous")
        fresh_by_name[file_name] = row

    account_required_ids = {
        artifact_id
        for artifact_id, artifact in canonical_artifacts.items()
        if artifact["installAccessClass"] == "account_required"
    }
    open_roles: dict[str, dict[str, Any]] = {}
    protected_roles: list[tuple[str, dict[str, Any]]] = []
    for artifact_id, artifact in canonical_artifacts.items():
        for role in artifact["roles"]:
            file_name = str(role["fileName"])
            if artifact["installAccessClass"] == "open_public":
                if file_name in open_roles:
                    raise CutoverError(
                        "prepared open-public file path closure is ambiguous"
                    )
                open_roles[file_name] = role
            else:
                protected_roles.append((artifact_id, role))
    if set(open_roles) != set(fresh_by_name):
        raise CutoverError(
            "prepared open-public roles differ from fresh authority"
        )
    if any(
        str(role["fileName"]) in fresh_by_name
        for _artifact_id, role in protected_roles
    ):
        raise CutoverError(
            "account-required and fresh file path closures overlap"
        )

    expected_names = {
        *fresh_by_name,
        *(
            str(role["fileName"])
            for _artifact_id, role in protected_roles
        ),
    }
    files_root = generation_root / "files"
    try:
        files_metadata = files_root.lstat()
    except OSError as exc:
        raise CutoverError(
            "prepared generation files closure is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(files_metadata.st_mode)
        or not stat.S_ISDIR(files_metadata.st_mode)
    ):
        raise CutoverError(
            "prepared generation file closure differs from authenticated roles"
        )
    try:
        entries = [
            (entry, entry.lstat())
            for entry in files_root.iterdir()
        ]
    except OSError as exc:
        raise CutoverError(
            "prepared generation file closure changed while inspected"
        ) from exc
    if (
        any(
            entry.name not in expected_names
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            for entry, metadata in entries
        )
        or {entry.name for entry, _metadata in entries}
        != expected_names
    ):
        raise CutoverError(
            "prepared generation file closure differs from authenticated roles"
        )

    actual: dict[str, dict[str, Any]] = {}
    for file_name in sorted(expected_names):
        raw = stable_regular_bytes(
            files_root / file_name,
            label=f"prepared generation file {file_name}",
            maximum_bytes=None,
        )
        actual[file_name] = {
            "sha256": sha256_bytes(raw),
            "sizeBytes": len(raw),
        }
    for file_name, fresh in fresh_by_name.items():
        role = open_roles[file_name]
        expected = actual[file_name]
        if any(
            not _json_semantically_equal(
                fresh.get(key),
                expected[key],
            )
            for key in ("sha256", "sizeBytes")
        ):
            raise CutoverError(
                "fresh authority differs from sealed generation bytes"
            )
        if role["role"] != "sidecar" and any(
            not _json_semantically_equal(
                role.get(key),
                expected[key],
            )
            for key in ("sha256", "sizeBytes")
        ):
            raise CutoverError(
                "open-public manifest differs from sealed generation bytes"
            )

    candidates: list[dict[str, Any]] = []
    for artifact_id, role in protected_roles:
        file_name = str(role["fileName"])
        expected = actual[file_name]
        if role["role"] != "sidecar" and any(
            not _json_semantically_equal(
                role.get(key),
                expected[key],
            )
            for key in ("sha256", "sizeBytes")
        ):
            raise CutoverError(
                "account-required manifest differs from sealed generation bytes"
            )
        candidates.append(
            {
                "artifactId": artifact_id,
                "role": role["role"],
                "path": f"/downloads/files/{file_name}",
                "sha256": expected["sha256"],
                "sizeBytes": expected["sizeBytes"],
                "installAccessClass": "account_required",
            }
        )
    paths = [str(row["path"]) for row in candidates]
    if len(paths) != len(set(paths)):
        raise CutoverError(
            "retained account-required artifact path closure is ambiguous"
        )
    bindings = sorted(
        candidates,
        key=lambda row: (
            str(row["artifactId"]),
            str(row["role"]),
            str(row["path"]),
        ),
    )
    if bool(account_required_ids) != bool(bindings):
        raise CutoverError(
            "account-required artifact and denial binding closure disagree"
        )
    return bindings, {
        "accountRequiredArtifactCount": len(account_required_ids),
        "bindingCount": len(bindings),
        "sealedGenerationFileCount": len(actual),
        "freshFileCount": len(fresh_by_name),
        "zeroCountProved": (
            not account_required_ids and not bindings
        ),
    }


def _probe_denied_download(
    *,
    scheme: str,
    connect_host: str,
    connect_port: int,
    request_host: str,
    path: str,
    generation_id: str,
    artifact_id: str,
    route_kind: str,
    expected_sha256: str,
    expected_size_bytes: int,
    timeout: float = 30,
) -> dict[str, Any]:
    _validate_download_probe_target(request_host=request_host, path=path)
    if (
        route_kind not in {"stable", "generation"}
        or not artifact_id
        or SHA256.fullmatch(expected_sha256) is None
        or isinstance(expected_size_bytes, bool)
        or expected_size_bytes <= 0
    ):
        raise CutoverError(
            "account-required denial expectation is invalid"
        )
    if (
        route_kind == "stable"
        and not path.startswith("/downloads/files/")
    ) or (
        route_kind == "generation"
        and not path.startswith(
            f"/downloads/g/{generation_id}/files/"
        )
    ):
        raise CutoverError(
            "account-required denial route shape drifted"
        )
    connection = _open_probe_connection(
        scheme=scheme,
        connect_host=connect_host,
        connect_port=connect_port,
        timeout=timeout,
    )
    try:
        request_headers = _probe_request_headers(request_host)
        connection.request("GET", path, headers=request_headers)
        response = connection.getresponse()
        headers = _response_header_values(response)
        _reject_download_response_state(
            headers,
            allow_location=route_kind == "stable",
        )
        expected_status = 302 if route_kind == "stable" else 409
        if response.status != expected_status:
            raise CutoverError(
                "account-required artifact denial status drifted"
            )
        generations = headers.get(
            "x-chummer-release-generation",
            [],
        )
        if generations != [generation_id]:
            raise CutoverError(
                "account-required denial generation header drifted"
            )
        locations = headers.get("location", [])
        if route_kind == "stable":
            if len(locations) != 1:
                raise CutoverError(
                    "account-required redirect has ambiguous Location"
                )
            parsed_location = urlsplit(locations[0])
            try:
                redirect_port = parsed_location.port
            except ValueError as exc:
                raise CutoverError(
                    "account-required redirect port is invalid"
                ) from exc
            if (
                parsed_location.username is not None
                or parsed_location.password is not None
                or (
                    parsed_location.hostname is not None
                    and parsed_location.hostname != request_host
                )
                or (
                    parsed_location.scheme
                    and parsed_location.scheme != "https"
                )
                or redirect_port not in {None, 443}
                or parsed_location.path != "/login"
                or parsed_location.fragment
            ):
                raise CutoverError(
                    "account-required redirect escaped the account boundary"
                )
            try:
                redirect_query = parse_qs(
                    parsed_location.query,
                    strict_parsing=True,
                )
            except ValueError as exc:
                raise CutoverError(
                    "account-required redirect query is malformed"
                ) from exc
            if (
                set(redirect_query) != {"next"}
                or redirect_query["next"] != [
                    f"/downloads/install/{artifact_id}"
                ]
            ):
                raise CutoverError(
                    "account-required redirect target drifted"
                )
        elif locations:
            raise CutoverError(
                "account-required non-redirect exposed Location"
            )
        digest = hashlib.sha256()
        size = 0
        body_parts: list[bytes] = []
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            body_parts.append(chunk)
            size += len(chunk)
            if size > 64 * 1024:
                raise CutoverError(
                    "account-required denial returned an artifact-sized body"
                )
        observed_sha256 = digest.hexdigest()
        if (
            size == expected_size_bytes
            and observed_sha256 == expected_sha256
        ):
            raise CutoverError(
                "account-required denial returned the protected artifact bytes"
            )
        if route_kind == "stable":
            if size != 0:
                raise CutoverError(
                    "account-required redirect returned a non-empty body"
                )
        else:
            content_types = headers.get("content-type", [])
            if (
                len(content_types) != 1
                or not content_types[0].lower().startswith(
                    "application/json"
                )
            ):
                raise CutoverError(
                    "generation-bound denial is not JSON"
                )
            try:
                denial = json.loads(b"".join(body_parts))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise CutoverError(
                    "generation-bound denial body is malformed"
                ) from exc
            expected_denial = {
                "error": "generation_bound_credential_required",
                "message": (
                    "This retained release generation requires its "
                    "generation-bound install ticket or claim code. "
                    "Use the install command issued for this exact release."
                ),
            }
            if denial != expected_denial:
                raise CutoverError(
                    "generation-bound denial contract drifted"
                )
        return {
            "method": "GET",
            "endpoint": f"{scheme}://{request_host}{path}",
            "httpStatus": int(response.status),
            "bodySizeBytes": size,
            "bodySha256": observed_sha256,
            "protectedSizeBytes": expected_size_bytes,
            "protectedSha256": expected_sha256,
            "generationId": generation_id,
            "anonymous": True,
            "artifactBytesServed": False,
            "bodyDiffersFromProtectedBytes": True,
            "routeKind": route_kind,
            "redirectsFollowed": 0,
        }
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise CutoverError("account-required denial probe failed") from exc
    finally:
        connection.close()


def probe_download_artifact_hosts(
    config: SidecarConfig,
    *,
    shelf: Mapping[str, Any],
    scope: str,
) -> dict[str, Any]:
    if scope == "local":
        scheme = "http"
        connect_port = SIDECAR_PORT
    elif scope == "public":
        scheme = "https"
        connect_port = 443
    else:
        raise CutoverError("artifact probe scope is invalid")
    generation_id = str(shelf.get("generationId") or "").strip()
    generation_root = Path(str(shelf.get("generationRoot") or ""))
    if (
        not generation_id
        or not generation_root.is_absolute()
        or generation_root.name != generation_id
    ):
        raise CutoverError("artifact probe generation authority is invalid")
    fresh_rows = _fresh_delta_rows(shelf)
    (
        retained_bindings,
        denial_closure,
    ) = _retained_account_required_bindings(
        config=config,
        generation_root=generation_root,
        fresh_rows=fresh_rows,
    )
    observations: list[dict[str, Any]] = []
    denial_observations: list[dict[str, Any]] = []
    for hostname in SIDECAR_HOSTS:
        connect_host = SIDECAR_ADDRESS if scope == "local" else hostname
        for row in fresh_rows:
            for route_kind, path in (
                ("stable", str(row["path"])),
                (
                    "generation",
                    (
                        f"/downloads/g/{generation_id}/files/"
                        f"{Path(str(row['path'])).name}"
                    ),
                ),
            ):
                observation = _stream_exact_download(
                    scheme=scheme,
                    connect_host=connect_host,
                    connect_port=connect_port,
                    request_host=hostname,
                    path=path,
                    expected_sha256=str(row["sha256"]),
                    expected_size_bytes=int(row["sizeBytes"]),
                    generation_id=generation_id,
                )
                observations.append(
                    {
                        **observation,
                        "kind": row["kind"],
                        "routeKind": route_kind,
                    }
                )
        for retained in retained_bindings:
            for route_kind, path in (
                ("stable", str(retained["path"])),
                (
                    "generation",
                    (
                        f"/downloads/g/{generation_id}/files/"
                        f"{Path(str(retained['path'])).name}"
                    ),
                ),
            ):
                denial_observations.append(
                    {
                        **_probe_denied_download(
                            scheme=scheme,
                            connect_host=connect_host,
                            connect_port=connect_port,
                            request_host=hostname,
                            path=path,
                            generation_id=generation_id,
                            artifact_id=str(retained["artifactId"]),
                            route_kind=route_kind,
                            expected_sha256=str(retained["sha256"]),
                            expected_size_bytes=int(
                                retained["sizeBytes"]
                            ),
                        ),
                        "artifactId": retained["artifactId"],
                        "role": retained["role"],
                        "installAccessClass": "account_required",
                    }
                )
    expected_denial_observations = (
        len(SIDECAR_HOSTS) * len(retained_bindings) * 2
    )
    if len(denial_observations) != expected_denial_observations:
        raise CutoverError(
            "account-required denial observation closure is incomplete"
        )
    return {
        "status": "pass",
        "scope": scope,
        "hosts": list(SIDECAR_HOSTS),
        "generationId": generation_id,
        "freshArtifacts": observations,
        "accountRequiredDenials": denial_observations,
        "accountRequiredDenialClosure": {
            "status": "pass",
            **denial_closure,
            "expectedObservationCount": expected_denial_observations,
            "observedObservationCount": len(denial_observations),
        },
    }


def _probe_exact_manifest(
    *,
    scheme: str,
    connect_host: str,
    connect_port: int,
    request_host: str,
    path: str,
    expected: bytes,
    shelf: Mapping[str, Any],
    generation_id: str | None,
    timeout: float = 30,
) -> dict[str, Any]:
    status, headers, body = _http_bytes(
        scheme=scheme,
        connect_host=connect_host,
        connect_port=connect_port,
        request_host=request_host,
        path=path,
        timeout=timeout,
    )
    if status != 200:
        raise CutoverError("served manifest did not return HTTP 200")
    observed_generation = headers.get("x-chummer-release-generation", "")
    if (
        not isinstance(generation_id, str)
        or not generation_id
        or observed_generation != generation_id
    ):
        raise CutoverError("served manifest generation header drifted")
    prepared_payload = _strict_json_object_bytes(
        expected,
        label="prepared manifest",
    )
    served_payload = _strict_json_object_bytes(
        body,
        label="served manifest",
    )
    if "releaseTruth" in prepared_payload:
        raise CutoverError(
            "prepared manifest unexpectedly contains a releaseTruth envelope"
        )
    _verify_prepared_manifest_authority(
        shelf=shelf,
        prepared=prepared_payload,
        prepared_sha256=sha256_bytes(expected),
        path=path,
        generation_id=generation_id,
    )
    (
        expected_release_truth,
        release_scope_decision_sha256,
    ) = _review_required_release_truth_authority(shelf)
    release_truth = served_payload.get("releaseTruth")
    _verify_review_required_release_truth(
        release_truth,
        expected=expected_release_truth,
        prepared=prepared_payload,
        generation_id=generation_id,
        release_scope_decision_sha256=release_scope_decision_sha256,
    )
    unwrapped_payload = dict(served_payload)
    del unwrapped_payload["releaseTruth"]
    if not _json_semantically_equal(unwrapped_payload, prepared_payload):
        raise CutoverError(
            "served manifest payload differs from the prepared manifest"
        )
    return {
        "endpoint": f"{scheme}://{request_host}{path}",
        "httpStatus": status,
        "bodySha256": sha256_bytes(body),
        "sizeBytes": len(body),
        "generationId": observed_generation,
        "anonymous": True,
    }


_RELEASE_TRUTH_FIELDS = frozenset(
    {
        "contractName",
        "releaseVersion",
        "channel",
        "releaseStatus",
        "rolloutState",
        "supportabilityState",
        "availablePlatforms",
        "primaryHeadByPlatform",
        "artifactCount",
        "downloadAccessPosture",
        "knownIssueSummary",
        "manifestSha256",
        "registryCommit",
        "releaseDecisionStatus",
        "releaseDecisionSha256",
        "releaseScopeDecisionSha256",
        "artifactHandoff",
    }
)
_PUBLIC_PREVIEW_BYTE_HANDOFF_FIELDS = frozenset(
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


def _json_semantically_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (
            left.keys() == right.keys()
            and all(
                _json_semantically_equal(left[key], right[key])
                for key in left
            )
        )
    if isinstance(left, list):
        return (
            len(left) == len(right)
            and all(
                _json_semantically_equal(left_item, right_item)
                for left_item, right_item in zip(left, right, strict=True)
            )
        )
    return bool(left == right)


def _exact_manifest_alias(
    payload: Mapping[str, Any],
    names: tuple[str, ...],
    *,
    label: str,
    nullable_aliases: frozenset[str] = frozenset(),
) -> str:
    values: list[str] = []
    for name in names:
        if name not in payload:
            continue
        value = payload[name]
        if value is None and name in nullable_aliases:
            continue
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise CutoverError(
                f"prepared manifest {label} aliases drifted"
            )
        values.append(value)
    if (
        not values
        or any(value != values[0] for value in values[1:])
    ):
        raise CutoverError(f"prepared manifest {label} aliases drifted")
    return values[0]


def _verify_prepared_manifest_authority(
    *,
    shelf: Mapping[str, Any],
    prepared: Mapping[str, Any],
    prepared_sha256: str,
    path: str,
    generation_id: str,
) -> None:
    authority = shelf.get("releaseCandidateAuthority")
    review_authority = (
        authority.get("reviewAuthority")
        if isinstance(authority, dict)
        else None
    )
    release_truth = (
        authority.get("reviewRequiredReleaseTruth")
        if isinstance(authority, dict)
        else None
    )
    canonical_hashes = (
        shelf.get("canonicalMirrorSha256"),
        shelf.get("generationCanonicalSha256"),
        (
            authority.get("canonicalManifestSha256")
            if isinstance(authority, dict)
            else None
        ),
        (
            review_authority.get("manifestSha256")
            if isinstance(review_authority, dict)
            else None
        ),
        (
            release_truth.get("manifestSha256")
            if isinstance(release_truth, dict)
            else None
        ),
    )
    compatibility_hashes = (
        shelf.get("compatibilityMirrorSha256"),
        shelf.get("generationCompatibilitySha256"),
    )
    if (
        shelf.get("generationId") != generation_id
        or prepared.get("generationId") != generation_id
        or not isinstance(authority, dict)
        or authority.get("generationId") != generation_id
        or not isinstance(review_authority, dict)
        or review_authority.get("generationId") != generation_id
        or any(
            not isinstance(value, str)
            or SHA256.fullmatch(value) is None
            for value in (*canonical_hashes, *compatibility_hashes)
        )
        or any(
            value != canonical_hashes[0]
            for value in canonical_hashes[1:]
        )
        or compatibility_hashes[1] != compatibility_hashes[0]
    ):
        raise CutoverError(
            "prepared manifest generation or authority hashes drifted"
        )
    manifest_name = PurePosixPath(path).name
    if manifest_name == "RELEASE_CHANNEL.generated.json":
        expected_sha256 = canonical_hashes[0]
    elif manifest_name == "releases.json":
        expected_sha256 = compatibility_hashes[0]
    else:
        raise CutoverError("served manifest path is not canonical")
    if prepared_sha256 != expected_sha256:
        raise CutoverError(
            "prepared manifest SHA-256 differs from its shelf authority"
        )


def _prepared_public_preview_artifact(
    prepared: Mapping[str, Any],
    *,
    generation_id: str,
) -> dict[str, Any]:
    collections = [
        prepared[name]
        for name in ("artifacts", "downloads")
        if name in prepared
    ]
    if (
        len(collections) != 1
        or not isinstance(collections[0], list)
        or len(collections[0]) != 1
        or not isinstance(collections[0][0], dict)
    ):
        raise CutoverError(
            "prepared manifest public-preview artifact closure drifted"
        )
    artifact = collections[0][0]
    artifact_id = _exact_manifest_alias(
        artifact,
        ("artifactId", "id"),
        label="artifact identity",
    )
    download_url = _exact_manifest_alias(
        artifact,
        ("downloadUrl", "url"),
        label="artifact download URL",
    )
    file_name = _exact_manifest_alias(
        artifact,
        ("fileName",),
        label="artifact file name",
    )
    expected_url = f"/downloads/g/{generation_id}/files/{file_name}"
    size_bytes = artifact.get("sizeBytes")
    sha256 = artifact.get("sha256")
    if (
        SAFE_NAME.fullmatch(artifact_id) is None
        or download_url != expected_url
        or artifact.get("head") != "avalonia"
        or artifact.get("platform") != "windows"
        or artifact.get("rid") != "win-x64"
        or artifact.get("arch") != "x64"
        or artifact.get("installAccessClass") != "open_public"
        or not isinstance(sha256, str)
        or SHA256.fullmatch(sha256) is None
        or isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes <= 0
    ):
        raise CutoverError(
            "prepared manifest public-preview artifact binding drifted"
        )
    return {
        "artifactId": artifact_id,
        "head": "avalonia",
        "platform": "windows",
        "rid": "win-x64",
        "arch": "x64",
        "sha256": sha256,
        "sizeBytes": size_bytes,
        "artifactAccessClass": "open_public",
        "downloadUrl": download_url,
        "publicInstallRoute": f"/downloads/install/{artifact_id}",
    }


def _verify_review_required_release_truth(
    value: Any,
    *,
    expected: Mapping[str, Any],
    prepared: Mapping[str, Any],
    generation_id: str | None,
    release_scope_decision_sha256: str,
) -> None:
    if generation_id is None:
        raise CutoverError(
            "review-required releaseTruth requires a generation binding"
        )
    if (
        not isinstance(value, dict)
        or not isinstance(expected, dict)
        or set(value) != _RELEASE_TRUTH_FIELDS
        or set(expected) != _RELEASE_TRUTH_FIELDS
        or not _json_semantically_equal(value, expected)
    ):
        raise CutoverError(
            "served releaseTruth does not match its exact authority envelope"
        )
    release_version = _exact_manifest_alias(
        prepared,
        ("releaseVersion", "version", "publicVersion"),
        label="release version",
        nullable_aliases=frozenset({"publicVersion"}),
    )
    artifact = _prepared_public_preview_artifact(
        prepared,
        generation_id=generation_id,
    )
    handoff = value.get("artifactHandoff")
    if (
        set(value) != _RELEASE_TRUTH_FIELDS
        or value.get("contractName")
        != "chummer.release-truth-projection/v1"
        or value.get("releaseVersion") != release_version
        or value.get("channel")
        != _exact_manifest_alias(
            prepared,
            ("channel", "channelId"),
            label="channel",
            nullable_aliases=frozenset({"channelId"}),
        )
        or value.get("channel") != "preview"
        or value.get("releaseStatus") != "published"
        or value.get("releaseStatus") != prepared.get("status")
        or value.get("rolloutState")
        != "public_release_review_required"
        or value.get("rolloutState") != prepared.get("rolloutState")
        or value.get("supportabilityState") != "review_required"
        or value.get("supportabilityState")
        != prepared.get("supportabilityState")
        or value.get("knownIssueSummary")
        != prepared.get("knownIssueSummary")
        or value.get("availablePlatforms") != ["windows"]
        or value.get("primaryHeadByPlatform") != {"windows": "avalonia"}
        or value.get("artifactCount") != 1
        or value.get("downloadAccessPosture") != "open_public"
        or value.get("releaseDecisionStatus") != "review_required"
        or COMMIT.fullmatch(str(value.get("registryCommit") or "")) is None
        or SHA256.fullmatch(str(value.get("manifestSha256") or "")) is None
        or SHA256.fullmatch(
            str(value.get("releaseDecisionSha256") or "")
        )
        is None
        or SHA256.fullmatch(release_scope_decision_sha256) is None
        or value.get("releaseScopeDecisionSha256")
        != release_scope_decision_sha256
        or not isinstance(handoff, dict)
        or set(handoff) != _PUBLIC_PREVIEW_BYTE_HANDOFF_FIELDS
        or not _json_semantically_equal(
            handoff,
            {
                "contractName": "chummer.public-preview-byte-handoff/v1",
                "status": "approved_public_preview_bytes",
                "sourcePublicationState": "preview",
                "releaseScopeDecisionSha256": (
                    release_scope_decision_sha256
                ),
                "releaseVersion": release_version,
                "channel": "preview",
                **artifact,
                "signingRequirement": "preview_unsigned_allowed",
            },
        )
    ):
        raise CutoverError(
            "served releaseTruth is not the review-required public-byte posture"
        )


def _review_required_release_truth_authority(
    shelf: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    authority = shelf.get("releaseCandidateAuthority")
    release_truth = (
        authority.get("reviewRequiredReleaseTruth")
        if isinstance(authority, dict)
        else None
    )
    release_scope_decision_sha256 = (
        authority.get("releaseScopeDecisionSha256")
        if isinstance(authority, dict)
        else None
    )
    canonical_manifest_sha256 = (
        authority.get("canonicalManifestSha256")
        if isinstance(authority, dict)
        else None
    )
    review_authority = (
        authority.get("reviewAuthority")
        if isinstance(authority, dict)
        else None
    )
    if (
        not isinstance(release_truth, dict)
        or not isinstance(release_scope_decision_sha256, str)
        or SHA256.fullmatch(release_scope_decision_sha256) is None
        or not isinstance(canonical_manifest_sha256, str)
        or SHA256.fullmatch(canonical_manifest_sha256) is None
        or release_truth.get("manifestSha256")
        != canonical_manifest_sha256
        or release_truth.get("releaseScopeDecisionSha256")
        != release_scope_decision_sha256
        or release_truth.get("releaseVersion")
        != authority.get("candidateVersion")
        or not isinstance(review_authority, dict)
        or review_authority.get("contractName")
        != "chummer.review-required-public-byte-authority/v1"
        or review_authority.get("status") != "pass"
        or review_authority.get("generationId")
        != authority.get("generationId")
        or review_authority.get("manifestSha256")
        != release_truth.get("manifestSha256")
        or review_authority.get("releaseScopeDecisionSha256")
        != release_truth.get("releaseScopeDecisionSha256")
        or review_authority.get("releaseDecisionSha256")
        != release_truth.get("releaseDecisionSha256")
        or SHA256.fullmatch(
            str(review_authority.get("authoritySnapshotSha256") or "")
        )
        is None
    ):
        raise CutoverError(
            "review-required releaseTruth authority is unavailable"
        )
    return release_truth, release_scope_decision_sha256


def probe_sidecar_hosts(
    config: SidecarConfig,
    *,
    shelf: Mapping[str, Any],
    generation_id: str,
    generation_root: Path,
) -> dict[str, Any]:
    canonical = stable_regular_bytes(
        generation_root / "RELEASE_CHANNEL.generated.json",
        label="prepared generation canonical manifest",
        maximum_bytes=8 * 1024 * 1024,
    )
    compatibility = stable_regular_bytes(
        generation_root / "releases.json",
        label="prepared generation compatibility manifest",
        maximum_bytes=8 * 1024 * 1024,
    )
    observations: list[dict[str, Any]] = []
    for hostname in SIDECAR_HOSTS:
        status, _headers, readiness = _http_bytes(
            scheme="http",
            connect_host=SIDECAR_ADDRESS,
            connect_port=SIDECAR_PORT,
            request_host=hostname,
            path="/api/ready/public-downloads",
            timeout=30,
        )
        try:
            readiness_payload = json.loads(readiness)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CutoverError("sidecar readiness response is malformed") from exc
        if (
            status != 200
            or not isinstance(readiness_payload, dict)
            or readiness_payload.get("ready") is not True
            or readiness_payload.get("servingReady") is not True
        ):
            raise CutoverError("sidecar serving readiness did not pass")
        observations.append(
            {
                "endpoint": f"http://{hostname}/api/ready/public-downloads",
                "httpStatus": status,
                "bodySha256": sha256_bytes(readiness),
                "anonymous": True,
            }
        )
        for path, expected in (
            ("/downloads/RELEASE_CHANNEL.generated.json", canonical),
            ("/downloads/releases.json", compatibility),
            (
                f"/downloads/g/{generation_id}/"
                "RELEASE_CHANNEL.generated.json",
                canonical,
            ),
            (f"/downloads/g/{generation_id}/releases.json", compatibility),
        ):
            observations.append(
                _probe_exact_manifest(
                    scheme="http",
                    connect_host=SIDECAR_ADDRESS,
                    connect_port=SIDECAR_PORT,
                    request_host=hostname,
                    path=path,
                    expected=expected,
                    shelf=shelf,
                    generation_id=generation_id,
                )
            )
    artifact_verification = probe_download_artifact_hosts(
        config,
        shelf=shelf,
        scope="local",
    )
    return {
        "status": "pass",
        "origin": SIDECAR_ORIGIN,
        "hosts": list(SIDECAR_HOSTS),
        "generationId": generation_id,
        "observations": observations,
        "artifactVerification": artifact_verification,
    }


def _local_served_generation_manifest_sha256(
    local_probe: Mapping[str, Any],
    *,
    generation_id: str,
) -> str:
    expected_endpoints = {
        (
            f"http://{hostname}/downloads/g/{generation_id}/"
            "releases.json"
        )
        for hostname in SIDECAR_HOSTS
    }
    if (
        local_probe.get("status") != "pass"
        or local_probe.get("origin") != SIDECAR_ORIGIN
        or local_probe.get("hosts") != list(SIDECAR_HOSTS)
        or local_probe.get("generationId") != generation_id
        or not isinstance(local_probe.get("observations"), list)
    ):
        raise CutoverError(
            "recorded local generation probe authority is malformed"
        )
    matched: dict[str, str] = {}
    for candidate in local_probe["observations"]:
        if not isinstance(candidate, Mapping):
            raise CutoverError(
                "recorded local generation probe observation is malformed"
            )
        endpoint = candidate.get("endpoint")
        if endpoint not in expected_endpoints:
            continue
        if endpoint in matched:
            raise CutoverError(
                "recorded local generation probe endpoint is duplicated"
            )
        body_sha256 = str(candidate.get("bodySha256") or "")
        if (
            candidate.get("httpStatus") != 200
            or candidate.get("generationId") != generation_id
            or candidate.get("anonymous") is not True
            or SHA256.fullmatch(body_sha256) is None
        ):
            raise CutoverError(
                "recorded local generation probe observation is invalid"
            )
        matched[str(endpoint)] = body_sha256
    if set(matched) != expected_endpoints:
        raise CutoverError(
            "recorded local generation probe host closure is incomplete"
        )
    unique_sha256 = set(matched.values())
    if len(unique_sha256) != 1:
        raise CutoverError(
            "recorded local generation probe body digest diverged by host"
        )
    return unique_sha256.pop()


def probe_public_incumbent(
    config: SidecarConfig,
    *,
    expected: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
) -> dict[str, dict[str, Any]]:
    base = urlsplit(config.base_url)
    if base.scheme != "https" or base.hostname != SIDECAR_HOSTS[0]:
        raise CutoverError("public base URL is outside the canonical origin")
    observations: dict[str, dict[str, Any]] = {}
    for hostname in SIDECAR_HOSTS:
        host_observations: dict[str, Any] = {}
        for path in (
            "/downloads/RELEASE_CHANNEL.generated.json",
            "/downloads/releases.json",
        ):
            status, _headers, body = _http_bytes(
                scheme="https",
                connect_host=hostname,
                connect_port=443,
                request_host=hostname,
                path=path,
                timeout=30,
            )
            observation = {
                "httpStatus": status,
                "bodySha256": sha256_bytes(body),
                "sizeBytes": len(body),
            }
            if status != 200:
                raise CutoverError("incumbent public manifest is unavailable")
            if (
                expected is not None
                and observation != expected.get(hostname, {}).get(path)
            ):
                raise CutoverError(
                    "incumbent public manifest changed across rollback"
                )
            host_observations[path] = observation
        observations[hostname] = host_observations
    return observations


class TopologyBActionsProtocol(Protocol):
    def record_primary_failure(self, config: Any, error: Exception) -> dict[str, Any]: ...
    def prepare_sidecar_release_shelf(self, config: Any) -> dict[str, Any]: ...
    def generate_sidecar_data_protection(self, config: Any) -> dict[str, Any]: ...
    def materialize_sidecar_compose(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def create_sidecar_resources(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def start_sidecar_runtime(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def wait_sidecar_healthy(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def probe_sidecar_hosts(self, config: Any, *args: Any, **kwargs: Any) -> dict[str, Any]: ...
    def probe_public_incumbent(self, config: Any, **kwargs: Any) -> dict[str, Any]: ...
    def capture_cloudflare(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def apply_cloudflare(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def commit_cloudflare(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def write_active_receipt(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def rollback_cloudflare(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def cleanup_sidecar_resources(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def classify_recovery(self, config: Any) -> str: ...
    def reconcile_committed(self, config: Any, *args: Any) -> dict[str, Any]: ...
    def authorize_committed_retirement(
        self, config: Any, *args: Any
    ) -> dict[str, Any]: ...
    def restore_committed_prior(
        self, config: Any, *args: Any
    ) -> dict[str, Any]: ...
    def commit_retirement_evidence(
        self, config: Any, *args: Any
    ) -> dict[str, Any]: ...
    def retire_active_authority(
        self, config: Any, *args: Any
    ) -> dict[str, Any]: ...
    def verify_retired_authority_connectors(
        self, config: Any, *args: Any
    ) -> dict[str, Any]: ...
    def finalize_committed_retirement(
        self, config: Any, *args: Any
    ) -> dict[str, Any]: ...


def _validate_sidecar_config(config: SidecarConfig) -> None:
    if config.operation not in OPERATIONS:
        raise CutoverError("topology-B operation is invalid")
    if COMMIT.fullmatch(config.source_head) is None:
        raise CutoverError("source HEAD must be a lowercase full commit")
    controller_source_head = (
        getattr(config, "controller_source_head", "") or config.source_head
    )
    if COMMIT.fullmatch(controller_source_head) is None:
        raise CutoverError(
            "controller source HEAD must be a lowercase full commit"
        )
    if SHA256.fullmatch(config.shared_lock_token) is None:
        raise CutoverError("shared mutation lock token is invalid")
    if SIDECAR_PROJECT.fullmatch(config.project_name) is None:
        raise CutoverError("sidecar Compose project name is invalid")
    if config.base_url.rstrip("/") != "https://chummer.run":
        raise CutoverError("public base URL is not canonical")
    if CF_ACCOUNT_ID.fullmatch(config.cloudflare_account_id) is None:
        raise CutoverError("Cloudflare account id is invalid")
    if CF_TUNNEL_ID.fullmatch(config.cloudflare_tunnel_id) is None:
        raise CutoverError("Cloudflare tunnel id is invalid")
    if config.cloudflare_api_base != "https://api.cloudflare.com/client/v4":
        raise CutoverError("Cloudflare API base is invalid")
    if not 1 <= config.ready_timeout_seconds <= 900:
        raise CutoverError("portal readiness timeout is outside the audited range")
    if config.delivery_phase not in {"bootstrap", "windows-preview"}:
        raise CutoverError("public download delivery phase is invalid")
    if (
        config.operation == RETIRE_OPERATION
        and SHA256.fullmatch(
            getattr(config, "canonical_publisher_sha256", "")
        )
        is None
    ):
        raise CutoverError(
            "canonical flagship publisher SHA-256 is required for retirement"
        )
    try:
        observed_head = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(config.source_root),
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ],
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CutoverError("source HEAD could not be verified") from exc
    if observed_head != controller_source_head:
        raise CutoverError("checked-out source does not match source HEAD")
    if config.operation in {RECOVERY_OPERATION, RETIRE_OPERATION}:
        for directory, label in (
            (config.source_root, "source root"),
            (config.shelf_root, "canonical release shelf"),
            (config.receipt_root, "receipt root"),
            (config.docker_config_root, "Docker configuration root"),
            (
                config.docker_config_root / "config",
                "Docker client configuration",
            ),
            (
                config.active_runtime_authority.parent,
                "active runtime authority parent",
            ),
        ):
            try:
                metadata = directory.lstat()
            except OSError as exc:
                raise CutoverError(f"{label} is unavailable") from exc
            if (
                not directory.is_absolute()
                or directory.resolve(strict=True) != directory
                or not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
            ):
                raise CutoverError(f"{label} is unsafe")
        if config.shelf_root != CANONICAL_RELEASE_SHELF_ROOT:
            raise CutoverError("canonical release shelf path drifted")
        stable_regular_bytes(
            config.cloudflare_credentials_file,
            label="Cloudflare credentials file",
            maximum_bytes=1024 * 1024,
            owner_only=True,
        )
        if config.operation_root.exists():
            private_directory(config.operation_root, create=False)
        elif (
            config.operation != RECOVERY_OPERATION
            or not config.operation_journal.is_file()
        ):
            raise RecoveryUncertain(
                "journaled operation has no exact operation root"
            )
        private_directory(config.receipt_root, create=False)
        private_directory(config.docker_config_root, create=False)
        private_directory(config.docker_config_root / "config", create=False)
        private_directory(
            config.active_runtime_authority.parent,
            create=False,
        )
        return
    for directory, label in (
        (config.source_root, "source root"),
        (config.shelf_root, "canonical release shelf"),
        (config.migration_candidate_root, "migration candidate"),
        (config.release_candidate_root, "sealed release candidate"),
        (config.projection_snapshot_root, "projection snapshot"),
        (config.fleet_source, "fleet runtime source"),
        (config.build_context, "build context"),
        (config.fleet_media_contracts, "fleet media contracts"),
        (config.design_product_root, "design product root"),
        (config.receipt_root, "receipt root"),
        (config.docker_config_root, "Docker configuration root"),
        (config.docker_config_root / "config", "Docker client configuration"),
    ):
        try:
            metadata = directory.lstat()
        except OSError as exc:
            raise CutoverError(f"{label} is unavailable") from exc
        if (
            not directory.is_absolute()
            or directory.resolve(strict=True) != directory
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
        ):
            raise CutoverError(f"{label} is unsafe")
    if (
        config.shelf_root != CANONICAL_RELEASE_SHELF_ROOT
        or config.shelf_root.is_symlink()
    ):
        raise CutoverError("canonical release shelf path drifted")
    for digest, label in (
        (config.migration_authority_sha256, "migration authority"),
        (
            config.candidate_import_authority_sha256,
            "candidate import authority",
        ),
        (
            config.direct_import_receipt_sha256,
            "direct-import receipt",
        ),
        (
            config.manifest_closure_restoration_spec_sha256,
            "manifest-closure restoration spec",
        ),
        (config.release_channel_receipt_sha256, "release-channel receipt"),
        (config.projection_snapshot_sha256, "projection snapshot"),
        (
            config.projection_source_tree_sha256,
            "projection source tree",
        ),
        (config.projection_manifest_sha256, "projection manifest"),
        (config.runtime_proof_sha256, "runtime proof"),
        (config.final_gold_sha256, "final-gold handoff"),
        (config.fleet_sha256, "fleet runtime tree"),
    ):
        if SHA256.fullmatch(digest) is None:
            raise CutoverError(f"{label} SHA-256 is invalid")
    if (
        config.projection_snapshot_id
        != f"public-projection-{config.projection_snapshot_sha256}"
    ):
        raise CutoverError("projection snapshot identity is invalid")
    for path, digest, label, owner_only in (
        (
            config.migration_authority,
            config.migration_authority_sha256,
            "migration authority",
            False,
        ),
        (
            config.candidate_import_authority,
            config.candidate_import_authority_sha256,
            "candidate import authority",
            False,
        ),
        (
            config.direct_import_receipt,
            config.direct_import_receipt_sha256,
            "direct-import receipt",
            False,
        ),
        (
            config.manifest_closure_restoration_spec,
            config.manifest_closure_restoration_spec_sha256,
            "manifest-closure restoration spec",
            False,
        ),
        (
            config.release_channel_receipt,
            config.release_channel_receipt_sha256,
            "release-channel receipt",
            False,
        ),
        (
            config.runtime_proof_source,
            config.runtime_proof_sha256,
            "runtime proof",
            False,
        ),
        (
            config.final_gold_source,
            config.final_gold_sha256,
            "final-gold handoff",
            False,
        ),
        (
            config.cloudflare_credentials_file,
            "",
            "Cloudflare credentials file",
            True,
        ),
    ):
        raw = stable_regular_bytes(
            path,
            label=label,
            maximum_bytes=None if digest else 1024 * 1024,
            owner_only=owner_only,
        )
        if digest and sha256_bytes(raw) != digest:
            raise CutoverError(f"{label} SHA-256 drifted")
    observed_fleet = tree_sha256_file_stream(
        config.fleet_source,
        label="fleet runtime source",
    )
    if observed_fleet != config.fleet_sha256:
        raise CutoverError("fleet runtime source tree digest drifted")
    observed_projection = tree_sha256_file_stream(
        config.projection_snapshot_root,
        label="projection snapshot source",
    )
    if observed_projection != config.projection_source_tree_sha256:
        raise CutoverError("projection snapshot tree digest drifted")
    if config.projection_snapshot_root.name != config.projection_snapshot_id:
        raise CutoverError("projection snapshot directory identity drifted")
    if config.candidate_import_authority != (
        config.projection_snapshot_root
        / "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
    ):
        raise CutoverError(
            "candidate import authority is outside the selected projection snapshot"
        )
    if config.direct_import_receipt != (
        config.release_candidate_root.parent
        / "UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json"
    ):
        raise CutoverError(
            "direct-import receipt is not adjacent to the sealed candidate bundle"
        )
    if config.release_channel_receipt != (
        config.projection_snapshot_root / "RELEASE_CHANNEL.generated.json"
    ):
        raise CutoverError(
            "release-channel receipt is outside the selected projection snapshot"
        )
    if config.runtime_proof_source != (
        config.projection_snapshot_root
        / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    ):
        raise CutoverError(
            "runtime proof is outside the selected projection snapshot"
        )
    private_directory(config.receipt_root, create=False)
    private_directory(config.active_runtime_authority.parent, create=False)
    private_directory(config.docker_config_root, create=False)
    private_directory(config.docker_config_root / "config", create=False)
    if config.operation == CUTOVER_OPERATION:
        if config.operation_root.exists() or config.operation_root.is_symlink():
            raise CutoverError("fresh sidecar operation root already exists")
        private_directory(config.operation_root.parent, create=False)
    else:
        private_directory(config.operation_root, create=False)


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


def _candidate_inventory_sha256(
    rows: list[dict[str, Any]],
) -> str:
    digest = hashlib.sha256()
    for row in rows:
        encoded = str(row["path"]).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(int(row["sizeBytes"]).to_bytes(8, "big"))
        digest.update(bytes.fromhex(str(row["sha256"])))
    return digest.hexdigest()


def _scope_bound_full_candidate_inventory(
    config: SidecarConfig,
    *,
    candidate_materializer: Any,
    inventory: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[
    list[dict[str, Any]],
    dict[str, int],
    list[dict[str, Any]],
    dict[str, bytes],
]:
    if (
        set(inventory) != {"contractName", "contractVersion", "files"}
        or inventory.get("contractName")
        != "chummer.release-upload.candidate-inventory/v1"
        or type(inventory.get("contractVersion")) is not int
        or inventory["contractVersion"] != 1
        or not isinstance(inventory.get("files"), list)
    ):
        raise CutoverError("scope-bound candidate inventory contract drifted")
    authority_rows = inventory["files"]
    if (
        not authority_rows
        or any(
            not isinstance(row, dict)
            or set(row) != {"path", "sha256", "sizeBytes"}
            or not isinstance(row.get("path"), str)
            or not row["path"]
            or row["path"].startswith("/")
            or "\\" in row["path"]
            or any(
                part in {"", ".", ".."} or ":" in part
                for part in row["path"].split("/")
            )
            or not isinstance(row.get("sha256"), str)
            or SHA256.fullmatch(row["sha256"]) is None
            or type(row.get("sizeBytes")) is not int
            or row["sizeBytes"] < 0
            for row in authority_rows
        )
        or authority_rows
        != sorted(authority_rows, key=lambda row: str(row["path"]))
        or len({str(row["path"]) for row in authority_rows})
        != len(authority_rows)
    ):
        raise CutoverError("scope-bound candidate inventory rows drifted")

    try:
        (
            actual_rows,
            actual_modes,
            actual_directories,
            captured,
        ) = candidate_materializer._scan_bundle_tree(
            config.release_candidate_root
        )
    except CutoverError:
        raise
    except Exception as exc:
        raise CutoverError(
            "scope-bound full candidate tree validation failed"
        ) from exc

    authority_paths = {
        str(row["path"]) for row in authority_rows
    }
    actual_by_path = {
        str(row["path"]): row for row in actual_rows
    }
    if (
        len(actual_by_path) != len(actual_rows)
        or set(actual_by_path) - authority_paths
        != SCOPE_BOUND_CANDIDATE_ADJUNCT_PATHS
        or authority_paths - set(actual_by_path)
    ):
        raise CutoverError(
            "scope-bound candidate adjunct path closure drifted"
        )
    authenticated_rows = [
        actual_by_path[str(row["path"])]
        for row in authority_rows
    ]
    if authenticated_rows != authority_rows:
        raise CutoverError(
            "scope-bound authenticated candidate subset drifted"
        )
    if (
        type(candidate.get("fileCount")) is not int
        or candidate["fileCount"] != len(authenticated_rows)
        or type(candidate.get("totalBytes")) is not int
        or candidate["totalBytes"]
        != sum(row["sizeBytes"] for row in authenticated_rows)
        or candidate.get("inventorySha256")
        != _candidate_inventory_sha256(authenticated_rows)
    ):
        raise CutoverError(
            "scope-bound authenticated candidate summary drifted"
        )

    authenticated_directories = {
        prefix
        for path in authority_paths
        for prefix in (
            "/".join(path.split("/")[:index])
            for index in range(1, len(path.split("/")))
        )
    }
    actual_directory_by_path = {
        str(row.get("path") or ""): row
        for row in actual_directories
        if isinstance(row, dict)
    }
    expected_directories = authenticated_directories | {
        "release-evidence",
        "startup-smoke",
    }
    if (
        len(actual_directory_by_path) != len(actual_directories)
        or set(actual_directory_by_path) != expected_directories
        or any(
            actual_directory_by_path[path].get("mode") != 0o700
            for path in ("release-evidence", "startup-smoke")
        )
        or any(
            actual_modes.get(path) != 0o400
            for path in SCOPE_BOUND_CANDIDATE_ADJUNCT_PATHS
        )
    ):
        raise CutoverError(
            "scope-bound candidate adjunct metadata drifted"
        )

    adjunct_bytes: dict[str, bytes] = {}
    for path in sorted(SCOPE_BOUND_CANDIDATE_ADJUNCT_PATHS):
        raw = stable_regular_bytes(
            config.release_candidate_root / path,
            label=f"scope-bound candidate adjunct {path}",
            maximum_bytes=4 * 1024 * 1024,
            owner_only=True,
        )
        row = actual_by_path[path]
        if (
            sha256_bytes(raw) != row["sha256"]
            or len(raw) != row["sizeBytes"]
        ):
            raise CutoverError(
                "scope-bound candidate adjunct changed after inventory scan"
            )
        adjunct_bytes[path] = raw

    return (
        authenticated_rows,
        {
            path: int(actual_modes[path])
            for path in authority_paths
        },
        [
            actual_directory_by_path[path]
            for path in sorted(authenticated_directories)
        ],
        {
            **captured,
            **adjunct_bytes,
        },
    )


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
        or any(
            not isinstance(item, dict)
            or set(item) != {"id", "severity", "summary"}
            or item.get("severity") != "release_truth"
            or not isinstance(item.get("id"), str)
            or not item["id"]
            or not isinstance(item.get("summary"), str)
            or not item["summary"]
            for item in blocking
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


def _validate_scope_bound_existing_bytes_candidate(
    config: SidecarConfig,
    *,
    projection_verifier: Any,
    candidate_materializer: Any,
    authority: dict[str, Any],
    authority_raw: bytes,
    candidate: dict[str, Any],
    custody: dict[str, Any],
    direct_import: dict[str, Any],
) -> dict[str, Any]:
    """Validate the zero-retention existing-bytes v3 import profile."""

    profile = SCOPE_BOUND_EXISTING_BYTES_PROFILE
    if config.direct_import_receipt != (
        config.release_candidate_root.parent
        / "UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json"
    ):
        raise CutoverError(
            "scope-bound direct-import receipt is not candidate-adjacent"
        )
    direct_keys = {
        "canonicalManifest",
        "compatibilityManifest",
        "contractName",
        "contractVersion",
        "crossRunBitReproducible",
        "deployAuthorized",
        "generationInventory",
        "hubCandidateImportAuthority",
        "platformScope",
        "projectionProfile",
        "publicationAuthorized",
        "release",
        "releaseScopeDecision",
        "signature",
        "sourceCommitPosture",
        "sourceCommits",
        "status",
        "transport",
        "uploadAuthorized",
    }
    authority_sha256 = sha256_bytes(authority_raw)
    if (
        set(direct_import) != direct_keys
        or direct_import.get("contractName")
        != "chummer6-ui.preview-nightly-unsigned-direct-import"
        or type(direct_import.get("contractVersion")) is not int
        or direct_import.get("contractVersion") != 1
        or direct_import.get("projectionProfile") != profile
        or direct_import.get("status") != "sealed_review_required"
        or direct_import.get("platformScope") != "windows_only"
        or direct_import.get("crossRunBitReproducible") is not False
        or not _json_semantically_equal(
            direct_import.get("signature"),
            {
                "policy": "preview_policy",
                "required": False,
                "status": "unsigned",
            },
        )
        or any(
            direct_import.get(name) is not False
            for name in (
                "publicationAuthorized",
                "uploadAuthorized",
                "deployAuthorized",
            )
        )
        or not _json_semantically_equal(
            direct_import.get("release"),
            {
                "channel": "preview",
                "version": candidate.get("version"),
            },
        )
        or not _json_semantically_equal(
            direct_import.get("sourceCommitPosture"),
            SCOPE_BOUND_SOURCE_COMMIT_POSTURE,
        )
        or not _json_semantically_equal(
            direct_import.get("hubCandidateImportAuthority"),
            {
                "path": (
                    "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
                ),
                "sha256": authority_sha256,
                "sizeBytes": len(authority_raw),
            },
        )
    ):
        raise CutoverError(
            "scope-bound direct-import receipt authority posture drifted"
        )
    try:
        projection_verifier._scope_bound_secret_free(
            direct_import, label="scope-bound direct-import receipt"
        )
        inventory_raw = projection_verifier._candidate_embedded_bytes(
            custody.get("inventory"),
            label="scope-bound candidate upload inventory",
            expected_path="CANDIDATE_UPLOAD_INVENTORY.generated.json",
        )
        inventory = projection_verifier._strict_json_object(
            inventory_raw,
            label="scope-bound candidate upload inventory",
        )
        (
            release_rows,
            release_modes,
            release_directories,
            release_captured,
        ) = _scope_bound_full_candidate_inventory(
            config,
            candidate_materializer=candidate_materializer,
            inventory=inventory,
            candidate=candidate,
        )
        canonical_raw = projection_verifier._candidate_embedded_bytes(
            custody.get("canonicalManifest"),
            label="scope-bound candidate canonical manifest",
            expected_path="RELEASE_CHANNEL.generated.json",
        )
        compatibility_raw = projection_verifier._candidate_embedded_bytes(
            custody.get("compatibilityManifest"),
            label="scope-bound candidate compatibility manifest",
            expected_path="releases.json",
        )
        decision_raw = projection_verifier._candidate_embedded_bytes(
            custody.get("releaseScopeDecision"),
            label="scope-bound approved release decision",
            expected_path=projection_verifier.CANDIDATE_SCOPE_DECISION_FILE,
        )
        generation_raw = projection_verifier._candidate_embedded_bytes(
            custody.get("generationInventory"),
            label="scope-bound generation inventory",
            expected_path=(
                projection_verifier.CANDIDATE_GENERATION_INVENTORY_FILE
            ),
        )
        generation = projection_verifier._strict_json_object(
            generation_raw,
            label="scope-bound generation inventory",
        )
        canonical = projection_verifier._strict_json_object(
            canonical_raw, label="scope-bound canonical manifest"
        )
        compatibility = projection_verifier._strict_json_object(
            compatibility_raw,
            label="scope-bound compatibility manifest",
        )
    except CutoverError:
        raise
    except Exception as exc:
        raise CutoverError(
            "scope-bound release bundle custody validation failed"
        ) from exc

    def reference(raw: bytes, path: str) -> dict[str, Any]:
        return {
            "path": path,
            "sha256": sha256_bytes(raw),
            "sizeBytes": len(raw),
        }

    source_commits = direct_import.get("sourceCommits")
    binding = custody.get("scopeBoundExistingBytes")
    if (
        not isinstance(binding, dict)
        or not isinstance(source_commits, dict)
        or not _json_semantically_equal(
            source_commits,
            binding.get("sourceCommits"),
        )
        or not _json_semantically_equal(
            binding.get("sourceCommitPosture"),
            SCOPE_BOUND_SOURCE_COMMIT_POSTURE,
        )
        or not _json_semantically_equal(
            direct_import.get("sourceCommitPosture"),
            binding.get("sourceCommitPosture"),
        )
        or set(source_commits) != {"hub", "registry", "ui"}
        or any(
            COMMIT.fullmatch(str(source_commits.get(name) or "")) is None
            for name in ("hub", "registry", "ui")
        )
        or source_commits.get("hub") != config.source_head
        or not _json_semantically_equal(
            direct_import.get("releaseScopeDecision"),
            reference(
                decision_raw,
                projection_verifier.CANDIDATE_SCOPE_DECISION_FILE,
            ),
        )
        or not _json_semantically_equal(
            direct_import.get("generationInventory"),
            reference(
                generation_raw,
                projection_verifier.CANDIDATE_GENERATION_INVENTORY_FILE,
            ),
        )
        or not _json_semantically_equal(
            direct_import.get("canonicalManifest"),
            reference(canonical_raw, "RELEASE_CHANNEL.generated.json"),
        )
        or not _json_semantically_equal(
            direct_import.get("compatibilityManifest"),
            reference(compatibility_raw, "releases.json"),
        )
        or not _json_semantically_equal(
            direct_import.get("transport"),
            {
                "bundleIdentitySha256": candidate.get(
                    "bundleIdentitySha256"
                ),
                "generationId": binding.get("generationId"),
                "mode": "existing_bytes",
            },
        )
    ):
        raise CutoverError(
            "scope-bound direct-import receipt byte graph drifted"
        )
    try:
        projection_verifier._validate_scope_bound_manifest_source_and_routes(
            canonical,
            compatibility,
            generation_id=str(binding.get("generationId") or ""),
            registry_commit=str(source_commits["registry"]),
        )
    except Exception as exc:
        raise CutoverError(
            "scope-bound manifest source or route revalidation failed"
        ) from exc

    release_files = [
        {**row, "mode": release_modes[str(row["path"])]}
        for row in release_rows
    ]
    root_mode = stat.S_IMODE(config.release_candidate_root.lstat().st_mode)
    if (
        type(generation.get("rootMode")) is not int
        or generation["rootMode"] != root_mode
        or not _json_semantically_equal(
            generation.get("files"),
            release_files,
        )
        or not _json_semantically_equal(
            generation.get("directories"),
            release_directories,
        )
        or not _json_semantically_equal(
            binding.get("retainedFromIncumbent"),
            [],
        )
        or not _json_semantically_equal(
            binding.get("retainedPlatforms"),
            [],
        )
        or not _json_semantically_equal(
            binding.get("shelfPlatforms"),
            ["windows"],
        )
    ):
        raise CutoverError(
            "scope-bound generation inventory or zero-retention posture drifted"
        )
    expected_fresh_paths = (
        "files/chummer-avalonia-win-x64-installer.exe",
        "files/chummer-avalonia-win-x64-payload.zip",
        "files/chummer-avalonia-win-x64-payload.zip.json",
    )
    fresh = binding.get("freshDelta")
    if (
        not isinstance(fresh, list)
        or tuple(
            str(item.get("path") or "")
            for item in fresh
            if isinstance(item, dict)
        )
        != expected_fresh_paths
    ):
        raise CutoverError(
            "scope-bound fresh delta is not installer/payload/sidecar"
        )
    release_by_path = {
        str(item["path"]): item for item in release_files
    }
    fresh_by_path = {
        str(item["path"]): item
        for item in fresh
        if isinstance(item, dict)
    }
    for path in expected_fresh_paths:
        release_row = release_by_path.get(path)
        fresh_row = fresh_by_path.get(path)
        if release_row is None or fresh_row is None or any(
            not _json_semantically_equal(
                release_row.get(key),
                fresh_row.get(key),
            )
            for key in ("mode", "sha256", "sizeBytes")
        ):
            raise CutoverError(
                "scope-bound fresh delta differs from exact candidate bytes"
            )

    canonical_bundle_raw = stable_regular_bytes(
        config.release_candidate_root
        / "RELEASE_CHANNEL.generated.json",
        label="scope-bound candidate canonical manifest",
        maximum_bytes=8 * 1024 * 1024,
    )
    compatibility_bundle_raw = stable_regular_bytes(
        config.release_candidate_root / "releases.json",
        label="scope-bound candidate compatibility manifest",
        maximum_bytes=8 * 1024 * 1024,
    )
    release_receipt_raw = stable_regular_bytes(
        config.release_channel_receipt,
        label="scope-bound authenticated release-channel receipt",
        maximum_bytes=8 * 1024 * 1024,
    )
    if (
        canonical_bundle_raw != canonical_raw
        or canonical_bundle_raw != release_receipt_raw
        or compatibility_bundle_raw != compatibility_raw
        or sha256_bytes(release_receipt_raw)
        != config.release_channel_receipt_sha256
    ):
        raise CutoverError(
            "scope-bound release manifest bytes do not share one authority"
        )

    review_authority = _validate_scope_bound_review_authority(
        canonical_raw=canonical_bundle_raw,
        canonical=canonical,
        evidence_bytes=release_captured,
        generation_id=str(binding.get("generationId") or ""),
        release_scope_decision_sha256=str(
            binding.get("releaseScopeDecisionSha256") or ""
        ),
        candidate_version=str(candidate.get("version") or ""),
    )
    startup_smoke = _validate_scope_bound_startup_smoke(
        release_captured[SCOPE_BOUND_STARTUP_SMOKE_PATH],
        artifact=canonical["artifacts"][0],
        release_version=str(candidate.get("version") or ""),
    )

    sidecar_raw = stable_regular_bytes(
        config.release_candidate_root
        / "files"
        / "chummer-avalonia-win-x64-payload.zip.json",
        label="scope-bound Windows payload sidecar",
        maximum_bytes=1024 * 1024,
    )
    try:
        sidecar = projection_verifier._strict_json_object(
            sidecar_raw, label="scope-bound Windows payload sidecar"
        )
        installer = canonical["artifacts"][0]
        payload_name = str(installer.get("payloadFileName") or "")
        sidecar_url = urlsplit(str(sidecar.get("downloadUrl") or ""))
    except Exception as exc:
        raise CutoverError(
            "scope-bound Windows payload sidecar is malformed"
        ) from exc
    if (
        set(sidecar)
        != {
            "contractName",
            "downloadUrl",
            "fileName",
            "installerFileName",
            "payloadAcquisitionMode",
            "releaseVersion",
            "sha256",
            "sizeBytes",
        }
        or sidecar.get("contractName")
        != "chummer6-ui.windows_bootstrap_payload"
        or sidecar.get("fileName") != installer.get("payloadFileName")
        or sidecar.get("installerFileName") != installer.get("fileName")
        or sidecar.get("payloadAcquisitionMode") != "download"
        or sidecar.get("releaseVersion") != candidate.get("version")
        or sidecar.get("sha256") != installer.get("payloadSha256")
        or type(sidecar.get("sizeBytes")) is not int
        or sidecar["sizeBytes"] <= 0
        or not _json_semantically_equal(
            sidecar.get("sizeBytes"),
            installer.get("payloadSizeBytes"),
        )
        or sidecar_url.query
        or sidecar_url.fragment
        or sidecar_url.path != f"/downloads/files/{payload_name}"
        or sidecar_url.scheme not in {"", "https"}
        or sidecar_url.scheme == ""
        and bool(sidecar_url.netloc)
        or sidecar_url.scheme == "https"
        and (
            sidecar_url.netloc != "chummer.run"
            or sidecar_url.hostname != "chummer.run"
            or sidecar_url.username is not None
            or sidecar_url.password is not None
        )
    ):
        raise CutoverError(
            "scope-bound Windows payload sidecar byte graph drifted"
        )

    empty_inventory_sha256 = (
        projection_verifier._candidate_ui_compact_sha256([])
    )
    return {
        "path": str(config.candidate_import_authority),
        "sha256": config.candidate_import_authority_sha256,
        "contractName": authority["contractName"],
        "contractVersion": authority["contractVersion"],
        "projectionProfile": profile,
        "candidateVersion": candidate["version"],
        "generationId": binding["generationId"],
        "releaseScopeDecisionSha256": binding[
            "releaseScopeDecisionSha256"
        ],
        "reviewRequiredReleaseTruth": review_authority[
            "releaseTruth"
        ],
        "reviewAuthority": {
            key: value
            for key, value in review_authority.items()
            if key != "releaseTruth"
        },
        "startupSmoke": startup_smoke,
        "sourceCommits": dict(source_commits),
        "sourceCommitVerification": (
            SCOPE_BOUND_SOURCE_COMMIT_VERIFICATION
        ),
        "directImportReceipt": {
            "path": str(config.direct_import_receipt),
            "sha256": config.direct_import_receipt_sha256,
        },
        "bundleIdentitySha256": candidate["bundleIdentitySha256"],
        "inventorySha256": candidate["inventorySha256"],
        "fileCount": candidate["fileCount"],
        "totalBytes": candidate["totalBytes"],
        "canonicalManifestSha256": candidate[
            "canonicalManifestSha256"
        ],
        "freshDelta": [
            {
                "path": path,
                "sha256": str(fresh_by_path[path]["sha256"]),
                "sizeBytes": int(fresh_by_path[path]["sizeBytes"]),
            }
            for path in expected_fresh_paths
        ],
        "retainedInventorySha256": empty_inventory_sha256,
        "incumbentInventorySha256": empty_inventory_sha256,
        "servingAuthority": True,
        "validatedAtUtc": utc_now(),
    }


def validate_release_candidate_authority(
    config: SidecarConfig,
    *,
    projection_verifier: Any | None = None,
    candidate_materializer: Any | None = None,
) -> dict[str, Any]:
    """Authenticate the exact sealed bundle and its incumbent/fresh partition."""

    scripts = config.source_root / "scripts"
    projection_verifier = projection_verifier or load_module(
        scripts / "release/verify_public_projection.py",
        f"topology_b_projection_verifier_{secrets.token_hex(6)}",
    )
    candidate_materializer = candidate_materializer or load_module(
        scripts / "release/materialize_candidate_import_authority.py",
        f"topology_b_candidate_materializer_{secrets.token_hex(6)}",
    )
    authority_raw = stable_regular_bytes(
        config.candidate_import_authority,
        label="candidate import authority",
        maximum_bytes=16 * 1024 * 1024,
    )
    if (
        sha256_bytes(authority_raw)
        != config.candidate_import_authority_sha256
    ):
        raise CutoverError("candidate import authority SHA-256 drifted")
    try:
        authority = projection_verifier._validate_candidate_import_authority(
            authority_raw
        )
    except Exception as exc:
        raise CutoverError(
            "candidate import authority semantic validation failed"
        ) from exc
    if (
        authority.get("contractName")
        != "chummer.release-upload.candidate-import-authority/v3"
        or type(authority.get("contractVersion")) is not int
        or authority.get("contractVersion") != 3
    ):
        raise CutoverError("candidate import authority is not the required v3 contract")
    candidate = authority.get("candidate")
    custody = authority.get("custody")
    if not isinstance(candidate, dict) or not isinstance(custody, dict):
        raise CutoverError("candidate import authority identity is unavailable")
    if (
        type(candidate.get("fileCount")) is not int
        or candidate["fileCount"] <= 0
        or type(candidate.get("totalBytes")) is not int
        or candidate["totalBytes"] <= 0
    ):
        raise CutoverError(
            "candidate import authority count or size is malformed"
        )
    direct_import_raw = stable_regular_bytes(
        config.direct_import_receipt,
        label="sealed direct-import receipt",
        maximum_bytes=4 * 1024 * 1024,
    )
    if sha256_bytes(direct_import_raw) != config.direct_import_receipt_sha256:
        raise CutoverError("direct-import receipt SHA-256 drifted")
    try:
        direct_import = projection_verifier._strict_json_object(
            direct_import_raw,
            label="sealed direct-import receipt",
        )
    except Exception as exc:
        raise CutoverError("direct-import receipt is malformed") from exc
    if (
        authority.get("projectionProfile")
        == SCOPE_BOUND_EXISTING_BYTES_PROFILE
    ):
        return _validate_scope_bound_existing_bytes_candidate(
            config,
            projection_verifier=projection_verifier,
            candidate_materializer=candidate_materializer,
            authority=authority,
            authority_raw=authority_raw,
            candidate=candidate,
            custody=custody,
            direct_import=direct_import,
        )
    direct_import_keys = {
        "compositionRequest",
        "contractName",
        "contractVersion",
        "crossRunBitReproducible",
        "deployAuthorized",
        "hubCandidateImportAuthority",
        "platformScope",
        "publicationAuthorized",
        "registryCandidateReceipt",
        "registryFinalizeAuthority",
        "registryFinalizeReceipt",
        "release",
        "signature",
        "sourceCommits",
        "status",
        "transport",
        "uiScope",
        "uploadAuthorized",
    }
    if (
        set(direct_import) != direct_import_keys
        or direct_import.get("contractName")
        != "chummer6-ui.preview-nightly-unsigned-direct-import"
        or type(direct_import.get("contractVersion")) is not int
        or direct_import.get("contractVersion") != 1
        or direct_import.get("status") != "sealed_review_required"
        or direct_import.get("platformScope") != "windows_only"
        or direct_import.get("crossRunBitReproducible") is not False
        or not _json_semantically_equal(
            direct_import.get("signature"),
            {
                "policy": "preview_policy",
                "required": False,
                "status": "unsigned",
            },
        )
        or any(
            direct_import.get(name) is not False
            for name in (
                "publicationAuthorized",
                "uploadAuthorized",
                "deployAuthorized",
            )
        )
        or not _json_semantically_equal(
            direct_import.get("release"),
            {
                "channel": "preview",
                "version": candidate.get("version"),
            },
        )
        or not _json_semantically_equal(
            direct_import.get("hubCandidateImportAuthority"),
            {
                "path": (
                    "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
                ),
                "sha256": config.candidate_import_authority_sha256,
                "sizeBytes": len(authority_raw),
            },
        )
    ):
        raise CutoverError("direct-import receipt authority posture drifted")

    try:
        inventory_raw = projection_verifier._candidate_embedded_bytes(
            custody.get("inventory"),
            label="candidate upload inventory",
            expected_path="CANDIDATE_UPLOAD_INVENTORY.generated.json",
        )
        inventory = projection_verifier._strict_json_object(
            inventory_raw,
            label="candidate upload inventory",
        )
        (
            release_rows,
            release_modes,
            _release_directory_modes,
            _release_captured,
        ) = candidate_materializer._validate_bundle_inventory(
            config.release_candidate_root,
            inventory,
            candidate,
            allow_root_ancillary_files=True,
        )
        evidence = custody.get("unsignedPublicationEvidence")
        if not isinstance(evidence, dict) or not isinstance(
            evidence.get("files"), list
        ):
            raise CutoverError("candidate unsigned publication evidence is unavailable")
        scope_path = projection_verifier.CANDIDATE_UNSIGNED_SCOPE_FILE
        matching_scope = [
            item
            for item in evidence["files"]
            if isinstance(item, dict) and item.get("path") == scope_path
        ]
        if len(matching_scope) != 1:
            raise CutoverError("candidate unsigned scope custody is ambiguous")
        scope = projection_verifier._strict_json_object(
            scope_raw := projection_verifier._candidate_embedded_bytes(
                matching_scope[0],
                label="candidate unsigned publication scope",
                expected_path=scope_path,
            ),
            label="candidate unsigned publication scope",
        )
        registry_candidate = projection_verifier._strict_json_object(
            registry_candidate_raw := projection_verifier._candidate_embedded_bytes(
                custody.get("registryPrepareCandidateReceipt"),
                label="candidate Registry PREPARE receipt",
                expected_path=(
                    projection_verifier.CANDIDATE_REGISTRY_RECEIPT_FILE
                ),
            ),
            label="candidate Registry PREPARE receipt",
        )
        composition = registry_candidate.get("compositionInputDocument")
        if not isinstance(composition, dict):
            raise CutoverError("candidate incumbent composition is unavailable")
        incumbent_snapshot = composition.get("incumbentSnapshot")
        if not isinstance(incumbent_snapshot, dict):
            raise CutoverError("candidate incumbent snapshot is unavailable")
        (
            incumbent_rows,
            incumbent_modes,
            incumbent_directory_modes,
            _incumbent_captured,
        ) = candidate_materializer._scan_bundle_tree(
            config.migration_candidate_root
        )
    except CutoverError:
        raise
    except Exception as exc:
        raise CutoverError(
            "sealed release bundle custody validation failed"
        ) from exc

    source_commits = direct_import.get("sourceCommits")
    registry_commit = registry_candidate.get("registryCommit")
    ui_commit = scope.get("sourceSha")
    if (
        not isinstance(source_commits, dict)
        or set(source_commits) != {"hub", "registry", "ui"}
        or any(
            COMMIT.fullmatch(str(source_commits.get(name) or "")) is None
            for name in ("hub", "registry", "ui")
        )
        or source_commits.get("hub") != config.source_head
        or source_commits.get("registry") != registry_commit
        or source_commits.get("ui") != ui_commit
    ):
        raise CutoverError(
            "direct-import source commits do not bind Hub, Registry, and UI custody"
        )

    def reference(raw: bytes, path: str) -> dict[str, Any]:
        return {
            "path": path,
            "sha256": sha256_bytes(raw),
            "sizeBytes": len(raw),
        }

    registry_authority_raw = projection_verifier._candidate_embedded_bytes(
        custody.get("registryFinalizeAuthority"),
        label="candidate Registry FINALIZE authority",
        expected_path=projection_verifier.CANDIDATE_REGISTRY_AUTHORITY_FILE,
    )
    registry_finalize_raw = projection_verifier._candidate_embedded_bytes(
        custody.get("registryFinalizeReceipt"),
        label="candidate Registry FINALIZE receipt",
        expected_path=projection_verifier.CANDIDATE_REGISTRY_FINALIZE_FILE,
    )
    composition_raw = (
        json.dumps(composition, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if (
        not _json_semantically_equal(
            direct_import.get("registryCandidateReceipt"),
            reference(
                registry_candidate_raw,
                projection_verifier.CANDIDATE_REGISTRY_RECEIPT_FILE,
            ),
        )
        or not _json_semantically_equal(
            direct_import.get("registryFinalizeAuthority"),
            reference(
                registry_authority_raw,
                projection_verifier.CANDIDATE_REGISTRY_AUTHORITY_FILE,
            ),
        )
        or not _json_semantically_equal(
            direct_import.get("registryFinalizeReceipt"),
            reference(
                registry_finalize_raw,
                projection_verifier.CANDIDATE_REGISTRY_FINALIZE_FILE,
            ),
        )
        or not _json_semantically_equal(
            direct_import.get("compositionRequest"),
            reference(
                composition_raw,
                projection_verifier.CANDIDATE_UNSIGNED_COMPOSITION_FILE,
            ),
        )
        or not _json_semantically_equal(
            direct_import.get("uiScope"),
            reference(scope_raw, scope_path),
        )
    ):
        raise CutoverError(
            "direct-import receipt does not bind embedded Registry/UI custody"
        )

    release_with_modes = [
        {**row, "mode": release_modes[str(row["path"])]}
        for row in release_rows
    ]
    if not _json_semantically_equal(
        release_with_modes,
        scope.get("fullShelfInventory"),
    ):
        raise CutoverError(
            "sealed release bundle modes differ from the v3 authority"
        )
    incumbent_with_modes = [
        {**row, "mode": incumbent_modes[str(row["path"])]}
        for row in incumbent_rows
    ]
    if (
        not _json_semantically_equal(
            incumbent_with_modes,
            incumbent_snapshot.get("fullShelfInventory"),
        )
        or not _json_semantically_equal(
            incumbent_directory_modes,
            incumbent_snapshot.get("directoryModes"),
        )
    ):
        raise CutoverError(
            "v3 authority incumbent snapshot differs from the attested candidate"
        )

    fresh = scope.get("freshDelta")
    expected_fresh = (
        "files/chummer-avalonia-win-x64-installer.exe",
        "files/chummer-avalonia-win-x64-payload.zip",
        "files/chummer-avalonia-win-x64-payload.zip.json",
    )
    if (
        not isinstance(fresh, list)
        or tuple(
            str(item.get("path") or "")
            for item in fresh
            if isinstance(item, dict)
        )
        != expected_fresh
    ):
        raise CutoverError(
            "v3 authority freshDelta is not exactly installer/payload/sidecar"
        )
    fresh_by_path = {
        str(item["path"]): item
        for item in fresh
        if isinstance(item, dict)
    }
    if set(fresh_by_path) != set(expected_fresh):
        raise CutoverError("v3 authority freshDelta path closure drifted")
    release_by_path = {
        str(item["path"]): item for item in release_with_modes
    }
    for path, fresh_row in fresh_by_path.items():
        release_row = release_by_path.get(path)
        if release_row is None or any(
            not _json_semantically_equal(
                fresh_row.get(key),
                release_row.get(key),
            )
            for key in ("mode", "sha256", "sizeBytes")
        ):
            raise CutoverError(
                "v3 authority freshDelta differs from exact sealed bundle bytes"
            )
    incumbent_by_path = {
        str(item["path"]): item for item in incumbent_with_modes
    }
    for path, fresh_row in fresh_by_path.items():
        incumbent_row = incumbent_by_path.get(path)
        if (
            incumbent_row is not None
            and incumbent_row.get("sha256") == fresh_row.get("sha256")
        ):
            raise CutoverError(
                "v3 authority labels an incumbent Windows byte as fresh"
            )

    retained = scope.get("retainedFromIncumbent")
    if not isinstance(retained, list):
        raise CutoverError("v3 authority retained incumbent inventory is unavailable")
    retained_by_path = {
        str(item.get("path") or ""): item
        for item in retained
        if isinstance(item, dict)
    }
    expected_retained_paths = set(incumbent_by_path) - {
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        *expected_fresh,
    }
    if set(retained_by_path) != expected_retained_paths:
        raise CutoverError("v3 authority retained incumbent path closure drifted")
    for path, retained_row in retained_by_path.items():
        incumbent_row = incumbent_by_path[path]
        if any(
            not _json_semantically_equal(
                retained_row.get(key),
                incumbent_row.get(key),
            )
            for key in ("mode", "sha256", "sizeBytes")
        ):
            raise CutoverError("v3 authority retained incumbent bytes drifted")

    canonical_authority_raw = projection_verifier._candidate_embedded_bytes(
        custody.get("canonicalManifest"),
        label="candidate canonical manifest",
        expected_path="RELEASE_CHANNEL.generated.json",
    )
    compatibility_authority_raw = projection_verifier._candidate_embedded_bytes(
        custody.get("compatibilityManifest"),
        label="candidate compatibility manifest",
        expected_path="releases.json",
    )
    canonical_bundle_raw = stable_regular_bytes(
        config.release_candidate_root / "RELEASE_CHANNEL.generated.json",
        label="sealed candidate canonical manifest",
        maximum_bytes=8 * 1024 * 1024,
    )
    compatibility_bundle_raw = stable_regular_bytes(
        config.release_candidate_root / "releases.json",
        label="sealed candidate compatibility manifest",
        maximum_bytes=8 * 1024 * 1024,
    )
    release_receipt_raw = stable_regular_bytes(
        config.release_channel_receipt,
        label="authenticated release-channel receipt",
        maximum_bytes=8 * 1024 * 1024,
    )
    if (
        canonical_bundle_raw != canonical_authority_raw
        or canonical_bundle_raw != release_receipt_raw
        or compatibility_bundle_raw != compatibility_authority_raw
        or sha256_bytes(canonical_bundle_raw)
        != candidate.get("canonicalManifestSha256")
        or sha256_bytes(release_receipt_raw)
        != config.release_channel_receipt_sha256
    ):
        raise CutoverError(
            "release manifest bytes do not share one v3 candidate authority"
        )

    return {
        "path": str(config.candidate_import_authority),
        "sha256": config.candidate_import_authority_sha256,
        "contractName": authority["contractName"],
        "contractVersion": authority["contractVersion"],
        "candidateVersion": candidate["version"],
        "sourceCommits": dict(source_commits),
        "directImportReceipt": {
            "path": str(config.direct_import_receipt),
            "sha256": config.direct_import_receipt_sha256,
        },
        "bundleIdentitySha256": candidate["bundleIdentitySha256"],
        "inventorySha256": candidate["inventorySha256"],
        "fileCount": candidate["fileCount"],
        "totalBytes": candidate["totalBytes"],
        "canonicalManifestSha256": candidate[
            "canonicalManifestSha256"
        ],
        "freshDelta": [
            {
                "path": path,
                "sha256": str(fresh_by_path[path]["sha256"]),
                "sizeBytes": int(fresh_by_path[path]["sizeBytes"]),
            }
            for path in expected_fresh
        ],
        "retainedInventorySha256": evidence[
            "retainedInventorySha256"
        ],
        "incumbentInventorySha256": evidence[
            "incumbentInventorySha256"
        ],
        "servingAuthority": True,
        "validatedAtUtc": utc_now(),
    }


def prepare_sidecar_release_shelf(
    config: SidecarConfig,
    *,
    generation: Any | None = None,
    attestor: Any | None = None,
    projection_verifier: Any | None = None,
    candidate_materializer: Any | None = None,
) -> dict[str, Any]:
    scripts = config.source_root / "scripts"
    generation = generation or load_module(
        scripts / "release_shelf_generation.py",
        f"topology_b_release_generation_{secrets.token_hex(6)}",
    )
    attestor = attestor or load_module(
        scripts / "attest_initial_release_shelf_cutover.py",
        f"topology_b_migration_attestor_{secrets.token_hex(6)}",
    )
    projection_verifier = projection_verifier or load_module(
        scripts / "release/verify_public_projection.py",
        f"topology_b_projection_verifier_{secrets.token_hex(6)}",
    )
    candidate_materializer = candidate_materializer or load_module(
        scripts / "release/materialize_candidate_import_authority.py",
        f"topology_b_candidate_materializer_{secrets.token_hex(6)}",
    )
    _require_digest_file(
        config.migration_authority,
        config.migration_authority_sha256,
        "migration candidate authority",
    )
    restorations = _load_restoration_spec(config)
    candidate_receipt = materialize_incumbent_candidate(
        attestor=attestor,
        shelf_root=config.shelf_root,
        candidate_root=config.migration_candidate_root,
        manifest_closure_restorations=restorations,
    )
    release_validation: dict[str, Any] | None = None
    if getattr(config, "delivery_phase", None) == "windows-preview":
        release_validation = validate_release_candidate_authority(
            config,
            projection_verifier=projection_verifier,
            candidate_materializer=candidate_materializer,
        )
    candidate_generation_id = str(
        (release_validation or {}).get("generationId") or ""
    )
    generation_id = (
        generation.validate_generation_id(candidate_generation_id)
        if candidate_generation_id
        else generation.new_generation_id()
    )
    activation_receipt_id = generation.new_activation_receipt_id()
    authority_validation_root = (
        config.operation_root / "candidate-authority-validation"
    )
    authority_validation = attestor.prepare_public_download_migration(
        config.shelf_root,
        authority_validation_root,
        config.migration_candidate_root,
        config.migration_authority,
        config.migration_authority_sha256,
        config.source_head,
        generation_id,
        activation_receipt_id,
    )
    if release_validation is None:
        release_validation = validate_release_candidate_authority(
            config,
            projection_verifier=projection_verifier,
            candidate_materializer=candidate_materializer,
        )
    prepared = generation.prepare_sidecar_active_layout(
        config.release_candidate_root,
        config.shelf_source,
        generation_id=generation_id,
        activation_receipt_id=activation_receipt_id,
        activated_at=utc_now(),
    )
    pointer = prepared["pointer"]
    generation_root = (
        config.shelf_source
        / generation.GENERATIONS_DIRECTORY
        / generation_id
    )
    receipt = {
        "contractName": "chummer.public-download-sidecar-shelf/v1",
        "status": "pass",
        "sourceHead": config.source_head,
        "incumbentMigrationAuthority": {
            "path": str(config.migration_authority),
            "sha256": config.migration_authority_sha256,
            "candidateInventoryDigest": candidate_receipt[
                "candidateInventoryDigest"
            ],
            "validation": authority_validation,
            "validationSha256": sha256_bytes(
                json.dumps(
                    authority_validation,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ),
            "servingAuthority": False,
        },
        "releaseCandidateAuthority": release_validation,
        "generationId": generation_id,
        "activationReceiptId": activation_receipt_id,
        "inventoryDigest": pointer["inventoryDigest"],
        "pointerSha256": prepared["pointerSha256"],
        "activationCandidateSha256": prepared[
            "activationCandidateSha256"
        ],
        "canonicalMirrorSha256": prepared["canonicalMirrorSha256"],
        "compatibilityMirrorSha256": prepared[
            "compatibilityMirrorSha256"
        ],
        "generationCanonicalSha256": generation.sha256_file(
            generation_root / generation.CANONICAL_MANIFEST
        ),
        "generationCompatibilitySha256": generation.sha256_file(
            generation_root / generation.COMPATIBILITY_MANIFEST
        ),
        "writerPolicy": prepared["writerPolicy"],
        "shelfTreeSha256": tree_sha256_file_stream(
            config.shelf_source,
            label="prepared sidecar release shelf",
        ),
        "generationRoot": str(generation_root),
    }
    write_private_json(
        config.operation_root / "sidecar-shelf-receipt.json",
        receipt,
    )
    return receipt


def _sidecar_compose_environment(
    config: SidecarConfig,
    *,
    dp: Mapping[str, Any],
    app_overlay_sha256: str,
    shelf: Mapping[str, Any],
) -> dict[str, str]:
    values = {
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_FILE": str(
            config.sidecar_certificate
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_FILE": str(
            config.sidecar_certificate_password
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_SHA256": str(
            dp["certificateSha256"]
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_SHA256": str(
            dp["passwordSha256"]
        ),
        "CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR": str(
            config.overlay_staging_root
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256": app_overlay_sha256,
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SOURCE": str(config.fleet_source),
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256": config.fleet_sha256,
        "CHUMMER_PUBLIC_DOWNLOAD_SHELF_SOURCE": str(config.shelf_source),
        "CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256": str(
            shelf["shelfTreeSha256"]
        ),
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": str(
            config.projection_snapshot_root
        ),
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256": (
            config.projection_source_tree_sha256
        ),
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": str(
            config.runtime_proof_source
        ),
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256": (
            config.runtime_proof_sha256
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE": str(
            config.final_gold_source
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256": config.final_gold_sha256,
    }
    for logical, environment_name in SIDECAR_VOLUME_ENVIRONMENT.items():
        values[environment_name] = config.volume_names[logical]
    return values


def materialize_sidecar_compose(
    config: SidecarConfig,
    runner: TopologyBRunner,
    *,
    image_id: str,
    dp: Mapping[str, Any],
    app_overlay_sha256: str,
    shelf: Mapping[str, Any],
) -> dict[str, Any]:
    materializer = (
        config.source_root
        / "scripts/materialize_public_download_only_compose.py"
    )
    validator = (
        config.source_root
        / "scripts/validate_public_download_only_compose_runtime.py"
    )
    runner.python(
        materializer,
        [
            "--source-root",
            str(config.source_root),
            "--source-head",
            config.source_head,
            "--source",
            str(config.source_root / "docker-compose.public-edge.yml"),
            "--profile-source",
            str(config.source_root / "docker-compose.public-downloads.yml"),
            "--output",
            str(config.compose_file),
            "--receipt-output",
            str(config.materialization_receipt),
            "--candidate-image-id",
            image_id,
            "--operation",
            config.operation,
        ],
        label="materialize topology-B Compose",
    )
    environment = _sidecar_compose_environment(
        config,
        dp=dp,
        app_overlay_sha256=app_overlay_sha256,
        shelf=shelf,
    )
    rendered = runner.compose(
        ["config", "--format", "json"],
        environment=environment,
        label="render topology-B Compose",
    )
    validator_arguments = [
        "--project-name",
        config.project_name,
        "--operation-root",
        str(config.operation_root),
        "--operation",
        config.operation,
        "--source-root",
        str(config.source_root),
        "--source-head",
        config.source_head,
        "--materialized-compose",
        str(config.compose_file),
        "--materialization-receipt",
        str(config.materialization_receipt),
        "--candidate-image-id",
        image_id,
        "--shelf-source",
        str(config.shelf_source),
        "--shelf-sha256",
        str(shelf["shelfTreeSha256"]),
        "--certificate-source",
        str(config.sidecar_certificate),
        "--certificate-password-source",
        str(config.sidecar_certificate_password),
        "--certificate-sha256",
        str(dp["certificateSha256"]),
        "--certificate-password-sha256",
        str(dp["passwordSha256"]),
        "--app-overlay-source",
        str(config.overlay_staging_root),
        "--app-overlay-sha256",
        app_overlay_sha256,
        "--fleet-source",
        str(config.fleet_source),
        "--fleet-sha256",
        config.fleet_sha256,
        "--projection-source",
        str(config.projection_snapshot_root),
        "--projection-sha256",
        config.projection_source_tree_sha256,
        "--runtime-proof-source",
        str(config.runtime_proof_source),
        "--runtime-proof-sha256",
        config.runtime_proof_sha256,
        "--final-gold-source",
        str(config.final_gold_source),
        "--final-gold-sha256",
        config.final_gold_sha256,
    ]
    validator_volume_flags = {
        "public-download-app": "--app-volume",
        "public-download-fleet": "--fleet-volume",
        "public-download-state": "--state-volume",
        "public-download-upload-sessions": "--upload-sessions-volume",
        "public-download-windows-proof": "--windows-proof-volume",
        "public-download-windows-proof-upload": (
            "--windows-proof-upload-volume"
        ),
        "public-download-runtime-secrets": "--runtime-secrets-volume",
        "public-download-projection": "--projection-volume",
        "public-download-proofs": "--proofs-volume",
        "public-download-shelf": "--shelf-volume",
    }
    for logical in SIDECAR_LOGICAL_VOLUMES:
        validator_arguments.extend(
            [validator_volume_flags[logical], config.volume_names[logical]]
        )
    validator_arguments.extend(["--output", str(config.runtime_attestation)])
    runner.python(
        validator,
        validator_arguments,
        label="attest topology-B Compose",
        input_bytes=rendered,
    )
    return {
        "projectName": config.project_name,
        "publishedAddress": SIDECAR_ADDRESS,
        "publishedPort": SIDECAR_PORT,
        "candidateImageId": image_id,
        "composePath": str(config.compose_file),
        "materializationReceipt": str(config.materialization_receipt),
        "runtimeAttestation": str(config.runtime_attestation),
        "environment": environment,
        "volumes": dict(config.volume_names),
    }


class TopologyBActions:
    """Concrete, journaled side-effect boundary for the topology-B controller."""

    def __init__(self, config: SidecarConfig) -> None:
        self.config = config
        _validate_sidecar_config(config)
        self.runner = TopologyBRunner(config)
        scripts = config.source_root / "scripts"
        self.generation = load_module(
            scripts / "release_shelf_generation.py",
            f"topology_b_generation_{secrets.token_hex(6)}",
        )
        self.attestor = load_module(
            scripts / "attest_initial_release_shelf_cutover.py",
            f"topology_b_attestor_{secrets.token_hex(6)}",
        )
        self.cloudflare = load_module(
            scripts / "cloudflare_public_download_transaction.py",
            f"topology_b_cloudflare_{secrets.token_hex(6)}",
        )
        self.projection_verifier = load_module(
            scripts / "release/verify_public_projection.py",
            f"topology_b_projection_verifier_{secrets.token_hex(6)}",
        )
        self.candidate_materializer = load_module(
            scripts / "release/materialize_candidate_import_authority.py",
            f"topology_b_candidate_materializer_{secrets.token_hex(6)}",
        )
        self._compose_environment: dict[str, str] = {}
        self._state: dict[str, Any] = {}
        if config.operation == CUTOVER_OPERATION:
            config.operation_root.mkdir(mode=0o700)
            config.operation_root.chmod(0o700)
            private_directory(config.operation_root, create=False)
            planned = {
                "schema": TOPOLOGY_B_OPERATION_SCHEMA,
                "phase": "planned",
                "operation": config.operation,
                "projectName": config.project_name,
                "operationRoot": str(config.operation_root),
                "sourceHead": config.source_head,
                "bindAddress": SIDECAR_ADDRESS,
                "bindPort": SIDECAR_PORT,
                "canonicalProject": CANONICAL_PROJECT,
                "canonicalShelfRoot": str(config.shelf_root),
                "volumes": dict(config.volume_names),
                "createdAtUtc": utc_now(),
                "updatedAtUtc": utc_now(),
                "receipts": {},
                "incumbentBaseline": None,
            }
            write_private_json(config.operation_journal, planned)
            self._state = planned
        else:
            self._state = self._load_operation_journal()

    def _load_operation_journal(self) -> dict[str, Any]:
        raw = stable_regular_bytes(
            self.config.operation_journal,
            label="topology-B operation journal",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RecoveryUncertain(
                "topology-B operation journal is malformed"
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != TOPOLOGY_B_OPERATION_SCHEMA
            or payload.get("projectName") != self.config.project_name
            or payload.get("operationRoot") != str(self.config.operation_root)
            or payload.get("sourceHead") != self.config.source_head
            or payload.get("volumes") != self.config.volume_names
        ):
            raise RecoveryUncertain(
                "topology-B operation journal authority drifted"
            )
        return payload

    def _record(self, phase: str, name: str, receipt: Any) -> None:
        state = copy.deepcopy(self._state)
        state["phase"] = phase
        state["updatedAtUtc"] = utc_now()
        receipts = state.setdefault("receipts", {})
        if not isinstance(receipts, dict):
            raise RecoveryUncertain("topology-B operation receipts are malformed")
        receipts[name] = receipt
        write_private_json(
            self.config.operation_journal,
            state,
            replace=True,
        )
        self._state = state

    def record_primary_failure(
        self,
        _config: SidecarConfig,
        error: Exception,
    ) -> dict[str, Any]:
        state = copy.deepcopy(self._state)
        receipts = state.setdefault("receipts", {})
        if not isinstance(receipts, dict):
            raise RecoveryUncertain("topology-B operation receipts are malformed")
        expected_receipt_fields = {
            "contractName",
            "recordedAtUtc",
            "projectName",
            "sourceHead",
            "command",
        }
        expected_command_fields = {
            "contractName",
            "stage",
            "failureKind",
            "exitStatus",
            "stdoutSha256",
            "stdoutSizeBytes",
            "stderrSha256",
            "stderrSizeBytes",
            "safeStderrSummary",
        }

        def validate_receipt(candidate: Any) -> dict[str, Any]:
            command = (
                candidate.get("command")
                if isinstance(candidate, dict)
                else None
            )
            if (
                not isinstance(candidate, dict)
                or set(candidate) != expected_receipt_fields
                or candidate.get("contractName")
                != "chummer.public-download-primary-failure/v1"
                or candidate.get("projectName") != self.config.project_name
                or candidate.get("sourceHead") != self.config.source_head
                or not isinstance(candidate.get("recordedAtUtc"), str)
                or not isinstance(command, dict)
                or set(command) != expected_command_fields
                or command.get("contractName")
                != "chummer.public-download-command-failure/v1"
                or not isinstance(command.get("stage"), str)
                or not 1 <= len(command["stage"]) <= 160
                or not command["stage"].isprintable()
                or command.get("failureKind")
                not in {
                    "failed",
                    "timed out",
                    "could not execute",
                    "controller exception",
                }
                or (
                    command.get("exitStatus") is not None
                    and (
                        isinstance(command.get("exitStatus"), bool)
                        or not isinstance(command.get("exitStatus"), int)
                        or command["exitStatus"] < 0
                    )
                )
                or SHA256.fullmatch(str(command.get("stdoutSha256") or ""))
                is None
                or SHA256.fullmatch(str(command.get("stderrSha256") or ""))
                is None
                or any(
                    isinstance(command.get(field), bool)
                    or not isinstance(command.get(field), int)
                    or command[field] < 0
                    for field in ("stdoutSizeBytes", "stderrSizeBytes")
                )
                or command.get("safeStderrSummary")
                not in {
                    "stderr was empty",
                    "Compose required-variable validation failed",
                    "Docker daemon connection was unavailable",
                    "stderr content redacted; correlate by SHA-256",
                    (
                        "exception detail redacted; no subprocess stderr "
                        "was captured"
                    ),
                }
            ):
                raise RecoveryUncertain(
                    "topology-B primary failure evidence is malformed"
                )
            return candidate

        existing = receipts.get("primaryFailure")
        if existing is not None:
            return validate_receipt(existing)
        command_failure = _find_command_failure(error)
        if command_failure is not None:
            command = copy.deepcopy(command_failure.evidence)
        else:
            command = {
                "contractName": "chummer.public-download-command-failure/v1",
                "stage": "topology-B controller",
                "failureKind": "controller exception",
                "exitStatus": None,
                "stdoutSha256": sha256_bytes(b""),
                "stdoutSizeBytes": 0,
                "stderrSha256": sha256_bytes(b""),
                "stderrSizeBytes": 0,
                "safeStderrSummary": (
                    "exception detail redacted; no subprocess stderr was captured"
                ),
            }
        receipt = {
            "contractName": "chummer.public-download-primary-failure/v1",
            "recordedAtUtc": utc_now(),
            "projectName": self.config.project_name,
            "sourceHead": self.config.source_head,
            "command": command,
        }
        validate_receipt(receipt)
        receipts["primaryFailure"] = receipt
        state["updatedAtUtc"] = utc_now()
        write_private_json(
            self.config.operation_journal,
            state,
            replace=True,
        )
        self._state = state
        return receipt

    def _assert_canonical_shelf_unchanged(self) -> None:
        expected = self._state.get("canonicalShelfTreeSha256")
        observed = tree_sha256_file_stream(
            self.config.shelf_root,
            label="canonical incumbent release shelf",
        )
        if expected is None:
            self._state["canonicalShelfTreeSha256"] = observed
            write_private_json(
                self.config.operation_journal,
                self._state,
                replace=True,
            )
        elif observed != expected:
            raise CutoverError(
                "canonical incumbent release shelf changed during topology-B cutover"
            )

    def _cloudflare_api(self) -> Any:
        values = _parse_credentials_file(
            self.config.cloudflare_credentials_file
        )
        headers = self.cloudflare.resolve_auth_headers(
            values,
            api_token_env="CLOUDFLARE_API_TOKEN",
            allow_legacy_global_key_auth=True,
            legacy_email_env="CLOUDFLARE_EMAIL",
            legacy_global_key_env="CLOUDFLARE_GLOBAL_API_KEY",
        )
        return self.cloudflare.CloudflareTunnelApi(
            api_base=self.config.cloudflare_api_base,
            account_id=self.config.cloudflare_account_id,
            tunnel_id=self.config.cloudflare_tunnel_id,
            auth_headers=headers,
            timeout_seconds=20,
        )

    def _validated_retirement_baseline(self) -> dict[str, Any]:
        baseline = self._state.get("incumbentBaseline")
        expected_paths = {
            "/downloads/RELEASE_CHANNEL.generated.json",
            "/downloads/releases.json",
        }
        if (
            not isinstance(baseline, dict)
            or set(baseline) != set(SIDECAR_HOSTS)
        ):
            raise RecoveryUncertain(
                "committed topology-B incumbent baseline is incomplete"
            )
        for hostname in SIDECAR_HOSTS:
            observations = baseline.get(hostname)
            if (
                not isinstance(observations, dict)
                or set(observations) != expected_paths
            ):
                raise RecoveryUncertain(
                    "committed topology-B incumbent path closure drifted"
                )
            for path in sorted(expected_paths):
                observation = observations.get(path)
                if (
                    not isinstance(observation, dict)
                    or set(observation)
                    != {"httpStatus", "bodySha256", "sizeBytes"}
                    or type(observation.get("httpStatus")) is not int
                    or observation["httpStatus"] != 200
                    or SHA256.fullmatch(
                        str(observation.get("bodySha256") or "")
                    )
                    is None
                    or type(observation.get("sizeBytes")) is not int
                    or observation["sizeBytes"] <= 0
                ):
                    raise RecoveryUncertain(
                        "committed topology-B incumbent observation is invalid"
                    )
        return copy.deepcopy(baseline)

    def _load_retirement_authority(
        self,
        config: SidecarConfig,
    ) -> tuple[bytes, dict[str, Any], Path]:
        active_present = (
            config.active_runtime_authority.exists()
            or config.active_runtime_authority.is_symlink()
        )
        retired_present = (
            config.retired_active_authority.exists()
            or config.retired_active_authority.is_symlink()
        )
        if active_present and retired_present:
            raise RecoveryUncertain(
                "active and retired topology-B authorities both exist"
            )
        if not active_present and not retired_present:
            raise RecoveryUncertain(
                "topology-B retirement authority is unavailable"
            )
        path = (
            config.active_runtime_authority
            if active_present
            else config.retired_active_authority
        )
        raw = stable_regular_bytes(
            path,
            label="topology-B runtime authority",
            maximum_bytes=1024 * 1024,
            owner_only=True,
        )
        payload = _strict_json_object_bytes(
            raw,
            label="topology-B runtime authority",
        )
        expected_fields = {
            "schema",
            "status",
            "operation",
            "operationRoot",
            "projectName",
            "sourceHead",
            "origin",
            "publicHosts",
            "generationId",
            "shelfTreeSha256",
            "candidateImageId",
            "portalContainerId",
            "volumes",
            "finalGoldDiagnostic",
            "cloudflare",
            "activatedAtUtc",
        }
        final_gold = payload.get("finalGoldDiagnostic")
        cloudflare_summary = payload.get("cloudflare")
        if (
            set(payload) != expected_fields
            or payload.get("schema") != TOPOLOGY_B_ACTIVE_SCHEMA
            or payload.get("status") != "active"
            or payload.get("operation") != CUTOVER_OPERATION
            or payload.get("operationRoot") != str(config.operation_root)
            or payload.get("projectName") != config.project_name
            or payload.get("sourceHead") != config.source_head
            or payload.get("origin") != SIDECAR_ORIGIN
            or payload.get("publicHosts") != list(SIDECAR_HOSTS)
            or SHA256.fullmatch(
                str(payload.get("shelfTreeSha256") or "")
            )
            is None
            or IMAGE_ID.fullmatch(
                str(payload.get("candidateImageId") or "")
            )
            is None
            or CONTAINER_ID.fullmatch(
                str(payload.get("portalContainerId") or "")
            )
            is None
            or payload.get("volumes") != config.volume_names
            or not isinstance(payload.get("activatedAtUtc"), str)
            or not isinstance(final_gold, dict)
            or set(final_gold) != {"path", "sha256", "authority"}
            or not isinstance(final_gold.get("path"), str)
            or SHA256.fullmatch(str(final_gold.get("sha256") or ""))
            is None
            or final_gold.get("authority")
            != "diagnostic-only-not-release-completion"
            or not isinstance(cloudflare_summary, dict)
            or set(cloudflare_summary)
            != {
                "phase",
                "targetConfigSha256",
                "targetVersion",
                "evidencePath",
                "evidenceSha256",
            }
            or cloudflare_summary.get("phase") != "committed"
            or SHA256.fullmatch(
                str(cloudflare_summary.get("targetConfigSha256") or "")
            )
            is None
            or type(cloudflare_summary.get("targetVersion")) is not int
            or cloudflare_summary["targetVersion"] < 0
            or cloudflare_summary.get("evidencePath")
            != str(config.cloudflare_committed_evidence)
            or SHA256.fullmatch(
                str(cloudflare_summary.get("evidenceSha256") or "")
            )
            is None
        ):
            raise RecoveryUncertain(
                "topology-B runtime authority is malformed"
            )
        try:
            self.cloudflare.validate_generation_id(payload.get("generationId"))
        except Exception as exc:
            raise RecoveryUncertain(
                "topology-B runtime generation identity is invalid"
            ) from exc
        recorded = self._state.get("receipts", {}).get("activeAuthority")
        if not _json_semantically_equal(recorded, payload):
            raise RecoveryUncertain(
                "topology-B active authority differs from its operation journal"
            )
        return raw, payload, path

    def _load_committed_retirement_evidence(
        self,
        config: SidecarConfig,
        active: Mapping[str, Any],
    ) -> tuple[bytes, dict[str, Any]]:
        evidence_raw = stable_regular_bytes(
            config.cloudflare_committed_evidence,
            label="committed Cloudflare evidence",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        try:
            evidence = self.cloudflare.load_journal(
                config.cloudflare_committed_evidence
            )
        except Exception as exc:
            raise RecoveryUncertain(
                "terminal committed Cloudflare evidence is invalid"
            ) from exc
        summary = active.get("cloudflare")
        if (
            evidence.get("phase") != "committed"
            or evidence.get("accountId") != config.cloudflare_account_id
            or evidence.get("tunnelId") != config.cloudflare_tunnel_id
            or evidence.get("origin") != SIDECAR_ORIGIN
            or evidence.get("generationId") != active.get("generationId")
            or not isinstance(summary, Mapping)
            or evidence.get("targetConfigSha256")
            != summary.get("targetConfigSha256")
            or evidence.get("targetVersion") != summary.get("targetVersion")
            or summary.get("evidenceSha256")
            != sha256_bytes(evidence_raw)
            or self.cloudflare.canonical_sha256(evidence["priorConfig"])
            != evidence.get("priorConfigSha256")
        ):
            raise RecoveryUncertain(
                "committed Cloudflare evidence is not the active target"
            )
        return evidence_raw, evidence

    def authorize_committed_retirement(
        self,
        config: SidecarConfig,
        *_args: Any,
    ) -> dict[str, Any]:
        if config.operation != RETIRE_OPERATION:
            raise RecoveryUncertain(
                "committed retirement requires the explicit retirement operation"
            )
        if (
            self._state.get("operation") != CUTOVER_OPERATION
            or self._state.get("phase") not in {
                "active",
                "retirement-authorized",
                "retirement-cloudflare-restored",
                "retirement-incumbent-verified",
                "retirement-evidence-committed",
                "retirement-restoration-connectors-reverified",
                "retirement-connectors-verified",
                "retirement-post-marker-connectors-verified",
                "retirement-connectors-reverified",
                "retirement-authority-retired",
                "cleaned",
                "retired",
            }
        ):
            raise RecoveryUncertain(
                "topology-B operation is not a committed active transition"
            )
        authority_raw, active, _authority_path = (
            self._load_retirement_authority(config)
        )
        evidence_raw, evidence = self._load_committed_retirement_evidence(
            config,
            active,
        )
        baseline = self._validated_retirement_baseline()
        receipts = self._state.get("receipts")
        if not isinstance(receipts, dict):
            raise RecoveryUncertain(
                "topology-B operation receipts are malformed"
            )
        controller_source_head = (
            config.controller_source_head or config.source_head
        )
        expected = {
            "contractName": (
                "chummer.public-download-committed-retirement-authorization/v1"
            ),
            "operation": RETIRE_OPERATION,
            "operationRoot": str(config.operation_root),
            "projectName": config.project_name,
            "operationSourceHead": config.source_head,
            "controllerSourceHead": controller_source_head,
            "activeAuthorityPath": str(config.active_runtime_authority),
            "activeAuthoritySha256": sha256_bytes(authority_raw),
            "committedEvidencePath": str(
                config.cloudflare_committed_evidence
            ),
            "committedEvidenceSha256": sha256_bytes(evidence_raw),
            "targetConfigSha256": evidence["targetConfigSha256"],
            "targetVersion": evidence["targetVersion"],
            "priorConfigSha256": evidence["priorConfigSha256"],
            "priorVersion": evidence["priorVersion"],
            "incumbentBaselineSha256": (
                self.cloudflare.canonical_sha256(baseline)
            ),
        }
        existing = receipts.get("retirementAuthorization")
        if existing is not None:
            if (
                not isinstance(existing, dict)
                or set(existing) != {*expected, "authorizedAtUtc"}
                or any(existing.get(key) != value for key, value in expected.items())
                or not isinstance(existing.get("authorizedAtUtc"), str)
            ):
                raise RecoveryUncertain(
                    "topology-B retirement authorization drifted"
                )
            authorization = copy.deepcopy(existing)
        else:
            if config.retired_active_authority.exists():
                raise RecoveryUncertain(
                    "retired authority exists without durable authorization"
                )
            authorization = {
                **expected,
                "authorizedAtUtc": utc_now(),
            }
        api = self._cloudflare_api()
        try:
            with self.cloudflare.ExclusiveFileLock(config.cloudflare_lock):
                current = self.cloudflare.parse_configuration_response(
                    api.get_configuration()
                )
                target_matches = (
                    current.sha256 == evidence["targetConfigSha256"]
                    and current.version == evidence["targetVersion"]
                )
                prior_matches = (
                    current.sha256 == evidence["priorConfigSha256"]
                )
                if existing is None and not target_matches:
                    raise RecoveryUncertain(
                        "live Cloudflare config is not the committed target"
                    )
                if existing is not None and not (
                    target_matches or prior_matches
                ):
                    raise RecoveryUncertain(
                        "live Cloudflare config left the authorized retirement boundary"
                    )
                if existing is None:
                    self._record(
                        "retirement-authorized",
                        "retirementAuthorization",
                        authorization,
                    )
        except RecoveryUncertain:
            raise
        except Exception as exc:
            raise RecoveryUncertain(
                "committed retirement authorization could not verify Cloudflare"
            ) from exc
        return authorization

    def restore_committed_prior(
        self,
        config: SidecarConfig,
        authorization: Mapping[str, Any],
        *_args: Any,
    ) -> dict[str, Any]:
        receipts = self._state.get("receipts")
        if (
            not isinstance(receipts, dict)
            or receipts.get("retirementAuthorization") != authorization
        ):
            raise RecoveryUncertain(
                "durable retirement authorization is unavailable"
            )
        _authority_raw, active, _authority_path = (
            self._load_retirement_authority(config)
        )
        _evidence_raw, evidence = self._load_committed_retirement_evidence(
            config,
            active,
        )
        existing = receipts.get("cloudflareRetirement")
        expected_fields = {
            "contractName",
            "phase",
            "operationRoot",
            "targetConfigSha256",
            "targetVersion",
            "priorConfigSha256",
            "restoredVersion",
            "restoredResponseSha256",
            "connectorConvergence",
            "restoredAtUtc",
            "connectorsVerifiedAtUtc",
        }
        if existing is not None and (
            not isinstance(existing, dict)
            or set(existing) != expected_fields
            or existing.get("contractName")
            != "chummer.public-download-cloudflare-retirement/v1"
            or existing.get("phase") != "restored"
            or existing.get("operationRoot") != str(config.operation_root)
            or existing.get("targetConfigSha256")
            != evidence["targetConfigSha256"]
            or existing.get("targetVersion") != evidence["targetVersion"]
            or existing.get("priorConfigSha256")
            != evidence["priorConfigSha256"]
            or type(existing.get("restoredVersion")) is not int
            or existing["restoredVersion"] < 0
            or SHA256.fullmatch(
                str(existing.get("restoredResponseSha256") or "")
            )
            is None
            or not isinstance(existing.get("restoredAtUtc"), str)
            or not isinstance(
                existing.get("connectorsVerifiedAtUtc"),
                str,
            )
        ):
            raise RecoveryUncertain(
                "Cloudflare retirement restoration receipt drifted"
            )
        if existing is not None:
            try:
                validated_connectors = (
                    self.cloudflare
                    .validate_current_connector_convergence_receipt(
                        existing.get("connectorConvergence")
                    )
                )
            except Exception as exc:
                raise RecoveryUncertain(
                    "Cloudflare retirement connector receipt drifted"
                ) from exc
            if (
                validated_connectors.get("targetVersion")
                != existing["restoredVersion"]
            ):
                raise RecoveryUncertain(
                    "Cloudflare retirement connector version drifted"
                )
        api = self._cloudflare_api()
        try:
            with self.cloudflare.ExclusiveFileLock(config.cloudflare_lock):
                current = self.cloudflare.parse_configuration_response(
                    api.get_configuration()
                )
                if existing is not None:
                    if (
                        current.sha256 != evidence["priorConfigSha256"]
                        or current.version != existing["restoredVersion"]
                    ):
                        raise RecoveryUncertain(
                            "restored Cloudflare configuration drifted"
                        )
                    restored = current
                    converged = current
                else:
                    target_matches = (
                        current.sha256 == evidence["targetConfigSha256"]
                        and current.version == evidence["targetVersion"]
                    )
                    if target_matches:
                        restored = (
                            self.cloudflare
                            ._configuration_after_put_or_reget(
                                api,
                                config=evidence["priorConfig"],
                                expected_sha256=evidence[
                                    "priorConfigSha256"
                                ],
                                fallback_sha256=evidence[
                                    "targetConfigSha256"
                                ],
                                fallback_version=evidence[
                                    "targetVersion"
                                ],
                            )
                        )
                    elif (
                        current.sha256
                        == evidence["priorConfigSha256"]
                    ):
                        # A prior attempt may have completed the PUT before
                        # its response or local receipt became durable.
                        restored = current
                    else:
                        raise RecoveryUncertain(
                            "Cloudflare target drifted before retirement PUT"
                        )
                    converged = self.cloudflare.poll_configuration(
                        api,
                        expected_sha256=evidence[
                            "priorConfigSha256"
                        ],
                        expected_version=restored.version,
                        transitional=[
                            (
                                evidence["targetConfigSha256"],
                                evidence["targetVersion"],
                            )
                        ],
                        attempts=30,
                        sleep_fn=time.sleep,
                        interval_seconds=2.0,
                    )
                connector_convergence = (
                    self.cloudflare.poll_current_connector_convergence(
                        api,
                        restored.version,
                        attempts=30,
                        sleep_fn=time.sleep,
                        interval_seconds=2.0,
                    )
                )
                receipt = {
                    "contractName": (
                        "chummer.public-download-cloudflare-retirement/v1"
                    ),
                    "phase": "restored",
                    "operationRoot": str(config.operation_root),
                    "targetConfigSha256": evidence[
                        "targetConfigSha256"
                    ],
                    "targetVersion": evidence["targetVersion"],
                    "priorConfigSha256": evidence[
                        "priorConfigSha256"
                    ],
                    "restoredVersion": restored.version,
                    "restoredResponseSha256": (
                        self.cloudflare.canonical_sha256(
                            converged.response
                        )
                    ),
                    "connectorConvergence": connector_convergence,
                    "restoredAtUtc": (
                        existing["restoredAtUtc"]
                        if existing is not None
                        else utc_now()
                    ),
                    "connectorsVerifiedAtUtc": utc_now(),
                }
                if existing is not None:
                    self._record(
                        "retirement-restoration-connectors-reverified",
                        "retirementRestorationConnectorResumeGate",
                        connector_convergence,
                    )
                    return copy.deepcopy(existing)
                self._record(
                    "retirement-cloudflare-restored",
                    "cloudflareRetirement",
                    receipt,
                )
                return receipt
        except RecoveryUncertain:
            raise
        except Exception as exc:
            raise RecoveryUncertain(
                "exact committed Cloudflare prior restoration is uncertain"
            ) from exc

    def commit_retirement_evidence(
        self,
        config: SidecarConfig,
        authorization: Mapping[str, Any],
        restoration: Mapping[str, Any],
        incumbent: Mapping[str, Any],
        *_args: Any,
    ) -> dict[str, Any]:
        baseline = self._validated_retirement_baseline()
        if not _json_semantically_equal(incumbent, baseline):
            raise RecoveryUncertain(
                "retirement incumbent observation differs from its baseline"
            )
        receipts = self._state.get("receipts")
        if (
            not isinstance(receipts, dict)
            or receipts.get("retirementAuthorization") != authorization
            or receipts.get("cloudflareRetirement") != restoration
            or receipts.get("incumbentAfterRetirement") != incumbent
        ):
            raise RecoveryUncertain(
                "retirement proof inputs are not durably journaled"
            )
        _authority_raw, active, _authority_path = (
            self._load_retirement_authority(config)
        )
        _committed_raw, committed = (
            self._load_committed_retirement_evidence(config, active)
        )
        if (
            restoration.get("priorConfigSha256")
            != committed["priorConfigSha256"]
            or type(restoration.get("restoredVersion")) is not int
        ):
            raise RecoveryUncertain(
                "retirement restoration is not bound to committed evidence"
            )
        try:
            connector_convergence = (
                self.cloudflare
                .validate_current_connector_convergence_receipt(
                    restoration.get("connectorConvergence")
                )
            )
        except Exception as exc:
            raise RecoveryUncertain(
                "retirement restoration connector evidence is invalid"
            ) from exc
        if (
            connector_convergence.get("targetVersion")
            != restoration["restoredVersion"]
        ):
            raise RecoveryUncertain(
                "retirement restoration connector target drifted"
            )
        connector_convergence_sha256 = (
            self.cloudflare.canonical_sha256(
                connector_convergence
            )
        )
        api = self._cloudflare_api()
        try:
            with self.cloudflare.ExclusiveFileLock(config.cloudflare_lock):
                current = self.cloudflare.parse_configuration_response(
                    api.get_configuration()
                )
                if (
                    current.sha256 != committed["priorConfigSha256"]
                    or current.version != restoration["restoredVersion"]
                ):
                    raise RecoveryUncertain(
                        "Cloudflare prior config drifted before retirement proof"
                    )
                expected = {
                    "contractName": (
                        "chummer.public-download-committed-retirement-evidence/v1"
                    ),
                    "status": "committed",
                    "operation": RETIRE_OPERATION,
                    "operationRoot": str(config.operation_root),
                    "projectName": config.project_name,
                    "operationSourceHead": config.source_head,
                    "controllerSourceHead": (
                        config.controller_source_head or config.source_head
                    ),
                    "authorizationSha256": (
                        self.cloudflare.canonical_sha256(authorization)
                    ),
                    "restorationSha256": (
                        self.cloudflare.canonical_sha256(restoration)
                    ),
                    "connectorConvergenceSha256": (
                        connector_convergence_sha256
                    ),
                    "targetConfigSha256": committed[
                        "targetConfigSha256"
                    ],
                    "targetVersion": committed["targetVersion"],
                    "priorConfigSha256": committed[
                        "priorConfigSha256"
                    ],
                    "restoredVersion": restoration["restoredVersion"],
                    "incumbentBaselineSha256": (
                        self.cloudflare.canonical_sha256(baseline)
                    ),
                    "incumbentObservationSha256": (
                        self.cloudflare.canonical_sha256(incumbent)
                    ),
                    "incumbent": copy.deepcopy(dict(incumbent)),
                }
                evidence_present = (
                    config.cloudflare_retirement_evidence.exists()
                    or config.cloudflare_retirement_evidence.is_symlink()
                )
                if evidence_present:
                    raw = stable_regular_bytes(
                        config.cloudflare_retirement_evidence,
                        label="Cloudflare retirement evidence",
                        maximum_bytes=16 * 1024 * 1024,
                        owner_only=True,
                    )
                    evidence = _strict_json_object_bytes(
                        raw,
                        label="Cloudflare retirement evidence",
                    )
                    if (
                        set(evidence) != {*expected, "committedAtUtc"}
                        or any(
                            not _json_semantically_equal(
                                evidence.get(key),
                                value,
                            )
                            for key, value in expected.items()
                        )
                        or not isinstance(
                            evidence.get("committedAtUtc"),
                            str,
                        )
                    ):
                        raise RecoveryUncertain(
                            "Cloudflare retirement evidence drifted"
                        )
                else:
                    evidence = {
                        **expected,
                        "committedAtUtc": utc_now(),
                    }
                    write_private_json(
                        config.cloudflare_retirement_evidence,
                        evidence,
                    )
                    raw = stable_regular_bytes(
                        config.cloudflare_retirement_evidence,
                        label="Cloudflare retirement evidence",
                        maximum_bytes=16 * 1024 * 1024,
                        owner_only=True,
                    )
        except RecoveryUncertain:
            raise
        except Exception as exc:
            raise RecoveryUncertain(
                "retirement evidence could not verify exact Cloudflare prior"
            ) from exc
        summary = {
            "contractName": (
                "chummer.public-download-retirement-evidence-summary/v1"
            ),
            "status": "committed",
            "evidencePath": str(config.cloudflare_retirement_evidence),
            "evidenceSha256": sha256_bytes(raw),
            "priorConfigSha256": committed["priorConfigSha256"],
            "restoredVersion": restoration["restoredVersion"],
            "connectorConvergenceSha256": (
                connector_convergence_sha256
            ),
            "incumbentBaselineSha256": (
                self.cloudflare.canonical_sha256(baseline)
            ),
        }
        existing_summary = receipts.get("retirementEvidence")
        if existing_summary is not None and existing_summary != summary:
            raise RecoveryUncertain(
                "retirement evidence summary drifted"
            )
        self._record(
            "retirement-evidence-committed",
            "retirementEvidence",
            summary,
        )
        return summary

    @staticmethod
    def _fsync_directory(path: Path) -> None:
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

    def retire_active_authority(
        self,
        config: SidecarConfig,
        authorization: Mapping[str, Any],
        restoration: Mapping[str, Any],
        retirement_evidence: Mapping[str, Any],
        *_args: Any,
    ) -> dict[str, Any]:
        receipts = self._state.get("receipts")
        if (
            not isinstance(receipts, dict)
            or receipts.get("retirementAuthorization") != authorization
            or receipts.get("cloudflareRetirement") != restoration
            or receipts.get("retirementEvidence") != retirement_evidence
        ):
            raise RecoveryUncertain(
                "authority retirement lacks durable proof"
            )
        evidence_raw = stable_regular_bytes(
            config.cloudflare_retirement_evidence,
            label="Cloudflare retirement evidence",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        if sha256_bytes(evidence_raw) != retirement_evidence.get(
            "evidenceSha256"
        ):
            raise RecoveryUncertain(
                "authority retirement evidence digest drifted"
            )
        authority_raw, _active, authority_path = (
            self._load_retirement_authority(config)
        )
        if sha256_bytes(authority_raw) != authorization.get(
            "activeAuthoritySha256"
        ):
            raise RecoveryUncertain(
                "runtime authority changed after retirement authorization"
            )
        private_directory(
            config.active_runtime_authority.parent,
            create=False,
        )
        private_directory(config.operation_root, create=False)
        source_parent = config.active_runtime_authority.parent.lstat()
        destination_parent = config.operation_root.lstat()
        if source_parent.st_dev != destination_parent.st_dev:
            raise RecoveryUncertain(
                "runtime authority retirement is not on one filesystem"
            )
        existing_receipt = receipts.get("retiredAuthority")
        if (
            existing_receipt is not None
            and authority_path == config.active_runtime_authority
        ):
            raise RecoveryUncertain(
                "retired authority journal contradicts the active marker"
            )
        marker_connector_gate: dict[str, Any] | None = None
        if authority_path == config.retired_active_authority:
            recorded_gate = receipts.get("retirementConnectorGate")
            try:
                marker_connector_gate = copy.deepcopy(
                    self.cloudflare
                    .validate_current_connector_convergence_receipt(
                        recorded_gate
                    )
                )
            except Exception as exc:
                raise RecoveryUncertain(
                    "retired authority lacks its connector-set gate"
                ) from exc
            if (
                marker_connector_gate.get("targetVersion")
                != restoration.get("restoredVersion")
            ):
                raise RecoveryUncertain(
                    "retired authority connector gate version drifted"
                )
        api = self._cloudflare_api()
        try:
            with self.cloudflare.ExclusiveFileLock(config.cloudflare_lock):
                current = self.cloudflare.parse_configuration_response(
                    api.get_configuration()
                )
                if (
                    current.sha256
                    != retirement_evidence.get("priorConfigSha256")
                    or current.version
                    != retirement_evidence.get("restoredVersion")
                ):
                    raise RecoveryUncertain(
                        "Cloudflare prior config drifted before authority retirement"
                    )
                if authority_path == config.active_runtime_authority:
                    marker_connector_gate = (
                        self.cloudflare
                        .poll_current_connector_convergence(
                            api,
                            current.version,
                            attempts=30,
                            sleep_fn=time.sleep,
                            interval_seconds=2.0,
                        )
                    )
                    self._record(
                        "retirement-connectors-verified",
                        "retirementConnectorGate",
                        marker_connector_gate,
                    )
                    if (
                        config.retired_active_authority.exists()
                        or config.retired_active_authority.is_symlink()
                    ):
                        raise RecoveryUncertain(
                            "retired authority destination already exists"
                        )
                    os.replace(
                        config.active_runtime_authority,
                        config.retired_active_authority,
                    )
                    self._fsync_directory(
                        config.active_runtime_authority.parent
                    )
                    self._fsync_directory(config.operation_root)
                    disposition = "atomically-retired"
                else:
                    disposition = "already-atomically-retired"
        except RecoveryUncertain:
            raise
        except Exception as exc:
            raise RecoveryUncertain(
                "active topology-B authority retirement is uncertain"
            ) from exc
        retired_raw = stable_regular_bytes(
            config.retired_active_authority,
            label="retired topology-B runtime authority",
            maximum_bytes=1024 * 1024,
            owner_only=True,
        )
        if (
            sha256_bytes(retired_raw)
            != authorization["activeAuthoritySha256"]
            or config.active_runtime_authority.exists()
            or config.active_runtime_authority.is_symlink()
        ):
            raise RecoveryUncertain(
                "atomic topology-B authority retirement was not exact"
            )
        if marker_connector_gate is None:
            raise RecoveryUncertain(
                "atomic topology-B authority retirement lacks connector proof"
            )
        connector_gate_sha256 = self.cloudflare.canonical_sha256(
            marker_connector_gate
        )
        if existing_receipt is not None:
            expected_existing = {
                "contractName": (
                    "chummer.public-download-retired-authority/v1"
                ),
                "status": "retired",
                "activeAuthorityPath": str(
                    config.active_runtime_authority
                ),
                "retiredAuthorityPath": str(
                    config.retired_active_authority
                ),
                "activeAuthoritySha256": sha256_bytes(retired_raw),
                "retirementEvidenceSha256": sha256_bytes(evidence_raw),
                "connectorGateSha256": connector_gate_sha256,
            }
            if (
                not isinstance(existing_receipt, dict)
                or set(existing_receipt)
                != {*expected_existing, "disposition", "retiredAtUtc"}
                or any(
                    existing_receipt.get(key) != value
                    for key, value in expected_existing.items()
                )
                or existing_receipt.get("disposition")
                not in {
                    "atomically-retired",
                    "already-atomically-retired",
                }
                or not isinstance(
                    existing_receipt.get("retiredAtUtc"),
                    str,
                )
            ):
                raise RecoveryUncertain(
                    "retired authority receipt drifted"
                )
            return copy.deepcopy(existing_receipt)
        receipt = {
            "contractName": (
                "chummer.public-download-retired-authority/v1"
            ),
            "status": "retired",
            "activeAuthorityPath": str(
                config.active_runtime_authority
            ),
            "retiredAuthorityPath": str(
                config.retired_active_authority
            ),
            "activeAuthoritySha256": sha256_bytes(retired_raw),
            "retirementEvidenceSha256": sha256_bytes(evidence_raw),
            "connectorGateSha256": connector_gate_sha256,
            "disposition": disposition,
            "retiredAtUtc": utc_now(),
        }
        self._record(
            "retirement-authority-retired",
            "retiredAuthority",
            receipt,
        )
        return receipt

    def _validated_retirement_connector_boundary(
        self,
        value: Any,
        *,
        config: SidecarConfig,
        boundary: str,
        restored_version: int,
        retired_authority_sha256: str,
        marker_connector_gate_sha256: str,
    ) -> dict[str, Any]:
        expected_fields = {
            "contractName",
            "status",
            "boundary",
            "operationRoot",
            "restoredVersion",
            "retiredAuthoritySha256",
            "markerConnectorGateSha256",
            "connectorConvergence",
            "connectorConvergenceSha256",
            "verifiedAtUtc",
        }
        if (
            not isinstance(value, dict)
            or set(value) != expected_fields
            or value.get("contractName")
            != (
                "chummer.public-download-retirement-"
                "connector-boundary/v1"
            )
            or value.get("status") != "pass"
            or value.get("boundary") != boundary
            or value.get("operationRoot") != str(config.operation_root)
            or value.get("restoredVersion") != restored_version
            or value.get("retiredAuthoritySha256")
            != retired_authority_sha256
            or value.get("markerConnectorGateSha256")
            != marker_connector_gate_sha256
            or not isinstance(value.get("verifiedAtUtc"), str)
        ):
            raise RecoveryUncertain(
                "retirement connector boundary receipt drifted"
            )
        try:
            convergence = (
                self.cloudflare
                .validate_current_connector_convergence_receipt(
                    value.get("connectorConvergence")
                )
            )
        except Exception as exc:
            raise RecoveryUncertain(
                "retirement connector boundary convergence drifted"
            ) from exc
        if (
            convergence.get("targetVersion") != restored_version
            or self.cloudflare.canonical_sha256(convergence)
            != value.get("connectorConvergenceSha256")
        ):
            raise RecoveryUncertain(
                "retirement connector boundary version drifted"
            )
        return value

    def verify_retired_authority_connectors(
        self,
        config: SidecarConfig,
        authorization: Mapping[str, Any],
        restoration: Mapping[str, Any],
        retirement_evidence: Mapping[str, Any],
        retired_authority: Mapping[str, Any],
        *_args: Any,
    ) -> dict[str, Any]:
        receipts = self._state.get("receipts")
        if (
            not isinstance(receipts, dict)
            or receipts.get("retirementAuthorization") != authorization
            or receipts.get("cloudflareRetirement") != restoration
            or receipts.get("retirementEvidence") != retirement_evidence
            or receipts.get("retiredAuthority") != retired_authority
            or config.active_runtime_authority.exists()
            or config.active_runtime_authority.is_symlink()
        ):
            raise RecoveryUncertain(
                "post-marker connector verification lacks durable proof"
            )
        retired_raw, _active, retired_path = (
            self._load_retirement_authority(config)
        )
        retired_authority_sha256 = sha256_bytes(retired_raw)
        if (
            retired_path != config.retired_active_authority
            or retired_authority_sha256
            != authorization.get("activeAuthoritySha256")
            or retired_authority.get("activeAuthoritySha256")
            != retired_authority_sha256
        ):
            raise RecoveryUncertain(
                "post-marker connector verification lacks retired authority"
            )
        try:
            marker_connector_gate = (
                self.cloudflare
                .validate_current_connector_convergence_receipt(
                    receipts.get("retirementConnectorGate")
                )
            )
        except Exception as exc:
            raise RecoveryUncertain(
                "post-marker connector verification lacks marker proof"
            ) from exc
        restored_version = restoration.get("restoredVersion")
        marker_connector_gate_sha256 = (
            self.cloudflare.canonical_sha256(marker_connector_gate)
        )
        if (
            type(restored_version) is not int
            or restored_version < 0
            or marker_connector_gate.get("targetVersion")
            != restored_version
            or retired_authority.get("connectorGateSha256")
            != marker_connector_gate_sha256
        ):
            raise RecoveryUncertain(
                "post-marker connector verification binding drifted"
            )
        existing_post_marker = receipts.get(
            "retirementPostMarkerConnectorGate"
        )
        if existing_post_marker is not None:
            self._validated_retirement_connector_boundary(
                existing_post_marker,
                config=config,
                boundary="post-marker",
                restored_version=restored_version,
                retired_authority_sha256=retired_authority_sha256,
                marker_connector_gate_sha256=(
                    marker_connector_gate_sha256
                ),
            )
        existing_resume = receipts.get("retirementConnectorResumeGate")
        if existing_resume is not None:
            if existing_post_marker is None:
                raise RecoveryUncertain(
                    "resume connector proof predates post-marker proof"
                )
            self._validated_retirement_connector_boundary(
                existing_resume,
                config=config,
                boundary="resume-post-marker",
                restored_version=restored_version,
                retired_authority_sha256=retired_authority_sha256,
                marker_connector_gate_sha256=(
                    marker_connector_gate_sha256
                ),
            )
        api = self._cloudflare_api()
        try:
            with self.cloudflare.ExclusiveFileLock(
                config.cloudflare_lock
            ):
                current = self.cloudflare.parse_configuration_response(
                    api.get_configuration()
                )
                if (
                    current.sha256
                    != retirement_evidence.get("priorConfigSha256")
                    or current.version != restored_version
                ):
                    raise RecoveryUncertain(
                        "Cloudflare prior config drifted after authority "
                        "retirement"
                    )
                convergence = (
                    self.cloudflare
                    .poll_current_connector_convergence(
                        api,
                        current.version,
                        attempts=30,
                        sleep_fn=time.sleep,
                        interval_seconds=2.0,
                    )
                )
        except RecoveryUncertain:
            raise
        except Exception as exc:
            raise RecoveryUncertain(
                "post-marker connector verification is uncertain"
            ) from exc
        boundary = (
            "post-marker"
            if existing_post_marker is None
            else "resume-post-marker"
        )
        receipt = {
            "contractName": (
                "chummer.public-download-retirement-"
                "connector-boundary/v1"
            ),
            "status": "pass",
            "boundary": boundary,
            "operationRoot": str(config.operation_root),
            "restoredVersion": restored_version,
            "retiredAuthoritySha256": retired_authority_sha256,
            "markerConnectorGateSha256": (
                marker_connector_gate_sha256
            ),
            "connectorConvergence": convergence,
            "connectorConvergenceSha256": (
                self.cloudflare.canonical_sha256(convergence)
            ),
            "verifiedAtUtc": utc_now(),
        }
        try:
            if existing_post_marker is None:
                self._record(
                    "retirement-post-marker-connectors-verified",
                    "retirementPostMarkerConnectorGate",
                    receipt,
                )
            else:
                self._record(
                    "retirement-connectors-reverified",
                    "retirementConnectorResumeGate",
                    receipt,
                )
        except RecoveryUncertain:
            raise
        except Exception as exc:
            raise RecoveryUncertain(
                "post-marker connector proof could not become durable"
            ) from exc
        return receipt

    def finalize_committed_retirement(
        self,
        config: SidecarConfig,
        authorization: Mapping[str, Any],
        restoration: Mapping[str, Any],
        retirement_evidence: Mapping[str, Any],
        retired_authority: Mapping[str, Any],
        incumbent: Mapping[str, Any],
        cleanup: Mapping[str, Any],
        *_args: Any,
    ) -> dict[str, Any]:
        if (
            config.active_runtime_authority.exists()
            or config.active_runtime_authority.is_symlink()
        ):
            raise RecoveryUncertain(
                "active topology-B authority still exists at finalization"
            )
        retired_raw, _active, retired_path = (
            self._load_retirement_authority(config)
        )
        if retired_path != config.retired_active_authority:
            raise RecoveryUncertain(
                "retired topology-B authority is not authoritative"
            )
        evidence_raw = stable_regular_bytes(
            config.cloudflare_retirement_evidence,
            label="Cloudflare retirement evidence",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        baseline = self._validated_retirement_baseline()
        if not _json_semantically_equal(incumbent, baseline):
            raise RecoveryUncertain(
                "final incumbent observation differs from its baseline"
            )
        receipts = self._state.get("receipts")
        if (
            not isinstance(receipts, dict)
            or receipts.get("retirementAuthorization") != authorization
            or receipts.get("cloudflareRetirement") != restoration
            or receipts.get("retirementEvidence") != retirement_evidence
            or receipts.get("retiredAuthority") != retired_authority
            or receipts.get("cleanup") != cleanup
        ):
            raise RecoveryUncertain(
                "retirement finalization lacks durable cleanup proof"
            )
        try:
            marker_connector_gate = (
                self.cloudflare
                .validate_current_connector_convergence_receipt(
                    receipts.get("retirementConnectorGate")
                )
            )
        except Exception as exc:
            raise RecoveryUncertain(
                "retirement finalization lacks connector-set proof"
            ) from exc
        marker_connector_gate_sha256 = (
            self.cloudflare.canonical_sha256(marker_connector_gate)
        )
        restored_version = restoration.get("restoredVersion")
        if type(restored_version) is not int or restored_version < 0:
            raise RecoveryUncertain(
                "retirement restored version is invalid"
            )
        retired_authority_sha256 = sha256_bytes(retired_raw)
        post_marker_connector_gate = (
            self._validated_retirement_connector_boundary(
                receipts.get("retirementPostMarkerConnectorGate"),
                config=config,
                boundary="post-marker",
                restored_version=restored_version,
                retired_authority_sha256=retired_authority_sha256,
                marker_connector_gate_sha256=(
                    marker_connector_gate_sha256
                ),
            )
        )
        latest_connector_gate = receipts.get(
            "retirementConnectorResumeGate",
            post_marker_connector_gate,
        )
        latest_boundary = (
            "resume-post-marker"
            if "retirementConnectorResumeGate" in receipts
            else "post-marker"
        )
        latest_connector_gate = (
            self._validated_retirement_connector_boundary(
                latest_connector_gate,
                config=config,
                boundary=latest_boundary,
                restored_version=restored_version,
                retired_authority_sha256=retired_authority_sha256,
                marker_connector_gate_sha256=(
                    marker_connector_gate_sha256
                ),
            )
        )
        post_marker_connector_gate_sha256 = (
            self.cloudflare.canonical_sha256(
                post_marker_connector_gate
            )
        )
        latest_connector_gate_sha256 = (
            self.cloudflare.canonical_sha256(latest_connector_gate)
        )
        if (
            marker_connector_gate.get("targetVersion")
            != restored_version
            or retired_authority.get("connectorGateSha256")
            != marker_connector_gate_sha256
        ):
            raise RecoveryUncertain(
                "retirement connector-set proof drifted"
            )
        api = self._cloudflare_api()
        try:
            with self.cloudflare.ExclusiveFileLock(config.cloudflare_lock):
                current = self.cloudflare.parse_configuration_response(
                    api.get_configuration()
                )
                if (
                    current.sha256
                    != restoration.get("priorConfigSha256")
                    or current.version
                    != restoration.get("restoredVersion")
                ):
                    raise RecoveryUncertain(
                        "Cloudflare prior config drifted after sidecar cleanup"
                    )
        except RecoveryUncertain:
            raise
        except Exception as exc:
            raise RecoveryUncertain(
                "terminal retirement Cloudflare verification failed"
            ) from exc
        expected = {
            "contractName": (
                "chummer.public-download-committed-retirement/v1"
            ),
            "status": "retired",
            "operation": RETIRE_OPERATION,
            "operationRoot": str(config.operation_root),
            "projectName": config.project_name,
            "operationSourceHead": config.source_head,
            "controllerSourceHead": (
                config.controller_source_head or config.source_head
            ),
            "retiredAuthorityPath": str(
                config.retired_active_authority
            ),
            "retiredAuthoritySha256": sha256_bytes(retired_raw),
            "retirementEvidencePath": str(
                config.cloudflare_retirement_evidence
            ),
            "retirementEvidenceSha256": sha256_bytes(evidence_raw),
            "connectorGateSha256": marker_connector_gate_sha256,
            "postMarkerConnectorGateSha256": (
                post_marker_connector_gate_sha256
            ),
            "latestConnectorGateSha256": (
                latest_connector_gate_sha256
            ),
            "priorConfigSha256": restoration["priorConfigSha256"],
            "restoredVersion": restoration["restoredVersion"],
            "incumbentBaselineSha256": (
                self.cloudflare.canonical_sha256(baseline)
            ),
            "incumbentObservationSha256": (
                self.cloudflare.canonical_sha256(incumbent)
            ),
            "cleanupSha256": self.cloudflare.canonical_sha256(cleanup),
        }
        receipt_present = (
            config.retirement_receipt.exists()
            or config.retirement_receipt.is_symlink()
        )
        if receipt_present:
            raw = stable_regular_bytes(
                config.retirement_receipt,
                label="terminal topology-B retirement receipt",
                maximum_bytes=16 * 1024 * 1024,
                owner_only=True,
            )
            receipt = _strict_json_object_bytes(
                raw,
                label="terminal topology-B retirement receipt",
            )
            if (
                set(receipt) != {*expected, "completedAtUtc"}
                or any(
                    receipt.get(key) != value
                    for key, value in expected.items()
                )
                or not isinstance(receipt.get("completedAtUtc"), str)
            ):
                raise RecoveryUncertain(
                    "terminal topology-B retirement receipt drifted"
                )
        else:
            receipt = {
                **expected,
                "completedAtUtc": utc_now(),
            }
            write_private_json(config.retirement_receipt, receipt)
        existing = receipts.get("retirement")
        if existing is not None and existing != receipt:
            raise RecoveryUncertain(
                "terminal topology-B retirement journal drifted"
            )
        self._record("retired", "retirement", receipt)
        return receipt

    def prepare_sidecar_release_shelf(
        self, config: SidecarConfig
    ) -> dict[str, Any]:
        if not isinstance(self._state.get("incumbentBaseline"), dict):
            baseline = probe_public_incumbent(config)
            state = copy.deepcopy(self._state)
            state["incumbentBaseline"] = baseline
            self._state = state
            self._record(
                "incumbent-baseline-captured",
                "incumbentBaseline",
                baseline,
            )
        self._assert_canonical_shelf_unchanged()
        receipt = prepare_sidecar_release_shelf(
            config,
            generation=self.generation,
            attestor=self.attestor,
            projection_verifier=self.projection_verifier,
            candidate_materializer=self.candidate_materializer,
        )
        self._record("shelf-prepared", "shelf", receipt)
        return receipt

    def generate_sidecar_data_protection(
        self, config: SidecarConfig
    ) -> dict[str, Any]:
        receipt = generate_sidecar_data_protection(config, self.runner)
        self._record("data-protection-prepared", "dataProtection", receipt)
        return receipt

    def _stage_application(self) -> dict[str, Any]:
        output = self.config.operation_root / "overlay-stage.json"
        host_build = prepare_operation_host_build(self.config)
        self.runner.python(
            self.config.source_root
            / "scripts/publish_public_edge_portal_overlay.py",
            [
                "--source-root",
                str(self.config.source_root),
                "--active-root",
                str(self.config.overlay_root),
                "--staging-root",
                str(self.config.overlay_staging_root),
                "--backup-root",
                str(self.config.overlay_backup_root),
                "--build-root",
                str(self.config.overlay_build_root),
                "--host-build-root",
                str(self.config.host_build_root),
                "--downloads-source-root",
                str(self.config.shelf_source),
                "--playwright-authority",
                str(host_build["playwrightAuthority"]),
                "--playwright-authority-sha256",
                str(host_build["playwrightAuthoritySha256"]),
                "--delivery-phase",
                self.config.delivery_phase,
                "--surface-profile",
                "public-download",
                "--release-channel-receipt",
                str(self.config.release_channel_receipt),
                "--release-channel-receipt-sha256",
                self.config.release_channel_receipt_sha256,
                "--output",
                str(output),
            ],
            label="stage operation-only portal application",
            timeout=3600,
            environment={
                "HOME": str(host_build["home"]),
                "DOTNET_ROOT": str(host_build["sdk"]),
                "DOTNET_CLI_HOME": str(host_build["dotnetCliHome"]),
                "NUGET_PACKAGES": str(host_build["nugetPackages"]),
                "NUGET_HTTP_CACHE_PATH": str(host_build["nugetHttpCache"]),
                "TMPDIR": str(host_build["tmp"]),
                "PATH": f"{host_build['sdk']}:/usr/bin:/bin",
            },
        )
        overlay_digest = tree_sha256_file_stream(
            self.config.overlay_staging_root,
            label="operation-only portal application",
        )
        return {
            "receipt": str(output),
            "root": str(self.config.overlay_staging_root),
            "treeSha256": overlay_digest,
            "hostBuild": host_build,
        }

    def materialize_sidecar_compose(
        self,
        config: SidecarConfig,
        shelf: Mapping[str, Any],
        dp: Mapping[str, Any],
    ) -> dict[str, Any]:
        application = self._stage_application()
        contexts, context_digests, context_receipt = (
            prepare_immutable_build_contexts(
                config,
                config.operation_root,
            )
        )
        if (
            set(context_digests) != CANDIDATE_BUILD_CONTEXT_NAMES
            or any(
                not isinstance(digest, str)
                or SHA256.fullmatch(digest) is None
                for digest in context_digests.values()
            )
        ):
            raise CutoverError(
                "immutable candidate build context authority is malformed"
            )
        planned_tag = (
            f"chummer-run-api:public-download-{config.source_head[:16]}-"
            f"{secrets.token_hex(4)}"
        )
        self._record(
            "candidate-image-planned",
            "candidateImagePlan",
            {
                "contractName": (
                    "chummer.public-download-candidate-image-plan/v1"
                ),
                "candidateTag": planned_tag,
                "sourceHead": config.source_head,
                "immutableBuildContextDigests": dict(context_digests),
                "plannedAtUtc": utc_now(),
            },
        )

        def bind_candidate_image(tag: str, image_id: str) -> None:
            if tag != planned_tag or IMAGE_ID.fullmatch(image_id) is None:
                raise CutoverError(
                    "candidate image build did not match its durable plan"
                )
            self._record(
                "candidate-image-built",
                "candidateImage",
                {
                    "contractName": (
                        "chummer.public-download-candidate-image-binding/v1"
                    ),
                    "candidateTag": tag,
                    "candidateImageId": image_id,
                    "sourceHead": config.source_head,
                    "boundAtUtc": utc_now(),
                },
            )

        unique_tag, image_id = build_candidate_image(
            config,
            self.runner,
            contexts=contexts,
            context_digests=context_digests,
            unique_tag=planned_tag,
            on_built=bind_candidate_image,
        )
        tag_match = CANDIDATE_IMAGE_TAG.fullmatch(unique_tag)
        if (
            tag_match is None
            or tag_match.group(1) != config.source_head[:16]
            or IMAGE_ID.fullmatch(image_id) is None
        ):
            raise CutoverError("candidate image binding is invalid")
        if resolve_image_tag(self.runner, unique_tag) != image_id:
            raise CutoverError("candidate image tag changed before sidecar use")
        compose = materialize_sidecar_compose(
            config,
            self.runner,
            image_id=image_id,
            dp=dp,
            app_overlay_sha256=str(application["treeSha256"]),
            shelf=shelf,
        )
        self._compose_environment = dict(compose["environment"])
        receipt = {
            **compose,
            "candidateTag": unique_tag,
            "application": application,
            "immutableBuildContextReceipt": str(context_receipt),
            "immutableBuildContextDigests": context_digests,
        }
        self._record("runtime-materialized", "runtime", receipt)
        return receipt

    @staticmethod
    def _validated_sidecar_volume_authority(
        inspection: object,
        *,
        config: SidecarConfig,
        logical: str,
        name: str,
    ) -> dict[str, Any]:
        expected_labels = {
            "run.chummer.public-download-operation": config.project_name,
            "run.chummer.public-download-logical-volume": logical,
        }
        volume = (
            inspection[0]
            if isinstance(inspection, list)
            and len(inspection) == 1
            and isinstance(inspection[0], dict)
            else None
        )
        mountpoint = (
            volume.get("Mountpoint")
            if isinstance(volume, dict)
            else None
        )
        mount_path = (
            Path(mountpoint)
            if isinstance(mountpoint, str)
            else None
        )
        if (
            volume is None
            or volume.get("Name") != name
            or volume.get("Labels") != expected_labels
            or volume.get("Driver") != "local"
            or volume.get("Scope") != "local"
            or volume.get("Options") not in (None, {})
            or mount_path is None
            or not mount_path.is_absolute()
            or mountpoint.startswith("//")
            or "|" in mountpoint
            or any(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in mountpoint
            )
            or str(mount_path) != mountpoint
            or ".." in mount_path.parts
            or mount_path.name != "_data"
            or mount_path.parent.name != name
        ):
            raise RecoveryUncertain(
                "topology-B volume authority is ambiguous"
            )
        return volume

    def create_sidecar_resources(
        self,
        config: SidecarConfig,
        _runtime: Mapping[str, Any],
    ) -> dict[str, Any]:
        created: list[str] = []
        for logical in SIDECAR_LOGICAL_VOLUMES:
            name = config.volume_names[logical]
            listed = self._strict_output_lines(
                self.runner.docker(
                    [
                        "volume",
                        "ls",
                        "--quiet",
                        "--filter",
                        f"name=^{name}$",
                    ],
                    label=f"prove exact {logical} sidecar volume absent",
                ),
                label=f"exact {logical} sidecar volume",
            )
            if listed:
                raise RecoveryUncertain(
                    "preexisting topology-B volume is prohibited"
                )
        for logical in SIDECAR_LOGICAL_VOLUMES:
            name = config.volume_names[logical]
            raw = self.runner.docker(
                [
                    "volume",
                    "create",
                    "--label",
                    f"run.chummer.public-download-operation={config.project_name}",
                    "--label",
                    f"run.chummer.public-download-logical-volume={logical}",
                    name,
                ],
                label=f"create exact {logical} sidecar volume",
            )
            if self._strict_output_lines(
                raw,
                label=f"created {logical} sidecar volume",
            ) != [name]:
                raise CutoverError("Docker returned an unexpected volume name")
            try:
                inspection = json.loads(
                    self.runner.docker(
                        ["volume", "inspect", name],
                        label=f"verify created {logical} sidecar volume",
                    )
                )
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise RecoveryUncertain(
                    "created topology-B volume inspection is malformed"
                ) from exc
            try:
                self._validated_sidecar_volume_authority(
                    inspection,
                    config=config,
                    logical=logical,
                    name=name,
                )
            except RecoveryUncertain as exc:
                raise RecoveryUncertain(
                    "created topology-B volume authority is ambiguous"
                ) from exc
            created.append(name)
        receipt = {
            "projectName": config.project_name,
            "volumes": created,
            "reusedEmptyVolumes": [],
        }
        self._record("resources-created", "resources", receipt)
        return receipt

    def start_sidecar_runtime(
        self,
        config: SidecarConfig,
        runtime: Mapping[str, Any],
        _resources: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self._compose_environment:
            environment = runtime.get("environment")
            if not isinstance(environment, dict):
                raise CutoverError("sidecar Compose environment is unavailable")
            self._compose_environment = {
                str(key): str(value) for key, value in environment.items()
            }
        self.runner.compose(
            ["up", "-d", "--no-build", "--remove-orphans"],
            environment=self._compose_environment,
            label="start isolated topology-B sidecar",
            timeout=600,
        )
        raw = self.runner.compose(
            ["ps", "--quiet", PORTAL_SERVICE],
            environment=self._compose_environment,
            label="resolve isolated topology-B portal",
        )
        container_id = raw.decode("ascii", errors="strict").strip()
        if CONTAINER_ID.fullmatch(container_id) is None:
            raise CutoverError("isolated topology-B portal identity is invalid")
        inspection = docker_inspect_json(
            self.runner,
            "container",
            container_id,
        )
        labels = inspection.get("Config", {}).get("Labels") or {}
        if (
            labels.get("com.docker.compose.project") != config.project_name
            or labels.get("com.docker.compose.service") != PORTAL_SERVICE
            or str(inspection.get("Image") or "")
            != runtime.get("candidateImageId")
        ):
            raise CutoverError("isolated topology-B portal authority drifted")
        receipt = {
            "containerId": container_id,
            "imageId": runtime["candidateImageId"],
            "projectName": config.project_name,
        }
        self._record("sidecar-started", "sidecar", receipt)
        return receipt

    def wait_sidecar_healthy(
        self,
        config: SidecarConfig,
        runtime: Mapping[str, Any],
        sidecar: Mapping[str, Any],
    ) -> dict[str, Any]:
        receipt = wait_healthy(
            self.runner,
            str(sidecar["containerId"]),
            expected_image=str(runtime["candidateImageId"]),
            timeout_seconds=config.ready_timeout_seconds,
        )
        self._record("sidecar-healthy", "health", receipt)
        return receipt

    def probe_sidecar_hosts(
        self,
        config: SidecarConfig,
        shelf: Mapping[str, Any],
        *_args: Any,
        hosts: tuple[str, ...],
        scope: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if hosts != SIDECAR_HOSTS:
            raise CutoverError("sidecar host closure drifted")
        if scope == "local":
            receipt = probe_sidecar_hosts(
                config,
                shelf=shelf,
                generation_id=str(shelf["generationId"]),
                generation_root=Path(str(shelf["generationRoot"])),
            )
            self._record("local-verified", "localProbe", receipt)
            return receipt
        if scope != "public":
            raise CutoverError("sidecar probe scope is invalid")
        receipt = self._verify_public_downloads(shelf)
        self._record("public-verified", "publicProbe", receipt)
        return receipt

    def probe_public_incumbent(
        self,
        config: SidecarConfig,
        *,
        phase: str,
        hosts: tuple[str, ...],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if hosts != SIDECAR_HOSTS:
            raise CutoverError("incumbent host closure drifted")
        if phase == "before-cloudflare":
            baseline = self._state.get("incumbentBaseline")
            receipt = probe_public_incumbent(
                config,
                expected=baseline if isinstance(baseline, dict) else None,
            )
            state = copy.deepcopy(self._state)
            state["incumbentBaseline"] = receipt
            self._state = state
            self._record("incumbent-captured", "incumbentBefore", receipt)
            return receipt
        if phase == "after-retirement":
            baseline = self._state.get("incumbentBaseline")
            if not isinstance(baseline, dict):
                raise RecoveryUncertain(
                    "incumbent retirement baseline is unavailable"
                )
            receipt = probe_public_incumbent(config, expected=baseline)
            self._record(
                "retirement-incumbent-verified",
                "incumbentAfterRetirement",
                receipt,
            )
            return receipt
        if phase != "after-rollback":
            raise CutoverError("incumbent probe phase is invalid")
        baseline = self._state.get("incumbentBaseline")
        if not isinstance(baseline, dict):
            rollback_receipt = (
                self._state.get("receipts", {}).get(
                    "cloudflareRollback",
                    {},
                )
            )
            if (
                self._state.get("phase") != "planned"
                and (
                    not isinstance(rollback_receipt, dict)
                    or rollback_receipt.get("phase") != "not-captured"
                )
            ):
                raise RecoveryUncertain(
                    "incumbent rollback baseline is unavailable"
                )
            receipt = probe_public_incumbent(config)
        else:
            receipt = probe_public_incumbent(config, expected=baseline)
        self._record("incumbent-restored", "incumbentAfterRollback", receipt)
        return receipt

    def capture_cloudflare(
        self,
        config: SidecarConfig,
        shelf: Mapping[str, Any],
        _runtime: Mapping[str, Any],
        _sidecar: Mapping[str, Any],
        local_probe: Mapping[str, Any],
        _incumbent: Mapping[str, Any],
    ) -> dict[str, Any]:
        release_revalidation = validate_release_candidate_authority(
            config,
            projection_verifier=self.projection_verifier,
            candidate_materializer=self.candidate_materializer,
        )
        if release_revalidation != shelf.get("releaseCandidateAuthority"):
            initial = shelf.get("releaseCandidateAuthority")
            if (
                not isinstance(initial, dict)
                or {
                    key: value
                    for key, value in initial.items()
                    if key != "validatedAtUtc"
                }
                != {
                    key: value
                    for key, value in release_revalidation.items()
                    if key != "validatedAtUtc"
                }
            ):
                raise CutoverError(
                    "release candidate authority changed before Cloudflare capture"
                )
        self._record(
            "release-authority-revalidated",
            "releaseCandidateAuthorityRevalidation",
            release_revalidation,
        )
        generation_id = str(shelf["generationId"])
        recorded_local_probe = (
            self._state.get("receipts", {}).get("localProbe")
            if isinstance(self._state.get("receipts"), dict)
            else None
        )
        if local_probe != recorded_local_probe:
            raise CutoverError(
                "local generation probe changed before Cloudflare capture"
            )
        served_manifest_sha256 = (
            _local_served_generation_manifest_sha256(
                local_probe,
                generation_id=generation_id,
            )
        )
        receipt = self.cloudflare.capture_transaction(
            self._cloudflare_api(),
            account_id=config.cloudflare_account_id,
            tunnel_id=config.cloudflare_tunnel_id,
            origin=SIDECAR_ORIGIN,
            generation_id=generation_id,
            probe_endpoint=(
                f"https://chummer.run/downloads/g/{generation_id}/releases.json"
            ),
            probe_body_sha256=served_manifest_sha256,
            journal_path=config.cloudflare_journal,
            lock_path=config.cloudflare_lock,
        )
        summary = {
            "phase": receipt["phase"],
            "priorConfigSha256": receipt["priorConfigSha256"],
            "priorVersion": receipt["priorVersion"],
            "targetConfigSha256": receipt["targetConfigSha256"],
            "generationId": generation_id,
        }
        self._record("cloudflare-captured", "cloudflareCapture", summary)
        return summary

    def apply_cloudflare(
        self,
        config: SidecarConfig,
        *_args: Any,
    ) -> dict[str, Any]:
        receipt = self.cloudflare.apply_transaction(
            self._cloudflare_api(),
            journal_path=config.cloudflare_journal,
            lock_path=config.cloudflare_lock,
        )
        summary = {
            "phase": receipt["phase"],
            "targetConfigSha256": receipt["targetConfigSha256"],
            "targetVersion": receipt["targetVersion"],
            "connectorConvergence": receipt["connectorConvergence"],
        }
        self._record("cloudflare-applied", "cloudflareApply", summary)
        return summary

    def _wait_for_public_generation_convergence(
        self,
        shelf: Mapping[str, Any],
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        interval_seconds: float = 2.0,
    ) -> list[dict[str, Any]]:
        if interval_seconds <= 0:
            raise CutoverError(
                "public generation convergence interval is invalid"
            )
        journal = self.cloudflare.load_journal(
            self.config.cloudflare_journal
        )
        generation_id = str(shelf["generationId"])
        expected_body_sha256 = str(
            journal.get("probeBodySha256") or ""
        )
        if (
            journal.get("generationId") != generation_id
            or SHA256.fullmatch(expected_body_sha256) is None
        ):
            raise CutoverError(
                "Cloudflare public generation probe authority drifted"
            )
        generation_root = Path(str(shelf["generationRoot"]))
        manifest = stable_regular_bytes(
            generation_root / "releases.json",
            label="prepared generation compatibility manifest",
            maximum_bytes=8 * 1024 * 1024,
        )
        path = f"/downloads/g/{generation_id}/releases.json"
        deadline = monotonic_fn() + self.config.ready_timeout_seconds
        last_error: BaseException | None = None
        while True:
            observations: list[dict[str, Any]] = []
            try:
                for hostname in SIDECAR_HOSTS:
                    remaining = deadline - monotonic_fn()
                    if remaining <= 0:
                        raise CutoverError(
                            "public generation convergence deadline elapsed"
                        )
                    observed = _probe_exact_manifest(
                        scheme="https",
                        connect_host=hostname,
                        connect_port=443,
                        request_host=hostname,
                        path=path,
                        expected=manifest,
                        shelf=shelf,
                        generation_id=generation_id,
                        timeout=min(30.0, remaining),
                    )
                    if monotonic_fn() > deadline:
                        raise CutoverError(
                            "public generation convergence deadline elapsed"
                        )
                    if observed["bodySha256"] != expected_body_sha256:
                        raise CutoverError(
                            "public generation body digest differs from "
                            "the attested local sidecar"
                        )
                    observations.append(observed)
                return observations
            except (
                CutoverError,
                OSError,
                http.client.HTTPException,
            ) as exc:
                last_error = exc
            remaining = deadline - monotonic_fn()
            if remaining <= 0:
                raise CutoverError(
                    "public generation did not converge before timeout"
                ) from last_error
            sleep_fn(min(interval_seconds, remaining))

    def _verify_public_downloads(
        self,
        shelf: Mapping[str, Any],
    ) -> dict[str, Any]:
        generation_root = Path(str(shelf["generationRoot"]))
        convergence = self._wait_for_public_generation_convergence(shelf)
        strict_output = self.config.operation_root / "public-postdeploy.json"
        self.runner.python(
            self.config.source_root
            / "scripts/verify_public_download_only_postdeploy.py",
            [
                "--base-url",
                self.config.base_url,
                "--source-root",
                str(self.config.source_root),
                "--local-manifest",
                str(generation_root / "releases.json"),
                "--local-canonical-manifest",
                str(generation_root / "RELEASE_CHANNEL.generated.json"),
                "--delivery-phase",
                self.config.delivery_phase,
                "--output",
                str(strict_output),
                "--timeout",
                "30",
            ],
            label="verify strict anonymous public download delivery",
            timeout=1800,
        )
        strict = json.loads(
            stable_regular_bytes(
                strict_output,
                label="strict public download receipt",
                maximum_bytes=16 * 1024 * 1024,
                owner_only=True,
            )
        )
        if strict.get("status") != "pass":
            raise CutoverError("strict public download receipt did not pass")
        artifact_verification = probe_download_artifact_hosts(
            self.config,
            shelf=shelf,
            scope="public",
        )
        journal = self.cloudflare.load_journal(
            self.config.cloudflare_journal
        )
        manifest = stable_regular_bytes(
            generation_root / "releases.json",
            label="prepared generation compatibility manifest",
            maximum_bytes=8 * 1024 * 1024,
        )
        generation_id = str(shelf["generationId"])
        path = f"/downloads/g/{generation_id}/releases.json"
        observations: list[dict[str, Any]] = []
        for hostname in SIDECAR_HOSTS:
            observed = _probe_exact_manifest(
                scheme="https",
                connect_host=hostname,
                connect_port=443,
                request_host=hostname,
                path=path,
                expected=manifest,
                shelf=shelf,
                generation_id=generation_id,
            )
            observations.append(
                {
                    "endpoint": f"https://{hostname}{path}",
                    "httpStatus": observed["httpStatus"],
                    "bodySha256": observed["bodySha256"],
                    "anonymous": True,
                }
            )
        missing_connector_ids = [
            row["id"]
            for row in journal["connectorConvergence"]
            if not row["configVersionAvailable"]
        ]
        external = {
            "schema": self.cloudflare.EXTERNAL_PROBE_SCHEMA,
            "accountId": journal["accountId"],
            "tunnelId": journal["tunnelId"],
            "targetConfigSha256": journal["targetConfigSha256"],
            "targetVersion": journal["targetVersion"],
            "connectorIds": missing_connector_ids,
            "generationId": generation_id,
            "observations": observations,
            "observedAt": utc_now(),
        }
        write_private_json(self.config.external_probe_receipt, external)
        self.cloudflare.validate_external_probe_receipt(external, journal)
        self._assert_canonical_shelf_unchanged()
        return {
            "strictReceiptPath": str(strict_output),
            "strictReceiptSha256": sha256_bytes(
                stable_regular_bytes(
                    strict_output,
                    label="strict public download receipt",
                    maximum_bytes=16 * 1024 * 1024,
                    owner_only=True,
                )
            ),
            "externalProbeReceiptPath": str(
                self.config.external_probe_receipt
            ),
            "externalProbeReceiptSha256": sha256_bytes(
                stable_regular_bytes(
                    self.config.external_probe_receipt,
                    label="Cloudflare external probe receipt",
                    maximum_bytes=1024 * 1024,
                    owner_only=True,
                )
            ),
            "artifactVerification": artifact_verification,
            "convergenceObservations": convergence,
        }

    def commit_cloudflare(
        self,
        config: SidecarConfig,
        *_args: Any,
    ) -> dict[str, Any]:
        receipt = self.cloudflare.commit_transaction(
            self._cloudflare_api(),
            journal_path=config.cloudflare_journal,
            lock_path=config.cloudflare_lock,
            evidence_path=config.cloudflare_committed_evidence,
            external_probe_receipt=config.external_probe_receipt,
        )
        summary = {
            "phase": receipt["phase"],
            "targetConfigSha256": receipt["targetConfigSha256"],
            "targetVersion": receipt["targetVersion"],
            "evidencePath": str(config.cloudflare_committed_evidence),
            "evidenceSha256": sha256_bytes(
                stable_regular_bytes(
                    config.cloudflare_committed_evidence,
                    label="committed Cloudflare evidence",
                    maximum_bytes=16 * 1024 * 1024,
                    owner_only=True,
                )
            ),
        }
        self._record("cloudflare-committed", "cloudflareCommit", summary)
        return summary

    def write_active_receipt(
        self,
        config: SidecarConfig,
        shelf: Mapping[str, Any],
        runtime: Mapping[str, Any],
        sidecar: Mapping[str, Any],
        cloudflare_commit: Mapping[str, Any],
        *_args: Any,
    ) -> dict[str, Any]:
        payload = {
            "schema": TOPOLOGY_B_ACTIVE_SCHEMA,
            "status": "active",
            "operation": config.operation,
            "operationRoot": str(config.operation_root),
            "projectName": config.project_name,
            "sourceHead": config.source_head,
            "origin": SIDECAR_ORIGIN,
            "publicHosts": list(SIDECAR_HOSTS),
            "generationId": shelf["generationId"],
            "shelfTreeSha256": shelf["shelfTreeSha256"],
            "candidateImageId": runtime["candidateImageId"],
            "portalContainerId": sidecar["containerId"],
            "volumes": dict(config.volume_names),
            "finalGoldDiagnostic": {
                "path": str(config.final_gold_source),
                "sha256": config.final_gold_sha256,
                "authority": "diagnostic-only-not-release-completion",
            },
            "cloudflare": dict(cloudflare_commit),
            "activatedAtUtc": utc_now(),
        }
        write_private_json(
            config.active_runtime_authority,
            payload,
            replace=(
                config.active_runtime_authority.exists()
                and not config.active_runtime_authority.is_symlink()
            ),
        )
        self._record("active", "activeAuthority", payload)
        return payload

    def rollback_cloudflare(
        self,
        config: SidecarConfig,
        *_args: Any,
    ) -> dict[str, Any]:
        if (
            not self.cloudflare.journal_path_present(
                config.cloudflare_journal
            )
            and not self.cloudflare.journal_path_present(
                config.cloudflare_rollback_evidence
            )
        ):
            receipt = {"phase": "not-captured"}
        else:
            receipt = self.cloudflare.rollback_transaction(
                self._cloudflare_api(),
                journal_path=config.cloudflare_journal,
                lock_path=config.cloudflare_lock,
                evidence_path=config.cloudflare_rollback_evidence,
            )
        summary = {
            "phase": receipt["phase"],
            "evidencePath": (
                str(config.cloudflare_rollback_evidence)
                if config.cloudflare_rollback_evidence.exists()
                else None
            ),
        }
        self._record("cloudflare-rolled-back", "cloudflareRollback", summary)
        return summary

    @staticmethod
    def _strict_output_lines(value: bytes, *, label: str) -> list[str]:
        try:
            decoded = value.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise RecoveryUncertain(f"{label} output is malformed") from exc
        return [line.strip() for line in decoded.splitlines() if line.strip()]

    def _prove_pre_runtime_absence(
        self,
        config: SidecarConfig,
    ) -> dict[str, Any]:
        checks = (
            (
                "containers",
                [
                    "container",
                    "ls",
                    "--all",
                    "--quiet",
                    "--no-trunc",
                    "--filter",
                    f"label=com.docker.compose.project={config.project_name}",
                ],
            ),
            (
                "networks",
                [
                    "network",
                    "ls",
                    "--quiet",
                    "--no-trunc",
                    "--filter",
                    f"label=com.docker.compose.project={config.project_name}",
                ],
            ),
            (
                "labeledVolumes",
                [
                    "volume",
                    "ls",
                    "--quiet",
                    "--filter",
                    "label=run.chummer.public-download-operation="
                    f"{config.project_name}",
                ],
            ),
        )
        for resource, arguments in checks:
            try:
                output = self.runner.docker(
                    arguments,
                    label=f"prove no exact topology-B {resource}",
                )
            except CutoverError as exc:
                raise RecoveryUncertain(
                    f"pre-runtime topology-B {resource} could not be proven absent"
                ) from exc
            observed = self._strict_output_lines(
                output,
                label=f"topology-B {resource}",
            )
            if observed:
                raise RecoveryUncertain(
                    f"pre-runtime topology-B {resource} are present"
                )
        try:
            listener_output = self.runner.run(
                [
                    "/usr/bin/ss",
                    "-H",
                    "-ltn",
                    f"sport = :{SIDECAR_PORT}",
                ],
                label="prove topology-B sidecar port is free",
            )
        except CutoverError as exc:
            raise RecoveryUncertain(
                "pre-runtime topology-B sidecar port could not be proven free"
            ) from exc
        listeners = self._strict_output_lines(
            listener_output,
            label="topology-B sidecar port",
        )
        if listeners:
            raise RecoveryUncertain(
                "pre-runtime topology-B sidecar port is in use"
            )
        return {
            "contractName": (
                "chummer.public-download-pre-runtime-absence/v1"
            ),
            "projectName": config.project_name,
            "containers": 0,
            "networks": 0,
            "labeledVolumes": 0,
            "publishedAddress": SIDECAR_ADDRESS,
            "publishedPort": SIDECAR_PORT,
            "listeners": 0,
            "status": "pass",
        }

    def _validated_runtime_environment(
        self,
        config: SidecarConfig,
        runtime: Mapping[str, Any],
        receipts: Mapping[str, Any],
        *,
        historical_source: bool = False,
    ) -> tuple[dict[str, str], str]:
        environment = runtime.get("environment")
        shelf = receipts.get("shelf")
        data_protection = receipts.get("dataProtection")
        application = runtime.get("application")
        binding = receipts.get("candidateImage")
        if (
            not isinstance(environment, dict)
            or not environment
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in environment.items()
            )
            or not isinstance(shelf, dict)
            or not isinstance(data_protection, dict)
            or not isinstance(application, dict)
            or not isinstance(binding, dict)
            or not isinstance(shelf.get("shelfTreeSha256"), str)
            or SHA256.fullmatch(shelf["shelfTreeSha256"])
            is None
            or not isinstance(
                data_protection.get("certificateSha256"),
                str,
            )
            or SHA256.fullmatch(data_protection["certificateSha256"])
            is None
            or not isinstance(data_protection.get("passwordSha256"), str)
            or SHA256.fullmatch(data_protection["passwordSha256"])
            is None
            or not isinstance(application.get("treeSha256"), str)
            or SHA256.fullmatch(application["treeSha256"])
            is None
            or runtime.get("projectName") != config.project_name
            or runtime.get("publishedAddress") != SIDECAR_ADDRESS
            or type(runtime.get("publishedPort")) is not int
            or runtime["publishedPort"] != SIDECAR_PORT
            or runtime.get("candidateImageId")
            != binding.get("candidateImageId")
            or runtime.get("candidateTag") != binding.get("candidateTag")
            or not _json_semantically_equal(
                runtime.get("volumes"),
                config.volume_names,
            )
            or runtime.get("composePath") != str(config.compose_file)
            or runtime.get("materializationReceipt")
            != str(config.materialization_receipt)
            or runtime.get("runtimeAttestation")
            != str(config.runtime_attestation)
        ):
            raise RecoveryUncertain(
                "topology-B runtime Compose authority is malformed"
            )
        try:
            expected = _sidecar_compose_environment(
                config,
                dp=data_protection,
                app_overlay_sha256=str(application["treeSha256"]),
                shelf=shelf,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RecoveryUncertain(
                "topology-B runtime Compose environment cannot be reconstructed"
            ) from exc
        if environment != expected:
            raise RecoveryUncertain(
                "topology-B runtime Compose environment drifted"
            )
        try:
            compose_bytes = stable_regular_bytes(
                config.compose_file,
                label="topology-B materialized Compose",
                owner_only=True,
            )
            materialization_bytes = stable_regular_bytes(
                config.materialization_receipt,
                label="topology-B Compose materialization receipt",
                owner_only=True,
            )
            attestation_bytes = stable_regular_bytes(
                config.runtime_attestation,
                label="topology-B Compose runtime attestation",
                owner_only=True,
            )
            materialization = json.loads(materialization_bytes)
            attestation = json.loads(attestation_bytes)
            canonical_source_root = config.source_root.resolve(strict=True)
            receipt_source_root = canonical_source_root
            if historical_source:
                recorded_source_root = (
                    materialization.get("sourceRoot")
                    if isinstance(materialization, dict)
                    else None
                )
                if not isinstance(recorded_source_root, str):
                    raise RecoveryUncertain(
                        "historical topology-B source root is unavailable"
                    )
                receipt_source_root = Path(recorded_source_root)
                if (
                    not receipt_source_root.is_absolute()
                    or any(
                        part in {"", ".", ".."}
                        for part in receipt_source_root.parts
                    )
                    or str(receipt_source_root) != recorded_source_root
                ):
                    raise RecoveryUncertain(
                        "historical topology-B source root is malformed"
                    )
            base_source = (
                receipt_source_root / "docker-compose.public-edge.yml"
            )
            profile_source = (
                receipt_source_root / "docker-compose.public-downloads.yml"
            )
            if historical_source:
                revision_sources: dict[str, bytes] = {}
                for relative in (
                    "docker-compose.public-edge.yml",
                    "docker-compose.public-downloads.yml",
                ):
                    completed = subprocess.run(
                        [
                            "/usr/bin/git",
                            "-C",
                            str(canonical_source_root),
                            "show",
                            f"{config.source_head}:{relative}",
                        ],
                        env={
                            "PATH": "/usr/bin:/bin",
                            "LANG": "C",
                            "LC_ALL": "C",
                        },
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        timeout=10,
                    )
                    if len(completed.stdout) > 16 * 1024 * 1024:
                        raise RecoveryUncertain(
                            "historical topology-B Compose source is oversized"
                        )
                    revision_sources[relative] = completed.stdout
                base_sha256 = sha256_bytes(
                    revision_sources["docker-compose.public-edge.yml"]
                )
                profile_sha256 = sha256_bytes(
                    revision_sources["docker-compose.public-downloads.yml"]
                )
            else:
                base_sha256 = sha256_bytes(
                    stable_regular_bytes(
                        base_source,
                        label="revision-bound public-edge Compose source",
                    )
                )
                profile_sha256 = sha256_bytes(
                    stable_regular_bytes(
                        profile_source,
                        label=(
                            "revision-bound public-download Compose profile"
                        ),
                    )
                )
        except (
            CutoverError,
            OSError,
            subprocess.SubprocessError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            raise RecoveryUncertain(
                "topology-B runtime Compose authority is unavailable"
            ) from exc
        compose_sha256 = sha256_bytes(compose_bytes)
        materialization_fields = {
            "contractName",
            "status",
            "operation",
            "sourceRoot",
            "sourceHead",
            "baseComposeSource",
            "baseComposeSourceSha256",
            "profileSource",
            "profileSourceSha256",
            "candidateImageId",
            "composeSha256",
        }
        attestation_fields = {
            "contractName",
            "status",
            "operation",
            "runtimeProfile",
            "projectName",
            "operationRoot",
            "portalImageId",
            "initializerImageId",
            "initializerConstrained",
            "portalAppCopiedReadOnly",
            "portalFleetCopiedReadOnly",
            "longRunningSourceBindsAbsent",
            "releaseShelfPreinitialized",
            "releaseShelfPortalReadOnly",
            "isolatedVolumes",
            "runtimeInputs",
            "postgresServicesAbsent",
            "postgresEnvironmentAbsent",
            "postgresMountsAbsent",
            "postgresHostMappingAbsent",
            "portalBuildAbsent",
            "publicDownloadsHealthcheck",
            "releaseShelfPosture",
            "portalMountCount",
            "initializerMountCount",
            "publishedAddress",
            "publishedPort",
            "renderedComposeSha256",
            "sourceRoot",
            "sourceHead",
            "baseComposeSourceSha256",
            "profileSourceSha256",
            "materializedComposeSha256",
        }
        expected_runtime_inputs = {
            "appOverlay": {
                "source": str(config.overlay_staging_root),
                "sha256": application["treeSha256"],
            },
            "fleet": {
                "source": str(config.fleet_source),
                "sha256": config.fleet_sha256,
            },
            "shelf": {
                "source": str(config.shelf_source),
                "sha256": shelf["shelfTreeSha256"],
            },
            "projection": {
                "source": str(config.projection_snapshot_root),
                "sha256": config.projection_source_tree_sha256,
            },
            "runtimeProof": {
                "source": str(config.runtime_proof_source),
                "sha256": config.runtime_proof_sha256,
            },
            "finalGold": {
                "source": str(config.final_gold_source),
                "sha256": config.final_gold_sha256,
            },
            "certificateSha256": data_protection["certificateSha256"],
            "certificatePasswordSha256": data_protection["passwordSha256"],
            "certificateAuthority": "operation-bound-sidecar-only",
        }
        expected_release_shelf_posture = {
            "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
            "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
        }
        recorded_operation = self._state.get("operation", config.operation)
        if recorded_operation != CUTOVER_OPERATION:
            raise RecoveryUncertain(
                "topology-B runtime deployment operation drifted"
            )
        if (
            not isinstance(materialization, dict)
            or set(materialization) != materialization_fields
            or materialization.get("contractName")
            != "chummer.public-download-only-compose-materialization/v1"
            or materialization.get("status") != "pass"
            or materialization.get("operation") != recorded_operation
            or materialization.get("sourceRoot")
            != str(receipt_source_root)
            or materialization.get("sourceHead") != config.source_head
            or materialization.get("baseComposeSource") != str(base_source)
            or materialization.get("baseComposeSourceSha256") != base_sha256
            or materialization.get("profileSource") != str(profile_source)
            or materialization.get("profileSourceSha256") != profile_sha256
            or materialization.get("candidateImageId")
            != binding.get("candidateImageId")
            or materialization.get("composeSha256") != compose_sha256
            or not isinstance(attestation, dict)
            or set(attestation) != attestation_fields
            or attestation.get("contractName")
            != "chummer.public-download-only-compose-runtime-attestation/v1"
            or attestation.get("status") != "pass"
            or attestation.get("operation") != recorded_operation
            or attestation.get("runtimeProfile") != RUNTIME_PROFILE
            or attestation.get("projectName") != config.project_name
            or attestation.get("operationRoot") != str(config.operation_root)
            or attestation.get("portalImageId")
            != binding.get("candidateImageId")
            or attestation.get("initializerImageId")
            != binding.get("candidateImageId")
            or attestation.get("initializerConstrained") is not True
            or attestation.get("portalAppCopiedReadOnly") is not True
            or attestation.get("portalFleetCopiedReadOnly") is not True
            or attestation.get("longRunningSourceBindsAbsent") is not True
            or attestation.get("releaseShelfPreinitialized") is not True
            or attestation.get("releaseShelfPortalReadOnly") is not True
            or not _json_semantically_equal(
                attestation.get("isolatedVolumes"),
                config.volume_names,
            )
            or not _json_semantically_equal(
                attestation.get("runtimeInputs"),
                expected_runtime_inputs,
            )
            or attestation.get("postgresServicesAbsent") is not True
            or attestation.get("postgresEnvironmentAbsent") is not True
            or attestation.get("postgresMountsAbsent") is not True
            or attestation.get("postgresHostMappingAbsent") is not True
            or attestation.get("portalBuildAbsent") is not True
            or attestation.get("publicDownloadsHealthcheck") is not True
            or not _json_semantically_equal(
                attestation.get("releaseShelfPosture"),
                expected_release_shelf_posture,
            )
            or type(attestation.get("portalMountCount")) is not int
            or attestation["portalMountCount"] != 10
            or type(attestation.get("initializerMountCount")) is not int
            or attestation["initializerMountCount"] != 18
            or attestation.get("publishedAddress") != SIDECAR_ADDRESS
            or type(attestation.get("publishedPort")) is not int
            or attestation["publishedPort"] != SIDECAR_PORT
            or attestation.get("sourceRoot") != str(receipt_source_root)
            or attestation.get("sourceHead") != config.source_head
            or attestation.get("baseComposeSourceSha256") != base_sha256
            or attestation.get("profileSourceSha256") != profile_sha256
            or attestation.get("materializedComposeSha256")
            != compose_sha256
            or SHA256.fullmatch(
                str(attestation.get("renderedComposeSha256") or "")
            )
            is None
        ):
            raise RecoveryUncertain(
                "topology-B runtime Compose authority drifted"
            )
        return expected, str(attestation["renderedComposeSha256"])

    def _prove_rendered_compose_unchanged(
        self,
        environment: Mapping[str, str],
        rendered_compose_sha256: str,
    ) -> None:
        rendered = self.runner.compose(
            ["config", "--format", "json"],
            environment=environment,
            label="revalidate topology-B Compose before cleanup",
        )
        if sha256_bytes(rendered) != rendered_compose_sha256:
            raise RecoveryUncertain(
                "topology-B rendered Compose authority drifted"
            )

    def _preflight_candidate_image(
        self,
        config: SidecarConfig,
    ) -> dict[str, Any]:
        receipts = self._state.get("receipts")
        if not isinstance(receipts, dict):
            raise RecoveryUncertain("topology-B operation receipts are malformed")
        binding = receipts.get("candidateImage")
        plan = receipts.get("candidateImagePlan")
        recovered_from_plan = False
        if plan is None:
            if binding is None:
                return {"disposition": "not-bound"}
            raise RecoveryUncertain(
                "topology-B bound candidate image has no durable plan"
            )
        expected_plan_fields = {
            "contractName",
            "candidateTag",
            "sourceHead",
            "immutableBuildContextDigests",
            "plannedAtUtc",
        }
        digests = (
            plan.get("immutableBuildContextDigests")
            if isinstance(plan, dict)
            else None
        )
        planned_tag = (
            str(plan.get("candidateTag") or "")
            if isinstance(plan, dict)
            else ""
        )
        tag_match = CANDIDATE_IMAGE_TAG.fullmatch(planned_tag)
        if (
            not isinstance(plan, dict)
            or set(plan) != expected_plan_fields
            or plan.get("contractName")
            != "chummer.public-download-candidate-image-plan/v1"
            or plan.get("sourceHead") != config.source_head
            or not isinstance(plan.get("plannedAtUtc"), str)
            or tag_match is None
            or tag_match.group(1) != config.source_head[:16]
            or not isinstance(digests, dict)
            or set(digests) != CANDIDATE_BUILD_CONTEXT_NAMES
            or any(
                not isinstance(value, str)
                or SHA256.fullmatch(value) is None
                for value in digests.values()
            )
        ):
            raise RecoveryUncertain(
                "topology-B candidate image plan is malformed"
            )
        planned_digests: Mapping[str, str] = digests
        if binding is None:
            planned_image_ids = self._strict_output_lines(
                self.runner.docker(
                    [
                        "image",
                        "ls",
                        "--quiet",
                        "--no-trunc",
                        planned_tag,
                    ],
                    label="resolve planned candidate image tag for cleanup",
                ),
                label="planned candidate image tag",
            )
            if planned_image_ids:
                if (
                    len(set(planned_image_ids)) != 1
                    or any(
                        IMAGE_ID.fullmatch(item) is None
                        for item in planned_image_ids
                    )
                ):
                    raise RecoveryUncertain(
                        "planned candidate image tag is ambiguous"
                    )
                image_id = planned_image_ids[0]
                binding = {
                    "contractName": (
                        "chummer.public-download-candidate-image-binding/v1"
                    ),
                    "candidateTag": planned_tag,
                    "candidateImageId": image_id,
                    "sourceHead": config.source_head,
                    "boundAtUtc": utc_now(),
                }
                recovered_from_plan = True
            else:
                return {
                    "disposition": "planned-image-absent",
                    "candidateTag": planned_tag,
                }
        expected_fields = {
            "contractName",
            "candidateTag",
            "candidateImageId",
            "sourceHead",
            "boundAtUtc",
        }
        if (
            not isinstance(binding, dict)
            or set(binding) != expected_fields
            or binding.get("contractName")
            != "chummer.public-download-candidate-image-binding/v1"
            or binding.get("sourceHead") != config.source_head
            or not isinstance(binding.get("boundAtUtc"), str)
            or not isinstance(binding.get("candidateTag"), str)
            or not isinstance(binding.get("candidateImageId"), str)
        ):
            raise RecoveryUncertain(
                "topology-B candidate image binding is malformed"
            )
        tag = binding["candidateTag"]
        image_id = binding["candidateImageId"]
        tag_match = CANDIDATE_IMAGE_TAG.fullmatch(tag)
        if (
            tag != planned_tag
            or tag_match is None
            or tag_match.group(1) != config.source_head[:16]
            or IMAGE_ID.fullmatch(image_id) is None
        ):
            raise RecoveryUncertain(
                "topology-B candidate image binding is invalid"
            )

        all_image_ids = self._strict_output_lines(
            self.runner.docker(
                ["image", "ls", "--all", "--quiet", "--no-trunc"],
                label="inventory local images for candidate cleanup",
            ),
            label="local image inventory",
        )
        if any(IMAGE_ID.fullmatch(item) is None for item in all_image_ids):
            raise RecoveryUncertain("local image inventory is malformed")
        tag_image_ids = self._strict_output_lines(
            self.runner.docker(
                ["image", "ls", "--quiet", "--no-trunc", tag],
                label="resolve exact candidate image tag for cleanup",
            ),
            label="candidate image tag",
        )
        if any(IMAGE_ID.fullmatch(item) is None for item in tag_image_ids):
            raise RecoveryUncertain("candidate image tag output is malformed")
        if not tag_image_ids:
            if image_id not in all_image_ids:
                return {
                    "disposition": "already-absent",
                    "candidateTag": tag,
                    "candidateImageId": image_id,
                }
            tag_present = False
        else:
            tag_present = True
        if (
            tag_present
            and (
                set(tag_image_ids) != {image_id}
                or image_id not in all_image_ids
            )
        ):
            raise RecoveryUncertain(
                "candidate image tag no longer resolves to its bound image"
            )
        try:
            inspection = json.loads(
                self.runner.docker(
                    ["image", "inspect", tag if tag_present else image_id],
                    label="inspect exact candidate image for cleanup",
                )
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RecoveryUncertain(
                "candidate image inspection is malformed"
            ) from exc
        if not isinstance(inspection, list) or len(inspection) != 1:
            raise RecoveryUncertain(
                "candidate image inspection does not match its binding"
            )
        inspected_image = inspection[0]
        inspected_config = (
            inspected_image.get("Config")
            if isinstance(inspected_image, dict)
            else None
        )
        inspected_labels = (
            inspected_config.get("Labels")
            if isinstance(inspected_config, dict)
            else None
        )
        context_label_prefix = "run.chummer.build-context."
        context_label_suffix = ".sha256"
        observed_context_digests = (
            {
                key[
                    len(context_label_prefix) : -len(context_label_suffix)
                ]: value
                for key, value in inspected_labels.items()
                if isinstance(key, str)
                and key.startswith(context_label_prefix)
                and key.endswith(context_label_suffix)
            }
            if isinstance(inspected_labels, dict)
            else {}
        )
        if (
            not isinstance(inspected_image, dict)
            or inspected_image.get("Id") != image_id
            or set(inspected_image.get("RepoTags") or [])
            != ({tag} if tag_present else set())
            or inspected_image.get("RepoDigests") not in (None, [])
            or not isinstance(inspected_labels, dict)
            or inspected_labels.get("org.opencontainers.image.revision")
            != config.source_head
            or inspected_labels.get("run.chummer.runtime-profile")
            != RUNTIME_PROFILE
            or observed_context_digests != planned_digests
        ):
            raise RecoveryUncertain(
                "candidate image inspection does not match its binding"
            )
        if recovered_from_plan:
            self._record(
                "candidate-image-recovered",
                "candidateImage",
                binding,
            )
        return {
            "disposition": "remove",
            "candidateTag": tag,
            "candidateImageId": image_id,
            "tagPresent": tag_present,
        }

    def _sidecar_container_references(
        self,
        config: SidecarConfig,
        candidate_image_id: str | None,
        *,
        allow_exact_project_containers: bool,
    ) -> list[str]:
        container_ids = self._strict_output_lines(
            self.runner.docker(
                [
                    "container",
                    "ls",
                    "--all",
                    "--quiet",
                    "--no-trunc",
                ],
                label="inventory containers for candidate image cleanup",
            ),
            label="container inventory",
        )
        if any(CONTAINER_ID.fullmatch(item) is None for item in container_ids):
            raise RecoveryUncertain("container inventory is malformed")
        project_references: list[str] = []
        project_services: set[str] = set()
        operation_volumes = set(config.volume_names.values())
        for container_id in container_ids:
            try:
                container_inspection = json.loads(
                    self.runner.docker(
                        ["container", "inspect", container_id],
                        label="inspect candidate image container reference",
                    )
                )
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise RecoveryUncertain(
                    "container inspection is malformed"
                ) from exc
            if (
                not isinstance(container_inspection, list)
                or len(container_inspection) != 1
                or not isinstance(container_inspection[0], dict)
                or container_inspection[0].get("Id") != container_id
                or IMAGE_ID.fullmatch(
                    str(container_inspection[0].get("Image") or "")
                )
                is None
                or not isinstance(
                    container_inspection[0].get("Mounts"),
                    list,
                )
            ):
                raise RecoveryUncertain(
                    "container inspection is ambiguous"
                )
            container = container_inspection[0]
            mounts = container["Mounts"]
            if any(
                not isinstance(mount, dict)
                or not isinstance(mount.get("Type"), str)
                or (
                    mount.get("Type") == "volume"
                    and not isinstance(mount.get("Name"), str)
                )
                for mount in mounts
            ):
                raise RecoveryUncertain(
                    "container mount inspection is ambiguous"
                )
            referenced_operation_volumes = [
                mount["Name"]
                for mount in mounts
                if mount.get("Type") == "volume"
                and mount.get("Name") in operation_volumes
            ]
            references_candidate = (
                candidate_image_id is not None
                and container.get("Image") == candidate_image_id
            )
            container_config = container.get("Config")
            labels = (
                container_config.get("Labels")
                if isinstance(container_config, dict)
                else None
            )
            service = (
                labels.get("com.docker.compose.service")
                if isinstance(labels, dict)
                else None
            )
            references_project = (
                isinstance(labels, dict)
                and labels.get("com.docker.compose.project")
                == config.project_name
            )
            if (
                not references_candidate
                and not referenced_operation_volumes
                and not references_project
            ):
                continue
            if (
                not allow_exact_project_containers
                or not isinstance(labels, dict)
                or labels.get("com.docker.compose.project")
                != config.project_name
                or labels.get("com.docker.compose.project.config_files")
                != str(config.compose_file)
                or labels.get("com.docker.compose.project.working_dir")
                != str(config.operation_root)
                or labels.get("com.docker.compose.oneoff") != "False"
                or labels.get("com.docker.compose.container-number") != "1"
                or service
                not in {"chummer-public-download-init", PORTAL_SERVICE}
                or service in project_services
                or not references_candidate
                or len(referenced_operation_volumes)
                != len(operation_volumes)
                or set(referenced_operation_volumes) != operation_volumes
            ):
                raise RecoveryUncertain(
                    "sidecar image or volume has a foreign or ambiguous "
                    "container reference"
                )
            project_services.add(service)
            project_references.append(container_id)
        return sorted(project_references)

    def _prove_sidecar_resources_unreferenced(
        self,
        config: SidecarConfig,
        preflight: Mapping[str, Any],
    ) -> None:
        candidate_image_id = preflight.get("candidateImageId")
        if candidate_image_id is not None and (
            not isinstance(candidate_image_id, str)
            or IMAGE_ID.fullmatch(candidate_image_id) is None
        ):
            raise RecoveryUncertain(
                "candidate image cleanup identity is malformed"
            )
        self._sidecar_container_references(
            config,
            candidate_image_id,
            allow_exact_project_containers=False,
        )

    def _prove_zero_sidecar_project_networks(
        self,
        config: SidecarConfig,
        *,
        phase: str,
    ) -> None:
        checks = (
            (
                "project-labeled",
                [
                    "network",
                    "ls",
                    "--quiet",
                    "--no-trunc",
                    "--filter",
                    "label=com.docker.compose.project="
                    f"{config.project_name}",
                ],
            ),
            (
                "default-name",
                [
                    "network",
                    "ls",
                    "--quiet",
                    "--no-trunc",
                    "--filter",
                    "name=^"
                    f"{re.escape(config.project_name + '_default')}$",
                ],
            ),
        )
        for scope, arguments in checks:
            network_ids = self._strict_output_lines(
                self.runner.docker(
                    arguments,
                    label=(
                        f"prove zero {scope} topology-B networks "
                        f"{phase}"
                    ),
                ),
                label=f"{scope} topology-B network inventory",
            )
            if any(
                CONTAINER_ID.fullmatch(network_id) is None
                for network_id in network_ids
            ):
                raise RecoveryUncertain(
                    "topology-B network inventory is malformed"
                )
            if network_ids:
                raise RecoveryUncertain(
                    "topology-B project network deletion scope is not empty"
                )

    def _remove_candidate_image(
        self,
        preflight: Mapping[str, Any],
    ) -> dict[str, Any]:
        if preflight.get("disposition") != "remove":
            return dict(preflight)
        tag = str(preflight["candidateTag"])
        image_id = str(preflight["candidateImageId"])
        tag_image_ids = self._strict_output_lines(
            self.runner.docker(
                ["image", "ls", "--quiet", "--no-trunc", tag],
                label="recheck exact candidate image tag before removal",
            ),
            label="candidate image tag recheck",
        )
        if preflight.get("tagPresent") is True:
            if set(tag_image_ids) != {image_id}:
                raise RecoveryUncertain(
                    "candidate image tag changed after cleanup preflight"
                )
        elif tag_image_ids:
            raise RecoveryUncertain(
                "candidate image tag reappeared after cleanup preflight"
            )
        self.runner.docker(
            ["image", "rm", image_id],
            label="remove exact unused candidate image",
        )
        remaining_ids = self._strict_output_lines(
            self.runner.docker(
                ["image", "ls", "--all", "--quiet", "--no-trunc"],
                label="verify candidate image removal",
            ),
            label="post-cleanup local image inventory",
        )
        remaining_tag_ids = self._strict_output_lines(
            self.runner.docker(
                ["image", "ls", "--quiet", "--no-trunc", tag],
                label="verify candidate image tag removal",
            ),
            label="post-cleanup candidate image tag",
        )
        if (
            any(IMAGE_ID.fullmatch(item) is None for item in remaining_ids)
            or remaining_tag_ids
            or image_id in remaining_ids
        ):
            raise RecoveryUncertain(
                "candidate image removal could not be verified"
            )
        return {
            "disposition": "removed",
            "candidateTag": tag,
            "candidateImageId": image_id,
        }

    def _require_retirement_cleanup_connector_gate(
        self,
        config: SidecarConfig,
        receipts: Mapping[str, Any],
    ) -> None:
        restoration = receipts.get("cloudflareRetirement")
        retired_authority = receipts.get("retiredAuthority")
        if (
            not isinstance(restoration, Mapping)
            or not isinstance(retired_authority, Mapping)
            or config.active_runtime_authority.exists()
            or config.active_runtime_authority.is_symlink()
        ):
            raise RecoveryUncertain(
                "retirement cleanup lacks retired marker authority"
            )
        retired_raw, _active, retired_path = (
            self._load_retirement_authority(config)
        )
        retired_authority_sha256 = sha256_bytes(retired_raw)
        if (
            retired_path != config.retired_active_authority
            or retired_authority.get("activeAuthoritySha256")
            != retired_authority_sha256
        ):
            raise RecoveryUncertain(
                "retirement cleanup retired authority drifted"
            )
        try:
            marker_connector_gate = (
                self.cloudflare
                .validate_current_connector_convergence_receipt(
                    receipts.get("retirementConnectorGate")
                )
            )
        except Exception as exc:
            raise RecoveryUncertain(
                "retirement cleanup lacks marker connector proof"
            ) from exc
        restored_version = restoration.get("restoredVersion")
        marker_connector_gate_sha256 = (
            self.cloudflare.canonical_sha256(marker_connector_gate)
        )
        if (
            type(restored_version) is not int
            or restored_version < 0
            or marker_connector_gate.get("targetVersion")
            != restored_version
            or retired_authority.get("connectorGateSha256")
            != marker_connector_gate_sha256
        ):
            raise RecoveryUncertain(
                "retirement cleanup marker connector proof drifted"
            )
        self._validated_retirement_connector_boundary(
            receipts.get("retirementPostMarkerConnectorGate"),
            config=config,
            boundary="post-marker",
            restored_version=restored_version,
            retired_authority_sha256=retired_authority_sha256,
            marker_connector_gate_sha256=(
                marker_connector_gate_sha256
            ),
        )
        resume_gate = receipts.get("retirementConnectorResumeGate")
        if resume_gate is not None:
            self._validated_retirement_connector_boundary(
                resume_gate,
                config=config,
                boundary="resume-post-marker",
                restored_version=restored_version,
                retired_authority_sha256=retired_authority_sha256,
                marker_connector_gate_sha256=(
                    marker_connector_gate_sha256
                ),
            )

    def cleanup_sidecar_resources(
        self,
        config: SidecarConfig,
        *_args: Any,
    ) -> dict[str, Any]:
        receipts = self._state.get("receipts")
        if not isinstance(receipts, dict):
            raise RecoveryUncertain("topology-B operation receipts are malformed")
        if getattr(config, "operation", None) == RETIRE_OPERATION:
            self._require_retirement_cleanup_connector_gate(
                config,
                receipts,
            )
        runtime = receipts.get("runtime")
        if runtime is not None and not isinstance(runtime, dict):
            raise RecoveryUncertain("topology-B runtime receipt is malformed")
        cleanup_config = config
        if (
            getattr(config, "operation", None) == RETIRE_OPERATION
            and runtime is not None
        ):
            environment = runtime.get("environment")
            required = {
                "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SOURCE": "path",
                "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256": "digest",
                "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": "path",
                "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256": "digest",
                "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": "path",
                "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256": "digest",
                "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE": "path",
                "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256": "digest",
            }
            if not isinstance(environment, dict):
                raise RecoveryUncertain(
                    "retirement runtime environment is unavailable"
                )
            selected: dict[str, str] = {}
            for name, kind in required.items():
                value = environment.get(name)
                if (
                    not isinstance(value, str)
                    or not value
                    or value != value.strip()
                    or "\x00" in value
                    or "\r" in value
                    or "\n" in value
                ):
                    raise RecoveryUncertain(
                        "retirement runtime input authority is malformed"
                    )
                if kind == "digest":
                    if SHA256.fullmatch(value) is None:
                        raise RecoveryUncertain(
                            "retirement runtime input digest is malformed"
                        )
                else:
                    candidate = Path(value)
                    if (
                        not candidate.is_absolute()
                        or any(part in {"", ".", ".."} for part in candidate.parts)
                        or str(candidate) != value
                    ):
                        raise RecoveryUncertain(
                            "retirement runtime input path is malformed"
                        )
                selected[name] = value
            cleanup_config = dataclass_replace(
                config,
                operation=CUTOVER_OPERATION,
                fleet_source=Path(
                    selected["CHUMMER_PUBLIC_DOWNLOAD_FLEET_SOURCE"]
                ),
                fleet_sha256=selected[
                    "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256"
                ],
                projection_snapshot_root=Path(
                    selected[
                        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT"
                    ]
                ),
                projection_source_tree_sha256=selected[
                    "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256"
                ],
                runtime_proof_source=Path(
                    selected[
                        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE"
                    ]
                ),
                runtime_proof_sha256=selected[
                    "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256"
                ],
                final_gold_source=Path(
                    selected["CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE"]
                ),
                final_gold_sha256=selected[
                    "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256"
                ],
            )
        pre_runtime_absence: dict[str, Any] | None = None
        if runtime is not None:
            environment, rendered_compose_sha256 = (
                self._validated_runtime_environment(
                    cleanup_config,
                    runtime,
                    receipts,
                    historical_source=(
                        getattr(config, "operation", None)
                        == RETIRE_OPERATION
                    ),
                )
            )
        else:
            environment = None
            rendered_compose_sha256 = None
            pre_runtime_absence = self._prove_pre_runtime_absence(cleanup_config)
        candidate_preflight = self._preflight_candidate_image(cleanup_config)
        candidate_image_id = candidate_preflight.get("candidateImageId")
        self._sidecar_container_references(
            cleanup_config,
            (
                str(candidate_image_id)
                if candidate_image_id is not None
                else None
            ),
            allow_exact_project_containers=runtime is not None,
        )
        self._prove_zero_sidecar_project_networks(
            cleanup_config,
            phase="before cleanup",
        )
        if runtime is not None:
            if environment is None or rendered_compose_sha256 is None:
                raise RecoveryUncertain(
                    "topology-B runtime Compose authority is unavailable"
                )
            compose_disposition = "remove"
        else:
            environment = None
            compose_disposition = "not-created"
        removable: list[str] = []
        for logical, name in cleanup_config.volume_names.items():
            listed = self.runner.docker(
                [
                    "volume",
                    "ls",
                    "--quiet",
                    "--filter",
                    f"name=^{name}$",
                ],
                label="resolve exact topology-B volume",
            )
            listed_names = self._strict_output_lines(
                listed,
                label="exact topology-B volume",
            )
            if not listed_names:
                continue
            if set(listed_names) != {name}:
                raise RecoveryUncertain(
                    "topology-B volume resolution is ambiguous"
                )
            try:
                inspection = json.loads(
                    self.runner.docker(
                        ["volume", "inspect", name],
                        label="inspect exact topology-B volume",
                    )
                )
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise RecoveryUncertain(
                    "topology-B volume inspection is malformed"
                ) from exc
            try:
                self._validated_sidecar_volume_authority(
                    inspection,
                    config=cleanup_config,
                    logical=logical,
                    name=name,
                )
            except RecoveryUncertain as exc:
                raise RecoveryUncertain(
                    "topology-B volume identity is ambiguous"
                ) from exc
            removable.append(name)
        if runtime is not None:
            self._prove_rendered_compose_unchanged(
                environment,
                rendered_compose_sha256,
            )
            self.runner.compose(
                ["down", "--remove-orphans"],
                environment=environment,
                label="remove exact topology-B sidecar project",
                timeout=600,
            )
            compose_disposition = "removed"
        self._prove_sidecar_resources_unreferenced(
            cleanup_config,
            candidate_preflight,
        )
        self._prove_zero_sidecar_project_networks(
            cleanup_config,
            phase="after cleanup",
        )
        removed: list[str] = []
        for name in removable:
            self.runner.docker(
                ["volume", "rm", name],
                label="remove exact topology-B volume",
            )
            remaining = self._strict_output_lines(
                self.runner.docker(
                    [
                        "volume",
                        "ls",
                        "--quiet",
                        "--filter",
                        f"name=^{name}$",
                    ],
                    label="verify exact topology-B volume removal",
                ),
                label="post-cleanup topology-B volume",
            )
            if remaining:
                raise RecoveryUncertain(
                    "topology-B volume removal could not be verified"
                )
            removed.append(name)
        candidate_image = self._remove_candidate_image(candidate_preflight)
        receipt = {
            "projectName": config.project_name,
            "composeDisposition": compose_disposition,
            "preRuntimeAbsence": pre_runtime_absence,
            "removedVolumes": removed,
            "candidateImage": candidate_image,
        }
        self._record("cleaned", "cleanup", receipt)
        return receipt

    def classify_recovery(self, config: SidecarConfig) -> str:
        if self.cloudflare.journal_path_present(
            config.cloudflare_committed_evidence
        ):
            try:
                committed = self.cloudflare.load_journal(
                    config.cloudflare_committed_evidence
                )
            except Exception as exc:
                raise RecoveryUncertain(
                    "committed Cloudflare evidence is invalid"
                ) from exc
            if committed.get("phase") != "committed":
                raise RecoveryUncertain(
                    "committed Cloudflare evidence is not terminal"
                )
            return "committed"
        if self.cloudflare.journal_path_present(config.cloudflare_journal):
            try:
                journal = self.cloudflare.load_journal(
                    config.cloudflare_journal
                )
            except Exception as exc:
                raise RecoveryUncertain(
                    "live Cloudflare journal is invalid"
                ) from exc
            if journal["phase"] == "committed":
                return "committed"
            if journal["phase"] == "rolled-back":
                return "rollback"
            if journal["phase"] not in {
                "captured",
                "apply-in-flight",
                "applied",
                "awaiting-external-probe",
                "rollback-in-flight",
            }:
                raise RecoveryUncertain(
                    "Cloudflare recovery journal phase is unsupported"
                )
        elif self._state.get("phase") in {
            "cloudflare-committed",
            "active",
        }:
            raise RecoveryUncertain(
                "operation recorded a committed route but terminal evidence is missing"
            )
        return "rollback"

    def reconcile_committed(
        self,
        config: SidecarConfig,
        *_args: Any,
    ) -> dict[str, Any]:
        receipt = self.cloudflare.commit_transaction(
            self._cloudflare_api(),
            journal_path=config.cloudflare_journal,
            lock_path=config.cloudflare_lock,
            evidence_path=config.cloudflare_committed_evidence,
            external_probe_receipt=(
                config.external_probe_receipt
                if config.external_probe_receipt.is_file()
                else None
            ),
        )
        active = self._state.get("receipts", {}).get("activeAuthority")
        shelf = self._state.get("receipts", {}).get("shelf")
        runtime = self._state.get("receipts", {}).get("runtime")
        sidecar = self._state.get("receipts", {}).get("sidecar")
        commit = self._state.get("receipts", {}).get("cloudflareCommit")
        if not isinstance(commit, dict):
            commit = {
                "phase": receipt["phase"],
                "targetConfigSha256": receipt[
                    "targetConfigSha256"
                ],
                "targetVersion": receipt["targetVersion"],
                "evidencePath": str(
                    config.cloudflare_committed_evidence
                ),
                "evidenceSha256": sha256_bytes(
                    stable_regular_bytes(
                        config.cloudflare_committed_evidence,
                        label="committed Cloudflare evidence",
                        maximum_bytes=16 * 1024 * 1024,
                        owner_only=True,
                    )
                ),
            }
        if not all(
            isinstance(item, dict)
            for item in (shelf, runtime, sidecar, commit)
        ):
            raise RecoveryUncertain(
                "committed route lacks reconstructable active authority"
            )
        current_runtime = container_runtime(
            self.runner,
            str(sidecar.get("containerId") or ""),
        )
        if (
            not current_runtime["wasRunning"]
            or current_runtime["imageId"]
            != runtime.get("candidateImageId")
        ):
            raise RecoveryUncertain(
                "committed sidecar runtime is not exact and running"
            )
        wait_healthy(
            self.runner,
            str(sidecar["containerId"]),
            expected_image=str(runtime["candidateImageId"]),
            timeout_seconds=self.config.ready_timeout_seconds,
        )
        probe_sidecar_hosts(
            self.config,
            shelf=shelf,
            generation_id=str(shelf["generationId"]),
            generation_root=Path(str(shelf["generationRoot"])),
        )
        probe_download_artifact_hosts(
            self.config,
            shelf=shelf,
            scope="public",
        )
        manifest = stable_regular_bytes(
            Path(str(shelf["generationRoot"])) / "releases.json",
            label="recovery generation compatibility manifest",
            maximum_bytes=8 * 1024 * 1024,
        )
        path = (
            f"/downloads/g/{shelf['generationId']}/releases.json"
        )
        for hostname in SIDECAR_HOSTS:
            _probe_exact_manifest(
                scheme="https",
                connect_host=hostname,
                connect_port=443,
                request_host=hostname,
                path=path,
                expected=manifest,
                shelf=shelf,
                generation_id=str(shelf["generationId"]),
            )
        if not isinstance(active, dict):
            active = self.write_active_receipt(
                config,
                shelf,
                runtime,
                sidecar,
                commit,
            )
        return {"cloudflarePhase": receipt["phase"], "active": active}


def execute_topology_b(
    config: SidecarConfig,
    actions: TopologyBActionsProtocol | None = None,
) -> dict[str, Any]:
    action_boundary = actions if actions is not None else TopologyBActions(config)
    cloudflare_committed = False
    cloudflare_transaction_started = False
    try:
        shelf = action_boundary.prepare_sidecar_release_shelf(config)
        data_protection = action_boundary.generate_sidecar_data_protection(
            config
        )
        runtime = action_boundary.materialize_sidecar_compose(
            config,
            shelf,
            data_protection,
        )
        resources = action_boundary.create_sidecar_resources(
            config,
            runtime,
        )
        sidecar = action_boundary.start_sidecar_runtime(
            config,
            runtime,
            resources,
        )
        health = action_boundary.wait_sidecar_healthy(
            config,
            runtime,
            sidecar,
        )
        local_probe = action_boundary.probe_sidecar_hosts(
            config,
            shelf,
            runtime,
            sidecar,
            hosts=SIDECAR_HOSTS,
            scope="local",
        )
        incumbent = action_boundary.probe_public_incumbent(
            config,
            phase="before-cloudflare",
            hosts=SIDECAR_HOSTS,
        )
        cloudflare_transaction_started = True
        capture = action_boundary.capture_cloudflare(
            config,
            shelf,
            runtime,
            sidecar,
            local_probe,
            incumbent,
        )
        applied = action_boundary.apply_cloudflare(
            config,
            capture,
        )
        public_probe = action_boundary.probe_sidecar_hosts(
            config,
            shelf,
            runtime,
            sidecar,
            applied,
            hosts=SIDECAR_HOSTS,
            scope="public",
        )
        committed = action_boundary.commit_cloudflare(
            config,
            applied,
            public_probe,
        )
        cloudflare_committed = True
        active = action_boundary.write_active_receipt(
            config,
            shelf,
            runtime,
            sidecar,
            committed,
            health,
            local_probe,
            public_probe,
        )
        return {
            "contractName": TOPOLOGY_B_CONTRACT,
            "status": "pass",
            "operation": config.operation,
            "projectName": config.project_name,
            "sourceHead": getattr(config, "source_head", ""),
            "shelf": shelf,
            "dataProtection": data_protection,
            "runtime": runtime,
            "resources": resources,
            "sidecar": sidecar,
            "health": health,
            "localProbe": local_probe,
            "cloudflareCapture": capture,
            "cloudflareApply": applied,
            "publicProbe": public_probe,
            "cloudflareCommit": committed,
            "activeAuthority": active,
            "incumbentPortalStopped": False,
            "incumbentTunnelStopped": False,
            "canonicalShelfMutated": False,
        }
    except Exception as original:
        if cloudflare_committed:
            evidence_error: Exception | None = None
            try:
                action_boundary.record_primary_failure(config, original)
            except Exception as error:
                evidence_error = error
            suffix = (
                "; primary failure evidence could not be retained"
                if evidence_error is not None
                else ""
            )
            raise RecoveryUncertain(
                "Cloudflare committed; active authority requires "
                f"reconciliation{suffix}"
            ) from (evidence_error or original)
        if not cloudflare_transaction_started:
            try:
                action_boundary.record_primary_failure(config, original)
            except Exception as evidence_error:
                raise RecoveryUncertain(
                    "topology-B primary failure evidence could not be retained"
                ) from evidence_error
            try:
                action_boundary.cleanup_sidecar_resources(config)
            except Exception as cleanup_error:
                raise RecoveryUncertain(
                    "pre-Cloudflare sidecar cleanup is uncertain; "
                    "primary failure evidence was retained"
                ) from cleanup_error
            raise CutoverError(
                "topology-B cutover failed before Cloudflare mutation"
            ) from original
        try:
            action_boundary.rollback_cloudflare(config)
            action_boundary.probe_public_incumbent(
                config,
                phase="after-rollback",
                hosts=SIDECAR_HOSTS,
            )
        except Exception as recovery_error:
            try:
                action_boundary.record_primary_failure(config, original)
            except Exception:
                pass
            raise RecoveryUncertain(
                "topology-B rollback or incumbent verification is uncertain"
            ) from recovery_error
        evidence_error = None
        try:
            action_boundary.record_primary_failure(config, original)
        except Exception as error:
            evidence_error = error
        try:
            action_boundary.cleanup_sidecar_resources(config)
        except Exception as cleanup_error:
            suffix = (
                "; primary failure evidence could not be retained"
                if evidence_error is not None
                else "; primary failure evidence was retained"
            )
            raise RecoveryUncertain(
                "topology-B failed after exact rollback but sidecar cleanup "
                f"is uncertain{suffix}"
            ) from cleanup_error
        if evidence_error is not None:
            raise RecoveryUncertain(
                "topology-B failed after exact rollback and cleanup; "
                "primary failure evidence could not be retained"
            ) from evidence_error
        raise CutoverError(
            "topology-B cutover failed after exact rollback"
        ) from original


def recover_topology_b(
    config: SidecarConfig,
    actions: TopologyBActionsProtocol | None = None,
) -> dict[str, Any]:
    action_boundary = actions if actions is not None else TopologyBActions(config)
    try:
        disposition = action_boundary.classify_recovery(config)
        if disposition == "committed":
            reconciliation = action_boundary.reconcile_committed(config)
            return {
                "contractName": TOPOLOGY_B_CONTRACT,
                "status": "pass",
                "operation": config.operation,
                "disposition": "committed-sidecar-reconciled",
                "reconciliation": reconciliation,
            }
        if disposition != "rollback":
            raise RecoveryUncertain(
                "topology-B recovery disposition is unsupported"
            )
        rollback = action_boundary.rollback_cloudflare(config)
        incumbent = action_boundary.probe_public_incumbent(
            config,
            phase="after-rollback",
            hosts=SIDECAR_HOSTS,
        )
        cleanup = action_boundary.cleanup_sidecar_resources(config)
        return {
            "contractName": TOPOLOGY_B_CONTRACT,
            "status": "pass",
            "operation": config.operation,
            "disposition": "rolled-back-to-incumbent",
            "cloudflareRollback": rollback,
            "incumbent": incumbent,
            "cleanup": cleanup,
        }
    except RecoveryUncertain:
        raise
    except Exception as exc:
        raise RecoveryUncertain(
            "topology-B recovery could not establish exact state"
        ) from exc


def _topology_b_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _topology_b_canonical_sha256(value: Any) -> str:
    return sha256_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    )


def _topology_b_utc_timestamp(value: Any, *, label: str) -> datetime:
    if (
        type(value) is not str
        or TOPOLOGY_B_CANONICAL_UTC_TIMESTAMP.fullmatch(value) is None
    ):
        raise RecoveryUncertain(f"{label} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(
            value.removesuffix("Z") + "+00:00"
        )
    except ValueError as exc:
        raise RecoveryUncertain(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise RecoveryUncertain(f"{label} is not UTC")
    return parsed.astimezone(UTC)


def _topology_b_is_commit(value: Any) -> bool:
    return type(value) is str and COMMIT.fullmatch(value) is not None


def _topology_b_is_sha256(value: Any) -> bool:
    return type(value) is str and SHA256.fullmatch(value) is not None


def _topology_b_canonical_absolute_path(
    value: Any,
) -> PurePosixPath | None:
    if (
        type(value) is not str
        or not value.startswith("/")
        or value.startswith("//")
        or len(value) > 4096
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in value
        )
    ):
        return None
    candidate = PurePosixPath(value)
    if (
        not candidate.is_absolute()
        or candidate.as_posix() != value
        or any(part in {".", ".."} for part in candidate.parts)
    ):
        return None
    return candidate


def _topology_b_public_directory(path: Path, *, create: bool) -> Path:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise RecoveryUncertain(
            f"public retirement proof directory path is unsafe: {path}"
        )
    parent_descriptor: int | None = None
    directory_descriptor: int | None = None
    created = False
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        if create:
            parent_descriptor = os.open(path.parent, directory_flags)
            parent_metadata = os.fstat(parent_descriptor)
            parent_named_metadata = path.parent.lstat()
            if (
                not stat.S_ISDIR(parent_metadata.st_mode)
                or parent_metadata.st_uid != os.getuid()
                or stat.S_IMODE(parent_metadata.st_mode) & 0o022
                or (
                    parent_metadata.st_dev,
                    parent_metadata.st_ino,
                )
                != (
                    parent_named_metadata.st_dev,
                    parent_named_metadata.st_ino,
                )
                or path.parent.resolve(strict=True) != path.parent
            ):
                raise RecoveryUncertain(
                    "public retirement proof parent directory is unsafe: "
                    f"{path.parent}"
                )
            try:
                os.mkdir(path.name, mode=0o755, dir_fd=parent_descriptor)
                created = True
            except FileExistsError:
                pass
            directory_descriptor = os.open(
                path.name,
                directory_flags,
                dir_fd=parent_descriptor,
            )
        else:
            directory_descriptor = os.open(path, directory_flags)

        if created:
            # The descriptor was opened with O_DIRECTORY|O_NOFOLLOW. Even if
            # the name is raced after mkdir, fchmod can never follow a symlink.
            os.fchmod(directory_descriptor, 0o755)
        metadata = os.fstat(directory_descriptor)
        named_metadata = path.lstat()
        resolved = path.resolve(strict=True)
        if (
            resolved != path
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (
                metadata.st_dev,
                metadata.st_ino,
            )
            != (
                named_metadata.st_dev,
                named_metadata.st_ino,
            )
            or (create and stat.S_IMODE(metadata.st_mode) != 0o755)
        ):
            raise RecoveryUncertain(
                f"public retirement proof directory is unsafe: {path}"
            )
        if created:
            os.fsync(directory_descriptor)
            if parent_descriptor is None:
                raise RecoveryUncertain(
                    "public retirement proof parent descriptor is missing"
                )
            os.fsync(parent_descriptor)
    except OSError as exc:
        raise RecoveryUncertain(
            f"public retirement proof directory is unavailable: {path}"
        ) from exc
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    return path


def _topology_b_public_directory_descriptor(path: Path) -> int:
    _topology_b_public_directory(path, create=False)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        named_metadata = path.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (
                metadata.st_dev,
                metadata.st_ino,
            )
            != (
                named_metadata.st_dev,
                named_metadata.st_ino,
            )
            or path.resolve(strict=True) != path
        ):
            raise RecoveryUncertain(
                f"public retirement proof directory changed: {path}"
            )
        return descriptor
    except BaseException:
        if "descriptor" in locals():
            os.close(descriptor)
        raise


def _stable_public_retirement_entry(
    directory_descriptor: int,
    name: str,
    *,
    maximum_bytes: int,
) -> bytes | None:
    if (
        not isinstance(name, str)
        or not name
        or Path(name).name != name
        or "/" in name
        or "\x00" in name
    ):
        raise RecoveryUncertain(
            "public retirement proof entry name is unsafe"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(
            name,
            flags,
            dir_fd=directory_descriptor,
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RecoveryUncertain(
            f"public retirement proof entry is unsafe: {name}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o444
            or before.st_size < 1
            or before.st_size > maximum_bytes
        ):
            raise RecoveryUncertain(
                f"public retirement proof entry metadata drifted: {name}"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise RecoveryUncertain(
                    f"public retirement proof entry was truncated: {name}"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise RecoveryUncertain(
                f"public retirement proof entry grew while read: {name}"
            )
        after = os.fstat(descriptor)
        named = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_uid,
            value.st_gid,
            value.st_nlink,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if identity(before) != identity(after) or identity(after) != identity(
            named
        ):
            raise RecoveryUncertain(
                f"public retirement proof entry changed while read: {name}"
            )
        return b"".join(chunks)
    except OSError as exc:
        raise RecoveryUncertain(
            f"public retirement proof entry changed while read: {name}"
        ) from exc
    finally:
        os.close(descriptor)


def _rename_public_retirement_noreplace(
    directory_descriptor: int,
    source_name: str,
    target_name: str,
) -> bool:
    """Atomically publish one single-link entry without replacing a winner."""

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            rename_noreplace = libc.renameatx_np
            rename_noreplace.argtypes = (
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            rename_noreplace.restype = ctypes.c_int
            result = rename_noreplace(
                directory_descriptor,
                os.fsencode(source_name),
                directory_descriptor,
                os.fsencode(target_name),
                0x00000004,  # RENAME_EXCL
            )
        else:
            rename_noreplace = libc.renameat2
            rename_noreplace.argtypes = (
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            rename_noreplace.restype = ctypes.c_int
            result = rename_noreplace(
                directory_descriptor,
                os.fsencode(source_name),
                directory_descriptor,
                os.fsencode(target_name),
                1,  # RENAME_NOREPLACE
            )
    except (AttributeError, OSError) as exc:
        raise RecoveryUncertain(
            "atomic no-replace publication is unavailable"
        ) from exc
    if result == 0:
        return True
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        return False
    raise RecoveryUncertain(
        "atomic no-replace public retirement publication failed"
    ) from OSError(error_number, os.strerror(error_number))


def _atomic_public_retirement_write(
    path: Path,
    value: bytes,
    *,
    replace: bool,
) -> None:
    if not isinstance(value, bytes) or not value:
        raise RecoveryUncertain(
            "public retirement proof bytes are empty or malformed"
        )
    directory_descriptor = _topology_b_public_directory_descriptor(
        path.parent
    )
    temporary_name = (
        f".{path.name}.{secrets.token_hex(16)}.staging"
    )
    temporary_created = False
    try:
        existing = _stable_public_retirement_entry(
            directory_descriptor,
            path.name,
            maximum_bytes=16 * 1024 * 1024,
        )
        if existing is not None and not replace:
            if existing != value:
                raise RecoveryUncertain(
                    "content-addressed public retirement proof drifted: "
                    f"{path.name}"
                )
            return

        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        temporary_created = True
        try:
            view = memoryview(value)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise RecoveryUncertain(
                        "public retirement proof staging write was short"
                    )
                view = view[written:]
            os.fchmod(descriptor, 0o444)
            staged = os.fstat(descriptor)
            if (
                not stat.S_ISREG(staged.st_mode)
                or staged.st_uid != os.getuid()
                or staged.st_nlink != 1
                or stat.S_IMODE(staged.st_mode) != 0o444
                or staged.st_size != len(value)
            ):
                raise RecoveryUncertain(
                    "public retirement proof staging metadata drifted"
                )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        if replace:
            try:
                named = os.stat(
                    path.name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                named = None
            if named is not None and (
                not stat.S_ISREG(named.st_mode)
                or named.st_uid != os.getuid()
                or named.st_nlink != 1
                or stat.S_IMODE(named.st_mode) != 0o444
            ):
                raise RecoveryUncertain(
                    "public retirement proof replacement target drifted: "
                    f"{path.name}"
                )
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            temporary_created = False
        else:
            renamed = _rename_public_retirement_noreplace(
                directory_descriptor,
                temporary_name,
                path.name,
            )
            if renamed:
                temporary_created = False
            else:
                winner = _stable_public_retirement_entry(
                    directory_descriptor,
                    path.name,
                    maximum_bytes=16 * 1024 * 1024,
                )
                if winner != value:
                    raise RecoveryUncertain(
                        "content-addressed public retirement proof race "
                        "did not preserve exact bytes"
                    )

        if temporary_created:
            os.unlink(temporary_name, dir_fd=directory_descriptor)
            temporary_created = False
        os.fsync(directory_descriptor)
        observed = _stable_public_retirement_entry(
            directory_descriptor,
            path.name,
            maximum_bytes=16 * 1024 * 1024,
        )
        if observed != value:
            raise RecoveryUncertain(
                f"public retirement proof publication drifted: {path.name}"
            )
        directory_metadata = os.fstat(directory_descriptor)
        named_directory = path.parent.lstat()
        if (
            directory_metadata.st_dev,
            directory_metadata.st_ino,
        ) != (
            named_directory.st_dev,
            named_directory.st_ino,
        ):
            raise RecoveryUncertain(
                "public retirement proof directory changed during publication"
            )
    except OSError as exc:
        raise RecoveryUncertain(
            f"public retirement proof publication failed: {path.name}"
        ) from exc
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
                os.fsync(directory_descriptor)
            except OSError:
                pass
        os.close(directory_descriptor)


def strict_public_retirement_get(
    url: str,
    *,
    maximum_bytes: int = 16 * 1024 * 1024,
) -> bytes:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "chummer.run"
        or parsed.hostname != "chummer.run"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/downloads/")
        or ".." in PurePosixPath(parsed.path).parts
    ):
        raise RecoveryUncertain(
            "public retirement proof readback URL is not canonical"
        )
    connection = http.client.HTTPSConnection(
        "chummer.run",
        443,
        timeout=30,
        context=ssl.create_default_context(),
    )
    try:
        connection.request(
            "GET",
            parsed.path,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": "chummer-topology-b-retirement-proof/1",
            },
        )
        response = connection.getresponse()
        if (
            response.status != 200
            or response.getheader("Location") is not None
            or response.getheader("Content-Encoding") not in (None, "identity")
        ):
            response.read(64 * 1024)
            raise RecoveryUncertain(
                "public retirement proof readback was not a direct "
                "identity-encoded HTTP 200"
            )
        value = response.read(maximum_bytes + 1)
        if not value or len(value) > maximum_bytes:
            raise RecoveryUncertain(
                "public retirement proof readback size is invalid"
            )
        declared = response.getheader("Content-Length")
        if declared is not None and (
            not declared.isascii()
            or not declared.isdigit()
            or int(declared) != len(value)
        ):
            raise RecoveryUncertain(
                "public retirement proof Content-Length drifted"
            )
        return value
    except (OSError, http.client.HTTPException) as exc:
        raise RecoveryUncertain(
            "public retirement proof readback failed"
        ) from exc
    finally:
        connection.close()


def validate_topology_b_public_retirement_bundle(
    *,
    proof_bytes: bytes,
    committed_boundary_bytes: bytes,
    post_marker_bytes: bytes,
    expected_source_head: str,
    expected_publisher_sha256: str,
    cloudflare: Any,
    now: datetime | None = None,
    allow_expired: bool = False,
) -> dict[str, Any]:
    if not _topology_b_is_commit(expected_source_head):
        raise RecoveryUncertain(
            "public retirement proof source authority is invalid"
        )
    if not _topology_b_is_sha256(expected_publisher_sha256):
        raise RecoveryUncertain(
            "public retirement proof publisher authority is invalid"
        )
    proof = _strict_json_object_bytes(
        proof_bytes,
        label="public topology-B retirement proof",
    )
    proof_fields = {
        "contractName",
        "contractVersion",
        "generatedAt",
        "status",
        "source",
        "sidecarAuthorityRetired",
        "activeSidecarMarkerCount",
        "activeSidecarMarkers",
        "retiredAuthoritySha256",
        "committedBoundaryReceipt",
        "postMarkerConvergenceReceipt",
        "canonicalAuthority",
    }
    if set(proof) != proof_fields:
        raise RecoveryUncertain(
            "public topology-B retirement proof fields drifted"
        )
    generated = _topology_b_utc_timestamp(
        proof.get("generatedAt"),
        label="public topology-B retirement generatedAt",
    )
    if type(allow_expired) is not bool:
        raise RecoveryUncertain(
            "public retirement proof expiry policy is malformed"
        )
    if now is None:
        observed_now = datetime.now(UTC)
    elif (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() != timedelta(0)
    ):
        raise RecoveryUncertain(
            "public retirement proof observation time is not UTC"
        )
    else:
        observed_now = now.astimezone(UTC)
    if generated > observed_now + timedelta(minutes=5) or (
        not allow_expired
        and observed_now - generated > timedelta(hours=24)
    ):
        raise RecoveryUncertain(
            "public topology-B retirement proof is stale or future-dated"
        )
    source = proof.get("source")
    if (
        any(
            type(proof.get(field)) is not str
            for field in (
                "contractName",
                "generatedAt",
                "status",
                "retiredAuthoritySha256",
            )
        )
        or proof.get("contractName")
        != TOPOLOGY_B_PUBLIC_RETIREMENT_CONTRACT
        or type(proof.get("contractVersion")) is not int
        or proof.get("contractVersion") != 1
        or proof.get("status") != "passed"
        or type(source) is not dict
        or set(source) != {"repository", "ref", "commit"}
        or any(
            type(source.get(field)) is not str
            for field in ("repository", "ref", "commit")
        )
        or source.get("repository") != TOPOLOGY_B_SOURCE_REPOSITORY
        or source.get("ref") != TOPOLOGY_B_SOURCE_REF
        or source.get("commit") != expected_source_head
        or proof.get("sidecarAuthorityRetired") is not True
        or type(proof.get("activeSidecarMarkerCount")) is not int
        or proof.get("activeSidecarMarkerCount") != 0
        or type(proof.get("activeSidecarMarkers")) is not list
        or proof.get("activeSidecarMarkers") != []
        or not _topology_b_is_sha256(
            proof.get("retiredAuthoritySha256")
        )
    ):
        raise RecoveryUncertain(
            "public topology-B retirement authority drifted"
        )

    def validate_binding(
        value: Any,
        raw: bytes,
        *,
        label: str,
    ) -> None:
        if (
            type(value) is not dict
            or set(value) != {"sha256", "sizeBytes"}
            or type(value.get("sha256")) is not str
            or value.get("sha256") != sha256_bytes(raw)
            or type(value.get("sizeBytes")) is not int
            or value["sizeBytes"] != len(raw)
            or value["sizeBytes"] <= 0
        ):
            raise RecoveryUncertain(
                f"public topology-B {label} binding drifted"
            )

    validate_binding(
        proof.get("committedBoundaryReceipt"),
        committed_boundary_bytes,
        label="committed boundary",
    )
    validate_binding(
        proof.get("postMarkerConvergenceReceipt"),
        post_marker_bytes,
        label="post-marker convergence",
    )
    terminal = _strict_json_object_bytes(
        committed_boundary_bytes,
        label="committed topology-B retirement boundary",
    )
    terminal_fields = {
        "contractName",
        "status",
        "operation",
        "operationRoot",
        "projectName",
        "operationSourceHead",
        "controllerSourceHead",
        "retiredAuthorityPath",
        "retiredAuthoritySha256",
        "retirementEvidencePath",
        "retirementEvidenceSha256",
        "connectorGateSha256",
        "postMarkerConnectorGateSha256",
        "latestConnectorGateSha256",
        "priorConfigSha256",
        "restoredVersion",
        "incumbentBaselineSha256",
        "incumbentObservationSha256",
        "cleanupSha256",
        "completedAtUtc",
    }
    terminal_string_fields = terminal_fields - {"restoredVersion"}
    operation_root = _topology_b_canonical_absolute_path(
        terminal.get("operationRoot")
    )
    retired_authority_path = _topology_b_canonical_absolute_path(
        terminal.get("retiredAuthorityPath")
    )
    retirement_evidence_path = _topology_b_canonical_absolute_path(
        terminal.get("retirementEvidencePath")
    )
    terminal_sha256_fields = (
        "retiredAuthoritySha256",
        "retirementEvidenceSha256",
        "connectorGateSha256",
        "postMarkerConnectorGateSha256",
        "latestConnectorGateSha256",
        "priorConfigSha256",
        "incumbentBaselineSha256",
        "incumbentObservationSha256",
        "cleanupSha256",
    )
    if (
        set(terminal) != terminal_fields
        or any(
            type(terminal.get(field)) is not str
            for field in terminal_string_fields
        )
        or terminal.get("contractName")
        != "chummer.public-download-committed-retirement/v1"
        or terminal.get("status") != "retired"
        or terminal.get("operation") != RETIRE_OPERATION
        or terminal.get("controllerSourceHead") != expected_source_head
        or not _topology_b_is_commit(
            terminal.get("operationSourceHead")
        )
        or not _topology_b_is_commit(
            terminal.get("controllerSourceHead")
        )
        or operation_root is None
        or type(terminal.get("projectName")) is not str
        or SIDECAR_PROJECT.fullmatch(terminal["projectName"]) is None
        or operation_root.name != terminal["projectName"]
        or retired_authority_path
        != operation_root / "retired-active-runtime-authority.json"
        or retirement_evidence_path
        != operation_root / "cloudflare-retirement-committed.json"
        or terminal.get("retiredAuthoritySha256")
        != proof.get("retiredAuthoritySha256")
        or type(terminal.get("restoredVersion")) is not int
        or terminal["restoredVersion"] < 0
        or any(
            not _topology_b_is_sha256(terminal.get(field))
            for field in terminal_sha256_fields
        )
    ):
        raise RecoveryUncertain(
            "committed topology-B retirement boundary drifted"
        )
    completed = _topology_b_utc_timestamp(
        terminal.get("completedAtUtc"),
        label="committed topology-B retirement completedAtUtc",
    )
    if completed > generated:
        raise RecoveryUncertain(
            "public topology-B retirement envelope predates terminal completion"
        )
    post_marker = _strict_json_object_bytes(
        post_marker_bytes,
        label="post-marker connector convergence receipt",
    )
    post_marker_fields = {
        "contractName",
        "status",
        "boundary",
        "operationRoot",
        "restoredVersion",
        "retiredAuthoritySha256",
        "markerConnectorGateSha256",
        "connectorConvergence",
        "connectorConvergenceSha256",
        "verifiedAtUtc",
    }
    if (
        set(post_marker) != post_marker_fields
        or any(
            type(post_marker.get(field)) is not str
            for field in (
                "contractName",
                "status",
                "boundary",
                "operationRoot",
                "retiredAuthoritySha256",
                "markerConnectorGateSha256",
                "connectorConvergenceSha256",
                "verifiedAtUtc",
            )
        )
        or post_marker.get("contractName")
        != "chummer.public-download-retirement-connector-boundary/v1"
        or post_marker.get("status") != "pass"
        or post_marker.get("boundary")
        not in {"post-marker", "resume-post-marker"}
        or post_marker.get("operationRoot")
        != terminal.get("operationRoot")
        or type(post_marker.get("restoredVersion")) is not int
        or post_marker.get("restoredVersion")
        != terminal.get("restoredVersion")
        or post_marker.get("retiredAuthoritySha256")
        != terminal.get("retiredAuthoritySha256")
        or post_marker.get("markerConnectorGateSha256")
        != terminal.get("connectorGateSha256")
        or not _topology_b_is_sha256(
            post_marker.get("retiredAuthoritySha256")
        )
        or not _topology_b_is_sha256(
            post_marker.get("markerConnectorGateSha256")
        )
        or not _topology_b_is_sha256(
            post_marker.get("connectorConvergenceSha256")
        )
        or type(post_marker.get("connectorConvergence")) is not dict
        or _topology_b_canonical_sha256(post_marker)
        != terminal.get("latestConnectorGateSha256")
    ):
        raise RecoveryUncertain(
            "post-marker connector convergence boundary drifted"
        )
    boundary = post_marker["boundary"]
    post_marker_sha256 = _topology_b_canonical_sha256(post_marker)
    original_post_marker_sha256 = terminal.get(
        "postMarkerConnectorGateSha256"
    )
    latest_post_marker_sha256 = terminal.get("latestConnectorGateSha256")
    if (
        boundary == "post-marker"
        and (
            post_marker_sha256 != original_post_marker_sha256
            or post_marker_sha256 != latest_post_marker_sha256
        )
    ):
        raise RecoveryUncertain(
            "original post-marker connector convergence digest drifted"
        )
    if (
        boundary == "resume-post-marker"
        and (
            post_marker_sha256 != latest_post_marker_sha256
            or post_marker_sha256 == original_post_marker_sha256
        )
    ):
        raise RecoveryUncertain(
            "resume post-marker connector convergence digest drifted"
        )
    try:
        convergence = (
            cloudflare.validate_current_connector_convergence_receipt(
                post_marker.get("connectorConvergence")
            )
        )
    except Exception as exc:
        raise RecoveryUncertain(
            "post-marker connector convergence authority is invalid"
        ) from exc
    if (
        convergence.get("targetVersion")
        != terminal.get("restoredVersion")
        or _topology_b_canonical_sha256(convergence)
        != post_marker.get("connectorConvergenceSha256")
    ):
        raise RecoveryUncertain(
            "post-marker connector convergence digest drifted"
        )
    post_marker_verified = _topology_b_utc_timestamp(
        post_marker.get("verifiedAtUtc"),
        label="post-marker connector convergence verifiedAtUtc",
    )
    if post_marker_verified > completed:
        raise RecoveryUncertain(
            "post-marker connector convergence is later than completion"
        )
    if (
        terminal.get("incumbentBaselineSha256")
        != terminal.get("incumbentObservationSha256")
    ):
        raise RecoveryUncertain(
            "committed topology-B incumbent observation differs from baseline"
        )
    canonical = proof.get("canonicalAuthority")
    if (
        type(canonical) is not dict
        or set(canonical)
        != {
            "baseUrl",
            "manifestUrl",
            "publisherPath",
            "publisherSha256",
        }
        or any(
            type(canonical.get(field)) is not str
            for field in (
                "baseUrl",
                "manifestUrl",
                "publisherPath",
                "publisherSha256",
            )
        )
        or canonical.get("baseUrl") != CANONICAL_DOWNLOADS_BASE_URL
        or canonical.get("manifestUrl")
        != CANONICAL_DOWNLOADS_MANIFEST_URL
        or canonical.get("publisherPath")
        != CANONICAL_DOWNLOADS_PUBLISHER_PATH
        or canonical.get("publisherSha256")
        != expected_publisher_sha256
    ):
        raise RecoveryUncertain(
            "public topology-B canonical publisher authority drifted"
        )
    return proof


def _topology_b_require_git_ancestor(
    source_root: Path,
    ancestor: str,
    descendant: str,
) -> None:
    if (
        not _topology_b_is_commit(ancestor)
        or not _topology_b_is_commit(descendant)
    ):
        raise RecoveryUncertain(
            "public topology-B source ancestry is malformed"
        )
    try:
        result = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(source_root),
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
            ],
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoveryUncertain(
            "public topology-B source ancestry could not be verified"
        ) from exc
    if result.returncode != 0:
        raise RecoveryUncertain(
            "terminal topology-B source is not an ancestor of "
            "the current protected source"
        )


def materialize_topology_b_public_retirement_proof(
    config: SidecarConfig,
    retirement_result: Mapping[str, Any],
    *,
    public_reader: Callable[[str], bytes] | None = None,
    attempts: int = 30,
    sleep_fn: Callable[[float], None] = time.sleep,
    interval_seconds: float = 2.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    if config.operation != RETIRE_OPERATION:
        raise RecoveryUncertain(
            "public topology-B retirement proof requires retirement"
        )
    materializer_source_head = (
        config.controller_source_head or config.source_head
    )
    terminal_source_head = (
        retirement_result.get("controllerSourceHead")
        if isinstance(retirement_result, Mapping)
        else None
    )
    if (
        not _topology_b_is_commit(materializer_source_head)
        or not _topology_b_is_commit(terminal_source_head)
        or not _topology_b_is_sha256(
            config.canonical_publisher_sha256
        )
        or config.base_url.rstrip("/") != "https://chummer.run"
        or not isinstance(retirement_result, Mapping)
        or retirement_result.get("status") != "pass"
        or retirement_result.get("operation") != RETIRE_OPERATION
        or retirement_result.get("disposition")
        != "committed-sidecar-retired-to-incumbent"
    ):
        raise RecoveryUncertain(
            "public topology-B retirement proof inputs are invalid"
        )
    try:
        observed_source_head = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(config.source_root),
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ],
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoveryUncertain(
            "public topology-B retirement source could not be verified"
        ) from exc
    if observed_source_head != materializer_source_head:
        raise RecoveryUncertain(
            "public topology-B retirement source HEAD drifted"
        )
    _topology_b_require_git_ancestor(
        config.source_root,
        terminal_source_head,
        materializer_source_head,
    )
    if (
        config.active_runtime_authority.exists()
        or config.active_runtime_authority.is_symlink()
    ):
        raise RecoveryUncertain(
            "public topology-B retirement proof found an active sidecar marker"
        )
    terminal_bytes = stable_regular_bytes(
        config.retirement_receipt,
        label="terminal topology-B retirement receipt",
        maximum_bytes=16 * 1024 * 1024,
        owner_only=True,
    )
    terminal = _strict_json_object_bytes(
        terminal_bytes,
        label="terminal topology-B retirement receipt",
    )
    if not _json_semantically_equal(
        retirement_result.get("terminalReceipt"),
        terminal,
    ):
        raise RecoveryUncertain(
            "public topology-B retirement result is not terminal-bound"
        )
    journal_bytes = stable_regular_bytes(
        config.operation_journal,
        label="terminal topology-B operation journal",
        maximum_bytes=16 * 1024 * 1024,
        owner_only=True,
    )
    journal = _strict_json_object_bytes(
        journal_bytes,
        label="terminal topology-B operation journal",
    )
    receipts = journal.get("receipts")
    post_marker = None
    original_post_marker = None
    if type(receipts) is dict:
        original_post_marker = receipts.get(
            "retirementPostMarkerConnectorGate"
        )
        post_marker = receipts.get(
            "retirementConnectorResumeGate",
            original_post_marker,
        )
    if (
        journal.get("schema") != TOPOLOGY_B_OPERATION_SCHEMA
        or journal.get("phase") != "retired"
        or journal.get("operation") != CUTOVER_OPERATION
        or type(receipts) is not dict
        or not _json_semantically_equal(
            receipts.get("retirement"),
            terminal,
        )
        or type(original_post_marker) is not dict
        or type(post_marker) is not dict
    ):
        raise RecoveryUncertain(
            "public topology-B retirement journal authority drifted"
        )
    retired_authority_bytes = stable_regular_bytes(
        config.retired_active_authority,
        label="retired topology-B runtime authority",
        maximum_bytes=1024 * 1024,
        owner_only=True,
    )
    if sha256_bytes(retired_authority_bytes) != terminal.get(
        "retiredAuthoritySha256"
    ):
        raise RecoveryUncertain(
            "public topology-B retired authority digest drifted"
        )
    post_marker_bytes = _topology_b_json_bytes(post_marker)
    if now is None:
        observed_now = datetime.now(UTC)
    elif (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() != timedelta(0)
    ):
        raise RecoveryUncertain(
            "public topology-B materialization time is not UTC"
        )
    else:
        observed_now = now.astimezone(UTC)
    generated_at = (
        observed_now.replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    proof_payload = {
        "contractName": TOPOLOGY_B_PUBLIC_RETIREMENT_CONTRACT,
        "contractVersion": 1,
        "generatedAt": generated_at,
        "status": "passed",
        "source": {
            "repository": TOPOLOGY_B_SOURCE_REPOSITORY,
            "ref": TOPOLOGY_B_SOURCE_REF,
            "commit": terminal_source_head,
        },
        "sidecarAuthorityRetired": True,
        "activeSidecarMarkerCount": 0,
        "activeSidecarMarkers": [],
        "retiredAuthoritySha256": terminal.get(
            "retiredAuthoritySha256"
        ),
        "committedBoundaryReceipt": {
            "sha256": sha256_bytes(terminal_bytes),
            "sizeBytes": len(terminal_bytes),
        },
        "postMarkerConvergenceReceipt": {
            "sha256": sha256_bytes(post_marker_bytes),
            "sizeBytes": len(post_marker_bytes),
        },
        "canonicalAuthority": {
            "baseUrl": CANONICAL_DOWNLOADS_BASE_URL,
            "manifestUrl": CANONICAL_DOWNLOADS_MANIFEST_URL,
            "publisherPath": CANONICAL_DOWNLOADS_PUBLISHER_PATH,
            "publisherSha256": config.canonical_publisher_sha256,
        },
    }
    proof_bytes = _topology_b_json_bytes(proof_payload)
    cloudflare = load_module(
        config.source_root
        / "scripts/cloudflare_public_download_transaction.py",
        f"topology_b_public_proof_cloudflare_{secrets.token_hex(6)}",
    )
    validate_topology_b_public_retirement_bundle(
        proof_bytes=proof_bytes,
        committed_boundary_bytes=terminal_bytes,
        post_marker_bytes=post_marker_bytes,
        expected_source_head=terminal_source_head,
        expected_publisher_sha256=config.canonical_publisher_sha256,
        cloudflare=cloudflare,
        now=observed_now,
    )
    if (
        config.public_retirement_proof.exists()
        or config.public_retirement_proof.is_symlink()
    ):
        staged = stable_regular_bytes(
            config.public_retirement_proof,
            label="staged public topology-B retirement proof",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        staged_payload = _strict_json_object_bytes(
            staged,
            label="staged public topology-B retirement proof",
        )
        staged_generated = _topology_b_utc_timestamp(
            staged_payload.get("generatedAt"),
            label="staged public topology-B retirement generatedAt",
        )
        validate_topology_b_public_retirement_bundle(
            proof_bytes=staged,
            committed_boundary_bytes=terminal_bytes,
            post_marker_bytes=post_marker_bytes,
            expected_source_head=terminal_source_head,
            expected_publisher_sha256=config.canonical_publisher_sha256,
            cloudflare=cloudflare,
            now=observed_now,
            allow_expired=True,
        )
    write_private_json(
        config.public_retirement_proof,
        proof_payload,
        replace=True,
    )

    _topology_b_public_directory(config.shelf_root, create=False)
    content_root = _topology_b_public_directory(
        config.shelf_root / TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY,
        create=True,
    )
    committed_name = (
        "committed-boundary-"
        f"{sha256_bytes(terminal_bytes)}.json"
    )
    post_marker_name = (
        "post-marker-convergence-"
        f"{sha256_bytes(post_marker_bytes)}.json"
    )
    committed_path = content_root / committed_name
    post_marker_path = content_root / post_marker_name
    proof_path = (
        config.shelf_root / TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME
    )
    _atomic_public_retirement_write(
        committed_path,
        terminal_bytes,
        replace=False,
    )
    _atomic_public_retirement_write(
        post_marker_path,
        post_marker_bytes,
        replace=False,
    )
    # The fixed proof is the commit marker. Content-addressed dependencies are
    # durable first, so an interrupted replacement leaves either the complete
    # prior proof or the complete new proof.
    _atomic_public_retirement_write(
        proof_path,
        proof_bytes,
        replace=True,
    )

    proof_url = (
        f"{CANONICAL_DOWNLOADS_BASE_URL}/"
        f"{TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME}"
    )
    committed_url = (
        f"{CANONICAL_DOWNLOADS_BASE_URL}/"
        f"{TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY}/{committed_name}"
    )
    post_marker_url = (
        f"{CANONICAL_DOWNLOADS_BASE_URL}/"
        f"{TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY}/{post_marker_name}"
    )
    expected_readback = {
        committed_url: terminal_bytes,
        post_marker_url: post_marker_bytes,
        proof_url: proof_bytes,
    }
    if (
        type(attempts) is not int
        or not 1 <= attempts <= 60
        or interval_seconds < 0
        or interval_seconds > 10
    ):
        raise RecoveryUncertain(
            "public topology-B readback bounds are invalid"
        )
    reader = public_reader or strict_public_retirement_get
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            for url, expected in expected_readback.items():
                observed = reader(url)
                if not isinstance(observed, bytes) or observed != expected:
                    raise RecoveryUncertain(
                        "public topology-B retirement bytes did not "
                        f"converge: {url}"
                    )
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                sleep_fn(interval_seconds)
    if last_error is not None:
        raise RecoveryUncertain(
            "public topology-B retirement proof did not converge"
        ) from last_error

    receipt_expected = {
        "contractName": (
            TOPOLOGY_B_PUBLIC_RETIREMENT_MATERIALIZATION_CONTRACT
        ),
        "status": "pass",
        "operationRoot": str(config.operation_root),
        "sourceHead": terminal_source_head,
        "materializerSourceHead": materializer_source_head,
        "terminalCompletedAt": terminal.get("completedAtUtc"),
        "proof": {
            "path": str(proof_path),
            "url": proof_url,
            "sha256": sha256_bytes(proof_bytes),
            "sizeBytes": len(proof_bytes),
        },
        "committedBoundary": {
            "path": str(committed_path),
            "url": committed_url,
            "sha256": sha256_bytes(terminal_bytes),
            "sizeBytes": len(terminal_bytes),
        },
        "postMarkerConvergence": {
            "path": str(post_marker_path),
            "url": post_marker_url,
            "sha256": sha256_bytes(post_marker_bytes),
            "sizeBytes": len(post_marker_bytes),
        },
        "publisherSha256": config.canonical_publisher_sha256,
    }
    materialization_path = (
        config.public_retirement_materialization_receipt
    )
    if materialization_path.exists() or materialization_path.is_symlink():
        raw = stable_regular_bytes(
            materialization_path,
            label="public topology-B retirement materialization receipt",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        materialization = _strict_json_object_bytes(
            raw,
            label="public topology-B retirement materialization receipt",
        )
        legacy_contract = (
            "chummer.public-download-topology-b-retirement-"
            "proof-materialization/v1"
        )
        contract_name = materialization.get("contractName")
        if contract_name == TOPOLOGY_B_PUBLIC_RETIREMENT_MATERIALIZATION_CONTRACT:
            expected_keys = {*receipt_expected, "verifiedAtUtc"}
            immutable_keys = {
                "contractName",
                "status",
                "operationRoot",
                "sourceHead",
                "terminalCompletedAt",
                "committedBoundary",
                "postMarkerConvergence",
                "publisherSha256",
            }
            previous_materializer_source = materialization.get(
                "materializerSourceHead"
            )
            immutable_expected = receipt_expected
        elif contract_name == legacy_contract:
            immutable_expected = {
                key: value
                for key, value in receipt_expected.items()
                if key
                not in {
                    "materializerSourceHead",
                    "terminalCompletedAt",
                }
            }
            immutable_expected["contractName"] = legacy_contract
            expected_keys = {*immutable_expected, "verifiedAtUtc"}
            immutable_keys = {
                "contractName",
                "status",
                "operationRoot",
                "sourceHead",
                "committedBoundary",
                "postMarkerConvergence",
                "publisherSha256",
            }
            previous_materializer_source = materialization.get("sourceHead")
        else:
            raise RecoveryUncertain(
                "public topology-B retirement materialization contract drifted"
            )
        previous_proof = materialization.get("proof")
        if (
            set(materialization) != expected_keys
            or any(
                not _json_semantically_equal(
                    materialization.get(key),
                    immutable_expected[key],
                )
                for key in immutable_keys
            )
            or type(previous_materializer_source) is not str
            or COMMIT.fullmatch(previous_materializer_source) is None
            or type(previous_proof) is not dict
            or set(previous_proof)
            != {"path", "url", "sha256", "sizeBytes"}
            or previous_proof.get("path")
            != receipt_expected["proof"]["path"]
            or previous_proof.get("url")
            != receipt_expected["proof"]["url"]
            or not _topology_b_is_sha256(
                previous_proof.get("sha256")
            )
            or type(previous_proof.get("sizeBytes")) is not int
            or previous_proof["sizeBytes"] <= 0
            or type(materialization.get("verifiedAtUtc")) is not str
        ):
            raise RecoveryUncertain(
                "public topology-B retirement materialization drifted"
            )
        previous_verified = _topology_b_utc_timestamp(
            materialization["verifiedAtUtc"],
            label="prior public topology-B materialization verifiedAtUtc",
        )
        if previous_verified > observed_now + timedelta(minutes=5):
            raise RecoveryUncertain(
                "prior public topology-B materialization is future-dated"
            )
        _topology_b_require_git_ancestor(
            config.source_root,
            previous_materializer_source,
            materializer_source_head,
        )
    materialization = {
        **receipt_expected,
        "verifiedAtUtc": generated_at,
    }
    write_private_json(
        materialization_path,
        materialization,
        replace=True,
    )
    return materialization


def _adopt_terminal_committed_retirement(
    config: SidecarConfig,
) -> dict[str, Any] | None:
    """Adopt a completed retirement using only immutable local authority.

    The terminal receipt is written only after restoration, connector gates,
    marker retirement, and cleanup are durable.  If its journal append was
    interrupted, no provider observation may supersede those completed
    bindings before the exact receipt is adopted.
    """

    terminal_path = getattr(config, "retirement_receipt", None)
    if not isinstance(terminal_path, Path) or not (
        terminal_path.exists() or terminal_path.is_symlink()
    ):
        return None
    if getattr(config, "operation", None) != RETIRE_OPERATION:
        raise RecoveryUncertain(
            "terminal topology-B retirement requires explicit retirement"
        )

    try:
        terminal_raw = stable_regular_bytes(
            terminal_path,
            label="terminal topology-B retirement receipt",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        terminal = _strict_json_object_bytes(
            terminal_raw,
            label="terminal topology-B retirement receipt",
        )
        journal_raw = stable_regular_bytes(
            config.operation_journal,
            label="topology-B operation journal",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        state = _strict_json_object_bytes(
            journal_raw,
            label="topology-B operation journal",
        )
        if (
            state.get("schema") != TOPOLOGY_B_OPERATION_SCHEMA
            or state.get("operation") != CUTOVER_OPERATION
            or state.get("projectName") != config.project_name
            or state.get("operationRoot") != str(config.operation_root)
            or state.get("sourceHead") != config.source_head
            or state.get("volumes") != config.volume_names
            or state.get("phase") not in {"cleaned", "retired"}
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement journal authority drifted"
            )
        receipts = state.get("receipts")
        required_receipts = {
            "activeAuthority",
            "retirementAuthorization",
            "cloudflareRetirement",
            "incumbentAfterRetirement",
            "retirementEvidence",
            "retiredAuthority",
            "retirementConnectorGate",
            "retirementPostMarkerConnectorGate",
            "cleanup",
        }
        if (
            not isinstance(receipts, dict)
            or any(
                not isinstance(receipts.get(name), dict)
                for name in required_receipts
            )
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement lacks durable boundary receipts"
            )

        cloudflare = load_module(
            config.source_root
            / "scripts/cloudflare_public_download_transaction.py",
            f"topology_b_terminal_cloudflare_{secrets.token_hex(6)}",
        )

        baseline = state.get("incumbentBaseline")
        expected_paths = {
            "/downloads/RELEASE_CHANNEL.generated.json",
            "/downloads/releases.json",
        }
        if (
            not isinstance(baseline, dict)
            or set(baseline) != set(SIDECAR_HOSTS)
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement baseline is incomplete"
            )
        for hostname in SIDECAR_HOSTS:
            observations = baseline.get(hostname)
            if (
                not isinstance(observations, dict)
                or set(observations) != expected_paths
            ):
                raise RecoveryUncertain(
                    "terminal topology-B retirement baseline drifted"
                )
            for path in sorted(expected_paths):
                observation = observations.get(path)
                if (
                    not isinstance(observation, dict)
                    or set(observation)
                    != {"httpStatus", "bodySha256", "sizeBytes"}
                    or type(observation.get("httpStatus")) is not int
                    or observation["httpStatus"] != 200
                    or SHA256.fullmatch(
                        str(observation.get("bodySha256") or "")
                    )
                    is None
                    or type(observation.get("sizeBytes")) is not int
                    or observation["sizeBytes"] <= 0
                ):
                    raise RecoveryUncertain(
                        "terminal topology-B retirement baseline is invalid"
                    )

        if (
            config.active_runtime_authority.exists()
            or config.active_runtime_authority.is_symlink()
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement retains active authority"
            )
        retired_raw = stable_regular_bytes(
            config.retired_active_authority,
            label="retired topology-B runtime authority",
            maximum_bytes=1024 * 1024,
            owner_only=True,
        )
        active_authority = _strict_json_object_bytes(
            retired_raw,
            label="retired topology-B runtime authority",
        )
        if not _json_semantically_equal(
            receipts["activeAuthority"],
            active_authority,
        ):
            raise RecoveryUncertain(
                "terminal topology-B retired authority journal drifted"
            )
        committed_raw = stable_regular_bytes(
            config.cloudflare_committed_evidence,
            label="committed Cloudflare evidence",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        evidence_raw = stable_regular_bytes(
            config.cloudflare_retirement_evidence,
            label="Cloudflare retirement evidence",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        evidence = _strict_json_object_bytes(
            evidence_raw,
            label="Cloudflare retirement evidence",
        )

        canonical_sha256 = cloudflare.canonical_sha256
        baseline_sha256 = canonical_sha256(baseline)
        retired_authority_sha256 = sha256_bytes(retired_raw)
        authorization = receipts["retirementAuthorization"]
        durable_controller_source_head = authorization.get(
            "controllerSourceHead"
        )
        authorization_expected = {
            "contractName": (
                "chummer.public-download-committed-retirement-"
                "authorization/v1"
            ),
            "operation": RETIRE_OPERATION,
            "operationRoot": str(config.operation_root),
            "projectName": config.project_name,
            "operationSourceHead": config.source_head,
            "controllerSourceHead": durable_controller_source_head,
            "activeAuthorityPath": str(config.active_runtime_authority),
            "activeAuthoritySha256": retired_authority_sha256,
            "committedEvidencePath": str(
                config.cloudflare_committed_evidence
            ),
            "committedEvidenceSha256": sha256_bytes(committed_raw),
            "targetConfigSha256": authorization.get(
                "targetConfigSha256"
            ),
            "targetVersion": authorization.get("targetVersion"),
            "priorConfigSha256": authorization.get("priorConfigSha256"),
            "priorVersion": authorization.get("priorVersion"),
            "incumbentBaselineSha256": baseline_sha256,
        }
        if (
            set(authorization)
            != {*authorization_expected, "authorizedAtUtc"}
            or any(
                authorization.get(key) != value
                for key, value in authorization_expected.items()
            )
            or SHA256.fullmatch(
                str(authorization.get("targetConfigSha256") or "")
            )
            is None
            or type(authorization.get("targetVersion")) is not int
            or authorization["targetVersion"] < 0
            or SHA256.fullmatch(
                str(authorization.get("priorConfigSha256") or "")
            )
            is None
            or type(authorization.get("priorVersion")) is not int
            or authorization["priorVersion"] < 0
            or not isinstance(durable_controller_source_head, str)
            or COMMIT.fullmatch(durable_controller_source_head) is None
            or not isinstance(authorization.get("authorizedAtUtc"), str)
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement authorization drifted"
            )

        restoration = receipts["cloudflareRetirement"]
        restoration_fields = {
            "contractName",
            "phase",
            "operationRoot",
            "targetConfigSha256",
            "targetVersion",
            "priorConfigSha256",
            "restoredVersion",
            "restoredResponseSha256",
            "connectorConvergence",
            "restoredAtUtc",
            "connectorsVerifiedAtUtc",
        }
        try:
            restoration_connectors = (
                cloudflare.validate_current_connector_convergence_receipt(
                    restoration.get("connectorConvergence")
                )
            )
        except Exception as exc:
            raise RecoveryUncertain(
                "terminal topology-B restoration connectors drifted"
            ) from exc
        if (
            set(restoration) != restoration_fields
            or restoration.get("contractName")
            != "chummer.public-download-cloudflare-retirement/v1"
            or restoration.get("phase") != "restored"
            or restoration.get("operationRoot")
            != str(config.operation_root)
            or restoration.get("targetConfigSha256")
            != authorization["targetConfigSha256"]
            or restoration.get("targetVersion")
            != authorization["targetVersion"]
            or restoration.get("priorConfigSha256")
            != authorization["priorConfigSha256"]
            or type(restoration.get("restoredVersion")) is not int
            or restoration["restoredVersion"] < 0
            or restoration_connectors.get("targetVersion")
            != restoration["restoredVersion"]
            or SHA256.fullmatch(
                str(restoration.get("restoredResponseSha256") or "")
            )
            is None
            or not isinstance(restoration.get("restoredAtUtc"), str)
            or not isinstance(
                restoration.get("connectorsVerifiedAtUtc"),
                str,
            )
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement restoration drifted"
            )

        incumbent = receipts["incumbentAfterRetirement"]
        if not _json_semantically_equal(incumbent, baseline):
            raise RecoveryUncertain(
                "terminal topology-B incumbent observation drifted"
            )
        connector_convergence_sha256 = canonical_sha256(
            restoration_connectors
        )
        evidence_expected = {
            "contractName": (
                "chummer.public-download-committed-retirement-evidence/v1"
            ),
            "status": "committed",
            "operation": RETIRE_OPERATION,
            "operationRoot": str(config.operation_root),
            "projectName": config.project_name,
            "operationSourceHead": config.source_head,
            "controllerSourceHead": durable_controller_source_head,
            "authorizationSha256": canonical_sha256(authorization),
            "restorationSha256": canonical_sha256(restoration),
            "connectorConvergenceSha256": (
                connector_convergence_sha256
            ),
            "targetConfigSha256": authorization["targetConfigSha256"],
            "targetVersion": authorization["targetVersion"],
            "priorConfigSha256": restoration["priorConfigSha256"],
            "restoredVersion": restoration["restoredVersion"],
            "incumbentBaselineSha256": baseline_sha256,
            "incumbentObservationSha256": canonical_sha256(incumbent),
            "incumbent": copy.deepcopy(incumbent),
        }
        if (
            set(evidence) != {*evidence_expected, "committedAtUtc"}
            or any(
                not _json_semantically_equal(evidence.get(key), value)
                for key, value in evidence_expected.items()
            )
            or not isinstance(evidence.get("committedAtUtc"), str)
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement evidence drifted"
            )
        retirement_evidence = receipts["retirementEvidence"]
        retirement_evidence_expected = {
            "contractName": (
                "chummer.public-download-retirement-evidence-summary/v1"
            ),
            "status": "committed",
            "evidencePath": str(config.cloudflare_retirement_evidence),
            "evidenceSha256": sha256_bytes(evidence_raw),
            "priorConfigSha256": restoration["priorConfigSha256"],
            "restoredVersion": restoration["restoredVersion"],
            "connectorConvergenceSha256": (
                connector_convergence_sha256
            ),
            "incumbentBaselineSha256": baseline_sha256,
        }
        if retirement_evidence != retirement_evidence_expected:
            raise RecoveryUncertain(
                "terminal topology-B retirement evidence summary drifted"
            )

        try:
            marker_connector_gate = (
                cloudflare.validate_current_connector_convergence_receipt(
                    receipts["retirementConnectorGate"]
                )
            )
        except Exception as exc:
            raise RecoveryUncertain(
                "terminal topology-B marker connector gate drifted"
            ) from exc
        restored_version = restoration["restoredVersion"]
        marker_connector_gate_sha256 = canonical_sha256(
            marker_connector_gate
        )
        if marker_connector_gate.get("targetVersion") != restored_version:
            raise RecoveryUncertain(
                "terminal topology-B marker connector version drifted"
            )

        def validate_boundary(
            value: Any,
            *,
            boundary: str,
        ) -> dict[str, Any]:
            fields = {
                "contractName",
                "status",
                "boundary",
                "operationRoot",
                "restoredVersion",
                "retiredAuthoritySha256",
                "markerConnectorGateSha256",
                "connectorConvergence",
                "connectorConvergenceSha256",
                "verifiedAtUtc",
            }
            if (
                not isinstance(value, dict)
                or set(value) != fields
                or value.get("contractName")
                != (
                    "chummer.public-download-retirement-"
                    "connector-boundary/v1"
                )
                or value.get("status") != "pass"
                or value.get("boundary") != boundary
                or value.get("operationRoot") != str(config.operation_root)
                or value.get("restoredVersion") != restored_version
                or value.get("retiredAuthoritySha256")
                != retired_authority_sha256
                or value.get("markerConnectorGateSha256")
                != marker_connector_gate_sha256
                or not isinstance(value.get("verifiedAtUtc"), str)
            ):
                raise RecoveryUncertain(
                    "terminal topology-B connector boundary drifted"
                )
            try:
                convergence = (
                    cloudflare
                    .validate_current_connector_convergence_receipt(
                        value.get("connectorConvergence")
                    )
                )
            except Exception as exc:
                raise RecoveryUncertain(
                    "terminal topology-B connector convergence drifted"
                ) from exc
            if (
                convergence.get("targetVersion") != restored_version
                or canonical_sha256(convergence)
                != value.get("connectorConvergenceSha256")
            ):
                raise RecoveryUncertain(
                    "terminal topology-B connector boundary version drifted"
                )
            return value

        post_marker_connector_gate = validate_boundary(
            receipts["retirementPostMarkerConnectorGate"],
            boundary="post-marker",
        )
        resume_present = "retirementConnectorResumeGate" in receipts
        latest_connector_gate = (
            validate_boundary(
                receipts["retirementConnectorResumeGate"],
                boundary="resume-post-marker",
            )
            if resume_present
            else post_marker_connector_gate
        )
        post_marker_connector_gate_sha256 = canonical_sha256(
            post_marker_connector_gate
        )
        latest_connector_gate_sha256 = canonical_sha256(
            latest_connector_gate
        )

        retired_authority = receipts["retiredAuthority"]
        retired_authority_expected = {
            "contractName": (
                "chummer.public-download-retired-authority/v1"
            ),
            "status": "retired",
            "activeAuthorityPath": str(config.active_runtime_authority),
            "retiredAuthorityPath": str(
                config.retired_active_authority
            ),
            "activeAuthoritySha256": retired_authority_sha256,
            "retirementEvidenceSha256": sha256_bytes(evidence_raw),
            "connectorGateSha256": marker_connector_gate_sha256,
        }
        if (
            set(retired_authority)
            != {
                *retired_authority_expected,
                "disposition",
                "retiredAtUtc",
            }
            or any(
                retired_authority.get(key) != value
                for key, value in retired_authority_expected.items()
            )
            or retired_authority.get("disposition")
            not in {
                "atomically-retired",
                "already-atomically-retired",
            }
            or not isinstance(retired_authority.get("retiredAtUtc"), str)
        ):
            raise RecoveryUncertain(
                "terminal topology-B retired authority receipt drifted"
            )

        cleanup = receipts["cleanup"]
        terminal_expected = {
            "contractName": (
                "chummer.public-download-committed-retirement/v1"
            ),
            "status": "retired",
            "operation": RETIRE_OPERATION,
            "operationRoot": str(config.operation_root),
            "projectName": config.project_name,
            "operationSourceHead": config.source_head,
            "controllerSourceHead": durable_controller_source_head,
            "retiredAuthorityPath": str(
                config.retired_active_authority
            ),
            "retiredAuthoritySha256": retired_authority_sha256,
            "retirementEvidencePath": str(
                config.cloudflare_retirement_evidence
            ),
            "retirementEvidenceSha256": sha256_bytes(evidence_raw),
            "connectorGateSha256": marker_connector_gate_sha256,
            "postMarkerConnectorGateSha256": (
                post_marker_connector_gate_sha256
            ),
            "latestConnectorGateSha256": (
                latest_connector_gate_sha256
            ),
            "priorConfigSha256": restoration["priorConfigSha256"],
            "restoredVersion": restored_version,
            "incumbentBaselineSha256": baseline_sha256,
            "incumbentObservationSha256": canonical_sha256(incumbent),
            "cleanupSha256": canonical_sha256(cleanup),
        }
        if (
            set(terminal) != {*terminal_expected, "completedAtUtc"}
            or any(
                terminal.get(key) != value
                for key, value in terminal_expected.items()
            )
            or not isinstance(terminal.get("completedAtUtc"), str)
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement receipt drifted"
            )

        existing_terminal = receipts.get("retirement")
        if existing_terminal is None:
            if state.get("phase") != "cleaned":
                raise RecoveryUncertain(
                    "terminal topology-B retirement journal is incomplete"
                )
            adopted = copy.deepcopy(state)
            adopted["phase"] = "retired"
            adopted["updatedAtUtc"] = utc_now()
            adopted_receipts = adopted.get("receipts")
            if not isinstance(adopted_receipts, dict):
                raise RecoveryUncertain(
                    "terminal topology-B retirement receipts are malformed"
                )
            adopted_receipts["retirement"] = copy.deepcopy(terminal)
            write_private_json(
                config.operation_journal,
                adopted,
                replace=True,
            )
            adopted_raw = stable_regular_bytes(
                config.operation_journal,
                label="adopted topology-B operation journal",
                maximum_bytes=16 * 1024 * 1024,
                owner_only=True,
            )
            if _strict_json_object_bytes(
                adopted_raw,
                label="adopted topology-B operation journal",
            ) != adopted:
                raise RecoveryUncertain(
                    "terminal topology-B retirement adoption was not durable"
                )
            state = adopted
            receipts = adopted_receipts
        elif (
            existing_terminal != terminal
            or state.get("phase") != "retired"
        ):
            raise RecoveryUncertain(
                "terminal topology-B retirement journal drifted"
            )
        if stable_regular_bytes(
            terminal_path,
            label="terminal topology-B retirement receipt",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        ) != terminal_raw:
            raise RecoveryUncertain(
                "terminal topology-B retirement receipt changed during adoption"
            )

        return {
            "contractName": TOPOLOGY_B_CONTRACT,
            "status": "pass",
            "operation": config.operation,
            "disposition": "committed-sidecar-retired-to-incumbent",
            "operationSourceHead": config.source_head,
            "controllerSourceHead": durable_controller_source_head,
            "cloudflareRestoration": copy.deepcopy(restoration),
            "incumbent": copy.deepcopy(incumbent),
            "retirementEvidence": copy.deepcopy(retirement_evidence),
            "retiredAuthority": copy.deepcopy(retired_authority),
            "postMarkerConnectors": copy.deepcopy(
                latest_connector_gate
            ),
            "cleanup": copy.deepcopy(cleanup),
            "terminalReceipt": copy.deepcopy(terminal),
        }
    except RecoveryUncertain:
        raise
    except BaseException as exc:
        raise RecoveryUncertain(
            "terminal topology-B retirement could not be adopted locally"
        ) from exc


def retire_topology_b(
    config: SidecarConfig,
    actions: TopologyBActionsProtocol | None = None,
) -> dict[str, Any]:
    """Retire a terminal committed sidecar back to its exact incumbent.

    This is deliberately separate from recovery.  Once the committed target is
    restored to its captured prior configuration, every failure remains
    journaled and uncertain; this path never silently reapplies the sidecar.
    """

    previous_signal_handlers: dict[int, Any] = {}

    def interrupt_retirement(
        signal_number: int,
        _frame: Any,
    ) -> None:
        raise _RetirementInterrupted(signal_number)

    try:
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            previous_signal_handlers[signal_number] = signal.getsignal(
                signal_number
            )
            signal.signal(signal_number, interrupt_retirement)
        adopted_terminal = _adopt_terminal_committed_retirement(config)
        if adopted_terminal is not None:
            return adopted_terminal
        action_boundary = (
            actions if actions is not None else TopologyBActions(config)
        )
        authorization = action_boundary.authorize_committed_retirement(
            config
        )
        restoration = action_boundary.restore_committed_prior(
            config,
            authorization,
        )
        incumbent = action_boundary.probe_public_incumbent(
            config,
            phase="after-retirement",
            hosts=SIDECAR_HOSTS,
        )
        retirement_evidence = (
            action_boundary.commit_retirement_evidence(
                config,
                authorization,
                restoration,
                incumbent,
            )
        )
        retired_authority = action_boundary.retire_active_authority(
            config,
            authorization,
            restoration,
            retirement_evidence,
        )
        post_marker_connectors = (
            action_boundary.verify_retired_authority_connectors(
                config,
                authorization,
                restoration,
                retirement_evidence,
                retired_authority,
            )
        )
        cleanup = action_boundary.cleanup_sidecar_resources(config)
        terminal = action_boundary.finalize_committed_retirement(
            config,
            authorization,
            restoration,
            retirement_evidence,
            retired_authority,
            incumbent,
            cleanup,
        )
        return {
            "contractName": TOPOLOGY_B_CONTRACT,
            "status": "pass",
            "operation": config.operation,
            "disposition": "committed-sidecar-retired-to-incumbent",
            "operationSourceHead": config.source_head,
            "controllerSourceHead": (
                config.controller_source_head or config.source_head
            ),
            "cloudflareRestoration": restoration,
            "incumbent": incumbent,
            "retirementEvidence": retirement_evidence,
            "retiredAuthority": retired_authority,
            "postMarkerConnectors": post_marker_connectors,
            "cleanup": cleanup,
            "terminalReceipt": terminal,
        }
    except RecoveryUncertain:
        raise
    except BaseException as exc:
        raise RecoveryUncertain(
            "committed topology-B retirement could not establish exact state"
        ) from exc
    finally:
        for signal_number, previous_handler in (
            previous_signal_handlers.items()
        ):
            signal.signal(signal_number, previous_handler)


def execute(config: SidecarConfig) -> dict[str, Any]:
    return execute_topology_b(config)


def parse_args(argv: list[str] | None = None) -> SidecarConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation",
        choices=tuple(sorted(OPERATIONS)),
        required=True,
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--shared-mutation-lock-token", required=True)
    parser.add_argument("--shelf-root", type=Path, required=True)
    parser.add_argument("--migration-candidate-root", type=Path, required=True)
    parser.add_argument("--migration-authority", type=Path, required=True)
    parser.add_argument("--migration-authority-sha256", required=True)
    parser.add_argument("--release-candidate-root", type=Path, required=True)
    parser.add_argument(
        "--candidate-import-authority",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--candidate-import-authority-sha256",
        required=True,
    )
    parser.add_argument("--direct-import-receipt", type=Path, required=True)
    parser.add_argument("--direct-import-receipt-sha256", required=True)
    parser.add_argument(
        "--manifest-closure-restoration-spec",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--manifest-closure-restoration-spec-sha256",
        required=True,
    )
    parser.add_argument("--release-channel-receipt", type=Path, required=True)
    parser.add_argument("--release-channel-receipt-sha256", required=True)
    parser.add_argument("--projection-snapshot-root", type=Path, required=True)
    parser.add_argument("--projection-snapshot-id", required=True)
    parser.add_argument("--projection-snapshot-sha256", required=True)
    parser.add_argument(
        "--projection-snapshot-tree-sha256",
        dest="projection_source_tree_sha256",
        required=True,
    )
    parser.add_argument("--projection-manifest-sha256", required=True)
    parser.add_argument("--runtime-proof-source", type=Path, required=True)
    parser.add_argument("--runtime-proof-sha256", required=True)
    parser.add_argument("--final-gold-source", type=Path, required=True)
    parser.add_argument("--final-gold-sha256", required=True)
    parser.add_argument("--fleet-source", type=Path, required=True)
    parser.add_argument("--fleet-sha256", required=True)
    parser.add_argument("--operation-root", type=Path, required=True)
    parser.add_argument("--active-runtime-authority", type=Path, required=True)
    parser.add_argument("--docker-config-root", type=Path, required=True)
    parser.add_argument(
        "--cloudflare-credentials-file",
        type=Path,
        required=True,
    )
    parser.add_argument("--cloudflare-account-id", required=True)
    parser.add_argument("--cloudflare-tunnel-id", required=True)
    parser.add_argument(
        "--cloudflare-api-base",
        default="https://api.cloudflare.com/client/v4",
    )
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--canonical-publisher-sha256",
        default="",
        help=(
            "independent SHA-256 of the canonical flagship HTTP publisher; "
            "mandatory for committed topology-B retirement"
        ),
    )
    parser.add_argument("--build-context", type=Path, required=True)
    parser.add_argument("--fleet-media-contracts", type=Path, required=True)
    parser.add_argument("--design-product-root", type=Path, required=True)
    parser.add_argument(
        "--delivery-phase",
        choices=("bootstrap", "windows-preview"),
        required=True,
    )
    parser.add_argument("--ready-timeout-seconds", type=int, default=180)
    args = parser.parse_args(argv)

    def exact_existing(path: Path, label: str) -> Path:
        if not path.is_absolute() or path.is_symlink():
            raise CutoverError(f"{label} must use an exact absolute path")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise CutoverError(f"{label} is unavailable") from exc
        if resolved != path:
            raise CutoverError(f"{label} contains a symlink component")
        return path

    source_root = exact_existing(args.source_root, "source root")
    shelf_root = exact_existing(args.shelf_root, "canonical release shelf")
    if shelf_root != CANONICAL_RELEASE_SHELF_ROOT:
        raise CutoverError("release shelf must be the exact canonical path")
    receipt_root = exact_existing(args.receipt_root, "receipt root")
    docker_config_root = exact_existing(
        args.docker_config_root,
        "Docker configuration root",
    )
    active_parent = exact_existing(
        args.active_runtime_authority.parent,
        "active runtime authority parent",
    )
    if args.active_runtime_authority != active_parent / args.active_runtime_authority.name:
        raise CutoverError("active runtime authority path is unsafe")
    recovery = args.operation == RECOVERY_OPERATION
    retirement = args.operation == RETIRE_OPERATION
    journal_only = recovery or retirement
    if not journal_only:
        operation_parent = exact_existing(
            args.operation_root.parent,
            "sidecar operation parent",
        )
        operation_root = operation_parent / args.operation_root.name
        if operation_root != args.operation_root:
            raise CutoverError("sidecar operation root is not canonical")
    elif recovery:
        if args.operation_root.exists() or args.operation_root.is_symlink():
            operation_root = exact_existing(
                args.operation_root,
                "sidecar operation root",
            )
        else:
            operation_parent = exact_existing(
                args.operation_root.parent,
                "sidecar operation parent",
            )
            operation_root = operation_parent / args.operation_root.name
            planned_journal = (
                receipt_root / f"{operation_root.name}.operation.json"
            )
            if not planned_journal.is_file() or planned_journal.is_symlink():
                raise RecoveryUncertain(
                    "missing operation root has no planned recovery journal"
                )
    else:
        operation_root = exact_existing(
            args.operation_root,
            "sidecar retirement operation root",
        )
        retirement_journal = (
            receipt_root / f"{operation_root.name}.operation.json"
        )
        if not retirement_journal.is_file() or retirement_journal.is_symlink():
            raise RecoveryUncertain(
                "retirement requires the exact committed operation journal"
            )

    def cutover_input(path: Path, label: str) -> Path:
        return path if journal_only else exact_existing(path, label)

    operation_source_head = args.source_head
    if retirement:
        raw_operation_journal = stable_regular_bytes(
            retirement_journal,
            label="topology-B retirement operation journal",
            maximum_bytes=16 * 1024 * 1024,
            owner_only=True,
        )
        try:
            retirement_state = json.loads(raw_operation_journal)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RecoveryUncertain(
                "topology-B retirement operation journal is malformed"
            ) from exc
        operation_source_head = (
            str(retirement_state.get("sourceHead") or "")
            if isinstance(retirement_state, dict)
            else ""
        )
        if (
            not isinstance(retirement_state, dict)
            or retirement_state.get("schema") != TOPOLOGY_B_OPERATION_SCHEMA
            or retirement_state.get("operation") != CUTOVER_OPERATION
            or retirement_state.get("projectName") != operation_root.name
            or retirement_state.get("operationRoot") != str(operation_root)
            or COMMIT.fullmatch(operation_source_head) is None
        ):
            raise RecoveryUncertain(
                "topology-B retirement operation journal authority drifted"
            )

    return SidecarConfig(
        operation=args.operation,
        source_root=source_root,
        source_head=operation_source_head,
        shared_lock_token=args.shared_mutation_lock_token,
        shelf_root=shelf_root,
        migration_candidate_root=cutover_input(
            args.migration_candidate_root,
            "migration candidate",
        ),
        migration_authority=cutover_input(
            args.migration_authority,
            "migration authority",
        ),
        migration_authority_sha256=args.migration_authority_sha256,
        release_candidate_root=cutover_input(
            args.release_candidate_root,
            "sealed release candidate",
        ),
        candidate_import_authority=cutover_input(
            args.candidate_import_authority,
            "candidate import authority",
        ),
        candidate_import_authority_sha256=(
            args.candidate_import_authority_sha256
        ),
        direct_import_receipt=cutover_input(
            args.direct_import_receipt,
            "sealed direct-import receipt",
        ),
        direct_import_receipt_sha256=args.direct_import_receipt_sha256,
        manifest_closure_restoration_spec=cutover_input(
            args.manifest_closure_restoration_spec,
            "manifest-closure restoration spec",
        ),
        manifest_closure_restoration_spec_sha256=(
            args.manifest_closure_restoration_spec_sha256
        ),
        release_channel_receipt=cutover_input(
            args.release_channel_receipt,
            "release-channel receipt",
        ),
        release_channel_receipt_sha256=args.release_channel_receipt_sha256,
        projection_snapshot_root=cutover_input(
            args.projection_snapshot_root,
            "projection snapshot",
        ),
        projection_snapshot_id=args.projection_snapshot_id,
        projection_snapshot_sha256=args.projection_snapshot_sha256,
        projection_source_tree_sha256=(
            args.projection_source_tree_sha256
        ),
        projection_manifest_sha256=args.projection_manifest_sha256,
        runtime_proof_source=cutover_input(
            args.runtime_proof_source,
            "runtime proof",
        ),
        runtime_proof_sha256=args.runtime_proof_sha256,
        final_gold_source=cutover_input(
            args.final_gold_source,
            "final-gold handoff",
        ),
        final_gold_sha256=args.final_gold_sha256,
        fleet_source=cutover_input(
            args.fleet_source,
            "fleet runtime source",
        ),
        fleet_sha256=args.fleet_sha256,
        operation_root=operation_root,
        active_runtime_authority=args.active_runtime_authority,
        docker_config_root=docker_config_root,
        cloudflare_credentials_file=exact_existing(
            args.cloudflare_credentials_file,
            "Cloudflare credentials file",
        ),
        cloudflare_account_id=args.cloudflare_account_id,
        cloudflare_tunnel_id=args.cloudflare_tunnel_id,
        cloudflare_api_base=args.cloudflare_api_base,
        receipt_root=receipt_root,
        base_url=args.base_url,
        build_context=cutover_input(args.build_context, "build context"),
        fleet_media_contracts=cutover_input(
            args.fleet_media_contracts,
            "fleet media contracts",
        ),
        design_product_root=cutover_input(
            args.design_product_root,
            "design product root",
        ),
        delivery_phase=args.delivery_phase,
        ready_timeout_seconds=args.ready_timeout_seconds,
        controller_source_head=args.source_head,
        canonical_publisher_sha256=args.canonical_publisher_sha256,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        if config.operation == RECOVERY_OPERATION:
            result = recover_topology_b(config)
        elif config.operation == RETIRE_OPERATION:
            result = retire_topology_b(config)
            public_proof = materialize_topology_b_public_retirement_proof(
                config,
                result,
            )
            result = {
                **result,
                "publicRetirementProof": public_proof,
            }
        else:
            result = execute(config)
    except RecoveryUncertain as exc:
        print(
            f"public_download_cutover: journaled operation uncertain: {exc}",
            file=sys.stderr,
        )
        return 76
    except (CutoverError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"public_download_cutover: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
