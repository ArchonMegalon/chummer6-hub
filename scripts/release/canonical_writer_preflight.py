#!/usr/bin/env python3
"""Sealed, local-only preflight for the canonical release-shelf writer.

This command never writes to the configured source manifests, a production shelf,
or a running deployment.  It builds one content-addressed candidate, projects a
copy of the current release envelope through a loopback-only process, exercises
the immutable-generation pointer protocol in a temporary shelf, and emits an
explicit go/no-go receipt.

A successful build is deliberately not enough.  ``decision=go`` additionally
requires an operator-supplied source-closure digest and one coherent candidate
that contains the truth floor, generation reader, activation journal, readiness
probe, and their focused tests.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import hashlib
import importlib.util
import ipaddress
import json
import math
import os
import re
import secrets
import select
import shutil
import signal
import socket
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Sequence


sys.dont_write_bytecode = True


SCHEMA = "chummer.canonical-writer-preflight/v3"
SOURCE_CLOSURE_SCHEMA = "chummer.source-closure/v2"
SOURCE_PROJECTION_SCHEMA = "chummer.source-projection/v1"
BUILD_CLOSURE_SCHEMA = "chummer.build-closure/v1"
RUNTIME_GENERATION_CLOSURE_SCHEMA = "chummer.runtime-generation-closure/v1"
LIVE_ENVELOPE_SNAPSHOT_SCHEMA = "chummer.live-envelope-snapshot/v1"
DOTNET_TOOLCHAIN_CLOSURE_SCHEMA = "chummer.dotnet-toolchain-closure/v1"
TEST_SOURCE_PROJECTION_SCHEMA = "chummer.test-source-projection/v1"
CANONICAL = "RELEASE_CHANNEL.generated.json"
COMPATIBILITY = "releases.json"
DERIVED_DIRECTORIES = {
    ".git",
    ".vexp",
    ".codex-studio",
    ".runtime",
    ".state",
    ".cache",
    "_completion",
    "_staging",
    "bin",
    "obj",
    "node_modules",
    "TestResults",
    "test-results",
    "__pycache__",
}
REQUIRED_CANDIDATE_PATHS = (
    "Chummer.Run.Api/Services/PublicReleaseManifestService.cs",
    "Chummer.Run.Api/Services/ReleaseProofFreshnessEvaluator.cs",
    "Chummer.Run.Api/Services/ReleaseProofTrustEvaluator.cs",
    "Chummer.Run.Api/Services/PrivacyLaunchGate.cs",
    "Chummer.Run.Api/Services/ReleaseBundlePromotionService.cs",
    "Chummer.Run.Api/Services/ReleaseBundleUploadSessionService.cs",
    "Chummer.Run.Api/Services/ReleaseShelfGenerationStore.cs",
    "Chummer.Run.Api/Services/ReleaseShelfActivationProtocolReadinessProbe.cs",
    "Chummer.Run.Api/Services/ArtifactDeliveryPolicy.cs",
    "Chummer.Run.Api/Services/InstallLinking/DataProtectionKeyProtectionConfigurator.cs",
    "Chummer.Run.Api/Services/InstallLinking/InstallLinkingStoreActivation.cs",
    "Chummer.Run.Api/Services/InstallLinking/Postgres/InstallLinkingPostgresAuthorityCoordinator.cs",
    "Chummer.Run.Api/Services/InstallLinking/Postgres/InstallLinkingPostgresContracts.cs",
    "Chummer.Run.Api/Services/InstallLinking/Postgres/InstallLinkingPostgresMigrator.cs",
    "Chummer.Run.Api/Services/InstallLinking/Postgres/NpgsqlInstallLinkingSnapshotAuthority.cs",
    "Chummer.Run.Api/Services/PortalDeploymentIdentityReadinessService.cs",
    "Chummer.Run.Api/Controllers/DownloadsCompatibilityController.cs",
    "Chummer.InstallLinking.Postgres.Tool/Program.cs",
    "Chummer.Tests/PublicReleaseManifestServiceTests.cs",
    "Chummer.Tests/ReleaseProofFreshnessEvaluatorTests.cs",
    "Chummer.Tests/ReleaseProofTrustEvaluatorTests.cs",
    "Chummer.Tests/ReleaseBundlePromotionServiceTests.cs",
    "Chummer.Tests/ReleaseBundleUploadSessionServiceTests.cs",
    "Chummer.Tests/ReleaseShelfGenerationStoreTests.cs",
    "Chummer.Tests/DownloadsCompatibilityControllerTests.cs",
    "scripts/publish_public_edge_portal_overlay.py",
    "scripts/release/canonical_writer_preflight.py",
    "scripts/release/landlock_exec.py",
    "scripts/release_shelf_generation.py",
)
MAIN_TRUTH_TEST_FILTER = "|".join(
    (
        "FullyQualifiedName~ReleaseProofFreshnessEvaluatorTests",
        "FullyQualifiedName~ReleaseProofTrustEvaluatorTests",
        "FullyQualifiedName~PublicReleaseManifestServiceTests",
        "FullyQualifiedName~ReleaseBundlePromotionServiceTests",
        "FullyQualifiedName~ReleaseBundleUploadSessionServiceTests",
        "FullyQualifiedName~ReleaseShelfGenerationStoreTests",
        "FullyQualifiedName~DownloadsCompatibilityControllerTests",
        "FullyQualifiedName~InternalReleaseBundlesControllerTests",
    )
)

POSTGRES_IMAGE = "postgres:17-alpine"
POSTGRES_HBA_PATH = "/tls/pg_hba.conf"
POSTGRES_HBA_BYTES = (
    b"local all all trust\n"
    b"hostssl all all 0.0.0.0/0 scram-sha-256\n"
    b"hostssl all all ::/0 scram-sha-256\n"
    b"hostnossl all all 0.0.0.0/0 reject\n"
    b"hostnossl all all ::/0 reject\n"
)
POSTGRES_HBA_INSPECTION_SQL = (
    "SELECT jsonb_build_object("
    "'ssl', current_setting('ssl'), "
    "'hbaFile', current_setting('hba_file'), "
    "'rules', COALESCE((SELECT jsonb_agg(jsonb_build_object("
    "'ruleNumber', rule_number, 'type', type, 'database', database, "
    "'user', user_name, 'address', address, 'netmask', netmask, "
    "'authMethod', auth_method, 'options', options, 'error', error"
    ") ORDER BY rule_number) FROM pg_hba_file_rules), '[]'::jsonb)"
    ")::text"
)
POSTGRES_FORWARDER_MAX_CONNECTIONS = 32
POSTGRES_FORWARDER_IDLE_TIMEOUT_SECONDS = 30.0
DATA_PROTECTION_CERTIFICATE_DAYS = 30
POSTGRES_IMAGE_ID_PATTERN = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
LOWER_SHA256_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")
PORTABLE_TOKEN_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PORTABLE_FILE_NAME_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,254}\Z")
CANONICAL_DOWNLOAD_PATH_PATTERN = re.compile(r"\A/downloads/[A-Za-z0-9._~/-]+\Z")
ALLOWED_RELEASE_CHANNELS = frozenset({"preview", "stable"})
ALLOWED_ARTIFACT_KINDS = frozenset({"installer", "archive"})
ALLOWED_INSTALL_ACCESS_CLASSES = frozenset({"open_public", "account_required"})
REQUIRED_RELEASE_PROOF_JOURNEYS = (
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
)
REQUIRED_RELEASE_PROOF_ROUTES = (
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/access",
    "/account/work",
    "/account/roster",
    "/account/support",
    "/contact",
    "/downloads",
)
RELEASE_PROOF_INSTALL_ROUTE_PATTERN = re.compile(
    r"\A/downloads/install/[a-z0-9][a-z0-9-]*\Z"
)
RUNTIME_ROLE_PATTERN = re.compile(r"\A[a-z_][a-z0-9_]{0,62}\Z")
SECRET_TOKEN_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")
POSTGRES_CONNECTION_PATH_PATTERN = re.compile(r"\A/[A-Za-z0-9._/+\-]+\Z")
DOCKER_OWNER_LABEL = "com.chummer.canonical-writer-preflight.owner"
LOCAL_DOCKER_SOCKET = Path("/run/docker.sock")
DOCKER_CONFIG_ROOT = "/nonexistent"
NETWORK_SCOPE = (
    "isolated child TCP connects are kernel-brokered to explicit loopback ports only; "
    "UDP/raw/Unix sockets denied; Docker bound to unix:///run/docker.sock"
)
CHILD_ISOLATION_CONTRACT = (
    "landlock-write-rights+seccomp-loopback-connect-broker-"
    "port-allowlist-loopback-bind-listen-fast-open-"
    "af-unix-datagram-raw-io-uring-deny"
)
GIT_HERMETIC_ARGUMENTS = (
    "--no-optional-locks",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.pager=cat",
)
RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
MAX_DATA_PROTECTION_KEY_BYTES = 1024 * 1024
MAX_RUNTIME_ARTIFACT_BYTES = 64 * 1024 * 1024
LIVE_ENVELOPE_RECEIPT_SCHEMA = 1
LIVE_ENVELOPE_RECEIPT_OPERATION = "canonical_truth_source_correction"
OUTPUT_WITHHELD = "[command output withheld; SHA-256 retained]"
MAX_REUSE_EVIDENCE_BYTES = 8 * 1024 * 1024
FIRST_PASS_COMMAND_NAMES = (
    "restore",
    "truth-tests",
    "publish-install-linking-postgres-tool",
    "publish",
)
FIRST_PASS_GATE_CONTRACT = {
    "candidateBaseMatches": True,
    "coherentCandidateContainsWriterAndTruthFloor": True,
    "sourceClosureOperatorPinned": True,
    "sourceClosureStableThroughRuntimeAndRollback": True,
    "sourceProjectionStableThroughRuntimeAndRollback": True,
    "toolingClosureStableThroughRuntimeAndRollback": True,
    "systemToolsOperatorPinned": True,
    "systemToolsStableThroughRuntimeAndRollback": True,
    "dotnetToolchainOperatorPinned": True,
    "dotnetToolchainStableThroughRuntimeAndRollback": True,
    "childWriteIsolationEnforced": True,
    "generationToolBoundToCandidate": True,
    "liveEnvelopeReceiptBinding": True,
    "liveEnvelopeSnapshotStableThroughRuntimeAndRollback": True,
    "restoreTestsPublish": True,
    "contentAddressedBuildClosure": True,
    "buildClosureOperatorPinned": False,
    "buildClosureStableDuringRuntime": True,
    "finalizedOverlayIdentity": True,
    "productionModeReadyAndTruthProjection": False,
    "atomicGenerationPointerRollback": True,
    "productionMutation": False,
}
FIRST_PASS_REASON_CONTRACT = (
    "build_closure_not_operator_pinned",
    "production_mode_loopback_runtime_gate_failed",
)
COMMAND_RECEIPT_KEYS = frozenset(
    {
        "name",
        "argv",
        "cwd",
        "exitCode",
        "passed",
        "durationSeconds",
        "stdoutSha256",
        "stderrSha256",
        "stdoutTail",
        "stderrTail",
    }
)
FIRST_PASS_RECEIPT_KEYS = frozenset(
    {
        "schemaVersion",
        "state",
        "decision",
        "startedAt",
        "completedAt",
        "productionMutation",
        "networkScope",
        "candidate",
        "requiredCandidatePaths",
        "sourceClosure",
        "sourceProjection",
        "toolingClosure",
        "systemTools",
        "dotnetToolchain",
        "buildClosure",
        "liveEnvelope",
        "liveEnvelopeSnapshot",
        "postgresImage",
        "commands",
        "testSourceProjection",
        "reusedBuildEvidence",
        "runtimeBuildProjection",
        "runtime",
        "overlayIdentity",
        "rollbackProbe",
        "gates",
        "reasons",
        "rollbackPlan",
    }
)


class PreflightError(RuntimeError):
    """A bounded preflight operation could not produce trustworthy evidence."""


class PreflightCancelled(BaseException):
    """External cancellation that must unwind every cleanup scope without being retained."""


def _terminate_for_signal(signum: int, _frame: Any) -> None:
    """Turn CI cancellation into normal exception unwinding and one cleanup pass."""

    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        name = signal.Signals(signum).name
    except ValueError:
        name = str(signum)
    raise PreflightCancelled(f"preflight terminated by signal {name}")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return 3xx responses to the caller instead of following their Location."""

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


@dataclass(frozen=True)
class CommandResult:
    name: str
    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    duration_seconds: float
    stdout_sha256: str
    stderr_sha256: str
    stdout_tail: str
    stderr_tail: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "exitCode": self.exit_code,
            "passed": self.passed,
            "durationSeconds": round(self.duration_seconds, 3),
            "stdoutSha256": self.stdout_sha256,
            "stderrSha256": self.stderr_sha256,
            "stdoutTail": self.stdout_tail,
            "stderrTail": self.stderr_tail,
        }


@dataclass(frozen=True)
class RuntimeTlsMaterial:
    ca_certificate: Path
    server_certificate: Path
    server_key: Path
    data_protection_certificate: Path
    data_protection_password_file: Path


@dataclass(frozen=True)
class PostgresRuntimeAuthority:
    runtime_connection_file: Path
    image_id: str
    container_name: str
    host_port: int
    evidence: dict[str, Any]


@dataclass(frozen=True)
class LoopbackRuntimeHandle:
    process: subprocess.Popen[bytes]
    port: int
    ssl_context: ssl.SSLContext
    evidence: dict[str, Any]


@dataclass(frozen=True)
class SourceProjection:
    root: Path
    workspace_root: Path
    candidate_root: Path
    media_factory_root: Path
    manifest: dict[str, Any]
    omitted_symlinks: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class JsonByteSnapshot:
    label: str
    source_path: Path
    retained_path: Path
    raw: bytes
    sha256: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class LiveEnvelopeSnapshot:
    root: Path
    receipt: JsonByteSnapshot
    canonical: JsonByteSnapshot
    compatibility: JsonByteSnapshot
    closure: dict[str, Any]


@dataclass(frozen=True)
class DotnetExecution:
    host: Path
    host_sha256: str
    root: Path
    toolchain_closure: dict[str, Any]
    python_host: Path
    python_host_sha256: str
    landlock_launcher: Path
    seccomp_library: Path
    landlock_abi: int


@dataclass(frozen=True)
class PinnedSystemTools:
    git: Path
    git_sha256: str
    docker: Path
    docker_sha256: str
    docker_socket: Path
    docker_socket_identity: dict[str, int]
    openssl: Path
    openssl_sha256: str
    seccomp_library: Path
    seccomp_library_sha256: str


@dataclass(frozen=True)
class RuntimeBuildProjection:
    root: Path
    publish_root: Path
    postgres_tool_root: Path
    source_closure_sha256: str
    content_sha256: str
    sealed_closure: dict[str, Any]
    independent_inodes: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_lower_sha256(value: Any, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not LOWER_SHA256_PATTERN.fullmatch(normalized):
        raise PreflightError(f"{label} must be an operator-supplied lowercase SHA-256")
    return normalized


def require_postgres_image_id(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not POSTGRES_IMAGE_ID_PATTERN.fullmatch(normalized):
        raise PreflightError(
            "--expected-postgres-image-id must be an operator-supplied sha256:<64 hex> image ID"
        )
    return normalized


def _trusted_root_owned_regular_file(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise PreflightError(f"{label} must be an absolute path")
    resolved = _resolve_without_symlink_components(path, label)
    metadata = resolved.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o022
    ):
        raise PreflightError(
            f"{label} must be a root-owned, non-writable regular file: {resolved}"
        )
    return resolved


def _trusted_root_owned_executable(path: Path, label: str) -> Path:
    resolved = _trusted_root_owned_regular_file(path, label)
    if resolved.stat().st_mode & 0o111 == 0:
        raise PreflightError(f"{label} must be executable: {resolved}")
    return resolved


def _bind_pinned_executable(path: Path, expected_sha256: str, label: str) -> tuple[Path, str]:
    resolved = _trusted_root_owned_executable(path, label)
    actual = sha256_file(resolved)
    expected = require_lower_sha256(expected_sha256, f"expected {label} SHA-256")
    if not secrets.compare_digest(actual, expected):
        raise PreflightError(f"{label} does not match its operator pin; computed {actual}")
    return resolved, actual


def docker_socket_identity(path: Path = LOCAL_DOCKER_SOCKET) -> tuple[Path, dict[str, int]]:
    resolved = _resolve_without_symlink_components(path, "local Docker daemon socket")
    metadata = resolved.lstat()
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o002
    ):
        raise PreflightError(
            "local Docker daemon endpoint must be a root-owned, non-world-writable socket"
        )
    return resolved, {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "mode": stat.S_IMODE(metadata.st_mode),
    }


def docker_argv(docker_host: Path, *arguments: str) -> tuple[str, ...]:
    return (
        str(docker_host),
        "--config",
        DOCKER_CONFIG_ROOT,
        "--host",
        f"unix://{LOCAL_DOCKER_SOCKET}",
        *arguments,
    )


def git_argv(git_host: Path, *arguments: str) -> tuple[str, ...]:
    return (str(git_host), *GIT_HERMETIC_ARGUMENTS, *arguments)


def git_environment() -> dict[str, str]:
    return sanitized_environment(
        {
            "HOME": "/nonexistent",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )


def bind_system_tools(
    *,
    git: Path,
    expected_git_sha256: str,
    docker: Path,
    expected_docker_sha256: str,
    openssl: Path,
    expected_openssl_sha256: str,
    seccomp_library: Path,
    expected_seccomp_library_sha256: str,
) -> PinnedSystemTools:
    if Path(DOCKER_CONFIG_ROOT).exists():
        raise PreflightError("fail-closed Docker/Git config root unexpectedly exists")
    git_host, git_sha256 = _bind_pinned_executable(git, expected_git_sha256, "Git host")
    docker_host, docker_sha256 = _bind_pinned_executable(
        docker, expected_docker_sha256, "Docker host"
    )
    docker_socket, docker_identity = docker_socket_identity()
    openssl_host, openssl_sha256 = _bind_pinned_executable(
        openssl, expected_openssl_sha256, "OpenSSL host"
    )
    seccomp = _trusted_root_owned_regular_file(seccomp_library, "libseccomp")
    seccomp_sha256 = sha256_file(seccomp)
    expected_seccomp = require_lower_sha256(
        expected_seccomp_library_sha256,
        "expected libseccomp SHA-256",
    )
    if not secrets.compare_digest(seccomp_sha256, expected_seccomp):
        raise PreflightError(
            f"libseccomp does not match its operator pin; computed {seccomp_sha256}"
        )
    return PinnedSystemTools(
        git=git_host,
        git_sha256=git_sha256,
        docker=docker_host,
        docker_sha256=docker_sha256,
        docker_socket=docker_socket,
        docker_socket_identity=docker_identity,
        openssl=openssl_host,
        openssl_sha256=openssl_sha256,
        seccomp_library=seccomp,
        seccomp_library_sha256=seccomp_sha256,
    )


def system_tools_receipt(
    tools: PinnedSystemTools,
    *,
    final_sha256: Mapping[str, str] | None = None,
    stable: bool = True,
) -> dict[str, Any]:
    final = final_sha256 or {
        "git": tools.git_sha256,
        "docker": tools.docker_sha256,
        "openssl": tools.openssl_sha256,
        "libseccomp": tools.seccomp_library_sha256,
    }
    return {
        "git": {
            "path": str(tools.git),
            "sha256": tools.git_sha256,
            "finalSha256": final["git"],
            "hermeticArguments": list(GIT_HERMETIC_ARGUMENTS),
            "globalConfig": "/dev/null",
            "systemConfigDisabled": True,
            "repositoryFsmonitorDisabled": True,
            "repositoryHooksDisabled": True,
        },
        "docker": {
            "path": str(tools.docker),
            "sha256": tools.docker_sha256,
            "finalSha256": final["docker"],
            "configRoot": DOCKER_CONFIG_ROOT,
            "endpoint": f"unix://{tools.docker_socket}",
            "socketIdentity": dict(tools.docker_socket_identity),
            "socketStableThroughRuntimeAndRollback": stable,
        },
        "openssl": {
            "path": str(tools.openssl),
            "sha256": tools.openssl_sha256,
            "finalSha256": final["openssl"],
        },
        "libseccomp": {
            "path": str(tools.seccomp_library),
            "sha256": tools.seccomp_library_sha256,
            "finalSha256": final["libseccomp"],
        },
        "operatorPinned": True,
        "stableThroughRuntimeAndRollback": stable,
    }


def query_landlock_abi() -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    value = int(libc.syscall(444, 0, 0, 1))
    if value < 0:
        error = ctypes.get_errno()
        raise PreflightError(
            f"Landlock ABI query failed: {os.strerror(error)}"
        )
    if value < 3:
        raise PreflightError(
            f"Landlock ABI {value} cannot enforce truncate/refer write isolation"
        )
    return value


def build_dotnet_toolchain_closure(root: Path) -> dict[str, Any]:
    root = _resolve_without_symlink_components(root, ".NET toolchain root")
    if not root.is_dir():
        raise PreflightError(f".NET toolchain root is not a directory: {root}")
    rows: list[dict[str, Any]] = []

    def retain(path: Path, relative: str) -> None:
        before = path.lstat()
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )

        def require_stable(after: os.stat_result) -> None:
            if any(
                getattr(before, field) != getattr(after, field)
                for field in stable_fields
            ):
                raise PreflightError(f".NET toolchain changed while it was hashed: {path}")

        mode = stat.S_IMODE(before.st_mode)
        if stat.S_ISLNK(before.st_mode):
            target = os.readlink(path)
            resolved_target = (path.parent / target).resolve(strict=True)
            if not resolved_target.is_relative_to(root):
                raise PreflightError(f".NET toolchain symlink escapes its root: {path}")
            raw = os.fsencode(target)
            require_stable(path.lstat())
            rows.append(
                {
                    "path": relative,
                    "state": "symlink",
                    "mode": mode,
                    "sizeBytes": len(raw),
                    "sha256": sha256_bytes(raw),
                }
            )
            return
        if before.st_uid != 0 or before.st_mode & 0o022:
            raise PreflightError(f".NET toolchain entry is not root-owned/read-only: {path}")
        if stat.S_ISDIR(before.st_mode):
            rows.append(
                {
                    "path": relative,
                    "state": "directory",
                    "mode": mode,
                    "sizeBytes": 0,
                    "sha256": sha256_bytes(f"directory:{relative}".encode()),
                }
            )
            with os.scandir(path) as entries:
                children = sorted(entries, key=lambda entry: entry.name)
            for child in children:
                child_relative = (
                    child.name if relative == "." else f"{relative}/{child.name}"
                )
                retain(Path(child.path), child_relative)
            after = path.lstat()
        elif stat.S_ISREG(before.st_mode):
            digest = sha256_file(path)
            rows.append(
                {
                    "path": relative,
                    "state": "regular",
                    "mode": mode,
                    "sizeBytes": before.st_size,
                    "sha256": digest,
                }
            )
            after = path.lstat()
        else:
            raise PreflightError(f".NET toolchain contains a special file: {path}")
        require_stable(after)

    retain(root, ".")
    rows.sort(key=lambda row: str(row["path"]))
    return {
        "schemaVersion": DOTNET_TOOLCHAIN_CLOSURE_SCHEMA,
        "files": rows,
        "fileCount": len(rows),
        "totalBytes": sum(int(row["sizeBytes"]) for row in rows),
        "closureSha256": sha256_bytes(canonical_json_bytes(rows)),
    }


def bind_dotnet_execution(
    configured_host: Path,
    expected_host_sha256: str,
    expected_toolchain_sha256: str,
    landlock_launcher: Path,
    seccomp_library: Path,
) -> DotnetExecution:
    host = _trusted_root_owned_executable(configured_host, ".NET host")
    host_sha256 = sha256_file(host)
    expected_host = require_lower_sha256(
        expected_host_sha256,
        "expected .NET host SHA-256",
    )
    if not secrets.compare_digest(host_sha256, expected_host):
        raise PreflightError(
            ".NET host does not match its operator-supplied SHA-256; "
            f"computed {host_sha256}"
        )
    root = host.parent
    if host.name != "dotnet" or not all(
        (root / relative).is_dir() for relative in ("host/fxr", "sdk", "shared")
    ):
        raise PreflightError(".NET host is not rooted in one complete toolchain")
    closure = build_dotnet_toolchain_closure(root)
    expected_toolchain = require_lower_sha256(
        expected_toolchain_sha256,
        "expected .NET toolchain closure SHA-256",
    )
    if not secrets.compare_digest(closure["closureSha256"], expected_toolchain):
        raise PreflightError(
            ".NET toolchain does not match its operator-supplied closure SHA-256; "
            f"computed {closure['closureSha256']}"
        )
    python_host = _trusted_root_owned_executable(
        Path(sys.executable).resolve(strict=True),
        "Landlock launcher Python host",
    )
    launcher = _resolve_without_symlink_components(
        landlock_launcher,
        "Landlock launcher",
    )
    if not launcher.is_file() or not stat.S_ISREG(launcher.stat().st_mode):
        raise PreflightError(f"Landlock launcher is not a regular file: {launcher}")
    return DotnetExecution(
        host=host,
        host_sha256=host_sha256,
        root=root,
        toolchain_closure=closure,
        python_host=python_host,
        python_host_sha256=sha256_file(python_host),
        landlock_launcher=launcher,
        seccomp_library=seccomp_library,
        landlock_abi=query_landlock_abi(),
    )


def dotnet_toolchain_receipt(
    execution: DotnetExecution,
    *,
    final_sha256: str | None = None,
    stable: bool = True,
) -> dict[str, Any]:
    return {
        "hostPath": str(execution.host),
        "hostSha256": execution.host_sha256,
        "hostOperatorPinned": True,
        "root": str(execution.root),
        "closureSha256": execution.toolchain_closure["closureSha256"],
        "closureOperatorPinned": True,
        "finalSha256": (
            execution.toolchain_closure["closureSha256"]
            if final_sha256 is None
            else final_sha256
        ),
        "stableThroughRuntimeAndRollback": stable,
        "fileCount": execution.toolchain_closure["fileCount"],
        "totalBytes": execution.toolchain_closure["totalBytes"],
        "pythonHostPath": str(execution.python_host),
        "pythonHostSha256": execution.python_host_sha256,
        "landlockAbi": execution.landlock_abi,
        "writeIsolation": CHILD_ISOLATION_CONTRACT,
        "networkIsolation": (
            "seccomp-user-notification-explicit-loopback-port-"
            "connect-bind-listen-broker+tcp-fast-open-deny"
        ),
    }


def isolated_dotnet_argv(
    execution: DotnetExecution,
    command: Sequence[str],
    allowed_write_roots: Sequence[Path],
    allowed_connect_ports: Sequence[int] = (),
    allowed_bind_ports: Sequence[int] = (),
) -> tuple[str, ...]:
    if not command or Path(command[0]) != execution.host:
        raise PreflightError("isolated .NET command must use the pinned absolute host")
    roots = tuple(sorted({Path(path).resolve(strict=True) for path in allowed_write_roots}))
    if not roots:
        raise PreflightError("isolated .NET command requires an explicit write allowance")
    ports = tuple(sorted(set(allowed_connect_ports)))
    if len(ports) != len(allowed_connect_ports) or any(
        type(port) is not int or port < 1 or port > 65535 for port in ports
    ):
        raise PreflightError("isolated .NET connect allowances must be unique TCP ports")
    bind_ports = tuple(sorted(set(allowed_bind_ports)))
    if len(bind_ports) != len(allowed_bind_ports) or any(
        type(port) is not int or port < 1 or port > 65535 for port in bind_ports
    ):
        raise PreflightError("isolated .NET bind allowances must be unique TCP ports")
    launcher: list[str] = [
        str(execution.python_host),
        str(execution.landlock_launcher),
        "--seccomp-library",
        str(execution.seccomp_library),
    ]
    for root in roots:
        launcher.extend(("--allow-write", str(root)))
    for port in ports:
        launcher.extend(("--allow-connect-port", str(port)))
    for port in bind_ports:
        launcher.extend(("--allow-bind-port", str(port)))
    launcher.append("--")
    launcher.extend(str(value) for value in command)
    return tuple(launcher)


def bind_generation_tool(candidate_root: Path, configured_path: Path) -> Path:
    expected = candidate_root / "scripts" / "release_shelf_generation.py"
    expected = _resolve_without_symlink_components(expected, "candidate generation tool")
    configured = _resolve_without_symlink_components(configured_path, "configured generation tool")
    if configured != expected:
        raise PreflightError(
            "--generation-tool must resolve to the candidate's scripts/release_shelf_generation.py"
        )
    return expected


def build_output_closure(publish_root: Path, postgres_tool_root: Path) -> dict[str, Any]:
    roots = (("portal", publish_root), ("postgres-tool", postgres_tool_root))
    manifest = build_closure_manifest(
        BUILD_CLOSURE_SCHEMA,
        roots,
        excluded_directories=(),
    )
    directories: list[dict[str, Any]] = []
    for label, root in roots:
        root = _resolve_without_symlink_components(root, f"build output root {label}")
        for current, directory_names, _file_names in os.walk(root, followlinks=False):
            directory_names.sort()
            current_path = Path(current)
            if any((current_path / name).is_symlink() for name in directory_names):
                raise PreflightError("build output contains a directory symlink")
            relative = current_path.relative_to(root).as_posix()
            logical = label if relative == "." else f"{label}/{relative}"
            directories.append(
                {
                    "path": logical,
                    "mode": stat.S_IMODE(current_path.lstat().st_mode),
                }
            )
    directories.sort(key=lambda row: str(row["path"]))
    manifest["directories"] = directories
    manifest["closureSha256"] = sha256_bytes(
        canonical_json_bytes(
            {"files": manifest["files"], "directories": directories}
        )
    )
    return manifest


def closure_content_sha256(closure: Mapping[str, Any]) -> str:
    files = closure.get("files")
    directories = closure.get("directories")
    if not isinstance(files, list) or not isinstance(directories, list):
        raise PreflightError("closure content projection is incomplete")
    projected_files = [
        {
            "path": str(row.get("path") or ""),
            "sizeBytes": int(row.get("sizeBytes") or 0),
            "sha256": str(row.get("sha256") or ""),
        }
        for row in files
        if isinstance(row, dict)
    ]
    projected_directories = [
        str(row.get("path") or "")
        for row in directories
        if isinstance(row, dict)
    ]
    if len(projected_files) != len(files) or len(projected_directories) != len(directories):
        raise PreflightError("closure content projection contains malformed rows")
    return sha256_bytes(
        canonical_json_bytes(
            {
                "files": projected_files,
                "directories": projected_directories,
            }
        )
    )


def materialize_test_source_projection(
    candidate_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Copy the pinned repository fixtures expected beside isolated test binaries."""

    source_compose = candidate_root / "docker-compose.public-edge.yml"
    source_fixtures = candidate_root / "tests" / "fixtures"
    source_closure = build_closure_manifest(
        TEST_SOURCE_PROJECTION_SCHEMA,
        (("compose", source_compose), ("fixtures", source_fixtures)),
        excluded_directories=(),
    )

    projected_compose = output_root / "docker-compose.public-edge.yml"
    projected_fixtures = output_root / "tests" / "fixtures"
    if projected_compose.exists() or projected_fixtures.exists():
        raise PreflightError("isolated test source projection already exists")
    write_owner_only_file(projected_compose, source_compose.read_bytes())
    os.chmod(projected_compose, stat.S_IMODE(source_compose.stat().st_mode))
    for relative, source in _iter_regular_files(source_fixtures, frozenset()):
        projected = projected_fixtures / relative
        write_owner_only_file(projected, source.read_bytes())
        os.chmod(projected, stat.S_IMODE(source.stat().st_mode))

    projected_closure = build_closure_manifest(
        TEST_SOURCE_PROJECTION_SCHEMA,
        (("compose", projected_compose), ("fixtures", projected_fixtures)),
        excluded_directories=(),
    )
    if source_closure["closureSha256"] != projected_closure["closureSha256"]:
        raise PreflightError("isolated test source projection does not match pinned source bytes")
    return {
        "passed": True,
        "productionMutation": False,
        "closureSha256": source_closure["closureSha256"],
        "fileCount": source_closure["fileCount"],
        "totalBytes": source_closure["totalBytes"],
        "composePath": str(projected_compose),
        "fixturesRoot": str(projected_fixtures),
    }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"{label} is unreadable or malformed: {path} ({exc})") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"{label} must be a JSON object: {path}")
    return value


def _strict_json_object_from_bytes(raw: bytes, label: str, source: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON property: {key}")
            value[key] = item
        return value

    def reject_non_finite(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    def parse_finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"non-finite JSON number: {value}")
        return parsed

    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
            parse_float=parse_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PreflightError(f"{label} is not strict UTF-8 JSON: {source} ({exc})") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"{label} must be a JSON object: {source}")
    return value


def read_strict_json_byte_snapshot(
    path: Path,
    label: str,
    *,
    expected_sha256: str | None = None,
    max_bytes: int = MAX_REUSE_EVIDENCE_BYTES,
) -> tuple[dict[str, Any], bytes, str, Path]:
    """Read, hash, and strictly decode one stable descriptor-backed byte image."""

    if type(max_bytes) is not int or max_bytes <= 0:
        raise PreflightError(f"{label} byte limit must be a positive integer")
    expected = (
        require_lower_sha256(expected_sha256, f"expected {label} SHA-256")
        if expected_sha256 is not None
        else None
    )
    resolved = _resolve_without_symlink_components(path, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(resolved, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PreflightError(f"{label} must be a regular file: {resolved}")
        if before.st_size > max_bytes:
            raise PreflightError(f"{label} exceeds the {max_bytes}-byte evidence limit")
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > max_bytes:
                raise PreflightError(f"{label} exceeds the {max_bytes}-byte evidence limit")
        after = os.fstat(descriptor)
    except OSError as exc:
        raise PreflightError(f"{label} is unreadable: {resolved} ({exc})") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise PreflightError(f"{label} changed while its byte snapshot was read: {resolved}")
    raw = b"".join(chunks)
    if len(raw) != before.st_size:
        raise PreflightError(f"{label} size changed while its byte snapshot was read: {resolved}")
    actual = sha256_bytes(raw)
    if expected is not None and not secrets.compare_digest(actual, expected):
        raise PreflightError(f"{label} does not match its operator-supplied SHA-256")
    return _strict_json_object_from_bytes(raw, label, resolved), raw, actual, resolved


def read_operator_pinned_json_object(
    path: Path,
    expected_sha256: str,
    label: str,
) -> tuple[dict[str, Any], str]:
    """Hash and decode the same bounded byte snapshot of operator-pinned evidence."""

    value, _raw, actual, _resolved = read_strict_json_byte_snapshot(
        path,
        label,
        expected_sha256=expected_sha256,
    )
    return value, actual


def normalize_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PreflightError("publication timestamp must be a non-empty unpadded string")
    token = value
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError as exc:
        raise PreflightError("publication timestamp must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreflightError("publication timestamp must include an explicit UTC offset")
    return parsed.astimezone(timezone.utc).isoformat()


def truth_test_command(
    candidate_root: Path,
    dotnet_host: Path,
) -> tuple[Path | None, tuple[str, ...]]:
    isolated = candidate_root / "tests" / "CanonicalManifestTruth.Tests" / "CanonicalManifestTruth.Tests.csproj"
    if isolated.is_file():
        return isolated, (
            str(dotnet_host),
            "test",
            str(isolated),
            "--no-restore",
            "--logger",
            "console;verbosity=normal",
        )

    integrated = candidate_root / "Chummer.Tests" / "Chummer.Tests.csproj"
    if integrated.is_file():
        return integrated, (
            str(dotnet_host),
            "test",
            str(integrated),
            "--framework",
            "net10.0",
            "--no-restore",
            "--filter",
            MAIN_TRUTH_TEST_FILTER,
            "--logger",
            "console;verbosity=normal",
        )

    return None, ()


def first_pass_command_contract(
    candidate_root: Path,
    first_pass_output_root: Path,
    publish_root: Path,
    postgres_tool_root: Path,
    dotnet_execution: DotnetExecution,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the only command sequence accepted as reusable first-pass evidence."""

    test_project, truth_argv = truth_test_command(candidate_root, dotnet_execution.host)
    if test_project is None or not truth_argv:
        raise PreflightError("reused first-pass evidence requires the focused truth-test project")
    artifacts = first_pass_output_root / "dotnet-artifacts"
    restore_packages = first_pass_output_root / "nuget-packages"
    write_roots = tuple(
        first_pass_output_root / name
        for name in (
            "dotnet-artifacts",
            "nuget-packages",
            "dotnet-home",
            "nuget-http-cache",
            "nuget-plugins-cache",
            "tmp",
            "logs",
        )
    ) + (publish_root, postgres_tool_root)
    raw_commands = (
        (
            "restore",
            (
                str(dotnet_execution.host),
                "restore",
                str(test_project),
                "--nologo",
                "--artifacts-path",
                str(artifacts),
                f"-p:RestorePackagesPath={restore_packages}",
            ),
        ),
        (
            "truth-tests",
            (
                *truth_argv,
                "--artifacts-path",
                str(artifacts),
                f"-p:RestorePackagesPath={restore_packages}",
            ),
        ),
        (
            "publish-install-linking-postgres-tool",
            (
                str(dotnet_execution.host),
                "publish",
                str(
                    candidate_root
                    / "Chummer.InstallLinking.Postgres.Tool"
                    / "Chummer.InstallLinking.Postgres.Tool.csproj"
                ),
                "-c",
                "Release",
                "-o",
                str(postgres_tool_root),
                "--nologo",
                "-m:1",
                "-p:BuildInParallel=false",
                "-p:UseSharedCompilation=false",
                "--artifacts-path",
                str(artifacts),
                f"-p:RestorePackagesPath={restore_packages}",
            ),
        ),
        (
            "publish",
            (
                str(dotnet_execution.host),
                "publish",
                str(candidate_root / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"),
                "-c",
                "Release",
                "-o",
                str(publish_root),
                "--no-restore",
                "--nologo",
                "-m:1",
                "-p:BuildInParallel=false",
                "-p:UseSharedCompilation=false",
                "--artifacts-path",
                str(artifacts),
                f"-p:RestorePackagesPath={restore_packages}",
            ),
        ),
    )
    return tuple(
        (
            name,
            isolated_dotnet_argv(dotnet_execution, argv, write_roots),
        )
        for name, argv in raw_commands
    )


def validate_first_pass_reuse_evidence(
    evidence: dict[str, Any],
    *,
    evidence_path: Path,
    candidate_root: Path,
    candidate_identity: Mapping[str, Any],
    required_paths: Mapping[str, bool],
    source_closure: Mapping[str, Any],
    source_projection: SourceProjection,
    tooling_closure: Mapping[str, Any],
    build_closure: Mapping[str, Any],
    expected_build_sha256: str,
    publish_root: Path,
    postgres_tool_root: Path,
    test_source_projection: Mapping[str, Any],
    live_envelope: Mapping[str, Any],
    live_envelope_snapshot: LiveEnvelopeSnapshot,
    dotnet_execution: DotnetExecution,
    system_tools: PinnedSystemTools,
    expected_postgres_image_id: str,
) -> list[dict[str, Any]]:
    """Validate that pinned evidence is exactly the non-runtime first build pass."""

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise PreflightError(f"reused preflight evidence {message}")

    first_output = evidence_path.parent
    require(
        evidence_path == first_output / "preflight.receipt.json",
        "path must be the first-pass preflight.receipt.json",
    )
    require(
        publish_root == first_output / "publish"
        and postgres_tool_root == first_output / "postgres-tool",
        "build roots are not the receipt's exact first-pass siblings",
    )
    require(set(evidence) == FIRST_PASS_RECEIPT_KEYS, "top-level contract is not exact")
    require(evidence.get("schemaVersion") == SCHEMA, "schema is invalid")
    require(evidence.get("state") == "completed", "state is not completed")
    require(evidence.get("decision") == "no-go", "must be the unpinned first-pass no-go")
    try:
        started_at = normalize_timestamp(evidence.get("startedAt"))
        completed_at = normalize_timestamp(evidence.get("completedAt"))
        temporal_contract_valid = datetime.fromisoformat(completed_at) >= datetime.fromisoformat(
            started_at
        )
    except (PreflightError, TypeError, ValueError):
        temporal_contract_valid = False
    require(
        temporal_contract_valid,
        "timestamps are malformed, timezone-naive, or reversed",
    )
    require(evidence.get("productionMutation") is False, "claims a production mutation")
    require(
        evidence.get("networkScope")
        == NETWORK_SCOPE,
        "network scope is invalid",
    )
    require(evidence.get("candidate") == dict(candidate_identity), "candidate identity drifted")
    require(
        evidence.get("requiredCandidatePaths") == dict(required_paths)
        and all(required_paths.values()),
        "candidate path contract is invalid",
    )
    require(evidence.get("liveEnvelope") == dict(live_envelope), "live envelope drifted")
    require(
        evidence.get("systemTools") == system_tools_receipt(system_tools),
        "system tool identity drifted",
    )
    require(
        evidence.get("dotnetToolchain") == dotnet_toolchain_receipt(dotnet_execution),
        ".NET toolchain identity drifted",
    )
    first_live_envelope_root = first_output / "live-envelope-snapshot"
    first_live_envelope_closure = build_live_envelope_snapshot_closure(
        first_live_envelope_root
    )
    require(
        first_live_envelope_closure["closureSha256"]
        == live_envelope_snapshot.closure["closureSha256"],
        "live envelope snapshot bytes drifted",
    )
    expected_live_envelope_snapshot = live_envelope_snapshot_receipt_evidence(
        live_envelope_snapshot,
        live_envelope,
        root=first_live_envelope_root,
        final_sha256=first_live_envelope_closure["closureSha256"],
        stable=True,
    )
    require(
        evidence.get("liveEnvelopeSnapshot") == expected_live_envelope_snapshot,
        "live envelope snapshot contract is not exact",
    )
    require(
        evidence.get("postgresImage")
        == {
            "reference": POSTGRES_IMAGE,
            "expectedImageId": expected_postgres_image_id,
        },
        "PostgreSQL image contract is invalid",
    )
    require(evidence.get("reusedBuildEvidence") is None, "was itself a reused build")
    require(evidence.get("runtimeBuildProjection") is None, "used a runtime build projection")
    require(
        evidence.get("runtime")
        == {
            "passed": False,
            "skipped": True,
            "reason": "build_closure_not_operator_pinned",
        },
        "runtime contract is not the intentionally skipped first pass",
    )
    require(evidence.get("gates") == FIRST_PASS_GATE_CONTRACT, "gate contract is not exact")
    require(
        evidence.get("reasons") == list(FIRST_PASS_REASON_CONTRACT),
        "reason contract is not exact",
    )

    expected_source = {
        "path": str(first_output / "source-closure.json"),
        "sha256": source_closure["closureSha256"],
        "expectedSha256": source_closure["closureSha256"],
        "operatorPinned": True,
        "stableThroughRuntimeAndRollback": True,
        "afterBuildSha256": source_closure["closureSha256"],
        "finalSha256": source_closure["closureSha256"],
    }
    require(evidence.get("sourceClosure") == expected_source, "source closure is not exact")
    first_projection_root = first_output / "source-projection"
    (
        first_projection_workspace,
        first_projection_candidate,
        first_projection_media,
        _,
    ) = _source_projection_roots(first_projection_root)
    expected_projection_sha = str(source_projection.manifest["closureSha256"])
    recorded_projection = evidence.get("sourceProjection")
    recorded_monitors = (
        recorded_projection.get("transientMutationMonitors")
        if isinstance(recorded_projection, dict)
        else None
    )
    expected_monitor_roots = [
        str(first_projection_root),
        str(first_live_envelope_root),
        str(first_output / "docker-compose.public-edge.yml"),
        str(first_output / "tests" / "fixtures"),
    ]
    require(
        isinstance(recorded_monitors, list)
        and len(recorded_monitors) == len(FIRST_PASS_COMMAND_NAMES)
        and [row.get("command") for row in recorded_monitors if isinstance(row, dict)]
        == list(FIRST_PASS_COMMAND_NAMES)
        and all(
            isinstance(row, dict)
            and row.get("passed") is True
            and row.get("mutationEventCount") == 0
            and row.get("queueOverflow") is False
            and row.get("monitorErrors") == []
            and row.get("roots") == expected_monitor_roots
            and type(row.get("watchCount")) is int
            and row.get("watchCount") > 0
            for row in recorded_monitors
        ),
        "source projection mutation-monitor contract is invalid",
    )
    expected_projection = source_projection_receipt_evidence(
        SourceProjection(
            root=first_projection_root,
            workspace_root=first_projection_workspace,
            candidate_root=first_projection_candidate,
            media_factory_root=first_projection_media,
            manifest=source_projection.manifest,
            omitted_symlinks=source_projection.omitted_symlinks,
        ),
        manifest_path=first_output / "source-projection-closure.json",
        after_build_sha256=expected_projection_sha,
        final_sha256=expected_projection_sha,
        stable=True,
        mutation_monitors=recorded_monitors,
        execution_reused=False,
    )
    require(
        evidence.get("sourceProjection") == expected_projection,
        "source projection is not exact",
    )
    expected_tooling = {
        "path": str(first_output / "tooling-closure.json"),
        "sha256": tooling_closure["closureSha256"],
        "fileCount": tooling_closure["fileCount"],
        "finalSha256": tooling_closure["closureSha256"],
        "stableThroughRuntimeAndRollback": True,
    }
    require(evidence.get("toolingClosure") == expected_tooling, "tooling closure is not exact")
    expected_build = {
        "path": str(first_output / "build-closure.json"),
        "sha256": build_closure["closureSha256"],
        "fileCount": build_closure["fileCount"],
        "totalBytes": build_closure["totalBytes"],
        "expectedSha256": None,
        "operatorPinned": False,
        "portalRoot": str(publish_root),
        "postgresToolRoot": str(postgres_tool_root),
    }
    require(evidence.get("buildClosure") == expected_build, "build closure is not exact")
    require(
        expected_build_sha256 == build_closure["closureSha256"],
        "build closure does not match the second-pass operator pin",
    )

    first_dotnet_execution = DotnetExecution(
        host=dotnet_execution.host,
        host_sha256=dotnet_execution.host_sha256,
        root=dotnet_execution.root,
        toolchain_closure=dotnet_execution.toolchain_closure,
        python_host=dotnet_execution.python_host,
        python_host_sha256=dotnet_execution.python_host_sha256,
        landlock_launcher=(
            first_projection_candidate / "scripts" / "release" / "landlock_exec.py"
        ),
        seccomp_library=dotnet_execution.seccomp_library,
        landlock_abi=dotnet_execution.landlock_abi,
    )
    expected_commands = first_pass_command_contract(
        first_projection_candidate,
        first_output,
        publish_root,
        postgres_tool_root,
        first_dotnet_execution,
    )
    commands = evidence.get("commands")
    require(isinstance(commands, list), "commands are not a list")
    require(len(commands) == len(expected_commands), "command count is not exact")
    for row, (expected_name, expected_argv) in zip(commands, expected_commands, strict=True):
        require(isinstance(row, dict), "contains a non-object command")
        require(set(row) == COMMAND_RECEIPT_KEYS, f"command {expected_name} fields are not exact")
        require(row.get("name") == expected_name, f"command {expected_name} name/order drifted")
        require(row.get("argv") == list(expected_argv), f"command {expected_name} argv drifted")
        require(
            row.get("cwd") == str(first_projection_candidate),
            f"command {expected_name} cwd escaped the source projection",
        )
        require(type(row.get("exitCode")) is int and row.get("exitCode") == 0, f"command {expected_name} did not exit zero")
        require(row.get("passed") is True, f"command {expected_name} did not pass")
        duration = row.get("durationSeconds")
        require(
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and math.isfinite(duration)
            and duration >= 0,
            f"command {expected_name} duration is invalid",
        )
        require(
            LOWER_SHA256_PATTERN.fullmatch(str(row.get("stdoutSha256") or "")) is not None
            and LOWER_SHA256_PATTERN.fullmatch(str(row.get("stderrSha256") or "")) is not None,
            f"command {expected_name} output digest is invalid",
        )
        require(
            row.get("stdoutTail") == OUTPUT_WITHHELD
            and row.get("stderrTail") == OUTPUT_WITHHELD,
            f"command {expected_name} retained command output",
        )

    projection = evidence.get("testSourceProjection")
    if test_source_projection.get("passed") is True:
        expected_projection = {
            "passed": True,
            "productionMutation": False,
            "closureSha256": test_source_projection["closureSha256"],
            "fileCount": test_source_projection["fileCount"],
            "totalBytes": test_source_projection["totalBytes"],
            "composePath": str(first_output / "docker-compose.public-edge.yml"),
            "fixturesRoot": str(first_output / "tests" / "fixtures"),
        }
    else:
        expected_projection = {"passed": False, "skipped": True}
    require(projection == expected_projection, "test-source projection contract is invalid")

    overlay = evidence.get("overlayIdentity")
    build_info = (
        publish_root
        / ".codex-studio"
        / "runtime"
        / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    )
    require(isinstance(overlay, dict) and overlay.get("passed") is True, "overlay identity did not pass")
    require(overlay.get("reused") is not True, "overlay identity was reused")
    require(overlay.get("path") == str(build_info), "overlay identity path drifted")
    require(
        build_info.is_file() and overlay.get("sha256") == sha256_file(build_info),
        "overlay identity bytes drifted",
    )
    rollback = evidence.get("rollbackProbe")
    rollback_closures = (
        str(rollback.get("generationAClosureSha256Before") or "")
        if isinstance(rollback, dict)
        else "",
        str(rollback.get("generationAClosureSha256AfterActivation") or "")
        if isinstance(rollback, dict)
        else "",
        str(rollback.get("generationAClosureSha256AfterRollback") or "")
        if isinstance(rollback, dict)
        else "",
    )
    require(
        isinstance(rollback, dict)
        and set(rollback)
        == {
            "passed",
            "productionMutation",
            "atomicCommitPrimitive",
            "generationA",
            "generationB",
            "observedAfterActivation",
            "observedAfterRollback",
            "observedAfterRestore",
            "generationABytesUnchanged",
            "generationAClosureSha256Before",
            "generationAClosureSha256AfterActivation",
            "generationAClosureSha256AfterRollback",
            "pointerASha256",
            "pointerBSha256",
        }
        and rollback.get("passed") is True
        and rollback.get("productionMutation") is False,
        "rollback probe top-level contract is invalid",
    )
    require(
        rollback.get("atomicCommitPrimitive")
        == "fsync temporary current.json then os.replace and parent fsync"
        and rollback.get("generationA") == "preflight-generation-a"
        and rollback.get("generationB") == "preflight-generation-b"
        and rollback.get("observedAfterActivation") == "preflight-generation-b"
        and rollback.get("observedAfterRollback") == "preflight-generation-a"
        and rollback.get("observedAfterRestore") == "preflight-generation-b"
        and rollback.get("generationABytesUnchanged") is True
        and all(LOWER_SHA256_PATTERN.fullmatch(value) for value in rollback_closures)
        and len(set(rollback_closures)) == 1
        and LOWER_SHA256_PATTERN.fullmatch(str(rollback.get("pointerASha256") or ""))
        is not None
        and LOWER_SHA256_PATTERN.fullmatch(str(rollback.get("pointerBSha256") or ""))
        is not None
        and rollback.get("pointerASha256") != rollback.get("pointerBSha256"),
        "rollback probe contract is invalid",
    )
    rollback_plan = evidence.get("rollbackPlan")
    require(
        isinstance(rollback_plan, dict)
        and rollback_plan.get("activationAuthorized") is False
        and rollback_plan.get("candidateBuildSha256") == build_closure["closureSha256"]
        and rollback_plan.get("releaseShelfPrimitive") == rollback.get("atomicCommitPrimitive")
        and rollback_plan.get("productionTargetCaptured") is False,
        "rollback plan contract is invalid",
    )
    return commands


def _resolve_without_symlink_components(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            raise PreflightError(f"{label} is missing: {current}")
        if stat.S_ISLNK(metadata.st_mode):
            raise PreflightError(f"{label} contains a symbolic-link component: {current}")
    return absolute.resolve(strict=True)


def prepare_output_root(path: Path, candidate_root: Path) -> Path:
    """Create an owner-only output root without following operator-path symlinks."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode):
            raise PreflightError(
                f"output root contains a symbolic-link component: {current}"
            )
    candidate = candidate_root.resolve(strict=True)
    if absolute == candidate or absolute.is_relative_to(candidate):
        raise PreflightError("output root must be outside the candidate source root")
    if absolute.exists() and not absolute.is_dir():
        raise PreflightError(f"output root must be a directory: {absolute}")
    if absolute.exists() and any(absolute.iterdir()):
        raise PreflightError(f"output root must be absent or empty: {absolute}")
    absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Recheck after creation so a parent symlink or concurrent leaf substitution
    # cannot silently redirect preflight writes.
    resolved = _resolve_without_symlink_components(absolute, "output root")
    if resolved != absolute:
        raise PreflightError("output root resolution changed during creation")
    os.chmod(absolute, 0o700)
    return absolute


def _iter_regular_files(
    root: Path,
    excluded_directories: frozenset[str],
) -> Iterator[tuple[str, Path]]:
    root = _resolve_without_symlink_components(root, "closure root")
    if root.is_file():
        yield root.name, root
        return
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        retained: list[str] = []
        for name in sorted(directory_names):
            child = current_path / name
            if child.is_symlink():
                raise PreflightError(f"source closure contains a symbolic link: {child}")
            if name not in excluded_directories:
                retained.append(name)
        directory_names[:] = retained
        for name in sorted(file_names):
            path = current_path / name
            if path.is_symlink():
                raise PreflightError(f"source closure contains a symbolic link: {path}")
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode):
                raise PreflightError(f"source closure entry is not a regular file: {path}")
            yield path.relative_to(root).as_posix(), path


def build_closure_manifest(
    schema: str,
    labelled_roots: Sequence[tuple[str, Path]],
    *,
    excluded_directories: Iterable[str] = DERIVED_DIRECTORIES,
) -> dict[str, Any]:
    excluded = frozenset(excluded_directories)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, root in labelled_roots:
        if not label or "/" in label or "\\" in label:
            raise PreflightError(f"closure label is unsafe: {label!r}")
        if not root.exists():
            raise PreflightError(f"closure input is missing: {root}")
        root_kind = "file" if root.is_file() else "directory"
        for relative, path in _iter_regular_files(root, excluded):
            logical = f"{label}/{relative}" if root_kind == "directory" else label
            if logical in seen:
                raise PreflightError(f"closure contains a duplicate logical path: {logical}")
            seen.add(logical)
            metadata = path.stat()
            rows.append(
                {
                    "path": logical,
                    "mode": stat.S_IMODE(metadata.st_mode),
                    "sizeBytes": metadata.st_size,
                    "sha256": sha256_file(path),
                }
            )
    rows.sort(key=lambda row: str(row["path"]))
    return {
        "schemaVersion": schema,
        "files": rows,
        "fileCount": len(rows),
        "totalBytes": sum(int(row["sizeBytes"]) for row in rows),
        "closureSha256": sha256_bytes(canonical_json_bytes(rows)),
    }


def build_topology_closure_manifest(
    schema: str,
    labelled_roots: Sequence[tuple[str, Path]],
    *,
    excluded_directories: Iterable[str] = DERIVED_DIRECTORIES,
) -> dict[str, Any]:
    """Hash regular-file bytes and the complete directory namespace/modes."""

    roots = tuple(labelled_roots)
    manifest = build_closure_manifest(
        schema,
        roots,
        excluded_directories=excluded_directories,
    )
    excluded = frozenset(excluded_directories)
    directories: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, root in roots:
        if not label or "/" in label or "\\" in label:
            raise PreflightError(f"closure label is unsafe: {label!r}")
        resolved = _resolve_without_symlink_components(root, f"topology closure root {label}")
        if not resolved.is_dir():
            continue
        for current, directory_names, _file_names in os.walk(resolved, followlinks=False):
            current_path = Path(current)
            retained: list[str] = []
            for name in sorted(directory_names):
                child = current_path / name
                if child.is_symlink():
                    raise PreflightError(f"closure contains a directory symlink: {child}")
                if name not in excluded:
                    retained.append(name)
            directory_names[:] = retained
            relative = current_path.relative_to(resolved).as_posix()
            logical = label if relative == "." else f"{label}/{relative}"
            if logical in seen:
                raise PreflightError(f"closure contains a duplicate directory: {logical}")
            seen.add(logical)
            metadata = current_path.lstat()
            if not stat.S_ISDIR(metadata.st_mode):
                raise PreflightError(f"closure topology entry is not a directory: {current_path}")
            directories.append(
                {
                    "path": logical,
                    "mode": stat.S_IMODE(metadata.st_mode),
                }
            )
    directories.sort(key=lambda row: str(row["path"]))
    manifest["directories"] = directories
    manifest["directoryCount"] = len(directories)
    manifest["closureSha256"] = sha256_bytes(
        canonical_json_bytes(
            {"files": manifest["files"], "directories": directories}
        )
    )
    return manifest


def _git_source_rows(
    label: str,
    root: Path,
    git_host: Path = Path("/usr/bin/git"),
) -> list[dict[str, Any]]:
    if not label or "/" in label or "\\" in label:
        raise PreflightError(f"closure label is unsafe: {label!r}")
    root = _resolve_without_symlink_components(root, f"Git source closure root {label}")
    completed = subprocess.run(
        git_argv(
            git_host,
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=git_environment(),
        check=False,
    )
    if completed.returncode != 0:
        raise PreflightError(
            "could not enumerate Git-visible source closure: "
            + completed.stderr.decode("utf-8", errors="replace")[-500:]
        )

    rows: list[dict[str, Any]] = []
    for encoded in completed.stdout.split(b"\0"):
        if not encoded:
            continue
        relative = encoded.decode("utf-8", errors="strict")
        logical_path = PurePosixPath(relative)
        if logical_path.is_absolute() or ".." in logical_path.parts or not logical_path.parts:
            raise PreflightError(f"Git source closure contains an unsafe path: {relative!r}")
        if any(part in DERIVED_DIRECTORIES for part in logical_path.parts):
            continue
        path = root.joinpath(*logical_path.parts)
        logical = f"{label}/{logical_path.as_posix()}"
        if not path.exists() and not path.is_symlink():
            rows.append(
                {
                    "path": logical,
                    "mode": 0,
                    "sizeBytes": 0,
                    "sha256": sha256_bytes(f"deleted:{logical}".encode("utf-8")),
                    "state": "deleted",
                }
            )
            continue
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            # Git models a symlink as source content. Hash its link text without
            # resolving or traversing it; closure roots themselves remain
            # strictly symlink-free.
            link_payload = os.fsencode(os.readlink(path))
            rows.append(
                {
                    "path": logical,
                    "mode": stat.S_IMODE(metadata.st_mode),
                    "sizeBytes": len(link_payload),
                    "sha256": sha256_bytes(link_payload),
                    "state": "symlink",
                }
            )
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise PreflightError(f"Git source closure entry is not a regular file: {path}")
        rows.append(
            {
                "path": logical,
                "mode": stat.S_IMODE(metadata.st_mode),
                "sizeBytes": metadata.st_size,
                "sha256": sha256_file(path),
                "state": "present",
            }
        )
    return rows


def build_source_closure_manifest(
    candidate_root: Path,
    external_roots: Sequence[tuple[str, Path]],
    external_git_roots: Sequence[tuple[str, Path]] = (),
    *,
    git_host: Path = Path("/usr/bin/git"),
) -> dict[str, Any]:
    rows = _git_source_rows("chummer-run-services", candidate_root, git_host)
    for label, root in external_git_roots:
        rows.extend(_git_source_rows(label, root, git_host))
    external = build_closure_manifest(SOURCE_CLOSURE_SCHEMA, external_roots)
    rows.extend(external["files"])
    rows.sort(key=lambda row: str(row["path"]))
    logical_paths = [str(row["path"]) for row in rows]
    if len(logical_paths) != len(set(logical_paths)):
        raise PreflightError("source closure contains duplicate logical paths")
    return {
        "schemaVersion": SOURCE_CLOSURE_SCHEMA,
        "files": rows,
        "fileCount": len(rows),
        "totalBytes": sum(int(row["sizeBytes"]) for row in rows),
        "closureSha256": sha256_bytes(canonical_json_bytes(rows)),
    }


def _source_projection_roots(
    projection_root: Path,
) -> tuple[Path, Path, Path, dict[str, Path]]:
    workspace = projection_root / "chummercomplete"
    candidate = workspace / "chummer.run-services"
    media = projection_root / "fleet" / "repos" / "chummer-media-factory"
    roots = {
        "chummer-run-services": candidate,
        "chummer-core-engine": workspace / "chummer-core-engine",
        "chummer-hub-registry": workspace / "chummer-hub-registry",
        "media-factory": media,
    }
    return workspace, candidate, media, roots


def _copy_projection_file(
    source: Path,
    destination: Path,
    expected: Mapping[str, Any],
) -> None:
    resolved = _resolve_without_symlink_components(source, "source projection input")
    if resolved != source.absolute():
        raise PreflightError("source projection input resolved to an unexpected path")
    expected_mode = int(expected.get("mode") or 0)
    expected_size = int(expected.get("sizeBytes") or 0)
    expected_sha256 = str(expected.get("sha256") or "")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, flags)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, raw_temp = tempfile.mkstemp(prefix=".source-projection.", dir=destination.parent)
    temp = Path(raw_temp)
    digest = hashlib.sha256()
    copied = 0
    try:
        with os.fdopen(source_fd, "rb", closefd=True) as source_handle:
            before = os.fstat(source_handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise PreflightError("source projection input is not a regular file")
            if stat.S_IMODE(before.st_mode) != expected_mode or before.st_size != expected_size:
                raise PreflightError("source projection input metadata drifted after closure")
            with os.fdopen(descriptor, "wb", closefd=True) as destination_handle:
                while True:
                    chunk = source_handle.read(1024 * 1024)
                    if not chunk:
                        break
                    destination_handle.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
            after = os.fstat(source_handle.fileno())
            if (
                stat.S_IMODE(after.st_mode) != expected_mode
                or after.st_size != expected_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
            ):
                raise PreflightError("source projection input changed while it was copied")
        if copied != expected_size or digest.hexdigest() != expected_sha256:
            raise PreflightError("source projection input bytes drifted after closure")
        os.chmod(temp, expected_mode)
        os.replace(temp, destination)
    finally:
        try:
            os.close(source_fd)
        except OSError:
            pass
        try:
            os.close(descriptor)
        except OSError:
            pass
        temp.unlink(missing_ok=True)


def _projection_manifest(
    projection_roots: Mapping[str, Path],
) -> dict[str, Any]:
    manifest = build_closure_manifest(
        SOURCE_PROJECTION_SCHEMA,
        tuple((label, projection_roots[label]) for label in sorted(projection_roots)),
        excluded_directories=(),
    )
    directories: list[dict[str, Any]] = []
    for label in sorted(projection_roots):
        root = _resolve_without_symlink_components(
            projection_roots[label],
            f"source projection directory root {label}",
        )
        for current, directory_names, _file_names in os.walk(root, followlinks=False):
            directory_names.sort()
            current_path = Path(current)
            if any((current_path / name).is_symlink() for name in directory_names):
                raise PreflightError("source projection contains a directory symlink")
            relative = current_path.relative_to(root).as_posix()
            logical = label if relative == "." else f"{label}/{relative}"
            metadata = current_path.lstat()
            directories.append(
                {
                    "path": logical,
                    "mode": stat.S_IMODE(metadata.st_mode),
                }
            )
    directories.sort(key=lambda row: str(row["path"]))
    manifest["directories"] = directories
    manifest["closureSha256"] = sha256_bytes(
        canonical_json_bytes(
            {"files": manifest["files"], "directories": directories}
        )
    )
    return manifest


def seal_tree_owner_read_only(root: Path) -> None:
    root = _resolve_without_symlink_components(root, "tree to seal read-only")
    for current, directory_names, file_names in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in file_names:
            path = current_path / name
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
                raise PreflightError(f"read-only tree contains a non-regular file: {path}")
            os.chmod(path, 0o500 if metadata.st_mode & 0o111 else 0o400)
        for name in directory_names:
            path = current_path / name
            if path.is_symlink() or not path.is_dir():
                raise PreflightError(f"read-only tree contains a directory symlink: {path}")
            os.chmod(path, 0o500)
        os.chmod(current_path, 0o500)


def owner_read_only_tree_passes(root: Path) -> bool:
    try:
        for current, directory_names, file_names in os.walk(
            root,
            topdown=True,
            followlinks=False,
        ):
            current_path = Path(current)
            if current_path.is_symlink() or stat.S_IMODE(current_path.stat().st_mode) != 0o500:
                return False
            for name in directory_names:
                path = current_path / name
                if path.is_symlink():
                    return False
            for name in file_names:
                path = current_path / name
                mode = path.lstat().st_mode
                if (
                    path.is_symlink()
                    or not stat.S_ISREG(mode)
                    or stat.S_IMODE(mode) not in {0o400, 0o500}
                ):
                    return False
        return True
    except OSError:
        return False


def materialize_runtime_build_projection(
    source_publish_root: Path,
    source_postgres_tool_root: Path,
    expected_source_closure: Mapping[str, Any],
    projection_parent: Path,
) -> RuntimeBuildProjection:
    expected_sha256 = str(expected_source_closure.get("closureSha256") or "")
    if LOWER_SHA256_PATTERN.fullmatch(expected_sha256) is None:
        raise PreflightError("runtime build projection requires one pinned build closure")
    source_before = build_output_closure(
        source_publish_root,
        source_postgres_tool_root,
    )
    if source_before != expected_source_closure:
        raise PreflightError("reused build changed before runtime projection")
    ensure_owner_only_directory(projection_parent)
    root = projection_parent / expected_sha256
    if root.exists():
        raise PreflightError(f"runtime build projection already exists: {root}")
    publish_root = root / "portal"
    postgres_tool_root = root / "postgres-tool"
    source_roots = {
        "portal": source_publish_root,
        "postgres-tool": source_postgres_tool_root,
    }
    destination_roots = {
        "portal": publish_root,
        "postgres-tool": postgres_tool_root,
    }
    root.mkdir(parents=True, mode=0o700)
    for raw in expected_source_closure.get("directories", []):
        if not isinstance(raw, dict):
            raise PreflightError("build closure contains a malformed directory row")
        logical = PurePosixPath(str(raw.get("path") or ""))
        if logical.is_absolute() or not logical.parts or ".." in logical.parts:
            raise PreflightError("build closure contains an unsafe directory path")
        label = logical.parts[0]
        if label not in destination_roots:
            raise PreflightError("build closure contains an unknown directory label")
        relative_parts = logical.parts[1:]
        destination = destination_roots[label].joinpath(*relative_parts)
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)

    independent = True
    for raw in expected_source_closure.get("files", []):
        if not isinstance(raw, dict):
            raise PreflightError("build closure contains a malformed file row")
        logical = PurePosixPath(str(raw.get("path") or ""))
        if logical.is_absolute() or len(logical.parts) < 2 or ".." in logical.parts:
            raise PreflightError("build closure contains an unsafe file path")
        label = logical.parts[0]
        if label not in source_roots:
            raise PreflightError("build closure contains an unknown file label")
        relative = Path(*logical.parts[1:])
        source = source_roots[label] / relative
        destination = destination_roots[label] / relative
        _copy_projection_file(source, destination, raw)
        source_metadata = source.stat()
        destination_metadata = destination.stat()
        independent = independent and not (
            source_metadata.st_dev == destination_metadata.st_dev
            and source_metadata.st_ino == destination_metadata.st_ino
        )
    source_after = build_output_closure(
        source_publish_root,
        source_postgres_tool_root,
    )
    if source_after != expected_source_closure:
        raise PreflightError("reused build changed while runtime projection was copied")
    unsealed = build_output_closure(publish_root, postgres_tool_root)
    expected_content = closure_content_sha256(expected_source_closure)
    if closure_content_sha256(unsealed) != expected_content or not independent:
        raise PreflightError("runtime build projection is not one independent exact copy")
    seal_tree_owner_read_only(root)
    sealed = build_output_closure(publish_root, postgres_tool_root)
    if (
        closure_content_sha256(sealed) != expected_content
        or not owner_read_only_tree_passes(root)
    ):
        raise PreflightError("runtime build projection did not retain sealed exact content")
    return RuntimeBuildProjection(
        root=root,
        publish_root=publish_root,
        postgres_tool_root=postgres_tool_root,
        source_closure_sha256=expected_sha256,
        content_sha256=expected_content,
        sealed_closure=sealed,
        independent_inodes=independent,
    )


def runtime_build_projection_receipt_evidence(
    projection: RuntimeBuildProjection,
    *,
    final_sha256: str,
    stable: bool,
    mutation_monitor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "root": str(projection.root),
        "portalRoot": str(projection.publish_root),
        "postgresToolRoot": str(projection.postgres_tool_root),
        "sourceBuildClosureSha256": projection.source_closure_sha256,
        "contentSha256": projection.content_sha256,
        "sealedClosureSha256": projection.sealed_closure["closureSha256"],
        "fileCount": projection.sealed_closure["fileCount"],
        "totalBytes": projection.sealed_closure["totalBytes"],
        "independentInodes": projection.independent_inodes,
        "ownerReadOnlyModes": owner_read_only_tree_passes(projection.root),
        "writeIsolation": CHILD_ISOLATION_CONTRACT
        + "+inotify-transient-mutation-monitor",
        "finalSha256": final_sha256,
        "stableThroughRuntime": stable,
        "transientMutationMonitor": (
            dict(mutation_monitor) if mutation_monitor is not None else None
        ),
        "transientMutationDetectionPassed": bool(
            mutation_monitor is not None and mutation_monitor.get("passed") is True
        ),
    }


def materialize_source_projection(
    source_closure: Mapping[str, Any],
    *,
    candidate_root: Path,
    workspace_root: Path,
    media_factory_root: Path,
    projection_root: Path,
) -> SourceProjection:
    if projection_root.exists():
        raise PreflightError("source projection root already exists")
    ensure_owner_only_directory(projection_root)
    projected_workspace, projected_candidate, projected_media, projected_roots = (
        _source_projection_roots(projection_root)
    )
    source_roots = {
        "chummer-run-services": candidate_root,
        "chummer-core-engine": workspace_root / "chummer-core-engine",
        "chummer-hub-registry": workspace_root / "chummer-hub-registry",
        "media-factory": media_factory_root,
    }
    for root in source_roots.values():
        _resolve_without_symlink_components(root, "source projection repository root")
    for root in projected_roots.values():
        root.mkdir(parents=True, exist_ok=False, mode=0o700)

    raw_rows = source_closure.get("files")
    if not isinstance(raw_rows, list):
        raise PreflightError("source closure has no file rows for projection")
    expected_rows: list[dict[str, Any]] = []
    omitted_symlinks: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise PreflightError("source closure contains a non-object row")
        logical = PurePosixPath(str(raw.get("path") or ""))
        if logical.is_absolute() or len(logical.parts) < 2 or ".." in logical.parts:
            raise PreflightError("source closure contains an unsafe projection path")
        label = logical.parts[0]
        if label not in source_roots or label not in projected_roots:
            raise PreflightError(f"source closure projection label is unknown: {label}")
        relative = Path(*logical.parts[1:])
        source = source_roots[label] / relative
        destination = projected_roots[label] / relative
        state = str(raw.get("state") or "")
        if state == "deleted":
            if source.exists() or source.is_symlink():
                raise PreflightError("deleted source projection input reappeared")
            continue
        if state == "symlink":
            metadata = source.lstat()
            if not stat.S_ISLNK(metadata.st_mode):
                raise PreflightError("source projection symlink row changed type")
            link_payload = os.fsencode(os.readlink(source))
            if (
                len(link_payload) != int(raw.get("sizeBytes") or 0)
                or sha256_bytes(link_payload) != str(raw.get("sha256") or "")
            ):
                raise PreflightError("source projection symlink row drifted")
            # Symlinks are deliberately not materialized. If an evaluated build
            # input depended on one, the isolated projection build fails closed
            # instead of following an ambient or absolute host path.
            omitted_symlinks.append(
                {
                    "path": logical.as_posix(),
                    "sourceLinkSha256": str(raw.get("sha256") or ""),
                }
            )
            continue
        if state != "present":
            raise PreflightError("source closure row has an unsupported state")
        _copy_projection_file(source, destination, raw)
        expected_rows.append(
            {
                "path": logical.as_posix(),
                "mode": int(raw["mode"]),
                "sizeBytes": int(raw["sizeBytes"]),
                "sha256": str(raw["sha256"]),
            }
        )

    expected_rows.sort(key=lambda row: str(row["path"]))
    unsealed_manifest = _projection_manifest(projected_roots)
    if unsealed_manifest["files"] != expected_rows:
        raise PreflightError("materialized source projection does not match pinned rows")
    seal_tree_owner_read_only(projection_root)
    manifest = _projection_manifest(projected_roots)
    if not owner_read_only_tree_passes(projection_root):
        raise PreflightError("materialized source projection is not owner-read-only")
    manifest["sourceClosureSha256"] = str(source_closure.get("closureSha256") or "")
    manifest["unsealedContentClosureSha256"] = unsealed_manifest["closureSha256"]
    manifest["omittedSymlinks"] = omitted_symlinks
    manifest["layout"] = {
        "workspaceRoot": str(projected_workspace),
        "candidateRoot": str(projected_candidate),
        "mediaFactoryRoot": str(projected_media),
    }
    return SourceProjection(
        root=projection_root,
        workspace_root=projected_workspace,
        candidate_root=projected_candidate,
        media_factory_root=projected_media,
        manifest=manifest,
        omitted_symlinks=tuple(omitted_symlinks),
    )


def source_projection_receipt_evidence(
    projection: SourceProjection,
    *,
    manifest_path: Path,
    after_build_sha256: str,
    final_sha256: str,
    stable: bool,
    mutation_monitors: Sequence[Mapping[str, Any]] = (),
    execution_reused: bool = False,
) -> dict[str, Any]:
    return {
        "path": str(manifest_path),
        "root": str(projection.root),
        "workspaceRoot": str(projection.workspace_root),
        "candidateRoot": str(projection.candidate_root),
        "mediaFactoryRoot": str(projection.media_factory_root),
        "schemaVersion": SOURCE_PROJECTION_SCHEMA,
        "sourceClosureSha256": str(
            projection.manifest.get("sourceClosureSha256") or ""
        ),
        "sha256": str(projection.manifest.get("closureSha256") or ""),
        "fileCount": int(projection.manifest.get("fileCount") or 0),
        "totalBytes": int(projection.manifest.get("totalBytes") or 0),
        "omittedSymlinks": [dict(row) for row in projection.omitted_symlinks],
        "afterBuildSha256": after_build_sha256,
        "finalSha256": final_sha256,
        "stableThroughRuntimeAndRollback": stable,
        "commandsBoundToProjection": True,
        "ownerReadOnlyModes": owner_read_only_tree_passes(projection.root),
        "childWriteIsolation": CHILD_ISOLATION_CONTRACT
        + "+inotify-transient-mutation-monitor",
        "transientMutationMonitors": [dict(row) for row in mutation_monitors],
        "transientMutationDetectionPassed": bool(
            execution_reused
            or (
                mutation_monitors
                and all(row.get("passed") is True for row in mutation_monitors)
            )
        ),
        "childExecutionMode": (
            "validated-first-pass-reuse" if execution_reused else "isolated-projection"
        ),
    }


def git_text(repo: Path, git_host: Path, *args: str) -> str:
    completed = subprocess.run(
        git_argv(git_host, *args),
        cwd=repo,
        env=git_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise PreflightError(f"git {' '.join(args)} failed for {repo}")
    return completed.stdout.strip()


def git_identity(repo: Path, git_host: Path) -> dict[str, Any]:
    status = git_text(repo, git_host, "status", "--porcelain=v1", "-z").encode("utf-8")
    return {
        "path": str(repo.resolve()),
        "head": git_text(repo, git_host, "rev-parse", "HEAD"),
        "statusSha256": sha256_bytes(status),
        "dirty": bool(status),
    }


def sanitized_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    allowed = ("HOME", "DOTNET_ROOT", "NUGET_PACKAGES", "SSL_CERT_FILE", "SSL_CERT_DIR")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.setdefault("HOME", str(Path.home()))
    environment["PATH"] = "/usr/bin:/bin"
    environment["DOTNET_NOLOGO"] = "1"
    environment["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    if extra:
        environment.update({str(key): str(value) for key, value in extra.items()})
    return environment


@contextlib.contextmanager
def transient_tree_mutation_monitor(
    roots: Sequence[Path],
    evidence: dict[str, Any],
) -> Iterator[None]:
    """Detect transient content, topology, mode, xattr/ACL, or timestamp mutation."""

    in_modify = 0x00000002
    in_attrib = 0x00000004
    in_close_write = 0x00000008
    in_moved_from = 0x00000040
    in_moved_to = 0x00000080
    in_create = 0x00000100
    in_delete = 0x00000200
    in_delete_self = 0x00000400
    in_move_self = 0x00000800
    in_q_overflow = 0x00004000
    in_ignored = 0x00008000
    watch_mask = (
        in_modify
        | in_attrib
        | in_close_write
        | in_moved_from
        | in_moved_to
        | in_create
        | in_delete
        | in_delete_self
        | in_move_self
    )
    relevant_mask = watch_mask | in_q_overflow | in_ignored
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]
    libc.inotify_init1.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    libc.inotify_add_watch.restype = ctypes.c_int
    descriptor = int(libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC))
    if descriptor < 0:
        error = ctypes.get_errno()
        raise PreflightError(f"inotify initialization failed: {os.strerror(error)}")
    stop = threading.Event()
    lock = threading.Lock()
    observed_masks: list[int] = []
    monitor_errors: list[str] = []
    watch_count = 0

    def record_available() -> None:
        while True:
            try:
                raw = os.read(descriptor, 256 * 1024)
            except BlockingIOError:
                return
            except OSError as exc:
                if stop.is_set() and exc.errno == errno.EBADF:
                    return
                with lock:
                    monitor_errors.append(str(exc))
                return
            if not raw:
                return
            offset = 0
            masks: list[int] = []
            while offset + 16 <= len(raw):
                _watch, mask, _cookie, name_length = struct.unpack_from(
                    "iIII", raw, offset
                )
                offset += 16 + int(name_length)
                if mask & relevant_mask:
                    masks.append(int(mask))
            if offset != len(raw):
                with lock:
                    monitor_errors.append("malformed inotify event stream")
                return
            if masks:
                with lock:
                    observed_masks.extend(masks)

    def consume() -> None:
        while not stop.is_set():
            try:
                readable, _, _ = select.select((descriptor,), (), (), 0.05)
            except (OSError, ValueError) as exc:
                with lock:
                    monitor_errors.append(str(exc))
                return
            if readable:
                record_available()
        record_available()

    normalized_roots: list[Path] = []
    thread: threading.Thread | None = None
    try:
        for root in roots:
            resolved = _resolve_without_symlink_components(root, "mutation monitor root")
            normalized_roots.append(resolved)
            watch_paths: list[Path] = []
            if resolved.is_file():
                watch_paths.append(resolved)
            elif not resolved.is_dir():
                raise PreflightError(f"mutation monitor root is not file/directory: {resolved}")
            for current, directory_names, _file_names in os.walk(resolved, followlinks=False):
                directory_names.sort()
                current_path = Path(current)
                if any((current_path / name).is_symlink() for name in directory_names):
                    raise PreflightError("mutation monitor root contains a directory symlink")
                watch_paths.append(current_path)
            for current_path in watch_paths:
                watch = int(
                    libc.inotify_add_watch(
                        descriptor,
                        os.fsencode(current_path),
                        watch_mask,
                    )
                )
                if watch < 0:
                    error = ctypes.get_errno()
                    raise PreflightError(
                        f"inotify watch failed for {current_path}: {os.strerror(error)}"
                    )
                watch_count += 1
        thread = threading.Thread(target=consume, name="cwpf-mutation-monitor", daemon=True)
        thread.start()
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=2)
        record_available()
        os.close(descriptor)
        with lock:
            event_count = len(observed_masks)
            queue_overflow = any(mask & in_q_overflow for mask in observed_masks)
            errors = tuple(monitor_errors)
        evidence.update(
            {
                "roots": [str(path) for path in normalized_roots],
                "watchCount": watch_count,
                "mutationEventCount": event_count,
                "queueOverflow": queue_overflow,
                "monitorErrors": list(errors),
                "passed": bool(
                    normalized_roots
                    and watch_count > 0
                    and event_count == 0
                    and not queue_overflow
                    and not errors
                    and (thread is None or not thread.is_alive())
                ),
            }
        )


def production_loopback_origin_settings() -> dict[str, str]:
    """Keep the public origin production-valid while the listener stays loopback-only."""
    return {
        "CHUMMER_PUBLIC_CANONICAL_ORIGIN": "https://chummer.run",
        "CHUMMER_PUBLIC_ALLOWED_HOSTS": "chummer.run;127.0.0.1",
    }


def _safe_tail(value: bytes, maximum: int = 4000) -> str:
    text = value[-maximum:].decode("utf-8", errors="replace")
    # The preflight never supplies secrets, but avoid reflecting common credential
    # headers if a dependency emits an ambient diagnostic unexpectedly.
    sanitized: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(
            token in lowered
            for token in (
                "authorization:",
                "bearer ",
                "client_secret",
                "api_key",
                "password=",
                "pwd=",
                "connection string",
            )
        ):
            sanitized.append("[credential-bearing diagnostic redacted]")
        else:
            sanitized.append(line)
    return "\n".join(sanitized)


def ensure_owner_only_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise PreflightError(f"owner-only directory is invalid: {path}")
    os.chmod(path, 0o700)


def write_owner_only_file(path: Path, payload: bytes) -> None:
    if not payload:
        raise PreflightError(f"owner-only file must not be empty: {path}")
    ensure_owner_only_directory(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def owner_only_file_passes(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and not path.is_symlink()
        and metadata.st_nlink == 1
        and stat.S_IMODE(metadata.st_mode) == 0o600
        and metadata.st_size > 0
    )


def _run_provisioning_command(
    name: str,
    argv: Sequence[str],
    *,
    cwd: Path,
    evidence: list[dict[str, Any]],
    timeout_seconds: int = 120,
    environment: Mapping[str, str] | None = None,
    stdin_payload: bytes | None = None,
    suppress_receipt_output: bool = False,
) -> bytes:
    if not argv or not Path(argv[0]).is_absolute():
        raise PreflightError(f"provisioning command {name} must use an absolute executable")
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=sanitized_environment(environment),
            input=stdin_payload,
            stdin=subprocess.DEVNULL if stdin_payload is None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = (exc.stderr or b"") + b"\nprovisioning command timed out\n"
        exit_code = 124
    stdout_tail = (
        "[output suppressed for credential-bearing command]"
        if suppress_receipt_output
        else "[output suppressed for stdin-bearing command]"
        if stdin_payload is not None
        else _safe_tail(stdout, maximum=1000)
    )
    stderr_tail = (
        "[output suppressed for credential-bearing command]"
        if suppress_receipt_output
        else "[output suppressed for stdin-bearing command]"
        if stdin_payload is not None
        else _safe_tail(stderr, maximum=1000)
    )
    evidence.append(
        {
            "name": name,
            "executable": Path(argv[0]).name if argv else "",
            "argvSha256": sha256_bytes(canonical_json_bytes(list(argv))),
            "exitCode": exit_code,
            "passed": exit_code == 0,
            "durationSeconds": round(time.monotonic() - started, 3),
            "stdoutSha256": sha256_bytes(stdout),
            "stderrSha256": sha256_bytes(stderr),
            "stdoutTail": stdout_tail,
            "stderrTail": stderr_tail,
            "stdinSupplied": stdin_payload is not None,
            "stdinBytes": len(stdin_payload) if stdin_payload is not None else 0,
            "receiptOutputWithheld": suppress_receipt_output,
        }
    )
    if exit_code != 0:
        raise PreflightError(f"hermetic provisioning command failed: {name}")
    return stdout


def _secure_remove_tree(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        for current, _, file_names in os.walk(path, topdown=False, followlinks=False):
            for file_name in file_names:
                candidate = Path(current) / file_name
                try:
                    metadata = candidate.lstat()
                    if stat.S_ISREG(metadata.st_mode) and metadata.st_size <= 4 * 1024 * 1024:
                        with candidate.open("r+b", buffering=0) as handle:
                            remaining = metadata.st_size
                            zeros = b"\0" * min(64 * 1024, max(1, remaining))
                            while remaining > 0:
                                chunk = zeros[: min(len(zeros), remaining)]
                                handle.write(chunk)
                                remaining -= len(chunk)
                            handle.flush()
                            os.fsync(handle.fileno())
                except OSError:
                    pass
        shutil.rmtree(path)
        return not path.exists()
    except OSError:
        return False


def generate_runtime_tls_material(
    secret_root: Path,
    evidence: list[dict[str, Any]],
    openssl_host: Path,
) -> RuntimeTlsMaterial:
    ensure_owner_only_directory(secret_root)
    tls_root = secret_root / "https"
    data_protection_root = secret_root / "data-protection"
    ensure_owner_only_directory(tls_root)
    ensure_owner_only_directory(data_protection_root)

    ca_key = tls_root / "ca.key"
    ca_certificate = tls_root / "ca.crt"
    server_key = tls_root / "server.key"
    server_request = tls_root / "server.csr"
    server_certificate = tls_root / "server.crt"
    extensions = tls_root / "server.ext"
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=IP:127.0.0.1,DNS:localhost,DNS:chummer.run\n",
        encoding="ascii",
    )
    os.chmod(extensions, 0o600)
    _run_provisioning_command(
        "https-ca",
        (
            str(openssl_host), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(ca_key), "-out", str(ca_certificate), "-days", "2",
            "-subj", "/CN=Chummer Canonical Writer Preflight CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        ),
        cwd=secret_root,
        evidence=evidence,
    )
    _run_provisioning_command(
        "https-server-request",
        (
            str(openssl_host), "req", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(server_key), "-out", str(server_request),
            "-subj", "/CN=127.0.0.1",
        ),
        cwd=secret_root,
        evidence=evidence,
    )
    _run_provisioning_command(
        "https-server-certificate",
        (
            str(openssl_host), "x509", "-req", "-in", str(server_request),
            "-CA", str(ca_certificate), "-CAkey", str(ca_key), "-CAcreateserial",
            "-out", str(server_certificate), "-days", "2", "-sha256",
            "-extfile", str(extensions),
        ),
        cwd=secret_root,
        evidence=evidence,
    )
    os.chmod(ca_key, 0o600)
    os.chmod(server_key, 0o600)
    os.chmod(ca_certificate, 0o644)
    os.chmod(server_certificate, 0o644)

    protection_key = data_protection_root / "certificate.key"
    protection_certificate_pem = data_protection_root / "certificate.crt"
    protection_certificate = data_protection_root / "certificate.pfx"
    protection_password = data_protection_root / "certificate-password"
    write_owner_only_file(protection_password, (secrets.token_hex(32) + "\n").encode("ascii"))
    _run_provisioning_command(
        "data-protection-certificate",
        (
            str(openssl_host), "req", "-x509", "-newkey", "rsa:3072", "-nodes",
            "-keyout", str(protection_key), "-out", str(protection_certificate_pem),
            "-days", str(DATA_PROTECTION_CERTIFICATE_DAYS),
            "-subj", "/CN=Chummer Canonical Writer Preflight Data Protection",
            "-addext", "basicConstraints=critical,CA:FALSE",
            "-addext", "keyUsage=critical,keyEncipherment,dataEncipherment",
        ),
        cwd=secret_root,
        evidence=evidence,
    )
    _run_provisioning_command(
        "data-protection-pfx",
        (
            str(openssl_host), "pkcs12", "-export", "-out", str(protection_certificate),
            "-inkey", str(protection_key), "-in", str(protection_certificate_pem),
            "-passout", f"file:{protection_password}",
        ),
        cwd=secret_root,
        evidence=evidence,
    )
    for owner_secret in (
        protection_key,
        protection_certificate_pem,
        protection_certificate,
        protection_password,
    ):
        os.chmod(owner_secret, 0o600)
    if not all(
        owner_only_file_passes(path)
        for path in (protection_certificate, protection_password, server_key, ca_key)
    ):
        raise PreflightError("runtime certificate material is not owner-only")
    return RuntimeTlsMaterial(
        ca_certificate=ca_certificate,
        server_certificate=server_certificate,
        server_key=server_key,
        data_protection_certificate=protection_certificate,
        data_protection_password_file=protection_password,
    )


def _cleanup_provisioning_command(
    name: str,
    argv: Sequence[str],
    *,
    cwd: Path,
    evidence: list[dict[str, Any]],
) -> bool:
    try:
        _run_provisioning_command(
            name,
            argv,
            cwd=cwd,
            evidence=evidence,
            timeout_seconds=30,
        )
        return True
    except PreflightError:
        return False


def _docker_owner_label(owner: str) -> str:
    if not SECRET_TOKEN_PATTERN.fullmatch(owner):
        raise PreflightError("Docker resource owner token is invalid")
    return f"{DOCKER_OWNER_LABEL}={owner}"


def _docker_resource_present(
    kind: str,
    name: str,
    *,
    docker_host: Path,
    cwd: Path,
    evidence: list[dict[str, Any]],
    phase: str,
) -> bool:
    if kind == "container":
        argv = docker_argv(
            docker_host, "container", "ls", "--all",
            "--filter", f"name={name}", "--format", "{{.Names}}",
        )
    elif kind == "network":
        argv = docker_argv(
            docker_host, "network", "ls",
            "--filter", f"name={name}", "--format", "{{.Name}}",
        )
    elif kind == "volume":
        argv = docker_argv(
            docker_host, "volume", "ls",
            "--filter", f"name={name}", "--format", "{{.Name}}",
        )
    else:
        raise PreflightError(f"unsupported Docker resource kind: {kind}")
    output = _run_provisioning_command(
        f"{phase}-{kind}-presence",
        argv,
        cwd=cwd,
        evidence=evidence,
        timeout_seconds=30,
    ).decode("utf-8", errors="strict")
    return name in {line.strip() for line in output.splitlines() if line.strip()}


def _docker_resource_absent_stably(
    kind: str,
    name: str,
    *,
    docker_host: Path,
    cwd: Path,
    evidence: list[dict[str, Any]],
    phase: str,
) -> bool:
    for attempt in range(5):
        if _docker_resource_present(
            kind,
            name,
            docker_host=docker_host,
            cwd=cwd,
            evidence=evidence,
            phase=f"{phase}-{attempt + 1}",
        ):
            return False
        if attempt < 4:
            time.sleep(0.25)
    return True


def _docker_resource_owner(
    kind: str,
    name: str,
    *,
    docker_host: Path,
    cwd: Path,
    evidence: list[dict[str, Any]],
) -> str:
    label_path = ".Config.Labels" if kind == "container" else ".Labels"
    return _run_provisioning_command(
        f"cleanup-{kind}-owner",
        docker_argv(
            docker_host, kind, "inspect", "--format",
            f'{{{{ index {label_path} "{DOCKER_OWNER_LABEL}" }}}}',
            name,
        ),
        cwd=cwd,
        evidence=evidence,
        timeout_seconds=30,
    ).decode("utf-8", errors="strict").strip()


def _cleanup_owned_docker_resource(
    kind: str,
    name: str,
    owner: str,
    *,
    docker_host: Path,
    cwd: Path,
    evidence: list[dict[str, Any]],
) -> bool:
    try:
        if _docker_resource_absent_stably(
            kind,
            name,
            docker_host=docker_host,
            cwd=cwd,
            evidence=evidence,
            phase="cleanup-before",
        ):
            return True
        if _docker_resource_owner(
            kind,
            name,
            docker_host=docker_host,
            cwd=cwd,
            evidence=evidence,
        ) != owner:
            return False
        remove_argv: tuple[str, ...]
        if kind == "container":
            remove_argv = docker_argv(
                docker_host, "container", "rm", "--force", name
            )
        else:
            remove_argv = docker_argv(docker_host, kind, "rm", name)
        if not _cleanup_provisioning_command(
            f"cleanup-{kind}-remove",
            remove_argv,
            cwd=cwd,
            evidence=evidence,
        ):
            return False
        return _docker_resource_absent_stably(
            kind,
            name,
            docker_host=docker_host,
            cwd=cwd,
            evidence=evidence,
            phase="cleanup-after",
        )
    except PreflightError:
        return False


def _postgres_connection_string(
    *,
    port: int,
    username: str,
    password: str,
    ca_certificate: Path,
) -> str:
    if not 1 <= port <= 65535:
        raise PreflightError("isolated PostgreSQL loopback port is invalid")
    if not RUNTIME_ROLE_PATTERN.fullmatch(username):
        raise PreflightError("isolated PostgreSQL role is invalid")
    if not SECRET_TOKEN_PATTERN.fullmatch(password):
        raise PreflightError("isolated PostgreSQL credential shape is invalid")
    certificate = _resolve_without_symlink_components(
        ca_certificate,
        "isolated PostgreSQL CA certificate",
    )
    if not certificate.is_file() or not stat.S_ISREG(certificate.stat().st_mode):
        raise PreflightError("isolated PostgreSQL CA certificate must be a regular file")
    certificate_value = os.fspath(certificate)
    if not POSTGRES_CONNECTION_PATH_PATTERN.fullmatch(certificate_value):
        raise PreflightError(
            "isolated PostgreSQL CA certificate path contains connection-string metacharacters"
        )
    return (
        f"Host=127.0.0.1;Port={port};Database=chummer_preflight;"
        f"Username={username};Password={password};SSL Mode=VerifyFull;"
        f"Root Certificate={certificate_value};Trust Server Certificate=false;"
        "Pooling=false"
    )


def _decode_docker_inspect_json(payload: bytes, label: str) -> Any:
    try:
        return json.loads(payload.decode("utf-8", errors="strict").strip())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"{label} did not return exact JSON") from exc


def _postgres_hba_contract_evidence(value: Any) -> dict[str, Any]:
    expected_rules = [
        {
            "ruleNumber": 1,
            "type": "local",
            "database": ["all"],
            "user": ["all"],
            "address": None,
            "netmask": None,
            "authMethod": "trust",
            "options": None,
            "error": None,
        },
        {
            "ruleNumber": 2,
            "type": "hostssl",
            "database": ["all"],
            "user": ["all"],
            "address": "0.0.0.0",
            "netmask": "0.0.0.0",
            "authMethod": "scram-sha-256",
            "options": None,
            "error": None,
        },
        {
            "ruleNumber": 3,
            "type": "hostssl",
            "database": ["all"],
            "user": ["all"],
            "address": "::",
            "netmask": "::",
            "authMethod": "scram-sha-256",
            "options": None,
            "error": None,
        },
        {
            "ruleNumber": 4,
            "type": "hostnossl",
            "database": ["all"],
            "user": ["all"],
            "address": "0.0.0.0",
            "netmask": "0.0.0.0",
            "authMethod": "reject",
            "options": None,
            "error": None,
        },
        {
            "ruleNumber": 5,
            "type": "hostnossl",
            "database": ["all"],
            "user": ["all"],
            "address": "::",
            "netmask": "::",
            "authMethod": "reject",
            "options": None,
            "error": None,
        },
    ]
    exact_document = isinstance(value, dict) and set(value) == {
        "ssl",
        "hbaFile",
        "rules",
    }
    rules = value.get("rules") if isinstance(value, dict) else None
    rules_exact = isinstance(rules, list) and rules == expected_rules
    evidence = {
        "serverSslEnabled": isinstance(value, dict) and value.get("ssl") == "on",
        "serverSettingBound": (
            isinstance(value, dict) and value.get("hbaFile") == POSTGRES_HBA_PATH
        ),
        "fileRulesExact": rules_exact,
        "hostSslRequired": rules_exact,
        "hostNoSslRejected": rules_exact,
        "parseErrorsAbsent": rules_exact,
        "ruleCount": len(rules) if isinstance(rules, list) else 0,
    }
    evidence["passed"] = bool(exact_document and all(
        evidence[key]
        for key in (
            "serverSslEnabled",
            "serverSettingBound",
            "fileRulesExact",
            "hostSslRequired",
            "hostNoSslRejected",
            "parseErrorsAbsent",
        )
    ))
    return evidence


def _postgres_transport_proof_evidence(
    value: Any,
    *,
    accepted_before: int,
    accepted_after: int,
) -> dict[str, Any]:
    expected = {
        "contractName": "chummer.postgres_transport_proof.v1",
        "authenticated": True,
        "pgStatSsl": True,
        "plaintextAttempted": True,
        "plaintextRejected": True,
        "plaintextSqlState": "28000",
        "gssEncryptionDisabled": True,
    }
    exact = isinstance(value, dict) and value == expected
    connection_delta = accepted_after - accepted_before
    evidence = {
        **expected,
        "exactToolContract": exact,
        "viaLoopbackForwarder": connection_delta >= 2,
        "acceptedConnectionsBefore": accepted_before,
        "acceptedConnectionsAfter": accepted_after,
        "acceptedConnectionsDelta": connection_delta,
        "outputWithheld": True,
    }
    evidence["passed"] = bool(exact and evidence["viaLoopbackForwarder"])
    return evidence


def _validated_internal_container_ipv4(
    networks: Any,
    expected_network_name: str,
) -> str:
    if not isinstance(networks, dict) or set(networks) != {expected_network_name}:
        raise PreflightError(
            "isolated PostgreSQL must be attached only to its owned internal network"
        )
    network = networks.get(expected_network_name)
    if not isinstance(network, dict):
        raise PreflightError("isolated PostgreSQL internal network attachment is invalid")
    raw_address = str(network.get("IPAddress") or "").strip()
    try:
        address = ipaddress.ip_address(raw_address)
    except ValueError as exc:
        raise PreflightError(
            "isolated PostgreSQL internal network address is invalid"
        ) from exc
    if not isinstance(address, ipaddress.IPv4Address) or not any(
        address in network_range for network_range in RFC1918_NETWORKS
    ):
        raise PreflightError(
            "isolated PostgreSQL must have an RFC1918 IPv4 address on its internal network"
        )
    return str(address)


def _docker_ports_are_unpublished(host_bindings: Any, network_ports: Any) -> bool:
    if host_bindings not in (None, {}):
        return False
    if network_ports is None:
        return True
    return isinstance(network_ports, dict) and all(
        binding is None for binding in network_ports.values()
    )


@contextlib.contextmanager
def loopback_tcp_forwarder(
    *,
    target_host: str,
    target_port: int,
    evidence: dict[str, Any],
) -> Iterator[int]:
    """Forward opaque TCP bytes from one ephemeral loopback listener.

    Docker 29 suppresses published ports for containers attached only to an
    internal network. Keeping PostgreSQL on that sole internal network is the
    egress boundary; this host-local forwarder supplies the loopback endpoint
    without weakening that boundary or terminating PostgreSQL TLS.
    """

    try:
        target_address = ipaddress.ip_address(target_host)
    except ValueError as exc:
        raise PreflightError("loopback forwarder target address is invalid") from exc
    if not isinstance(target_address, ipaddress.IPv4Address) or not any(
        target_address in network_range for network_range in RFC1918_NETWORKS
    ):
        raise PreflightError("loopback forwarder target must be an RFC1918 IPv4 address")
    if not 1 <= target_port <= 65535:
        raise PreflightError("loopback forwarder target port is invalid")

    stop = threading.Event()
    lock = threading.Lock()
    workers: list[threading.Thread] = []
    active_sockets: set[socket.socket] = set()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.settimeout(0.2)
    evidence.update(
        {
            "started": False,
            "listenerLoopbackOnly": False,
            "targetAddress": str(target_address),
            "targetPort": target_port,
            "tlsTerminated": False,
            "acceptedConnections": 0,
            "upstreamConnectionFailures": 0,
            "rejectedConnections": 0,
            "idleTimeouts": 0,
            "prunedWorkers": 0,
            "maximumConcurrentWorkers": 0,
            "connectionLimit": POSTGRES_FORWARDER_MAX_CONNECTIONS,
            "idleTimeoutSeconds": POSTGRES_FORWARDER_IDLE_TIMEOUT_SECONDS,
            "cleanupPassed": False,
        }
    )

    def close_socket(handle: socket.socket) -> None:
        try:
            handle.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            handle.close()
        except OSError:
            pass

    def forward_connection(client: socket.socket) -> None:
        upstream: socket.socket | None = None
        try:
            upstream = socket.create_connection(
                (str(target_address), target_port),
                timeout=5,
            )
            upstream.settimeout(None)
            client.settimeout(None)
            with lock:
                active_sockets.update((client, upstream))
                evidence["acceptedConnections"] += 1
            peers = {client: upstream, upstream: client}
            last_activity = time.monotonic()
            while not stop.is_set():
                try:
                    readable, _, _ = select.select(tuple(peers), (), (), 0.2)
                except (OSError, ValueError):
                    return
                if not readable:
                    if (
                        time.monotonic() - last_activity
                        >= POSTGRES_FORWARDER_IDLE_TIMEOUT_SECONDS
                    ):
                        with lock:
                            evidence["idleTimeouts"] += 1
                        return
                    continue
                for source in readable:
                    try:
                        payload = source.recv(64 * 1024)
                    except OSError:
                        return
                    if not payload:
                        return
                    last_activity = time.monotonic()
                    try:
                        peers[source].sendall(payload)
                    except OSError:
                        return
        except OSError:
            with lock:
                evidence["upstreamConnectionFailures"] += 1
        finally:
            with lock:
                active_sockets.discard(client)
                if upstream is not None:
                    active_sockets.discard(upstream)
            close_socket(client)
            if upstream is not None:
                close_socket(upstream)

    def accept_connections() -> None:
        while not stop.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            worker = threading.Thread(
                target=forward_connection,
                args=(client,),
                name="chummer-cwpf-postgres-forwarder-connection",
                daemon=True,
            )
            with lock:
                live_workers = [candidate for candidate in workers if candidate.is_alive()]
                evidence["prunedWorkers"] += len(workers) - len(live_workers)
                workers[:] = live_workers
                if len(workers) >= POSTGRES_FORWARDER_MAX_CONNECTIONS:
                    evidence["rejectedConnections"] += 1
                    rejected = True
                else:
                    workers.append(worker)
                    evidence["maximumConcurrentWorkers"] = max(
                        int(evidence["maximumConcurrentWorkers"]),
                        len(workers),
                    )
                    rejected = False
            if rejected:
                close_socket(client)
                continue
            worker.start()

    accept_thread: threading.Thread | None = None
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(POSTGRES_FORWARDER_MAX_CONNECTIONS)
        bound_host, bound_port = listener.getsockname()
        if bound_host != "127.0.0.1" or not 1 <= int(bound_port) <= 65535:
            raise PreflightError("PostgreSQL forwarder did not bind exact IPv4 loopback")
        accept_thread = threading.Thread(
            target=accept_connections,
            name="chummer-cwpf-postgres-forwarder-listener",
            daemon=True,
        )
        accept_thread.start()
        evidence["started"] = True
        evidence["listenerLoopbackOnly"] = True
        evidence["hostPort"] = int(bound_port)
        yield int(bound_port)
    finally:
        stop.set()
        close_socket(listener)
        if accept_thread is not None:
            accept_thread.join(timeout=2)
        with lock:
            active_snapshot = tuple(active_sockets)
        for handle in active_snapshot:
            close_socket(handle)
        deadline = time.monotonic() + 6
        while True:
            with lock:
                worker_snapshot = tuple(workers)
            for worker in worker_snapshot:
                worker.join(timeout=max(0.0, deadline - time.monotonic()))
            with lock:
                remaining = tuple(worker for worker in workers if worker.is_alive())
                active_remaining = len(active_sockets)
            if not remaining or time.monotonic() >= deadline:
                break
        evidence["cleanupPassed"] = bool(
            (accept_thread is None or not accept_thread.is_alive())
            and not remaining
            and active_remaining == 0
            and listener.fileno() == -1
        )
        evidence["passed"] = bool(
            evidence["started"]
            and evidence["listenerLoopbackOnly"]
            and evidence["tlsTerminated"] is False
            and evidence["upstreamConnectionFailures"] == 0
            and evidence["rejectedConnections"] == 0
            and evidence["idleTimeouts"] == 0
            and evidence["cleanupPassed"]
        )


@contextlib.contextmanager
def isolated_postgres_authority(
    *,
    secret_root: Path,
    tls: RuntimeTlsMaterial,
    postgres_tool_root: Path,
    work_root: Path,
    evidence: dict[str, Any],
    expected_image_id: str,
    dotnet_execution: DotnetExecution,
    docker_host: Path,
) -> Iterator[PostgresRuntimeAuthority]:
    """Provision one exact-image, loopback-only PostgreSQL 17 authority.

    All credentials enter Docker through an owner-only env file or command stdin.
    The receipt retains command digests and non-secret readiness facts only.
    """

    commands: list[dict[str, Any]] = []
    cleanup_commands: list[dict[str, Any]] = []
    evidence.update(
        {
            "passed": False,
            "productionMutation": False,
            "imageReference": POSTGRES_IMAGE,
            "expectedImageId": expected_image_id,
            "imageIdMatchesOperatorPin": False,
            "networkInternal": False,
            "containerAttachedOnlyToInternalNetwork": False,
            "dockerPortPublishingDisabled": False,
            "listenerLoopbackOnly": False,
            "schemaVersion": None,
            "runtimePrivilegesValidated": False,
            "commands": commands,
            "cleanupCommands": cleanup_commands,
            "cleanupPassed": False,
        }
    )
    ensure_owner_only_directory(secret_root)
    ensure_owner_only_directory(work_root)
    postgres_secrets = secret_root / "postgres"
    ensure_owner_only_directory(postgres_secrets)
    expected_image_id = require_postgres_image_id(expected_image_id)
    suffix = secrets.token_hex(16)
    owner = secrets.token_hex(32)
    owner_label = _docker_owner_label(owner)
    container_name = f"chummer-cwpf-pg-{suffix}"
    copy_container_name = f"chummer-cwpf-pg-tls-{suffix}"
    network_name = f"chummer-cwpf-net-{suffix}"
    data_volume = f"chummer-cwpf-pgdata-{suffix}"
    tls_volume = f"chummer-cwpf-pgtls-{suffix}"
    image_id = ""
    authority: PostgresRuntimeAuthority | None = None
    forwarder_evidence: dict[str, Any] = {}
    evidence["loopbackForwarder"] = forwarder_evidence
    forwarder_stack = contextlib.ExitStack()
    try:
        raw_image_id = _run_provisioning_command(
            "postgres-image-inspect",
            docker_argv(
                docker_host, "image", "inspect", "--format", "{{.Id}}", POSTGRES_IMAGE
            ),
            cwd=work_root,
            evidence=commands,
        ).decode("ascii", errors="strict").strip()
        if not POSTGRES_IMAGE_ID_PATTERN.fullmatch(raw_image_id):
            raise PreflightError("cached PostgreSQL image does not expose an exact image ID")
        if raw_image_id != expected_image_id:
            raise PreflightError("cached PostgreSQL image ID does not match the operator pin")
        image_id = raw_image_id
        evidence["imageId"] = image_id
        evidence["imageIdMatchesOperatorPin"] = True

        _run_provisioning_command(
            "postgres-network-create",
            docker_argv(
                docker_host, "network", "create", "--internal",
                "--label", owner_label, network_name,
            ),
            cwd=work_root,
            evidence=commands,
        )
        network_is_internal = _decode_docker_inspect_json(
            _run_provisioning_command(
                "postgres-network-internal-inspect",
                docker_argv(
                    docker_host, "network", "inspect", "--format", "{{json .Internal}}",
                    network_name,
                ),
                cwd=work_root,
                evidence=commands,
            ),
            "owned PostgreSQL network inspection",
        )
        if network_is_internal is not True:
            raise PreflightError("owned PostgreSQL network is not internal")
        evidence["networkInternal"] = True
        for name, volume in (("postgres-data-volume-create", data_volume), ("postgres-tls-volume-create", tls_volume)):
            _run_provisioning_command(
                name,
                docker_argv(
                    docker_host, "volume", "create", "--label", owner_label, volume
                ),
                cwd=work_root,
                evidence=commands,
            )

        _run_provisioning_command(
            "postgres-tls-volume-populate",
            docker_argv(
                docker_host, "run", "--rm", "--interactive", "--pull", "never",
                "--name", copy_container_name,
                "--label", owner_label,
                "--network", "none",
                "--user", "0",
                "--volume", f"{tls_volume}:/tls",
                "--volume", f"{tls.ca_certificate.parent}:/source:ro",
                image_id,
                "sh", "-ec",
                "cat > /tls/pg_hba.conf; "
                "cp /source/server.crt /source/server.key /source/ca.crt /tls/; "
                "chown postgres:postgres /tls/server.crt /tls/server.key /tls/ca.crt "
                "/tls/pg_hba.conf; "
                "chmod 0600 /tls/server.key /tls/pg_hba.conf; "
                "chmod 0644 /tls/server.crt /tls/ca.crt",
            ),
            cwd=work_root,
            evidence=commands,
            stdin_payload=POSTGRES_HBA_BYTES,
        )

        admin_password = secrets.token_hex(32)
        runtime_password = secrets.token_hex(32)
        runtime_role = f"cwpf_runtime_{suffix}"
        admin_password_file = postgres_secrets / "container-password"
        admin_env_file = postgres_secrets / "container.env"
        write_owner_only_file(
            admin_password_file,
            (admin_password + "\n").encode("ascii"),
        )
        write_owner_only_file(
            admin_env_file,
            (
                "POSTGRES_USER=cwpf_admin\n"
                "POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password\n"
                "POSTGRES_DB=chummer_preflight\n"
                "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256\n"
            ).encode("ascii"),
        )
        if not owner_only_file_passes(admin_env_file) or not owner_only_file_passes(
            admin_password_file
        ):
            raise PreflightError("isolated PostgreSQL container credential files are not owner-only")

        _run_provisioning_command(
            "postgres-container-start",
            docker_argv(
                docker_host, "run", "--detach", "--pull", "never",
                "--name", container_name,
                "--label", owner_label,
                "--network", network_name,
                "--env-file", str(admin_env_file),
                "--volume", f"{admin_password_file}:/run/secrets/postgres-password:ro",
                "--volume", f"{data_volume}:/var/lib/postgresql/data",
                "--volume", f"{tls_volume}:/tls:ro",
                image_id,
                "postgres",
                "-c", "ssl=on",
                "-c", "ssl_cert_file=/tls/server.crt",
                "-c", "ssl_key_file=/tls/server.key",
                "-c", "ssl_ca_file=/tls/ca.crt",
                "-c", f"hba_file={POSTGRES_HBA_PATH}",
                "-c", "ssl_min_protocol_version=TLSv1.2",
                "-c", "password_encryption=scram-sha-256",
            ),
            cwd=work_root,
            evidence=commands,
        )
        readiness_started = time.monotonic()
        readiness_attempts = 0
        while time.monotonic() - readiness_started < 60:
            readiness_attempts += 1
            completed = subprocess.run(
                docker_argv(
                    docker_host, "exec", "--user", "postgres", container_name,
                    "pg_isready", "--host", "127.0.0.1",
                    "--username", "cwpf_admin", "--dbname", "chummer_preflight",
                ),
                cwd=work_root,
                env=sanitized_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
            if completed.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise PreflightError("isolated PostgreSQL did not become ready before deadline")
        evidence["readinessAttempts"] = readiness_attempts
        evidence["readinessDurationSeconds"] = round(time.monotonic() - readiness_started, 3)

        hba_output = _run_provisioning_command(
            "postgres-hba-contract",
            docker_argv(
                docker_host, "exec", "--user", "postgres", container_name,
                "psql", "--username", "cwpf_admin", "--dbname", "chummer_preflight",
                "--no-psqlrc", "--tuples-only", "--no-align",
                "--set", "ON_ERROR_STOP=1",
                "--command", POSTGRES_HBA_INSPECTION_SQL,
            ),
            cwd=work_root,
            evidence=commands,
        )
        hba_document = _decode_docker_inspect_json(
            hba_output,
            "isolated PostgreSQL HBA contract",
        )
        hba_evidence = _postgres_hba_contract_evidence(hba_document)
        evidence["hba"] = hba_evidence
        if not hba_evidence["passed"]:
            raise PreflightError("isolated PostgreSQL HBA contract is not exact TLS-only authority")

        container_networks = _decode_docker_inspect_json(
            _run_provisioning_command(
                "postgres-container-networks-inspect",
                docker_argv(
                    docker_host, "container", "inspect", "--format",
                    "{{json .NetworkSettings.Networks}}", container_name,
                ),
                cwd=work_root,
                evidence=commands,
            ),
            "isolated PostgreSQL network inspection",
        )
        target_host = _validated_internal_container_ipv4(
            container_networks,
            network_name,
        )
        evidence["containerAttachedOnlyToInternalNetwork"] = True

        host_bindings = _decode_docker_inspect_json(
            _run_provisioning_command(
                "postgres-container-host-bindings-inspect",
                docker_argv(
                    docker_host, "container", "inspect", "--format",
                    "{{json .HostConfig.PortBindings}}", container_name,
                ),
                cwd=work_root,
                evidence=commands,
            ),
            "isolated PostgreSQL host port binding inspection",
        )
        network_ports = _decode_docker_inspect_json(
            _run_provisioning_command(
                "postgres-container-network-ports-inspect",
                docker_argv(
                    docker_host, "container", "inspect", "--format",
                    "{{json .NetworkSettings.Ports}}", container_name,
                ),
                cwd=work_root,
                evidence=commands,
            ),
            "isolated PostgreSQL network port inspection",
        )
        if not _docker_ports_are_unpublished(host_bindings, network_ports):
            raise PreflightError("isolated PostgreSQL unexpectedly published a Docker port")
        evidence["dockerPortPublishingDisabled"] = True

        host_port = forwarder_stack.enter_context(
            loopback_tcp_forwarder(
                target_host=target_host,
                target_port=5432,
                evidence=forwarder_evidence,
            )
        )
        evidence["listenerLoopbackOnly"] = bool(
            forwarder_evidence.get("listenerLoopbackOnly")
        )

        bootstrap_sql = (
            "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n"
            f"CREATE ROLE {runtime_role} LOGIN PASSWORD '{runtime_password}';\n"
        ).encode("ascii")
        _run_provisioning_command(
            "postgres-bootstrap-authority-role",
            docker_argv(
                docker_host, "exec", "--interactive", "--user", "postgres", container_name,
                "psql", "--username", "cwpf_admin", "--dbname", "chummer_preflight",
                "--no-psqlrc", "--set", "ON_ERROR_STOP=1",
            ),
            cwd=work_root,
            evidence=commands,
            stdin_payload=bootstrap_sql,
        )

        version_output = _run_provisioning_command(
            "postgres-major-version",
            docker_argv(
                docker_host, "exec", "--user", "postgres", container_name,
                "psql", "--username", "cwpf_admin", "--dbname", "chummer_preflight",
                "--no-psqlrc", "--tuples-only", "--no-align", "--command", "SHOW server_version_num",
            ),
            cwd=work_root,
            evidence=commands,
        ).decode("ascii", errors="strict").strip()
        if not re.fullmatch(r"17[0-9]{4}", version_output):
            raise PreflightError("isolated PostgreSQL server is not major version 17")
        evidence["majorVersion"] = 17

        admin_connection_file = postgres_secrets / "migrator.connection"
        runtime_connection_file = postgres_secrets / "runtime.connection"
        write_owner_only_file(
            admin_connection_file,
            (
                _postgres_connection_string(
                    port=host_port,
                    username="cwpf_admin",
                    password=admin_password,
                    ca_certificate=tls.ca_certificate,
                )
                + "\n"
            ).encode("utf-8"),
        )
        write_owner_only_file(
            runtime_connection_file,
            (
                _postgres_connection_string(
                    port=host_port,
                    username=runtime_role,
                    password=runtime_password,
                    ca_certificate=tls.ca_certificate,
                )
                + "\n"
            ).encode("utf-8"),
        )
        if not owner_only_file_passes(admin_connection_file) or not owner_only_file_passes(runtime_connection_file):
            raise PreflightError("isolated PostgreSQL connection files are not owner-only")

        postgres_tool = postgres_tool_root / "Chummer.InstallLinking.Postgres.Tool.dll"
        if not postgres_tool.is_file():
            raise PreflightError("published InstallLinking PostgreSQL tool is missing")
        dotnet_home = work_root / "dotnet-home"
        dotnet_temp = work_root / "tmp"
        ensure_owner_only_directory(dotnet_home)
        ensure_owner_only_directory(dotnet_temp)
        dotnet_environment = {
            "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE": str(
                admin_connection_file
            ),
            "DOTNET_ROOT": str(dotnet_execution.root),
            "DOTNET_HOST_PATH": str(dotnet_execution.host),
            "DOTNET_MULTILEVEL_LOOKUP": "0",
            "DOTNET_CLI_HOME": str(dotnet_home),
            "HOME": str(dotnet_home),
            "TMPDIR": str(dotnet_temp),
            "TMP": str(dotnet_temp),
            "TEMP": str(dotnet_temp),
            "PATH": "/usr/bin:/bin",
        }
        _run_provisioning_command(
            "postgres-authority-prepare",
            isolated_dotnet_argv(
                dotnet_execution,
                (str(dotnet_execution.host), str(postgres_tool), "prepare", runtime_role),
                (work_root,),
                (host_port,),
            ),
            cwd=postgres_tool_root,
            evidence=commands,
            timeout_seconds=120,
            environment=dotnet_environment,
        )
        accepted_before_transport = int(
            forwarder_evidence.get("acceptedConnections") or 0
        )
        transport_output = _run_provisioning_command(
            "postgres-transport-proof",
            isolated_dotnet_argv(
                dotnet_execution,
                (str(dotnet_execution.host), str(postgres_tool), "transport-proof"),
                (work_root,),
                (host_port,),
            ),
            cwd=postgres_tool_root,
            evidence=commands,
            timeout_seconds=30,
            environment=dotnet_environment,
            suppress_receipt_output=True,
        )
        accepted_after_transport = int(
            forwarder_evidence.get("acceptedConnections") or 0
        )
        transport_document = _decode_docker_inspect_json(
            transport_output,
            "isolated PostgreSQL transport proof",
        )
        transport_evidence = _postgres_transport_proof_evidence(
            transport_document,
            accepted_before=accepted_before_transport,
            accepted_after=accepted_after_transport,
        )
        evidence["transportProof"] = transport_evidence
        if not transport_evidence["passed"]:
            raise PreflightError("isolated PostgreSQL transport proof failed")
        evidence["schemaVersion"] = 2
        evidence["runtimePrivilegesValidated"] = True
        evidence["runtimeConnectionFileOwnerOnly"] = owner_only_file_passes(runtime_connection_file)
        evidence["passed"] = bool(
            evidence["networkInternal"]
            and evidence["containerAttachedOnlyToInternalNetwork"]
            and evidence["dockerPortPublishingDisabled"]
            and evidence["imageIdMatchesOperatorPin"]
            and evidence["listenerLoopbackOnly"]
            and forwarder_evidence.get("started") is True
            and forwarder_evidence.get("tlsTerminated") is False
            and evidence.get("hba", {}).get("passed") is True
            and evidence.get("transportProof", {}).get("passed") is True
            and evidence["majorVersion"] == 17
            and evidence["schemaVersion"] == 2
            and evidence["runtimePrivilegesValidated"]
            and evidence["runtimeConnectionFileOwnerOnly"]
        )
        authority = PostgresRuntimeAuthority(
            runtime_connection_file=runtime_connection_file,
            image_id=image_id,
            container_name=container_name,
            host_port=host_port,
            evidence=evidence,
        )
        yield authority
    finally:
        try:
            forwarder_stack.close()
        except Exception:
            forwarder_evidence["cleanupPassed"] = False
            evidence["passed"] = False
        cleanup_results = [
            _cleanup_owned_docker_resource(
                kind,
                name,
                owner,
                docker_host=docker_host,
                cwd=work_root,
                evidence=cleanup_commands,
            )
            for kind, name in (
                ("container", copy_container_name),
                ("container", container_name),
                ("volume", data_volume),
                ("volume", tls_volume),
                ("network", network_name),
            )
        ]
        evidence["cleanupPassed"] = all(cleanup_results)
        if forwarder_evidence.get("started") and not forwarder_evidence.get("passed"):
            evidence["passed"] = False
        if not evidence["cleanupPassed"]:
            evidence["passed"] = False


def _load_overlay_publisher(candidate_root: Path) -> Any:
    path = candidate_root / "scripts" / "publish_public_edge_portal_overlay.py"
    spec = importlib.util.spec_from_file_location(
        "canonical_writer_overlay_identity_preflight",
        path,
    )
    if spec is None or spec.loader is None:
        raise PreflightError(f"cannot import overlay identity materializer: {path}")
    module = importlib.util.module_from_spec(spec)
    scripts_root = str(path.parent)
    sys.path.insert(0, scripts_root)
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(scripts_root)
        except ValueError:
            pass
    return module


def ensure_private_payload_state_root(publish_root: Path) -> Path:
    state_root = publish_root / "state"
    if state_root.is_symlink() or (state_root.exists() and not state_root.is_dir()):
        raise PreflightError("preflight private payload state root is unsafe")
    state_root.mkdir(parents=False, exist_ok=True, mode=0o700)
    os.chmod(state_root, 0o700)
    return state_root


def read_preflight_overlay_identity(build_info_path: Path) -> dict[str, Any]:
    build_info = read_json_object(build_info_path, "preflight overlay build info")
    source = build_info.get("sourceFingerprint")
    staged = build_info.get("stagedPayloadFingerprint")
    deployment = build_info.get("fullDeploymentDigest")
    mode_receipt = build_info.get("payloadModeReceipt")
    source_digest = source.get("aggregateSha256") if isinstance(source, dict) else None
    staged_digest = staged.get("aggregateSha256") if isinstance(staged, dict) else None
    deployment_digest = deployment.get("sha256") if isinstance(deployment, dict) else None
    passed = bool(
        build_info.get("contractName") == "chummer.public_edge_portal_overlay_publish.v1"
        and build_info.get("status") == "pass"
        and build_info.get("activationStatus") == "activated"
        and re.fullmatch(r"[0-9a-f]{64}", str(source_digest or ""))
        and re.fullmatch(r"[0-9a-f]{64}", str(staged_digest or ""))
        and re.fullmatch(r"[0-9a-f]{64}", str(deployment_digest or ""))
        and isinstance(mode_receipt, dict)
        and mode_receipt.get("status") == "pass"
    )
    return {
        "passed": passed,
        "path": str(build_info_path),
        "sha256": sha256_file(build_info_path),
        "sourceFingerprintSha256": source_digest,
        "stagedPayloadSha256": staged_digest,
        "fullDeploymentDigestSha256": deployment_digest,
        "payloadModesPassed": (
            isinstance(mode_receipt, dict) and mode_receipt.get("status") == "pass"
        ),
    }


def finalize_preflight_overlay_identity(
    candidate_root: Path,
    publish_root: Path,
) -> dict[str, Any]:
    publisher = _load_overlay_publisher(candidate_root)
    state_root = ensure_private_payload_state_root(publish_root)
    created_mountpoints = publisher.ensure_required_compose_mountpoints(publish_root)
    fingerprint = publisher.source_fingerprint(candidate_root)
    build_info_path = publisher.write_overlay_build_info(
        publish_root,
        source_root=candidate_root,
        built_source_fingerprint=fingerprint,
        status="pass",
        activation_status="activated",
        verification={
            "status": "pass",
            "reason": "hermetic_production_loopback_preflight",
            "receiptStatus": "pass",
            "testOnlyHooksInjected": False,
        },
    )
    identity = read_preflight_overlay_identity(build_info_path)
    identity.update({
        "sourceFingerprintEnvelopeSha256": sha256_bytes(
            canonical_json_bytes(fingerprint)
        ),
        "privateStateRoot": str(state_root),
        "privateStateRootMode": stat.S_IMODE(state_root.stat().st_mode),
        "runtimeMountpointsMaterialized": sorted(created_mountpoints),
    })
    return identity


def run_command(
    name: str,
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    log_root: Path,
    timeout_seconds: int,
    monitored_roots: Sequence[Path] = (),
    mutation_evidence: list[dict[str, Any]] | None = None,
) -> CommandResult:
    if not argv or not Path(argv[0]).is_absolute():
        raise PreflightError(f"preflight command {name} must use an absolute executable")
    started = time.monotonic()
    monitor_row: dict[str, Any] = {"command": name}
    monitor_scope = (
        transient_tree_mutation_monitor(monitored_roots, monitor_row)
        if monitored_roots
        else contextlib.nullcontext()
    )
    try:
        with monitor_scope:
            completed = subprocess.run(
                list(argv),
                cwd=cwd,
                env=dict(environment),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout_seconds,
            )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = (exc.stderr or b"") + b"\npreflight command timed out\n"
        exit_code = 124
    if monitored_roots and mutation_evidence is not None:
        mutation_evidence.append(monitor_row)
    duration = time.monotonic() - started
    # Build tools can echo ambient credentials in otherwise useful diagnostics.
    # Retain content digests for auditability, but never persist or receipt their
    # raw output. `log_root` remains in the signature for call-site stability.
    _ = log_root
    return CommandResult(
        name=name,
        argv=tuple(argv),
        cwd=str(cwd),
        exit_code=exit_code,
        duration_seconds=duration,
        stdout_sha256=sha256_bytes(stdout),
        stderr_sha256=sha256_bytes(stderr),
        stdout_tail=OUTPUT_WITHHELD,
        stderr_tail=OUTPUT_WITHHELD,
    )


def make_optimistic_copy(source: Path, destination: Path) -> dict[str, Any]:
    payload = read_json_object(source, source.name)
    payload["status"] = "published"
    payload["rolloutState"] = "promoted_preview"
    payload["rolloutReason"] = "Current release shelf passed the local release run before publication."
    payload["supportabilityState"] = "preview_supported"
    payload["supportabilitySummary"] = "Current preview release is supported."
    metrics = payload.setdefault("publicTrustMetrics", {})
    if not isinstance(metrics, dict):
        raise PreflightError(f"{source.name} publicTrustMetrics must be an object")
    freshness = metrics.setdefault("proofFreshness", {})
    if not isinstance(freshness, dict):
        raise PreflightError(f"{source.name} proofFreshness must be an object")
    freshness["status"] = "stale"
    public_channel = metrics.setdefault("releaseChannel", {})
    if not isinstance(public_channel, dict):
        raise PreflightError(f"{source.name} releaseChannel must be an object")
    public_channel.update(
        {
            "rolloutState": "promoted_preview",
            "supportabilityState": "preview_supported",
            "posture": "preview",
            "summary": "The current preview is supported.",
        }
    )
    registry = payload.setdefault("registryBoundaryCoverage", {})
    if not isinstance(registry, dict):
        raise PreflightError(f"{source.name} registryBoundaryCoverage must be an object")
    registry_channel = registry.setdefault("releaseChannel", {})
    if not isinstance(registry_channel, dict):
        raise PreflightError(f"{source.name} registry releaseChannel must be an object")
    registry_channel.update(
        {
            "rolloutState": "promoted_preview",
            "supportabilityState": "preview_supported",
            "publicTrustPosture": "preview",
            "summary": "Registry truth reports a supported preview.",
        }
    )
    atomic_write_json(destination, payload)
    return payload


def trust_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    metrics = payload.get("publicTrustMetrics")
    registry = payload.get("registryBoundaryCoverage")
    public_channel = metrics.get("releaseChannel") if isinstance(metrics, dict) else None
    freshness = metrics.get("proofFreshness") if isinstance(metrics, dict) else None
    freshness = metrics.get("proofFreshness") if isinstance(metrics, dict) else None
    revocation = metrics.get("revocationFacts") if isinstance(metrics, dict) else None
    registry_channel = registry.get("releaseChannel") if isinstance(registry, dict) else None
    return {
        "status": payload.get("status"),
        "rolloutState": payload.get("rolloutState"),
        "rolloutReason": payload.get("rolloutReason"),
        "supportabilityState": payload.get("supportabilityState"),
        "supportabilitySummary": payload.get("supportabilitySummary"),
        "proofFreshnessStatus": freshness.get("status") if isinstance(freshness, dict) else None,
        "publicTrustRolloutState": public_channel.get("rolloutState") if isinstance(public_channel, dict) else None,
        "publicTrustChannelId": public_channel.get("channelId") if isinstance(public_channel, dict) else None,
        "publicTrustPublicationStatus": public_channel.get("publicationStatus") if isinstance(public_channel, dict) else None,
        "publicTrustSupportabilityState": public_channel.get("supportabilityState") if isinstance(public_channel, dict) else None,
        "publicTrustPosture": public_channel.get("posture") if isinstance(public_channel, dict) else None,
        "publicTrustSummary": public_channel.get("summary") if isinstance(public_channel, dict) else None,
        "publicTrustRecommendedRouteCount": public_channel.get("recommendedRouteCount") if isinstance(public_channel, dict) else None,
        "publicTrustBlockedRouteCount": public_channel.get("blockedRouteCount") if isinstance(public_channel, dict) else None,
        "publicTrustRevokedRouteCount": public_channel.get("revokedRouteCount") if isinstance(public_channel, dict) else None,
        "publicTrustFallbackRecoveryRouteCount": public_channel.get("fallbackRecoveryRouteCount") if isinstance(public_channel, dict) else None,
        "revocationStatus": revocation.get("status") if isinstance(revocation, dict) else None,
        "channelRevoked": revocation.get("channelRevoked") if isinstance(revocation, dict) else None,
        "activeRevocationCount": revocation.get("activeRevocationCount") if isinstance(revocation, dict) else None,
        "activeRevocations": revocation.get("activeRevocations") if isinstance(revocation, dict) else None,
        "revocationSummary": revocation.get("summary") if isinstance(revocation, dict) else None,
        "registryRolloutState": registry_channel.get("rolloutState") if isinstance(registry_channel, dict) else None,
        "registrySupportabilityState": registry_channel.get("supportabilityState") if isinstance(registry_channel, dict) else None,
        "registryPublicTrustPosture": registry_channel.get("publicTrustPosture") if isinstance(registry_channel, dict) else None,
        "registryPublicTrustSummary": registry_channel.get("summary") if isinstance(registry_channel, dict) else None,
        "registryPublicationStatus": registry_channel.get("publicationStatus") if isinstance(registry_channel, dict) else None,
        "registryStatus": registry.get("status") if isinstance(registry, dict) else None,
        "registryOwner": registry.get("owner") if isinstance(registry, dict) else None,
        "registryChannelId": registry.get("channelId") if isinstance(registry, dict) else None,
        "registryReleaseVersion": registry.get("releaseVersion") if isinstance(registry, dict) else None,
    }


def revocation_binding(payload: Mapping[str, Any]) -> dict[str, Any]:
    identity = manifest_identity(payload)
    metrics = payload.get("publicTrustMetrics")
    revocation = metrics.get("revocationFacts") if isinstance(metrics, dict) else None
    expected_summary = (
        f"No channel or route revocations are active on channel {identity['channel']}."
    )
    if (
        not isinstance(revocation, dict)
        or revocation.get("status") != "clear"
        or revocation.get("channelRevoked") is not False
        or type(revocation.get("activeRevocationCount")) is not int
        or revocation.get("activeRevocationCount") != 0
        or revocation.get("activeRevocations") != []
        or revocation.get("summary") != expected_summary
    ):
        raise PreflightError(
            "manifest revocation facts contradict a published, non-revoked release"
        )
    projection = {
        "status": "clear",
        "channelRevoked": False,
        "activeRevocationCount": 0,
        "activeRevocations": [],
        "summary": expected_summary,
    }
    return {
        "projection": projection,
        "sha256": sha256_bytes(canonical_json_bytes(projection)),
    }


def release_channel_authority_binding(
    payload: Mapping[str, Any],
    coverage: Mapping[str, Any],
) -> dict[str, Any]:
    identity = manifest_identity(payload)
    metrics = payload.get("publicTrustMetrics")
    public_channel = metrics.get("releaseChannel") if isinstance(metrics, dict) else None
    freshness = metrics.get("proofFreshness") if isinstance(metrics, dict) else None
    registry = payload.get("registryBoundaryCoverage")
    registry_channel = registry.get("releaseChannel") if isinstance(registry, dict) else None
    freshness_status = freshness.get("status") if isinstance(freshness, dict) else None
    if freshness_status in {"stale", "missing"}:
        expected_counts = {
            "recommendedRouteCount": 0,
            "blockedRouteCount": coverage.get("desktopRouteTruthCount"),
            "revokedRouteCount": 0,
            "fallbackRecoveryRouteCount": 0,
        }
    else:
        expected_counts = {
            "recommendedRouteCount": coverage.get("recommendedRouteCount"),
            "blockedRouteCount": coverage.get("blockedRouteCount"),
            "revokedRouteCount": coverage.get("revokedRouteCount"),
            "fallbackRecoveryRouteCount": coverage.get("fallbackRecoveryRouteCount"),
        }
    if (
        not isinstance(public_channel, dict)
        or freshness_status not in {"fresh", "stale", "missing"}
        or public_channel.get("channelId") != identity["channel"]
        or public_channel.get("publicationStatus") != "published"
        or any(
            type(public_channel.get(key)) is not int
            or public_channel.get(key) != value
            for key, value in expected_counts.items()
        )
        or not isinstance(registry, dict)
        or registry.get("status") != "closed"
        or registry.get("owner") != "chummer6-hub-registry"
        or registry.get("channelId") != identity["channel"]
        or registry.get("releaseVersion") != identity["version"]
        or not isinstance(registry_channel, dict)
        or registry_channel.get("publicationStatus") != "published"
        or registry_channel.get("promotedInstallerTupleCount")
        != coverage.get("promotedInstallerTupleCount")
        or registry_channel.get("desktopRouteTruthCount")
        != coverage.get("desktopRouteTruthCount")
    ):
        raise PreflightError(
            "manifest release-channel authority conflicts with release identity or route truth"
        )
    projection = {
        "channelId": identity["channel"],
        "releaseVersion": identity["version"],
        "publicationStatus": "published",
        "proofFreshnessStatus": freshness_status,
        **expected_counts,
        "registryStatus": "closed",
        "registryOwner": "chummer6-hub-registry",
        "promotedInstallerTupleCount": coverage["promotedInstallerTupleCount"],
        "desktopRouteTruthCount": coverage["desktopRouteTruthCount"],
    }
    return {
        "projection": projection,
        "sha256": sha256_bytes(canonical_json_bytes(projection)),
    }


def contract_identity_binding(payload: Mapping[str, Any]) -> dict[str, Any]:
    aliases = [payload.get("contractName"), payload.get("contract_name")]
    if aliases != ["Chummer.Hub.Registry.Contracts"] * 2:
        raise PreflightError(
            "manifest contract-name aliases must exactly identify the Registry contract"
        )
    projection = {
        "contractName": "Chummer.Hub.Registry.Contracts",
        "contract_name": "Chummer.Hub.Registry.Contracts",
    }
    return {
        "projection": projection,
        "sha256": sha256_bytes(canonical_json_bytes(projection)),
    }


def release_proof_binding(
    payload: Mapping[str, Any],
    inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    proof = payload.get("releaseProof")
    if not isinstance(proof, dict):
        raise PreflightError("manifest release proof contract is missing or malformed")

    def alias_value(primary: str, secondary: str, label: str) -> Any:
        has_primary = primary in proof
        has_secondary = secondary in proof
        if has_primary and has_secondary and proof.get(primary) != proof.get(secondary):
            raise PreflightError(f"manifest release proof {label} aliases conflict")
        if has_primary:
            return proof.get(primary)
        if has_secondary:
            return proof.get(secondary)
        raise PreflightError(f"manifest release proof {label} is missing")

    status = proof.get("status")
    if not isinstance(status, str) or status != status.strip().lower():
        raise PreflightError("manifest release proof status is malformed")
    if status not in {"pass", "passed", "ready", "review_required"}:
        raise PreflightError("manifest release proof status is unsupported")
    normalized_status = "passed" if status in {"pass", "passed", "ready"} else status

    try:
        generated_at = normalize_timestamp(
            alias_value("generatedAt", "generated_at", "generated-at")
        )
    except PreflightError as exc:
        raise PreflightError("manifest release proof generated-at is malformed") from exc
    base_url = alias_value("baseUrl", "base_url", "base URL")
    if base_url != "https://chummer.run":
        raise PreflightError(
            "manifest release proof base URL must be the canonical public origin"
        )

    journeys = alias_value("journeysPassed", "journeys_passed", "journey list")
    if not isinstance(journeys, list) or tuple(journeys) != REQUIRED_RELEASE_PROOF_JOURNEYS:
        raise PreflightError(
            "manifest release proof journeys must match the canonical Registry contract"
        )

    routes = alias_value("proofRoutes", "proof_routes", "route list")
    if not isinstance(routes, list) or not routes:
        raise PreflightError("manifest release proof routes must be a non-empty list")
    normalized_routes: list[str] = []
    for route in routes:
        if (
            not isinstance(route, str)
            or not route
            or route != route.strip().lower()
            or not route.startswith("/")
            or route.endswith("/")
            or any(character.isspace() for character in route)
            or any(token in route for token in ("?", "#", "%", "\\", "//"))
            or any(segment in {"", ".", ".."} for segment in route[1:].split("/"))
        ):
            raise PreflightError("manifest release proof contains a non-canonical route")
        normalized_routes.append(route)
    if len(set(normalized_routes)) != len(normalized_routes):
        raise PreflightError("manifest release proof routes contain duplicates")
    required_routes = list(REQUIRED_RELEASE_PROOF_ROUTES)
    additional_routes = normalized_routes[len(required_routes) :]
    expected_additional_routes = sorted(
        {
            f"/downloads/install/{row['id']}"
            for row in inventory
            if row.get("kind") == "installer"
        }
        - set(REQUIRED_RELEASE_PROOF_ROUTES)
    )
    if (
        normalized_routes[: len(required_routes)] != required_routes
        or any(
            RELEASE_PROOF_INSTALL_ROUTE_PATTERN.fullmatch(route) is None
            for route in additional_routes
        )
        or additional_routes != expected_additional_routes
    ):
        raise PreflightError(
            "manifest release proof routes conflict with Registry ordering or artifact inventory"
        )

    localization_gate = alias_value(
        "uiLocalizationReleaseGate",
        "ui_localization_release_gate",
        "UI localization gate",
    )
    if not isinstance(localization_gate, dict):
        raise PreflightError("manifest release proof UI localization gate is malformed")
    gate_status = localization_gate.get("status")
    gate_generated_values = [
        localization_gate[key]
        for key in ("generatedAt", "generated_at")
        if key in localization_gate
    ]
    try:
        normalized_gate_timestamps = {
            normalize_timestamp(value) for value in gate_generated_values
        }
    except PreflightError as exc:
        raise PreflightError(
            "manifest release proof UI localization gate timestamp is malformed"
        ) from exc
    if (
        gate_status != "pass"
        or not gate_generated_values
        or len(normalized_gate_timestamps) != 1
    ):
        raise PreflightError(
            "manifest release proof UI localization gate is not a canonical passing gate"
        )
    normalized_gate = dict(localization_gate)
    normalized_gate.pop("generated_at", None)
    normalized_gate["generatedAt"] = normalize_timestamp(gate_generated_values[0])

    projection = {
        "status": normalized_status,
        "generatedAt": generated_at,
        "baseUrl": base_url,
        "journeysPassed": list(REQUIRED_RELEASE_PROOF_JOURNEYS),
        "proofRoutes": normalized_routes,
        "uiLocalizationReleaseGate": normalized_gate,
    }
    return {
        "projection": projection,
        "sha256": sha256_bytes(canonical_json_bytes(projection)),
    }


def _approved_review_required_narratives(
    payload: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> bool:
    try:
        identity = manifest_identity(payload)
    except (PreflightError, TypeError, ValueError):
        return False
    try:
        coverage = desktop_tuple_coverage_binding(payload, artifact_inventory(payload))
    except (PreflightError, TypeError, ValueError, OverflowError):
        return False
    promoted = coverage["promotedInstallerTupleCount"]
    route_count = coverage["desktopRouteTruthCount"]
    approved_rollout_reasons = {
        "Current shelf is published, but release posture stays review-required because "
        "stale or incomplete proof receipts still block launch-readiness claims.",
        "Current shelf is published, but release posture stays review-required because "
        "stale or incomplete proof receipts and Hosted Build privacy, retention, recovery, "
        "and erasure review still block launch-readiness claims.",
    }
    approved_supportability_summaries = {
        "Current preview artifacts remain downloadable for proof testing, but supportability "
        "is review-required until stale proof receipts are refreshed.",
        "Current preview artifacts remain downloadable for proof testing, but supportability "
        "is review-required until stale proof receipts and Hosted Build privacy, retention, "
        "recovery, and erasure decisions are refreshed.",
    }
    approved_public_trust_summaries = {
        f"Channel {identity['channel']} remains published for bounded proof testing, but public "
        "trust posture is blocked until proof freshness is current.",
        f"Channel {identity['channel']} remains published for bounded proof testing, but public "
        "trust posture is blocked until proof freshness and Hosted Build privacy review are current.",
    }
    approved_registry_summary = (
        f"Release-channel truth for {identity['channel']}/{identity['version']} keeps {promoted} "
        f"promoted installer tuples and {route_count} explicit desktop route-truth rows while "
        "rollout remains public_release_review_required and public trust is blocked."
    )
    return bool(
        projection.get("rolloutReason") in approved_rollout_reasons
        and projection.get("supportabilitySummary") in approved_supportability_summaries
        and projection.get("publicTrustSummary") in approved_public_trust_summaries
        and projection.get("registryPublicTrustSummary") == approved_registry_summary
    )


def trust_floor_passes(payload: Mapping[str, Any]) -> bool:
    projection = trust_projection(payload)
    try:
        revocation_binding(payload)
        inventory = artifact_inventory(payload)
        coverage = desktop_tuple_coverage_binding(payload, inventory)
        release_channel_authority_binding(payload, coverage)
        release_proof_binding(payload, inventory)
    except (PreflightError, TypeError, ValueError, OverflowError):
        return False
    return (
        projection["status"] == "published"
        and projection["rolloutState"] == "public_release_review_required"
        and projection["supportabilityState"] == "review_required"
        and projection["proofFreshnessStatus"] == "stale"
        and projection["publicTrustRolloutState"] == "public_release_review_required"
        and projection["publicTrustPublicationStatus"] == "published"
        and projection["publicTrustSupportabilityState"] == "review_required"
        and projection["publicTrustPosture"] == "blocked"
        and projection["revocationStatus"] == "clear"
        and projection["channelRevoked"] is False
        and projection["activeRevocationCount"] == 0
        and projection["activeRevocations"] == []
        and projection["registryRolloutState"] == "public_release_review_required"
        and projection["registrySupportabilityState"] == "review_required"
        and projection["registryPublicTrustPosture"] == "blocked"
        and projection["registryPublicationStatus"] == "published"
        and _approved_review_required_narratives(payload, projection)
    )


def manifest_identity(payload: Mapping[str, Any]) -> dict[str, str]:
    version_aliases = [payload[key] for key in ("releaseVersion", "version") if key in payload]
    channel_aliases = [payload[key] for key in ("channelId", "channel") if key in payload]
    timestamp_aliases = [
        payload[key]
        for key in ("publishedAt", "generatedAt", "generated_at")
        if key in payload
    ]
    if not version_aliases or not channel_aliases or not timestamp_aliases:
        raise PreflightError("manifest identity aliases are incomplete")
    for label, values in (
        ("version", version_aliases),
        ("channel", channel_aliases),
        ("publication timestamp", timestamp_aliases),
    ):
        if any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            for value in values
        ):
            raise PreflightError(f"manifest {label} aliases are malformed")
    normalized_timestamps = [normalize_timestamp(value) for value in timestamp_aliases]
    if any(PORTABLE_TOKEN_PATTERN.fullmatch(value) is None for value in version_aliases):
        raise PreflightError("manifest version aliases are not portable tokens")
    if any(value not in ALLOWED_RELEASE_CHANNELS for value in channel_aliases):
        raise PreflightError("manifest channel aliases are not allowed release channels")
    if (
        len(set(version_aliases)) != 1
        or len(set(channel_aliases)) != 1
        or len(set(normalized_timestamps)) != 1
    ):
        raise PreflightError("manifest identity aliases conflict")
    return {
        "version": version_aliases[0],
        "channel": channel_aliases[0],
        "publishedAt": normalized_timestamps[0],
    }


def artifact_inventory(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    release_identity = manifest_identity(payload)
    has_artifacts = "artifacts" in payload
    has_downloads = "downloads" in payload
    if has_artifacts and has_downloads:
        raise PreflightError(
            "manifest must not expose simultaneous artifacts and downloads collections"
        )
    raw_rows = payload.get("artifacts") if has_artifacts else payload.get("downloads")
    if (has_artifacts or has_downloads) and not isinstance(raw_rows, list):
        raise PreflightError("manifest artifact inventory collection must be a list")
    if raw_rows is None:
        raw_rows = []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    seen_file_names: set[str] = set()
    seen_urls: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise PreflightError("manifest artifact inventory contains a non-object row")
        artifact_id = raw.get("artifactId") or raw.get("id")
        file_name = raw.get("fileName")
        digest = raw.get("sha256")
        size = raw.get("sizeBytes")
        download_url = raw.get("downloadUrl") or raw.get("url")
        access_class = raw.get("installAccessClass")
        kind = raw.get("kind")
        head = raw.get("head")
        arch = raw.get("arch")
        platform = raw.get("platform")
        rid = raw.get("rid")
        compatibility_state = raw.get("compatibilityState")
        id_aliases = [raw[key] for key in ("artifactId", "id") if key in raw]
        url_aliases = [raw[key] for key in ("downloadUrl", "url") if key in raw]
        normalized_id_aliases = [
            value.strip() for value in id_aliases if isinstance(value, str)
        ]
        normalized_url_aliases = [
            value.strip() for value in url_aliases if isinstance(value, str)
        ]
        parsed_download_url = (
            urllib.parse.urlsplit(download_url.strip())
            if isinstance(download_url, str)
            else None
        )
        if (
            not isinstance(artifact_id, str)
            or not artifact_id.strip()
            or artifact_id != artifact_id.strip()
            or not isinstance(file_name, str)
            or not file_name.strip()
            or file_name != file_name.strip()
            or not isinstance(digest, str)
            or digest != digest.strip().lower()
            or LOWER_SHA256_PATTERN.fullmatch(digest) is None
            or type(size) is not int
            or size < 0
            or not isinstance(download_url, str)
            or download_url != download_url.strip()
            or not download_url.startswith("/downloads/")
            or parsed_download_url is None
            or parsed_download_url.scheme
            or parsed_download_url.netloc
            or parsed_download_url.query
            or parsed_download_url.fragment
            or not isinstance(access_class, str)
            or not access_class.strip()
            or access_class != access_class.strip()
            or access_class not in ALLOWED_INSTALL_ACCESS_CLASSES
            or not isinstance(kind, str)
            or not kind
            or kind != kind.strip()
            or kind not in ALLOWED_ARTIFACT_KINDS
            or not isinstance(head, str)
            or not head
            or head != head.strip()
            or not isinstance(arch, str)
            or not arch
            or arch != arch.strip()
            or not isinstance(platform, str)
            or not platform
            or platform != platform.strip()
            or not isinstance(rid, str)
            or not rid
            or rid != rid.strip()
            or PORTABLE_TOKEN_PATTERN.fullmatch(artifact_id) is None
            or PORTABLE_FILE_NAME_PATTERN.fullmatch(file_name) is None
            or PORTABLE_TOKEN_PATTERN.fullmatch(head) is None
            or PORTABLE_TOKEN_PATTERN.fullmatch(arch) is None
            or PORTABLE_TOKEN_PATTERN.fullmatch(platform) is None
            or PORTABLE_TOKEN_PATTERN.fullmatch(rid) is None
            or compatibility_state != "compatible"
            or raw.get("compatibilityReason") is not None
            or any(
                not isinstance(raw.get(key), str)
                or raw.get(key) != release_identity["version"]
                for key in ("version", "releaseVersion")
                if key in raw
            )
            or any(
                not isinstance(raw.get(key), str)
                or raw.get(key) != release_identity["channel"]
                for key in ("channel", "channelId")
                if key in raw
            )
            or any(
                not isinstance(raw.get(key), str)
                or normalize_timestamp(raw.get(key)) != release_identity["publishedAt"]
                for key in ("publishedAt", "generatedAt", "generated_at")
                if key in raw
            )
            or CANONICAL_DOWNLOAD_PATH_PATTERN.fullmatch(download_url) is None
            or "%" in download_url
            or "\\" in download_url
            or parsed_download_url.path != download_url
            or any(segment in {"", ".", ".."} for segment in download_url.split("/")[2:])
            or download_url.rsplit("/", 1)[-1] != file_name
            or not (
                download_url == f"/downloads/files/{file_name}"
                or (
                    len(download_url.split("/")) == 6
                    and download_url.split("/")[2] == "g"
                    and PORTABLE_TOKEN_PATTERN.fullmatch(download_url.split("/")[3])
                    and download_url.split("/")[4] == "files"
                    and download_url.split("/")[5] == file_name
                )
            )
            or any(
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
                for value in id_aliases
            )
            or len(set(normalized_id_aliases)) > 1
            or any(
                not isinstance(value, str)
                or value != value.strip()
                for value in url_aliases
            )
            or len(normalized_url_aliases) != len(url_aliases)
            or any(not value for value in normalized_url_aliases)
            or len(set(normalized_url_aliases)) > 1
        ):
            raise PreflightError("manifest artifact inventory row is malformed")
        key = (artifact_id.strip(), file_name.strip())
        if key in seen:
            raise PreflightError("manifest artifact inventory contains a duplicate row")
        normalized_url = download_url.strip()
        if (
            key[0] in seen_ids
            or key[1] in seen_file_names
            or normalized_url in seen_urls
        ):
            raise PreflightError(
                "manifest artifact inventory contains an ambiguous id, file name, or URL"
            )
        seen.add(key)
        seen_ids.add(key[0])
        seen_file_names.add(key[1])
        seen_urls.add(normalized_url)
        rows.append(
            {
                "id": key[0],
                "fileName": key[1],
                "sha256": digest.strip().lower(),
                "sizeBytes": size,
                "url": normalized_url,
                "installAccessClass": access_class.strip(),
                "kind": kind,
                "head": head,
                "arch": arch,
                "platform": platform,
                "rid": rid,
                "compatibilityState": compatibility_state,
            }
        )
    return sorted(rows, key=lambda row: (row["id"], row["fileName"]))


def desktop_tuple_coverage_binding(
    payload: Mapping[str, Any],
    inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    coverage = payload.get("desktopTupleCoverage")
    registry = payload.get("registryBoundaryCoverage")
    registry_channel = registry.get("releaseChannel") if isinstance(registry, dict) else None
    if not isinstance(coverage, dict) or not isinstance(registry_channel, dict):
        raise PreflightError("manifest desktop tuple coverage is incomplete")
    promoted_rows = coverage.get("promotedInstallerTuples")
    route_rows = coverage.get("desktopRouteTruth")
    if not isinstance(promoted_rows, list) or not isinstance(route_rows, list):
        raise PreflightError("manifest desktop tuple coverage rows must be arrays")
    inventory_by_id = {
        str(row.get("id") or ""): row
        for row in inventory
        if isinstance(row, Mapping)
    }

    def row_binding(raw: Any, label: str) -> tuple[str, str, str, str, str, str]:
        if not isinstance(raw, dict):
            raise PreflightError(f"manifest {label} contains a non-object row")
        tuple_id = raw.get("tupleId")
        artifact_id = raw.get("artifactId")
        if (
            not isinstance(tuple_id, str)
            or not tuple_id
            or tuple_id != tuple_id.strip()
            or not isinstance(artifact_id, str)
            or not artifact_id
            or artifact_id != artifact_id.strip()
            or artifact_id not in inventory_by_id
        ):
            raise PreflightError(f"manifest {label} row is not artifact-bound")
        head = raw.get("head")
        arch = raw.get("arch")
        platform = raw.get("platform")
        rid = raw.get("rid")
        artifact = inventory_by_id[artifact_id]
        if (
            not isinstance(head, str)
            or not head
            or head != head.strip()
            or not isinstance(arch, str)
            or not arch
            or arch != arch.strip()
            or head != artifact.get("head")
            or arch != artifact.get("arch")
            or not isinstance(platform, str)
            or not platform
            or platform != platform.strip()
            or not isinstance(rid, str)
            or not rid
            or rid != rid.strip()
            or platform != artifact.get("platform")
            or rid != artifact.get("rid")
            or tuple_id != f"{head}:{platform}:{rid}"
            or PORTABLE_TOKEN_PATTERN.fullmatch(head) is None
            or PORTABLE_TOKEN_PATTERN.fullmatch(arch) is None
            or PORTABLE_TOKEN_PATTERN.fullmatch(platform) is None
            or PORTABLE_TOKEN_PATTERN.fullmatch(rid) is None
        ):
            raise PreflightError(f"manifest {label} row identity conflicts with its artifact")
        return tuple_id, artifact_id, head, arch, platform, rid

    promoted = [row_binding(row, "promoted installer tuple") for row in promoted_rows]
    routes = [row_binding(row, "desktop route truth") for row in route_rows]
    promoted_tuple_ids = [row[0] for row in promoted]
    route_tuple_ids = [row[0] for row in routes]
    if (
        not promoted_rows
        or not route_rows
        or len(set(promoted_tuple_ids)) != len(promoted_tuple_ids)
        or len(set(route_tuple_ids)) != len(route_tuple_ids)
        or set(promoted) != set(routes)
        or {
            artifact_id
            for artifact_id, artifact in inventory_by_id.items()
            if artifact.get("kind") == "installer"
        }
        != {row[1] for row in promoted}
        or any(
            row.get("kind") != "installer"
            or inventory_by_id[str(row.get("artifactId") or "")].get("kind") != "installer"
            for row in promoted_rows
        )
        or any(row.get("promotionState") != "promoted" for row in route_rows)
        or coverage.get("complete") is not True
        or registry_channel.get("desktopTupleComplete") is not True
        or registry_channel.get("promotedInstallerTupleCount") != len(promoted_rows)
        or registry_channel.get("desktopRouteTruthCount") != len(route_rows)
    ):
        raise PreflightError("manifest desktop tuple coverage counts or rows conflict")
    for row in route_rows:
        role = row.get("routeRole")
        artifact_id = str(row.get("artifactId") or "")
        if (
            role not in {"primary", "fallback"}
            or row.get("promotionState") != "promoted"
            or row.get("promotionReasonCode")
            != "installer_smoke_and_release_proof_passed"
            or row.get("revokeState") != "not_revoked"
            or row.get("revokeSource") != "none"
            or row.get("revokeReasonCode") != "no_registry_revoke_marker"
            or row.get("installPosture") != "installer_first"
            or row.get("rollbackState") != "fallback_available"
            or row.get("updateEligibility")
            != ("eligible" if role == "primary" else "manual_fallback")
            or row.get("publicInstallRoute")
            not in {
                f"/downloads/install/{artifact_id}",
                inventory_by_id[artifact_id].get("url"),
            }
        ):
            raise PreflightError("manifest desktop route truth semantics conflict")
    required_platforms = coverage.get("requiredDesktopPlatforms")
    required_heads = coverage.get("requiredDesktopHeads")
    required_tuples = coverage.get("requiredDesktopPlatformHeadRidTuples")
    promoted_tuples = coverage.get("promotedPlatformHeadRidTuples")
    missing_keys = (
        "missingRequiredPlatforms",
        "missingRequiredHeads",
        "missingRequiredPlatformHeadPairs",
        "missingRequiredPlatformHeadRidTuples",
    )
    if (
        not isinstance(required_platforms, list)
        or not required_platforms
        or not isinstance(required_heads, list)
        or not required_heads
        or not isinstance(required_tuples, list)
        or not required_tuples
        or not isinstance(promoted_tuples, list)
        or set(promoted_tuples)
        != {f"{head}:{rid}:{platform}" for _, _, head, _, platform, rid in promoted}
        or not set(required_tuples).issubset(set(promoted_tuples))
        or not set(required_platforms).issubset(
            {platform for _, _, _, _, platform, _ in promoted}
        )
        or not set(required_heads).issubset({head for _, _, head, _, _, _ in promoted})
        or any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or (
                ":" not in value
                and PORTABLE_TOKEN_PATTERN.fullmatch(value) is None
            )
            for rows in (required_platforms, required_heads, required_tuples, promoted_tuples)
            for value in rows
        )
        or any(len(set(rows)) != len(rows) for rows in (
            required_platforms,
            required_heads,
            required_tuples,
            promoted_tuples,
        ))
        or any(coverage.get(key) != [] for key in missing_keys)
    ):
        raise PreflightError("manifest required desktop coverage is incomplete")
    return {
        "promotedInstallerTupleCount": len(promoted_rows),
        "desktopRouteTruthCount": len(route_rows),
        "recommendedRouteCount": sum(
            1 for row in route_rows if row.get("routeRole") == "primary"
        ),
        "fallbackRecoveryRouteCount": sum(
            1 for row in route_rows if row.get("routeRole") == "fallback"
        ),
        "blockedRouteCount": 0,
        "revokedRouteCount": 0,
        "coverageSha256": sha256_bytes(canonical_json_bytes(coverage)),
    }


def prepared_manifest_binding(payload: Mapping[str, Any]) -> dict[str, Any]:
    template = template_manifest_binding(payload)
    inventory = template["artifactInventory"]
    identity = template["releaseIdentity"]
    generation_id = payload.get("generationId")
    if (
        not isinstance(generation_id, str)
        or not generation_id.strip()
        or generation_id != generation_id.strip()
        or PORTABLE_TOKEN_PATTERN.fullmatch(generation_id) is None
    ):
        raise PreflightError("manifest generationId is missing from immutable binding")
    return {
        "generationId": generation_id.strip(),
        "identityAliasesConsistent": True,
        "releaseIdentity": identity,
        "artifactInventory": inventory,
        "artifactCount": len(inventory),
        "artifactInventorySha256": sha256_bytes(canonical_json_bytes(inventory)),
        "publicationStatus": "published",
        "desktopTupleCoverage": template["desktopTupleCoverage"],
        "revocationFacts": template["revocationFacts"],
        "releaseChannelAuthority": template["releaseChannelAuthority"],
        "contractIdentity": template["contractIdentity"],
        "releaseProof": template["releaseProof"],
        "immutableProjectionSha256": sha256_bytes(
            canonical_json_bytes(
                {
                    "generationId": generation_id.strip(),
                    "releaseIdentity": identity,
                    "artifactInventory": inventory,
                    "publicationStatus": "published",
                    "desktopTupleCoverage": template["desktopTupleCoverage"],
                    "revocationFacts": template["revocationFacts"],
                    "releaseChannelAuthority": template["releaseChannelAuthority"],
                    "contractIdentity": template["contractIdentity"],
                    "releaseProof": template["releaseProof"],
                }
            )
        ),
    }


def template_manifest_binding(payload: Mapping[str, Any]) -> dict[str, Any]:
    identity = manifest_identity(payload)
    inventory = artifact_inventory(payload)
    registry = payload.get("registryBoundaryCoverage")
    registry_channel = registry.get("releaseChannel") if isinstance(registry, dict) else None
    if payload.get("status") != "published" or not isinstance(registry_channel, dict) or registry_channel.get(
        "publicationStatus"
    ) != "published":
        raise PreflightError("manifest publication status must be exactly published")
    if not inventory:
        raise PreflightError("manifest artifact inventory must not be empty")
    coverage = desktop_tuple_coverage_binding(payload, inventory)
    revocation = revocation_binding(payload)
    release_channel = release_channel_authority_binding(payload, coverage)
    contract_identity = contract_identity_binding(payload)
    release_proof = release_proof_binding(payload, inventory)
    return {
        "identityAliasesConsistent": True,
        "releaseIdentity": identity,
        "artifactInventory": inventory,
        "artifactCount": len(inventory),
        "artifactInventorySha256": sha256_bytes(canonical_json_bytes(inventory)),
        "desktopTupleCoverage": coverage,
        "revocationFacts": revocation,
        "releaseChannelAuthority": release_channel,
        "contractIdentity": contract_identity,
        "releaseProof": release_proof,
    }


def served_manifest_binding_evidence(
    payload: Mapping[str, Any] | None,
    headers: Mapping[str, Sequence[str]],
    expected_generation_id: str,
    expected_binding: Mapping[str, Any],
) -> dict[str, Any]:
    generation_values = tuple(headers.get("x-chummer-release-generation", ()))
    expected_inventory = expected_binding.get("artifactInventory")
    try:
        observed_binding = (
            prepared_manifest_binding(payload) if isinstance(payload, dict) else None
        )
    except (PreflightError, TypeError, ValueError, OverflowError):
        observed_binding = None
    observed_inventory = (
        observed_binding.get("artifactInventory")
        if isinstance(observed_binding, dict)
        else None
    )
    expected_projection = str(
        expected_binding.get("immutableProjectionSha256") or ""
    )
    observed_projection = str(
        observed_binding.get("immutableProjectionSha256") or ""
    ) if isinstance(observed_binding, dict) else ""
    evidence = {
        "expectedGenerationId": expected_generation_id,
        "responseGenerationValues": list(generation_values),
        "generationHeaderExact": generation_values == (expected_generation_id,),
        "expectedBodyGenerationId": str(expected_binding.get("generationId") or ""),
        "observedBodyGenerationId": (
            str(observed_binding.get("generationId") or "")
            if isinstance(observed_binding, dict)
            else ""
        ),
        "bodyGenerationExact": bool(expected_generation_id)
        and str(expected_binding.get("generationId") or "") == expected_generation_id
        and (
            str(observed_binding.get("generationId") or "")
            if isinstance(observed_binding, dict)
            else ""
        )
        == expected_generation_id,
        "identityAliasesConsistent": bool(
            isinstance(observed_binding, dict)
            and observed_binding.get("identityAliasesConsistent") is True
        ),
        "expectedArtifactCount": int(expected_binding.get("artifactCount") or 0),
        "observedArtifactCount": (
            int(observed_binding.get("artifactCount") or 0)
            if isinstance(observed_binding, dict)
            else 0
        ),
        "expectedArtifactInventorySha256": str(
            expected_binding.get("artifactInventorySha256") or ""
        ),
        "observedArtifactInventorySha256": (
            str(observed_binding.get("artifactInventorySha256") or "")
            if isinstance(observed_binding, dict)
            else ""
        ),
        "artifactInventoryExact": observed_inventory == expected_inventory,
        "expectedImmutableProjectionSha256": expected_projection,
        "observedImmutableProjectionSha256": observed_projection,
        "immutableProjectionExact": bool(expected_projection)
        and observed_projection == expected_projection,
    }
    evidence["passed"] = bool(
        evidence["generationHeaderExact"]
        and evidence["bodyGenerationExact"]
        and evidence["identityAliasesConsistent"]
        and evidence["artifactInventoryExact"]
        and evidence["immutableProjectionExact"]
    )
    return evidence


def parity_result(canonical: Mapping[str, Any], compatibility: Mapping[str, Any]) -> dict[str, Any]:
    canonical_identity = manifest_identity(canonical)
    compatibility_identity = manifest_identity(compatibility)
    canonical_trust = trust_projection(canonical)
    compatibility_trust = trust_projection(compatibility)
    canonical_inventory = artifact_inventory(canonical)
    compatibility_inventory = artifact_inventory(compatibility)
    canonical_coverage = desktop_tuple_coverage_binding(canonical, canonical_inventory)
    compatibility_coverage = desktop_tuple_coverage_binding(
        compatibility, compatibility_inventory
    )
    canonical_revocation = revocation_binding(canonical)
    compatibility_revocation = revocation_binding(compatibility)
    canonical_release_channel = release_channel_authority_binding(
        canonical, canonical_coverage
    )
    compatibility_release_channel = release_channel_authority_binding(
        compatibility, compatibility_coverage
    )
    canonical_contract_identity = contract_identity_binding(canonical)
    compatibility_contract_identity = contract_identity_binding(compatibility)
    canonical_release_proof = release_proof_binding(canonical, canonical_inventory)
    compatibility_release_proof = release_proof_binding(
        compatibility, compatibility_inventory
    )
    fields = (
        "status",
        "rolloutState",
        "supportabilityState",
        "publicTrustRolloutState",
        "publicTrustChannelId",
        "publicTrustPublicationStatus",
        "publicTrustSupportabilityState",
        "publicTrustPosture",
        "revocationStatus",
        "channelRevoked",
        "activeRevocationCount",
        "activeRevocations",
        "revocationSummary",
        "rolloutReason",
        "supportabilitySummary",
        "publicTrustSummary",
        "publicTrustRecommendedRouteCount",
        "publicTrustBlockedRouteCount",
        "publicTrustRevokedRouteCount",
        "publicTrustFallbackRecoveryRouteCount",
        "registryRolloutState",
        "registrySupportabilityState",
        "registryPublicTrustPosture",
        "registryPublicTrustSummary",
        "registryPublicationStatus",
        "registryStatus",
        "registryOwner",
        "registryChannelId",
        "registryReleaseVersion",
    )
    return {
        "passed": (
            canonical_identity == compatibility_identity
            and all(canonical_trust[field] == compatibility_trust[field] for field in fields)
            and canonical_inventory == compatibility_inventory
            and canonical_coverage == compatibility_coverage
            and canonical_revocation == compatibility_revocation
            and canonical_release_channel == compatibility_release_channel
            and canonical_contract_identity == compatibility_contract_identity
            and canonical_release_proof == compatibility_release_proof
        ),
        "canonicalIdentity": canonical_identity,
        "compatibilityIdentity": compatibility_identity,
        "canonicalTrust": canonical_trust,
        "compatibilityTrust": compatibility_trust,
        "canonicalArtifactInventorySha256": sha256_bytes(canonical_json_bytes(canonical_inventory)),
        "compatibilityArtifactInventorySha256": sha256_bytes(canonical_json_bytes(compatibility_inventory)),
        "artifactInventoryEqual": canonical_inventory == compatibility_inventory,
        "canonicalDesktopTupleCoverage": canonical_coverage,
        "compatibilityDesktopTupleCoverage": compatibility_coverage,
        "desktopTupleCoverageEqual": canonical_coverage == compatibility_coverage,
        "canonicalRevocationFacts": canonical_revocation,
        "compatibilityRevocationFacts": compatibility_revocation,
        "revocationFactsEqual": canonical_revocation == compatibility_revocation,
        "canonicalReleaseChannelAuthority": canonical_release_channel,
        "compatibilityReleaseChannelAuthority": compatibility_release_channel,
        "releaseChannelAuthorityEqual": canonical_release_channel
        == compatibility_release_channel,
        "canonicalContractIdentity": canonical_contract_identity,
        "compatibilityContractIdentity": compatibility_contract_identity,
        "contractIdentityEqual": canonical_contract_identity
        == compatibility_contract_identity,
        "canonicalReleaseProof": canonical_release_proof,
        "compatibilityReleaseProof": compatibility_release_proof,
        "releaseProofEqual": canonical_release_proof == compatibility_release_proof,
    }


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _validate_loopback_probe_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise PreflightError(f"loopback probe URL has an invalid port: {url}") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise PreflightError(f"probe URL is not exact HTTPS loopback: {url}")
    return parsed


def http_get_json(
    url: str,
    *,
    timeout_seconds: float = 3.0,
    ssl_context: ssl.SSLContext | None = None,
) -> tuple[int, dict[str, Any] | None, bytes, dict[str, tuple[str, ...]]]:
    expected_url = _validate_loopback_probe_url(url).geturl()
    request = urllib.request.Request(
        expected_url,
        headers={"Host": "chummer.run", "Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl_context),
        _NoRedirectHandler(),
    )
    final_url = expected_url
    response_headers: Any = None
    try:
        with opener.open(  # noqa: S310 - URL is validated as exact loopback above
            request,
            timeout=timeout_seconds,
        ) as response:
            body = response.read(4 * 1024 * 1024 + 1)
            status = int(response.status)
            final_url = response.geturl()
            response_headers = response.headers
    except urllib.error.HTTPError as exc:
        body = exc.read(4 * 1024 * 1024 + 1)
        status = int(exc.code)
        final_url = exc.geturl()
        response_headers = exc.headers
    if final_url != expected_url:
        raise PreflightError(
            f"loopback probe attempted to leave its exact URL: {expected_url} -> {final_url}"
        )
    if 300 <= status < 400:
        raise PreflightError(f"loopback probe refused redirect response {status}: {expected_url}")
    if len(body) > 4 * 1024 * 1024:
        raise PreflightError(f"loopback response exceeds bound: {url}")
    try:
        value = _strict_json_object_from_bytes(
            body,
            "loopback HTTPS response",
            Path(urllib.parse.urlsplit(expected_url).path or "/"),
        )
    except PreflightError:
        value = None
    generation_values = tuple(
        str(item).strip()
        for item in (
            response_headers.get_all("X-Chummer-Release-Generation", [])
            if response_headers is not None
            else []
        )
    )
    return (
        status,
        value if isinstance(value, dict) else None,
        body,
        {"x-chummer-release-generation": generation_values},
    )


def http_get_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float = 10.0,
    ssl_context: ssl.SSLContext | None = None,
) -> tuple[int, bytes, dict[str, tuple[str, ...]]]:
    if type(max_bytes) is not int or not 0 <= max_bytes <= MAX_RUNTIME_ARTIFACT_BYTES:
        raise PreflightError(
            f"loopback artifact byte bound must be between 0 and {MAX_RUNTIME_ARTIFACT_BYTES}"
        )
    expected_url = _validate_loopback_probe_url(url).geturl()
    request = urllib.request.Request(
        expected_url,
        headers={"Host": "chummer.run", "Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl_context),
        _NoRedirectHandler(),
    )
    final_url = expected_url
    response_headers: Any = None
    try:
        with opener.open(  # noqa: S310 - URL is validated as exact loopback above
            request,
            timeout=timeout_seconds,
        ) as response:
            body = response.read(max_bytes + 1)
            status = int(response.status)
            final_url = response.geturl()
            response_headers = response.headers
    except urllib.error.HTTPError as exc:
        body = exc.read(max_bytes + 1)
        status = int(exc.code)
        final_url = exc.geturl()
        response_headers = exc.headers
    if final_url != expected_url:
        raise PreflightError(
            f"loopback artifact probe attempted to leave its exact URL: "
            f"{expected_url} -> {final_url}"
        )
    if 300 <= status < 400:
        raise PreflightError(
            f"loopback artifact probe refused redirect response {status}: {expected_url}"
        )
    if len(body) > max_bytes:
        raise PreflightError(f"loopback artifact response exceeds bound: {url}")
    generation_values = tuple(
        str(item).strip()
        for item in (
            response_headers.get_all("X-Chummer-Release-Generation", [])
            if response_headers is not None
            else []
        )
    )
    return status, body, {"x-chummer-release-generation": generation_values}


def generation_artifact_delivery_evidence(
    base_url: str,
    ssl_context: ssl.SSLContext,
    expected_generation_id: str,
    expected_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not expected_generation_id:
        raise PreflightError("artifact proof requires one expected generation ID")
    rows: list[dict[str, Any]] = []
    for artifact in expected_inventory:
        artifact_id = str(artifact.get("id") or "")
        file_name = str(artifact.get("fileName") or "")
        expected_sha256 = str(artifact.get("sha256") or "")
        expected_size = artifact.get("sizeBytes")
        expected_path = (
            f"/downloads/g/{urllib.parse.quote(expected_generation_id, safe='')}/files/"
            f"{urllib.parse.quote(file_name, safe='')}"
        )
        observed_path = str(artifact.get("url") or "")
        access_class = str(artifact.get("installAccessClass") or "")
        if (
            not artifact_id
            or not file_name
            or Path(file_name).name != file_name
            or LOWER_SHA256_PATTERN.fullmatch(expected_sha256) is None
            or type(expected_size) is not int
            or expected_size < 0
            or expected_size > MAX_RUNTIME_ARTIFACT_BYTES
            or access_class != "open_public"
            or observed_path != expected_path
        ):
            raise PreflightError(
                "prepared artifact is not one exact generation-bound open-public file"
            )
        status, body, headers = http_get_bytes(
            f"{base_url}{observed_path}",
            max_bytes=expected_size,
            ssl_context=ssl_context,
        )
        generation_values = tuple(
            headers.get("x-chummer-release-generation", ())
        )
        observed_sha256 = sha256_bytes(body)
        row = {
            "artifactId": artifact_id,
            "path": observed_path,
            "status": status,
            "responseGenerationValues": list(generation_values),
            "generationHeaderExact": generation_values == (expected_generation_id,),
            "expectedSizeBytes": expected_size,
            "observedSizeBytes": len(body),
            "sizeExact": len(body) == expected_size,
            "expectedSha256": expected_sha256,
            "observedSha256": observed_sha256,
            "sha256Exact": secrets.compare_digest(observed_sha256, expected_sha256),
        }
        row["passed"] = bool(
            status == 200
            and row["generationHeaderExact"]
            and row["sizeExact"]
            and row["sha256Exact"]
        )
        rows.append(row)
    return {
        "passed": bool(rows) and all(row["passed"] for row in rows),
        "generationId": expected_generation_id,
        "artifactCount": len(rows),
        "artifacts": rows,
    }


def _readiness_rows_by_name(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        return {}
    rows: dict[str, Mapping[str, Any]] = {}
    for raw in value:
        if not isinstance(raw, dict):
            return {}
        name = str(raw.get("name") or "").strip()
        if not name or name in rows:
            return {}
        rows[name] = raw
    return rows


def _is_nonempty_token(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def deep_readiness_passes(status: int, payload: Mapping[str, Any] | None) -> bool:
    if status != 200 or not isinstance(payload, dict):
        return False
    hub = payload.get("hub")
    play = payload.get("playProjection")
    deployment = payload.get("deploymentIdentity")
    if not all(isinstance(value, dict) for value in (hub, play, deployment)):
        return False
    assert isinstance(hub, dict) and isinstance(play, dict) and isinstance(deployment, dict)
    shelf = hub.get("releaseShelf")
    if not isinstance(shelf, dict):
        return False
    checks = _readiness_rows_by_name(hub.get("checks"))
    required_checks = {
        "data_protection_storage",
        "install_linking_store",
        "release_shelf",
        "canonical_release_manifest",
    }
    checks_pass = bool(checks) and required_checks.issubset(checks) and all(
        row.get("passed") is True
        and str(row.get("status") or "").lower() == "pass"
        and _is_nonempty_token(row.get("code"))
        for row in checks.values()
    )
    deployment_digest = deployment.get("fullDeploymentDigestSha256")
    source_digest = deployment.get("sourceFingerprintSha256")
    return bool(
        payload.get("ready") is True
        and str(payload.get("status") or "").lower() == "ready"
        and hub.get("contractName") == "chummer.run.api.deep_readiness.v2"
        and hub.get("ready") is True
        and str(hub.get("status") or "").lower() == "pass"
        and hub.get("servingReady") is True
        and hub.get("publicationChecksConfigured") is True
        and checks_pass
        and shelf.get("mode") == "generation"
        and shelf.get("servingReady") is True
        and shelf.get("publicationChecksConfigured") is True
        and _is_nonempty_token(shelf.get("generationId"))
        and _is_nonempty_token(shelf.get("activationReceiptId"))
        and LOWER_SHA256_PATTERN.fullmatch(str(shelf.get("inventoryDigest") or ""))
        and play.get("ready") is True
        and deployment.get("ready") is True
        and deployment.get("code") == "overlay_identity_bound"
        and LOWER_SHA256_PATTERN.fullmatch(str(source_digest or ""))
        and LOWER_SHA256_PATTERN.fullmatch(str(deployment_digest or ""))
    )


def publication_readiness_passes(
    status: int,
    payload: Mapping[str, Any] | None,
) -> bool:
    if status != 200 or not isinstance(payload, dict):
        return False
    checks = _readiness_rows_by_name(payload.get("checks"))
    required = {
        "release_shelf_serving",
        "publication_probe_contract",
        "activation_protocol",
        "release_storage_admission",
    }
    return bool(
        payload.get("ready") is True
        and payload.get("checksConfigured") is True
        and str(payload.get("status") or "").lower() == "ready"
        and str(payload.get("code") or "").lower() == "publication_ready"
        and _is_nonempty_token(payload.get("generationId"))
        and _is_nonempty_token(payload.get("activationReceiptId"))
        and LOWER_SHA256_PATTERN.fullmatch(str(payload.get("inventoryDigest") or ""))
        and bool(checks)
        and required.issubset(checks)
        and all(
            row.get("ready") is True
            and str(row.get("status") or "").lower() == "ready"
            and _is_nonempty_token(row.get("code"))
            for row in checks.values()
        )
    )


def coherent_readiness_identity_evidence(
    deep_payload: Mapping[str, Any] | None,
    publication_payload: Mapping[str, Any] | None,
    shelf_evidence: Mapping[str, Any],
    overlay_identity: Mapping[str, Any],
) -> dict[str, Any]:
    expected_shelf = {
        "generationId": str(shelf_evidence.get("generationId") or ""),
        "activationReceiptId": str(shelf_evidence.get("activationReceiptId") or ""),
        "inventoryDigest": str(shelf_evidence.get("inventoryDigest") or ""),
    }
    expected_deployment = {
        "code": "overlay_identity_bound",
        "sourceFingerprintSha256": str(
            overlay_identity.get("sourceFingerprintSha256") or ""
        ),
        "fullDeploymentDigestSha256": str(
            overlay_identity.get("fullDeploymentDigestSha256") or ""
        ),
    }
    hub = deep_payload.get("hub") if isinstance(deep_payload, dict) else None
    deep_shelf = hub.get("releaseShelf") if isinstance(hub, dict) else None
    deployment = (
        deep_payload.get("deploymentIdentity")
        if isinstance(deep_payload, dict)
        else None
    )
    observed_deep_shelf = {
        key: str(deep_shelf.get(key) or "") if isinstance(deep_shelf, dict) else ""
        for key in expected_shelf
    }
    observed_publication = {
        key: (
            str(publication_payload.get(key) or "")
            if isinstance(publication_payload, dict)
            else ""
        )
        for key in expected_shelf
    }
    observed_deployment = {
        key: str(deployment.get(key) or "") if isinstance(deployment, dict) else ""
        for key in expected_deployment
    }
    expected_shapes = bool(
        _is_nonempty_token(expected_shelf["generationId"])
        and _is_nonempty_token(expected_shelf["activationReceiptId"])
        and LOWER_SHA256_PATTERN.fullmatch(expected_shelf["inventoryDigest"])
        and LOWER_SHA256_PATTERN.fullmatch(
            expected_deployment["sourceFingerprintSha256"]
        )
        and LOWER_SHA256_PATTERN.fullmatch(
            expected_deployment["fullDeploymentDigestSha256"]
        )
    )
    evidence = {
        "expectedShelf": expected_shelf,
        "deepShelf": observed_deep_shelf,
        "publicationShelf": observed_publication,
        "expectedDeployment": expected_deployment,
        "observedDeployment": observed_deployment,
        "deepMatchesPreparedShelf": observed_deep_shelf == expected_shelf,
        "publicationMatchesPreparedShelf": observed_publication == expected_shelf,
        "deepMatchesPublication": observed_deep_shelf == observed_publication,
        "deploymentMatchesOverlay": observed_deployment == expected_deployment,
    }
    evidence["passed"] = bool(
        expected_shapes
        and all(
            evidence[key]
            for key in (
                "deepMatchesPreparedShelf",
                "publicationMatchesPreparedShelf",
                "deepMatchesPublication",
                "deploymentMatchesOverlay",
            )
        )
    )
    return evidence


def manifest_matches_release_identity(
    payload: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        return manifest_identity(payload) == {
            "version": str(expected.get("version") or ""),
            "channel": str(expected.get("channel") or ""),
            "publishedAt": normalize_timestamp(expected.get("publishedAt")),
        }
    except (PreflightError, ValueError, TypeError):
        return False


@contextlib.contextmanager
def loopback_runtime(
    publish_root: Path,
    downloads_root: Path,
    state_root: Path,
    log_path: Path,
    tls: RuntimeTlsMaterial,
    postgres: PostgresRuntimeAuthority,
    dotnet_execution: DotnetExecution,
) -> Iterator[LoopbackRuntimeHandle]:
    port = free_loopback_port()
    ensure_owner_only_directory(state_root)
    data_protection = state_root / "data-protection-keyring"
    install_linking_root = state_root / "install-linking"
    release_sessions = state_root / "release-upload-sessions"
    runtime_temp = state_root / "tmp"
    runtime_home = state_root / "home"
    runtime_cache = state_root / "cache"
    runtime_config = state_root / "config"
    for isolated_root in (
        data_protection,
        install_linking_root,
        release_sessions,
        runtime_temp,
        runtime_home,
        runtime_cache,
        runtime_config,
    ):
        ensure_owner_only_directory(isolated_root)
    environment = sanitized_environment(
        {
            **production_loopback_origin_settings(),
            "ASPNETCORE_URLS": f"https://127.0.0.1:{port}",
            "ASPNETCORE_ENVIRONMENT": "Production",
            "ASPNETCORE_Kestrel__Certificates__Default__Path": str(tls.server_certificate),
            "ASPNETCORE_Kestrel__Certificates__Default__KeyPath": str(tls.server_key),
            "CHUMMER_DOWNLOADS_SOURCE_ROOT": str(downloads_root),
            "CHUMMER_PUBLIC_CANON_ROOT": str(publish_root / ".codex-design"),
            "CHUMMER_DATA_PROTECTION_KEYS_PATH": str(data_protection),
            "CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH": str(tls.data_protection_certificate),
            "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE": str(
                tls.data_protection_password_file
            ),
            "CHUMMER_INSTALL_LINKING_STORE_PATH": str(
                install_linking_root / "install-linking-store.json"
            ),
            "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE": str(
                postgres.runtime_connection_file
            ),
            "CHUMMER_RELEASE_UPLOAD_SESSION_ROOT": str(release_sessions),
            "CHUMMER_RELEASE_REGISTRY_CURRENT_URL": "",
            "CHUMMER_HUB_REGISTRY_BASE_URL": "",
            "CHUMMER_HUB_GOOGLE_AUTH_ENABLED": "false",
            "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
            "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
            # Every unconfigured file-backed store falls back through
            # Path.GetTempPath().  Override the process temp/home/XDG roots so the
            # preflight cannot read or mutate another test run's state.
            "TMPDIR": str(runtime_temp),
            "TMP": str(runtime_temp),
            "TEMP": str(runtime_temp),
            "HOME": str(runtime_home),
            "XDG_CACHE_HOME": str(runtime_cache),
            "XDG_CONFIG_HOME": str(runtime_config),
            "DOTNET_ROOT": str(dotnet_execution.root),
            "DOTNET_HOST_PATH": str(dotnet_execution.host),
            "DOTNET_MULTILEVEL_LOOKUP": "0",
            "DOTNET_CLI_HOME": str(runtime_home),
            "PATH": "/usr/bin:/bin",
        }
    )
    if "CHUMMER_ENABLE_HTTPS_REDIRECTION" in environment:
        raise PreflightError("production loopback runtime must not disable HTTPS redirection")
    ssl_context = ssl.create_default_context(cafile=str(tls.ca_certificate))
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    runtime_evidence = {
        "httpsListener": True,
        "httpsPeerVerificationRequired": True,
        "listenerLoopbackOnly": environment["ASPNETCORE_URLS"].startswith(
            "https://127.0.0.1:"
        ),
        "productionEnvironment": environment["ASPNETCORE_ENVIRONMENT"] == "Production",
        "httpsRedirectionEnabled": "CHUMMER_ENABLE_HTTPS_REDIRECTION" not in environment,
        "dataProtectionPathExplicit": bool(environment["CHUMMER_DATA_PROTECTION_KEYS_PATH"]),
        "dataProtectionCertificateOwnerOnly": owner_only_file_passes(
            tls.data_protection_certificate
        ),
        "dataProtectionPasswordOwnerOnly": owner_only_file_passes(
            tls.data_protection_password_file
        ),
        "installLinkingStoreExplicit": bool(environment["CHUMMER_INSTALL_LINKING_STORE_PATH"]),
        "postgresConnectionFileOwnerOnly": owner_only_file_passes(
            postgres.runtime_connection_file
        ),
        "releaseSessionRootExplicit": bool(environment["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"]),
        "layoutV1Required": environment["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] == "true",
        "initialMigrationDisabled": environment[
            "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"
        ] == "false",
        "writeIsolationEnforced": True,
        "landlockAbi": dotnet_execution.landlock_abi,
    }
    # Runtime diagnostics may contain connection strings. The probe is judged
    # through structured HTTPS responses and process state, so discard console
    # output instead of ever writing a secret-bearing runtime log.
    _ = log_path
    process = subprocess.Popen(
        list(
            isolated_dotnet_argv(
                dotnet_execution,
                (str(dotnet_execution.host), "Chummer.Run.Api.dll"),
                (state_root,),
                (postgres.host_port,),
                (port,),
            )
        ),
        cwd=publish_root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        yield LoopbackRuntimeHandle(process, port, ssl_context, runtime_evidence)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)


def _data_protection_keyring_evidence(path: Path) -> dict[str, Any]:
    key_files = sorted(path.glob("key-*.xml")) if path.is_dir() else []
    encrypted = True
    hashes: list[str] = []
    for key_file in key_files:
        if key_file.is_symlink() or not key_file.is_file():
            encrypted = False
            continue
        payload = key_file.read_bytes()
        hashes.append(sha256_bytes(payload))
        if len(payload) > MAX_DATA_PROTECTION_KEY_BYTES:
            encrypted = False
            continue
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            encrypted = False
            continue

        local_name = lambda tag: str(tag).rsplit("}", 1)[-1]
        if local_name(root.tag) != "key":
            encrypted = False
            continue
        encrypted_secrets = [
            child
            for child in list(root)
            if local_name(child.tag) == "encryptedSecret"
        ]
        plaintext_descriptors = [
            child
            for child in list(root)
            if local_name(child.tag) in {"descriptor", "secret"}
        ]
        if len(encrypted_secrets) != 1 or plaintext_descriptors:
            encrypted = False
            continue
        encrypted_secret = encrypted_secrets[0]
        decryptor_type = str(encrypted_secret.attrib.get("decryptorType") or "").strip()
        cipher_values = [
            str(node.text or "").strip()
            for node in encrypted_secret.iter()
            if local_name(node.tag) == "CipherValue"
        ]
        if not decryptor_type or not cipher_values or not all(cipher_values):
            encrypted = False
    return {
        "keyCount": len(key_files),
        "encryptedAtRest": bool(key_files) and encrypted,
        "keySetSha256": sha256_bytes(canonical_json_bytes(hashes)),
    }


def probe_runtime(
    candidate_root: Path,
    publish_root: Path,
    postgres_tool_root: Path,
    generation_tool: Path,
    live_envelope_snapshot: LiveEnvelopeSnapshot,
    live_envelope_binding: Mapping[str, Any],
    overlay_identity: Mapping[str, Any],
    work_root: Path,
    expected_postgres_image_id: str,
    dotnet_execution: DotnetExecution,
    system_tools: PinnedSystemTools,
) -> dict[str, Any]:
    ensure_owner_only_directory(work_root)
    source_hashes = {
        "canonical": live_envelope_snapshot.canonical.sha256,
        "compatibility": live_envelope_snapshot.compatibility.sha256,
    }
    source_template_binding = {
        "canonicalSha256": source_hashes["canonical"],
        "expectedCanonicalSha256": str(
            live_envelope_binding.get("canonicalSha256") or ""
        ),
        "compatibilitySha256": source_hashes["compatibility"],
        "expectedCompatibilitySha256": str(
            live_envelope_binding.get("compatibilitySha256") or ""
        ),
        "liveEnvelopeBindingSha256": str(
            live_envelope_binding.get("bindingSha256") or ""
        ),
    }
    source_template_binding["passed"] = bool(
        live_envelope_binding.get("passed") is True
        and source_template_binding["liveEnvelopeBindingSha256"]
        and source_template_binding["canonicalSha256"]
        == source_template_binding["expectedCanonicalSha256"]
        and source_template_binding["compatibilitySha256"]
        == source_template_binding["expectedCompatibilitySha256"]
    )
    result: dict[str, Any] = {
        "passed": False,
        "started": False,
        "productionEnvironment": True,
        "productionMutation": False,
        "sourceTemplateSha256": source_hashes,
        "sourceTemplateBinding": source_template_binding,
        "httpsPeerVerified": False,
        "aliveThroughFinalBoundSample": False,
    }
    log_path = work_root / "runtime.log"
    state_root = work_root / "state"
    secret_root = work_root / "secrets"
    postgres_evidence: dict[str, Any] = {}
    tls_commands: list[dict[str, Any]] = []
    generation_root: Path | None = None
    fixture_hashes_before: dict[str, str] = {}
    generation_closure_before: dict[str, Any] = {}
    try:
        downloads, shelf_evidence = prepare_runtime_release_shelf(
            generation_tool,
            work_root / "release-shelf",
            live_envelope_snapshot.canonical.payload,
            live_envelope_snapshot.compatibility.payload,
        )
        result["releaseShelf"] = shelf_evidence
        generation_root = downloads / "generations" / str(shelf_evidence["generationId"])
        fixture_hashes_before = {
            "canonical": sha256_file(generation_root / CANONICAL),
            "compatibility": sha256_file(generation_root / COMPATIBILITY),
        }
        result["fixtureSha256Before"] = fixture_hashes_before
        generation_closure_before = build_topology_closure_manifest(
            RUNTIME_GENERATION_CLOSURE_SCHEMA,
            (("generation", generation_root),),
            excluded_directories=(),
        )
        result["generationClosureBefore"] = generation_closure_before
        tls = generate_runtime_tls_material(
            secret_root,
            tls_commands,
            system_tools.openssl,
        )
        result["tlsProvisioning"] = {
            "passed": all(row.get("passed") is True for row in tls_commands),
            "commands": tls_commands,
            "serverKeyOwnerOnly": owner_only_file_passes(tls.server_key),
            "dataProtectionCertificateOwnerOnly": owner_only_file_passes(
                tls.data_protection_certificate
            ),
            "dataProtectionPasswordOwnerOnly": owner_only_file_passes(
                tls.data_protection_password_file
            ),
        }
        with isolated_postgres_authority(
            secret_root=secret_root,
            tls=tls,
            postgres_tool_root=postgres_tool_root,
            work_root=work_root / "postgres-provisioning",
            evidence=postgres_evidence,
            expected_image_id=expected_postgres_image_id,
            dotnet_execution=dotnet_execution,
            docker_host=system_tools.docker,
        ) as postgres:
            with loopback_runtime(
                publish_root,
                downloads,
                state_root,
                log_path,
                tls,
                postgres,
                dotnet_execution,
            ) as runtime:
                result["runtimeEnvelope"] = runtime.evidence
                base = f"https://127.0.0.1:{runtime.port}"
                deadline = time.monotonic() + 60
                probe_started = time.monotonic()
                readiness_attempts = 0
                last_error: str | None = None
                health_status = 0
                health_payload: dict[str, Any] | None = None
                ready_status = 0
                ready_payload: dict[str, Any] | None = None
                ready_body = b""
                publication_status = 0
                publication_payload: dict[str, Any] | None = None
                publication_body = b""
                identity_evidence: dict[str, Any] = {"passed": False}
                coherent_sample_observed = False
                while time.monotonic() < deadline and runtime.process.poll() is None:
                    readiness_attempts += 1
                    # Never combine a successful response from an earlier polling
                    # attempt with a later partial attempt.  A coherent sample is
                    # all-or-nothing within one iteration.
                    health_status = 0
                    health_payload = None
                    ready_status = 0
                    ready_payload = None
                    ready_body = b""
                    publication_status = 0
                    publication_payload = None
                    publication_body = b""
                    identity_evidence = {"passed": False}
                    try:
                        health_status, health_payload, _, _ = http_get_json(
                            f"{base}/api/health",
                            ssl_context=runtime.ssl_context,
                        )
                        if health_status == 200:
                            result["started"] = True
                            result["httpsPeerVerified"] = True
                            ready_status, ready_payload, ready_body, _ = http_get_json(
                                f"{base}/api/ready",
                                ssl_context=runtime.ssl_context,
                            )
                            publication_status, publication_payload, publication_body, _ = (
                                http_get_json(
                                    f"{base}/api/ready/publication",
                                    ssl_context=runtime.ssl_context,
                                )
                            )
                            identity_evidence = coherent_readiness_identity_evidence(
                                ready_payload,
                                publication_payload,
                                shelf_evidence,
                                overlay_identity,
                            )
                            if (
                                deep_readiness_passes(ready_status, ready_payload)
                                and publication_readiness_passes(
                                    publication_status,
                                    publication_payload,
                                )
                                and identity_evidence["passed"]
                            ):
                                coherent_sample_observed = True
                                break
                    except (OSError, ssl.SSLError, PreflightError) as exc:
                        last_error = str(exc)
                    time.sleep(0.25)
                result["processExitCodeAtProbe"] = runtime.process.poll()
                result["health"] = {"status": health_status, "payload": health_payload}
                result["readinessProbe"] = {
                    "attempts": readiness_attempts,
                    "durationSeconds": round(time.monotonic() - probe_started, 3),
                    "boundedDeadlineSeconds": 60,
                }
                result["ready"] = {
                    "status": ready_status,
                    "passed": deep_readiness_passes(ready_status, ready_payload),
                    "payload": ready_payload,
                    "bodySha256": sha256_bytes(ready_body),
                }
                result["publicationReady"] = {
                    "status": publication_status,
                    "passed": publication_readiness_passes(
                        publication_status,
                        publication_payload,
                    ),
                    "payload": publication_payload,
                    "bodySha256": sha256_bytes(publication_body),
                }
                result["readinessIdentity"] = identity_evidence
                result["coherentReadinessSampleObserved"] = coherent_sample_observed
                if not result["started"]:
                    result["error"] = last_error or "runtime did not become healthy before deadline"
                elif not (
                    result["ready"]["passed"]
                    and result["publicationReady"]["passed"]
                    and identity_evidence["passed"]
                    and coherent_sample_observed
                ):
                    result["error"] = (
                        last_error
                        or "runtime did not expose one coherent deep/publication identity before deadline"
                    )
                else:
                    canonical_status, canonical_payload, canonical_body, canonical_headers = http_get_json(
                        f"{base}/downloads/{CANONICAL}",
                        ssl_context=runtime.ssl_context,
                    )
                    compatibility_status, compatibility_payload, compatibility_body, compatibility_headers = http_get_json(
                        f"{base}/downloads/{COMPATIBILITY}",
                        ssl_context=runtime.ssl_context,
                    )
                    for name, body in (
                        ("served-canonical.json", canonical_body),
                        ("served-compatibility.json", compatibility_body),
                    ):
                        response_path = work_root / name
                        write_owner_only_file(response_path, body)
                    expected_release_identity = shelf_evidence["releaseIdentity"]
                    expected_generation_id = str(shelf_evidence["generationId"])
                    prepared_bindings = shelf_evidence["preparedManifestBindings"]
                    canonical_binding = served_manifest_binding_evidence(
                        canonical_payload,
                        canonical_headers,
                        expected_generation_id,
                        prepared_bindings["canonical"],
                    )
                    compatibility_binding = served_manifest_binding_evidence(
                        compatibility_payload,
                        compatibility_headers,
                        expected_generation_id,
                        prepared_bindings["compatibility"],
                    )
                    result["canonical"] = {
                        "status": canonical_status,
                        "bodySha256": sha256_bytes(canonical_body),
                        "bodyPath": str(work_root / "served-canonical.json"),
                        "trust": trust_projection(canonical_payload or {}),
                        "truthFloorPassed": trust_floor_passes(canonical_payload or {}),
                        "matchesPreparedReleaseIdentity": manifest_matches_release_identity(
                            canonical_payload,
                            expected_release_identity,
                        ),
                        "preparedGenerationBinding": canonical_binding,
                    }
                    result["compatibility"] = {
                        "status": compatibility_status,
                        "bodySha256": sha256_bytes(compatibility_body),
                        "bodyPath": str(work_root / "served-compatibility.json"),
                        "trust": trust_projection(compatibility_payload or {}),
                        "truthFloorPassed": trust_floor_passes(compatibility_payload or {}),
                        "matchesPreparedReleaseIdentity": manifest_matches_release_identity(
                            compatibility_payload,
                            expected_release_identity,
                        ),
                        "preparedGenerationBinding": compatibility_binding,
                    }
                    result["parity"] = parity_result(
                        canonical_payload or {},
                        compatibility_payload or {},
                    )
                    result["artifactDelivery"] = generation_artifact_delivery_evidence(
                        base,
                        runtime.ssl_context,
                        expected_generation_id,
                        prepared_bindings["canonical"]["artifactInventory"],
                    )
                    post_ready_status, post_ready_payload, post_ready_body, _ = http_get_json(
                        f"{base}/api/ready",
                        ssl_context=runtime.ssl_context,
                    )
                    (
                        post_publication_status,
                        post_publication_payload,
                        post_publication_body,
                        _,
                    ) = http_get_json(
                        f"{base}/api/ready/publication",
                        ssl_context=runtime.ssl_context,
                    )
                    post_identity = coherent_readiness_identity_evidence(
                        post_ready_payload,
                        post_publication_payload,
                        shelf_evidence,
                        overlay_identity,
                    )
                    result["postManifestReadiness"] = {
                        "passed": bool(
                            deep_readiness_passes(
                                post_ready_status,
                                post_ready_payload,
                            )
                            and publication_readiness_passes(
                                post_publication_status,
                                post_publication_payload,
                            )
                            and post_identity["passed"]
                        ),
                        "readyStatus": post_ready_status,
                        "readyBodySha256": sha256_bytes(post_ready_body),
                        "publicationStatus": post_publication_status,
                        "publicationBodySha256": sha256_bytes(
                            post_publication_body
                        ),
                        "identity": post_identity,
                    }
                    final_process_exit = runtime.process.poll()
                    result["processExitCodeAfterFinalProbe"] = final_process_exit
                    result["aliveThroughFinalBoundSample"] = final_process_exit is None
                    result["dataProtectionKeyring"] = _data_protection_keyring_evidence(
                        state_root / "data-protection-keyring"
                    )
    except Exception as exc:  # retain bounded, fail-closed disposable-envelope evidence
        result["error"] = str(exc)
    finally:
        result["postgresAuthority"] = postgres_evidence
        fixture_hashes_after: dict[str, str] = {}
        try:
            if generation_root is not None and generation_root.is_dir():
                fixture_hashes_after = {
                    "canonical": sha256_file(generation_root / CANONICAL),
                    "compatibility": sha256_file(generation_root / COMPATIBILITY),
                }
        except Exception as exc:
            result["fixtureIntegritySamplingError"] = str(exc)
        result["fixtureSha256After"] = fixture_hashes_after
        result["preparedManifestBytesUnchanged"] = bool(
            fixture_hashes_before and fixture_hashes_before == fixture_hashes_after
        )
        generation_closure_after: dict[str, Any] = {}
        try:
            if generation_root is not None and generation_root.is_dir():
                generation_closure_after = build_topology_closure_manifest(
                    RUNTIME_GENERATION_CLOSURE_SCHEMA,
                    (("generation", generation_root),),
                    excluded_directories=(),
                )
        except Exception as exc:
            result["generationClosureSamplingError"] = str(exc)
        result["generationClosureAfter"] = generation_closure_after
        result["preparedGenerationWasUnchanged"] = bool(
            generation_closure_before
            and generation_closure_before == generation_closure_after
        )
        try:
            result["credentialsRemoved"] = _secure_remove_tree(secret_root)
        except Exception as exc:
            result["credentialsRemoved"] = False
            result["credentialCleanupError"] = str(exc)
        try:
            result["isolatedRuntimeStateRemoved"] = _secure_remove_tree(state_root)
        except Exception as exc:
            result["isolatedRuntimeStateRemoved"] = False
            result["runtimeStateCleanupError"] = str(exc)
    result["runtimeConsoleOutputPersisted"] = False
    runtime_envelope = result.get("runtimeEnvelope")
    result["passed"] = bool(
        not result.get("error")
        and result.get("started")
        and result.get("httpsPeerVerified")
        and result.get("aliveThroughFinalBoundSample")
        and isinstance(runtime_envelope, dict)
        and all(runtime_envelope.values())
        and result.get("ready", {}).get("passed")
        and result.get("publicationReady", {}).get("passed")
        and result.get("readinessIdentity", {}).get("passed")
        and result.get("coherentReadinessSampleObserved")
        and result.get("sourceTemplateBinding", {}).get("passed")
        and result.get("postManifestReadiness", {}).get("passed")
        and result.get("dataProtectionKeyring", {}).get("encryptedAtRest")
        and result.get("canonical", {}).get("status") == 200
        and result.get("canonical", {}).get("truthFloorPassed")
        and result.get("canonical", {}).get("matchesPreparedReleaseIdentity")
        and result.get("canonical", {})
        .get("preparedGenerationBinding", {})
        .get("passed")
        and result.get("compatibility", {}).get("status") == 200
        and result.get("compatibility", {}).get("truthFloorPassed")
        and result.get("compatibility", {}).get("matchesPreparedReleaseIdentity")
        and result.get("compatibility", {})
        .get("preparedGenerationBinding", {})
        .get("passed")
        and result.get("parity", {}).get("passed")
        and result.get("artifactDelivery", {}).get("passed")
        and result.get("preparedManifestBytesUnchanged")
        and result.get("preparedGenerationWasUnchanged")
        and postgres_evidence.get("passed")
        and postgres_evidence.get("cleanupPassed")
        and result.get("credentialsRemoved")
        and result.get("isolatedRuntimeStateRemoved")
        and result.get("releaseShelf", {}).get("passed")
        and result.get("tlsProvisioning", {}).get("passed")
    )
    return result


def _load_generation_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("canonical_writer_generation_preflight", path)
    if spec is None or spec.loader is None:
        raise PreflightError(f"cannot import generation tool: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_generation_fixture(
    root: Path,
    version: str,
    artifact_bytes: bytes,
    *,
    channel: str = "preview",
    published_at: str = "2026-07-16T12:00:00Z",
) -> Path:
    files = root / "files"
    files.mkdir(parents=True)
    artifact = files / "preflight-installer.exe"
    artifact.write_bytes(artifact_bytes)
    digest = sha256_file(artifact)
    common = {
        "version": version,
        "channel": channel,
        "publishedAt": published_at,
        "generatedAt": published_at,
        "generated_at": published_at,
        "contractName": "Chummer.Hub.Registry.Contracts",
        "contract_name": "Chummer.Hub.Registry.Contracts",
        "status": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "releaseProof": {
            "status": "passed",
            "generatedAt": published_at,
            "baseUrl": "https://chummer.run",
            "journeysPassed": list(REQUIRED_RELEASE_PROOF_JOURNEYS),
            "proofRoutes": [
                *REQUIRED_RELEASE_PROOF_ROUTES,
                "/downloads/install/preflight-installer",
            ],
            "uiLocalizationReleaseGate": {
                "status": "pass",
                "generatedAt": published_at,
            },
        },
        "publicTrustMetrics": {
            "proofFreshness": {"status": "stale"},
            "releaseChannel": {
                "channelId": channel,
                "publicationStatus": "published",
                "rolloutState": "public_release_review_required",
                "supportabilityState": "review_required",
                "posture": "blocked",
                "recommendedRouteCount": 0,
                "blockedRouteCount": 1,
                "revokedRouteCount": 0,
                "fallbackRecoveryRouteCount": 0,
            },
            "revocationFacts": {
                "status": "clear",
                "channelRevoked": False,
                "activeRevocationCount": 0,
                "activeRevocations": [],
                "summary": f"No channel or route revocations are active on channel {channel}.",
            },
        },
        "registryBoundaryCoverage": {
            "status": "closed",
            "owner": "chummer6-hub-registry",
            "channelId": channel,
            "releaseVersion": version,
            "releaseChannel": {
                "publicationStatus": "published",
                "rolloutState": "public_release_review_required",
                "supportabilityState": "review_required",
                "publicTrustPosture": "blocked",
                "desktopTupleComplete": True,
                "promotedInstallerTupleCount": 1,
                "desktopRouteTruthCount": 1,
            }
        },
        "desktopTupleCoverage": {
            "requiredDesktopPlatforms": ["desktop"],
            "requiredDesktopHeads": ["preflight"],
            "requiredDesktopPlatformHeadRidTuples": ["preflight:test-x64:desktop"],
            "promotedPlatformHeadRidTuples": ["preflight:test-x64:desktop"],
            "missingRequiredPlatforms": [],
            "missingRequiredHeads": [],
            "missingRequiredPlatformHeadPairs": [],
            "missingRequiredPlatformHeadRidTuples": [],
            "promotedInstallerTuples": [
                {
                    "tupleId": "preflight:desktop:test-x64",
                    "artifactId": "preflight-installer",
                    "kind": "installer",
                    "head": "preflight",
                    "arch": "x64",
                    "platform": "desktop",
                    "rid": "test-x64",
                }
            ],
            "desktopRouteTruth": [
                {
                    "tupleId": "preflight:desktop:test-x64",
                    "artifactId": "preflight-installer",
                    "routeRole": "primary",
                    "promotionState": "promoted",
                    "promotionReasonCode": "installer_smoke_and_release_proof_passed",
                    "revokeState": "not_revoked",
                    "revokeSource": "none",
                    "revokeReasonCode": "no_registry_revoke_marker",
                    "installPosture": "installer_first",
                    "rollbackState": "fallback_available",
                    "updateEligibility": "eligible",
                    "publicInstallRoute": "/downloads/install/preflight-installer",
                    "head": "preflight",
                    "arch": "x64",
                    "platform": "desktop",
                    "rid": "test-x64",
                }
            ],
            "complete": True,
        },
    }
    canonical = {
        **common,
        "releaseVersion": version,
        "artifacts": [
            {
                "artifactId": "preflight-installer",
                "fileName": artifact.name,
                "downloadUrl": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": len(artifact_bytes),
                "installAccessClass": "open_public",
                "kind": "installer",
                "head": "preflight",
                "arch": "x64",
                "platform": "desktop",
                "rid": "test-x64",
                "compatibilityState": "compatible",
                "compatibilityReason": None,
            }
        ],
    }
    compatibility = {
        **common,
        "downloads": [
            {
                "id": "preflight-installer",
                "fileName": artifact.name,
                "url": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": len(artifact_bytes),
                "installAccessClass": "open_public",
                "kind": "installer",
                "head": "preflight",
                "arch": "x64",
                "platform": "desktop",
                "rid": "test-x64",
                "compatibilityState": "compatible",
                "compatibilityReason": None,
            }
        ],
    }
    atomic_write_json(root / CANONICAL, canonical)
    atomic_write_json(root / COMPATIBILITY, compatibility)
    return root


def prepare_runtime_release_shelf(
    generation_tool: Path,
    work_root: Path,
    canonical_template: Mapping[str, Any],
    compatibility_template: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    module = _load_generation_module(generation_tool)
    canonical_identity = manifest_identity(canonical_template)
    compatibility_identity = manifest_identity(compatibility_template)
    if canonical_identity != compatibility_identity:
        raise PreflightError("runtime shelf templates do not have one release identity")
    candidate = _write_generation_fixture(
        work_root / "candidate",
        canonical_identity["version"],
        b"canonical-writer-production-envelope-preflight",
        channel=canonical_identity["channel"],
        published_at=canonical_identity["publishedAt"],
    )
    # The server must lower this deliberately optimistic, stale-proof input to the
    # review-required truth floor without rewriting the immutable generation bytes.
    make_optimistic_copy(candidate / CANONICAL, candidate / CANONICAL)
    make_optimistic_copy(candidate / COMPATIBILITY, candidate / COMPATIBILITY)
    candidate_hashes = {
        "canonical": sha256_file(candidate / CANONICAL),
        "compatibility": sha256_file(candidate / COMPATIBILITY),
    }
    shelf = work_root / "shelf"
    pointer = module.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="canonical-writer-production-envelope",
        activated_at=utc_now(),
        activation_receipt_id="canonical-writer-production-envelope",
    )
    writer_policy = shelf / module.WRITER_POLICY
    atomic_write_json(
        writer_policy,
        {
            "schemaVersion": module.SERVER_WRITER_POLICY_SCHEMA,
            "mode": module.SERVER_WRITER_POLICY_MODE,
        },
    )
    if not owner_only_file_passes(writer_policy):
        raise PreflightError("runtime release shelf writer policy is not owner-only")
    state, generation_root, resolved = module.resolve_shelf_root(shelf)
    passed = bool(
        state == "generation"
        and generation_root.name == pointer["generationId"]
        and resolved is not None
        and (shelf / module.LAYOUT_MARKER).is_file()
        and (shelf / module.CURRENT_POINTER).is_file()
    )
    if not passed:
        raise PreflightError("runtime release shelf layout-v1 activation failed")
    prepared_canonical = read_json_object(
        generation_root / CANONICAL,
        "prepared canonical generation manifest",
    )
    prepared_compatibility = read_json_object(
        generation_root / COMPATIBILITY,
        "prepared compatibility generation manifest",
    )
    prepared_bindings = {
        "canonical": prepared_manifest_binding(prepared_canonical),
        "compatibility": prepared_manifest_binding(prepared_compatibility),
    }
    if (
        not prepared_bindings["canonical"]["artifactInventory"]
        or prepared_bindings["canonical"]["artifactInventory"]
        != prepared_bindings["compatibility"]["artifactInventory"]
        or prepared_bindings["canonical"]["generationId"] != pointer["generationId"]
        or prepared_bindings["compatibility"]["generationId"] != pointer["generationId"]
    ):
        raise PreflightError(
            "prepared generation manifests do not have one non-empty immutable binding"
        )
    return shelf, {
        "passed": True,
        "layout": "v1",
        "generationId": pointer["generationId"],
        "activationReceiptId": pointer["activationReceiptId"],
        "inventoryDigest": str(pointer["inventoryDigest"]).removeprefix("sha256:"),
        "releaseIdentity": canonical_identity,
        "fixtureDerivation": "identity-bound-synthetic-production-envelope",
        "preparedManifestBindings": prepared_bindings,
        "optimisticFixtureSha256Before": candidate_hashes,
        "writerPolicyOwnerOnly": True,
        "writerPolicyMode": module.SERVER_WRITER_POLICY_MODE,
    }


def _replace_pointer_atomically(path: Path, pointer_bytes: bytes) -> None:
    descriptor, raw_temp = tempfile.mkstemp(prefix=".current.rollback.", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(pointer_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


def generation_rollback_probe(generation_tool: Path, work_root: Path) -> dict[str, Any]:
    module = _load_generation_module(generation_tool)
    shelf = work_root / "shelf"
    candidate_a = _write_generation_fixture(work_root / "candidate-a", "preflight-a", b"artifact-a")
    pointer_a = module.activate_filesystem(
        candidate_a,
        shelf,
        initialize_layout=True,
        generation_id="preflight-generation-a",
        activated_at="2026-07-16T12:01:00Z",
        activation_receipt_id="preflight-activation-a",
    )
    pointer_a_bytes = (shelf / module.CURRENT_POINTER).read_bytes()
    generation_a_root = (
        shelf / module.GENERATIONS_DIRECTORY / "preflight-generation-a"
    )
    generation_a_before = build_topology_closure_manifest(
        RUNTIME_GENERATION_CLOSURE_SCHEMA,
        (("generation", generation_a_root),),
        excluded_directories=(),
    )
    candidate_b = _write_generation_fixture(work_root / "candidate-b", "preflight-b", b"artifact-b")
    pointer_b = module.activate_filesystem(
        candidate_b,
        shelf,
        initialize_layout=False,
        generation_id="preflight-generation-b",
        activated_at="2026-07-16T12:02:00Z",
        activation_receipt_id="preflight-activation-b",
    )
    pointer_b_bytes = (shelf / module.CURRENT_POINTER).read_bytes()
    state_b, root_b, resolved_b = module.resolve_shelf_root(shelf)
    generation_a_after_activation = build_topology_closure_manifest(
        RUNTIME_GENERATION_CLOSURE_SCHEMA,
        (("generation", generation_a_root),),
        excluded_directories=(),
    )
    _replace_pointer_atomically(shelf / module.CURRENT_POINTER, pointer_a_bytes)
    state_rollback, root_rollback, resolved_rollback = module.resolve_shelf_root(shelf)
    generation_a_after_rollback = build_topology_closure_manifest(
        RUNTIME_GENERATION_CLOSURE_SCHEMA,
        (("generation", generation_a_root),),
        excluded_directories=(),
    )
    rollback_generation_immutable = bool(
        generation_a_before
        == generation_a_after_activation
        == generation_a_after_rollback
    )
    _replace_pointer_atomically(shelf / module.CURRENT_POINTER, pointer_b_bytes)
    state_restored, root_restored, resolved_restored = module.resolve_shelf_root(shelf)
    passed = (
        state_b == state_rollback == state_restored == "generation"
        and root_b.name == pointer_b["generationId"]
        and root_rollback.name == pointer_a["generationId"]
        and root_restored.name == pointer_b["generationId"]
        and resolved_b is not None
        and resolved_rollback is not None
        and resolved_restored is not None
        and rollback_generation_immutable
    )
    return {
        "passed": passed,
        "productionMutation": False,
        "atomicCommitPrimitive": "fsync temporary current.json then os.replace and parent fsync",
        "generationA": pointer_a["generationId"],
        "generationB": pointer_b["generationId"],
        "observedAfterActivation": root_b.name,
        "observedAfterRollback": root_rollback.name,
        "observedAfterRestore": root_restored.name,
        "generationABytesUnchanged": rollback_generation_immutable,
        "generationAClosureSha256Before": generation_a_before["closureSha256"],
        "generationAClosureSha256AfterActivation": generation_a_after_activation[
            "closureSha256"
        ],
        "generationAClosureSha256AfterRollback": generation_a_after_rollback[
            "closureSha256"
        ],
        "pointerASha256": sha256_bytes(pointer_a_bytes),
        "pointerBSha256": sha256_bytes(pointer_b_bytes),
    }


def _copy_runtime_content(candidate_root: Path, workspace_root: Path, publish_root: Path) -> None:
    design = candidate_root / ".codex-design"
    if design.is_dir():
        shutil.copytree(design, publish_root / ".codex-design", dirs_exist_ok=True)
    black_ledger = workspace_root / "chummer-hub-registry" / "black-ledger"
    if black_ledger.is_dir():
        shutil.copytree(black_ledger, publish_root / "black-ledger", dirs_exist_ok=True)


def build_live_envelope_snapshot_closure(root: Path) -> dict[str, Any]:
    expected = {
        "receipt": root / "verification.receipt.json",
        "canonical": root / CANONICAL,
        "compatibility": root / COMPATIBILITY,
    }
    try:
        actual_names = {path.name for path in root.iterdir()}
    except OSError as exc:
        raise PreflightError(f"live envelope snapshot is unreadable: {root} ({exc})") from exc
    if actual_names != {path.name for path in expected.values()}:
        raise PreflightError("live envelope snapshot contains an unexpected entry set")
    for label, path in expected.items():
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or path.is_symlink()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o400
        ):
            raise PreflightError(f"live envelope snapshot {label} is not owner-read-only")
    return build_closure_manifest(
        LIVE_ENVELOPE_SNAPSHOT_SCHEMA,
        tuple(expected.items()),
        excluded_directories=(),
    )


def materialize_live_envelope_snapshot(
    canonical_template: Path,
    compatibility_template: Path,
    receipt_path: Path,
    expected_receipt_sha256: str,
    snapshot_root: Path,
) -> LiveEnvelopeSnapshot:
    receipt, receipt_raw, receipt_sha256, receipt_source = read_strict_json_byte_snapshot(
        receipt_path,
        "live envelope receipt",
        expected_sha256=expected_receipt_sha256,
    )
    source = receipt.get("source")
    if not isinstance(source, dict):
        raise PreflightError("live envelope receipt has no source binding")
    expected_canonical = require_lower_sha256(
        source.get("afterSha256"),
        "live envelope receipt canonical source SHA-256",
    )
    expected_compatibility = require_lower_sha256(
        source.get("releasesSourceSha256"),
        "live envelope receipt compatibility source SHA-256",
    )
    canonical, canonical_raw, canonical_sha256, canonical_source = (
        read_strict_json_byte_snapshot(
            canonical_template,
            "canonical template",
            expected_sha256=expected_canonical,
        )
    )
    compatibility, compatibility_raw, compatibility_sha256, compatibility_source = (
        read_strict_json_byte_snapshot(
            compatibility_template,
            "compatibility template",
            expected_sha256=expected_compatibility,
        )
    )
    if snapshot_root.exists():
        raise PreflightError(f"live envelope snapshot root already exists: {snapshot_root}")
    ensure_owner_only_directory(snapshot_root)
    retained_receipt = snapshot_root / "verification.receipt.json"
    retained_canonical = snapshot_root / CANONICAL
    retained_compatibility = snapshot_root / COMPATIBILITY
    for path, raw in (
        (retained_receipt, receipt_raw),
        (retained_canonical, canonical_raw),
        (retained_compatibility, compatibility_raw),
    ):
        write_owner_only_file(path, raw)
        os.chmod(path, 0o400)
    directory = os.open(snapshot_root, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    snapshot = LiveEnvelopeSnapshot(
        root=snapshot_root,
        receipt=JsonByteSnapshot(
            "receipt",
            receipt_source,
            retained_receipt,
            receipt_raw,
            receipt_sha256,
            receipt,
        ),
        canonical=JsonByteSnapshot(
            "canonical",
            canonical_source,
            retained_canonical,
            canonical_raw,
            canonical_sha256,
            canonical,
        ),
        compatibility=JsonByteSnapshot(
            "compatibility",
            compatibility_source,
            retained_compatibility,
            compatibility_raw,
            compatibility_sha256,
            compatibility,
        ),
        closure=build_live_envelope_snapshot_closure(snapshot_root),
    )
    return snapshot


def live_envelope_snapshot_receipt_evidence(
    snapshot: LiveEnvelopeSnapshot,
    binding: Mapping[str, Any],
    *,
    root: Path | None = None,
    final_sha256: str | None = None,
    stable: bool,
) -> dict[str, Any]:
    effective_root = root or snapshot.root
    return {
        "schemaVersion": LIVE_ENVELOPE_SNAPSHOT_SCHEMA,
        "root": str(effective_root),
        "bindingSha256": str(binding.get("bindingSha256") or ""),
        "closureSha256": str(snapshot.closure["closureSha256"]),
        "fileCount": int(snapshot.closure["fileCount"]),
        "totalBytes": int(snapshot.closure["totalBytes"]),
        "finalSha256": (
            str(snapshot.closure["closureSha256"])
            if final_sha256 is None
            else final_sha256
        ),
        "stableThroughRuntimeAndRollback": stable,
    }


def _envelope_binding(snapshot: LiveEnvelopeSnapshot) -> dict[str, Any]:
    canonical = snapshot.canonical.payload
    compatibility = snapshot.compatibility.payload
    receipt = snapshot.receipt.payload
    result: dict[str, Any] = {
        "schemaVersion": LIVE_ENVELOPE_SNAPSHOT_SCHEMA,
        "canonicalSha256": snapshot.canonical.sha256,
        "compatibilitySha256": snapshot.compatibility.sha256,
        "receiptSha256": snapshot.receipt.sha256,
        "canonicalIdentity": {},
        "compatibilityIdentity": {},
        "identityParity": False,
        "canonicalTruthFloor": False,
        "compatibilityTruthFloor": False,
        "semanticParity": {"passed": False},
        "semanticContractValid": False,
        "receiptBound": True,
        "receiptDigestOperatorPinned": True,
        "receiptContractValid": False,
        "canonicalRawArtifactInventorySha256": sha256_bytes(
            canonical_json_bytes(canonical.get("artifacts"))
        ),
    }
    try:
        canonical_binding = template_manifest_binding(canonical)
        compatibility_binding = template_manifest_binding(compatibility)
        semantic_parity = parity_result(canonical, compatibility)
        result.update(
            {
                "canonicalIdentity": canonical_binding["releaseIdentity"],
                "compatibilityIdentity": compatibility_binding["releaseIdentity"],
                "identityParity": canonical_binding["releaseIdentity"]
                == compatibility_binding["releaseIdentity"],
                "canonicalTruthFloor": trust_floor_passes(canonical),
                "compatibilityTruthFloor": trust_floor_passes(compatibility),
                "semanticParity": semantic_parity,
                "canonicalArtifactInventorySha256": canonical_binding[
                    "artifactInventorySha256"
                ],
                "compatibilityArtifactInventorySha256": compatibility_binding[
                    "artifactInventorySha256"
                ],
            }
        )
        result["semanticContractValid"] = bool(
            result["canonicalTruthFloor"]
            and result["compatibilityTruthFloor"]
            and semantic_parity["passed"]
        )
    except (PreflightError, TypeError, ValueError, OverflowError) as exc:
        result["semanticError"] = str(exc)
    source = receipt.get("source")
    if not isinstance(source, dict):
        raise PreflightError("live envelope receipt has no source binding")
    result["receiptCanonicalSha256"] = source.get("afterSha256")
    result["receiptCompatibilitySha256"] = source.get("releasesSourceSha256")
    result["receiptMatchesTemplates"] = (
        result["canonicalSha256"] == source.get("afterSha256")
        and result["compatibilitySha256"] == source.get("releasesSourceSha256")
    )
    served_canonical = receipt.get("servedCanonical")
    served_releases = receipt.get("servedReleases")
    runtime = receipt.get("runtime")
    identity = result["canonicalIdentity"]
    canonical_hashes_bound = bool(
        isinstance(served_canonical, dict)
        and all(
            LOWER_SHA256_PATTERN.fullmatch(str(served_canonical.get(key) or ""))
            for key in ("beforeSha256", "afterSha256", "originSha256", "publicSha256")
        )
        and served_canonical.get("afterSha256")
        == served_canonical.get("originSha256")
        == served_canonical.get("publicSha256")
        and served_canonical.get("artifactInventoryDigest")
        == result.get("canonicalRawArtifactInventorySha256")
    )
    releases_hashes_bound = bool(
        isinstance(served_releases, dict)
        and LOWER_SHA256_PATTERN.fullmatch(
            str(served_releases.get("originSha256") or "")
        )
        and served_releases.get("originSha256") == served_releases.get("publicSha256")
    )
    runtime_identity_bound = bool(
        isinstance(runtime, dict)
        and LOWER_SHA256_PATTERN.fullmatch(
            str(runtime.get("containerIdentityAndConfigDigestBefore") or "")
        )
        and runtime.get("containerIdentityAndConfigDigestBefore")
        == runtime.get("containerIdentityAndConfigDigestAfter")
    )
    result["receiptCanonicalHashesBound"] = canonical_hashes_bound
    result["receiptReleasesHashesBound"] = releases_hashes_bound
    result["receiptRuntimeIdentityBound"] = runtime_identity_bound
    result["receiptContractValid"] = bool(
        receipt.get("schemaVersion") == LIVE_ENVELOPE_RECEIPT_SCHEMA
        and receipt.get("state") == "completed"
        and receipt.get("operation") == LIVE_ENVELOPE_RECEIPT_OPERATION
        and receipt.get("publicationMutation") is False
        and receipt.get("artifactBytesChanged") is False
        and receipt.get("containerRestarted") is False
        and bool(identity)
        and receipt.get("version") == identity.get("version")
        and normalize_timestamp(receipt.get("publishedAt")) == identity.get("publishedAt")
        and isinstance(served_canonical, dict)
        and canonical_hashes_bound
        and served_canonical.get("originPublicByteIdentical") is True
        and served_canonical.get("artifactInventoryUnchanged") is True
        and served_canonical.get("proofFreshnessStatus") == "stale"
        and served_canonical.get("rolloutState") == "public_release_review_required"
        and served_canonical.get("supportabilityState") == "review_required"
        and served_canonical.get("publicTrustPosture") == "blocked"
        and served_canonical.get("publicTrustSupportabilityState") == "review_required"
        and served_canonical.get("registryPublicTrustPosture") == "blocked"
        and served_canonical.get("registrySupportabilityState") == "review_required"
        and served_canonical.get("optimisticNarrativeRemoved") is True
        and isinstance(served_releases, dict)
        and releases_hashes_bound
        and served_releases.get("originPublicByteIdentical") is True
        and served_releases.get("rolloutState") == "public_release_review_required"
        and served_releases.get("supportabilityState") == "review_required"
        and isinstance(runtime, dict)
        and runtime_identity_bound
        and runtime.get("statusOriginHttpStatus") == 200
        and runtime.get("statusPublicHttpStatus") == 200
        and runtime.get("statusCacheControl") == "private, no-store, max-age=0"
        and runtime.get("containerIdentityAndConfigUnchanged") is True
    )
    result["bindingSha256"] = sha256_bytes(
        canonical_json_bytes(
            {
                "schemaVersion": result["schemaVersion"],
                "receiptSha256": result["receiptSha256"],
                "canonicalSha256": result["canonicalSha256"],
                "compatibilitySha256": result["compatibilitySha256"],
                "canonicalIdentity": result["canonicalIdentity"],
                "compatibilityIdentity": result["compatibilityIdentity"],
                "semanticContractValid": result["semanticContractValid"],
                "semanticParity": result["semanticParity"],
            }
        )
    )
    result["passed"] = bool(
        result["identityParity"]
        and result["semanticContractValid"]
        and result["receiptMatchesTemplates"]
        and result["receiptDigestOperatorPinned"]
        and result["receiptContractValid"]
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--media-factory-root", type=Path, required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--expected-source-closure-sha256", required=True)
    parser.add_argument("--canonical-template", type=Path, required=True)
    parser.add_argument("--compatibility-template", type=Path, required=True)
    parser.add_argument("--live-envelope-receipt", type=Path, required=True)
    parser.add_argument("--expected-live-envelope-receipt-sha256", required=True)
    parser.add_argument("--generation-tool", type=Path, required=True)
    parser.add_argument("--git-host", type=Path, required=True)
    parser.add_argument("--expected-git-host-sha256", required=True)
    parser.add_argument("--docker-host", type=Path, required=True)
    parser.add_argument("--expected-docker-host-sha256", required=True)
    parser.add_argument("--openssl-host", type=Path, required=True)
    parser.add_argument("--expected-openssl-host-sha256", required=True)
    parser.add_argument("--seccomp-library", type=Path, required=True)
    parser.add_argument("--expected-seccomp-library-sha256", required=True)
    parser.add_argument("--dotnet-host", type=Path, required=True)
    parser.add_argument("--expected-dotnet-host-sha256", required=True)
    parser.add_argument("--expected-dotnet-toolchain-closure-sha256", required=True)
    parser.add_argument("--expected-postgres-image-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--reuse-build-root", type=Path)
    parser.add_argument("--reuse-postgres-tool-root", type=Path)
    parser.add_argument("--reuse-evidence-receipt", type=Path)
    parser.add_argument("--expected-reuse-evidence-receipt-sha256")
    parser.add_argument("--expected-build-closure-sha256")
    parser.add_argument("--command-timeout-seconds", type=int, default=1800)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    candidate_root = _resolve_without_symlink_components(args.candidate_root, "candidate root")
    workspace_root = _resolve_without_symlink_components(args.workspace_root, "workspace root")
    media_factory_root = _resolve_without_symlink_components(
        args.media_factory_root,
        "media factory source root",
    )
    canonical_template = _resolve_without_symlink_components(
        args.canonical_template,
        "canonical template",
    )
    compatibility_template = _resolve_without_symlink_components(
        args.compatibility_template,
        "compatibility template",
    )
    generation_tool = bind_generation_tool(candidate_root, args.generation_tool)
    system_tools = bind_system_tools(
        git=args.git_host,
        expected_git_sha256=args.expected_git_host_sha256,
        docker=args.docker_host,
        expected_docker_sha256=args.expected_docker_host_sha256,
        openssl=args.openssl_host,
        expected_openssl_sha256=args.expected_openssl_host_sha256,
        seccomp_library=args.seccomp_library,
        expected_seccomp_library_sha256=args.expected_seccomp_library_sha256,
    )
    expected_postgres_image_id = require_postgres_image_id(args.expected_postgres_image_id)
    expected_live_receipt = require_lower_sha256(
        args.expected_live_envelope_receipt_sha256,
        "--expected-live-envelope-receipt-sha256",
    )
    expected_source = require_lower_sha256(
        args.expected_source_closure_sha256,
        "--expected-source-closure-sha256",
    )
    expected_build = (
        require_lower_sha256(
            args.expected_build_closure_sha256,
            "--expected-build-closure-sha256",
        )
        if args.expected_build_closure_sha256
        else ""
    )
    expected_reuse_evidence = (
        require_lower_sha256(
            args.expected_reuse_evidence_receipt_sha256,
            "--expected-reuse-evidence-receipt-sha256",
        )
        if args.expected_reuse_evidence_receipt_sha256
        else ""
    )
    live_receipt_path = _resolve_without_symlink_components(
        args.live_envelope_receipt,
        "live envelope receipt",
    )
    output_root = prepare_output_root(args.output_root, candidate_root)
    started_at = utc_now()
    reasons: list[str] = []
    reuse_values = (
        args.reuse_build_root,
        args.reuse_postgres_tool_root,
        args.reuse_evidence_receipt,
        args.expected_reuse_evidence_receipt_sha256,
        args.expected_build_closure_sha256,
    )
    if any(reuse_values) and not all(reuse_values):
        raise PreflightError(
            "reuse requires --reuse-build-root, --reuse-postgres-tool-root, "
            "--reuse-evidence-receipt, --expected-reuse-evidence-receipt-sha256, "
            "and --expected-build-closure-sha256 together"
        )

    candidate_identity = git_identity(candidate_root, system_tools.git)
    candidate_identity["expectedBase"] = args.expected_base
    candidate_identity["baseMatches"] = candidate_identity["head"] == args.expected_base
    if not candidate_identity["baseMatches"]:
        reasons.append("candidate_base_mismatch")

    required_paths = {
        relative: (candidate_root / relative).is_file()
        for relative in REQUIRED_CANDIDATE_PATHS
    }
    coherent_candidate = all(required_paths.values())
    if not coherent_candidate:
        reasons.append("candidate_missing_durable_writer_or_focused_test_sources")

    external_source_inputs: list[tuple[str, Path]] = []
    external_git_inputs = [
        ("chummer-core-engine", workspace_root / "chummer-core-engine"),
        ("chummer-hub-registry", workspace_root / "chummer-hub-registry"),
        ("media-factory", media_factory_root),
    ]
    source_before = build_source_closure_manifest(
        candidate_root,
        external_source_inputs,
        external_git_inputs,
        git_host=system_tools.git,
    )
    atomic_write_json(output_root / "source-closure.json", source_before)
    source_approved = expected_source == source_before["closureSha256"]
    if not source_approved:
        raise PreflightError(
            "source closure does not match --expected-source-closure-sha256; "
            f"computed closure was written to {output_root / 'source-closure.json'}"
        )
    source_projection = materialize_source_projection(
        source_before,
        candidate_root=candidate_root,
        workspace_root=workspace_root,
        media_factory_root=media_factory_root,
        projection_root=output_root / "source-projection",
    )
    atomic_write_json(
        output_root / "source-projection-closure.json",
        source_projection.manifest,
    )
    execution_candidate_root = source_projection.candidate_root
    execution_workspace_root = source_projection.workspace_root
    execution_generation_tool = execution_candidate_root / "scripts" / "release_shelf_generation.py"
    if not execution_generation_tool.is_file():
        raise PreflightError("source projection omitted the bound generation tool")
    execution_landlock_launcher = (
        execution_candidate_root / "scripts" / "release" / "landlock_exec.py"
    )
    dotnet_execution = bind_dotnet_execution(
        args.dotnet_host,
        args.expected_dotnet_host_sha256,
        args.expected_dotnet_toolchain_closure_sha256,
        execution_landlock_launcher,
        system_tools.seccomp_library,
    )
    atomic_write_json(
        output_root / "dotnet-toolchain-closure.json",
        dotnet_execution.toolchain_closure,
    )

    live_envelope_snapshot = materialize_live_envelope_snapshot(
        canonical_template,
        compatibility_template,
        live_receipt_path,
        expected_live_receipt,
        output_root / "live-envelope-snapshot",
    )
    envelope = _envelope_binding(live_envelope_snapshot)
    if not envelope["passed"]:
        reasons.append("live_envelope_binding_failed")

    tooling_inputs: list[tuple[str, Path]] = [
        ("preflight-tool", Path(__file__).resolve()),
        ("generation-tool", generation_tool),
        ("dotnet-host", dotnet_execution.host),
        ("git-host", system_tools.git),
        ("docker-host", system_tools.docker),
        ("openssl-host", system_tools.openssl),
        ("libseccomp", system_tools.seccomp_library),
        ("landlock-python-host", dotnet_execution.python_host),
        ("landlock-launcher", dotnet_execution.landlock_launcher),
        ("live-envelope-receipt", live_envelope_snapshot.receipt.retained_path),
        ("live-envelope-canonical", live_envelope_snapshot.canonical.retained_path),
        (
            "live-envelope-compatibility",
            live_envelope_snapshot.compatibility.retained_path,
        ),
    ]
    tooling_closure = build_closure_manifest(
        "chummer.canonical-writer-preflight-tooling/v1",
        tooling_inputs,
    )
    atomic_write_json(output_root / "tooling-closure.json", tooling_closure)

    environment = sanitized_environment(
        {
            "DOTNET_CLI_HOME": str(output_root / "dotnet-home"),
            "HOME": str(output_root / "dotnet-home"),
            "NUGET_PACKAGES": str(output_root / "nuget-packages"),
            "NUGET_HTTP_CACHE_PATH": str(output_root / "nuget-http-cache"),
            "NUGET_PLUGINS_CACHE_PATH": str(output_root / "nuget-plugins-cache"),
            "DOTNET_ROOT": str(dotnet_execution.root),
            "DOTNET_HOST_PATH": str(dotnet_execution.host),
            "DOTNET_MULTILEVEL_LOOKUP": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": "/usr/bin:/bin",
        }
    )
    logs = output_root / "logs"
    test_project, truth_test_argv = truth_test_command(
        execution_candidate_root,
        dotnet_execution.host,
    )
    test_source_projection: dict[str, Any] = {"passed": False, "skipped": True}
    if test_project == execution_candidate_root / "Chummer.Tests" / "Chummer.Tests.csproj":
        test_source_projection = materialize_test_source_projection(
            execution_candidate_root,
            output_root,
        )
    source_monitor_roots: list[Path] = [
        source_projection.root,
        live_envelope_snapshot.root,
    ]
    if test_source_projection.get("passed") is True:
        source_monitor_roots.extend(
            (
                Path(str(test_source_projection["composePath"])),
                Path(str(test_source_projection["fixturesRoot"])),
            )
        )
    build_artifacts_root = output_root / "dotnet-artifacts"
    if truth_test_argv:
        truth_test_argv = (
            *truth_test_argv,
            "--artifacts-path",
            str(build_artifacts_root),
            f"-p:RestorePackagesPath={output_root / 'nuget-packages'}",
        )
    commands: list[CommandResult] = []
    source_mutation_monitors: list[dict[str, Any]] = []
    publish_root = output_root / "publish"
    postgres_tool_root = output_root / "postgres-tool"
    build_write_roots = tuple(
        output_root / name
        for name in (
            "dotnet-artifacts",
            "nuget-packages",
            "dotnet-home",
            "nuget-http-cache",
            "nuget-plugins-cache",
            "tmp",
            "logs",
        )
    ) + (publish_root, postgres_tool_root)
    for write_root in build_write_roots:
        ensure_owner_only_directory(write_root)
    reused_build: dict[str, Any] | None = None
    runtime_build_projection: RuntimeBuildProjection | None = None
    runtime_build_projection_error: str | None = None
    build_source_publish_root = publish_root
    build_source_postgres_tool_root = postgres_tool_root
    commands_passed = False
    build_closure: dict[str, Any] | None = None
    if args.reuse_build_root:
        publish_root = _resolve_without_symlink_components(
            args.reuse_build_root,
            "reused portal build root",
        )
        postgres_tool_root = _resolve_without_symlink_components(
            args.reuse_postgres_tool_root,
            "reused PostgreSQL tool root",
        )
        evidence_path = _resolve_without_symlink_components(
            args.reuse_evidence_receipt,
            "reused preflight evidence",
        )
        evidence, evidence_sha256 = read_operator_pinned_json_object(
            evidence_path,
            expected_reuse_evidence,
            "reused preflight evidence",
        )
        build_closure = build_output_closure(publish_root, postgres_tool_root)
        prior_commands = validate_first_pass_reuse_evidence(
            evidence,
            evidence_path=evidence_path,
            candidate_root=candidate_root,
            candidate_identity=candidate_identity,
            required_paths=required_paths,
            source_closure=source_before,
            source_projection=source_projection,
            tooling_closure=tooling_closure,
            build_closure=build_closure,
            expected_build_sha256=expected_build,
            publish_root=publish_root,
            postgres_tool_root=postgres_tool_root,
            test_source_projection=test_source_projection,
            live_envelope=envelope,
            live_envelope_snapshot=live_envelope_snapshot,
            dotnet_execution=dotnet_execution,
            system_tools=system_tools,
            expected_postgres_image_id=expected_postgres_image_id,
        )
        commands_passed = True
        reused_build = {
            "receiptPath": str(evidence_path),
            "receiptSha256": evidence_sha256,
            "expectedReceiptSha256": expected_reuse_evidence,
            "receiptOperatorPinned": True,
            "publishRoot": str(publish_root),
            "postgresToolRoot": str(postgres_tool_root),
            "expectedBuildClosureSha256": expected_build,
            "validated": True,
            "commands": prior_commands,
        }
        atomic_write_json(output_root / "build-closure.json", build_closure)
        build_source_publish_root = publish_root
        build_source_postgres_tool_root = postgres_tool_root
        try:
            runtime_build_projection = materialize_runtime_build_projection(
                build_source_publish_root,
                build_source_postgres_tool_root,
                build_closure,
                output_root / "runtime-build-projection",
            )
            publish_root = runtime_build_projection.publish_root
            postgres_tool_root = runtime_build_projection.postgres_tool_root
            reused_build["runtimeProjectionRoot"] = str(runtime_build_projection.root)
        except Exception as exc:
            runtime_build_projection_error = str(exc)
            reasons.append("runtime_build_projection_failed")
    elif test_project is not None:
        commands.append(
            run_command(
                "restore",
                isolated_dotnet_argv(
                    dotnet_execution,
                    (
                    str(dotnet_execution.host),
                    "restore",
                    str(test_project),
                    "--nologo",
                    "--artifacts-path",
                    str(build_artifacts_root),
                    f"-p:RestorePackagesPath={output_root / 'nuget-packages'}",
                ),
                    build_write_roots,
                ),
                cwd=execution_candidate_root,
                environment=environment,
                log_root=logs,
                timeout_seconds=args.command_timeout_seconds,
                monitored_roots=source_monitor_roots,
                mutation_evidence=source_mutation_monitors,
            )
        )
        if commands[-1].passed:
            commands.append(
                run_command(
                    "truth-tests",
                    isolated_dotnet_argv(
                        dotnet_execution,
                        truth_test_argv,
                        build_write_roots,
                    ),
                    cwd=execution_candidate_root,
                    environment=environment,
                    log_root=logs,
                    timeout_seconds=args.command_timeout_seconds,
                    monitored_roots=source_monitor_roots,
                    mutation_evidence=source_mutation_monitors,
                )
            )
        if commands[-1].passed:
            commands.append(
                run_command(
                    "publish-install-linking-postgres-tool",
                    isolated_dotnet_argv(
                        dotnet_execution,
                        (
                        str(dotnet_execution.host),
                        "publish",
                        str(
                            execution_candidate_root
                            / "Chummer.InstallLinking.Postgres.Tool"
                            / "Chummer.InstallLinking.Postgres.Tool.csproj"
                        ),
                        "-c",
                        "Release",
                        "-o",
                        str(postgres_tool_root),
                        "--nologo",
                        "-m:1",
                        "-p:BuildInParallel=false",
                        "-p:UseSharedCompilation=false",
                        "--artifacts-path",
                        str(build_artifacts_root),
                        f"-p:RestorePackagesPath={output_root / 'nuget-packages'}",
                    ),
                        build_write_roots,
                    ),
                    cwd=execution_candidate_root,
                    environment=environment,
                    log_root=logs,
                    timeout_seconds=args.command_timeout_seconds,
                    monitored_roots=source_monitor_roots,
                    mutation_evidence=source_mutation_monitors,
                )
            )
        if commands[-1].passed:
            commands.append(
                run_command(
                    "publish",
                    isolated_dotnet_argv(
                        dotnet_execution,
                        (
                        str(dotnet_execution.host),
                        "publish",
                        str(
                            execution_candidate_root
                            / "Chummer.Run.Api"
                            / "Chummer.Run.Api.csproj"
                        ),
                        "-c",
                        "Release",
                        "-o",
                        str(publish_root),
                        "--no-restore",
                        "--nologo",
                        "-m:1",
                        "-p:BuildInParallel=false",
                        "-p:UseSharedCompilation=false",
                        "--artifacts-path",
                        str(build_artifacts_root),
                        f"-p:RestorePackagesPath={output_root / 'nuget-packages'}",
                    ),
                        build_write_roots,
                    ),
                    cwd=execution_candidate_root,
                    environment=environment,
                    log_root=logs,
                    timeout_seconds=args.command_timeout_seconds,
                    monitored_roots=source_monitor_roots,
                    mutation_evidence=source_mutation_monitors,
                )
            )
        commands_passed = bool(commands) and all(command.passed for command in commands)
    else:
        reasons.append("focused_truth_test_project_missing")
    if not commands_passed:
        reasons.append("candidate_restore_test_or_publish_failed")

    source_after_build = build_source_closure_manifest(
        candidate_root,
        external_source_inputs,
        external_git_inputs,
        git_host=system_tools.git,
    )
    projection_after_build = _projection_manifest(
        _source_projection_roots(source_projection.root)[3]
    )

    runtime: dict[str, Any] = {"passed": False, "skipped": True}
    runtime_mutation_monitor: dict[str, Any] | None = None
    overlay_identity: dict[str, Any] = {"passed": False, "skipped": True}
    build_stable_during_runtime = False
    if commands_passed and (publish_root / "Chummer.Run.Api.dll").is_file():
        if reused_build is None:
            _copy_runtime_content(
                execution_candidate_root,
                execution_workspace_root,
                publish_root,
            )
            try:
                overlay_identity = finalize_preflight_overlay_identity(
                    execution_candidate_root,
                    publish_root,
                )
            except Exception as exc:
                overlay_identity = {"passed": False, "error": str(exc)}
            if overlay_identity.get("passed"):
                build_closure = build_output_closure(publish_root, postgres_tool_root)
                build_source_publish_root = publish_root
                build_source_postgres_tool_root = postgres_tool_root
                atomic_write_json(output_root / "build-closure.json", build_closure)
        else:
            build_info = (
                publish_root
                / ".codex-studio"
                / "runtime"
                / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
            )
            try:
                overlay_identity = read_preflight_overlay_identity(build_info)
                overlay_identity["reused"] = True
            except Exception as exc:
                overlay_identity = {"passed": False, "error": str(exc), "reused": True}
        build_operator_pinned = bool(
            build_closure is not None
            and expected_build
            and expected_build == build_closure["closureSha256"]
            and runtime_build_projection is not None
        )
        if not build_operator_pinned:
            runtime = {
                "passed": False,
                "skipped": True,
                "reason": "build_closure_not_operator_pinned",
            }
        elif overlay_identity.get("passed") and (
            postgres_tool_root / "Chummer.InstallLinking.Postgres.Tool.dll"
        ).is_file():
            runtime_mutation_monitor = {}
            with transient_tree_mutation_monitor(
                (publish_root, postgres_tool_root),
                runtime_mutation_monitor,
            ):
                runtime = probe_runtime(
                    execution_candidate_root,
                    publish_root,
                    postgres_tool_root,
                    execution_generation_tool,
                    live_envelope_snapshot,
                    envelope,
                    overlay_identity,
                    output_root / "runtime-probe",
                    expected_postgres_image_id,
                    dotnet_execution,
                    system_tools,
                )
        build_after_runtime = build_output_closure(publish_root, postgres_tool_root)
        build_stable_during_runtime = bool(
            (
                runtime_build_projection is not None
                and build_after_runtime["closureSha256"]
                == runtime_build_projection.sealed_closure["closureSha256"]
            )
            or (
                runtime_build_projection is None
                and build_closure is not None
                and build_after_runtime["closureSha256"] == build_closure["closureSha256"]
            )
        )
    else:
        build_operator_pinned = False
    if not build_operator_pinned:
        reasons.append("build_closure_not_operator_pinned")
    if not build_stable_during_runtime:
        reasons.append("build_closure_changed_or_was_unavailable_during_runtime")
    if not runtime.get("passed"):
        reasons.append("production_mode_loopback_runtime_gate_failed")
    if not overlay_identity.get("passed"):
        reasons.append("finalized_overlay_identity_gate_failed")

    rollback: dict[str, Any]
    try:
        rollback = generation_rollback_probe(
            execution_generation_tool,
            output_root / "rollback-probe",
        )
    except Exception as exc:  # evidence must survive a fail-closed protocol probe
        rollback = {"passed": False, "error": str(exc), "productionMutation": False}
    if not rollback.get("passed"):
        reasons.append("atomic_generation_pointer_rollback_probe_failed")

    source_final = build_source_closure_manifest(
        candidate_root,
        external_source_inputs,
        external_git_inputs,
        git_host=system_tools.git,
    )
    source_stable = (
        source_before["closureSha256"]
        == source_after_build["closureSha256"]
        == source_final["closureSha256"]
    )
    if not source_stable:
        reasons.append("source_closure_changed_during_preflight")
    projection_final = _projection_manifest(
        _source_projection_roots(source_projection.root)[3]
    )
    projection_stable = (
        source_projection.manifest["closureSha256"]
        == projection_after_build["closureSha256"]
        == projection_final["closureSha256"]
    )
    if not projection_stable:
        reasons.append("source_projection_changed_during_preflight")
    live_envelope_snapshot_sampling_error: str | None = None
    try:
        live_envelope_snapshot_final = build_live_envelope_snapshot_closure(
            live_envelope_snapshot.root
        )
    except Exception as exc:
        live_envelope_snapshot_sampling_error = str(exc)
        live_envelope_snapshot_final = {
            "closureSha256": "",
            "fileCount": 0,
            "totalBytes": 0,
        }
    live_envelope_snapshot_stable = bool(
        not live_envelope_snapshot_sampling_error
        and live_envelope_snapshot.closure["closureSha256"]
        == live_envelope_snapshot_final["closureSha256"]
    )
    if not live_envelope_snapshot_stable:
        reasons.append("live_envelope_snapshot_changed_during_preflight")
    tooling_sampling_error: str | None = None
    try:
        tooling_final = build_closure_manifest(
            "chummer.canonical-writer-preflight-tooling/v1",
            tooling_inputs,
        )
    except Exception as exc:
        tooling_sampling_error = str(exc)
        tooling_final = {"closureSha256": "", "fileCount": 0, "totalBytes": 0}
    tooling_stable = bool(
        not tooling_sampling_error
        and tooling_final["closureSha256"] == tooling_closure["closureSha256"]
    )
    if not tooling_stable:
        reasons.append("tooling_closure_changed_during_preflight")
    system_tools_sampling_error: str | None = None
    try:
        system_tools_final = {
            "git": sha256_file(system_tools.git),
            "docker": sha256_file(system_tools.docker),
            "openssl": sha256_file(system_tools.openssl),
            "libseccomp": sha256_file(system_tools.seccomp_library),
        }
        final_docker_socket, final_docker_socket_identity = docker_socket_identity(
            system_tools.docker_socket
        )
    except Exception as exc:
        system_tools_sampling_error = str(exc)
        system_tools_final = {
            "git": "",
            "docker": "",
            "openssl": "",
            "libseccomp": "",
        }
        final_docker_socket = Path("/")
        final_docker_socket_identity = {}
    system_tools_stable = bool(
        not system_tools_sampling_error
        and system_tools_final
        == {
            "git": system_tools.git_sha256,
            "docker": system_tools.docker_sha256,
            "openssl": system_tools.openssl_sha256,
            "libseccomp": system_tools.seccomp_library_sha256,
        }
        and final_docker_socket == system_tools.docker_socket
        and final_docker_socket_identity == system_tools.docker_socket_identity
    )
    if not system_tools_stable:
        reasons.append("system_tools_changed_during_preflight")
    dotnet_toolchain_sampling_error: str | None = None
    try:
        dotnet_toolchain_final = build_dotnet_toolchain_closure(dotnet_execution.root)
    except Exception as exc:
        dotnet_toolchain_sampling_error = str(exc)
        dotnet_toolchain_final = {"closureSha256": ""}
    dotnet_toolchain_stable = bool(
        not dotnet_toolchain_sampling_error
        and dotnet_toolchain_final["closureSha256"]
        == dotnet_execution.toolchain_closure["closureSha256"]
    )
    if not dotnet_toolchain_stable:
        reasons.append("dotnet_toolchain_changed_during_preflight")
    runtime_build_projection_evidence: dict[str, Any] | None = None
    if runtime_build_projection is not None:
        try:
            runtime_build_projection_final = build_output_closure(
                runtime_build_projection.publish_root,
                runtime_build_projection.postgres_tool_root,
            )
            runtime_build_projection_stable = bool(
                runtime_build_projection_final["closureSha256"]
                == runtime_build_projection.sealed_closure["closureSha256"]
                and owner_read_only_tree_passes(runtime_build_projection.root)
            )
        except Exception as exc:
            runtime_build_projection_error = str(exc)
            runtime_build_projection_final = {"closureSha256": ""}
            runtime_build_projection_stable = False
        build_stable_during_runtime = bool(
            build_stable_during_runtime and runtime_build_projection_stable
        )
        if not runtime_build_projection_stable:
            reasons.append("runtime_build_projection_changed_during_preflight")
        runtime_build_projection_evidence = {
            **runtime_build_projection_receipt_evidence(
                runtime_build_projection,
                final_sha256=runtime_build_projection_final["closureSha256"],
                stable=runtime_build_projection_stable,
                mutation_monitor=runtime_mutation_monitor,
            ),
            **(
                {"samplingError": runtime_build_projection_error}
                if runtime_build_projection_error
                else {}
            ),
        }
    elif runtime_build_projection_error:
        runtime_build_projection_evidence = {
            "passed": False,
            "error": runtime_build_projection_error,
        }

    source_execution_isolated = bool(
        reused_build is not None
        or (
            len(source_mutation_monitors) == len(FIRST_PASS_COMMAND_NAMES)
            and all(row.get("passed") is True for row in source_mutation_monitors)
        )
    )
    runtime_execution_isolated = bool(
        runtime.get("skipped") is True
        or (
            runtime_mutation_monitor is not None
            and runtime_mutation_monitor.get("passed") is True
        )
    )
    child_write_isolation_enforced = bool(
        dotnet_execution.landlock_abi >= 3
        and source_execution_isolated
        and runtime_execution_isolated
    )
    if not child_write_isolation_enforced:
        reasons.append("child_write_or_transient_metadata_isolation_failed")

    gates = {
        "candidateBaseMatches": bool(candidate_identity["baseMatches"]),
        "coherentCandidateContainsWriterAndTruthFloor": coherent_candidate,
        "sourceClosureOperatorPinned": source_approved,
        "sourceClosureStableThroughRuntimeAndRollback": source_stable,
        "sourceProjectionStableThroughRuntimeAndRollback": projection_stable,
        "toolingClosureStableThroughRuntimeAndRollback": tooling_stable,
        "systemToolsOperatorPinned": True,
        "systemToolsStableThroughRuntimeAndRollback": system_tools_stable,
        "dotnetToolchainOperatorPinned": True,
        "dotnetToolchainStableThroughRuntimeAndRollback": dotnet_toolchain_stable,
        "childWriteIsolationEnforced": child_write_isolation_enforced,
        "generationToolBoundToCandidate": True,
        "liveEnvelopeReceiptBinding": bool(envelope["passed"]),
        "liveEnvelopeSnapshotStableThroughRuntimeAndRollback": (
            live_envelope_snapshot_stable
        ),
        "restoreTestsPublish": commands_passed,
        "contentAddressedBuildClosure": build_closure is not None,
        "buildClosureOperatorPinned": build_operator_pinned,
        "buildClosureStableDuringRuntime": build_stable_during_runtime,
        "finalizedOverlayIdentity": bool(overlay_identity.get("passed")),
        "productionModeReadyAndTruthProjection": bool(runtime.get("passed")),
        "atomicGenerationPointerRollback": bool(rollback.get("passed")),
        "productionMutation": False,
    }
    decision = "go" if all(value for key, value in gates.items() if key != "productionMutation") else "no-go"
    if decision == "go" and reasons:
        raise PreflightError("internal preflight inconsistency: go decision has failure reasons")
    receipt = {
        "schemaVersion": SCHEMA,
        "state": "completed",
        "decision": decision,
        "startedAt": started_at,
        "completedAt": utc_now(),
        "productionMutation": False,
        "networkScope": NETWORK_SCOPE,
        "candidate": candidate_identity,
        "requiredCandidatePaths": required_paths,
        "sourceClosure": {
            "path": str(output_root / "source-closure.json"),
            "sha256": source_before["closureSha256"],
            "expectedSha256": expected_source or None,
            "operatorPinned": source_approved,
            "stableThroughRuntimeAndRollback": source_stable,
            "afterBuildSha256": source_after_build["closureSha256"],
            "finalSha256": source_final["closureSha256"],
        },
        "sourceProjection": source_projection_receipt_evidence(
            source_projection,
            manifest_path=output_root / "source-projection-closure.json",
            after_build_sha256=projection_after_build["closureSha256"],
            final_sha256=projection_final["closureSha256"],
            stable=projection_stable,
            mutation_monitors=source_mutation_monitors,
            execution_reused=reused_build is not None,
        ),
        "toolingClosure": {
            "path": str(output_root / "tooling-closure.json"),
            "sha256": tooling_closure["closureSha256"],
            "fileCount": tooling_closure["fileCount"],
            "finalSha256": tooling_final["closureSha256"],
            "stableThroughRuntimeAndRollback": tooling_stable,
        },
        "systemTools": {
            **system_tools_receipt(
                system_tools,
                final_sha256=system_tools_final,
                stable=system_tools_stable,
            ),
            **(
                {"samplingError": system_tools_sampling_error}
                if system_tools_sampling_error
                else {}
            ),
        },
        "dotnetToolchain": dotnet_toolchain_receipt(
            dotnet_execution,
            final_sha256=dotnet_toolchain_final["closureSha256"],
            stable=dotnet_toolchain_stable,
        ),
        "buildClosure": (
            {
                "path": str(output_root / "build-closure.json"),
                "sha256": build_closure["closureSha256"],
                "fileCount": build_closure["fileCount"],
                "totalBytes": build_closure["totalBytes"],
                "expectedSha256": expected_build or None,
                "operatorPinned": build_operator_pinned,
                "portalRoot": str(build_source_publish_root),
                "postgresToolRoot": str(build_source_postgres_tool_root),
            }
            if build_closure is not None
            else None
        ),
        "liveEnvelope": envelope,
        "liveEnvelopeSnapshot": {
            **live_envelope_snapshot_receipt_evidence(
                live_envelope_snapshot,
                envelope,
                final_sha256=live_envelope_snapshot_final["closureSha256"],
                stable=live_envelope_snapshot_stable,
            ),
            **(
                {"samplingError": live_envelope_snapshot_sampling_error}
                if live_envelope_snapshot_sampling_error
                else {}
            ),
        },
        "postgresImage": {
            "reference": POSTGRES_IMAGE,
            "expectedImageId": expected_postgres_image_id,
        },
        "commands": [command.to_json() for command in commands],
        "testSourceProjection": test_source_projection,
        "reusedBuildEvidence": reused_build,
        "runtimeBuildProjection": runtime_build_projection_evidence,
        "runtime": runtime,
        "overlayIdentity": overlay_identity,
        "rollbackProbe": rollback,
        "gates": gates,
        "reasons": sorted(set(reasons)),
        "rollbackPlan": {
            "activationAuthorized": False,
            "candidateBuildSha256": build_closure["closureSha256"] if build_closure else None,
            "restorePrimitive": "content-addressed prior overlay plus compare-and-swap activation; not exercised against production",
            "releaseShelfPrimitive": rollback.get("atomicCommitPrimitive"),
            "productionTargetCaptured": False,
        },
    }
    receipt_path = output_root / "preflight.receipt.json"
    atomic_write_json(receipt_path, receipt)
    digest = sha256_file(receipt_path)
    digest_path = output_root / "preflight.receipt.sha256"
    digest_path.write_text(f"{digest}  {receipt_path.name}\n", encoding="ascii")
    os.chmod(digest_path, 0o600)
    print(json.dumps({"decision": decision, "receipt": str(receipt_path), "sha256": digest}, sort_keys=True))
    return 0 if decision == "go" else 2


if __name__ == "__main__":
    try:
        signal.signal(signal.SIGTERM, _terminate_for_signal)
        raise SystemExit(main())
    except PreflightCancelled as exc:
        print(f"canonical writer preflight cancelled: {exc}", file=sys.stderr)
        raise SystemExit(128 + signal.SIGTERM)
    except PreflightError as exc:
        print(f"canonical writer preflight error: {exc}", file=sys.stderr)
        raise SystemExit(1)
