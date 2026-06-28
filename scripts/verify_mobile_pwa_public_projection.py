#!/usr/bin/env python3
from __future__ import annotations

import argparse
from urllib.parse import urlparse

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


ROUTES = ["/mobile", "/pwa", "/play", "/player", "/gm", "/observer", "/session"]
EXPECTED_FINAL_ROUTES = {
    "/mobile": "/mobile",
    "/pwa": "/mobile",
    "/play": "/play",
    "/player": "/play?role=player",
    "/gm": "/play?role=gm",
    "/observer": "/play?role=observer",
    "/session": "/play",
}
EXPECTED_SHORTCUTS = {"/mobile", "/play", "/play/continuity"}
EXPECTED_SHELL_CACHE_PATHS = {"/mobile", "/play", "/play/continuity", "/mobile/pwa.json", "/ready/handoff/mobile.json"}
EXPECTED_PWA_LEDGER_STATUSES = {"opt_in_required", "no_world_data", "live", "world_not_followed"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the first-party mobile/PWA public projection.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def run(base_url: str) -> int:
    session = requests.Session()
    route_results = []
    for route in ROUTES:
        response = session.get(f"{base_url}{route}", timeout=30, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url
        parsed_final = urlparse(final_url)
        final_route = f"{parsed_final.path}{f'?{parsed_final.query}' if parsed_final.query else ''}"
        route_results.append(
            {
                "route": route,
                "status_code": response.status_code,
                "final_url": final_url,
                "final_route": final_route,
                "expected_final_route": EXPECTED_FINAL_ROUTES[route],
            }
        )

    mobile_html = session.get(f"{base_url}/mobile", timeout=30)
    mobile_html.raise_for_status()
    continuity_html = session.get(f"{base_url}/play/continuity", timeout=30)
    continuity_html.raise_for_status()
    mobile_json_response = session.get(f"{base_url}/mobile/pwa.json", timeout=30)
    mobile_json_response.raise_for_status()
    ledger_stream_response = session.get(f"{base_url}/mobile/pwa/ledger.json", timeout=30)
    ledger_stream_response.raise_for_status()
    receipt_index_response = session.get(f"{base_url}/play/continuity/receipts", timeout=30)
    receipt_index_response.raise_for_status()
    manifest_response = session.get(f"{base_url}/manifest.json", timeout=30)
    manifest_response.raise_for_status()
    service_worker_response = session.get(f"{base_url}/service-worker.js", timeout=30)
    service_worker_response.raise_for_status()

    manifest = manifest_response.json()
    mobile_json = mobile_json_response.json()
    ledger_stream = ledger_stream_response.json()
    receipt_index = receipt_index_response.json()
    has_manifest_link = 'rel="manifest"' in mobile_html.text and "/manifest.json" in mobile_html.text
    has_sw_registration = "serviceWorker.register(\"/service-worker.js\"" in mobile_html.text
    has_install_button = "Install this app" in mobile_html.text
    has_continuity_action = "/play/continuity" in mobile_html.text
    shortcut_urls = {shortcut.get("url") for shortcut in (manifest.get("shortcuts") or []) if isinstance(shortcut, dict)}
    screenshot_count = len(manifest.get("screenshots") or [])
    has_manifest_id = manifest.get("id") == "/mobile"
    has_display_override = bool(manifest.get("display_override"))
    has_expected_shortcuts = EXPECTED_SHORTCUTS.issubset(shortcut_urls)
    has_expected_shell_cache_paths = all(path in service_worker_response.text for path in EXPECTED_SHELL_CACHE_PATHS)
    has_navigation_preload = "navigationPreload" in service_worker_response.text
    has_runtime_cache = "RUNTIME_CACHE" in service_worker_response.text
    has_push_handler = 'self.addEventListener("push"' in service_worker_response.text
    has_notification_click_handler = 'self.addEventListener("notificationclick"' in service_worker_response.text
    has_notification_close_handler = 'self.addEventListener("notificationclose"' in service_worker_response.text
    continuity_receipt_count = len(receipt_index.get("receipts") or [])
    continuity_boundary_present = bool(receipt_index.get("boundary"))
    mobile_json_has_routes = (
        mobile_json.get("install_route") == "/downloads"
        and mobile_json.get("continuity_route") == "/play/continuity"
        and mobile_json.get("receipt_index_route") == "/play/continuity/receipts"
    )
    ledger_stream_mode = ledger_stream.get("mode")
    ledger_stream_status = ledger_stream.get("status")
    ledger_stream_has_updates_route = ledger_stream.get("updates_route") == "/mobile/pwa/ledger.json"
    ledger_stream_has_valid_status = ledger_stream_status in EXPECTED_PWA_LEDGER_STATUSES
    ledger_stream_is_living_world = ledger_stream_mode == "mobile_pwa_living_world"
    ledger_stream_contract_holds = (
        isinstance(ledger_stream, dict)
        and ledger_stream_is_living_world
        and ledger_stream_has_valid_status
        and ledger_stream_has_updates_route
    )
    role_routes_hold = all(
        result["final_route"] == result["expected_final_route"]
        for result in route_results
    )
    checks = [
        has_manifest_link,
        has_sw_registration,
        has_install_button,
        has_continuity_action,
        has_manifest_id,
        has_display_override,
        has_expected_shortcuts,
        screenshot_count >= 2,
        has_expected_shell_cache_paths,
        has_navigation_preload,
        has_runtime_cache,
        has_push_handler,
        has_notification_click_handler,
        has_notification_close_handler,
        continuity_receipt_count >= 3,
        continuity_boundary_present,
        mobile_json_has_routes,
        ledger_stream_contract_holds,
        role_routes_hold,
    ]

    payload = {
        "contract_name": "chummer.mobile_pwa_public_projection",
        "status": "pass" if all(checks) else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "route_results": route_results,
        "manifest": {
            "id": manifest.get("id"),
            "start_url": manifest.get("start_url"),
            "display": manifest.get("display"),
            "display_override": manifest.get("display_override"),
            "shortcut_count": len(manifest.get("shortcuts") or []),
            "icon_count": len(manifest.get("icons") or []),
            "screenshot_count": screenshot_count,
            "shortcut_urls": sorted(shortcut_urls),
        },
        "service_worker": {
            "path": "/service-worker.js",
            "status_code": service_worker_response.status_code,
            "has_fetch_handler": "self.addEventListener(\"fetch\"" in service_worker_response.text,
            "has_navigation_preload": has_navigation_preload,
            "has_runtime_cache": has_runtime_cache,
            "has_expected_shell_cache_paths": has_expected_shell_cache_paths,
            "has_push_handler": has_push_handler,
            "has_notification_click_handler": has_notification_click_handler,
            "has_notification_close_handler": has_notification_close_handler,
        },
        "page_assertions": {
            "has_manifest_link": has_manifest_link,
            "has_service_worker_registration": has_sw_registration,
            "has_install_button": has_install_button,
            "has_continuity_action": has_continuity_action,
            "role_routes_hold": role_routes_hold,
            "continuity_page_status_code": continuity_html.status_code,
        },
        "continuity": {
            "receipt_count": continuity_receipt_count,
            "has_boundary": continuity_boundary_present,
            "mobile_json_has_routes": mobile_json_has_routes,
        },
        "ledger_stream": {
            "status": ledger_stream_status,
            "mode": ledger_stream_mode,
            "has_contract": ledger_stream_contract_holds,
        },
    }
    write_json(completion_path("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"), payload)
    write_text(
        completion_path("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.md"),
        "\n".join(
            [
                "# Mobile and PWA public projection audit",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                f"- Manifest start URL: `{payload['manifest']['start_url']}`",
                f"- Display mode: `{payload['manifest']['display']}`",
                f"- Display override present: `{has_display_override}`",
                f"- Manifest screenshots: `{screenshot_count}`",
                f"- Manifest link present on `/mobile`: `{has_manifest_link}`",
                f"- Service worker registration present on `/mobile`: `{has_sw_registration}`",
                f"- Install action visible on `/mobile`: `{has_install_button}`",
                f"- Continuity action visible on `/mobile`: `{has_continuity_action}`",
                f"- Service worker fetch handler present: `{payload['service_worker']['has_fetch_handler']}`",
                f"- Service worker navigation preload present: `{has_navigation_preload}`",
                f"- Service worker continuity cache paths present: `{has_expected_shell_cache_paths}`",
                f"- Service worker push handler present: `{has_push_handler}`",
                f"- Service worker notification click handler present: `{has_notification_click_handler}`",
                f"- Service worker notification close handler present: `{has_notification_close_handler}`",
                f"- Role-route redirects hold: `{role_routes_hold}`",
                f"- Continuity receipt count: `{continuity_receipt_count}`",
                f"- Continuity boundary present: `{continuity_boundary_present}`",
            ]
        ),
    )
    if payload["status"] == "pass":
        print("mobile_pwa_public_projection:ok")
    return 0 if payload["status"] == "pass" else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url)

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
