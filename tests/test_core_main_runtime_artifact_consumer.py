from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import sys
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = ROOT / "eng/core-main-runtime-artifact-authority.json"
WORKFLOW_PATH = ROOT / ".github/workflows/core-main-runtime-artifact-consumer.yml"
SCRIPT_PATH = ROOT / "scripts/ai/consume-core-main-runtime-artifact.py"
AUTHORITY_SHA256 = "1f1514e274ddc1dc59d87dcd42874d1d8eb0914b2bd9f3258f15e2f813a0e947"


class NonSeekableBytesIO(io.BytesIO):
    def seekable(self) -> bool:
        return False

    def seek(self, *_args: Any, **_kwargs: Any) -> int:
        raise io.UnsupportedOperation("synthetic GitHub artifact stream is non-seekable")


def load_module():
    spec = importlib.util.spec_from_file_location(
        "consume_core_main_runtime_artifact", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def authority_payload() -> dict[str, Any]:
    return json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, mode: int = 0o600) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(mode)


def open_descriptor_count() -> int:
    return len(os.listdir("/proc/self/fd"))


def api_metadata(authority: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    producer = authority["producer"]
    run = {
        "id": producer["run_id"],
        "run_attempt": producer["run_attempt"],
        "event": producer["event"],
        "status": "completed",
        "conclusion": "success",
        "head_branch": producer["branch"],
        "head_sha": producer["head_commit"],
        "name": producer["workflow_name"],
        "path": producer["workflow_path"],
        "workflow_id": producer["workflow_id"],
        "repository": {"full_name": producer["repository"]},
        "head_repository": {"full_name": producer["repository"]},
        "pull_requests": [],
        "head_commit": {
            "id": producer["head_commit"],
            "tree_id": producer["recipe_tree"],
        },
    }
    artifact = {
        "id": producer["artifact_id"],
        "name": producer["artifact_name"],
        "size_in_bytes": producer["artifact_size_bytes"],
        "digest": f"sha256:{producer['artifact_sha256']}",
        "expired": False,
        "archive_download_url": (
            f"https://api.github.com/repos/{producer['repository']}/actions/"
            f"artifacts/{producer['artifact_id']}/zip"
        ),
        "workflow_run": {
            "id": producer["run_id"],
            "head_branch": producer["branch"],
            "head_sha": producer["head_commit"],
            "repository_id": producer["repository_id"],
            "head_repository_id": producer["repository_id"],
        },
    }
    return run, artifact


def build_synthetic_lane(
    tmp_path: Path, mutation: str | None = None
) -> tuple[Any, dict[str, Any], Path, Path, Path, Path, Path]:
    module = load_module()
    authority = copy.deepcopy(authority_payload())
    member_payloads = {
        row["path"]: f"synthetic:{row['path']}\n".encode()
        for row in authority["archive"]["members"]
    }
    for row in authority["archive"]["members"]:
        payload = member_payloads[row["path"]]
        row["size_bytes"] = len(payload)
        row["sha256"] = hashlib.sha256(payload).hexdigest()
    authority["archive"]["uncompressed_size_bytes"] = sum(
        len(payload) for payload in member_payloads.values()
    )
    by_path = {row["path"]: row for row in authority["archive"]["members"]}
    validator = authority["validator_authority"]
    validator["runtime_package_plane_lock"]["sha256"] = by_path[
        "runtime-package-plane.lock.json"
    ]["sha256"]
    validator["inventory"]["sha256"] = by_path[
        "chummer-core-runtime-packages.inventory.json"
    ]["sha256"]
    validator["receipt"]["sha256"] = by_path["no-siblings.v3.receipt.json"][
        "sha256"
    ]

    runner_temp = tmp_path / "runner"
    runner_temp.mkdir(mode=0o700)
    workspace = runner_temp / "core-main-runtime.synthetic"
    workspace.mkdir(mode=0o700)
    archive_path = workspace / "artifact.zip"
    infos: list[tuple[zipfile.ZipInfo, bytes]] = []
    for index, row in enumerate(authority["archive"]["members"]):
        name = "../escape" if mutation == "zip_slip" and index == 0 else row["path"]
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.create_version = 45
        info.extract_version = 20
        info.flag_bits = 8
        mode = stat.S_IFLNK | 0o777 if mutation == "symlink" and index == 0 else stat.S_IFREG | 0o644
        info.external_attr = mode << 16
        info.compress_type = zipfile.ZIP_STORED
        infos.append((info, member_payloads[row["path"]]))
    if mutation == "duplicate":
        infos.append((copy.copy(infos[0][0]), infos[0][1]))
    if mutation == "extra":
        extra = zipfile.ZipInfo("foreign.txt", date_time=(1980, 1, 1, 0, 0, 0))
        extra.create_system = 3
        extra.create_version = 45
        extra.extract_version = 20
        extra.flag_bits = 8
        extra.external_attr = (stat.S_IFREG | 0o644) << 16
        extra.compress_type = zipfile.ZIP_STORED
        infos.append((extra, b"foreign\n"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        archive_buffer = NonSeekableBytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            for info, payload in infos:
                archive.writestr(info, payload)
        archive_path.write_bytes(archive_buffer.getvalue())
    archive_path.chmod(0o600)
    archive_bytes = archive_path.read_bytes()
    authority["producer"]["artifact_size_bytes"] = len(archive_bytes)
    authority["producer"]["artifact_sha256"] = hashlib.sha256(archive_bytes).hexdigest()
    validator["artifact_selector"]["sha256"] = authority["producer"][
        "artifact_sha256"
    ]
    authority_path = tmp_path / "authority.json"
    write_json(authority_path, authority)
    run, artifact = api_metadata(authority)
    run_path = workspace / "run.json"
    artifact_path = workspace / "artifact.json"
    write_json(run_path, run)
    write_json(artifact_path, artifact)
    return (
        module,
        authority,
        authority_path,
        runner_temp,
        workspace,
        run_path,
        artifact_path,
    )


def test_committed_authority_is_the_exact_verified_main_snapshot() -> None:
    module = load_module()
    raw = AUTHORITY_PATH.read_bytes()
    authority = module.load_authority(AUTHORITY_PATH)
    producer = authority["producer"]

    assert hashlib.sha256(raw).hexdigest() == AUTHORITY_SHA256
    assert producer == {
        "repository": "ArchonMegalon/chummer6-core",
        "repository_id": 1178942851,
        "workflow_id": 315904519,
        "workflow_name": "Core package-plane",
        "workflow_path": ".github/workflows/package-plane.yml",
        "run_id": 32748122851,
        "run_attempt": 1,
        "event": "push",
        "branch": "main",
        "head_commit": "a8e191ea49f2cac8a3f695c56812254d34cbd669",
        "recipe_tree": "87369e1fa54f36b00d6527ff2efb89e048db4165",
        "artifact_id": 9528212865,
        "artifact_name": (
            "chummer-core-runtime-package-plane-"
            "a8e191ea49f2cac8a3f695c56812254d34cbd669"
        ),
        "artifact_sha256": (
            "048f5bbd927ba15f0b2e6ea0695e35ef9fceeef51b30afc6ad09c9ac60267d28"
        ),
        "artifact_size_bytes": 1546656,
    }
    assert authority["archive"]["member_count"] == 11
    assert authority["archive"]["uncompressed_size_bytes"] == 1544098
    assert len(authority["archive"]["members"]) == 11
    assert len(
        [
            row
            for row in authority["archive"]["members"]
            if row["path"].startswith("packages/")
        ]
    ) == 8


def test_committed_owner_authority_rows_are_exact() -> None:
    authority = authority_payload()["validator_authority"]
    assert authority["owner_package_plane_lock_sha256"] == (
        "ac731fe6e4ce7f9f2b7173fcec600769f0f76566734dc962f0ed61f68527e1fd"
    )
    assert authority["owner_package_inventory_sha256"] == (
        "81c92d4c8ce94a302fd094f6eb666bf32e338e5047b9c91b8fb37058192ab4d0"
    )
    assert [
        (row["id"], row["sha256"], row["size_bytes"])
        for row in authority["owner_package_inventory"]["packages"]
    ] == [
        (
            "Chummer.Engine.Contracts",
            "45d77b32fd5eb63b5bfe0a1ee0fe2af0406ec20dbbd07efa58cd203ceac2977a",
            412578,
        ),
        (
            "Chummer.Hub.Registry.Contracts",
            "542844e6c7a349b5c0ec563e1911cf28831eb9736cad77e672996c8263239905",
            161221,
        ),
        (
            "Chummer.Play.Contracts",
            "eb9e7fe81920109b9dba662727cedb2fa1f960942b8bef7e1a3ee207c841db46",
            103938,
        ),
        (
            "Chummer.Run.Contracts",
            "1730990ececc0d5cf6a4a310b0999d701065ddd0e83613e7980075e491e3b3c2",
            406660,
        ),
    ]


def test_workflow_is_pinned_minimal_and_has_one_shot_consumption() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    trigger = workflow.get("on", workflow.get(True))
    assert workflow["permissions"] == {"contents": "read"}
    assert set(trigger) == {"workflow_dispatch", "push"}
    assert trigger["push"]["branches"] == ["main"]
    steps = workflow["jobs"]["consume"]["steps"]
    uses = [step["uses"] for step in steps if "uses" in step]
    assert uses == [
        "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    ]
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", value) for value in uses)
    assert not any("download-artifact" in value for value in uses)
    lifecycle = steps[1]
    assert lifecycle["env"]["CORE_ARTIFACT_READ_TOKEN"] == (
        "${{ secrets.CHUMMER_CORE_ARTIFACT_READ_TOKEN }}"
    )
    script = lifecycle["run"]
    for value in (
        "actions/runs/32748122851",
        "actions/artifacts/9528212865",
        "actions/artifacts/9528212865/zip",
        "--max-filesize 16777216",
        "ulimit -f 32768",
        'trap cleanup_snapshot EXIT',
        '--artifact-root "${export_root}"',
        '"${consumer}" finalize',
        'test ! -e "${snapshot_dir}"',
    ):
        assert value in script
    after_finalize = script.split('"${consumer}" finalize', 1)[1]
    assert "export_root" not in after_finalize
    assert steps[2]["with"]["path"] == (
        "${{ runner.temp }}/core-main-runtime-artifact-verdict.json"
    )


def test_api_metadata_requires_real_main_push_tree_and_exact_artifact() -> None:
    module = load_module()
    authority = module.load_authority(AUTHORITY_PATH)
    run, artifact = api_metadata(authority)
    module.validate_api_metadata(authority, run, artifact)

    hostile_run = copy.deepcopy(run)
    hostile_run["event"] = "pull_request"
    with pytest.raises(module.ConsumerError, match="workflow run metadata"):
        module.validate_api_metadata(authority, hostile_run, artifact)

    hostile_artifact = copy.deepcopy(artifact)
    hostile_artifact["workflow_run"]["head_sha"] = "f" * 40
    with pytest.raises(module.ConsumerError, match="artifact API metadata"):
        module.validate_api_metadata(authority, run, hostile_artifact)


def test_prepare_extracts_only_exact_regular_members_with_exact_modes(
    tmp_path: Path,
) -> None:
    (
        module,
        _authority,
        authority_path,
        runner_temp,
        workspace,
        run_path,
        artifact_path,
    ) = build_synthetic_lane(tmp_path)
    export_root = workspace / "artifact-root"
    validator_authority = workspace / "validator-authority.json"
    module.prepare(
        authority_path,
        run_path,
        artifact_path,
        workspace / "artifact.zip",
        runner_temp,
        workspace,
        export_root,
        validator_authority,
    )

    assert stat.S_IMODE(export_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((export_root / "packages").stat().st_mode) == 0o755
    extracted_files = [path for path in export_root.rglob("*") if path.is_file()]
    assert len(extracted_files) == 11
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o644 for path in extracted_files)
    assert stat.S_IMODE(validator_authority.stat().st_mode) == 0o600
    module.cleanup(authority_path, runner_temp, workspace)
    assert not workspace.exists()


@pytest.mark.parametrize("mutation", ["zip_slip", "duplicate", "symlink", "extra"])
def test_prepare_rejects_hostile_zip_layouts(
    tmp_path: Path, mutation: str
) -> None:
    (
        module,
        _authority,
        authority_path,
        runner_temp,
        workspace,
        run_path,
        artifact_path,
    ) = build_synthetic_lane(tmp_path, mutation)
    with pytest.raises(module.ConsumerError):
        module.prepare(
            authority_path,
            run_path,
            artifact_path,
            workspace / "artifact.zip",
            runner_temp,
            workspace,
            workspace / "artifact-root",
            workspace / "validator-authority.json",
        )
    module.cleanup(authority_path, runner_temp, workspace)
    assert not workspace.exists()


def validator_result(authority: dict[str, Any], contract: str) -> dict[str, Any]:
    validator = authority["validator_authority"]
    result: dict[str, Any] = {
        "contract": contract,
        "status": "pass",
        "outer_artifact_selector": validator["artifact_selector"],
        "member_count": 11,
        "package_count": 8,
        "package_recipe_commit": authority["producer"]["head_commit"],
        "runtime_source_commit": validator["runtime_source_commit"],
        "runtime_package_plane_lock": validator["runtime_package_plane_lock"],
        "inventory": {"sha256": validator["inventory"]["sha256"]},
        "receipt": {"sha256": validator["receipt"]["sha256"]},
        "ordered_package_ids": [
            "Chummer.Engine.Contracts",
            "Chummer.Application",
            "Chummer.Rulesets.Hosting",
            "Chummer.Rulesets.Sr5",
            "Chummer.Rulesets.Sr6",
            "Chummer.Infrastructure",
            "Chummer.Rulesets.Sr4",
            "Chummer.Engine.GmCharacterEdits",
        ],
        "checks": {"exact_eleven_member_layout": "pass"},
    }
    if contract.endswith("/v3"):
        result["post_validation_consumption_authority"] = {
            "contract": "github-actions.immutable-artifact-selector/v1",
            "artifact_id": authority["producer"]["artifact_id"],
            "sha256": authority["producer"]["artifact_sha256"],
        }
        result["artifact_byte_snapshot"] = {
            "contract": "chummer-hub.core-runtime-package-byte-snapshot/v1",
            "sha256": authority["archive"]["validator_byte_snapshot_sha256"],
            "member_count": 11,
            "source_path_posture": "not_attested_after_snapshot_capture",
        }
    return result


def test_verdict_rejects_v2_and_requires_v3_snapshot() -> None:
    module = load_module()
    authority = module.load_authority(AUTHORITY_PATH)
    with pytest.raises(module.ConsumerError, match="immutable-snapshot v3"):
        module.validation_summary(
            authority,
            validator_result(
                authority,
                "chummer-hub.core-runtime-package-artifact-validation/v2",
            ),
        )

    v3_result = validator_result(authority, module.VALIDATION_V3)
    v3 = module.validation_summary(authority, v3_result)
    assert v3["artifact_byte_snapshot"] == {
        "contract": "chummer-hub.core-runtime-package-byte-snapshot/v1",
        "sha256": "b5875da488e804b5f6eff33b81d0f1080b1b2b6c4dcf45676dbe451693e2a68a",
        "member_count": 11,
        "source_path_posture": "not_attested_after_snapshot_capture",
    }
    del v3_result["artifact_byte_snapshot"]
    with pytest.raises(module.ConsumerError, match="byte snapshot"):
        module.validation_summary(authority, v3_result)


def test_finalize_deletes_artifact_root_before_recording_only_verdict(
    tmp_path: Path,
) -> None:
    (
        module,
        authority,
        authority_path,
        runner_temp,
        workspace,
        run_path,
        artifact_path,
    ) = build_synthetic_lane(tmp_path)
    export_root = workspace / "artifact-root"
    module.prepare(
        authority_path,
        run_path,
        artifact_path,
        workspace / "artifact.zip",
        runner_temp,
        workspace,
        export_root,
        workspace / "validator-authority.json",
    )
    validation_path = workspace / "validation.json"
    write_json(validation_path, validator_result(authority, module.VALIDATION_V3))
    verdict_path = runner_temp / "core-main-runtime-artifact-verdict.json"

    module.finalize(
        authority_path,
        validation_path,
        runner_temp,
        workspace,
        verdict_path,
    )

    assert not workspace.exists()
    assert {path.name for path in runner_temp.iterdir()} == {verdict_path.name}
    assert stat.S_IMODE(verdict_path.stat().st_mode) == 0o600
    rendered = verdict_path.read_text(encoding="utf-8")
    assert "artifact-root" not in rendered
    assert "not_attested_after_snapshot_capture" in rendered


def test_archive_leaf_swap_is_rejected_without_descriptor_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        module,
        _authority,
        authority_path,
        runner_temp,
        workspace,
        run_path,
        artifact_path,
    ) = build_synthetic_lane(tmp_path)
    archive_path = workspace / "artifact.zip"
    original_archive = tmp_path / "original-artifact.zip"
    hostile_archive = tmp_path / "hostile-artifact.zip"
    hostile_archive.write_bytes(b"hostile replacement\n")
    hostile_archive.chmod(0o600)
    real_open = module.os.open
    swapped = False

    def swap_before_archive_open(
        path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        nonlocal swapped
        if path == "artifact.zip" and dir_fd is not None and not swapped:
            swapped = True
            os.rename(archive_path, original_archive)
            os.rename(hostile_archive, archive_path)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    before = open_descriptor_count()
    with monkeypatch.context() as patcher:
        patcher.setattr(module.os, "open", swap_before_archive_open)
        with pytest.raises(module.ConsumerError, match="downloaded archive"):
            module.prepare(
                authority_path,
                run_path,
                artifact_path,
                archive_path,
                runner_temp,
                workspace,
                workspace / "artifact-root",
                workspace / "validator-authority.json",
            )
    assert swapped
    assert open_descriptor_count() == before
    archive_path.unlink()
    original_archive.rename(archive_path)
    module.cleanup(authority_path, runner_temp, workspace)
    assert not workspace.exists()


def test_extraction_directory_swap_never_writes_through_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        module,
        _authority,
        authority_path,
        runner_temp,
        workspace,
        run_path,
        artifact_path,
    ) = build_synthetic_lane(tmp_path)
    export_root = workspace / "artifact-root"
    packages_path = export_root / "packages"
    held_packages_path = export_root / "packages-held"
    outside = tmp_path / "outside-packages"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("do not touch\n", encoding="utf-8")
    real_open = module.os.open
    swapped = False

    def swap_packages_before_member_create(
        path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        nonlocal swapped
        if (
            isinstance(path, str)
            and path.endswith(".nupkg")
            and flags & os.O_CREAT
            and dir_fd is not None
            and not swapped
        ):
            swapped = True
            os.rename(packages_path, held_packages_path)
            os.symlink(outside, packages_path, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    before = open_descriptor_count()
    with monkeypatch.context() as patcher:
        patcher.setattr(module.os, "open", swap_packages_before_member_create)
        with pytest.raises(module.ConsumerError, match="packages directory path"):
            module.prepare(
                authority_path,
                run_path,
                artifact_path,
                workspace / "artifact.zip",
                runner_temp,
                workspace,
                export_root,
                workspace / "validator-authority.json",
            )
    assert swapped
    assert list(outside.iterdir()) == [sentinel]
    assert open_descriptor_count() == before
    packages_path.unlink()
    held_packages_path.rename(packages_path)
    module.cleanup(authority_path, runner_temp, workspace)
    assert not workspace.exists()


def test_finalize_cleanup_uses_held_root_and_fails_closed_on_root_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        module,
        authority,
        authority_path,
        runner_temp,
        workspace,
        run_path,
        artifact_path,
    ) = build_synthetic_lane(tmp_path)
    export_root = workspace / "artifact-root"
    held_export_root = workspace / "artifact-root-held"
    outside = tmp_path / "outside-cleanup"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("do not touch\n", encoding="utf-8")
    module.prepare(
        authority_path,
        run_path,
        artifact_path,
        workspace / "artifact.zip",
        runner_temp,
        workspace,
        export_root,
        workspace / "validator-authority.json",
    )
    write_json(
        workspace / "validation.json",
        validator_result(authority, module.VALIDATION_V3),
    )
    verdict_path = runner_temp / "core-main-runtime-artifact-verdict.json"
    real_unlink = module.os.unlink
    swapped = False

    def swap_root_during_package_cleanup(
        path: Any, *, dir_fd: int | None = None
    ) -> None:
        nonlocal swapped
        if (
            isinstance(path, str)
            and path.endswith(".nupkg")
            and dir_fd is not None
            and not swapped
        ):
            swapped = True
            os.rename(export_root, held_export_root)
            os.symlink(outside, export_root, target_is_directory=True)
        real_unlink(path, dir_fd=dir_fd)

    before = open_descriptor_count()
    with monkeypatch.context() as patcher:
        patcher.setattr(module.os, "unlink", swap_root_during_package_cleanup)
        with pytest.raises(module.ConsumerError, match="extraction root path"):
            module.finalize(
                authority_path,
                workspace / "validation.json",
                runner_temp,
                workspace,
                verdict_path,
            )
    assert swapped
    assert not verdict_path.exists()
    assert list(outside.iterdir()) == [sentinel]
    assert open_descriptor_count() == before
    export_root.unlink()
    held_export_root.rename(export_root)
    module.cleanup(authority_path, runner_temp, workspace)
    assert not workspace.exists()


def test_verdict_write_uses_held_runner_and_removes_output_after_runner_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        module,
        authority,
        authority_path,
        runner_temp,
        workspace,
        run_path,
        artifact_path,
    ) = build_synthetic_lane(tmp_path)
    module.prepare(
        authority_path,
        run_path,
        artifact_path,
        workspace / "artifact.zip",
        runner_temp,
        workspace,
        workspace / "artifact-root",
        workspace / "validator-authority.json",
    )
    write_json(
        workspace / "validation.json",
        validator_result(authority, module.VALIDATION_V3),
    )
    verdict_path = runner_temp / "core-main-runtime-artifact-verdict.json"
    held_runner = runner_temp.with_name(f"{runner_temp.name}-held")
    real_open = module.os.open
    swapped = False

    def swap_runner_before_verdict_create(
        path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        nonlocal swapped
        if path == verdict_path.name and flags & os.O_CREAT and not swapped:
            swapped = True
            os.rename(runner_temp, held_runner)
            os.mkdir(runner_temp, mode=0o700)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    before = open_descriptor_count()
    with monkeypatch.context() as patcher:
        patcher.setattr(module.os, "open", swap_runner_before_verdict_create)
        with pytest.raises(module.ConsumerError, match="runner temp path"):
            module.finalize(
                authority_path,
                workspace / "validation.json",
                runner_temp,
                workspace,
                verdict_path,
            )
    assert swapped
    assert open_descriptor_count() == before
    assert not (held_runner / verdict_path.name).exists()
    assert not verdict_path.exists()
    runner_temp.rmdir()
    held_runner.rename(runner_temp)
    assert not workspace.exists()
