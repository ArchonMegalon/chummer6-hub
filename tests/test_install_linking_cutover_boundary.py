from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_install_linking_cutover_boundary.py"
CANDIDATE_IMAGE = "sha256:" + "a" * 64
CANDIDATE_TOOL_IMAGE = "sha256:" + "c" * 64


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
        candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        operator_container_image_id=(
            CANDIDATE_TOOL_IMAGE
            if phase in module.OPERATOR_COMPLETION_PHASES
            else None
        ),
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
    assert persisted["candidateToolImageId"] == CANDIDATE_TOOL_IMAGE
    assert persisted["importDisposition"] == "completed"
    assert persisted["importCompleted"] is True
    assert persisted["importSkippedNoLocalStore"] is False
    assert persisted["localStorePresentAtCutover"] is True
    assert persisted["sequence"] == len(module.PHASES)
    assert persisted["previousPhase"] == "validate_completed"
    assert len(persisted["previousReceiptSha256"]) == 64
    assert os.stat(output).st_mode & 0o777 == 0o600
    phase_receipts = [output.with_name(f"{output.name}.{phase}.json") for phase in module.PHASES]
    assert all(path.is_file() for path in phase_receipts)
    assert all(os.stat(path).st_mode & 0o777 == 0o600 for path in phase_receipts)
    for index, path in enumerate(phase_receipts):
        journal = json.loads(path.read_text(encoding="utf-8"))
        assert journal["sequence"] == index + 1
        if index == 0:
            assert journal["previousReceiptSha256"] is None
        else:
            prior_bytes = phase_receipts[index - 1].read_bytes()
            assert journal["previousReceiptSha256"] == hashlib.sha256(prior_bytes).hexdigest()


def test_boundary_receipt_records_no_local_store_branch_before_validation(
    tmp_path: Path,
) -> None:
    module = load_module()
    output = tmp_path / "boundary.json"
    active_build_info = build_info(tmp_path)

    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
        "public_acceptance_completed",
    ):
        receipt = advance(module, output, active_build_info, phase)

    assert receipt["status"] == "pass"
    assert receipt["sequence"] == 5
    assert receipt["importDisposition"] == "skipped_no_local_store"
    assert receipt["importCompleted"] is False
    assert receipt["importSkippedNoLocalStore"] is True
    assert receipt["localStorePresentAtCutover"] is False
    assert receipt["validateCompleted"] is True
    skipped_receipt = output.with_name(
        f"{output.name}.{module.IMPORT_SKIPPED_PHASE}.json"
    )
    assert skipped_receipt.is_file()


def test_boundary_receipt_requires_import_or_explicit_no_store_checkpoint(
    tmp_path: Path,
) -> None:
    module = load_module()
    output = tmp_path / "boundary.json"
    active_build_info = build_info(tmp_path)
    advance(module, output, active_build_info, "prepare_starting")
    advance(module, output, active_build_info, "prepare_completed")

    with pytest.raises(ValueError, match="cannot skip"):
        advance(module, output, active_build_info, "validate_completed")


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
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            operator_container_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
        )

    with pytest.raises(ValueError, match="candidate tool image identity drifted"):
        module.materialize(
            output=output,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id="sha256:" + "d" * 64,
            operator_container_image_id="sha256:" + "d" * 64,
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
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=build_info(tmp_path),
        )


def test_boundary_receipt_rejects_repeated_phase_and_symlinked_receipt_root(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    advance(module, output, active_build_info, "prepare_starting")
    with pytest.raises(ValueError, match="advance exactly once"):
        advance(module, output, active_build_info, "prepare_starting")

    real_root = tmp_path / "real-receipts"
    real_root.mkdir(mode=0o700)
    linked_root = tmp_path / "linked-receipts"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValueError, match="must not contain symlinks"):
        module.materialize(
            output=linked_root / "boundary.json",
            phase="prepare_starting",
            cutover_id="2026-07-17T12:00:01Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
        )


def test_boundary_receipt_requires_verified_tool_image_for_operator_completion(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    advance(module, output, active_build_info, "prepare_starting")
    with pytest.raises(ValueError, match="exact candidate tool image"):
        module.materialize(
            output=output,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            operator_container_image_id="sha256:" + "e" * 64,
            active_build_info=active_build_info,
        )
