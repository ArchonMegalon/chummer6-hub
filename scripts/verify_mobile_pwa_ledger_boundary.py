#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_STATUSES = {"opt_in_required", "no_world_data", "live", "world_not_followed"}


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def verify_source() -> dict[str, Any]:
    controller = read_text("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    view = read_text("Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml")
    playwright = read_text("tests/public/mobile-pwa-public.spec.ts")
    service_worker = read_text("Chummer.Run.Api/wwwroot/service-worker.js")

    required = {
        "controller_private_no_store": 'private, no-store, no-cache, max-age=0' in controller,
        "controller_vary_cookie_authorization": 'Vary"] = "Cookie, Authorization"' in controller,
        "controller_world_not_followed_hides_turn": "world_turn = (int?)null" in controller,
        "controller_gates_continuity": "continuity = followsCurrentWorld ? continuity : null" in controller,
        "view_install_only_no_ledger": (
            'data-play-surface="install-only"' in view
            and "/mobile/pwa/ledger.json" not in view
            and "data-pwa-ledger-" not in view
        ),
        "playwright_install_shell_boundary": (
            "public install shell does not request private ledger data" in playwright
        ),
        "service_worker_non_cacheable": '"/mobile/pwa/ledger.json"' in service_worker and "NON_CACHEABLE_PATHS" in service_worker,
    }
    failures = [name for name, ok in required.items() if not ok]
    return {
        "status": "pass" if not failures else "fail",
        "required": required,
        "failures": failures,
    }


def fetch(base_url: str, timeout_seconds: float) -> tuple[int, dict[str, str], str, str]:
    url = f"{base_url.rstrip('/')}/mobile/pwa/ledger.json"
    request = urllib.request.Request(url, headers={"User-Agent": "ChummerMobilePwaLedgerBoundaryProof/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, headers, body, response.geturl()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in error.headers.items()}
        return error.code, headers, body, error.geturl()


def header_contains(headers: dict[str, str], name: str, expected: str) -> bool:
    return expected.lower() in headers.get(name.lower(), "").lower()


def verify_payload(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("mode") != "mobile_pwa_living_world":
        failures.append("payload mode is not mobile_pwa_living_world")

    status = payload.get("status")
    if status not in ALLOWED_STATUSES:
        failures.append(f"payload status {status!r} is not allowed")

    if payload.get("updates_route") != "/mobile/pwa/ledger.json":
        failures.append("payload updates_route is not /mobile/pwa/ledger.json")

    if status == "opt_in_required" and payload.get("opt_in_route") != "/account":
        failures.append("opt_in_required payload does not point to /account")

    if status == "world_not_followed":
        world = payload.get("world") if isinstance(payload.get("world"), dict) else {}
        tracker = payload.get("tracker") if isinstance(payload.get("tracker"), dict) else {}
        if world.get("world_turn") is not None:
            failures.append("world_not_followed payload leaks world_turn")
        if payload.get("continuity") is not None:
            failures.append("world_not_followed payload leaks continuity")
        if payload.get("hot_district") is not None:
            failures.append("world_not_followed payload leaks hot_district")
        if payload.get("move_district") is not None:
            failures.append("world_not_followed payload leaks move_district")
        if tracker.get("turn_route") is not None:
            failures.append("world_not_followed payload leaks turn_route")
        if tracker.get("newsreel_route") is not None:
            failures.append("world_not_followed payload leaks newsreel_route")

    if status == "live":
        continuity = payload.get("continuity")
        tracker = payload.get("tracker") if isinstance(payload.get("tracker"), dict) else {}
        if not isinstance(payload.get("world"), dict):
            failures.append("live payload missing world object")
        if not isinstance(continuity, dict):
            failures.append("live payload missing continuity object")
        if not isinstance(payload.get("top_districts"), list):
            failures.append("live payload missing top_districts array")
        if not isinstance(tracker.get("turn_route"), str):
            failures.append("live payload missing tracker.turn_route")
        if not isinstance(tracker.get("newsreel_route"), str):
            failures.append("live payload missing tracker.newsreel_route")

    return failures


def verify_live(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    status_code, headers, body, final_url = fetch(base_url, timeout_seconds)
    failures: list[str] = []
    payload: dict[str, Any] = {}
    if status_code != 200:
        failures.append(f"/mobile/pwa/ledger.json returned HTTP {status_code}")
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            payload = parsed
        else:
            failures.append("ledger response is not a JSON object")
    except json.JSONDecodeError:
        failures.append("ledger response is not valid JSON")

    cache_control = headers.get("cache-control", "")
    vary = headers.get("vary", "")
    if "private" not in cache_control.lower() or "no-store" not in cache_control.lower():
        failures.append("cache-control does not include private no-store")
    if not header_contains(headers, "pragma", "no-cache"):
        failures.append("pragma is not no-cache")
    if not re.search(r"(^|,\s*)0($|,)", headers.get("expires", "0")) and headers.get("expires", "") != "0":
        failures.append("expires is not 0")
    if "cookie" not in vary.lower() or "authorization" not in vary.lower():
        failures.append("vary does not include Cookie and Authorization")

    if payload:
        failures.extend(verify_payload(payload))

    return {
        "status": "pass" if not failures else "fail",
        "base_url": base_url.rstrip("/"),
        "route": "/mobile/pwa/ledger.json",
        "status_code": status_code,
        "final_url": final_url,
        "payload_status": payload.get("status"),
        "payload_mode": payload.get("mode"),
        "updates_route": payload.get("updates_route"),
        "cache_control": cache_control,
        "pragma": headers.get("pragma", ""),
        "expires": headers.get("expires", ""),
        "vary": vary,
        "failures": failures,
    }


def verify(base_url: str | None, timeout_seconds: float) -> dict[str, Any]:
    source = verify_source()
    live = verify_live(base_url, timeout_seconds) if base_url else None
    failures = list(source.get("failures", []))
    if live and live.get("status") != "pass":
        failures.extend(live.get("failures", []))
    return {
        "contractName": "chummer.mobile_pwa_ledger_boundary.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if not failures else "fail",
        "source": source,
        "live": live,
        "base_url": base_url.rstrip("/") if base_url else "",
        "payload_status": live.get("payload_status") if live else "",
        "cache_control": live.get("cache_control") if live else "",
        "vary": live.get("vary") if live else "",
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the mobile PWA ledger opt-in and cache boundary.")
    parser.add_argument("--base-url", help="Base URL to verify live /mobile/pwa/ledger.json behavior.")
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
