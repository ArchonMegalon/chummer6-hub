#!/usr/bin/env python3
"""Build Hub's external package plane from exact owner commits.

The feed is always rebuilt from clean, detached checkouts. A nupkg with valid
metadata is not trusted unless its bytes match the inventory written by this
same build transaction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


LOCK_CONTRACT = "chummer-hub.package-plane-lock/v3"
INVENTORY_CONTRACT = "chummer-hub.external-package-inventory/v2"
INVENTORY_FILE_NAME = "chummer-hub-packages.inventory.json"
EXPECTED_PACKAGE_IDS = (
    "Chummer.Engine.Contracts",
    "Chummer.Hub.Registry.Contracts",
    "Chummer.Run.Registry",
)
EXPECTED_INTERNAL_DEPENDENCIES = {
    "Chummer.Engine.Contracts": (),
    "Chummer.Hub.Registry.Contracts": (),
    "Chummer.Run.Registry": ("Chummer.Hub.Registry.Contracts",),
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
    r"^package/services/metadata/core-properties/[0-9a-f]{32}\.psmdcp$"
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
    nupkg_sha256: str
    nupkg_size_bytes: int


@dataclass(frozen=True)
class PackagePlaneLock:
    dotnet_sdk: str
    dotnet_install_url: str
    dotnet_install_sha256: str
    toolchain_sha256: Mapping[str, str]
    package_version: str
    approved_remote_source: str
    build_recipe_path: str
    build_recipe_sha256: str
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
        "dotnet_sdk",
        "dotnet_install",
        "toolchain_sha256",
        "package_version",
        "approved_remote_source",
        "build_recipe",
        "packages",
    }
    if not isinstance(payload, dict) or set(payload) != expected_top_level:
        raise PackagePlaneError("package-plane lock must contain the exact v3 fields")
    if payload.get("contract") != LOCK_CONTRACT:
        raise PackagePlaneError(f"package-plane lock contract must be {LOCK_CONTRACT}")
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
        nupkg_sha256 = _required_string(row, "nupkg_sha256")
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
        if SHA256_PATTERN.fullmatch(nupkg_sha256) is None:
            raise PackagePlaneError(f"invalid nupkg SHA256 for {package_id}")
        if (
            not isinstance(nupkg_size_bytes, int)
            or isinstance(nupkg_size_bytes, bool)
            or nupkg_size_bytes <= 0
        ):
            raise PackagePlaneError(f"invalid nupkg size for {package_id}")
        authority = checkout_authority.setdefault(
            checkout_directory, (repository, commit)
        )
        if authority != (repository, commit):
            raise PackagePlaneError(
                "one checkout_directory cannot name multiple source authorities"
            )
        packages.append(
            PackageSpec(
                package_id,
                version,
                repository,
                commit,
                checkout_directory,
                project,
                license_type,
                license_value,
                license_sha256,
                nupkg_sha256,
                nupkg_size_bytes,
            )
        )
    ids = tuple(spec.package_id for spec in packages)
    if ids != EXPECTED_PACKAGE_IDS:
        raise PackagePlaneError(
            "packages must contain the exact ordered Hub package plane: "
            + ", ".join(EXPECTED_PACKAGE_IDS)
        )
    return PackagePlaneLock(
        dotnet_sdk,
        dotnet_install_url,
        dotnet_install_sha256,
        toolchain_sha256,
        package_version,
        approved_remote_source,
        build_recipe_path,
        build_recipe_sha256,
        tuple(packages),
    )


def load_lock(path: Path) -> PackagePlaneLock:
    try:
        return validate_lock_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagePlaneError(f"unable to read package-plane lock {path}: {exc}") from exc


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
    temporary_root = cli_home.parent / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    result.update(
        {
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


def package_build_properties(
    lock: PackagePlaneLock,
    spec: PackageSpec,
    checkout: Path,
    package_root: Path,
) -> tuple[str, ...]:
    normalized_source_root = f"/_/src/{spec.checkout_directory}"
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


def validate_package(
    feed: Path,
    spec: PackageSpec,
    dependency_versions: Mapping[str, str] | None = None,
) -> Path:
    version = spec.version
    path = _package_path(feed, spec.package_id, version)
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            _validate_payload_names(names, spec)
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
    if observed_size != spec.nupkg_size_bytes or observed_sha256 != spec.nupkg_sha256:
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
                "file_name": path.name,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "contract": INVENTORY_CONTRACT,
        "package_plane_lock_sha256": lock_sha256,
        "package_version": lock.package_version,
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
) -> str:
    if feed.exists() or feed.is_symlink():
        raise PackagePlaneError("feed destination must start absent; package reuse is forbidden")
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
        validate_dotnet_toolchain(lock, dotnet, env=env)
        nuget_config = root / "NuGet.Config"
        nuget_config.write_text(
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
            "<configuration><packageSources><clear />"
            f"<add key=\"nuget.org\" value=\"{lock.approved_remote_source}\" protocolVersion=\"3\" />"
            "</packageSources></configuration>\n",
            encoding="utf-8",
        )
        repositories: dict[str, PackageSpec] = {}
        for spec in lock.packages:
            repositories.setdefault(spec.checkout_directory, spec)
        for spec in repositories.values():
            acquire_source(source_root, spec, env=env)
        for spec in lock.packages:
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
            _run(
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
                cwd=checkout,
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
            )
        inventory = _inventory_payload(lock, staged_feed, lock_sha256)
        _write_json(staged_feed / INVENTORY_FILE_NAME, inventory)
        os.replace(staged_feed, feed)
    return validate_feed_inventory(feed, lock, lock_sha256)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--feed", type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--print-version", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    lock_path = (args.lock or repo_root / "eng/package-plane.lock.json").resolve()
    lock = load_lock(lock_path)
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
    else:
        digest = build_feed(lock, lock_sha256=lock_sha256, feed=feed, dotnet=args.dotnet)
    print(f"hub-package-plane: ok ({len(lock.packages)} packages; inventory {digest})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PackagePlaneError as exc:
        print(f"hub-package-plane: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
