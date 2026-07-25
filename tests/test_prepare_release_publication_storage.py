from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_release_publication_storage.py"
SPEC = importlib.util.spec_from_file_location(
    "prepare_release_publication_storage",
    SCRIPT,
)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_prepares_owner_only_session_root_and_writer_policy(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    downloads = tmp_path / "downloads"
    downloads.mkdir()

    MODULE.secure_session_tree(sessions, os.getuid(), os.getgid())
    policy = MODULE.ensure_writer_policy(downloads, os.getuid(), os.getgid())
    MODULE.ensure_writer_policy(downloads, os.getuid(), os.getgid())

    assert stat.S_IMODE(sessions.stat().st_mode) == 0o700
    assert stat.S_IMODE(policy.stat().st_mode) == 0o600
    assert json.loads(policy.read_text(encoding="utf-8")) == MODULE.WRITER_POLICY


def test_rejects_symlinked_writer_policy(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "outside.json"
    target.write_text("{}\n", encoding="utf-8")
    (downloads / MODULE.WRITER_POLICY_NAME).symlink_to(target)

    with pytest.raises(MODULE.StoragePreparationError, match="owner-only regular file"):
        MODULE.ensure_writer_policy(downloads, os.getuid(), os.getgid())


def test_rejects_noncanonical_existing_writer_policy(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    policy = downloads / MODULE.WRITER_POLICY_NAME
    policy.write_text('{"schemaVersion":"wrong","mode":"server-journal-v1"}\n')
    policy.chmod(0o600)

    with pytest.raises(MODULE.StoragePreparationError, match="noncanonical"):
        MODULE.ensure_writer_policy(downloads, os.getuid(), os.getgid())
