#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COMPLETION = ROOT.parent / "_completion" / "all_horizons_missed_potential"

TARGETS = {
    "COMMUNITY_OPEN_RUN_E2E.generated.json": {
        "horizon_id": "community_hub",
        "route": "/community",
        "state": "shipped_mvp",
        "checks": [
            ("/community", "Community Hub"),
            ("/community/open-runs/open_run_board.md", "# Open run board"),
            ("/community/open-runs/open_run_board.json", "\"status\": \"live\""),
        ],
    },
    "CREATOR_OS_PUBLICATION_E2E.generated.json": {
        "horizon_id": "creator_os",
        "route": "/creator",
        "state": "shipped_mvp",
        "checks": [
            ("/creator", "Creator OS"),
            ("/creator/packets/publication_board.md", "# Publication board"),
            ("/creator/packets/publication_board.json", "\"status\": \"live\""),
        ],
    },
    "RUNNER_PASSPORT_E2E.generated.json": {
        "horizon_id": "runner_passport",
        "route": "/passport",
        "state": "shipped_mvp",
        "checks": [
            ("/passport", "Runner Passport"),
            ("/passport/receipts/runner_return_posture.md", "# Runner return posture"),
            ("/passport/receipts/runner_return_posture.json", "\"status\": \"live\""),
        ],
    },
}


def fetch(url: str) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 Codex Wave7 Verifier"})
    with urlopen(request) as response:
        return response.getcode(), response.read().decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://chummer.run")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    COMPLETION.mkdir(parents=True, exist_ok=True)

    all_ok = True
    for filename, config in TARGETS.items():
        checks = []
        for path, needle in config["checks"]:
            status, body = fetch(base + path)
            ok = status == 200 and needle in body
            checks.append(
                {
                    "path": path,
                    "status_code": status,
                    "ok": ok,
                    "contains": needle,
                }
            )
            all_ok = all_ok and ok

        payload = {
            "horizon_id": config["horizon_id"],
            "route": config["route"],
            "state": config["state"],
            "status": "pass" if all(item["ok"] for item in checks) else "not_ready",
            "checks": checks,
        }
        (COMPLETION / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
