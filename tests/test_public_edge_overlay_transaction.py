from __future__ import annotations

import hashlib
import importlib.util
import json
import signal
import subprocess
from contextlib import nullcontext
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "public_edge_overlay_transaction.py"
CANDIDATE_PROOF_BYTES = b"candidate-proof-authority\n"
PRIOR_PROOF_BYTES = b"prior-proof-authority\n"
CANDIDATE_PROOF_SHA256 = hashlib.sha256(CANDIDATE_PROOF_BYTES).hexdigest()
PRIOR_PROOF_SHA256 = hashlib.sha256(PRIOR_PROOF_BYTES).hexdigest()
CANDIDATE_PORTAL_NAME = "chummer-public-edge-candidate-test"
CANDIDATE_PORTAL_ID = "c" * 64
CANDIDATE_PORTAL_IMAGE = "sha256:" + "6" * 64
AUTHORITY_IDENTITY_SHA256 = "8" * 64
RUNTIME_ROLE_SHA256 = "9" * 64


def load_module():
    spec = importlib.util.spec_from_file_location(
        "public_edge_overlay_transaction_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def disable_host_locks(module, monkeypatch) -> None:
    monkeypatch.setattr(
        module.overlay,
        "public_edge_mutation_lock",
        lambda **_kwargs: nullcontext(None),
    )
    monkeypatch.setattr(
        module.overlay,
        "overlay_publish_lock",
        lambda *_args, **_kwargs: nullcontext(None),
    )


def runtime_prior_state() -> dict[str, object]:
    return {
        "candidatePortalContainerName": CANDIDATE_PORTAL_NAME,
        "expectedRuntimeProofBindSourceSha256": CANDIDATE_PROOF_SHA256,
        "publicProjectionManifestSha256": "5" * 64,
        "publicProjectionSnapshotId": "public-projection-" + "7" * 64,
        "publicProjectionSnapshotSha256": "7" * 64,
        "priorImageTagId": "sha256:" + "1" * 64,
        "priorToolImageTagId": "sha256:" + "2" * 64,
        "priorPortalContainerId": "a" * 64,
        "priorPortalContainerName": "chummer6-hub-chummer-portal-1",
        "priorPortalImageId": "sha256:" + "3" * 64,
        "priorPortalProofAuthorityMountSha256": PRIOR_PROOF_SHA256,
        "priorPortalProofPublicMountSha256": PRIOR_PROOF_SHA256,
        "priorPortalExisted": True,
        "priorPortalWasRunning": True,
        "priorTunnelContainerId": "b" * 64,
        "priorTunnelImageId": "sha256:" + "4" * 64,
        "priorTunnelExisted": True,
        "priorTunnelWasRunning": True,
    }


def deploy_proof_authority(tmp_path: Path) -> dict[str, Path]:
    proof_bind_source = tmp_path / "runtime-proof-source.json"
    candidate_snapshot = tmp_path / "candidate-proof-snapshot.json"
    prior_authority_snapshot = tmp_path / "prior-authority-proof-snapshot.json"
    prior_public_snapshot = tmp_path / "prior-public-proof-snapshot.json"
    proof_bind_source.write_bytes(CANDIDATE_PROOF_BYTES)
    candidate_snapshot.write_bytes(CANDIDATE_PROOF_BYTES)
    prior_authority_snapshot.write_bytes(PRIOR_PROOF_BYTES)
    prior_public_snapshot.write_bytes(PRIOR_PROOF_BYTES)
    return {
        "proof_bind_source": proof_bind_source,
        "candidate_proof_bind_source_snapshot": candidate_snapshot,
        "prior_portal_proof_authority_snapshot": prior_authority_snapshot,
        "prior_portal_proof_public_snapshot": prior_public_snapshot,
    }


def install_linking_authority_readiness_payload() -> dict[str, object]:
    return {
        "authorityIdentitySha256": AUTHORITY_IDENTITY_SHA256,
        "checkedAtUtc": "2026-07-23T12:34:56.1234567+00:00",
        "code": "runtime_role_least_privilege",
        "contractName": (
            "chummer.install_linking_postgres_runtime_authority_readiness.v1"
        ),
        "currentRoleMatches": True,
        "leastPrivilegeValid": True,
        "ready": True,
        "runtimeRoleSha256": RUNTIME_ROLE_SHA256,
        "status": "pass",
    }


def write_install_linking_authority_readiness(
    path: Path,
    *,
    payload: dict[str, object] | None = None,
) -> tuple[Path, str]:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    encoded = (
        json.dumps(
            payload or install_linking_authority_readiness_payload(),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(encoded)
    path.chmod(0o600)
    return path, hashlib.sha256(encoded).hexdigest()


class SimulatedHardCrash(BaseException):
    pass


def prepare_deploy_activation(
    module,
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, dict[str, int]]:
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    staging_root = tmp_path / "overlay-next" / "app"
    backup_root = tmp_path / "overlay-backups"
    journal = tmp_path / "deploy-journal.json"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    staging_root.mkdir(parents=True)
    backup_root.mkdir()
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    (staging_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    prior_identity = module.overlay.directory_identity(
        active_root,
        label="active root",
    )
    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=journal,
        shared_mutation_lock_token="9" * 64,
        runtime_prior_state=runtime_prior_state(),
        staging_root=staging_root,
        backup_root=backup_root,
        activation_receipt=tmp_path / "activation.json",
        **deploy_proof_authority(tmp_path),
    )
    return (
        source_root,
        active_root,
        staging_root,
        backup_root,
        journal,
        prior_identity,
    )


def write_activation_receipt(
    module,
    path: Path,
    *,
    active_root: Path,
    backup_root: Path,
    backup_path: Path,
) -> None:
    path.write_text(
        json.dumps(
            {
                "contractName": module.overlay.CONTRACT_NAME,
                "status": "pass",
                "activateRequested": True,
                "activationStatus": "activated",
                "activationAtomicCutover": True,
                "activeRoot": str(active_root),
                "backupRoot": str(backup_root),
                "backupPath": str(backup_path),
                "sharedMutationLock": {
                    "status": "held",
                    "inherited": True,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_restore_reinstalls_exact_prior_overlay_identity(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    staging_root = tmp_path / "overlay-next" / "app"
    backup_root = tmp_path / "overlay-backups"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    staging_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    (staging_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    prior_identity = module.overlay.directory_identity(active_root, label="active root")
    snapshot_path = tmp_path / "snapshot.json"
    activation_receipt = tmp_path / "activation.json"
    rollback_receipt = tmp_path / "rollback.json"

    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=snapshot_path,
        shared_mutation_lock_token="a" * 64,
    )
    activation = module.overlay.activate_overlay_tree(
        staging_root,
        active_root,
        backup_root=backup_root,
    )
    backup_path = Path(activation["backupPath"])
    write_activation_receipt(
        module,
        activation_receipt,
        active_root=active_root,
        backup_root=backup_root,
        backup_path=backup_path,
    )

    receipt = module.restore(
        source_root=source_root,
        active_root=active_root,
        backup_root=backup_root,
        snapshot_path=snapshot_path,
        activation_receipt=activation_receipt,
        output=rollback_receipt,
        shared_mutation_lock_token="a" * 64,
    )

    assert receipt["status"] == "pass"
    assert receipt["action"] == "exact_prior_tree_restored"
    assert receipt["exactPriorStateRestored"] is True
    assert (active_root / "payload.txt").read_text(encoding="utf-8") == "prior\n"
    assert module.overlay.directory_identity(active_root, label="active root") == prior_identity
    assert json.loads(rollback_receipt.read_text(encoding="utf-8"))["status"] == "pass"


def test_restore_accepts_already_restored_state_without_activation_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"

    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=snapshot_path,
        shared_mutation_lock_token="b" * 64,
    )
    receipt = module.restore(
        source_root=source_root,
        active_root=active_root,
        backup_root=tmp_path / "overlay-backups",
        snapshot_path=snapshot_path,
        activation_receipt=tmp_path / "missing-activation.json",
        output=tmp_path / "rollback.json",
        shared_mutation_lock_token="b" * 64,
    )

    assert receipt["action"] == "already_restored"
    assert receipt["exactPriorStateRestored"] is True


def test_restore_rejects_tampered_backup_without_replacing_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    staging_root = tmp_path / "overlay-next" / "app"
    backup_root = tmp_path / "overlay-backups"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    staging_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    (staging_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"
    activation_receipt = tmp_path / "activation.json"

    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=snapshot_path,
        shared_mutation_lock_token="c" * 64,
    )
    activation = module.overlay.activate_overlay_tree(
        staging_root,
        active_root,
        backup_root=backup_root,
    )
    backup_path = Path(activation["backupPath"])
    (backup_path / "payload.txt").write_text("tampered\n", encoding="utf-8")
    write_activation_receipt(
        module,
        activation_receipt,
        active_root=active_root,
        backup_root=backup_root,
        backup_path=backup_path,
    )

    with pytest.raises(RuntimeError, match="could not resolve one exact preserved prior overlay"):
        module.restore(
            source_root=source_root,
            active_root=active_root,
            backup_root=backup_root,
            snapshot_path=snapshot_path,
            activation_receipt=activation_receipt,
            output=tmp_path / "rollback.json",
            shared_mutation_lock_token="c" * 64,
        )

    assert (active_root / "payload.txt").read_text(encoding="utf-8") == "candidate\n"


def test_restore_after_exchange_does_not_require_activation_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    staging_root = tmp_path / "overlay-next" / "app"
    backup_root = tmp_path / "overlay-backups"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    staging_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    (staging_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"
    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=snapshot_path,
        shared_mutation_lock_token="f" * 64,
    )
    module.overlay.activate_overlay_tree(
        staging_root,
        active_root,
        backup_root=backup_root,
    )

    receipt = module.restore(
        source_root=source_root,
        active_root=active_root,
        backup_root=backup_root,
        snapshot_path=snapshot_path,
        activation_receipt=tmp_path / "publisher-died-before-receipt.json",
        output=tmp_path / "rollback.json",
        shared_mutation_lock_token="f" * 64,
    )

    assert receipt["action"] == "exact_prior_tree_restored"
    assert (active_root / "payload.txt").read_text(encoding="utf-8") == "prior\n"


def test_deploy_recovery_survives_hard_crash_after_atomic_exchange(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    (
        source_root,
        active_root,
        staging_root,
        backup_root,
        journal,
        prior_identity,
    ) = prepare_deploy_activation(module, tmp_path)
    original_move = module.overlay.atomic_move_overlay_root

    def crash_before_backup_move(source: Path, destination: Path) -> None:
        if source == staging_root:
            raise SimulatedHardCrash()
        original_move(source, destination)

    monkeypatch.setattr(
        module.overlay,
        "atomic_move_overlay_root",
        crash_before_backup_move,
    )
    with pytest.raises(SimulatedHardCrash):
        module.overlay.activate_overlay_tree(
            staging_root,
            active_root,
            backup_root=backup_root,
        )
    monkeypatch.setattr(module.overlay, "atomic_move_overlay_root", original_move)

    activation_journal = module.overlay.activation_transaction_journal_path(
        active_root
    )
    assert activation_journal.exists()
    assert (active_root / "payload.txt").read_text(encoding="utf-8") == "candidate\n"
    assert (staging_root / "payload.txt").read_text(encoding="utf-8") == "prior\n"

    receipt = module.restore(
        source_root=source_root,
        active_root=active_root,
        backup_root=backup_root,
        snapshot_path=journal,
        activation_receipt=tmp_path / "wrong-new-receipt.json",
        output=tmp_path / "rollback.json",
        shared_mutation_lock_token="9" * 64,
    )

    assert receipt["activationRecovery"] == "exact_prior_activation_state_restored"
    assert module.overlay.directory_identity(active_root, label="active root") == prior_identity
    assert (active_root / "payload.txt").read_text(encoding="utf-8") == "prior\n"
    assert not activation_journal.exists()


def test_deploy_recovery_survives_hard_crash_after_prior_tree_backup_move(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    (
        source_root,
        active_root,
        staging_root,
        backup_root,
        journal,
        prior_identity,
    ) = prepare_deploy_activation(module, tmp_path)
    activation_journal = module.overlay.activation_transaction_journal_path(
        active_root
    )
    original_unlink = Path.unlink

    def crash_before_activation_journal_retirement(
        path: Path,
        *args,
        **kwargs,
    ) -> None:
        if path == activation_journal:
            raise SimulatedHardCrash()
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", crash_before_activation_journal_retirement)
    with pytest.raises(SimulatedHardCrash):
        module.overlay.activate_overlay_tree(
            staging_root,
            active_root,
            backup_root=backup_root,
        )
    monkeypatch.setattr(Path, "unlink", original_unlink)

    assert activation_journal.exists()
    assert (active_root / "payload.txt").read_text(encoding="utf-8") == "candidate\n"
    assert not staging_root.exists()

    receipt = module.restore(
        source_root=source_root,
        active_root=active_root,
        backup_root=backup_root,
        snapshot_path=journal,
        activation_receipt=tmp_path / "wrong-new-receipt.json",
        output=tmp_path / "rollback.json",
        shared_mutation_lock_token="9" * 64,
    )

    assert receipt["activationRecovery"] == "exact_prior_activation_state_restored"
    assert module.overlay.directory_identity(active_root, label="active root") == prior_identity
    assert (active_root / "payload.txt").read_text(encoding="utf-8") == "prior\n"
    assert not activation_journal.exists()


def test_deploy_recovery_survives_hard_crash_while_restoring_prior_absence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    staging_root = tmp_path / "overlay-next" / "app"
    backup_root = tmp_path / "overlay-backups"
    journal = tmp_path / "deploy-journal.json"
    source_root.mkdir()
    staging_root.mkdir(parents=True)
    backup_root.mkdir()
    (staging_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=journal,
        shared_mutation_lock_token="8" * 64,
        runtime_prior_state=runtime_prior_state(),
        staging_root=staging_root,
        backup_root=backup_root,
        activation_receipt=tmp_path / "activation.json",
        **deploy_proof_authority(tmp_path),
    )
    activation_journal = module.overlay.activation_transaction_journal_path(
        active_root
    )
    original_unlink = Path.unlink

    def crash_before_activation_journal_retirement(
        path: Path,
        *args,
        **kwargs,
    ) -> None:
        if path == activation_journal:
            raise SimulatedHardCrash()
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", crash_before_activation_journal_retirement)
    with pytest.raises(SimulatedHardCrash):
        module.overlay.activate_overlay_tree(
            staging_root,
            active_root,
            backup_root=backup_root,
        )
    monkeypatch.setattr(Path, "unlink", original_unlink)
    assert active_root.exists()
    assert activation_journal.exists()

    receipt = module.restore(
        source_root=source_root,
        active_root=active_root,
        backup_root=backup_root,
        snapshot_path=journal,
        activation_receipt=tmp_path / "wrong-new-receipt.json",
        output=tmp_path / "rollback.json",
        shared_mutation_lock_token="8" * 64,
    )

    assert receipt["activationRecovery"] == "exact_prior_activation_state_restored"
    assert receipt["exactPriorStateRestored"] is True
    assert not active_root.exists()
    assert not activation_journal.exists()


def test_restore_reestablishes_prior_active_root_absence(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    source_root.mkdir()
    snapshot_path = tmp_path / "snapshot.json"

    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=snapshot_path,
        shared_mutation_lock_token="d" * 64,
    )
    active_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    receipt = module.restore(
        source_root=source_root,
        active_root=active_root,
        backup_root=tmp_path / "overlay-backups",
        snapshot_path=snapshot_path,
        activation_receipt=tmp_path / "unused.json",
        output=tmp_path / "rollback.json",
        shared_mutation_lock_token="d" * 64,
    )

    assert receipt["action"] == "prior_absence_restored"
    assert not active_root.exists()


def test_restore_rejects_uncertain_activation_journal_even_when_bytes_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"
    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=snapshot_path,
        shared_mutation_lock_token="e" * 64,
    )
    journal_path = module.overlay.activation_transaction_journal_path(active_root)
    journal_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        module.overlay.OverlayActivationError,
        match="incomplete_activation_transaction_requires_recovery",
    ):
        module.restore(
            source_root=source_root,
            active_root=active_root,
            backup_root=tmp_path / "overlay-backups",
            snapshot_path=snapshot_path,
            activation_receipt=tmp_path / "unused.json",
            output=tmp_path / "rollback.json",
            shared_mutation_lock_token="e" * 64,
        )


def test_snapshot_authenticates_real_inherited_shared_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    lock_path = tmp_path / "state" / "public-edge-mutation.lock"
    lock_path.mkdir(parents=True, mode=0o700)
    lock_path.chmod(0o700)
    token = "1" * 64
    token_path = lock_path / module.overlay.PUBLIC_EDGE_MUTATION_LOCK_TOKEN_FILE
    token_path.write_text(token + "\n", encoding="ascii")
    token_path.chmod(0o600)
    monkeypatch.setattr(module.overlay, "PUBLIC_EDGE_MUTATION_LOCK", lock_path)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")

    payload = module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=tmp_path / "snapshot.json",
        shared_mutation_lock_token=token,
    )

    assert payload["status"] == "pass"
    assert payload["phase"] == "prepared"
    assert token_path.read_text(encoding="ascii") == token + "\n"


def test_transaction_phase_journal_is_monotonic(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "overlay" / "app"
    journal = tmp_path / "snapshot.json"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=journal,
        shared_mutation_lock_token="2" * 64,
    )

    with pytest.raises(RuntimeError, match="cannot skip forward"):
        module.mark_phase(
            source_root=source_root,
            active_root=active_root,
            journal_path=journal,
            phase="overlay_activated",
            shared_mutation_lock_token="2" * 64,
        )

    for phase in ("image_build_started", "image_built", "tunnel_drained"):
        payload = module.mark_phase(
            source_root=source_root,
            active_root=active_root,
            journal_path=journal,
            phase=phase,
            shared_mutation_lock_token="2" * 64,
        )
    assert payload["phase"] == "tunnel_drained"
    with pytest.raises(RuntimeError, match="cannot move backward"):
        module.mark_phase(
            source_root=source_root,
            active_root=active_root,
            journal_path=journal,
            phase="image_built",
            shared_mutation_lock_token="2" * 64,
        )
    assert json.loads(journal.read_text(encoding="utf-8"))["phase"] == "tunnel_drained"


def test_deploy_snapshot_rejects_inconsistent_runtime_prior_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "active" / "app"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    state = runtime_prior_state()
    state["priorPortalExisted"] = False

    with pytest.raises(RuntimeError, match="absent prior portal"):
        module.snapshot(
            source_root=source_root,
            active_root=active_root,
            output=tmp_path / "journal.json",
            shared_mutation_lock_token="3" * 64,
            runtime_prior_state=state,
        )


def test_deploy_snapshot_rejects_unsealed_runtime_proof_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "active" / "app"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    state = runtime_prior_state()
    state["expectedRuntimeProofBindSourceSha256"] = "A" * 64

    with pytest.raises(RuntimeError, match="proof bind-source SHA-256"):
        module.snapshot(
            source_root=source_root,
            active_root=active_root,
            output=tmp_path / "journal.json",
            shared_mutation_lock_token="3" * 64,
            runtime_prior_state=state,
        )


def test_install_linking_authority_readiness_is_pinned_from_one_stable_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path / "install-linking-authority-readiness-test.json"
        )
    )
    original_read = module.overlay.read_stable_regular_bytes
    read_paths: list[Path] = []

    def record_read(path: Path, **kwargs):
        read_paths.append(path)
        return original_read(path, **kwargs)

    monkeypatch.setattr(
        module.overlay,
        "read_stable_regular_bytes",
        record_read,
    )

    normalized, actual_sha256, payload = (
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )
    )

    assert normalized == readiness_path
    assert actual_sha256 == readiness_sha256
    assert payload == install_linking_authority_readiness_payload()
    assert read_paths == [readiness_path]


def test_install_linking_authority_readiness_rejects_malformed_or_noncanonical_json(
    tmp_path: Path,
) -> None:
    module = load_module()
    malformed = tmp_path / "malformed.json"
    malformed.write_bytes(b'{"status":"pass",}\n')
    malformed.chmod(0o600)
    malformed_sha256 = hashlib.sha256(malformed.read_bytes()).hexdigest()

    with pytest.raises(RuntimeError, match="strict JSON"):
        module.validate_install_linking_authority_readiness(
            malformed,
            expected_sha256=malformed_sha256,
            evidence_root=tmp_path,
        )

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical_bytes = json.dumps(
        install_linking_authority_readiness_payload(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    noncanonical.write_bytes(noncanonical_bytes)
    noncanonical.chmod(0o600)
    with pytest.raises(RuntimeError, match="not canonical JSON"):
        module.validate_install_linking_authority_readiness(
            noncanonical,
            expected_sha256=hashlib.sha256(noncanonical_bytes).hexdigest(),
            evidence_root=tmp_path,
        )


def test_install_linking_authority_readiness_rejects_digest_mismatch(
    tmp_path: Path,
) -> None:
    module = load_module()
    readiness_path, _readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path / "install-linking-authority-readiness-test.json"
        )
    )

    with pytest.raises(RuntimeError, match="does not match its pin"):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256="f" * 64,
            evidence_root=tmp_path,
        )


def test_install_linking_authority_readiness_rejects_path_identity_change_after_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path / "install-linking-authority-readiness-test.json"
        )
    )
    original_read = module.overlay.read_stable_regular_bytes

    def replace_after_read(path: Path, **kwargs):
        payload, metadata = original_read(path, **kwargs)
        replacement = tmp_path / "replacement-readiness.json"
        replacement.write_bytes(payload)
        replacement.chmod(0o600)
        replacement.replace(path)
        return payload, metadata

    monkeypatch.setattr(
        module.overlay,
        "read_stable_regular_bytes",
        replace_after_read,
    )

    with pytest.raises(RuntimeError, match="changed identity"):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )


def test_install_linking_authority_readiness_rejects_path_outside_evidence_root(
    tmp_path: Path,
) -> None:
    module = load_module()
    tmp_path.chmod(0o700)
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path
            / "other-evidence"
            / "install-linking-authority-readiness-test.json"
        )
    )

    with pytest.raises(RuntimeError, match="remain in the active runtime evidence root"):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )


def test_install_linking_authority_readiness_rejects_noncanonical_alias_path(
    tmp_path: Path,
) -> None:
    module = load_module()
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path / "install-linking-authority-readiness-test.json"
        )
    )
    aliased_path = tmp_path / "unused-component" / ".." / readiness_path.name

    with pytest.raises(RuntimeError, match="exact, canonical, and absolute"):
        module.validate_install_linking_authority_readiness(
            aliased_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )


def test_install_linking_authority_readiness_rejects_symlink(
    tmp_path: Path,
) -> None:
    module = load_module()
    target, readiness_sha256 = write_install_linking_authority_readiness(
        tmp_path / "readiness-target.json"
    )
    readiness_path = tmp_path / "install-linking-authority-readiness-test.json"
    readiness_path.symlink_to(target)

    with pytest.raises(RuntimeError, match="symlink"):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )


def test_install_linking_authority_readiness_rejects_open_schema(
    tmp_path: Path,
) -> None:
    module = load_module()
    payload = install_linking_authority_readiness_payload()
    payload["diagnostic"] = "benign-extra-field"
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path / "install-linking-authority-readiness-test.json",
            payload=payload,
        )
    )

    with pytest.raises(RuntimeError, match="contract is invalid"):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )


@pytest.mark.parametrize(
    "secret_value",
    (
        "password=do-not-publish",
        "postgresql://runtime-user:do-not-publish@database/chummer",
        "https://runtime-user:do-not-publish@example.test/readiness",
        "https://example.test/readiness?access_token=do-not-publish",
        "-----BEGIN PRIVATE KEY-----\ndo-not-publish",
        "Bearer abcdefghijklmnop",
        "github_pat_" + "a" * 24,
        "eyJabcdefghijk.abcdefghijk.abcdefghijk",
    ),
)
def test_install_linking_authority_readiness_rejects_secret_value(
    tmp_path: Path,
    secret_value: str,
) -> None:
    module = load_module()
    payload = install_linking_authority_readiness_payload()
    payload["checkedAtUtc"] = secret_value
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path / "install-linking-authority-readiness-test.json",
            payload=payload,
        )
    )

    with pytest.raises(RuntimeError, match="apparent secret material"):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )


def test_install_linking_authority_readiness_rejects_public_or_multi_link_file(
    tmp_path: Path,
) -> None:
    module = load_module()
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path / "install-linking-authority-readiness-test.json"
        )
    )
    readiness_path.chmod(0o640)

    with pytest.raises(RuntimeError, match="mode-0600 single-link"):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )

    readiness_path.chmod(0o600)
    (tmp_path / "readiness-hardlink.json").hardlink_to(readiness_path)
    with pytest.raises(RuntimeError, match="mode-0600 single-link"):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("currentRoleMatches", False, "contract is invalid"),
        ("leastPrivilegeValid", 1, "contract is invalid"),
        ("runtimeRoleSha256", "A" * 64, "contract is invalid"),
        (
            "authorityIdentitySha256",
            int("8" * 64),
            "contract is invalid",
        ),
        (
            "checkedAtUtc",
            "2026-07-23T12:34:56+01:00",
            "timestamp is invalid",
        ),
    ),
)
def test_install_linking_authority_readiness_rejects_invalid_success_semantics(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    module = load_module()
    payload = install_linking_authority_readiness_payload()
    payload[field] = value
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            tmp_path / "install-linking-authority-readiness-test.json",
            payload=payload,
        )
    )

    with pytest.raises(RuntimeError, match=message):
        module.validate_install_linking_authority_readiness(
            readiness_path,
            expected_sha256=readiness_sha256,
            evidence_root=tmp_path,
        )


def test_complete_retires_only_fully_advanced_deploy_journal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_host_locks(module, monkeypatch)
    source_root = tmp_path / "source"
    active_root = tmp_path / "active" / "app"
    journal = tmp_path / "journal.json"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    staging_root = tmp_path / "staging" / "app"
    staging_root.mkdir(parents=True)
    (staging_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    runtime_evidence_root = tmp_path / "canonical-runtime-evidence"
    runtime_evidence_root.mkdir(mode=0o700)
    cutover_evidence_root = tmp_path / "private-cutover-evidence"
    cutover_evidence_root.mkdir(mode=0o700)
    runtime_authority_output = (
        runtime_evidence_root / "active-runtime-authority.json"
    )
    module.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=journal,
        shared_mutation_lock_token="4" * 64,
        runtime_prior_state=runtime_prior_state(),
        staging_root=staging_root,
        backup_root=backup_root,
        activation_receipt=tmp_path / "activation.json",
        **deploy_proof_authority(tmp_path),
    )
    readiness_path, readiness_sha256 = (
        write_install_linking_authority_readiness(
            cutover_evidence_root
            / "install-linking-authority-readiness-test.json"
        )
    )
    with pytest.raises(RuntimeError, match="before tunnel start"):
        module.complete_transaction(
            source_root=source_root,
            active_root=active_root,
            journal_path=journal,
            runtime_authority_output=runtime_authority_output,
            candidate_portal_container_id=CANDIDATE_PORTAL_ID,
            candidate_portal_container_name=CANDIDATE_PORTAL_NAME,
            candidate_portal_image_id=CANDIDATE_PORTAL_IMAGE,
            install_linking_authority_readiness=readiness_path,
            install_linking_authority_readiness_sha256=readiness_sha256,
            shared_mutation_lock_token="4" * 64,
        )
    for phase in module.TRANSACTION_PHASES[1:]:
        module.mark_phase(
            source_root=source_root,
            active_root=active_root,
            journal_path=journal,
            phase=phase,
            shared_mutation_lock_token="4" * 64,
        )

    killed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.util
import os
import signal
import sys
from contextlib import nullcontext
from pathlib import Path

(
    script,
    source,
    active,
    journal,
    authority,
    container_id,
    name,
    image,
    readiness,
    readiness_sha256,
) = sys.argv[1:]
spec = importlib.util.spec_from_file_location("killed_complete_transaction", script)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.overlay.public_edge_mutation_lock = lambda **_kwargs: nullcontext(None)
module.overlay.overlay_publish_lock = lambda *_args, **_kwargs: nullcontext(None)
original_unlink = Path.unlink

def kill_before_journal_retirement(path, *args, **kwargs):
    if path == Path(journal):
        os.kill(os.getpid(), signal.SIGKILL)
    return original_unlink(path, *args, **kwargs)

Path.unlink = kill_before_journal_retirement
module.complete_transaction(
    source_root=Path(source),
    active_root=Path(active),
    journal_path=Path(journal),
    runtime_authority_output=Path(authority),
    candidate_portal_container_id=container_id,
    candidate_portal_container_name=name,
    candidate_portal_image_id=image,
    install_linking_authority_readiness=Path(readiness),
    install_linking_authority_readiness_sha256=readiness_sha256,
    shared_mutation_lock_token="4" * 64,
)
""",
            str(SCRIPT_PATH),
            str(source_root),
            str(active_root),
            str(journal),
            str(runtime_authority_output),
            CANDIDATE_PORTAL_ID,
            CANDIDATE_PORTAL_NAME,
            CANDIDATE_PORTAL_IMAGE,
            str(readiness_path),
            readiness_sha256,
        ],
        check=False,
    )
    assert killed.returncode == -signal.SIGKILL

    # A crash after the candidate authority is durable but before journal
    # retirement remains rollback-authorized: recovery sees the journal first.
    assert journal.exists()
    interrupted_authority = json.loads(
        runtime_authority_output.read_text(encoding="utf-8")
    )
    assert interrupted_authority["portal"]["containerId"] == CANDIDATE_PORTAL_ID
    interrupted_authority_bytes = (
        runtime_authority_output
    ).read_bytes()
    interrupted_authority_identity = (
        runtime_authority_output
    ).stat()

    receipt = module.complete_transaction(
        source_root=source_root,
        active_root=active_root,
        journal_path=journal,
        runtime_authority_output=runtime_authority_output,
        candidate_portal_container_id=CANDIDATE_PORTAL_ID,
        candidate_portal_container_name=CANDIDATE_PORTAL_NAME,
        candidate_portal_image_id=CANDIDATE_PORTAL_IMAGE,
        install_linking_authority_readiness=readiness_path,
        install_linking_authority_readiness_sha256=readiness_sha256,
        shared_mutation_lock_token="4" * 64,
    )

    assert receipt["status"] == "pass"
    assert receipt["journalRetired"] is True
    assert not journal.exists()
    authority = json.loads(
        runtime_authority_output.read_text(encoding="utf-8")
    )
    assert set(authority) == module.ACTIVE_RUNTIME_AUTHORITY_FIELDS
    assert authority["portal"]["containerId"] == CANDIDATE_PORTAL_ID
    assert authority["portal"]["containerName"] == CANDIDATE_PORTAL_NAME
    assert authority["portal"]["proofAuthorityMountSha256"] == CANDIDATE_PROOF_SHA256
    assert authority["portal"]["proofAuthorityMountSha256"] != PRIOR_PROOF_SHA256
    assert authority["installLinkingAuthorityReadinessPath"] == str(
        readiness_path
    )
    assert authority["installLinkingAuthorityReadinessSha256"] == readiness_sha256
    assert (
        runtime_authority_output
    ).read_bytes() == interrupted_authority_bytes
    completed_authority_identity = (
        runtime_authority_output
    ).stat()
    assert (
        completed_authority_identity.st_ino
        == interrupted_authority_identity.st_ino
    )
    assert (
        completed_authority_identity.st_mtime_ns
        == interrupted_authority_identity.st_mtime_ns
    )


def test_deploy_script_orders_staging_activation_and_full_preflight() -> None:
    script_path = ROOT / "scripts" / "deploy_public_edge_portal.sh"
    script = script_path.read_text(encoding="utf-8")
    source_gate = (
        'trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \\\n'
        '  --source-root "$SOURCE_ROOT" \\\n'
        '  --skip-overlay-marker-check'
    )
    stage = (
        'trusted_source_python "$SOURCE_ROOT/scripts/publish_public_edge_portal_overlay.py" \\\n'
        '  --source-root "$SOURCE_ROOT"'
    )
    drain = "compose_cli stop chummer-run-cloudflared"
    activation = (
        'trusted_source_python "$SOURCE_ROOT/scripts/publish_public_edge_portal_overlay.py" \\\n'
        '  --activate \\\n'
        '  --reuse-staging'
    )
    full_preflight = (
        'trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \\\n'
        '  --source-root "$SOURCE_ROOT" \\\n'
        '  --overlay-root "$OVERLAY_ROOT"'
    )

    first_source_gate = script.index(source_gate)
    stage_index = script.index(stage, first_source_gate)
    journal_index = script.index(
        'public_edge_overlay_transaction.py" snapshot',
        stage_index,
    )
    build_phase_index = script.index(
        "mark_deploy_phase image_build_started",
        journal_index,
    )
    candidate_promotion_index = script.index(
        'docker_cli image tag \\\n'
        '  "$INSTALL_LINKING_CANDIDATE_PORTAL_TAG" "$IMAGE_TAG"',
        build_phase_index,
    )
    build_complete_phase_index = script.index(
        "mark_deploy_phase image_built",
        candidate_promotion_index,
    )
    second_source_gate = script.index(source_gate, build_complete_phase_index)
    drain_index = script.index(drain, second_source_gate)
    activation_index = script.index(activation, drain_index)
    full_preflight_index = script.index(full_preflight, activation_index)
    volume_init_index = script.index("compose_cli run --rm --no-deps chummer-portal-volume-init")

    assert (
        first_source_gate
        < stage_index
        < journal_index
        < build_phase_index
        < candidate_promotion_index
        < build_complete_phase_index
        < second_source_gate
    )
    assert second_source_gate < drain_index < activation_index < volume_init_index
    assert volume_init_index < full_preflight_index
    assert (
        'RELEASE_CHANNEL_RECEIPT_INPUT="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT-}"'
        in script
    )
    assert "--output-name RELEASE_CHANNEL.generated.json" in script
    assert "authenticated CURRENT release channel is unavailable" in script
    assert (
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256 must be independently supplied"
        in script
    )
    assert (
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT must be externally supplied"
        not in script
    )
    assert script.count('--release-channel-receipt "$RELEASE_CHANNEL_RECEIPT"') == 7
    assert script.count('--release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256"') == 7
    assert "public_edge_deploy_recovery.py" in script
    assert "run_deploy_recovery" in script
    assert 'DEPLOY_OPERATION="${1:-deploy}"' in script
    assert "public_edge_deploy_recovered_interrupted_transaction" in script
    assert "active-overlay-transaction.json" in script
    assert '--prior-tool-image-tag-id "$prior_tool_image_tag_id"' in script
    assert '--prior-tunnel-image-id "$prior_tunnel_image_id"' in script
    assert "replacement_portal_may_exist" not in script
    assert 'proof.get("sha256")' in script
    assert "if before != after:" in script
    assert "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json" in script
    assert (
        "/app/wwwroot/proofs/mac-codex-release/"
        "HUB_LOCAL_RELEASE_PROOF.generated.json"
    ) in script
    proof_compare_index = script.index('if [[ "$proof_authority_mount_sha256"')
    portal_candidate_index = script.index(
        "compose_cli run -T -d --no-deps --service-ports --use-aliases",
        full_preflight_index,
    )
    candidate_identity_index = script.index(
        "if ! verify_candidate_runtime_identity; then",
        proof_compare_index,
    )
    complete_index = script.index(
        'public_edge_overlay_transaction.py" complete',
        candidate_identity_index,
    )
    prior_cleanup_index = script.index(
        'docker_cli container rm "$prior_portal_container_id"',
        complete_index,
    )
    assert full_preflight_index < portal_candidate_index < proof_compare_index
    assert proof_compare_index < candidate_identity_index < complete_index < prior_cleanup_index
    assert "--force-recreate" not in script
    assert "exit 70" in script
