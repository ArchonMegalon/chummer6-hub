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
    maximum_bytes: int = 16 * 1024 * 1024,
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
        or before.st_size > maximum_bytes
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
) -> dict[str, Any]:
    if candidate_root.exists() or candidate_root.is_symlink():
        raise CutoverError("unattested migration candidate already exists")
    parent = private_directory(candidate_root.parent, create=False)
    candidate_root.mkdir(mode=0o700)
    if candidate_root.parent != parent:
        raise CutoverError("migration candidate parent changed")
    with attestor.anchored_directory(
        shelf_root,
        "release shelf root",
    ) as shelf:
        snapshot = attestor.capture_legacy_snapshot_fd(
            shelf,
            allow_aborted_history=False,
        )
        raw_rows = snapshot["legacyInventory"]["files"]
        referenced = {
            str(row["path"])
            for row in attestor._public_download_manifest_references(
                shelf,
                raw_rows,
            )
        }
        copied: list[str] = []
        excluded: list[str] = []
        for row in raw_rows:
            relative = str(row["path"])
            if relative.startswith("files/") and relative not in referenced:
                excluded.append(relative)
                continue
            source = shelf_root / relative
            destination = candidate_root / relative
            try:
                metadata = source.lstat()
            except OSError as exc:
                raise CutoverError("incumbent release byte disappeared during copy") from exc
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_nlink != int(row["linkCount"])
                or metadata.st_size != int(row["sizeBytes"])
            ):
                raise CutoverError("incumbent release byte metadata changed during copy")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination, follow_symlinks=False)
            copied_bytes = stable_regular_bytes(
                destination,
                label="migration candidate byte",
                maximum_bytes=max(int(row["sizeBytes"]), 1),
            )
            if (
                len(copied_bytes) != int(row["sizeBytes"])
                or sha256_bytes(copied_bytes) != str(row["sha256"])
            ):
                raise CutoverError("migration candidate byte differs from incumbent")
            copied.append(relative)
    fsync_candidate_tree(candidate_root)
    return {
        "copiedPaths": copied,
        "excludedUnreferencedFiles": excluded,
    }


def migrate_shelf(
    config: Config,
    *,
    attestor: Any,
    generation: Any,
) -> tuple[dict[str, Any], Path, Path]:
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
            copy_receipt = materialize_incumbent_candidate(
                attestor=attestor,
                shelf_root=config.shelf_root,
                candidate_root=config.migration_candidate_root,
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
            if not pointer_path.exists():
                with attestor.anchored_directory(
                    config.shelf_root,
                    "release shelf root",
                ) as shelf, attestor.anchored_directory(
                    config.migration_candidate_root,
                    "public-download migration candidate",
                ) as candidate, attestor.anchored_directory(
                    config.migration_state_root,
                    "cutover state root",
                ) as state:
                    attestor._validate_public_download_prestate(
                        prestate,
                        state=state,
                        shelf=shelf,
                        candidate=candidate,
                        source_head=config.source_head,
                    )
                    attestor._revalidate_public_download_migration_authority(
                        prestate
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
        if not pointer_path.exists():
            generation.activate_filesystem(
                config.migration_candidate_root,
                config.shelf_root,
                initialize_layout=True,
                generation_id=generation_id,
                activation_receipt_id=activation_receipt_id,
                promotion_lease=lease,
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


def build_candidate_image(config: Config, runner: Runner) -> tuple[str, str]:
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
            str(config.source_root / "Chummer.Run.Api/Dockerfile"),
            "--build-context",
            f"run-services-source={config.source_root}",
            "--build-context",
            "hub-registry-source="
            + str(config.build_context / "chummer-hub-registry"),
            "--build-context",
            f"fleet-media-factory-contracts={config.fleet_media_contracts}",
            "--build-context",
            f"design-product={config.design_product_root}",
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
            "--tag",
            unique_tag,
            str(config.build_context),
        ],
        label="build unique public-download portal image",
        timeout=3600,
    )
    inspection = docker_inspect_json(runner, "image", unique_tag)
    image_id = str(inspection.get("Id") or "")
    labels = inspection.get("Config", {}).get("Labels") or {}
    if (
        IMAGE_ID.fullmatch(image_id) is None
        or labels.get("org.opencontainers.image.revision") != config.source_head
        or labels.get("run.chummer.runtime-profile") != RUNTIME_PROFILE
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
) -> tuple[str, dict[str, Any]]:
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
    health = wait_healthy(
        runner,
        candidate_id,
        expected_image=image_id,
        timeout_seconds=config.ready_timeout_seconds,
    )
    return candidate_id, health


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
    restore_active_authority(config, receipt_dir)
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
        payload.get("contractName")
        != "chummer.public-edge.active-runtime-authority/v1"
        or payload.get("status") != "pass"
        or payload.get("runtimeProfile") != RUNTIME_PROFILE
        or not isinstance(portal, dict)
    ):
        return None
    container_id = str(portal.get("containerId") or "")
    image_id = str(portal.get("imageId") or "")
    if (
        CONTAINER_ID.fullmatch(container_id) is None
        or IMAGE_ID.fullmatch(image_id) is None
    ):
        return None
    runtime = container_runtime(runner, container_id)
    if not runtime["wasRunning"] or runtime["imageId"] != image_id:
        return None
    return payload


def execute(config: Config) -> dict[str, Any]:
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
    if config.transaction_journal.exists() or config.transaction_journal.is_symlink():
        try:
            recovery_receipt = run_recovery(config, runner)
        except Exception as exc:
            raise RecoveryUncertain("interrupted public-download cutover is not recoverable") from exc

    if (
        config.operation == RECOVERY_OPERATION
        and not config.transaction_journal.exists()
        and active_public_runtime(config, runner) is not None
    ):
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
    unique_tag, candidate_image_id = build_candidate_image(config, runner)
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
    warm_id = ""
    try:
        warm_id, warm_health = start_oneoff_portal(
            config,
            runner,
            compose,
            name=warm_name,
            overlay_root=config.overlay_staging_root,
            service_ports=False,
            image_id=candidate_image_id,
        )
        serving_after_warm = http_manifest_observation(
            base_url=config.base_url,
            manifest_root=generation_manifest.parent,
            portal_id=incumbent_portal["containerId"],
            runner=runner,
            phase="after-replacement-warmup-healthy",
        )
    finally:
        if warm_id:
            remove_oneoff(runner, warm_id, warm_name)

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
    snapshot_active_authority(config, receipt_dir)
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
        candidate_id, candidate_health = start_oneoff_portal(
            config,
            runner,
            compose,
            name=candidate_name,
            overlay_root=config.overlay_root,
            service_ports=True,
            image_id=candidate_image_id,
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
    return Config(
        operation=args.operation,
        source_root=args.source_root.resolve(strict=True),
        source_head=args.source_head,
        shared_lock_token=args.shared_mutation_lock_token,
        shelf_root=args.shelf_root.resolve(strict=True),
        migration_state_root=args.migration_state_root,
        migration_candidate_root=args.migration_candidate_root,
        migration_authority=args.migration_authority.resolve(strict=True),
        migration_authority_sha256=args.migration_authority_sha256,
        release_channel_receipt=args.release_channel_receipt.resolve(strict=True),
        release_channel_receipt_sha256=args.release_channel_receipt_sha256,
        projection_snapshot_root=args.projection_snapshot_root.resolve(strict=True),
        projection_snapshot_id=args.projection_snapshot_id,
        projection_snapshot_sha256=args.projection_snapshot_sha256,
        projection_manifest_sha256=args.projection_manifest_sha256,
        runtime_proof_source=args.runtime_proof_source.resolve(strict=True),
        runtime_proof_sha256=args.runtime_proof_sha256,
        certificate_file=args.certificate_file.resolve(strict=True),
        certificate_password_file=args.certificate_password_file.resolve(strict=True),
        overlay_root=args.overlay_root,
        overlay_staging_root=args.overlay_staging_root,
        overlay_backup_root=args.overlay_backup_root,
        overlay_build_root=args.overlay_build_root,
        transaction_journal=args.transaction_journal,
        active_runtime_authority=args.active_runtime_authority,
        docker_config_root=args.docker_config_root.resolve(strict=True),
        env_file=args.env_file.resolve(strict=True),
        receipt_root=args.receipt_root,
        base_url=args.base_url,
        build_context=args.build_context.resolve(strict=True),
        fleet_media_contracts=args.fleet_media_contracts.resolve(strict=True),
        design_product_root=args.design_product_root.resolve(strict=True),
        ready_timeout_seconds=args.ready_timeout_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        if config.ready_timeout_seconds < 1 or config.ready_timeout_seconds > 900:
            raise CutoverError("portal readiness timeout is outside the audited range")
        result = execute(config)
    except RecoveryUncertain as exc:
        print(f"public_download_cutover: recovery uncertain: {exc}", file=sys.stderr)
        return 76
    except (CutoverError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"public_download_cutover: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
