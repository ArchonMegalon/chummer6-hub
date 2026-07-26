from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "scripts" / "quarantine_historical_release_bearer_configs.py"
)
SPEC = importlib.util.spec_from_file_location(
    "quarantine_historical_release_bearer_configs_test",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


SECRET = "historical-super-secret-ticket"
CONFIG_BYTES = (
    'silent\nheader = "Authorization: Bearer '
    + SECRET
    + '"\nshow-error\n'
).encode()


def write_candidate(root: Path, relative: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(CONFIG_BYTES)
    path.chmod(0o600)
    return path


def run_quarantine(
    root: Path,
    *extra: str,
    targets: list[str] | None = None,
) -> int:
    if targets is None:
        targets = sorted(
            path.relative_to(root).as_posix()
            for path in root.glob(
                f"run-*/**/{module.TARGET_FILE_NAME}"
            )
        )
    arguments = [
        "--release-root",
        str(root),
        "--quarantine",
        "--confirm",
        module.QUARANTINE_CONFIRMATION,
        *extra,
    ]
    for target in targets:
        arguments.extend(("--target", target))
    return module.run(arguments)


@pytest.mark.parametrize(
    "line",
    (
        b'header = "Authorization: Bearer ticket"',
        b'oauth2-bearer = "ticket"',
        b'oauth2-bearer: "ticket"',
        b'oauth2-bearer "ticket"',
        b'--oauth2-bearer "ticket"',
    ),
)
def test_bearer_detector_accepts_curl_config_grammar(line: bytes) -> None:
    assert module._contains_bearer_material(line + b"\n")


@pytest.mark.parametrize(
    "line",
    (
        b"# oauth2-bearer = ticket",
        b"oauth2-bearer-disabled = ticket",
        b"oauth2-bearer",
        b'header = "Authorization: Basic ticket"',
    ),
)
def test_bearer_detector_rejects_comments_and_similar_names(
    line: bytes,
) -> None:
    assert not module._contains_bearer_material(line + b"\n")


def test_audit_is_redacted_and_scoped_to_release_runs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-193632/nested/upload-auth.curl",
    )
    ignored = write_candidate(
        tmp_path,
        "not-a-release-run/upload-auth.curl",
    )
    external_receipt = tmp_path / "receipts" / "audit.json"

    assert (
        module.run(
            [
                "--release-root",
                str(tmp_path),
                "--receipt",
                str(external_receipt),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert SECRET not in captured.out
    assert hashlib.sha256(CONFIG_BYTES).hexdigest() not in captured.out
    result = json.loads(captured.out)
    assert result["status"] == "findings"
    assert result["candidateCount"] == 1
    assert result["bearerMaterialCount"] == 1
    assert result["candidates"][0]["relativePath"] == (
        "run-20260724-193632/nested/upload-auth.curl"
    )
    assert result["candidates"][0]["mode"] == "0600"
    assert result["candidates"][0]["bearerMaterialDetected"] is True
    assert "sha256" not in result["candidates"][0]
    assert candidate.read_bytes() == CONFIG_BYTES
    assert ignored.read_bytes() == CONFIG_BYTES
    assert SECRET not in external_receipt.read_text(encoding="utf-8")
    assert stat.S_IMODE(external_receipt.stat().st_mode) == 0o600
    assert stat.S_IMODE(external_receipt.parent.stat().st_mode) == 0o700


def test_quarantine_requires_exact_confirmation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-130312/upload-auth.curl",
    )

    assert (
        module.run(
            [
                "--release-root",
                str(tmp_path),
                "--quarantine",
                "--confirm",
                "wrong",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert module.QUARANTINE_CONFIRMATION in captured.err
    assert SECRET not in captured.err
    assert candidate.exists()


def test_quarantine_moves_findings_and_writes_owner_only_redacted_receipts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = write_candidate(
        tmp_path,
        "run-20260724-130312/a/upload-auth.curl",
    )
    second = write_candidate(
        tmp_path,
        "run-20260724-193632/b/upload-auth.curl",
    )
    assert run_quarantine(tmp_path) == 0

    captured = capsys.readouterr()
    assert SECRET not in captured.out
    result = json.loads(captured.out)
    assert result["status"] == "quarantined"
    assert result["quarantinedCount"] == 2
    assert result["rotationRequiredBeforeDeletion"] is True
    assert not first.exists()
    assert not second.exists()
    for candidate in result["candidates"]:
        quarantined = tmp_path / candidate["quarantineRelativePath"]
        assert quarantined.read_bytes() == CONFIG_BYTES
        assert stat.S_IMODE(quarantined.stat().st_mode) == 0o600
    internal_receipt = tmp_path / result["receiptRelativePath"]
    receipt_text = internal_receipt.read_text(encoding="utf-8")
    assert SECRET not in receipt_text
    assert hashlib.sha256(CONFIG_BYTES).hexdigest() not in receipt_text
    assert stat.S_IMODE(internal_receipt.stat().st_mode) == 0o600
    assert stat.S_IMODE(internal_receipt.parent.stat().st_mode) == 0o700
    journal = tmp_path / result["journalRelativePath"]
    journal_text = journal.read_text(encoding="utf-8")
    assert SECRET not in journal_text
    assert hashlib.sha256(CONFIG_BYTES).hexdigest() not in journal_text
    assert '"event":"started"' in journal_text
    assert journal_text.count('"event":"move-planned"') == 2
    assert journal_text.count('"event":"moved"') == 2
    assert '"event":"completed"' in journal_text
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600


def test_symlink_candidate_is_rejected_without_following_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "outside-secret"
    target.write_bytes(CONFIG_BYTES)
    candidate = (
        tmp_path / "run-20260724-193632" / "nested" / "upload-auth.curl"
    )
    candidate.parent.mkdir(parents=True)
    candidate.symlink_to(target)

    assert module.run(["--release-root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "regular non-symlink" in captured.err
    assert SECRET not in captured.err
    assert target.read_bytes() == CONFIG_BYTES


def test_hard_link_candidate_is_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-193632/upload-auth.curl",
    )
    os.link(candidate, tmp_path / "other-link")

    assert module.run(["--release-root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "multiple hard links" in captured.err
    assert SECRET not in captured.err
    assert candidate.exists()


def test_tracked_candidate_is_reported_without_modifying_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = tmp_path / "run-20260724-193632"
    subprocess.run(("git", "init", "-q", str(run_root)), check=True)
    candidate = write_candidate(run_root, "state/upload-auth.curl")
    subprocess.run(
        ("git", "-C", str(run_root), "add", "state/upload-auth.curl"),
        check=True,
    )
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "misleading-git-dir"))

    result = module.audit_release_root(tmp_path)

    assert result["gitTrackedCount"] == 1
    assert result["candidates"][0]["gitTracked"] is True
    assert result["candidates"][0]["gitRootRelativePath"] == run_root.name
    assert candidate.exists()


def test_indeterminate_git_state_cannot_be_reported_as_untracked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-193632/upload-auth.curl",
    )

    def failed_git(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args=("git",),
            returncode=128,
            stdout="",
            stderr="fatal: corrupt repository state",
        )

    monkeypatch.setattr(module.subprocess, "run", failed_git)
    with pytest.raises(module.AuditError, match="Git repository"):
        module.audit_release_root(tmp_path)
    assert candidate.exists()


def test_corrupt_git_marker_cannot_be_reported_as_untracked(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run-20260724-193632"
    (run_root / ".git").mkdir(parents=True)
    candidate = write_candidate(run_root, "state/upload-auth.curl")

    with pytest.raises(module.AuditError, match="Git repository"):
        module.audit_release_root(tmp_path)
    assert candidate.exists()


def test_relative_or_symlink_release_root_is_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert module.run(["--release-root", "relative"]) == 2
    assert "absolute path" in capsys.readouterr().err

    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    assert module.run(["--release-root", str(linked_root)]) == 2
    assert "symbolic link" in capsys.readouterr().err


def test_oversized_candidate_is_rejected_without_reading_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = (
        tmp_path / "run-20260724-193632" / "upload-auth.curl"
    )
    candidate.parent.mkdir(parents=True)
    with candidate.open("wb") as stream:
        stream.truncate(module.MAX_CREDENTIAL_FILE_BYTES + 1)

    assert module.run(["--release-root", str(tmp_path)]) == 2
    assert "safe audit size limit" in capsys.readouterr().err


def test_quarantine_target_set_must_match_current_audit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-193632/upload-auth.curl",
    )
    assert (
        run_quarantine(
            tmp_path,
            targets=["run-older/upload-auth.curl"],
        )
        == 2
    )
    assert "exactly match" in capsys.readouterr().err
    assert candidate.exists()
    assert not (tmp_path / module.QUARANTINE_DIRECTORY_NAME).exists()


def test_quarantine_refuses_git_tracked_candidate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "run-20260724-193632"
    subprocess.run(("git", "init", "-q", str(run_root)), check=True)
    candidate = write_candidate(run_root, "state/upload-auth.curl")
    subprocess.run(
        ("git", "-C", str(run_root), "add", "state/upload-auth.curl"),
        check=True,
    )

    assert run_quarantine(tmp_path) == 2
    captured = capsys.readouterr()
    assert "Git-tracked" in captured.err
    assert SECRET not in captured.err
    assert candidate.exists()
    assert not (tmp_path / module.QUARANTINE_DIRECTORY_NAME).exists()


def test_quarantine_refuses_non_bearer_same_named_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = (
        tmp_path / "run-20260724-193632" / "upload-auth.curl"
    )
    candidate.parent.mkdir(parents=True)
    candidate.write_text("silent\nshow-error\n", encoding="utf-8")
    candidate.chmod(0o600)

    assert run_quarantine(tmp_path) == 2
    assert "non-bearer" in capsys.readouterr().err
    assert candidate.exists()
    assert not (tmp_path / module.QUARANTINE_DIRECTORY_NAME).exists()


def test_existing_receipt_and_parent_are_never_overwritten_or_chmodded(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared_parent = tmp_path / "shared"
    shared_parent.mkdir(mode=0o755)
    shared_parent.chmod(0o755)
    receipt = shared_parent / "audit.json"
    receipt.write_text("keep-me\n", encoding="utf-8")
    receipt.chmod(0o600)

    assert (
        module.run(
            [
                "--release-root",
                str(tmp_path),
                "--receipt",
                str(receipt),
            ]
        )
        == 2
    )
    assert "owner-only" in capsys.readouterr().err
    assert receipt.read_text(encoding="utf-8") == "keep-me\n"
    assert stat.S_IMODE(shared_parent.stat().st_mode) == 0o755

    shared_parent.chmod(0o700)
    assert (
        module.run(
            [
                "--release-root",
                str(tmp_path),
                "--receipt",
                str(receipt),
            ]
        )
        == 2
    )
    assert "already exists" in capsys.readouterr().err
    assert receipt.read_text(encoding="utf-8") == "keep-me\n"


def test_forged_parent_traversal_audit_row_is_rejected(
    tmp_path: Path,
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-193632/upload-auth.curl",
    )
    audit = module.audit_release_root(tmp_path)
    audit["candidates"][0]["relativePath"] = (
        "run-20260724-193632/../../victim/upload-auth.curl"
    )

    with pytest.raises(module.AuditError, match="outside"):
        module.quarantine_candidates(
            tmp_path,
            audit,
            [
                "run-20260724-193632/../../victim/upload-auth.curl",
            ],
        )
    assert candidate.exists()
    assert not (tmp_path / module.QUARANTINE_DIRECTORY_NAME).exists()


def test_walk_error_cannot_be_reported_as_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = tmp_path / "run-20260724-193632"
    run_root.mkdir()

    def failed_walk(
        path: Path,
        *,
        topdown: bool,
        onerror: object,
        followlinks: bool,
    ) -> list[object]:
        del path, topdown, followlinks
        assert callable(onerror)
        onerror(
            PermissionError(
                errno.EACCES,
                "permission denied",
                str(run_root),
            )
        )
        return []

    monkeypatch.setattr(module.os, "walk", failed_walk)
    with pytest.raises(module.AuditError, match="unable to traverse"):
        module.audit_release_root(tmp_path)


def test_source_acl_is_refused_before_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-193632/upload-auth.curl",
    )

    monkeypatch.setattr(
        module,
        "_darwin_fd_has_extended_acl",
        lambda descriptor, display_path: display_path.endswith(
            module.TARGET_FILE_NAME
        ),
    )

    assert run_quarantine(tmp_path) == 2
    assert "extended ACL" in capsys.readouterr().err
    assert candidate.exists()
    assert not (tmp_path / module.QUARANTINE_DIRECTORY_NAME).exists()


def test_source_swap_during_rename_is_detected_and_journaled(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-193632/upload-auth.curl",
    )
    original_rename = os.rename
    original = candidate.with_name("original-upload-auth.curl")
    substitute_bytes = CONFIG_BYTES.replace(
        SECRET.encode(),
        b"substitute-ticket",
    )

    def swapping_rename(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        original_rename(candidate, original)
        candidate.write_bytes(substitute_bytes)
        candidate.chmod(0o600)
        original_rename(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(module.os, "rename", swapping_rename)
    monkeypatch.setattr(
        module,
        "_require_descriptor_relative_filesystem_support",
        lambda: None,
    )
    assert run_quarantine(tmp_path) == 2
    captured = capsys.readouterr()
    assert SECRET not in captured.err
    assert candidate.read_bytes() == substitute_bytes
    assert original.read_bytes() == CONFIG_BYTES
    quarantined_files = list(
        (tmp_path / module.QUARANTINE_DIRECTORY_NAME).rglob(
            module.TARGET_FILE_NAME
        )
    )
    assert quarantined_files == []
    journals = list(
        (tmp_path / module.QUARANTINE_DIRECTORY_NAME).rglob(
            module.JOURNAL_FILE_NAME
        )
    )
    assert len(journals) == 1
    journal_text = journals[0].read_text(encoding="utf-8")
    assert '"event":"failed"' in journal_text
    assert "replacement restored to source" in journal_text


def test_rollback_reports_indeterminate_source_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    destination = destination_root / module.TARGET_FILE_NAME
    destination.write_bytes(CONFIG_BYTES)
    source_descriptor = os.open(source_root, os.O_RDONLY | os.O_DIRECTORY)
    destination_descriptor = os.open(
        destination_root,
        os.O_RDONLY | os.O_DIRECTORY,
    )
    destination_stat = destination.stat()
    original_stat = os.stat

    def fail_source_stat(
        path: str,
        *,
        dir_fd: int,
        follow_symlinks: bool,
    ) -> os.stat_result:
        if dir_fd == source_descriptor:
            raise OSError(errno.EIO, "simulated stat failure")
        return original_stat(
            path,
            dir_fd=dir_fd,
            follow_symlinks=follow_symlinks,
        )

    try:
        monkeypatch.setattr(module.os, "stat", fail_source_stat)
        disposition = module._restore_unexpected_rename(
            source_descriptor,
            destination_descriptor,
            module.TARGET_FILE_NAME,
            destination_stat,
        )
    finally:
        monkeypatch.setattr(module.os, "stat", original_stat)
        os.close(source_descriptor)
        os.close(destination_descriptor)

    assert "may exist at source" in disposition
    assert (source_root / module.TARGET_FILE_NAME).exists()
    assert destination.exists()


def test_partial_quarantine_has_private_recovery_journal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = write_candidate(
        tmp_path,
        "run-20260724-130312/upload-auth.curl",
    )
    second = write_candidate(
        tmp_path,
        "run-20260724-193632/upload-auth.curl",
    )
    original_move = module._move_preflighted_candidate
    move_count = 0

    def fail_second_move(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal move_count
        move_count += 1
        if move_count == 2:
            raise OSError(errno.EIO, "simulated move failure")
        return original_move(*args, **kwargs)

    monkeypatch.setattr(
        module,
        "_move_preflighted_candidate",
        fail_second_move,
    )
    assert run_quarantine(tmp_path) == 2
    captured = capsys.readouterr()
    assert "private journal" in captured.err
    assert SECRET not in captured.err
    assert not first.exists()
    assert second.exists()
    journals = list(
        (tmp_path / module.QUARANTINE_DIRECTORY_NAME).rglob(
            module.JOURNAL_FILE_NAME
        )
    )
    assert len(journals) == 1
    journal_text = journals[0].read_text(encoding="utf-8")
    assert '"event":"moved"' in journal_text
    assert '"event":"failed"' in journal_text
    assert stat.S_IMODE(journals[0].stat().st_mode) == 0o600
    assert SECRET not in journal_text


def test_quarantine_rejects_external_receipt_before_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = write_candidate(
        tmp_path,
        "run-20260724-193632/upload-auth.curl",
    )
    external_receipt = tmp_path / "receipts" / "audit.json"

    assert (
        run_quarantine(tmp_path, "--receipt", str(external_receipt)) == 2
    )
    captured = capsys.readouterr()
    assert "audit-only" in captured.err
    assert SECRET not in captured.err
    assert candidate.exists()
    assert not external_receipt.exists()
    assert not (tmp_path / module.QUARANTINE_DIRECTORY_NAME).exists()


def test_directory_fsync_tolerates_only_portable_unsupported_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(
            module.os,
            "fsync",
            lambda ignored: (_ for _ in ()).throw(
                OSError(errno.EINVAL, "unsupported")
            ),
        )
        assert module._fsync_directory_descriptor(descriptor) is False

        monkeypatch.setattr(
            module.os,
            "fsync",
            lambda ignored: (_ for _ in ()).throw(
                OSError(errno.EIO, "I/O failure")
            ),
        )
        with pytest.raises(OSError, match="I/O failure"):
            module._fsync_directory_descriptor(descriptor)
    finally:
        os.close(descriptor)
