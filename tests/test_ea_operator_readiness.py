from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MATERIALIZE = Path(__file__).resolve().parents[1] / "scripts" / "materialize_ea_operator_readiness.py"
VERIFY = Path(__file__).resolve().parents[1] / "scripts" / "verify_ea_operator_readiness.py"
PUBLIC_PAIRING_HREF = "host-local:///sessions/redacted/pair"
PUBLIC_MYMEDIA_WATCH_HREF = "host-local:///index.html#!/tables"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_onemin_rate_limit_is_supplemental_attention_not_a_blocker() -> None:
    module = _load(MATERIALIZE, "materialize_ea_operator_readiness_onemin_rate_limit")
    component = {
        "key": "onemin_direct_refresh",
        "probe_ok": True,
        "ready": False,
        "status": "rate_limited",
    }

    assert module.readiness_contract.component_requires_attention(component) is True
    assert module.readiness_contract.component_counts_as_blocked(component) is False


def test_build_receipt_keeps_operator_state_but_fails_on_missing_components(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_ea_operator_readiness")
    payload = {
        "observed_at": "2026-07-04T17:12:09Z",
        "probe_ok": True,
        "ready": False,
        "status": "ready_with_actions",
        "attention_required_count": 2,
        "blocked_count": 1,
        "component_count": 2,
        "components": [
            {"key": "telegram", "status": "ready"},
            {"key": "whatsapp", "status": "blocked"},
        ],
        "next_actions": [{"action": "scan_whatsapp_web_qr"}],
    }
    monkeypatch.setattr(module, "_run_probe", lambda timeout_seconds: (0, payload, json.dumps(payload), ""))

    receipt = module.build_receipt(timeout_seconds=5.0)

    assert receipt["updated_at"]
    assert receipt["status"] == "fail"
    assert receipt["structural_status"] == "fail"
    assert receipt["effective_status"] == "ready_with_actions"
    assert receipt["operator_status"] == "ready_with_actions"
    assert receipt["runtime_status"] == "blocked"
    assert receipt["runtime_ready"] is False
    assert receipt["blocking_count"] == 2
    assert receipt["advisory_count"] == 0
    assert receipt["probe_ok"] is True
    assert "google_workspace_oauth" in receipt["missing_component_keys"]
    assert receipt["secret_leak_detected"] is False


def test_build_receipt_treats_presence_flags_as_secret_safe(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_ea_operator_readiness_presence")
    payload = {
        "observed_at": "2026-07-04T17:12:09Z",
        "probe_ok": True,
        "ready": False,
        "status": "ready_with_actions",
        "source": "/docker/EA/scripts/ea_live_ops.py",
        "attention_required_count": 2,
        "blocked_count": 2,
        "probe_failed_count": 0,
        "component_count": 7,
        "components": [
            {
                "key": "telegram",
                "label": "Telegram operator delivery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "source": "/docker/EA/app/services/telegram_delivery.py",
                "details": {"bot_token_present": True},
            },
            {
                "key": "google_workspace_oauth",
                "label": "Google Workspace OAuth",
                "probe_ok": True,
                "ready": True,
                "status": "pass",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "source": "scripts.materialize_google_workspace_oauth_readiness.py",
                "details": {"expected_google_email_present": True},
            },
            {
                "key": "pushbullet",
                "label": "Pushbullet operator delivery",
                "probe_ok": True,
                "ready": False,
                "status": "blocked_setup_required",
                "reason": "pushbullet_token_missing:elisabeth",
                "next_action": "create_missing_pushbullet_access_tokens",
                "next_action_href": "https://www.pushbullet.com/#settings/account",
                "next_action_label": "Open Pushbullet account settings",
                "next_action_method": "get",
                "source": "scripts/materialize_pushbullet_delivery_readiness.py",
                "details": {"missing_token_keys": ["elisabeth"]},
            },
            {
                "key": "whatsapp",
                "label": "WhatsApp Web action processor",
                "probe_ok": True,
                "ready": False,
                "status": "blocked",
                "reason": "sidecar_not_ready",
                "next_action": "scan_whatsapp_web_qr",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {"processor_callback_secret_present": True},
            },
            {
                "key": "whatsapp_pairing",
                "label": "WhatsApp Web pairing recovery",
                "probe_ok": True,
                "ready": False,
                "status": "available",
                "reason": "",
                "next_action": "scan_whatsapp_web_qr",
                "next_action_href": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "next_action_label": "Open WhatsApp pairing",
                "next_action_method": "get",
                "source": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "details": {"session_ref": "tibor-wa-web"},
            },
            {
                "key": "teable_recovery",
                "label": "Teable env recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {"missing_secret_value_count": 0},
            },
            {
                "key": "mymedia_alexa",
                "label": "My Media for Alexa",
                "probe_ok": True,
                "ready": True,
                "status": "ready_library_scan_in_progress",
                "reason": "mymedia_library_scan_in_progress",
                "next_action": "wait_for_mymedia_library_scan",
                "next_action_href": "http://127.0.0.1:52051/index.html#!/tables",
                "next_action_label": "Open Watch Folders",
                "next_action_method": "get",
                "source": "file:///docker/EA/scripts/probe_mymedia_alexa.py",
                "details": {"pairing_ready": True},
            },
        ],
        "next_actions": [
            {
                "component_key": "pushbullet",
                "component_label": "Pushbullet operator delivery",
                "action": "create_missing_pushbullet_access_tokens",
                "reason": "pushbullet_token_missing:elisabeth",
                "href": "https://www.pushbullet.com/#settings/account",
                "label": "Open Pushbullet account settings",
                "method": "get",
            },
            {
                "component_key": "whatsapp_pairing",
                "component_label": "WhatsApp Web pairing recovery",
                "action": "scan_whatsapp_web_qr",
                "reason": "",
                "href": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "label": "Open WhatsApp pairing",
                "method": "get",
            },
        ],
    }
    monkeypatch.setattr(module, "_run_probe", lambda timeout_seconds: (0, payload, json.dumps(payload), ""))

    receipt = module.build_receipt(timeout_seconds=5.0)

    assert receipt["updated_at"]
    assert receipt["status"] == "pass"
    assert receipt["structural_status"] == "pass"
    assert receipt["effective_status"] == "ready_with_actions"
    assert receipt["runtime_status"] == "blocked"
    assert receipt["runtime_ready"] is False
    assert receipt["blocking_count"] == 1
    assert receipt["advisory_count"] == 1
    assert receipt["blocking_findings"] == ["blocked:whatsapp_pairing:available"]
    assert receipt["advisory_findings"] == ["attention:pushbullet:blocked_setup_required"]
    assert receipt["secret_leak_detected"] is False
    assert all("details" not in component for component in receipt["components"])
    assert "missing_token_keys" not in receipt["stdout_tail"]
    assert "session_ref" not in receipt["stdout_tail"]
    assert receipt["stdout_tail"].startswith("returncode=0 ")
    assert "runtime_status=blocked" in receipt["stdout_tail"]
    assert "source=script:ea_live_ops.py" in receipt["stdout_tail"]
    assert "/docker/EA" not in receipt["stdout_tail"]
    assert "elisabeth" not in json.dumps(receipt)
    assert "tibor-wa-web" not in json.dumps(receipt)
    assert receipt["components"][2]["reason"] == "pushbullet_token_missing"
    assert receipt["components"][0]["source"] == "script:telegram_delivery.py"
    assert receipt["components"][1]["source"] == "script:materialize_google_workspace_oauth_readiness.py"
    assert receipt["components"][2]["source"] == "script:materialize_pushbullet_delivery_readiness.py"
    assert receipt["components"][4]["source"] == PUBLIC_PAIRING_HREF
    assert receipt["components"][6]["source"] == "script:probe_mymedia_alexa.py"
    assert receipt["components"][4]["next_action_href"] == PUBLIC_PAIRING_HREF
    assert receipt["components"][6]["next_action_href"] == PUBLIC_MYMEDIA_WATCH_HREF
    assert receipt["next_actions"][0]["reason"] == "pushbullet_token_missing"
    assert receipt["next_actions"][1]["href"] == PUBLIC_PAIRING_HREF
    assert receipt["advisory_action_component_keys"] == ["mymedia_alexa"]
    assert receipt["advisory_actions"] == [
        {
            "component_key": "mymedia_alexa",
            "component_label": "My Media for Alexa",
            "action": "wait_for_mymedia_library_scan",
            "reason": "mymedia_library_scan_in_progress",
            "href": PUBLIC_MYMEDIA_WATCH_HREF,
            "label": "Open Watch Folders",
            "method": "get",
        }
    ]
    assert receipt["attention_component_keys"] == ["pushbullet", "whatsapp_pairing"]
    assert receipt["blocked_component_keys"] == ["whatsapp_pairing"]
    assert receipt["effective_component_keys"] == [
        "telegram",
        "google_workspace_oauth",
        "pushbullet",
        "whatsapp_pairing",
        "teable_recovery",
        "mymedia_alexa",
    ]
    assert receipt["next_action_component_keys"] == ["pushbullet", "whatsapp_pairing"]


def test_build_receipt_preserves_steering_and_supplemental_split_from_live_probe(
    monkeypatch, tmp_path: Path
) -> None:
    materialize = _load(MATERIALIZE, "materialize_ea_operator_readiness_split")
    verify = _load(VERIFY, "verify_ea_operator_readiness_split")
    payload = {
        "observed_at": "2026-07-06T04:50:56Z",
        "probe_ok": True,
        "ready": False,
        "status": "ready_with_actions",
        "source": "/docker/EA/scripts/ea_live_ops.py",
        "attention_required_count": 1,
        "blocked_count": 1,
        "probe_failed_count": 0,
        "supplemental_attention_count": 2,
        "supplemental_blocked_count": 1,
        "supplemental_probe_failed_count": 0,
        "steering_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "components": [
            {
                "key": "telegram",
                "label": "Telegram operator delivery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "source": "/docker/EA/app/services/telegram_delivery.py",
            },
            {
                "key": "google_workspace_oauth",
                "label": "Google Workspace OAuth",
                "probe_ok": True,
                "ready": False,
                "status": "ready_retry_required",
                "reason": "oauth_retry_or_account_selection_required",
                "next_action": "retry_full_workspace_auth_with_approved_account",
                "next_action_href": "/integrations/google",
                "next_action_label": "Retry Google auth",
                "next_action_method": "get",
                "source": "scripts.materialize_google_workspace_oauth_readiness.py",
            },
            {
                "key": "pushbullet",
                "label": "Pushbullet operator delivery",
                "probe_ok": True,
                "ready": False,
                "status": "blocked_setup_required",
                "reason": "pushbullet_token_missing:elisabeth",
                "next_action": "create_missing_pushbullet_access_tokens",
                "next_action_href": "https://www.pushbullet.com/#settings/account",
                "next_action_label": "Open Pushbullet account settings",
                "next_action_method": "get",
                "source": "scripts/materialize_pushbullet_delivery_readiness.py",
            },
            {
                "key": "whatsapp",
                "label": "WhatsApp Web action processor",
                "probe_ok": True,
                "ready": False,
                "status": "blocked",
                "reason": "sidecar_not_ready",
                "next_action": "scan_whatsapp_web_qr",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
            },
            {
                "key": "whatsapp_pairing",
                "label": "WhatsApp Web pairing recovery",
                "probe_ok": True,
                "ready": False,
                "status": "available",
                "reason": "",
                "next_action": "scan_whatsapp_web_qr",
                "next_action_href": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "next_action_label": "Open WhatsApp pairing",
                "next_action_method": "get",
                "source": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
            },
            {
                "key": "teable_recovery",
                "label": "Teable env recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
            },
            {
                "key": "mymedia_alexa",
                "label": "My Media for Alexa",
                "probe_ok": True,
                "ready": True,
                "status": "ready_library_scan_in_progress",
                "reason": "mymedia_library_scan_in_progress",
                "next_action": "wait_for_mymedia_library_scan",
                "next_action_href": "http://127.0.0.1:52051/index.html#!/tables",
                "next_action_label": "Open Watch Folders",
                "next_action_method": "get",
                "source": "file:///docker/EA/scripts/probe_mymedia_alexa.py",
            },
        ],
        "next_actions": [
            {
                "component_key": "google_workspace_oauth",
                "component_label": "Google Workspace OAuth",
                "action": "retry_full_workspace_auth_with_approved_account",
                "reason": "oauth_retry_or_account_selection_required",
                "href": "/integrations/google",
                "label": "Retry Google auth",
                "method": "get",
            }
        ],
        "supplemental_attention_component_keys": ["pushbullet", "whatsapp_pairing"],
        "supplemental_blocked_component_keys": ["whatsapp_pairing"],
        "supplemental_probe_failed_component_keys": [],
        "supplemental_next_actions": [
            {
                "component_key": "pushbullet",
                "component_label": "Pushbullet operator delivery",
                "action": "create_missing_pushbullet_access_tokens",
                "reason": "pushbullet_token_missing:elisabeth",
                "href": "https://www.pushbullet.com/#settings/account",
                "label": "Open Pushbullet account settings",
                "method": "get",
            },
            {
                "component_key": "whatsapp_pairing",
                "component_label": "WhatsApp Web pairing recovery",
                "action": "scan_whatsapp_web_qr",
                "reason": "",
                "href": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "label": "Open WhatsApp pairing",
                "method": "get",
            },
        ],
    }
    monkeypatch.setattr(materialize, "_run_probe", lambda timeout_seconds: (0, payload, json.dumps(payload), ""))

    receipt = materialize.build_receipt(timeout_seconds=5.0)

    assert receipt["runtime_status"] == "blocked"
    assert receipt["attention_required_count"] == 1
    assert receipt["blocked_count"] == 1
    assert receipt["attention_component_keys"] == ["google_workspace_oauth"]
    assert receipt["blocked_component_keys"] == ["google_workspace_oauth"]
    assert receipt["next_action_component_keys"] == ["google_workspace_oauth"]
    assert receipt["supplemental_attention_component_keys"] == ["pushbullet", "whatsapp_pairing"]
    assert receipt["supplemental_blocked_component_keys"] == ["whatsapp_pairing"]
    assert receipt["supplemental_next_action_component_keys"] == ["pushbullet", "whatsapp_pairing"]
    assert receipt["blocking_findings"] == ["blocked:google_workspace_oauth:ready_retry_required"]
    assert receipt["advisory_findings"] == []
    assert receipt["advisory_action_component_keys"] == ["mymedia_alexa"]
    assert receipt["effective_component_keys"] == [
        "telegram",
        "google_workspace_oauth",
        "pushbullet",
        "whatsapp_pairing",
        "teable_recovery",
        "mymedia_alexa",
    ]
    assert receipt["components"][4]["next_action_href"] == PUBLIC_PAIRING_HREF
    assert receipt["components"][6]["next_action_href"] == PUBLIC_MYMEDIA_WATCH_HREF

    receipt_path = tmp_path / "ea-operator-readiness-split.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    verified, passed = verify.verify_receipt(receipt_path)

    assert passed is True
    assert verified["status"] == "pass"
    assert verified["runtime_status"] == "blocked"


def test_verify_receipt_passes_when_required_components_present(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_ea_operator_readiness")
    receipt_path = tmp_path / "EA_OPERATOR_READINESS.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-04T20:33:27Z",
        "updated_at": "2026-07-04T20:33:27Z",
        "observed_at": "2026-07-04T20:33:27Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "ready_with_actions",
        "runtime_status": "degraded",
        "runtime_ready": False,
        "source": "script:ea_live_ops.py",
        "source_runtime": "ea_live_ops.bridge",
        "probe_ok": True,
        "secret_leak_detected": False,
        "operator_ready": False,
        "operator_status": "ready_with_actions",
        "blocking_count": 0,
        "advisory_count": 1,
        "attention_required_count": 1,
        "blocked_count": 0,
        "probe_failed_count": 0,
        "component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "effective_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "ready_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "attention_component_keys": ["pushbullet"],
        "blocked_component_keys": [],
        "probe_failed_component_keys": [],
        "blocking_findings": [],
        "advisory_findings": ["attention:pushbullet:blocked_setup_required"],
        "next_action_component_keys": ["pushbullet"],
        "advisory_action_component_keys": ["mymedia_alexa"],
        "components": [
            {
                "key": "telegram",
                "label": "Telegram operator delivery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "google_workspace_oauth",
                "label": "Google Workspace OAuth",
                "probe_ok": True,
                "ready": True,
                "status": "pass",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "source": "script:materialize_google_workspace_oauth_readiness.py",
                "details": {},
            },
            {
                "key": "pushbullet",
                "label": "Pushbullet operator delivery",
                "probe_ok": True,
                "ready": False,
                "status": "blocked_setup_required",
                "reason": "pushbullet_token_missing:elisabeth",
                "next_action": "create_missing_pushbullet_access_tokens",
                "next_action_href": "https://www.pushbullet.com/#settings/account",
                "next_action_label": "Open Pushbullet account settings",
                "next_action_method": "get",
                "source": "script:materialize_pushbullet_delivery_readiness.py",
                "details": {},
            },
            {
                "key": "whatsapp",
                "label": "WhatsApp Web action processor",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "whatsapp_pairing",
                "label": "WhatsApp Web pairing recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "teable_recovery",
                "label": "Teable env recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "mymedia_alexa",
                "label": "My Media for Alexa",
                "probe_ok": True,
                "ready": True,
                "status": "ready_library_scan_in_progress",
                "reason": "mymedia_library_scan_in_progress",
                "next_action": "wait_for_mymedia_library_scan",
                "next_action_href": PUBLIC_MYMEDIA_WATCH_HREF,
                "next_action_label": "Open Watch Folders",
                "next_action_method": "get",
                "details": {},
            },
        ],
        "next_actions": [
            {
                "component_key": "pushbullet",
                "component_label": "Pushbullet operator delivery",
                "action": "create_missing_pushbullet_access_tokens",
                "reason": "pushbullet_token_missing",
                "href": "https://www.pushbullet.com/#settings/account",
                "label": "Open Pushbullet account settings",
                "method": "get",
            }
        ],
        "advisory_actions": [
            {
                "component_key": "mymedia_alexa",
                "component_label": "My Media for Alexa",
                "action": "wait_for_mymedia_library_scan",
                "reason": "mymedia_library_scan_in_progress",
                "href": PUBLIC_MYMEDIA_WATCH_HREF,
                "label": "Open Watch Folders",
                "method": "get",
            }
        ],
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is True
    assert verified["status"] == "pass"
    assert verified["structural_status"] == "pass"
    assert verified["effective_status"] == "ready_with_actions"
    assert verified["runtime_status"] == "degraded"
    assert verified["runtime_ready"] is False
    assert verified["operator_status"] == "ready_with_actions"


def test_verify_receipt_derives_runtime_fields_for_legacy_receipt(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_ea_operator_readiness_legacy_runtime")
    receipt_path = tmp_path / "EA_OPERATOR_READINESS.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-04T20:33:27Z",
        "updated_at": "2026-07-04T20:33:27Z",
        "observed_at": "2026-07-04T20:33:27Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "ready_with_actions",
        "source": "script:ea_live_ops.py",
        "source_runtime": "ea_live_ops.bridge",
        "probe_ok": True,
        "secret_leak_detected": False,
        "operator_ready": False,
        "operator_status": "ready_with_actions",
        "attention_required_count": 1,
        "blocked_count": 0,
        "probe_failed_count": 0,
        "component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "effective_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "ready_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "attention_component_keys": ["pushbullet"],
        "blocked_component_keys": [],
        "probe_failed_component_keys": [],
        "next_action_component_keys": ["pushbullet"],
        "advisory_action_component_keys": ["mymedia_alexa"],
        "components": [
            {
                "key": "telegram",
                "label": "Telegram operator delivery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "google_workspace_oauth",
                "label": "Google Workspace OAuth",
                "probe_ok": True,
                "ready": True,
                "status": "pass",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "source": "script:materialize_google_workspace_oauth_readiness.py",
                "details": {},
            },
            {
                "key": "pushbullet",
                "label": "Pushbullet operator delivery",
                "probe_ok": True,
                "ready": False,
                "status": "blocked_setup_required",
                "reason": "pushbullet_token_missing:elisabeth",
                "next_action": "create_missing_pushbullet_access_tokens",
                "next_action_href": "https://www.pushbullet.com/#settings/account",
                "next_action_label": "Open Pushbullet account settings",
                "next_action_method": "get",
                "source": "script:materialize_pushbullet_delivery_readiness.py",
                "details": {},
            },
            {
                "key": "whatsapp",
                "label": "WhatsApp Web action processor",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "whatsapp_pairing",
                "label": "WhatsApp Web pairing recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "teable_recovery",
                "label": "Teable env recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "mymedia_alexa",
                "label": "My Media for Alexa",
                "probe_ok": True,
                "ready": True,
                "status": "ready_library_scan_in_progress",
                "reason": "mymedia_library_scan_in_progress",
                "next_action": "wait_for_mymedia_library_scan",
                "next_action_href": PUBLIC_MYMEDIA_WATCH_HREF,
                "next_action_label": "Open Watch Folders",
                "next_action_method": "get",
                "details": {},
            },
        ],
        "next_actions": [
            {
                "component_key": "pushbullet",
                "component_label": "Pushbullet operator delivery",
                "action": "create_missing_pushbullet_access_tokens",
                "reason": "pushbullet_token_missing",
                "href": "https://www.pushbullet.com/#settings/account",
                "label": "Open Pushbullet account settings",
                "method": "get",
            }
        ],
        "advisory_actions": [
            {
                "component_key": "mymedia_alexa",
                "component_label": "My Media for Alexa",
                "action": "wait_for_mymedia_library_scan",
                "reason": "mymedia_library_scan_in_progress",
                "href": PUBLIC_MYMEDIA_WATCH_HREF,
                "label": "Open Watch Folders",
                "method": "get",
            }
        ],
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is True
    assert verified["status"] == "pass"
    assert verified["runtime_status"] == "degraded"
    assert verified["runtime_ready"] is False
    assert verified["blocking_count"] == 0
    assert verified["advisory_count"] == 1


def test_build_receipt_suppresses_duplicate_whatsapp_qr_blocker(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_ea_operator_readiness_qr")
    payload = {
        "observed_at": "2026-07-04T20:00:03Z",
        "probe_ok": True,
        "ready": False,
        "status": "ready_with_actions",
        "attention_required_count": 1,
        "blocked_count": 1,
        "probe_failed_count": 0,
        "component_count": 3,
        "components": [
            {
                "key": "whatsapp",
                "label": "WhatsApp Web action processor",
                "probe_ok": True,
                "ready": False,
                "status": "blocked",
                "reason": "sidecar_not_ready",
                "next_action": "scan_whatsapp_web_qr",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "whatsapp_pairing",
                "label": "WhatsApp Web pairing recovery",
                "probe_ok": True,
                "ready": False,
                "status": "available",
                "reason": "",
                "next_action": "scan_whatsapp_web_qr",
                "next_action_href": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "next_action_label": "Open WhatsApp pairing",
                "next_action_method": "get",
                "details": {},
            },
            {
                "key": "telegram",
                "label": "Telegram operator delivery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
        ],
        "next_actions": [
            {
                "component_key": "whatsapp_pairing",
                "component_label": "WhatsApp Web pairing recovery",
                "action": "scan_whatsapp_web_qr",
                "reason": "",
                "href": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "label": "Open WhatsApp pairing",
                "method": "get",
            }
        ],
    }
    monkeypatch.setattr(module, "_run_probe", lambda timeout_seconds: (0, payload, json.dumps(payload), ""))

    receipt = module.build_receipt(timeout_seconds=5.0)

    assert receipt["updated_at"]
    assert receipt["effective_component_keys"] == ["whatsapp_pairing", "telegram"]
    assert receipt["blocked_component_keys"] == ["whatsapp_pairing"]
    assert receipt["attention_component_keys"] == ["whatsapp_pairing"]
    assert receipt["next_action_component_keys"] == ["whatsapp_pairing"]
    assert receipt["advisory_action_component_keys"] == []
    assert receipt["components"][0]["next_action_href"] == ""
    assert receipt["components"][1]["next_action_href"] == PUBLIC_PAIRING_HREF
    assert receipt["next_actions"][0]["href"] == PUBLIC_PAIRING_HREF
    assert "tibor-wa-web" not in json.dumps(receipt)


def test_verify_receipt_fails_when_counts_and_actions_are_stale(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_ea_operator_readiness_stale")
    receipt_path = tmp_path / "EA_OPERATOR_READINESS.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-04T20:00:03Z",
        "updated_at": "2026-07-04T20:00:03Z",
        "observed_at": "2026-07-04T20:00:03Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "ready_with_actions",
        "runtime_status": "blocked",
        "runtime_ready": False,
        "source": "script:ea_live_ops.py",
        "source_runtime": "ea_live_ops.bridge",
        "probe_ok": True,
        "secret_leak_detected": False,
        "operator_ready": False,
        "operator_status": "ready_with_actions",
        "blocking_count": 5,
        "advisory_count": 0,
        "attention_required_count": 5,
        "blocked_count": 5,
        "probe_failed_count": 0,
        "component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "effective_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "ready_component_keys": ["telegram", "teable_recovery", "mymedia_alexa"],
        "attention_component_keys": [
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "mymedia_alexa",
        ],
        "blocked_component_keys": [
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "mymedia_alexa",
        ],
        "probe_failed_component_keys": [],
        "blocking_findings": [
            "blocked:google_workspace_oauth:ready_retry_required",
            "attention:pushbullet:blocked_setup_required",
        ],
        "advisory_findings": [],
        "next_action_component_keys": [
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "mymedia_alexa",
        ],
        "advisory_action_component_keys": ["google_workspace_oauth"],
        "components": [
            {
                "key": "telegram",
                "label": "Telegram operator delivery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "source": "/docker/EA/app/services/telegram_delivery.py",
                "details": {},
            },
            {
                "key": "google_workspace_oauth",
                "label": "Google Workspace OAuth",
                "probe_ok": True,
                "ready": False,
                "status": "ready_retry_required",
                "reason": "oauth_retry_or_account_selection_required",
                "next_action": "retry_full_workspace_auth_with_approved_account",
                "next_action_href": "/integrations/google",
                "next_action_label": "Retry Google auth",
                "next_action_method": "get",
                "details": {},
            },
            {
                "key": "pushbullet",
                "label": "Pushbullet operator delivery",
                "probe_ok": True,
                "ready": False,
                "status": "blocked_setup_required",
                "reason": "pushbullet_token_missing:elisabeth",
                "next_action": "create_missing_pushbullet_access_tokens",
                "next_action_href": "https://www.pushbullet.com/#settings/account",
                "next_action_label": "Open Pushbullet account settings",
                "next_action_method": "get",
                "details": {},
            },
            {
                "key": "whatsapp",
                "label": "WhatsApp Web action processor",
                "probe_ok": True,
                "ready": False,
                "status": "blocked",
                "reason": "sidecar_not_ready",
                "next_action": "scan_whatsapp_web_qr",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "whatsapp_pairing",
                "label": "WhatsApp Web pairing recovery",
                "probe_ok": True,
                "ready": False,
                "status": "available",
                "reason": "",
                "next_action": "scan_whatsapp_web_qr",
                "next_action_href": PUBLIC_PAIRING_HREF,
                "next_action_label": "Open WhatsApp pairing",
                "next_action_method": "get",
                "details": {},
            },
            {
                "key": "teable_recovery",
                "label": "Teable env recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "mymedia_alexa",
                "label": "My Media for Alexa",
                "probe_ok": True,
                "ready": True,
                "status": "ready_library_scan_in_progress",
                "reason": "mymedia_library_scan_in_progress",
                "next_action": "wait_for_mymedia_library_scan",
                "next_action_href": "http://127.0.0.1:52051/index.html#!/tables",
                "next_action_label": "Open Watch Folders",
                "next_action_method": "get",
                "details": {},
            },
        ],
        "next_actions": [
            {
                "component_key": "google_workspace_oauth",
                "component_label": "Google Workspace OAuth",
                "action": "retry_full_workspace_auth_with_approved_account",
                "reason": "oauth_retry_or_account_selection_required",
                "href": "/integrations/google",
                "label": "Retry Google auth",
                "method": "get",
            },
            {
                "component_key": "pushbullet",
                "component_label": "Pushbullet operator delivery",
                "action": "create_missing_pushbullet_access_tokens",
                "reason": "pushbullet_token_missing:elisabeth",
                "href": "https://www.pushbullet.com/#settings/account",
                "label": "Open Pushbullet account settings",
                "method": "get",
            },
            {
                "component_key": "whatsapp",
                "component_label": "WhatsApp Web action processor",
                "action": "scan_whatsapp_web_qr",
                "reason": "sidecar_not_ready",
                "href": "",
                "label": "",
                "method": "",
            },
            {
                "component_key": "whatsapp_pairing",
                "component_label": "WhatsApp Web pairing recovery",
                "action": "scan_whatsapp_web_qr",
                "reason": "",
                "href": PUBLIC_PAIRING_HREF,
                "label": "Open WhatsApp pairing",
                "method": "get",
            },
            {
                "component_key": "mymedia_alexa",
                "component_label": "My Media for Alexa",
                "action": "wait_for_mymedia_library_scan",
                "reason": "mymedia_library_scan_in_progress",
                "href": "http://127.0.0.1:52051/index.html#!/tables",
                "label": "Open Watch Folders",
                "method": "get",
            },
        ],
        "advisory_actions": [
            {
                "component_key": "google_workspace_oauth",
                "component_label": "Google Workspace OAuth",
                "action": "retry_full_workspace_auth_with_approved_account",
                "reason": "oauth_retry_or_account_selection_required",
                "href": "/integrations/google",
                "label": "Retry Google auth",
                "method": "get",
            }
        ],
        "stdout_tail": "returncode=0 observed_at=2026-07-04T20:00:03Z probe_ok=true status=ready_with_actions ready=false runtime_status=blocked runtime_ready=false component_count=7 attention_required_count=5 blocked_count=5 probe_failed_count=0 source=/docker/EA/scripts/ea_live_ops.py",
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is False
    assert "effective_component_keys_mismatch" in verified["failures"]
    assert "attention_required_count_mismatch" in verified["failures"]
    assert "blocked_count_mismatch" in verified["failures"]
    assert "next_actions_mismatch" in verified["failures"]
    assert "advisory_action_component_keys_mismatch" in verified["failures"]
    assert "advisory_actions_mismatch" in verified["failures"]
    assert "unsafe_component_next_action_href:mymedia_alexa" in verified["failures"]
    assert "unsafe_component_source:telegram" in verified["failures"]
    assert "unsafe_next_action_href:mymedia_alexa" in verified["failures"]
    assert "unsafe_stdout_tail_source" in verified["failures"]


def test_verify_receipt_fails_when_structural_and_effective_status_are_missing(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_ea_operator_readiness_status_fields")
    receipt_path = tmp_path / "EA_OPERATOR_READINESS.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-04T20:00:03Z",
        "observed_at": "2026-07-04T20:00:03Z",
        "status": "pass",
        "source": "script:ea_live_ops.py",
        "source_runtime": "ea_live_ops.bridge",
        "probe_ok": True,
        "secret_leak_detected": False,
        "operator_ready": False,
        "operator_status": "ready_with_actions",
        "blocking_count": 0,
        "advisory_count": 0,
        "attention_required_count": 0,
        "blocked_count": 0,
        "probe_failed_count": 0,
        "component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "effective_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "ready_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "attention_component_keys": [],
        "blocked_component_keys": [],
        "probe_failed_component_keys": [],
        "blocking_findings": [],
        "advisory_findings": [],
        "next_action_component_keys": [],
        "components": [],
        "next_actions": [],
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is False
    assert verified["status"] == "fail"
    assert "updated_at_missing" in verified["failures"]
    assert "structural_status_mismatch" in verified["failures"]
    assert "effective_status_mismatch" in verified["failures"]


def test_verify_receipt_fails_structurally_when_receipt_is_missing(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_ea_operator_readiness_missing")
    receipt_path = tmp_path / "EA_OPERATOR_READINESS.generated.json"

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is False
    assert verified["status"] == "fail"
    assert verified["failures"] == ["missing_receipt"]
    assert verified["structural_status"] == "missing"
    assert verified["effective_status"] == "missing"
