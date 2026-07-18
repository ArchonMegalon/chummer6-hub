from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "ai" / "bootstrap-hub-package-feed.py"
LOCK_PATH = ROOT / "eng" / "package-plane.lock.json"
PACKAGE_VERSION = "0.0.0-packageplane.20260718.1"
CONTRACT_PROJECTS = (
    "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj",
    "Chummer.Control.Contracts/Chummer.Control.Contracts.csproj",
    "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj",
    "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj",
    "Chummer.World.Contracts/Chummer.World.Contracts.csproj",
)
PACKAGE_PLANE_PROJECTS = (
    "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj",
    "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj",
    "Chummer.Run.Api/Chummer.Run.Api.csproj",
    "Chummer.Run.Api.Tests/Chummer.Run.Api.Tests.csproj",
    "Chummer.Tests/Chummer.Tests.csproj",
)


def load_module():
    spec = importlib.util.spec_from_file_location("hub_package_plane", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _parent_map(root: ElementTree.Element) -> dict[ElementTree.Element, ElementTree.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def test_lock_pins_exact_owner_commits_and_package_version() -> None:
    module = load_module()
    lock = module.load_lock(LOCK_PATH)
    assert lock.package_version == PACKAGE_VERSION
    assert [spec.package_id for spec in lock.packages] == [
        "Chummer.Engine.Contracts",
        "Chummer.Hub.Registry.Contracts",
        "Chummer.Run.Registry",
    ]
    assert all(len(spec.commit) == 40 for spec in lock.packages)
    assert all(spec.repository.startswith("https://github.com/ArchonMegalon/") for spec in lock.packages)


@pytest.mark.parametrize(
    "bad_commit",
    ["main", "refs/heads/main", "v1.0.0", "A" * 40, "0" * 39],
)
def test_lock_rejects_branch_tag_or_noncanonical_commit(bad_commit: str) -> None:
    module = load_module()
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    payload["packages"][0]["commit"] = bad_commit
    with pytest.raises(module.PackagePlaneError, match="40-character SHA"):
        module.validate_lock_payload(payload)


def test_isolated_environment_overrides_ambient_cache_and_sibling_inputs(
    tmp_path: Path,
) -> None:
    module = load_module()
    poisoned = {
        "PATH": os.environ.get("PATH", ""),
        "NUGET_PACKAGES": "/ambient/packages",
        "DOTNET_CLI_HOME": "/ambient/dotnet",
        "NUGET_HTTP_CACHE_PATH": "/ambient/http",
        "RestorePackagesPath": "/ambient/restore",
        "RestoreAdditionalProjectSources": "/ambient/feed",
        "CHUMMER_WORKSPACE_ROOT": "/ambient/siblings",
        "CHUMMER_PACKAGE_FEED": "/ambient/packages",
        "ChummerUseLocalCompatibilityTree": "true",
    }
    result = module.isolated_environment(
        poisoned,
        tmp_path / "packages",
        tmp_path / "cli",
        tmp_path / "http",
    )
    assert result["NUGET_PACKAGES"] == str(tmp_path / "packages")
    assert result["DOTNET_CLI_HOME"] == str(tmp_path / "cli")
    assert result["NUGET_HTTP_CACHE_PATH"] == str(tmp_path / "http")
    assert not any(value.startswith("/ambient") for value in result.values())
    assert "CHUMMER_WORKSPACE_ROOT" not in result
    assert "CHUMMER_PACKAGE_FEED" not in result


def test_exact_head_checkout_validator_rejects_dirty_tree(tmp_path: Path) -> None:
    module = load_module()
    checkout = tmp_path / "source"
    checkout.mkdir()
    subprocess.run(["git", "init"], cwd=checkout, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "package-plane@example.invalid"], cwd=checkout, check=True)
    subprocess.run(["git", "config", "user.name", "Package Plane Test"], cwd=checkout, check=True)
    tracked = checkout / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=checkout, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=checkout, check=True, capture_output=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, check=True, capture_output=True, text=True
    ).stdout.strip()
    repository = "https://github.com/ArchonMegalon/chummer6-core.git"
    subprocess.run(["git", "remote", "add", "origin", repository], cwd=checkout, check=True)
    spec = module.PackageSpec(
        "Chummer.Engine.Contracts",
        repository,
        commit,
        "source",
        "Chummer.Contracts/Chummer.Contracts.csproj",
        "expression",
        "GPL-3.0-only",
        None,
    )
    tracked.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(module.PackagePlaneError, match="exact-HEAD checkout is dirty"):
        module.validate_checkout(checkout, spec, env=os.environ)


def _write_fake_engine_package(module, feed: Path, assembly: bytes) -> tuple[object, str]:
    version = PACKAGE_VERSION
    repository = "https://github.com/ArchonMegalon/chummer6-core.git"
    commit = "1" * 40
    package_id = "Chummer.Engine.Contracts"
    spec = module.PackageSpec(
        package_id,
        repository,
        commit,
        "core",
        "Chummer.Contracts/Chummer.Contracts.csproj",
        "expression",
        "GPL-3.0-only",
        None,
    )
    nuspec = f"""<?xml version="1.0"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>{package_id}</id><version>{version}</version>
    <license type="expression">GPL-3.0-only</license>
    <repository type="git" url="{repository}" commit="{commit}" />
    <dependencies><group targetFramework="net10.0" /></dependencies>
  </metadata>
</package>
"""
    path = feed / f"{package_id}.{version}.nupkg"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{package_id}.nuspec", nuspec)
        archive.writestr(f"lib/net10.0/{package_id}.dll", assembly)
    return spec, nuspec


def test_inventory_rejects_metadata_valid_package_byte_replacement(tmp_path: Path) -> None:
    module = load_module()
    feed = tmp_path / "feed"
    feed.mkdir()
    spec, _ = _write_fake_engine_package(module, feed, b"trusted")
    lock = module.PackagePlaneLock("10.0.103", PACKAGE_VERSION, "https://api.nuget.org/v3/index.json", (spec,))
    lock_sha = "2" * 64
    package = module.validate_package(feed, spec, PACKAGE_VERSION)
    inventory = module._inventory_payload(lock, feed, lock_sha)
    (feed / module.INVENTORY_FILE_NAME).write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    module.validate_feed_inventory(feed, lock, lock_sha)

    original_digest = hashlib.sha256(package.read_bytes()).hexdigest()
    _write_fake_engine_package(module, feed, b"metadata-valid-malicious-bytes")
    assert hashlib.sha256(package.read_bytes()).hexdigest() != original_digest
    module.validate_package(feed, spec, PACKAGE_VERSION)
    with pytest.raises(module.PackagePlaneError, match="package byte binding mismatch"):
        module.validate_feed_inventory(feed, lock, lock_sha)


def test_build_feed_rejects_any_existing_destination(tmp_path: Path) -> None:
    module = load_module()
    feed = tmp_path / "feed"
    feed.mkdir()
    lock = module.load_lock(LOCK_PATH)
    with pytest.raises(module.PackagePlaneError, match="must start absent"):
        module.build_feed(lock, lock_sha256="0" * 64, feed=feed, dotnet="dotnet")


def test_build_feed_rejects_sdk_roll_forward(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    lock = module.load_lock(LOCK_PATH)
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **_kwargs):
        rendered = tuple(command)
        calls.append(rendered)
        if rendered[-1] == "--version":
            return "10.0.110\n"
        raise AssertionError(f"unexpected command after SDK mismatch: {rendered}")

    monkeypatch.setattr(module, "_run", fake_run)
    with pytest.raises(module.PackagePlaneError, match="expected 10.0.103, observed 10.0.110"):
        module.build_feed(
            lock,
            lock_sha256="0" * 64,
            feed=tmp_path / "feed",
            dotnet="dotnet",
        )
    assert calls == [("dotnet", "--version")]


def test_external_project_references_require_explicit_local_tree_opt_in() -> None:
    for relative in PACKAGE_PLANE_PROJECTS:
        root = ElementTree.fromstring((ROOT / relative).read_text(encoding="utf-8-sig"))
        parents = _parent_map(root)
        for reference in root.findall(".//ProjectReference"):
            include = reference.get("Include", "").replace("\\", "/")
            external = any(
                marker in include
                for marker in (
                    "chummer-core-engine/",
                    "chummer-hub-registry/",
                    "$(ChummerCoreEngineRoot)",
                    "$(ChummerHubRegistryRoot)",
                    "$(ChummerMediaFactoryRoot)",
                )
            )
            if not external:
                continue
            condition = parents[reference].get("Condition", "")
            assert "ChummerUseLocalCompatibilityTree" in condition
            assert "== 'true'" in condition


def test_default_package_plane_is_false_even_when_siblings_exist() -> None:
    props = ElementTree.fromstring(
        (ROOT / "Directory.Build.props").read_text(encoding="utf-8-sig")
    )
    values = props.findall(".//ChummerUseLocalCompatibilityTree")
    assert len(values) == 1
    assert (values[0].text or "").strip() == "false"
    assert values[0].get("Condition") == "'$(ChummerUseLocalCompatibilityTree)' == ''"

    result = subprocess.run(
        [
            "dotnet",
            "msbuild",
            str(ROOT / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"),
            "-nologo",
            "-getProperty:ChummerUseLocalCompatibilityTree",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "false"


def test_all_packable_hub_contracts_embed_one_proprietary_license() -> None:
    expected_license = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "All rights reserved." in expected_license
    for relative in CONTRACT_PROJECTS:
        root = ElementTree.fromstring((ROOT / relative).read_text(encoding="utf-8-sig"))
        runtime_identifiers = root.findall(".//RuntimeIdentifiers")
        assert len(runtime_identifiers) == 1, relative
        assert runtime_identifiers[0].get("Condition") == (
            "'$(RuntimeIdentifiers)' == '' and '$(RuntimeIdentifier)' != ''"
        )
        licenses = root.findall(".//PackageLicenseFile")
        assert len(licenses) == 1, relative
        assert (licenses[0].text or "").strip() == "LICENSE"
        packed_licenses = [
            item
            for item in root.findall(".//None")
            if item.get("Include") == "../LICENSE"
        ]
        assert len(packed_licenses) == 1, relative
        assert packed_licenses[0].get("Pack", "").lower() == "true"
        assert packed_licenses[0].get("PackagePath") == ""
