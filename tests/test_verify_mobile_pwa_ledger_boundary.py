from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_mobile_pwa_ledger_boundary.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_mobile_pwa_ledger_boundary", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_source_contract_passes_for_current_mobile_pwa_boundary() -> None:
    module = load_module()

    result = module.verify_source()

    assert result["status"] == "pass"
    assert result["required"]["controller_private_no_store"] is True
    assert result["required"]["controller_vary_cookie_authorization"] is True
    assert result["required"]["controller_world_not_followed_hides_turn"] is True
    assert result["required"]["view_install_only_no_ledger"] is True
    assert result["required"]["playwright_install_shell_boundary"] is True
    assert result["required"]["service_worker_non_cacheable"] is True


def test_opt_in_required_payload_requires_account_route() -> None:
    module = load_module()

    failures = module.verify_payload(
        {
            "mode": "mobile_pwa_living_world",
            "status": "opt_in_required",
            "updates_route": "/mobile/pwa/ledger.json",
            "opt_in_route": "/account",
        }
    )

    assert failures == []


def test_world_not_followed_payload_must_not_leak_live_detail() -> None:
    module = load_module()

    failures = module.verify_payload(
        {
            "mode": "mobile_pwa_living_world",
            "status": "world_not_followed",
            "updates_route": "/mobile/pwa/ledger.json",
            "world": {"world_turn": 42},
            "continuity": {"turn": 42},
            "hot_district": {"name": "Redmond"},
            "move_district": {"name": "Downtown"},
            "tracker": {
                "turn_route": "/ledger/turns/42",
                "newsreel_route": "/ledger/turns/42/newsreel.json",
            },
        }
    )

    assert "world_not_followed payload leaks world_turn" in failures
    assert "world_not_followed payload leaks continuity" in failures
    assert "world_not_followed payload leaks hot_district" in failures
    assert "world_not_followed payload leaks move_district" in failures
    assert "world_not_followed payload leaks turn_route" in failures
    assert "world_not_followed payload leaks newsreel_route" in failures


def test_live_receipt_requires_private_no_store_and_vary_headers(monkeypatch) -> None:
    module = load_module()

    def fake_fetch(base_url: str, timeout_seconds: float):
        return (
            200,
            {
                "cache-control": "private, no-store, no-cache, max-age=0",
                "pragma": "no-cache",
                "expires": "0",
                "vary": "Cookie, Authorization",
            },
            '{"mode":"mobile_pwa_living_world","status":"opt_in_required","updates_route":"/mobile/pwa/ledger.json","opt_in_route":"/account"}',
            "https://chummer.run/mobile/pwa/ledger.json",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_live("https://chummer.run", 1)

    assert result["status"] == "pass"
    assert result["payload_status"] == "opt_in_required"
    assert result["cache_control"] == "private, no-store, no-cache, max-age=0"
    assert result["vary"] == "Cookie, Authorization"


def test_live_receipt_fails_without_private_boundary_headers(monkeypatch) -> None:
    module = load_module()

    def fake_fetch(base_url: str, timeout_seconds: float):
        return (
            200,
            {"cache-control": "public, max-age=3600", "vary": "Accept-Encoding"},
            '{"mode":"mobile_pwa_living_world","status":"opt_in_required","updates_route":"/mobile/pwa/ledger.json","opt_in_route":"/account"}',
            "https://chummer.run/mobile/pwa/ledger.json",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_live("https://chummer.run", 1)

    assert result["status"] == "fail"
    assert "cache-control does not include private no-store" in result["failures"]
    assert "pragma is not no-cache" in result["failures"]
    assert "vary does not include Cookie and Authorization" in result["failures"]
