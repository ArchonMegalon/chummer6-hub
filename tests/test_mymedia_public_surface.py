from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "materialize_mymedia_public_surface.py"


def _module():
    spec = importlib.util.spec_from_file_location("materialize_mymedia_public_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def passing_probe_payload() -> dict[str, object]:
    return {
        "observed_at": "2026-07-04T20:33:27Z",
        "probe_ok": True,
        "status": "ready_library_scan_in_progress",
        "reason": "mymedia_library_scan_in_progress",
        "connection_status": "connected",
        "container_running": True,
        "library_scan_pending": True,
        "watch_folder_states": ["indexing"],
        "tracks": 12453,
        "public_surface_configured": True,
        "public_surface_ready": True,
        "public_surface_status": "access_protected",
        "public_surface_reason": "",
        "public_surface_scope": "public",
        "public_surface_http_status_code": 302,
        "public_surface_access_protected": True,
        "public_surface_cloudflare_blocked": False,
        "public_surface_redirect_host": "girschele.cloudflareaccess.com",
        "public_surface_next_action": "",
        "public_surface_next_action_href": "https://mymedia.girschele.com",
        "public_surface_next_action_label": "Open public My Media URL",
        "public_surface_next_action_method": "get",
    }


def test_build_receipt_passes_for_access_protected_public_surface(monkeypatch) -> None:
    module = _module()
    payload = passing_probe_payload()
    monkeypatch.setattr(module, "_run_probe", lambda timeout_seconds: (0, payload, '{"status":"ok"}', ""))

    receipt = module.build_receipt(timeout_seconds=5)

    assert receipt["updated_at"]
    assert receipt["status"] == "pass"
    assert receipt["structural_status"] == "pass"
    assert receipt["effective_status"] == "access_protected"
    assert receipt["probe_ok"] is True
    assert receipt["public_surface_ready"] is True
    assert receipt["public_surface_status"] == "access_protected"
    assert receipt["public_surface_url"] == "https://mymedia.girschele.com"
    assert receipt["mymedia_status"] == "ready_library_scan_in_progress"
    assert receipt["stdout_tail"].startswith("returncode=0 ")
    assert "{" not in receipt["stdout_tail"]
    assert receipt["failures"] == []


def test_build_receipt_sanitizes_stdout_source(monkeypatch) -> None:
    module = _module()
    payload = passing_probe_payload()
    payload["source"] = "/docker/EA/scripts/probe_mymedia_alexa.py"
    monkeypatch.setattr(module, "_run_probe", lambda timeout_seconds: (0, payload, '{"status":"ok"}', ""))

    receipt = module.build_receipt(timeout_seconds=5)

    assert receipt["updated_at"]
    assert "source=script:probe_mymedia_alexa.py" in receipt["stdout_tail"]
    assert "/docker/EA" not in receipt["stdout_tail"]


def test_build_receipt_keeps_public_surface_failure_specific(monkeypatch) -> None:
    module = _module()
    payload = passing_probe_payload()
    payload.update(
        {
            "probe_ok": False,
            "public_surface_ready": False,
            "public_surface_status": "blocked_by_cloudflare",
            "public_surface_reason": "mymedia_public_console_blocked_by_cloudflare",
            "public_surface_cloudflare_blocked": True,
            "public_surface_next_action": "repair_mymedia_public_console_route",
        }
    )
    monkeypatch.setattr(module, "_run_probe", lambda timeout_seconds: (1, payload, '{"status":"fail"}', ""))

    receipt = module.build_receipt(timeout_seconds=5)

    assert receipt["updated_at"]
    assert receipt["status"] == "fail"
    assert receipt["structural_status"] == "fail"
    assert receipt["effective_status"] == "blocked_by_cloudflare"
    assert receipt["public_surface_ready"] is False
    assert receipt["public_surface_status"] == "blocked_by_cloudflare"
    assert receipt["stdout_tail"].startswith("returncode=1 ")
    assert "mymedia_public_console_blocked_by_cloudflare" in receipt["failures"]
    assert receipt["nextActions"] == [
        "repair_mymedia_public_console_route label=Open public My Media URL href=https://mymedia.girschele.com"
    ]


def test_build_receipt_detects_secret_leak(monkeypatch) -> None:
    module = _module()
    payload = passing_probe_payload()
    payload["access_token"] = "leak"
    monkeypatch.setattr(module, "_run_probe", lambda timeout_seconds: (0, payload, '{"status":"ok"}', ""))

    receipt = module.build_receipt(timeout_seconds=5)

    assert receipt["updated_at"]
    assert receipt["status"] == "fail"
    assert receipt["structural_status"] == "fail"
    assert receipt["effective_status"] == "access_protected"
    assert receipt["secret_leak_detected"] is True
    assert "secret_leak_detected" in receipt["failures"]


def test_build_receipt_sanitizes_loopback_next_action_href(monkeypatch) -> None:
    module = _module()
    payload = passing_probe_payload()
    payload.update(
        {
            "probe_ok": False,
            "public_surface_ready": False,
            "public_surface_status": "blocked_by_cloudflare",
            "public_surface_reason": "mymedia_public_console_blocked_by_cloudflare",
            "public_surface_cloudflare_blocked": True,
            "public_surface_next_action": "open_local_watch_folders_console",
            "public_surface_next_action_href": "http://127.0.0.1:52051/index.html#!/tables",
            "public_surface_next_action_label": "Open Watch Folders",
        }
    )
    monkeypatch.setattr(module, "_run_probe", lambda timeout_seconds: (1, payload, '{"status":"fail"}', ""))

    receipt = module.build_receipt(timeout_seconds=5)

    assert receipt["updated_at"]
    assert receipt["public_surface_url"] == "host-local:///index.html#!/tables"
    assert receipt["next_action_href"] == "host-local:///index.html#!/tables"
    assert receipt["nextActions"] == [
        "open_local_watch_folders_console label=Open Watch Folders href=host-local:///index.html#!/tables"
    ]
