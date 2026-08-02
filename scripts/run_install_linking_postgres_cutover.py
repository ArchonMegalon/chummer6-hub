#!/usr/bin/env python3
"""Run the governed, predeploy InstallLinking PostgreSQL cutover boundary.

This operator owns no provider API and never reads a provider token. It builds uniquely tagged
candidate images, executes bounded Compose jobs from inspected stopped containers, and records
enough immutable evidence for the cutover-boundary materializer to verify every phase.

An explicitly selected synthetic workspace may replace canonical dependency paths. Every source
must be a sealed, standalone Git repository beneath that root and bind an exact content digest,
origin, and main commit. The ownership and mode seal prevents accidental or cross-user mutation;
an actor already running as the operator UID can remove that seal and is outside this boundary.
The final pre-execution bind narrows that mutation window but does not claim atomic pathname
immunity from an actor already running as the operator UID.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

try:
    from scripts.public_edge_build_policy import (
        PUBLIC_EDGE_BUILD_ARG_NAMES,
        PUBLIC_EDGE_BUILD_KEYS_BY_SERVICE,
        PUBLIC_EDGE_BUILD_SERVICE_TARGETS,
        PUBLIC_EDGE_COMPOSE_TOP_LEVEL_KEYS,
        PUBLIC_EDGE_DOCKER_COPY_STAGE_REFERENCES_BY_STAGE,
        PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE,
        PUBLIC_EDGE_DOCKER_NAMED_CONTEXTS_BY_STAGE,
        PUBLIC_EDGE_DOCKER_STAGE_ORDER,
        PUBLIC_EDGE_NAMED_CONTEXT_NAMES,
        PUBLIC_EDGE_RAW_SERVICE_IMAGES,
        PUBLIC_EDGE_RAW_SERVICE_KEYS_BY_SERVICE,
        PUBLIC_EDGE_RENDERED_BUILD_SERVICE_NAMES,
        PUBLIC_EDGE_RENDERED_SERVICE_KEYS_BY_SERVICE,
        PUBLIC_EDGE_SERVICE_PROFILES_BY_SERVICE,
        docker_context_policy_findings,
        docker_copy_from_reference,
        docker_instruction_uses_mount,
        docker_logical_instruction_records,
        docker_logical_instructions,
        dockerfile_parser_directive_findings,
        public_edge_compose_build_syntax_failures,
        public_edge_rendered_compose_failures,
        rendered_build_contract_matches,
    )
    from scripts.materialize_install_linking_cutover_boundary import (
        PHASE_EVIDENCE_CONTRACT,
        POSTQUIESCE_REPROOF_CONTRACT,
        POSTQUIESCE_REPROOF_PHASE,
        PUBLIC_EDGE_CUTOVER_POSTDEPLOY_SCHEMA_SHA256,
        PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME,
        bind_active_build_info,
        bind_state_volume_inventory,
        materialize as materialize_boundary,
    )
    from scripts.public_edge_mutation_lock import (
        AUTH_ROOT,
        LOCK_PATH,
        MutationLease,
        PublicEdgeMutationLockUnavailable,
        acquire_mutation_lease,
        release_mutation_lease,
    )
    from scripts.strict_json_contract import (
        StrictJsonContractError,
        canonical_json_bytes,
        strict_json_object,
    )
    from scripts.verify_install_linking_cutover_boundary import verify_boundary
except ModuleNotFoundError:
    from public_edge_build_policy import (
        PUBLIC_EDGE_BUILD_ARG_NAMES,
        PUBLIC_EDGE_BUILD_KEYS_BY_SERVICE,
        PUBLIC_EDGE_BUILD_SERVICE_TARGETS,
        PUBLIC_EDGE_COMPOSE_TOP_LEVEL_KEYS,
        PUBLIC_EDGE_DOCKER_COPY_STAGE_REFERENCES_BY_STAGE,
        PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE,
        PUBLIC_EDGE_DOCKER_NAMED_CONTEXTS_BY_STAGE,
        PUBLIC_EDGE_DOCKER_STAGE_ORDER,
        PUBLIC_EDGE_NAMED_CONTEXT_NAMES,
        PUBLIC_EDGE_RAW_SERVICE_IMAGES,
        PUBLIC_EDGE_RAW_SERVICE_KEYS_BY_SERVICE,
        PUBLIC_EDGE_RENDERED_BUILD_SERVICE_NAMES,
        PUBLIC_EDGE_RENDERED_SERVICE_KEYS_BY_SERVICE,
        PUBLIC_EDGE_SERVICE_PROFILES_BY_SERVICE,
        docker_context_policy_findings,
        docker_copy_from_reference,
        docker_instruction_uses_mount,
        docker_logical_instruction_records,
        docker_logical_instructions,
        dockerfile_parser_directive_findings,
        public_edge_compose_build_syntax_failures,
        public_edge_rendered_compose_failures,
        rendered_build_contract_matches,
    )
    from materialize_install_linking_cutover_boundary import (
        PHASE_EVIDENCE_CONTRACT,
        POSTQUIESCE_REPROOF_CONTRACT,
        POSTQUIESCE_REPROOF_PHASE,
        PUBLIC_EDGE_CUTOVER_POSTDEPLOY_SCHEMA_SHA256,
        PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME,
        bind_active_build_info,
        bind_state_volume_inventory,
        materialize as materialize_boundary,
    )
    from public_edge_mutation_lock import (
        AUTH_ROOT,
        LOCK_PATH,
        MutationLease,
        PublicEdgeMutationLockUnavailable,
        acquire_mutation_lease,
        release_mutation_lease,
    )
    from strict_json_contract import (
        StrictJsonContractError,
        canonical_json_bytes,
        strict_json_object,
    )
    from verify_install_linking_cutover_boundary import verify_boundary


CONTRACT_NAME = "chummer.install_linking_postgres_cutover_run.v1"
CANDIDATE_BUILD_INFO_CONTRACT = (
    "chummer.install_linking_postgres_candidate_build_info.v1"
)
SOURCE_REPLAY_PREFLIGHT_CONTRACT = (
    "chummer.install_linking_postgres_source_replay_preflight.v1"
)
JOB_RECEIPT_CONTRACT = "chummer.install_linking_postgres_operator_job.v1"
START_INTENT_CONTRACT = "chummer.install_linking_postgres_start_intent.v1"
REVIEWED_HUB_REGISTRY_DOCKERIGNORE = (
    b".git\n"
    b".github\n"
    b".runtime\n"
    b".tmp\n"
    b".vexp\n"
    b"**/bin\n"
    b"**/obj\n"
    b"**/__pycache__\n"
    b"*.log\n"
)
JOB_TIMEOUT_SECONDS = 180
COMMAND_TIMEOUT_SECONDS = 30
SYNTHETIC_GIT_FSCK_TIMEOUT_SECONDS = 5 * 60
BUILD_TIMEOUT_SECONDS = 20 * 60
MAX_COMMAND_OUTPUT_BYTES = 2 * 1024 * 1024
CANONICAL_ENV_FILE = Path("/docker/chummercomplete/chummer.run-services/.env")
CANONICAL_BUILD_CONTEXT = Path("/docker/chummercomplete")
CANONICAL_DOCKER_CONFIG_ROOT = Path(
    "/docker/chummercomplete/.state/public-edge-docker-cli"
)
CANONICAL_FLEET_MEDIA_REPOSITORY = Path(
    "/docker/fleet/repos/chummer-media-factory"
)
CANONICAL_DESIGN_PRODUCT = Path("/docker/chummercomplete/chummer-design")
CANONICAL_HUB_REGISTRY = Path(
    "/docker/chummercomplete/chummer-hub-registry"
)
BUILD_DEPENDENCY_PROVENANCE_CONTRACT = (
    "chummer.install_linking_postgres_build_dependency_provenance.v1"
)
SOURCE_CONTENT_MANIFEST_CONTRACT = (
    "chummer.install_linking_postgres_source_content_manifest.v1"
)
MAX_SOURCE_FILE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_SOURCE_FILE_COUNT = 200_000
DOCKERFILE_FRONTEND_REFERENCE = (
    "docker/dockerfile:1.4@sha256:"
    "9ba7531bd80fb0a858632727cf7a112fbfd19b17e94c4e84ced81e24ef1a0dbc"
)
DOCKER_BASE_IMAGE_REFERENCES = {
    "build": (
        "mcr.microsoft.com/dotnet/sdk:10.0.103@sha256:"
        "e362a8dbcd691522456da26a5198b8f3ca1d7641c95624fadc5e3e82678bd08a"
    ),
    "hub-package-feed": (
        "mcr.microsoft.com/dotnet/sdk:10.0.103@sha256:"
        "e362a8dbcd691522456da26a5198b8f3ca1d7641c95624fadc5e3e82678bd08a"
    ),
    "install-linking-postgres-tool-final": (
        "mcr.microsoft.com/dotnet/aspnet:10.0@sha256:"
        "1fa23fc4872d95fd71c2833ebe65d7e84a43b2d51a31d119516852f13d9505a7"
    ),
    "public-pwa-proof": (
        "python:3.12-slim@sha256:"
        "c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28"
    ),
    "final": (
        "mcr.microsoft.com/dotnet/aspnet:10.0@sha256:"
        "1fa23fc4872d95fd71c2833ebe65d7e84a43b2d51a31d119516852f13d9505a7"
    ),
}
RUN_SERVICES_PACKAGE_INPUTS = (
    "Directory.Build.props",
    "global.json",
    "eng/NuGet.Container.Config",
    "eng/package-plane.lock.json",
    "scripts/ai/bootstrap-hub-package-feed.py",
    "scripts/public_edge_postdeploy_contract.py",
    "scripts/public_edge_postdeploy_gate.v1.schema.json",
    "Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj",
    "Chummer.Run.LoopbackProbe/Chummer.Run.LoopbackProbe.csproj",
    "Chummer.Run.LoopbackProbe/packages.lock.json",
    "Chummer.Run.LoopbackProbe/Program.cs",
    "Chummer.Run.Api/Chummer.Run.Api.csproj",
    "Chummer.Run.Api/packages.lock.json",
    "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj",
    "Chummer.Campaign.Contracts/packages.lock.json",
    "Chummer.Control.Contracts/Chummer.Control.Contracts.csproj",
    "Chummer.Control.Contracts/packages.lock.json",
    "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj",
    "Chummer.Play.Contracts/packages.lock.json",
    "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj",
    "Chummer.Run.Contracts/packages.lock.json",
    "Chummer.World.Contracts/Chummer.World.Contracts.csproj",
    "Chummer.World.Contracts/packages.lock.json",
)
PACKAGE_PLANE_CONTRACT = "chummer-hub.package-plane-lock/v4"
PACKAGE_PLANE_BUILD_RECIPE = "scripts/ai/bootstrap-hub-package-feed.py"
PACKAGE_PLANE_DOTNET_SDK = "10.0.103"
CANONICAL_ORIGIN_URLS = {
    "run-services-source": (
        "https://github.com/ArchonMegalon/chummer6-hub.git"
    ),
    "hub-registry": (
        "https://github.com/ArchonMegalon/chummer6-hub-registry.git"
    ),
    "design-product": (
        "https://github.com/ArchonMegalon/chummer6-design.git"
    ),
    "fleet-media-factory-contracts": (
        "https://github.com/ArchonMegalon/chummer6-media-factory.git"
    ),
}
SYNTHETIC_SOURCE_KIND = "standalone-git-repository"
EXPECTED_NAMED_CONTEXT_COPY_INSTRUCTIONS_BY_STAGE = (
    PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE
)
CANONICAL_PROJECT = "chummer6-hub"
CANONICAL_DOCKER_CONTEXT = "default"
CANONICAL_DOCKER_HOST = "unix:///var/run/docker.sock"
PORTAL_CANONICAL_TAG = "chummer-run-api:local"
TOOL_CANONICAL_TAG = "chummer-install-linking-postgres-tool:local"
IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
HEX_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
HEAD_PATTERN = re.compile(r"[0-9a-f]{40}")
CUTOVER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}")
SAFE_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{0,127}")

JOB_SPECS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "transport-proof",
        "chummer-install-linking-postgres-admin",
        ("transport-proof",),
        "chummer.postgres_transport_proof.v1",
    ),
    (
        "prepare",
        "chummer-install-linking-postgres-admin",
        ("prepare",),
        "chummer.install_linking_postgres_prepare.v1",
    ),
    (
        "prove-empty-authority",
        "chummer-install-linking-postgres-runtime-proof",
        ("prove-empty-authority",),
        "chummer.install_linking_postgres_empty_authority_proof.v1",
    ),
    (
        "prove-runtime-role",
        "chummer-install-linking-postgres-runtime-proof",
        ("prove-runtime-role",),
        "chummer.install_linking_postgres_runtime_role_proof.v1",
    ),
    (
        "prove-local-store-absent",
        "chummer-install-linking-postgres-import-presence-proof",
        ("prove-local-store-absent",),
        "chummer.install_linking_local_store_absence_proof.v1",
    ),
    (
        "validate",
        "chummer-install-linking-postgres-admin",
        ("validate",),
        "chummer.install_linking_postgres_schema_validation.v1",
    ),
)
POSTQUIESCE_BASE_JOB_SPECS: tuple[
    tuple[str, str, tuple[str, ...], str], ...
] = (
    (
        "prove-local-store-absent",
        "chummer-install-linking-postgres-import-presence-proof",
        ("prove-local-store-absent",),
        "chummer.install_linking_local_store_absence_proof.v1",
    ),
    (
        "prove-empty-authority",
        "chummer-install-linking-postgres-runtime-proof",
        ("prove-empty-authority",),
        "chummer.install_linking_postgres_empty_authority_proof.v1",
    ),
    (
        "prove-runtime-role",
        "chummer-install-linking-postgres-runtime-proof",
        ("prove-runtime-role",),
        "chummer.install_linking_postgres_runtime_role_proof.v1",
    ),
)

PHASE_JOB_NAMES = {
    "prepare_completed": (
        "transport-proof",
        "prepare",
        "prove-empty-authority",
        "prove-runtime-role",
    ),
    "import_skipped_no_local_store": ("prove-local-store-absent",),
    "validate_completed": ("validate",),
}

EXPECTED_MOUNTS = {
    "chummer-install-linking-postgres-admin": {
        "/run/chummer-secrets/install-linking-postgres-migrator.connection-string": False,
        "/run/chummer-secrets/install-linking-postgres-server-ca.pem": False,
    },
    "chummer-install-linking-postgres-runtime-proof": {
        "/run/chummer-secrets/install-linking-postgres-runtime.connection-string": False,
        "/run/chummer-secrets/install-linking-postgres-server-ca.pem": False,
    },
    "chummer-install-linking-postgres-import-presence-proof": {
        "/app/state": False,
    },
}
EXPECTED_CRITICAL_ENVIRONMENT_KEYS = {
    "chummer-install-linking-postgres-admin": {
        "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE",
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE",
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST",
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT",
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
    },
    "chummer-install-linking-postgres-runtime-proof": {
        "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE",
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE",
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST",
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT",
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
    },
    "chummer-install-linking-postgres-import-presence-proof": {
        "CHUMMER_INSTALL_LINKING_STORE_PATH",
    },
}
EXPECTED_FIXED_CRITICAL_ENVIRONMENT = {
    "chummer-install-linking-postgres-admin": {
        "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE": (
            "/run/chummer-secrets/"
            "install-linking-postgres-migrator.connection-string"
        ),
    },
    "chummer-install-linking-postgres-runtime-proof": {
        "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE": (
            "/run/chummer-secrets/"
            "install-linking-postgres-runtime.connection-string"
        ),
    },
    "chummer-install-linking-postgres-import-presence-proof": {
        "CHUMMER_INSTALL_LINKING_STORE_PATH": (
            "/app/state/install-linking/install-linking-store.json"
        ),
    },
}
EXPECTED_TMPFS_OPTIONS = {
    "mode=1777",
    "nodev",
    "noexec",
    "nosuid",
    "rw",
}
DOCKER_EXCLUDED_IGNORED_COMPONENTS = {
    ".artifacts",
    ".codex-studio",
    ".pytest_cache",
    ".state",
    ".tmp",
    ".vexp",
    ".vs",
    "TestResults",
    "__pycache__",
    "bin",
    "deploy-readiness",
    "dist",
    "docs",
    "feedback",
    "node_modules",
    "obj",
    "out",
    "test-results",
    "tests",
    "unpublished",
}
DOCKER_EXCLUDED_IGNORED_SUFFIXES = {
    ".bin",
    ".deb",
    ".dmg",
    ".exe",
    ".key",
    ".msi",
    ".nupkg",
    ".p12",
    ".pem",
    ".pfx",
    ".snupkg",
    ".trx",
    ".zip",
}


class CutoverError(RuntimeError):
    """A fail-closed error before the database state became ambiguous."""


class AmbiguousCutoverError(CutoverError):
    """A post-start condition that requires manual inspection and retains the lock."""


class CommandDeadlineExceeded(CutoverError):
    """A bounded subprocess exhausted its supplied monotonic budget."""


class JobWaitAmbiguity(AmbiguousCutoverError):
    def __init__(self, message: str, *, timed_out: bool):
        super().__init__(message)
        self.timed_out = timed_out


class CutoverSignal(BaseException):
    def __init__(self, signum: int):
        super().__init__(f"operator received signal {signum}")
        self.signum = signum


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def critical_environment_sha256(
    service: str,
    environment: dict[str, str],
) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "service": service,
                "values": {
                    key: environment[key]
                    for key in sorted(
                        EXPECTED_CRITICAL_ENVIRONMENT_KEYS[service]
                    )
                },
            },
            label=f"{service} critical environment",
        )
    )


def postquiesce_job_specs(
    attempt_id: str,
) -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
    return tuple(
        (
            f"postquiesce-{attempt_id}-{proof_name}",
            service,
            command,
            proof_contract,
        )
        for proof_name, service, command, proof_contract in (
            POSTQUIESCE_BASE_JOB_SPECS
        )
    )


def validate_inherited_mutation_lock(
    token: str,
    *,
    expected_identity: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int, int]:
    if re.fullmatch(r"[0-9a-f]{64}", token) is None:
        raise CutoverError("shared mutation lock token is malformed")
    lock_metadata = LOCK_PATH.lstat()
    if (
        stat.S_ISLNK(lock_metadata.st_mode)
        or not stat.S_ISDIR(lock_metadata.st_mode)
        or lock_metadata.st_uid != os.getuid()
        or stat.S_IMODE(lock_metadata.st_mode) != 0o700
    ):
        raise CutoverError("shared mutation lock has unsafe identity")
    if sorted(entry.name for entry in os.scandir(LOCK_PATH)) != ["owner-token"]:
        raise CutoverError("shared mutation lock contains unexpected entries")
    token_path = LOCK_PATH / "owner-token"
    token_metadata = token_path.lstat()
    if (
        stat.S_ISLNK(token_metadata.st_mode)
        or not stat.S_ISREG(token_metadata.st_mode)
        or token_metadata.st_nlink != 1
        or token_metadata.st_uid != os.getuid()
        or stat.S_IMODE(token_metadata.st_mode) != 0o600
    ):
        raise CutoverError("shared mutation lock token has unsafe identity")
    descriptor = os.open(
        token_path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        payload = os.read(descriptor, 129)
        if len(payload) > 128:
            raise CutoverError("shared mutation lock token is oversized")
    finally:
        os.close(descriptor)
    lock_after = LOCK_PATH.lstat()
    token_after = token_path.lstat()
    identity = (
        lock_metadata.st_dev,
        lock_metadata.st_ino,
        opened.st_dev,
        opened.st_ino,
    )
    if (
        identity
        != (
            lock_after.st_dev,
            lock_after.st_ino,
            token_after.st_dev,
            token_after.st_ino,
        )
        or (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        != (
            token_after.st_dev,
            token_after.st_ino,
            token_after.st_size,
            token_after.st_mtime_ns,
            token_after.st_ctime_ns,
        )
        or expected_identity is not None
        and identity != expected_identity
    ):
        raise CutoverError("shared mutation lock identity changed")
    try:
        observed_token = payload.decode("ascii", "strict").strip()
    except UnicodeDecodeError as exc:
        raise CutoverError("shared mutation lock token is not ASCII") from exc
    if not hmac.compare_digest(observed_token, token):
        raise CutoverError("shared mutation lock token does not own the active lock")
    return identity


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


def validate_private_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise CutoverError("receipt root must be absolute")
    normalized = Path(os.path.abspath(path))
    current = Path(normalized.anchor)
    for component in normalized.parts[1:]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise CutoverError("receipt root must not contain symlinks")
    metadata = normalized.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise CutoverError("receipt root must be caller-owned mode 0700")
    return normalized


def atomic_private_write(path: Path, payload: bytes, *, replace: bool = False) -> None:
    if not path.is_absolute() or path.parent != validate_private_directory(path.parent):
        raise CutoverError("private output path is outside its validated directory")
    if path.is_symlink():
        raise CutoverError("private output must not be a symlink")
    if path.exists() and not replace:
        raise CutoverError(f"private output already exists: {path.name}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_private_json(
    path: Path,
    payload: dict[str, Any],
    *,
    replace: bool = False,
) -> str:
    encoded = canonical_json_bytes(payload, label=path.name)
    atomic_private_write(path, encoded, replace=replace)
    return sha256_bytes(encoded)


def hash_regular_file(
    path: Path,
    *,
    owner_only: bool,
    maximum_bytes: int = 16 * 1024 * 1024,
    allow_empty: bool = False,
) -> str:
    if not path.is_absolute():
        raise CutoverError("bound input must be absolute")
    normalized = Path(os.path.abspath(path))
    metadata = normalized.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or (not allow_empty and metadata.st_size <= 0)
        or metadata.st_size > maximum_bytes
        or (owner_only and (
            metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ))
    ):
        raise CutoverError("bound input is not a safe regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise CutoverError("bound input is oversized")
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        or total != before.st_size
    ):
        raise CutoverError("bound input changed while hashing")
    path_after = normalized.lstat()
    if (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_size,
        path_after.st_mtime_ns,
        path_after.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise CutoverError("bound input pathname changed after hashing")
    return digest.hexdigest()


def read_regular_file_bytes(
    path: Path,
    *,
    maximum_bytes: int = 16 * 1024 * 1024,
) -> bytes:
    if not path.is_absolute():
        raise CutoverError("bound source input must be absolute")
    normalized = Path(os.path.abspath(path))
    metadata = normalized.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size <= 0
        or metadata.st_size > maximum_bytes
    ):
        raise CutoverError("bound source input is not a safe regular file")
    descriptor = os.open(
        normalized,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise CutoverError("bound source input is oversized")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_after = normalized.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
    )
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        )
        or identity
        != (
            path_after.st_dev,
            path_after.st_ino,
            path_after.st_size,
            path_after.st_mtime_ns,
            path_after.st_ctime_ns,
            path_after.st_nlink,
        )
        or total != before.st_size
    ):
        raise CutoverError("bound source input changed while being read")
    return b"".join(chunks)


def read_private_canonical_json(
    path: Path,
    *,
    maximum_bytes: int = MAX_COMMAND_OUTPUT_BYTES,
) -> tuple[dict[str, Any], str]:
    if not path.is_absolute():
        raise CutoverError("private JSON input must be absolute")
    normalized = Path(os.path.abspath(path))
    metadata = normalized.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size <= 0
        or metadata.st_size > maximum_bytes
    ):
        raise CutoverError(
            "private JSON input is not a caller-owned mode-0600 regular file"
        )
    descriptor = os.open(
        normalized,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise CutoverError("private JSON input is oversized")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_after = normalized.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
        stat.S_IMODE(before.st_mode),
    )
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
            stat.S_IMODE(after.st_mode),
        )
        or identity
        != (
            path_after.st_dev,
            path_after.st_ino,
            path_after.st_size,
            path_after.st_mtime_ns,
            path_after.st_ctime_ns,
            path_after.st_nlink,
            stat.S_IMODE(path_after.st_mode),
        )
        or total != before.st_size
    ):
        raise CutoverError("private JSON input changed while being read")
    raw = b"".join(chunks)
    try:
        payload = strict_json_object(raw, label=path.name)
        canonical = canonical_json_bytes(payload, label=path.name)
    except StrictJsonContractError as exc:
        raise CutoverError("private JSON input is not canonical JSON") from exc
    if raw != canonical:
        raise CutoverError("private JSON input is not canonical JSON")
    return payload, sha256_bytes(raw)


def require_safe_source_directory(path: Path, *, label: str) -> Path:
    normalized = Path(os.path.abspath(path))
    try:
        metadata = normalized.lstat()
        resolved = normalized.resolve(strict=True)
    except OSError as exc:
        raise CutoverError(f"{label} source directory is unavailable") from exc
    if (
        not path.is_absolute()
        or resolved != normalized
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise CutoverError(
            f"{label} source directory must be absolute and non-symlinked"
        )
    return normalized


def require_path_within(
    path: Path,
    root: Path,
    *,
    label: str,
    allow_root: bool = False,
) -> None:
    if path == root:
        if allow_root:
            return
        raise CutoverError(f"{label} must be strictly beneath the synthetic root")
    if root not in path.parents:
        raise CutoverError(f"{label} is outside the approved synthetic root")


def _source_file_record(root: Path, relative_path: str) -> dict[str, Any]:
    relative = Path(relative_path)
    if (
        not relative_path
        or relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != relative_path
    ):
        raise CutoverError("source content contains an unsafe relative path")
    path = root / relative
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CutoverError("source content entry is unavailable") from exc
    if (
        resolved != path
        or stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > MAX_SOURCE_FILE_BYTES
    ):
        raise CutoverError(
            "source content entries must be non-symlinked regular files"
        )
    digest = hash_regular_file(
        path,
        owner_only=False,
        maximum_bytes=MAX_SOURCE_FILE_BYTES,
        allow_empty=True,
    )
    after = path.lstat()
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
        raise CutoverError("source content entry changed while being hashed")
    return {
        "mode": f"{stat.S_IMODE(before.st_mode):04o}",
        "path": relative_path,
        "sha256": digest,
        "size": before.st_size,
    }


def source_content_sha256(
    root: Path,
    relative_paths: Iterable[str],
) -> tuple[str, int, str]:
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for relative_path in sorted(set(relative_paths)):
        record = _source_file_record(root, relative_path)
        entries.append(record)
        total_bytes += int(record["size"])
        if (
            len(entries) > MAX_SOURCE_FILE_COUNT
            or total_bytes > MAX_SOURCE_TOTAL_BYTES
        ):
            raise CutoverError("source content manifest exceeds governed bounds")
    if not entries:
        raise CutoverError("source content manifest is empty")
    file_set_sha256 = sha256_bytes(
        "".join(f"{entry['path']}\n" for entry in entries).encode("utf-8")
    )
    digest = sha256_bytes(
        canonical_json_bytes(
            {
                "contractName": SOURCE_CONTENT_MANIFEST_CONTRACT,
                "entries": entries,
            },
            label="source content manifest",
        )
    )
    return digest, len(entries), file_set_sha256


def _synthetic_entry_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_uid,
    )


def validate_synthetic_workspace_root(root: Path) -> None:
    metadata = root.lstat()
    if metadata.st_uid != os.getuid():
        raise CutoverError("synthetic workspace must be owned by the operator UID")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise CutoverError("synthetic workspace must have exact mode 0700")


def validate_sealed_standalone_repository(repository: Path) -> None:
    """Validate a read-only, current-UID tree with local unaliased Git storage."""

    operator_uid = os.getuid()
    git_root = repository / ".git"
    try:
        git_metadata = git_root.lstat()
    except OSError as exc:
        raise CutoverError(
            "synthetic source has no local Git metadata directory"
        ) from exc
    if (
        not stat.S_ISDIR(git_metadata.st_mode)
        or stat.S_ISLNK(git_metadata.st_mode)
    ):
        raise CutoverError(
            "synthetic source must use a real local .git directory"
        )

    def visit(directory: Path, *, require_content: bool) -> bool:
        before = directory.lstat()
        if (
            not stat.S_ISDIR(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != operator_uid
            or stat.S_IMODE(before.st_mode) & 0o222
        ):
            raise CutoverError(
                "synthetic source directories must be operator-owned and sealed"
            )
        has_content = False
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            path = directory / entry.name
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or metadata.st_uid != operator_uid
                or stat.S_IMODE(metadata.st_mode) & 0o222
            ):
                raise CutoverError(
                    "synthetic source entries must be operator-owned, non-symlinked, and sealed"
                )
            if stat.S_ISDIR(metadata.st_mode):
                if path == git_root:
                    visit(path, require_content=False)
                    continue
                child_has_content = visit(
                    path,
                    require_content=require_content,
                )
                has_content = has_content or child_has_content
            elif stat.S_ISREG(metadata.st_mode):
                if metadata.st_nlink != 1:
                    raise CutoverError(
                        "synthetic source files must have one unaliased link"
                    )
                has_content = True
            else:
                raise CutoverError("synthetic source contains a special file")
        after = directory.lstat()
        if _synthetic_entry_identity(before) != _synthetic_entry_identity(after):
            raise CutoverError(
                "synthetic source changed while its seal was inspected"
            )
        if require_content and not has_content:
            raise CutoverError(
                "synthetic source contains an unbound empty directory"
            )
        return has_content

    visit(repository, require_content=True)
    forbidden_git_indirections = (
        git_root / "commondir",
        git_root / "worktrees",
        git_root / "shallow",
        git_root / "info" / "grafts",
        git_root / "objects" / "info" / "alternates",
        git_root / "objects" / "info" / "http-alternates",
    )
    if any(path.exists() or path.is_symlink() for path in forbidden_git_indirections):
        raise CutoverError(
            "synthetic source uses forbidden shared, shallow, alternate, or grafted Git state"
        )
    promisor_packs = tuple((git_root / "objects" / "pack").glob("*.promisor"))
    if promisor_packs:
        raise CutoverError("synthetic source uses partial/promisor Git objects")


_docker_logical_instruction_records = docker_logical_instruction_records


def require_candidate_dockerfile_parser_policy(text: str) -> None:
    exact_syntax, late_directives = dockerfile_parser_directive_findings(
        text,
        expected_syntax_directive=(
            f"# syntax={DOCKERFILE_FRONTEND_REFERENCE}"
        ),
    )
    if not exact_syntax or late_directives:
        raise CutoverError(
            "candidate Dockerfile parser directive contract drifted"
        )


def require_public_edge_compose_build_syntax(text: str) -> None:
    failures = public_edge_compose_build_syntax_failures(text)
    if failures:
        raise CutoverError(
            "raw Compose build authority drifted: " + failures[0]
        )


class CommandRunner:
    def __init__(
        self,
        *,
        docker_config_root: Path,
        routing_environment: dict[str, str] | None = None,
    ):
        self._environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(docker_config_root / "home"),
            "DOCKER_CONFIG": str(docker_config_root / "config"),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
        self._environment.update(routing_environment or {})

    def run(
        self,
        arguments: Sequence[str],
        *,
        timeout: float = COMMAND_TIMEOUT_SECONDS,
        check: bool = True,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                list(arguments),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandDeadlineExceeded(
                "bounded operator command timed out"
            ) from exc
        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
        if len(stdout) > MAX_COMMAND_OUTPUT_BYTES or len(stderr) > MAX_COMMAND_OUTPUT_BYTES:
            raise CutoverError("bounded operator command output is oversized")
        if check and completed.returncode != 0:
            raise CutoverError(
                f"bounded operator command failed with status {completed.returncode}"
            )
        return CommandResult(completed.returncode, stdout, stderr)

    @property
    def environment(self) -> dict[str, str]:
        return dict(self._environment)


@dataclass(frozen=True)
class CutoverInputs:
    source_root: Path
    compose_file: Path
    env_file: Path
    receipt_root: Path
    boundary_output: Path
    expected_head: str
    compose_sha256: str
    env_sha256: str
    runner_sha256: str
    expected_hub_registry_head: str
    expected_design_product_head: str
    expected_fleet_media_factory_head: str
    expected_build_context_dockerignore_sha256: str
    cutover_id: str
    synthetic_workspace_root: Path | None = None
    build_context_root: Path = CANONICAL_BUILD_CONTEXT
    hub_registry_root: Path = CANONICAL_HUB_REGISTRY
    design_product_root: Path = CANONICAL_DESIGN_PRODUCT
    fleet_media_factory_root: Path = CANONICAL_FLEET_MEDIA_REPOSITORY
    expected_run_services_content_sha256: str | None = None
    expected_hub_registry_content_sha256: str | None = None
    expected_design_product_content_sha256: str | None = None
    expected_fleet_media_factory_content_sha256: str | None = None


def validate_build_workspace_paths(inputs: CutoverInputs) -> None:
    source_roots = {
        "run-services-source": inputs.source_root,
        "hub-registry": inputs.hub_registry_root,
        "design-product": inputs.design_product_root,
        "fleet-media-factory-contracts": inputs.fleet_media_factory_root,
    }
    content_pins = {
        "run-services-source": inputs.expected_run_services_content_sha256,
        "hub-registry": inputs.expected_hub_registry_content_sha256,
        "design-product": inputs.expected_design_product_content_sha256,
        "fleet-media-factory-contracts": (
            inputs.expected_fleet_media_factory_content_sha256
        ),
    }
    if inputs.synthetic_workspace_root is None:
        if (
            inputs.build_context_root != CANONICAL_BUILD_CONTEXT
            or inputs.hub_registry_root != CANONICAL_HUB_REGISTRY
            or inputs.design_product_root != CANONICAL_DESIGN_PRODUCT
            or inputs.fleet_media_factory_root
            != CANONICAL_FLEET_MEDIA_REPOSITORY
            or any(value is not None for value in content_pins.values())
        ):
            raise CutoverError(
                "noncanonical build sources require an approved synthetic root"
            )
        return

    synthetic_root = require_safe_source_directory(
        inputs.synthetic_workspace_root,
        label="synthetic workspace",
    )
    validate_synthetic_workspace_root(synthetic_root)
    build_context_root = require_safe_source_directory(
        inputs.build_context_root,
        label="build context",
    )
    require_path_within(
        build_context_root,
        synthetic_root,
        label="build context",
        allow_root=True,
    )
    if (
        build_context_root != inputs.source_root
        and build_context_root not in inputs.source_root.parents
    ):
        raise CutoverError(
            "synthetic build context must contain the run-services source"
        )
    if (
        inputs.build_context_root == CANONICAL_BUILD_CONTEXT
        or inputs.hub_registry_root == CANONICAL_HUB_REGISTRY
        or inputs.design_product_root == CANONICAL_DESIGN_PRODUCT
        or inputs.fleet_media_factory_root
        == CANONICAL_FLEET_MEDIA_REPOSITORY
    ):
        raise CutoverError(
            "synthetic workspace cannot fall back to a canonical source path"
        )
    normalized_roots: dict[str, Path] = {}
    for name, path in source_roots.items():
        normalized = require_safe_source_directory(path, label=name)
        require_path_within(normalized, synthetic_root, label=name)
        validate_sealed_standalone_repository(normalized)
        normalized_roots[name] = normalized
    root_items = list(normalized_roots.items())
    for index, (name, path) in enumerate(root_items):
        for other_name, other_path in root_items[index + 1 :]:
            if (
                path == other_path
                or path in other_path.parents
                or other_path in path.parents
            ):
                raise CutoverError(
                    "synthetic source repositories must be distinct siblings: "
                    f"{name}, {other_name}"
                )
    for name, content_pin in content_pins.items():
        if (
            content_pin is None
            or HEX_SHA256_PATTERN.fullmatch(content_pin) is None
        ):
            raise CutoverError(
                f"{name} requires an exact synthetic content pin"
            )


def build_routing_environment(inputs: CutoverInputs) -> dict[str, str]:
    return {
        "CHUMMER_BUILD_CONCURRENCY": "1",
        "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(inputs.build_context_root),
        "CHUMMER_RUN_SERVICES_CONTEXT_DIR": str(inputs.source_root),
        "CHUMMER_RUN_SERVICES_SOURCE": str(inputs.source_root),
        "CHUMMER_HUB_REGISTRY_SOURCE": str(inputs.hub_registry_root),
        "CHUMMER_DESIGN_PRODUCT_SOURCE": str(inputs.design_product_root),
        "CHUMMER_FLEET_MEDIA_FACTORY_CONTRACTS_SOURCE": str(
            inputs.fleet_media_factory_root
            / "src"
            / "Chummer.Media.Contracts"
        ),
    }


class GovernedCutoverRunner:
    def __init__(
        self,
        inputs: CutoverInputs,
        *,
        command_runner: CommandRunner,
        lock_path: Path = LOCK_PATH,
        lock_authorization_root: Path = AUTH_ROOT,
    ):
        self.inputs = inputs
        self.commands = command_runner
        self.lock_path = lock_path
        self.lock_authorization_root = lock_authorization_root
        self.lease: MutationLease | None = None
        self.start_intent_written = False
        self.container_start_may_have_been_invoked = False
        self.active_container_id: str | None = None
        self.job_receipts: dict[str, tuple[Path, str]] = {}
        self.candidate_image_id = ""
        self.candidate_tool_image_id = ""
        self.candidate_build_info_path = (
            inputs.receipt_root
            / "INSTALL_LINKING_POSTGRES_CANDIDATE_BUILD_INFO.generated.json"
        )
        self.candidate_build_info_sha256 = ""
        suffix = hashlib.sha256(inputs.cutover_id.encode("utf-8")).hexdigest()[:24]
        self.portal_tag = f"chummer-run-api:cutover-{suffix}"
        self.tool_tag = f"chummer-install-linking-postgres-tool:cutover-{suffix}"
        self.name_suffix = suffix
        self.build_override = inputs.receipt_root / "compose.cutover-images.override.json"
        self.secret_canary = secrets.token_hex(32)
        self.secret_canary_sha256 = sha256_bytes(self.secret_canary.encode("ascii"))
        self.public_network_name = ""
        self.public_network_id = ""
        self.expected_mount_source_sha256: dict[str, dict[str, str]] = {}
        self.expected_critical_environment_sha256: dict[str, str] = {}
        self.build_source_provenance: dict[str, dict[str, Any]] = {}
        self.volume_inventory_receipt_path: Path | None = None
        self.volume_inventory_receipt_sha256 = ""
        self.runtime_role_sha256 = ""
        self.authority_identity_sha256 = ""

    def _docker(self, *arguments: str) -> list[str]:
        return [
            "/usr/bin/docker",
            "--context",
            CANONICAL_DOCKER_CONTEXT,
            *arguments,
        ]

    def _compose(
        self,
        *arguments: str,
        overrides: Iterable[Path] = (),
        project: str = CANONICAL_PROJECT,
    ) -> list[str]:
        command = self._docker(
            "compose",
            "--env-file",
            str(self.inputs.env_file),
            "-p",
            project,
            "-f",
            str(self.inputs.compose_file),
            "-f",
            str(self.build_override),
        )
        for override in overrides:
            command.extend(["-f", str(override)])
        command.extend(["--project-directory", str(self.inputs.source_root)])
        command.extend(arguments)
        return command

    def _job_project(self, job_name: str) -> str:
        job_hash = hashlib.sha256(job_name.encode("utf-8")).hexdigest()[:12]
        return f"chummer6-ilpg-{self.name_suffix[:16]}-{job_hash}"

    def _resolve_image(self, tag: str, *, allow_absent: bool = False) -> str:
        result = self.commands.run(
            self._docker("image", "inspect", tag, "--format", "{{.Id}}"),
            check=False,
        )
        if result.returncode != 0:
            if allow_absent:
                return ""
            raise CutoverError("required image tag is unavailable")
        value = result.stdout.decode("ascii", "strict").strip()
        if IMAGE_ID_PATTERN.fullmatch(value) is None:
            raise CutoverError("image tag did not resolve to one exact image ID")
        return value

    def _require_candidate_tags_absent(self) -> None:
        for tag in (self.portal_tag, self.tool_tag):
            result = self.commands.run(
                self._docker(
                    "image",
                    "ls",
                    "--quiet",
                    "--no-trunc",
                    "--filter",
                    f"reference={tag}",
                )
            )
            try:
                resolved = result.stdout.decode("ascii", "strict").strip()
            except UnicodeDecodeError as exc:
                raise CutoverError(
                    "candidate tag absence query was not ASCII"
                ) from exc
            if resolved:
                raise CutoverError(
                    "cutover candidate tag already exists; select a fresh cutover id"
                )

    def _git_output(self, repository: Path, *arguments: str) -> str:
        try:
            return self.commands.run(
                ["/usr/bin/git", "-C", str(repository), *arguments]
            ).stdout.decode("utf-8", "strict").strip()
        except UnicodeDecodeError as exc:
            raise CutoverError("build-source Git output was not UTF-8") from exc

    def _git_optional_output(self, repository: Path, *arguments: str) -> str:
        result = self.commands.run(
            ["/usr/bin/git", "-C", str(repository), *arguments],
            check=False,
        )
        if result.returncode not in {0, 1}:
            raise CutoverError("optional build-source Git query failed")
        try:
            return result.stdout.decode("utf-8", "strict").strip()
        except UnicodeDecodeError as exc:
            raise CutoverError("build-source Git output was not UTF-8") from exc

    @staticmethod
    def _ignored_entry_is_docker_excluded(relative_path: str) -> bool:
        path = Path(relative_path)
        if (
            not relative_path
            or path.is_absolute()
            or ".." in path.parts
        ):
            return False
        name = path.name.lower()
        return (
            any(
                component in DOCKER_EXCLUDED_IGNORED_COMPONENTS
                for component in path.parts
            )
            or name == ".env"
            or name.startswith(".env.")
            or name.startswith("credentials.")
            or name.startswith("secrets.")
            or any(name.endswith(suffix) for suffix in DOCKER_EXCLUDED_IGNORED_SUFFIXES)
        )

    @staticmethod
    def _tracked_context_entry_is_sensitive_or_output(
        relative_path: str,
    ) -> bool:
        path = Path(relative_path)
        if (
            not relative_path
            or path.is_absolute()
            or ".." in path.parts
        ):
            return True
        lowered_parts = tuple(component.lower() for component in path.parts)
        name = path.name.lower()
        return (
            any(
                component
                in {
                    ".git",
                    ".state",
                    "bin",
                    "node_modules",
                    "obj",
                }
                for component in lowered_parts
            )
            or any(
                lowered_parts[index : index + 2]
                == ("docker", "secrets")
                for index in range(max(0, len(lowered_parts) - 1))
            )
            or name == ".env"
            or (
                name.startswith(".env.")
                and name not in {".env.example", ".env.sample"}
            )
            or name.startswith("credentials.")
            or name.startswith("secrets.")
            or any(
                name.endswith(suffix)
                for suffix in (".key", ".p12", ".pem", ".pfx")
            )
        )

    def _git_source_provenance(
        self,
        *,
        name: str,
        repository: Path,
        consumed_path: Path,
        expected_head: str,
        allow_docker_excluded_ignored: bool,
        expected_content_sha256: str | None = None,
        additional_content_paths: Sequence[str] = (),
    ) -> dict[str, Any]:
        repository = require_safe_source_directory(
            repository,
            label=name,
        )
        consumed_path = require_safe_source_directory(
            consumed_path,
            label=f"{name} consumed",
        )
        if (
            consumed_path != repository
            and repository not in consumed_path.parents
        ):
            raise CutoverError(f"{name} build source path is unsafe")
        if self.inputs.synthetic_workspace_root is not None:
            validate_sealed_standalone_repository(repository)
            if expected_content_sha256 is None:
                raise CutoverError(
                    f"{name} synthetic source requires an exact content pin"
                )
            replace_refs = self._git_output(
                repository,
                "for-each-ref",
                "--format=%(refname)",
                "refs/replace",
            )
            shallow = self._git_output(
                repository,
                "rev-parse",
                "--is-shallow-repository",
            )
            promisor_configuration = self._git_optional_output(
                repository,
                "config",
                "--local",
                "--get-regexp",
                (
                    r"^(extensions\.partialclone|"
                    r"remote\..*\.promisor|"
                    r"remote\..*\.partialclonefilter)$"
                ),
            )
            self.commands.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(repository),
                    "fsck",
                    "--strict",
                    "--full",
                    "--no-dangling",
                    "--no-progress",
                ],
                timeout=SYNTHETIC_GIT_FSCK_TIMEOUT_SECONDS,
            )
            if replace_refs or shallow != "false" or promisor_configuration:
                raise CutoverError(
                    f"{name} synthetic Git source uses replace, shallow, or promisor state"
                )
        top_level = self._git_output(
            repository,
            "rev-parse",
            "--show-toplevel",
        )
        head = self._git_output(repository, "rev-parse", "HEAD")
        origin_main = self._git_output(
            repository,
            "rev-parse",
            "refs/remotes/origin/main",
        )
        origin_url = self._git_output(
            repository,
            "remote",
            "get-url",
            "origin",
        )
        dirty = self.commands.run(
            [
                "/usr/bin/git",
                "-C",
                str(repository),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ]
        ).stdout
        relative_consumed = os.path.relpath(consumed_path, repository)
        ignored_output = self._git_output(
            repository,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--",
            relative_consumed,
        )
        ignored_entries = [
            entry
            for entry in ignored_output.splitlines()
            if entry
        ]
        tracked_output = self._git_output(
            repository,
            "ls-files",
            "-z",
            "--",
            relative_consumed,
        )
        tracked_entries = sorted(
            entry for entry in tracked_output.split("\0") if entry
        )
        sensitive_tracked_entries = [
            entry
            for entry in tracked_entries
            if self._tracked_context_entry_is_sensitive_or_output(entry)
        ]
        if (
            top_level != str(repository)
            or head != expected_head
            or origin_main != expected_head
            or origin_url != CANONICAL_ORIGIN_URLS[name]
            or dirty
            or any(
                not allow_docker_excluded_ignored
                or not self._ignored_entry_is_docker_excluded(entry)
                for entry in ignored_entries
            )
            or not tracked_entries
            or sensitive_tracked_entries
        ):
            raise CutoverError(
                f"{name} is not one clean, exact, canonical origin/main build source"
            )
        if expected_content_sha256 is None:
            return {
                "consumedPathSha256": sha256_bytes(
                    str(consumed_path).encode("utf-8")
                ),
                "contextFileSetSha256": sha256_bytes(
                    "".join(
                        f"{entry}\n" for entry in tracked_entries
                    ).encode("utf-8")
                ),
                "head": head,
                "ignoredInputCount": len(ignored_entries),
                "originMain": origin_main,
                "originUrlSha256": sha256_bytes(
                    origin_url.encode("utf-8")
                ),
                "repositoryRootSha256": sha256_bytes(
                    str(repository).encode("utf-8")
                ),
                "sensitivePathCount": 0,
                "trackedInputCount": len(tracked_entries),
            }
        content_paths = sorted(
            set(tracked_entries) | set(additional_content_paths)
        )
        content_sha256, content_count, context_file_set_sha256 = (
            source_content_sha256(repository, content_paths)
        )
        if content_sha256 != expected_content_sha256:
            raise CutoverError(f"{name} content digest does not match its exact pin")
        return {
            "consumedPathSha256": sha256_bytes(
                str(consumed_path).encode("utf-8")
            ),
            "contentSha256": content_sha256,
            "contextFileSetSha256": context_file_set_sha256,
            "head": head,
            "ignoredInputCount": len(ignored_entries),
            "originMain": origin_main,
            "originUrlSha256": sha256_bytes(origin_url.encode("utf-8")),
            "repositoryRootSha256": sha256_bytes(
                str(repository).encode("utf-8")
            ),
            "sensitivePathCount": 0,
            "sourceKind": SYNTHETIC_SOURCE_KIND,
            "trackedInputCount": content_count,
        }

    def _source_provenance(
        self,
        *,
        name: str,
        repository: Path,
        consumed_path: Path,
        expected_head: str,
        expected_content_sha256: str | None,
        allow_docker_excluded_ignored: bool,
        additional_content_paths: Sequence[str] = (),
    ) -> dict[str, Any]:
        return self._git_source_provenance(
            name=name,
            repository=repository,
            consumed_path=consumed_path,
            expected_head=expected_head,
            expected_content_sha256=expected_content_sha256,
            allow_docker_excluded_ignored=allow_docker_excluded_ignored,
            additional_content_paths=additional_content_paths,
        )

    @staticmethod
    def _require_explicit_allowlist_dockerignore(
        path: Path,
        *,
        label: str,
    ) -> str:
        raw = read_regular_file_bytes(path, maximum_bytes=256 * 1024)
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise CutoverError(f"{label} Docker ignore is not UTF-8") from exc
        rules = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if (
            not rules
            or rules[0] != "*"
            or not any(rule.startswith("!") for rule in rules[1:])
            or any("\0" in rule for rule in rules)
        ):
            raise CutoverError(
                f"{label} Docker ignore is not an explicit allowlist"
            )
        return sha256_bytes(raw)

    @staticmethod
    def _require_exact_dockerignore(
        path: Path,
        *,
        label: str,
        expected: bytes,
    ) -> str:
        raw = read_regular_file_bytes(path, maximum_bytes=256 * 1024)
        if raw != expected:
            raise CutoverError(
                f"{label} Docker ignore does not match its reviewed contract"
            )
        return sha256_bytes(raw)

    def _validate_build_workspace_paths(self) -> None:
        validate_build_workspace_paths(self.inputs)

    @staticmethod
    def _validate_package_plane(
        payload: dict[str, Any],
        *,
        recipe_sha256: str,
    ) -> int:
        if (
            set(payload)
            != {
                "approved_remote_source",
                "build_recipe",
                "contract",
                "dotnet_install",
                "dotnet_sdk",
                "package_version",
                "packages",
                "toolchain_sha256",
            }
            or payload.get("contract") != PACKAGE_PLANE_CONTRACT
            or payload.get("dotnet_sdk") != PACKAGE_PLANE_DOTNET_SDK
            or payload.get("approved_remote_source")
            != "https://api.nuget.org/v3/index.json"
        ):
            raise CutoverError("package-plane authority contract drifted")
        recipe = payload.get("build_recipe")
        if (
            not isinstance(recipe, dict)
            or set(recipe) != {"path", "sha256"}
            or recipe.get("path") != PACKAGE_PLANE_BUILD_RECIPE
            or recipe.get("sha256") != recipe_sha256
        ):
            raise CutoverError("package-plane build recipe is not exact")
        dotnet_install = payload.get("dotnet_install")
        if (
            not isinstance(dotnet_install, dict)
            or set(dotnet_install) != {"sha256", "url"}
            or dotnet_install.get("url") != "https://dot.net/v1/dotnet-install.sh"
            or HEX_SHA256_PATTERN.fullmatch(
                str(dotnet_install.get("sha256") or "")
            )
            is None
        ):
            raise CutoverError("package-plane SDK bootstrap pin is invalid")
        toolchain = payload.get("toolchain_sha256")
        if (
            not isinstance(toolchain, dict)
            or set(toolchain)
            != {"csc", "dotnet_host", "msbuild", "nuget_packaging"}
            or any(
                HEX_SHA256_PATTERN.fullmatch(str(value)) is None
                for value in toolchain.values()
            )
        ):
            raise CutoverError("package-plane toolchain pins are invalid")
        packages = payload.get("packages")
        if not isinstance(packages, list) or not packages:
            raise CutoverError("package-plane package set is empty")
        identities: set[tuple[str, str]] = set()
        for package in packages:
            if (
                not isinstance(package, dict)
                or not isinstance(package.get("id"), str)
                or not package["id"]
                or not isinstance(package.get("version"), str)
                or not package["version"]
                or not isinstance(package.get("repository"), str)
                or not package["repository"].startswith(
                    "https://github.com/ArchonMegalon/"
                )
                or HEAD_PATTERN.fullmatch(str(package.get("commit") or ""))
                is None
                or HEX_SHA256_PATTERN.fullmatch(
                    str(package.get("nupkg_sha256") or "")
                )
                is None
                or not isinstance(package.get("nupkg_size_bytes"), int)
                or isinstance(package.get("nupkg_size_bytes"), bool)
                or package["nupkg_size_bytes"] <= 0
                or not isinstance(package.get("project"), str)
                or Path(package["project"]).is_absolute()
                or ".." in Path(package["project"]).parts
            ):
                raise CutoverError("package-plane package pin is invalid")
            identity = (package["id"], package["version"])
            if identity in identities:
                raise CutoverError("package-plane package identity is duplicated")
            identities.add(identity)
        return len(packages)

    def _capture_build_dependency_provenance(self) -> dict[str, Any]:
        self._validate_build_workspace_paths()
        source = self.inputs.source_root
        build_context_name = (
            "synthetic-build-context"
            if self.inputs.synthetic_workspace_root is not None
            else "canonical-build-context"
        )
        dockerfile_path = source / "Chummer.Run.Api" / "Dockerfile"
        dockerignore_path = source / "Chummer.Run.Api" / "Dockerfile.dockerignore"
        source_dockerignore_path = source / ".dockerignore"
        design_dockerignore_path = (
            self.inputs.design_product_root / ".dockerignore"
        )
        hub_dockerignore_path = self.inputs.hub_registry_root / ".dockerignore"
        fleet_media_contracts = (
            self.inputs.fleet_media_factory_root
            / "src"
            / "Chummer.Media.Contracts"
        )
        fleet_dockerignore_path = fleet_media_contracts / ".dockerignore"

        dockerfile = read_regular_file_bytes(
            dockerfile_path,
            maximum_bytes=1024 * 1024,
        )
        try:
            dockerfile_text = dockerfile.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise CutoverError("candidate Dockerfile is not UTF-8") from exc
        require_candidate_dockerfile_parser_policy(dockerfile_text)
        (
            logical_instruction_records,
            malformed_continuations,
        ) = _docker_logical_instruction_records(dockerfile_text)
        if malformed_continuations:
            raise CutoverError(
                "candidate Dockerfile has a malformed continuation"
            )
        logical_instructions = tuple(
            instruction
            for _line_number, instruction, _used_continuation
            in logical_instruction_records
        )
        context_policy = docker_context_policy_findings(
            logical_instruction_records
        )
        add_instructions = [
            instruction
            for instruction in logical_instructions
            if re.match(r"ADD(?:\s|$)", instruction, flags=re.IGNORECASE)
        ]
        unqualified_copy_instructions = [
            instruction
            for instruction in logical_instructions
            if re.match(r"COPY(?:\s|$)", instruction, flags=re.IGNORECASE)
            and re.search(
                r"--from(?:=|\s+)[^\s]+",
                instruction,
                flags=re.IGNORECASE,
            )
            is None
        ]
        from_lines = [
            line.strip()
            for line in dockerfile_text.splitlines()
            if line.lstrip().upper().startswith("FROM ")
        ]
        expected_from_lines = [
            f"FROM {DOCKER_BASE_IMAGE_REFERENCES['public-pwa-proof']} AS public-pwa-proof",
            f"FROM {DOCKER_BASE_IMAGE_REFERENCES['hub-package-feed']} AS hub-package-feed",
            f"FROM {DOCKER_BASE_IMAGE_REFERENCES['build']} AS build",
            (
                "FROM "
                f"{DOCKER_BASE_IMAGE_REFERENCES['install-linking-postgres-tool-final']} "
                "AS install-linking-postgres-tool-final"
            ),
            f"FROM {DOCKER_BASE_IMAGE_REFERENCES['final']} AS final",
        ]
        first_line = dockerfile_text.splitlines()[0] if dockerfile_text else ""
        forbidden_install_markers = (
            "apt-get update",
            "apt-get install",
            "apk add",
            "dnf install",
            "yum install",
        )
        if (
            first_line != f"# syntax={DOCKERFILE_FRONTEND_REFERENCE}"
            or from_lines != expected_from_lines
            or add_instructions
            or unqualified_copy_instructions
            or not context_policy["exactReviewedCopySet"]
            or context_policy["forbiddenContextUses"]
            or context_policy["heredocUses"]
            or context_policy["mountFromUses"]
            or context_policy["noncopyFromUses"]
            or context_policy["invalidCopyFromUses"]
            or context_policy["continuationUses"]
            or context_policy["onbuildUses"]
            or any(marker in dockerfile_text for marker in forbidden_install_markers)
            or dockerfile_text.count("--locked-mode") != 2
            or dockerfile_text.count("-p:RestoreAdditionalProjectSources=") != 2
            or dockerfile_text.count(
                "dotnet restore "
                "fleet/repos/chummer-media-factory/src/"
                "Chummer.Media.Contracts/Chummer.Media.Contracts.csproj"
            )
            != 1
            or dockerfile_text.count(
                "dotnet restore "
                "chummer.run-services/Chummer.Run.LoopbackProbe/"
                "Chummer.Run.LoopbackProbe.csproj"
            )
            != 1
            or dockerfile_text.count(
                "dotnet publish "
                "/src/chummer.run-services/Chummer.Run.LoopbackProbe/"
                "Chummer.Run.LoopbackProbe.csproj"
            )
            != 1
            or dockerfile_text.count(
                "COPY --from=build /app/loopback-probe "
                "/app/loopback-probe/"
            )
            != 1
            or dockerfile_text.count(
                "COPY --from=hub-registry-source black-ledger/ "
                "chummer-hub-registry/black-ledger/"
            )
            != 1
            or "COPY chummer-hub-registry/black-ledger/" in dockerfile_text
            or "install-linking-postgres-tool" in dockerfile_text.split(
                expected_from_lines[-1],
                1,
            )[-1]
        ):
            raise CutoverError("Docker build dependency contract drifted")

        input_hashes: dict[str, str] = {}
        input_payloads: dict[str, bytes] = {}
        for relative_path in RUN_SERVICES_PACKAGE_INPUTS:
            payload = read_regular_file_bytes(
                source / relative_path,
                maximum_bytes=16 * 1024 * 1024,
            )
            input_payloads[relative_path] = payload
            input_hashes[relative_path] = sha256_bytes(payload)
        try:
            package_plane = strict_json_object(
                input_payloads["eng/package-plane.lock.json"],
                label="package-plane lock",
            )
        except StrictJsonContractError as exc:
            raise CutoverError("package-plane lock is not strict JSON") from exc
        package_count = self._validate_package_plane(
            package_plane,
            recipe_sha256=input_hashes[PACKAGE_PLANE_BUILD_RECIPE],
        )
        if (
            input_hashes[
                "scripts/public_edge_postdeploy_gate.v1.schema.json"
            ]
            != PUBLIC_EDGE_CUTOVER_POSTDEPLOY_SCHEMA_SHA256
        ):
            raise CutoverError(
                "postdeploy receipt schema digest drifted during capture"
            )

        global_json = strict_json_object(
            input_payloads["global.json"],
            label="global.json",
        )
        if global_json != {
            "sdk": {
                "rollForward": "disable",
                "version": PACKAGE_PLANE_DOTNET_SDK,
            }
        }:
            raise CutoverError("global SDK lock drifted")

        try:
            loopback_lock = strict_json_object(
                input_payloads[
                    "Chummer.Run.LoopbackProbe/packages.lock.json"
                ],
                label="loopback probe package lock",
            )
            loopback_project = input_payloads[
                "Chummer.Run.LoopbackProbe/Chummer.Run.LoopbackProbe.csproj"
            ].decode("utf-8-sig", "strict")
            loopback_program = input_payloads[
                "Chummer.Run.LoopbackProbe/Program.cs"
            ].decode("utf-8-sig", "strict")
        except (StrictJsonContractError, UnicodeDecodeError) as exc:
            raise CutoverError(
                "loopback probe source or package lock is invalid"
            ) from exc
        if (
            loopback_lock
            != {"version": 1, "dependencies": {"net10.0": {}}}
            or "<TargetFramework>net10.0</TargetFramework>"
            not in loopback_project
            or "<OutputType>Exe</OutputType>" not in loopback_project
            or any(
                marker in loopback_project
                for marker in (
                    "<PackageReference",
                    "<ProjectReference",
                    "<FrameworkReference",
                )
            )
            or any(
                marker in loopback_program
                for marker in (
                    "Chummer.InstallLinking",
                    "Npgsql",
                    "Environment.GetEnvironmentVariable",
                    "System.Data",
                )
            )
        ):
            raise CutoverError(
                "loopback probe is not a standalone SDK-only HTTP client"
            )

        media_project = read_regular_file_bytes(
            fleet_media_contracts / "Chummer.Media.Contracts.csproj",
            maximum_bytes=1024 * 1024,
        )
        try:
            media_project_text = media_project.decode("utf-8-sig", "strict")
        except UnicodeDecodeError as exc:
            raise CutoverError("media contracts project is not UTF-8") from exc
        if (
            "<PackageReference" in media_project_text
            or "<TargetFramework>net10.0</TargetFramework>"
            not in media_project_text
        ):
            raise CutoverError(
                "external media contracts restore is not SDK-only"
            )

        hub_registry_dockerignore_sha256 = self._require_exact_dockerignore(
            hub_dockerignore_path,
            label="hub registry",
            expected=REVIEWED_HUB_REGISTRY_DOCKERIGNORE,
        )
        context_policies = {
            build_context_name: {
                "contextBoundary": (
                    "synthetic-root-with-explicit-allowlist"
                    if self.inputs.synthetic_workspace_root is not None
                    else "canonical-root-with-explicit-allowlist"
                ),
                "dockerignoreSha256": (
                    self.inputs.expected_build_context_dockerignore_sha256
                ),
                "effectiveDockerignoreSha256": (
                    self._require_explicit_allowlist_dockerignore(
                        dockerignore_path,
                        label="canonical build context",
                    )
                ),
                "repositoryContained": True,
            },
            "design-product": {
                "contextBoundary": "exact-clean-repository",
                "dockerignoreSha256": (
                    self._require_explicit_allowlist_dockerignore(
                        design_dockerignore_path,
                        label="design product",
                    )
                ),
                "effectiveDockerignoreSha256": (
                    self._require_explicit_allowlist_dockerignore(
                        design_dockerignore_path,
                        label="design product",
                    )
                ),
                "repositoryContained": True,
            },
            "hub-registry-source": {
                "contextBoundary": "exact-clean-repository",
                "dockerignoreSha256": hub_registry_dockerignore_sha256,
                "effectiveDockerignoreSha256": (
                    hub_registry_dockerignore_sha256
                ),
                "repositoryContained": True,
            },
            "fleet-media-factory-contracts": {
                "contextBoundary": "exact-clean-repository-subtree",
                "dockerignoreSha256": None,
                "effectiveDockerignoreSha256": None,
                "repositoryContained": True,
            },
            "run-services-source": {
                "contextBoundary": "exact-clean-repository",
                "dockerignoreSha256": (
                    self._require_explicit_allowlist_dockerignore(
                        source_dockerignore_path,
                        label="run services",
                    )
                ),
                "effectiveDockerignoreSha256": (
                    self._require_explicit_allowlist_dockerignore(
                        source_dockerignore_path,
                        label="run services",
                    )
                ),
                "repositoryContained": True,
            },
        }
        if fleet_dockerignore_path.exists():
            raise CutoverError(
                "fleet media context gained an unreviewed Docker ignore"
            )
        input_set_sha256 = sha256_bytes(
            canonical_json_bytes(
                input_hashes,
                label="build package input hash set",
            )
        )
        return {
            "baseImages": dict(DOCKER_BASE_IMAGE_REFERENCES),
            "contextPolicies": context_policies,
            "contractName": BUILD_DEPENDENCY_PROVENANCE_CONTRACT,
            "dockerfileFrontend": DOCKERFILE_FRONTEND_REFERENCE,
            "dockerfileSha256": sha256_bytes(dockerfile),
            "externalMediaProjectSha256": sha256_bytes(media_project),
            "externalMediaRestoreIsSdkOnly": True,
            "loopbackProbeIsSdkOnly": True,
            "loopbackProbeProgramSha256": input_hashes[
                "Chummer.Run.LoopbackProbe/Program.cs"
            ],
            "loopbackProbeProjectSha256": input_hashes[
                "Chummer.Run.LoopbackProbe/Chummer.Run.LoopbackProbe.csproj"
            ],
            "packageInputSetSha256": input_set_sha256,
            "packageInputs": input_hashes,
            "packagePlaneContract": PACKAGE_PLANE_CONTRACT,
            "packagePlanePackageCount": package_count,
            "postdeploySchemaContractName": (
                PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME
            ),
            "postdeploySchemaSha256": (
                input_hashes[
                    "scripts/public_edge_postdeploy_gate.v1.schema.json"
                ]
            ),
            "runtimePackageManagerInvocationCount": 0,
            "status": "pass",
        }

    def _capture_build_source_provenance(
        self,
    ) -> dict[str, dict[str, Any]]:
        self._validate_build_workspace_paths()
        build_context_name = (
            "synthetic-build-context"
            if self.inputs.synthetic_workspace_root is not None
            else "canonical-build-context"
        )
        dockerignore = self.inputs.build_context_root / ".dockerignore"
        if (
            not dockerignore.is_absolute()
            or dockerignore.resolve(strict=True) != dockerignore
            or hash_regular_file(dockerignore, owner_only=False)
            != self.inputs.expected_build_context_dockerignore_sha256
        ):
            raise CutoverError(
                "Docker build-context ignore contract drifted"
            )
        provenance = {
            "run-services-source": self._source_provenance(
                name="run-services-source",
                repository=self.inputs.source_root,
                consumed_path=self.inputs.source_root,
                expected_head=self.inputs.expected_head,
                expected_content_sha256=(
                    self.inputs.expected_run_services_content_sha256
                ),
                allow_docker_excluded_ignored=True,
            ),
            "hub-registry": self._source_provenance(
                name="hub-registry",
                repository=self.inputs.hub_registry_root,
                consumed_path=self.inputs.hub_registry_root,
                expected_head=self.inputs.expected_hub_registry_head,
                expected_content_sha256=(
                    self.inputs.expected_hub_registry_content_sha256
                ),
                allow_docker_excluded_ignored=False,
            ),
            "design-product": self._source_provenance(
                name="design-product",
                repository=self.inputs.design_product_root,
                consumed_path=(
                    self.inputs.design_product_root / "products" / "chummer"
                ),
                expected_head=self.inputs.expected_design_product_head,
                expected_content_sha256=(
                    self.inputs.expected_design_product_content_sha256
                ),
                allow_docker_excluded_ignored=False,
                additional_content_paths=(".dockerignore",),
            ),
            "fleet-media-factory-contracts": self._source_provenance(
                name="fleet-media-factory-contracts",
                repository=self.inputs.fleet_media_factory_root,
                consumed_path=(
                    self.inputs.fleet_media_factory_root
                    / "src"
                    / "Chummer.Media.Contracts"
                ),
                expected_head=self.inputs.expected_fleet_media_factory_head,
                expected_content_sha256=(
                    self.inputs.expected_fleet_media_factory_content_sha256
                ),
                allow_docker_excluded_ignored=False,
            ),
            build_context_name: {
                "consumedPathSha256": sha256_bytes(
                    str(self.inputs.build_context_root).encode("utf-8")
                ),
                "dockerignoreSha256": (
                    self.inputs.expected_build_context_dockerignore_sha256
                ),
            },
            "build-dependency-contract": (
                self._capture_build_dependency_provenance()
            ),
        }
        return provenance

    def _bind_pinned_source_inputs(self) -> None:
        """Rebind the exact local files that determine a Compose invocation."""
        self._validate_build_workspace_paths()
        source = self.inputs.source_root
        if not source.is_absolute() or source.resolve(strict=True) != source:
            raise CutoverError("source root must be an absolute non-symlinked path")
        if self.inputs.compose_file != source / "docker-compose.public-edge.yml":
            raise CutoverError("Compose input must be the exact source-root contract")
        actual_compose = hash_regular_file(
            self.inputs.compose_file,
            owner_only=False,
        )
        actual_env = hash_regular_file(self.inputs.env_file, owner_only=True)
        runner_path = source / "scripts" / "run_install_linking_postgres_cutover.py"
        actual_runner = hash_regular_file(runner_path, owner_only=False)
        if (
            actual_compose != self.inputs.compose_sha256
            or actual_env != self.inputs.env_sha256
            or actual_runner != self.inputs.runner_sha256
        ):
            raise CutoverError("an independently pinned cutover input digest drifted")
        compose_payload = read_regular_file_bytes(
            self.inputs.compose_file,
            maximum_bytes=4 * 1024 * 1024,
        )
        if sha256_bytes(compose_payload) != actual_compose:
            raise CutoverError("Compose input changed while being validated")
        try:
            compose_text = compose_payload.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise CutoverError("Compose input is not strict UTF-8") from exc
        require_public_edge_compose_build_syntax(compose_text)

    def _validate_source(self) -> None:
        self._bind_pinned_source_inputs()
        source = self.inputs.source_root
        if self.inputs.synthetic_workspace_root is None:
            head = self.commands.run(
                ["/usr/bin/git", "-C", str(source), "rev-parse", "HEAD"]
            ).stdout.decode("ascii", "strict").strip()
            upstream = self.commands.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(source),
                    "rev-parse",
                    "refs/remotes/origin/main",
                ]
            ).stdout.decode("ascii", "strict").strip()
            dirty = self.commands.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(source),
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                ]
            ).stdout
            if (
                head != self.inputs.expected_head
                or upstream != self.inputs.expected_head
                or dirty
            ):
                raise CutoverError(
                    "cutover source is not clean exact origin/main"
                )
        else:
            self._source_provenance(
                name="run-services-source",
                repository=source,
                consumed_path=source,
                expected_head=self.inputs.expected_head,
                expected_content_sha256=(
                    self.inputs.expected_run_services_content_sha256
                ),
                allow_docker_excluded_ignored=True,
            )
        docker_context = self.commands.run(
            self._docker(
                "context",
                "inspect",
                CANONICAL_DOCKER_CONTEXT,
                "--format",
                "{{.Name}}|{{.Endpoints.docker.Host}}|{{.Endpoints.docker.SkipTLSVerify}}",
            )
        ).stdout.decode("utf-8", "strict").strip()
        if docker_context != (
            f"{CANONICAL_DOCKER_CONTEXT}|{CANONICAL_DOCKER_HOST}|false"
        ):
            raise CutoverError("Docker context is not the canonical local daemon")

    def _validate_rendered_compose(
        self,
        *,
        overrides: Iterable[Path] = (),
        project: str = CANONICAL_PROJECT,
        transient_service_keys: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        rendered = self.commands.run(
            self._compose(
                "--profile",
                "*",
                "config",
                "--format",
                "json",
                overrides=overrides,
                project=project,
            ),
            timeout=COMMAND_TIMEOUT_SECONDS,
        ).stdout
        try:
            payload = json.loads(rendered)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CutoverError("rendered Compose contract was not valid JSON") from exc
        services = payload.get("services") if isinstance(payload, dict) else None
        networks = payload.get("networks") if isinstance(payload, dict) else None
        if not isinstance(services, dict) or not isinstance(networks, dict):
            raise CutoverError("rendered Compose contract omitted services or networks")
        expected_additional_contexts = {
            "design-product": str(self.inputs.design_product_root),
            "fleet-media-factory-contracts": str(
                self.inputs.fleet_media_factory_root
                / "src"
                / "Chummer.Media.Contracts"
            ),
            "hub-registry-source": str(self.inputs.hub_registry_root),
            "run-services-source": str(self.inputs.source_root),
        }
        expected_dockerfile = str(
            self.inputs.source_root / "Chummer.Run.Api" / "Dockerfile"
        )
        expected_images = {
            service_name: (
                self.portal_tag
                if service_name == "chummer-portal"
                else self.tool_tag
            )
            for service_name in PUBLIC_EDGE_BUILD_SERVICE_TARGETS
        }
        rendered_policy_failures = public_edge_rendered_compose_failures(
            payload,
            expected_images=expected_images,
            build_context=str(self.inputs.build_context_root),
            dockerfile=expected_dockerfile,
            additional_contexts=expected_additional_contexts,
            transient_service_keys=transient_service_keys,
        )
        if rendered_policy_failures:
            raise CutoverError(
                "rendered build authority drifted: "
                + rendered_policy_failures[0]
            )
        for service_name, expected_image in expected_images.items():
            service = services.get(service_name)
            build = service.get("build") if isinstance(service, dict) else None
            if (
                not isinstance(service, dict)
                or service.get("image") != expected_image
                or not rendered_build_contract_matches(
                    build,
                    service_name=service_name,
                    build_context=str(self.inputs.build_context_root),
                    dockerfile=expected_dockerfile,
                    additional_contexts=expected_additional_contexts,
                )
            ):
                raise CutoverError(
                    f"rendered build authority drifted for {service_name}"
                )
            if service_name not in EXPECTED_CRITICAL_ENVIRONMENT_KEYS:
                continue
            environment = service.get("environment")
            critical_keys = EXPECTED_CRITICAL_ENVIRONMENT_KEYS[service_name]
            if (
                not isinstance(environment, dict)
                or any(
                    not isinstance(environment.get(key), str)
                    or not environment[key]
                    for key in critical_keys
                )
            ):
                raise CutoverError(
                    f"rendered critical environment drifted for {service_name}"
                )
            critical_environment = {
                key: environment[key]
                for key in critical_keys
            }
            if any(
                critical_environment.get(key) != expected
                for key, expected in EXPECTED_FIXED_CRITICAL_ENVIRONMENT[
                    service_name
                ].items()
            ):
                raise CutoverError(
                    f"rendered critical environment drifted for {service_name}"
                )
            self.expected_critical_environment_sha256[service_name] = (
                critical_environment_sha256(
                    service_name,
                    critical_environment,
                )
            )
            volume_entries = service.get("volumes")
            if not isinstance(volume_entries, list):
                raise CutoverError(
                    f"rendered mount authority drifted for {service_name}"
                )
            source_digests: dict[str, str] = {}
            for entry in volume_entries:
                if not isinstance(entry, dict):
                    raise CutoverError(
                        f"rendered mount authority drifted for {service_name}"
                    )
                destination = str(entry.get("target") or "")
                source = str(entry.get("source") or "")
                source_kind = str(entry.get("type") or "")
                if destination not in EXPECTED_MOUNTS[service_name]:
                    raise CutoverError(
                        f"rendered mount authority drifted for {service_name}"
                    )
                if (
                    entry.get("read_only")
                    is not (not EXPECTED_MOUNTS[service_name][destination])
                ):
                    raise CutoverError(
                        f"rendered mount mode drifted for {service_name}"
                    )
                if source_kind == "volume":
                    if (
                        service_name
                        != "chummer-install-linking-postgres-import-presence-proof"
                        or source != "chummer-run-api-state"
                    ):
                        raise CutoverError("rendered local-state volume drifted")
                    source_identity = (
                        f"{CANONICAL_PROJECT}_chummer-run-api-state"
                    )
                elif source_kind == "bind":
                    source_path = Path(source)
                    if (
                        not source_path.is_absolute()
                        or source_path.resolve(strict=True) != source_path
                    ):
                        raise CutoverError(
                            "rendered credential mount source is unsafe"
                        )
                    source_identity = source
                else:
                    raise CutoverError("rendered operator mount type drifted")
                source_digests[destination] = sha256_bytes(
                    source_identity.encode("utf-8")
                )
            if set(source_digests) != set(EXPECTED_MOUNTS[service_name]):
                raise CutoverError(
                    f"rendered mount set drifted for {service_name}"
                )
            self.expected_mount_source_sha256[service_name] = source_digests
        public_network = networks.get("public-origin")
        public_name = (
            public_network.get("name")
            if isinstance(public_network, dict)
            else None
        )
        if (
            not isinstance(public_name, str)
            or SAFE_NAME_PATTERN.fullmatch(public_name) is None
            or public_network.get("external") is not True
        ):
            raise CutoverError("rendered public-origin network authority drifted")
        network_id = self.commands.run(
            self._docker(
                "network",
                "inspect",
                public_name,
                "--format",
                "{{.Id}}",
            )
        ).stdout.decode("ascii", "strict").strip()
        if (
            re.fullmatch(r"[0-9a-f]{64}", network_id) is None
            or (
                self.public_network_id
                and self.public_network_id != network_id
            )
        ):
            raise CutoverError("public-origin network identity drifted")
        self.public_network_name = public_name
        self.public_network_id = network_id

    def _final_bind_compose_inputs(
        self,
        *,
        job_override: Path | None = None,
        job_service: str = "",
        job_command: Sequence[str] = (),
        container_name: str = "",
        project: str = CANONICAL_PROJECT,
    ) -> None:
        """Bind the complete effective Compose authority immediately before dispatch."""
        overrides = (job_override,) if job_override is not None else ()
        transient_service_keys = (
            {job_service: ("container_name",)}
            if job_override is not None
            else None
        )
        self._validate_source()
        self._bind_existing_build_override()
        if job_override is not None:
            self._bind_job_override(
                job_override,
                service=job_service,
                command=job_command,
                container_name=container_name,
            )
        self._validate_rendered_compose(
            overrides=overrides,
            project=project,
            transient_service_keys=transient_service_keys,
        )
        # Complete every slow source and Docker identity check after rendering,
        # then make the bounded pinned-file checks below the final filesystem
        # operation before the caller dispatches its preconstructed command.
        self._validate_source()
        self._bind_pinned_source_inputs()
        self._bind_existing_build_override()
        if job_override is not None:
            self._bind_job_override(
                job_override,
                service=job_service,
                command=job_command,
                container_name=container_name,
            )

    def _build_override_payload(self) -> dict[str, Any]:
        return {
            "services": {
                "chummer-portal": {"image": self.portal_tag},
                "chummer-install-linking-postgres-admin": {
                    "image": self.tool_tag
                },
                "chummer-install-linking-postgres-runtime-proof": {
                    "image": self.tool_tag
                },
                "chummer-install-linking-postgres-import-presence-proof": {
                    "image": self.tool_tag
                },
                "chummer-install-linking-postgres-import": {
                    "image": self.tool_tag
                },
            }
        }

    def _write_build_override(self) -> None:
        write_private_json(
            self.build_override,
            self._build_override_payload(),
        )

    def _bind_existing_build_override(self) -> None:
        payload, _ = read_private_canonical_json(self.build_override)
        if payload != self._build_override_payload():
            raise CutoverError(
                "retained cutover image override identity drifted"
            )

    def _acquire_lease(self) -> None:
        self.lease = acquire_mutation_lease(
            actor="cutover",
            lock_path=self.lock_path,
            authorization_root=self.lock_authorization_root,
        )
        receipt_path = self.inputs.receipt_root / "PUBLIC_EDGE_MUTATION_LEASE.json"
        write_private_json(receipt_path, self.lease.receipt(status="active"))

    def _release_lease(self) -> None:
        if self.lease is None:
            return
        release_mutation_lease(self.lease)
        receipt_path = self.inputs.receipt_root / "PUBLIC_EDGE_MUTATION_LEASE.json"
        write_private_json(
            receipt_path,
            self.lease.receipt(status="released"),
            replace=True,
        )
        self.lease = None

    def _build_candidates(self) -> None:
        self._require_candidate_tags_absent()
        prior_portal = self._resolve_image(PORTAL_CANONICAL_TAG, allow_absent=True)
        prior_tool = self._resolve_image(TOOL_CANONICAL_TAG, allow_absent=True)
        source_provenance_before = self._capture_build_source_provenance()
        build_command = self._compose(
            "--profile",
            "install-linking-postgres-admin",
            "build",
            "chummer-portal",
            "chummer-install-linking-postgres-admin",
        )
        self._final_bind_compose_inputs()
        self.commands.run(
            build_command,
            timeout=BUILD_TIMEOUT_SECONDS,
        )
        self.candidate_image_id = self._resolve_image(self.portal_tag)
        self.candidate_tool_image_id = self._resolve_image(self.tool_tag)
        self._validate_source()
        self._validate_rendered_compose()
        source_provenance_after = self._capture_build_source_provenance()
        if source_provenance_after != source_provenance_before:
            raise CutoverError("Docker build source changed during candidate build")
        self.build_source_provenance = source_provenance_after
        if (
            self._resolve_image(PORTAL_CANONICAL_TAG, allow_absent=True)
            != prior_portal
            or self._resolve_image(TOOL_CANONICAL_TAG, allow_absent=True)
            != prior_tool
        ):
            raise CutoverError("unique candidate build changed a canonical recovery tag")
        build_info = {
            "candidateImageId": self.candidate_image_id,
            "candidatePortalTag": self.portal_tag,
            "candidateToolImageId": self.candidate_tool_image_id,
            "candidateToolTag": self.tool_tag,
            "buildSourceProvenance": self.build_source_provenance,
            "canonicalPortalTagIdBeforeAndAfter": prior_portal or None,
            "canonicalToolTagIdBeforeAndAfter": prior_tool or None,
            "composeSha256": self.inputs.compose_sha256,
            "contractName": CANDIDATE_BUILD_INFO_CONTRACT,
            "cutoverId": self.inputs.cutover_id,
            "envSha256": self.inputs.env_sha256,
            "generatedAtUtc": now_iso(),
            "operatorCriticalEnvironmentSha256": (
                self.expected_critical_environment_sha256
            ),
            "operatorMountSourceSha256": self.expected_mount_source_sha256,
            "publicNetworkId": self.public_network_id,
            "publicNetworkName": self.public_network_name,
            "runnerSha256": self.inputs.runner_sha256,
            "sourceHead": self.inputs.expected_head,
            "status": "pass",
            "uniqueTagsPreserveCanonicalRecoveryAuthority": True,
        }
        self.candidate_build_info_sha256 = write_private_json(
            self.candidate_build_info_path,
            build_info,
        )

    def _materialize(
        self,
        phase: str,
        *,
        evidence: Path | None = None,
        operator_image: bool = False,
    ) -> None:
        materialize_boundary(
            output=self.inputs.boundary_output,
            phase=phase,
            cutover_id=self.inputs.cutover_id,
            candidate_image_id=self.candidate_image_id,
            candidate_tool_image_id=self.candidate_tool_image_id,
            operator_container_image_id=(
                self.candidate_tool_image_id if operator_image else None
            ),
            active_build_info=self.candidate_build_info_path,
            evidence_receipt=evidence,
        )

    def _job_override_payload(
        self,
        *,
        service: str,
        command: Sequence[str],
        container_name: str,
    ) -> dict[str, Any]:
        return {
            "services": {
                service: {
                    "command": list(command),
                    "container_name": container_name,
                    "environment": {
                        "CHUMMER_CUTOVER_SECRET_CANARY": self.secret_canary,
                    },
                    "image": self.tool_tag,
                }
            },
            "volumes": {
                "chummer-run-api-state": {
                    "external": True,
                    "name": f"{CANONICAL_PROJECT}_chummer-run-api-state",
                },
            },
        }

    def _bind_job_override(
        self,
        path: Path,
        *,
        service: str,
        command: Sequence[str],
        container_name: str,
    ) -> None:
        expected = self._job_override_payload(
            service=service,
            command=command,
            container_name=container_name,
        )
        payload, digest = read_private_canonical_json(path)
        expected_digest = sha256_bytes(
            canonical_json_bytes(expected, label=path.name)
        )
        if payload != expected or digest != expected_digest:
            raise CutoverError(
                "generated job Compose override identity drifted"
            )

    def _job_override(
        self,
        *,
        job_name: str,
        service: str,
        command: Sequence[str],
    ) -> tuple[Path, str, str]:
        project = self._job_project(job_name)
        container_name = (
            f"chummer-install-linking-cutover-{self.name_suffix}-"
            f"{job_name.replace('_', '-')}"
        )
        if SAFE_NAME_PATTERN.fullmatch(container_name) is None:
            raise CutoverError("deterministic container name is invalid")
        path = self.inputs.receipt_root / f"compose.{job_name}.override.json"
        payload = self._job_override_payload(
            service=service,
            command=command,
            container_name=container_name,
        )
        write_private_json(path, payload)
        return path, container_name, project

    def _inspect_container(
        self,
        *,
        container_name: str,
        service: str,
        project: str,
        command: Sequence[str],
    ) -> tuple[str, dict[str, Any]]:
        raw = self.commands.run(
            self._docker("container", "inspect", container_name)
        ).stdout
        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CutoverError("container inspection was not valid JSON") from exc
        if not isinstance(decoded, list) or len(decoded) != 1:
            raise CutoverError("container inspection was not unique")
        payload = decoded[0]
        if not isinstance(payload, dict):
            raise CutoverError("container inspection was malformed")
        container_id = str(payload.get("Id") or "")
        config = payload.get("Config")
        host = payload.get("HostConfig")
        mounts = payload.get("Mounts")
        network_settings = payload.get("NetworkSettings")
        state = payload.get("State")
        if not all(
            isinstance(value, expected)
            for value, expected in (
                (config, dict),
                (host, dict),
                (mounts, list),
                (network_settings, dict),
                (state, dict),
            )
        ):
            raise CutoverError("container inspection omitted required state")
        labels = config.get("Labels")
        cap_drop = host.get("CapDrop")
        security_opt = host.get("SecurityOpt")
        tmpfs = host.get("Tmpfs")
        observed_mounts = {
            str(mount.get("Destination")): bool(mount.get("RW"))
            for mount in mounts
            if isinstance(mount, dict)
        }
        observed_mount_types = {
            str(mount.get("Destination")): str(mount.get("Type") or "")
            for mount in mounts
            if isinstance(mount, dict)
        }
        observed_mount_source_sha256 = {
            str(mount.get("Destination")): sha256_bytes(
                str(
                    mount.get("Name")
                    if mount.get("Type") == "volume"
                    else mount.get("Source") or ""
                ).encode("utf-8")
            )
            for mount in mounts
            if isinstance(mount, dict)
        }
        observed_tmpfs = (
            {
                str(destination): set(str(options).split(","))
                for destination, options in tmpfs.items()
            }
            if isinstance(tmpfs, dict)
            else {}
        )
        expected_mounts = EXPECTED_MOUNTS[service]
        networks = network_settings.get("Networks")
        expected_networks = (
            set()
            if service == "chummer-install-linking-postgres-import-presence-proof"
            else {self.public_network_name}
        )
        if (
            re.fullmatch(r"[0-9a-f]{64}", container_id) is None
            or payload.get("Image") != self.candidate_tool_image_id
            or payload.get("Name") != f"/{container_name}"
            or not isinstance(labels, dict)
            or labels.get("com.docker.compose.project") != project
            or labels.get("com.docker.compose.service") != service
            or labels.get("com.docker.compose.oneoff") != "False"
            or config.get("Cmd") != list(command)
            or host.get("ReadonlyRootfs") is not True
            or set(cap_drop or []) != {"ALL"}
            or "no-new-privileges:true" not in (security_opt or [])
            or re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", str(config.get("User") or ""))
            is None
            or observed_mounts != expected_mounts
            or observed_tmpfs != {"/tmp": EXPECTED_TMPFS_OPTIONS}
            or state.get("Status") != "created"
            or state.get("Running") is not False
            or not isinstance(networks, dict)
            or set(networks) != expected_networks
            or observed_mount_source_sha256
            != self.expected_mount_source_sha256[service]
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(labels.get("com.docker.compose.config-hash") or ""),
            )
            is None
        ):
            raise CutoverError("stopped operator container contract drifted")
        if service == "chummer-install-linking-postgres-import-presence-proof":
            observed_network_id = ""
        else:
            network = networks.get(self.public_network_name)
            observed_network_id = (
                str(network.get("NetworkID") or "")
                if isinstance(network, dict)
                else ""
            )
            if observed_network_id != self.public_network_id:
                raise CutoverError("operator network identity drifted")
        if (
            service == "chummer-install-linking-postgres-import-presence-proof"
            and (
                observed_mount_types != {"/app/state": "volume"}
                or next(
                    (
                        mount.get("Name")
                        for mount in mounts
                        if isinstance(mount, dict)
                        and mount.get("Destination") == "/app/state"
                    ),
                    None,
                )
                != f"{CANONICAL_PROJECT}_chummer-run-api-state"
            )
        ) or (
            service != "chummer-install-linking-postgres-import-presence-proof"
            and set(observed_mount_types.values()) != {"bind"}
        ):
            raise CutoverError("operator container mount authority drifted")
        environment = config.get("Env")
        if not isinstance(environment, list):
            raise CutoverError("operator container environment is unavailable")
        environment_keys = [
            str(item).partition("=")[0]
            for item in environment
            if isinstance(item, str) and "=" in item
        ]
        if len(environment_keys) != len(set(environment_keys)):
            raise CutoverError("operator container environment contains duplicates")
        environment_map = {
            str(item).partition("=")[0]: str(item).partition("=")[2]
            for item in environment
            if isinstance(item, str) and "=" in item
        }
        critical_keys = EXPECTED_CRITICAL_ENVIRONMENT_KEYS[service]
        if (
            not critical_keys.issubset(environment_map)
            or critical_environment_sha256(
                service,
                {
                    key: environment_map[key]
                    for key in critical_keys
                },
            )
            != self.expected_critical_environment_sha256[service]
        ):
            raise CutoverError(
                "operator container critical environment drifted"
            )
        if environment_map.get("CHUMMER_CUTOVER_SECRET_CANARY") != self.secret_canary:
            raise CutoverError("operator container omitted its secret-leak canary")
        if service != "chummer-install-linking-postgres-import-presence-proof":
            runtime_role = environment_map.get(
                "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
                "",
            )
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$-]{0,62}", runtime_role) is None:
                raise CutoverError("operator runtime role binding is invalid")
            runtime_role_sha256 = sha256_bytes(runtime_role.encode("utf-8"))
            if (
                self.runtime_role_sha256
                and self.runtime_role_sha256 != runtime_role_sha256
            ):
                raise CutoverError(
                    "admin and runtime proof containers selected different roles"
                )
            self.runtime_role_sha256 = runtime_role_sha256
        if service == "chummer-install-linking-postgres-import-presence-proof":
            if (
                host.get("NetworkMode") != "none"
                or any(
                    marker in str(item)
                    for item in environment
                    for marker in ("POSTGRES", "DATA_PROTECTION")
                )
            ):
                raise CutoverError(
                    "local-store proof container received a network or credential authority"
                )
        elif host.get("NetworkMode") != self.public_network_name:
            raise CutoverError("PostgreSQL proof container has the wrong network")
        if service == "chummer-install-linking-postgres-admin":
            if (
                "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE"
                not in environment_map
                or "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE"
                in environment_map
                or any("DATA_PROTECTION" in key for key in environment_map)
            ):
                raise CutoverError("admin proof container credential authority drifted")
        if service == "chummer-install-linking-postgres-runtime-proof":
            if (
                "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE"
                not in environment_map
                or "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE"
                in environment_map
                or "CHUMMER_INSTALL_LINKING_STORE_PATH" in environment_map
                or any("DATA_PROTECTION" in key for key in environment_map)
            ):
                raise CutoverError("runtime proof container credential authority drifted")
        extra_hosts = host.get("ExtraHosts") or []
        if (
            service == "chummer-install-linking-postgres-import-presence-proof"
            and extra_hosts
        ) or (
            service != "chummer-install-linking-postgres-import-presence-proof"
            and len(extra_hosts) != 1
        ):
            raise CutoverError("operator container extra-host topology drifted")
        return container_id, {
            "capDrop": sorted(cap_drop or []),
            "command": list(command),
            "composeProject": project,
            "criticalEnvironmentSha256": (
                self.expected_critical_environment_sha256[service]
            ),
            "extraHostCount": len(extra_hosts),
            "imageId": self.candidate_tool_image_id,
            "labels": {
                "composeConfigHash": labels["com.docker.compose.config-hash"],
                "composeOneoff": labels["com.docker.compose.oneoff"],
                "composeProject": labels["com.docker.compose.project"],
                "composeService": labels["com.docker.compose.service"],
            },
            "mounts": [
                {
                    "destination": destination,
                    "readWrite": read_write,
                    "sourceIdentitySha256": (
                        observed_mount_source_sha256[destination]
                    ),
                    "sourceKind": observed_mount_types[destination],
                }
                for destination, read_write in sorted(observed_mounts.items())
            ],
            "networkId": observed_network_id,
            "networkMode": str(host.get("NetworkMode") or ""),
            "noNewPrivileges": True,
            "readOnlyRootFilesystem": True,
            "service": service,
            "tmpfs": [
                {
                    "destination": destination,
                    "options": sorted(options),
                }
                for destination, options in sorted(observed_tmpfs.items())
            ],
            "user": str(config.get("User") or ""),
        }

    def _terminate_active_container(self, container_id: str) -> None:
        for arguments, timeout in (
            (("container", "stop", "--time", "5", container_id), 15),
            (("container", "kill", "--signal", "KILL", container_id), 10),
            (("container", "wait", container_id), 15),
        ):
            try:
                self.commands.run(
                    self._docker(*arguments),
                    timeout=timeout,
                    check=False,
                )
            except CutoverError:
                continue

    def _inspect_observed_state(
        self,
        container_id: str,
    ) -> tuple[str, int | None]:
        try:
            raw = self.commands.run(
                self._docker("container", "inspect", container_id)
            ).stdout
            decoded = json.loads(raw)
            payload = decoded[0]
            state = payload["State"]
            status = state["Status"]
            exit_code = state.get("ExitCode")
        except (
            CutoverError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            IndexError,
            KeyError,
            TypeError,
        ):
            return "unobservable", None
        if (
            not isinstance(payload, dict)
            or payload.get("Id") != container_id
            or status
            not in {
                "created",
                "running",
                "paused",
                "restarting",
                "removing",
                "exited",
                "dead",
            }
        ):
            return "unobservable", None
        return status, exit_code if isinstance(exit_code, int) else None

    def _write_start_intent(
        self,
        *,
        job_name: str,
        service: str,
        project: str,
        container_name: str,
        container_id: str,
    ) -> tuple[Path, str, str]:
        created_at = now_iso()
        payload = {
            "candidateToolImageId": self.candidate_tool_image_id,
            "composeProject": project,
            "containerId": container_id,
            "containerName": container_name,
            "contractName": START_INTENT_CONTRACT,
            "createdAtUtc": created_at,
            "cutoverId": self.inputs.cutover_id,
            "jobName": job_name,
            "service": service,
            "status": "start_pending",
        }
        path = self.inputs.receipt_root / f"{job_name}.start-intent.json"
        digest = write_private_json(path, payload)
        self.start_intent_written = True
        self.active_container_id = container_id
        return path, digest, created_at

    def _capture_logs(
        self,
        container_id: str,
        job_name: str,
    ) -> tuple[Path, str, Path, str, bool]:
        captured = True
        try:
            logs = self.commands.run(
                self._docker("container", "logs", container_id),
                timeout=30,
                check=False,
            )
            captured = logs.returncode == 0
        except CutoverError:
            logs = CommandResult(1, b"", b"")
            captured = False
        stdout_path = self.inputs.receipt_root / f"{job_name}.stdout.log"
        stderr_path = self.inputs.receipt_root / f"{job_name}.stderr.log"
        atomic_private_write(stdout_path, logs.stdout)
        atomic_private_write(stderr_path, logs.stderr)
        return (
            stdout_path,
            sha256_bytes(logs.stdout),
            stderr_path,
            sha256_bytes(logs.stderr),
            captured,
        )

    @staticmethod
    def _remaining_job_budget(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise JobWaitAmbiguity(
                "operator container exceeded its monotonic deadline",
                timed_out=True,
            )
        return remaining

    def _wait_for_job(self, container_id: str, *, deadline: float) -> int:
        try:
            result = self.commands.run(
                self._docker("container", "wait", container_id),
                timeout=self._remaining_job_budget(deadline),
                check=False,
            )
        except (CommandDeadlineExceeded, JobWaitAmbiguity) as exc:
            raise JobWaitAmbiguity(
                "operator container wait timed out",
                timed_out=True,
            ) from exc
        if time.monotonic() > deadline:
            raise JobWaitAmbiguity(
                "operator container exited after its monotonic deadline",
                timed_out=True,
            )
        if result.returncode != 0:
            raise JobWaitAmbiguity(
                "operator container wait was lost",
                timed_out=False,
            )
        value = result.stdout.decode("ascii", "strict").strip()
        if re.fullmatch(r"-?[0-9]+", value) is None:
            raise JobWaitAmbiguity(
                "operator container wait was malformed",
                timed_out=False,
            )
        return int(value)

    def _write_job_receipt(
        self,
        *,
        job_name: str,
        service: str,
        compose_project: str,
        container_name: str,
        container_id: str,
        container_state: str,
        started_at: str,
        exit_code: int | None,
        timed_out: bool,
        ambiguous: bool,
        logs_captured: bool,
        secret_canary_leaked: bool,
        stdout_path: Path,
        stdout_sha256: str,
        stderr_path: Path,
        stderr_sha256: str,
        proof_path: Path | None,
        proof_sha256: str | None,
        start_intent_path: Path,
        start_intent_sha256: str,
        topology: dict[str, Any],
        status: str,
        image_id_after: str | None,
    ) -> tuple[Path, str]:
        receipt = {
            "ambiguous": ambiguous,
            "candidateBuildInfoSha256": self.candidate_build_info_sha256,
            "candidateImageId": self.candidate_image_id,
            "candidateToolImageId": self.candidate_tool_image_id,
            "containerId": container_id,
            "containerImageId": self.candidate_tool_image_id,
            "containerName": container_name,
            "containerState": container_state,
            "composeProject": compose_project,
            "contractName": JOB_RECEIPT_CONTRACT,
            "cutoverId": self.inputs.cutover_id,
            "exitCode": exit_code,
            "finishedAtUtc": now_iso(),
            "imageIdAfter": image_id_after,
            "imageIdBefore": self.candidate_tool_image_id,
            "jobName": job_name,
            "logsCaptured": logs_captured,
            "proofPath": None if proof_path is None else str(proof_path),
            "proofSha256": proof_sha256,
            "retainedContainer": True,
            "secretCanaryLeaked": secret_canary_leaked,
            "secretCanarySha256": self.secret_canary_sha256,
            "service": service,
            "startedAtUtc": started_at,
            "startIntentPath": str(start_intent_path),
            "startIntentSha256": start_intent_sha256,
            "status": status,
            "stderrPath": str(stderr_path),
            "stderrSha256": stderr_sha256,
            "stdoutPath": str(stdout_path),
            "stdoutSha256": stdout_sha256,
            "timedOut": timed_out,
            "timeoutSeconds": JOB_TIMEOUT_SECONDS,
            "topology": topology,
        }
        path = self.inputs.receipt_root / f"{job_name}.job-receipt.json"
        digest = write_private_json(path, receipt)
        self.job_receipts[job_name] = (path, digest)
        return path, digest

    def _run_job(
        self,
        *,
        job_name: str,
        service: str,
        command: Sequence[str],
        proof_contract: str,
    ) -> None:
        override, container_name, project = self._job_override(
            job_name=job_name,
            service=service,
            command=command,
        )
        existing = self.commands.run(
            self._docker("container", "inspect", container_name),
            check=False,
        )
        if existing.returncode == 0:
            raise AmbiguousCutoverError(
                f"deterministic operator container already exists: {container_name}"
            )
        # Compose v5 does not support ``create --no-deps``. The rendered
        # operator-service allowlists reject ``depends_on``, so selecting one
        # governed service cannot create an uninspected dependency container.
        create_command = self._compose(
            "--profile",
            "install-linking-postgres-admin",
            "create",
            "--no-build",
            "--no-recreate",
            service,
            overrides=(override,),
            project=project,
        )
        self._final_bind_compose_inputs(
            job_override=override,
            job_service=service,
            job_command=command,
            container_name=container_name,
            project=project,
        )
        self.commands.run(create_command)
        container_id, topology = self._inspect_container(
            container_name=container_name,
            service=service,
            project=project,
            command=command,
        )
        if self._resolve_image(self.tool_tag) != self.candidate_tool_image_id:
            raise AmbiguousCutoverError("tool image changed after container creation")
        job_deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
        (
            start_intent_path,
            start_intent_sha256,
            started_at,
        ) = self._write_start_intent(
            job_name=job_name,
            service=service,
            project=project,
            container_name=container_name,
            container_id=container_id,
        )
        receipt_written = False
        timed_out = False
        logs_captured = False
        secret_canary_leaked = False
        stdout_path: Path | None = None
        stdout_sha256 = ""
        stderr_path: Path | None = None
        stderr_sha256 = ""
        proof_path: Path | None = None
        proof_sha256: str | None = None
        image_id_after: str | None = None
        try:
            try:
                self.container_start_may_have_been_invoked = True
                self.commands.run(
                    self._docker("container", "start", container_id),
                    timeout=self._remaining_job_budget(job_deadline),
                )
            except (CommandDeadlineExceeded, JobWaitAmbiguity) as exc:
                raise JobWaitAmbiguity(
                    "operator container start exhausted its monotonic deadline",
                    timed_out=True,
                ) from exc
            exit_code = self._wait_for_job(
                container_id,
                deadline=job_deadline,
            )
            container_state, observed_exit_code = self._inspect_observed_state(
                container_id
            )
            if container_state != "exited" or observed_exit_code != exit_code:
                raise AmbiguousCutoverError(
                    "operator container final state did not bind to docker wait"
                )
            (
                stdout_path,
                stdout_sha256,
                stderr_path,
                stderr_sha256,
                logs_captured,
            ) = self._capture_logs(container_id, job_name)
            stdout_bytes = stdout_path.read_bytes()
            stderr_bytes = stderr_path.read_bytes()
            secret_canary_leaked = (
                self.secret_canary.encode("ascii") in stdout_bytes + stderr_bytes
            )
            proof_valid = False
            if (
                exit_code == 0
                and logs_captured
                and not secret_canary_leaked
                and stderr_bytes == b""
            ):
                try:
                    proof = strict_json_object(
                        stdout_bytes,
                        label=f"{job_name} proof",
                    )
                    proof_valid = (
                        proof.get("contractName") == proof_contract
                        and proof.get("status") == "pass"
                        and stdout_bytes
                        == canonical_json_bytes(proof, label=f"{job_name} proof")
                    )
                    if proof_contract != (
                        "chummer.install_linking_local_store_absence_proof.v1"
                    ):
                        authority_identity_sha256 = str(
                            proof.get("authorityIdentitySha256") or ""
                        )
                        proof_valid = (
                            proof_valid
                            and HEX_SHA256_PATTERN.fullmatch(
                                authority_identity_sha256
                            )
                            is not None
                            and (
                                not self.authority_identity_sha256
                                or self.authority_identity_sha256
                                == authority_identity_sha256
                            )
                        )
                        if proof_valid:
                            self.authority_identity_sha256 = (
                                authority_identity_sha256
                            )
                except StrictJsonContractError:
                    proof_valid = False
                if proof_valid:
                    proof_path = self.inputs.receipt_root / f"{job_name}.proof.json"
                    atomic_private_write(proof_path, stdout_bytes)
                    proof_sha256 = hash_regular_file(
                        proof_path,
                        owner_only=True,
                        maximum_bytes=MAX_COMMAND_OUTPUT_BYTES,
                    )
            image_id_after = self._resolve_image(self.tool_tag)
            ambiguous = (
                exit_code != 0
                or secret_canary_leaked
                or not proof_valid
                or image_id_after != self.candidate_tool_image_id
            )
            self._write_job_receipt(
                job_name=job_name,
                service=service,
                compose_project=project,
                container_name=container_name,
                container_id=container_id,
                container_state=container_state,
                started_at=started_at,
                exit_code=observed_exit_code,
                timed_out=False,
                ambiguous=ambiguous,
                logs_captured=logs_captured,
                secret_canary_leaked=secret_canary_leaked,
                stdout_path=stdout_path,
                stdout_sha256=stdout_sha256,
                stderr_path=stderr_path,
                stderr_sha256=stderr_sha256,
                proof_path=proof_path,
                proof_sha256=proof_sha256,
                start_intent_path=start_intent_path,
                start_intent_sha256=start_intent_sha256,
                topology=topology,
                status="unknown" if ambiguous else "pass",
                image_id_after=image_id_after,
            )
            receipt_written = True
            self.active_container_id = None
            if ambiguous:
                raise AmbiguousCutoverError(
                    f"operator job {job_name} did not produce a passing proof"
                )
        except (Exception, CutoverSignal) as exc:
            if isinstance(exc, JobWaitAmbiguity):
                timed_out = exc.timed_out
            self._terminate_active_container(container_id)
            container_state, observed_exit_code = self._inspect_observed_state(
                container_id
            )
            if stdout_path is None or stderr_path is None:
                (
                    stdout_path,
                    stdout_sha256,
                    stderr_path,
                    stderr_sha256,
                    logs_captured,
                ) = self._capture_logs(container_id, job_name)
                secret_canary_leaked = (
                    self.secret_canary.encode("ascii")
                    in stdout_path.read_bytes() + stderr_path.read_bytes()
                )
            if image_id_after is None:
                try:
                    image_id_after = self._resolve_image(self.tool_tag)
                except CutoverError:
                    image_id_after = None
            if not receipt_written:
                self._write_job_receipt(
                    job_name=job_name,
                    service=service,
                    compose_project=project,
                    container_name=container_name,
                    container_id=container_id,
                    container_state=container_state,
                    started_at=started_at,
                    exit_code=observed_exit_code,
                    timed_out=timed_out,
                    ambiguous=True,
                    logs_captured=logs_captured,
                    secret_canary_leaked=secret_canary_leaked,
                    stdout_path=stdout_path,
                    stdout_sha256=stdout_sha256,
                    stderr_path=stderr_path,
                    stderr_sha256=stderr_sha256,
                    proof_path=proof_path,
                    proof_sha256=proof_sha256,
                    start_intent_path=start_intent_path,
                    start_intent_sha256=start_intent_sha256,
                    topology=topology,
                    status="unknown",
                    image_id_after=image_id_after,
                )
            self.active_container_id = None
            if isinstance(exc, CutoverSignal):
                raise
            raise AmbiguousCutoverError(
                f"operator job {job_name} has unknown post-start state"
            ) from exc

    def _write_phase_evidence(
        self,
        phase: str,
        *,
        job_names: Sequence[str] | None = None,
        artifact_stem: str | None = None,
    ) -> Path:
        selected_job_names = (
            tuple(job_names)
            if job_names is not None
            else PHASE_JOB_NAMES[phase]
        )
        aggregate = hashlib.sha256()
        references: list[dict[str, str]] = []
        for name in selected_job_names:
            path, digest = self.job_receipts[name]
            references.append(
                {
                    "name": name,
                    "path": str(path),
                    "sha256": digest,
                }
            )
            aggregate.update(name.encode("utf-8"))
            aggregate.update(b"\0")
            aggregate.update(digest.encode("ascii"))
            aggregate.update(b"\n")
        payload = {
            "authorityIdentitySha256": self.authority_identity_sha256,
            "candidateBuildInfoSha256": self.candidate_build_info_sha256,
            "candidateImageId": self.candidate_image_id,
            "candidateToolImageId": self.candidate_tool_image_id,
            "contractName": PHASE_EVIDENCE_CONTRACT,
            "cutoverId": self.inputs.cutover_id,
            "jobReceiptChainSha256": aggregate.hexdigest(),
            "jobReceipts": references,
            "phase": phase,
            "status": "pass",
        }
        if phase == POSTQUIESCE_REPROOF_PHASE:
            if (
                self.volume_inventory_receipt_path is None
                or HEX_SHA256_PATTERN.fullmatch(
                    self.volume_inventory_receipt_sha256
                )
                is None
            ):
                raise CutoverError(
                    "post-quiesce phase lacks its state-volume inventory binding"
                )
            payload.update(
                {
                    "runtimeRoleSha256": self.runtime_role_sha256,
                    "volumeInventoryReceiptPath": str(
                        self.volume_inventory_receipt_path
                    ),
                    "volumeInventoryReceiptSha256": (
                        self.volume_inventory_receipt_sha256
                    ),
                }
            )
        path = self.inputs.receipt_root / (
            f"{artifact_stem or phase}.phase-evidence.json"
        )
        write_private_json(path, payload)
        return path

    def _write_final_receipt(
        self,
        *,
        status: str,
        reason: str | None,
        replace: bool = False,
    ) -> Path:
        boundary_sha256 = (
            hash_regular_file(self.inputs.boundary_output, owner_only=True)
            if self.inputs.boundary_output.exists()
            else None
        )
        payload = {
            "boundaryReceiptPath": str(self.inputs.boundary_output),
            "boundaryReceiptSha256": boundary_sha256,
            "candidateBuildInfoPath": str(self.candidate_build_info_path),
            "candidateBuildInfoSha256": self.candidate_build_info_sha256 or None,
            "candidateImageId": self.candidate_image_id or None,
            "candidateToolImageId": self.candidate_tool_image_id or None,
            "contractName": CONTRACT_NAME,
            "cutoverId": self.inputs.cutover_id,
            "finishedAtUtc": now_iso(),
            "jobReceipts": [
                {
                    "name": name,
                    "path": str(path),
                    "sha256": digest,
                }
                for name, (path, digest) in self.job_receipts.items()
            ],
            "predeployStopsAtValidateCompleted": True,
            "publicAcceptanceCompleted": False,
            "reason": reason,
            "status": status,
        }
        path = self.inputs.receipt_root / "INSTALL_LINKING_POSTGRES_CUTOVER_RUN.json"
        write_private_json(path, payload, replace=replace)
        return path

    def _write_postquiesce_receipt(
        self,
        output: Path,
        *,
        attempt_id: str,
        boundary_sha256: str,
        mutation_lock_token_sha256: str,
        started_at: str,
        status: str,
        reason: str | None,
        phase_evidence_path: Path | None,
        replace: bool = False,
    ) -> Path:
        phase_evidence_sha256 = (
            hash_regular_file(phase_evidence_path, owner_only=True)
            if phase_evidence_path is not None
            else None
        )
        payload = {
            "activeBuildInfoPath": str(self.candidate_build_info_path),
            "activeBuildInfoSha256": (
                self.candidate_build_info_sha256 or None
            ),
            "boundaryReceiptPath": str(self.inputs.boundary_output),
            "boundaryReceiptSha256": boundary_sha256,
            "attemptId": attempt_id,
            "candidateImageId": self.candidate_image_id or None,
            "candidatePortalTag": self.portal_tag,
            "candidateToolImageId": self.candidate_tool_image_id or None,
            "candidateToolTag": self.tool_tag,
            "containerStartMayHaveBeenInvoked": (
                self.container_start_may_have_been_invoked
            ),
            "contractName": POSTQUIESCE_REPROOF_CONTRACT,
            "cutoverId": self.inputs.cutover_id,
            "finishedAtUtc": now_iso(),
            "mutationLockPath": str(LOCK_PATH),
            "mutationLockTokenSha256": mutation_lock_token_sha256,
            "phaseEvidencePath": (
                None if phase_evidence_path is None else str(phase_evidence_path)
            ),
            "phaseEvidenceSha256": phase_evidence_sha256,
            "reason": reason,
            "sourceHead": self.inputs.expected_head,
            "startIntentWritten": self.start_intent_written,
            "startedAtUtc": started_at,
            "status": status,
            "volumeInventoryReceiptPath": (
                None
                if self.volume_inventory_receipt_path is None
                else str(self.volume_inventory_receipt_path)
            ),
            "volumeInventoryReceiptSha256": (
                self.volume_inventory_receipt_sha256 or None
            ),
        }
        write_private_json(output, payload, replace=replace)
        return output

    def verify_source_replay(
        self,
        *,
        active_build_info: Path,
        expected_active_build_info_sha256: str,
        expected_candidate_image_id: str,
        expected_candidate_tool_image_id: str,
    ) -> dict[str, Any]:
        """Reprove exact build sources without mutating Docker or PostgreSQL."""

        bound_path, bound_sha256, build_info = bind_active_build_info(
            active_build_info,
            cutover_id=self.inputs.cutover_id,
            candidate_image_id=expected_candidate_image_id,
            candidate_tool_image_id=expected_candidate_tool_image_id,
        )
        self._validate_source()
        observed_provenance = self._capture_build_source_provenance()
        if (
            bound_path != active_build_info
            or bound_sha256 != expected_active_build_info_sha256
            or observed_provenance != build_info.get(
                "buildSourceProvenance"
            )
        ):
            raise CutoverError(
                "candidate build-source replay binding drifted"
            )
        return {
            "activeBuildInfoSha256": bound_sha256,
            "buildSourceProvenanceSha256": sha256_bytes(
                canonical_json_bytes(
                    observed_provenance,
                    label="build-source replay provenance",
                )
            ),
            "contractName": SOURCE_REPLAY_PREFLIGHT_CONTRACT,
            "sourceHead": self.inputs.expected_head,
            "status": "pass",
        }

    def run_postquiesce_reproof(
        self,
        *,
        attempt_id: str,
        expected_boundary_sha256: str,
        expected_candidate_image_id: str,
        expected_candidate_tool_image_id: str,
        shared_mutation_lock_token: str,
        volume_inventory_receipt: Path,
        expected_volume_inventory_sha256: str,
        output: Path,
    ) -> Path:
        started_at = now_iso()
        token_sha256 = sha256_bytes(
            shared_mutation_lock_token.encode("ascii")
        )
        lock_identity = validate_inherited_mutation_lock(
            shared_mutation_lock_token
        )
        self.candidate_image_id = expected_candidate_image_id
        self.candidate_tool_image_id = expected_candidate_tool_image_id
        self.volume_inventory_receipt_path = Path(
            os.path.abspath(volume_inventory_receipt)
        )
        self.volume_inventory_receipt_sha256 = (
            expected_volume_inventory_sha256
        )
        phase_evidence: Path | None = None
        try:
            (
                bound_volume_inventory_path,
                bound_volume_inventory_sha256,
                _,
            ) = bind_state_volume_inventory(
                self.volume_inventory_receipt_path,
                expected_sha256=expected_volume_inventory_sha256,
                attempt_id=attempt_id,
                cutover_id=self.inputs.cutover_id,
                candidate_tool_image_id=expected_candidate_tool_image_id,
                mutation_lock_token_sha256=token_sha256,
            )
            if (
                bound_volume_inventory_path
                != self.volume_inventory_receipt_path
                or bound_volume_inventory_sha256
                != self.volume_inventory_receipt_sha256
            ):
                raise CutoverError(
                    "post-quiesce state-volume inventory binding drifted"
                )
            self._validate_source()
            observed_source_provenance = (
                self._capture_build_source_provenance()
            )
            observed_portal = self._resolve_image(self.portal_tag)
            observed_tool = self._resolve_image(self.tool_tag)
            verification = verify_boundary(
                boundary=self.inputs.boundary_output,
                expected_boundary_sha256=expected_boundary_sha256,
                expected_cutover_id=self.inputs.cutover_id,
                expected_source_head=self.inputs.expected_head,
                expected_candidate_image_id=expected_candidate_image_id,
                expected_candidate_tool_image_id=expected_candidate_tool_image_id,
                observed_candidate_image_id=observed_portal,
                observed_candidate_tool_image_id=observed_tool,
                source_root=self.inputs.source_root,
                env_file=self.inputs.env_file,
                expected_phase="validate_completed",
            )
            self.candidate_build_info_path = Path(
                str(verification["activeBuildInfoPath"])
            )
            (
                _,
                self.candidate_build_info_sha256,
                build_info,
            ) = bind_active_build_info(
                self.candidate_build_info_path,
                cutover_id=self.inputs.cutover_id,
                candidate_image_id=self.candidate_image_id,
                candidate_tool_image_id=self.candidate_tool_image_id,
            )
            self._bind_existing_build_override()
            self._validate_rendered_compose()
            if (
                self.expected_mount_source_sha256
                != build_info["operatorMountSourceSha256"]
                or observed_source_provenance
                != build_info["buildSourceProvenance"]
                or self.expected_critical_environment_sha256
                != build_info["operatorCriticalEnvironmentSha256"]
                or self.public_network_name != build_info["publicNetworkName"]
                or self.public_network_id != build_info["publicNetworkId"]
                or self._resolve_image(self.portal_tag)
                != self.candidate_image_id
                or self._resolve_image(self.tool_tag)
                != self.candidate_tool_image_id
            ):
                raise CutoverError(
                    "post-quiesce candidate topology or image identity drifted"
                )
            validate_inherited_mutation_lock(
                shared_mutation_lock_token,
                expected_identity=lock_identity,
            )
            selected_job_specs = postquiesce_job_specs(attempt_id)
            for job_name, service, command, proof_contract in selected_job_specs:
                validate_inherited_mutation_lock(
                    shared_mutation_lock_token,
                    expected_identity=lock_identity,
                )
                self._run_job(
                    job_name=job_name,
                    service=service,
                    command=command,
                    proof_contract=proof_contract,
                )
                validate_inherited_mutation_lock(
                    shared_mutation_lock_token,
                    expected_identity=lock_identity,
                )
            phase_evidence = self._write_phase_evidence(
                POSTQUIESCE_REPROOF_PHASE,
                job_names=tuple(
                    specification[0] for specification in selected_job_specs
                ),
                artifact_stem=f"{POSTQUIESCE_REPROOF_PHASE}.{attempt_id}",
            )
            validate_inherited_mutation_lock(
                shared_mutation_lock_token,
                expected_identity=lock_identity,
            )
            return self._write_postquiesce_receipt(
                output,
                attempt_id=attempt_id,
                boundary_sha256=expected_boundary_sha256,
                mutation_lock_token_sha256=token_sha256,
                started_at=started_at,
                status="pass",
                reason=None,
                phase_evidence_path=phase_evidence,
            )
        except (Exception, CutoverSignal) as exc:
            if self.active_container_id is not None:
                self._terminate_active_container(self.active_container_id)
            ambiguous = self.start_intent_written or isinstance(
                exc,
                AmbiguousCutoverError,
            )
            self._write_postquiesce_receipt(
                output,
                attempt_id=attempt_id,
                boundary_sha256=expected_boundary_sha256,
                mutation_lock_token_sha256=token_sha256,
                started_at=started_at,
                status="unknown" if ambiguous else "fail",
                reason=(
                    f"signal_{exc.signum}"
                    if isinstance(exc, CutoverSignal)
                    else type(exc).__name__
                ),
                phase_evidence_path=phase_evidence,
                replace=output.exists(),
            )
            if ambiguous:
                raise AmbiguousCutoverError(
                    "post-quiesce proof state is unknown; retained containers require review"
                ) from exc
            if isinstance(exc, CutoverSignal):
                raise CutoverError(
                    "signal interrupted post-quiesce proof before container start"
                ) from exc
            raise

    def run(self) -> Path:
        self._validate_source()
        self._write_build_override()
        self._acquire_lease()
        try:
            self._validate_rendered_compose()
            self._build_candidates()
            self._materialize("prepare_starting")
            for job_name, service, command, proof_contract in JOB_SPECS[:4]:
                self._run_job(
                    job_name=job_name,
                    service=service,
                    command=command,
                    proof_contract=proof_contract,
                )
            prepare_evidence = self._write_phase_evidence("prepare_completed")
            self._materialize(
                "prepare_completed",
                evidence=prepare_evidence,
                operator_image=True,
            )
            job_name, service, command, proof_contract = JOB_SPECS[4]
            self._run_job(
                job_name=job_name,
                service=service,
                command=command,
                proof_contract=proof_contract,
            )
            import_evidence = self._write_phase_evidence(
                "import_skipped_no_local_store"
            )
            self._materialize(
                "import_skipped_no_local_store",
                evidence=import_evidence,
                operator_image=True,
            )
            job_name, service, command, proof_contract = JOB_SPECS[5]
            self._run_job(
                job_name=job_name,
                service=service,
                command=command,
                proof_contract=proof_contract,
            )
            validate_evidence = self._write_phase_evidence("validate_completed")
            self._materialize(
                "validate_completed",
                evidence=validate_evidence,
                operator_image=True,
            )
            self._release_lease()
            final = self._write_final_receipt(status="pass", reason=None)
            return final
        except CutoverSignal as exc:
            if self.active_container_id is not None:
                self._terminate_active_container(self.active_container_id)
            self._write_final_receipt(
                status="unknown" if self.start_intent_written else "fail",
                reason=f"signal_{exc.signum}",
                replace=(
                    self.inputs.receipt_root
                    / "INSTALL_LINKING_POSTGRES_CUTOVER_RUN.json"
                ).exists(),
            )
            if self.start_intent_written:
                raise AmbiguousCutoverError(
                    "signal interrupted a post-start database phase"
                ) from exc
            self._release_lease()
            raise CutoverError("signal interrupted cutover before prepare") from exc
        except Exception as exc:
            ambiguous = self.start_intent_written or isinstance(
                exc,
                AmbiguousCutoverError,
            )
            self._write_final_receipt(
                status="unknown" if ambiguous else "fail",
                reason=type(exc).__name__,
                replace=(
                    self.inputs.receipt_root
                    / "INSTALL_LINKING_POSTGRES_CUTOVER_RUN.json"
                ).exists(),
            )
            if not ambiguous:
                self._release_lease()
            if ambiguous:
                raise AmbiguousCutoverError(
                    "cutover state is unknown; retained containers and mutation lock require review"
                ) from exc
            raise


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--post-quiesce-reproof", action="store_true")
    parser.add_argument("--source-replay-preflight", action="store_true")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--synthetic-workspace-root", type=Path)
    parser.add_argument("--build-context-root", type=Path)
    parser.add_argument("--hub-registry-root", type=Path)
    parser.add_argument("--design-product-root", type=Path)
    parser.add_argument("--fleet-media-factory-root", type=Path)
    parser.add_argument("--expected-run-services-content-sha256")
    parser.add_argument("--expected-hub-registry-content-sha256")
    parser.add_argument("--expected-design-product-content-sha256")
    parser.add_argument("--expected-fleet-media-factory-content-sha256")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-compose-sha256", required=True)
    parser.add_argument("--env-file", type=Path, default=CANONICAL_ENV_FILE)
    parser.add_argument("--expected-env-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-hub-registry-head", required=True)
    parser.add_argument("--expected-design-product-head", required=True)
    parser.add_argument("--expected-fleet-media-factory-head", required=True)
    parser.add_argument(
        "--expected-build-context-dockerignore-sha256",
        required=True,
    )
    parser.add_argument("--cutover-id", required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--boundary-output", type=Path, required=True)
    parser.add_argument("--expected-boundary-sha256")
    parser.add_argument("--expected-candidate-image-id")
    parser.add_argument("--expected-candidate-tool-image-id")
    parser.add_argument("--shared-mutation-lock-token")
    parser.add_argument("--reproof-attempt-id")
    parser.add_argument("--volume-inventory-receipt", type=Path)
    parser.add_argument("--expected-volume-inventory-sha256")
    parser.add_argument("--active-build-info", type=Path)
    parser.add_argument("--expected-active-build-info-sha256")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> CutoverInputs:
    if args.post_quiesce_reproof and args.source_replay_preflight:
        raise CutoverError(
            "source replay preflight and post-quiesce reproof are exclusive"
        )
    if (
        HEAD_PATTERN.fullmatch(args.expected_head) is None
        or HEX_SHA256_PATTERN.fullmatch(args.expected_compose_sha256) is None
        or HEX_SHA256_PATTERN.fullmatch(args.expected_env_sha256) is None
        or HEX_SHA256_PATTERN.fullmatch(args.expected_runner_sha256) is None
        or HEAD_PATTERN.fullmatch(args.expected_hub_registry_head) is None
        or HEAD_PATTERN.fullmatch(args.expected_design_product_head) is None
        or HEAD_PATTERN.fullmatch(args.expected_fleet_media_factory_head)
        is None
        or HEX_SHA256_PATTERN.fullmatch(
            args.expected_build_context_dockerignore_sha256
        )
        is None
        or CUTOVER_ID_PATTERN.fullmatch(args.cutover_id) is None
    ):
        raise CutoverError("an externally selected cutover identity is invalid")
    source_root = Path(os.path.abspath(args.source_root))
    synthetic_workspace_root = (
        Path(os.path.abspath(args.synthetic_workspace_root))
        if args.synthetic_workspace_root is not None
        else None
    )
    synthetic_paths = (
        args.build_context_root,
        args.hub_registry_root,
        args.design_product_root,
        args.fleet_media_factory_root,
    )
    content_pins = (
        args.expected_run_services_content_sha256,
        args.expected_hub_registry_content_sha256,
        args.expected_design_product_content_sha256,
        args.expected_fleet_media_factory_content_sha256,
    )
    if synthetic_workspace_root is None:
        if (
            any(path is not None for path in synthetic_paths)
            or any(pin is not None for pin in content_pins)
        ):
            raise CutoverError(
                "synthetic source options require an approved synthetic root"
            )
        build_context_root = CANONICAL_BUILD_CONTEXT
        hub_registry_root = CANONICAL_HUB_REGISTRY
        design_product_root = CANONICAL_DESIGN_PRODUCT
        fleet_media_factory_root = CANONICAL_FLEET_MEDIA_REPOSITORY
    else:
        if any(path is None for path in synthetic_paths):
            raise CutoverError(
                "synthetic workspace requires explicit build and dependency paths"
            )
        if any(
            pin is None or HEX_SHA256_PATTERN.fullmatch(pin) is None
            for pin in content_pins
        ):
            raise CutoverError(
                "synthetic workspace requires exact content digest pins"
            )
        build_context_root = Path(
            os.path.abspath(args.build_context_root)
        )
        hub_registry_root = Path(
            os.path.abspath(args.hub_registry_root)
        )
        design_product_root = Path(
            os.path.abspath(args.design_product_root)
        )
        fleet_media_factory_root = Path(
            os.path.abspath(args.fleet_media_factory_root)
        )
    env_file = Path(os.path.abspath(args.env_file))
    receipt_root = validate_private_directory(
        Path(os.path.abspath(args.receipt_root))
    )
    boundary_output = Path(os.path.abspath(args.boundary_output))
    if env_file != CANONICAL_ENV_FILE:
        raise CutoverError("cutover requires the canonical public-edge environment file")
    if args.source_replay_preflight:
        if (
            args.active_build_info is None
            or args.expected_active_build_info_sha256 is None
            or args.expected_candidate_image_id is None
            or args.expected_candidate_tool_image_id is None
            or HEX_SHA256_PATTERN.fullmatch(
                args.expected_active_build_info_sha256
            )
            is None
            or IMAGE_ID_PATTERN.fullmatch(
                args.expected_candidate_image_id
            )
            is None
            or IMAGE_ID_PATTERN.fullmatch(
                args.expected_candidate_tool_image_id
            )
            is None
            or any(
                value is not None
                for value in (
                    args.expected_boundary_sha256,
                    args.shared_mutation_lock_token,
                    args.reproof_attempt_id,
                    args.volume_inventory_receipt,
                    args.expected_volume_inventory_sha256,
                    args.output,
                )
            )
        ):
            raise CutoverError(
                "source replay preflight requires exact build-info and image "
                "pins without post-quiesce inputs"
            )
        active_build_info = Path(
            os.path.abspath(args.active_build_info)
        )
        if (
            boundary_output.parent != receipt_root
            or active_build_info.parent != receipt_root
            or active_build_info.is_symlink()
        ):
            raise CutoverError(
                "source replay preflight inputs escaped the receipt root"
            )
        args.active_build_info = active_build_info
    elif args.post_quiesce_reproof:
        if (
            args.output is None
            or args.expected_boundary_sha256 is None
            or args.expected_candidate_image_id is None
            or args.expected_candidate_tool_image_id is None
            or args.shared_mutation_lock_token is None
            or args.reproof_attempt_id is None
            or args.volume_inventory_receipt is None
            or args.expected_volume_inventory_sha256 is None
            or HEX_SHA256_PATTERN.fullmatch(args.expected_boundary_sha256)
            is None
            or IMAGE_ID_PATTERN.fullmatch(args.expected_candidate_image_id)
            is None
            or IMAGE_ID_PATTERN.fullmatch(
                args.expected_candidate_tool_image_id
            )
            is None
            or re.fullmatch(
                r"[0-9a-f]{64}",
                args.shared_mutation_lock_token,
            )
            is None
            or re.fullmatch(
                r"[a-z0-9][a-z0-9-]{7,31}",
                args.reproof_attempt_id,
            )
            is None
            or HEX_SHA256_PATTERN.fullmatch(
                args.expected_volume_inventory_sha256
            )
            is None
        ):
            raise CutoverError(
                "post-quiesce reproof requires exact boundary, image, and lock pins"
            )
        output = Path(os.path.abspath(args.output))
        volume_inventory_receipt = Path(
            os.path.abspath(args.volume_inventory_receipt)
        )
        if (
            boundary_output.parent != receipt_root
            or output.parent != receipt_root
            or volume_inventory_receipt.parent != receipt_root
            or volume_inventory_receipt.name
            != (
                "INSTALL_LINKING_STATE_VOLUME_INVENTORY."
                "post-incumbent-quiesce."
                f"{args.reproof_attempt_id}.json"
            )
            or output.name
            != (
                "INSTALL_LINKING_POSTGRES_POSTQUIESCE_REPROOF."
                f"{args.reproof_attempt_id}.json"
            )
            or output.exists()
            or output.is_symlink()
            or args.active_build_info is not None
            or args.expected_active_build_info_sha256 is not None
        ):
            raise CutoverError(
                "post-quiesce outputs must be new files in the boundary receipt root"
            )
    elif any(
        value is not None
        for value in (
            args.expected_boundary_sha256,
            args.expected_candidate_image_id,
            args.expected_candidate_tool_image_id,
            args.shared_mutation_lock_token,
            args.reproof_attempt_id,
            args.volume_inventory_receipt,
            args.expected_volume_inventory_sha256,
            args.active_build_info,
            args.expected_active_build_info_sha256,
            args.output,
        )
    ):
        raise CutoverError(
            "post-quiesce-only inputs are invalid for a predeploy cutover"
        )
    elif boundary_output.parent != receipt_root:
        raise CutoverError("boundary output must be directly beneath the receipt root")
    inputs = CutoverInputs(
        source_root=source_root,
        compose_file=source_root / "docker-compose.public-edge.yml",
        env_file=env_file,
        receipt_root=receipt_root,
        boundary_output=boundary_output,
        expected_head=args.expected_head,
        compose_sha256=args.expected_compose_sha256,
        env_sha256=args.expected_env_sha256,
        runner_sha256=args.expected_runner_sha256,
        expected_hub_registry_head=args.expected_hub_registry_head,
        expected_design_product_head=args.expected_design_product_head,
        expected_fleet_media_factory_head=(
            args.expected_fleet_media_factory_head
        ),
        expected_build_context_dockerignore_sha256=(
            args.expected_build_context_dockerignore_sha256
        ),
        cutover_id=args.cutover_id,
        synthetic_workspace_root=synthetic_workspace_root,
        build_context_root=build_context_root,
        hub_registry_root=hub_registry_root,
        design_product_root=design_product_root,
        fleet_media_factory_root=fleet_media_factory_root,
        expected_run_services_content_sha256=(
            args.expected_run_services_content_sha256
        ),
        expected_hub_registry_content_sha256=(
            args.expected_hub_registry_content_sha256
        ),
        expected_design_product_content_sha256=(
            args.expected_design_product_content_sha256
        ),
        expected_fleet_media_factory_content_sha256=(
            args.expected_fleet_media_factory_content_sha256
        ),
    )
    validate_build_workspace_paths(inputs)
    return inputs


def _signal_handler(signum: int, _frame: object) -> None:
    raise CutoverSignal(signum)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inputs = validate_args(args)
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, _signal_handler)
        runner = GovernedCutoverRunner(
            inputs,
            command_runner=CommandRunner(
                docker_config_root=CANONICAL_DOCKER_CONFIG_ROOT,
                routing_environment=build_routing_environment(inputs),
            ),
        )
        if args.source_replay_preflight:
            replay_verification = runner.verify_source_replay(
                active_build_info=args.active_build_info,
                expected_active_build_info_sha256=(
                    args.expected_active_build_info_sha256
                ),
                expected_candidate_image_id=(
                    args.expected_candidate_image_id
                ),
                expected_candidate_tool_image_id=(
                    args.expected_candidate_tool_image_id
                ),
            )
            receipt = None
            output_contract = SOURCE_REPLAY_PREFLIGHT_CONTRACT
        elif args.post_quiesce_reproof:
            receipt = runner.run_postquiesce_reproof(
                attempt_id=args.reproof_attempt_id,
                expected_boundary_sha256=args.expected_boundary_sha256,
                expected_candidate_image_id=args.expected_candidate_image_id,
                expected_candidate_tool_image_id=(
                    args.expected_candidate_tool_image_id
                ),
                shared_mutation_lock_token=args.shared_mutation_lock_token,
                volume_inventory_receipt=Path(
                    os.path.abspath(args.volume_inventory_receipt)
                ),
                expected_volume_inventory_sha256=(
                    args.expected_volume_inventory_sha256
                ),
                output=Path(os.path.abspath(args.output)),
            )
            output_contract = POSTQUIESCE_REPROOF_CONTRACT
        else:
            receipt = runner.run()
            output_contract = CONTRACT_NAME
    except AmbiguousCutoverError as exc:
        print(f"InstallLinking cutover stopped with unknown state: {exc}", file=sys.stderr)
        return 70
    except (
        CutoverError,
        PublicEdgeMutationLockUnavailable,
        OSError,
        ValueError,
    ) as exc:
        print(f"InstallLinking cutover failed closed: {exc}", file=sys.stderr)
        return 1
    if args.source_replay_preflight:
        print(
            json.dumps(
                replay_verification,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    print(
        json.dumps(
            {
                "contractName": output_contract,
                "receiptPath": str(receipt),
                "status": "pass",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
