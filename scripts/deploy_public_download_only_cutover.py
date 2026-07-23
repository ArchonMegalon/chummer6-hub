#!/usr/bin/env python3
"""Run the fail-closed incumbent-only public-download release cutover.

This controller is intentionally callable only from the authenticated public-edge
wrapper while that wrapper owns the shared mutation lock.  It never tags either
canonical application image and never starts a PostgreSQL or initializer service.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen


CONTRACT_NAME = "chummer.public-download-only-deployment/v1"
RUNTIME_PROFILE = "public-download-only"
OPERATIONS = {
    "initial-release-shelf-public-download-cutover",
    "initial-release-shelf-public-download-cutover-recover",
}
RECOVERY_OPERATION = "initial-release-shelf-public-download-cutover-recover"
CUTOVER_OPERATION = "initial-release-shelf-public-download-cutover"
CANONICAL_PROJECT = "chummer6-hub"
CANONICAL_PORT = 8091
CANONICAL_STATE_VOLUME = "chummer6-hub_chummer-run-api-state"
CANONICAL_PORTAL_TAG = "chummer-run-api:local"
CANONICAL_TOOL_TAG = "chummer-install-linking-postgres-tool:local"
PORTAL_SERVICE = "chummer-portal"
TUNNEL_SERVICE = "chummer-run-cloudflared"
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
    finally:
        temporary.unlink(missing_ok=True)


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
    unique_tag = (
        f"chummer-run-api:public-download-{config.source_head[:16]}-"
        f"{secrets.token_hex(4)}"
    )
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


def execute(config: Config) -> dict[str, Any]:
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


def parse_args(argv: list[str] | None = None) -> Config:
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
    parser.add_argument("--release-channel-receipt", type=Path, required=True)
    parser.add_argument("--release-channel-receipt-sha256", required=True)
    parser.add_argument("--projection-snapshot-root", type=Path, required=True)
    parser.add_argument("--projection-snapshot-id", required=True)
    parser.add_argument("--projection-snapshot-sha256", required=True)
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
        release_channel_receipt=exact_input(args.release_channel_receipt),
        release_channel_receipt_sha256=args.release_channel_receipt_sha256,
        projection_snapshot_root=args.projection_snapshot_root.resolve(strict=True),
        projection_snapshot_id=args.projection_snapshot_id,
        projection_snapshot_sha256=args.projection_snapshot_sha256,
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


def main(argv: list[str] | None = None) -> int:
    global SHELF_MUTATION_MAY_HAVE_BEGUN
    SHELF_MUTATION_MAY_HAVE_BEGUN = False
    try:
        config = parse_args(argv)
        if config.ready_timeout_seconds < 1 or config.ready_timeout_seconds > 900:
            raise CutoverError("portal readiness timeout is outside the audited range")
        result = execute(config)
    except RecoveryUncertain as exc:
        print(f"public_download_cutover: recovery uncertain: {exc}", file=sys.stderr)
        return 76
    except (CutoverError, OSError, ValueError, json.JSONDecodeError) as exc:
        if SHELF_MUTATION_MAY_HAVE_BEGUN:
            print(
                "public_download_cutover: release-shelf mutation may have "
                f"begun; recovery required: {exc}",
                file=sys.stderr,
            )
            return 76
        print(f"public_download_cutover: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
