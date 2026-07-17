from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sync_public_edge_operational_mirrors.py"
PREFLIGHT = REPO_ROOT / "scripts" / "check_public_edge_deploy_preflight.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def initialize_mirror(root: Path, relative_paths: tuple[Path, ...], content: bytes = b"old\n") -> None:
    for relative_path in relative_paths:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "codex@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Codex Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)


def initialize_source(root: Path, relative_paths: tuple[Path, ...]) -> None:
    for index, relative_path in enumerate(relative_paths):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"canonical-{index}\n".encode())


def test_contracted_paths_match_deploy_preflight_exact_mirror_contract() -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_contract")
    preflight = load_module(PREFLIGHT, "public_edge_deploy_preflight_contract")
    expected = tuple(
        item[1] for item in preflight.PUBLIC_EDGE_OPERATIONAL_MIRROR_EXACT_PATH_SPECS
    )
    assert module.CONTRACTED_RELATIVE_PATHS == expected


def test_check_only_reports_drift_without_writing(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_check")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    before = {
        path: (mirror / path).read_bytes() for path in module.CONTRACTED_RELATIVE_PATHS
    }

    plan = module.build_sync_plan(source, {"mirror": mirror})

    assert plan["status"] == "review_required"
    assert plan["driftCount"] == len(module.CONTRACTED_RELATIVE_PATHS)
    assert plan["updatedCount"] == 0
    assert before == {
        path: (mirror / path).read_bytes() for path in module.CONTRACTED_RELATIVE_PATHS
    }


def test_apply_updates_clean_targets_only_after_complete_preflight(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_apply")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)

    result = module.apply_sync_plan(
        module.build_sync_plan(source, {"mirror": mirror})
    )

    assert result["status"] == "pass"
    assert result["driftCount"] == 0
    assert result["updatedCount"] == len(module.CONTRACTED_RELATIVE_PATHS)
    for relative_path in module.CONTRACTED_RELATIVE_PATHS:
        assert (mirror / relative_path).read_bytes() == (source / relative_path).read_bytes()


def test_apply_refuses_dirty_contracted_target_and_writes_nothing(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_dirty")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    dirty_path = mirror / module.CONTRACTED_RELATIVE_PATHS[0]
    dirty_path.write_text("operator change\n", encoding="utf-8")
    before = {
        path: (mirror / path).read_bytes() for path in module.CONTRACTED_RELATIVE_PATHS
    }

    result = module.apply_sync_plan(
        module.build_sync_plan(source, {"mirror": mirror})
    )

    assert result["status"] == "blocked"
    assert any(item["id"] == "mirror_contracted_paths_dirty" for item in result["blockers"])
    assert result["updatedCount"] == 0
    assert before == {
        path: (mirror / path).read_bytes() for path in module.CONTRACTED_RELATIVE_PATHS
    }


def test_preflight_refuses_symlink_target(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_symlink")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    target = mirror / module.CONTRACTED_RELATIVE_PATHS[0]
    outside = tmp_path / "outside"
    outside.write_text("outside\n", encoding="utf-8")
    target.unlink()
    target.symlink_to(outside)

    plan = module.build_sync_plan(source, {"mirror": mirror})

    assert plan["status"] == "blocked"
    assert any(item["id"] == "unsafe_symlink" for item in plan["blockers"])
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_apply_refuses_target_changed_after_plan_and_writes_nothing(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_cas")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    plan = module.build_sync_plan(source, {"mirror": mirror})
    changed = mirror / module.CONTRACTED_RELATIVE_PATHS[-1]
    changed.write_text("raced\n", encoding="utf-8")
    untouched = mirror / module.CONTRACTED_RELATIVE_PATHS[0]
    before_untouched = untouched.read_bytes()

    result = module.apply_sync_plan(plan)

    assert result["status"] == "blocked"
    assert result["updatedCount"] == 0
    assert any(item["id"] == "mirror_changed_after_preflight" for item in result["blockers"])
    assert untouched.read_bytes() == before_untouched


def test_apply_refuses_same_bytes_replacement_with_new_inode(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_inode_cas")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    plan = module.build_sync_plan(source, {"mirror": mirror})
    replaced_target = mirror / module.CONTRACTED_RELATIVE_PATHS[-1]
    replacement = replaced_target.with_name(f"{replaced_target.name}.replacement")
    replacement.write_bytes(replaced_target.read_bytes())
    replacement.replace(replaced_target)
    git_status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--",
            str(module.CONTRACTED_RELATIVE_PATHS[-1]),
        ],
        cwd=mirror,
        capture_output=True,
        text=True,
        check=True,
    )
    assert git_status.stdout == ""

    result = module.apply_sync_plan(plan)

    assert result["status"] == "blocked"
    assert result["updatedCount"] == 0
    assert result["blockers"][0]["id"] == "mirror_changed_after_preflight"
    assert replaced_target.read_bytes() == b"old\n"


def test_activation_race_restores_operator_bytes_instead_of_losing_them(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_activation_race")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    plan = module.build_sync_plan(source, {"mirror": mirror})
    raced_target = mirror / module.CONTRACTED_RELATIVE_PATHS[0]
    original_exchange = module._atomic_exchange_entries
    raced = False

    def exchange_after_operator_write(parent_fd: int, left_name: str, right_name: str) -> None:
        nonlocal raced
        if not raced:
            raced = True
            raced_target.write_bytes(b"operator-race\n")
        original_exchange(parent_fd, left_name, right_name)

    monkeypatch.setattr(module, "_atomic_exchange_entries", exchange_after_operator_write)

    result = module.apply_sync_plan(plan)

    assert result["status"] == "blocked"
    assert result["updatedCount"] == 0
    assert result["blockers"][0]["id"] == "activation_cas_failed"
    assert raced_target.read_bytes() == b"operator-race\n"
    for relative_path in module.CONTRACTED_RELATIVE_PATHS[1:]:
        assert (mirror / relative_path).read_bytes() == b"old\n"


def test_activation_symlink_swap_never_writes_through_link(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_activation_symlink")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    plan = module.build_sync_plan(source, {"mirror": mirror})
    raced_target = mirror / module.CONTRACTED_RELATIVE_PATHS[0]
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside-must-survive\n")
    original_exchange = module._atomic_exchange_entries
    raced = False

    def exchange_after_symlink_swap(parent_fd: int, left_name: str, right_name: str) -> None:
        nonlocal raced
        if not raced:
            raced = True
            raced_target.unlink()
            raced_target.symlink_to(outside)
        original_exchange(parent_fd, left_name, right_name)

    monkeypatch.setattr(module, "_atomic_exchange_entries", exchange_after_symlink_swap)

    result = module.apply_sync_plan(plan)

    assert result["status"] == "blocked"
    assert result["updatedCount"] == 0
    assert result["blockers"][0]["id"] == "activation_cas_failed"
    assert raced_target.is_symlink()
    assert raced_target.readlink() == outside
    assert outside.read_bytes() == b"outside-must-survive\n"
    assert result["blockers"][0]["retainedRollbackPaths"]


def test_parent_directory_symlink_swap_is_detected_and_outside_tree_is_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_parent_symlink")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    plan = module.build_sync_plan(source, {"mirror": mirror})
    first_relative = module.CONTRACTED_RELATIVE_PATHS[0]
    parent = (mirror / first_relative).parent
    detached_parent = parent.with_name(f"{parent.name}.operator-detached")
    outside_parent = tmp_path / "outside-parent"
    outside_parent.mkdir()
    outside_target = outside_parent / first_relative.name
    outside_target.write_bytes(b"outside-parent-must-survive\n")
    original_exchange = module._atomic_exchange_entries
    raced = False

    def exchange_after_parent_swap(parent_fd: int, left_name: str, right_name: str) -> None:
        nonlocal raced
        if not raced:
            raced = True
            parent.rename(detached_parent)
            parent.symlink_to(outside_parent, target_is_directory=True)
        original_exchange(parent_fd, left_name, right_name)

    monkeypatch.setattr(module, "_atomic_exchange_entries", exchange_after_parent_swap)

    result = module.apply_sync_plan(plan)

    assert result["status"] == "blocked"
    assert result["updatedCount"] == 0
    assert outside_target.read_bytes() == b"outside-parent-must-survive\n"
    assert (detached_parent / first_relative.name).read_bytes() == b"old\n"
    assert parent.is_symlink()


def test_late_activation_race_rolls_back_already_exchanged_targets(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_transaction_rollback")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    plan = module.build_sync_plan(source, {"mirror": mirror})
    raced_target = mirror / module.CONTRACTED_RELATIVE_PATHS[1]
    original_exchange = module._atomic_exchange_entries
    activation_count = 0
    raced = False

    def exchange_with_second_target_race(parent_fd: int, left_name: str, right_name: str) -> None:
        nonlocal activation_count, raced
        activation_count += 1
        if activation_count == 2 and not raced:
            raced = True
            raced_target.write_bytes(b"second-target-operator-race\n")
        original_exchange(parent_fd, left_name, right_name)

    monkeypatch.setattr(module, "_atomic_exchange_entries", exchange_with_second_target_race)

    result = module.apply_sync_plan(plan)

    assert result["status"] == "blocked"
    assert result["updatedCount"] == 0
    assert raced_target.read_bytes() == b"second-target-operator-race\n"
    assert (mirror / module.CONTRACTED_RELATIVE_PATHS[0]).read_bytes() == b"old\n"
    for relative_path in module.CONTRACTED_RELATIVE_PATHS[2:]:
        assert (mirror / relative_path).read_bytes() == b"old\n"


def test_post_activation_validation_preserves_new_operator_edit_and_backup(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_post_activation_race")
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(mirror, module.CONTRACTED_RELATIVE_PATHS)
    plan = module.build_sync_plan(source, {"mirror": mirror})
    raced_target = mirror / module.CONTRACTED_RELATIVE_PATHS[0]
    original_validate = module._validate_activated_entry
    raced = False

    def validate_after_operator_edit(entry) -> None:
        nonlocal raced
        if not raced:
            raced = True
            raced_target.write_bytes(b"operator-post-activation-race\n")
        original_validate(entry)

    monkeypatch.setattr(module, "_validate_activated_entry", validate_after_operator_edit)

    result = module.apply_sync_plan(plan)

    assert result["status"] == "blocked"
    assert result["updatedCount"] == 1
    assert result["blockers"][0]["id"] == "post_activation_target_changed"
    assert raced_target.read_bytes() == b"operator-post-activation-race\n"
    retained = result["blockers"][0]["retainedRollbackPaths"]
    assert len(retained) == 1
    assert Path(retained[0]).read_bytes() == b"old\n"
    for relative_path in module.CONTRACTED_RELATIVE_PATHS[1:]:
        assert (mirror / relative_path).read_bytes() == b"old\n"


def test_missing_configured_mirror_root_is_explicit_failure(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_missing")
    source = tmp_path / "source"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)

    plan = module.build_sync_plan(source, {"missing": tmp_path / "missing"})

    assert plan["status"] == "blocked"
    assert plan["driftCount"] == 0
    assert plan["blockers"] == [
        {
            "id": "unsafe_or_missing_mirror_root",
            "mirror": "missing",
            "path": str((tmp_path / "missing").absolute()),
        }
    ]


def test_source_and_mirror_alias_is_rejected(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_source_alias")
    source = tmp_path / "source"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)

    plan = module.build_sync_plan(source, {"mirror": source})

    assert plan["status"] == "blocked"
    assert any(item["id"] == "mirror_aliases_source_root" for item in plan["blockers"])


def test_symlinked_mirror_root_is_rejected(tmp_path: Path) -> None:
    module = load_module(SCRIPT, "sync_public_edge_operational_mirrors_root_symlink")
    source = tmp_path / "source"
    real_mirror = tmp_path / "real-mirror"
    mirror_link = tmp_path / "mirror-link"
    initialize_source(source, module.CONTRACTED_RELATIVE_PATHS)
    initialize_mirror(real_mirror, module.CONTRACTED_RELATIVE_PATHS)
    mirror_link.symlink_to(real_mirror, target_is_directory=True)

    plan = module.build_sync_plan(source, {"mirror": mirror_link})

    assert plan["status"] == "blocked"
    assert any(item["id"] == "unsafe_or_missing_mirror_root" for item in plan["blockers"])
