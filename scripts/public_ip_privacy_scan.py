#!/usr/bin/env python3
from __future__ import annotations

import argparse

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


FORBIDDEN_PHRASES = (
    "drug addicts",
    "dumbest",
    "ugliest",
    "provider callback",
    "GOOGLE_OIDC_",
    "webhook secret",
)

REQUIRED_PHRASES = (
    "fictional runner/campaign statistics only",
    "Opt-in aggregate only",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan the public landing copy for privacy-safe flagship wording.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    parser.add_argument("--route", default="/", help="Public route to verify. Defaults to landing page.")
    return parser.parse_args()


def run(base_url: str, route: str) -> int:
    failures: list[str] = []
    normalized_route = route if route.startswith("/") else f"/{route}"
    response = requests.get(f"{base_url}{normalized_route}", timeout=30)
    response.raise_for_status()
    body = response.text

    for phrase in REQUIRED_PHRASES:
        if phrase not in body:
            failures.append(f"missing required phrase: {phrase}")
    for phrase in FORBIDDEN_PHRASES:
        if phrase in body:
            failures.append(f"forbidden phrase present: {phrase}")

    payload = {
        "contract_name": "chummer.public_ip_privacy_scan",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "route": normalized_route,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("PUBLIC_IP_PRIVACY_SCAN.generated.json"), payload)

    lines = [
        "# Public IP/privacy scan",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Route: `{normalized_route}`",
        f"- Status: `{payload['status']}`",
        f"- Failure count: `{payload['failure_count']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "Public flagship copy stays privacy-safe and avoids stigmatizing labels or operator leakage."])
    write_text(completion_path("PUBLIC_IP_PRIVACY_SCAN.md"), "\n".join(lines))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"), args.route)

    with LocalHubApp() as app:
        return run(app.base_url, args.route)


if __name__ == "__main__":
    raise SystemExit(main())
