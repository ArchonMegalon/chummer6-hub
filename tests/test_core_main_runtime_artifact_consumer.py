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
AUTHORITY_SHA256 = "094b9c1f26f780c5b55229c1c53c8d42bbd1fdd70d8edb85522be01665282fd1"


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


def public_metadata(
    authority: dict[str, Any], receipt: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    producer = authority["producer"]
    public_release = authority["public_release"]
    bot = {
        "login": "github-actions[bot]",
        "id": 41898282,
        "type": "Bot",
        "site_admin": False,
    }
    assets = []
    for key in ("receipt_asset", "bundle_asset"):
        asset = public_release[key]
        assets.append(
            {
                "id": asset["id"],
                "name": asset["name"],
                "label": asset["label"],
                "content_type": asset["content_type"],
                "state": asset["state"],
                "size": asset["size_bytes"],
                "digest": f"sha256:{asset['sha256']}",
                "created_at": asset["created_at_utc"],
                "updated_at": asset["updated_at_utc"],
                "url": asset["api_url"],
                "browser_download_url": asset["download_url"],
                "download_count": 99,
                "uploader": bot,
            }
        )
    release = {
        "id": public_release["release_id"],
        "tag_name": public_release["tag_name"],
        "target_commitish": public_release["target_commit"],
        "name": public_release["name"],
        "body": public_release["body"],
        "draft": public_release["draft"],
        "prerelease": public_release["prerelease"],
        "immutable": public_release["immutable"],
        "created_at": public_release["created_at_utc"],
        "published_at": public_release["published_at_utc"],
        "updated_at": public_release["updated_at_utc"],
        "url": public_release["release_api_url"],
        "html_url": public_release["release_html_url"],
        "author": bot,
        "assets": assets,
    }
    tag = {
        "ref": f"refs/tags/{public_release['tag_name']}",
        "url": public_release["tag_api_url"].replace("/ref/tags/", "/refs/tags/"),
        "object": {
            "type": "commit",
            "sha": producer["head_commit"],
            "url": (
                f"https://api.github.com/repos/{producer['repository']}/git/commits/"
                f"{producer['head_commit']}"
            ),
        },
    }
    return release, tag, receipt


def public_receipt(authority: dict[str, Any]) -> dict[str, Any]:
    producer = authority["producer"]
    release = authority["public_release"]
    return {
        "contract": "chummer-core.runtime-package-public-handoff/v2",
        "repository": producer["repository"],
        "ref": "refs/heads/main",
        "commit": producer["head_commit"],
        "release_tag": release["tag_name"],
        "receipt_asset_name": release["receipt_asset"]["name"],
        "source_actions_artifact": {
            "id": producer["artifact_id"],
            "name": producer["artifact_name"],
            "sha256": producer["artifact_sha256"],
            "size_bytes": producer["artifact_size_bytes"],
            "workflow_run": {
                "id": producer["run_id"],
                "attempt": producer["run_attempt"],
                "event": producer["event"],
                "head_branch": producer["branch"],
                "head_sha": producer["head_commit"],
                "head_tree": producer["recipe_tree"],
                "repository": producer["repository"],
                "workflow_id": producer["workflow_id"],
                "workflow_ref": (
                    f"{producer['repository']}/{producer['workflow_path']}@refs/heads/"
                    f"{producer['branch']}"
                ),
                "workflow_sha": producer["head_commit"],
                "attempt_api_url": (
                    f"https://api.github.com/repos/{producer['repository']}/actions/runs/"
                    f"{producer['run_id']}/attempts/{producer['run_attempt']}"
                ),
            },
            "authenticated_metadata": {
                "api_url": (
                    f"https://api.github.com/repos/{producer['repository']}/actions/"
                    f"artifacts/{producer['artifact_id']}"
                ),
                "archive_download_url": (
                    f"https://api.github.com/repos/{producer['repository']}/actions/"
                    f"artifacts/{producer['artifact_id']}/zip"
                ),
                "created_at_utc": "2026-08-24T18:18:59Z",
                "expires_at_utc": "2026-08-29T18:18:58Z",
                "repository_id": producer["repository_id"],
                "head_repository_id": producer["repository_id"],
            },
        },
        "bundle": {
            "contract": "chummer-core.runtime-package-public-handoff-zip/v1",
            "asset_name": release["bundle_asset"]["name"],
            "sha256": release["bundle_asset"]["sha256"],
            "size_bytes": release["bundle_asset"]["size_bytes"],
            "member_count": authority["archive"]["member_count"],
            "uncompressed_size_bytes": authority["archive"]["uncompressed_size_bytes"],
            "members": authority["archive"]["members"],
        },
    }


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
    archive_path = workspace / "bundle.zip"
    infos: list[tuple[zipfile.ZipInfo, bytes]] = []
    for index, row in enumerate(authority["archive"]["members"]):
        name = "../escape" if mutation == "zip_slip" and index == 0 else row["path"]
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.create_version = 20
        info.extract_version = 20
        info.flag_bits = 0
        mode = stat.S_IFLNK | 0o777 if mutation == "symlink" and index == 0 else stat.S_IFREG | 0o644
        info.external_attr = mode << 16
        info.compress_type = zipfile.ZIP_STORED
        infos.append((info, member_payloads[row["path"]]))
    if mutation == "duplicate":
        infos.append((copy.copy(infos[0][0]), infos[0][1]))
    if mutation == "extra":
        extra = zipfile.ZipInfo("foreign.txt", date_time=(1980, 1, 1, 0, 0, 0))
        extra.create_system = 3
        extra.create_version = 20
        extra.extract_version = 20
        extra.flag_bits = 0
        extra.external_attr = (stat.S_IFREG | 0o644) << 16
        extra.compress_type = zipfile.ZIP_STORED
        infos.append((extra, b"foreign\n"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            for info, payload in infos:
                archive.writestr(info, payload)
        archive_path.write_bytes(archive_buffer.getvalue())
    archive_path.chmod(0o600)
    archive_bytes = archive_path.read_bytes()
    authority["public_release"]["bundle_asset"]["size_bytes"] = len(archive_bytes)
    authority["public_release"]["bundle_asset"]["sha256"] = hashlib.sha256(
        archive_bytes
    ).hexdigest()
    receipt = public_receipt(authority)
    receipt_path = workspace / "receipt.json"
    write_json(receipt_path, receipt)
    receipt_bytes = receipt_path.read_bytes()
    authority["public_release"]["receipt_asset"]["size_bytes"] = len(receipt_bytes)
    authority["public_release"]["receipt_asset"]["sha256"] = hashlib.sha256(
        receipt_bytes
    ).hexdigest()
    authority_path = tmp_path / "authority.json"
    write_json(authority_path, authority)
    release, tag, _receipt = public_metadata(authority, receipt)
    release_path = workspace / "release.json"
    tag_path = workspace / "tag.json"
    write_json(release_path, release)
    write_json(tag_path, tag)
    return (
        module,
        authority,
        authority_path,
        runner_temp,
        workspace,
        release_path,
        tag_path,
    )


def test_committed_authority_is_the_exact_public_main_snapshot() -> None:
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
        "run_id": 32761161259,
        "run_attempt": 1,
        "event": "push",
        "branch": "main",
        "head_commit": "c6138ff7ca27d66e85b223d0b29381cff4811277",
        "recipe_tree": "a18d8c0336a3d6c445fb6237098d7393cbf851ae",
        "artifact_id": 9532906073,
        "artifact_name": (
            "chummer-core-runtime-package-plane-"
            "c6138ff7ca27d66e85b223d0b29381cff4811277"
        ),
        "artifact_sha256": (
            "985c4a63b47ad585f042815226e6173595212003d2fe34fabfdbf49fae28f1b6"
        ),
        "artifact_size_bytes": 1546942,
    }
    release = authority["public_release"]
    assert release["release_id"] == 375901074
    assert release["target_commit"] == producer["head_commit"]
    assert release["immutable"] is False
    assert (release["receipt_asset"]["id"], release["receipt_asset"]["sha256"]) == (
        527996284,
        "f5fb506fde7f51c39ee982f3e8e935433f6dd7401e243a62643563a37a71dd0f",
    )
    assert (release["bundle_asset"]["id"], release["bundle_asset"]["sha256"]) == (
        527996285,
        "76943cee5aa7761adf6f13cf8e641d03cf9892ea2ab795d2c9a4e0de6ccd9ce9",
    )
    assert authority["archive"]["member_count"] == 11
    assert authority["archive"]["uncompressed_size_bytes"] == 1544384
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


def test_workflow_is_anonymous_pinned_bounded_and_one_shot() -> None:
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
    assert lifecycle["env"] == {"PYTHONDONTWRITEBYTECODE": "1"}
    script = lifecycle["run"]
    for value in (
        "releases/375901074",
        "git/ref/tags/${tag}",
        "core-runtime-package-plane-c6138ff7ca27d66e85b223d0b29381cff4811277",
        "--max-filesize 65536",
        "--max-filesize 16777216",
        "ulimit -f 32768",
        'trap cleanup_snapshot EXIT',
        '--release-metadata "${snapshot_dir}/release.json"',
        '--tag-metadata "${snapshot_dir}/tag.json"',
        '--receipt "${snapshot_dir}/receipt.json"',
        '--bundle "${snapshot_dir}/bundle.zip"',
        '--artifact-root "${export_root}"',
        '"${consumer}" finalize',
        'test ! -e "${snapshot_dir}"',
    ):
        assert value in script
    assert "secrets." not in script
    assert "Authorization:" not in script
    assert "/latest" not in script
    assert "/actions/artifacts/" not in script
    after_finalize = script.split('"${consumer}" finalize', 1)[1]
    assert "export_root" not in after_finalize
    assert steps[2]["with"]["path"] == (
        "${{ runner.temp }}/core-main-runtime-artifact-verdict.json"
    )


def test_public_metadata_requires_exact_release_tag_assets_and_v2_receipt() -> None:
    module = load_module()
    authority = module.load_authority(AUTHORITY_PATH)
    receipt = public_receipt(authority)
    release, tag, receipt = public_metadata(authority, receipt)
    module.validate_public_release_metadata(authority, release, tag, receipt)

    hostile_tag = copy.deepcopy(tag)
    hostile_tag["object"]["sha"] = "f" * 40
    with pytest.raises(module.ConsumerError, match="direct release tag"):
        module.validate_public_release_metadata(authority, release, hostile_tag, receipt)

    hostile_receipt = copy.deepcopy(receipt)
    hostile_receipt["source_actions_artifact"]["workflow_run"]["head_tree"] = "f" * 40
    with pytest.raises(module.ConsumerError, match="workflow provenance"):
        module.validate_public_release_metadata(
            authority, release, tag, hostile_receipt
        )

    hostile_release = copy.deepcopy(release)
    hostile_release["assets"][1]["digest"] = "sha256:" + "f" * 64
    with pytest.raises(module.ConsumerError, match="bundle_asset .*metadata"):
        module.validate_public_release_metadata(
            authority, hostile_release, tag, receipt
        )


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
        workspace / "receipt.json",
        workspace / "bundle.zip",
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
            workspace / "receipt.json",
            workspace / "bundle.zip",
            runner_temp,
            workspace,
            workspace / "artifact-root",
            workspace / "validator-authority.json",
        )
    module.cleanup(authority_path, runner_temp, workspace)
    assert not workspace.exists()


def test_prepare_rejects_same_size_public_receipt_byte_substitution(
    tmp_path: Path,
) -> None:
    (
        module,
        _authority,
        authority_path,
        runner_temp,
        workspace,
        release_path,
        tag_path,
    ) = build_synthetic_lane(tmp_path)
    receipt_path = workspace / "receipt.json"
    payload = bytearray(receipt_path.read_bytes())
    assert payload[-1:] == b"\n"
    payload[-1] = ord(" ")
    receipt_path.write_bytes(payload)
    receipt_path.chmod(0o600)

    with pytest.raises(module.ConsumerError, match="receipt SHA-256"):
        module.prepare(
            authority_path,
            release_path,
            tag_path,
            receipt_path,
            workspace / "bundle.zip",
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
        "sha256": "83e500154045c0cec7700c6307df096799edb6d958341b4480bdc1e35ab51e17",
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
        workspace / "receipt.json",
        workspace / "bundle.zip",
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
    archive_path = workspace / "bundle.zip"
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
        if path == "bundle.zip" and dir_fd is not None and not swapped:
            swapped = True
            os.rename(archive_path, original_archive)
            os.rename(hostile_archive, archive_path)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    before = open_descriptor_count()
    with monkeypatch.context() as patcher:
        patcher.setattr(module.os, "open", swap_before_archive_open)
        with pytest.raises(module.ConsumerError, match="downloaded public bundle"):
            module.prepare(
                authority_path,
                run_path,
                artifact_path,
                workspace / "receipt.json",
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
                workspace / "receipt.json",
                workspace / "bundle.zip",
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
        workspace / "receipt.json",
        workspace / "bundle.zip",
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
        workspace / "receipt.json",
        workspace / "bundle.zip",
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
