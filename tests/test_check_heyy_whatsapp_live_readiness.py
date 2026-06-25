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


def test_build_report_treats_configured_blocked_ea_host_as_not_ready():
    module = load_module()
    values = {
        "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED": "true",
        "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL": "http://local-ea-mock:8090",
        "CHUMMER_HEYY_SCAM_CHAT_BLOCKED_EA_DELIVERY_HOSTS": "support-progress-mock;local-ea-mock|127.0.0.1",
        "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN": "ea-token",
        "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID": "principal-1",
        "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID": "whatsapp-binding",
        "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL": "https://chat.test",
    }

    report = module.build_report(values, "+436647916419", {"status": "reachable", "conversation_count": 1})

    assert report["status"] == "blocked"
    assert "live_provider_unconfigured" in report["blockers"]
    assert report["providers"]["ea_ready"] is False
    assert report["config"]["ea_base_url_host"] == "local-ea-mock"
    assert report["config"]["ea_base_url_blocked"] is True
    assert report["config"]["blocked_ea_delivery_hosts"] == ["127.0.0.1", "::1", "local-ea-mock", "localhost", "support-progress-mock"]


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


def test_probe_whatsapp_web_sidecar_includes_safe_qr_metadata(monkeypatch):
    module = load_module()
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(url, timeout):
        calls.append(str(url))
        if str(url).endswith("/healthz"):
            return FakeResponse({"ok": True, "session_ref": "tibor-wa-web", "status": "qr_required"})
        return FakeResponse(
            {
                "last_qr_at": "2026-06-25T12:00:00Z",
                "ok": True,
                "qr": "secret-qr-payload",
                "qr_present": True,
                "qr_required": True,
                "ready": False,
                "session_ref": "tibor-wa-web",
                "status": "qr_required",
            }
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(module, "datetime", type("FixedDateTime", (), {"now": staticmethod(lambda _tz: module.datetime.fromisoformat("2026-06-25T12:01:30+00:00")), "fromisoformat": module.datetime.fromisoformat}))

    report = module.probe_whatsapp_web_sidecar("http://127.0.0.1:8098", "default-wa-web")

    assert calls == ["http://127.0.0.1:8098/healthz", "http://127.0.0.1:8098/sessions/tibor-wa-web/qr"]
    assert report["session_ref"] == "tibor-wa-web"
    assert report["qr"]["qr_present"] is True
    assert report["qr"]["qr_required"] is True
    assert report["qr"]["qr_age_seconds"] == 90
    assert report["qr"]["pair_url"] == "http://127.0.0.1:8098/sessions/tibor-wa-web/pair"
    assert report["qr"]["qr_svg_url"] == "http://127.0.0.1:8098/sessions/tibor-wa-web/qr.svg"
    assert report["qr"]["raw_qr_included"] is False
    assert "qr" not in report["qr"]


def test_probe_whatsapp_web_qr_metadata_omits_pair_urls_without_qr(monkeypatch):
    module = load_module()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "last_qr_at": "",
                    "ok": True,
                    "qr_present": False,
                    "qr_required": False,
                    "ready": True,
                    "session_ref": "tibor-wa-web",
                    "status": "ready",
                }
            ).encode("utf-8")

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda url, timeout: FakeResponse())

    report = module.probe_whatsapp_web_qr_metadata("http://127.0.0.1:8098", "tibor-wa-web")

    assert report["qr_present"] is False
    assert report["pair_url"] == ""
    assert report["qr_svg_url"] == ""
    assert report["raw_qr_included"] is False


def test_probe_whatsapp_web_qr_metadata_reports_auth_failure_without_raw_qr(monkeypatch):
    module = load_module()

    def fake_urlopen(url, timeout):
        raise module.urllib.error.HTTPError(str(url), 401, "Unauthorized", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    report = module.probe_whatsapp_web_qr_metadata("http://127.0.0.1:8098", "tibor-wa-web")

    assert report["status"] == "unavailable"
    assert report["reason"] == "http_401"
    assert report["raw_qr_included"] is False


def test_resolve_whatsapp_web_session_ref_prefers_runtime_config():
    module = load_module()

    assert module.resolve_whatsapp_web_session_ref({"EA_WHATSAPP_WEB_DEFAULT_SESSION_REF": "tibor-wa-web"}, "") == "tibor-wa-web"
    assert module.resolve_whatsapp_web_session_ref({"WA_WEB_SESSION_REF": "sidecar-wa-web"}, "") == "sidecar-wa-web"
    assert module.resolve_whatsapp_web_session_ref({"EA_WHATSAPP_WEB_DEFAULT_SESSION_REF": "tibor-wa-web"}, "manual-wa-web") == "manual-wa-web"


def test_build_report_blocks_when_whatsapp_web_sidecar_is_not_ready():
    module = load_module()
    values = {
        "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED": "true",
        "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL": "https://ea.test",
        "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN": "ea-token",
        "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID": "principal-1",
        "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID": "whatsapp-binding",
        "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL": "https://chat.test",
    }

    report = module.build_report(
        values,
        "+436647916419",
        {"status": "reachable", "conversation_count": 1},
        {"status": "qr_required", "ready": False, "reason": "qr_required", "session_ref": "tibor-wa-web"},
    )

    assert report["status"] == "blocked"
    assert "whatsapp_web_sidecar_not_ready" in report["blockers"]
    assert report["whatsapp_web_sidecar"]["status"] == "qr_required"
    assert report["providers"]["ea_ready"] is True
    assert report["drafting"]["ready"] is True


def test_build_report_includes_operator_next_action_for_qr_required_sidecar():
    module = load_module()
    values = {
        "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED": "true",
        "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL": "https://ea.test",
        "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN": "ea-token",
        "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID": "principal-1",
        "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID": "whatsapp-binding",
        "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL": "https://chat.test",
    }

    report = module.build_report(
        values,
        "+436647916419",
        {"status": "reachable", "conversation_count": 1},
        {
            "status": "qr_required",
            "ready": False,
            "reason": "qr_required",
            "session_ref": "tibor-wa-web",
            "qr": {
                "pair_url": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "qr_present": True,
                "qr_required": True,
                "qr_svg_url": "http://127.0.0.1:8098/sessions/tibor-wa-web/qr.svg",
                "raw_qr_included": False,
                "session_ref": "tibor-wa-web",
            },
        },
    )

    assert report["operator_next_action"] == {
        "status": "operator_required",
        "reason": "whatsapp_web_qr_scan_required",
        "pair_url": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
        "qr_svg_url": "http://127.0.0.1:8098/sessions/tibor-wa-web/qr.svg",
        "session_ref": "tibor-wa-web",
        "after_scan": "rerun_heyy_whatsapp_live_readiness",
        "raw_qr_included": False,
    }


def test_build_report_omits_operator_next_action_when_sidecar_ready():
    module = load_module()
    values = {
        "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED": "true",
        "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL": "https://ea.test",
        "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN": "ea-token",
        "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID": "principal-1",
        "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID": "whatsapp-binding",
        "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL": "https://chat.test",
    }

    report = module.build_report(
        values,
        "+436647916419",
        {"status": "reachable", "conversation_count": 1},
        {"status": "ready", "ready": True, "session_ref": "tibor-wa-web"},
    )

    assert report["operator_next_action"] == {"status": "not_needed", "reason": "whatsapp_web_sidecar_ready"}


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


def test_main_reports_resolved_whatsapp_web_probe_source(monkeypatch, capsys, tmp_path):
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
                "CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN=internal-token",
                "EA_WHATSAPP_WEB_DEFAULT_SESSION_REF=tibor-wa-web",
            ]
        ),
        encoding="utf-8",
    )
    captured_probe: dict[str, str] = {}

    def fake_probe_sidecar(base_url: str, session_ref: str):
        captured_probe["base_url"] = base_url
        captured_probe["session_ref"] = session_ref
        return {"status": "qr_required", "ready": False, "reason": "qr_required", "session_ref": session_ref}

    monkeypatch.setattr(module, "probe_internal_api", lambda _base_url, _token: {"status": "reachable", "conversation_count": 1})
    monkeypatch.setattr(module, "probe_whatsapp_web_sidecar", fake_probe_sidecar)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_heyy_whatsapp_live_readiness.py",
            "--env-file",
            str(env_file),
            "--skip-container",
            "--include-whatsapp-web-sidecar",
            "--whatsapp-web-sidecar-base-url",
            "http://127.0.0.1:8098",
        ],
    )

    exit_code = module.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert captured_probe == {"base_url": "http://127.0.0.1:8098", "session_ref": "tibor-wa-web"}
    assert payload["sources"]["whatsapp_web_sidecar_base_url"] == "http://127.0.0.1:8098"
    assert payload["sources"]["whatsapp_web_session_ref"] == "tibor-wa-web"
    assert payload["sources"]["whatsapp_web_requested_session_ref"] == "tibor-wa-web"
    assert payload["sources"]["whatsapp_web_reported_session_ref"] == "tibor-wa-web"
    assert payload["whatsapp_web_sidecar"]["session_ref"] == "tibor-wa-web"


def test_main_reports_whatsapp_web_requested_and_reported_session_refs(monkeypatch, capsys, tmp_path):
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
                "CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN=internal-token",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "probe_internal_api", lambda _base_url, _token: {"status": "reachable", "conversation_count": 1})
    monkeypatch.setattr(
        module,
        "probe_whatsapp_web_sidecar",
        lambda _base_url, _session_ref: {
            "status": "qr_required",
            "ready": False,
            "reason": "qr_required",
            "session_ref": "tibor-wa-web",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_heyy_whatsapp_live_readiness.py",
            "--env-file",
            str(env_file),
            "--skip-container",
            "--include-whatsapp-web-sidecar",
        ],
    )

    exit_code = module.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["sources"]["whatsapp_web_session_ref"] == "tibor-wa-web"
    assert payload["sources"]["whatsapp_web_requested_session_ref"] == "default-wa-web"
    assert payload["sources"]["whatsapp_web_reported_session_ref"] == "tibor-wa-web"


def test_main_reports_post_scan_commands_for_qr_required_sidecar(monkeypatch, capsys, tmp_path):
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
                "CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN=internal-token",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "probe_internal_api", lambda _base_url, _token: {"status": "reachable", "conversation_count": 1})
    monkeypatch.setattr(
        module,
        "probe_whatsapp_web_sidecar",
        lambda _base_url, _session_ref: {
            "status": "qr_required",
            "ready": False,
            "reason": "qr_required",
            "session_ref": "tibor-wa-web",
            "qr": {
                "pair_url": "http://127.0.0.1:8098/sessions/tibor-wa-web/pair",
                "qr_present": True,
                "qr_required": True,
                "qr_svg_url": "http://127.0.0.1:8098/sessions/tibor-wa-web/qr.svg",
                "raw_qr_included": False,
                "session_ref": "tibor-wa-web",
            },
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_heyy_whatsapp_live_readiness.py",
            "--env-file",
            str(env_file),
            "--skip-container",
            "--include-whatsapp-web-sidecar",
            "--whatsapp-web-sidecar-base-url",
            "http://127.0.0.1:8098",
            "--internal-api-base-url",
            "http://127.0.0.1:8091",
        ],
    )

    exit_code = module.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    action = payload["operator_next_action"]
    assert action["status"] == "operator_required"
    assert action["rerun_readiness_command"] == [
        "python3",
        "scripts/check_heyy_whatsapp_live_readiness.py",
        "--env-file",
        str(env_file),
        "--skip-container",
        "--include-whatsapp-web-sidecar",
        "--whatsapp-web-sidecar-base-url",
        "http://127.0.0.1:8098",
        "--whatsapp-web-session-ref",
        "tibor-wa-web",
        "--internal-api-base-url",
        "http://127.0.0.1:8091",
    ]
    assert action["herta_live_verifier_command"] == [
        "python3",
        "/docker/EA/scripts/verify_whatsapp_web_herta_live_e2e.py",
        "--session-api-base-url",
        "http://127.0.0.1:8098",
        "--session-ref",
        "tibor-wa-web",
    ]
