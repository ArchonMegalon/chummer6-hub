from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
POLICY_NAME = ".release-shelf-writer-policy.json"
POLICY = {
    "schemaVersion": "chummer.release-shelf.writer-policy/v1",
    "mode": "server-journal-v1",
}


def write_policy(root: Path) -> None:
    root.mkdir(parents=True)
    (root / POLICY_NAME).write_text(json.dumps(POLICY) + "\n", encoding="utf-8")


def test_all_supported_local_publishers_name_the_server_writer_policy() -> None:
    sources = (
        ROOT / "scripts" / "release_shelf_generation.py",
        ROOT / "scripts" / "publish-download-bundle.sh",
        ROOT / "scripts" / "runbook.sh",
        ROOT / "scripts" / "materialize-public-downloads-bundle.sh",
        ROOT / "scripts" / "generate-releases-manifest.sh",
        WORKSPACE / "chummer6-hub" / "scripts" / "release_shelf_generation.py",
        WORKSPACE / "chummer6-hub" / "scripts" / "publish-download-bundle.sh",
        WORKSPACE / "chummer-presentation" / "scripts" / "publish-download-bundle.sh",
        WORKSPACE / "chummer-presentation" / "scripts" / "publish-latest-nightly-to-downloads.sh",
    )
    for source in sources:
        text = source.read_text(encoding="utf-8")
        assert POLICY_NAME in text, source
        assert "server-journal-v1" in text or source.name in {
            "runbook.sh",
            "materialize-public-downloads-bundle.sh",
            "generate-releases-manifest.sh",
        }, source


def test_presentation_nightly_refuses_marked_production_root_before_any_write(
    tmp_path: Path,
) -> None:
    shelf = tmp_path / "downloads"
    write_policy(shelf)
    before = sorted(path.relative_to(shelf) for path in shelf.rglob("*"))
    script = (
        WORKSPACE
        / "chummer-presentation"
        / "scripts"
        / "publish-latest-nightly-to-downloads.sh"
    )

    completed = subprocess.run(
        ["bash", str(script), str(shelf)],
        cwd=script.parent.parent,
        env={**os.environ, "CHUMMER_FORCE_NIGHTLY_PUBLISH": "1"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "server-journal-v1" in completed.stderr
    assert sorted(path.relative_to(shelf) for path in shelf.rglob("*")) == before


def test_presentation_fixed_path_publisher_refuses_marked_root_before_bundle_checks(
    tmp_path: Path,
) -> None:
    shelf = tmp_path / "downloads"
    write_policy(shelf)
    bundle = tmp_path / "missing-bundle"
    script = WORKSPACE / "chummer-presentation" / "scripts" / "publish-download-bundle.sh"

    completed = subprocess.run(
        ["bash", str(script), str(bundle), str(shelf)],
        cwd=script.parent.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "server-journal-v1" in completed.stderr
    assert not (shelf / "current.json").exists()
    assert not (shelf / "generations").exists()
