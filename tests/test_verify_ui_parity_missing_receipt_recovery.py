from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts" / "ai" / "verify.sh"


def test_missing_nested_release_receipt_rematerializes_parity_gates() -> None:
    verifier = VERIFY_SCRIPT.read_text(encoding="utf-8")

    assert 'MISSING_EXECUTABLE_RECEIPT_MARKER="parity audit failed: required executable receipt is missing:"' in verifier
    assert "resolve_ui_parity_release_channel_recovery_path" in verifier
    assert '"$ROOT_DIR/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"' in verifier
    assert 'CHUMMER_UI_REPO_ROOT_ALIAS="$UI_REPO_ROOT"' in verifier
    assert 'CHUMMER_DESKTOP_WORKFLOW_RELEASE_CHANNEL_PATH="$release_channel_recovery_path"' in verifier
    assert 'CHUMMER_DESKTOP_VISUAL_RELEASE_CHANNEL_PATH="$release_channel_recovery_path"' in verifier
    assert 'CHUMMER_FLAGSHIP_UI_RELEASE_CHANNEL_PATH="$release_channel_recovery_path"' in verifier
    assert 'run_gate_materializer_script "$UI_WORKFLOW_GATE_MATERIALIZER" "workflow gate materializer"' in verifier


def test_missing_receipt_recovery_keeps_fail_closed_manifest_requirement() -> None:
    verifier = VERIFY_SCRIPT.read_text(encoding="utf-8")

    assert "UI parity receipt recovery requires an existing authoritative release-channel manifest." in verifier
    assert "return 1" in verifier
