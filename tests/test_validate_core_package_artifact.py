from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "ai" / "validate-core-package-artifact.py"
SOURCE_COMMIT = "1" * 40
RECIPE_COMMIT = "2" * 40
PACKAGE_VERSION = "0.0.0-packageplane.test.sha2222222"
OWNER_PACKAGE_VERSION = "0.1.0-preview"
LOCK_CONTRACT = "chummer-core.runtime-package-plane-lock/test-v1"
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
        "version": f"1.0.{index}",
        "sha256": f"{index + 3:x}" * 64,
        "size_bytes": 1000 + index,
        "role": (
            "locked_engine_baseline_not_selected"
            if index == 0
            else "locked_owner_dependency"
        ),
    }


def build_fixture(tmp_path: Path) -> ArtifactFixture:
    module = load_module()
    root = tmp_path / "artifact"
    packages_root = root / module.PACKAGES_DIRECTORY_NAME
    packages_root.mkdir(parents=True)

    lock_path = root / module.LOCK_FILE_NAME
    lock = {
        "contract": LOCK_CONTRACT,
        "sdk": "test-only",
        "future_producer_field": {"allowed": True},
    }
    lock_bytes = write_json(lock_path, lock)
    lock_sha256 = digest(lock_bytes)

    package_rows: list[dict[str, Any]] = []
    for index, package_id in enumerate(module.EXPECTED_PACKAGE_IDS):
        file_name = f"{package_id}.{PACKAGE_VERSION}.nupkg"
        package_bytes = f"synthetic package {index}: {package_id}\n".encode("utf-8")
        (packages_root / file_name).write_bytes(package_bytes)
        dependencies = []
        if index:
            dependencies.append(
                {
                    "id": module.EXPECTED_PACKAGE_IDS[0],
                    "version": PACKAGE_VERSION,
                }
            )
        package_rows.append(
            {
                "id": package_id,
                "version": PACKAGE_VERSION,
                "repository": module.CORE_REPOSITORY,
                "source_commit": SOURCE_COMMIT,
                "project": f"src/{package_id}/{package_id}.csproj",
                "assembly": f"{package_id}.dll",
                "target_framework": "net10.0",
                "dependencies": dependencies,
                "file_name": file_name,
                "sha256": digest(package_bytes),
                "size_bytes": len(package_bytes),
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


def test_validates_exact_eleven_member_artifact_and_outer_selector(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)

    result = module.validate_artifact(fixture.root, fixture.authority_path)

    assert result["status"] == "pass"
    assert result["member_count"] == 11
    assert result["package_count"] == 8
    assert result["ordered_package_ids"] == list(module.EXPECTED_PACKAGE_IDS)
    assert result["outer_artifact_selector"] == fixture.authority["artifact_selector"]
    assert result["checks"] == {
        "exact_eleven_member_layout": "pass",
        "strict_json_contracts": "pass",
        "inventory_receipt_cross_links": "pass",
        "package_byte_bindings": "pass",
        "contained_regular_files": "pass",
    }


def test_fixture_mirrors_current_producer_receipt_semantics(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)

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

    assert module.validate_artifact(fixture.root, fixture.authority_path)[
        "status"
    ] == "pass"


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
    assert result.stdout == ""


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

    with pytest.raises(module.ArtifactValidationError, match="exact inventory set"):
        module.validate_artifact(fixture.root, fixture.authority_path)


def test_rejects_case_variant_package_path(tmp_path: Path) -> None:
    module = load_module()
    fixture = build_fixture(tmp_path)
    original = fixture.packages_root / fixture.inventory["packages"][0]["file_name"]
    original.rename(fixture.packages_root / original.name.swapcase())

    with pytest.raises(module.ArtifactValidationError, match="exact inventory set"):
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
