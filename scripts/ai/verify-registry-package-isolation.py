#!/usr/bin/env python3
"""Run only the synthetic in-process Registry package tests after strict intake.

Controller runs this in a disposable complete Hub checkout. No listener,
production startup, deployment, release write, source fallback or account access.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REGISTRY_IDS = ("Chummer.Hub.Registry.Contracts", "Chummer.Run.Registry")
BASELINE_REGISTRY_COMMIT = "af9a7e19c3bf331e96411dfb8f9e7820a98cab29"
PROJECT = "Chummer.Run.Registry.PackageTests"


def load_module(root, name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), root / f"scripts/ai/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def selected_registry(lock, commit):
    rows = {row.package_id: row for row in lock.packages if row.package_id in REGISTRY_IDS}
    if set(rows) != set(REGISTRY_IDS) or any(row.commit != commit for row in rows.values()):
        raise ValueError("Both Registry packages must bind to the selected corrected source")
    if commit == BASELINE_REGISTRY_COMMIT:
        raise ValueError("Refusing runtime tests against the old vulnerable package source")
    return rows


def audit_assets(root, cache, rows, feed):
    for project in ("Chummer.Run.Api", PROJECT):
        payload = json.loads((root / project / "obj/project.assets.json").read_bytes())
        if {Path(p).resolve() for p in payload["packageFolders"]} != {cache.resolve()}:
            raise ValueError("Restore escaped the isolated package cache")
        for package_id, row in rows.items():
            library = payload["libraries"].get(f"{package_id}/{row.version}", {})
            if library.get("type") != "package":
                raise ValueError(f"{project} does not consume selected {package_id} as a package")
            expected_sha512 = base64.b64encode(hashlib.sha512((feed / f"{package_id}.{row.version}.nupkg").read_bytes()).digest()).decode()
            if library.get("sha512") != expected_sha512:
                raise ValueError(f"{project} restored different bytes for {package_id}")
            for key, item in payload["libraries"].items():
                if item.get("type") == "project" and key.split("/")[0] in REGISTRY_IDS:
                    raise ValueError("Registry sibling project fallback is forbidden")


def audit_loaded_files(root, rows, feed):
    result = {}
    for package_id, row in rows.items():
        with zipfile.ZipFile(feed / f"{package_id}.{row.version}.nupkg") as package:
            expected = hashlib.sha256(package.read(f"lib/net10.0/{package_id}.dll")).hexdigest()
        for project in ("Chummer.Run.Api", PROJECT):
            path = root / project / "bin/Release/net10.0" / f"{package_id}.dll"
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"{project} runtime DLL differs from admitted {package_id}")
        result[package_id] = expected
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--feed", required=True, type=Path)
    parser.add_argument("--core-feed", required=True, type=Path)
    parser.add_argument("--selected-registry-commit", required=True)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--prepare-locks", action="store_true", help="Restore new lock files for review only; no build or runtime test")
    args = parser.parse_args()
    root, feed, core_feed = args.repo_root.resolve(), args.feed.absolute(), args.core_feed.absolute()
    module = load_module(root, "bootstrap-hub-package-feed")
    verifier = load_module(root, "verify-hub-package-plane")
    lock_path = root / "eng/package-plane.lock.json"
    lock = module.load_lock(lock_path)
    module.validate_build_recipe(root, lock)
    rows = selected_registry(lock, args.selected_registry_commit)
    props = ET.parse(root / "Directory.Build.props").getroot()
    for name, package_id in (("ChummerHubRegistryContractsPackageVersion", REGISTRY_IDS[0]),
                             ("ChummerRunRegistryPackageVersion", REGISTRY_IDS[1])):
        if props.findtext(f".//{name}") != rows[package_id].version:
            raise ValueError("Hub default package version differs from the selected lock")
    lock_hash = module._sha256(lock_path)
    inventory_hash = module.validate_feed_inventory(feed, lock, lock_hash)
    module.validate_core_runtime_feed(core_feed, lock.core_runtime)
    work = args.work.absolute()
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    cache, cli_home, http_cache = work / "packages", work / "dotnet-cli", work / "http-cache"
    for path in (cache, cli_home, http_cache):
        path.mkdir(mode=0o700)
    env = module.isolated_environment(os.environ, cache, cli_home, http_cache)
    env["TMPDIR"] = str(work)
    module.validate_dotnet_toolchain(lock, args.dotnet, env=env)
    if module._run((args.dotnet, "--version"), cwd=root, env=env).strip() != lock.dotnet_sdk:
        raise ValueError("Selected SDK version differs from the package authority")
    config = work / "NuGet.Config"
    verifier._write_nuget_config(config, feed.resolve(), core_feed.resolve(), lock.approved_remote_source,
                                  (x.package_id for x in lock.packages), (x.package_id for x in lock.core_runtime.packages))
    project = root / PROJECT / f"{PROJECT}.csproj"
    common = ["-m:1", "-p:ChummerUseLocalCompatibilityTree=false", "-p:ChummerPackageFeed=",
              f"-p:RestorePackagesPath={cache}", "-p:UseSharedCompilation=false",
              "-p:TargetFramework=net10.0", "-p:TargetFrameworks=net10.0", f"-p:ChummerRegistrySelectedCommit={args.selected_registry_commit}"]
    before_locks = {str(p.relative_to(root)): module._sha256(p) for p in root.glob("*/packages.lock.json")}
    command = [args.dotnet, "restore", str(project), "--configfile", str(config), "--packages", str(cache),
               "--no-cache", "--nologo", *common,
               f"-p:RestoreLockedMode={'false' if args.prepare_locks else 'true'}"]
    if args.prepare_locks:
        command.append("--force-evaluate")
    subprocess.run(command, cwd=root, env=env, check=True)
    audit_assets(root, cache, rows, feed)
    if args.prepare_locks:
        print("Lock preparation only; review generated packages.lock.json files before the locked verification run")
        return
    subprocess.run([args.dotnet, "build", str(project), "-c", "Release", "--no-restore", "--nologo", *common],
                   cwd=root, env=env, check=True)
    assemblies = audit_loaded_files(root, rows, feed)
    subprocess.run([args.dotnet, "test", str(project), "-c", "Release", "--no-build", "--no-restore", "--nologo",
                    "--filter", "FullyQualifiedName~RegistryReadIsolationTests", "--results-directory", str(work),
                    "--logger", "trx;LogFileName=registry-package-isolation.trx", *common], cwd=root, env=env, check=True)
    counts = verifier._trx_counts(work / "registry-package-isolation.trx")
    verifier._require_passing_tests(counts, "Registry package isolation")
    if counts["passed"] != 12:
        raise ValueError("Expected all 12 synthetic context integration cases")
    if before_locks != {str(p.relative_to(root)): module._sha256(p) for p in root.glob("*/packages.lock.json")}:
        raise ValueError("Locked verification changed a consumer package lock")
    if lock_hash != module._sha256(lock_path) or inventory_hash != module.validate_feed_inventory(feed, lock, lock_hash):
        raise ValueError("Package authority changed during verification")
    module.validate_core_runtime_feed(core_feed, lock.core_runtime)
    if assemblies != audit_loaded_files(root, rows, feed):
        raise ValueError("Runtime assemblies changed during tests")
    (work / "result.json").write_text(json.dumps({
        "status": "pass", "scope": "packaged Hub controller/service/store synthetic integration",
        "registry_commit": args.selected_registry_commit, "package_lock_sha256": lock_hash,
        "inventory_sha256": inventory_hash, "assembly_sha256": assemblies, "tests": counts,
        "live_http": False, "production_closure": False, "published": False,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
