#!/usr/bin/env python3
from __future__ import annotations

import argparse

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


ROUTES = ["/mobile", "/pwa", "/play", "/player", "/gm", "/observer", "/session"]


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
        route_results.append(
            {
                "route": route,
                "status_code": response.status_code,
                "final_url": response.url,
            }
        )

    mobile_html = session.get(f"{base_url}/mobile", timeout=30)
    mobile_html.raise_for_status()
    manifest_response = session.get(f"{base_url}/manifest.json", timeout=30)
    manifest_response.raise_for_status()
    service_worker_response = session.get(f"{base_url}/service-worker.js", timeout=30)
    service_worker_response.raise_for_status()

    manifest = manifest_response.json()
    has_manifest_link = 'rel="manifest"' in mobile_html.text and "/manifest.json" in mobile_html.text
    has_sw_registration = "serviceWorker.register(\"/service-worker.js\"" in mobile_html.text

    payload = {
        "contract_name": "chummer.mobile_pwa_public_projection",
        "status": "pass" if has_manifest_link and has_sw_registration else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "route_results": route_results,
        "manifest": {
            "start_url": manifest.get("start_url"),
            "display": manifest.get("display"),
            "shortcut_count": len(manifest.get("shortcuts") or []),
            "icon_count": len(manifest.get("icons") or []),
        },
        "service_worker": {
            "path": "/service-worker.js",
            "status_code": service_worker_response.status_code,
            "has_fetch_handler": "self.addEventListener(\"fetch\"" in service_worker_response.text,
        },
        "page_assertions": {
            "has_manifest_link": has_manifest_link,
            "has_service_worker_registration": has_sw_registration,
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
                f"- Manifest link present on `/mobile`: `{has_manifest_link}`",
                f"- Service worker registration present on `/mobile`: `{has_sw_registration}`",
                f"- Service worker fetch handler present: `{payload['service_worker']['has_fetch_handler']}`",
            ]
        ),
    )
    return 0 if payload["status"] == "pass" else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url)

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
