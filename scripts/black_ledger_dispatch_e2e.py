#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


DISPATCH_ID = "dispatch_turn_0001_main"
FORBIDDEN_PUBLIC_TERMS = (
    "productlift",
    "emailit",
    "deftform",
    "icanpreneur",
    "support_case",
    "private_campaign",
    "account_email",
    "operator_secret",
    "sourcebook_text",
    "gmail.com",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Black Ledger dispatch routes and preview-safe dispatch content.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def require_phrase(body: str, phrase: str, failures: list[str], label: str) -> None:
    if phrase not in body:
        failures.append(f"{label} missing required phrase: {phrase}")


def forbid_terms(body: str, failures: list[str], label: str) -> None:
    lowered = body.lower()
    for term in FORBIDDEN_PUBLIC_TERMS:
        if term in lowered:
            failures.append(f"{label} contains forbidden term: {term}")


def run(base_url: str) -> int:
    failures: list[str] = []

    root = requests.get(f"{base_url}/", timeout=30)
    root.raise_for_status()
    archive = requests.get(f"{base_url}/ledger/dispatches", timeout=30)
    archive.raise_for_status()
    detail = requests.get(f"{base_url}/ledger/dispatches/{DISPATCH_ID}", timeout=30)
    detail.raise_for_status()
    turn_archive = requests.get(f"{base_url}/ledger/turns/1/dispatches", timeout=30)
    turn_archive.raise_for_status()
    faction_archive = requests.get(f"{base_url}/ledger/factions/ashline-circle/dispatches", timeout=30)
    faction_archive.raise_for_status()

    require_phrase(root.text, "Turn 1 newsreel", failures, "/")
    require_phrase(root.text, "Enter Black Ledger", failures, "/")

    require_phrase(archive.text, "Read dispatches", failures, "/ledger/dispatches")
    require_phrase(archive.text, "A fictional, public-safe seed world with six factions, visible pressure zones, and bounded dispatches.", failures, "/ledger/dispatches")
    require_phrase(archive.text, "ledger_tick_0001_preseeded", failures, "/ledger/dispatches")

    require_phrase(detail.text, "The city is moving.", failures, f"/ledger/dispatches/{DISPATCH_ID}")
    require_phrase(detail.text, "Use the map to inspect seeded districts, visible pressure arcs, and public-safe dispatches without exposing private tables.", failures, f"/ledger/dispatches/{DISPATCH_ID}")
    require_phrase(detail.text, "ledger_tick_0001_preseeded", failures, f"/ledger/dispatches/{DISPATCH_ID}")
    require_phrase(detail.text, "Safety: public-safe", failures, f"/ledger/dispatches/{DISPATCH_ID}")
    require_phrase(turn_archive.text, "Turn 1", failures, "/ledger/turns/1/dispatches")
    require_phrase(faction_archive.text, "Ashline Circle", failures, "/ledger/factions/ashline-circle/dispatches")

    forbid_terms(root.text, failures, "/")
    forbid_terms(archive.text, failures, "/ledger/dispatches")
    forbid_terms(detail.text, failures, f"/ledger/dispatches/{DISPATCH_ID}")
    forbid_terms(turn_archive.text, failures, "/ledger/turns/1/dispatches")
    forbid_terms(faction_archive.text, failures, "/ledger/factions/ashline-circle/dispatches")

    payload = {
        "contract_name": "chummer.black_ledger_dispatch_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "dispatch_id": DISPATCH_ID,
        "archive_url": f"{base_url}/ledger/dispatches",
        "detail_url": f"{base_url}/ledger/dispatches/{DISPATCH_ID}",
        "turn_archive_url": f"{base_url}/ledger/turns/1/dispatches",
        "faction_archive_url": f"{base_url}/ledger/factions/ashline-circle/dispatches",
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("BLACK_LEDGER_DISPATCH_E2E.generated.json"), payload)
    lines = [
        "# Black Ledger dispatch E2E",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {payload['base_url']}",
        f"- Dispatch: `{payload['dispatch_id']}`",
        f"- Status: `{payload['status']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "Dispatch archive, detail route, and homepage teaser are public-safe and receipt-backed."])
    write_text(completion_path("BLACK_LEDGER_DISPATCH_E2E.md"), "\n".join(lines))
    return 0 if not failures else 1


def run_source() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    controller = (repo_root / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")
    ledger_view = (repo_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Ledger.cshtml").read_text(encoding="utf-8")
    landing_view = (repo_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Landing.cshtml").read_text(encoding="utf-8")
    service = (repo_root / "Chummer.Run.Api" / "Services" / "Community" / "BlackLedgerPublicStatsService.cs").read_text(encoding="utf-8")

    failures: list[str] = []
    for phrase, body, label in [
        ('[HttpGet("/ledger/dispatches")]', controller, "controller"),
        ('[HttpGet("/ledger/dispatches/{dispatchId}")]', controller, "controller"),
        ('[HttpGet("/ledger/turns/{turn}/dispatches")]', controller, "controller"),
        ('[HttpGet("/ledger/factions/{factionId}/dispatches")]', controller, "controller"),
        ("Latest Black Ledger dispatch", landing_view, "landing"),
        ("Latest dispatches", ledger_view, "ledger_view"),
        ("Receipt-backed narrative, not free-floating lore.", ledger_view, "ledger_view"),
        ("drone_logistics_overlay", service, "service"),
    ]:
        require_phrase(body, phrase, failures, label)
    forbid_terms(landing_view, failures, "landing")
    forbid_terms(ledger_view, failures, "ledger_view")

    payload = {
        "contract_name": "chummer.black_ledger_dispatch_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": "source-only",
        "dispatch_id": DISPATCH_ID,
        "archive_url": "source:ledger_view",
        "detail_url": "source:service",
        "turn_archive_url": "source:controller",
        "faction_archive_url": "source:controller",
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("BLACK_LEDGER_DISPATCH_E2E.generated.json"), payload)
    write_text(completion_path("BLACK_LEDGER_DISPATCH_E2E.md"), "\n".join(["# Black Ledger dispatch E2E", "", f"- Generated: {payload['generated_at_utc']}", f"- Base URL: {payload['base_url']}", f"- Dispatch: `{payload['dispatch_id']}`", f"- Status: `{payload['status']}`"] + ([ "", "## Failures", *[f"- {item}" for item in failures] ] if failures else ["", "Dispatch source, archive, and route family are present."])))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))
    return run_source()


if __name__ == "__main__":
    raise SystemExit(main())
