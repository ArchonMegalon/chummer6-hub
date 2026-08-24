#!/usr/bin/env python3
"""Build Hub's exact package plane from one public Core handoff and owner commits.

Core packages are copied byte-for-byte from a digest-bound public release
bundle; they are never rebuilt by Hub. Registry and Hub-owned packages are
built from clean, detached checkouts. A nupkg with valid metadata is not
trusted unless its bytes match the reviewed v5 lock.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


LOCK_CONTRACT = "chummer-hub.package-plane-lock/v5"
INVENTORY_CONTRACT = "chummer-hub.package-inventory/v4"
INVENTORY_FILE_NAME = "chummer-hub-packages.inventory.json"
OBSERVED_AUTHORITY_FILE_NAME = "chummer-hub-packages.observed-authority.json"
SEALED_LOCK_STATE = "sealed"
PENDING_LOCK_STATE = "awaiting-pinned-ci-byte-authority"
CORE_SOURCE_KIND = "core_public_bundle"
BUILD_SOURCE_KIND = "source_build"
CORE_PACKAGE_VERSION = "0.0.0-packageplane.candidate.shabc08228d3ce0"
OWNER_PACKAGE_VERSION = "0.0.0-packageplane.20260721.1"
EXPECTED_PACKAGE_IDS = (
    "Chummer.Engine.Contracts",
    "Chummer.Application",
    "Chummer.Rulesets.Hosting",
    "Chummer.Rulesets.Sr5",
    "Chummer.Rulesets.Sr6",
    "Chummer.Infrastructure",
    "Chummer.Rulesets.Sr4",
    "Chummer.Engine.GmCharacterEdits",
    "Chummer.Hub.Registry.Contracts",
    "Chummer.Run.Registry",
    "Chummer.Play.Contracts",
    "Chummer.Run.Contracts",
    "Chummer.Campaign.Contracts",
    "Chummer.Control.Contracts",
    "Chummer.World.Contracts",
)
EXPECTED_INTERNAL_DEPENDENCIES = {
    "Chummer.Engine.Contracts": (),
    "Chummer.Application": (
        "Chummer.Engine.Contracts",
        "Chummer.Hub.Registry.Contracts",
        "Chummer.Run.Contracts",
    ),
    "Chummer.Rulesets.Hosting": (
        "Chummer.Application",
        "Chummer.Engine.Contracts",
        "Chummer.Run.Contracts",
    ),
    "Chummer.Rulesets.Sr5": (
        "Chummer.Application",
        "Chummer.Engine.Contracts",
        "Chummer.Run.Contracts",
    ),
    "Chummer.Rulesets.Sr6": (
        "Chummer.Application",
        "Chummer.Engine.Contracts",
        "Chummer.Run.Contracts",
    ),
    "Chummer.Infrastructure": (
        "Chummer.Application",
        "Chummer.Engine.Contracts",
        "Chummer.Hub.Registry.Contracts",
        "Chummer.Rulesets.Hosting",
        "Chummer.Rulesets.Sr5",
        "Chummer.Rulesets.Sr6",
        "Chummer.Run.Contracts",
    ),
    "Chummer.Rulesets.Sr4": (
        "Chummer.Application",
        "Chummer.Engine.Contracts",
        "Chummer.Infrastructure",
        "Chummer.Run.Contracts",
    ),
    "Chummer.Engine.GmCharacterEdits": (
        "Chummer.Application",
        "Chummer.Engine.Contracts",
        "Chummer.Hub.Registry.Contracts",
        "Chummer.Infrastructure",
        "Chummer.Rulesets.Hosting",
        "Chummer.Rulesets.Sr5",
        "Chummer.Rulesets.Sr6",
        "Chummer.Run.Contracts",
    ),
    "Chummer.Hub.Registry.Contracts": (),
    "Chummer.Run.Registry": ("Chummer.Hub.Registry.Contracts",),
    "Chummer.Play.Contracts": (),
    "Chummer.Run.Contracts": (
        "Chummer.Engine.Contracts",
        "Chummer.Hub.Registry.Contracts",
        "Chummer.Play.Contracts",
    ),
    "Chummer.Campaign.Contracts": ("Chummer.Engine.Contracts",),
    "Chummer.Control.Contracts": (),
    "Chummer.World.Contracts": (),
}
EXPECTED_PACKAGE_AUTHORITIES = {
    "Chummer.Engine.Contracts": {
        "repository": "https://github.com/ArchonMegalon/chummer6-core.git",
        "checkout_directory": "chummer-core-engine",
        "project": "Chummer.Contracts/Chummer.Contracts.csproj",
        "license_type": "expression",
        "license_value": "GPL-3.0-only",
        "license_sha256": None,
    },
    "Chummer.Application": {
        "repository": "https://github.com/ArchonMegalon/chummer6-core.git",
        "checkout_directory": "chummer-core-engine",
        "project": "Chummer.Application/Chummer.Application.csproj",
        "license_type": "expression",
        "license_value": "GPL-3.0-only",
        "license_sha256": None,
    },
    "Chummer.Rulesets.Hosting": {
        "repository": "https://github.com/ArchonMegalon/chummer6-core.git",
        "checkout_directory": "chummer-core-engine",
        "project": "Chummer.Rulesets.Hosting/Chummer.Rulesets.Hosting.csproj",
        "license_type": "expression",
        "license_value": "GPL-3.0-only",
        "license_sha256": None,
    },
    "Chummer.Rulesets.Sr5": {
        "repository": "https://github.com/ArchonMegalon/chummer6-core.git",
        "checkout_directory": "chummer-core-engine",
        "project": "Chummer.Rulesets.Sr5/Chummer.Rulesets.Sr5.csproj",
        "license_type": "expression",
        "license_value": "GPL-3.0-only",
        "license_sha256": None,
    },
    "Chummer.Rulesets.Sr6": {
        "repository": "https://github.com/ArchonMegalon/chummer6-core.git",
        "checkout_directory": "chummer-core-engine",
        "project": "Chummer.Rulesets.Sr6/Chummer.Rulesets.Sr6.csproj",
        "license_type": "expression",
        "license_value": "GPL-3.0-only",
        "license_sha256": None,
    },
    "Chummer.Infrastructure": {
        "repository": "https://github.com/ArchonMegalon/chummer6-core.git",
        "checkout_directory": "chummer-core-engine",
        "project": "Chummer.Infrastructure/Chummer.Infrastructure.csproj",
        "license_type": "expression",
        "license_value": "GPL-3.0-only",
        "license_sha256": None,
    },
    "Chummer.Rulesets.Sr4": {
        "repository": "https://github.com/ArchonMegalon/chummer6-core.git",
        "checkout_directory": "chummer-core-engine",
        "project": "Chummer.Rulesets.Sr4/Chummer.Rulesets.Sr4.csproj",
        "license_type": "expression",
        "license_value": "GPL-3.0-only",
        "license_sha256": None,
    },
    "Chummer.Engine.GmCharacterEdits": {
        "repository": "https://github.com/ArchonMegalon/chummer6-core.git",
        "checkout_directory": "chummer-core-engine",
        "project": "Chummer.GmCharacterEdits/Chummer.GmCharacterEdits.csproj",
        "license_type": "expression",
        "license_value": "GPL-3.0-only",
        "license_sha256": None,
    },
    "Chummer.Hub.Registry.Contracts": {
        "repository": "https://github.com/ArchonMegalon/chummer6-hub-registry.git",
        "checkout_directory": "chummer-hub-registry",
        "project": "Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj",
        "license_type": "file",
        "license_value": "LICENSE",
        "license_sha256": (
            "2ecaed15e0f77335d19138e3a98b82779714a4483c45d356a75053f9d33de0e4"
        ),
    },
    "Chummer.Run.Registry": {
        "repository": "https://github.com/ArchonMegalon/chummer6-hub-registry.git",
        "checkout_directory": "chummer-hub-registry",
        "project": "Chummer.Run.Registry/Chummer.Run.Registry.csproj",
        "license_type": "file",
        "license_value": "LICENSE",
        "license_sha256": (
            "2ecaed15e0f77335d19138e3a98b82779714a4483c45d356a75053f9d33de0e4"
        ),
    },
    "Chummer.Play.Contracts": {
        "repository": "https://github.com/ArchonMegalon/chummer6-hub.git",
        "checkout_directory": "chummer-run-services",
        "project": "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj",
        "license_type": "file",
        "license_value": "LICENSE",
        "license_sha256": (
            "2ecaed15e0f77335d19138e3a98b82779714a4483c45d356a75053f9d33de0e4"
        ),
    },
    "Chummer.Run.Contracts": {
        "repository": "https://github.com/ArchonMegalon/chummer6-hub.git",
        "checkout_directory": "chummer-run-services",
        "project": "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj",
        "license_type": "file",
        "license_value": "LICENSE",
        "license_sha256": (
            "2ecaed15e0f77335d19138e3a98b82779714a4483c45d356a75053f9d33de0e4"
        ),
    },
    "Chummer.Campaign.Contracts": {
        "repository": "https://github.com/ArchonMegalon/chummer6-hub.git",
        "checkout_directory": "chummer-run-services",
        "project": "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj",
        "license_type": "file",
        "license_value": "LICENSE",
        "license_sha256": (
            "2ecaed15e0f77335d19138e3a98b82779714a4483c45d356a75053f9d33de0e4"
        ),
    },
    "Chummer.Control.Contracts": {
        "repository": "https://github.com/ArchonMegalon/chummer6-hub.git",
        "checkout_directory": "chummer-run-services",
        "project": "Chummer.Control.Contracts/Chummer.Control.Contracts.csproj",
        "license_type": "file",
        "license_value": "LICENSE",
        "license_sha256": (
            "2ecaed15e0f77335d19138e3a98b82779714a4483c45d356a75053f9d33de0e4"
        ),
    },
    "Chummer.World.Contracts": {
        "repository": "https://github.com/ArchonMegalon/chummer6-hub.git",
        "checkout_directory": "chummer-run-services",
        "project": "Chummer.World.Contracts/Chummer.World.Contracts.csproj",
        "license_type": "file",
        "license_value": "LICENSE",
        "license_sha256": (
            "2ecaed15e0f77335d19138e3a98b82779714a4483c45d356a75053f9d33de0e4"
        ),
    },
}
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VERSION_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
HTTPS_GITHUB_PATTERN = re.compile(
    r"^https://github\.com/ArchonMegalon/[A-Za-z0-9._-]+\.git$"
)
CORE_PROPERTIES_PATTERN = re.compile(
    r"^package/services/metadata/core-properties/(?:[0-9a-f]{32}|[0-9a-f]{64})\.psmdcp$"
)
CORE_PROPERTIES_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/"
    "core-properties"
)
MANIFEST_RELATIONSHIP = "http://schemas.microsoft.com/packaging/2010/07/manifest"
RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
CANONICAL_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
CANONICAL_ZIP_EXTERNAL_ATTR = 0o100644 << 16
GM_RUNTIME_ASSEMBLIES = (
    "Chummer.Application",
    "Chummer.Engine.GmCharacterEdits",
    "Chummer.Infrastructure",
    "Chummer.Rulesets.Hosting",
    "Chummer.Rulesets.Sr5",
    "Chummer.Rulesets.Sr6",
)


class PackagePlaneError(RuntimeError):
    """Raised when immutable package-plane authority cannot be proven."""


@dataclass(frozen=True)
class PackageSpec:
    package_id: str
    version: str
    repository: str
    commit: str
    checkout_directory: str
    project: str
    license_type: str
    license_value: str
    license_sha256: str | None
    nupkg_sha256: str | None
    nupkg_size_bytes: int | None
    source_kind: str = BUILD_SOURCE_KIND
    bundle_member: str | None = None
    byte_authority_status: str = "locked"


@dataclass(frozen=True)
class CorePublicBundle:
    asset_url: str
    asset_name: str
    release_tag: str
    release_commit: str
    source_commit: str
    receipt_asset_url: str
    receipt_sha256: str
    receipt_size_bytes: int
    sha256: str
    size_bytes: int
    member_count: int
    uncompressed_size_bytes: int
    runtime_lock_sha256: str
    runtime_inventory_sha256: str
    no_siblings_receipt_sha256: str


@dataclass(frozen=True)
class PackagePlaneLock:
    state: str
    dotnet_sdk: str
    dotnet_install_url: str
    dotnet_install_sha256: str
    toolchain_sha256: Mapping[str, str]
    package_version: str
    approved_remote_source: str
    build_recipe_path: str
    build_recipe_sha256: str
    core_public_bundle: CorePublicBundle
    dependency_graph: Mapping[str, tuple[tuple[str, str], ...]]
    packages: tuple[PackageSpec, ...]


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PackagePlaneError(f"{key} must be a non-empty canonical string")
    return value


def _safe_relative_path(raw: str, label: str) -> str:
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in raw
    ):
        raise PackagePlaneError(f"{label} must be a contained POSIX relative path")
    return raw


def validate_lock_payload(payload: Any) -> PackagePlaneLock:
    expected_top_level = {
        "contract",
        "state",
        "dotnet_sdk",
        "dotnet_install",
        "toolchain_sha256",
        "package_version",
        "approved_remote_source",
        "build_recipe",
        "core_public_bundle",
        "dependency_graph",
        "packages",
    }
    if not isinstance(payload, dict) or set(payload) != expected_top_level:
        raise PackagePlaneError("package-plane lock must contain the exact v5 fields")
    if payload.get("contract") != LOCK_CONTRACT:
        raise PackagePlaneError(f"package-plane lock contract must be {LOCK_CONTRACT}")
    state = _required_string(payload, "state")
    if state not in {SEALED_LOCK_STATE, PENDING_LOCK_STATE}:
        raise PackagePlaneError("package-plane lock state is not recognized")
    dotnet_sdk = _required_string(payload, "dotnet_sdk")
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", dotnet_sdk) is None:
        raise PackagePlaneError("dotnet_sdk must be an exact three-part version")
    dotnet_install = payload.get("dotnet_install")
    if not isinstance(dotnet_install, dict) or set(dotnet_install) != {"url", "sha256"}:
        raise PackagePlaneError("dotnet_install must contain exact url/sha256 fields")
    dotnet_install_url = _required_string(dotnet_install, "url")
    dotnet_install_sha256 = _required_string(dotnet_install, "sha256")
    if dotnet_install_url != "https://dot.net/v1/dotnet-install.sh":
        raise PackagePlaneError("dotnet installer URL must be the approved HTTPS endpoint")
    if SHA256_PATTERN.fullmatch(dotnet_install_sha256) is None:
        raise PackagePlaneError("dotnet installer SHA256 must be canonical")

    toolchain = payload.get("toolchain_sha256")
    expected_toolchain_keys = {
        "dotnet_host",
        "csc",
        "msbuild",
        "nuget_packaging",
    }
    if not isinstance(toolchain, dict) or set(toolchain) != expected_toolchain_keys:
        raise PackagePlaneError("toolchain_sha256 must contain the exact tool set")
    toolchain_sha256 = {
        key: _required_string(toolchain, key) for key in sorted(expected_toolchain_keys)
    }
    if any(SHA256_PATTERN.fullmatch(value) is None for value in toolchain_sha256.values()):
        raise PackagePlaneError("toolchain SHA256 values must be canonical")

    package_version = _required_string(payload, "package_version")
    if VERSION_PATTERN.fullmatch(package_version) is None:
        raise PackagePlaneError("package_version must be one exact SemVer value")
    if package_version != OWNER_PACKAGE_VERSION:
        raise PackagePlaneError(
            f"package_version must be the Core owner dependency version {OWNER_PACKAGE_VERSION}"
        )
    approved_remote_source = _required_string(payload, "approved_remote_source")
    if approved_remote_source != "https://api.nuget.org/v3/index.json":
        raise PackagePlaneError("approved_remote_source must be the HTTPS NuGet.org v3 index")

    build_recipe = payload.get("build_recipe")
    if not isinstance(build_recipe, dict) or set(build_recipe) != {"path", "sha256"}:
        raise PackagePlaneError("build_recipe must contain exact path/sha256 fields")
    build_recipe_path = _safe_relative_path(
        _required_string(build_recipe, "path"), "build_recipe.path"
    )
    if build_recipe_path != "scripts/ai/bootstrap-hub-package-feed.py":
        raise PackagePlaneError("build_recipe.path must name the package bootstrap")
    build_recipe_sha256 = _required_string(build_recipe, "sha256")
    if SHA256_PATTERN.fullmatch(build_recipe_sha256) is None:
        raise PackagePlaneError("build recipe SHA256 must be canonical")

    bundle = payload.get("core_public_bundle")
    expected_bundle_keys = {
        "asset_url",
        "asset_name",
        "release_tag",
        "release_commit",
        "source_commit",
        "receipt_asset_url",
        "receipt_sha256",
        "receipt_size_bytes",
        "sha256",
        "size_bytes",
        "member_count",
        "uncompressed_size_bytes",
        "runtime_lock_sha256",
        "runtime_inventory_sha256",
        "no_siblings_receipt_sha256",
    }
    if not isinstance(bundle, dict) or set(bundle) != expected_bundle_keys:
        raise PackagePlaneError("core_public_bundle must contain the exact v5 fields")
    bundle_strings = {
        key: _required_string(bundle, key)
        for key in expected_bundle_keys
        if key not in {
            "size_bytes",
            "receipt_size_bytes",
            "member_count",
            "uncompressed_size_bytes",
        }
    }
    expected_release_prefix = (
        "https://github.com/ArchonMegalon/chummer6-core/releases/download/"
    )
    if not bundle_strings["asset_url"].startswith(expected_release_prefix):
        raise PackagePlaneError("Core bundle must use the approved immutable release path")
    if not bundle_strings["receipt_asset_url"].startswith(expected_release_prefix):
        raise PackagePlaneError("Core receipt must use the approved immutable release path")
    if PurePosixPath(bundle_strings["asset_url"]).name != bundle_strings["asset_name"]:
        raise PackagePlaneError("Core bundle asset name does not match its URL")
    if not SHA_PATTERN.fullmatch(bundle_strings["release_commit"]):
        raise PackagePlaneError("Core release commit must be an exact lowercase SHA")
    if not SHA_PATTERN.fullmatch(bundle_strings["source_commit"]):
        raise PackagePlaneError("Core source commit must be an exact lowercase SHA")
    if bundle_strings["release_tag"] != (
        "core-runtime-package-plane-" + bundle_strings["release_commit"]
    ):
        raise PackagePlaneError("Core release tag must bind the exact release commit")
    expected_release_base = expected_release_prefix + bundle_strings["release_tag"] + "/"
    if bundle_strings["asset_url"] != (
        expected_release_base + bundle_strings["asset_name"]
    ):
        raise PackagePlaneError("Core asset URL does not bind the exact release tag")
    expected_receipt_name = (
        "chummer-core-runtime-package-plane-"
        + bundle_strings["release_commit"]
        + ".public-handoff.json"
    )
    if bundle_strings["receipt_asset_url"] != expected_release_base + expected_receipt_name:
        raise PackagePlaneError("Core receipt URL does not bind the exact release tag")
    for key in (
        "receipt_sha256",
        "sha256",
        "runtime_lock_sha256",
        "runtime_inventory_sha256",
        "no_siblings_receipt_sha256",
    ):
        if SHA256_PATTERN.fullmatch(bundle_strings[key]) is None:
            raise PackagePlaneError(f"Core bundle {key} must be canonical")
    for key in (
        "size_bytes",
        "receipt_size_bytes",
        "member_count",
        "uncompressed_size_bytes",
    ):
        value = bundle.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise PackagePlaneError(f"Core bundle {key} must be a positive integer")
    core_public_bundle = CorePublicBundle(
        asset_url=bundle_strings["asset_url"],
        asset_name=bundle_strings["asset_name"],
        release_tag=bundle_strings["release_tag"],
        release_commit=bundle_strings["release_commit"],
        source_commit=bundle_strings["source_commit"],
        receipt_asset_url=bundle_strings["receipt_asset_url"],
        receipt_sha256=bundle_strings["receipt_sha256"],
        receipt_size_bytes=bundle["receipt_size_bytes"],
        sha256=bundle_strings["sha256"],
        size_bytes=bundle["size_bytes"],
        member_count=bundle["member_count"],
        uncompressed_size_bytes=bundle["uncompressed_size_bytes"],
        runtime_lock_sha256=bundle_strings["runtime_lock_sha256"],
        runtime_inventory_sha256=bundle_strings["runtime_inventory_sha256"],
        no_siblings_receipt_sha256=bundle_strings["no_siblings_receipt_sha256"],
    )

    rows = payload.get("packages")
    if not isinstance(rows, list):
        raise PackagePlaneError("packages must be a list")
    packages: list[PackageSpec] = []
    checkout_authority: dict[str, tuple[str, str]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PackagePlaneError(f"packages[{index}] must be an object")
        package_id = _required_string(row, "id")
        expected_authority = EXPECTED_PACKAGE_AUTHORITIES.get(package_id)
        if expected_authority is None:
            raise PackagePlaneError(f"unapproved package id: {package_id}")
        expected_row_keys = {
            "id",
            "version",
            "repository",
            "commit",
            "checkout_directory",
            "project",
            "license_type",
            "license_value",
            "source_kind",
            "bundle_member",
            "byte_authority_status",
            "nupkg_sha256",
            "nupkg_size_bytes",
        }
        if expected_authority["license_type"] == "file":
            expected_row_keys.add("license_sha256")
        if set(row) != expected_row_keys:
            raise PackagePlaneError(f"packages[{index}] must contain the exact fields")
        repository = _required_string(row, "repository")
        version = _required_string(row, "version")
        commit = _required_string(row, "commit")
        checkout_directory = _safe_relative_path(
            _required_string(row, "checkout_directory"),
            f"packages[{index}].checkout_directory",
        )
        project = _safe_relative_path(
            _required_string(row, "project"), f"packages[{index}].project"
        )
        license_type = _required_string(row, "license_type")
        license_value = _required_string(row, "license_value")
        license_sha256 = row.get("license_sha256")
        source_kind = _required_string(row, "source_kind")
        bundle_member = row.get("bundle_member")
        byte_authority_status = _required_string(row, "byte_authority_status")
        nupkg_sha256 = row.get("nupkg_sha256")
        nupkg_size_bytes = row.get("nupkg_size_bytes")
        if not HTTPS_GITHUB_PATTERN.fullmatch(repository):
            raise PackagePlaneError("repository must be an allowlisted HTTPS GitHub URL")
        if VERSION_PATTERN.fullmatch(version) is None:
            raise PackagePlaneError(f"invalid package version for {package_id}")
        if not SHA_PATTERN.fullmatch(commit):
            raise PackagePlaneError("commit must be an exact lowercase 40-character SHA")
        if "/" in checkout_directory:
            raise PackagePlaneError("checkout_directory must be one directory name")
        if license_type not in {"expression", "file"}:
            raise PackagePlaneError("license_type must be expression or file")
        if license_type == "file":
            if not isinstance(license_sha256, str) or not SHA256_PATTERN.fullmatch(
                license_sha256
            ):
                raise PackagePlaneError("file licenses require an exact SHA256")
        elif license_sha256 is not None:
            raise PackagePlaneError("expression licenses must not declare license_sha256")
        observed_authority = {
            "repository": repository,
            "checkout_directory": checkout_directory,
            "project": project,
            "license_type": license_type,
            "license_value": license_value,
            "license_sha256": license_sha256,
        }
        if observed_authority != expected_authority:
            raise PackagePlaneError(f"immutable authority mismatch for {package_id}")
        is_core = package_id in EXPECTED_PACKAGE_IDS[:8]
        expected_source_kind = CORE_SOURCE_KIND if is_core else BUILD_SOURCE_KIND
        if source_kind != expected_source_kind:
            raise PackagePlaneError(f"source kind mismatch for {package_id}")
        if is_core:
            expected_member = f"packages/{package_id}.{version}.nupkg"
            if bundle_member != expected_member:
                raise PackagePlaneError(f"Core bundle member mismatch for {package_id}")
            if repository != "https://github.com/ArchonMegalon/chummer6-core.git":
                raise PackagePlaneError(f"Core repository mismatch for {package_id}")
            if commit != core_public_bundle.source_commit:
                raise PackagePlaneError(f"Core source commit mismatch for {package_id}")
            if version != CORE_PACKAGE_VERSION:
                raise PackagePlaneError(f"Core package version mismatch for {package_id}")
        elif bundle_member is not None:
            raise PackagePlaneError(f"source-built package cannot name a bundle member: {package_id}")
        if not is_core and version != OWNER_PACKAGE_VERSION:
            raise PackagePlaneError(f"owner package version mismatch for {package_id}")
        if byte_authority_status == "locked":
            if not isinstance(nupkg_sha256, str) or SHA256_PATTERN.fullmatch(nupkg_sha256) is None:
                raise PackagePlaneError(f"invalid nupkg SHA256 for {package_id}")
            if (
                not isinstance(nupkg_size_bytes, int)
                or isinstance(nupkg_size_bytes, bool)
                or nupkg_size_bytes <= 0
            ):
                raise PackagePlaneError(f"invalid nupkg size for {package_id}")
        elif byte_authority_status == "pending_pinned_ci":
            if is_core:
                raise PackagePlaneError("Core public-bundle bytes may never be pending")
            if nupkg_sha256 is not None or nupkg_size_bytes is not None:
                raise PackagePlaneError(
                    f"pending byte authority must not carry placeholder bytes: {package_id}"
                )
        else:
            raise PackagePlaneError(f"unknown byte authority status for {package_id}")
        authority = checkout_authority.setdefault(
            checkout_directory, (repository, commit)
        )
        if authority != (repository, commit):
            raise PackagePlaneError(
                "one checkout_directory cannot name multiple source authorities"
            )
        packages.append(
            PackageSpec(
                package_id=package_id,
                version=version,
                repository=repository,
                commit=commit,
                checkout_directory=checkout_directory,
                project=project,
                license_type=license_type,
                license_value=license_value,
                license_sha256=license_sha256,
                nupkg_sha256=nupkg_sha256,
                nupkg_size_bytes=nupkg_size_bytes,
                source_kind=source_kind,
                bundle_member=bundle_member,
                byte_authority_status=byte_authority_status,
            )
        )
    ids = tuple(spec.package_id for spec in packages)
    if ids != EXPECTED_PACKAGE_IDS:
        raise PackagePlaneError(
            "packages must contain the exact ordered Hub package plane: "
            + ", ".join(EXPECTED_PACKAGE_IDS)
        )
    pending = tuple(
        spec.package_id
        for spec in packages
        if spec.byte_authority_status == "pending_pinned_ci"
    )
    if state == SEALED_LOCK_STATE and pending:
        raise PackagePlaneError("sealed v5 lock cannot contain pending package bytes")
    expected_pending = EXPECTED_PACKAGE_IDS[8:]
    if state == PENDING_LOCK_STATE and pending != expected_pending:
        raise PackagePlaneError(
            "pending v5 lock must leave the exact seven source-built packages "
            "to pinned CI byte authority"
        )
    versions = {spec.package_id: spec.version for spec in packages}
    expected_dependency_graph = {
        package_id: [
            {"id": dependency_id, "version": versions[dependency_id]}
            for dependency_id in EXPECTED_INTERNAL_DEPENDENCIES[package_id]
        ]
        for package_id in EXPECTED_PACKAGE_IDS
    }
    if payload.get("dependency_graph") != expected_dependency_graph:
        raise PackagePlaneError("v5 dependency_graph does not match the exact 15-package graph")
    dependency_graph = {
        package_id: tuple(
            (row["id"], row["version"])
            for row in expected_dependency_graph[package_id]
        )
        for package_id in EXPECTED_PACKAGE_IDS
    }
    return PackagePlaneLock(
        state,
        dotnet_sdk,
        dotnet_install_url,
        dotnet_install_sha256,
        toolchain_sha256,
        package_version,
        approved_remote_source,
        build_recipe_path,
        build_recipe_sha256,
        core_public_bundle,
        dependency_graph,
        tuple(packages),
    )


def load_lock(path: Path, *, allow_pending: bool = True) -> PackagePlaneLock:
    try:
        lock = validate_lock_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagePlaneError(f"unable to read package-plane lock {path}: {exc}") from exc
    if lock.state != SEALED_LOCK_STATE and not allow_pending:
        raise PackagePlaneError(
            "package-plane v5 is not sealed; run the pinned CI byte-authority lane"
        )
    return lock


def validate_build_recipe(repo_root: Path, lock: PackagePlaneLock) -> None:
    repo_root = repo_root.resolve()
    recipe = repo_root / lock.build_recipe_path
    if (
        recipe.is_symlink()
        or not recipe.is_file()
        or recipe.resolve().parent != (repo_root / "scripts/ai").resolve()
        or _sha256(recipe) != lock.build_recipe_sha256
    ):
        raise PackagePlaneError("package build recipe does not match the authority lock")


def _run(
    command: Iterable[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    args = list(command)
    result = subprocess.run(
        args,
        cwd=cwd,
        env=None if env is None else dict(env),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise PackagePlaneError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{result.stdout}"
        )
    return result.stdout


def isolated_environment(
    base: Mapping[str, str], package_root: Path, cli_home: Path, http_cache: Path
) -> dict[str, str]:
    inherited = {
        "PATH",
        "DOTNET_ROOT",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
    result = {key: value for key, value in base.items() if key in inherited}
    private_home = cli_home.parent / "home"
    temporary_root = cli_home.parent / "tmp"
    for directory in (
        private_home,
        cli_home,
        package_root,
        http_cache,
        temporary_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    result.update(
        {
            "HOME": str(private_home),
            "DOTNET_CLI_HOME": str(cli_home),
            "NUGET_PACKAGES": str(package_root),
            "NUGET_HTTP_CACHE_PATH": str(http_cache),
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
            "DOTNET_NOLOGO": "1",
            "DOTNET_MULTILEVEL_LOOKUP": "0",
            "DOTNET_ROLL_FORWARD": "LatestPatch",
            "DOTNET_ROLL_FORWARD_TO_PRERELEASE": "0",
            "CI": "true",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "TMPDIR": str(temporary_root),
            "SOURCE_DATE_EPOCH": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return result


def validate_dotnet_toolchain(
    lock: PackagePlaneLock, dotnet: str, *, env: Mapping[str, str]
) -> dict[str, str]:
    executable_name = shutil.which(dotnet, path=env.get("PATH")) or dotnet
    executable = Path(executable_name).resolve()
    if not executable.is_file():
        raise PackagePlaneError(f"dotnet host is not a regular file: {executable}")
    sdk_rows: list[Path] = []
    for line in _run((dotnet, "--list-sdks"), env=env).splitlines():
        version, separator, location = line.partition(" [")
        if version == lock.dotnet_sdk and separator and location.endswith("]"):
            sdk_rows.append(Path(location[:-1]) / lock.dotnet_sdk)
    if len(sdk_rows) != 1:
        raise PackagePlaneError(
            f"expected one exact SDK {lock.dotnet_sdk}, observed {len(sdk_rows)}"
        )
    sdk_root = sdk_rows[0].resolve()
    files = {
        "dotnet_host": executable,
        "csc": sdk_root / "Roslyn/bincore/csc.dll",
        "msbuild": sdk_root / "Microsoft.Build.dll",
        "nuget_packaging": sdk_root / "NuGet.Packaging.dll",
    }
    if any(not path.is_file() for path in files.values()):
        raise PackagePlaneError("exact SDK toolchain files are incomplete")
    observed = {key: _sha256(path) for key, path in files.items()}
    if observed != dict(lock.toolchain_sha256):
        raise PackagePlaneError(
            "dotnet toolchain bytes do not match the package-plane authority lock"
        )
    return observed


def validate_checkout(
    checkout: Path, spec: PackageSpec, *, env: Mapping[str, str]
) -> None:
    observed = _run(("git", "rev-parse", "HEAD"), cwd=checkout, env=env).strip()
    if observed != spec.commit:
        raise PackagePlaneError(f"checkout commit mismatch for {spec.package_id}: {observed}")
    origin = _run(("git", "remote", "get-url", "origin"), cwd=checkout, env=env).strip()
    if origin != spec.repository:
        raise PackagePlaneError(f"checkout origin mismatch for {spec.package_id}: {origin}")
    status = _run(
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        cwd=checkout,
        env=env,
    ).strip()
    if status:
        raise PackagePlaneError(f"exact-HEAD checkout is dirty for {spec.package_id}:\n{status}")


def acquire_source(
    source_root: Path, spec: PackageSpec, *, env: Mapping[str, str]
) -> Path:
    checkout = source_root / spec.checkout_directory
    if checkout.exists() or checkout.is_symlink():
        raise PackagePlaneError("source checkout destination must start absent")
    checkout.parent.mkdir(parents=True, exist_ok=True)
    _run(("git", "init", str(checkout)), env=env)
    _run(("git", "remote", "add", "origin", spec.repository), cwd=checkout, env=env)
    _run(("git", "fetch", "--no-tags", "--depth=1", "origin", spec.commit), cwd=checkout, env=env)
    _run(("git", "checkout", "--detach", spec.commit), cwd=checkout, env=env)
    validate_checkout(checkout, spec, env=env)
    return checkout


def restore_with_ephemeral_package_locks(
    checkout: Path,
    command: Iterable[str],
    *,
    env: Mapping[str, str],
) -> str:
    """Restore against this feed without trusting stale same-version hashes.

    Owner commits retain their reviewed lock bytes. They are temporarily absent
    only while NuGet resolves the exact authority feed, then restored byte for
    byte before the checkout is validated and the package is accepted.
    """

    checkout = checkout.resolve()
    source_lock_bytes: dict[Path, bytes] = {}
    for path in checkout.rglob("packages.lock.json"):
        if path.is_symlink() or not path.is_file():
            raise PackagePlaneError("source package locks must be regular files")
        resolved = path.resolve()
        resolved.relative_to(checkout)
        source_lock_bytes[resolved] = path.read_bytes()
    for path in source_lock_bytes:
        path.unlink()
    try:
        return _run(command, cwd=checkout, env=env)
    finally:
        for path in checkout.rglob("packages.lock.json"):
            if path.is_symlink() or path.is_file():
                path.unlink()
            else:
                raise PackagePlaneError("generated package lock is not a regular file")
        for path, content in source_lock_bytes.items():
            path.write_bytes(content)


def package_build_properties(
    lock: PackagePlaneLock,
    spec: PackageSpec,
    checkout: Path,
    package_root: Path,
) -> tuple[str, ...]:
    normalized_source_root = f"/_/src/{spec.checkout_directory}"
    versions = {row.package_id: row.version for row in lock.packages}
    missing_local_contracts = package_root.parent / "no-local-core-contracts.csproj"
    return (
        f"-p:PackageVersion={spec.version}",
        f"-p:Version={spec.version}",
        f"-p:RepositoryCommit={spec.commit}",
        f"-p:SourceRevisionId={spec.commit}",
        f"-p:RepositoryUrl={spec.repository}",
        "-p:RepositoryBranch=",
        "-p:PublishRepositoryUrl=true",
        "-p:ContinuousIntegrationBuild=true",
        "-p:Deterministic=true",
        "-p:DeterministicSourcePaths=true",
        "-p:EmbedUntrackedSources=false",
        "-p:RestorePackagesWithLockFile=true",
        "-p:RestoreLockedMode=false",
        "-p:ChummerUseLocalCompatibilityTree=false",
        f"-p:ChummerPackagePlaneVersion={lock.package_version}",
        f"-p:ChummerEngineContractsPackageVersion={versions['Chummer.Engine.Contracts']}",
        f"-p:ChummerHubRegistryContractsPackageVersion={versions['Chummer.Hub.Registry.Contracts']}",
        f"-p:ChummerRunRegistryPackageVersion={versions['Chummer.Run.Registry']}",
        f"-p:ChummerRunContractsPackageVersion={versions['Chummer.Run.Contracts']}",
        f"-p:ChummerLocalContractsProject={missing_local_contracts}",
        "-p:PreferBundledChummerMediaContracts=true",
        f"-p:PathMap={checkout.resolve()}={normalized_source_root}",
        "-p:UseSharedCompilation=false",
        f"-p:RestorePackagesPath={package_root}",
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_text(root: ET.Element, name: str) -> str:
    for element in root.iter():
        if _local_name(element.tag) == name:
            return (element.text or "").strip()
    return ""


def _repository(root: ET.Element) -> tuple[str, str]:
    for element in root.iter():
        if _local_name(element.tag) == "repository":
            return (
                (element.attrib.get("url") or "").strip(),
                (element.attrib.get("commit") or "").strip(),
            )
    return "", ""


def _license(root: ET.Element) -> tuple[str, str]:
    for element in root.iter():
        if _local_name(element.tag) == "license":
            return (
                (element.attrib.get("type") or "").strip(),
                (element.text or "").strip(),
            )
    return "", ""


def _internal_dependencies(root: ET.Element) -> tuple[tuple[str, str], ...]:
    dependencies = []
    for element in root.iter():
        if _local_name(element.tag) != "dependency":
            continue
        package_id = (element.attrib.get("id") or "").strip()
        if package_id.startswith("Chummer."):
            dependencies.append(
                (package_id, (element.attrib.get("version") or "").strip())
            )
    return tuple(sorted(dependencies))


def _package_path(feed: Path, package_id: str, version: str) -> Path:
    expected = f"{package_id}.{version}.nupkg".lower()
    resolved_feed = feed.resolve()
    matches = [
        candidate
        for candidate in feed.iterdir()
        if candidate.is_file()
        and not candidate.is_symlink()
        and candidate.resolve().parent == resolved_feed
        and candidate.name.lower() == expected
    ]
    if len(matches) != 1:
        raise PackagePlaneError(f"feed must contain exactly one {package_id} {version}")
    return matches[0]


def _validate_payload_names(names: list[str], spec: PackageSpec) -> None:
    if len(names) != len(set(names)):
        raise PackagePlaneError(f"duplicate package paths in {spec.package_id}")
    expected_assembly = f"lib/net10.0/{spec.package_id}.dll"
    allowed_exact = {
        "_rels/.rels",
        f"{spec.package_id}.nuspec",
        expected_assembly,
        f"lib/net10.0/{spec.package_id}.xml",
        "LICENSE",
        "PACKAGE_README.md",
        "README.md",
        "[Content_Types].xml",
    }
    if spec.package_id == "Chummer.Engine.GmCharacterEdits":
        allowed_exact.update(
            f"lib/net10.0/{assembly}.dll" for assembly in GM_RUNTIME_ASSEMBLIES
        )
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or "\\" in name or ".." in path.parts:
            raise PackagePlaneError(f"unsafe package path in {spec.package_id}: {name}")
        if name in allowed_exact or CORE_PROPERTIES_PATTERN.fullmatch(name):
            continue
        raise PackagePlaneError(f"unlisted payload in {spec.package_id}: {name}")
    if expected_assembly not in names:
        raise PackagePlaneError(f"expected assembly is missing from {spec.package_id}")


def _canonical_relationships(spec: PackageSpec, core_properties_path: str) -> bytes:
    ET.register_namespace("", RELATIONSHIPS_NAMESPACE)
    root = ET.Element(f"{{{RELATIONSHIPS_NAMESPACE}}}Relationships")
    relationships = (
        (MANIFEST_RELATIONSHIP, f"/{spec.package_id}.nuspec"),
        (CORE_PROPERTIES_RELATIONSHIP, f"/{core_properties_path}"),
    )
    for relationship_type, target in sorted(relationships):
        identifier = "R" + hashlib.sha256(
            f"{relationship_type}\n{target}".encode("utf-8")
        ).hexdigest()[:16].upper()
        ET.SubElement(
            root,
            f"{{{RELATIONSHIPS_NAMESPACE}}}Relationship",
            {"Type": relationship_type, "Target": target, "Id": identifier},
        )
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _canonical_core_properties(spec: PackageSpec, version: str) -> bytes:
    core_namespace = (
        "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    )
    dc_namespace = "http://purl.org/dc/elements/1.1/"
    ET.register_namespace("", core_namespace)
    ET.register_namespace("dc", dc_namespace)
    root = ET.Element(f"{{{core_namespace}}}coreProperties")
    fields = (
        (f"{{{dc_namespace}}}creator", spec.package_id),
        (f"{{{dc_namespace}}}description", "Chummer deterministic package-plane artifact"),
        (f"{{{dc_namespace}}}identifier", spec.package_id),
        (f"{{{core_namespace}}}version", version),
        (f"{{{core_namespace}}}keywords", ""),
        (f"{{{core_namespace}}}lastModifiedBy", "Chummer package plane v2"),
    )
    for name, value in fields:
        ET.SubElement(root, name).text = value
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def canonicalize_package(path: Path, spec: PackageSpec, version: str) -> None:
    """Rewrite a NuGet package into one byte-stable, platform-neutral ZIP."""

    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            _validate_payload_names(names, spec)
            if len(names) != len(set(names)):
                raise PackagePlaneError(f"duplicate package paths in {spec.package_id}")
            payloads = {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackagePlaneError(f"invalid package {path}: {exc}") from exc

    core_paths = [name for name in names if CORE_PROPERTIES_PATTERN.fullmatch(name)]
    if len(core_paths) != 1 or "_rels/.rels" not in payloads:
        raise PackagePlaneError(
            f"{spec.package_id} must contain one core-properties part and relationships"
        )
    old_core_path = core_paths[0]
    payloads.pop(old_core_path)
    core_bytes = _canonical_core_properties(spec, version)
    core_digest = hashlib.sha256(core_bytes).hexdigest()
    core_path = (
        "package/services/metadata/core-properties/"
        f"{core_digest[:32]}.psmdcp"
    )
    payloads[core_path] = core_bytes
    payloads["_rels/.rels"] = _canonical_relationships(spec, core_path)

    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(handle)
    temporary_path = Path(temporary)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.comment = b""
            for name in sorted(payloads):
                info = zipfile.ZipInfo(name, date_time=CANONICAL_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = CANONICAL_ZIP_EXTERNAL_ATTR
                info.extra = b""
                info.comment = b""
                archive.writestr(info, payloads[name])
        with temporary_path.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _validate_canonical_package(
    archive: zipfile.ZipFile, names: list[str], spec: PackageSpec, version: str
) -> None:
    if names != sorted(names) or archive.comment:
        raise PackagePlaneError(f"non-canonical archive layout in {spec.package_id}")
    if "_rels/.rels" not in names:
        raise PackagePlaneError(f"canonical relationships are missing from {spec.package_id}")
    for info in archive.infolist():
        if (
            info.date_time != CANONICAL_ZIP_TIMESTAMP
            or info.compress_type != zipfile.ZIP_STORED
            or info.create_system != 3
            or info.external_attr != CANONICAL_ZIP_EXTERNAL_ATTR
            or info.extra
            or info.comment
        ):
            raise PackagePlaneError(f"non-canonical ZIP metadata in {spec.package_id}")
    core_paths = [name for name in names if CORE_PROPERTIES_PATTERN.fullmatch(name)]
    if len(core_paths) != 1:
        raise PackagePlaneError(f"non-canonical core-properties part in {spec.package_id}")
    core_path = core_paths[0]
    expected_core_path = (
        "package/services/metadata/core-properties/"
        f"{hashlib.sha256(archive.read(core_path)).hexdigest()[:32]}.psmdcp"
    )
    if core_path != expected_core_path:
        raise PackagePlaneError(f"core-properties digest path mismatch in {spec.package_id}")
    if archive.read(core_path) != _canonical_core_properties(spec, version):
        raise PackagePlaneError(f"non-canonical core properties in {spec.package_id}")
    if archive.read("_rels/.rels") != _canonical_relationships(spec, core_path):
        raise PackagePlaneError(f"non-canonical relationships in {spec.package_id}")


def _validate_public_core_package(
    archive: zipfile.ZipFile, names: list[str], spec: PackageSpec
) -> None:
    if len(names) != len(set(names)) or archive.comment:
        raise PackagePlaneError(f"non-canonical public Core package: {spec.package_id}")
    core_paths = [name for name in names if CORE_PROPERTIES_PATTERN.fullmatch(name)]
    if len(core_paths) != 1 or "_rels/.rels" not in names:
        raise PackagePlaneError(
            f"public Core package metadata is incomplete: {spec.package_id}"
        )
    for info in archive.infolist():
        mode = (info.external_attr >> 16) & 0o170000
        if (
            info.is_dir()
            or mode == 0o120000
            or info.flag_bits & 0x1
            or info.file_size > 16 * 1024 * 1024
        ):
            raise PackagePlaneError(f"unsafe public Core package member: {info.filename}")


def validate_package(
    feed: Path,
    spec: PackageSpec,
    dependency_versions: Mapping[str, str] | None = None,
    *,
    enforce_locked_bytes: bool = True,
) -> Path:
    version = spec.version
    path = _package_path(feed, spec.package_id, version)
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            _validate_payload_names(names, spec)
            if spec.source_kind == CORE_SOURCE_KIND:
                _validate_public_core_package(archive, names, spec)
            else:
                _validate_canonical_package(archive, names, spec, version)
            nuspec_names = [name for name in names if name.lower().endswith(".nuspec")]
            if len(nuspec_names) != 1:
                raise PackagePlaneError(f"{path.name} must contain exactly one nuspec")
            root = ET.fromstring(archive.read(nuspec_names[0]))
            if spec.license_type == "file":
                try:
                    license_bytes = archive.read(spec.license_value)
                except KeyError as exc:
                    raise PackagePlaneError(
                        f"license file is missing from {path.name}"
                    ) from exc
                if hashlib.sha256(license_bytes).hexdigest() != spec.license_sha256:
                    raise PackagePlaneError(f"license bytes drifted in {path.name}")
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise PackagePlaneError(f"invalid package {path}: {exc}") from exc
    if _element_text(root, "id") != spec.package_id:
        raise PackagePlaneError(f"package id mismatch in {path.name}")
    if _element_text(root, "version") != version:
        raise PackagePlaneError(f"package version mismatch in {path.name}")
    if _repository(root) != (spec.repository, spec.commit):
        raise PackagePlaneError(f"package source provenance mismatch in {path.name}")
    if _license(root) != (spec.license_type, spec.license_value):
        raise PackagePlaneError(f"package license metadata mismatch in {path.name}")
    versions = dependency_versions or {}
    expected_dependencies = tuple(
        sorted(
            (package_id, versions.get(package_id, version))
            for package_id in EXPECTED_INTERNAL_DEPENDENCIES[spec.package_id]
        )
    )
    if _internal_dependencies(root) != expected_dependencies:
        raise PackagePlaneError(f"internal dependency drift in {path.name}")
    observed_size = path.stat().st_size
    observed_sha256 = _sha256(path)
    if enforce_locked_bytes and (
        spec.byte_authority_status != "locked"
        or observed_size != spec.nupkg_size_bytes
        or observed_sha256 != spec.nupkg_sha256
    ):
        raise PackagePlaneError(
            f"locked package byte authority mismatch in {path.name}: "
            f"expected sha256={spec.nupkg_sha256} size={spec.nupkg_size_bytes}; "
            f"observed sha256={observed_sha256} size={observed_size}"
        )
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_exact_regular_file(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    label: str,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PackagePlaneError(f"unable to open {label}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            raise PackagePlaneError(f"{label} is not the exact expected regular file")
        chunks: list[bytes] = []
        remaining = expected_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    data = b"".join(chunks)
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or after.st_size != expected_size
        or len(data) != expected_size
        or hashlib.sha256(data).hexdigest() != expected_sha256
    ):
        raise PackagePlaneError(f"{label} bytes do not match v5 authority")
    return data


def validate_core_public_receipt(
    receipt_path: Path, lock: PackagePlaneLock
) -> dict[str, Any]:
    authority = lock.core_public_bundle
    receipt_bytes = _read_exact_regular_file(
        receipt_path,
        expected_size=authority.receipt_size_bytes,
        expected_sha256=authority.receipt_sha256,
        label="Core public handoff receipt",
    )
    try:
        payload = json.loads(receipt_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagePlaneError(f"invalid Core public handoff receipt: {exc}") from exc
    if not isinstance(payload, dict):
        raise PackagePlaneError("Core public handoff receipt must be one object")
    bundle = payload.get("bundle")
    if (
        payload.get("contract") != "chummer-core.runtime-package-public-handoff/v2"
        or payload.get("repository") != "ArchonMegalon/chummer6-core"
        or payload.get("ref") != "refs/heads/main"
        or payload.get("commit") != authority.release_commit
        or payload.get("release_tag") != authority.release_tag
        or not isinstance(bundle, dict)
        or bundle.get("contract")
        != "chummer-core.runtime-package-public-handoff-zip/v1"
        or bundle.get("asset_name") != authority.asset_name
        or bundle.get("sha256") != authority.sha256
        or bundle.get("size_bytes") != authority.size_bytes
        or bundle.get("member_count") != authority.member_count
        or bundle.get("uncompressed_size_bytes") != authority.uncompressed_size_bytes
    ):
        raise PackagePlaneError("Core public handoff receipt authority drifted")
    workflow_run = ((payload.get("source_actions_artifact") or {}).get("workflow_run") or {})
    if (
        workflow_run.get("event") != "push"
        or workflow_run.get("head_branch") != "main"
        or workflow_run.get("head_sha") != authority.release_commit
        or workflow_run.get("workflow_sha") != authority.release_commit
    ):
        raise PackagePlaneError("Core public handoff workflow authority drifted")
    rows = bundle.get("members")
    if not isinstance(rows, list) or len(rows) != authority.member_count:
        raise PackagePlaneError("Core public handoff member receipt drifted")
    observed = {
        row.get("path"): (row.get("sha256"), row.get("size_bytes"))
        for row in rows
        if isinstance(row, dict)
    }
    expected_digests = {
        "runtime-package-plane.lock.json": authority.runtime_lock_sha256,
        "chummer-core-runtime-packages.inventory.json": (
            authority.runtime_inventory_sha256
        ),
        "no-siblings.v3.receipt.json": authority.no_siblings_receipt_sha256,
        **{
            spec.bundle_member: spec.nupkg_sha256
            for spec in lock.packages
            if spec.source_kind == CORE_SOURCE_KIND and spec.bundle_member is not None
        },
    }
    if set(observed) != set(expected_digests):
        raise PackagePlaneError("Core public handoff member set drifted")
    for path, expected_sha in expected_digests.items():
        digest, size = observed[path]
        if digest != expected_sha or not isinstance(size, int) or size <= 0:
            raise PackagePlaneError(f"Core public handoff member drifted: {path}")
    return {
        "asset_url": authority.asset_url,
        "receipt_asset_url": authority.receipt_asset_url,
        "receipt_sha256": authority.receipt_sha256,
        "receipt_size_bytes": authority.receipt_size_bytes,
        "release_tag": authority.release_tag,
        "release_commit": authority.release_commit,
    }


def cleanup_downloaded_core_authority(
    destination: Path, lock: PackagePlaneLock
) -> None:
    names = (
        lock.core_public_bundle.asset_name,
        PurePosixPath(lock.core_public_bundle.receipt_asset_url).name,
    )
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags)
    except FileNotFoundError:
        return
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode):
            raise PackagePlaneError("Core public-authority cleanup target is not a directory")
        for name in names:
            try:
                os.unlink(name, dir_fd=descriptor)
            except FileNotFoundError:
                pass
    finally:
        os.close(descriptor)
    current = os.stat(destination, follow_symlinks=False)
    if (
        current.st_dev != opened.st_dev
        or current.st_ino != opened.st_ino
        or not stat.S_ISDIR(current.st_mode)
    ):
        raise PackagePlaneError("Core public-authority cleanup identity changed")
    destination.rmdir()


def download_core_public_authority(
    destination: Path, lock: PackagePlaneLock
) -> tuple[Path, Path]:
    if destination.exists() or destination.is_symlink():
        raise PackagePlaneError("Core public-authority destination must start absent")
    destination.mkdir(parents=True, mode=0o700)
    authority = lock.core_public_bundle
    rows = (
        (
            authority.asset_url,
            authority.asset_name,
            authority.sha256,
            authority.size_bytes,
        ),
        (
            authority.receipt_asset_url,
            PurePosixPath(authority.receipt_asset_url).name,
            authority.receipt_sha256,
            authority.receipt_size_bytes,
        ),
    )
    paths: list[Path] = []
    try:
        for url, name, expected_sha, expected_size in rows:
            path = destination / name
            digest = hashlib.sha256()
            observed_size = 0
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "chummer-hub-package-plane-v5"},
                method="GET",
            )
            try:
                response = urllib.request.urlopen(request, timeout=60)
            except (OSError, urllib.error.URLError) as exc:
                raise PackagePlaneError(
                    f"unable to fetch Core public authority {name}: {exc}"
                ) from exc
            with response, path.open("xb") as stream:
                path.chmod(0o600)
                while True:
                    chunk = response.read(min(1024 * 1024, expected_size + 1 - observed_size))
                    if not chunk:
                        break
                    observed_size += len(chunk)
                    if observed_size > expected_size:
                        raise PackagePlaneError(f"Core public authority is oversized: {name}")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if observed_size != expected_size or digest.hexdigest() != expected_sha:
                raise PackagePlaneError(f"Core public authority bytes drifted: {name}")
            paths.append(path)
    except Exception:
        cleanup_downloaded_core_authority(destination, lock)
        raise
    return paths[0], paths[1]


def import_core_public_bundle(
    bundle_path: Path,
    lock: PackagePlaneLock,
    staged_feed: Path,
    *,
    enforce_locked_bytes: bool,
) -> dict[str, Any]:
    authority = lock.core_public_bundle
    bundle_bytes = _read_exact_regular_file(
        bundle_path,
        expected_size=authority.size_bytes,
        expected_sha256=authority.sha256,
        label="Core public bundle",
    )
    core_specs = tuple(
        spec for spec in lock.packages if spec.source_kind == CORE_SOURCE_KIND
    )
    expected_members = {
        "runtime-package-plane.lock.json",
        "chummer-core-runtime-packages.inventory.json",
        "no-siblings.v3.receipt.json",
        *(spec.bundle_member for spec in core_specs if spec.bundle_member is not None),
    }
    try:
        with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != expected_members:
                raise PackagePlaneError("Core public bundle member set drifted")
            if len(infos) != authority.member_count:
                raise PackagePlaneError("Core public bundle member count drifted")
            if sum(info.file_size for info in infos) != authority.uncompressed_size_bytes:
                raise PackagePlaneError("Core public bundle uncompressed size drifted")
            for info in infos:
                path = PurePosixPath(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if (
                    path.is_absolute()
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or "\\" in info.filename
                    or info.is_dir()
                    or mode == 0o120000
                    or info.flag_bits & 0x1
                    or info.file_size > 16 * 1024 * 1024
                ):
                    raise PackagePlaneError(
                        f"unsafe Core public bundle member: {info.filename}"
                    )
            payloads = {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackagePlaneError(f"invalid Core public bundle: {exc}") from exc

    pinned_json = {
        "runtime-package-plane.lock.json": authority.runtime_lock_sha256,
        "chummer-core-runtime-packages.inventory.json": (
            authority.runtime_inventory_sha256
        ),
        "no-siblings.v3.receipt.json": authority.no_siblings_receipt_sha256,
    }
    for name, expected_sha in pinned_json.items():
        if hashlib.sha256(payloads[name]).hexdigest() != expected_sha:
            raise PackagePlaneError(f"Core public bundle {name} digest drifted")
    try:
        runtime_lock = json.loads(payloads["runtime-package-plane.lock.json"])
        inventory = json.loads(
            payloads["chummer-core-runtime-packages.inventory.json"]
        )
        receipt = json.loads(payloads["no-siblings.v3.receipt.json"])
    except json.JSONDecodeError as exc:
        raise PackagePlaneError(f"Core public bundle JSON is invalid: {exc}") from exc
    if (
        runtime_lock.get("contract") != "chummer-core.runtime-package-plane-lock/v1"
        or runtime_lock.get("package_version") != CORE_PACKAGE_VERSION
        or (runtime_lock.get("runtime_source") or {}).get("commit")
        != authority.source_commit
    ):
        raise PackagePlaneError("Core runtime lock authority drifted")
    expected_owner_rows = {
        ("Chummer.Hub.Registry.Contracts", OWNER_PACKAGE_VERSION),
        ("Chummer.Play.Contracts", OWNER_PACKAGE_VERSION),
        ("Chummer.Run.Contracts", OWNER_PACKAGE_VERSION),
    }
    observed_owner_rows = {
        (row.get("id"), row.get("version"))
        for row in runtime_lock.get("external_owner_packages", [])
        if isinstance(row, dict)
    }
    if observed_owner_rows != expected_owner_rows:
        raise PackagePlaneError("Core external-owner dependency versions drifted")
    if (
        inventory.get("contract") != "chummer-core.runtime-package-inventory/v1"
        or inventory.get("package_version") != CORE_PACKAGE_VERSION
        or inventory.get("runtime_source_commit") != authority.source_commit
        or inventory.get("package_recipe_commit") != authority.release_commit
    ):
        raise PackagePlaneError("Core runtime inventory authority drifted")
    if (
        receipt.get("contract") != "chummer-core.no-siblings-package-plane/v3"
        or receipt.get("status") != "pass"
        or receipt.get("package_recipe_commit") != authority.release_commit
        or receipt.get("runtime_source_commit") != authority.source_commit
        or receipt.get("candidate_package_version") != CORE_PACKAGE_VERSION
        or receipt.get("package_version") != OWNER_PACKAGE_VERSION
        or receipt.get("eight_package_runtime_plane") != "pass"
    ):
        raise PackagePlaneError("Core no-siblings receipt authority drifted")
    inventory_rows = inventory.get("packages")
    if not isinstance(inventory_rows, list) or len(inventory_rows) != len(core_specs):
        raise PackagePlaneError("Core inventory must contain exactly eight packages")
    dependency_versions = {spec.package_id: spec.version for spec in lock.packages}
    for spec, row in zip(core_specs, inventory_rows, strict=True):
        if not isinstance(row, dict):
            raise PackagePlaneError(f"invalid Core inventory row for {spec.package_id}")
        expected_file_name = f"{spec.package_id}.{spec.version}.nupkg"
        if (
            row.get("id") != spec.package_id
            or row.get("version") != spec.version
            or row.get("source_commit") != spec.commit
            or row.get("project") != spec.project
            or row.get("file_name") != expected_file_name
            or row.get("sha256") != spec.nupkg_sha256
            or row.get("size_bytes") != spec.nupkg_size_bytes
        ):
            raise PackagePlaneError(f"Core inventory row drifted for {spec.package_id}")
        member = spec.bundle_member
        if member is None:
            raise PackagePlaneError(f"Core bundle member is missing for {spec.package_id}")
        package_bytes = payloads[member]
        if (
            hashlib.sha256(package_bytes).hexdigest() != spec.nupkg_sha256
            or len(package_bytes) != spec.nupkg_size_bytes
        ):
            raise PackagePlaneError(f"Core package member drifted for {spec.package_id}")
        destination = staged_feed / expected_file_name
        destination.write_bytes(package_bytes)
        destination.chmod(0o600)
        validate_package(
            staged_feed,
            spec,
            dependency_versions,
            enforce_locked_bytes=enforce_locked_bytes,
        )
    return {
        "asset_url": authority.asset_url,
        "release_tag": authority.release_tag,
        "release_commit": authority.release_commit,
        "source_commit": authority.source_commit,
        "sha256": authority.sha256,
        "size_bytes": authority.size_bytes,
        "runtime_lock_sha256": authority.runtime_lock_sha256,
        "runtime_inventory_sha256": authority.runtime_inventory_sha256,
        "no_siblings_receipt_sha256": authority.no_siblings_receipt_sha256,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _inventory_payload(
    lock: PackagePlaneLock, feed: Path, lock_sha256: str
) -> dict[str, Any]:
    packages = []
    dependency_versions = {spec.package_id: spec.version for spec in lock.packages}
    for spec in lock.packages:
        path = validate_package(feed, spec, dependency_versions)
        packages.append(
            {
                "id": spec.package_id,
                "version": spec.version,
                "repository": spec.repository,
                "commit": spec.commit,
                "project": spec.project,
                "source_kind": spec.source_kind,
                "license_type": spec.license_type,
                "license_value": spec.license_value,
                "license_sha256": spec.license_sha256,
                "file_name": path.name,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "contract": INVENTORY_CONTRACT,
        "package_plane_lock_sha256": lock_sha256,
        "package_version": lock.package_version,
        "dotnet_sdk": lock.dotnet_sdk,
        "dotnet_toolchain_sha256": dict(lock.toolchain_sha256),
        "core_public_bundle": {
            "asset_url": lock.core_public_bundle.asset_url,
            "release_tag": lock.core_public_bundle.release_tag,
            "release_commit": lock.core_public_bundle.release_commit,
            "source_commit": lock.core_public_bundle.source_commit,
            "sha256": lock.core_public_bundle.sha256,
            "size_bytes": lock.core_public_bundle.size_bytes,
        },
        "dependency_graph": {
            package_id: [
                {"id": dependency_id, "version": version}
                for dependency_id, version in dependencies
            ]
            for package_id, dependencies in lock.dependency_graph.items()
        },
        "packages": packages,
    }


def _expected_feed_entry_names(lock: PackagePlaneLock) -> set[str]:
    return {
        INVENTORY_FILE_NAME,
        *(f"{spec.package_id}.{spec.version}.nupkg" for spec in lock.packages),
    }


def _assert_exact_feed_entries(feed: Path, lock: PackagePlaneLock) -> None:
    if feed.is_symlink() or not feed.is_dir():
        raise PackagePlaneError("feed must be one regular, non-symlink directory")
    resolved_feed = feed.resolve()
    expected = _expected_feed_entry_names(lock)
    entries = list(feed.iterdir())
    for entry in entries:
        if (
            entry.is_symlink()
            or not entry.is_file()
            or entry.resolve().parent != resolved_feed
        ):
            raise PackagePlaneError("feed entries must be contained regular files")
    observed = {entry.name for entry in entries}
    if observed != expected:
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise PackagePlaneError(
            "feed must contain the exact locked file set (" + "; ".join(details) + ")"
        )


def validate_feed_inventory(
    feed: Path, lock: PackagePlaneLock, lock_sha256: str
) -> str:
    _assert_exact_feed_entries(feed, lock)
    inventory_path = feed / INVENTORY_FILE_NAME
    try:
        inventory_bytes = inventory_path.read_bytes()
        payload = json.loads(inventory_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagePlaneError(f"unable to read package inventory: {exc}") from exc
    expected_top_level_keys = {
        "contract",
        "package_plane_lock_sha256",
        "package_version",
        "dotnet_sdk",
        "dotnet_toolchain_sha256",
        "core_public_bundle",
        "dependency_graph",
        "packages",
    }
    if not isinstance(payload, dict) or set(payload) != expected_top_level_keys:
        raise PackagePlaneError("package inventory must contain the exact top-level fields")
    if payload.get("contract") != INVENTORY_CONTRACT:
        raise PackagePlaneError(f"package inventory contract must be {INVENTORY_CONTRACT}")
    if payload.get("package_plane_lock_sha256") != lock_sha256:
        raise PackagePlaneError("package inventory does not bind the exact lock bytes")
    if payload.get("package_version") != lock.package_version:
        raise PackagePlaneError("package inventory version does not match the lock")
    if payload.get("dotnet_sdk") != lock.dotnet_sdk:
        raise PackagePlaneError("package inventory SDK authority drifted")
    if payload.get("dotnet_toolchain_sha256") != dict(lock.toolchain_sha256):
        raise PackagePlaneError("package inventory toolchain authority drifted")
    expected_core_bundle = {
        "asset_url": lock.core_public_bundle.asset_url,
        "release_tag": lock.core_public_bundle.release_tag,
        "release_commit": lock.core_public_bundle.release_commit,
        "source_commit": lock.core_public_bundle.source_commit,
        "sha256": lock.core_public_bundle.sha256,
        "size_bytes": lock.core_public_bundle.size_bytes,
    }
    if payload.get("core_public_bundle") != expected_core_bundle:
        raise PackagePlaneError("package inventory Core bundle authority drifted")
    expected_dependency_graph = {
        package_id: [
            {"id": dependency_id, "version": version}
            for dependency_id, version in dependencies
        ]
        for package_id, dependencies in lock.dependency_graph.items()
    }
    if payload.get("dependency_graph") != expected_dependency_graph:
        raise PackagePlaneError("package inventory dependency graph drifted")
    rows = payload.get("packages")
    if not isinstance(rows, list) or len(rows) != len(lock.packages):
        raise PackagePlaneError("package inventory must contain the exact locked set")
    dependency_versions = {spec.package_id: spec.version for spec in lock.packages}
    for spec, row in zip(lock.packages, rows, strict=True):
        if not isinstance(row, dict):
            raise PackagePlaneError(f"invalid inventory row for {spec.package_id}")
        expected_row_keys = {
            "id",
            "version",
            "repository",
            "commit",
            "project",
            "source_kind",
            "license_type",
            "license_value",
            "license_sha256",
            "file_name",
            "sha256",
            "size_bytes",
        }
        if set(row) != expected_row_keys:
            raise PackagePlaneError(
                f"inventory row for {spec.package_id} must contain the exact fields"
            )
        expected = {
            "id": spec.package_id,
            "version": spec.version,
            "repository": spec.repository,
            "commit": spec.commit,
            "project": spec.project,
            "source_kind": spec.source_kind,
            "license_type": spec.license_type,
            "license_value": spec.license_value,
            "license_sha256": spec.license_sha256,
            "file_name": f"{spec.package_id}.{spec.version}.nupkg",
        }
        for key, value in expected.items():
            if row.get(key) != value:
                raise PackagePlaneError(f"inventory {key} mismatch for {spec.package_id}")
        digest = row.get("sha256")
        size = row.get("size_bytes")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise PackagePlaneError(f"invalid inventory digest for {spec.package_id}")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise PackagePlaneError(f"invalid inventory size for {spec.package_id}")
        path = validate_package(feed, spec, dependency_versions)
        if path.stat().st_size != size or _sha256(path) != digest:
            raise PackagePlaneError(f"package byte binding mismatch for {spec.package_id}")
    return hashlib.sha256(inventory_bytes).hexdigest()


def build_feed(
    lock: PackagePlaneLock,
    *,
    lock_sha256: str,
    feed: Path,
    dotnet: str,
    core_public_bundle: Path | None = None,
    core_public_receipt: Path | None = None,
    observe_package_authority: bool = False,
) -> str:
    if feed.exists() or feed.is_symlink():
        raise PackagePlaneError("feed destination must start absent; package reuse is forbidden")
    if lock.state != SEALED_LOCK_STATE and not observe_package_authority:
        raise PackagePlaneError(
            "package-plane v5 is not sealed; normal feed materialization is forbidden"
        )
    if core_public_bundle is None:
        raise PackagePlaneError("Core public bundle path is required")
    if core_public_receipt is None:
        raise PackagePlaneError("Core public handoff receipt path is required")
    feed.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hub-package-plane-", dir=feed.parent) as temporary:
        root = Path(temporary)
        source_root = root / "sources"
        package_root = root / "nuget-packages"
        cli_home = root / "dotnet-cli"
        http_cache = root / "nuget-http-cache"
        staged_feed = root / "feed"
        for directory in (source_root, package_root, cli_home, http_cache, staged_feed):
            directory.mkdir(parents=True, exist_ok=True)
        env = isolated_environment(os.environ, package_root, cli_home, http_cache)
        observed_sdk = _run((dotnet, "--version"), env=env).strip()
        if observed_sdk != lock.dotnet_sdk:
            raise PackagePlaneError(
                f"dotnet SDK mismatch: expected {lock.dotnet_sdk}, observed {observed_sdk}"
            )
        observed_toolchain = validate_dotnet_toolchain(lock, dotnet, env=env)
        receipt_provenance = validate_core_public_receipt(
            core_public_receipt.resolve(), lock
        )
        bundle_provenance = import_core_public_bundle(
            core_public_bundle.resolve(),
            lock,
            staged_feed,
            enforce_locked_bytes=True,
        )
        nuget_config = root / "NuGet.Config"
        nuget_config.write_text(
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
            "<configuration><packageSources><clear />"
            f"<add key=\"locked-chummer\" value=\"{staged_feed}\" />"
            f"<add key=\"nuget.org\" value=\"{lock.approved_remote_source}\" protocolVersion=\"3\" />"
            "</packageSources><packageSourceMapping>"
            "<packageSource key=\"locked-chummer\"><package pattern=\"Chummer.*\" /></packageSource>"
            "<packageSource key=\"nuget.org\"><package pattern=\"*\" /></packageSource>"
            "</packageSourceMapping></configuration>\n",
            encoding="utf-8",
        )
        repositories: dict[str, PackageSpec] = {}
        for spec in lock.packages:
            if spec.source_kind == CORE_SOURCE_KIND:
                continue
            repositories.setdefault(spec.checkout_directory, spec)
        for spec in repositories.values():
            acquire_source(source_root, spec, env=env)
        for spec in lock.packages:
            if spec.source_kind == CORE_SOURCE_KIND:
                continue
            checkout = source_root / spec.checkout_directory
            project = checkout / Path(spec.project)
            if not project.is_file():
                raise PackagePlaneError(f"locked project is missing: {spec.project}")
            common_properties = package_build_properties(
                lock,
                spec,
                checkout,
                package_root,
            )
            restore_with_ephemeral_package_locks(
                checkout,
                (
                    dotnet,
                    "restore",
                    str(project),
                    "--configfile",
                    str(nuget_config),
                    "--packages",
                    str(package_root),
                    "--no-cache",
                    "--nologo",
                    "-m:1",
                    *common_properties,
                ),
                env=env,
            )
            pack_command = [
                dotnet,
                "pack",
                str(project),
                "--configuration",
                "Release",
                "--no-restore",
                "--nologo",
                "-m:1",
                *common_properties,
            ]
            if spec.license_type == "expression":
                pack_command.append(f"-p:PackageLicenseExpression={spec.license_value}")
            pack_command.extend(("--output", str(staged_feed)))
            sys.stdout.write(_run(pack_command, cwd=checkout, env=env))
            canonicalize_package(
                staged_feed / f"{spec.package_id}.{spec.version}.nupkg",
                spec,
                spec.version,
            )
            validate_checkout(checkout, spec, env=env)
            validate_package(
                staged_feed,
                spec,
                {row.package_id: row.version for row in lock.packages},
                enforce_locked_bytes=not observe_package_authority,
            )
        if observe_package_authority:
            observed_rows = [
                {
                    "id": spec.package_id,
                    "version": spec.version,
                    "repository": spec.repository,
                    "commit": spec.commit,
                    "project": spec.project,
                    "source_kind": spec.source_kind,
                    "license_type": spec.license_type,
                    "license_value": spec.license_value,
                    "license_sha256": spec.license_sha256,
                    "candidate_byte_authority_status": spec.byte_authority_status,
                    "candidate_sha256": spec.nupkg_sha256,
                    "candidate_size_bytes": spec.nupkg_size_bytes,
                    "sha256": _sha256(
                        _package_path(staged_feed, spec.package_id, spec.version)
                    ),
                    "size_bytes": _package_path(
                        staged_feed, spec.package_id, spec.version
                    ).stat().st_size,
                    "matches_candidate_byte_authority": (
                        None
                        if spec.byte_authority_status == "pending_pinned_ci"
                        else (
                            spec.nupkg_sha256
                            == _sha256(
                                _package_path(
                                    staged_feed, spec.package_id, spec.version
                                )
                            )
                            and spec.nupkg_size_bytes
                            == _package_path(
                                staged_feed, spec.package_id, spec.version
                            ).stat().st_size
                        )
                    ),
                }
                for spec in lock.packages
            ]
            source_built_rows = [
                row for row in observed_rows if row["source_kind"] == BUILD_SOURCE_KIND
            ]
            pending_source_built_ids = [
                row["id"]
                for row in source_built_rows
                if row["candidate_byte_authority_status"] == "pending_pinned_ci"
            ]
            locked_source_built_rows = [
                row
                for row in source_built_rows
                if row["candidate_byte_authority_status"] == "locked"
            ]
            observed = {
                "contract": "chummer-hub.observed-package-authority/v2",
                "lock_state": lock.state,
                "candidate_lock_sha256": lock_sha256,
                "build_recipe_sha256": lock.build_recipe_sha256,
                "dotnet_sdk": lock.dotnet_sdk,
                "dotnet_toolchain_sha256": observed_toolchain,
                "source_checkout_mode": "fresh-detached-exact-commit",
                "source_package_lock_mode": "ephemeral-authority-feed-regeneration",
                "isolated_package_cache": True,
                "ambient_package_reuse": False,
                "dependency_graph": {
                    package_id: [
                        {"id": dependency_id, "version": version}
                        for dependency_id, version in dependencies
                    ]
                    for package_id, dependencies in lock.dependency_graph.items()
                },
                "core_public_bundle": bundle_provenance,
                "core_public_receipt": receipt_provenance,
                "packages": observed_rows,
                "imported_core_packages": [
                    row for row in observed_rows if row["source_kind"] == CORE_SOURCE_KIND
                ],
                "source_built_packages": [
                    row for row in observed_rows if row["source_kind"] == BUILD_SOURCE_KIND
                ],
                "source_built_authority_summary": {
                    "pending_ids": pending_source_built_ids,
                    "pending_count": len(pending_source_built_ids),
                    "locked_ids": [row["id"] for row in locked_source_built_rows],
                    "locked_count": len(locked_source_built_rows),
                    "all_locked_bytes_match": (
                        None
                        if not locked_source_built_rows
                        else all(
                            row["matches_candidate_byte_authority"] is True
                            for row in locked_source_built_rows
                        )
                    ),
                },
            }
            _write_json(staged_feed / OBSERVED_AUTHORITY_FILE_NAME, observed)
            observed_bytes = (staged_feed / OBSERVED_AUTHORITY_FILE_NAME).read_bytes()
            os.replace(staged_feed, feed)
            return hashlib.sha256(observed_bytes).hexdigest()
        inventory = _inventory_payload(lock, staged_feed, lock_sha256)
        _write_json(staged_feed / INVENTORY_FILE_NAME, inventory)
        os.replace(staged_feed, feed)
    return validate_feed_inventory(feed, lock, lock_sha256)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--feed", type=Path)
    parser.add_argument("--core-public-bundle", type=Path)
    parser.add_argument("--core-public-receipt", type=Path)
    parser.add_argument("--download-core-public-authority-directory", type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--print-version", action="store_true")
    parser.add_argument("--observe-package-authority", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    lock_path = (args.lock or repo_root / "eng/package-plane.lock.json").resolve()
    lock = load_lock(
        lock_path,
        allow_pending=args.observe_package_authority or args.print_version,
    )
    validate_build_recipe(repo_root, lock)
    lock_sha256 = _sha256(lock_path)
    if args.print_version:
        print(lock.package_version)
        return 0
    if args.feed is None:
        raise PackagePlaneError("--feed is required unless --print-version is used")
    feed = args.feed.resolve()
    if args.validate_only:
        digest = validate_feed_inventory(feed, lock, lock_sha256)
        print(
            f"hub-package-plane: ok ({len(lock.packages)} packages; "
            f"inventory {digest})"
        )
        return 0
    if lock.state != SEALED_LOCK_STATE and not args.observe_package_authority:
        raise PackagePlaneError(
            "package-plane v5 is not sealed; public authority will not be downloaded"
        )
    downloaded_authority_directory: Path | None = None
    if args.download_core_public_authority_directory is not None:
        if args.core_public_bundle is not None or args.core_public_receipt is not None:
            raise PackagePlaneError(
                "downloaded and caller-supplied Core authority are mutually exclusive"
            )
        downloaded_authority_directory = (
            args.download_core_public_authority_directory.resolve()
        )
        core_public_bundle, core_public_receipt = download_core_public_authority(
            downloaded_authority_directory, lock
        )
    else:
        if args.core_public_bundle is None:
            raise PackagePlaneError("--core-public-bundle is required")
        if args.core_public_receipt is None:
            raise PackagePlaneError("--core-public-receipt is required")
        core_public_bundle = args.core_public_bundle
        core_public_receipt = args.core_public_receipt
    try:
        digest = build_feed(
            lock,
            lock_sha256=lock_sha256,
            feed=feed,
            dotnet=args.dotnet,
            core_public_bundle=core_public_bundle,
            core_public_receipt=core_public_receipt,
            observe_package_authority=args.observe_package_authority,
        )
    finally:
        if downloaded_authority_directory is not None:
            cleanup_downloaded_core_authority(downloaded_authority_directory, lock)
    label = "observed authority" if args.observe_package_authority else "inventory"
    print(f"hub-package-plane: ok ({len(lock.packages)} packages; {label} {digest})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PackagePlaneError as exc:
        print(f"hub-package-plane: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
