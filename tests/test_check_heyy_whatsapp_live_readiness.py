from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_heyy_whatsapp_live_readiness.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_heyy_whatsapp_live_readiness", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_report_blocks_when_internal_api_is_unreachable():
    module = load_module()
    values = {
        "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED": "true",
        "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL": "https://ea.test",
        "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN": "ea-token",
        "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID": "principal-1",
        "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID": "whatsapp-binding",
        "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL": "https://chat.test",
    }

    report = module.build_report(values, "+436647916419", {"status": "unreachable", "reason": "TimeoutError", "detail": "timed out"})

    assert report["status"] == "blocked"
    assert "internal_api_unreachable" in report["blockers"]
    assert report["providers"]["ea_ready"] is True
    assert report["drafting"]["ready"] is True


def test_build_report_blocks_when_draft_generation_is_unconfigured():
    module = load_module()
    values = {
        "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED": "true",
        "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL": "https://ea.test",
        "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN": "ea-token",
        "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID": "principal-1",
        "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID": "whatsapp-binding",
        "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL": "https://code.girschele.com",
        "ANSWERLY_PROVIDER_VERIFICATION_STATE": "unverified",
    }

    report = module.build_report(values, "+436647916419", {"status": "reachable", "conversation_count": 1})

    assert report["status"] == "blocked"
    assert "draft_generation_unconfigured" in report["blockers"]
    assert "answerly_upstream_auth_missing" in report["blockers"]
    assert report["providers"]["ea_ready"] is True
    assert report["drafting"]["chat_route"] == "unconfigured"
    assert report["drafting"]["chat_route_candidate"] == "answerly_upstream"
    assert report["drafting"]["configured_chat_base_url_present"] is True
    assert report["drafting"]["answerly_upstream_base_url_present"] is True
    assert report["drafting"]["blocking_reason"] == "answerly_upstream_auth_missing"
    assert report["drafting"]["answerly_verification_state"] == "unverified"
    assert report["drafting"]["ready"] is False


def test_probe_internal_api_reports_reachable(monkeypatch):
    module = load_module()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'[{"conversationId":"conv-1"}]'

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda request, timeout: FakeResponse())

    report = module.probe_internal_api("http://127.0.0.1:8091", "token")

    assert report == {"status": "reachable", "conversation_count": 1}


def test_main_reports_blocked_when_internal_api_token_missing(monkeypatch, capsys, tmp_path):
    module = load_module()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED=true",
                "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL=https://ea.test",
                "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN=ea-token",
                "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID=principal-1",
                "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID=whatsapp-binding",
                "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL=https://chat.test",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_heyy_whatsapp_live_readiness.py",
            "--env-file",
            str(env_file),
            "--skip-container",
        ],
    )

    exit_code = module.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["internal_api"]["reason"] == "internal_api_token_missing"
    assert "internal_api_unreachable" in payload["blockers"]
