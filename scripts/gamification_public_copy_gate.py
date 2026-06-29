#!/usr/bin/env python3
from __future__ import annotations

import argparse

import requests

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


REQUIRED_VISIBLE_PHRASES = [
    "Participate",
    "Public requests, clear bugs, useful ideas.",
]

REQUIRED_SOURCE_PHRASES = [
    '[HttpGet("/participate/board")]',
    "BuildParticipateFrameHref",
    "?embed=1",
]

FORBIDDEN_PHRASES = [
    "Earn Karma",
    "Leaderboard",
    "Top voters decide roadmap",
    "Guaranteed implementation",
    "Public bug reports are support tickets",
    "Votes show demand. Chummer decides what ships.",
    "Follow an item to hear when it changes.",
    "Good reports include context and reproduction steps.",
    "Private logs and account issues belong in Help, not public feedback.",
]

ROUTES = [
    "/feedback",
    "/participate",
]
PARTICIPATE_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the public participation copy stays motivational without fake gamification or vote authority.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def run(base_url: str) -> int:
    session = requests.Session()
    combined_html = []
    route_statuses = []
    failures: list[str] = []
    for route in ROUTES:
        response = session.get(f"{base_url}{route}", timeout=30)
        response.raise_for_status()
        combined_html.append(response.text)
        route_statuses.append({"route": route, "status_code": response.status_code})

    joined = "\n".join(combined_html)
    for phrase in REQUIRED_VISIBLE_PHRASES:
        if phrase not in joined:
            failures.append(f"missing required visible phrase: {phrase}")
    for phrase in FORBIDDEN_PHRASES:
        if phrase in joined:
            failures.append(f"forbidden phrase present: {phrase}")
    controller_source = PARTICIPATE_CONTROLLER.read_text(encoding="utf-8")
    for phrase in REQUIRED_SOURCE_PHRASES:
        if phrase not in controller_source:
            failures.append(f"participate controller missing required board route phrase: {phrase}")

    payload = {
        "contract_name": "chummer.gamification_public_copy_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "routes": route_statuses,
        "required_visible_phrases": REQUIRED_VISIBLE_PHRASES,
        "required_source_phrases": REQUIRED_SOURCE_PHRASES,
        "participate_controller": str(PARTICIPATE_CONTROLLER),
        "forbidden_phrases": FORBIDDEN_PHRASES,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("GAMIFICATION_PUBLIC_COPY_GATE.generated.json"), payload)
    lines = [
        "# Gamification public copy gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Status: `{payload['status']}`",
        f"- Failure count: {payload['failure_count']}",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "Public participation copy keeps motivation, route clarity, and shipping authority without fake public gamification claims."])
    write_text(completion_path("GAMIFICATION_PUBLIC_COPY_GATE.md"), "\n".join(lines))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
