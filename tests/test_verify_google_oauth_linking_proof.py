from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_google_oauth_linking_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_google_oauth_linking_proof", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def structural_payload() -> dict:
    return {
        "contract_name": "chummer.run.google_oauth_linking_proof",
        "proof_contract_version": 2,
        "status": "fail",
        "base_url": "https://chummer.run",
        "quick_handoff_probe": {"pass": True},
        "signed_in_link_handoff": {"status": "operator_required", "pass": False},
        "operator_end_to_end_evidence": {
            "pass": False,
            "exists": False,
            "path": "/tmp/operator-evidence.json",
            "failures": ["missing operator evidence receipt: /tmp/operator-evidence.json"],
        },
        "operator_request_artifacts": {
            "pass": True,
            "request_receipt_path": "/tmp/operator-request.generated.json",
            "operator_ask_text_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt",
            "operator_ask_metadata_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json",
            "operator_evidence_template_path": "/tmp/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
            "required_operator_evidence_path": "/tmp/operator-evidence.json",
            "operator_ask_send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "operator_ask_receipt_name": "google-oauth-linking-operator-ask.receipt.json",
            "failures": [],
        },
        "failures": ["operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json"],
    }


def test_verify_accepts_structurally_valid_receipt_when_operator_evidence_is_still_missing(tmp_path: Path) -> None:
    module = load_module()
    receipt = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    write_json(receipt, structural_payload())

    ok, result = module.verify(receipt)

    assert ok is True
    assert result["status"] == "pass"
    assert result["operator_request_artifacts_pass"] is True
    assert result["operator_evidence_pass"] is False


def test_verify_requires_live_pass_when_flag_enabled(tmp_path: Path) -> None:
    module = load_module()
    receipt = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    write_json(receipt, structural_payload())

    ok, result = module.verify(receipt, require_pass=True)

    assert ok is False
    assert result["status"] == "fail"
    assert "operator_end_to_end_evidence_not_pass" in result["issues"]
    assert "receipt_status_not_pass" in result["issues"]


def test_verify_rejects_structurally_broken_request_pack_even_without_require_pass(tmp_path: Path) -> None:
    module = load_module()
    receipt = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    payload = structural_payload()
    payload["operator_request_artifacts"] = {
        "pass": False,
        "failures": ["operator ask metadata message_sha256 mismatch"],
    }
    write_json(receipt, payload)

    ok, result = module.verify(receipt)

    assert ok is False
    assert result["status"] == "fail"
    assert "operator_request_artifacts_not_pass" in result["issues"]
