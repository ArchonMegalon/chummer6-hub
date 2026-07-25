#!/usr/bin/env python3
"""Materializer-owned Campaign OS local smoke proof v3."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence


CONTRACT_NAME = "chummer6-hub.campaign_os_local_proof"
CONTRACT_VERSION = 3
PROOF_KIND = "materializer_owned_executed_smoke_receipt"
INVOCATION_ID = "run_services_smoke"
INVOCATION_OWNER = "campaign_os_local_proof_materializer"
JOURNEY_SPEC_VERSION = 1
RECEIPT_LIFETIME = dt.timedelta(hours=24)
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60
DEFAULT_FUTURE_SKEW_SECONDS = 5 * 60
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 64 * 1024
MAX_TREE_FILES = 200_000
MAX_TREE_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
TREE_FORMAT_VERSION = 1
PREPARE_TIMEOUT_SECONDS = 60 * 60
RUN_TIMEOUT_SECONDS = 15 * 60

SOURCE_PATH = "tests/RunServicesSmoke/Program.cs"
JOURNEY_SPEC_PATH = ".codex-design/product/GOLDEN_JOURNEY_RELEASE_GATES.yaml"
RUNNER_PATH = "scripts/ai/run_services_smoke.sh"
PREPARE_HELPER_PATH = "scripts/ai/prepare_run_services_smoke.sh"
ENVIRONMENT_HELPER_PATH = "scripts/ai/_env.sh"
CLEANROOM_BUILDER_PATH = "scripts/ai/build_r1_cleanroom.sh"
REGISTRY_GLOBAL_USINGS_PATH = "../chummer-hub-registry/Chummer.Run.Registry/GlobalUsings.RegistryContracts.cs"
MATERIALIZER_PATH = "scripts/materialize_campaign_os_local_proof.py"
CONTRACT_MODULE_PATH = "scripts/campaign_os_local_proof_v3.py"
DEFAULT_RECEIPT_PATH = ".codex-studio/published/HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json"
ASSEMBLY_FILE_NAME = "RunServicesSmoke.dll"
RUNTIMECONFIG_FILE_NAME = "RunServicesSmoke.runtimeconfig.json"
CHECKPOINT_FILE_NAME = "campaign-os-checkpoints.jsonl"
DOTNET_HOST_PATH = Path("/usr/bin/dotnet")
BASH_HOST_PATH = Path("/usr/bin/bash")
MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_MODE = "restore_free_with_locally_closed_package_inputs"

PROJECT_SPECS = (
    ("../chummer-core-engine/Chummer.Contracts", "Chummer.Contracts.csproj", "../chummer-core-engine/.tmp/nuget/packages"),
    ("../chummer-hub-registry/Chummer.Hub.Registry.Contracts", "Chummer.Hub.Registry.Contracts.csproj", "../chummer-hub-registry/.tmp/nuget/packages"),
    ("../chummer-hub-registry/Chummer.Run.Registry", "Chummer.Run.Registry.csproj", "../chummer-hub-registry/.tmp/nuget/packages"),
    ("../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts", "Chummer.Media.Contracts.csproj", "../../fleet/repos/chummer-media-factory/.tmp/nuget/packages"),
    ("../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime", "Chummer.Media.Factory.Runtime.csproj", "../../fleet/repos/chummer-media-factory/.tmp/nuget/packages"),
    ("Chummer.Play.Contracts", "Chummer.Play.Contracts.csproj", ".tmp/nuget/packages"),
    ("Chummer.Campaign.Contracts", "Chummer.Campaign.Contracts.csproj", ".tmp/nuget/packages"),
    ("Chummer.Control.Contracts", "Chummer.Control.Contracts.csproj", ".tmp/nuget/packages"),
    ("Chummer.Run.Contracts", "Chummer.Run.Contracts.csproj", ".tmp/nuget/packages"),
    ("Chummer.World.Contracts", "Chummer.World.Contracts.csproj", ".tmp/nuget/packages"),
    ("Chummer.Run.Api", "Chummer.Run.Api.csproj", ".tmp/nuget/packages"),
    ("Chummer.Run.Identity", "Chummer.Run.Identity.csproj", ".tmp/nuget/packages"),
    ("Chummer.Run.AI", "Chummer.Run.AI.csproj", ".tmp/nuget/packages"),
)
PROJECT_ROOTS = tuple(item[0] for item in PROJECT_SPECS)
SMOKE_SOURCE_ROOT = "tests/RunServicesSmoke"
TREE_EXCLUDED_DIRECTORIES = frozenset(("bin", "obj", "TestResults", ".tmp"))
ANCESTOR_BUILD_CONTROL_NAMES = frozenset((
    ".editorconfig",
    "global.json",
    "NuGet.Config",
    "nuget.config",
    "Directory.Build.props",
    "Directory.Build.targets",
    "Directory.Packages.props",
    "Directory.Packages.targets",
    "Directory.Build.rsp",
    "MSBuild.rsp",
    "packages.lock.json",
))
RUNTIME_DATA_SPECS = (
    (".codex-design/product", ".codex-design/product"),
    ("../chummer-design/products/chummer", "products/chummer"),
)
RUNTIME_DATA_FILES = (("scripts/runbook.sh", "scripts/runbook.sh"),)
MANAGED_COMPONENT_ROOTS = (
    "hostfxr",
    "Microsoft.NETCore.App",
    "Microsoft.AspNetCore.App",
    "Microsoft.NETCore.App.Ref",
    "Microsoft.AspNetCore.App.Ref",
    "sdk",
)

RUNTIME_CLOSURE_PATHS = (
    "Chummer.Campaign.Contracts.dll",
    "Chummer.Control.Contracts.dll",
    "Chummer.Engine.Contracts.dll",
    "Chummer.Hub.Registry.Contracts.dll",
    "Chummer.Media.Contracts.dll",
    "Chummer.Media.Factory.Runtime.dll",
    "Chummer.Play.Contracts.dll",
    "Chummer.Run.AI.dll",
    "Chummer.Run.Api.dll",
    "Chummer.Run.Contracts.dll",
    "Chummer.Run.Identity.dll",
    "Chummer.Run.Registry.dll",
    "Chummer.World.Contracts.dll",
    "RunServicesSmoke.dll",
    "RunServicesSmoke.runtimeconfig.json",
    "YamlDotNet.dll",
)
MANIFEST_PATHS = tuple(sorted((*RUNTIME_CLOSURE_PATHS, "toolchain/dotnet", "toolchain/csc.dll")))

JOURNEY_IDS = (
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "recover_from_sync_conflict",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
)
CHECKPOINT_IDS = {
    journey_id: f"{journey_id}.run_services_smoke_exit_zero"
    for journey_id in JOURNEY_IDS
}

ROOT_FIELDS = (
    "contract_name",
    "contract_version",
    "status",
    "proof_kind",
    "run_id",
    "started_at",
    "completed_at",
    "generated_at",
    "expires_at",
    "invocation",
    "inputs",
    "execution",
    "journeys",
    "summary",
)
INPUT_FIELDS = (
    "source",
    "journey_spec",
    "runner",
    "prepare_helper",
    "environment_helper",
    "cleanroom_builder",
    "registry_global_usings",
    "materializer",
    "contract_module",
    "dotnet_host",
    "csc",
    "assembly",
)
EXECUTION_FIELDS = (
    "phase",
    "failure_reason",
    "candidate_source_build_inputs_before",
    "candidate_source_build_inputs_after",
    "staged_candidate_inputs_before",
    "staged_candidate_inputs_after",
    "managed_dotnet_closure_before",
    "managed_dotnet_closure_after",
    "runtime_manifest_before",
    "runtime_manifest_after",
    "checkpoint_log",
    "runtime_checkpoints",
    "candidate_source_build_inputs_stable",
    "staged_candidate_inputs_stable",
    "managed_dotnet_closure_stable",
    "runtime_closure_stable",
    "closure_stable",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SPEC_VERSION_RE = re.compile(r"^version:\s*([0-9]+)\s*$")
_SPEC_JOURNEY_RE = re.compile(r"^  - id:\s*([a-z0-9_]+)\s*$")
_SDK_VERSION_RE = re.compile(r"^[0-9A-Za-z._-]+$")
_FRAMEWORK_VERSION_RE = re.compile(r"^10\.0\.(0|[1-9][0-9]*)$")
_DOTNET_VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<metadata>[0-9A-Za-z.-]+))?$"
)


class ProofContractError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason_code: str
    payload: dict[str, Any] | None = None


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def normalize_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProofContractError("timestamp_not_utc")
    return value.astimezone(dt.timezone.utc).replace(microsecond=0)


def format_utc(value: dt.datetime) -> str:
    return normalize_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: object) -> dt.datetime:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise ProofContractError("timestamp_invalid")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ProofContractError("timestamp_invalid") from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _reject_symlink_components(path: Path, *, allow_leaf_symlink: bool = False) -> None:
    absolute = _absolute(path)
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    for index, part in enumerate(parts):
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError as exc:
            raise ProofContractError("path_component_missing") from exc
        except OSError as exc:
            raise ProofContractError("path_component_stat_failed") from exc
        is_leaf = index == len(parts) - 1
        if stat.S_ISLNK(metadata.st_mode) and not (is_leaf and allow_leaf_symlink):
            raise ProofContractError("path_symlink_component")


def _read_regular_bytes(
    path: Path,
    *,
    max_bytes: int,
    reason_prefix: str,
    allow_empty: bool = False,
) -> bytes:
    absolute = _absolute(path)
    try:
        _reject_symlink_components(absolute)
        before = os.lstat(absolute)
    except ProofContractError as exc:
        if exc.reason_code == "path_component_missing":
            raise ProofContractError(f"{reason_prefix}_missing") from exc
        if exc.reason_code == "path_symlink_component":
            raise ProofContractError(f"{reason_prefix}_symlink") from exc
        raise ProofContractError(f"{reason_prefix}_stat_failed") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ProofContractError(f"{reason_prefix}_not_regular")
    if before.st_size < 0 or (before.st_size == 0 and not allow_empty):
        raise ProofContractError(f"{reason_prefix}_empty")
    if before.st_size > max_bytes:
        raise ProofContractError(f"{reason_prefix}_too_large")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise ProofContractError(f"{reason_prefix}_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ProofContractError(f"{reason_prefix}_not_regular")
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ProofContractError(f"{reason_prefix}_unstable")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after_open = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(data) > max_bytes:
        raise ProofContractError(f"{reason_prefix}_too_large")
    stable_open = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    )
    if len(data) != opened.st_size or stable_open != (
        after_open.st_dev,
        after_open.st_ino,
        after_open.st_size,
        after_open.st_mtime_ns,
    ):
        raise ProofContractError(f"{reason_prefix}_unstable")
    try:
        after_path = os.lstat(absolute)
    except OSError as exc:
        raise ProofContractError(f"{reason_prefix}_unstable") from exc
    if stable_open != (
        after_path.st_dev,
        after_path.st_ino,
        after_path.st_size,
        after_path.st_mtime_ns,
    ):
        raise ProofContractError(f"{reason_prefix}_unstable")
    return data


def _identity(path: Path, logical_path: str) -> dict[str, object]:
    data = _read_regular_bytes(path, max_bytes=MAX_INPUT_BYTES, reason_prefix="input")
    return {
        "path": logical_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _external_identity(path: Path) -> dict[str, object]:
    absolute = _absolute(path)
    data = _read_regular_bytes(absolute, max_bytes=MAX_INPUT_BYTES, reason_prefix="input")
    return {
        "path": str(absolute),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _dotnet_identity(path: Path) -> dict[str, object]:
    requested = _absolute(path)
    try:
        _reject_symlink_components(requested, allow_leaf_symlink=True)
        resolved = requested.resolve(strict=True)
    except (OSError, ProofContractError) as exc:
        raise ProofContractError("dotnet_host_invalid") from exc
    data = _read_regular_bytes(resolved, max_bytes=MAX_INPUT_BYTES, reason_prefix="dotnet_host")
    return {
        "path": str(requested),
        "resolved_path": str(resolved),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _assembly_identity(path: Path) -> dict[str, object]:
    if path.name != ASSEMBLY_FILE_NAME:
        raise ProofContractError("assembly_file_name_mismatch")
    data = _read_regular_bytes(path, max_bytes=MAX_INPUT_BYTES, reason_prefix="assembly")
    return {
        "file_name": ASSEMBLY_FILE_NAME,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _parse_journey_spec(data: bytes) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProofContractError("journey_spec_invalid_utf8") from exc
    versions: list[int] = []
    in_journeys = False
    journey_ids: list[str] = []
    for line in text.splitlines():
        version = _SPEC_VERSION_RE.fullmatch(line)
        if version is not None:
            versions.append(int(version.group(1)))
        if line == "journey_gates:":
            if in_journeys:
                raise ProofContractError("journey_spec_duplicate_section")
            in_journeys = True
            continue
        if in_journeys:
            journey = _SPEC_JOURNEY_RE.fullmatch(line)
            if journey is not None:
                journey_ids.append(journey.group(1))
    if versions != [JOURNEY_SPEC_VERSION]:
        raise ProofContractError("journey_spec_version_mismatch")
    if tuple(journey_ids) != JOURNEY_IDS:
        raise ProofContractError("journey_spec_set_mismatch")


def _canonical_digest(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _validate_relative_tree_path(path: str, reason_prefix: str) -> None:
    pure = PurePosixPath(path)
    if (
        not path
        or pure.is_absolute()
        or pure.as_posix() != path
        or ".." in pure.parts
        or "." in pure.parts
        or "\\" in path
        or "\x00" in path
    ):
        raise ProofContractError(f"{reason_prefix}_path_invalid")


def _scan_tree_once(
    root: Path,
    *,
    excluded_directories: frozenset[str],
    reason_prefix: str,
    allow_missing: bool = False,
) -> list[dict[str, object]] | None:
    absolute = _absolute(root)
    try:
        _reject_symlink_components(absolute)
        root_metadata = os.lstat(absolute)
    except ProofContractError as exc:
        if allow_missing and exc.reason_code == "path_component_missing":
            return None
        if exc.reason_code == "path_symlink_component":
            raise ProofContractError(f"{reason_prefix}_symlink") from exc
        raise ProofContractError(f"{reason_prefix}_root_invalid") from exc
    except FileNotFoundError:
        if allow_missing:
            return None
        raise ProofContractError(f"{reason_prefix}_root_missing")
    except OSError as exc:
        raise ProofContractError(f"{reason_prefix}_root_invalid") from exc
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ProofContractError(f"{reason_prefix}_root_not_directory")

    def raise_walk_error(error: OSError) -> None:
        raise ProofContractError(f"{reason_prefix}_scan_failed") from error

    def reject_excluded_symlinks(excluded_root: Path) -> None:
        for excluded_directory, excluded_names, excluded_files in os.walk(
            excluded_root,
            followlinks=False,
            onerror=raise_walk_error,
        ):
            excluded_directory_path = Path(excluded_directory)
            for excluded_name in (*excluded_names, *excluded_files):
                try:
                    excluded_metadata = os.lstat(excluded_directory_path / excluded_name)
                except OSError as exc:
                    raise ProofContractError(f"{reason_prefix}_unstable") from exc
                if stat.S_ISLNK(excluded_metadata.st_mode):
                    raise ProofContractError(f"{reason_prefix}_symlink")

    entries: list[dict[str, object]] = []
    total_size = 0
    for directory, directory_names, file_names in os.walk(
        absolute,
        followlinks=False,
        onerror=raise_walk_error,
    ):
        directory_path = Path(directory)
        try:
            directory_metadata = os.lstat(directory_path)
        except OSError as exc:
            raise ProofContractError(f"{reason_prefix}_unstable") from exc
        if stat.S_ISLNK(directory_metadata.st_mode):
            raise ProofContractError(f"{reason_prefix}_symlink")
        if not stat.S_ISDIR(directory_metadata.st_mode):
            raise ProofContractError(f"{reason_prefix}_non_regular")

        retained_directories: list[str] = []
        for name in sorted(directory_names):
            child = directory_path / name
            try:
                child_metadata = os.lstat(child)
            except OSError as exc:
                raise ProofContractError(f"{reason_prefix}_unstable") from exc
            if stat.S_ISLNK(child_metadata.st_mode):
                raise ProofContractError(f"{reason_prefix}_symlink")
            if not stat.S_ISDIR(child_metadata.st_mode):
                raise ProofContractError(f"{reason_prefix}_non_regular")
            if name in excluded_directories:
                reject_excluded_symlinks(child)
            else:
                retained_directories.append(name)
        directory_names[:] = retained_directories

        for name in sorted(file_names):
            path = directory_path / name
            relative = path.relative_to(absolute).as_posix()
            _validate_relative_tree_path(relative, reason_prefix)
            try:
                metadata = os.lstat(path)
            except OSError as exc:
                raise ProofContractError(f"{reason_prefix}_unstable") from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise ProofContractError(f"{reason_prefix}_symlink")
            if not stat.S_ISREG(metadata.st_mode):
                raise ProofContractError(f"{reason_prefix}_non_regular")
            data = _read_regular_bytes(
                path,
                max_bytes=MAX_INPUT_BYTES,
                reason_prefix=reason_prefix,
                allow_empty=True,
            )
            total_size += len(data)
            if total_size > MAX_TREE_TOTAL_BYTES:
                raise ProofContractError(f"{reason_prefix}_too_large")
            entries.append({
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            })
            if len(entries) > MAX_TREE_FILES:
                raise ProofContractError(f"{reason_prefix}_too_many_files")

    entries.sort(key=lambda item: str(item["path"]))
    if len({item["path"] for item in entries}) != len(entries):
        raise ProofContractError(f"{reason_prefix}_duplicate_path")
    return entries


def _stable_tree_entries(
    root: Path,
    *,
    excluded_directories: frozenset[str] = frozenset(),
    reason_prefix: str,
    allow_missing: bool = False,
) -> list[dict[str, object]] | None:
    first = _scan_tree_once(
        root,
        excluded_directories=excluded_directories,
        reason_prefix=reason_prefix,
        allow_missing=allow_missing,
    )
    second = _scan_tree_once(
        root,
        excluded_directories=excluded_directories,
        reason_prefix=reason_prefix,
        allow_missing=allow_missing,
    )
    if first != second:
        raise ProofContractError(f"{reason_prefix}_unstable")
    return first


def _tree_record(
    root_label: str,
    path: Path,
    *,
    excluded_directories: frozenset[str] = frozenset(),
    reason_prefix: str,
    allow_missing: bool = False,
) -> dict[str, object]:
    entries = _stable_tree_entries(
        path,
        excluded_directories=excluded_directories,
        reason_prefix=reason_prefix,
        allow_missing=allow_missing,
    )
    if entries is None:
        digest = _canonical_digest({"root": root_label, "state": "missing"})
        return {
            "root": root_label,
            "file_count": 0,
            "total_size_bytes": 0,
            "tree_sha256": digest,
        }
    return {
        "root": root_label,
        "file_count": len(entries),
        "total_size_bytes": sum(int(item["size_bytes"]) for item in entries),
        "tree_sha256": _canonical_digest(entries),
    }


def _scan_explicit_files_once(
    items: Sequence[tuple[str, Path]],
    *,
    reason_prefix: str,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    logical_paths: set[str] = set()
    absolute_paths: set[str] = set()
    total_size = 0
    for logical_path, path in sorted(items, key=lambda item: item[0]):
        if not logical_path or logical_path in logical_paths:
            raise ProofContractError(f"{reason_prefix}_duplicate_path")
        absolute = _absolute(path)
        absolute_key = str(absolute)
        if absolute_key in absolute_paths:
            raise ProofContractError(f"{reason_prefix}_duplicate_path")
        logical_paths.add(logical_path)
        absolute_paths.add(absolute_key)
        data = _read_regular_bytes(
            absolute,
            max_bytes=MAX_INPUT_BYTES,
            reason_prefix=reason_prefix,
            allow_empty=True,
        )
        total_size += len(data)
        if total_size > MAX_TREE_TOTAL_BYTES:
            raise ProofContractError(f"{reason_prefix}_too_large")
        entries.append({
            "path": logical_path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        })
    if len(entries) > MAX_TREE_FILES:
        raise ProofContractError(f"{reason_prefix}_too_many_files")
    return entries


def _explicit_files_record(
    root_label: str,
    items: Sequence[tuple[str, Path]],
    *,
    reason_prefix: str,
) -> dict[str, object]:
    first = _scan_explicit_files_once(items, reason_prefix=reason_prefix)
    second = _scan_explicit_files_once(items, reason_prefix=reason_prefix)
    if first != second:
        raise ProofContractError(f"{reason_prefix}_unstable")
    return {
        "root": root_label,
        "file_count": len(first),
        "total_size_bytes": sum(int(item["size_bytes"]) for item in first),
        "tree_sha256": _canonical_digest(first),
    }


def _ancestor_control_items(root: Path) -> list[tuple[str, Path]]:
    discovered: dict[str, Path] = {}
    for logical_root in (*PROJECT_ROOTS, SMOKE_SOURCE_ROOT):
        current = _absolute(root / logical_root).parent
        while True:
            for name in sorted(ANCESTOR_BUILD_CONTROL_NAMES):
                candidate = current / name
                try:
                    os.lstat(candidate)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise ProofContractError("ancestor_build_controls_unstable") from exc
                key = str(_absolute(candidate))
                discovered[key] = candidate
            if current.parent == current:
                break
            current = current.parent
    return [(path, candidate) for path, candidate in sorted(discovered.items())]


def _ancestor_controls_record(root: Path) -> dict[str, object]:
    first_items = _ancestor_control_items(root)
    first = _scan_explicit_files_once(first_items, reason_prefix="ancestor_build_controls")
    second_items = _ancestor_control_items(root)
    second = _scan_explicit_files_once(second_items, reason_prefix="ancestor_build_controls")
    if first != second:
        raise ProofContractError("ancestor_build_controls_unstable")
    return {
        "root": "ancestor_build_controls",
        "file_count": len(first),
        "total_size_bytes": sum(int(item["size_bytes"]) for item in first),
        "tree_sha256": _canonical_digest(first),
    }


def _project_asset_items(root: Path) -> list[tuple[str, Path]]:
    return [
        (f"{project_root}/obj/project.assets.json", root / project_root / "obj" / "project.assets.json")
        for project_root, _project_file, _package_root in PROJECT_SPECS
    ]


def _generated_nuget_import_items(root: Path) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for project_root, project_file, _package_root in PROJECT_SPECS:
        for suffix in ("nuget.g.props", "nuget.g.targets"):
            relative = f"{project_root}/obj/{project_file}.{suffix}"
            items.append((relative, root / project_root / "obj" / f"{project_file}.{suffix}"))
    return items


def _validate_safe_msbuild_target(element: ET.Element) -> None:
    name = element.attrib.get("Name")
    if name == "EnsureRuntimeMetadataForReferencingProjects":
        if element.attrib != {
            "Name": "EnsureRuntimeMetadataForReferencingProjects",
            "BeforeTargets": "AddDepsJsonAndRuntimeConfigToCopyItemsForReferencingProjects",
            "DependsOnTargets": "GenerateBuildDependencyFile;GenerateBuildRuntimeConfigurationFiles",
            "Condition": "'$(HasRuntimeOutput)' == 'true' and ('$(GenerateDependencyFile)' == 'true' or '$(GenerateRuntimeConfigurationFiles)' == 'true')",
        } or list(element):
            raise ProofContractError("msbuild_target_untrusted")
        return
    if name == "MaterializeReferenceAssemblyFallback":
        children = list(element)
        if (
            element.attrib != {
                "Name": "MaterializeReferenceAssemblyFallback",
                "AfterTargets": "Build",
                "Condition": "'$(ProduceReferenceAssembly)' == 'true' and '$(TargetRefPath)' != '' and Exists('$(TargetPath)') and !Exists('$(TargetRefPath)')",
            }
            or len(children) != 2
            or children[0].tag.rsplit("}", 1)[-1] != "MakeDir"
            or children[0].attrib != {
                "Directories": "$([System.IO.Path]::GetDirectoryName('$(TargetRefPath)'))"
            }
            or children[1].tag.rsplit("}", 1)[-1] != "Copy"
            or children[1].attrib != {
                "SourceFiles": "$(TargetPath)",
                "DestinationFiles": "$(TargetRefPath)",
                "SkipUnchangedFiles": "true",
            }
        ):
            raise ProofContractError("msbuild_target_untrusted")
        return
    raise ProofContractError("msbuild_target_untrusted")


def _validate_closed_msbuild_definitions(root: Path) -> None:
    definition_paths: dict[str, Path] = {}
    build_suffixes = frozenset((".csproj", ".proj", ".props", ".targets"))
    primary_projects: dict[str, tuple[str, str]] = {}
    generated_package_roots: dict[str, Path] = {}
    for logical_root, project_file, package_root in PROJECT_SPECS:
        project_root = root / logical_root
        entries = _stable_tree_entries(
            project_root,
            excluded_directories=TREE_EXCLUDED_DIRECTORIES,
            reason_prefix="msbuild_definition_tree",
        )
        if entries is None:
            raise ProofContractError("msbuild_definition_tree_missing")
        for entry in entries:
            relative = str(entry["path"])
            path = project_root / PurePosixPath(relative)
            if path.suffix.lower() == ".rsp":
                raise ProofContractError("msbuild_response_file_untrusted")
        primary_path = project_root / project_file
        primary_key = str(_absolute(primary_path))
        definition_paths[primary_key] = primary_path
        primary_projects[primary_key] = (logical_root, project_file)
        for control_name in ANCESTOR_BUILD_CONTROL_NAMES:
            control_path = project_root / control_name
            try:
                control_metadata = os.lstat(control_path)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise ProofContractError("msbuild_definition_unstable") from exc
            if stat.S_ISLNK(control_metadata.st_mode):
                raise ProofContractError("msbuild_definition_symlink")
            if control_path.suffix.lower() == ".rsp":
                raise ProofContractError("msbuild_response_file_untrusted")
            if control_path.suffix.lower() in build_suffixes:
                definition_paths[str(_absolute(control_path))] = control_path
        cache_root = _absolute(root / package_root)
        for suffix in ("nuget.g.props", "nuget.g.targets"):
            generated_path = project_root / "obj" / f"{project_file}.{suffix}"
            generated_key = str(_absolute(generated_path))
            definition_paths[generated_key] = generated_path
            generated_package_roots[generated_key] = cache_root
    for _logical, path in _generated_nuget_import_items(root):
        definition_paths[str(_absolute(path))] = path
    for _logical, path in _ancestor_control_items(root):
        if path.suffix.lower() == ".rsp":
            raise ProofContractError("msbuild_response_file_untrusted")
        if path.suffix.lower() in build_suffixes:
            definition_paths[str(_absolute(path))] = path

    allowed_properties = frozenset((
        "AddRazorSupportForMvc", "AnalysisLevel", "AssemblyName", "AssemblyVersion",
        "ChummerDesktopRuntimeIdentifiers", "ChummerEngineContractsLocalFeed",
        "ChummerEngineContractsPackageVersion", "ChummerLocalContractsProject",
        "ChummerMediaContractsAssembly", "ChummerMediaContractsProject", "DefaultItemExcludes",
        "Description", "EnableDefaultCompileItems", "EnableDefaultRazorGenerateItems",
        "EnableNETAnalyzers", "FileVersion", "GenerateDocumentationFile",
        "GeneratePackageOnBuild", "GenerateRuntimeConfigurationFiles", "ImplicitUsings",
        "IsPackable", "MaxCpuCount", "NoWarn", "NuGetPackageFolders", "NuGetPackageRoot",
        "NuGetProjectStyle", "NuGetToolVersion", "Nullable", "OutputType", "PackageId",
        "PackageReadmeFile", "PackageTags", "PreferBundledChummerMediaContracts",
        "ProduceReferenceAssembly", "ProjectAssetsFile", "RazorCompileOnBuild",
        "RazorCompileOnPublish", "RepositoryType", "RestoreAdditionalProjectSources",
        "RestorePackagesPath", "RestoreSuccess", "RestoreTool", "RestoreUseStaticGraphEvaluation",
        "RootNamespace", "RunBrowserSurfaceProxyTimeoutApiOnly", "RuntimeIdentifiers",
        "TargetFramework", "Title", "TreatWarningsAsErrors", "Version",
    ))
    allowed_conditions = frozenset((
        " '$(ExcludeRestorePackageImports)' != 'true' ",
        " '$(NuGetPackageFolders)' == '' ",
        " '$(NuGetPackageRoot)' == '' ",
        " '$(NuGetProjectStyle)' == '' ",
        " '$(NuGetToolVersion)' == '' ",
        " '$(ProjectAssetsFile)' == '' ",
        " '$(RestoreSuccess)' == '' ",
        " '$(RestoreTool)' == '' ",
        "'$(ChummerDesktopRuntimeIdentifiers)' == ''",
        "'$(ChummerLocalContractsProject)' == '' and Exists('$(MSBuildThisFileDirectory)Chummer.Contracts/Chummer.Contracts.csproj')",
        "'$(ChummerMediaContractsAssembly)' == '' and Exists('$(MSBuildThisFileDirectory)../compat/Chummer.Media.Contracts.dll')",
        "'$(ChummerMediaContractsProject)' != ''",
        "'$(PreferBundledChummerMediaContracts)' != 'true' and '$(ChummerMediaContractsProject)' == '' and Exists('$(MSBuildThisFileDirectory)../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj')",
        "'$(PreferBundledChummerMediaContracts)' != 'true' and '$(ChummerMediaContractsProject)' == '' and Exists('$(MSBuildThisFileDirectory)../../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj')",
        "'$(PreferBundledChummerMediaContracts)' == ''",
        "'$(ProduceReferenceAssembly)' == 'true' and '$(TargetRefPath)' != '' and Exists('$(TargetPath)') and !Exists('$(TargetRefPath)')",
        "'$(RestorePackagesPath)' == ''",
        "'$(RunBrowserSurfaceProxyTimeoutApiOnly)' != 'true'",
        "'$(RunBrowserSurfaceProxyTimeoutApiOnly)' == ''",
        "'$(RunBrowserSurfaceProxyTimeoutApiOnly)' == 'true'",
        "'$(RuntimeIdentifiers)' == ''",
        "'$(RuntimeIdentifiers)' == '' and '$(RuntimeIdentifier)' != ''",
        "'$(UseChummerEngineContractsLocalFeed)' != 'false' and Exists('$(ChummerEngineContractsLocalFeed)')",
        "'$(ChummerMediaContractsProject)' == '' and '$(ChummerMediaContractsAssembly)' != ''",
        "Exists('..\\..\\..\\fleet\\repos\\chummer-media-factory\\src\\Chummer.Media.Contracts\\Chummer.Media.Contracts.csproj')",
        "Exists('..\\..\\..\\fleet\\repos\\chummer-media-factory\\src\\Chummer.Media.Factory.Runtime\\Chummer.Media.Factory.Runtime.csproj')",
    ))
    allowed_property_expressions = {
        "ChummerDesktopRuntimeIdentifiers": frozenset(),
        "ChummerEngineContractsLocalFeed": frozenset((
            "$(MSBuildThisFileDirectory).tmp/ai/local-nuget",
        )),
        "ChummerLocalContractsProject": frozenset((
            "$(MSBuildThisFileDirectory)Chummer.Contracts/Chummer.Contracts.csproj",
        )),
        "ChummerMediaContractsAssembly": frozenset((
            "$(MSBuildThisFileDirectory)../compat/Chummer.Media.Contracts.dll",
        )),
        "ChummerMediaContractsProject": frozenset((
            "$(MSBuildThisFileDirectory)../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj",
            "$(MSBuildThisFileDirectory)../../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj",
        )),
        "DefaultItemExcludes": frozenset((
            "$(DefaultItemExcludes);**/obj_tmp/**",
            "$(DefaultItemExcludes);$(MSBuildThisFileDirectory).state/**",
        )),
        "ProjectAssetsFile": frozenset((
            "$(MSBuildThisFileDirectory)project.assets.json",
        )),
        "RestoreAdditionalProjectSources": frozenset((
            "$(RestoreAdditionalProjectSources);$(ChummerEngineContractsLocalFeed)",
        )),
        "RestorePackagesPath": frozenset((
            "$(MSBuildThisFileDirectory).tmp/nuget/packages",
        )),
        "RuntimeIdentifiers": frozenset((
            "$(ChummerDesktopRuntimeIdentifiers)",
            "$(RuntimeIdentifier)",
        )),
    }
    allowed_item_attributes = {
        "Compile": frozenset(("Include",)),
        "Content": frozenset(("Include", "Update", "Remove", "CopyToPublishDirectory")),
        "EmbeddedResource": frozenset(("Include",)),
        "None": frozenset(("Include", "Pack", "PackagePath", "Visible")),
        "PackageReference": frozenset(("Include", "Version")),
        "ProjectReference": frozenset(("Include", "Condition", "ReferenceOutputAssembly")),
        "Reference": frozenset(("Include", "Condition")),
        "SourceRoot": frozenset(("Include",)),
    }
    expected_project_paths = tuple(Path(path) for path in sorted(primary_projects))
    expected_package_references = frozenset((
        ("Npgsql", "10.0.3"),
        ("YamlDotNet", "16.3.0"),
    ))
    expected_reference_outputs: set[str] = set()
    for logical_root, project_file, _package_root in PROJECT_SPECS:
        assembly_name = "Chummer.Engine.Contracts" if project_file == "Chummer.Contracts.csproj" else Path(project_file).stem
        expected_reference_outputs.add(str(_absolute(
            root / logical_root / "bin" / "Debug" / "net10.0" / f"{assembly_name}.dll"
        )))
    configured_cache_roots = frozenset(
        str(_absolute(root / package_root))
        for _logical_root, _project_file, package_root in PROJECT_SPECS
    )

    def validate_condition(value: str | None) -> None:
        if value is not None and value not in allowed_conditions:
            raise ProofContractError("msbuild_condition_untrusted")

    def same_bound_project(path: Path) -> bool:
        absolute = _absolute(path)
        try:
            _reject_symlink_components(absolute)
            metadata = os.lstat(absolute)
        except (OSError, ProofContractError):
            return False
        if not stat.S_ISREG(metadata.st_mode):
            return False
        for expected in expected_project_paths:
            try:
                if absolute == expected or os.path.samefile(absolute, expected):
                    return True
            except OSError:
                continue
        return False

    def resolve_definition_path(value: str, definition: Path) -> Path:
        normalized = value.replace("\\", "/")
        normalized = normalized.replace("$(MSBuildProjectDirectory)", str(definition.parent))
        normalized = normalized.replace("$(MSBuildThisFileDirectory)", f"{definition.parent}/")
        if "$(" in normalized or "$([" in normalized:
            raise ProofContractError("msbuild_path_property_untrusted")
        path = Path(normalized)
        return _absolute(path if path.is_absolute() else definition.parent / path)

    media_project_declaration_count = 0
    selected_media_project: Path | None = None
    for definition_key, candidate in definition_paths.items():
        if definition_key not in primary_projects or candidate.name != "Chummer.Run.Contracts.csproj":
            continue
        candidate_data = _read_regular_bytes(
            candidate,
            max_bytes=MAX_INPUT_BYTES,
            reason_prefix="msbuild_definition",
            allow_empty=False,
        )
        candidate_document = ET.fromstring(candidate_data)
        for candidate_element in candidate_document.iter():
            if candidate_element.tag.rsplit("}", 1)[-1] != "ChummerMediaContractsProject":
                continue
            media_project_declaration_count += 1
            candidate_path = resolve_definition_path(
                (candidate_element.text or "").strip(),
                candidate,
            )
            if selected_media_project is None and os.path.exists(candidate_path):
                selected_media_project = candidate_path
    if media_project_declaration_count and (
        selected_media_project is None or not same_bound_project(selected_media_project)
    ):
        raise ProofContractError("msbuild_media_project_selection_untrusted")

    def validate_project_reference(value: str, definition: Path) -> None:
        if value == "$(ChummerMediaContractsProject)":
            if selected_media_project is None or not same_bound_project(selected_media_project):
                raise ProofContractError("msbuild_project_reference_untrusted")
            return
        if not same_bound_project(resolve_definition_path(value, definition)):
            raise ProofContractError("msbuild_project_reference_untrusted")

    def validate_local_item_path(value: str, definition: Path) -> None:
        normalized = value.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if (
            not normalized
            or pure.is_absolute()
            or ".." in pure.parts
            or "$(" in normalized
            or "$([" in normalized
            or "$" in normalized
            or "@(" in normalized
            or "%(" in normalized
            or ";" in normalized
            or ":" in normalized
            or "\n" in normalized
            or "\r" in normalized
            or "\x00" in normalized
        ):
            raise ProofContractError("msbuild_item_path_untrusted")

    def validate_hint_path(value: str, definition: Path) -> None:
        if value == "$(ChummerMediaContractsAssembly)":
            if definition.name != "Chummer.Run.Contracts.csproj":
                raise ProofContractError("msbuild_hint_path_untrusted")
            return
        normalized = value.replace("$(Configuration)", "Debug")
        if str(resolve_definition_path(normalized, definition)) not in expected_reference_outputs:
            raise ProofContractError("msbuild_hint_path_untrusted")

    for path_key, path in sorted(definition_paths.items()):
        data = _read_regular_bytes(
            path,
            max_bytes=MAX_INPUT_BYTES,
            reason_prefix="msbuild_definition",
            allow_empty=False,
        )
        if b"<!DOCTYPE" in data.upper():
            raise ProofContractError("msbuild_definition_untrusted")
        try:
            document = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ProofContractError("msbuild_definition_invalid") from exc
        if document.tag.rsplit("}", 1)[-1] != "Project":
            raise ProofContractError("msbuild_definition_invalid")
        if not set(document.attrib).issubset({"Sdk", "ToolsVersion"}):
            raise ProofContractError("msbuild_project_attribute_untrusted")
        sdk = document.attrib.get("Sdk")
        if sdk is not None and sdk not in ("Microsoft.NET.Sdk", "Microsoft.NET.Sdk.Web"):
            raise ProofContractError("msbuild_sdk_untrusted")
        tools_version = document.attrib.get("ToolsVersion")
        if tools_version is not None and (
            tools_version != "14.0" or path_key not in generated_package_roots
        ):
            raise ProofContractError("msbuild_tools_version_untrusted")
        property_values: dict[str, list[str]] = {}
        source_root_values: list[str] = []
        for group in document:
            group_tag = group.tag.rsplit("}", 1)[-1]
            if group_tag in ("Import", "UsingTask", "Sdk", "Exec"):
                raise ProofContractError("msbuild_definition_untrusted")
            if group_tag == "PropertyGroup":
                if not set(group.attrib).issubset({"Condition"}):
                    raise ProofContractError("msbuild_group_attribute_untrusted")
                validate_condition(group.attrib.get("Condition"))
                for property_element in group:
                    property_name = property_element.tag.rsplit("}", 1)[-1]
                    if (
                        property_name not in allowed_properties
                        or list(property_element)
                        or not set(property_element.attrib).issubset({"Condition"})
                    ):
                        raise ProofContractError("msbuild_property_untrusted")
                    validate_condition(property_element.attrib.get("Condition"))
                    property_value = (property_element.text or "").strip()
                    if any(token in property_value for token in ("$([", "@(", "%(", "\x00", "\n", "\r")):
                        raise ProofContractError("msbuild_property_expression_untrusted")
                    if "$(" in property_value and property_value not in allowed_property_expressions.get(property_name, frozenset()):
                        raise ProofContractError("msbuild_property_expression_untrusted")
                    property_values.setdefault(property_name, []).append(property_value)
                    if property_name == "TargetFramework" and property_value != "net10.0":
                        raise ProofContractError("msbuild_target_framework_untrusted")
                    if property_name == "PreferBundledChummerMediaContracts" and property_value != "false":
                        raise ProofContractError("msbuild_property_value_untrusted")
                    if property_name == "EnableDefaultCompileItems" and property_value != "false":
                        raise ProofContractError("msbuild_property_value_untrusted")
                    if property_name == "RestorePackagesPath":
                        if str(resolve_definition_path(property_value, path)) not in configured_cache_roots:
                            raise ProofContractError("msbuild_restore_path_untrusted")
                    if property_name in ("NuGetPackageRoot", "NuGetPackageFolders"):
                        expected_cache = generated_package_roots.get(path_key)
                        if expected_cache is None or _absolute(Path(property_value)) != expected_cache:
                            raise ProofContractError("msbuild_nuget_path_untrusted")
                    if property_name == "ProjectAssetsFile":
                        if path_key not in generated_package_roots or property_value != "$(MSBuildThisFileDirectory)project.assets.json":
                            raise ProofContractError("msbuild_assets_path_untrusted")
                    if property_name == "ChummerLocalContractsProject":
                        expected_core = _absolute(root / "../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj")
                        if resolve_definition_path(property_value, path) != expected_core:
                            raise ProofContractError("msbuild_property_path_untrusted")
                    if property_name == "ChummerMediaContractsProject" and property_value not in (
                        "$(MSBuildThisFileDirectory)../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj",
                        "$(MSBuildThisFileDirectory)../../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj",
                    ):
                        raise ProofContractError("msbuild_property_path_untrusted")
                    if property_name == "ChummerMediaContractsAssembly":
                        expected_compat = _absolute(root / "compat/Chummer.Media.Contracts.dll")
                        if (
                            property_value != "$(MSBuildThisFileDirectory)../compat/Chummer.Media.Contracts.dll"
                            or resolve_definition_path(property_value, path) != expected_compat
                        ):
                            raise ProofContractError("msbuild_property_path_untrusted")
                continue
            if group_tag == "ItemGroup":
                if not set(group.attrib).issubset({"Condition"}):
                    raise ProofContractError("msbuild_group_attribute_untrusted")
                validate_condition(group.attrib.get("Condition"))
                for item in group:
                    item_name = item.tag.rsplit("}", 1)[-1]
                    permitted_attributes = allowed_item_attributes.get(item_name)
                    if permitted_attributes is None or not set(item.attrib).issubset(permitted_attributes):
                        raise ProofContractError("msbuild_item_untrusted")
                    validate_condition(item.attrib.get("Condition"))
                    if item_name in ("Compile", "Content", "EmbeddedResource", "None"):
                        path_attributes = [
                            item.attrib[key]
                            for key in ("Include", "Update", "Remove")
                            if key in item.attrib
                        ]
                        if len(path_attributes) != 1:
                            raise ProofContractError("msbuild_item_path_untrusted")
                        validate_local_item_path(path_attributes[0], path)
                    elif item_name == "ProjectReference":
                        project_reference = item.attrib.get("Include")
                        if not isinstance(project_reference, str):
                            raise ProofContractError("msbuild_project_reference_untrusted")
                        if (
                            project_reference == "$(ChummerMediaContractsProject)"
                            and item.attrib.get("Condition") != "'$(ChummerMediaContractsProject)' != ''"
                        ):
                            raise ProofContractError("msbuild_project_reference_untrusted")
                        validate_project_reference(project_reference, path)
                    elif item_name == "PackageReference":
                        package_reference = (item.attrib.get("Include"), item.attrib.get("Version"))
                        if package_reference not in expected_package_references:
                            raise ProofContractError("msbuild_package_reference_untrusted")
                    elif item_name == "Reference":
                        if item.attrib.get("Include") not in {
                            "Chummer.Hub.Registry.Contracts", "Chummer.Play.Contracts",
                            "Chummer.Media.Contracts", "Chummer.Media.Factory.Runtime",
                        }:
                            raise ProofContractError("msbuild_reference_untrusted")
                    elif item_name == "SourceRoot":
                        expected_cache = generated_package_roots.get(path_key)
                        source_root = item.attrib.get("Include")
                        if expected_cache is None or source_root not in (str(expected_cache), f"{expected_cache}/"):
                            raise ProofContractError("msbuild_source_root_untrusted")
                        source_root_values.append(source_root)
                    for child in item:
                        child_name = child.tag.rsplit("}", 1)[-1]
                        child_value = (child.text or "").strip()
                        if item_name == "ProjectReference" and child_name == "ExcludeAssets":
                            if child.attrib or child_value != "contentFiles":
                                raise ProofContractError("msbuild_project_reference_untrusted")
                        elif item_name == "Reference" and child_name == "HintPath":
                            if child.attrib:
                                raise ProofContractError("msbuild_hint_path_untrusted")
                            validate_hint_path(child_value, path)
                        elif item_name == "Reference" and child_name == "Private":
                            if child.attrib or child_value != "true":
                                raise ProofContractError("msbuild_reference_untrusted")
                        else:
                            raise ProofContractError("msbuild_item_metadata_untrusted")
                    if item_name == "Reference":
                        hint_paths = [
                            (child.text or "").strip()
                            for child in item
                            if child.tag.rsplit("}", 1)[-1] == "HintPath"
                        ]
                        if hint_paths == ["$(ChummerMediaContractsAssembly)"] and item.attrib.get("Condition") != (
                            "'$(ChummerMediaContractsProject)' == '' and '$(ChummerMediaContractsAssembly)' != ''"
                        ):
                            raise ProofContractError("msbuild_reference_untrusted")
                continue
            if group_tag == "Target":
                _validate_safe_msbuild_target(group)
                continue
            raise ProofContractError("msbuild_group_untrusted")

        primary = primary_projects.get(path_key)
        if primary is not None:
            _logical_root, project_file = primary
            expected_assembly = "Chummer.Engine.Contracts" if project_file == "Chummer.Contracts.csproj" else Path(project_file).stem
            if property_values.get("TargetFramework") != ["net10.0"]:
                raise ProofContractError("msbuild_target_framework_untrusted")
            if any(value != expected_assembly for value in property_values.get("AssemblyName", [])):
                raise ProofContractError("msbuild_assembly_name_untrusted")
            if project_file == "Chummer.Contracts.csproj":
                unconditional_assembly_names = [
                    (element.text or "").strip()
                    for group in document
                    if group.tag.rsplit("}", 1)[-1] == "PropertyGroup" and "Condition" not in group.attrib
                    for element in group
                    if element.tag.rsplit("}", 1)[-1] == "AssemblyName" and "Condition" not in element.attrib
                ]
                if unconditional_assembly_names != ["Chummer.Engine.Contracts"]:
                    raise ProofContractError("msbuild_assembly_name_untrusted")
        generated_cache = generated_package_roots.get(path_key)
        if generated_cache is not None and path.name.endswith(".nuget.g.props"):
            if (
                property_values.get("ProjectAssetsFile") != ["$(MSBuildThisFileDirectory)project.assets.json"]
                or property_values.get("NuGetPackageRoot") != [str(generated_cache)]
                or property_values.get("NuGetPackageFolders") != [str(generated_cache)]
                or source_root_values != [f"{generated_cache}/"]
            ):
                raise ProofContractError("msbuild_generated_props_untrusted")
        for element in document.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "Target":
                _validate_safe_msbuild_target(element)
            elif tag in ("Import", "UsingTask", "Sdk", "Exec"):
                raise ProofContractError("msbuild_definition_untrusted")


def _asset_package_directories(root: Path) -> tuple[list[str], list[tuple[str, Path]]]:
    package_roots: set[str] = set()
    package_directories: dict[str, Path] = {}
    expected_projects = tuple(
        _absolute(root / project_root / project_file)
        for project_root, project_file, _package_root in PROJECT_SPECS
    )

    def is_bound_project(path: Path) -> bool:
        absolute = _absolute(path)
        try:
            _reject_symlink_components(absolute)
            metadata = os.lstat(absolute)
        except (OSError, ProofContractError):
            return False
        if not stat.S_ISREG(metadata.st_mode):
            return False
        for expected in expected_projects:
            try:
                if absolute == expected or os.path.samefile(absolute, expected):
                    return True
            except OSError:
                continue
        return False

    def resolve_asset_project_path(project_directory: Path, value: object) -> Path:
        if (
            not isinstance(value, str)
            or not value
            or "\\" in value
            or "\x00" in value
            or "$" in value
            or "@(" in value
            or "%(" in value
        ):
            raise ProofContractError("project_assets_project_path_invalid")
        path = Path(value)
        resolved = _absolute(path if path.is_absolute() else project_directory / path)
        if not is_bound_project(resolved):
            raise ProofContractError("project_assets_project_path_untrusted")
        return resolved

    for project_root, project_file, configured_package_root in PROJECT_SPECS:
        project_directory = _absolute(root / project_root)
        owning_project = _absolute(project_directory / project_file)
        asset_path = root / project_root / "obj" / "project.assets.json"
        data = _read_regular_bytes(
            asset_path,
            max_bytes=MAX_INPUT_BYTES,
            reason_prefix="project_assets",
        )
        try:
            asset = json.loads(data.decode("utf-8"), object_pairs_hook=_duplicate_rejector)
        except (UnicodeDecodeError, json.JSONDecodeError, ProofContractError) as exc:
            raise ProofContractError("project_assets_invalid") from exc
        if not isinstance(asset, dict) or asset.get("version") != 3:
            raise ProofContractError("project_assets_invalid")
        targets = asset.get("targets")
        if not isinstance(targets, dict) or not any(
            "net10.0" in str(key).lower() or "version=v10.0" in str(key).lower()
            for key in targets
        ):
            raise ProofContractError("project_assets_target_mismatch")
        logs = asset.get("logs", [])
        if not isinstance(logs, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("level"), str)
            for item in logs
        ):
            raise ProofContractError("project_assets_invalid")
        if any(item["level"].lower() == "error" for item in logs):
            raise ProofContractError("project_assets_restore_error")
        package_folders = asset.get("packageFolders")
        if not isinstance(package_folders, dict) or len(package_folders) != 1:
            raise ProofContractError("project_assets_package_root_mismatch")
        expected_root = _absolute(root / configured_package_root)
        package_folder = next(iter(package_folders))
        if not isinstance(package_folder, str) or not Path(package_folder).is_absolute():
            raise ProofContractError("project_assets_package_root_mismatch")
        actual_root = _absolute(Path(package_folder))
        if actual_root != expected_root:
            raise ProofContractError("project_assets_package_root_mismatch")
        try:
            _reject_symlink_components(expected_root)
            metadata = os.lstat(expected_root)
        except (OSError, ProofContractError) as exc:
            raise ProofContractError("nuget_package_root_invalid") from exc
        if not stat.S_ISDIR(metadata.st_mode):
            raise ProofContractError("nuget_package_root_invalid")
        package_roots.add(str(expected_root))

        libraries = asset.get("libraries")
        if not isinstance(libraries, dict):
            raise ProofContractError("project_assets_invalid")
        library_types: dict[str, str] = {}
        package_paths_by_library: dict[str, Path] = {}
        for library_key, library in libraries.items():
            if not isinstance(library_key, str) or not isinstance(library, dict):
                raise ProofContractError("project_assets_invalid")
            library_type = library.get("type")
            if library_type not in ("package", "project"):
                raise ProofContractError("project_assets_library_type_untrusted")
            library_types[library_key] = library_type
            if library_type == "project":
                if not set(library).issubset({"type", "path", "msbuildProject"}):
                    raise ProofContractError("project_assets_project_library_invalid")
                project_path = library.get("path")
                msbuild_project = library.get("msbuildProject")
                if project_path != msbuild_project:
                    raise ProofContractError("project_assets_project_path_mismatch")
                resolve_asset_project_path(project_directory, project_path)
                continue

            if not set(library).issubset({"type", "path", "files", "sha512"}):
                raise ProofContractError("project_assets_package_library_invalid")
            package_path = library.get("path")
            if not isinstance(package_path, str) or package_path != library_key.lower():
                raise ProofContractError("nuget_package_path_mismatch")
            _validate_relative_tree_path(package_path, "nuget_package")
            package_directory = _absolute(expected_root / package_path)
            try:
                package_directory.relative_to(expected_root)
            except ValueError as exc:
                raise ProofContractError("nuget_package_path_escape") from exc
            logical = f"{expected_root.as_posix()}::{package_path}"
            package_directories[logical] = package_directory
            package_paths_by_library[library_key] = package_directory
            files = library.get("files")
            if not isinstance(files, list) or not files:
                raise ProofContractError("project_assets_package_files_invalid")
            for relative_file in files:
                if not isinstance(relative_file, str):
                    raise ProofContractError("project_assets_package_files_invalid")
                _validate_relative_tree_path(relative_file, "nuget_package_file")
                package_file = _absolute(package_directory / relative_file)
                try:
                    package_file.relative_to(package_directory)
                    _read_regular_bytes(
                        package_file,
                        max_bytes=MAX_INPUT_BYTES,
                        reason_prefix="nuget_package_file",
                        allow_empty=True,
                    )
                except (ValueError, ProofContractError) as exc:
                    raise ProofContractError("project_assets_package_files_invalid") from exc

        path_sections = frozenset((
            "analyzers", "build", "buildMultiTargeting", "buildTransitive", "compile",
            "contentFiles", "native", "resource", "runtime", "runtimeTargets", "tools",
        ))
        dictionary_sections = frozenset(("dependencies",))
        list_sections = frozenset(("frameworkReferences",))
        scalar_sections = frozenset(("framework", "type"))
        for target_name, target in targets.items():
            if not isinstance(target_name, str) or not isinstance(target, dict):
                raise ProofContractError("project_assets_target_invalid")
            for library_key, target_library in target.items():
                if (
                    not isinstance(library_key, str)
                    or library_key not in library_types
                    or not isinstance(target_library, dict)
                    or target_library.get("type") != library_types[library_key]
                ):
                    raise ProofContractError("project_assets_target_library_invalid")
                if not set(target_library).issubset(
                    path_sections | dictionary_sections | list_sections | scalar_sections
                ):
                    raise ProofContractError("project_assets_target_section_untrusted")
                for section_name, section in target_library.items():
                    if section_name in scalar_sections:
                        if not isinstance(section, str):
                            raise ProofContractError("project_assets_target_section_invalid")
                        continue
                    if section_name in list_sections:
                        if not isinstance(section, list) or not all(
                            isinstance(item, str) for item in section
                        ):
                            raise ProofContractError("project_assets_target_section_invalid")
                        continue
                    if not isinstance(section, dict):
                        raise ProofContractError("project_assets_target_section_invalid")
                    if section_name in dictionary_sections:
                        if not all(isinstance(key, str) for key in section):
                            raise ProofContractError("project_assets_target_section_invalid")
                        continue
                    for relative_asset, metadata in section.items():
                        if not isinstance(relative_asset, str) or not isinstance(metadata, dict):
                            raise ProofContractError("project_assets_target_asset_invalid")
                        _validate_relative_tree_path(relative_asset, "project_assets_target_asset")
                        if library_types[library_key] == "package":
                            package_directory = package_paths_by_library.get(library_key)
                            if package_directory is None:
                                raise ProofContractError("project_assets_target_asset_invalid")
                            package_file = _absolute(package_directory / relative_asset)
                            try:
                                package_file.relative_to(package_directory)
                                _read_regular_bytes(
                                    package_file,
                                    max_bytes=MAX_INPUT_BYTES,
                                    reason_prefix="project_assets_target_asset",
                                    allow_empty=True,
                                )
                            except (ValueError, ProofContractError) as exc:
                                raise ProofContractError("project_assets_target_asset_invalid") from exc

        project = asset.get("project")
        if not isinstance(project, dict):
            raise ProofContractError("project_assets_project_metadata_missing")
        restore = project.get("restore")
        if not isinstance(restore, dict):
            raise ProofContractError("project_assets_project_metadata_invalid")
        restored_owner = resolve_asset_project_path(
            project_directory,
            restore.get("projectPath"),
        )
        unique_owner = resolve_asset_project_path(
            project_directory,
            restore.get("projectUniqueName"),
        )
        if not (
            os.path.samefile(restored_owner, owning_project)
            and os.path.samefile(unique_owner, owning_project)
        ):
            raise ProofContractError("project_assets_owner_mismatch")
        packages_path = restore.get("packagesPath")
        output_path = restore.get("outputPath")
        if (
            not isinstance(packages_path, str)
            or _absolute(Path(packages_path)) != expected_root
            or not isinstance(output_path, str)
            or _absolute(Path(output_path)) != _absolute(project_directory / "obj")
        ):
            raise ProofContractError("project_assets_restore_path_mismatch")
        restore_frameworks = restore.get("frameworks")
        if not isinstance(restore_frameworks, dict):
            raise ProofContractError("project_assets_restore_frameworks_invalid")
        for framework in restore_frameworks.values():
            if not isinstance(framework, dict):
                raise ProofContractError("project_assets_restore_frameworks_invalid")
            project_references = framework.get("projectReferences", {})
            if not isinstance(project_references, dict):
                raise ProofContractError("project_assets_project_references_invalid")
            for reference_path, reference in project_references.items():
                resolved_key = resolve_asset_project_path(project_directory, reference_path)
                if (
                    not isinstance(reference, dict)
                    or not set(reference).issubset({"projectPath", "excludeAssets"})
                    or resolve_asset_project_path(project_directory, reference.get("projectPath")) != resolved_key
                    or (
                        "excludeAssets" in reference
                        and reference.get("excludeAssets") != "contentfiles"
                    )
                ):
                    raise ProofContractError("project_assets_project_references_invalid")
    return sorted(package_roots), sorted(package_directories.items())


def _nuget_packages_record(root: Path) -> tuple[list[str], dict[str, object]]:
    package_roots, directories = _asset_package_directories(root)
    combined_entries: list[dict[str, object]] = []
    total_size = 0
    for logical_root, directory in directories:
        entries = _stable_tree_entries(directory, reason_prefix="nuget_package")
        if entries is None:
            raise ProofContractError("nuget_package_missing")
        for entry in entries:
            path = f"{logical_root}/{entry['path']}"
            combined_entries.append({
                "path": path,
                "sha256": entry["sha256"],
                "size_bytes": entry["size_bytes"],
            })
            total_size += int(entry["size_bytes"])
    combined_entries.sort(key=lambda item: str(item["path"]))
    if len({item["path"] for item in combined_entries}) != len(combined_entries):
        raise ProofContractError("nuget_package_duplicate_path")
    if len(combined_entries) > MAX_TREE_FILES or total_size > MAX_TREE_TOTAL_BYTES:
        raise ProofContractError("nuget_package_closure_too_large")
    return package_roots, {
        "root": "project_assets.packageFolders",
        "file_count": len(combined_entries),
        "total_size_bytes": total_size,
        "tree_sha256": _canonical_digest(combined_entries),
    }


def _candidate_source_build_inputs(root: Path) -> dict[str, object]:
    project_roots = [
        _tree_record(
            logical_root,
            root / logical_root,
            excluded_directories=TREE_EXCLUDED_DIRECTORIES,
            reason_prefix="candidate_project_tree",
        )
        for logical_root in PROJECT_ROOTS
    ]
    smoke_source_tree = _tree_record(
        SMOKE_SOURCE_ROOT,
        root / SMOKE_SOURCE_ROOT,
        excluded_directories=TREE_EXCLUDED_DIRECTORIES,
        reason_prefix="candidate_smoke_tree",
    )
    runtime_data_roots = [
        _tree_record(
            source_root,
            root / source_root,
            excluded_directories=TREE_EXCLUDED_DIRECTORIES,
            reason_prefix="runtime_data_tree",
        )
        for source_root, _stage_root in RUNTIME_DATA_SPECS
    ]
    runtime_data_files = _explicit_files_record(
        "runtime_data_files",
        [(source, root / source) for source, _stage in RUNTIME_DATA_FILES],
        reason_prefix="runtime_data_file",
    )
    ancestor_controls = _ancestor_controls_record(root)
    project_assets = _explicit_files_record(
        "project_assets",
        _project_asset_items(root),
        reason_prefix="project_assets",
    )
    generated_imports = _explicit_files_record(
        "generated_nuget_imports",
        _generated_nuget_import_items(root),
        reason_prefix="generated_nuget_imports",
    )
    _validate_closed_msbuild_definitions(root)
    package_roots, nuget_packages = _nuget_packages_record(root)
    body: dict[str, object] = {
        "kind": "candidate_source_build_inputs",
        "tree_format_version": TREE_FORMAT_VERSION,
        "project_roots": project_roots,
        "smoke_source_tree": smoke_source_tree,
        "runtime_data_roots": runtime_data_roots,
        "runtime_data_files": runtime_data_files,
        "ancestor_build_controls": ancestor_controls,
        "project_assets": project_assets,
        "generated_nuget_imports": generated_imports,
        "nuget_package_roots": package_roots,
        "nuget_packages": nuget_packages,
        "project_root_count": len(project_roots),
        "runtime_data_root_count": len(runtime_data_roots),
    }
    return {**body, "closure_sha256": _canonical_digest(body)}


def _version_sort_key(
    value: str,
) -> tuple[tuple[int, int, int], int, tuple[tuple[int, object], ...], str]:
    match = _DOTNET_VERSION_RE.fullmatch(value)
    if match is None or match.group("major") != "10":
        raise ProofContractError("managed_dotnet_version_invalid")
    core = (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )
    prerelease = match.group("prerelease")
    if prerelease is None:
        return core, 1, (), value
    identifiers: list[tuple[int, object]] = []
    for identifier in prerelease.split("."):
        if not identifier:
            raise ProofContractError("managed_dotnet_version_invalid")
        if identifier.isdigit():
            identifiers.append((0, int(identifier)))
        else:
            identifiers.append((1, identifier))
    return core, 0, tuple(identifiers), value


def _select_managed_version_directory(
    parent: Path,
    *,
    suffix: tuple[str, ...] = (),
) -> tuple[str, Path]:
    absolute_parent = _absolute(parent)
    try:
        _reject_symlink_components(absolute_parent)
        parent_metadata = os.lstat(absolute_parent)
    except (OSError, ProofContractError) as exc:
        raise ProofContractError("managed_dotnet_root_invalid") from exc
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise ProofContractError("managed_dotnet_root_invalid")
    candidates: list[tuple[str, Path]] = []
    try:
        entries = list(os.scandir(absolute_parent))
    except OSError as exc:
        raise ProofContractError("managed_dotnet_root_invalid") from exc
    for entry in entries:
        if entry.is_symlink():
            raise ProofContractError("managed_dotnet_symlink")
        if not entry.is_dir(follow_symlinks=False) or not entry.name.startswith("10."):
            continue
        _version_sort_key(entry.name)
        selected = Path(entry.path).joinpath(*suffix)
        try:
            _reject_symlink_components(selected)
            selected_metadata = os.lstat(selected)
        except (OSError, ProofContractError):
            continue
        if stat.S_ISDIR(selected_metadata.st_mode):
            candidates.append((entry.name, selected))
    if not candidates:
        raise ProofContractError("managed_dotnet_version_missing")
    return max(candidates, key=lambda item: _version_sort_key(item[0]))


def _managed_dotnet_layout(dotnet_path: Path) -> tuple[dict[str, object], list[tuple[str, str, Path]], Path]:
    dotnet = _dotnet_identity(dotnet_path)
    dotnet_root = Path(str(dotnet["resolved_path"])).parent
    hostfxr_version, hostfxr_path = _select_managed_version_directory(dotnet_root / "host" / "fxr")
    netcore_version, netcore_path = _select_managed_version_directory(
        dotnet_root / "shared" / "Microsoft.NETCore.App"
    )
    aspnet_version, aspnet_path = _select_managed_version_directory(
        dotnet_root / "shared" / "Microsoft.AspNetCore.App"
    )
    netcore_ref_version, netcore_ref_path = _select_managed_version_directory(
        dotnet_root / "packs" / "Microsoft.NETCore.App.Ref",
        suffix=("ref", "net10.0"),
    )
    aspnet_ref_version, aspnet_ref_path = _select_managed_version_directory(
        dotnet_root / "packs" / "Microsoft.AspNetCore.App.Ref",
        suffix=("ref", "net10.0"),
    )
    sdk_version, sdk_path = _select_managed_version_directory(dotnet_root / "sdk")
    components = [
        ("hostfxr", hostfxr_version, hostfxr_path),
        ("Microsoft.NETCore.App", netcore_version, netcore_path),
        ("Microsoft.AspNetCore.App", aspnet_version, aspnet_path),
        ("Microsoft.NETCore.App.Ref", netcore_ref_version, netcore_ref_path),
        ("Microsoft.AspNetCore.App.Ref", aspnet_ref_version, aspnet_ref_path),
        ("sdk", sdk_version, sdk_path),
    ]
    csc_path = sdk_path / "Roslyn" / "bincore" / "csc.dll"
    _read_regular_bytes(csc_path, max_bytes=MAX_INPUT_BYTES, reason_prefix="csc")
    return dotnet, components, csc_path


def _managed_dotnet_closure(dotnet_path: Path) -> dict[str, object]:
    dotnet, layout, _csc_path = _managed_dotnet_layout(dotnet_path)
    components: list[dict[str, object]] = []
    for root_name, version, path in layout:
        tree = _tree_record(
            root_name,
            path,
            reason_prefix="managed_dotnet_tree",
        )
        components.append({
            "root": root_name,
            "version": version,
            "path": str(_absolute(path)),
            "file_count": tree["file_count"],
            "total_size_bytes": tree["total_size_bytes"],
            "tree_sha256": tree["tree_sha256"],
        })
    body: dict[str, object] = {
        "kind": "managed_dotnet_closure",
        "dotnet_host": dotnet,
        "components": components,
        "component_count": len(components),
    }
    return {**body, "closure_sha256": _canonical_digest(body)}


def _copy_tree_without_outputs(source: Path, destination: Path, *, reason_prefix: str) -> None:
    entries = _stable_tree_entries(
        source,
        excluded_directories=TREE_EXCLUDED_DIRECTORIES,
        reason_prefix=reason_prefix,
    )
    if entries is None:
        raise ProofContractError(f"{reason_prefix}_missing")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    for entry in entries:
        relative = str(entry["path"])
        source_path = source / PurePosixPath(relative)
        destination_path = destination / PurePosixPath(relative)
        destination_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        data = _read_regular_bytes(
            source_path,
            max_bytes=MAX_INPUT_BYTES,
            reason_prefix=reason_prefix,
            allow_empty=True,
        )
        descriptor = os.open(
            destination_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise ProofContractError(f"{reason_prefix}_write_failed")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _stage_candidate_inputs(root: Path, candidate_root: Path) -> None:
    _mkdir_private(candidate_root)
    _copy_tree_without_outputs(
        root / "Chummer.Run.Api",
        candidate_root / "Chummer.Run.Api",
        reason_prefix="stage_api_tree",
    )
    for source_root, stage_root in RUNTIME_DATA_SPECS:
        _copy_tree_without_outputs(
            root / source_root,
            candidate_root / stage_root,
            reason_prefix="stage_runtime_data",
        )
    for source_file, stage_file in RUNTIME_DATA_FILES:
        source_path = root / source_file
        destination_path = candidate_root / stage_file
        destination_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        data = _read_regular_bytes(
            source_path,
            max_bytes=MAX_INPUT_BYTES,
            reason_prefix="stage_runtime_data_file",
            allow_empty=True,
        )
        descriptor = os.open(
            destination_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            remaining = memoryview(data)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise ProofContractError("stage_runtime_data_file_write_failed")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _staged_candidate_inputs(candidate_root: Path) -> dict[str, object]:
    roots = [
        _tree_record(
            "Chummer.Run.Api",
            candidate_root / "Chummer.Run.Api",
            excluded_directories=TREE_EXCLUDED_DIRECTORIES,
            reason_prefix="staged_candidate_tree",
        )
    ]
    roots.extend(
        _tree_record(
            stage_root,
            candidate_root / stage_root,
            excluded_directories=TREE_EXCLUDED_DIRECTORIES,
            reason_prefix="staged_candidate_tree",
        )
        for _source_root, stage_root in RUNTIME_DATA_SPECS
    )
    files = _explicit_files_record(
        "runtime_data_files",
        [(stage, candidate_root / stage) for _source, stage in RUNTIME_DATA_FILES],
        reason_prefix="staged_candidate_file",
    )
    body: dict[str, object] = {
        "kind": "staged_candidate_inputs",
        "tree_format_version": TREE_FORMAT_VERSION,
        "roots": roots,
        "runtime_data_files": files,
        "root_count": len(roots),
    }
    return {**body, "closure_sha256": _canonical_digest(body)}


def _tree_record_content(record: Mapping[str, object]) -> tuple[object, object, object]:
    return record.get("file_count"), record.get("total_size_bytes"), record.get("tree_sha256")


def _assert_stage_matches_candidate(
    candidate: Mapping[str, object],
    staged: Mapping[str, object],
) -> None:
    project_records = {
        str(item["root"]): item
        for item in candidate["project_roots"]  # type: ignore[index]
    }
    staged_records = {
        str(item["root"]): item
        for item in staged["roots"]  # type: ignore[index]
    }
    if _tree_record_content(project_records["Chummer.Run.Api"]) != _tree_record_content(
        staged_records["Chummer.Run.Api"]
    ):
        raise ProofContractError("staged_candidate_source_mismatch")
    runtime_records = candidate["runtime_data_roots"]  # type: ignore[index]
    for (source_root, stage_root), source_record in zip(RUNTIME_DATA_SPECS, runtime_records, strict=True):
        if source_record.get("root") != source_root or _tree_record_content(source_record) != _tree_record_content(
            staged_records[stage_root]
        ):
            raise ProofContractError("staged_candidate_source_mismatch")
    if _tree_record_content(candidate["runtime_data_files"]) != _tree_record_content(  # type: ignore[index]
        staged["runtime_data_files"]  # type: ignore[index]
    ):
        raise ProofContractError("staged_candidate_source_mismatch")


def _repo_inputs(
    root: Path,
    dotnet_path: Path,
    *,
    csc_path: Path | None,
) -> dict[str, object]:
    source_data = _read_regular_bytes(root / SOURCE_PATH, max_bytes=MAX_INPUT_BYTES, reason_prefix="input")
    spec_data = _read_regular_bytes(root / JOURNEY_SPEC_PATH, max_bytes=MAX_INPUT_BYTES, reason_prefix="input")
    _parse_journey_spec(spec_data)
    return {
        "source": {
            "path": SOURCE_PATH,
            "sha256": hashlib.sha256(source_data).hexdigest(),
            "size_bytes": len(source_data),
        },
        "journey_spec": {
            "path": JOURNEY_SPEC_PATH,
            "sha256": hashlib.sha256(spec_data).hexdigest(),
            "size_bytes": len(spec_data),
            "version": JOURNEY_SPEC_VERSION,
        },
        "runner": _identity(root / RUNNER_PATH, RUNNER_PATH),
        "prepare_helper": _identity(root / PREPARE_HELPER_PATH, PREPARE_HELPER_PATH),
        "environment_helper": _identity(root / ENVIRONMENT_HELPER_PATH, ENVIRONMENT_HELPER_PATH),
        "cleanroom_builder": _identity(root / CLEANROOM_BUILDER_PATH, CLEANROOM_BUILDER_PATH),
        "registry_global_usings": _identity(root / REGISTRY_GLOBAL_USINGS_PATH, REGISTRY_GLOBAL_USINGS_PATH),
        "materializer": _identity(root / MATERIALIZER_PATH, MATERIALIZER_PATH),
        "contract_module": _identity(root / CONTRACT_MODULE_PATH, CONTRACT_MODULE_PATH),
        "dotnet_host": _dotnet_identity(dotnet_path),
        "csc": _external_identity(csc_path) if csc_path is not None else None,
        "assembly": None,
    }


def _running_journeys() -> list[dict[str, object]]:
    return [
        {"id": journey_id, "status": "running", "checkpoint_ids": [CHECKPOINT_IDS[journey_id]]}
        for journey_id in JOURNEY_IDS
    ]


def _passed_journeys(checkpoints: list[dict[str, str]]) -> list[dict[str, object]]:
    expected = [CHECKPOINT_IDS[item] for item in JOURNEY_IDS]
    if [item["checkpoint_id"] for item in checkpoints] != expected:
        raise ProofContractError("runtime_checkpoint_set_mismatch")
    return [
        {"id": journey_id, "status": "passed", "checkpoint_ids": [CHECKPOINT_IDS[journey_id]]}
        for journey_id in JOURNEY_IDS
    ]


def _summary(passed: bool) -> dict[str, int]:
    count = len(JOURNEY_IDS)
    return {
        "journey_count": count,
        "passed_journey_count": count if passed else 0,
        "checkpoint_count": count,
        "passed_checkpoint_count": count if passed else 0,
    }


def _running_payload(root: Path, dotnet_path: Path, run_id: str, started: dt.datetime) -> dict[str, object]:
    timestamp = format_utc(started)
    return {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "status": "running",
        "proof_kind": PROOF_KIND,
        "run_id": run_id,
        "started_at": timestamp,
        "completed_at": None,
        "generated_at": timestamp,
        "expires_at": None,
        "invocation": {
            "id": INVOCATION_ID,
            "owner": INVOCATION_OWNER,
            "dependency_mode": DEPENDENCY_MODE,
            "prepare_exit_code": None,
            "runner_exit_code": None,
        },
        "inputs": _repo_inputs(root, dotnet_path, csc_path=None),
        "execution": {
            "phase": "starting",
            "failure_reason": None,
            "candidate_source_build_inputs_before": None,
            "candidate_source_build_inputs_after": None,
            "staged_candidate_inputs_before": None,
            "staged_candidate_inputs_after": None,
            "managed_dotnet_closure_before": None,
            "managed_dotnet_closure_after": None,
            "runtime_manifest_before": None,
            "runtime_manifest_after": None,
            "checkpoint_log": None,
            "runtime_checkpoints": [],
            "candidate_source_build_inputs_stable": None,
            "staged_candidate_inputs_stable": None,
            "managed_dotnet_closure_stable": None,
            "runtime_closure_stable": None,
            "closure_stable": None,
        },
        "journeys": _running_journeys(),
        "summary": _summary(False),
    }


def _duplicate_rejector(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProofContractError("receipt_duplicate_key")
        result[key] = value
    return result


def _load_receipt(path: Path) -> dict[str, Any]:
    data = _read_regular_bytes(path, max_bytes=MAX_RECEIPT_BYTES, reason_prefix="receipt")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProofContractError("receipt_invalid_utf8") from exc
    try:
        value = json.loads(text, object_pairs_hook=_duplicate_rejector)
    except ProofContractError:
        raise
    except json.JSONDecodeError as exc:
        raise ProofContractError("receipt_invalid_json") from exc
    if not isinstance(value, dict):
        raise ProofContractError("receipt_root_not_object")
    return value


def _assert_canonical_output(root: Path, receipt_path: Path) -> None:
    expected = _absolute(root / DEFAULT_RECEIPT_PATH)
    actual = _absolute(receipt_path)
    if actual != expected:
        raise ProofContractError("receipt_output_not_canonical")
    try:
        _reject_symlink_components(actual.parent)
    except ProofContractError as exc:
        raise ProofContractError("receipt_output_symlink_ancestor") from exc
    try:
        current = os.lstat(actual)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ProofContractError("receipt_output_stat_failed") from exc
    if stat.S_ISLNK(current.st_mode):
        raise ProofContractError("receipt_output_symlink")
    if not stat.S_ISREG(current.st_mode):
        raise ProofContractError("receipt_output_not_regular")


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _manifest_hash(entries: list[dict[str, object]]) -> str:
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _runtime_manifest(runtime_root: Path, dotnet: dict[str, object], csc: dict[str, object]) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    if not runtime_root.is_dir() or runtime_root.is_symlink():
        raise ProofContractError("runtime_root_invalid")

    def raise_walk_error(error: OSError) -> None:
        raise ProofContractError("runtime_scan_failed") from error

    for directory, directory_names, file_names in os.walk(
        runtime_root,
        followlinks=False,
        onerror=raise_walk_error,
    ):
        directory_names.sort()
        file_names.sort()
        directory_path = Path(directory)
        for name in directory_names:
            if (directory_path / name).is_symlink():
                raise ProofContractError("runtime_symlink")
        for name in file_names:
            path = directory_path / name
            relative = path.relative_to(runtime_root).as_posix()
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or "." in pure.parts or "\\" in relative:
                raise ProofContractError("runtime_path_invalid")
            data = _read_regular_bytes(path, max_bytes=MAX_INPUT_BYTES, reason_prefix="runtime")
            entries.append({
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            })
    runtime_paths = {str(item["path"]) for item in entries}
    if runtime_paths != set(RUNTIME_CLOSURE_PATHS):
        raise ProofContractError("runtime_closure_set_mismatch")
    entries.extend([
        {"path": "toolchain/dotnet", "sha256": dotnet["sha256"], "size_bytes": dotnet["size_bytes"]},
        {"path": "toolchain/csc.dll", "sha256": csc["sha256"], "size_bytes": csc["size_bytes"]},
    ])
    entries.sort(key=lambda item: str(item["path"]))
    if len({item["path"] for item in entries}) != len(entries):
        raise ProofContractError("runtime_manifest_duplicate_path")
    return {
        "algorithm": "sha256",
        "entries": entries,
        "entry_count": len(entries),
        "manifest_sha256": _manifest_hash(entries),
    }


def _validate_runtimeconfig_managed_binding(
    runtime_root: Path,
    managed_closure: Mapping[str, object],
) -> None:
    data = _read_regular_bytes(
        runtime_root / RUNTIMECONFIG_FILE_NAME,
        max_bytes=MAX_INPUT_BYTES,
        reason_prefix="runtimeconfig",
    )
    try:
        document = json.loads(data.decode("utf-8"), object_pairs_hook=_duplicate_rejector)
    except (UnicodeDecodeError, json.JSONDecodeError, ProofContractError) as exc:
        raise ProofContractError("runtimeconfig_invalid") from exc
    if not isinstance(document, dict) or tuple(document) != ("runtimeOptions",):
        raise ProofContractError("runtimeconfig_invalid")
    runtime_options = document.get("runtimeOptions")
    if (
        not isinstance(runtime_options, dict)
        or runtime_options.get("tfm") != "net10.0"
    ):
        raise ProofContractError("runtimeconfig_framework_mismatch")
    if tuple(runtime_options) != ("tfm", "frameworks"):
        raise ProofContractError("runtimeconfig_framework_policy_untrusted")
    frameworks = runtime_options.get("frameworks")
    expected_names = ("Microsoft.NETCore.App", "Microsoft.AspNetCore.App")
    if not isinstance(frameworks, list) or len(frameworks) != len(expected_names):
        raise ProofContractError("runtimeconfig_framework_mismatch")

    components = managed_closure.get("components")
    if not isinstance(components, list):
        raise ProofContractError("managed_dotnet_schema_mismatch")
    selected_versions = {
        item.get("root"): item.get("version")
        for item in components
        if isinstance(item, dict)
    }
    for expected_name, framework in zip(expected_names, frameworks, strict=True):
        if (
            not isinstance(framework, dict)
            or tuple(framework) != ("name", "version")
            or framework.get("name") != expected_name
            or not isinstance(framework.get("version"), str)
            or _FRAMEWORK_VERSION_RE.fullmatch(framework["version"]) is None
        ):
            raise ProofContractError("runtimeconfig_framework_mismatch")
        selected = selected_versions.get(expected_name)
        if (
            not isinstance(selected, str)
            or _FRAMEWORK_VERSION_RE.fullmatch(selected) is None
            or framework["version"] != selected
        ):
            raise ProofContractError("runtimeconfig_framework_mismatch")


def _checkpoint_log_identity(path: Path) -> dict[str, object]:
    data = _read_regular_bytes(path, max_bytes=MAX_CHECKPOINT_BYTES, reason_prefix="checkpoint_log")
    return {
        "file_name": CHECKPOINT_FILE_NAME,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _runtime_checkpoints(path: Path, run_id: str) -> list[dict[str, str]]:
    data = _read_regular_bytes(path, max_bytes=MAX_CHECKPOINT_BYTES, reason_prefix="checkpoint_log")
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ProofContractError("checkpoint_log_invalid_utf8") from exc
    checkpoints: list[dict[str, str]] = []
    for line in lines:
        try:
            value = json.loads(line, object_pairs_hook=_duplicate_rejector)
        except (json.JSONDecodeError, ProofContractError) as exc:
            raise ProofContractError("runtime_checkpoint_invalid_json") from exc
        if not isinstance(value, dict) or tuple(value) != ("checkpoint_id", "run_id", "status"):
            raise ProofContractError("runtime_checkpoint_schema_mismatch")
        if not all(isinstance(value[item], str) for item in value):
            raise ProofContractError("runtime_checkpoint_schema_mismatch")
        checkpoints.append(value)
    expected = [
        {"checkpoint_id": CHECKPOINT_IDS[journey], "run_id": run_id, "status": "passed"}
        for journey in JOURNEY_IDS
    ]
    if checkpoints != expected:
        raise ProofContractError("runtime_checkpoint_set_mismatch")
    return checkpoints


def _checkpoint_bytes(checkpoints: list[dict[str, str]]) -> bytes:
    return (
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
            for item in checkpoints
        )
    ).encode("utf-8")


def _mkdir_private(path: Path) -> None:
    path.mkdir(mode=0o700, parents=False, exist_ok=False)
    metadata = os.lstat(path)
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ProofContractError("private_directory_mode_invalid")


def _sanitized_environment(
    work_root: Path,
    repository_root: Path,
    *,
    run_id: str | None = None,
    checkpoint_path: Path | None = None,
    candidate_root: Path | None = None,
) -> dict[str, str]:
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(work_root / "home"),
        "DOTNET_CLI_HOME": str(work_root / "dotnet-home"),
        "NUGET_PACKAGES": str(_absolute(repository_root / ".tmp" / "nuget" / "packages")),
        "TMPDIR": str(work_root / "tmp"),
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_NOLOGO": "1",
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1",
        "CHUMMER_BUILD_NO_RESTORE": "1",
        "CHUMMER_BUILD_SOLUTION": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
    }
    if run_id is not None and checkpoint_path is not None and candidate_root is not None:
        environment["CHUMMER_CAMPAIGN_OS_RUN_ID"] = run_id
        environment["CHUMMER_CAMPAIGN_OS_CHECKPOINT_OUT"] = str(checkpoint_path)
        environment["CHUMMER_CAMPAIGN_OS_CANDIDATE_ROOT"] = str(candidate_root)
    elif any(item is not None for item in (run_id, checkpoint_path, candidate_root)):
        raise ProofContractError("proof_environment_incomplete")
    return environment


def _run_fixed_process(
    arguments: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> int:
    stdout_descriptor = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    stderr_descriptor = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        process = subprocess.Popen(
            arguments,
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=stdout_descriptor,
            stderr=stderr_descriptor,
            close_fds=True,
            start_new_session=True,
        )
        try:
            return process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ProofContractError("execution_timeout") from exc
    finally:
        os.close(stdout_descriptor)
        os.close(stderr_descriptor)


class FixedSmokeExecutor:
    dotnet_path = DOTNET_HOST_PATH

    def resolve_csc(self, root: Path, work_root: Path, environment: Mapping[str, str]) -> Path:
        _dotnet, _components, csc_path = _managed_dotnet_layout(self.dotnet_path)
        return csc_path

    def prepare(
        self,
        root: Path,
        work_root: Path,
        csc_path: Path,
        environment: Mapping[str, str],
        logs_root: Path,
    ) -> int:
        _dotnet, components, expected_csc_path = _managed_dotnet_layout(self.dotnet_path)
        if _absolute(csc_path) != _absolute(expected_csc_path):
            raise ProofContractError("csc_path_untrusted")
        component_map = {
            name: (version, path)
            for name, version, path in components
        }
        return _run_fixed_process(
            [
                str(BASH_HOST_PATH),
                "--noprofile",
                "--norc",
                str(root / PREPARE_HELPER_PATH),
                str(work_root),
                str(csc_path),
                str(component_map["Microsoft.NETCore.App.Ref"][1]),
                str(component_map["Microsoft.AspNetCore.App.Ref"][1]),
                component_map["Microsoft.NETCore.App"][0],
                component_map["Microsoft.AspNetCore.App"][0],
                component_map["hostfxr"][0],
            ],
            cwd=root,
            environment=environment,
            stdout_path=logs_root / "prepare.stdout",
            stderr_path=logs_root / "prepare.stderr",
            timeout_seconds=PREPARE_TIMEOUT_SECONDS,
        )

    def execute(
        self,
        root: Path,
        assembly_path: Path,
        environment: Mapping[str, str],
        logs_root: Path,
    ) -> int:
        return _run_fixed_process(
            [str(self.dotnet_path), str(assembly_path)],
            cwd=root,
            environment=environment,
            stdout_path=logs_root / "run.stdout",
            stderr_path=logs_root / "run.stderr",
            timeout_seconds=RUN_TIMEOUT_SECONDS,
        )


def _valid_uuid4(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value


def _record_running_failure(receipt_path: Path, payload: dict[str, Any], reason: str, phase: str) -> None:
    payload["status"] = "running"
    payload["execution"]["phase"] = phase
    payload["execution"]["failure_reason"] = reason
    try:
        _atomic_write_json(receipt_path, payload)
    except Exception:
        pass


def run_owned_smoke(
    root: Path,
    receipt_path: Path,
    *,
    executor: FixedSmokeExecutor | None = None,
    now: Callable[[], dt.datetime] = utc_now,
    run_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
) -> dict[str, Any]:
    repository_root = _absolute(root)
    output = _absolute(receipt_path)
    _assert_canonical_output(repository_root, output)
    if executor is not None and repository_root == MODULE_REPOSITORY_ROOT:
        raise ProofContractError("executor_override_forbidden")
    selected_executor = executor or FixedSmokeExecutor()
    run_id = str(run_id_factory())
    if not _valid_uuid4(run_id):
        raise ProofContractError("run_id_invalid")
    started = normalize_utc(now())
    payload = _running_payload(repository_root, selected_executor.dotnet_path, run_id, started)
    _atomic_write_json(output, payload)
    phase = "starting"

    try:
        _reject_symlink_components(Path("/tmp"))
        work_root = Path(tempfile.mkdtemp(prefix="chummer-campaign-os-", dir="/tmp"))
        work_metadata = os.lstat(work_root)
        if not stat.S_ISDIR(work_metadata.st_mode) or stat.S_IMODE(work_metadata.st_mode) != 0o700:
            raise ProofContractError("private_directory_mode_invalid")
        try:
            for child in ("runtime", "build", "logs", "home", "dotnet-home", "tmp"):
                _mkdir_private(work_root / child)
            runtime_root = work_root / "runtime"
            logs_root = work_root / "logs"
            candidate_root = work_root / "candidate"
            checkpoint_path = logs_root / CHECKPOINT_FILE_NAME
            prepare_environment = _sanitized_environment(work_root, repository_root)

            phase = "candidate_input_failed"
            candidate_before = _candidate_source_build_inputs(repository_root)
            _stage_candidate_inputs(repository_root, candidate_root)
            staged_before = _staged_candidate_inputs(candidate_root)
            _assert_stage_matches_candidate(candidate_before, staged_before)
            managed_before = _managed_dotnet_closure(selected_executor.dotnet_path)

            csc_path = selected_executor.resolve_csc(repository_root, work_root, prepare_environment)
            _dotnet_layout, _managed_layout, expected_csc_path = _managed_dotnet_layout(
                selected_executor.dotnet_path
            )
            if _absolute(csc_path) != _absolute(expected_csc_path):
                raise ProofContractError("csc_path_untrusted")
            csc_identity = _external_identity(csc_path)
            payload["inputs"]["csc"] = csc_identity
            payload["execution"]["candidate_source_build_inputs_before"] = candidate_before
            payload["execution"]["staged_candidate_inputs_before"] = staged_before
            payload["execution"]["managed_dotnet_closure_before"] = managed_before
            payload["execution"]["phase"] = "preparing"
            phase = "prepare_failed"
            _atomic_write_json(output, payload)

            prepare_exit = selected_executor.prepare(
                repository_root,
                work_root,
                csc_path,
                prepare_environment,
                logs_root,
            )
            if not isinstance(prepare_exit, int) or isinstance(prepare_exit, bool):
                raise ProofContractError("prepare_result_invalid")
            payload["invocation"]["prepare_exit_code"] = prepare_exit
            if prepare_exit != 0:
                raise ProofContractError("prepare_nonzero")

            dotnet_identity = _dotnet_identity(selected_executor.dotnet_path)
            if dotnet_identity != payload["inputs"]["dotnet_host"]:
                raise ProofContractError("dotnet_host_identity_drift")
            if _external_identity(csc_path) != csc_identity:
                raise ProofContractError("csc_identity_drift")
            _validate_runtimeconfig_managed_binding(runtime_root, managed_before)
            manifest_before = _runtime_manifest(runtime_root, dotnet_identity, csc_identity)
            assembly_path = runtime_root / ASSEMBLY_FILE_NAME
            payload["inputs"]["assembly"] = _assembly_identity(assembly_path)
            payload["execution"]["runtime_manifest_before"] = manifest_before
            payload["execution"]["phase"] = "executing"
            phase = "run_failed"
            _atomic_write_json(output, payload)

            run_environment = _sanitized_environment(
                work_root,
                repository_root,
                run_id=run_id,
                checkpoint_path=checkpoint_path,
                candidate_root=candidate_root,
            )
            runner_exit = selected_executor.execute(
                repository_root,
                assembly_path,
                run_environment,
                logs_root,
            )
            if not isinstance(runner_exit, int) or isinstance(runner_exit, bool):
                raise ProofContractError("runner_result_invalid")
            payload["invocation"]["runner_exit_code"] = runner_exit
            candidate_after = _candidate_source_build_inputs(repository_root)
            staged_after = _staged_candidate_inputs(candidate_root)
            _assert_stage_matches_candidate(candidate_after, staged_after)
            managed_after = _managed_dotnet_closure(selected_executor.dotnet_path)
            _validate_runtimeconfig_managed_binding(runtime_root, managed_after)
            manifest_after = _runtime_manifest(
                runtime_root,
                _dotnet_identity(selected_executor.dotnet_path),
                _external_identity(csc_path),
            )
            payload["execution"]["candidate_source_build_inputs_after"] = candidate_after
            payload["execution"]["staged_candidate_inputs_after"] = staged_after
            payload["execution"]["managed_dotnet_closure_after"] = managed_after
            payload["execution"]["runtime_manifest_after"] = manifest_after
            candidate_stable = candidate_after == candidate_before
            staged_stable = staged_after == staged_before
            managed_stable = managed_after == managed_before
            runtime_stable = manifest_after == manifest_before
            closure_stable = candidate_stable and staged_stable and managed_stable and runtime_stable
            payload["execution"]["candidate_source_build_inputs_stable"] = candidate_stable
            payload["execution"]["staged_candidate_inputs_stable"] = staged_stable
            payload["execution"]["managed_dotnet_closure_stable"] = managed_stable
            payload["execution"]["runtime_closure_stable"] = runtime_stable
            payload["execution"]["closure_stable"] = closure_stable
            if runner_exit != 0:
                raise ProofContractError("runner_nonzero")
            if not candidate_stable:
                phase = "closure_drift"
                raise ProofContractError("candidate_source_build_inputs_drift")
            if not staged_stable:
                phase = "closure_drift"
                raise ProofContractError("staged_candidate_inputs_drift")
            if not managed_stable:
                phase = "closure_drift"
                raise ProofContractError("managed_dotnet_closure_drift")
            if not runtime_stable:
                phase = "closure_drift"
                raise ProofContractError("runtime_closure_drift")

            phase = "checkpoint_failed"
            checkpoints = _runtime_checkpoints(checkpoint_path, run_id)
            checkpoint_log = _checkpoint_log_identity(checkpoint_path)
            checkpoint_bytes = _checkpoint_bytes(checkpoints)
            if (
                checkpoint_log["sha256"] != hashlib.sha256(checkpoint_bytes).hexdigest()
                or checkpoint_log["size_bytes"] != len(checkpoint_bytes)
            ):
                raise ProofContractError("checkpoint_log_semantic_mismatch")
            payload["execution"]["checkpoint_log"] = checkpoint_log
            payload["execution"]["runtime_checkpoints"] = checkpoints

            current_inputs = _repo_inputs(repository_root, selected_executor.dotnet_path, csc_path=csc_path)
            for key in INPUT_FIELDS[:-1]:
                if current_inputs[key] != payload["inputs"][key]:
                    raise ProofContractError(f"{key}_identity_drift")
            if _assembly_identity(assembly_path) != payload["inputs"]["assembly"]:
                raise ProofContractError("assembly_identity_drift")

            completed = normalize_utc(now())
            if completed < started:
                raise ProofContractError("timestamp_order_invalid")
            payload["status"] = "passed"
            payload["completed_at"] = format_utc(completed)
            payload["generated_at"] = format_utc(completed)
            try:
                expires = completed + RECEIPT_LIFETIME
            except OverflowError as exc:
                raise ProofContractError("timestamp_overflow") from exc
            payload["expires_at"] = format_utc(expires)
            payload["execution"]["phase"] = "verified"
            payload["execution"]["failure_reason"] = None
            payload["journeys"] = _passed_journeys(checkpoints)
            payload["summary"] = _summary(True)
            _atomic_write_json(output, payload)
            return payload
        finally:
            shutil.rmtree(work_root)
    except ProofContractError as exc:
        _record_running_failure(output, payload, exc.reason_code, phase)
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        _record_running_failure(output, payload, "execution_error", phase)
        raise ProofContractError("execution_error") from exc


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_identity(value: object, *, path: str | None = None, spec: bool = False) -> bool:
    if not isinstance(value, dict):
        return False
    expected = {"path", "sha256", "size_bytes"} | ({"version"} if spec else set())
    expected_order = ("path", "sha256", "size_bytes", "version") if spec else ("path", "sha256", "size_bytes")
    if tuple(value) != expected_order or set(value) != expected:
        return False
    if path is not None and value.get("path") != path:
        return False
    if not isinstance(value.get("sha256"), str) or _SHA256_RE.fullmatch(value["sha256"]) is None:
        return False
    if not _is_int(value.get("size_bytes")) or value["size_bytes"] <= 0 or value["size_bytes"] > MAX_INPUT_BYTES:
        return False
    return not spec or value.get("version") == JOURNEY_SPEC_VERSION


def _valid_assembly(value: object) -> bool:
    if not isinstance(value, dict) or tuple(value) != ("file_name", "sha256", "size_bytes"):
        return False
    return (
        value.get("file_name") == ASSEMBLY_FILE_NAME
        and isinstance(value.get("sha256"), str)
        and _SHA256_RE.fullmatch(value["sha256"]) is not None
        and _is_int(value.get("size_bytes"))
        and 0 < value["size_bytes"] <= MAX_INPUT_BYTES
    )


def _valid_dotnet(value: object) -> bool:
    if not isinstance(value, dict) or tuple(value) != ("path", "resolved_path", "sha256", "size_bytes"):
        return False
    return (
        value.get("path") == str(DOTNET_HOST_PATH)
        and isinstance(value.get("resolved_path"), str)
        and Path(value["resolved_path"]).is_absolute()
        and isinstance(value.get("sha256"), str)
        and _SHA256_RE.fullmatch(value["sha256"]) is not None
        and _is_int(value.get("size_bytes"))
        and 0 < value["size_bytes"] <= MAX_INPUT_BYTES
    )


def _valid_tree_record(value: object, *, root: str | None = None, allow_empty: bool = True) -> bool:
    if not isinstance(value, dict) or tuple(value) != (
        "root", "file_count", "total_size_bytes", "tree_sha256"
    ):
        return False
    if root is not None and value.get("root") != root:
        return False
    file_count = value.get("file_count")
    total_size = value.get("total_size_bytes")
    return (
        isinstance(value.get("root"), str)
        and bool(value["root"])
        and _is_int(file_count)
        and _is_int(total_size)
        and file_count >= (0 if allow_empty else 1)
        and file_count <= MAX_TREE_FILES
        and total_size >= 0
        and total_size <= MAX_TREE_TOTAL_BYTES
        and isinstance(value.get("tree_sha256"), str)
        and _SHA256_RE.fullmatch(value["tree_sha256"]) is not None
    )


def _validate_candidate_closure(value: object) -> None:
    fields = (
        "kind",
        "tree_format_version",
        "project_roots",
        "smoke_source_tree",
        "runtime_data_roots",
        "runtime_data_files",
        "ancestor_build_controls",
        "project_assets",
        "generated_nuget_imports",
        "nuget_package_roots",
        "nuget_packages",
        "project_root_count",
        "runtime_data_root_count",
        "closure_sha256",
    )
    if not isinstance(value, dict) or tuple(value) != fields:
        raise ProofContractError("candidate_closure_schema_mismatch")
    if value.get("kind") != "candidate_source_build_inputs" or value.get("tree_format_version") != TREE_FORMAT_VERSION:
        raise ProofContractError("candidate_closure_schema_mismatch")
    project_roots = value.get("project_roots")
    if (
        not isinstance(project_roots, list)
        or len(project_roots) != len(PROJECT_ROOTS)
        or value.get("project_root_count") != len(PROJECT_ROOTS)
    ):
        raise ProofContractError("candidate_project_roots_mismatch")
    for expected, record in zip(PROJECT_ROOTS, project_roots, strict=True):
        if not _valid_tree_record(record, root=expected, allow_empty=False):
            raise ProofContractError("candidate_project_root_invalid")
    if not _valid_tree_record(value.get("smoke_source_tree"), root=SMOKE_SOURCE_ROOT, allow_empty=False):
        raise ProofContractError("candidate_smoke_tree_invalid")
    runtime_roots = value.get("runtime_data_roots")
    if (
        not isinstance(runtime_roots, list)
        or len(runtime_roots) != len(RUNTIME_DATA_SPECS)
        or value.get("runtime_data_root_count") != len(RUNTIME_DATA_SPECS)
    ):
        raise ProofContractError("runtime_data_roots_mismatch")
    for (source_root, _stage_root), record in zip(RUNTIME_DATA_SPECS, runtime_roots, strict=True):
        if not _valid_tree_record(record, root=source_root, allow_empty=False):
            raise ProofContractError("runtime_data_root_invalid")
    expected_records = (
        ("runtime_data_files", "runtime_data_files", False),
        ("ancestor_build_controls", "ancestor_build_controls", True),
        ("project_assets", "project_assets", False),
        ("generated_nuget_imports", "generated_nuget_imports", False),
        ("nuget_packages", "project_assets.packageFolders", False),
    )
    for field, root_label, allow_empty in expected_records:
        if not _valid_tree_record(value.get(field), root=root_label, allow_empty=allow_empty):
            raise ProofContractError(f"{field}_identity_invalid")
    if value["project_assets"]["file_count"] != len(PROJECT_SPECS):
        raise ProofContractError("project_assets_count_mismatch")
    if value["generated_nuget_imports"]["file_count"] != len(PROJECT_SPECS) * 2:
        raise ProofContractError("generated_nuget_imports_count_mismatch")
    package_roots = value.get("nuget_package_roots")
    if (
        not isinstance(package_roots, list)
        or not package_roots
        or package_roots != sorted(package_roots)
        or len(set(package_roots)) != len(package_roots)
        or not all(isinstance(item, str) and Path(item).is_absolute() for item in package_roots)
    ):
        raise ProofContractError("nuget_package_roots_invalid")
    body = {key: value[key] for key in fields[:-1]}
    if value.get("closure_sha256") != _canonical_digest(body):
        raise ProofContractError("candidate_closure_digest_mismatch")


def _validate_staged_closure(value: object) -> None:
    fields = (
        "kind",
        "tree_format_version",
        "roots",
        "runtime_data_files",
        "root_count",
        "closure_sha256",
    )
    if not isinstance(value, dict) or tuple(value) != fields:
        raise ProofContractError("staged_candidate_schema_mismatch")
    if value.get("kind") != "staged_candidate_inputs" or value.get("tree_format_version") != TREE_FORMAT_VERSION:
        raise ProofContractError("staged_candidate_schema_mismatch")
    expected_roots = ("Chummer.Run.Api", *(stage for _source, stage in RUNTIME_DATA_SPECS))
    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != len(expected_roots) or value.get("root_count") != len(expected_roots):
        raise ProofContractError("staged_candidate_roots_mismatch")
    for expected, record in zip(expected_roots, roots, strict=True):
        if not _valid_tree_record(record, root=expected, allow_empty=False):
            raise ProofContractError("staged_candidate_root_invalid")
    if not _valid_tree_record(value.get("runtime_data_files"), root="runtime_data_files", allow_empty=False):
        raise ProofContractError("staged_candidate_file_invalid")
    body = {key: value[key] for key in fields[:-1]}
    if value.get("closure_sha256") != _canonical_digest(body):
        raise ProofContractError("staged_candidate_digest_mismatch")


def _validate_managed_dotnet_closure(value: object) -> None:
    fields = ("kind", "dotnet_host", "components", "component_count", "closure_sha256")
    if not isinstance(value, dict) or tuple(value) != fields:
        raise ProofContractError("managed_dotnet_schema_mismatch")
    if value.get("kind") != "managed_dotnet_closure" or not _valid_dotnet(value.get("dotnet_host")):
        raise ProofContractError("managed_dotnet_schema_mismatch")
    components = value.get("components")
    if not isinstance(components, list) or len(components) != len(MANAGED_COMPONENT_ROOTS) or value.get("component_count") != len(MANAGED_COMPONENT_ROOTS):
        raise ProofContractError("managed_dotnet_components_mismatch")
    for expected_root, component in zip(MANAGED_COMPONENT_ROOTS, components, strict=True):
        if not isinstance(component, dict) or tuple(component) != (
            "root", "version", "path", "file_count", "total_size_bytes", "tree_sha256"
        ):
            raise ProofContractError("managed_dotnet_component_invalid")
        try:
            version_valid = isinstance(component.get("version"), str)
            if version_valid:
                _version_sort_key(component["version"])
        except ProofContractError:
            version_valid = False
        if (
            component.get("root") != expected_root
            or not version_valid
            or not isinstance(component.get("path"), str)
            or not Path(component["path"]).is_absolute()
        ):
            raise ProofContractError("managed_dotnet_component_invalid")
        tree_projection = {
            "root": component["root"],
            "file_count": component["file_count"],
            "total_size_bytes": component["total_size_bytes"],
            "tree_sha256": component["tree_sha256"],
        }
        if not _valid_tree_record(tree_projection, root=expected_root, allow_empty=False):
            raise ProofContractError("managed_dotnet_component_invalid")
    body = {key: value[key] for key in fields[:-1]}
    if value.get("closure_sha256") != _canonical_digest(body):
        raise ProofContractError("managed_dotnet_digest_mismatch")


def _validate_manifest(value: object) -> None:
    if not isinstance(value, dict) or tuple(value) != ("algorithm", "entries", "entry_count", "manifest_sha256"):
        raise ProofContractError("runtime_manifest_schema_mismatch")
    entries = value.get("entries")
    if value.get("algorithm") != "sha256" or not isinstance(entries, list) or not entries:
        raise ProofContractError("runtime_manifest_schema_mismatch")
    paths: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or tuple(entry) != ("path", "sha256", "size_bytes"):
            raise ProofContractError("runtime_manifest_entry_invalid")
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            raise ProofContractError("runtime_manifest_entry_invalid")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or "." in pure.parts or "\\" in path:
            raise ProofContractError("runtime_manifest_entry_invalid")
        if not isinstance(entry.get("sha256"), str) or _SHA256_RE.fullmatch(entry["sha256"]) is None:
            raise ProofContractError("runtime_manifest_entry_invalid")
        if not _is_int(entry.get("size_bytes")) or entry["size_bytes"] <= 0 or entry["size_bytes"] > MAX_INPUT_BYTES:
            raise ProofContractError("runtime_manifest_entry_invalid")
        paths.append(path)
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        raise ProofContractError("runtime_manifest_order_invalid")
    if tuple(paths) != MANIFEST_PATHS:
        raise ProofContractError("runtime_closure_set_mismatch")
    if value.get("entry_count") != len(entries) or value.get("manifest_sha256") != _manifest_hash(entries):
        raise ProofContractError("runtime_manifest_digest_mismatch")


def _validate_passed_schema(payload: dict[str, Any]) -> None:
    if payload.get("contract_name") != CONTRACT_NAME:
        raise ProofContractError("contract_name_mismatch")
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise ProofContractError("contract_version_mismatch")
    if tuple(payload) != ROOT_FIELDS or set(payload) != set(ROOT_FIELDS):
        raise ProofContractError("receipt_schema_mismatch")
    if payload.get("status") != "passed":
        raise ProofContractError("status_mismatch")
    if payload.get("proof_kind") != PROOF_KIND:
        raise ProofContractError("proof_kind_mismatch")
    if not _valid_uuid4(payload.get("run_id")):
        raise ProofContractError("run_id_invalid")
    invocation = payload.get("invocation")
    if not isinstance(invocation, dict) or tuple(invocation) != (
        "id", "owner", "dependency_mode", "prepare_exit_code", "runner_exit_code"
    ):
        raise ProofContractError("invocation_schema_mismatch")
    if invocation != {
        "id": INVOCATION_ID,
        "owner": INVOCATION_OWNER,
        "dependency_mode": DEPENDENCY_MODE,
        "prepare_exit_code": 0,
        "runner_exit_code": 0,
    }:
        raise ProofContractError("invocation_result_mismatch")
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict) or tuple(inputs) != INPUT_FIELDS:
        raise ProofContractError("inputs_schema_mismatch")
    paths = {
        "source": SOURCE_PATH,
        "journey_spec": JOURNEY_SPEC_PATH,
        "runner": RUNNER_PATH,
        "prepare_helper": PREPARE_HELPER_PATH,
        "environment_helper": ENVIRONMENT_HELPER_PATH,
        "cleanroom_builder": CLEANROOM_BUILDER_PATH,
        "registry_global_usings": REGISTRY_GLOBAL_USINGS_PATH,
        "materializer": MATERIALIZER_PATH,
        "contract_module": CONTRACT_MODULE_PATH,
    }
    for key, path in paths.items():
        if not _valid_identity(inputs.get(key), path=path, spec=key == "journey_spec"):
            raise ProofContractError(f"{key}_identity_invalid")
    if not _valid_dotnet(inputs.get("dotnet_host")):
        raise ProofContractError("dotnet_host_identity_invalid")
    csc = inputs.get("csc")
    if not _valid_identity(csc) or not Path(csc["path"]).is_absolute():
        raise ProofContractError("csc_identity_invalid")
    if not _valid_assembly(inputs.get("assembly")):
        raise ProofContractError("assembly_identity_invalid")
    execution = payload.get("execution")
    if not isinstance(execution, dict) or tuple(execution) != EXECUTION_FIELDS:
        raise ProofContractError("execution_schema_mismatch")
    if (
        execution.get("phase") != "verified"
        or execution.get("failure_reason") is not None
        or execution.get("candidate_source_build_inputs_stable") is not True
        or execution.get("staged_candidate_inputs_stable") is not True
        or execution.get("managed_dotnet_closure_stable") is not True
        or execution.get("runtime_closure_stable") is not True
        or execution.get("closure_stable") is not True
    ):
        raise ProofContractError("execution_state_mismatch")
    candidate_before = execution.get("candidate_source_build_inputs_before")
    candidate_after = execution.get("candidate_source_build_inputs_after")
    staged_before = execution.get("staged_candidate_inputs_before")
    staged_after = execution.get("staged_candidate_inputs_after")
    managed_before = execution.get("managed_dotnet_closure_before")
    managed_after = execution.get("managed_dotnet_closure_after")
    _validate_candidate_closure(candidate_before)
    _validate_candidate_closure(candidate_after)
    _validate_staged_closure(staged_before)
    _validate_staged_closure(staged_after)
    _validate_managed_dotnet_closure(managed_before)
    _validate_managed_dotnet_closure(managed_after)
    if candidate_before != candidate_after:
        raise ProofContractError("candidate_source_build_inputs_drift")
    if staged_before != staged_after:
        raise ProofContractError("staged_candidate_inputs_drift")
    if managed_before != managed_after:
        raise ProofContractError("managed_dotnet_closure_drift")
    _assert_stage_matches_candidate(candidate_before, staged_before)
    _assert_stage_matches_candidate(candidate_after, staged_after)
    if managed_before["dotnet_host"] != inputs["dotnet_host"]:
        raise ProofContractError("managed_dotnet_host_mismatch")
    sdk_component = managed_before["components"][-1]
    expected_csc_path = Path(sdk_component["path"]) / "Roslyn" / "bincore" / "csc.dll"
    if Path(inputs["csc"]["path"]) != expected_csc_path:
        raise ProofContractError("csc_path_untrusted")
    _validate_manifest(execution.get("runtime_manifest_before"))
    _validate_manifest(execution.get("runtime_manifest_after"))
    if execution["runtime_manifest_before"] != execution["runtime_manifest_after"]:
        raise ProofContractError("runtime_closure_drift")
    checkpoint_log = execution.get("checkpoint_log")
    if not isinstance(checkpoint_log, dict) or tuple(checkpoint_log) != ("file_name", "sha256", "size_bytes"):
        raise ProofContractError("checkpoint_log_identity_invalid")
    if (
        checkpoint_log.get("file_name") != CHECKPOINT_FILE_NAME
        or not isinstance(checkpoint_log.get("sha256"), str)
        or _SHA256_RE.fullmatch(checkpoint_log["sha256"]) is None
        or not _is_int(checkpoint_log.get("size_bytes"))
        or not 0 < checkpoint_log["size_bytes"] <= MAX_CHECKPOINT_BYTES
    ):
        raise ProofContractError("checkpoint_log_identity_invalid")
    checkpoints = execution.get("runtime_checkpoints")
    expected_checkpoints = [
        {"checkpoint_id": CHECKPOINT_IDS[item], "run_id": payload["run_id"], "status": "passed"}
        for item in JOURNEY_IDS
    ]
    if checkpoints != expected_checkpoints:
        raise ProofContractError("runtime_checkpoint_set_mismatch")
    checkpoint_bytes = _checkpoint_bytes(expected_checkpoints)
    if (
        checkpoint_log["sha256"] != hashlib.sha256(checkpoint_bytes).hexdigest()
        or checkpoint_log["size_bytes"] != len(checkpoint_bytes)
    ):
        raise ProofContractError("checkpoint_log_semantic_mismatch")
    expected_journeys = _passed_journeys(expected_checkpoints)
    if payload.get("journeys") != expected_journeys or payload.get("summary") != _summary(True):
        raise ProofContractError("journey_summary_mismatch")
    manifest_entries = {
        item["path"]: item
        for item in execution["runtime_manifest_before"]["entries"]
    }
    if manifest_entries[ASSEMBLY_FILE_NAME]["sha256"] != inputs["assembly"]["sha256"] or manifest_entries[ASSEMBLY_FILE_NAME]["size_bytes"] != inputs["assembly"]["size_bytes"]:
        raise ProofContractError("assembly_manifest_mismatch")
    if (
        manifest_entries["toolchain/dotnet"]["sha256"] != inputs["dotnet_host"]["sha256"]
        or manifest_entries["toolchain/dotnet"]["size_bytes"] != inputs["dotnet_host"]["size_bytes"]
        or manifest_entries["toolchain/csc.dll"]["sha256"] != inputs["csc"]["sha256"]
        or manifest_entries["toolchain/csc.dll"]["size_bytes"] != inputs["csc"]["size_bytes"]
    ):
        raise ProofContractError("toolchain_manifest_mismatch")


def _validate_receipt_policy(
    payload: dict[str, Any],
    *,
    max_age_seconds: int,
    future_skew_seconds: int,
    now: dt.datetime | None,
    expected_run_id: str | None,
) -> None:
    if not _is_int(max_age_seconds) or max_age_seconds <= 0:
        raise ProofContractError("max_age_invalid")
    if max_age_seconds > DEFAULT_MAX_AGE_SECONDS:
        raise ProofContractError("max_age_policy_weakened")
    if not _is_int(future_skew_seconds) or future_skew_seconds < 0:
        raise ProofContractError("future_skew_invalid")
    if future_skew_seconds > DEFAULT_FUTURE_SKEW_SECONDS:
        raise ProofContractError("future_skew_policy_weakened")
    if expected_run_id is not None and payload["run_id"] != expected_run_id:
        raise ProofContractError("run_id_mismatch")
    started = parse_utc(payload["started_at"])
    completed = parse_utc(payload["completed_at"])
    generated = parse_utc(payload["generated_at"])
    expires = parse_utc(payload["expires_at"])
    if completed < started or completed != generated:
        raise ProofContractError("timestamp_order_invalid")
    try:
        expected_expiry = completed + RECEIPT_LIFETIME
    except OverflowError as exc:
        raise ProofContractError("timestamp_overflow") from exc
    if expires != expected_expiry:
        raise ProofContractError("expiry_binding_mismatch")
    current = normalize_utc(now or utc_now())
    try:
        future_limit = current + dt.timedelta(seconds=future_skew_seconds)
    except OverflowError as exc:
        raise ProofContractError("timestamp_overflow") from exc
    if started > future_limit or completed > future_limit:
        raise ProofContractError("receipt_from_future")
    if current >= expires:
        raise ProofContractError("receipt_expired")
    if current - generated > dt.timedelta(seconds=max_age_seconds):
        raise ProofContractError("receipt_too_old")


def validate_passed_receipt_schema(
    receipt_path: Path,
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    future_skew_seconds: int = DEFAULT_FUTURE_SKEW_SECONDS,
    now: dt.datetime | None = None,
    expected_run_id: str | None = None,
) -> ValidationResult:
    """Validate executed-proof semantics without rebinding every repo input."""

    try:
        payload = _load_receipt(_absolute(receipt_path))
        _validate_passed_schema(payload)
        _validate_receipt_policy(
            payload,
            max_age_seconds=max_age_seconds,
            future_skew_seconds=future_skew_seconds,
            now=now,
            expected_run_id=expected_run_id,
        )
        return ValidationResult(True, "valid", payload)
    except ProofContractError as exc:
        return ValidationResult(False, exc.reason_code)


def validate_passed_receipt(
    root: Path,
    receipt_path: Path,
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    future_skew_seconds: int = DEFAULT_FUTURE_SKEW_SECONDS,
    now: dt.datetime | None = None,
    expected_run_id: str | None = None,
) -> ValidationResult:
    try:
        repository_root = _absolute(root)
        output = _absolute(receipt_path)
        _assert_canonical_output(repository_root, output)
        payload = _load_receipt(output)
        _validate_passed_schema(payload)
        _validate_receipt_policy(
            payload,
            max_age_seconds=max_age_seconds,
            future_skew_seconds=future_skew_seconds,
            now=now,
            expected_run_id=expected_run_id,
        )

        current_candidate = _candidate_source_build_inputs(repository_root)
        if current_candidate != payload["execution"]["candidate_source_build_inputs_after"]:
            raise ProofContractError("candidate_source_build_inputs_current_mismatch")
        current_managed = _managed_dotnet_closure(DOTNET_HOST_PATH)
        if current_managed != payload["execution"]["managed_dotnet_closure_after"]:
            raise ProofContractError("managed_dotnet_closure_current_mismatch")
        sdk_component = current_managed["components"][-1]
        csc_path = Path(sdk_component["path"]) / "Roslyn" / "bincore" / "csc.dll"
        if Path(payload["inputs"]["csc"]["path"]) != csc_path:
            raise ProofContractError("csc_path_untrusted")
        current_inputs = _repo_inputs(repository_root, DOTNET_HOST_PATH, csc_path=csc_path)
        for key in INPUT_FIELDS[:-1]:
            if current_inputs[key] != payload["inputs"][key]:
                raise ProofContractError(f"{key}_identity_mismatch")
        return ValidationResult(True, "valid", payload)
    except ProofContractError as exc:
        return ValidationResult(False, exc.reason_code)


__all__ = [
    "ASSEMBLY_FILE_NAME",
    "CHECKPOINT_FILE_NAME",
    "CHECKPOINT_IDS",
    "CONTRACT_NAME",
    "CONTRACT_VERSION",
    "DEFAULT_FUTURE_SKEW_SECONDS",
    "DEFAULT_MAX_AGE_SECONDS",
    "DEFAULT_RECEIPT_PATH",
    "DOTNET_HOST_PATH",
    "EXECUTION_FIELDS",
    "FixedSmokeExecutor",
    "JOURNEY_IDS",
    "MANIFEST_PATHS",
    "MAX_CHECKPOINT_BYTES",
    "MAX_INPUT_BYTES",
    "MAX_RECEIPT_BYTES",
    "PREPARE_HELPER_PATH",
    "PROJECT_ROOTS",
    "PROJECT_SPECS",
    "PROOF_KIND",
    "ProofContractError",
    "RECEIPT_LIFETIME",
    "ROOT_FIELDS",
    "RUNTIME_CLOSURE_PATHS",
    "RUNTIME_DATA_FILES",
    "RUNTIME_DATA_SPECS",
    "SMOKE_SOURCE_ROOT",
    "TREE_EXCLUDED_DIRECTORIES",
    "ValidationResult",
    "format_utc",
    "run_owned_smoke",
    "validate_passed_receipt",
    "validate_passed_receipt_schema",
]
