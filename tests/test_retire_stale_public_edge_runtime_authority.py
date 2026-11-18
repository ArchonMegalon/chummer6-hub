from __future__ import annotations

from contextlib import nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/retire_stale_public_edge_runtime_authority.py"
CONTAINER_ID = "a" * 64


def load_module():
    spec = importlib.util.spec_from_file_location(
        "retire_stale_public_edge_runtime_authority_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeRuntime:
    def __init__(self, *, present: bool = False, ambiguous: bool = False) -> None:
        self.present = present
        self.ambiguous = ambiguous
        self.calls = 0

    def prove_missing(self, recorded_container_id: str) -> dict[str, object]:
        self.calls += 1
        assert recorded_container_id == CONTAINER_ID
        if self.present:
            raise RuntimeError("prior or canonical portal container is still present")
        if self.ambiguous:
            raise RuntimeError("Docker returned an ambiguous container identity")
        return {
            "dockerContext": "default",
            "dockerHost": "unix:///var/run/docker.sock",
            "project": "chummer6-hub",
            "service": "chummer-portal",
            "recordedContainerId": recorded_container_id,
            "recordedContainerPresent": False,
            "canonicalServiceContainerCount": 0,
            "anyPortalServiceContainerCount": 0,
            "publishedPort": 8091,
            "publishedPortContainerCount": 0,
        }


def authority_bytes() -> bytes:
    payload = {
        "contractName": "chummer.public-edge.active-runtime-authority/v1",
        "status": "pass",
        "generatedAtUtc": "2026-08-23T12:00:00Z",
        "portal": {
            "existed": True,
            "containerId": CONTAINER_ID,
            "containerName": "chummer6-hub-chummer-portal-1",
            "imageId": "sha256:" + "b" * 64,
            "wasRunning": True,
            "proofAuthorityMountSha256": "c" * 64,
            "proofPublicMountSha256": "c" * 64,
        },
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def fixture_paths(tmp_path: Path) -> dict[str, Path]:
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir(mode=0o700)
    active = receipt_root / "active-runtime-authority.json"
    active.write_bytes(authority_bytes())
    active.chmod(0o600)
    return {
        "active": active,
        "archive": receipt_root / "retired-active-runtime-authorities",
        "journal": receipt_root / "active-overlay-transaction.json",
        "public": receipt_root / "public-download-active-runtime-authority.json",
    }


def invoke(module, paths: dict[str, Path], runtime: FakeRuntime, **kwargs):
    return module.retire_stale_authority(
        operation_id="missing-portal-20260823",
        expected_authority_sha256=hashlib.sha256(authority_bytes()).hexdigest(),
        active_authority=paths["active"],
        archive_root=paths["archive"],
        deploy_journal=paths["journal"],
        public_download_authority=paths["public"],
        runtime=runtime,
        mutation_lock=nullcontext(),
        **kwargs,
    )


def test_retirement_archives_exact_authority_no_clobber_then_removes_active(
    tmp_path: Path,
) -> None:
    module = load_module()
    paths = fixture_paths(tmp_path)
    runtime = FakeRuntime()

    receipt = invoke(module, paths, runtime)

    archive_path = paths["archive"] / "missing-portal-20260823.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    metadata = archive_path.lstat()
    assert receipt["status"] == "pass"
    assert receipt["disposition"] == "retired"
    assert not paths["active"].exists()
    assert archive["reason"] == "recorded_portal_container_missing"
    assert archive["priorAuthoritySha256"] == hashlib.sha256(authority_bytes()).hexdigest()
    assert archive["priorAuthority"]["portal"]["containerId"] == CONTAINER_ID
    assert archive["evidence"]["canonicalServiceContainerCount"] == 0
    assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert metadata.st_nlink == 1
    assert metadata.st_uid == os.geteuid()
    assert runtime.calls == 2


def test_retirement_fault_after_archive_is_resumable_without_clobber(
    tmp_path: Path,
) -> None:
    module = load_module()
    paths = fixture_paths(tmp_path)
    runtime = FakeRuntime()

    with pytest.raises(RuntimeError, match="injected crash"):
        invoke(
            module,
            paths,
            runtime,
            after_archive=lambda: (_ for _ in ()).throw(RuntimeError("injected crash")),
        )

    archive_path = paths["archive"] / "missing-portal-20260823.json"
    original_archive = archive_path.read_bytes()
    assert paths["active"].is_file()

    receipt = invoke(module, paths, runtime)

    assert receipt["disposition"] == "retired"
    assert archive_path.read_bytes() == original_archive
    assert not paths["active"].exists()
    already = invoke(module, paths, runtime)
    assert already["disposition"] == "already_retired"


@pytest.mark.parametrize("runtime", [FakeRuntime(present=True), FakeRuntime(ambiguous=True)])
def test_retirement_rejects_live_or_ambiguous_runtime(
    tmp_path: Path,
    runtime: FakeRuntime,
) -> None:
    module = load_module()
    paths = fixture_paths(tmp_path)

    with pytest.raises(RuntimeError):
        invoke(module, paths, runtime)

    assert paths["active"].is_file()
    assert not (paths["archive"] / "missing-portal-20260823.json").exists()


@pytest.mark.parametrize("blocker", ["journal", "public"])
def test_retirement_does_not_weaken_existing_recovery_or_topology_authority(
    tmp_path: Path,
    blocker: str,
) -> None:
    module = load_module()
    paths = fixture_paths(tmp_path)
    paths[blocker].write_text("{}\n", encoding="utf-8")
    paths[blocker].chmod(0o600)

    with pytest.raises(RuntimeError, match="still own this state"):
        invoke(module, paths, FakeRuntime())

    assert paths["active"].is_file()


def test_retirement_rejects_pin_mode_link_and_operation_drift(tmp_path: Path) -> None:
    module = load_module()
    paths = fixture_paths(tmp_path)
    with pytest.raises(RuntimeError, match="external SHA-256 pin"):
        module.retire_stale_authority(
            operation_id="missing-portal-20260823",
            expected_authority_sha256="0" * 64,
            active_authority=paths["active"],
            archive_root=paths["archive"],
            deploy_journal=paths["journal"],
            public_download_authority=paths["public"],
            runtime=FakeRuntime(),
            mutation_lock=nullcontext(),
        )
    paths["active"].chmod(0o644)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        invoke(module, paths, FakeRuntime())
    paths["active"].chmod(0o600)
    alias = paths["active"].with_suffix(".alias")
    os.link(paths["active"], alias)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        invoke(module, paths, FakeRuntime())
