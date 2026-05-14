#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import requests

from absolute_completion_common import completion_path, now_iso, write_json, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the Anarchy public preview route family and content.")
    parser.add_argument("--base-url", default="", help="Optional live/local base URL. Defaults to source-only verification.")
    return parser.parse_args()


def require_phrase(body: str, phrase: str, failures: list[str], label: str) -> None:
    if phrase not in body:
        failures.append(f"{label} missing required phrase: {phrase}")


def run_source() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    controller = (repo_root / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")
    view = (repo_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Anarchy.cshtml").read_text(encoding="utf-8")
    service = (repo_root / "Chummer.Run.Api" / "Services" / "Community" / "AnarchyPreviewService.cs").read_text(encoding="utf-8")
    failures: list[str] = []

    for phrase, body, label in [
        ('[HttpGet("/anarchy")]', controller, "controller"),
        ('[HttpGet("/play/anarchy")]', controller, "controller"),
        ('[HttpGet("/ledger/anarchy")]', controller, "controller"),
        ("Not an SR5 skin. Not an SR6 mode.", view, "view"),
        ("Portable runner packet", view, "view"),
        ("shadowrun_anarchy", service, "service"),
        ("Playable preview", service, "service"),
    ]:
        require_phrase(body, phrase, failures, label)

    payload = {
        "contract_name": "chummer.anarchy_preview_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": "source-only",
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("ANARCHY_PREVIEW_E2E.generated.json"), payload)
    write_text(completion_path("ANARCHY_PREVIEW_E2E.md"), "\n".join([
        "# Anarchy preview E2E",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Status: `{payload['status']}`",
        *([] if not failures else ["", "## Failures", *[f"- {item}" for item in failures]])
    ]))
    return 0 if not failures else 1


def run_live(base_url: str) -> int:
    failures: list[str] = []
    for route, phrase in [
        ("/anarchy", "Dedicated ruleset preview"),
        ("/play/anarchy", "Anarchy play shell"),
        ("/ledger/anarchy", "Anarchy consequence lane"),
    ]:
        response = requests.get(f"{base_url}{route}", timeout=30)
        response.raise_for_status()
        require_phrase(response.text, phrase, failures, route)

    payload = {
        "contract_name": "chummer.anarchy_preview_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("ANARCHY_PREVIEW_E2E.generated.json"), payload)
    write_text(completion_path("ANARCHY_PREVIEW_E2E.md"), "\n".join([
        "# Anarchy preview E2E",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {payload['base_url']}",
        f"- Status: `{payload['status']}`",
        *([] if not failures else ["", "## Failures", *[f"- {item}" for item in failures]])
    ]))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run_live(args.base_url.rstrip("/"))
    return run_source()


if __name__ == "__main__":
    raise SystemExit(main())
