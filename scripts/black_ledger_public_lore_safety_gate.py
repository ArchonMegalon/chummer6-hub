#!/usr/bin/env python3
from __future__ import annotations

import argparse

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json

FORBIDDEN = (
    "productlift",
    "syllabbles",
    "teable",
    "appsumo",
    "operator_secret",
    "provider callback",
    "sourcebook_text",
    "private_campaign",
)

ROUTES = ("/", "/ledger", "/ledger/map", "/ledger/dispatches", "/api/v1/ledger/worlds/emerald-sprawl-prelude")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    return parser.parse_args()


def run(base_url: str) -> int:
    failures: list[str] = []
    route_statuses: list[dict[str, object]] = []
    for route in ROUTES:
        response = requests.get(f"{base_url.rstrip('/')}{route}", timeout=30)
        route_statuses.append({"route": route, "status_code": response.status_code})
        if response.status_code != 200:
            failures.append(f"{route} returned {response.status_code}")
            continue
        lowered = response.text.lower()
        for token in FORBIDDEN:
            if token in lowered:
                failures.append(f"{route} contains forbidden token: {token}")

    payload = {
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "base_url": base_url,
        "route_statuses": route_statuses,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("..", "black_ledger_public_seed", "BLACK_LEDGER_PUBLIC_LORE_SAFETY.generated.json"), payload)
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url)
    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
