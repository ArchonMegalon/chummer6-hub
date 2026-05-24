#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text

FORBIDDEN = (
    "productlift",
    "emailit",
    "deftform",
    "icanpreneur",
    "gmail.com",
    "support_case",
    "private_campaign",
    "account_email",
    "operator_secret",
    "sourcebook_text",
)

REQUIRED = (
    "Generated from",
    "public-safe",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Black Ledger dispatch safety and authority copy.")
    parser.add_argument("--base-url", default="")
    return parser.parse_args()


def check_body(body: str, label: str, failures: list[str]) -> None:
    lowered = body.lower()
    for term in FORBIDDEN:
        if term in lowered:
            failures.append(f"{label} contains forbidden term: {term}")
    for phrase in REQUIRED:
        if phrase not in body:
            failures.append(f"{label} missing required phrase: {phrase}")


def check_page(url: str, failures: list[str]) -> None:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    check_body(response.text, url, failures)


def run(base_url: str) -> int:
    failures: list[str] = []
    urls = [
        f"{base_url}/ledger/dispatches",
        f"{base_url}/ledger/dispatches/dispatch_turn_0001_main",
        f"{base_url}/ledger/turns/1/dispatches",
        f"{base_url}/ledger/factions/ashline-circle/dispatches",
    ]
    for url in urls:
        check_page(url, failures)
    payload = {
        "contract_name": "chummer.black_ledger_dispatch_safety_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "checked_urls": urls,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("DISPATCH_SAFETY_GATE.generated.json"), payload)
    write_text(
        completion_path("DISPATCH_SAFETY_GATE.md"),
        "\n".join(
            [
                "# Black Ledger Dispatch Safety Gate",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                f"- Status: `{payload['status']}`",
            ] + ([ "", "## Failures", *[f"- {item}" for item in failures] ] if failures else ["", "All checked dispatch routes passed safety copy checks."])
        ),
    )
    return 0 if not failures else 1


def run_source() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    bodies = {
        "controller": (repo_root / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8"),
        "ledger_view": (repo_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Ledger.cshtml").read_text(encoding="utf-8"),
        "service": (repo_root / "Chummer.Run.Api" / "Services" / "Community" / "BlackLedgerPublicStatsService.cs").read_text(encoding="utf-8"),
    }
    check_body(bodies["ledger_view"], "ledger_view", failures)
    if '[HttpGet("/ledger/turns/{turn}/dispatches")]' not in bodies["controller"]:
        failures.append('controller missing /ledger/turns/{turn}/dispatches route')
    if '[HttpGet("/ledger/factions/{factionId}/dispatches")]' not in bodies["controller"]:
        failures.append('controller missing /ledger/factions/{factionId}/dispatches route')
    if "drone_logistics_overlay" not in bodies["service"]:
        failures.append("service missing drone logistics package-pressure dispatch fixture")
    payload = {
        "contract_name": "chummer.black_ledger_dispatch_safety_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": "source-only",
        "checked_urls": ["source:controller", "source:ledger_view", "source:service"],
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("DISPATCH_SAFETY_GATE.generated.json"), payload)
    write_text(completion_path("DISPATCH_SAFETY_GATE.md"), "\n".join(["# Black Ledger Dispatch Safety Gate", "", f"- Generated: {payload['generated_at_utc']}", f"- Status: `{payload['status']}`"] + ([ "", "## Failures", *[f"- {item}" for item in failures] ] if failures else ["", "Source-backed dispatch safety checks passed."])))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))
    return run_source()


if __name__ == "__main__":
    raise SystemExit(main())
