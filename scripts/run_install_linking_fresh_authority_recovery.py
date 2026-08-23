#!/usr/bin/env python3
"""Governed one-shot recovery of InstallLinking into a fresh PostgreSQL authority.

Without the destructive confirmation this controller performs only the local protected-mirror,
Data Protection, and floor preflight. It never participates in the ordinary seeded-authority
public-edge cutover.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence

from public_edge_mutation_lock import (
    MutationLease,
    PublicEdgeMutationLockUnavailable,
    _load_lease_receipt,
    acquire_mutation_lease,
    release_mutation_lease,
)


CONFIRMATION = "--confirm-new-authority-and-history-reset"
DECISION_CONTRACT = "chummer.install_linking_fresh_authority_operator_decision.v1"
PREFLIGHT_CONTRACT = "chummer.install_linking_local_recovery_preflight.v1"
ACK_CONTRACT = "chummer.install_linking_local_recovery_acknowledgement.v1"
RECOVERY_CONTRACT = "chummer.install_linking_fresh_authority_recovery.v1"
MUTATION_INTENT_CONTRACT = "chummer.install_linking_fresh_authority_mutation_intent.v1"
JOB_CONTRACT = "chummer.install_linking_fresh_authority_job.v1"
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,95}")
SHA256 = re.compile(r"[0-9a-f]{64}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
DOCKER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}")
DEFAULT_COMPOSE = Path(__file__).resolve().parents[1] / (
    "docker-compose.install-linking-fresh-recovery.yml"
)
PREFLIGHT_FILE = "INSTALL_LINKING_FRESH_AUTHORITY_PREFLIGHT.json"
INTENT_FILE = "INSTALL_LINKING_FRESH_AUTHORITY_MUTATION_INTENT.json"
RECOVERY_FILE = "INSTALL_LINKING_FRESH_AUTHORITY_RECOVERY.json"
LEASE_FILE = "PUBLIC_EDGE_MUTATION_LEASE.json"


class RecoveryError(RuntimeError):
    pass


class AmbiguousRecoveryError(RecoveryError):
    pass


@dataclass(frozen=True)
class FileBinding:
    path: str
    sha256: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    mode: int


@dataclass(frozen=True)
class CompletedCommand:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class RecoveryInputs:
    recovery_id: str
    receipt_root: Path
    compose_file: Path
    env_file: Path
    project_name: str
    tool_image_id: str
    state_volume_name: str
    network_name: str
    expected_new_authority_identity_sha256: str | None
    expected_old_authority_identity_sha256: str | None
    expected_old_authority_state_sha256: str | None
    expected_old_head_generation: int | None
    expected_old_commit_count: int | None
    decision_receipt: Path | None
    decision_receipt_sha256: str | None
    mutate: bool
    resume_unknown: bool
    stopped_container_names: tuple[str, ...]


class SubprocessExecutor:
    def __call__(
        self,
        command: Sequence[str],
        environment: dict[str, str],
        timeout: int,
    ) -> CompletedCommand:
        completed = subprocess.run(
            list(command),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
        return CompletedCommand(completed.returncode, completed.stdout, completed.stderr)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RecoveryError(f"{label} must be an exact UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise RecoveryError(f"{label} is invalid") from error
    if parsed.tzinfo is None:
        raise RecoveryError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def load_json_strict(payload: bytes, label: str) -> dict[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RecoveryError(f"{label} contains duplicate keys")
            result[key] = value
        return result

    try:
        decoded = payload.decode("utf-8")
        result = json.loads(decoded, object_pairs_hook=object_pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RecoveryError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(result, dict):
        raise RecoveryError(f"{label} must be a JSON object")
    return result


def bind_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    allowed_modes: set[int],
    expected_sha256: str | None = None,
) -> tuple[FileBinding, bytes]:
    if not path.is_absolute():
        raise RecoveryError(f"{label} path must be absolute")
    reject_symlink_ancestors(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RecoveryError(f"{label} is unavailable") from error
    try:
        metadata = os.fstat(descriptor)
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or mode not in allowed_modes
            or metadata.st_size <= 0
            or metadata.st_size > maximum_bytes
        ):
            raise RecoveryError(f"{label} has unsafe metadata")
        payload = b""
        while len(payload) <= maximum_bytes:
            chunk = os.read(descriptor, min(65536, maximum_bytes + 1 - len(payload)))
            if not chunk:
                break
            payload += chunk
        if len(payload) != metadata.st_size or len(payload) > maximum_bytes:
            raise RecoveryError(f"{label} changed or is oversized")
    finally:
        os.close(descriptor)
    digest = sha256_bytes(payload)
    if expected_sha256 is not None and digest != expected_sha256:
        raise RecoveryError(f"{label} SHA-256 does not match its external pin")
    return (
        FileBinding(
            path=str(path),
            sha256=digest,
            device=metadata.st_dev,
            inode=metadata.st_ino,
            size=metadata.st_size,
            mtime_ns=metadata.st_mtime_ns,
            mode=mode,
        ),
        payload,
    )


def revalidate_file(binding: FileBinding, *, label: str, allowed_modes: set[int]) -> None:
    current, _ = bind_file(
        Path(binding.path),
        label=label,
        maximum_bytes=max(binding.size, 1),
        allowed_modes=allowed_modes,
        expected_sha256=binding.sha256,
    )
    if current != binding:
        raise RecoveryError(f"{label} identity or metadata drifted")


def ensure_receipt_root(path: Path, *, resume: bool) -> None:
    if not path.is_absolute():
        raise RecoveryError("receipt root must be absolute")
    if not path.exists():
        path.mkdir(parents=True, mode=0o700)
    reject_symlink_ancestors(path)
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RecoveryError("receipt root must be caller-owned mode 0700")
    if resume:
        return
    forbidden = (path / INTENT_FILE, path / RECOVERY_FILE, path / LEASE_FILE)
    if any(candidate.exists() or candidate.is_symlink() for candidate in forbidden):
        raise RecoveryError("fresh recovery requires a new receipt root")


def atomic_write(path: Path, payload: dict[str, Any], *, replace: bool = False) -> str:
    reject_symlink_ancestors(path.parent)
    if path.is_symlink():
        raise RecoveryError("receipt path must not be a symlink")
    if path.exists() and not replace:
        raise RecoveryError(f"receipt already exists: {path.name}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    data = canonical_bytes(payload)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path, follow_symlinks=False)
            temporary.unlink()
        directory = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return sha256_bytes(data)


def exact_keys(payload: dict[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise RecoveryError(f"{label} keys drifted")


def reject_symlink_ancestors(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if current.exists() or current.is_symlink():
            if stat.S_ISLNK(current.lstat().st_mode):
                raise RecoveryError(f"path contains a symbolic link: {current}")


def require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise RecoveryError(f"{label} must be a lowercase SHA-256")
    return value


def validate_decision(
    payload: dict[str, Any],
    inputs: RecoveryInputs,
    now: datetime,
) -> None:
    exact_keys(
        payload,
        {
            "acknowledgements",
            "approvedAtUtc",
            "contractName",
            "decision",
            "expiresAtUtc",
            "newAuthorityIdentitySha256",
            "oldAuthorityIdentitySha256",
            "oldAuthorityStateSha256",
            "oldCommitCount",
            "oldHeadGeneration",
            "recoveryId",
            "stateVolumeName",
            "status",
            "toolImageId",
        },
        "operator decision",
    )
    acknowledgements = payload.get("acknowledgements")
    if not isinstance(acknowledgements, dict):
        raise RecoveryError("operator decision acknowledgements are invalid")
    exact_keys(
        acknowledgements,
        {
            "existingAuthorityBackupUnavailable",
            "newAuthorityIdentityAndHistoryAccepted",
            "portalAndTunnelRemainStopped",
            "retainedLocalMirrorIsSoleSeedAccepted",
        },
        "operator decision acknowledgements",
    )
    if any(value is not True for value in acknowledgements.values()):
        raise RecoveryError("every operator decision acknowledgement must be true")
    expected = {
        "contractName": DECISION_CONTRACT,
        "status": "approved",
        "decision": "approve_new_authority_and_history_reset",
        "recoveryId": inputs.recovery_id,
        "oldAuthorityIdentitySha256": inputs.expected_old_authority_identity_sha256,
        "oldAuthorityStateSha256": inputs.expected_old_authority_state_sha256,
        "oldHeadGeneration": inputs.expected_old_head_generation,
        "oldCommitCount": inputs.expected_old_commit_count,
        "newAuthorityIdentitySha256": inputs.expected_new_authority_identity_sha256,
        "toolImageId": inputs.tool_image_id,
        "stateVolumeName": inputs.state_volume_name,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise RecoveryError(f"operator decision {key} does not match the recovery input")
    approved = parse_utc(payload.get("approvedAtUtc"), "approvedAtUtc")
    expires = parse_utc(payload.get("expiresAtUtc"), "expiresAtUtc")
    if approved > now + timedelta(minutes=5) or expires <= now:
        raise RecoveryError("operator decision is not currently valid")
    if expires <= approved or expires > approved + timedelta(days=7):
        raise RecoveryError("operator decision validity window is invalid")


def validate_preflight(payload: dict[str, Any]) -> None:
    exact_keys(
        payload,
        {
            "contractName",
            "dataProtectionReady",
            "floorGeneration",
            "floorPresent",
            "floorSnapshotSha256",
            "intentPresent",
            "intentSha256",
            "intentState",
            "localStorePresent",
            "retainedSnapshotSha256",
            "sourceEnvelopeSha256",
            "sourceGeneration",
            "sourceSnapshotSha256",
            "status",
        },
        "local recovery preflight proof",
    )
    if (
        payload.get("contractName") != PREFLIGHT_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("dataProtectionReady") is not True
        or payload.get("localStorePresent") is not True
        or payload.get("floorPresent") is not True
        or type(payload.get("sourceGeneration")) is not int
        or payload["sourceGeneration"] < 1
        or type(payload.get("floorGeneration")) is not int
        or payload["floorGeneration"] < 1
        or payload["sourceGeneration"] < payload["floorGeneration"]
    ):
        raise RecoveryError("local recovery mirror/DP/floor proof is not acceptable")
    for key in (
        "floorSnapshotSha256",
        "retainedSnapshotSha256",
        "sourceEnvelopeSha256",
        "sourceSnapshotSha256",
    ):
        require_sha(payload.get(key), key)
    intent_present = payload.get("intentPresent")
    if type(intent_present) is not bool:
        raise RecoveryError("local recovery intent posture is invalid")
    if intent_present:
        require_sha(payload.get("intentSha256"), "intentSha256")
        if payload.get("intentState") not in {"prepared", "committed_pending_mirror"}:
            raise RecoveryError("local recovery intent state is invalid")
    elif payload.get("intentSha256") is not None or payload.get("intentState") is not None:
        raise RecoveryError("absent local recovery intent has unexpected metadata")


def validate_proof_contract(payload: dict[str, Any], contract: str) -> None:
    contract_keys = {
        PREFLIGHT_CONTRACT: {
            "contractName",
            "dataProtectionReady",
            "floorGeneration",
            "floorPresent",
            "floorSnapshotSha256",
            "intentPresent",
            "intentSha256",
            "intentState",
            "localStorePresent",
            "retainedSnapshotSha256",
            "sourceEnvelopeSha256",
            "sourceGeneration",
            "sourceSnapshotSha256",
            "status",
        },
        "chummer.postgres_transport_proof.v1": {
            "authenticated",
            "authorityIdentitySha256",
            "contractName",
            "gssEncryptionDisabled",
            "pgStatSsl",
            "plaintextAttempted",
            "plaintextRejected",
            "plaintextSqlState",
            "status",
        },
        "chummer.install_linking_postgres_prepare.v1": {
            "appliedSchemaVersion",
            "authorityIdentitySha256",
            "contractName",
            "leastPrivilegeValid",
            "runtimeRoleSha256",
            "status",
        },
        "chummer.install_linking_postgres_empty_authority_proof.v1": {
            "appliedSchemaVersion",
            "authorityIdentitySha256",
            "commitCount",
            "contractName",
            "currentRoleMatches",
            "empty",
            "headGeneration",
            "leastPrivilegeValid",
            "runtimeRoleSha256",
            "schemaValid",
            "status",
        },
        "chummer.install_linking_postgres_schema_validation.v1": {
            "appliedSchemaVersion",
            "authorityIdentitySha256",
            "contractName",
            "status",
        },
        "chummer.install_linking_postgres_runtime_role_proof.v1": {
            "authorityIdentitySha256",
            "contractName",
            "currentRoleMatches",
            "leastPrivilegeValid",
            "runtimeRoleSha256",
            "status",
        },
        "chummer.install_linking_postgres_authority_readiness_proof.v1": {
            "appliedSchemaVersion",
            "authorityIdentitySha256",
            "authorityStateSha256",
            "commitCount",
            "contractName",
            "currentRoleMatches",
            "empty",
            "headGeneration",
            "leastPrivilegeValid",
            "runtimeRoleSha256",
            "schemaValid",
            "status",
        },
        ACK_CONTRACT: {
            "authorityIdentitySha256",
            "contractName",
            "envelopeSha256",
            "floorSnapshotSha256",
            "generation",
            "localAcknowledged",
            "localStoreSha256",
            "snapshotSha256",
            "status",
        },
    }
    expected_keys = contract_keys.get(contract)
    if expected_keys is None:
        raise RecoveryError(f"unsupported proof contract: {contract}")
    exact_keys(payload, expected_keys, contract)
    if payload.get("contractName") != contract or payload.get("status") != "pass":
        raise RecoveryError(f"{contract} proof failed")


class RecoveryController:
    def __init__(
        self,
        inputs: RecoveryInputs,
        *,
        executor: Callable[[Sequence[str], dict[str, str], int], CompletedCommand] | None = None,
        clock: Callable[[], datetime] = utc_now,
        acquire_lease: Callable[..., MutationLease] = acquire_mutation_lease,
        release_lease: Callable[[MutationLease], None] = release_mutation_lease,
        load_lease: Callable[[Path], MutationLease] = _load_lease_receipt,
    ) -> None:
        self.inputs = inputs
        self.executor = executor or SubprocessExecutor()
        self.clock = clock
        self.acquire_lease = acquire_lease
        self.release_lease = release_lease
        self.load_lease = load_lease
        self.env_binding: FileBinding | None = None
        self.compose_binding: FileBinding | None = None
        self.decision_binding: FileBinding | None = None
        self.decision: dict[str, Any] | None = None
        self.lease: MutationLease | None = None
        self.job_receipts: list[dict[str, Any]] = []
        self.durable_boundary_entered = False
        self.import_started = False

    def _environment(self) -> dict[str, str]:
        return {
            "PATH": "/usr/bin:/bin",
            "CHUMMER_INSTALL_LINKING_RECOVERY_TOOL_IMAGE": self.inputs.tool_image_id,
            "CHUMMER_INSTALL_LINKING_RECOVERY_STATE_VOLUME": self.inputs.state_volume_name,
            "CHUMMER_INSTALL_LINKING_RECOVERY_NETWORK": self.inputs.network_name,
        }

    def _exec(self, command: Sequence[str], timeout: int = 180) -> CompletedCommand:
        try:
            return self.executor(command, self._environment(), timeout)
        except subprocess.TimeoutExpired as error:
            raise AmbiguousRecoveryError("operator job exceeded its bounded deadline") from error

    def _compose_command(self, service: str, command: Sequence[str]) -> list[str]:
        return [
            "/usr/bin/docker",
            "compose",
            "--env-file",
            str(self.inputs.env_file),
            "--project-name",
            self.inputs.project_name,
            "-f",
            str(self.inputs.compose_file),
            "run",
            "--no-deps",
            "--rm",
            "-T",
            service,
            *command,
        ]

    def _guard_bound_inputs(self, *, decision: bool) -> None:
        assert self.env_binding is not None and self.compose_binding is not None
        revalidate_file(self.env_binding, label="recovery env file", allowed_modes={0o400, 0o600})
        revalidate_file(self.compose_binding, label="recovery Compose file", allowed_modes={0o444, 0o644})
        if decision:
            if self.decision_binding is None:
                raise RecoveryError("operator decision binding is unavailable")
            revalidate_file(
                self.decision_binding,
                label="operator decision receipt",
                allowed_modes={0o400},
            )

    def _write_job_receipt(
        self,
        name: str,
        service: str,
        command: Sequence[str],
        completed: CompletedCommand,
        proof: dict[str, Any] | None,
    ) -> None:
        jobs = self.inputs.receipt_root / "jobs"
        jobs.mkdir(mode=0o700, exist_ok=True)
        if stat.S_IMODE(jobs.lstat().st_mode) != 0o700 or jobs.lstat().st_uid != os.getuid():
            raise RecoveryError("job receipt directory is unsafe")
        receipt = {
            "command": list(command),
            "contractName": JOB_CONTRACT,
            "job": name,
            "proof": proof,
            "returnCode": completed.returncode,
            "service": service,
            "status": "pass" if completed.returncode == 0 else "fail",
            "stderrSha256": sha256_bytes(completed.stderr),
            "stdoutSha256": sha256_bytes(completed.stdout),
            "toolImageId": self.inputs.tool_image_id,
        }
        path = jobs / f"{len(self.job_receipts) + 1:02d}-{name}.json"
        digest = atomic_write(path, receipt)
        self.job_receipts.append(
            {"name": name, "path": str(path), "sha256": digest}
        )

    def _run_job(
        self,
        name: str,
        service: str,
        command: Sequence[str],
        *,
        contract: str | None = None,
        validator: Callable[[dict[str, Any]], None] | None = None,
        mutation_guard: bool = False,
    ) -> dict[str, Any] | None:
        self._guard_bound_inputs(decision=mutation_guard)
        completed = self._exec(self._compose_command(service, command))
        proof: dict[str, Any] | None = None
        parse_error: Exception | None = None
        if completed.returncode == 0 and contract is not None:
            try:
                proof = load_json_strict(completed.stdout, f"{name} stdout")
                validate_proof_contract(proof, contract)
                if validator is not None:
                    validator(proof)
            except Exception as error:  # receipt the exact command outcome before failing closed
                parse_error = error
        self._write_job_receipt(name, service, command, completed, proof if parse_error is None else None)
        if completed.returncode != 0:
            raise RecoveryError(f"{name} failed")
        if parse_error is not None:
            raise RecoveryError(f"{name} emitted an invalid proof") from parse_error
        return proof

    def _bind_inputs(self) -> None:
        if SAFE_ID.fullmatch(self.inputs.recovery_id) is None:
            raise RecoveryError("recovery id is invalid")
        if SAFE_ID.fullmatch(self.inputs.project_name) is None:
            raise RecoveryError("Compose project name is invalid")
        if IMAGE_ID.fullmatch(self.inputs.tool_image_id) is None:
            raise RecoveryError("tool image must be an exact sha256 image ID")
        for value, label in (
            (self.inputs.state_volume_name, "state volume name"),
            (self.inputs.network_name, "network name"),
        ):
            if not value or len(value) > 255 or any(character.isspace() for character in value):
                raise RecoveryError(f"{label} is invalid")
            if DOCKER_NAME.fullmatch(value) is None:
                raise RecoveryError(f"{label} must be a literal Docker object name")
        for value in self.inputs.stopped_container_names:
            if DOCKER_NAME.fullmatch(value) is None:
                raise RecoveryError("required stopped container name is invalid")
        ensure_receipt_root(self.inputs.receipt_root, resume=self.inputs.resume_unknown)
        self.env_binding, _ = bind_file(
            self.inputs.env_file,
            label="recovery env file",
            maximum_bytes=256 * 1024,
            allowed_modes={0o400, 0o600},
        )
        self.compose_binding, _ = bind_file(
            self.inputs.compose_file,
            label="recovery Compose file",
            maximum_bytes=256 * 1024,
            allowed_modes={0o444, 0o644},
        )

    def _validate_local_docker_inputs(self, *, require_network: bool) -> None:
        image = self._exec(
            ["/usr/bin/docker", "image", "inspect", "--format", "{{.Id}}", self.inputs.tool_image_id],
            timeout=30,
        )
        try:
            observed_image = image.stdout.decode("ascii", "strict").strip()
        except UnicodeError as error:
            raise RecoveryError("exact recovery tool image inspection was malformed") from error
        if image.returncode != 0 or observed_image != self.inputs.tool_image_id:
            raise RecoveryError("exact recovery tool image is unavailable")
        volume = self._exec(
            ["/usr/bin/docker", "volume", "inspect", self.inputs.state_volume_name],
            timeout=30,
        )
        if volume.returncode != 0:
            raise RecoveryError("exact recovery state volume is unavailable")
        if require_network:
            network = self._exec(
                ["/usr/bin/docker", "network", "inspect", self.inputs.network_name],
                timeout=30,
            )
            if network.returncode != 0:
                raise RecoveryError("exact recovery network is unavailable")

    def _prove_stopped(self) -> None:
        for name in self.inputs.stopped_container_names:
            inspected = self._exec(
                ["/usr/bin/docker", "container", "inspect", "--format", "{{.State.Running}}", name],
                timeout=30,
            )
            if inspected.returncode == 0 and inspected.stdout.decode("ascii", "strict").strip() != "false":
                raise RecoveryError(f"required stopped container is running: {name}")
            if inspected.returncode != 0:
                absent = self._exec(
                    [
                        "/usr/bin/docker",
                        "ps",
                        "-a",
                        "--filter",
                        f"name=^/{name}$",
                        "--format",
                        "{{.Names}}",
                    ],
                    timeout=30,
                )
                if absent.returncode != 0 or absent.stdout.strip():
                    raise RecoveryError(f"cannot prove stopped container state: {name}")
        consumers = self._exec(
            [
                "/usr/bin/docker",
                "ps",
                "--filter",
                f"volume={self.inputs.state_volume_name}",
                "--format",
                "{{.ID}}",
            ],
            timeout=30,
        )
        if consumers.returncode != 0 or consumers.stdout.strip():
            raise RecoveryError("the recovery state volume has a running consumer")

    def _preflight(self, name: str = "local-recovery-preflight") -> dict[str, Any]:
        proof = self._run_job(
            name,
            "install-linking-fresh-recovery-preflight",
            ["preflight-local-recovery"],
            contract=PREFLIGHT_CONTRACT,
            validator=validate_preflight,
        )
        assert proof is not None
        receipt = {
            "composeFileSha256": self.compose_binding.sha256 if self.compose_binding else None,
            "contractName": "chummer.install_linking_fresh_authority_preflight_receipt.v1",
            "dataProtectionReady": True,
            "envFileSha256": self.env_binding.sha256 if self.env_binding else None,
            "floorGeneration": proof["floorGeneration"],
            "intentPresent": proof["intentPresent"],
            "intentSha256": proof["intentSha256"],
            "localProof": proof,
            "recoveryId": self.inputs.recovery_id,
            "stateVolumeName": self.inputs.state_volume_name,
            "status": "pass",
            "toolImageId": self.inputs.tool_image_id,
        }
        atomic_write(
            self.inputs.receipt_root / PREFLIGHT_FILE,
            receipt,
            replace=(self.inputs.receipt_root / PREFLIGHT_FILE).exists(),
        )
        return proof

    def _bind_decision(self) -> None:
        if self.inputs.decision_receipt is None or self.inputs.decision_receipt_sha256 is None:
            raise RecoveryError("mutation requires an externally pinned operator decision receipt")
        for value, label in (
            (self.inputs.decision_receipt_sha256, "decision receipt SHA-256"),
            (self.inputs.expected_new_authority_identity_sha256, "new authority identity SHA-256"),
            (self.inputs.expected_old_authority_identity_sha256, "old authority identity SHA-256"),
            (self.inputs.expected_old_authority_state_sha256, "old authority state SHA-256"),
        ):
            require_sha(value, label)
        if (
            type(self.inputs.expected_old_head_generation) is not int
            or self.inputs.expected_old_head_generation < 1
            or type(self.inputs.expected_old_commit_count) is not int
            or self.inputs.expected_old_commit_count < 1
        ):
            raise RecoveryError("old authority generation and commit count must be positive")
        self.decision_binding, payload = bind_file(
            self.inputs.decision_receipt,
            label="operator decision receipt",
            maximum_bytes=64 * 1024,
            allowed_modes={0o400},
            expected_sha256=self.inputs.decision_receipt_sha256,
        )
        self.decision = load_json_strict(payload, "operator decision receipt")
        validate_decision(self.decision, self.inputs, self.clock())

    def _intent_payload(self, preflight: dict[str, Any]) -> dict[str, Any]:
        assert self.decision_binding is not None and self.compose_binding is not None
        assert self.env_binding is not None
        return {
            "confirmation": "confirm_new_authority_and_history_reset",
            "contractName": MUTATION_INTENT_CONTRACT,
            "decisionReceipt": asdict(self.decision_binding),
            "expectedNewAuthorityIdentitySha256": self.inputs.expected_new_authority_identity_sha256,
            "expectedOldAuthorityIdentitySha256": self.inputs.expected_old_authority_identity_sha256,
            "expectedOldAuthorityStateSha256": self.inputs.expected_old_authority_state_sha256,
            "expectedOldCommitCount": self.inputs.expected_old_commit_count,
            "expectedOldHeadGeneration": self.inputs.expected_old_head_generation,
            "localPreflightProofSha256": sha256_bytes(canonical_bytes(preflight)),
            "networkName": self.inputs.network_name,
            "normalCutoverRemainsSeededOnly": True,
            "recoveryId": self.inputs.recovery_id,
            "stateVolumeName": self.inputs.state_volume_name,
            "status": "in_progress",
            "toolImageId": self.inputs.tool_image_id,
            "wrapperSourceSha256": sha256_bytes(Path(__file__).read_bytes()),
        }

    def _acquire_or_resume_lease(self) -> None:
        lease_path = self.inputs.receipt_root / LEASE_FILE
        if self.inputs.resume_unknown:
            self.lease = self.load_lease(lease_path)
            return
        self.lease = self.acquire_lease(actor="install-linking-recovery")
        try:
            atomic_write(lease_path, self.lease.receipt(status="active"))
        except Exception:
            self.release_lease(self.lease)
            self.lease = None
            raise

    def _release_lease(self) -> None:
        if self.lease is None:
            return
        self.release_lease(self.lease)
        atomic_write(
            self.inputs.receipt_root / LEASE_FILE,
            self.lease.receipt(status="released"),
            replace=True,
        )
        self.lease = None

    def _require_identity(self, proof: dict[str, Any]) -> None:
        if proof.get("authorityIdentitySha256") != self.inputs.expected_new_authority_identity_sha256:
            raise RecoveryError("new PostgreSQL authority identity does not match the decision")

    def _run_post_import_proofs(self) -> dict[str, Any]:
        transport = self._run_job(
            "post-import-transport-proof",
            "install-linking-fresh-recovery-admin",
            ["transport-proof"],
            contract="chummer.postgres_transport_proof.v1",
            mutation_guard=True,
        )
        assert transport is not None
        self._require_identity(transport)
        validate = self._run_job(
            "post-import-schema-validation",
            "install-linking-fresh-recovery-admin",
            ["validate"],
            contract="chummer.install_linking_postgres_schema_validation.v1",
            mutation_guard=True,
        )
        assert validate is not None
        self._require_identity(validate)
        if validate.get("appliedSchemaVersion") != 2:
            raise RecoveryError("post-import schema is not exact version 2")
        role = self._run_job(
            "post-import-runtime-role-proof",
            "install-linking-fresh-recovery-runtime-proof",
            ["prove-runtime-role"],
            contract="chummer.install_linking_postgres_runtime_role_proof.v1",
            mutation_guard=True,
        )
        assert role is not None
        self._require_identity(role)
        if role.get("currentRoleMatches") is not True or role.get("leastPrivilegeValid") is not True:
            raise RecoveryError("post-import runtime role proof is invalid")
        ready = self._run_job(
            "post-import-authority-readiness",
            "install-linking-fresh-recovery-runtime-proof",
            ["prove-authority-ready"],
            contract="chummer.install_linking_postgres_authority_readiness_proof.v1",
            mutation_guard=True,
        )
        assert ready is not None
        self._require_identity(ready)
        if (
            ready.get("appliedSchemaVersion") != 2
            or ready.get("empty") is not False
            or ready.get("headGeneration") != 1
            or ready.get("commitCount") != 1
            or ready.get("schemaValid") is not True
            or ready.get("currentRoleMatches") is not True
            or ready.get("leastPrivilegeValid") is not True
        ):
            raise RecoveryError("post-import authority is not exact seeded generation 1")
        require_sha(ready.get("authorityStateSha256"), "new authority state SHA-256")
        acknowledgement = self._run_job(
            "post-import-local-acknowledgement",
            "install-linking-fresh-recovery-acknowledgement",
            ["prove-local-import-acknowledged"],
            contract=ACK_CONTRACT,
            mutation_guard=True,
        )
        assert acknowledgement is not None
        self._require_identity(acknowledgement)
        if acknowledgement.get("generation") != 1 or acknowledgement.get("localAcknowledged") is not True:
            raise RecoveryError("local mirror did not acknowledge the exact generation-one authority")
        for key in (
            "snapshotSha256",
            "envelopeSha256",
            "localStoreSha256",
            "floorSnapshotSha256",
        ):
            require_sha(acknowledgement.get(key), key)
        if acknowledgement["snapshotSha256"] != acknowledgement["floorSnapshotSha256"]:
            raise RecoveryError("local recovery floor digest does not match the acknowledged snapshot")
        return {"authority": ready, "acknowledgement": acknowledgement}

    def _write_final(
        self,
        *,
        status: str,
        reason: str | None,
        retained_intent_sha256: str | None = None,
        post_import: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "automaticDatabaseRollbackAllowed": False,
            "contractName": RECOVERY_CONTRACT,
            "decisionReceiptSha256": self.decision_binding.sha256 if self.decision_binding else None,
            "expectedNewAuthorityIdentitySha256": self.inputs.expected_new_authority_identity_sha256,
            "historyResetAccepted": self.inputs.mutate,
            "jobReceipts": self.job_receipts,
            "localMirrorRollbackAllowed": False,
            "normalCutoverRemainsSeededOnly": True,
            "portalAndTunnelMustRemainStopped": True,
            "postImportProof": post_import,
            "reason": reason,
            "recoveryId": self.inputs.recovery_id,
            "retainedImportIntentSha256": retained_intent_sha256,
            "status": status,
            "toolImageId": self.inputs.tool_image_id,
        }
        atomic_write(
            self.inputs.receipt_root / RECOVERY_FILE,
            payload,
            replace=(self.inputs.receipt_root / RECOVERY_FILE).exists(),
        )

    def run(self) -> Path:
        self._bind_inputs()
        self._validate_local_docker_inputs(require_network=self.inputs.mutate)
        prior: dict[str, Any] | None = None
        if self.inputs.resume_unknown:
            _, prior_bytes = bind_file(
                self.inputs.receipt_root / RECOVERY_FILE,
                label="prior recovery receipt",
                maximum_bytes=1024 * 1024,
                allowed_modes={0o600},
            )
            prior = load_json_strict(prior_bytes, "prior recovery receipt")
            prior_jobs = prior.get("jobReceipts")
            if prior.get("status") != "unknown" or not isinstance(prior_jobs, list):
                raise RecoveryError("resume requires an exact unknown recovery receipt")
            self.job_receipts = list(prior_jobs)
        preflight = self._preflight()
        if not self.inputs.mutate:
            return self.inputs.receipt_root / PREFLIGHT_FILE

        self._bind_decision()
        self._prove_stopped()
        intent_path = self.inputs.receipt_root / INTENT_FILE
        if self.inputs.resume_unknown:
            assert prior is not None
            if prior.get("status") != "unknown" or not preflight.get("intentPresent"):
                raise RecoveryError("resume requires an unknown receipt and a retained exact import intent")
            if prior.get("retainedImportIntentSha256") != preflight.get("intentSha256"):
                raise RecoveryError("retained import intent does not match the unknown receipt")
            _, existing_intent_bytes = bind_file(
                intent_path,
                label="mutation intent",
                maximum_bytes=256 * 1024,
                allowed_modes={0o600},
            )
            existing_intent = load_json_strict(existing_intent_bytes, "mutation intent")
            if existing_intent != self._intent_payload(preflight):
                # The preflight hash legitimately changes after the local import intent appears;
                # all immutable authority bindings must remain exact instead.
                for key, value in self._intent_payload(preflight).items():
                    if key == "localPreflightProofSha256":
                        continue
                    if existing_intent.get(key) != value:
                        raise RecoveryError("mutation intent authority binding drifted")
        else:
            if preflight.get("intentPresent"):
                raise RecoveryError("fresh mutation refuses an unbound retained import intent")
            atomic_write(intent_path, self._intent_payload(preflight))

        self._acquire_or_resume_lease()
        try:
            self._guard_bound_inputs(decision=True)
            self._prove_stopped()
            if not self.inputs.resume_unknown:
                transport = self._run_job(
                    "pre-prepare-transport-proof",
                    "install-linking-fresh-recovery-admin",
                    ["transport-proof"],
                    contract="chummer.postgres_transport_proof.v1",
                    mutation_guard=True,
                )
                assert transport is not None
                self._require_identity(transport)
                self.durable_boundary_entered = True
                prepare = self._run_job(
                    "prepare-empty-authority",
                    "install-linking-fresh-recovery-admin",
                    ["prepare"],
                    contract="chummer.install_linking_postgres_prepare.v1",
                    mutation_guard=True,
                )
                assert prepare is not None
                self._require_identity(prepare)
                if prepare.get("appliedSchemaVersion") != 2 or prepare.get("leastPrivilegeValid") is not True:
                    raise RecoveryError("fresh authority prepare proof is invalid")
                empty = self._run_job(
                    "prove-empty-authority",
                    "install-linking-fresh-recovery-runtime-proof",
                    ["prove-empty-authority"],
                    contract="chummer.install_linking_postgres_empty_authority_proof.v1",
                    mutation_guard=True,
                )
                assert empty is not None
                self._require_identity(empty)
                if (
                    empty.get("appliedSchemaVersion") != 2
                    or empty.get("empty") is not True
                    or empty.get("headGeneration") != 0
                    or empty.get("commitCount") != 0
                    or empty.get("schemaValid") is not True
                    or empty.get("currentRoleMatches") is not True
                    or empty.get("leastPrivilegeValid") is not True
                ):
                    raise RecoveryError("fresh authority is not exact empty generation 0")
            else:
                current = self._run_job(
                    "resume-authority-readiness",
                    "install-linking-fresh-recovery-runtime-proof",
                    ["prove-authority-ready"],
                    contract="chummer.install_linking_postgres_authority_readiness_proof.v1",
                    mutation_guard=True,
                )
                assert current is not None
                self._require_identity(current)
                if (
                    current.get("headGeneration") not in {0, 1}
                    or current.get("commitCount") != current.get("headGeneration")
                ):
                    raise RecoveryError("resume authority is not empty or exact generation 1")

            self.import_started = True
            self._run_job(
                "import-exact-local-intent",
                "install-linking-fresh-recovery-import",
                ["import-local", "--confirm-empty-authority"],
                mutation_guard=True,
            )
            post_import = self._run_post_import_proofs()
            self._write_final(status="pass", reason=None, post_import=post_import)
            self._release_lease()
            return self.inputs.receipt_root / RECOVERY_FILE
        except Exception as error:
            retained_intent_sha256: str | None = None
            if self.import_started:
                try:
                    observed = self._preflight("post-failure-local-recovery-preflight")
                    if observed.get("intentPresent"):
                        retained_intent_sha256 = str(observed["intentSha256"])
                except Exception:
                    pass
            ambiguous = self.durable_boundary_entered or self.import_started or isinstance(
                error, AmbiguousRecoveryError
            )
            self._write_final(
                status="unknown" if ambiguous else "fail",
                reason=type(error).__name__,
                retained_intent_sha256=retained_intent_sha256,
            )
            if not ambiguous:
                self._release_lease()
            if ambiguous:
                raise AmbiguousRecoveryError(
                    "fresh-authority recovery entered a durable boundary; preserve receipts, lease, and exact import intent"
                ) from error
            raise


def parse_args(argv: Sequence[str] | None = None) -> RecoveryInputs:
    parser = argparse.ArgumentParser(
        description="Preflight or govern an explicit InstallLinking fresh-authority recovery."
    )
    parser.add_argument("--recovery-id", required=True)
    parser.add_argument("--receipt-root", required=True, type=Path)
    parser.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--tool-image-id", required=True)
    parser.add_argument("--state-volume-name", required=True)
    parser.add_argument("--network-name", required=True)
    parser.add_argument("--expected-new-authority-identity-sha256")
    parser.add_argument("--expected-old-authority-identity-sha256")
    parser.add_argument("--expected-old-authority-state-sha256")
    parser.add_argument("--expected-old-head-generation", type=int)
    parser.add_argument("--expected-old-commit-count", type=int)
    parser.add_argument("--operator-decision-receipt", type=Path)
    parser.add_argument("--operator-decision-receipt-sha256")
    parser.add_argument(CONFIRMATION, action="store_true", dest="mutate")
    parser.add_argument("--resume-unknown", action="store_true")
    parser.add_argument(
        "--required-stopped-container",
        action="append",
        default=[],
        dest="stopped_containers",
    )
    args = parser.parse_args(argv)
    if args.resume_unknown and not args.mutate:
        parser.error("--resume-unknown requires the history-reset confirmation")
    mutation_values = (
        args.expected_new_authority_identity_sha256,
        args.expected_old_authority_identity_sha256,
        args.expected_old_authority_state_sha256,
        args.expected_old_head_generation,
        args.expected_old_commit_count,
        args.operator_decision_receipt,
        args.operator_decision_receipt_sha256,
    )
    if args.mutate and any(value is None for value in mutation_values):
        parser.error("history-reset mutation requires every decision and authority binding")
    if not args.mutate and any(value is not None for value in mutation_values):
        parser.error("decision and history-reset authority inputs require the confirmation flag")
    stopped = tuple(args.stopped_containers) or (
        "chummer6-hub-chummer-portal-1",
        "chummer6-hub-chummer-run-cloudflared-1",
        "chummer6-hub-chummer-run-cloudflared-replica-1",
    )
    return RecoveryInputs(
        recovery_id=args.recovery_id,
        receipt_root=args.receipt_root.resolve(),
        compose_file=args.compose_file.resolve(),
        env_file=args.env_file.resolve(),
        project_name=args.project_name,
        tool_image_id=args.tool_image_id,
        state_volume_name=args.state_volume_name,
        network_name=args.network_name,
        expected_new_authority_identity_sha256=args.expected_new_authority_identity_sha256,
        expected_old_authority_identity_sha256=args.expected_old_authority_identity_sha256,
        expected_old_authority_state_sha256=args.expected_old_authority_state_sha256,
        expected_old_head_generation=args.expected_old_head_generation,
        expected_old_commit_count=args.expected_old_commit_count,
        decision_receipt=args.operator_decision_receipt.resolve() if args.operator_decision_receipt else None,
        decision_receipt_sha256=args.operator_decision_receipt_sha256,
        mutate=args.mutate,
        resume_unknown=args.resume_unknown,
        stopped_container_names=stopped,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        output = RecoveryController(parse_args(argv)).run()
    except AmbiguousRecoveryError as error:
        print(str(error), file=sys.stderr)
        return 75
    except (RecoveryError, PublicEdgeMutationLockUnavailable, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
