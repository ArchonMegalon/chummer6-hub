from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "ai" / "bootstrap-hub-package-feed.py"
LOCK_PATH = ROOT / "eng" / "package-plane.lock.json"
PACKAGE_VERSION = "0.1.0-preview"
OWNER_PACKAGE_VERSIONS = {
    "Chummer.Engine.Contracts": "5.225.0",
    "Chummer.Hub.Registry.Contracts": "0.1.0-preview",
    "Chummer.Run.Registry": "0.1.0-preview",
}
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
LOCKED_PROJECTS = (
    "Chummer.Campaign.Contracts",
    "Chummer.Control.Contracts",
    "Chummer.Play.Contracts",
    "Chummer.Run.Contracts",
    "Chummer.World.Contracts",
    "Chummer.Run.Api",
    "Chummer.Run.Api.Tests",
)
OWNER_VERSION_PROPERTIES = {
    "Chummer.Engine.Contracts": "ChummerEngineContractsPackageVersion",
    "Chummer.Hub.Registry.Contracts": "ChummerHubRegistryContractsPackageVersion",
    "Chummer.Run.Registry": "ChummerRunRegistryPackageVersion",
}


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
    assert {spec.package_id: spec.version for spec in lock.packages} == OWNER_PACKAGE_VERSIONS
    assert all(spec.nupkg_sha256 and spec.nupkg_size_bytes > 0 for spec in lock.packages)
    assert lock.dotnet_install_url == "https://dot.net/v1/dotnet-install.sh"
    assert len(lock.dotnet_install_sha256) == 64


def test_lock_rejects_unknown_fields_or_authority_substitution() -> None:
    module = load_module()
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    payload["unbound"] = True
    with pytest.raises(module.PackagePlaneError, match="exact v3 fields"):
        module.validate_lock_payload(payload)

    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    payload["packages"][0]["unbound"] = True
    with pytest.raises(module.PackagePlaneError, match="exact fields"):
        module.validate_lock_payload(payload)

    for key, value in (
        ("repository", "https://github.com/ArchonMegalon/chummer6-ui.git"),
        ("project", "Chummer.Avalonia/Chummer.Avalonia.csproj"),
        ("license_value", "MIT"),
    ):
        payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        payload["packages"][0][key] = value
        with pytest.raises(module.PackagePlaneError, match="immutable authority mismatch"):
            module.validate_lock_payload(payload)


def test_repository_sdk_policy_disables_roll_forward() -> None:
    global_json = json.loads((ROOT / "global.json").read_text(encoding="utf-8"))
    assert global_json == {
        "sdk": {
            "version": "10.0.103",
            "rollForward": "disable",
        }
    }


def test_owner_dependency_versions_are_independent_from_hub_package_version() -> None:
    props = ElementTree.fromstring(
        (ROOT / "Directory.Build.props").read_text(encoding="utf-8-sig")
    )
    for property_name in OWNER_VERSION_PROPERTIES.values():
        elements = props.findall(f".//{property_name}")
        assert len(elements) == 1, property_name
        package_id = next(
            key for key, value in OWNER_VERSION_PROPERTIES.items() if value == property_name
        )
        assert (elements[0].text or "").strip() == OWNER_PACKAGE_VERSIONS[package_id]
        assert elements[0].get("Condition") == f"'$({property_name})' == ''"

    for relative in PACKAGE_PLANE_PROJECTS:
        project = ElementTree.fromstring(
            (ROOT / relative).read_text(encoding="utf-8-sig")
        )
        for reference in project.findall(".//PackageReference"):
            package_id = reference.get("Include", "")
            expected_property = OWNER_VERSION_PROPERTIES.get(package_id)
            if expected_property is None:
                continue
            assert reference.get("Version") == f"$({expected_property})", (
                relative,
                package_id,
            )


def test_package_plane_projects_enforce_content_hash_locks() -> None:
    for project_name in LOCKED_PROJECTS:
        project_path = ROOT / project_name / f"{project_name}.csproj"
        project = ElementTree.fromstring(project_path.read_text(encoding="utf-8-sig"))
        restore_with_lock = project.find(".//RestorePackagesWithLockFile")
        restore_locked = project.find(".//RestoreLockedMode")
        assert restore_with_lock is not None and (restore_with_lock.text or "").strip() == "true"
        assert restore_locked is not None and (restore_locked.text or "").strip() == "true"
        assert "ChummerUseLocalCompatibilityTree" in restore_with_lock.get("Condition", "")
        assert "ChummerUseLocalCompatibilityTree" in restore_locked.get("Condition", "")

        lock = json.loads((ROOT / project_name / "packages.lock.json").read_text(encoding="utf-8"))
        assert lock["version"] == 1
        assert isinstance(lock["dependencies"], dict)
        for dependencies in lock["dependencies"].values():
            for package_id, metadata in dependencies.items():
                if metadata.get("type") == "Project":
                    continue
                assert metadata.get("resolved"), package_id
                assert metadata.get("contentHash"), package_id


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
        "GITHUB_ACTIONS": "true",
        "GITHUB_SHA": "f" * 40,
        "GITHUB_WORKSPACE": "/ambient/github-workspace",
        "MSBuildSDKsPath": "/ambient/msbuild-sdks",
        "SOURCE_DATE_EPOCH": "1234567890",
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
    assert "GITHUB_ACTIONS" not in result
    assert "GITHUB_SHA" not in result
    assert "GITHUB_WORKSPACE" not in result
    assert "MSBuildSDKsPath" not in result
    assert result["CI"] == "true"
    assert result["SOURCE_DATE_EPOCH"] == "0"
    assert result["DOTNET_ROLL_FORWARD"] == "LatestPatch"
    assert result["DOTNET_MULTILEVEL_LOOKUP"] == "0"
    assert result["TZ"] == "UTC"
    assert result["TMPDIR"] == str(tmp_path / "tmp")


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
        PACKAGE_VERSION,
        repository,
        commit,
        "source",
        "Chummer.Contracts/Chummer.Contracts.csproj",
        "expression",
        "GPL-3.0-only",
        None,
        "0" * 64,
        1,
    )
    tracked.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(module.PackagePlaneError, match="exact-HEAD checkout is dirty"):
        module.validate_checkout(checkout, spec, env=os.environ)


def test_owner_build_properties_pin_revision_and_normalize_paths(tmp_path: Path) -> None:
    module = load_module()
    lock = module.load_lock(LOCK_PATH)
    spec = lock.packages[0]
    checkout = tmp_path / "machine-specific" / spec.checkout_directory
    package_root = tmp_path / "packages"
    properties = module.package_build_properties(lock, spec, checkout, package_root)
    assert f"-p:RepositoryCommit={spec.commit}" in properties
    assert f"-p:PackageVersion={spec.version}" in properties
    assert f"-p:Version={spec.version}" in properties
    assert f"-p:SourceRevisionId={spec.commit}" in properties
    assert "-p:RepositoryBranch=" in properties
    assert "-p:ContinuousIntegrationBuild=true" in properties
    assert "-p:Deterministic=true" in properties
    assert "-p:DeterministicSourcePaths=true" in properties
    assert "-p:EmbedUntrackedSources=false" in properties
    assert (
        f"-p:PathMap={checkout.resolve()}=/_/src/{spec.checkout_directory}"
        in properties
    )


def _write_fake_engine_package(module, feed: Path, assembly: bytes) -> tuple[object, str]:
    version = PACKAGE_VERSION
    repository = "https://github.com/ArchonMegalon/chummer6-core.git"
    commit = "1" * 40
    package_id = "Chummer.Engine.Contracts"
    spec = module.PackageSpec(
        package_id,
        version,
        repository,
        commit,
        "core",
        "Chummer.Contracts/Chummer.Contracts.csproj",
        "expression",
        "GPL-3.0-only",
        None,
        "0" * 64,
        1,
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
    core_properties = b"<coreProperties><identifier>fixture</identifier></coreProperties>"
    core_name = "package/services/metadata/core-properties/" + "a" * 32 + ".psmdcp"
    relationships = f"""<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Type="{module.MANIFEST_RELATIONSHIP}" Target="/{package_id}.nuspec" Id="random-manifest" />
  <Relationship Type="{module.CORE_PROPERTIES_RELATIONSHIP}" Target="/{core_name}" Id="random-core" />
</Relationships>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("_rels/.rels", relationships)
        archive.writestr(f"{package_id}.nuspec", nuspec)
        archive.writestr(f"lib/net10.0/{package_id}.dll", assembly)
        archive.writestr(core_name, core_properties)
    module.canonicalize_package(path, spec, version)
    spec = replace(
        spec,
        nupkg_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        nupkg_size_bytes=path.stat().st_size,
    )
    return spec, nuspec


def test_package_canonicalization_is_byte_reproducible(tmp_path: Path) -> None:
    module = load_module()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    first_spec, _ = _write_fake_engine_package(module, first, b"same assembly")
    second_spec, _ = _write_fake_engine_package(module, second, b"same assembly")
    first_path = module.validate_package(first, first_spec)
    second_path = module.validate_package(second, second_spec)
    assert first_path.read_bytes() == second_path.read_bytes()


def test_inventory_rejects_metadata_valid_package_byte_replacement(tmp_path: Path) -> None:
    module = load_module()
    feed = tmp_path / "feed"
    feed.mkdir()
    spec, _ = _write_fake_engine_package(module, feed, b"trusted")
    authority = module.load_lock(LOCK_PATH)
    lock = replace(authority, packages=(spec,))
    lock_sha = "2" * 64
    package = module.validate_package(feed, spec)
    inventory = module._inventory_payload(lock, feed, lock_sha)
    (feed / module.INVENTORY_FILE_NAME).write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    module.validate_feed_inventory(feed, lock, lock_sha)

    unlisted = feed / "Newtonsoft.Json.13.0.3.nupkg"
    unlisted.write_bytes(b"unlisted package bytes")
    with pytest.raises(module.PackagePlaneError, match="exact locked file set"):
        module.validate_feed_inventory(feed, lock, lock_sha)
    unlisted.unlink()

    inventory["unbound_field"] = "must fail closed"
    (feed / module.INVENTORY_FILE_NAME).write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(module.PackagePlaneError, match="exact top-level fields"):
        module.validate_feed_inventory(feed, lock, lock_sha)
    inventory.pop("unbound_field")
    (feed / module.INVENTORY_FILE_NAME).write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )

    original_digest = hashlib.sha256(package.read_bytes()).hexdigest()
    _write_fake_engine_package(module, feed, b"metadata-valid-malicious-bytes")
    assert hashlib.sha256(package.read_bytes()).hexdigest() != original_digest
    with pytest.raises(module.PackagePlaneError, match="locked package byte authority mismatch"):
        module.validate_package(feed, spec)
    with pytest.raises(module.PackagePlaneError, match="locked package byte authority mismatch"):
        module.validate_feed_inventory(feed, lock, lock_sha)


def test_feed_validation_rejects_external_symlink_handoffs(tmp_path: Path) -> None:
    module = load_module()
    feed = tmp_path / "authority"
    feed.mkdir()
    spec, _ = _write_fake_engine_package(module, feed, b"trusted")
    authority = module.load_lock(LOCK_PATH)
    lock = replace(authority, packages=(spec,))
    lock_sha = "2" * 64
    inventory = module._inventory_payload(lock, feed, lock_sha)
    (feed / module.INVENTORY_FILE_NAME).write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )

    linked_feed = tmp_path / "linked-feed"
    linked_feed.mkdir()
    for entry in feed.iterdir():
        (linked_feed / entry.name).symlink_to(entry)
    with pytest.raises(module.PackagePlaneError, match="contained regular files"):
        module.validate_feed_inventory(linked_feed, lock, lock_sha)

    feed_alias = tmp_path / "feed-alias"
    feed_alias.symlink_to(feed, target_is_directory=True)
    with pytest.raises(module.PackagePlaneError, match="non-symlink directory"):
        module.validate_feed_inventory(feed_alias, lock, lock_sha)


def test_pr_ci_installs_digest_locked_private_sdk() -> None:
    workflow = (ROOT / ".github/workflows/package-plane.yml").read_text(encoding="utf-8")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert "actions/setup-dotnet" not in workflow
    assert lock["dotnet_install"]["url"] in workflow
    assert lock["dotnet_install"]["sha256"] in workflow
    assert "${RUNNER_TEMP}/chummer-hub-dotnet" in workflow


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
