#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COMPLETION = ROOT.parent / "_completion" / "all_horizons_missed_potential"


def fetch(url: str) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 Codex Wave8 Verifier"})
    with urlopen(request) as response:
        return response.getcode(), response.read().decode("utf-8", errors="replace")


def write_json(name: str, payload: dict) -> None:
    COMPLETION.mkdir(parents=True, exist_ok=True)
    (COMPLETION / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://chummer.run")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    ghostwire_targets = [
        ("/ghostwire", "GHOSTWIRE after-action"),
        ("/ghostwire/after-action/replay_timeline.md", "# Replay timeline"),
        ("/ghostwire/after-action/replay_timeline.json", "\"status\": \"live\""),
    ]
    ghostwire_checks = []
    for path, needle in ghostwire_targets:
        status, body = fetch(base + path)
        ghostwire_checks.append({"path": path, "status_code": status, "ok": status == 200 and needle in body, "contains": needle})
    ghostwire_payload = {
        "horizon_id": "ghostwire",
        "route": "/ghostwire",
        "state": "shipped_mvp",
        "status": "pass" if all(item["ok"] for item in ghostwire_checks) else "not_ready",
        "checks": ghostwire_checks,
    }
    write_json("GHOSTWIRE_AFTER_ACTION_E2E.generated.json", ghostwire_payload)

    foundry_targets = [
        ("/exports/foundry", "Honestly parked"),
    ]
    foundry_checks = []
    for path, needle in foundry_targets:
        status, body = fetch(base + path)
        foundry_checks.append({"path": path, "status_code": status, "ok": status == 200 and needle in body, "contains": needle})
    foundry_payload = {
        "horizon_id": "foundry_handoff",
        "route": "/exports/foundry",
        "state": "honestly_parked",
        "status": "parked" if all(item["ok"] for item in foundry_checks) else "not_ready",
        "checks": foundry_checks,
    }
    write_json("FOUNDRY_HANDOFF_E2E.generated.json", foundry_payload)

    anarchy_targets = [
        ("/anarchy", "Shadowrun Anarchy"),
        ("/play/anarchy", "Anarchy play shell"),
        ("/ledger/anarchy", "Anarchy consequence lane"),
        ("/anarchy/export/runner.json", "\"ruleset_id\": \"shadowrun_anarchy\""),
        ("/anarchy/receipts/explain.json", "\"state\": \"shipped_mvp\""),
    ]
    anarchy_checks = []
    for path, needle in anarchy_targets:
        status, body = fetch(base + path)
        anarchy_checks.append({"path": path, "status_code": status, "ok": status == 200 and needle in body, "contains": needle})
    anarchy_payload = {
        "horizon_id": "anarchy",
        "route": "/anarchy",
        "state": "shipped_mvp",
        "status": "pass" if all(item["ok"] for item in anarchy_checks) else "not_ready",
        "checks": anarchy_checks,
    }
    write_json("ANARCHY_RULESET_PREVIEW_E2E.generated.json", anarchy_payload)

    return 0 if ghostwire_payload["status"] == "pass" and foundry_payload["status"] == "parked" and anarchy_payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
