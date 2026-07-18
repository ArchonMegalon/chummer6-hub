#!/usr/bin/env python3
"""Verify Hub from a fresh checkout with only locked external packages."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


INVENTORY_NAME = "chummer-hub-packages.inventory.json"
RECEIPT_CONTRACT = "chummer-hub.no-siblings-package-plane/v1"
HUB_REPOSITORY = "https://github.com/ArchonMegalon/chummer6-hub.git"
CONTRACT_PROJECTS = (
    "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj",
    "Chummer.Control.Contracts/Chummer.Control.Contracts.csproj",
    "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj",
    "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj",
    "Chummer.World.Contracts/Chummer.World.Contracts.csproj",
)
LOCKED_PROJECTS = (
    "Chummer.Campaign.Contracts",
    "Chummer.Control.Contracts",
    "Chummer.Play.Contracts",
    "Chummer.Run.Contracts",
    "Chummer.World.Contracts",
    "Chummer.Run.Api",
    "Chummer.Run.Api.Tests",
)


class VerificationError(RuntimeError):
    """Raised when the no-siblings package-plane proof fails."""


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
        raise VerificationError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{result.stdout}"
        )
    sys.stdout.write(result.stdout)
    return result.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_bootstrap(repo_root: Path):
    path = repo_root / "scripts" / "ai" / "bootstrap-hub-package-feed.py"
    spec = importlib.util.spec_from_file_location("hub_package_plane_bootstrap", path)
    if spec is None or spec.loader is None:
        raise VerificationError("unable to load package-plane bootstrap")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _clean_commit(repo_root: Path) -> str:
    commit = _run(("git", "rev-parse", "HEAD"), cwd=repo_root).strip()
    if len(commit) != 40:
        raise VerificationError("Hub checkout does not resolve to one exact commit")
    status = _run(
        ("git", "status", "--porcelain=v1", "--untracked-files=all"), cwd=repo_root
    ).strip()
    if status:
        raise VerificationError(f"Hub source checkout must be clean:\n{status}")
    return commit


def _write_nuget_config(path: Path, feed: Path, remote: str) -> None:
    exact_patterns = "".join(
        f'<package pattern="{package_id}" />'
        for package_id in (
            "Chummer.Engine.Contracts",
            "Chummer.Hub.Registry.Contracts",
            "Chummer.Run.Registry",
        )
    )
    path.write_text(
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
        "<configuration>\n"
        "  <packageSources><clear />"
        f'<add key="locked-chummer" value="{feed}" />'
        f'<add key="nuget.org" value="{remote}" protocolVersion="3" />'
        "</packageSources>\n"
        "  <packageSourceMapping>\n"
        f'    <packageSource key="locked-chummer">{exact_patterns}</packageSource>\n'
        '    <packageSource key="nuget.org"><package pattern="*" /></packageSource>\n'
        "  </packageSourceMapping>\n"
        "</configuration>\n",
        encoding="utf-8",
    )


def _audit_assets(
    consumer: Path, package_root: Path, package_version: str
) -> int:
    asset_paths = (
        consumer / "Chummer.Campaign.Contracts/obj/project.assets.json",
        consumer / "Chummer.Run.Contracts/obj/project.assets.json",
        consumer / "Chummer.Run.Api/obj/project.assets.json",
        consumer / "Chummer.Run.Api.Tests/obj/project.assets.json",
    )
    expected_root = package_root.resolve()
    observed_libraries: dict[str, dict] = {}
    for path in asset_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        roots = [Path(value).resolve() for value in (payload.get("packageFolders") or {})]
        if roots != [expected_root]:
            raise VerificationError(f"ambient NuGet package root detected in {path.name}")
        observed_libraries.update(payload.get("libraries") or {})
        for log in payload.get("logs") or []:
            if str(log.get("level", "")).lower() == "error" or log.get("code") == "NU1605":
                raise VerificationError(f"restore graph error in {path.name}: {log}")
    for package_id in (
        "Chummer.Engine.Contracts",
        "Chummer.Hub.Registry.Contracts",
        "Chummer.Run.Registry",
    ):
        identity = f"{package_id}/{package_version}"
        metadata = observed_libraries.get(identity)
        if not isinstance(metadata, dict) or metadata.get("type") != "package":
            raise VerificationError(f"locked package was not restored as a package: {identity}")
    return len(asset_paths)


def _audit_package_locks(consumer: Path, package_version: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for project_name in LOCKED_PROJECTS:
        path = consumer / project_name / "packages.lock.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1 or not isinstance(payload.get("dependencies"), dict):
            raise VerificationError(f"invalid NuGet lock contract for {project_name}")
        package_count = 0
        for framework, dependencies in payload["dependencies"].items():
            if not isinstance(framework, str) or not isinstance(dependencies, dict):
                raise VerificationError(f"invalid locked framework graph for {project_name}")
            for package_id, metadata in dependencies.items():
                if not isinstance(metadata, dict):
                    raise VerificationError(f"invalid locked dependency {package_id}")
                if metadata.get("type") == "Project":
                    continue
                package_count += 1
                if not isinstance(metadata.get("resolved"), str) or not isinstance(
                    metadata.get("contentHash"), str
                ):
                    raise VerificationError(
                        f"locked package lacks resolved version/content hash: {package_id}"
                    )
                if package_id in {
                    "Chummer.Engine.Contracts",
                    "Chummer.Hub.Registry.Contracts",
                    "Chummer.Run.Registry",
                } and metadata["resolved"] != package_version:
                    raise VerificationError(f"owner package lock drift: {package_id}")
        rows.append(
            {
                "project": project_name,
                "sha256": _sha256(path),
                "package_count": package_count,
            }
        )
    return rows


def _audit_contract_packages(
    consumer: Path, output: Path, commit: str, version: str, dotnet: str, common: tuple[str, ...], env: Mapping[str, str]
) -> list[dict[str, object]]:
    license_bytes = (consumer / "LICENSE").read_bytes()
    rows = []
    for relative in CONTRACT_PROJECTS:
        project = consumer / relative
        _run(
            (
                dotnet,
                "pack",
                str(project),
                "--configuration",
                "Release",
                "--no-build",
                "--no-restore",
                "--nologo",
                "-m:1",
                f"-p:PackageVersion={version}",
                f"-p:Version={version}",
                f"-p:RepositoryCommit={commit}",
                f"-p:RepositoryUrl={HUB_REPOSITORY}",
                "-p:PublishRepositoryUrl=true",
                *common,
                "--output",
                str(output),
            ),
            cwd=consumer,
            env=env,
        )
        package_id = project.stem
        path = output / f"{package_id}.{version}.nupkg"
        with zipfile.ZipFile(path) as archive:
            if archive.read("LICENSE") != license_bytes:
                raise VerificationError(f"package license bytes drifted for {package_id}")
            nuspec = ET.fromstring(archive.read(f"{package_id}.nuspec"))
            licenses = [
                element
                for element in nuspec.iter()
                if element.tag.rsplit("}", 1)[-1] == "license"
            ]
            if len(licenses) != 1 or licenses[0].get("type") != "file" or (licenses[0].text or "").strip() != "LICENSE":
                raise VerificationError(f"package license metadata drifted for {package_id}")
        rows.append(
            {
                "id": package_id,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return rows


def _trx_counts(path: Path) -> dict[str, int]:
    root = ET.fromstring(path.read_text(encoding="utf-8-sig"))
    counters = next(
        element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "Counters"
    )
    return {
        key: int(counters.get(key, "0"))
        for key in ("total", "executed", "passed", "failed", "error", "timeout", "aborted")
    }


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def verify(repo_root: Path, receipt_path: Path, dotnet: str) -> None:
    repo_root = repo_root.resolve()
    commit = _clean_commit(repo_root)
    bootstrap = _load_bootstrap(repo_root)
    lock_path = repo_root / "eng/package-plane.lock.json"
    lock = bootstrap.load_lock(lock_path)
    lock_sha = _sha256(lock_path)
    with tempfile.TemporaryDirectory(prefix="chummer-hub-no-siblings-") as temporary:
        root = Path(temporary)
        feed = root / "feed"
        consumer_parent = root / "consumer"
        consumer = consumer_parent / "chummer6-hub"
        package_root = root / "packages"
        cli_home = root / "dotnet-cli"
        http_cache = root / "nuget-http-cache"
        results = root / "results"
        contract_output = root / "contract-packages"
        for directory in (consumer_parent, package_root, cli_home, http_cache, results, contract_output):
            directory.mkdir(parents=True, exist_ok=True)
        bootstrap.build_feed(
            lock,
            lock_sha256=lock_sha,
            feed=feed,
            dotnet=dotnet,
        )
        inventory_path = feed / INVENTORY_NAME
        inventory_sha = bootstrap.validate_feed_inventory(feed, lock, lock_sha)
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

        _run(("git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(repo_root), str(consumer)))
        _run(("git", "checkout", "--quiet", "--detach", commit), cwd=consumer)
        if _run(("git", "rev-parse", "HEAD"), cwd=consumer).strip() != commit:
            raise VerificationError("isolated Hub checkout commit mismatch")
        if _run(("git", "status", "--porcelain=v1", "--untracked-files=all"), cwd=consumer).strip():
            raise VerificationError("isolated Hub checkout is dirty before restore")
        for forbidden in (
            consumer_parent / "chummer-core-engine",
            consumer_parent / "chummer-hub-registry",
            consumer_parent / "fleet",
        ):
            if forbidden.exists():
                raise VerificationError(f"forbidden sibling exists: {forbidden.name}")

        nuget_config = root / "NuGet.Config"
        _write_nuget_config(nuget_config, feed, lock.approved_remote_source)
        env = bootstrap.isolated_environment(os.environ, package_root, cli_home, http_cache)
        common = (
            "-p:ChummerUseLocalCompatibilityTree=false",
            f"-p:ChummerPackagePlaneVersion={lock.package_version}",
            "-p:ChummerPackageFeed=",
            "-p:RestoreAdditionalProjectSources=",
            f"-p:RestorePackagesPath={package_root}",
            "-p:UseSharedCompilation=false",
            "-p:TargetFramework=net10.0",
        )
        test_project = consumer / "Chummer.Run.Api.Tests/Chummer.Run.Api.Tests.csproj"
        _run(
            (
                dotnet,
                "restore",
                str(test_project),
                "--configfile",
                str(nuget_config),
                "--packages",
                str(package_root),
                "--locked-mode",
                "--no-cache",
                "--nologo",
                "-m:1",
                *common,
            ),
            cwd=consumer,
            env=env,
        )
        _run(
            (
                dotnet,
                "build",
                str(consumer / "Chummer.Run.Api/Chummer.Run.Api.csproj"),
                "--configuration",
                "Release",
                "--no-restore",
                "--nologo",
                "-m:1",
                *common,
            ),
            cwd=consumer,
            env=env,
        )
        _run(
            (
                dotnet,
                "test",
                str(test_project),
                "--configuration",
                "Release",
                "--framework",
                "net10.0",
                "--no-restore",
                "--nologo",
                "-m:1",
                "--logger",
                "trx;LogFileName=package-plane.trx",
                "--results-directory",
                str(results),
                *common,
            ),
            cwd=consumer,
            env=env,
        )
        asset_count = _audit_assets(consumer, package_root, lock.package_version)
        package_locks = _audit_package_locks(consumer, lock.package_version)
        contract_packages = _audit_contract_packages(
            consumer, contract_output, commit, lock.package_version, dotnet, common, env
        )
        test_counts = _trx_counts(results / "package-plane.trx")
        if test_counts["failed"] or test_counts["error"] or test_counts["timeout"] or test_counts["aborted"]:
            raise VerificationError(f"package-plane tests did not pass: {test_counts}")
        payload: dict[str, object] = {
            "contract": RECEIPT_CONTRACT,
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "status": "pass",
            "hub_commit": commit,
            "package_plane_lock_sha256": lock_sha,
            "package_inventory_sha256": inventory_sha,
            "package_version": lock.package_version,
            "dotnet_sdk": lock.dotnet_sdk,
            "source_authorities": [
                {"id": spec.package_id, "repository": spec.repository, "commit": spec.commit}
                for spec in lock.packages
            ],
            "external_packages": [
                {"id": row["id"], "sha256": row["sha256"], "size_bytes": row["size_bytes"]}
                for row in inventory["packages"]
            ],
            "hub_contract_packages": contract_packages,
            "no_sibling_directories": True,
            "isolated_package_cache": True,
            "package_source_mapping": {
                "locked_external_ids": "locked-chummer",
                "other": lock.approved_remote_source,
            },
            "asset_files_audited": asset_count,
            "package_lock_files": package_locks,
            "locked_mode_restore": True,
            "api_build": "pass",
            "api_tests": test_counts,
            "contract_pack_license_gate": "pass",
        }
        _atomic_json(receipt_path.resolve(), payload)
    print(f"hub-no-siblings-package-plane: ok ({test_counts['passed']} tests)")
    print(f"receipt: {receipt_path.resolve()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--dotnet", default="dotnet")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    verify(args.repo_root, args.receipt, args.dotnet)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (VerificationError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"hub-no-siblings-package-plane: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
