#!/usr/bin/env python3
from __future__ import annotations

import argparse
from urllib.parse import parse_qs, urlparse

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


PACKAGE_ID = "desktop-preview"
PUBLIC_ROUTES = [
    "/packages",
    f"/packages/{PACKAGE_ID}",
    f"/packages/{PACKAGE_ID}/vote",
    f"/packages/{PACKAGE_ID}/follow",
]
AUTH_ROUTES = [
    "/account/packages",
    f"/account/packages/{PACKAGE_ID}",
    "/admin/packages",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify public package routes and anonymous auth redirects.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def fetch_public(session: requests.Session, base_url: str, route: str) -> dict:
    response = session.get(f"{base_url}{route}", timeout=30, allow_redirects=True)
    return {
        "route": route,
        "status_code": response.status_code,
        "final_url": response.url,
        "ok": response.status_code == 200,
    }


def fetch_redirect(session: requests.Session, base_url: str, route: str) -> dict:
    response = session.get(f"{base_url}{route}", timeout=30, allow_redirects=False)
    location = response.headers.get("Location", "")
    parsed = urlparse(location)
    next_target = parse_qs(parsed.query).get("next", [""])[0]
    ok = response.status_code in (302, 303) and parsed.path == "/login" and next_target == route
    return {
        "route": route,
        "status_code": response.status_code,
        "location": location,
        "ok": ok,
    }


def run(base_url: str) -> int:
    session = requests.Session()
    public_results = [fetch_public(session, base_url, route) for route in PUBLIC_ROUTES]
    auth_results = [fetch_redirect(session, base_url, route) for route in AUTH_ROUTES]
    passed = all(result["ok"] for result in public_results + auth_results)

    payload = {
        "contract_name": "chummer.package_public_route_verification",
        "status": "pass" if passed else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "public_routes": public_results,
        "auth_routes": auth_results,
    }
    write_json(completion_path("PACKAGE_PUBLIC_ROUTE_VERIFICATION.generated.json"), payload)

    lines = [
        "# Package public route verification",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Status: `{payload['status']}`",
        "",
        "## Public routes",
        "",
    ]
    for result in public_results:
        lines.append(
            f"- `{result['route']}`: status=`{result['status_code']}` final=`{result['final_url']}` result=`{'pass' if result['ok'] else 'fail'}`"
        )
    lines.extend(["", "## Auth redirects", ""])
    for result in auth_results:
        lines.append(
            f"- `{result['route']}`: status=`{result['status_code']}` location=`{result['location']}` result=`{'pass' if result['ok'] else 'fail'}`"
        )

    write_text(completion_path("PACKAGE_PUBLIC_ROUTE_VERIFICATION.md"), "\n".join(lines))
    return 0 if passed else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
