from __future__ import annotations

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

    assert module.run(["--release-root", str(tmp_path)]) == 0
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
    external_receipt = tmp_path / "receipts" / "audit.json"

    assert (
        module.run(
            [
                "--release-root",
                str(tmp_path),
                "--quarantine",
                "--confirm",
                module.QUARANTINE_CONFIRMATION,
                "--receipt",
                str(external_receipt),
            ]
        )
        == 0
    )

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
    for receipt in (internal_receipt, external_receipt):
        receipt_text = receipt.read_text(encoding="utf-8")
        assert SECRET not in receipt_text
        assert hashlib.sha256(CONFIG_BYTES).hexdigest() not in receipt_text
        assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
        assert stat.S_IMODE(receipt.parent.stat().st_mode) == 0o700


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
) -> None:
    run_root = tmp_path / "run-20260724-193632"
    subprocess.run(("git", "init", "-q", str(run_root)), check=True)
    candidate = write_candidate(run_root, "state/upload-auth.curl")
    subprocess.run(
        ("git", "-C", str(run_root), "add", "state/upload-auth.curl"),
        check=True,
    )

    result = module.audit_release_root(tmp_path)

    assert result["gitTrackedCount"] == 1
    assert result["candidates"][0]["gitTracked"] is True
    assert result["candidates"][0]["gitRootRelativePath"] == run_root.name
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
