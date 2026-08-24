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
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


AUTHORITY_CONTRACT = "chummer-hub.core-runtime-package-artifact-authority/v1"
VALIDATION_CONTRACT = "chummer-hub.core-runtime-package-artifact-validation/v1"
INVENTORY_CONTRACT = "chummer-core.runtime-package-inventory/v1"
RECEIPT_CONTRACT = "chummer-core.no-siblings-package-plane/v3"
CORE_REPOSITORY = "https://github.com/ArchonMegalon/chummer6-core.git"

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
PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
PACKAGE_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.nupkg$")
ASSEMBLY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.dll$")
UTC_TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

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
    candidate_engine_inventory_sha256: str
    candidate_runtime_inventory_sha256: str
    runtime_source_commit: str
    package_recipe_commit: str
    owner_package_version: str
    runtime_package_version: str


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


def _load_json_file(path: Path, *, label: str, maximum: int) -> tuple[Any, bytes, str]:
    payload = _stable_file_bytes(path, label=label, maximum=maximum)
    return _decode_json(payload, label=label), payload, hashlib.sha256(payload).hexdigest()


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
    candidate_engine_inventory_sha256 = _sha256_value(
        root.get("candidate_engine_package_inventory_sha256"),
        label="candidate engine package inventory sha256",
    )
    candidate_runtime_inventory_sha256 = _sha256_value(
        root.get("candidate_runtime_package_inventory_sha256"),
        label="candidate runtime package inventory sha256",
    )
    owner_package_version = _canonical_string(
        root.get("owner_package_version"),
        label="authority owner_package_version",
    )
    runtime_package_version = _canonical_string(
        root.get("runtime_package_version"),
        label="authority runtime_package_version",
    )
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
        candidate_engine_inventory_sha256=candidate_engine_inventory_sha256,
        candidate_runtime_inventory_sha256=candidate_runtime_inventory_sha256,
        runtime_source_commit=runtime_source_commit,
        package_recipe_commit=package_recipe_commit,
        owner_package_version=owner_package_version,
        runtime_package_version=runtime_package_version,
    )


def _validate_artifact_root(root: Path) -> tuple[Path, Path, Path, Path]:
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise ArtifactValidationError("artifact root is unavailable") from exc
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ArtifactValidationError("artifact root must be one non-symlink directory")

    expected_root_names = {
        PACKAGES_DIRECTORY_NAME,
        INVENTORY_FILE_NAME,
        LOCK_FILE_NAME,
        RECEIPT_FILE_NAME,
    }
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise ArtifactValidationError("unable to enumerate artifact root") from exc
    observed_names = {entry.name for entry in entries}
    if len(entries) != len(observed_names):
        raise ArtifactValidationError("artifact root contains duplicate member names")
    if observed_names != expected_root_names:
        missing = sorted(expected_root_names - observed_names)
        foreign = sorted(observed_names - expected_root_names)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if foreign:
            details.append("foreign=" + ",".join(foreign))
        raise ArtifactValidationError(
            "artifact root must contain the exact layout (" + "; ".join(details) + ")"
        )

    packages = root / PACKAGES_DIRECTORY_NAME
    packages_metadata = packages.lstat()
    if not stat.S_ISDIR(packages_metadata.st_mode) or stat.S_ISLNK(packages_metadata.st_mode):
        raise ArtifactValidationError("packages must be one non-symlink directory")
    return (
        packages,
        root / INVENTORY_FILE_NAME,
        root / LOCK_FILE_NAME,
        root / RECEIPT_FILE_NAME,
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
    for index, (expected_id, value_row) in enumerate(
        zip(EXPECTED_PACKAGE_IDS, rows, strict=True)
    ):
        row = _exact_object(
            value_row, PACKAGE_KEYS, label=f"inventory packages[{index}]"
        )
        package_id = _canonical_string(row.get("id"), label=f"packages[{index}].id")
        if package_id != expected_id:
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
        assembly = _safe_file_name(
            row.get("assembly"), label=f"{package_id} assembly", pattern=ASSEMBLY_PATTERN
        )
        if assembly.casefold() in observed_assemblies:
            raise ArtifactValidationError("Core runtime assembly ownership is not unique")
        observed_assemblies.add(assembly.casefold())
        if row.get("target_framework") != "net10.0":
            raise ArtifactValidationError(f"target framework drift for {package_id}")
        file_name = _safe_file_name(
            row.get("file_name"),
            label=f"{package_id} file_name",
            pattern=PACKAGE_FILE_PATTERN,
        )
        if file_name.casefold() in observed_file_names:
            raise ArtifactValidationError("package filenames must be case-insensitively unique")
        observed_file_names.add(file_name.casefold())
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
    if tuple(row["id"] for row in locked_packages) != LOCKED_OWNER_PACKAGE_IDS:
        raise ArtifactValidationError("receipt locked package IDs or order differ from policy")
    if tuple(row["role"] for row in locked_packages) != LOCKED_OWNER_PACKAGE_ROLES:
        raise ArtifactValidationError("receipt locked package roles differ from policy")

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
    if resolved_owner_rows != locked_packages[1:]:
        raise ArtifactValidationError(
            "resolved owner rows must be exact Registry/Play/Run locked dependencies"
        )


def validate_artifact(artifact_root: Path, authority_path: Path) -> dict[str, Any]:
    authority = load_authority(authority_path.absolute())
    root = artifact_root.absolute()
    packages_root, inventory_path, lock_path, receipt_path = _validate_artifact_root(root)

    lock_value, _lock_bytes, lock_sha256 = _load_json_file(
        lock_path, label="runtime package-plane lock", maximum=MAX_LOCK_BYTES
    )
    if lock_sha256 != authority.runtime_lock_sha256:
        raise ArtifactValidationError("runtime package-plane lock bytes differ from authority")
    if not isinstance(lock_value, dict):
        raise ArtifactValidationError("runtime package-plane lock must be a JSON object")
    if lock_value.get("contract") != authority.runtime_lock_contract:
        raise ArtifactValidationError("runtime package-plane lock contract differs from authority")

    inventory_value, _inventory_bytes, inventory_sha256 = _load_json_file(
        inventory_path, label="runtime package inventory", maximum=MAX_INVENTORY_BYTES
    )
    if inventory_sha256 != authority.inventory_sha256:
        raise ArtifactValidationError("runtime package inventory bytes differ from authority")
    inventory_packages = _validate_inventory(
        inventory_value, authority=authority, lock_sha256=lock_sha256
    )

    try:
        package_entries = list(packages_root.iterdir())
    except OSError as exc:
        raise ArtifactValidationError("unable to enumerate packages directory") from exc
    expected_package_names = {row["file_name"] for row in inventory_packages}
    observed_package_names = {entry.name for entry in package_entries}
    if len(package_entries) != len(observed_package_names):
        raise ArtifactValidationError("packages directory contains duplicate member names")
    if observed_package_names != expected_package_names:
        missing = sorted(expected_package_names - observed_package_names)
        foreign = sorted(observed_package_names - expected_package_names)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if foreign:
            details.append("foreign=" + ",".join(foreign))
        raise ArtifactValidationError(
            "packages directory must contain the exact inventory set ("
            + "; ".join(details)
            + ")"
        )

    relative_names = [INVENTORY_FILE_NAME, LOCK_FILE_NAME, RECEIPT_FILE_NAME]
    package_results: list[dict[str, Any]] = []
    for row in inventory_packages:
        path = packages_root / row["file_name"]
        payload = _stable_file_bytes(
            path, label=f"package {row['id']}", maximum=MAX_PACKAGE_BYTES
        )
        if len(payload) != row["size_bytes"]:
            raise ArtifactValidationError(f"package size mismatch for {row['id']}")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != row["sha256"]:
            raise ArtifactValidationError(f"package digest mismatch for {row['id']}")
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
        raise ArtifactValidationError("artifact member paths must be case-insensitively unique")
    if len(relative_names) != 11:
        raise ArtifactValidationError("artifact must contain exactly eleven file members")

    receipt_value, _receipt_bytes, receipt_sha256 = _load_json_file(
        receipt_path, label="Core no-siblings v3 receipt", maximum=MAX_RECEIPT_BYTES
    )
    if receipt_sha256 != authority.receipt_sha256:
        raise ArtifactValidationError("Core no-siblings receipt bytes differ from authority")
    _validate_receipt(
        receipt_value,
        authority=authority,
        runtime_lock_sha256=lock_sha256,
        inventory_sha256=inventory_sha256,
        inventory_packages=inventory_packages,
    )

    return {
        "contract": VALIDATION_CONTRACT,
        "status": "pass",
        "outer_artifact_selector": dict(authority.artifact_selector),
        "member_count": len(relative_names),
        "package_count": len(package_results),
        "runtime_package_plane_lock": {
            "contract": authority.runtime_lock_contract,
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
            "package_inventory_sha256": authority.owner_inventory_sha256,
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
            "inventory_receipt_cross_links": "pass",
            "package_byte_bindings": "pass",
            "contained_regular_files": "pass",
        },
    }


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
