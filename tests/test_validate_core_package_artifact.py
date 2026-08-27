from __future__ import annotations

import copy
import hashlib
import io
import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "ai" / "validate-core-package-artifact.py"
SELECTED_CORE_COMMIT = "febd698752e195dceef79fbc3f83dc971564fe00"
SELECTED_CORE_LOCK_PATH = (
    ROOT / "tests" / "fixtures" / f"core-runtime-package-plane.{SELECTED_CORE_COMMIT[:12]}.lock.json"
)
SELECTED_CORE_LOCK_SHA256 = (
    "7d726ddea508af408d1eb50d36424385265a01a2895aa6a5e99e33a42056ae03"
)
SELECTED_CORE_LOCK_BYTES = SELECTED_CORE_LOCK_PATH.read_bytes()
if hashlib.sha256(SELECTED_CORE_LOCK_BYTES).hexdigest() != SELECTED_CORE_LOCK_SHA256:
    raise RuntimeError("selected Core runtime lock fixture digest differs")
SELECTED_CORE_LOCK = json.loads(SELECTED_CORE_LOCK_BYTES.decode("utf-8"))
SOURCE_COMMIT = SELECTED_CORE_LOCK["runtime_source"]["commit"]
RECIPE_COMMIT = "2" * 40
PACKAGE_VERSION = SELECTED_CORE_LOCK["package_version"]
OWNER_PACKAGE_VERSION = SELECTED_CORE_LOCK["external_owner_packages"][0]["version"]
LOCK_CONTRACT = SELECTED_CORE_LOCK["contract"]
OWNER_LOCK_SHA256 = "d" * 64
OWNER_INVENTORY_SHA256 = "e" * 64
CANDIDATE_ENGINE_INVENTORY_SHA256 = "f" * 64
CANDIDATE_RUNTIME_INVENTORY_SHA256 = "0" * 64
LOCKED_OWNER_IDS = (
    "Chummer.Engine.Contracts",
    "Chummer.Hub.Registry.Contracts",
    "Chummer.Play.Contracts",
    "Chummer.Run.Contracts",
)
CORE_REPOSITORY = SELECTED_CORE_LOCK["runtime_source"]["repository"]
REGISTRY_REPOSITORY = SELECTED_CORE_LOCK["external_owner_packages"][0]["repository"]
HUB_REPOSITORY = SELECTED_CORE_LOCK["external_owner_packages"][1]["repository"]
SDK_ARCHIVE_SHA512 = SELECTED_CORE_LOCK["dotnet_sdk"]["archive_sha512"]
ALLOWED_RECIPE_DELTA = tuple(SELECTED_CORE_LOCK["allowed_recipe_delta"])
BUILD_AUTHORITY_PATHS = tuple(
    row["path"] for row in SELECTED_CORE_LOCK["build_authority_files"]
)
RUNTIME_SPECS = tuple(
    (
        row["id"],
        row["project"],
        row["project_sha256"],
        row["assembly"],
        tuple(dependency["id"] for dependency in row["dependencies"]),
    )
    for row in SELECTED_CORE_LOCK["packages"]
)
GM_RUNTIME_ASSEMBLY_PATHS = (
    "lib/net10.0/Chummer.Application.dll",
    "lib/net10.0/Chummer.Engine.GmCharacterEdits.dll",
    "lib/net10.0/Chummer.Infrastructure.dll",
    "lib/net10.0/Chummer.Rulesets.Hosting.dll",
    "lib/net10.0/Chummer.Rulesets.Sr5.dll",
    "lib/net10.0/Chummer.Rulesets.Sr6.dll",
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_core_package_artifact", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def expected_snapshot_members(module: Any, fixture: "ArtifactFixture") -> tuple[Any, ...]:
    rows = [
        (module.LOCK_FILE_NAME, "runtime package-plane lock", fixture.lock_path),
        (module.INVENTORY_FILE_NAME, "runtime package inventory", fixture.inventory_path),
        (module.RECEIPT_FILE_NAME, "Core no-siblings v3 receipt", fixture.receipt_path),
    ]
    rows.extend(
        (
            f"{module.PACKAGES_DIRECTORY_NAME}/{row['file_name']}",
            f"package {row['id']}",
            fixture.packages_root / row["file_name"],
        )
        for row in fixture.inventory["packages"]
    )
    return tuple(
        module.ImmutableMemberSnapshot(
            member_path=member_path,
            label=label,
            payload=path.read_bytes(),
            sha256=digest(path.read_bytes()),
        )
        for member_path, label, path in rows
    )


def write_json(path: Path, payload: Any) -> bytes:
    rendered = json_bytes(payload)
    path.write_bytes(rendered)
    return rendered


@dataclass
class ArtifactFixture:
    root: Path
    packages_root: Path
    inventory_path: Path
    lock_path: Path
    receipt_path: Path
    authority_path: Path
    inventory: dict[str, Any]
    lock: dict[str, Any]
    receipt: dict[str, Any]
    authority: dict[str, Any]


def owner_row(index: int) -> dict[str, Any]:
    return {
        "id": LOCKED_OWNER_IDS[index],
        "version": OWNER_PACKAGE_VERSION,
        "sha256": f"{index + 3:x}" * 64,
        "size_bytes": 1000 + index,
        "role": (
            "locked_engine_baseline_not_selected"
            if index == 0
            else "locked_owner_dependency"
        ),
    }


def dependency_version(package_id: str) -> str:
    if package_id in {row[0] for row in RUNTIME_SPECS}:
        return PACKAGE_VERSION
    if package_id.startswith("Chummer."):
        return OWNER_PACKAGE_VERSION
    return {
        "Microsoft.Extensions.DependencyInjection": "10.0.0",
        "SharpCompress": "0.50.1",
    }[package_id]


def package_bytes(
    package_id: str,
    assembly: str,
    dependencies: list[dict[str, str]],
    *,
    nuspec_id: str | None = None,
    nuspec_dependencies: list[dict[str, str]] | None = None,
    foreign_entry: str | None = None,
    additional_entries: dict[str, bytes] | None = None,
    assembly_entry: str | None = None,
    omit_dependency_group: bool = False,
) -> bytes:
    package = ET.Element("package")
    metadata = ET.SubElement(package, "metadata")
    ET.SubElement(metadata, "id").text = nuspec_id or package_id
    ET.SubElement(metadata, "version").text = PACKAGE_VERSION
    license_element = ET.SubElement(metadata, "license", {"type": "expression"})
    license_element.text = "GPL-3.0-only"
    ET.SubElement(
        metadata,
        "repository",
        {"type": "git", "url": CORE_REPOSITORY, "commit": SOURCE_COMMIT},
    )
    rendered_dependencies = dependencies if nuspec_dependencies is None else nuspec_dependencies
    if not omit_dependency_group:
        container = ET.SubElement(metadata, "dependencies")
        group = ET.SubElement(container, "group", {"targetFramework": "net10.0"})
        for dependency in rendered_dependencies:
            ET.SubElement(
                group,
                "dependency",
                {
                    "id": dependency["id"],
                    "version": dependency["version"],
                    "exclude": "Build,Analyzers",
                },
            )
    nuspec = ET.tostring(package, encoding="utf-8", xml_declaration=True)
    runtime_assemblies = (
        GM_RUNTIME_ASSEMBLY_PATHS
        if package_id == "Chummer.Engine.GmCharacterEdits"
        else (f"lib/net10.0/{assembly}",)
    )
    entries = {
        "[Content_Types].xml": b"<Types />\n",
        "_rels/.rels": b"<Relationships />\n",
        f"{package_id}.nuspec": nuspec,
        **{
            path: f"assembly:{path}\n".encode()
            for path in runtime_assemblies
        },
    }
    if assembly_entry is not None:
        entries.pop(f"lib/net10.0/{assembly}", None)
        entries[assembly_entry] = f"assembly:{package_id}\n".encode()
    if foreign_entry is not None:
        entries[foreign_entry] = b"foreign\n"
    if additional_entries is not None:
        entries.update(additional_entries)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries, key=lambda value: (value.casefold(), value)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, entries[name])
    return buffer.getvalue()


def build_fixture(tmp_path: Path) -> ArtifactFixture:
    module = load_module()
    root = tmp_path / "artifact"
    packages_root = root / module.PACKAGES_DIRECTORY_NAME
    packages_root.mkdir(parents=True)

    lock_path = root / module.LOCK_FILE_NAME
    lock = copy.deepcopy(SELECTED_CORE_LOCK)
    runtime_lock_rows = lock["packages"]
    lock_bytes = write_json(lock_path, lock)
    lock_sha256 = digest(lock_bytes)

    package_rows: list[dict[str, Any]] = []
    for index, lock_row in enumerate(runtime_lock_rows):
        package_id = lock_row["id"]
        file_name = f"{package_id}.{PACKAGE_VERSION}.nupkg"
        dependencies = [dict(row) for row in lock_row["dependencies"]]
        rendered_package = package_bytes(
            package_id,
            lock_row["assembly"],
            dependencies,
        )
        (packages_root / file_name).write_bytes(rendered_package)
        package_rows.append(
            {
                "id": package_id,
                "version": PACKAGE_VERSION,
                "repository": module.CORE_REPOSITORY,
                "source_commit": SOURCE_COMMIT,
                "project": lock_row["project"],
                "assembly": lock_row["assembly"],
                "target_framework": "net10.0",
                "dependencies": dependencies,
                "file_name": file_name,
                "sha256": digest(rendered_package),
                "size_bytes": len(rendered_package),
            }
        )

    inventory_path = root / module.INVENTORY_FILE_NAME
    inventory = {
        "contract": module.INVENTORY_CONTRACT,
        "package_plane_lock_sha256": lock_sha256,
        "package_version": PACKAGE_VERSION,
        "runtime_source_commit": SOURCE_COMMIT,
        "package_recipe_commit": RECIPE_COMMIT,
        "packages": package_rows,
    }
    inventory_bytes = write_json(inventory_path, inventory)
    inventory_sha256 = digest(inventory_bytes)

    locked_packages = [owner_row(index) for index in range(4)]
    receipt_path = root / module.RECEIPT_FILE_NAME
    receipt = {
        "contract": module.RECEIPT_CONTRACT,
        "generated_at_utc": "2026-08-24T12:34:56Z",
        "status": "pass",
        "core_commit": RECIPE_COMMIT,
        "package_plane_lock_sha256": OWNER_LOCK_SHA256,
        "package_inventory_sha256": OWNER_INVENTORY_SHA256,
        "candidate_package_inventory_sha256": CANDIDATE_ENGINE_INVENTORY_SHA256,
        "candidate_runtime_package_inventory_sha256": CANDIDATE_RUNTIME_INVENTORY_SHA256,
        "runtime_package_inventory_sha256": inventory_sha256,
        "runtime_package_plane_lock_sha256": lock_sha256,
        "runtime_source_commit": SOURCE_COMMIT,
        "package_recipe_commit": RECIPE_COMMIT,
        "package_version": OWNER_PACKAGE_VERSION,
        "candidate_package_version": PACKAGE_VERSION,
        "locked_packages": locked_packages,
        "resolved_owner_contracts": [
            {**row, "role": "current_core_runtime_candidate"} for row in package_rows
        ]
        + [dict(row) for row in locked_packages[1:]],
        "no_sibling_directories": True,
        "isolated_package_cache": True,
        "package_source_mapping": {
            "Chummer.*": "locked-owner-contracts",
            "other": "https://api.nuget.org/v3/index.json",
        },
        "normal_local_engine_dependency_graph": "pass",
        "build": "pass",
        "package_plane_runtime_test": "pass",
        "local_owner_isolation_tests": "pass",
        "candidate_engine_contract_pack": "pass",
        "candidate_gm_edit_runtime_pack": "pass",
        "candidate_gm_edit_runtime_consumer": "pass",
        "eight_package_runtime_plane": "pass",
    }
    receipt_bytes = write_json(receipt_path, receipt)

    authority_path = tmp_path / "authority.json"
    authority = {
        "contract": module.AUTHORITY_CONTRACT,
        "artifact_selector": {
            "repository": module.CORE_REPOSITORY,
            "workflow_run_id": 123456,
            "artifact_id": 789012,
            "name": f"chummer-core-runtime-package-plane-{RECIPE_COMMIT}",
            "sha256": "9" * 64,
        },
        "runtime_package_plane_lock": {
            "contract": LOCK_CONTRACT,
            "sha256": lock_sha256,
        },
        "inventory": {"sha256": inventory_sha256},
        "receipt": {"sha256": digest(receipt_bytes)},
        "owner_package_plane_lock_sha256": OWNER_LOCK_SHA256,
        "owner_package_inventory_sha256": OWNER_INVENTORY_SHA256,
        "owner_package_inventory": {
            "contract": module.OWNER_INVENTORY_CONTRACT,
            "sha256": OWNER_INVENTORY_SHA256,
            "package_version": OWNER_PACKAGE_VERSION,
            "packages": [
                {
                    key: value
                    for key, value in row.items()
                    if key in {"id", "version", "sha256", "size_bytes"}
                }
                for row in locked_packages
            ],
        },
        "candidate_engine_package_inventory_sha256": (
            CANDIDATE_ENGINE_INVENTORY_SHA256
        ),
        "candidate_runtime_package_inventory_sha256": (
            CANDIDATE_RUNTIME_INVENTORY_SHA256
        ),
        "runtime_source_commit": SOURCE_COMMIT,
        "package_recipe_commit": RECIPE_COMMIT,
        "owner_package_version": OWNER_PACKAGE_VERSION,
        "runtime_package_version": PACKAGE_VERSION,
    }
    write_json(authority_path, authority)
    return ArtifactFixture(
        root=root,
        packages_root=packages_root,
        inventory_path=inventory_path,
        lock_path=lock_path,
        receipt_path=receipt_path,
        authority_path=authority_path,
        inventory=inventory,
        lock=lock,
        receipt=receipt,
        authority=authority,
    )


def rebind(
    fixture: ArtifactFixture,
    *,
    sync_resolved_runtime: bool = True,
    sync_receipt_inventory: bool = True,
    sync_receipt_lock: bool = True,
) -> None:
    lock_bytes = write_json(fixture.lock_path, fixture.lock)
    lock_sha256 = digest(lock_bytes)
    fixture.authority["runtime_package_plane_lock"]["sha256"] = lock_sha256
    fixture.authority["runtime_package_plane_lock"]["contract"] = fixture.lock[
        "contract"
    ]
    fixture.inventory["package_plane_lock_sha256"] = lock_sha256
    inventory_bytes = write_json(fixture.inventory_path, fixture.inventory)
    inventory_sha256 = digest(inventory_bytes)
    fixture.authority["inventory"]["sha256"] = inventory_sha256
    if sync_receipt_lock:
        fixture.receipt["runtime_package_plane_lock_sha256"] = lock_sha256
    if sync_receipt_inventory:
        fixture.receipt["runtime_package_inventory_sha256"] = inventory_sha256
    if sync_resolved_runtime:
        fixture.receipt["resolved_owner_contracts"][:8] = [
            {**row, "role": "current_core_runtime_candidate"}
            for row in fixture.inventory["packages"]
        ]
    receipt_bytes = write_json(fixture.receipt_path, fixture.receipt)
    fixture.authority["receipt"]["sha256"] = digest(receipt_bytes)
    write_json(fixture.authority_path, fixture.authority)


def rebind_receipt_only(fixture: ArtifactFixture) -> None:
    receipt_bytes = write_json(fixture.receipt_path, fixture.receipt)
    fixture.authority["receipt"]["sha256"] = digest(receipt_bytes)
    write_json(fixture.authority_path, fixture.authority)


def replace_package(
    fixture: ArtifactFixture,
    index: int,
    rendered: bytes,
) -> None:
    row = fixture.inventory["packages"][index]
    path = fixture.packages_root / row["file_name"]
    path.write_bytes(rendered)
    row["sha256"] = digest(rendered)
    row["size_bytes"] = len(rendered)
    rebind(fixture)


def test_validates_exact_eleven_member_artifact_and_outer_selector(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)

    result = module.validate_artifact(fixture.root, fixture.authority_path)

    assert result["status"] == "pass"
    assert result["member_count"] == 11
    assert result["package_count"] == 8
    assert result["ordered_package_ids"] == list(module.EXPECTED_PACKAGE_IDS)
    assert result["outer_artifact_selector"] == fixture.authority["artifact_selector"]
    assert result["post_validation_consumption_authority"] == {
        "contract": "github-actions.immutable-artifact-selector/v1",
        "artifact_id": fixture.authority["artifact_selector"]["artifact_id"],
        "sha256": fixture.authority["artifact_selector"]["sha256"],
    }
    assert result["artifact_byte_snapshot"] == {
        "contract": module.BYTE_SNAPSHOT_CONTRACT,
        "sha256": module._snapshot_sha256(expected_snapshot_members(module, fixture)),
        "member_count": 11,
        "source_path_posture": "not_attested_after_snapshot_capture",
    }
    assert result["checks"] == {
        "exact_eleven_member_layout": "pass",
        "strict_json_contracts": "pass",
        "runtime_lock_inventory_semantics": "pass",
        "inventory_receipt_cross_links": "pass",
        "owner_inventory_row_authority": "pass",
        "package_byte_bindings": "pass",
        "immutable_eleven_member_byte_snapshot": "pass",
        "snapshot_only_semantic_validation": "pass",
        "nupkg_payload_contracts": "pass",
        "contained_regular_files": "pass",
        "capture_time_directory_snapshots": "pass",
    }


def test_fixture_mirrors_current_producer_receipt_semantics(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)

    assert fixture.lock == SELECTED_CORE_LOCK
    assert SELECTED_CORE_LOCK_SHA256 == digest(SELECTED_CORE_LOCK_BYTES)
    assert tuple(SELECTED_CORE_LOCK["allowed_recipe_delta"]) == (
        module.EXPECTED_ALLOWED_RECIPE_DELTA
    )
    assert set(fixture.lock) == module.RUNTIME_LOCK_KEYS
    assert fixture.lock["contract"] == module.RUNTIME_LOCK_CONTRACT
    assert fixture.lock["dotnet_sdk"] == {
        "version": "10.0.103",
        "rid": "linux-x64",
        "archive_url": (
            "https://builds.dotnet.microsoft.com/dotnet/Sdk/10.0.103/"
            "dotnet-sdk-10.0.103-linux-x64.tar.gz"
        ),
        "archive_sha512": SDK_ARCHIVE_SHA512,
    }
    assert fixture.lock["allowed_recipe_delta"] == list(ALLOWED_RECIPE_DELTA)
    assert [row["path"] for row in fixture.lock["build_authority_files"]] == list(
        BUILD_AUTHORITY_PATHS
    )
    assert fixture.lock["external_owner_packages"] == [
        {
            "id": "Chummer.Hub.Registry.Contracts",
            "version": OWNER_PACKAGE_VERSION,
            "repository": REGISTRY_REPOSITORY,
            "commit": "af9a7e19c3bf331e96411dfb8f9e7820a98cab29",
        },
        {
            "id": "Chummer.Play.Contracts",
            "version": OWNER_PACKAGE_VERSION,
            "repository": HUB_REPOSITORY,
            "commit": "7c1faef298fb9028e77069c2467686f92624566c",
        },
        {
            "id": "Chummer.Run.Contracts",
            "version": OWNER_PACKAGE_VERSION,
            "repository": HUB_REPOSITORY,
            "commit": "7c1faef298fb9028e77069c2467686f92624566c",
        },
    ]
    assert fixture.lock["third_party_packages"] == [
        {"id": "Microsoft.Extensions.DependencyInjection", "version": "10.0.0"},
        {"id": "SharpCompress", "version": "0.50.1"},
    ]
    assert [row["id"] for row in fixture.lock["packages"]] == list(
        module.EXPECTED_PACKAGE_IDS
    )
    for lock_row, inventory_row in zip(
        fixture.lock["packages"], fixture.inventory["packages"], strict=True
    ):
        assert lock_row["project_sha256"] in {spec[2] for spec in RUNTIME_SPECS}
        for key in ("id", "project", "assembly", "target_framework", "dependencies"):
            assert inventory_row[key] == lock_row[key]
        assert inventory_row["file_name"] == (
            f"{lock_row['id']}.{fixture.lock['package_version']}.nupkg"
        )
    assert fixture.receipt["core_commit"] == RECIPE_COMMIT
    assert fixture.receipt["core_commit"] != SOURCE_COMMIT
    assert fixture.receipt["package_version"] == OWNER_PACKAGE_VERSION
    assert fixture.receipt["candidate_package_version"] == PACKAGE_VERSION
    assert fixture.receipt["package_plane_lock_sha256"] == OWNER_LOCK_SHA256
    assert fixture.receipt["runtime_package_plane_lock_sha256"] == fixture.inventory[
        "package_plane_lock_sha256"
    ]
    assert fixture.receipt["package_source_mapping"] == (
        module.EXPECTED_PACKAGE_SOURCE_MAPPING
    )
    assert [row["id"] for row in fixture.receipt["locked_packages"]] == list(
        module.LOCKED_OWNER_PACKAGE_IDS
    )
    assert [row["role"] for row in fixture.receipt["locked_packages"]] == list(
        module.LOCKED_OWNER_PACKAGE_ROLES
    )
    assert all(
        row["role"] == module.RESOLVED_RUNTIME_ROLE
        for row in fixture.receipt["resolved_owner_contracts"][:8]
    )
    assert fixture.receipt["resolved_owner_contracts"][8:] == fixture.receipt[
        "locked_packages"
    ][1:]
    assert fixture.authority["owner_package_inventory"]["packages"] == [
        {
            key: value
            for key, value in row.items()
            if key in {"id", "version", "sha256", "size_bytes"}
        }
        for row in fixture.receipt["locked_packages"]
    ]

    assert module.validate_artifact(fixture.root, fixture.authority_path)[
        "status"
    ] == "pass"


def test_sealed_public_handoff_recipe_has_no_additive_policy_profile() -> None:
    module = load_module()
    assert module.PUBLIC_HANDOFF_RECIPE_COMMIT == (
        "3260ac73714d8b001a3599d6776196e394dc6c35"
    )
    assert module.PUBLIC_HANDOFF_ALLOWED_RECIPE_DELTA == (
        module.EXPECTED_ALLOWED_RECIPE_DELTA
    )
    assert module.PUBLIC_HANDOFF_BUILD_AUTHORITY_PATHS == (
        module.EXPECTED_BUILD_AUTHORITY_PATHS
    )


@pytest.mark.parametrize(
    ("policy_field", "expected_error"),
    [
        ("allowed_recipe_delta", "allowed_recipe_delta omission, addition, or order"),
        ("build_authority_files", "build authority path omission, addition, or order"),
    ],
)
def test_retired_public_handoff_additive_policy_is_rejected(
    tmp_path: Path,
    policy_field: str,
    expected_error: str,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    if policy_field == "allowed_recipe_delta":
        fixture.lock[policy_field] = [
            *module.PUBLIC_HANDOFF_ALLOWED_RECIPE_DELTA,
            "tests/test_public_runtime_package_handoff.py",
        ]
    else:
        existing_by_path = {
            row["path"]: row for row in fixture.lock["build_authority_files"]
        }
        fixture.lock[policy_field] = [
            existing_by_path.get(path, {"path": path, "sha256": "a" * 64})
            for path in (
                *module.PUBLIC_HANDOFF_BUILD_AUTHORITY_PATHS,
                "tests/test_public_runtime_package_handoff.py",
            )
        ]
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match=expected_error):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_cli_writes_a_deterministic_validation_receipt(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    output = tmp_path / "validation.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--artifact-root",
            str(fixture.root),
            "--authority",
            str(fixture.authority_path),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["contract"] == module.VALIDATION_CONTRACT
    assert payload["status"] == "pass"
    assert output.stat().st_mode & 0o777 == 0o644
    assert result.stdout == ""


def test_cli_rejects_output_inside_validated_artifact(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    output = fixture.root / "validation.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--artifact-root",
            str(fixture.root),
            "--authority",
            str(fixture.authority_path),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )

    assert result.returncode == 1
    assert "outside the immutable artifact root" in result.stderr
    assert output.exists() is False


def test_cli_holds_output_directory_across_hostile_parent_symlink_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    safe_output = tmp_path / "safe-output"
    safe_output.mkdir()
    output_parent = tmp_path / "output-parent"
    output_parent.symlink_to(safe_output, target_is_directory=True)
    output = output_parent / "validation.json"
    original = module.validate_artifact

    def swap_parent_after_verdict(
        artifact_root: Path, authority_path: Path
    ) -> dict[str, Any]:
        result = original(artifact_root, authority_path)
        output_parent.unlink()
        output_parent.symlink_to(fixture.root, target_is_directory=True)
        return result

    monkeypatch.setattr(module, "validate_artifact", swap_parent_after_verdict)

    assert module.main(
        [
            "--artifact-root",
            str(fixture.root),
            "--authority",
            str(fixture.authority_path),
            "--output",
            str(output),
        ]
    ) == 0
    result = json.loads((safe_output / output.name).read_text(encoding="utf-8"))
    assert result["status"] == "pass"
    assert (fixture.root / output.name).exists() is False


def test_cli_atomically_replaces_hostile_output_file_symlink_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    output_root = tmp_path / "output"
    output_root.mkdir()
    output = output_root / "validation.json"
    protected = tmp_path / "protected.txt"
    protected.write_text("protected\n", encoding="utf-8")
    original = module.validate_artifact

    def swap_file_after_verdict(
        artifact_root: Path, authority_path: Path
    ) -> dict[str, Any]:
        result = original(artifact_root, authority_path)
        output.symlink_to(protected)
        return result

    monkeypatch.setattr(module, "validate_artifact", swap_file_after_verdict)

    assert module.main(
        [
            "--artifact-root",
            str(fixture.root),
            "--authority",
            str(fixture.authority_path),
            "--output",
            str(output),
        ]
    ) == 0
    assert output.is_symlink() is False
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "pass"
    assert protected.read_text(encoding="utf-8") == "protected\n"


def test_cli_never_resolves_the_output_path_after_the_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    output = tmp_path / "validation.json"
    original_validate = module.validate_artifact
    original_resolve = Path.resolve
    verdict_complete = False

    def record_verdict(
        artifact_root: Path, authority_path: Path
    ) -> dict[str, Any]:
        nonlocal verdict_complete
        result = original_validate(artifact_root, authority_path)
        verdict_complete = True
        return result

    def guarded_resolve(path: Path, *args: Any, **kwargs: Any) -> Path:
        if verdict_complete:
            raise AssertionError("no path may be resolved after the artifact verdict")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(module, "validate_artifact", record_verdict)
    monkeypatch.setattr(Path, "resolve", guarded_resolve)

    assert module.main(
        [
            "--artifact-root",
            str(fixture.root),
            "--authority",
            str(fixture.authority_path),
            "--output",
            str(output),
        ]
    ) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "pass"


def test_cli_cleans_dirfd_temporary_entry_when_atomic_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    output_root = tmp_path / "output"
    output_root.mkdir()
    output = output_root / "validation.json"

    def fail_replace(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        module.main(
            [
                "--artifact-root",
                str(fixture.root),
                "--authority",
                str(fixture.authority_path),
                "--output",
                str(output),
            ]
        )

    assert list(output_root.iterdir()) == []


def test_cli_rejects_replacing_the_trusted_authority_file(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)

    with pytest.raises(
        module.ArtifactValidationError,
        match="must not replace the trusted authority file",
    ):
        module.main(
            [
                "--artifact-root",
                str(fixture.root),
                "--authority",
                str(fixture.authority_path),
                "--output",
                str(fixture.authority_path),
            ]
        )


@pytest.mark.parametrize("name", ["foreign.txt", "Packages", "receipt.json"])
def test_rejects_foreign_root_members(tmp_path: Path, name: str) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    (fixture.root / name).write_text("foreign\n", encoding="utf-8")

    with pytest.raises(module.ArtifactValidationError, match="exact layout"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    "relative",
    [
        "chummer-core-runtime-packages.inventory.json",
        "runtime-package-plane.lock.json",
        "no-siblings.v3.receipt.json",
    ],
)
def test_rejects_missing_fixed_members(tmp_path: Path, relative: str) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    (fixture.root / relative).unlink()

    with pytest.raises(module.ArtifactValidationError, match="exact layout"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_missing_and_foreign_package_members(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    original = fixture.packages_root / fixture.inventory["packages"][0]["file_name"]
    original.unlink()
    (fixture.packages_root / "Foreign.Package.1.0.0.nupkg").write_bytes(b"foreign")

    with pytest.raises(module.ArtifactValidationError, match="exact layout"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_case_variant_package_path(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    original = fixture.packages_root / fixture.inventory["packages"][0]["file_name"]
    original.rename(fixture.packages_root / original.name.swapcase())

    with pytest.raises(module.ArtifactValidationError, match="exact layout"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_symlinked_package_member(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    package = fixture.packages_root / fixture.inventory["packages"][0]["file_name"]
    target = tmp_path / "outside.nupkg"
    target.write_bytes(package.read_bytes())
    package.unlink()
    package.symlink_to(target)

    with pytest.raises(module.ArtifactValidationError, match="single-link regular file"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_symlinked_packages_directory(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    outside = tmp_path / "outside-packages"
    fixture.packages_root.rename(outside)
    fixture.packages_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(module.ArtifactValidationError, match="non-symlink directory"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_hardlinked_package_member(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    package = fixture.packages_root / fixture.inventory["packages"][0]["file_name"]
    os.link(package, tmp_path / "second-link.nupkg")

    with pytest.raises(module.ArtifactValidationError, match="single-link regular file"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_governed_resource_limits_cover_the_verified_producer_envelope() -> None:
    module = load_module()

    assert module.MAX_PACKAGE_BYTES == 8 * 1024 * 1024
    assert module.MAX_IMMUTABLE_SNAPSHOT_BYTES == 32 * 1024 * 1024
    assert module.MAX_NUPKG_ENTRY_COUNT == 256
    assert module.MAX_NUPKG_ENTRY_UNCOMPRESSED_BYTES == 16 * 1024 * 1024
    assert module.MAX_NUPKG_TOTAL_UNCOMPRESSED_BYTES == 16 * 1024 * 1024
    assert 3_027_083 < module.MAX_IMMUTABLE_SNAPSHOT_BYTES
    assert 10 < module.MAX_NUPKG_ENTRY_COUNT
    assert 4_281_856 < module.MAX_NUPKG_ENTRY_UNCOMPRESSED_BYTES
    assert 4_284_562 < module.MAX_NUPKG_TOTAL_UNCOMPRESSED_BYTES


def test_rejects_aggregate_snapshot_bound_before_any_member_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    member_paths = [
        fixture.lock_path,
        fixture.inventory_path,
        fixture.receipt_path,
        *fixture.packages_root.iterdir(),
    ]
    observed_size = sum(path.stat().st_size for path in member_paths)
    captures = 0
    original = module._capture_immutable_member

    def recording_capture(snapshot: Any) -> Any:
        nonlocal captures
        captures += 1
        return original(snapshot)

    monkeypatch.setattr(module, "MAX_IMMUTABLE_SNAPSHOT_BYTES", observed_size - 1)
    monkeypatch.setattr(module, "_capture_immutable_member", recording_capture)

    with pytest.raises(
        module.ArtifactValidationError,
        match="governed aggregate byte bound",
    ):
        module.validate_artifact(fixture.root, fixture.authority_path)
    assert captures == 0


def test_rejects_member_bound_before_snapshot_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    package = fixture.packages_root / fixture.inventory["packages"][0]["file_name"]
    captures = 0
    original = module._capture_immutable_member

    def recording_capture(snapshot: Any) -> Any:
        nonlocal captures
        captures += 1
        return original(snapshot)

    monkeypatch.setattr(module, "MAX_PACKAGE_BYTES", package.stat().st_size - 1)
    monkeypatch.setattr(module, "_capture_immutable_member", recording_capture)

    with pytest.raises(module.ArtifactValidationError, match="bounded, single-link"):
        module.validate_artifact(fixture.root, fixture.authority_path)
    assert captures == 0


def test_rechecks_aggregate_snapshot_bound_during_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    member_paths = [
        fixture.lock_path,
        fixture.inventory_path,
        fixture.receipt_path,
        *fixture.packages_root.iterdir(),
    ]
    observed_size = sum(path.stat().st_size for path in member_paths)
    original = module._capture_immutable_member
    substituted = False

    def oversized_capture(snapshot: Any) -> Any:
        nonlocal substituted
        member = original(snapshot)
        if not substituted:
            substituted = True
            payload = member.payload + b"x"
            return module.ImmutableMemberSnapshot(
                member_path=member.member_path,
                label=member.label,
                payload=payload,
                sha256=digest(payload),
            )
        return member

    monkeypatch.setattr(module, "MAX_IMMUTABLE_SNAPSHOT_BYTES", observed_size)
    monkeypatch.setattr(module, "_capture_immutable_member", oversized_capture)

    with pytest.raises(
        module.ArtifactValidationError,
        match="during capture",
    ):
        module.validate_artifact(fixture.root, fixture.authority_path)
    assert substituted is True


def test_rejects_package_digest_and_size_drift(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    package = fixture.packages_root / fixture.inventory["packages"][0]["file_name"]
    package.write_bytes(package.read_bytes() + b"tampered")

    with pytest.raises(module.ArtifactValidationError, match="package size mismatch"):
        module.validate_artifact(fixture.root, fixture.authority_path)

    fixture.inventory["packages"][0]["size_bytes"] = package.stat().st_size
    rebind(fixture)
    with pytest.raises(module.ArtifactValidationError, match="package digest mismatch"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_inventory_unknown_field_even_when_rebound(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.inventory["unbound"] = True
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match="unknown=unbound"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_receipt_unknown_field_even_when_rebound(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["unbound"] = True
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="unknown=unbound"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_duplicate_inventory_json_key_even_when_rebound(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    raw = fixture.inventory_path.read_bytes()
    hostile = raw.replace(
        b'  "contract":',
        b'  "contract": "hostile-duplicate",\n  "contract":',
        1,
    )
    fixture.inventory_path.write_bytes(hostile)
    fixture.authority["inventory"]["sha256"] = digest(hostile)
    fixture.receipt["runtime_package_inventory_sha256"] = digest(hostile)
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="duplicate JSON key: contract"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_duplicate_receipt_json_key_even_when_rebound(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    raw = fixture.receipt_path.read_bytes()
    hostile = raw.replace(
        b'  "status":',
        b'  "status": "fail",\n  "status":',
        1,
    )
    fixture.receipt_path.write_bytes(hostile)
    fixture.authority["receipt"]["sha256"] = digest(hostile)
    write_json(fixture.authority_path, fixture.authority)

    with pytest.raises(module.ArtifactValidationError, match="duplicate JSON key: status"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_duplicate_lock_json_key_without_hard_coding_lock_shape(
    tmp_path: Path,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    raw = fixture.lock_path.read_bytes()
    hostile = raw.replace(
        b'  "contract":',
        b'  "contract": "hostile-duplicate",\n  "contract":',
        1,
    )
    fixture.lock_path.write_bytes(hostile)
    lock_sha256 = digest(hostile)
    fixture.authority["runtime_package_plane_lock"]["sha256"] = lock_sha256
    fixture.inventory["package_plane_lock_sha256"] = lock_sha256
    inventory_bytes = write_json(fixture.inventory_path, fixture.inventory)
    fixture.authority["inventory"]["sha256"] = digest(inventory_bytes)
    fixture.receipt["runtime_package_plane_lock_sha256"] = lock_sha256
    fixture.receipt["runtime_package_inventory_sha256"] = digest(inventory_bytes)
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="duplicate JSON key: contract"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_reordered_or_substituted_core_package_ids(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.inventory["packages"][0], fixture.inventory["packages"][1] = (
        fixture.inventory["packages"][1],
        fixture.inventory["packages"][0],
    )
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match="exact ordered Core"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize("hostile_name", ["../escape.nupkg", "/absolute.nupkg", "bad\\name.nupkg"])
def test_rejects_unsafe_inventory_package_paths(
    tmp_path: Path, hostile_name: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.inventory["packages"][0]["file_name"] = hostile_name
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match="safe canonical file name"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_case_colliding_inventory_file_names(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    original = fixture.inventory["packages"][0]["file_name"]
    fixture.inventory["packages"][1]["file_name"] = (
        original[: -len(".nupkg")].swapcase() + ".nupkg"
    )
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match="case-insensitively unique"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_duplicate_casefolded_dependency_ids(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    dependencies = fixture.inventory["packages"][1]["dependencies"]
    dependencies.append(
        {"id": dependencies[0]["id"].swapcase(), "version": PACKAGE_VERSION}
    )
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match="duplicate dependency id"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_runtime_inventory_receipt_cross_link_drift(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["runtime_package_inventory_sha256"] = "d" * 64
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="runtime inventory cross-link"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_inventory_bound_to_owner_lock_instead_of_runtime_lock(
    tmp_path: Path,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.inventory["package_plane_lock_sha256"] = OWNER_LOCK_SHA256
    inventory_bytes = write_json(fixture.inventory_path, fixture.inventory)
    fixture.authority["inventory"]["sha256"] = digest(inventory_bytes)
    fixture.receipt["runtime_package_inventory_sha256"] = digest(inventory_bytes)
    rebind_receipt_only(fixture)

    with pytest.raises(
        module.ArtifactValidationError, match="exact package-plane lock"
    ):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_owner_lock_receipt_cross_link_drift(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["package_plane_lock_sha256"] = "a" * 64
    rebind_receipt_only(fixture)

    with pytest.raises(
        module.ArtifactValidationError, match="owner package-plane lock cross-link"
    ):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_runtime_lock_receipt_cross_link_drift(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["runtime_package_plane_lock_sha256"] = "a" * 64
    rebind_receipt_only(fixture)

    with pytest.raises(
        module.ArtifactValidationError, match="runtime package-plane lock cross-link"
    ):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("package_inventory_sha256", "owner package inventory cross-link"),
        (
            "candidate_package_inventory_sha256",
            "candidate engine inventory cross-link",
        ),
        (
            "candidate_runtime_package_inventory_sha256",
            "candidate runtime inventory cross-link",
        ),
    ],
)
def test_rejects_owner_and_candidate_inventory_cross_link_drift(
    tmp_path: Path, field: str, message: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt[field] = "a" * 64
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match=message):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_core_commit_bound_to_runtime_source_instead_of_recipe(
    tmp_path: Path,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["core_commit"] = SOURCE_COMMIT
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="core_commit differs"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("package_version", PACKAGE_VERSION, "owner package_version differs"),
        (
            "candidate_package_version",
            OWNER_PACKAGE_VERSION,
            "candidate_package_version differs",
        ),
    ],
)
def test_rejects_owner_and_runtime_package_version_cross_link_drift(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt[field] = value
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match=message):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_resolved_runtime_rows_that_differ_from_inventory(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["resolved_owner_contracts"][0]["assembly"] = "Foreign.dll"
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="differs from inventory"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_resolved_runtime_candidate_role_drift(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["resolved_owner_contracts"][0]["role"] = "runtime_package"
    rebind_receipt_only(fixture)

    with pytest.raises(
        module.ArtifactValidationError, match="current_core_runtime_candidate"
    ):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_locked_owner_package_order_drift(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["locked_packages"][0], fixture.receipt["locked_packages"][1] = (
        fixture.receipt["locked_packages"][1],
        fixture.receipt["locked_packages"][0],
    )
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="IDs or order"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    ("index", "role"),
    [
        (0, "locked_owner_dependency"),
        (1, "locked_engine_baseline_not_selected"),
    ],
)
def test_rejects_locked_owner_package_role_drift(
    tmp_path: Path, index: int, role: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["locked_packages"][index]["role"] = role
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="roles differ"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize("mutation", ["order", "role"])
def test_rejects_resolved_registry_play_run_tail_drift(
    tmp_path: Path, mutation: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    resolved = fixture.receipt["resolved_owner_contracts"]
    if mutation == "order":
        resolved[8], resolved[9] = resolved[9], resolved[8]
    else:
        resolved[8]["role"] = "locked_engine_baseline_not_selected"
    rebind_receipt_only(fixture)

    with pytest.raises(
        module.ArtifactValidationError,
        match="exact Registry/Play/Run locked dependencies",
    ):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize("field", ["unbound", "unknown_selector"])
def test_rejects_unknown_authority_fields(tmp_path: Path, field: str) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    if field == "unbound":
        fixture.authority[field] = True
    else:
        fixture.authority["artifact_selector"][field] = True
    write_json(fixture.authority_path, fixture.authority)

    with pytest.raises(module.ArtifactValidationError, match="unknown="):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    "field",
    [
        "owner_package_plane_lock_sha256",
        "owner_package_inventory_sha256",
        "owner_package_inventory",
        "candidate_engine_package_inventory_sha256",
        "candidate_runtime_package_inventory_sha256",
        "owner_package_version",
    ],
)
def test_requires_each_explicit_owner_authority_binding(
    tmp_path: Path, field: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    del fixture.authority[field]
    write_json(fixture.authority_path, fixture.authority)

    with pytest.raises(module.ArtifactValidationError, match=f"missing={field}"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repository", "https://github.com/ArchonMegalon/chummer6-ui.git", "canonical Core repository"),
        ("workflow_run_id", 0, "positive integer"),
        ("artifact_id", True, "positive integer"),
        ("name", "latest", "exact package recipe commit"),
        ("sha256", "f" * 63, "lowercase SHA-256"),
    ],
)
def test_rejects_invalid_outer_artifact_selector(
    tmp_path: Path, field: str, value: Any, message: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.authority["artifact_selector"][field] = value
    write_json(fixture.authority_path, fixture.authority)

    with pytest.raises(module.ArtifactValidationError, match=message):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_receipt_contract_and_status(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["contract"] = "chummer-core.no-siblings-package-plane/v2"
    rebind_receipt_only(fixture)
    with pytest.raises(module.ArtifactValidationError, match="receipt contract"):
        module.validate_artifact(fixture.root, fixture.authority_path)

    fixture.receipt["contract"] = module.RECEIPT_CONTRACT
    fixture.receipt["status"] = "fail"
    rebind_receipt_only(fixture)
    with pytest.raises(module.ArtifactValidationError, match="status must be pass"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    "field",
    [
        "normal_local_engine_dependency_graph",
        "build",
        "package_plane_runtime_test",
        "local_owner_isolation_tests",
        "candidate_engine_contract_pack",
        "candidate_gm_edit_runtime_pack",
        "candidate_gm_edit_runtime_consumer",
        "eight_package_runtime_plane",
    ],
)
def test_rejects_non_pass_receipt_proof_fields(tmp_path: Path, field: str) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt[field] = "fail"
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match=field):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    "mapping",
    [
        {
            "Chummer.*": "https://api.nuget.org/v3/index.json",
            "other": "https://api.nuget.org/v3/index.json",
        },
        {"Chummer.*": "locked-owner-contracts", "other": "nuget.org"},
        {"Chummer.*": "locked-owner-contracts"},
        {
            "Chummer.*": "locked-owner-contracts",
            "other": "https://api.nuget.org/v3/index.json",
            "Foreign.*": "foreign",
        },
    ],
)
def test_rejects_non_exact_package_source_mapping(
    tmp_path: Path, mapping: dict[str, str]
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["package_source_mapping"] = mapping
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="mapping differs from policy"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize("field", ["no_sibling_directories", "isolated_package_cache"])
def test_rejects_false_receipt_isolation_gates(tmp_path: Path, field: str) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt[field] = False
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match=field):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_unknown_runtime_lock_field_even_when_rebound(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.lock["future_unreviewed_semantics"] = True
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match="unknown=future_unreviewed_semantics"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_invalid_runtime_lock_project_sha_even_when_rebound(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.lock["packages"][0]["project_sha256"] = "not-a-project-digest"
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match="project_sha256"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("project", "project differs from runtime lock"),
        ("assembly", "assembly differs from runtime lock"),
        ("framework", "target framework drift"),
        ("dependencies", "dependency graph differs from runtime lock"),
        ("file_name", "packages directory must contain the exact layout"),
    ],
)
def test_rejects_runtime_inventory_semantic_substitution_even_when_rebound(
    tmp_path: Path, mutation: str, message: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    row = fixture.inventory["packages"][5]
    if mutation == "project":
        row["project"] = "foreign/NotInfrastructure.csproj"
    elif mutation == "assembly":
        row["assembly"] = "Unrelated.Payload.dll"
    elif mutation == "framework":
        row["target_framework"] = "net9.0"
    elif mutation == "dependencies":
        row["dependencies"] = [{"id": "Totally.Foreign", "version": "latest"}]
    else:
        original = fixture.packages_root / row["file_name"]
        row["file_name"] = f"Substituted.{PACKAGE_VERSION}.nupkg"
        original.rename(fixture.packages_root / row["file_name"])
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match=message):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("identity", "nuspec identity drifted"),
        ("dependencies", "nuspec dependencies drifted"),
        ("assembly", "runtime assembly set differs"),
        ("foreign_payload", "contains foreign payloads"),
    ],
)
def test_rejects_rebound_nupkg_semantic_or_payload_substitution(
    tmp_path: Path, mutation: str, message: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    index = 1
    row = fixture.inventory["packages"][index]
    keyword: dict[str, Any] = {}
    if mutation == "identity":
        keyword["nuspec_id"] = "Chummer.Foreign.Contracts"
    elif mutation == "dependencies":
        keyword["nuspec_dependencies"] = []
    elif mutation == "assembly":
        keyword["assembly_entry"] = "lib/net10.0/Foreign.Payload.dll"
    else:
        keyword["foreign_entry"] = "tools/hostile.dll"
    rendered = package_bytes(
        row["id"],
        row["assembly"],
        [dict(dependency) for dependency in row["dependencies"]],
        **keyword,
    )
    replace_package(fixture, index, rendered)

    with pytest.raises(module.ArtifactValidationError, match=message):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_nupkg_entry_count_before_zipfile_metadata_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    row = fixture.inventory["packages"][0]
    rendered = package_bytes(
        row["id"],
        row["assembly"],
        [dict(dependency) for dependency in row["dependencies"]],
        additional_entries={
            f"tools/entry-{index:03}.bin": b"x"
            for index in range(module.MAX_NUPKG_ENTRY_COUNT - 3)
        },
    )

    def forbid_zipfile(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("ZipFile must not run before the entry-count gate")

    monkeypatch.setattr(module.zipfile, "ZipFile", forbid_zipfile)
    with pytest.raises(module.ArtifactValidationError, match="entry-count bound"):
        module._inspect_nupkg(rendered, package=row)


def test_rejects_nupkg_per_entry_expansion_before_archive_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    row = fixture.inventory["packages"][0]
    rendered = package_bytes(
        row["id"],
        row["assembly"],
        [dict(dependency) for dependency in row["dependencies"]],
        additional_entries={"tools/oversized.bin": b"x" * 2048},
    )

    def forbid_read(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("archive bytes must not be extracted before expansion gates")

    monkeypatch.setattr(module, "MAX_NUPKG_ENTRY_UNCOMPRESSED_BYTES", 1024)
    monkeypatch.setattr(module.zipfile.ZipFile, "read", forbid_read)
    with pytest.raises(module.ArtifactValidationError, match="uncompressed bound"):
        module._inspect_nupkg(rendered, package=row)


def test_rejects_nupkg_aggregate_expansion_before_archive_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    row = fixture.inventory["packages"][0]
    rendered = package_bytes(
        row["id"],
        row["assembly"],
        [dict(dependency) for dependency in row["dependencies"]],
        additional_entries={
            "tools/one.bin": b"x" * 700,
            "tools/two.bin": b"y" * 700,
        },
    )

    def forbid_read(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("archive bytes must not be extracted before expansion gates")

    monkeypatch.setattr(module, "MAX_NUPKG_ENTRY_UNCOMPRESSED_BYTES", 4096)
    monkeypatch.setattr(module, "MAX_NUPKG_TOTAL_UNCOMPRESSED_BYTES", 1024)
    monkeypatch.setattr(module.zipfile.ZipFile, "read", forbid_read)
    with pytest.raises(module.ArtifactValidationError, match="aggregate uncompressed bound"):
        module._inspect_nupkg(rendered, package=row)


@pytest.mark.parametrize(("field", "value"), [("version", "9.9.9"), ("sha256", "a" * 64)])
def test_rejects_rebound_owner_receipt_rows_outside_trusted_inventory(
    tmp_path: Path, field: str, value: Any
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.receipt["locked_packages"][1][field] = value
    fixture.receipt["resolved_owner_contracts"][8][field] = value
    rebind_receipt_only(fixture)

    with pytest.raises(module.ArtifactValidationError, match="exact owner inventory authority"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_owner_inventory_binding_digest_disagreement(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.authority["owner_package_inventory"]["sha256"] = "a" * 64
    write_json(fixture.authority_path, fixture.authority)

    with pytest.raises(module.ArtifactValidationError, match="differs from scalar authority"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize("target", ["root", "packages"])
def test_post_capture_directory_change_does_not_change_declared_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    initial_members = expected_snapshot_members(module, fixture)
    original = module._capture_immutable_member
    changed = False

    def racing_capture(snapshot: Any) -> Any:
        nonlocal changed
        captured = original(snapshot)
        if not changed:
            changed = True
            destination = fixture.root if target == "root" else fixture.packages_root
            (destination / "foreign-after-enumeration.txt").write_text(
                "foreign\n", encoding="utf-8"
            )
        return captured

    monkeypatch.setattr(module, "_capture_immutable_member", racing_capture)
    result = module.validate_artifact(fixture.root, fixture.authority_path)
    assert changed is True
    assert result["status"] == "pass"
    assert result["artifact_byte_snapshot"] == {
        "contract": module.BYTE_SNAPSHOT_CONTRACT,
        "sha256": module._snapshot_sha256(initial_members),
        "member_count": 11,
        "source_path_posture": "not_attested_after_snapshot_capture",
    }


@pytest.mark.parametrize("field", ["version", "rid", "archive_url", "archive_sha512"])
def test_rejects_any_sdk_archive_authority_drift_even_when_rebound(
    tmp_path: Path, field: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    fixture.lock["dotnet_sdk"][field] = {
        "version": "10.0.104",
        "rid": "linux-arm64",
        "archive_url": (
            "https://builds.dotnet.microsoft.com/dotnet/Sdk/10.0.104/"
            "dotnet-sdk-10.0.104-linux-x64.tar.gz"
        ),
        "archive_sha512": "a" * 128,
    }[field]
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError, match="SDK archive authority"):
        module.validate_artifact(fixture.root, fixture.authority_path)


@pytest.mark.parametrize(
    "field",
    [
        "allowed_recipe_delta",
        "build_authority_files",
        "external_owner_packages",
        "third_party_packages",
        "packages",
    ],
)
@pytest.mark.parametrize("mutation", ["omission", "addition", "reorder"])
def test_rejects_exact_core_v1_sequence_omission_addition_or_reordering(
    tmp_path: Path, field: str, mutation: str
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    rows = fixture.lock[field]
    if mutation == "omission":
        rows.pop()
    elif mutation == "addition":
        if field == "allowed_recipe_delta":
            rows.append("foreign/recipe-input.txt")
        else:
            rows.append(dict(rows[-1]))
    else:
        rows[0], rows[1] = rows[1], rows[0]
    rebind(fixture)

    with pytest.raises(module.ArtifactValidationError):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_engine_contracts_requires_one_empty_net10_dependency_group(
    tmp_path: Path,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    row = fixture.inventory["packages"][0]
    assert row["dependencies"] == []
    rendered = package_bytes(
        row["id"],
        row["assembly"],
        [],
        omit_dependency_group=True,
    )
    replace_package(fixture, 0, rendered)

    with pytest.raises(module.ArtifactValidationError, match="one dependency container"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_captures_all_eleven_members_once_in_canonical_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    original = module._capture_immutable_member
    captured_paths: list[str] = []

    def recording_capture(snapshot: Any) -> Any:
        member = original(snapshot)
        captured_paths.append(member.member_path)
        return member

    monkeypatch.setattr(module, "_capture_immutable_member", recording_capture)
    assert module.validate_artifact(fixture.root, fixture.authority_path)["status"] == "pass"
    assert captured_paths == [
        module.LOCK_FILE_NAME,
        module.INVENTORY_FILE_NAME,
        module.RECEIPT_FILE_NAME,
        *[
            f"{module.PACKAGES_DIRECTORY_NAME}/{package_id}.{module.RUNTIME_PACKAGE_VERSION}.nupkg"
            for package_id in module.EXPECTED_PACKAGE_IDS
        ],
    ]


def test_source_filesystem_phase_ends_after_single_snapshot_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    original_directory = module._require_exact_directory_names
    original_capture = module._capture_immutable_member
    original_decode = module._decode_json
    events: list[str] = []

    def recording_directory(*args: Any, **kwargs: Any) -> None:
        original_directory(*args, **kwargs)
        events.append("directory")

    def recording_capture(snapshot: Any) -> Any:
        member = original_capture(snapshot)
        events.append("capture")
        return member

    def recording_decode(payload: bytes, *, label: str) -> Any:
        events.append("semantic")
        return original_decode(payload, label=label)

    monkeypatch.setattr(module, "_require_exact_directory_names", recording_directory)
    monkeypatch.setattr(module, "_capture_immutable_member", recording_capture)
    monkeypatch.setattr(module, "_decode_json", recording_decode)

    assert module.validate_artifact(fixture.root, fixture.authority_path)["status"] == "pass"
    first_capture = events.index("capture")
    first_semantic = events.index("semantic", first_capture)
    assert events[first_capture:first_semantic] == ["capture"] * 11
    assert "directory" not in events[first_capture:]
    assert "capture" not in events[first_semantic:]


def mutate_same_size(path: Path) -> None:
    with path.open("r+b", buffering=0) as stream:
        first = stream.read(1)
        assert first
        stream.seek(0)
        stream.write(bytes([first[0] ^ 1]))
        os.fsync(stream.fileno())


@pytest.mark.parametrize("capture_number", [1, 11])
def test_source_mutation_after_snapshot_keeps_verdict_bound_to_initial_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capture_number: int,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    initial_members = expected_snapshot_members(module, fixture)
    expected_snapshot_sha256 = module._snapshot_sha256(initial_members)
    initial_lock_sha256 = digest(fixture.lock_path.read_bytes())
    original = module._capture_immutable_member
    captures = 0

    def mutate_after_capture(snapshot: Any) -> Any:
        nonlocal captures
        member = original(snapshot)
        captures += 1
        if captures == capture_number:
            mutate_same_size(fixture.lock_path)
        return member

    monkeypatch.setattr(module, "_capture_immutable_member", mutate_after_capture)
    result = module.validate_artifact(fixture.root, fixture.authority_path)

    assert captures == 11
    assert digest(fixture.lock_path.read_bytes()) != initial_lock_sha256
    assert result["status"] == "pass"
    assert result["artifact_byte_snapshot"]["sha256"] == expected_snapshot_sha256
    assert result["artifact_byte_snapshot"]["source_path_posture"] == (
        "not_attested_after_snapshot_capture"
    )


@pytest.mark.parametrize("phase", ["semantic", "result"])
def test_late_source_mutation_cannot_change_immutable_snapshot_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    expected_snapshot_sha256 = module._snapshot_sha256(
        expected_snapshot_members(module, fixture)
    )
    initial_lock_sha256 = digest(fixture.lock_path.read_bytes())
    changed = False

    if phase == "semantic":
        original = module._validate_receipt

        def mutate_during_semantics(*args: Any, **kwargs: Any) -> None:
            nonlocal changed
            original(*args, **kwargs)
            mutate_same_size(fixture.lock_path)
            changed = True

        monkeypatch.setattr(module, "_validate_receipt", mutate_during_semantics)
    else:
        original_result = module._snapshot_result

        def mutate_during_result(members: Any) -> dict[str, Any]:
            nonlocal changed
            summary = original_result(members)
            mutate_same_size(fixture.lock_path)
            changed = True
            return summary

        monkeypatch.setattr(module, "_snapshot_result", mutate_during_result)

    result = module.validate_artifact(fixture.root, fixture.authority_path)

    assert changed is True
    assert digest(fixture.lock_path.read_bytes()) != initial_lock_sha256
    assert result["status"] == "pass"
    assert result["artifact_byte_snapshot"]["sha256"] == expected_snapshot_sha256


def test_cli_output_consumes_only_immutable_authority_after_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    output = tmp_path / "validation.json"
    moved_root = tmp_path / "artifact-moved-after-verdict"
    original = module.validate_artifact

    def move_source_after_verdict(artifact_root: Path, authority_path: Path) -> dict[str, Any]:
        result = original(artifact_root, authority_path)
        artifact_root.rename(moved_root)
        return result

    monkeypatch.setattr(module, "validate_artifact", move_source_after_verdict)
    assert module.main(
        [
            "--artifact-root",
            str(fixture.root),
            "--authority",
            str(fixture.authority_path),
            "--output",
            str(output),
        ]
    ) == 0

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "pass"
    assert result["post_validation_consumption_authority"] == {
        "contract": "github-actions.immutable-artifact-selector/v1",
        "artifact_id": fixture.authority["artifact_selector"]["artifact_id"],
        "sha256": fixture.authority["artifact_selector"]["sha256"],
    }
    assert str(fixture.root) not in json.dumps(result, sort_keys=True)
