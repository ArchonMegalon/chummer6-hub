from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "recover_public_edge_mutation_lock.py"
TOKEN = "a" * 64


def load_module():
    spec = importlib.util.spec_from_file_location(
        "recover_public_edge_mutation_lock", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path: Path):
    lock = tmp_path / "state" / "public-edge-mutation.lock"
    lock.parent.mkdir(mode=0o700)
    lock.mkdir(mode=0o700)
    token = lock / "owner-token"
    token.write_text(TOKEN + "\n", encoding="ascii")
    token.chmod(0o600)
    old_ns = 1_700_000_000_000_000_000
    os.utime(lock, ns=(old_ns, old_ns))
    receipts = tmp_path / "receipts"
    receipts.mkdir(mode=0o700)
    digest = hashlib.sha256(TOKEN.encode("ascii")).hexdigest()
    authorization = receipts / f"deploy-{digest}.owner-token"
    authorization.write_text(TOKEN + "\n", encoding="ascii")
    authorization.chmod(0o600)
    output = receipts / "recovery.json"
    metadata = lock.lstat()
    return lock, authorization, receipts, output, metadata, old_ns


def recover(module, tmp_path: Path, **overrides):
    lock, authorization, receipts, output, metadata, old_ns = fixture(tmp_path)
    arguments = {
        "lock_dir": lock,
        "receipt_root": receipts,
        "output": output,
        "owner_token_file": authorization,
        "expected_device": metadata.st_dev,
        "expected_inode": metadata.st_ino,
        "expected_mtime_ns": metadata.st_mtime_ns,
        "minimum_age_seconds": 900,
        "reason": "Operator verified the interrupted deployment process is gone.",
        "confirmation": module.CONFIRMATION,
        "operator_attestation": module.OPERATOR_ATTESTATION,
        "now_ns": old_ns + 1_000 * 1_000_000_000,
    }
    arguments.update(overrides)
    return module.recover_stale_lock(**arguments), lock, output


def test_authenticated_manual_recovery_writes_durable_receipt_before_removal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_module()
    writes: list[tuple[str, bool]] = []
    original_write = module._atomic_write

    def tracked_write(path: Path, payload: dict[str, object]) -> None:
        lock = tmp_path / "state" / "public-edge-mutation.lock"
        writes.append((str(payload["status"]), lock.exists()))
        original_write(path, payload)

    monkeypatch.setattr(module, "_atomic_write", tracked_write)
    receipt, lock, output = recover(module, tmp_path)

    assert writes == [("in_progress", True), ("pass", False)]
    assert not lock.exists()
    assert not list(output.parent.glob("*.owner-token"))
    assert receipt["status"] == "pass"
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["automaticRecovery"] is False
    assert persisted["ownerTokenSha256"] != TOKEN
    assert "ownerToken" not in persisted
    assert output.stat().st_mode & 0o777 == 0o600


def test_recovery_rejects_wrong_external_authorization_token(tmp_path: Path) -> None:
    module = load_module()
    lock, authorization, receipts, output, metadata, old_ns = fixture(tmp_path)
    authorization.write_text("b" * 64 + "\n", encoding="ascii")

    with pytest.raises(ValueError, match="does not bind"):
        module.recover_stale_lock(
            lock_dir=lock,
            receipt_root=receipts,
            output=output,
            owner_token_file=authorization,
            expected_device=metadata.st_dev,
            expected_inode=metadata.st_ino,
            expected_mtime_ns=metadata.st_mtime_ns,
            minimum_age_seconds=900,
            reason="Manual recovery after process inspection.",
            confirmation=module.CONFIRMATION,
            operator_attestation=module.OPERATOR_ATTESTATION,
            now_ns=old_ns + 1_000 * 1_000_000_000,
        )
    assert lock.exists()
    assert not output.exists()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"confirmation": "yes"}, "confirmation"),
        ({"operator_attestation": "yes"}, "attestation"),
        ({"minimum_age_seconds": 299}, "at least"),
        ({"expected_inode": 1}, "identity"),
        ({"now_ns": 1_700_000_100_000_000_000}, "not old enough"),
    ],
)
def test_recovery_fails_closed_without_every_manual_authority(
    tmp_path: Path, override: dict[str, object], message: str
) -> None:
    module = load_module()
    with pytest.raises(ValueError, match=message):
        recover(module, tmp_path, **override)


def test_recovery_rejects_unexpected_lock_entries(tmp_path: Path) -> None:
    module = load_module()
    lock, authorization, receipts, output, metadata, old_ns = fixture(tmp_path)
    (lock / "unknown-owner-state").write_text("unsafe\n", encoding="utf-8")
    os.utime(lock, ns=(old_ns, old_ns))
    metadata = lock.lstat()

    with pytest.raises(ValueError, match="unexpected entries"):
        module.recover_stale_lock(
            lock_dir=lock,
            receipt_root=receipts,
            output=output,
            owner_token_file=authorization,
            expected_device=metadata.st_dev,
            expected_inode=metadata.st_ino,
            expected_mtime_ns=metadata.st_mtime_ns,
            minimum_age_seconds=900,
            reason="Manual recovery after process inspection.",
            confirmation=module.CONFIRMATION,
            operator_attestation=module.OPERATOR_ATTESTATION,
            now_ns=old_ns + 1_000 * 1_000_000_000,
        )
    assert lock.exists()
    assert not output.exists()


def orphan_fixture(
    tmp_path: Path, *, kind: str | None, include_internal_token: bool = True
):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    lock = state / "public-edge-mutation.lock"
    receipts = state / "public-edge-lock-recovery-receipts"
    receipts.mkdir(mode=0o700)
    digest = hashlib.sha256(TOKEN.encode("ascii")).hexdigest()
    authorization = receipts / f"deploy-{digest}.owner-token"
    authorization.write_text(TOKEN + "\n", encoding="ascii")
    authorization.chmod(0o600)
    artifact = None
    if kind is not None:
        artifact = state / f".{lock.name}.{kind}.{digest}"
        artifact.mkdir(mode=0o700)
        if include_internal_token:
            internal = artifact / "owner-token"
            internal.write_text(TOKEN + "\n", encoding="ascii")
            internal.chmod(0o600)
    old_ns = 1_700_000_000_000_000_000
    os.utime(authorization, ns=(old_ns, old_ns))
    if artifact is not None:
        os.utime(artifact, ns=(old_ns, old_ns))
    output = receipts / "orphan-recovery.json"
    return lock, receipts, authorization, artifact, output, old_ns


@pytest.mark.parametrize(
    ("kind", "include_internal_token"),
    [("staging", True), ("retired", False)],
)
def test_orphan_cleanup_removes_digest_bound_partial_directory_and_authorization(
    tmp_path: Path, kind: str, include_internal_token: bool
) -> None:
    module = load_module()
    lock, receipts, authorization, artifact, output, old_ns = orphan_fixture(
        tmp_path, kind=kind, include_internal_token=include_internal_token
    )
    assert artifact is not None
    authorization_metadata = authorization.lstat()
    artifact_metadata = artifact.lstat()

    receipt = module.cleanup_orphaned_artifact(
        lock_path=lock,
        receipt_root=receipts,
        output=output,
        owner_token_file=authorization,
        artifact_path=artifact,
        expected_authorization_device=authorization_metadata.st_dev,
        expected_authorization_inode=authorization_metadata.st_ino,
        expected_authorization_mtime_ns=authorization_metadata.st_mtime_ns,
        expected_artifact_device=artifact_metadata.st_dev,
        expected_artifact_inode=artifact_metadata.st_ino,
        expected_artifact_mtime_ns=artifact_metadata.st_mtime_ns,
        minimum_age_seconds=900,
        reason="Interrupted lease cleanup was manually inspected.",
        confirmation=module.ORPHAN_CONFIRMATION,
        operator_attestation=module.OPERATOR_ATTESTATION,
        now_ns=old_ns + 1_000 * 1_000_000_000,
    )

    assert receipt["status"] == "pass"
    assert receipt["recoveryMode"] == "orphan_cleanup"
    assert receipt["artifactKind"] == kind
    assert not artifact.exists()
    assert not authorization.exists()
    assert TOKEN not in output.read_text(encoding="utf-8")


def test_authorization_only_orphan_cleanup_is_explicit_and_nonblocking(
    tmp_path: Path,
) -> None:
    module = load_module()
    lock, receipts, authorization, artifact, output, old_ns = orphan_fixture(
        tmp_path, kind=None
    )
    assert artifact is None
    authorization_metadata = authorization.lstat()

    receipt = module.cleanup_orphaned_artifact(
        lock_path=lock,
        receipt_root=receipts,
        output=output,
        owner_token_file=authorization,
        artifact_path=None,
        expected_authorization_device=authorization_metadata.st_dev,
        expected_authorization_inode=authorization_metadata.st_ino,
        expected_authorization_mtime_ns=authorization_metadata.st_mtime_ns,
        expected_artifact_device=None,
        expected_artifact_inode=None,
        expected_artifact_mtime_ns=None,
        minimum_age_seconds=900,
        reason="Unique authorization orphan was manually inspected.",
        confirmation=module.ORPHAN_CONFIRMATION,
        operator_attestation=module.OPERATOR_ATTESTATION,
        now_ns=old_ns + 1_000 * 1_000_000_000,
    )

    assert receipt["artifactKind"] == "authorization_only"
    assert not authorization.exists()


def test_authorization_only_cleanup_refuses_capability_still_bound_to_fixed_lock(
    tmp_path: Path,
) -> None:
    module = load_module()
    lock, receipts, authorization, _artifact, output, old_ns = orphan_fixture(
        tmp_path, kind=None
    )
    lock.mkdir(mode=0o700)
    internal = lock / "owner-token"
    internal.write_text(TOKEN + "\n", encoding="ascii")
    internal.chmod(0o600)
    authorization_metadata = authorization.lstat()

    with pytest.raises(ValueError, match="still owns"):
        module.cleanup_orphaned_artifact(
            lock_path=lock,
            receipt_root=receipts,
            output=output,
            owner_token_file=authorization,
            artifact_path=None,
            expected_authorization_device=authorization_metadata.st_dev,
            expected_authorization_inode=authorization_metadata.st_ino,
            expected_authorization_mtime_ns=authorization_metadata.st_mtime_ns,
            expected_artifact_device=None,
            expected_artifact_inode=None,
            expected_artifact_mtime_ns=None,
            minimum_age_seconds=900,
            reason="Unique authorization orphan was manually inspected.",
            confirmation=module.ORPHAN_CONFIRMATION,
            operator_attestation=module.OPERATOR_ATTESTATION,
            now_ns=old_ns + 1_000 * 1_000_000_000,
        )
    assert lock.exists()
    assert authorization.exists()
    assert not output.exists()


def test_empty_incomplete_fixed_lock_has_distinct_manual_recovery_authority(
    tmp_path: Path,
) -> None:
    module = load_module()
    lock, receipts, authorization, _artifact, output, old_ns = orphan_fixture(
        tmp_path, kind=None
    )
    lock.mkdir(mode=0o700)
    os.utime(lock, ns=(old_ns, old_ns))
    lock_metadata = lock.lstat()
    authorization_metadata = authorization.lstat()

    receipt = module.recover_incomplete_lock(
        lock_dir=lock,
        receipt_root=receipts,
        output=output,
        owner_token_file=authorization,
        expected_device=lock_metadata.st_dev,
        expected_inode=lock_metadata.st_ino,
        expected_mtime_ns=lock_metadata.st_mtime_ns,
        expected_authorization_device=authorization_metadata.st_dev,
        expected_authorization_inode=authorization_metadata.st_ino,
        expected_authorization_mtime_ns=authorization_metadata.st_mtime_ns,
        minimum_age_seconds=900,
        reason="Legacy tokenless fixed lock was manually inspected.",
        confirmation=module.INCOMPLETE_CONFIRMATION,
        operator_attestation=module.OPERATOR_ATTESTATION,
        now_ns=old_ns + 1_000 * 1_000_000_000,
    )

    assert receipt["status"] == "pass"
    assert receipt["recoveryMode"] == "incomplete_fixed_lock"
    assert not lock.exists()
    assert not authorization.exists()


def test_incomplete_fixed_lock_recovery_refuses_nonempty_lock(tmp_path: Path) -> None:
    module = load_module()
    lock, receipts, authorization, _artifact, output, old_ns = orphan_fixture(
        tmp_path, kind=None
    )
    lock.mkdir(mode=0o700)
    (lock / "unexpected").write_text("unsafe\n", encoding="utf-8")
    os.utime(lock, ns=(old_ns, old_ns))
    lock_metadata = lock.lstat()
    authorization_metadata = authorization.lstat()

    with pytest.raises(ValueError, match="only an empty"):
        module.recover_incomplete_lock(
            lock_dir=lock,
            receipt_root=receipts,
            output=output,
            owner_token_file=authorization,
            expected_device=lock_metadata.st_dev,
            expected_inode=lock_metadata.st_ino,
            expected_mtime_ns=lock_metadata.st_mtime_ns,
            expected_authorization_device=authorization_metadata.st_dev,
            expected_authorization_inode=authorization_metadata.st_ino,
            expected_authorization_mtime_ns=authorization_metadata.st_mtime_ns,
            minimum_age_seconds=900,
            reason="Legacy tokenless fixed lock was manually inspected.",
            confirmation=module.INCOMPLETE_CONFIRMATION,
            operator_attestation=module.OPERATOR_ATTESTATION,
            now_ns=old_ns + 1_000 * 1_000_000_000,
        )
    assert lock.exists()
    assert authorization.exists()
    assert not output.exists()
