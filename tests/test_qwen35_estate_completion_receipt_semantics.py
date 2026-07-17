from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/check_qwen35_estate_completion.py")


def load_module():
    scripts_dir = str(SCRIPT_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("check_qwen35_estate_completion_semantics", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_is_passing_rejects_pass_shaped_receipt_with_failures() -> None:
    module = load_module()

    assert module.record_is_passing(
        {
            "id": "gate-mobile-pwa",
            "status": "pass",
            "failures": ["mobile PWA proof contradicted by live audit"],
        }
    ) is False


def test_command_receipt_ok_rejects_pass_shaped_receipt_with_failed_gates() -> None:
    module = load_module()

    assert module.command_receipt_ok(
        {
            "status": "pass",
            "failed_gates": ["verify_mobile_projection"],
            "evidence_paths": ["/tmp/fake-receipt.json"],
        }
    ) is False


def test_gate_presence_require_pass_rejects_pass_shaped_gate_with_failures() -> None:
    module = load_module()

    payload = {
        "gates": [
            {
                "id": "gate-auth-account-install",
                "status": "pass",
                "failures": ["google operator proof contradicted by embedded failures"],
            }
        ]
    }

    present, missing = module.gate_presence_in_payload(
        payload,
        ["gate-auth-account-install"],
        require_pass=True,
    )

    assert present == ["gate-auth-account-install"]
    assert missing == ["gate-auth-account-install"]
