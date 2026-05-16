#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPLETION_ROOT = Path(
    os.environ.get(
        "CHUMMER_COMPLETION_DIR",
        REPO_ROOT.parent / "_completion" / "black_ledger_globe_faction_closure",
    )
)
VERDICT_PATH = COMPLETION_ROOT / "FINAL_BLACK_LEDGER_GLOBE_AND_FACTIONS_VERDICT.md"
MANAGEMENT_PATH = COMPLETION_ROOT / "BLACK_LEDGER_FACTION_MANAGEMENT.generated.json"
BASE_URL = os.environ.get("BASE_URL", "https://chummer.run").rstrip("/")

FACTIONS = [
    "glass-tower-compact",
    "rust-market-syndicate",
    "ashline-circle",
    "neon-docks-union",
    "ghostline-network",
    "barrens-free-wardens",
]


def ensure_dir() -> None:
    COMPLETION_ROOT.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_status(path: str) -> tuple[int, str]:
    request = Request(f"{BASE_URL}{path}", headers={"User-Agent": "codex-black-ledger-closure/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.getcode(), response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        return 0, str(exc)


def main() -> int:
    ensure_dir()

    frontdoor = load_json(COMPLETION_ROOT / "BLACK_LEDGER_FRONTDOOR_PROOF.generated.json")
    command_map = load_json(COMPLETION_ROOT / "BLACK_LEDGER_COMMAND_MAP_RENDER.generated.json")
    faction_pages = load_json(COMPLETION_ROOT / "BLACK_LEDGER_FACTION_PAGES.generated.json")
    no_noise = load_json(COMPLETION_ROOT / "BLACK_LEDGER_NO_NOISE_LINK_AUDIT.generated.json")

    route_checks: list[dict[str, Any]] = []
    failures: list[str] = []

    for path in ["/ledger", "/ledger/map", "/ledger/factions"] + [f"/ledger/factions/{slug}" for slug in FACTIONS]:
        status, body = fetch_status(path)
        route_checks.append({"path": path, "status": status})
        if status != 200:
            failures.append(f"{path} returned {status}")
        if path.startswith("/ledger/factions/") and "This page explains pressure, not people." not in body:
            failures.append(f"{path} missing privacy note")

    management_routes = [
        "/account/ledger/factions/ashline-circle",
        "/account/ledger/factions/ashline-circle/manage",
        "/account/ledger/factions/ashline-circle/stewards",
        "/account/ledger/factions/ashline-circle/private-lore",
    ]
    management_checks: list[dict[str, Any]] = []
    management_failures: list[str] = []
    for path in management_routes:
        status, body = fetch_status(path)
        management_checks.append({"path": path, "status": status})
        if status not in (200, 302):
            management_failures.append(f"{path} returned {status}")
        login_gate = "Sign in" in body or "/login?next=" in body or "Log in" in body
        if status == 200 and "Authenticated faction workspace" not in body and not login_gate:
            management_failures.append(f"{path} did not render faction workspace copy")

    management_payload = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "pass" if not management_failures else "fail",
        "base_url": BASE_URL,
        "routes": management_checks,
        "note": "302 is acceptable for unauthenticated access because these pages are authenticated-only.",
    }
    write_json(MANAGEMENT_PATH, management_payload)
    failures.extend(management_failures)

    artifact_statuses = {
        "frontdoor": frontdoor and frontdoor.get("status") == "pass",
        "command_map": command_map and command_map.get("status") == "pass",
        "faction_pages": faction_pages and faction_pages.get("status") == "pass",
        "no_noise": no_noise and no_noise.get("status") == "pass",
        "faction_management": management_payload["status"] == "pass",
    }
    if not artifact_statuses["frontdoor"]:
        failures.append("frontdoor proof missing or failed")
    if not artifact_statuses["command_map"]:
        failures.append("command map proof missing or failed")
    if not artifact_statuses["faction_pages"]:
        failures.append("faction pages proof missing or failed")
    if not artifact_statuses["no_noise"]:
        failures.append("no-noise proof missing or failed")

    verdict = "BLACK_LEDGER_GLOBE_AND_FACTIONS_READY" if not failures else "NOT_READY"
    VERDICT_PATH.write_text(
        "# Final Black Ledger Globe And Factions Verdict\n\n"
        f"Verdict: `{verdict}`\n\n"
        f"Base URL: `{BASE_URL}`\n\n"
        "Artifacts:\n"
        f"- frontdoor: `{'pass' if artifact_statuses['frontdoor'] else 'fail'}`\n"
        f"- command_map: `{'pass' if artifact_statuses['command_map'] else 'fail'}`\n"
        f"- faction_pages: `{'pass' if artifact_statuses['faction_pages'] else 'fail'}`\n"
        f"- faction_management: `{'pass' if artifact_statuses['faction_management'] else 'fail'}`\n"
        f"- no_noise: `{'pass' if artifact_statuses['no_noise'] else 'fail'}`\n\n"
        + ("Failures:\n" + "\n".join(f"- {failure}" for failure in failures) + "\n" if failures else "Failures: none\n"),
        encoding="utf-8",
    )
    print(verdict)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
