#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COMPLETION = ROOT.parent / "_completion" / "all_horizons_missed_potential"

TARGETS = {
    "JACKPOINT_BRIEFING_E2E.generated.json": [
        "/jackpoint",
        "/jackpoint/briefings/emerald-sprawl-briefing.md",
        "/jackpoint/briefings/emerald-sprawl-briefing.json",
    ],
    "RUNSITE_PACKET_E2E.generated.json": [
        "/runsites",
        "/runsites/packs/redmond-dockyard-pack.md",
        "/runsites/packs/redmond-dockyard-pack.json",
    ],
    "PROPERTYQUARRY_ROUTE_PROOF.generated.json": [
        "/propertyquarry",
        "/propertyquarry/properties/northbound-research-lab.md",
        "/propertyquarry/properties/northbound-research-lab.json",
    ],
    "RUNBOOK_PRESS_PRIMER_E2E.generated.json": [
        "/runbook",
        "/runbook/primers/new-runner-primer.md",
        "/runbook/primers/new-runner-primer.json",
    ],
}


def fetch(url: str) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 Codex Wave6 Verifier"})
    with urlopen(request) as response:
        return response.getcode(), response.read().decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://chummer.run")
    args = parser.parse_args()
    COMPLETION.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for filename, paths in TARGETS.items():
        checks = []
        for path in paths:
            status, body = fetch(args.base_url.rstrip("/") + path)
            ok = status == 200 and len(body) > 20
            checks.append({"path": path, "status_code": status, "ok": ok})
            all_ok = all_ok and ok
        (COMPLETION / filename).write_text(json.dumps({"status": "pass" if all(item["ok"] for item in checks) else "not_ready", "checks": checks}, indent=2) + "\n", encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
