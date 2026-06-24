from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "send_heyy_whatsapp_live_test.py"


def load_module():
    spec = importlib.util.spec_from_file_location("send_heyy_whatsapp_live_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_probe_internal_api_returns_reachable_summary(monkeypatch):
    module = load_module()

    def fake_get_json(url: str, token: str):
        assert url.endswith("/api/internal/heyy/scam-chat/conversations?take=1")
        assert token == "internal-token"
        return [{"conversationId": "conv-1"}]

    monkeypatch.setattr(module, "get_json", fake_get_json)

    result = module.probe_internal_api("http://127.0.0.1:8091", "internal-token")

    assert result == {"status": "reachable", "conversationCount": 1}


def test_main_returns_blocked_json_when_internal_api_probe_times_out(monkeypatch, capsys, tmp_path):
    module = load_module()
    env_file = tmp_path / ".env"
    env_file.write_text("FLEET_INTERNAL_API_TOKEN=test-token\n", encoding="utf-8")

    monkeypatch.setattr(module, "run_readiness", lambda recipient, include_ea_db: (0, {"status": "ready"}))

    def fake_probe_internal_api(base_url: str, token: str):
        raise TimeoutError("timed out")

    monkeypatch.setattr(module, "probe_internal_api", fake_probe_internal_api)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_heyy_whatsapp_live_test.py",
            "--recipient",
            "+436647916419",
            "--dry-run",
            "--env-file",
            str(env_file),
        ],
    )

    exit_code = module.main()

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert captured["status"] == "blocked"
    assert captured["stage"] == "internal_api_probe"
    assert captured["apiBaseUrl"] == "http://127.0.0.1:8091"
    assert captured["failureReason"].startswith("TimeoutError:")


def test_main_returns_failed_json_when_ingest_post_fails(monkeypatch, capsys, tmp_path):
    module = load_module()
    env_file = tmp_path / ".env"
    env_file.write_text("FLEET_INTERNAL_API_TOKEN=test-token\n", encoding="utf-8")

    monkeypatch.setattr(module, "run_readiness", lambda recipient, include_ea_db: (0, {"status": "ready"}))
    monkeypatch.setattr(module, "probe_internal_api", lambda base_url, token: {"status": "reachable", "conversationCount": 0})

    def fake_post_json(url: str, token: str, payload: dict[str, object]):
        raise RuntimeError("http_503:upstream timeout")

    monkeypatch.setattr(module, "post_json", fake_post_json)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_heyy_whatsapp_live_test.py",
            "--recipient",
            "+436647916419",
            "--dry-run",
            "--env-file",
            str(env_file),
        ],
    )

    exit_code = module.main()

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert captured["status"] == "failed"
    assert captured["stage"] == "ingest"
    assert captured["internalApi"]["status"] == "reachable"
    assert captured["failureReason"].startswith("RuntimeError:http_503:")


def test_main_blocks_when_live_draft_falls_back(monkeypatch, capsys, tmp_path):
    module = load_module()
    env_file = tmp_path / ".env"
    env_file.write_text("FLEET_INTERNAL_API_TOKEN=test-token\n", encoding="utf-8")

    monkeypatch.setattr(module, "run_readiness", lambda recipient, include_ea_db: (0, {"status": "ready"}))
    monkeypatch.setattr(module, "probe_internal_api", lambda base_url, token: {"status": "reachable", "conversationCount": 0})

    def fake_post_json(url: str, token: str, payload: dict[str, object]):
        if url.endswith("/messages"):
            return {
                "conversationId": "conv-1",
                "status": "generated_fallback",
                "failureReason": "ea_chat_unconfigured",
                "personaId": "empathetic_slow_typing_old_lady",
                "mode": "draft_only",
                "manualApprovalRequired": True,
                "autoSendAllowed": False,
            }
        raise AssertionError("approval should not be called when draft generation fell back")

    monkeypatch.setattr(module, "post_json", fake_post_json)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_heyy_whatsapp_live_test.py",
            "--recipient",
            "+436647916419",
            "--dry-run",
            "--env-file",
            str(env_file),
        ],
    )

    exit_code = module.main()

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert captured["status"] == "blocked"
    assert captured["stage"] == "draft_generation"
    assert captured["conversation"]["status"] == "generated_fallback"
    assert captured["failureReason"] == "ea_chat_unconfigured"
