#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / ".codex-studio" / "published" / "TABLE_PULSE_SCENARIO_REPLAY.generated.json"
FLEET_RECEIPT = Path("/docker/chummercomplete/.integrated/fleet/_completion/table_pulse/TABLE_PULSE_SCENARIO_REPLAY.generated.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Require a discoverable Table Pulse scenario replay and current live public lane proof.")
    parser.add_argument("--base-url", default="https://chummer.run")
    return parser.parse_args()


def run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "pass": completed.returncode == 0,
    }


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    live_lane = run_command(["python3", "scripts/verify_table_pulse_connected_lane_surface.py", "--base-url", base_url])
    pwa_runtime = run_command(["python3", "scripts/verify_pwa_notification_runtime.py", "--base-url", base_url])
    scenario_exists = FLEET_RECEIPT.is_file()
    payload = {
        "contract_name": "chummer.table_pulse_scenario_replay",
        "base_url": base_url,
        "status": "pass" if scenario_exists and live_lane["pass"] and pwa_runtime["pass"] else "fail",
        "scenario_receipt_path": str(FLEET_RECEIPT),
        "scenario_receipt_exists": scenario_exists,
        "live_lane": live_lane,
        "pwa_runtime": pwa_runtime,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if payload["status"] != "pass":
        raise SystemExit("table pulse scenario replay failed")
    print("table_pulse_scenario_replay:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
