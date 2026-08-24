#!/usr/bin/env python3
"""Strict offline validation for the hosted Core runtime-package artifact.

The downloader is responsible for authenticating and digest-checking the outer
GitHub Actions artifact.  This validator receives that exact selector and the
expected extracted-content bindings through a separately trusted authority
file.  It performs no network access and does not infer a "latest" artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


AUTHORITY_CONTRACT = "chummer-hub.core-runtime-package-artifact-authority/v2"
VALIDATION_CONTRACT = "chummer-hub.core-runtime-package-artifact-validation/v2"
INVENTORY_CONTRACT = "chummer-core.runtime-package-inventory/v1"
RECEIPT_CONTRACT = "chummer-core.no-siblings-package-plane/v3"
RUNTIME_LOCK_CONTRACT = "chummer-core.runtime-package-plane-lock/v1"
OWNER_INVENTORY_CONTRACT = "chummer-core.owner-contract-package-inventory/v1"
CORE_REPOSITORY = "https://github.com/ArchonMegalon/chummer6-core.git"
REGISTRY_REPOSITORY = "https://github.com/ArchonMegalon/chummer6-hub-registry.git"
HUB_REPOSITORY = "https://github.com/ArchonMegalon/chummer6-hub.git"
LICENSE_EXPRESSION = "GPL-3.0-only"
SDK_VERSION = "10.0.103"
SDK_RID = "linux-x64"
SDK_ARCHIVE_URL = (
    "https://builds.dotnet.microsoft.com/dotnet/Sdk/10.0.103/"
    "dotnet-sdk-10.0.103-linux-x64.tar.gz"
)
SDK_ARCHIVE_SHA512 = (
    "bab94f13c57b2ac821d4924fe66084be9b44c41761ff7ff64522c8f7aba345659"
    "d31258401dcec31cc3cf6ccae1d012623075aca1c9b9165bcfe5ba9abda1c0c"
)
RUNTIME_PACKAGE_VERSION = "0.0.0-packageplane.candidate.shabc08228d3ce0"
RUNTIME_SOURCE_COMMIT = "bc08228d3ce06410ca97ada63a5af41a2eaa91bf"
OWNER_PACKAGE_VERSION = "0.0.0-packageplane.20260721.1"

INVENTORY_FILE_NAME = "chummer-core-runtime-packages.inventory.json"
LOCK_FILE_NAME = "runtime-package-plane.lock.json"
RECEIPT_FILE_NAME = "no-siblings.v3.receipt.json"
PACKAGES_DIRECTORY_NAME = "packages"

EXPECTED_PACKAGE_IDS = (
    "Chummer.Engine.Contracts",
    "Chummer.Application",
    "Chummer.Rulesets.Hosting",
    "Chummer.Rulesets.Sr5",
    "Chummer.Rulesets.Sr6",
    "Chummer.Infrastructure",
    "Chummer.Rulesets.Sr4",
    "Chummer.Engine.GmCharacterEdits",
)
EXPECTED_ALLOWED_RECIPE_DELTA = (
    ".github/workflows/package-plane.yml",
    "Chummer.Application/Chummer.Application.csproj",
    "Chummer.Contracts/Chummer.Contracts.csproj",
    "Chummer.GmCharacterEdits/Chummer.GmCharacterEdits.csproj",
    "Chummer.Infrastructure/Chummer.Infrastructure.csproj",
    "Chummer.Rulesets.Hosting/Chummer.Rulesets.Hosting.csproj",
    "Chummer.Rulesets.Sr4/Chummer.Rulesets.Sr4.csproj",
    "Chummer.Rulesets.Sr5/Chummer.Rulesets.Sr5.csproj",
    "Chummer.Rulesets.Sr6/Chummer.Rulesets.Sr6.csproj",
    "eng/runtime-package-plane.lock.json",
    "scripts/ai/runtime-package-plane.py",
    "scripts/ai/verify-no-siblings-package-plane.sh",
    "tests/test_package_plane.py",
    "tests/test_runtime_package_plane_authority.py",
)
EXPECTED_BUILD_AUTHORITY_PATHS = (
    ".github/workflows/package-plane.yml",
    "Chummer.CoreEngine.sln",
    "Directory.Build.props",
    "Directory.Build.targets",
    "eng/package-plane.lock.json",
    "global.json",
    "scripts/ai/_env.sh",
    "scripts/ai/bootstrap-contracts-feed.sh",
    "scripts/ai/bootstrap-owner-contracts-feed.py",
    "scripts/ai/runtime-package-plane.py",
    "scripts/ai/verify-no-siblings-package-plane.sh",
)
EXPECTED_EXTERNAL_OWNER_PACKAGES = (
    (
        "Chummer.Hub.Registry.Contracts",
        OWNER_PACKAGE_VERSION,
        REGISTRY_REPOSITORY,
        "af9a7e19c3bf331e96411dfb8f9e7820a98cab29",
    ),
    (
        "Chummer.Play.Contracts",
        OWNER_PACKAGE_VERSION,
        HUB_REPOSITORY,
        "7c1faef298fb9028e77069c2467686f92624566c",
    ),
    (
        "Chummer.Run.Contracts",
        OWNER_PACKAGE_VERSION,
        HUB_REPOSITORY,
        "7c1faef298fb9028e77069c2467686f92624566c",
    ),
)
EXPECTED_THIRD_PARTY_PACKAGES = (
    ("Microsoft.Extensions.DependencyInjection", "10.0.0"),
    ("SharpCompress", "0.50.1"),
)
EXPECTED_RUNTIME_PACKAGE_SPECS = (
    (
        "Chummer.Engine.Contracts",
        "Chummer.Contracts/Chummer.Contracts.csproj",
        "1ae056091372ae0fb353b983023cea521ac848b899fd8d3ca3d45e546f57707e",
        "Chummer.Engine.Contracts.dll",
        (),
    ),
    (
        "Chummer.Application",
        "Chummer.Application/Chummer.Application.csproj",
        "cf5fc7f7f7d25c2ab20ba7719f3a60929cd78b205b9a43683b4a7048fcf0c19a",
        "Chummer.Application.dll",
        (
            ("Chummer.Engine.Contracts", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Hub.Registry.Contracts", OWNER_PACKAGE_VERSION),
            ("Chummer.Run.Contracts", OWNER_PACKAGE_VERSION),
        ),
    ),
    (
        "Chummer.Rulesets.Hosting",
        "Chummer.Rulesets.Hosting/Chummer.Rulesets.Hosting.csproj",
        "b3e1145840a1767a92e6e7c42fa5e510249753b36973e75050d6eac198e17521",
        "Chummer.Rulesets.Hosting.dll",
        (
            ("Chummer.Application", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Engine.Contracts", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Run.Contracts", OWNER_PACKAGE_VERSION),
            ("Microsoft.Extensions.DependencyInjection", "10.0.0"),
        ),
    ),
    (
        "Chummer.Rulesets.Sr5",
        "Chummer.Rulesets.Sr5/Chummer.Rulesets.Sr5.csproj",
        "2f7f91916c55035d42d7e5bddd52e76379ad2d0bb6d6eb4ff7ac5c7bbbea9826",
        "Chummer.Rulesets.Sr5.dll",
        (
            ("Chummer.Application", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Engine.Contracts", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Run.Contracts", OWNER_PACKAGE_VERSION),
            ("Microsoft.Extensions.DependencyInjection", "10.0.0"),
        ),
    ),
    (
        "Chummer.Rulesets.Sr6",
        "Chummer.Rulesets.Sr6/Chummer.Rulesets.Sr6.csproj",
        "23023db965dbfbf1795a5d660f5d3d3bc0d12f17b0a164882e6910e1a25a1f1f",
        "Chummer.Rulesets.Sr6.dll",
        (
            ("Chummer.Application", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Engine.Contracts", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Run.Contracts", OWNER_PACKAGE_VERSION),
            ("Microsoft.Extensions.DependencyInjection", "10.0.0"),
        ),
    ),
    (
        "Chummer.Infrastructure",
        "Chummer.Infrastructure/Chummer.Infrastructure.csproj",
        "e017c01931b664a99cf4d74d89f0e6ed07576c1de47dfa89b740eb972f877936",
        "Chummer.Infrastructure.dll",
        (
            ("Chummer.Application", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Engine.Contracts", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Hub.Registry.Contracts", OWNER_PACKAGE_VERSION),
            ("Chummer.Rulesets.Hosting", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Rulesets.Sr5", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Rulesets.Sr6", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Run.Contracts", OWNER_PACKAGE_VERSION),
            ("Microsoft.Extensions.DependencyInjection", "10.0.0"),
            ("SharpCompress", "0.50.1"),
        ),
    ),
    (
        "Chummer.Rulesets.Sr4",
        "Chummer.Rulesets.Sr4/Chummer.Rulesets.Sr4.csproj",
        "86eafdcdf1638c3651d5357acd7f99023ca97c5641d83432be2b3c12f3ba5fb5",
        "Chummer.Rulesets.Sr4.dll",
        (
            ("Chummer.Application", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Engine.Contracts", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Infrastructure", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Run.Contracts", OWNER_PACKAGE_VERSION),
            ("Microsoft.Extensions.DependencyInjection", "10.0.0"),
        ),
    ),
    (
        "Chummer.Engine.GmCharacterEdits",
        "Chummer.GmCharacterEdits/Chummer.GmCharacterEdits.csproj",
        "7c2508ce3ee1c64338cc80df71e3a98487c5c8323db9bccb68e740f13f3db6a6",
        "Chummer.Engine.GmCharacterEdits.dll",
        (
            ("Chummer.Application", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Engine.Contracts", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Hub.Registry.Contracts", OWNER_PACKAGE_VERSION),
            ("Chummer.Infrastructure", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Rulesets.Hosting", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Rulesets.Sr5", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Rulesets.Sr6", RUNTIME_PACKAGE_VERSION),
            ("Chummer.Run.Contracts", OWNER_PACKAGE_VERSION),
        ),
    ),
)
LOCKED_OWNER_PACKAGE_IDS = (
    "Chummer.Engine.Contracts",
    "Chummer.Hub.Registry.Contracts",
    "Chummer.Play.Contracts",
    "Chummer.Run.Contracts",
)
LOCKED_OWNER_PACKAGE_ROLES = (
    "locked_engine_baseline_not_selected",
    "locked_owner_dependency",
    "locked_owner_dependency",
    "locked_owner_dependency",
)
RESOLVED_RUNTIME_ROLE = "current_core_runtime_candidate"
EXPECTED_PACKAGE_SOURCE_MAPPING = {
    "Chummer.*": "locked-owner-contracts",
    "other": "https://api.nuget.org/v3/index.json",
}
PASS_RECEIPT_FIELDS = (
    "normal_local_engine_dependency_graph",
    "build",
    "package_plane_runtime_test",
    "local_owner_isolation_tests",
    "candidate_engine_contract_pack",
    "candidate_gm_edit_runtime_pack",
    "candidate_gm_edit_runtime_consumer",
    "eight_package_runtime_plane",
)

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SHA512_PATTERN = re.compile(r"^[0-9a-f]{128}$")
PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
PACKAGE_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.nupkg$")
ASSEMBLY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.dll$")
UTC_TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
DOTNET_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
CORE_PROPERTIES_PATTERN = re.compile(
    r"^package/services/metadata/core-properties/[0-9a-f]{64}\.psmdcp$"
)

MAX_AUTHORITY_BYTES = 128 * 1024
MAX_INVENTORY_BYTES = 2 * 1024 * 1024
MAX_LOCK_BYTES = 8 * 1024 * 1024
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_PACKAGE_BYTES = 512 * 1024 * 1024

AUTHORITY_KEYS = {
    "contract",
    "artifact_selector",
    "runtime_package_plane_lock",
    "inventory",
    "receipt",
    "owner_package_plane_lock_sha256",
    "owner_package_inventory_sha256",
    "owner_package_inventory",
    "candidate_engine_package_inventory_sha256",
    "candidate_runtime_package_inventory_sha256",
    "runtime_source_commit",
    "package_recipe_commit",
    "owner_package_version",
    "runtime_package_version",
}
ARTIFACT_SELECTOR_KEYS = {
    "repository",
    "workflow_run_id",
    "artifact_id",
    "name",
    "sha256",
}
FILE_BINDING_KEYS = {"sha256"}
LOCK_BINDING_KEYS = {"contract", "sha256"}
OWNER_INVENTORY_BINDING_KEYS = {
    "contract",
    "sha256",
    "package_version",
    "packages",
}
OWNER_AUTHORITY_PACKAGE_KEYS = {"id", "version", "sha256", "size_bytes"}
RUNTIME_LOCK_KEYS = {
    "contract",
    "dotnet_sdk",
    "package_version",
    "runtime_source",
    "allowed_recipe_delta",
    "build_authority_files",
    "external_owner_packages",
    "third_party_packages",
    "packages",
}
DOTNET_SDK_KEYS = {"version", "rid", "archive_url", "archive_sha512"}
RUNTIME_SOURCE_KEYS = {"repository", "commit"}
BUILD_AUTHORITY_KEYS = {"path", "sha256"}
EXTERNAL_OWNER_KEYS = {"id", "version", "repository", "commit"}
THIRD_PARTY_KEYS = {"id", "version"}
RUNTIME_LOCK_PACKAGE_KEYS = {
    "id",
    "project",
    "project_sha256",
    "assembly",
    "target_framework",
    "dependencies",
}
INVENTORY_KEYS = {
    "contract",
    "package_plane_lock_sha256",
    "package_version",
    "runtime_source_commit",
    "package_recipe_commit",
    "packages",
}
PACKAGE_KEYS = {
    "id",
    "version",
    "repository",
    "source_commit",
    "project",
    "assembly",
    "target_framework",
    "dependencies",
    "file_name",
    "sha256",
    "size_bytes",
}
DEPENDENCY_KEYS = {"id", "version"}
OWNER_PACKAGE_KEYS = {"id", "version", "sha256", "size_bytes", "role"}
RESOLVED_RUNTIME_PACKAGE_KEYS = PACKAGE_KEYS | {"role"}
RECEIPT_KEYS = {
    "contract",
    "generated_at_utc",
    "status",
    "core_commit",
    "package_plane_lock_sha256",
    "package_inventory_sha256",
    "candidate_package_inventory_sha256",
    "candidate_runtime_package_inventory_sha256",
    "runtime_package_inventory_sha256",
    "runtime_package_plane_lock_sha256",
    "runtime_source_commit",
    "package_recipe_commit",
    "package_version",
    "candidate_package_version",
    "locked_packages",
    "resolved_owner_contracts",
    "no_sibling_directories",
    "isolated_package_cache",
    "package_source_mapping",
    "normal_local_engine_dependency_graph",
    "build",
    "package_plane_runtime_test",
    "local_owner_isolation_tests",
    "candidate_engine_contract_pack",
    "candidate_gm_edit_runtime_pack",
    "candidate_gm_edit_runtime_consumer",
    "eight_package_runtime_plane",
}


class ArtifactValidationError(RuntimeError):
    """Raised when hosted Core artifact authority cannot be proven."""


@dataclass(frozen=True)
class Authority:
    artifact_selector: Mapping[str, Any]
    runtime_lock_contract: str
    runtime_lock_sha256: str
    inventory_sha256: str
    receipt_sha256: str
    owner_lock_sha256: str
    owner_inventory_sha256: str
    owner_packages: tuple[Mapping[str, Any], ...]
    candidate_engine_inventory_sha256: str
    candidate_runtime_inventory_sha256: str
    runtime_source_commit: str
    package_recipe_commit: str
    owner_package_version: str
    runtime_package_version: str


@dataclass(frozen=True)
class RuntimeLock:
    package_version: str
    runtime_source_commit: str
    packages: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class DirectorySnapshot:
    descriptor: int
    identity: tuple[int, int, int, int, int, int]


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ArtifactValidationError(f"non-finite JSON number is forbidden: {value}")


def _decode_json(payload: bytes, *, label: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except ArtifactValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"invalid {label} JSON: {exc}") from exc


def _exact_object(value: Any, keys: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        missing = sorted(keys - set(value)) if isinstance(value, dict) else sorted(keys)
        extra = sorted(set(value) - keys) if isinstance(value, dict) else []
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("unknown=" + ",".join(extra))
        suffix = f" ({'; '.join(details)})" if details else ""
        raise ArtifactValidationError(f"{label} must contain exact fields{suffix}")
    return value


def _canonical_string(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 32 for character in value)
    ):
        raise ArtifactValidationError(f"{label} must be a non-empty canonical string")
    return value


def _sha(value: Any, *, label: str) -> str:
    rendered = _canonical_string(value, label=label)
    if SHA_PATTERN.fullmatch(rendered) is None:
        raise ArtifactValidationError(f"{label} must be a lowercase 40-character commit")
    return rendered


def _sha256_value(value: Any, *, label: str) -> str:
    rendered = _canonical_string(value, label=label)
    if SHA256_PATTERN.fullmatch(rendered) is None:
        raise ArtifactValidationError(f"{label} must be a lowercase SHA-256")
    return rendered


def _sha512_value(value: Any, *, label: str) -> str:
    rendered = _canonical_string(value, label=label)
    if SHA512_PATTERN.fullmatch(rendered) is None:
        raise ArtifactValidationError(f"{label} must be a lowercase SHA-512")
    return rendered


def _positive_integer(value: Any, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ArtifactValidationError(f"{label} must be a positive integer")
    return value


def _positive_size(value: Any, *, label: str) -> int:
    return _positive_integer(value, label=label)


def _safe_file_name(value: Any, *, label: str, pattern: re.Pattern[str]) -> str:
    rendered = _canonical_string(value, label=label)
    path = PurePosixPath(rendered)
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or path.name != rendered
        or rendered in {".", ".."}
        or "/" in rendered
        or "\\" in rendered
        or pattern.fullmatch(rendered) is None
    ):
        raise ArtifactValidationError(f"{label} must be one safe canonical file name")
    return rendered


def _safe_project_path(value: Any, *, label: str) -> str:
    rendered = _canonical_string(value, label=label)
    path = PurePosixPath(rendered)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in rendered
    ):
        raise ArtifactValidationError(f"{label} must be a contained POSIX relative path")
    return rendered


def _directory_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _open_directory(
    path: Path | str,
    *,
    label: str,
    directory_fd: int | None = None,
) -> DirectorySnapshot:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, dir_fd=directory_fd)
        metadata = os.fstat(descriptor)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ArtifactValidationError(
            f"{label} must be one non-symlink directory with stable identity"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise ArtifactValidationError(f"{label} must be one non-symlink directory")
    return DirectorySnapshot(descriptor, _directory_identity(metadata))


def _directory_names(snapshot: DirectorySnapshot, *, label: str) -> list[str]:
    try:
        before = os.fstat(snapshot.descriptor)
        names = os.listdir(snapshot.descriptor)
        after = os.fstat(snapshot.descriptor)
    except OSError as exc:
        raise ArtifactValidationError(f"unable to enumerate {label}") from exc
    if (
        _directory_identity(before) != snapshot.identity
        or _directory_identity(after) != snapshot.identity
    ):
        raise ArtifactValidationError(f"{label} changed while it was validated")
    if len(names) != len(set(names)):
        raise ArtifactValidationError(f"{label} contains duplicate member names")
    return names


def _require_exact_directory_names(
    snapshot: DirectorySnapshot,
    expected_names: set[str],
    *,
    label: str,
) -> None:
    observed_names = set(_directory_names(snapshot, label=label))
    if observed_names != expected_names:
        missing = sorted(expected_names - observed_names)
        foreign = sorted(observed_names - expected_names)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if foreign:
            details.append("foreign=" + ",".join(foreign))
        raise ArtifactValidationError(
            f"{label} must contain the exact layout (" + "; ".join(details) + ")"
        )


def _stable_file_bytes(path: Path, *, label: str, maximum: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ArtifactValidationError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > maximum
    ):
        raise ArtifactValidationError(
            f"{label} must be one bounded, single-link regular file"
        )
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
            ):
                raise ArtifactValidationError(f"{label} changed while it was opened")
            payload = stream.read(maximum + 1)
            if len(payload) > maximum or stream.read(1):
                raise ArtifactValidationError(f"{label} exceeds its size bound")
        after = path.lstat()
    except ArtifactValidationError:
        raise
    except OSError as exc:
        raise ArtifactValidationError(f"unable to read {label}") from exc
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_after != identity_before or not stat.S_ISREG(after.st_mode) or after.st_nlink != 1:
        raise ArtifactValidationError(f"{label} changed while it was read")
    return payload


def _stable_file_bytes_at(
    directory_fd: int,
    name: str,
    *,
    label: str,
    maximum: int,
) -> bytes:
    if PurePosixPath(name).name != name or "/" in name or "\\" in name:
        raise ArtifactValidationError(f"{label} does not have one contained file name")
    try:
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise ArtifactValidationError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > maximum
    ):
        raise ArtifactValidationError(
            f"{label} must be one bounded, single-link regular file"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
            ):
                raise ArtifactValidationError(f"{label} changed while it was opened")
            payload = stream.read(maximum + 1)
            if len(payload) > maximum or stream.read(1):
                raise ArtifactValidationError(f"{label} exceeds its size bound")
        after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except ArtifactValidationError:
        raise
    except OSError as exc:
        raise ArtifactValidationError(f"unable to read {label}") from exc
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_after != identity_before or not stat.S_ISREG(after.st_mode) or after.st_nlink != 1:
        raise ArtifactValidationError(f"{label} changed while it was read")
    return payload


def _load_json_file(path: Path, *, label: str, maximum: int) -> tuple[Any, bytes, str]:
    payload = _stable_file_bytes(path, label=label, maximum=maximum)
    return _decode_json(payload, label=label), payload, hashlib.sha256(payload).hexdigest()


def _load_json_file_at(
    directory_fd: int,
    name: str,
    *,
    label: str,
    maximum: int,
) -> tuple[Any, bytes, str]:
    payload = _stable_file_bytes_at(
        directory_fd, name, label=label, maximum=maximum
    )
    return _decode_json(payload, label=label), payload, hashlib.sha256(payload).hexdigest()


def _require_final_file_binding(
    directory_fd: int,
    name: str,
    *,
    label: str,
    maximum: int,
    expected_size: int,
    expected_sha256: str,
) -> None:
    payload = _stable_file_bytes_at(
        directory_fd, name, label=f"final {label}", maximum=maximum
    )
    if (
        len(payload) != expected_size
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise ArtifactValidationError(f"final byte binding differs for {label}")


def load_authority(path: Path) -> Authority:
    payload, _raw, _digest = _load_json_file(
        path, label="Core artifact authority", maximum=MAX_AUTHORITY_BYTES
    )
    root = _exact_object(payload, AUTHORITY_KEYS, label="Core artifact authority")
    if root.get("contract") != AUTHORITY_CONTRACT:
        raise ArtifactValidationError(
            f"Core artifact authority contract must be {AUTHORITY_CONTRACT}"
        )

    selector = _exact_object(
        root.get("artifact_selector"),
        ARTIFACT_SELECTOR_KEYS,
        label="artifact_selector",
    )
    repository = _canonical_string(selector.get("repository"), label="artifact repository")
    if repository != CORE_REPOSITORY:
        raise ArtifactValidationError("artifact repository is not the canonical Core repository")
    _positive_integer(selector.get("workflow_run_id"), label="artifact workflow_run_id")
    _positive_integer(selector.get("artifact_id"), label="artifact artifact_id")
    artifact_digest = _sha256_value(selector.get("sha256"), label="artifact sha256")

    runtime_source_commit = _sha(
        root.get("runtime_source_commit"), label="authority runtime_source_commit"
    )
    if runtime_source_commit != RUNTIME_SOURCE_COMMIT:
        raise ArtifactValidationError("authority runtime_source_commit differs from current Core v1")
    package_recipe_commit = _sha(
        root.get("package_recipe_commit"), label="authority package_recipe_commit"
    )
    artifact_name = _canonical_string(selector.get("name"), label="artifact name")
    expected_name = f"chummer-core-runtime-package-plane-{package_recipe_commit}"
    if artifact_name != expected_name:
        raise ArtifactValidationError(
            "artifact name must bind the exact package recipe commit"
        )

    runtime_lock_binding = _exact_object(
        root.get("runtime_package_plane_lock"),
        LOCK_BINDING_KEYS,
        label="runtime_package_plane_lock binding",
    )
    runtime_lock_contract = _canonical_string(
        runtime_lock_binding.get("contract"),
        label="runtime package-plane lock contract",
    )
    if runtime_lock_contract != RUNTIME_LOCK_CONTRACT:
        raise ArtifactValidationError(
            f"runtime package-plane lock contract must be {RUNTIME_LOCK_CONTRACT}"
        )
    runtime_lock_sha256 = _sha256_value(
        runtime_lock_binding.get("sha256"),
        label="runtime package-plane lock sha256",
    )
    inventory_binding = _exact_object(
        root.get("inventory"), FILE_BINDING_KEYS, label="inventory binding"
    )
    receipt_binding = _exact_object(
        root.get("receipt"), FILE_BINDING_KEYS, label="receipt binding"
    )
    inventory_sha256 = _sha256_value(
        inventory_binding.get("sha256"), label="inventory sha256"
    )
    receipt_sha256 = _sha256_value(
        receipt_binding.get("sha256"), label="receipt sha256"
    )
    owner_lock_sha256 = _sha256_value(
        root.get("owner_package_plane_lock_sha256"),
        label="owner package-plane lock sha256",
    )
    owner_inventory_sha256 = _sha256_value(
        root.get("owner_package_inventory_sha256"),
        label="owner package inventory sha256",
    )
    owner_package_version = _canonical_string(
        root.get("owner_package_version"),
        label="authority owner_package_version",
    )
    if owner_package_version != OWNER_PACKAGE_VERSION:
        raise ArtifactValidationError("authority owner_package_version differs from current Core v1")
    owner_inventory_binding = _exact_object(
        root.get("owner_package_inventory"),
        OWNER_INVENTORY_BINDING_KEYS,
        label="owner_package_inventory binding",
    )
    if owner_inventory_binding.get("contract") != OWNER_INVENTORY_CONTRACT:
        raise ArtifactValidationError(
            f"owner package inventory contract must be {OWNER_INVENTORY_CONTRACT}"
        )
    if owner_inventory_binding.get("sha256") != owner_inventory_sha256:
        raise ArtifactValidationError(
            "owner package inventory binding digest differs from scalar authority"
        )
    if owner_inventory_binding.get("package_version") != owner_package_version:
        raise ArtifactValidationError(
            "owner package inventory binding version differs from authority"
        )
    owner_values = owner_inventory_binding.get("packages")
    if not isinstance(owner_values, list) or len(owner_values) != len(
        LOCKED_OWNER_PACKAGE_IDS
    ):
        raise ArtifactValidationError(
            "owner package inventory binding must contain exactly four package rows"
        )
    owner_packages: list[dict[str, Any]] = []
    for index, (expected_id, value_row) in enumerate(
        zip(LOCKED_OWNER_PACKAGE_IDS, owner_values, strict=True)
    ):
        row = _exact_object(
            value_row,
            OWNER_AUTHORITY_PACKAGE_KEYS,
            label=f"owner package authority packages[{index}]",
        )
        package_id = _canonical_string(
            row.get("id"), label=f"owner package authority packages[{index}].id"
        )
        if package_id != expected_id:
            raise ArtifactValidationError(
                "owner package authority IDs or order differ from policy"
            )
        if row.get("version") != owner_package_version:
            raise ArtifactValidationError(
                f"owner package authority version drift for {package_id}"
            )
        owner_packages.append(
            {
                "id": package_id,
                "version": owner_package_version,
                "sha256": _sha256_value(
                    row.get("sha256"), label=f"owner package authority {package_id} sha256"
                ),
                "size_bytes": _positive_size(
                    row.get("size_bytes"),
                    label=f"owner package authority {package_id} size_bytes",
                ),
            }
        )
    candidate_engine_inventory_sha256 = _sha256_value(
        root.get("candidate_engine_package_inventory_sha256"),
        label="candidate engine package inventory sha256",
    )
    candidate_runtime_inventory_sha256 = _sha256_value(
        root.get("candidate_runtime_package_inventory_sha256"),
        label="candidate runtime package inventory sha256",
    )
    runtime_package_version = _canonical_string(
        root.get("runtime_package_version"),
        label="authority runtime_package_version",
    )
    if runtime_package_version != RUNTIME_PACKAGE_VERSION:
        raise ArtifactValidationError("authority runtime_package_version differs from current Core v1")
    return Authority(
        artifact_selector={
            "repository": repository,
            "workflow_run_id": selector["workflow_run_id"],
            "artifact_id": selector["artifact_id"],
            "name": artifact_name,
            "sha256": artifact_digest,
        },
        runtime_lock_contract=runtime_lock_contract,
        runtime_lock_sha256=runtime_lock_sha256,
        inventory_sha256=inventory_sha256,
        receipt_sha256=receipt_sha256,
        owner_lock_sha256=owner_lock_sha256,
        owner_inventory_sha256=owner_inventory_sha256,
        owner_packages=tuple(owner_packages),
        candidate_engine_inventory_sha256=candidate_engine_inventory_sha256,
        candidate_runtime_inventory_sha256=candidate_runtime_inventory_sha256,
        runtime_source_commit=runtime_source_commit,
        package_recipe_commit=package_recipe_commit,
        owner_package_version=owner_package_version,
        runtime_package_version=runtime_package_version,
    )


def _validate_runtime_lock(value: Any, *, authority: Authority) -> RuntimeLock:
    root = _exact_object(value, RUNTIME_LOCK_KEYS, label="runtime package-plane lock")
    if root.get("contract") != RUNTIME_LOCK_CONTRACT:
        raise ArtifactValidationError(
            f"runtime package-plane lock contract must be {RUNTIME_LOCK_CONTRACT}"
        )

    sdk = _exact_object(root.get("dotnet_sdk"), DOTNET_SDK_KEYS, label="dotnet_sdk")
    sdk_version = _canonical_string(sdk.get("version"), label="dotnet_sdk.version")
    if DOTNET_VERSION_PATTERN.fullmatch(sdk_version) is None:
        raise ArtifactValidationError("dotnet_sdk.version must be an exact three-part version")
    sdk_rid = _canonical_string(sdk.get("rid"), label="dotnet_sdk.rid")
    archive_url = _canonical_string(sdk.get("archive_url"), label="dotnet_sdk.archive_url")
    archive_sha512 = _sha512_value(
        sdk.get("archive_sha512"), label="dotnet_sdk.archive_sha512"
    )
    if (sdk_version, sdk_rid, archive_url, archive_sha512) != (
        SDK_VERSION,
        SDK_RID,
        SDK_ARCHIVE_URL,
        SDK_ARCHIVE_SHA512,
    ):
        raise ArtifactValidationError("dotnet SDK archive authority differs from current Core v1")

    if root.get("package_version") != RUNTIME_PACKAGE_VERSION:
        raise ArtifactValidationError("runtime lock package_version differs from current Core v1")
    runtime_source = _exact_object(
        root.get("runtime_source"), RUNTIME_SOURCE_KEYS, label="runtime_source"
    )
    if runtime_source.get("repository") != CORE_REPOSITORY:
        raise ArtifactValidationError("runtime lock source repository is not canonical Core")
    if runtime_source.get("commit") != RUNTIME_SOURCE_COMMIT:
        raise ArtifactValidationError("runtime lock source commit differs from current Core v1")

    allowed_delta = root.get("allowed_recipe_delta")
    if not isinstance(allowed_delta, list) or not allowed_delta:
        raise ArtifactValidationError("allowed_recipe_delta must be one non-empty list")
    normalized_delta = [
        _safe_project_path(row, label=f"allowed_recipe_delta[{index}]")
        for index, row in enumerate(allowed_delta)
    ]
    if len(normalized_delta) != len(set(value.casefold() for value in normalized_delta)):
        raise ArtifactValidationError("allowed_recipe_delta paths must be case-insensitively unique")
    if normalized_delta != list(EXPECTED_ALLOWED_RECIPE_DELTA):
        raise ArtifactValidationError(
            "allowed_recipe_delta omission, addition, or order differs from current Core v1"
        )

    build_authority = root.get("build_authority_files")
    if not isinstance(build_authority, list) or not build_authority:
        raise ArtifactValidationError("build_authority_files must be one non-empty list")
    build_paths: list[str] = []
    for index, value_row in enumerate(build_authority):
        row = _exact_object(
            value_row, BUILD_AUTHORITY_KEYS, label=f"build_authority_files[{index}]"
        )
        build_paths.append(
            _safe_project_path(row.get("path"), label=f"build_authority_files[{index}].path")
        )
        _sha256_value(row.get("sha256"), label=f"build_authority_files[{index}].sha256")
    if len(build_paths) != len(set(value.casefold() for value in build_paths)):
        raise ArtifactValidationError("build authority paths must be case-insensitively unique")
    if build_paths != list(EXPECTED_BUILD_AUTHORITY_PATHS):
        raise ArtifactValidationError(
            "build authority path omission, addition, or order differs from current Core v1"
        )

    external_values = root.get("external_owner_packages")
    if not isinstance(external_values, list) or len(external_values) != len(
        EXPECTED_EXTERNAL_OWNER_PACKAGES
    ):
        raise ArtifactValidationError("external_owner_packages must contain Registry/Play/Run")
    external_ids: list[str] = []
    for index, (
        (expected_id, expected_version, expected_repository, expected_commit),
        value_row,
    ) in enumerate(
        zip(EXPECTED_EXTERNAL_OWNER_PACKAGES, external_values, strict=True)
    ):
        row = _exact_object(
            value_row, EXTERNAL_OWNER_KEYS, label=f"external_owner_packages[{index}]"
        )
        commit = _sha(row.get("commit"), label=f"external owner package {expected_id} commit")
        if (
            row.get("id"),
            row.get("version"),
            row.get("repository"),
            commit,
        ) != (expected_id, expected_version, expected_repository, expected_commit):
            raise ArtifactValidationError(
                "external owner package omission, addition, order, or authority differs from current Core v1"
            )
        external_ids.append(expected_id)

    third_party_values = root.get("third_party_packages")
    expected_third_party = [
        {"id": package_id, "version": version}
        for package_id, version in EXPECTED_THIRD_PARTY_PACKAGES
    ]
    if not isinstance(third_party_values, list):
        raise ArtifactValidationError("third_party_packages must be one list")
    normalized_third_party = [
        _exact_object(row, THIRD_PARTY_KEYS, label=f"third_party_packages[{index}]")
        for index, row in enumerate(third_party_values)
    ]
    if normalized_third_party != expected_third_party:
        raise ArtifactValidationError("third-party package authority differs from current Core v1")

    package_values = root.get("packages")
    if not isinstance(package_values, list) or len(package_values) != len(EXPECTED_PACKAGE_IDS):
        raise ArtifactValidationError("runtime lock must contain exactly eight package rows")
    version_authority = {
        **{package_id: RUNTIME_PACKAGE_VERSION for package_id in EXPECTED_PACKAGE_IDS},
        **{package_id: OWNER_PACKAGE_VERSION for package_id in external_ids},
        **dict(EXPECTED_THIRD_PARTY_PACKAGES),
    }
    packages: list[dict[str, Any]] = []
    observed_assemblies: set[str] = set()
    seen_internal: set[str] = set()
    for index, (expected_id, value_row) in enumerate(
        zip(EXPECTED_PACKAGE_IDS, package_values, strict=True)
    ):
        row = _exact_object(
            value_row, RUNTIME_LOCK_PACKAGE_KEYS, label=f"runtime lock packages[{index}]"
        )
        if row.get("id") != expected_id:
            raise ArtifactValidationError("runtime lock package IDs or order differ from policy")
        project = _safe_project_path(row.get("project"), label=f"runtime lock {expected_id} project")
        project_sha256 = _sha256_value(
            row.get("project_sha256"), label=f"runtime lock {expected_id} project_sha256"
        )
        assembly = _safe_file_name(
            row.get("assembly"), label=f"runtime lock {expected_id} assembly", pattern=ASSEMBLY_PATTERN
        )
        if assembly.casefold() in observed_assemblies:
            raise ArtifactValidationError("runtime lock assembly ownership is not unique")
        observed_assemblies.add(assembly.casefold())
        if row.get("target_framework") != "net10.0":
            raise ArtifactValidationError(f"runtime lock target framework drift for {expected_id}")
        dependencies_value = row.get("dependencies")
        if not isinstance(dependencies_value, list):
            raise ArtifactValidationError(f"runtime lock dependencies must be a list for {expected_id}")
        dependencies = [
            _validate_dependency(dependency, package_id=expected_id, index=dependency_index)
            for dependency_index, dependency in enumerate(dependencies_value)
        ]
        dependency_ids = [dependency["id"] for dependency in dependencies]
        if len(dependency_ids) != len(set(value.casefold() for value in dependency_ids)):
            raise ArtifactValidationError(f"duplicate runtime lock dependency in {expected_id}")
        for dependency in dependencies:
            dependency_id = dependency["id"]
            if dependency_id not in version_authority:
                raise ArtifactValidationError(f"unknown runtime lock dependency in {expected_id}")
            if dependency["version"] != version_authority[dependency_id]:
                raise ArtifactValidationError(f"runtime lock dependency version drift in {expected_id}")
            if dependency_id in EXPECTED_PACKAGE_IDS and dependency_id not in seen_internal:
                raise ArtifactValidationError(f"runtime lock package order is not topological for {expected_id}")
        packages.append(
            {
                "id": expected_id,
                "project": project,
                "project_sha256": project_sha256,
                "assembly": assembly,
                "target_framework": "net10.0",
                "dependencies": dependencies,
            }
        )
        seen_internal.add(expected_id)
    expected_packages = [
        {
            "id": package_id,
            "project": project,
            "project_sha256": project_sha256,
            "assembly": assembly,
            "target_framework": "net10.0",
            "dependencies": [
                {"id": dependency_id, "version": version}
                for dependency_id, version in dependencies
            ],
        }
        for package_id, project, project_sha256, assembly, dependencies in (
            EXPECTED_RUNTIME_PACKAGE_SPECS
        )
    ]
    if packages != expected_packages:
        raise ArtifactValidationError(
            "runtime package omission, addition, order, project, digest, assembly, or dependency authority differs from current Core v1"
        )
    return RuntimeLock(
        package_version=authority.runtime_package_version,
        runtime_source_commit=authority.runtime_source_commit,
        packages=tuple(packages),
    )


def _validate_dependency(value: Any, *, package_id: str, index: int) -> dict[str, str]:
    row = _exact_object(
        value, DEPENDENCY_KEYS, label=f"{package_id} dependencies[{index}]"
    )
    dependency_id = _canonical_string(
        row.get("id"), label=f"{package_id} dependency id"
    )
    if PACKAGE_ID_PATTERN.fullmatch(dependency_id) is None:
        raise ArtifactValidationError(f"invalid dependency id in {package_id}")
    version = _canonical_string(
        row.get("version"), label=f"{package_id} dependency version"
    )
    return {"id": dependency_id, "version": version}


def _validate_inventory(
    value: Any,
    *,
    authority: Authority,
    runtime_lock: RuntimeLock,
    lock_sha256: str,
) -> list[dict[str, Any]]:
    root = _exact_object(value, INVENTORY_KEYS, label="runtime package inventory")
    if root.get("contract") != INVENTORY_CONTRACT:
        raise ArtifactValidationError(
            f"runtime package inventory contract must be {INVENTORY_CONTRACT}"
        )
    if root.get("package_plane_lock_sha256") != lock_sha256:
        raise ArtifactValidationError("inventory does not bind the exact package-plane lock")
    if root.get("package_version") != authority.runtime_package_version:
        raise ArtifactValidationError("inventory package_version differs from authority")
    if root.get("runtime_source_commit") != authority.runtime_source_commit:
        raise ArtifactValidationError("inventory runtime_source_commit differs from authority")
    if root.get("package_recipe_commit") != authority.package_recipe_commit:
        raise ArtifactValidationError("inventory package_recipe_commit differs from authority")

    rows = root.get("packages")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_PACKAGE_IDS):
        raise ArtifactValidationError("inventory must contain exactly eight package rows")
    packages: list[dict[str, Any]] = []
    observed_file_names: set[str] = set()
    observed_assemblies: set[str] = set()
    for index, (lock_row, value_row) in enumerate(
        zip(runtime_lock.packages, rows, strict=True)
    ):
        row = _exact_object(
            value_row, PACKAGE_KEYS, label=f"inventory packages[{index}]"
        )
        package_id = _canonical_string(row.get("id"), label=f"packages[{index}].id")
        if package_id != lock_row["id"]:
            raise ArtifactValidationError(
                "inventory package IDs must match the exact ordered Core runtime plane"
            )
        if row.get("version") != authority.runtime_package_version:
            raise ArtifactValidationError(f"package version drift for {package_id}")
        if row.get("repository") != CORE_REPOSITORY:
            raise ArtifactValidationError(f"repository drift for {package_id}")
        if row.get("source_commit") != authority.runtime_source_commit:
            raise ArtifactValidationError(f"source commit drift for {package_id}")
        project = _safe_project_path(row.get("project"), label=f"{package_id} project")
        if project != lock_row["project"]:
            raise ArtifactValidationError(f"project differs from runtime lock for {package_id}")
        assembly = _safe_file_name(
            row.get("assembly"), label=f"{package_id} assembly", pattern=ASSEMBLY_PATTERN
        )
        if assembly.casefold() in observed_assemblies:
            raise ArtifactValidationError("Core runtime assembly ownership is not unique")
        observed_assemblies.add(assembly.casefold())
        if assembly != lock_row["assembly"]:
            raise ArtifactValidationError(f"assembly differs from runtime lock for {package_id}")
        if row.get("target_framework") != "net10.0":
            raise ArtifactValidationError(f"target framework drift for {package_id}")
        if row.get("target_framework") != lock_row["target_framework"]:
            raise ArtifactValidationError(f"target framework differs from runtime lock for {package_id}")
        file_name = _safe_file_name(
            row.get("file_name"),
            label=f"{package_id} file_name",
            pattern=PACKAGE_FILE_PATTERN,
        )
        if file_name.casefold() in observed_file_names:
            raise ArtifactValidationError("package filenames must be case-insensitively unique")
        observed_file_names.add(file_name.casefold())
        expected_file_name = f"{package_id}.{authority.runtime_package_version}.nupkg"
        if file_name != expected_file_name:
            raise ArtifactValidationError(f"package filename differs from runtime lock for {package_id}")
        digest = _sha256_value(row.get("sha256"), label=f"{package_id} sha256")
        size = _positive_size(row.get("size_bytes"), label=f"{package_id} size_bytes")
        dependencies_value = row.get("dependencies")
        if not isinstance(dependencies_value, list):
            raise ArtifactValidationError(f"dependencies must be a list for {package_id}")
        dependencies = [
            _validate_dependency(dependency, package_id=package_id, index=dependency_index)
            for dependency_index, dependency in enumerate(dependencies_value)
        ]
        dependency_ids = [dependency["id"].casefold() for dependency in dependencies]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ArtifactValidationError(f"duplicate dependency id in {package_id}")
        if package_id.casefold() in dependency_ids:
            raise ArtifactValidationError(f"self dependency in {package_id}")
        if dependencies != lock_row["dependencies"]:
            raise ArtifactValidationError(f"dependency graph differs from runtime lock for {package_id}")
        packages.append(
            {
                "id": package_id,
                "version": authority.runtime_package_version,
                "repository": CORE_REPOSITORY,
                "source_commit": authority.runtime_source_commit,
                "project": project,
                "assembly": assembly,
                "target_framework": "net10.0",
                "dependencies": dependencies,
                "file_name": file_name,
                "sha256": digest,
                "size_bytes": size,
            }
        )
    return packages


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _one_xml_text(root: ET.Element, name: str, *, package_id: str) -> str:
    values = [
        (element.text or "").strip()
        for element in root.iter()
        if _xml_local_name(element.tag) == name
    ]
    if len(values) != 1:
        raise ArtifactValidationError(
            f"package {package_id} nuspec must contain exactly one {name}"
        )
    return values[0]


def _inspect_nupkg(payload: bytes, *, package: Mapping[str, Any]) -> None:
    package_id = str(package["id"])
    expected_assembly = f"lib/net10.0/{package['assembly']}"
    expected_nuspec = f"{package_id}.nuspec"
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if names != sorted(names, key=lambda value: (value.casefold(), value)):
                raise ArtifactValidationError(f"package {package_id} archive is not canonical")
            if len(names) != len(set(names)) or len(names) != len(
                set(name.casefold() for name in names)
            ):
                raise ArtifactValidationError(
                    f"package {package_id} archive members are not uniquely named"
                )
            for info in infos:
                path = PurePosixPath(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if (
                    path.is_absolute()
                    or "\\" in info.filename
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or info.is_dir()
                    or stat.S_ISLNK(mode)
                    or info.flag_bits & 0x1
                ):
                    raise ArtifactValidationError(
                        f"package {package_id} archive contains an unsafe member"
                    )
            if names.count(expected_nuspec) != 1:
                raise ArtifactValidationError(
                    f"package {package_id} must contain its one exact nuspec"
                )
            nuspec_info = archive.getinfo(expected_nuspec)
            if nuspec_info.file_size > 2 * 1024 * 1024:
                raise ArtifactValidationError(f"package {package_id} nuspec is oversized")
            nuspec_bytes = archive.read(nuspec_info)
    except ArtifactValidationError:
        raise
    except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
        raise ArtifactValidationError(f"package {package_id} is not a valid nupkg") from exc

    lib_entries = [name for name in names if name.startswith("lib/")]
    if lib_entries != [expected_assembly]:
        raise ArtifactValidationError(
            f"package {package_id} must own exactly {expected_assembly}"
        )
    allowed_entries = {
        "_rels/.rels",
        "[Content_Types].xml",
        expected_nuspec,
        expected_assembly,
    }
    if package_id == "Chummer.Engine.Contracts":
        allowed_entries.add("README.md")
    foreign_entries = {
        name
        for name in names
        if name not in allowed_entries and CORE_PROPERTIES_PATTERN.fullmatch(name) is None
    }
    if foreign_entries:
        raise ArtifactValidationError(
            f"package {package_id} contains foreign payloads: "
            + ", ".join(sorted(foreign_entries))
        )

    try:
        nuspec = ET.fromstring(nuspec_bytes)
    except ET.ParseError as exc:
        raise ArtifactValidationError(f"package {package_id} nuspec is invalid XML") from exc
    if (
        _one_xml_text(nuspec, "id", package_id=package_id) != package_id
        or _one_xml_text(nuspec, "version", package_id=package_id) != package["version"]
    ):
        raise ArtifactValidationError(f"package {package_id} nuspec identity drifted")
    repositories = [
        element for element in nuspec.iter() if _xml_local_name(element.tag) == "repository"
    ]
    if len(repositories) != 1 or (
        (repositories[0].get("url") or "").strip(),
        (repositories[0].get("commit") or "").strip(),
    ) != (package["repository"], package["source_commit"]):
        raise ArtifactValidationError(f"package {package_id} nuspec source authority drifted")
    licenses = [
        element for element in nuspec.iter() if _xml_local_name(element.tag) == "license"
    ]
    if len(licenses) != 1 or (
        (licenses[0].get("type") or "").strip(),
        (licenses[0].text or "").strip(),
    ) != ("expression", LICENSE_EXPRESSION):
        raise ArtifactValidationError(f"package {package_id} nuspec license drifted")

    expected_dependencies = {
        dependency["id"]: dependency["version"] for dependency in package["dependencies"]
    }
    dependency_containers = [
        element for element in nuspec.iter() if _xml_local_name(element.tag) == "dependencies"
    ]
    if len(dependency_containers) != 1:
        raise ArtifactValidationError(
            f"package {package_id} nuspec must contain one dependency container"
        )
    groups = [
        element
        for element in dependency_containers[0]
        if _xml_local_name(element.tag) == "group"
    ]
    if len(groups) != 1 or len(list(dependency_containers[0])) != 1:
        raise ArtifactValidationError(
            f"package {package_id} nuspec must contain one exact dependency group"
        )
    group = groups[0]
    if set(group.attrib) != {"targetFramework"} or group.get("targetFramework") != "net10.0":
        raise ArtifactValidationError(
            f"package {package_id} nuspec dependency framework drifted"
        )
    observed_dependencies: dict[str, str] = {}
    for element in group:
        if _xml_local_name(element.tag) != "dependency" or set(element.attrib) != {
            "id",
            "version",
            "exclude",
        }:
            raise ArtifactValidationError(
                f"package {package_id} nuspec dependency metadata is not exact"
            )
        dependency_id = (element.get("id") or "").strip()
        if dependency_id in observed_dependencies:
            raise ArtifactValidationError(
                f"package {package_id} nuspec repeats a dependency"
            )
        if (element.get("exclude") or "").strip() != "Build,Analyzers":
            raise ArtifactValidationError(
                f"package {package_id} nuspec dependency exclusions drifted"
            )
        observed_dependencies[dependency_id] = (element.get("version") or "").strip()
    if observed_dependencies != expected_dependencies:
        raise ArtifactValidationError(f"package {package_id} nuspec dependencies drifted")


def _validate_owner_row(value: Any, *, label: str) -> dict[str, Any]:
    row = _exact_object(value, OWNER_PACKAGE_KEYS, label=label)
    package_id = _canonical_string(row.get("id"), label=f"{label}.id")
    if PACKAGE_ID_PATTERN.fullmatch(package_id) is None:
        raise ArtifactValidationError(f"invalid owner package id in {label}")
    return {
        "id": package_id,
        "version": _canonical_string(row.get("version"), label=f"{label}.version"),
        "sha256": _sha256_value(row.get("sha256"), label=f"{label}.sha256"),
        "size_bytes": _positive_size(row.get("size_bytes"), label=f"{label}.size_bytes"),
        "role": _canonical_string(row.get("role"), label=f"{label}.role"),
    }


def _valid_utc_timestamp(value: Any) -> str:
    rendered = _canonical_string(value, label="receipt generated_at_utc")
    if UTC_TIMESTAMP_PATTERN.fullmatch(rendered) is None:
        raise ArtifactValidationError("receipt generated_at_utc must be canonical UTC seconds")
    try:
        datetime.strptime(rendered, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ArtifactValidationError("receipt generated_at_utc is not a real timestamp") from exc
    return rendered


def _validate_receipt(
    value: Any,
    *,
    authority: Authority,
    runtime_lock_sha256: str,
    inventory_sha256: str,
    inventory_packages: Sequence[Mapping[str, Any]],
) -> None:
    root = _exact_object(value, RECEIPT_KEYS, label="Core no-siblings v3 receipt")
    if root.get("contract") != RECEIPT_CONTRACT:
        raise ArtifactValidationError(f"receipt contract must be {RECEIPT_CONTRACT}")
    _valid_utc_timestamp(root.get("generated_at_utc"))
    if root.get("status") != "pass":
        raise ArtifactValidationError("Core no-siblings receipt status must be pass")
    for field in PASS_RECEIPT_FIELDS:
        if root.get(field) != "pass":
            raise ArtifactValidationError(f"receipt {field} must be pass")
    if root.get("no_sibling_directories") is not True:
        raise ArtifactValidationError("no_sibling_directories must be true")
    if root.get("isolated_package_cache") is not True:
        raise ArtifactValidationError("isolated_package_cache must be true")
    if root.get("package_source_mapping") != EXPECTED_PACKAGE_SOURCE_MAPPING:
        raise ArtifactValidationError("receipt package_source_mapping differs from policy")
    if root.get("core_commit") != authority.package_recipe_commit:
        raise ArtifactValidationError("receipt core_commit differs from authority")
    if root.get("runtime_source_commit") != authority.runtime_source_commit:
        raise ArtifactValidationError("receipt runtime_source_commit differs from authority")
    if root.get("package_recipe_commit") != authority.package_recipe_commit:
        raise ArtifactValidationError("receipt package_recipe_commit differs from authority")
    if root.get("package_version") != authority.owner_package_version:
        raise ArtifactValidationError("receipt owner package_version differs from authority")
    if root.get("candidate_package_version") != authority.runtime_package_version:
        raise ArtifactValidationError("receipt candidate_package_version differs from authority")
    if root.get("package_plane_lock_sha256") != authority.owner_lock_sha256:
        raise ArtifactValidationError("receipt owner package-plane lock cross-link mismatch")
    if root.get("runtime_package_plane_lock_sha256") != runtime_lock_sha256:
        raise ArtifactValidationError("receipt runtime package-plane lock cross-link mismatch")
    if root.get("package_inventory_sha256") != authority.owner_inventory_sha256:
        raise ArtifactValidationError("receipt owner package inventory cross-link mismatch")
    if (
        root.get("candidate_package_inventory_sha256")
        != authority.candidate_engine_inventory_sha256
    ):
        raise ArtifactValidationError("receipt candidate engine inventory cross-link mismatch")
    if (
        root.get("candidate_runtime_package_inventory_sha256")
        != authority.candidate_runtime_inventory_sha256
    ):
        raise ArtifactValidationError("receipt candidate runtime inventory cross-link mismatch")
    if root.get("runtime_package_inventory_sha256") != inventory_sha256:
        raise ArtifactValidationError("receipt runtime inventory cross-link mismatch")

    locked_values = root.get("locked_packages")
    if not isinstance(locked_values, list) or len(locked_values) != 4:
        raise ArtifactValidationError("receipt locked_packages must contain exactly four rows")
    locked_packages = [
        _validate_owner_row(row, label=f"locked_packages[{index}]")
        for index, row in enumerate(locked_values)
    ]
    expected_locked_packages = [
        {**dict(owner_row), "role": role}
        for owner_row, role in zip(
            authority.owner_packages, LOCKED_OWNER_PACKAGE_ROLES, strict=True
        )
    ]
    if tuple(row["id"] for row in locked_packages) != LOCKED_OWNER_PACKAGE_IDS:
        raise ArtifactValidationError("receipt locked package IDs or order differ from policy")
    if tuple(row["role"] for row in locked_packages) != LOCKED_OWNER_PACKAGE_ROLES:
        raise ArtifactValidationError("receipt locked package roles differ from policy")
    if locked_packages != expected_locked_packages:
        raise ArtifactValidationError(
            "receipt locked package rows differ from exact owner inventory authority"
        )

    resolved = root.get("resolved_owner_contracts")
    if not isinstance(resolved, list) or len(resolved) != 11:
        raise ArtifactValidationError(
            "resolved_owner_contracts must contain eight runtime rows followed by three owner rows"
        )
    for index, (inventory_row, value_row) in enumerate(
        zip(inventory_packages, resolved[:8], strict=True)
    ):
        row = _exact_object(
            value_row,
            RESOLVED_RUNTIME_PACKAGE_KEYS,
            label=f"resolved_owner_contracts[{index}]",
        )
        for key, expected in inventory_row.items():
            if row.get(key) != expected:
                raise ArtifactValidationError(
                    f"resolved runtime row differs from inventory for {inventory_row['id']}"
                )
        if row.get("role") != RESOLVED_RUNTIME_ROLE:
            raise ArtifactValidationError(
                "resolved runtime package role must be current_core_runtime_candidate"
            )

    resolved_owner_rows = [
        _validate_owner_row(row, label=f"resolved_owner_contracts[{index + 8}]")
        for index, row in enumerate(resolved[8:])
    ]
    if resolved_owner_rows != expected_locked_packages[1:]:
        raise ArtifactValidationError(
            "resolved owner rows must be exact Registry/Play/Run locked dependencies"
        )


def validate_artifact(artifact_root: Path, authority_path: Path) -> dict[str, Any]:
    authority = load_authority(authority_path.absolute())
    root_snapshot = _open_directory(
        artifact_root.absolute(), label="artifact root"
    )
    packages_snapshot: DirectorySnapshot | None = None
    expected_root_names = {
        PACKAGES_DIRECTORY_NAME,
        INVENTORY_FILE_NAME,
        LOCK_FILE_NAME,
        RECEIPT_FILE_NAME,
    }
    try:
        _require_exact_directory_names(
            root_snapshot, expected_root_names, label="artifact root"
        )
        packages_snapshot = _open_directory(
            PACKAGES_DIRECTORY_NAME,
            label="packages directory",
            directory_fd=root_snapshot.descriptor,
        )
        _directory_names(packages_snapshot, label="packages directory")

        lock_value, lock_bytes, lock_sha256 = _load_json_file_at(
            root_snapshot.descriptor,
            LOCK_FILE_NAME,
            label="runtime package-plane lock",
            maximum=MAX_LOCK_BYTES,
        )
        if lock_sha256 != authority.runtime_lock_sha256:
            raise ArtifactValidationError(
                "runtime package-plane lock bytes differ from authority"
            )
        runtime_lock = _validate_runtime_lock(lock_value, authority=authority)

        inventory_value, inventory_bytes, inventory_sha256 = _load_json_file_at(
            root_snapshot.descriptor,
            INVENTORY_FILE_NAME,
            label="runtime package inventory",
            maximum=MAX_INVENTORY_BYTES,
        )
        if inventory_sha256 != authority.inventory_sha256:
            raise ArtifactValidationError(
                "runtime package inventory bytes differ from authority"
            )
        inventory_packages = _validate_inventory(
            inventory_value,
            authority=authority,
            runtime_lock=runtime_lock,
            lock_sha256=lock_sha256,
        )

        expected_package_names = {row["file_name"] for row in inventory_packages}
        _require_exact_directory_names(
            packages_snapshot,
            expected_package_names,
            label="packages directory",
        )

        relative_names = [INVENTORY_FILE_NAME, LOCK_FILE_NAME, RECEIPT_FILE_NAME]
        package_results: list[dict[str, Any]] = []
        for row in inventory_packages:
            payload = _stable_file_bytes_at(
                packages_snapshot.descriptor,
                row["file_name"],
                label=f"package {row['id']}",
                maximum=MAX_PACKAGE_BYTES,
            )
            if len(payload) != row["size_bytes"]:
                raise ArtifactValidationError(f"package size mismatch for {row['id']}")
            digest = hashlib.sha256(payload).hexdigest()
            if digest != row["sha256"]:
                raise ArtifactValidationError(f"package digest mismatch for {row['id']}")
            _inspect_nupkg(payload, package=row)
            relative_names.append(f"{PACKAGES_DIRECTORY_NAME}/{row['file_name']}")
            package_results.append(
                {
                    "id": row["id"],
                    "version": row["version"],
                    "file_name": row["file_name"],
                    "sha256": digest,
                    "size_bytes": len(payload),
                }
            )
        folded_names = [name.casefold() for name in relative_names]
        if len(folded_names) != len(set(folded_names)):
            raise ArtifactValidationError(
                "artifact member paths must be case-insensitively unique"
            )
        if len(relative_names) != 11:
            raise ArtifactValidationError(
                "artifact must contain exactly eleven file members"
            )

        receipt_value, receipt_bytes, receipt_sha256 = _load_json_file_at(
            root_snapshot.descriptor,
            RECEIPT_FILE_NAME,
            label="Core no-siblings v3 receipt",
            maximum=MAX_RECEIPT_BYTES,
        )
        if receipt_sha256 != authority.receipt_sha256:
            raise ArtifactValidationError(
                "Core no-siblings receipt bytes differ from authority"
            )
        _validate_receipt(
            receipt_value,
            authority=authority,
            runtime_lock_sha256=lock_sha256,
            inventory_sha256=inventory_sha256,
            inventory_packages=inventory_packages,
        )

        # Re-read every member only after every semantic and receipt check.
        # Directory identity alone cannot detect an in-place mutation between
        # two otherwise stable reads.
        for name, label, maximum, initial_bytes, initial_sha256 in (
            (
                LOCK_FILE_NAME,
                "runtime package-plane lock",
                MAX_LOCK_BYTES,
                lock_bytes,
                lock_sha256,
            ),
            (
                INVENTORY_FILE_NAME,
                "runtime package inventory",
                MAX_INVENTORY_BYTES,
                inventory_bytes,
                inventory_sha256,
            ),
            (
                RECEIPT_FILE_NAME,
                "Core no-siblings v3 receipt",
                MAX_RECEIPT_BYTES,
                receipt_bytes,
                receipt_sha256,
            ),
        ):
            _require_final_file_binding(
                root_snapshot.descriptor,
                name,
                label=label,
                maximum=maximum,
                expected_size=len(initial_bytes),
                expected_sha256=initial_sha256,
            )
        for row in inventory_packages:
            _require_final_file_binding(
                packages_snapshot.descriptor,
                row["file_name"],
                label=f"package {row['id']}",
                maximum=MAX_PACKAGE_BYTES,
                expected_size=row["size_bytes"],
                expected_sha256=row["sha256"],
            )

        # Exact final membership snapshots close addition/removal and
        # directory replacement races after the complete eleven-file reread.
        _require_exact_directory_names(
            packages_snapshot,
            expected_package_names,
            label="packages directory",
        )
        _require_exact_directory_names(
            root_snapshot, expected_root_names, label="artifact root"
        )

        return {
            "contract": VALIDATION_CONTRACT,
            "status": "pass",
            "outer_artifact_selector": dict(authority.artifact_selector),
            "member_count": len(relative_names),
            "package_count": len(package_results),
            "runtime_package_plane_lock": {
                "contract": RUNTIME_LOCK_CONTRACT,
                "sha256": lock_sha256,
            },
            "inventory": {
                "contract": INVENTORY_CONTRACT,
                "file_name": INVENTORY_FILE_NAME,
                "sha256": inventory_sha256,
            },
            "receipt": {
                "contract": RECEIPT_CONTRACT,
                "file_name": RECEIPT_FILE_NAME,
                "sha256": receipt_sha256,
            },
            "runtime_source_commit": authority.runtime_source_commit,
            "package_recipe_commit": authority.package_recipe_commit,
            "owner_package_version": authority.owner_package_version,
            "runtime_package_version": authority.runtime_package_version,
            "owner_authority": {
                "package_plane_lock_sha256": authority.owner_lock_sha256,
                "package_inventory": {
                    "contract": OWNER_INVENTORY_CONTRACT,
                    "sha256": authority.owner_inventory_sha256,
                    "packages": [dict(row) for row in authority.owner_packages],
                },
                "candidate_engine_package_inventory_sha256": (
                    authority.candidate_engine_inventory_sha256
                ),
                "candidate_runtime_package_inventory_sha256": (
                    authority.candidate_runtime_inventory_sha256
                ),
            },
            "ordered_package_ids": list(EXPECTED_PACKAGE_IDS),
            "packages": package_results,
            "checks": {
                "exact_eleven_member_layout": "pass",
                "strict_json_contracts": "pass",
                "runtime_lock_inventory_semantics": "pass",
                "inventory_receipt_cross_links": "pass",
                "owner_inventory_row_authority": "pass",
                "package_byte_bindings": "pass",
                "final_eleven_member_byte_reread": "pass",
                "nupkg_payload_contracts": "pass",
                "contained_regular_files": "pass",
                "stable_directory_snapshots": "pass",
            },
        }
    finally:
        if packages_snapshot is not None:
            os.close(packages_snapshot.descriptor)
        os.close(root_snapshot.descriptor)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    destination = path.absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one extracted Core runtime-package artifact offline."
    )
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.output is not None:
        artifact_root = args.artifact_root.resolve(strict=True)
        output = args.output.resolve(strict=False)
        if output == artifact_root or artifact_root in output.parents:
            raise ArtifactValidationError(
                "validation output must remain outside the immutable artifact root"
            )
    result = validate_artifact(args.artifact_root, args.authority)
    if args.output is not None:
        _atomic_json(args.output, result)
    else:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ArtifactValidationError, OSError, ValueError) as exc:
        print(f"core-package-artifact: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
