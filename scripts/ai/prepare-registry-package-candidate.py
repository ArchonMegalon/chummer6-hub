#!/usr/bin/env python3
"""Controller-only local preparation; never publish or overwrite source authority.

Build using the existing locked recipe, or validate and reuse already observed
canonical bytes. Selection of the final reviewed Registry commit is an input,
not something this script can infer from a branch name or a passing read test.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path


def load_bootstrap(root):
    spec = importlib.util.spec_from_file_location("registry_candidate_bootstrap", root / "scripts/ai/bootstrap-hub-package-feed.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def select(module, lock, registry_commit, hub_commit, version):
    if not all(module.SHA_PATTERN.fullmatch(x) for x in (registry_commit, hub_commit)):
        raise ValueError("Select exact reviewed source commits, not branches")
    if not module.VERSION_PATTERN.fullmatch(version):
        raise ValueError("Select an exact unused release version")
    if any(row.version == version for row in lock.packages):
        raise ValueError("Never replace bytes under an existing locked package version")
    if registry_commit == lock.packages[0].commit:
        raise ValueError("Registry source must include the accepted correction")
    # In-memory historical digest fields are not used as candidate authority.
    # build_feed(observe_package_authority=True) does not enforce them. No new
    # lock is serialized until each candidate's actual bytes have been measured.
    return dataclasses.replace(lock, package_version=version, packages=tuple(
        dataclasses.replace(row, version=version, commit=(registry_commit if row.checkout_directory == "chummer-hub-registry" else hub_commit))
        for row in lock.packages
    ))


def local_source_acquirer(module, roots):
    def acquire(source_root, row, *, env):
        original = roots[row.checkout_directory].resolve()
        origin = module._run(("git", "remote", "get-url", "origin"), cwd=original, env=env).strip()
        if origin != row.repository:
            raise ValueError("Local source origin differs from the immutable package authority")
        resolved = module._run(("git", "rev-parse", row.commit + "^{commit}"), cwd=original, env=env).strip()
        if resolved != row.commit:
            raise ValueError("Local source does not contain the selected exact commit")
        checkout = source_root / row.checkout_directory
        if checkout.exists() or checkout.is_symlink():
            raise ValueError("Private source checkout must start absent")
        module._run(("git", "init", str(checkout)), env=env)
        module._run(("git", "remote", "add", "origin", row.repository), cwd=checkout, env=env)
        # Fetch immutable Git objects, never a dirty source-tree copy or hardlinks.
        module._run(("git", "fetch", "--no-tags", "--depth=1", str(original), row.commit), cwd=checkout, env=env)
        module._run(("git", "checkout", "--detach", row.commit), cwd=checkout, env=env)
        module.validate_checkout(checkout, row, env=env)
        return checkout
    return acquire


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--registry-commit", required=True)
    parser.add_argument("--hub-producer-commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--observed-feed", type=Path)
    inputs.add_argument("--build", action="store_true")
    parser.add_argument("--core-feed", type=Path)
    parser.add_argument("--registry-source", type=Path)
    parser.add_argument("--hub-source", type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    module = load_bootstrap(root)
    source_lock = root / "eng/package-plane.lock.json"
    lock = module.load_lock(source_lock)
    module.validate_build_recipe(root, lock)
    selected = select(module, lock, args.registry_commit, args.hub_producer_commit, args.version)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output must start absent; retain failed attempts for review")
    output.mkdir(mode=0o700, parents=True)
    observed = args.observed_feed
    if args.build:
        if args.core_feed is None or args.registry_source is None or args.hub_source is None:
            raise ValueError("Build requires exact Core feed and both local source repositories")
        module.acquire_source = local_source_acquirer(module, {
            "chummer-hub-registry": args.registry_source,
            "chummer-run-services": args.hub_source,
        })
        observed = output / "observed"
        module.build_feed(selected, lock_sha256=module._sha256(source_lock), feed=observed,
                          dotnet=args.dotnet, core_feed=args.core_feed,
                          observe_package_authority=True)
    if observed.is_symlink() or not observed.is_dir():
        raise ValueError("Observed feed must be a real directory")
    expected = {f"{row.package_id}.{row.version}.nupkg" for row in selected.packages}
    allowed = expected | {module.OBSERVED_AUTHORITY_FILE_NAME, module.INVENTORY_FILE_NAME}
    if not expected.issubset({p.name for p in observed.iterdir()}) or any(p.name not in allowed for p in observed.iterdir()):
        raise ValueError("Observed feed must contain exactly the selected four packages and optional receipts")
    # Validate private copies so changing input files cannot change measured outputs.
    feed = output / "feed"
    feed.mkdir(mode=0o700)
    for name in sorted(expected):
        original = observed / name
        if original.is_symlink() or not original.is_file():
            raise ValueError("Package input must be a regular non-symlink file")
        shutil.copyfile(original, feed / name)
    versions = {row.package_id: row.version for row in (*selected.core_runtime.packages, *selected.packages)}
    measured = []
    for row in selected.packages:
        path = module.validate_package(feed, row, versions, enforce_locked_bytes=False)
        measured.append(dataclasses.replace(row, nupkg_sha256=module._sha256(path), nupkg_size_bytes=path.stat().st_size))
    selected = dataclasses.replace(selected, packages=tuple(measured))
    payload = json.loads(source_lock.read_text())
    payload["package_version"] = args.version
    for row, measured_row in zip(payload["packages"], measured, strict=True):
        row.update(version=measured_row.version, commit=measured_row.commit,
                   nupkg_sha256=measured_row.nupkg_sha256, nupkg_size_bytes=measured_row.nupkg_size_bytes)
    module.validate_lock_payload(payload)
    proposed = output / "package-plane.lock.json"
    proposed.write_text(json.dumps(payload, indent=2) + "\n")
    inventory = module._inventory_payload(selected, feed, module._sha256(proposed))
    module._write_json(feed / module.INVENTORY_FILE_NAME, inventory)
    module.validate_feed_inventory(feed, selected, module._sha256(proposed))
    props = (root / "Directory.Build.props").read_text(encoding="utf-8-sig")
    for name in ("ChummerPackagePlaneVersion", "ChummerHubRegistryContractsPackageVersion", "ChummerRunRegistryPackageVersion"):
        props, count = re.subn(rf"(<{name}\b[^>]*>)[^<]+(</{name}>)", rf"\g<1>{args.version}\g<2>", props)
        if count != 1:
            raise ValueError(f"Expected one version property: {name}")
    (output / "Directory.Build.props").write_text(props)
    (output / "PREPARATION.json").write_text(json.dumps({
        "status": "prepared-for-controller-review", "published": False,
        "runtime_tests_executed": False, "source_lock_sha256": module._sha256(source_lock),
        "proposed_lock_sha256": module._sha256(proposed),
        "registry_commit": args.registry_commit, "hub_producer_commit": args.hub_producer_commit,
        "reused_observed_bytes": not args.build,
        "preparation_script_sha256": module._sha256(Path(__file__)),
        "source_acquisition": "existing-byte-intake" if not args.build else "exact-local-git-objects-canonical-origin",
    }, indent=2) + "\n")
    print(f"Prepared actual package bytes and proposed authority at {output}; no publication or behavior claim")


if __name__ == "__main__":
    main()
