from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "refresh_qwen35_estate_gate_receipts.py"


def load_module():
    spec = importlib.util.spec_from_file_location("refresh_qwen35_estate_gate_receipts", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gate_auth_account_install_materializes_google_operator_request_before_live_proof() -> None:
    module = load_module()
    gate = next(spec for spec in module.GATE_SPECS if spec.gate_id == "gate-auth-account-install")
    commands = [command.command for command in gate.commands]

    request_command = "python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run"
    request_verify_command = "python3 scripts/verify_google_oauth_linking_operator_evidence_request.py"
    proof_command = "python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run"

    assert request_command in commands
    assert request_verify_command in commands
    assert proof_command in commands
    assert commands.index(request_command) < commands.index(proof_command)
    assert commands.index(request_command) < commands.index(request_verify_command) < commands.index(proof_command)
