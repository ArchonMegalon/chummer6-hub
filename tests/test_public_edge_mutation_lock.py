from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_edge_mutation_lock.py"


def load_module():
    spec = importlib.util.spec_from_file_location("public_edge_mutation_lock_tested", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def roots(tmp_path: Path) -> tuple[Path, Path]:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    auth = state / "public-edge-lock-recovery-receipts"
    return state / "public-edge-mutation.lock", auth


def test_lease_is_published_complete_and_release_retires_before_cleanup(tmp_path: Path) -> None:
    module = load_module()
    lock, auth = roots(tmp_path)
    lease = module.acquire_mutation_lease(
        actor="restore", lock_path=lock, authorization_root=auth
    )

    assert (lock / "owner-token").read_text(encoding="ascii").strip() == lease.token
    assert lease.authorization_path.read_text(encoding="ascii").strip() == lease.token
    assert lease.authorization_path.name == f"restore-{lease.token_sha256}.owner-token"
    assert lease.receipt(status="active")["tokenSha256"] == lease.token_sha256
    assert "token" not in lease.receipt(status="active")

    module.release_mutation_lease(lease)
    assert not lock.exists()
    assert not lease.authorization_path.exists()
    assert not list(lock.parent.glob(".public-edge-mutation.lock.retired.*"))


def test_sigkill_shape_keeps_fixed_lock_and_external_authorization(tmp_path: Path) -> None:
    module = load_module()
    lock, auth = roots(tmp_path)
    lease = module.acquire_mutation_lease(
        actor="cutover", lock_path=lock, authorization_root=auth
    )

    # Dropping the in-memory lease simulates process death: both recovery authorities persist.
    assert lock.is_dir()
    assert (lock / "owner-token").is_file()
    assert lease.authorization_path.is_file()
    with pytest.raises(module.PublicEdgeMutationLockUnavailable, match="another public-edge"):
        module.acquire_mutation_lease(
            actor="restore", lock_path=lock, authorization_root=auth
        )


def test_unique_authorization_orphan_never_blocks_later_acquisition(tmp_path: Path) -> None:
    module = load_module()
    lock, auth = roots(tmp_path)
    auth.mkdir(mode=0o700)
    orphan = auth / ("deploy-" + "a" * 64 + ".owner-token")
    orphan.write_text("b" * 64 + "\n", encoding="ascii")
    orphan.chmod(0o600)

    lease = module.acquire_mutation_lease(
        actor="restore", lock_path=lock, authorization_root=auth
    )
    assert orphan.exists()
    module.release_mutation_lease(lease)
    assert orphan.exists()


def test_failed_no_replace_acquisition_cleans_its_unpublished_authorization(
    tmp_path: Path,
) -> None:
    module = load_module()
    lock, auth = roots(tmp_path)
    lock.mkdir(mode=0o700)

    with pytest.raises(module.PublicEdgeMutationLockUnavailable, match="another public-edge"):
        module.acquire_mutation_lease(
            actor="deploy", lock_path=lock, authorization_root=auth
        )

    assert lock.is_dir()
    assert list(lock.iterdir()) == []
    assert list(auth.glob("deploy-*.owner-token")) == []


def test_publish_uses_complete_staging_lock_before_atomic_no_replace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_module()
    lock, auth = roots(tmp_path)
    original_rename = module._rename_noreplace
    observed: list[bool] = []

    def inspect_then_rename(source: Path, destination: Path) -> None:
        if destination == lock:
            token = (source / "owner-token").read_text(encoding="ascii").strip()
            digest = module.hashlib.sha256(token.encode("ascii")).hexdigest()
            observed.append((auth / f"deploy-{digest}.owner-token").exists())
        original_rename(source, destination)

    monkeypatch.setattr(module, "_rename_noreplace", inspect_then_rename)
    lease = module.acquire_mutation_lease(
        actor="deploy", lock_path=lock, authorization_root=auth
    )
    assert observed == [True]
    module.release_mutation_lease(lease)


def test_retired_cleanup_orphan_does_not_republish_fixed_lock(tmp_path: Path) -> None:
    module = load_module()
    lock, auth = roots(tmp_path)
    interrupted = module.acquire_mutation_lease(
        actor="restore", lock_path=lock, authorization_root=auth
    )
    retired = lock.parent / f".{lock.name}.retired.{interrupted.token_sha256}"
    module._rename_noreplace(lock, retired)
    module._fsync_directory(lock.parent)

    replacement = module.acquire_mutation_lease(
        actor="deploy", lock_path=lock, authorization_root=auth
    )
    assert retired.is_dir()
    assert interrupted.authorization_path.is_file()
    module.release_mutation_lease(replacement)


@pytest.mark.parametrize("symlink_authorization_root", [False, True])
def test_lease_rejects_symlink_in_lock_or_authorization_path_components(
    tmp_path: Path, symlink_authorization_root: bool
) -> None:
    module = load_module()
    real_state = tmp_path / "real-state"
    real_state.mkdir(mode=0o700)
    alias = tmp_path / "state-alias"
    alias.symlink_to(real_state, target_is_directory=True)

    if symlink_authorization_root:
        lock = real_state / "public-edge-mutation.lock"
        authorization_root = alias / "public-edge-lock-recovery-receipts"
    else:
        lock = alias / "public-edge-mutation.lock"
        authorization_root = real_state / "public-edge-lock-recovery-receipts"

    with pytest.raises(
        module.PublicEdgeMutationLockUnavailable, match="must not contain symlinks"
    ):
        module.acquire_mutation_lease(
            actor="deploy",
            lock_path=lock,
            authorization_root=authorization_root,
        )
    assert not lock.exists()
