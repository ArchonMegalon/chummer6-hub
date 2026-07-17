from __future__ import annotations

import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "public_edge_overlay_transaction.py"


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

    payload = module.mark_phase(
        source_root=source_root,
        active_root=active_root,
        journal_path=journal,
        phase="overlay_activated",
        shared_mutation_lock_token="2" * 64,
    )
    assert payload["phase"] == "overlay_activated"
    with pytest.raises(RuntimeError, match="cannot move backward"):
        module.mark_phase(
            source_root=source_root,
            active_root=active_root,
            journal_path=journal,
            phase="portal_stopped",
            shared_mutation_lock_token="2" * 64,
        )
    assert json.loads(journal.read_text(encoding="utf-8"))["phase"] == "overlay_activated"


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
    build_index = script.index("docker_cli buildx build", stage_index)
    second_source_gate = script.index(source_gate, build_index)
    drain_index = script.index(drain, second_source_gate)
    activation_index = script.index(activation, drain_index)
    full_preflight_index = script.index(full_preflight, activation_index)
    volume_init_index = script.index("compose_cli run --rm --no-deps chummer-portal-volume-init")

    assert first_source_gate < stage_index < build_index < second_source_gate
    assert second_source_gate < drain_index < activation_index < volume_init_index
    assert volume_init_index < full_preflight_index
    assert (
        'RELEASE_CHANNEL_RECEIPT_INPUT="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT-}"'
        in script
    )
    assert "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT must be externally supplied" in script
    assert script.count('--release-channel-receipt "$RELEASE_CHANNEL_RECEIPT"') == 7
    assert script.count('--release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256"') == 6
    assert "restore_prior_overlay" in script
    assert "restore_prior_tunnel" in script
    assert "active-overlay-transaction.json" in script
    assert 'proof.get("sha256")' in script
    assert "if before != after:" in script
    assert "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json" in script
    assert (
        "/app/wwwroot/proofs/mac-codex-release/"
        "HUB_LOCAL_RELEASE_PROOF.generated.json"
    ) in script
    proof_compare_index = script.index('if [[ "$proof_authority_mount_sha256"')
    portal_recreate_index = script.index(
        "--wait --wait-timeout \"$PORTAL_READY_TIMEOUT_SECONDS\" chummer-portal",
        full_preflight_index,
    )
    candidate_identity_index = script.index(
        "if ! verify_candidate_runtime_identity; then",
        proof_compare_index,
    )
    assert portal_recreate_index < proof_compare_index < candidate_identity_index
    assert "exit 70" in script
