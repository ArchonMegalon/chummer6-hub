#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
COMPLETION = ROOT.parent / "_completion" / "all_horizons_missed_potential"


def fetch(url: str) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 Codex Wave5 Verifier"})
    with urlopen(request) as response:
        return response.getcode(), response.read().decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5051")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    COMPLETION.mkdir(parents=True, exist_ok=True)

    continuity_targets = [
        "/play/continuity",
        "/play/continuity/receipts",
        "/play/continuity/receipts/nexus_claimed_install_posture.json",
    ]
    mobile_targets = [
        "/mobile",
        "/play",
        "/mobile/pwa.json",
    ]

    continuity_results = []
    for path in continuity_targets:
        status, body = fetch(base + path)
        continuity_results.append({"path": path, "status_code": status, "ok": status == 200, "contains": "NEXUS-PAN" if path == "/play/continuity" else None})
        if path == "/play/continuity" and "NEXUS-PAN continuity" not in body:
            continuity_results[-1]["ok"] = False

    mobile_results = []
    for path in mobile_targets:
        status, body = fetch(base + path)
        mobile_results.append({"path": path, "status_code": status, "ok": status == 200, "contains": "PWA" if path == "/mobile" else None})
        if path == "/mobile" and "Installable PWA posture" not in body:
            mobile_results[-1]["ok"] = False

    continuity_payload = {
        "horizon_id": "nexus_pan",
        "route": "/play/continuity",
        "state": "shipped_mvp",
        "status": "pass" if all(item["ok"] for item in continuity_results) else "not_ready",
        "checks": continuity_results,
    }
    mobile_payload = {
        "horizon_id": "nexus_pan",
        "route": "/mobile",
        "state": "shipped_mvp",
        "status": "pass" if all(item["ok"] for item in mobile_results) else "not_ready",
        "checks": mobile_results,
    }

    (COMPLETION / "NEXUS_PAN_CONTINUITY_E2E.generated.json").write_text(json.dumps(continuity_payload, indent=2) + "\n", encoding="utf-8")
    (COMPLETION / "MOBILE_PWA_E2E.generated.json").write_text(json.dumps(mobile_payload, indent=2) + "\n", encoding="utf-8")
    return 0 if continuity_payload["status"] == "pass" and mobile_payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
