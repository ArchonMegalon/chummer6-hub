#!/usr/bin/env python3
"""Retire one stale public-edge runtime authority after its portal disappeared.

This is deliberately not a general recovery escape hatch.  It accepts only the
canonical state in which the active authority names one exact portal container,
there is no deploy journal, no topology-B authority, and Docker proves that both
the recorded container and every canonical portal service container are absent.
"""

from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Callable


CONTRACT_NAME = "chummer.public-edge.stale-runtime-authority-retirement/v1"
ACTIVE_AUTHORITY_CONTRACT_NAME = "chummer.public-edge.active-runtime-authority/v1"
READINESS_CONTRACT_NAME = (
    "chummer.install_linking_postgres_runtime_authority_readiness.v1"
)
CANONICAL_RECEIPT_ROOT = Path(
    "/docker/chummercomplete/.state/public-edge-deploy-receipts"
)
CANONICAL_ACTIVE_AUTHORITY = CANONICAL_RECEIPT_ROOT / "active-runtime-authority.json"
CANONICAL_DEPLOY_JOURNAL = CANONICAL_RECEIPT_ROOT / "active-overlay-transaction.json"
CANONICAL_PUBLIC_DOWNLOAD_AUTHORITY = (
    CANONICAL_RECEIPT_ROOT / "public-download-active-runtime-authority.json"
)
CANONICAL_ARCHIVE_ROOT = CANONICAL_RECEIPT_ROOT / "retired-active-runtime-authorities"
CANONICAL_MUTATION_LOCK = Path(
    "/docker/chummercomplete/.state/public-edge-mutation.lock"
)
CANONICAL_DOCKER_CONFIG_ROOT = Path(
    "/docker/chummercomplete/.state/public-edge-docker-cli"
)
CANONICAL_DOCKER_CONTEXT = "default"
CANONICAL_DOCKER_HOST = "unix:///var/run/docker.sock"
CANONICAL_PROJECT = "chummer6-hub"
CANONICAL_SERVICE = "chummer-portal"
CANONICAL_PUBLISHED_PORT = 8091
MAX_AUTHORITY_BYTES = 64 * 1024
MAX_READINESS_BYTES = 4096
MAX_ARCHIVE_BYTES = 128 * 1024
EXPECTED_OWNER_UID = 1000
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
CONTAINER_ID_PATTERN = re.compile(r"[0-9a-f]{64}")
IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
SAFE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
OPERATION_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{7,63}")


class RetirementError(RuntimeError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RetirementError(f"duplicate JSON key rejected: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class StableFile:
    path: Path
    descriptor: int
    payload: bytes
    digest: str
    identity: tuple[int, int, int, int, int, int, int, int]

    def close(self) -> None:
        os.close(self.descriptor)


def _absolute_normalized(path: Path, *, label: str) -> Path:
    if not path.is_absolute() or Path(os.path.normpath(path)) != path:
        raise RetirementError(f"{label} must be an exact normalized absolute path")
    return path


def _assert_no_symlink_components(path: Path, *, label: str) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RetirementError(f"unable to inspect {label}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise RetirementError(f"{label} contains a symbolic-link component")


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_nlink,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
    )


def _open_owner_only_file(
    path: Path,
    *,
    maximum_bytes: int,
    expected_mode: int = 0o600,
    allow_absent: bool = False,
) -> StableFile | None:
    path = _absolute_normalized(path, label="private file")
    _assert_no_symlink_components(path.parent, label="private file parent")
    try:
        parent_metadata = path.parent.lstat()
    except FileNotFoundError:
        if allow_absent:
            return None
        raise RetirementError("required private file parent is missing") from None
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != EXPECTED_OWNER_UID
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        raise RetirementError("private file parent metadata is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if allow_absent:
            return None
        raise RetirementError("required private file is missing") from None
    except OSError as exc:
        raise RetirementError("required private file could not be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != EXPECTED_OWNER_UID
            or stat.S_IMODE(before.st_mode) != expected_mode
            or before.st_nlink != 1
            or before.st_size < 1
            or before.st_size > maximum_bytes
        ):
            raise RetirementError("private file metadata is unsafe")
        payload = bytearray()
        while len(payload) <= maximum_bytes:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        try:
            path_metadata = path.lstat()
        except OSError as exc:
            raise RetirementError("private file path changed while open") from exc
        if (
            len(payload) != before.st_size
            or _identity(before) != _identity(after)
            or _identity(before) != _identity(path_metadata)
        ):
            raise RetirementError("private file changed while open")
        raw = bytes(payload)
        return StableFile(
            path=path,
            descriptor=descriptor,
            payload=raw,
            digest=hashlib.sha256(raw).hexdigest(),
            identity=_identity(before),
        )
    except Exception:
        os.close(descriptor)
        raise


def _parse_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                RetirementError(f"non-finite JSON value rejected: {value}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RetirementError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise RetirementError(f"{label} must be one JSON object")
    return payload


def _parse_utc(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "T" not in value
        or not (value.endswith("Z") or value.endswith("+00:00"))
    ):
        raise RetirementError(f"{label} must be an exact UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RetirementError(f"{label} is malformed") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise RetirementError(f"{label} is not UTC")
    return value


def _validate_readiness_binding(payload: dict[str, Any]) -> None:
    path = Path(str(payload.get("installLinkingAuthorityReadinessPath") or ""))
    expected = str(payload.get("installLinkingAuthorityReadinessSha256") or "")
    if (
        re.fullmatch(
            r"install-linking-authority-readiness-[A-Za-z0-9]{8}\.json",
            path.name,
        )
        is None
        or SHA256_PATTERN.fullmatch(expected) is None
    ):
        raise RetirementError("readiness authority digest is invalid")
    readiness_file = _open_owner_only_file(
        path,
        maximum_bytes=MAX_READINESS_BYTES,
    )
    assert readiness_file is not None
    try:
        readiness = _parse_object(readiness_file.payload, label="readiness authority")
    finally:
        readiness_file.close()
    expected_keys = {
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
    if (
        readiness_file.digest != expected
        or set(readiness) != expected_keys
        or readiness.get("contractName") != READINESS_CONTRACT_NAME
        or readiness.get("status") != "pass"
        or readiness.get("ready") is not True
        or readiness.get("code") != "runtime_role_least_privilege"
        or readiness.get("currentRoleMatches") is not True
        or readiness.get("leastPrivilegeValid") is not True
        or SHA256_PATTERN.fullmatch(str(readiness.get("authorityIdentitySha256") or "")) is None
        or SHA256_PATTERN.fullmatch(str(readiness.get("runtimeRoleSha256") or "")) is None
    ):
        raise RetirementError("readiness authority is invalid")
    _parse_utc(readiness.get("checkedAtUtc"), label="readiness checkedAtUtc")


def _validate_active_authority(
    payload: dict[str, Any],
    *,
    validate_readiness: bool = True,
) -> dict[str, Any]:
    legacy_keys = {"contractName", "status", "generatedAtUtc", "portal"}
    enriched_keys = legacy_keys | {
        "installLinkingAuthorityReadinessPath",
        "installLinkingAuthorityReadinessSha256",
    }
    if set(payload) not in (legacy_keys, enriched_keys):
        raise RetirementError("active runtime authority fields are invalid")
    if (
        payload.get("contractName") != ACTIVE_AUTHORITY_CONTRACT_NAME
        or payload.get("status") != "pass"
    ):
        raise RetirementError("active runtime authority contract is invalid")
    _parse_utc(payload.get("generatedAtUtc"), label="authority generatedAtUtc")
    portal = payload.get("portal")
    portal_keys = {
        "existed",
        "containerId",
        "containerName",
        "imageId",
        "wasRunning",
        "proofAuthorityMountSha256",
        "proofPublicMountSha256",
    }
    if not isinstance(portal, dict) or set(portal) != portal_keys:
        raise RetirementError("active runtime portal authority is invalid")
    container_id = str(portal.get("containerId") or "")
    container_name = str(portal.get("containerName") or "")
    image_id = str(portal.get("imageId") or "")
    authority_digest = str(portal.get("proofAuthorityMountSha256") or "")
    public_digest = str(portal.get("proofPublicMountSha256") or "")
    if (
        portal.get("existed") is not True
        or not isinstance(portal.get("wasRunning"), bool)
        or CONTAINER_ID_PATTERN.fullmatch(container_id) is None
        or SAFE_NAME_PATTERN.fullmatch(container_name) is None
        or IMAGE_ID_PATTERN.fullmatch(image_id) is None
    ):
        raise RetirementError("retirement requires one exact prior portal authority")
    if portal["wasRunning"]:
        if SHA256_PATTERN.fullmatch(authority_digest) is None or public_digest != authority_digest:
            raise RetirementError("running authority proof mounts are invalid")
    elif authority_digest or public_digest:
        raise RetirementError("stopped authority cannot claim proof mounts")
    if set(payload) == enriched_keys and validate_readiness:
        _validate_readiness_binding(payload)
    return portal


def _ensure_absent(path: Path, *, label: str) -> None:
    _assert_no_symlink_components(path.parent, label=f"{label} parent")
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RetirementError(f"unable to inspect {label}") from exc
    raise RetirementError(f"{label} exists; existing recovery/adoption rules still own this state")


class DockerObservation:
    def __init__(self) -> None:
        self._environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(CANONICAL_DOCKER_CONFIG_ROOT / "home"),
            "DOCKER_CONFIG": str(CANONICAL_DOCKER_CONFIG_ROOT / "config"),
            "LANG": "C",
            "LC_ALL": "C",
        }

    def _run(self, arguments: list[str]) -> str:
        completed = subprocess.run(
            ["/usr/bin/docker", "--context", CANONICAL_DOCKER_CONTEXT, *arguments],
            env=self._environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        if completed.returncode != 0:
            raise RetirementError("canonical Docker observation failed")
        return completed.stdout.strip()

    def prove_missing(self, recorded_container_id: str) -> dict[str, Any]:
        context = self._run(
            ["context", "inspect", CANONICAL_DOCKER_CONTEXT, "--format", "{{.Name}}|{{.Endpoints.docker.Host}}|{{.Endpoints.docker.SkipTLSVerify}}"]
        )
        if context != f"{CANONICAL_DOCKER_CONTEXT}|{CANONICAL_DOCKER_HOST}|false":
            raise RetirementError("Docker context is not the canonical local daemon")
        service_output = self._run(
            [
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={CANONICAL_PROJECT}",
                "--filter",
                f"label=com.docker.compose.service={CANONICAL_SERVICE}",
            ]
        )
        recorded_output = self._run(
            [
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"id={recorded_container_id}",
            ]
        )
        any_portal_service_output = self._run(
            [
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.service={CANONICAL_SERVICE}",
            ]
        )
        published_port_output = self._run(
            [
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"publish={CANONICAL_PUBLISHED_PORT}",
            ]
        )
        service_ids = [line for line in service_output.splitlines() if line]
        recorded_ids = [line for line in recorded_output.splitlines() if line]
        any_portal_service_ids = [
            line for line in any_portal_service_output.splitlines() if line
        ]
        published_port_ids = [
            line for line in published_port_output.splitlines() if line
        ]
        observed_ids = (
            *service_ids,
            *recorded_ids,
            *any_portal_service_ids,
            *published_port_ids,
        )
        if any(
            CONTAINER_ID_PATTERN.fullmatch(value) is None
            for value in observed_ids
        ):
            raise RetirementError("Docker returned an ambiguous container identity")
        if (
            service_ids
            or recorded_ids
            or any_portal_service_ids
            or published_port_ids
        ):
            raise RetirementError("prior or canonical portal container is still present")
        return {
            "dockerContext": CANONICAL_DOCKER_CONTEXT,
            "dockerHost": CANONICAL_DOCKER_HOST,
            "project": CANONICAL_PROJECT,
            "service": CANONICAL_SERVICE,
            "recordedContainerId": recorded_container_id,
            "recordedContainerPresent": False,
            "canonicalServiceContainerCount": 0,
            "anyPortalServiceContainerCount": 0,
            "publishedPort": CANONICAL_PUBLISHED_PORT,
            "publishedPortContainerCount": 0,
        }


def _prepare_archive_root(path: Path) -> None:
    parent = path.parent
    _assert_no_symlink_components(parent, label="archive parent")
    metadata = parent.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != EXPECTED_OWNER_UID
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RetirementError("canonical receipt root is unsafe")
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != EXPECTED_OWNER_UID
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RetirementError("archive root is unsafe")


def _write_no_clobber(path: Path, raw: bytes) -> None:
    parent_fd = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary_name = f".{path.name}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
    descriptor = -1
    linked = False
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RetirementError("archive write made no progress")
            view = view[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != EXPECTED_OWNER_UID
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or metadata.st_size != len(raw)
        ):
            raise RetirementError("archive staging metadata is unsafe")
        os.link(
            temporary_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        linked = True
        os.unlink(temporary_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError as exc:
        raise RetirementError("retirement archive already exists") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not linked:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)
    installed = _open_owner_only_file(path, maximum_bytes=MAX_ARCHIVE_BYTES)
    assert installed is not None
    try:
        if installed.payload != raw:
            raise RetirementError("retirement archive did not commit exact bytes")
    finally:
        installed.close()


def _archive_payload(
    *,
    operation_id: str,
    authority: dict[str, Any],
    authority_sha256: str,
    docker_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contractName": CONTRACT_NAME,
        "status": "pass",
        "operationId": operation_id,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reason": "recorded_portal_container_missing",
        "priorAuthoritySha256": authority_sha256,
        "priorAuthority": authority,
        "evidence": docker_evidence,
        "disposition": "retired_to_permit_fresh_runtime_baseline",
    }


def _validated_archive(
    archive: StableFile,
    *,
    operation_id: str,
    expected_authority_sha256: str,
) -> dict[str, Any]:
    payload = _parse_object(archive.payload, label="retirement archive")
    expected_keys = {
        "contractName",
        "status",
        "operationId",
        "generatedAtUtc",
        "reason",
        "priorAuthoritySha256",
        "priorAuthority",
        "evidence",
        "disposition",
    }
    if (
        set(payload) != expected_keys
        or payload.get("contractName") != CONTRACT_NAME
        or payload.get("status") != "pass"
        or payload.get("operationId") != operation_id
        or payload.get("reason") != "recorded_portal_container_missing"
        or payload.get("priorAuthoritySha256") != expected_authority_sha256
        or payload.get("disposition") != "retired_to_permit_fresh_runtime_baseline"
        or not isinstance(payload.get("priorAuthority"), dict)
        or not isinstance(payload.get("evidence"), dict)
    ):
        raise RetirementError("existing retirement archive conflicts with this operation")
    _parse_utc(payload.get("generatedAtUtc"), label="archive generatedAtUtc")
    _validate_active_authority(
        payload["priorAuthority"],
        validate_readiness=False,
    )
    return payload


def retire_stale_authority(
    *,
    operation_id: str,
    expected_authority_sha256: str,
    active_authority: Path,
    archive_root: Path,
    deploy_journal: Path,
    public_download_authority: Path,
    runtime: Any,
    mutation_lock: AbstractContextManager[Any],
    after_archive: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if OPERATION_ID_PATTERN.fullmatch(operation_id) is None:
        raise RetirementError("operation id is invalid")
    if os.geteuid() != EXPECTED_OWNER_UID:
        raise RetirementError(
            "retirement requires the canonical UID-1000 operator identity"
        )
    if SHA256_PATTERN.fullmatch(expected_authority_sha256) is None:
        raise RetirementError("external active-authority SHA-256 pin is invalid")
    archive_path = archive_root / f"{operation_id}.json"
    with mutation_lock:
        _ensure_absent(deploy_journal, label="active deploy recovery journal")
        _ensure_absent(
            public_download_authority,
            label="topology-B active runtime authority",
        )
        archive = _open_owner_only_file(
            archive_path,
            maximum_bytes=MAX_ARCHIVE_BYTES,
            allow_absent=True,
        )
        active = _open_owner_only_file(
            active_authority,
            maximum_bytes=MAX_AUTHORITY_BYTES,
            allow_absent=True,
        )
        archive_payload: dict[str, Any] | None = None
        try:
            if archive is not None:
                archive_payload = _validated_archive(
                    archive,
                    operation_id=operation_id,
                    expected_authority_sha256=expected_authority_sha256,
                )
            if active is None:
                if archive_payload is None:
                    raise RetirementError("active runtime authority is already absent without this archive")
                authority = archive_payload["priorAuthority"]
                portal = _validate_active_authority(authority)
                docker_evidence = runtime.prove_missing(portal["containerId"])
                return {
                    "contractName": CONTRACT_NAME,
                    "status": "pass",
                    "operationId": operation_id,
                    "disposition": "already_retired",
                    "archivePath": str(archive_path),
                    "archiveSha256": archive.digest,
                    "priorAuthoritySha256": expected_authority_sha256,
                    "evidence": docker_evidence,
                }
            if active.digest != expected_authority_sha256:
                raise RetirementError("active runtime authority does not match its external SHA-256 pin")
            authority = _parse_object(active.payload, label="active runtime authority")
            portal = _validate_active_authority(authority)
            if archive_payload is not None and archive_payload["priorAuthority"] != authority:
                raise RetirementError("existing archive does not contain the exact active authority")
            docker_evidence = runtime.prove_missing(portal["containerId"])
            if archive_payload is None:
                _prepare_archive_root(archive_root)
                archive_payload = _archive_payload(
                    operation_id=operation_id,
                    authority=authority,
                    authority_sha256=active.digest,
                    docker_evidence=docker_evidence,
                )
                archive_raw = (
                    json.dumps(
                        archive_payload,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                    + "\n"
                ).encode("utf-8")
                _write_no_clobber(archive_path, archive_raw)
                archive = _open_owner_only_file(
                    archive_path,
                    maximum_bytes=MAX_ARCHIVE_BYTES,
                )
                assert archive is not None
            if after_archive is not None:
                after_archive()
            docker_evidence = runtime.prove_missing(portal["containerId"])
            current_path = active_authority.lstat()
            current_descriptor = os.fstat(active.descriptor)
            if _identity(current_path) != active.identity or _identity(current_descriptor) != active.identity:
                raise RetirementError("active runtime authority changed before retirement")
            parent_fd = os.open(
                active_authority.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.unlink(active_authority.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            return {
                "contractName": CONTRACT_NAME,
                "status": "pass",
                "operationId": operation_id,
                "disposition": "retired",
                "archivePath": str(archive_path),
                "archiveSha256": archive.digest,
                "priorAuthoritySha256": active.digest,
                "evidence": docker_evidence,
            }
        finally:
            if active is not None:
                active.close()
            if archive is not None:
                archive.close()


def _load_overlay_module() -> Any:
    module_path = Path(__file__).resolve().with_name(
        "publish_public_edge_portal_overlay.py"
    )
    spec = importlib.util.spec_from_file_location(
        "chummer_stale_runtime_authority_retirement_overlay",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RetirementError("unable to load public-edge mutation authority")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Retire only a digest-pinned stale public-edge authority whose exact "
            "recorded and canonical portal containers are both absent."
        )
    )
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--expected-authority-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        overlay = _load_overlay_module()
        receipt = retire_stale_authority(
            operation_id=args.operation_id,
            expected_authority_sha256=args.expected_authority_sha256,
            active_authority=CANONICAL_ACTIVE_AUTHORITY,
            archive_root=CANONICAL_ARCHIVE_ROOT,
            deploy_journal=CANONICAL_DEPLOY_JOURNAL,
            public_download_authority=CANONICAL_PUBLIC_DOWNLOAD_AUTHORITY,
            runtime=DockerObservation(),
            mutation_lock=overlay.public_edge_mutation_lock(
                activate=True,
                lock_path=CANONICAL_MUTATION_LOCK,
            ),
        )
    except Exception as exc:
        print(f"stale runtime authority retirement failed: {exc}", file=sys.stderr)
        return 70
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
