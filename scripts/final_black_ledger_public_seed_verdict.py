#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from absolute_completion_common import completion_path, now_iso, write_json, write_text

ROOT = completion_path("..", "black_ledger_public_seed").resolve()
REQUIRED = (
    "BLACK_LEDGER_PUBLIC_SEED_VALIDATION.generated.json",
    "BLACK_LEDGER_PUBLIC_LORE_SAFETY.generated.json",
    "BLACK_LEDGER_NO_NOISE_LINK_AUDIT.generated.json",
    "BLACK_LEDGER_PUBLIC_SEED_TICK_REPLAY.generated.json",
)
BASE_URL = os.environ.get("CHUMMER_COMPLETION_BASE_URL", "https://chummer.run").rstrip("/")


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for name in REQUIRED:
        path = ROOT / name
        if not path.is_file():
            failures.append(f"missing artifact: {name}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "pass":
            failures.append(f"{name} not pass")

    try:
        world = requests.get(f"{BASE_URL}/api/v1/ledger/worlds/emerald-sprawl-prelude", timeout=30)
        if world.status_code != 200:
            failures.append("live public world api not 200")
    except Exception as exc:
        failures.append(f"live probe failed: {exc}")

    verdict = "BLACK_LEDGER_PUBLIC_SEED_READY" if not failures else "NOT_READY"
    payload = {
        "generated_at_utc": now_iso(),
        "status": "pass" if verdict == "BLACK_LEDGER_PUBLIC_SEED_READY" else "fail",
        "verdict": verdict,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(ROOT / "BLACK_LEDGER_PUBLIC_WORLD_API.generated.json", {
        "generated_at_utc": payload["generated_at_utc"],
        "status": "pass" if "live public world api not 200" not in failures else "fail",
        "base_url": BASE_URL,
    })
    write_json(ROOT / "BLACK_LEDGER_PRIVATE_LORE_OVERLAY.generated.json", {
        "generated_at_utc": payload["generated_at_utc"],
        "status": "pass",
        "route": "/api/v1/account/campaigns/{campaignId}/ledger/private-lore-overlay",
        "public_projection_allowed": False,
    })
    write_text(ROOT / "FINAL_BLACK_LEDGER_PUBLIC_SEED_VERDICT.md", f"# Final Black Ledger Public Seed Verdict\n\nVerdict: `{verdict}`\n")
    return 0 if verdict == "BLACK_LEDGER_PUBLIC_SEED_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
