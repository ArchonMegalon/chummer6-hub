from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import release_shelf_generation as shelf  # noqa: E402

SCRIPT = SCRIPTS / "sync_active_release_compatibility_mirror.py"
SPEC = importlib.util.spec_from_file_location(
    "sync_active_release_compatibility_mirror",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_candidate(root: Path) -> Path:
    files = root / "files"
    signing = root / "signing"
    evidence = root / "release-evidence"
    files.mkdir(parents=True)
    signing.mkdir()
    evidence.mkdir()
    artifact = files / "chummer-test-installer.exe"
    artifact.write_bytes(b"active-artifact")
    digest = shelf.sha256_file(artifact)
    canonical = {
        "version": "release-mirror-test",
        "releaseVersion": "release-mirror-test",
        "channel": "preview",
        "publishedAt": "2026-07-28T12:00:00Z",
        "artifacts": [
            {
                "artifactId": "test-installer",
                "fileName": artifact.name,
                "downloadUrl": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
                "installAccessClass": "open_public",
            }
        ],
    }
    compatibility = {
        "version": "release-mirror-test",
        "channel": "preview",
        "publishedAt": "2026-07-28T12:00:00Z",
        "downloads": [
            {
                "id": "test-installer",
                "fileName": artifact.name,
                "url": f"https://chummer.run/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
                "installAccessClass": "open_public",
            }
        ],
    }
    (root / shelf.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / shelf.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility, indent=2) + "\n",
        encoding="utf-8",
    )
    (signing / "test.receipt.json").write_text(
        '{"status":"pass"}\n',
        encoding="utf-8",
    )
    (evidence / "public-promotion.json").write_text(
        '{"status":"pass"}\n',
        encoding="utf-8",
    )
    return root


def prepare_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    shelf.prepare_layout(
        write_candidate(tmp_path / "candidate"),
        source,
        generation_id="generation-mirror-test",
        activated_at="2026-07-28T12:05:00Z",
        activation_receipt_id="activation-mirror-test",
    )
    (source / shelf.PROMOTION_LOCK).touch()
    return source


def test_check_reports_drift_without_mutation(tmp_path: Path) -> None:
    source = prepare_source(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    original = b'{"version":"stale"}\n'
    (target / shelf.COMPATIBILITY_MANIFEST).write_bytes(original)

    result = MODULE.sync_active_release_compatibility_mirror(
        source,
        target,
        apply=False,
    )

    assert result["status"] == "drift"
    assert result["inSync"] is False
    assert result["changed"] is False
    assert (target / shelf.COMPATIBILITY_MANIFEST).read_bytes() == original
    assert not list(target.glob(".release-compatibility-mirror-sync-*"))


def test_apply_syncs_active_generation_and_preserves_unrelated_files(
    tmp_path: Path,
) -> None:
    source = prepare_source(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("preserve me\n", encoding="utf-8")
    stale_files = target / "files"
    stale_files.mkdir()
    (stale_files / "stale.bin").write_bytes(b"stale")
    pointer_before = (source / shelf.CURRENT_POINTER).read_bytes()
    mode, generation, _ = shelf.resolve_shelf_root(source)
    assert mode == "generation"

    result = MODULE.sync_active_release_compatibility_mirror(
        source,
        target,
        apply=True,
    )

    assert result["status"] == "pass"
    assert result["changed"] is True
    assert result["generationId"] == "generation-mirror-test"
    assert result["releaseVersion"] == "release-mirror-test"
    assert (target / "README.md").read_text(encoding="utf-8") == "preserve me\n"
    assert MODULE.managed_snapshot(target) == MODULE.managed_snapshot(generation)
    assert (source / shelf.CURRENT_POINTER).read_bytes() == pointer_before
    assert (target / "signing" / "test.receipt.json").is_file()
    assert not list(target.glob(".release-compatibility-mirror-sync-*"))


def test_apply_rejects_linked_target_without_following_it(tmp_path: Path) -> None:
    source = prepare_source(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    (target / "files").symlink_to(external, target_is_directory=True)
    pointer_before = (source / shelf.CURRENT_POINTER).read_bytes()

    with pytest.raises(
        MODULE.CompatibilityMirrorSyncError,
        match="managed mirror entry is not regular",
    ):
        MODULE.sync_active_release_compatibility_mirror(
            source,
            target,
            apply=True,
        )

    assert sentinel.read_text(encoding="utf-8") == "outside\n"
    assert (source / shelf.CURRENT_POINTER).read_bytes() == pointer_before


def test_apply_refuses_authoritative_target(tmp_path: Path) -> None:
    source = prepare_source(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    (target / shelf.CURRENT_POINTER).write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        MODULE.CompatibilityMirrorSyncError,
        match="release authority metadata",
    ):
        MODULE.sync_active_release_compatibility_mirror(
            source,
            target,
            apply=True,
        )
