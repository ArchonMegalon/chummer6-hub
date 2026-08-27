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
VERIFY_SCRIPT_PATH = ROOT / "scripts" / "ai" / "verify-hub-package-plane.py"
PUBLIC_EDGE_PREFLIGHT_PATH = ROOT / "scripts/check_public_edge_deploy_preflight.py"
LOCK_PATH = ROOT / "eng" / "package-plane.lock.json"
PACKAGE_VERSION = "0.1.0-preview"
OWNER_PACKAGE_VERSIONS = {
    "Chummer.Engine.Contracts": "0.0.0-packageplane.candidate.shfebd698752e19",
    "Chummer.Hub.Registry.Contracts": "0.1.0-preview",
    "Chummer.Run.Registry": "0.1.0-preview",
    "Chummer.Play.Contracts": "0.1.0-preview",
    "Chummer.Run.Contracts": "0.1.0-preview",
    "Chummer.Engine.GmCharacterEdits": "0.0.0-packageplane.candidate.shfebd698752e19",
}
CORE_RUNTIME_PACKAGE_IDS = {
    "Chummer.Engine.Contracts",
    "Chummer.Application",
    "Chummer.Rulesets.Hosting",
    "Chummer.Rulesets.Sr5",
    "Chummer.Rulesets.Sr6",
    "Chummer.Infrastructure",
    "Chummer.Rulesets.Sr4",
    "Chummer.Engine.GmCharacterEdits",
}
HUB_PACKAGE_IDS = {
    "Chummer.Hub.Registry.Contracts",
    "Chummer.Run.Registry",
    "Chummer.Play.Contracts",
    "Chummer.Run.Contracts",
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
    "Chummer.BuildGhost.ToughTongue.Tests/Chummer.BuildGhost.ToughTongue.Tests.csproj",
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
    "Chummer.BuildGhost.ToughTongue.Tests",
)
OWNER_VERSION_PROPERTIES = {
    "Chummer.Engine.Contracts": "ChummerEngineContractsPackageVersion",
    "Chummer.Hub.Registry.Contracts": "ChummerHubRegistryContractsPackageVersion",
    "Chummer.Run.Registry": "ChummerRunRegistryPackageVersion",
    "Chummer.Engine.GmCharacterEdits": "ChummerCoreGmCharacterEditsPackageVersion",
}


def load_module():
    spec = importlib.util.spec_from_file_location("hub_package_plane", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_verifier_module():
    spec = importlib.util.spec_from_file_location(
        "hub_package_plane_verifier", VERIFY_SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_public_edge_preflight_module():
    spec = importlib.util.spec_from_file_location(
        "hub_package_plane_public_edge_preflight",
        PUBLIC_EDGE_PREFLIGHT_PATH,
    )
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
        "Chummer.Hub.Registry.Contracts",
        "Chummer.Run.Registry",
        "Chummer.Play.Contracts",
        "Chummer.Run.Contracts",
    ]
    assert [spec.package_id for spec in lock.core_runtime.packages] == [
        "Chummer.Engine.Contracts",
        "Chummer.Application",
        "Chummer.Rulesets.Hosting",
        "Chummer.Rulesets.Sr5",
        "Chummer.Rulesets.Sr6",
        "Chummer.Infrastructure",
        "Chummer.Rulesets.Sr4",
        "Chummer.Engine.GmCharacterEdits",
    ]
    assert lock.core_runtime.package_version == (
        "0.0.0-packageplane.candidate.shfebd698752e19"
    )
    assert lock.core_runtime.runtime_source_commit == (
        "febd698752e195dceef79fbc3f83dc971564fe00"
    )
    assert lock.core_runtime.package_recipe_commit == (
        "3260ac73714d8b001a3599d6776196e394dc6c35"
    )
    assert all(len(spec.commit) == 40 for spec in lock.packages)
    assert {spec.package_id: spec.version for spec in lock.packages} == {
        package_id: version
        for package_id, version in OWNER_PACKAGE_VERSIONS.items()
        if package_id not in {
            "Chummer.Engine.Contracts",
            "Chummer.Engine.GmCharacterEdits",
        }
    }
    assert all(spec.nupkg_sha256 and spec.nupkg_size_bytes > 0 for spec in lock.packages)
    assert lock.dotnet_install_url == "https://dot.net/v1/dotnet-install.sh"
    assert len(lock.dotnet_install_sha256) == 64


def test_lock_rejects_unknown_fields_or_authority_substitution() -> None:
    module = load_module()
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    payload["unbound"] = True
    with pytest.raises(module.PackagePlaneError, match="exact v5 fields"):
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
    "counts",
    [
        {"total": 0, "executed": 0, "passed": 0},
        {"total": 2, "executed": 1, "passed": 1},
        {"total": 2, "executed": 2, "passed": 1, "failed": 1},
    ],
)
def test_package_plane_receipt_rejects_empty_or_partial_test_runs(
    counts: dict[str, int],
) -> None:
    verifier = load_verifier_module()
    with pytest.raises(verifier.VerificationError, match="did not fully pass"):
        verifier._require_passing_tests(counts, "focused tests")

    verifier._require_passing_tests(
        {
            "total": 2,
            "executed": 2,
            "passed": 2,
            "failed": 0,
            "error": 0,
            "timeout": 0,
            "aborted": 0,
        },
        "focused tests",
    )


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
    assert result["HOME"] == str(tmp_path / "home")
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
    for directory in (
        tmp_path / "home",
        tmp_path / "packages",
        tmp_path / "cli",
        tmp_path / "http",
        tmp_path / "tmp",
    ):
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700


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


def test_hub_staging_rejects_stale_core_package_before_restore(tmp_path: Path) -> None:
    module = load_module()
    lock = module.load_lock(LOCK_PATH)
    feed = tmp_path / "hub-feed"
    feed.mkdir()
    for name in module._expected_feed_entry_names(lock):
        (feed / name).write_bytes(b"placeholder")
    stale_core = feed / "Chummer.Engine.Contracts.0.1.0-preview.nupkg"
    stale_core.write_bytes(b"stale core bytes must never enter Hub authority")

    with pytest.raises(module.PackagePlaneError, match="exact locked file set"):
        module._assert_exact_feed_entries(feed, lock)


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
    monkeypatch.setattr(module, "validate_core_runtime_feed", lambda *_args: None)
    with pytest.raises(module.PackagePlaneError, match="expected 10.0.103, observed 10.0.110"):
        module.build_feed(
            lock,
            lock_sha256="0" * 64,
            feed=tmp_path / "feed",
            core_feed=tmp_path / "core-feed",
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


def test_container_restore_uses_only_the_validated_locked_package_feed() -> None:
    dockerfile = (ROOT / "Chummer.Run.Api/Dockerfile").read_text(encoding="utf-8")
    config_path = ROOT / "eng/NuGet.Container.Config"
    config = ElementTree.fromstring(config_path.read_text(encoding="utf-8"))
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for required_input in (
        "!global.json",
        "!eng/package-plane.lock.json",
        "!eng/core-main-runtime-artifact-authority.json",
        "!eng/NuGet.Container.Config",
        "!scripts/ai/bootstrap-hub-package-feed.py",
        "**/bin/**",
        "**/obj/**",
    ):
        assert required_input in dockerignore
    assert (
        "FROM mcr.microsoft.com/dotnet/sdk:10.0.103@sha256:"
        "e362a8dbcd691522456da26a5198b8f3ca1d7641c95624fadc5e3e82678bd08a "
        "AS hub-package-feed"
    ) in dockerfile
    assert (
        "RUN [\"/usr/local/bin/python3\", \"-I\", \"-S\", "
        "\"scripts/ai/bootstrap-hub-package-feed.py\", \"--repo-root\", "
        "\"/proof\", \"--feed\", \"/opt/chummer-package-feed\", "
        "\"--core-feed\", \"/opt/chummer-core-runtime-feed\", "
        "\"--download-core-runtime\"]"
    ) in dockerfile
    assert (
        "COPY --from=public-pwa-proof "
        "/proof/public-pwa-proof-authority.receipt.json "
        "/tmp/hub-package-feed-public-pwa-proof.receipt.json"
    ) in dockerfile
    assert "COPY --from=public-pwa-proof /usr/local/ /usr/local/" in dockerfile
    assert "apt-get install -y --no-install-recommends python3" not in dockerfile
    assert (
        "COPY --from=hub-package-feed /opt/chummer-package-feed "
        "/opt/chummer-package-feed"
    ) in dockerfile
    assert (
        "COPY --from=hub-package-feed /opt/chummer-core-runtime-feed "
        "/opt/chummer-core-runtime-feed"
    ) in dockerfile
    assert "--configfile /tmp/chummer-package-feed.NuGet.Config" in dockerfile
    assert "--packages /tmp/chummer-nuget/packages" in dockerfile
    assert "--locked-mode" in dockerfile
    assert "--no-cache" in dockerfile
    assert "-p:ChummerPackageFeed=" in dockerfile
    assert "-p:RestoreAdditionalProjectSources=" in dockerfile
    assert (
        "-p:ChummerMediaContractsAssembly=/src/fleet/repos/"
        "chummer-media-factory/src/Chummer.Media.Contracts/bin/Release/"
        "net10.0/Chummer.Media.Contracts.dll"
    ) in dockerfile
    assert (
        "rm -rf /src/fleet/repos/chummer-media-factory/src/"
        "Chummer.Media.Contracts/bin"
    ) in dockerfile
    assert (
        "/src/fleet/repos/chummer-media-factory/src/"
        "Chummer.Media.Contracts/obj"
    ) in dockerfile
    assert "COPY chummer-core-engine/" not in dockerfile
    assert (
        "COPY chummer-hub-registry/Chummer.Hub.Registry.Contracts/" not in dockerfile
    )
    assert "COPY chummer-hub-registry/Chummer.Run.Registry/" not in dockerfile
    assert (
        "rm -rf /src/chummer.run-services/Chummer.Run.Api/bin "
        "/src/chummer.run-services/Chummer.Run.Api/obj"
    ) not in dockerfile
    assert "dotnet publish -c Release -o /app/publish --no-restore" in dockerfile
    for project_name in LOCKED_PROJECTS:
        if project_name in {
            "Chummer.Run.Api.Tests",
            "Chummer.BuildGhost.ToughTongue.Tests",
        }:
            continue
        assert (
            f"COPY --from=run-services-source {project_name}/packages.lock.json "
            f"chummer.run-services/{project_name}/"
        ) in dockerfile

    sources = {
        node.get("key"): node.get("value")
        for node in config.findall("./packageSources/add")
    }
    assert sources == {
        "locked-chummer": "/opt/chummer-package-feed",
        "locked-core-runtime": "/opt/chummer-core-runtime-feed",
        "nuget.org": "https://api.nuget.org/v3/index.json",
    }
    assert config.find("./packageSources/clear") is not None
    mappings = {
        node.get("key"): {
            pattern.get("pattern") for pattern in node.findall("./package")
        }
        for node in config.findall("./packageSourceMapping/packageSource")
    }
    assert mappings == {
        "locked-chummer": HUB_PACKAGE_IDS,
        "locked-core-runtime": CORE_RUNTIME_PACKAGE_IDS,
        "nuget.org": {"*"},
    }
    assert mappings["locked-chummer"].isdisjoint(mappings["locked-core-runtime"])

    preflight = load_public_edge_preflight_module()
    contract = preflight.validate_public_pwa_docker_build_contract(
        ROOT / "Chummer.Run.Api/Dockerfile"
    )
    assert contract["status"] == "pass", contract["failures"]
    assert contract["stageAliases"] == [
        "public-pwa-proof",
        "hub-package-feed",
        "build",
        "install-linking-postgres-tool-final",
        "final",
    ]
    assert contract["checks"]["exactPackageFeedStage"] is True
    assert contract["checks"]["packageFeedDependsOnProof"] is True
    assert contract["checks"]["buildDependsOnPackageFeed"] is True
    assert contract["checks"]["exactCoreRuntimeFeedConsumption"] is True
    assert contract["checks"]["receiptIsFirstBuildInstruction"] is True


def test_hosted_exact_sdk_lane_runs_projection_path_and_descriptor_tests() -> None:
    workflow = (ROOT / ".github/workflows/package-plane.yml").read_text(
        encoding="utf-8"
    )
    assert "--version 10.0.103" in workflow
    assert "Assert the hosted C# lane uses exact SDK 10.0.103" in workflow
    assert (
        "Build and test C# projection contracts without siblings on SDK 10.0.103"
        in workflow
    )

    api_tests = ElementTree.fromstring(
        (ROOT / "Chummer.Run.Api.Tests/Chummer.Run.Api.Tests.csproj").read_text(
            encoding="utf-8-sig"
        )
    )
    linked = {
        node.get("Include", "").replace("\\", "/")
        for node in api_tests.findall(".//Compile")
    }
    assert "../Chummer.Tests/PublicProjectionSnapshotServiceTests.cs" in linked
    assert "../Chummer.Tests/PublicProjectionProofRequestPathPolicyTests.cs" in linked
    assert (
        "../Chummer.Tests/ReleaseUploadAuthorityHandoffCompatibilityTests.cs" in linked
    )

    verifier = (ROOT / "scripts/ai/verify-hub-package-plane.py").read_text(
        encoding="utf-8"
    )
    assert "Chummer.BuildGhost.ToughTongue.Tests" in verifier
    assert "build-ghost-tough-tongue-package-plane.trx" in verifier
    assert '"build_ghost_tough_tongue_tests": build_ghost_test_counts' in verifier


def test_package_plane_runs_release_handoffs_and_candidate_ui_contracts() -> None:
    workflow = (ROOT / ".github/workflows/package-plane.yml").read_text(
        encoding="utf-8"
    )
    assert "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020" in workflow
    assert 'node-version: "22.17.0"' in workflow
    assert "scripts/materialize_release_authority_advance_request.py" in workflow
    assert "scripts/materialize_release_scorecard_handoff.py" in workflow
    assert "scripts/materialize_release_ready_receipt.py" in workflow
    assert "scripts/verify_governed_campaign_e2e_receipt.py" in workflow
    assert "scripts/verify_post_activation_acceptance.py" in workflow
    assert "scripts/verify_public_edge_compose_operability.py" in workflow
    assert "tests/test_materialize_release_authority_advance_request.py" in workflow
    assert "tests/test_materialize_release_scorecard_handoff.py" in workflow
    assert "tests/test_materialize_release_ready_campaign_preview.py" in workflow
    assert "tests/test_verify_governed_campaign_e2e_receipt.py" in workflow
    assert "tests/test_verify_post_activation_acceptance.py" in workflow
    assert "tests/test_public_edge_volume_initializer.py" in workflow
    assert "tests/public/ui-frame-candidate-binding.spec.ts" in workflow
    assert (
        "tests/test_public_edge_deploy_preflight.py::"
        "test_public_pwa_dockerfile_has_exact_pinned_validator_stage_and_receipt_dependency"
        in workflow
    )


def test_package_plane_runs_private_rook_hosting_as_nonprovider_policy() -> None:
    verifier = load_verifier_module()
    assert set(
        (
            "tests/test_build_ghost_private_nonprod_ai_deploy.py",
            "tests/test_build_ghost_private_nonprod_presentation_deploy.py",
            "tests/test_build_ghost_private_nonprod_compose.py",
            "tests/test_build_ghost_private_rook_hosting.py",
            "tests/test_build_ghost_tough_tongue_runtime_config.py",
        )
    ).issubset(verifier.RELEASE_CONTROL_PYTHON_TESTS)


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
