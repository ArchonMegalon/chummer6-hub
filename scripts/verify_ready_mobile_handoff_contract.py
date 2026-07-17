#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOOLS = {"inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world"}
REQUIRED_PACKET_ROLES = {"player", "gm", "organizer"}
REQUIRED_ROLE_ROUTES = {
    "Player": {
        "mode": "player",
        "route": "/mobile/player",
        "manifest_path": "/manifest.player.webmanifest",
        "manifest_id": "/mobile/player",
        "manifest_start_url": "/mobile/player",
        "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
        "frontdoor_default": True,
    },
    "GameMaster": {
        "mode": "gm",
        "route": "/mobile/gm",
        "manifest_path": "/manifest.gm.webmanifest",
        "manifest_id": "/mobile/gm",
        "manifest_start_url": "/mobile/gm",
        "session_handoff_route_template": "/mobile/gm?sessionId={sessionId}&role=GameMaster",
        "frontdoor_default": False,
    },
}


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def verify_payload(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    require(payload.get("mode") == "ready_for_tonight", failures, "mode is not ready_for_tonight")
    require(payload.get("status") == "ready", failures, "status is not ready")
    require(payload.get("next_best_screen") == "/mobile", failures, "next_best_screen is not /mobile")
    require(payload.get("pwa_route") == "/mobile", failures, "pwa_route is not /mobile")
    require(payload.get("continuity_route") == "/play/continuity", failures, "continuity_route is not /play/continuity")
    require(payload.get("frontdoor_launch_route") == "/mobile/player", failures, "frontdoor_launch_route is not /mobile/player")

    tools = payload.get("playtime_tools")
    if not isinstance(tools, list):
        failures.append("playtime_tools is not an array")
        tool_ids: set[str] = set()
    else:
        tool_ids = {str(item.get("id")) for item in tools if isinstance(item, dict)}
    for tool in sorted(REQUIRED_TOOLS):
        require(tool in tool_ids, failures, f"missing playtime tool {tool}")

    serialized = json.dumps(payload, sort_keys=True).lower()
    for phrase in [
        "character building stays before or after the session",
        "account opt-in",
        "followed-world selection",
        "gm remains final authority",
    ]:
        require(phrase in serialized, failures, f"missing boundary phrase {phrase}")

    packet_routes = payload.get("packet_routes")
    if not isinstance(packet_routes, list):
        failures.append("packet_routes is not an array")
        roles: set[str] = set()
    else:
        roles = {str(item.get("roleId")) for item in packet_routes if isinstance(item, dict)}
        for item in packet_routes:
            if not isinstance(item, dict):
                continue
            role = item.get("roleId")
            require(str(item.get("markdown", "")).startswith("/ready/packet/"), failures, f"{role}: markdown route missing")
            require(str(item.get("json", "")).startswith("/ready/packet/"), failures, f"{role}: json route missing")
    for role in sorted(REQUIRED_PACKET_ROLES):
        require(role in roles, failures, f"missing packet role {role}")

    role_routes = payload.get("role_routes")
    if not isinstance(role_routes, list):
        failures.append("role_routes is not an array")
    else:
        by_role = {
            str(item.get("role")): item
            for item in role_routes
            if isinstance(item, dict) and str(item.get("role") or "").strip()
        }
        for role_name, expected in REQUIRED_ROLE_ROUTES.items():
            route = by_role.get(role_name)
            require(route is not None, failures, f"missing role route {role_name}")
            if not isinstance(route, dict):
                continue
            require(route.get("mode") == expected["mode"], failures, f"{role_name}: mode is not {expected['mode']}")
            require(route.get("route") == expected["route"], failures, f"{role_name}: route is not {expected['route']}")
            require(route.get("manifest_path") == expected["manifest_path"], failures, f"{role_name}: manifest_path is not {expected['manifest_path']}")
            require(route.get("manifest_id") == expected["manifest_id"], failures, f"{role_name}: manifest_id is not {expected['manifest_id']}")
            require(route.get("manifest_start_url") == expected["manifest_start_url"], failures, f"{role_name}: manifest_start_url is not {expected['manifest_start_url']}")
            require(
                route.get("session_handoff_route_template") == expected["session_handoff_route_template"],
                failures,
                f"{role_name}: session_handoff_route_template is not {expected['session_handoff_route_template']}",
            )
            require(
                route.get("frontdoor_default") is expected["frontdoor_default"],
                failures,
                f"{role_name}: frontdoor_default is not {str(expected['frontdoor_default']).lower()}",
            )

    require(bool(payload.get("generated_at_utc")), failures, "generated_at_utc is missing")
    return failures


def verify_source() -> dict[str, Any]:
    service = read_text("Chummer.Run.Api/Services/ReadyForTonightService.cs")
    tests = read_text("Chummer.Tests/ReadyForTonightServiceTests.cs")
    manifest = read_text(".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml")
    failures: list[str] = []
    for needle in [
        "playtime_tools",
        "inventory",
        "health",
        "ammo",
        "modifiers",
        "quick_rolls",
        "living_world",
        "account opt-in",
        "followed-world selection",
        "GM remains final authority",
        'pwa_route = "/mobile"',
        'frontdoor_launch_route = "/mobile/player"',
        'route = "/mobile/player"',
        'route = "/mobile/gm"',
        'manifest_path = "/manifest.player.webmanifest"',
        'manifest_path = "/manifest.gm.webmanifest"',
        'manifest_start_url = "/mobile/player"',
        'manifest_start_url = "/mobile/gm"',
    ]:
        require(needle in service, failures, f"service missing {needle}")
    for needle in [
        "Mobile_handoff_names_playtime_tools_and_opt_in_boundaries",
        "quick_rolls",
        "living_world",
        "character building stays before or after the session",
        'root.GetProperty("frontdoor_launch_route")',
        'root.GetProperty("role_routes")',
        'frontdoor_default',
        '/manifest.gm.webmanifest',
    ]:
        require(needle in tests, failures, f"test missing {needle}")
    for needle in [
        "/ready/handoff/mobile.json",
        "purpose: ready_mobile_handoff",
        "- playtime_tools",
        "- role_routes",
        "- account opt-in",
        "- followed-world selection",
        "- /mobile/player",
        "- /mobile/gm",
        "- /manifest.player.webmanifest",
        "- /manifest.gm.webmanifest",
    ]:
        require(needle in manifest, failures, f"manifest missing {needle}")
    return {"status": "pass" if not failures else "fail", "failures": failures}


def fetch(base_url: str, timeout_seconds: float) -> tuple[int, dict[str, str], bytes, str]:
    url = urljoin(base_url.rstrip("/") + "/", "ready/handoff/mobile.json")
    request = Request(url, headers={"User-Agent": "ChummerReadyMobileHandoffProof/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, headers, response.read(), response.geturl()
    except HTTPError as exc:
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return exc.code, headers, exc.read(), exc.geturl()
    except URLError as exc:
        raise RuntimeError(f"/ready/handoff/mobile.json: {exc}") from exc


def verify_live(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    status_code, headers, body, final_url = fetch(base_url, timeout_seconds)
    failures: list[str] = []
    payload: dict[str, Any] = {}
    require(status_code == 200, failures, f"/ready/handoff/mobile.json returned HTTP {status_code}")
    require("json" in headers.get("content-type", ""), failures, f"unexpected content-type {headers.get('content-type')}")
    try:
        parsed = json.loads(body.decode("utf-8-sig"))
        if isinstance(parsed, dict):
            payload = parsed
        else:
            failures.append("handoff payload is not a JSON object")
    except json.JSONDecodeError as exc:
        failures.append(f"handoff payload is invalid JSON: {exc}")
    if payload:
        failures.extend(verify_payload(payload))
    return {
        "status": "pass" if not failures else "fail",
        "base_url": base_url.rstrip("/"),
        "route": "/ready/handoff/mobile.json",
        "status_code": status_code,
        "final_url": final_url,
        "content_type": headers.get("content-type", ""),
        "tool_ids": [item.get("id") for item in payload.get("playtime_tools", [])] if isinstance(payload.get("playtime_tools"), list) else [],
        "packet_roles": [item.get("roleId") for item in payload.get("packet_routes", [])] if isinstance(payload.get("packet_routes"), list) else [],
        "role_routes": payload.get("role_routes", []) if isinstance(payload.get("role_routes"), list) else [],
        "next_best_screen": payload.get("next_best_screen"),
        "pwa_route": payload.get("pwa_route"),
        "continuity_route": payload.get("continuity_route"),
        "frontdoor_launch_route": payload.get("frontdoor_launch_route"),
        "failures": failures,
    }


def verify(base_url: str | None, timeout_seconds: float) -> dict[str, Any]:
    source = verify_source()
    live = verify_live(base_url, timeout_seconds) if base_url else None
    failures = list(source.get("failures", []))
    if live and live.get("status") != "pass":
        failures.extend(live.get("failures", []))
    return {
        "contractName": "chummer.ready_mobile_handoff_contract.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if not failures else "fail",
        "source": source,
        "live": live,
        "base_url": base_url.rstrip("/") if base_url else "",
        "tool_ids": live.get("tool_ids") if live else [],
        "packet_roles": live.get("packet_roles") if live else [],
        "role_routes": live.get("role_routes") if live else [],
        "frontdoor_launch_route": live.get("frontdoor_launch_route") if live else "",
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the Ready for Tonight mobile handoff contract.")
    parser.add_argument("--base-url", help="Base URL to verify live /ready/handoff/mobile.json behavior.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    result = verify(args.base_url, args.timeout_seconds)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
