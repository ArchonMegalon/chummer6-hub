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


LOCK_CONTRACT = "chummer-hub.package-plane-lock/v1"
INVENTORY_CONTRACT = "chummer-hub.external-package-inventory/v1"
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


class PackagePlaneError(RuntimeError):
    """Raised when immutable package-plane authority cannot be proven."""


@dataclass(frozen=True)
class PackageSpec:
    package_id: str
    repository: str
    commit: str
    checkout_directory: str
    project: str
    license_type: str
    license_value: str
    license_sha256: str | None


@dataclass(frozen=True)
class PackagePlaneLock:
    dotnet_sdk: str
    package_version: str
    approved_remote_source: str
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
    if not isinstance(payload, dict) or payload.get("contract") != LOCK_CONTRACT:
        raise PackagePlaneError(f"package-plane lock contract must be {LOCK_CONTRACT}")
    dotnet_sdk = _required_string(payload, "dotnet_sdk")
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", dotnet_sdk) is None:
        raise PackagePlaneError("dotnet_sdk must be an exact three-part version")
    package_version = _required_string(payload, "package_version")
    if VERSION_PATTERN.fullmatch(package_version) is None:
        raise PackagePlaneError("package_version must be one exact SemVer value")
    approved_remote_source = _required_string(payload, "approved_remote_source")
    if approved_remote_source != "https://api.nuget.org/v3/index.json":
        raise PackagePlaneError("approved_remote_source must be the HTTPS NuGet.org v3 index")

    rows = payload.get("packages")
    if not isinstance(rows, list):
        raise PackagePlaneError("packages must be a list")
    packages: list[PackageSpec] = []
    checkout_authority: dict[str, tuple[str, str]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PackagePlaneError(f"packages[{index}] must be an object")
        package_id = _required_string(row, "id")
        repository = _required_string(row, "repository")
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
        if not HTTPS_GITHUB_PATTERN.fullmatch(repository):
            raise PackagePlaneError("repository must be an allowlisted HTTPS GitHub URL")
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
                repository,
                commit,
                checkout_directory,
                project,
                license_type,
                license_value,
                license_sha256,
            )
        )
    ids = tuple(spec.package_id for spec in packages)
    if ids != EXPECTED_PACKAGE_IDS:
        raise PackagePlaneError(
            "packages must contain the exact ordered Hub package plane: "
            + ", ".join(EXPECTED_PACKAGE_IDS)
        )
    return PackagePlaneLock(
        dotnet_sdk, package_version, approved_remote_source, tuple(packages)
    )


def load_lock(path: Path) -> PackagePlaneLock:
    try:
        return validate_lock_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagePlaneError(f"unable to read package-plane lock {path}: {exc}") from exc


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
    blocked = {
        "dotnet_cli_home",
        "nuget_packages",
        "nuget_http_cache_path",
        "restorepackagespath",
        "restoreadditionalprojectsources",
        "chummer_workspace_root",
        "chummer_package_feed",
        "chummeruselocalcompatibilitytree",
    }
    result = {key: value for key, value in base.items() if key.lower() not in blocked}
    result.update(
        {
            "DOTNET_CLI_HOME": str(cli_home),
            "NUGET_PACKAGES": str(package_root),
            "NUGET_HTTP_CACHE_PATH": str(http_cache),
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return result


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
    matches = [
        candidate
        for candidate in feed.iterdir()
        if candidate.is_file() and candidate.name.lower() == expected
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


def validate_package(feed: Path, spec: PackageSpec, version: str) -> Path:
    path = _package_path(feed, spec.package_id, version)
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            _validate_payload_names(names, spec)
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
    expected_dependencies = tuple(
        sorted((package_id, version) for package_id in EXPECTED_INTERNAL_DEPENDENCIES[spec.package_id])
    )
    if _internal_dependencies(root) != expected_dependencies:
        raise PackagePlaneError(f"internal dependency drift in {path.name}")
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
    for spec in lock.packages:
        path = validate_package(feed, spec, lock.package_version)
        packages.append(
            {
                "id": spec.package_id,
                "version": lock.package_version,
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


def validate_feed_inventory(
    feed: Path, lock: PackagePlaneLock, lock_sha256: str
) -> str:
    inventory_path = feed / INVENTORY_FILE_NAME
    try:
        inventory_bytes = inventory_path.read_bytes()
        payload = json.loads(inventory_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagePlaneError(f"unable to read package inventory: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("contract") != INVENTORY_CONTRACT:
        raise PackagePlaneError(f"package inventory contract must be {INVENTORY_CONTRACT}")
    if payload.get("package_plane_lock_sha256") != lock_sha256:
        raise PackagePlaneError("package inventory does not bind the exact lock bytes")
    if payload.get("package_version") != lock.package_version:
        raise PackagePlaneError("package inventory version does not match the lock")
    rows = payload.get("packages")
    if not isinstance(rows, list) or len(rows) != len(lock.packages):
        raise PackagePlaneError("package inventory must contain the exact locked set")
    for spec, row in zip(lock.packages, rows, strict=True):
        if not isinstance(row, dict):
            raise PackagePlaneError(f"invalid inventory row for {spec.package_id}")
        expected = {
            "id": spec.package_id,
            "version": lock.package_version,
            "repository": spec.repository,
            "commit": spec.commit,
            "project": spec.project,
            "file_name": f"{spec.package_id}.{lock.package_version}.nupkg",
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
        path = validate_package(feed, spec, lock.package_version)
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
            common_properties = (
                f"-p:PackageVersion={lock.package_version}",
                f"-p:Version={lock.package_version}",
                f"-p:RepositoryCommit={spec.commit}",
                f"-p:RepositoryUrl={spec.repository}",
                "-p:PublishRepositoryUrl=true",
                "-p:ContinuousIntegrationBuild=true",
                "-p:UseSharedCompilation=false",
                f"-p:RestorePackagesPath={package_root}",
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
            validate_checkout(checkout, spec, env=env)
            validate_package(staged_feed, spec, lock.package_version)
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
