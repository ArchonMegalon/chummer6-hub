from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_public_edge_deploy_authority.py"
SPEC = importlib.util.spec_from_file_location("verify_public_edge_deploy_authority", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def make_authorized_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "source"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Chummer Tests")
    (repo / "source.txt").write_text("trusted\n", encoding="utf-8")
    git(repo, "add", "source.txt")
    git(repo, "commit", "-qm", "trusted source")
    head = git(repo, "rev-parse", "HEAD")
    branch = git(repo, "branch", "--show-current")
    upstream_ref = "refs/remotes/origin/release-authority"
    git(repo, "remote", "add", "origin", "https://example.invalid/chummer.git")
    git(repo, "update-ref", upstream_ref, head)
    git(repo, "config", f"branch.{branch}.remote", "origin")
    git(repo, "config", f"branch.{branch}.merge", "refs/heads/release-authority")
    return repo, head, upstream_ref


def test_authority_requires_exact_head_and_configured_remote_ref(tmp_path: Path) -> None:
    repo, head, upstream_ref = make_authorized_repo(tmp_path)

    receipt = MODULE.verify_authority(
        repo,
        expected_head=head,
        expected_upstream_ref=upstream_ref,
    )

    assert receipt["status"] == "pass"
    assert receipt["head"] == head
    assert receipt["upstreamHead"] == head
    assert receipt["configuredUpstreamRef"] == upstream_ref


@pytest.mark.parametrize(
    "expected_head",
    ("", "HEAD", "main", "a" * 39, "g" * 40),
)
def test_authority_rejects_non_full_commit_authority(
    tmp_path: Path, expected_head: str
) -> None:
    repo, _head, upstream_ref = make_authorized_repo(tmp_path)

    with pytest.raises(ValueError, match="full 40-hex"):
        MODULE.verify_authority(
            repo,
            expected_head=expected_head,
            expected_upstream_ref=upstream_ref,
        )


@pytest.mark.parametrize(
    "upstream_ref",
    ("", "origin/main", "refs/heads/main", "refs/remotes/origin/../main", "refs/remotes/origin/main.lock"),
)
def test_authority_rejects_abbreviated_or_unsafe_upstream_ref(
    tmp_path: Path, upstream_ref: str
) -> None:
    repo, head, _configured_upstream = make_authorized_repo(tmp_path)

    with pytest.raises(ValueError, match="refs/remotes"):
        MODULE.verify_authority(
            repo,
            expected_head=head,
            expected_upstream_ref=upstream_ref,
        )


def test_authority_rejects_different_configured_upstream(tmp_path: Path) -> None:
    repo, head, _upstream_ref = make_authorized_repo(tmp_path)
    other_ref = "refs/remotes/other/release-authority"
    git(repo, "update-ref", other_ref, head)

    with pytest.raises(ValueError, match="does not match expected"):
        MODULE.verify_authority(
            repo,
            expected_head=head,
            expected_upstream_ref=other_ref,
        )


def test_authority_rejects_upstream_commit_drift(tmp_path: Path) -> None:
    repo, head, upstream_ref = make_authorized_repo(tmp_path)
    (repo / "upstream.txt").write_text("new upstream\n", encoding="utf-8")
    git(repo, "add", "upstream.txt")
    git(repo, "commit", "-qm", "new upstream")
    newer = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", upstream_ref, newer)
    git(repo, "reset", "--hard", "-q", head)

    receipt = MODULE.verify_authority(
        repo,
        expected_head=head,
        expected_upstream_ref=upstream_ref,
    )

    assert receipt["status"] == "fail"
    assert any(item["id"] == "wrong_upstream_head" for item in receipt["findings"])


def test_authority_rejects_dirty_source_but_can_ignore_only_generated_receipts(
    tmp_path: Path,
) -> None:
    repo, head, upstream_ref = make_authorized_repo(tmp_path)
    proof = repo / ".codex-studio" / "published" / "receipt.json"
    proof.parent.mkdir(parents=True)
    proof.write_text("{}\n", encoding="utf-8")

    strict = MODULE.verify_authority(
        repo,
        expected_head=head,
        expected_upstream_ref=upstream_ref,
    )
    receipt_only = MODULE.verify_authority(
        repo,
        expected_head=head,
        expected_upstream_ref=upstream_ref,
        ignore_generated_proof_drift=True,
    )
    (repo / "source.txt").write_text("tampered\n", encoding="utf-8")
    tampered = MODULE.verify_authority(
        repo,
        expected_head=head,
        expected_upstream_ref=upstream_ref,
        ignore_generated_proof_drift=True,
    )

    assert strict["status"] == "fail"
    assert receipt_only["status"] == "pass"
    assert receipt_only["ignoredGeneratedProofDriftCount"] == 1
    assert tampered["status"] == "fail"
    assert any(item["id"] == "dirty_worktree" for item in tampered["findings"])


def test_authority_ignores_ambient_git_directory_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, head, upstream_ref = make_authorized_repo(tmp_path)
    decoy, _decoy_head, _decoy_ref = make_authorized_repo(tmp_path / "decoy-parent")
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))

    receipt = MODULE.verify_authority(
        repo,
        expected_head=head,
        expected_upstream_ref=upstream_ref,
    )

    assert receipt["status"] == "pass"
    assert receipt["repoRoot"] == str(repo.resolve())


def test_authority_cli_always_emits_json_receipt_on_success(tmp_path: Path) -> None:
    repo, head, upstream_ref = make_authorized_repo(tmp_path)

    result = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--expected-head",
            head,
            "--expected-upstream-ref",
            upstream_ref,
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["contractName"] == "chummer.public_edge_deploy_authority.v1"
    assert receipt["status"] == "pass"
