from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_ready_mobile_handoff_contract.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_ready_mobile_handoff_contract", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_payload() -> dict:
    return {
        "mode": "ready_for_tonight",
        "status": "ready",
        "next_best_screen": "/mobile",
        "pwa_route": "/mobile",
        "continuity_route": "/play/continuity",
        "frontdoor_launch_route": "/mobile/player",
        "playtime_tools": [
            {"id": "inventory"},
            {"id": "health"},
            {"id": "ammo"},
            {"id": "modifiers"},
            {"id": "quick_rolls"},
            {"id": "living_world"},
        ],
        "boundaries": [
            "The mobile shell supports playtime tracking; character building stays before or after the session.",
            "Black Ledger live detail requires account opt-in and followed-world selection.",
            "GM remains final authority for modifiers, dice calls, and table consequences.",
        ],
        "packet_routes": [
            {"roleId": "player", "markdown": "/ready/packet/player.md", "json": "/ready/packet/player.json"},
            {"roleId": "gm", "markdown": "/ready/packet/gm.md", "json": "/ready/packet/gm.json"},
            {"roleId": "organizer", "markdown": "/ready/packet/organizer.md", "json": "/ready/packet/organizer.json"},
        ],
        "role_routes": [
            {
                "role": "Player",
                "mode": "player",
                "route": "/mobile/player",
                "manifest_path": "/manifest.player.webmanifest",
                "manifest_id": "/mobile/player",
                "manifest_start_url": "/mobile/player",
                "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
                "frontdoor_default": True,
            },
            {
                "role": "GameMaster",
                "mode": "gm",
                "route": "/mobile/gm",
                "manifest_path": "/manifest.gm.webmanifest",
                "manifest_id": "/mobile/gm",
                "manifest_start_url": "/mobile/gm",
                "session_handoff_route_template": "/mobile/gm?sessionId={sessionId}&role=GameMaster",
                "frontdoor_default": False,
            },
        ],
        "generated_at_utc": "2026-06-30T08:49:30Z",
    }


def test_source_contract_passes_for_current_ready_mobile_handoff() -> None:
    module = load_module()

    result = module.verify_source()

    assert result["status"] == "pass"


def test_valid_payload_passes_contract() -> None:
    module = load_module()

    assert module.verify_payload(valid_payload()) == []


def test_payload_requires_all_playtime_tools_and_boundaries() -> None:
    module = load_module()
    payload = valid_payload()
    payload["playtime_tools"] = [{"id": "inventory"}]
    payload["boundaries"] = ["Character builder replacement."]

    failures = module.verify_payload(payload)

    assert "missing playtime tool health" in failures
    assert "missing playtime tool quick_rolls" in failures
    assert "missing boundary phrase account opt-in" in failures
    assert "missing boundary phrase gm remains final authority" in failures


def test_payload_requires_role_specific_pwa_routes() -> None:
    module = load_module()
    payload = valid_payload()
    payload["frontdoor_launch_route"] = "/mobile"
    payload["role_routes"] = [{"role": "Player", "mode": "player", "route": "/mobile/player"}]

    failures = module.verify_payload(payload)

    assert "frontdoor_launch_route is not /mobile/player" in failures
    assert "Player: manifest_path is not /manifest.player.webmanifest" in failures
    assert "missing role route GameMaster" in failures


def test_live_receipt_records_tool_ids_and_packet_roles(monkeypatch) -> None:
    module = load_module()

    def fake_fetch(base_url: str, timeout_seconds: float):
        return (
            200,
            {"content-type": "application/json; charset=utf-8"},
            module.json.dumps(valid_payload()).encode("utf-8"),
            "https://chummer.run/ready/handoff/mobile.json",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_live("https://chummer.run", 1)

    assert result["status"] == "pass"
    assert "inventory" in result["tool_ids"]
    assert "player" in result["packet_roles"]
    assert result["frontdoor_launch_route"] == "/mobile/player"
    assert any(route["role"] == "Player" for route in result["role_routes"])



def test_live_receipt_fails_closed_on_forbidden_or_non_json(monkeypatch) -> None:
    module = load_module()

    def fake_fetch(base_url: str, timeout_seconds: float):
        return (403, {"content-type": "text/html"}, b"Forbidden", "https://chummer.run/ready/handoff/mobile.json")

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_live("https://chummer.run", 1)

    assert result["status"] == "fail"
    assert "/ready/handoff/mobile.json returned HTTP 403" in result["failures"]
    assert any("unexpected content-type" in failure for failure in result["failures"])
