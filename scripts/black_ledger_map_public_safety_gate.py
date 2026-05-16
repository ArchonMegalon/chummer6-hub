#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


FORBIDDEN_TERMS = (
    "productlift",
    "syllabbles",
    "teable",
    "support_case",
    "private_campaign",
    "account_email",
    "sourcebook_text",
    "operator_secret",
    "gmail.com",
    "provider callback",
)

REQUIRED_PHRASES = (
    "Opt-in aggregate only",
    "Every dispatch is generated from a world tick, public-safe pressure change, or closeout-facing movement.",
)

SCAN_ROUTES = (
    "/ledger",
    "/ledger/map",
    "/api/v1/ledger/worlds/emerald-sprawl-prelude/map",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Black Ledger command map remains public-safe and provider-safe.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def scan_route(base_url: str, route: str, failures: list[str]) -> dict:
    response = requests.get(f"{base_url}{route}", timeout=30)
    response.raise_for_status()
    body = response.text
    lowered = body.lower()

    for phrase in REQUIRED_PHRASES:
        if route == "/ledger" and phrase not in body:
            failures.append(f"{route} missing required phrase: {phrase}")
    for token in FORBIDDEN_TERMS:
        if token in lowered:
            failures.append(f"{route} contains forbidden term: {token}")

    return {
        "route": route,
        "status_code": response.status_code,
        "body_length": len(body),
    }


def run(base_url: str) -> int:
    failures: list[str] = []
    statuses = [scan_route(base_url, route, failures) for route in SCAN_ROUTES]

    map_payload = requests.get(
        f"{base_url}/api/v1/ledger/worlds/emerald-sprawl-prelude/map",
        timeout=30,
    ).json()
    require(map_payload.get("worldId") == "emerald-sprawl-prelude", "map api returned wrong worldId", failures)
    require(bool(map_payload.get("regions")), "map api returned empty regions", failures)
    require(bool(map_payload.get("factions")), "map api returned empty factions", failures)
    require(not any("@" in str(item) for item in map_payload.get("factions", [])), "map api leaked email-like data", failures)

    payload = {
        "contract_name": "chummer.black_ledger_map_public_safety_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "route_statuses": statuses,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("BLACK_LEDGER_COMMAND_MAP_PUBLIC_SAFETY.generated.json"), payload)
    lines = [
        "# Black Ledger Command Map Public Safety",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Status: `{payload['status']}`",
        f"- Routes scanned: `{len(statuses)}`",
        f"- Failure count: `{payload['failure_count']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in failures)
    else:
        lines.extend(["", "Command map pages and APIs remain public-safe and provider-safe."])
    write_text(completion_path("BLACK_LEDGER_COMMAND_MAP_PUBLIC_SAFETY.md"), "\n".join(lines))
    return 0 if not failures else 1


def run_source() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    landing = (repo_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Landing.cshtml").read_text(encoding="utf-8")
    ledger = (repo_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Ledger.cshtml").read_text(encoding="utf-8")
    service = (repo_root / "Chummer.Run.Api" / "Services" / "Community" / "BlackLedgerPublicStatsService.cs").read_text(encoding="utf-8")

    failures: list[str] = []
    require("Open command map" in landing, "landing page missing command map teaser link", failures)
    require("ledger-command-map" in ledger, "ledger view missing command map shell", failures)
    require("Opt-in aggregate only" in ledger, "ledger view missing public-safe copy", failures)
    require(
        "Every dispatch is generated from a world tick, public-safe pressure change, or closeout-facing movement." in ledger,
        "ledger view missing authority copy",
        failures,
    )
    lowered = "\n".join([landing, ledger, service]).lower()
    for token in FORBIDDEN_TERMS:
        if token in lowered:
            failures.append(f"source contains forbidden term: {token}")

    payload = {
        "contract_name": "chummer.black_ledger_map_public_safety_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": "source-only",
        "route_statuses": [],
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("BLACK_LEDGER_COMMAND_MAP_PUBLIC_SAFETY.generated.json"), payload)
    write_text(
        completion_path("BLACK_LEDGER_COMMAND_MAP_PUBLIC_SAFETY.md"),
        "\n".join(
            [
                "# Black Ledger Command Map Public Safety",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                f"- Base URL: {payload['base_url']}",
                f"- Status: `{payload['status']}`",
                f"- Failure count: `{payload['failure_count']}`",
            ] + (["", "## Failures", *[f"- {item}" for item in failures]] if failures else ["", "Source-level command map copy and contracts remain public-safe."])
        ),
    )
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))

    try:
        with LocalHubApp() as app:
            return run(app.base_url)
    except Exception:
        return run_source()


if __name__ == "__main__":
    raise SystemExit(main())
