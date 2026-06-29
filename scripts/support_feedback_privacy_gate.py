#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text
from verify_public_copy_leak_gate import visible_text


ROUTES = ("/contact", "/participate", "/feedback", "/help/feedback")
FORBIDDEN_RAW_PHRASES = (
    "GOOGLE_OIDC_",
    "IDENTITY_ADMIN_KEY",
    "webhook secret",
    "provider callback",
)
FORBIDDEN_VISIBLE_PHRASES = (
    "provider callback",
    "ProductLift",
    "Emailit",
    "Lunacal",
    "Deftform",
    "FacePop",
    "ClickRank",
)
REQUIRED_VISIBLE_BY_ROUTE = {
    "/contact": ("Contact",),
    "/participate": ("Public requests",),
}


@dataclass
class RoutePrivacyResult:
    route: str
    final_url: str
    status_code: int
    same_origin: bool
    success: bool
    failures: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify public support and feedback routes stay privacy-bounded.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def verify_route(session: requests.Session, base_url: str, route: str) -> RoutePrivacyResult:
    response = session.get(f"{base_url}{route}", timeout=30, allow_redirects=True)
    final_url = response.url
    base_host = urlparse(base_url).netloc.lower()
    final_host = urlparse(final_url).netloc.lower()
    same_origin = not final_host or final_host == base_host
    text = visible_text(response.text)
    failures: list[str] = []

    if response.status_code >= 400:
        failures.append(f"unexpected status {response.status_code}")
    if not same_origin:
        failures.append(f"cross-origin redirect to {final_url}")
    for phrase in FORBIDDEN_RAW_PHRASES:
        if phrase in response.text:
            failures.append(f"forbidden raw phrase present: {phrase}")
    for phrase in FORBIDDEN_VISIBLE_PHRASES:
        if phrase in text:
            failures.append(f"forbidden phrase present: {phrase}")
    for required in REQUIRED_VISIBLE_BY_ROUTE.get(route, ()):
        if required not in text:
            failures.append(f"missing required phrase: {required}")
    if route in {"/feedback", "/help/feedback"} and "/participate" not in urlparse(final_url).path:
        failures.append(f"{route} should resolve through /participate, got {final_url}")

    return RoutePrivacyResult(
        route=route,
        final_url=final_url,
        status_code=response.status_code,
        same_origin=same_origin,
        success=not failures,
        failures=failures,
    )


def run(base_url: str) -> int:
    session = requests.Session()
    results = [verify_route(session, base_url, route) for route in ROUTES]
    failures = [failure for result in results for failure in result.failures]
    payload = {
        "contract_name": "chummer.support_feedback_privacy_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "routes": [asdict(result) for result in results],
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("SUPPORT_FEEDBACK_PRIVACY_GATE.generated.json"), payload)

    lines = [
        "# Support and feedback privacy gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Status: `{payload['status']}`",
        f"- Failure count: `{payload['failure_count']}`",
        "",
        "## Routes",
        "",
    ]
    for result in results:
        lines.append(f"- `{result.route}` -> `{result.final_url}` status=`{result.status_code}` success=`{result.success}`")
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    write_text(completion_path("SUPPORT_FEEDBACK_PRIVACY_GATE.md"), "\n".join(lines))
    if failures:
        return 1
    print("support_feedback_privacy_gate:ok")
    return 0


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))
    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
