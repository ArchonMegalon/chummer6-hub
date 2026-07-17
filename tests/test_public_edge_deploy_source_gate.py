from __future__ import annotations

import importlib.util
import re
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


def test_public_edge_rebuild_scripts_call_source_gate() -> None:
    script_paths = [
        ROOT / "scripts" / "e2e-hub.sh",
        ROOT / "scripts" / "e2e-portal.sh",
        ROOT / "scripts" / "migration-loop.sh",
        ROOT / "scripts" / "ai" / "hub_closeout.sh",
    ]

    for script_path in script_paths:
        script = script_path.read_text(encoding="utf-8")
        assert "CHUMMER_PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" in script
        assert "scripts/check_public_edge_deploy_preflight.py" in script
        rebuild_match = re.search(
            r'(?:docker|"\$BUILD_PROVENANCE_DOCKER_BINARY") compose[^\n]+up -d --build',
            script,
        )
        assert rebuild_match is not None
        assert script.index("scripts/check_public_edge_deploy_preflight.py") < rebuild_match.start()
        if script_path.name != "e2e-portal.sh":
            assert "CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE" in script
            assert "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD" in script
            assert "scripts/verify_public_edge_deploy_source.py" in script
            assert "--expected-head" in script
        assert (
            "docker compose" in script
            or '"$BUILD_PROVENANCE_DOCKER_BINARY" compose' in script
        )


def test_hub_closeout_preflight_cannot_be_disabled() -> None:
    script = (
        ROOT / "scripts" / "ai" / "hub_closeout.sh"
    ).read_text(encoding="utf-8")

    assert "Public-edge deploy preflight is mandatory and cannot be disabled." in script
    assert "exit 2" in script
    assert re.search(
        r"if \[\[ \"\$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE\" == \"0\".*?exit 2.*?"
        r"python3 scripts/check_public_edge_deploy_preflight.py",
        script,
        re.DOTALL,
    )


def test_public_edge_rebuild_source_gate_still_covers_source_checked_scripts() -> None:
    script_paths = [
        ROOT / "scripts" / "e2e-hub.sh",
        ROOT / "scripts" / "migration-loop.sh",
        ROOT / "scripts" / "ai" / "hub_closeout.sh",
    ]

    for script_path in script_paths:
        script = script_path.read_text(encoding="utf-8")
        assert "CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE" in script
        assert "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD" in script
        assert "scripts/verify_public_edge_deploy_source.py" in script
        assert "--expected-head" in script
        assert (
            "docker compose" in script
            or '"$BUILD_PROVENANCE_DOCKER_BINARY" compose' in script
        )
