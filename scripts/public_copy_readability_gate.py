#!/usr/bin/env python3
from __future__ import annotations

import argparse

import requests

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


ROUTE_REQUIREMENTS = {
    "/downloads": [
        "Current public installer",
        "Stable",
        "Nightly",
    ],
    "/feedback": [
        "What should Chummer do next?",
        "Public requests, clear bugs, useful ideas.",
    ],
    "/participate": [
        "What should Chummer do next?",
        "Public requests, clear bugs, useful ideas.",
    ],
}
PARTICIPATE_SOURCE_REQUIREMENTS = (
    '[HttpGet("/participate/board")]',
    "BuildParticipateFrameHref",
    "?embed=1",
)
ROUTE_FORBIDDEN = (
    "Top voters decide roadmap",
    "Guaranteed implementation",
    "Public bug reports are support tickets",
)
ACCOUNT_SOURCE_REQUIREMENTS = (
    "Participation state",
    "Contribution points",
    "Impact journal",
    "Public recognition stays off unless you opt in.",
    "Votes show demand; only finished work ships.",
)
ACCOUNT_SOURCE_FORBIDDEN = (
    "Earn Karma",
    "Top voters decide roadmap",
)
ACCOUNT_SOURCE = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "Accounts" / "Account.cshtml"
PARTICIPATE_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify public participation copy stays readable, motivating, and explicit about account value and private boundaries.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def check_route_copy(base_url: str) -> tuple[list[str], list[dict[str, object]]]:
    failures: list[str] = []
    route_statuses: list[dict[str, object]] = []
    session = requests.Session()

    for route, required_phrases in ROUTE_REQUIREMENTS.items():
        response = session.get(f"{base_url}{route}", timeout=30)
        response.raise_for_status()
        body = response.text

        missing = [phrase for phrase in required_phrases if phrase not in body]
        forbidden = [phrase for phrase in ROUTE_FORBIDDEN if phrase in body]
        if missing:
            failures.extend(f"{route} missing required phrase: {phrase}" for phrase in missing)
        if forbidden:
            failures.extend(f"{route} contains forbidden phrase: {phrase}" for phrase in forbidden)

        route_statuses.append(
            {
                "route": route,
                "status_code": response.status_code,
                "missing_count": len(missing),
                "forbidden_count": len(forbidden),
            }
        )

    return failures, route_statuses


def check_account_source() -> list[str]:
    failures: list[str] = []
    source = ACCOUNT_SOURCE.read_text(encoding="utf-8")
    for phrase in ACCOUNT_SOURCE_REQUIREMENTS:
        if phrase not in source:
            failures.append(f"account source missing required phrase: {phrase}")
    for phrase in ACCOUNT_SOURCE_FORBIDDEN:
        if phrase in source:
            failures.append(f"account source contains forbidden phrase: {phrase}")
    return failures


def check_participate_source() -> list[str]:
    failures: list[str] = []
    source = PARTICIPATE_CONTROLLER.read_text(encoding="utf-8")
    for phrase in PARTICIPATE_SOURCE_REQUIREMENTS:
        if phrase not in source:
            failures.append(f"participate controller missing required phrase: {phrase}")
    return failures


def run(base_url: str) -> int:
    failures, route_statuses = check_route_copy(base_url)
    failures.extend(check_account_source())
    failures.extend(check_participate_source())

    payload = {
        "contract_name": "chummer.public_copy_readability_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "route_count": len(route_statuses),
        "route_statuses": route_statuses,
        "account_source": str(ACCOUNT_SOURCE),
        "participate_controller": str(PARTICIPATE_CONTROLLER),
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("PUBLIC_COPY_READABILITY_GATE.generated.json"), payload)

    lines = [
        "# Public copy readability gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {payload['base_url']}",
        f"- Status: `{payload['status']}`",
        f"- Failure count: {payload['failure_count']}",
        "",
        "## Route scan",
        "",
    ]
    lines.extend(
        f"- `{status['route']}`: status=`{status['status_code']}` missing=`{status['missing_count']}` forbidden=`{status['forbidden_count']}`"
        for status in route_statuses
    )
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "Public participation copy keeps next steps explicit, account value honest, and private boundaries clear."])

    write_text(completion_path("PUBLIC_COPY_READABILITY_GATE.md"), "\n".join(lines))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
