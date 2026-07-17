from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_install_linking_cutover_boundary.py"
CANDIDATE_IMAGE = "sha256:" + "a" * 64


def load_module():
    spec = importlib.util.spec_from_file_location(
        "materialize_install_linking_cutover_boundary", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_info(tmp_path: Path) -> Path:
    path = tmp_path / "active" / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    path.parent.mkdir()
    path.write_text('{"status":"pass"}\n', encoding="utf-8")
    return path


def advance(module, output: Path, active_build_info: Path, phase: str):
    return module.materialize(
        output=output,
        phase=phase,
        cutover_id="2026-07-17T12:00:00Z",
        candidate_image_id=CANDIDATE_IMAGE,
        active_build_info=active_build_info,
    )


def test_boundary_receipt_advances_sequentially_and_records_recovery_truth(
    tmp_path: Path,
) -> None:
    module = load_module()
    output = tmp_path / "boundary.json"
    output.touch(mode=0o600)
    active_build_info = build_info(tmp_path)

    for phase in module.PHASES:
        receipt = advance(module, output, active_build_info, phase)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "pass"
    assert persisted["phase"] == "public_acceptance_completed"
    assert persisted["irreversibleDatabaseBoundaryMayHaveBeenEntered"] is True
    assert persisted["automaticDatabaseRollbackAllowed"] is False
    assert persisted["recoveryAuthority"] == {
        "mode": "postgres_pitr_or_governed_recovery",
        "portalAndTunnelMustRemainStoppedUntilAccepted": False,
        "preserveFailedAuthorityAndLogs": True,
        "localMirrorRollbackAllowed": False,
        "schemaOrGenerationRewindAllowed": False,
    }
    assert len(persisted["activeBuildInfoSha256"]) == 64
    assert os.stat(output).st_mode & 0o777 == 0o600


def test_boundary_receipt_rejects_skipped_or_reversed_phase(tmp_path: Path) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"

    with pytest.raises(ValueError, match="must start"):
        advance(module, output, active_build_info, "prepare_completed")
    advance(module, output, active_build_info, "prepare_starting")
    with pytest.raises(ValueError, match="cannot skip"):
        advance(module, output, active_build_info, "import_completed")
    advance(module, output, active_build_info, "prepare_completed")
    with pytest.raises(ValueError, match="cannot move backwards"):
        advance(module, output, active_build_info, "prepare_starting")


def test_boundary_receipt_rejects_build_info_or_identity_drift(tmp_path: Path) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    advance(module, output, active_build_info, "prepare_starting")

    active_build_info.write_text('{"status":"changed"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="build-info binding drifted"):
        advance(module, output, active_build_info, "prepare_completed")
    with pytest.raises(ValueError, match="candidate image identity drifted"):
        module.materialize(
            output=output,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id="sha256:" + "b" * 64,
            active_build_info=active_build_info,
        )


@pytest.mark.parametrize("cutover_id", ["", "bad value", "x/escape", "x" * 129])
def test_boundary_receipt_rejects_unsafe_cutover_id(
    tmp_path: Path, cutover_id: str
) -> None:
    module = load_module()
    with pytest.raises(ValueError, match="safe literal"):
        module.materialize(
            output=tmp_path / "boundary.json",
            phase="prepare_starting",
            cutover_id=cutover_id,
            candidate_image_id=CANDIDATE_IMAGE,
            active_build_info=build_info(tmp_path),
        )
