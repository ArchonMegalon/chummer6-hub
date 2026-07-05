from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_google_oauth_linking_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_google_oauth_linking_proof", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_parse_google_redirect_requires_pkce_nonce_and_scope() -> None:
    module = load_module()
    redirect = module.parse_google_redirect(
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?redirect_uri=https%3A%2F%2Fchummer.run%2Fauth%2Fgoogle%2Fcallback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=test-state"
        "&nonce=test-nonce"
        "&code_challenge=test-challenge"
        "&code_challenge_method=S256"
        "&prompt=select_account",
        "https://chummer.run/auth/google/callback",
    )

    assert redirect["pass"] is True
    assert redirect["redirect_uri_matches"] is True
    assert redirect["code_challenge_method_s256"] is True
    assert redirect["scope_includes_openid_profile_email"] is True

    broken = module.parse_google_redirect(
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?redirect_uri=https%3A%2F%2Fchummer.run%2Fauth%2Fgoogle%2Fcallback"
        "&response_type=code"
        "&scope=openid%20profile"
        "&state="
        "&code_challenge_method=plain",
        "https://chummer.run/auth/google/callback",
    )

    assert broken["pass"] is False
    assert broken["scope_includes_openid_profile_email"] is False
    assert broken["state_present"] is False
    assert broken["code_challenge_method_s256"] is False


def test_inspect_operator_evidence_requires_all_steps_and_screenshots(tmp_path: Path) -> None:
    module = load_module()
    screenshot_a = tmp_path / "a.png"
    screenshot_b = tmp_path / "b.png"
    screenshot_a.write_bytes(b"a")
    screenshot_b.write_bytes(b"b")

    evidence_path = tmp_path / "operator.json"
    write_json(
        evidence_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": module.DEFAULT_BASE_URL,
            "observed_at_utc": "2026-07-04T09:00:00Z",
            "verified_steps": [
                "google_sign_in_completed_to_signed_in_state",
                "existing_account_linked_google",
                "linked_provider_visible_on_account_profile_or_advanced",
            ],
            "screenshot_paths": [str(screenshot_a), str(screenshot_b)],
        },
    )

    summary = module.inspect_operator_evidence(module.DEFAULT_BASE_URL, evidence_path)

    assert summary["pass"] is False
    assert "operator evidence missing verified_steps: google_sign_in_returned_to_existing_account" in summary["failures"]


def test_materialize_requires_operator_end_to_end_evidence_even_when_probes_pass(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    request_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    ask_text_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
    ask_metadata_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
    template_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"
    delivery_root = tmp_path / "telegram"
    delivery_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        module,
        "probe_public_google_handoff",
        lambda base_url: {"pass": True, "failures": [], "redirect": {"pass": True}},
    )
    monkeypatch.setattr(
        module,
        "probe_signed_in_google_link_handoff",
        lambda base_url, email: {"pass": True, "failures": [], "email": email, "google_link_redirect": {"pass": True}},
    )
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH", request_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_TEXT_PATH", ask_text_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_METADATA_PATH", ask_metadata_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH", template_path)
    monkeypatch.setattr(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", delivery_root)
    write_json(
        request_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME,
            "status": "operator_action_required",
            "base_url": module.DEFAULT_BASE_URL,
            "required_operator_evidence_path": str(tmp_path / "missing-operator.json"),
            "required_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "minimum_screenshot_count": module.MINIMUM_OPERATOR_SCREENSHOT_COUNT,
            "recommended_screenshot_paths": ["/tmp/one.png", "/tmp/two.png"],
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "operator_message_preview": "Google operator ask preview",
            "operator_message_sha256": module.sha256_text("operator ask\n"),
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
        },
    )
    ask_text_path.write_text("operator ask\n", encoding="utf-8")
    write_json(
        delivery_root / "google-oauth-linking-operator-ask.receipt.json",
        {
            "status": "sent",
            "generated_at_utc": "2026-07-04T20:58:05Z",
            "text_sha256": module.sha256_text("stale operator ask\n"),
            "text_preview": "stale operator ask",
            "message_ids": ["1"],
        },
    )
    write_json(
        ask_metadata_path,
        {
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "message_preview": "Google operator ask preview",
            "message_sha256": module.sha256_text("operator ask\n"),
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
            "request_receipt_path": str(request_path),
            "required_operator_evidence_path": str(tmp_path / "missing-operator.json"),
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
        },
    )
    write_json(
        template_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": module.DEFAULT_BASE_URL,
            "observed_at_utc": "",
            "verified_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "screenshot_paths": ["/tmp/one.png", "/tmp/two.png"],
            "notes": "",
        },
    )

    output_path = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    receipt = module.materialize(
        base_url=module.DEFAULT_BASE_URL,
        output_path=output_path,
        operator_evidence_path=tmp_path / "missing-operator.json",
        audit_email=module.DEFAULT_AUDIT_EMAIL,
    )

    assert receipt["status"] == "fail"
    assert receipt["operator_end_to_end_evidence"]["pass"] is False
    assert receipt["operator_request_artifacts"]["pass"] is True
    assert receipt["operator_request_artifacts"]["request_receipt_path"] == str(request_path)
    assert receipt["operator_request_artifacts"]["operator_evidence_template_path"] == str(template_path)
    assert receipt["operator_request_artifacts"]["operator_ask_send_command"] == (
        "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
    )
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_current_text_comparable"] is True
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_matches_current_text"] is False
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_needs_resend"] is True
    assert receipt["operator_request_artifacts"]["operator_ask_resend_command"] == (
        "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
    )
    assert receipt["operator_request_artifacts"]["operator_ask_receipt_name"] == "google-oauth-linking-operator-ask.receipt.json"
    assert any(
        item
        == "operator_request_artifacts: operator ask delivery is stale; resend current ask: "
        "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
        for item in receipt["failures"]
    )
    assert any(str(request_path) in item for item in receipt["next_actions"])
    assert any(str(template_path) in item for item in receipt["next_actions"])
    assert any(
        item
        == "Resend the current Google operator ask before waiting for more evidence: "
        "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
        for item in receipt["next_actions"]
    )
    assert receipt["nextActions"] == receipt["next_actions"]
    assert any("missing operator evidence receipt" in item for item in receipt["failures"])
    assert output_path.is_file()


def test_materialize_flags_broken_operator_request_artifacts_when_evidence_is_missing(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    request_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    ask_text_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
    ask_metadata_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
    template_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"

    monkeypatch.setattr(
        module,
        "probe_public_google_handoff",
        lambda base_url: {"pass": True, "failures": [], "redirect": {"pass": True}},
    )
    monkeypatch.setattr(
        module,
        "probe_signed_in_google_link_handoff",
        lambda base_url, email: {"pass": True, "failures": [], "email": email, "google_link_redirect": {"pass": True}},
    )
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH", request_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_TEXT_PATH", ask_text_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_METADATA_PATH", ask_metadata_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH", template_path)
    write_json(
        request_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME,
            "status": "operator_action_required",
            "base_url": module.DEFAULT_BASE_URL,
            "required_operator_evidence_path": str(tmp_path / "missing-operator.json"),
            "required_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "minimum_screenshot_count": module.MINIMUM_OPERATOR_SCREENSHOT_COUNT,
            "recommended_screenshot_paths": ["/tmp/one.png", "/tmp/two.png"],
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "operator_message_preview": "Google operator ask preview",
            "operator_message_sha256": module.sha256_text("operator ask\n"),
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
        },
    )
    ask_text_path.write_text("operator ask\n", encoding="utf-8")
    write_json(
        ask_metadata_path,
        {
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "message_preview": "Google operator ask preview",
            "message_sha256": "deadbeef",
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
            "request_receipt_path": str(request_path),
            "required_operator_evidence_path": str(tmp_path / "missing-operator.json"),
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
        },
    )
    write_json(
        template_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": module.DEFAULT_BASE_URL,
            "observed_at_utc": "",
            "verified_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "screenshot_paths": ["/tmp/one.png", "/tmp/two.png"],
            "notes": "",
        },
    )

    receipt = module.materialize(
        base_url=module.DEFAULT_BASE_URL,
        output_path=tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
        operator_evidence_path=tmp_path / "missing-operator.json",
        audit_email=module.DEFAULT_AUDIT_EMAIL,
    )

    assert receipt["operator_request_artifacts"]["pass"] is False
    assert "operator ask metadata message_sha256 mismatch" in receipt["operator_request_artifacts"]["failures"]
    assert any(
        item == "operator_request_artifacts: operator ask metadata message_sha256 mismatch"
        for item in receipt["failures"]
    )


def test_verify_receipt_rejects_shallow_legacy_payload() -> None:
    module = load_module()
    ok, issues = module.verify_receipt(
        {
            "contract_name": "chummer.run.google_oauth_linking_proof",
            "status": "pass",
            "base_url": "https://chummer.run",
            "script": "scripts/check-google-oauth-linking.py",
            "test_cases": [
                "anonymous user starts on /login",
                "Google handoff completes and lands on signed-in state",
                "existing account can link Google",
                "linked account can sign back in with Google",
            ],
        },
        require_pass=True,
    )

    assert ok is False
    assert "proof_contract_version_too_old" in issues
    assert "missing_quick_handoff_probe" in issues
    assert "missing_signed_in_link_handoff" in issues
    assert "missing_operator_end_to_end_evidence" in issues
