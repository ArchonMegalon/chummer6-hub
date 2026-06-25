from __future__ import annotations

import importlib.util
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_public_edge_deploy_source.py"
SPEC = importlib.util.spec_from_file_location("verify_public_edge_deploy_source", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def make_repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Chummer Tests")
    (repo / "README.md").write_text("clean deploy source\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-qm", "initial")
    return repo, git(repo, "rev-parse", "HEAD")


def test_clean_source_at_expected_head_passes() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, head = make_repo(Path(temp))

        receipt = MODULE.verify(repo, expected_head=head)

    assert receipt["status"] == "pass"
    assert receipt["dirtyLineCount"] == 0
    assert receipt["head"] == head


def test_dirty_source_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, head = make_repo(Path(temp))
        (repo / "README.md").write_text("dirty deploy source\n", encoding="utf-8")

        receipt = MODULE.verify(repo, expected_head=head)

    assert receipt["status"] == "fail"
    assert receipt["dirtyLineCount"] == 1
    assert any(finding["id"] == "dirty_worktree" for finding in receipt["findings"])


def test_untracked_source_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, head = make_repo(Path(temp))
        (repo / "untracked.txt").write_text("do not deploy me\n", encoding="utf-8")

        receipt = MODULE.verify(repo, expected_head=head)

    assert receipt["status"] == "fail"
    assert receipt["dirtyLineCount"] == 1
    assert any("untracked.txt" in line for line in receipt["dirtyLines"])


def test_wrong_expected_head_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="chummer-edge-source-") as temp:
        repo, _head = make_repo(Path(temp))
        wrong = "0" * 40

        receipt = MODULE.verify(repo, expected_head=wrong)

    assert receipt["status"] == "fail"
    assert any(finding["id"] == "wrong_head" for finding in receipt["findings"])
