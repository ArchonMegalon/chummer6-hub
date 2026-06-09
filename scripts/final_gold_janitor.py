#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
COMPLETION_ROOT = Path("/docker/chummercomplete/_completion")
ARTIFACT_ROOT_NAME = os.environ.get("CHUMMER_FINAL_GOLD_ARTIFACT_ROOT", "full_product_reaudit_v20")
ARTIFACT_ROOT = COMPLETION_ROOT / ARTIFACT_ROOT_NAME
DEFAULT_BASE_URL = os.environ.get("CHUMMER_FINAL_GOLD_BASE_URL", "https://chummer.run")
RECRAWL_MAX_AGE_HOURS = 24

REQUIRED_RECEIPTS = {
    "live_public_web_recrawl": PUBLISHED_ROOT / "LIVE_PUBLIC_WEB_RECRAWL.generated.json",
    "rule_authority_minimum_coverage": PUBLISHED_ROOT / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json",
    "provider_proof_discoverability": PUBLISHED_ROOT / "PROVIDER_PROOF_DISCOVERABILITY.generated.json",
    "black_ledger_live_media_proof": PUBLISHED_ROOT / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json",
    "table_pulse_scenario_replay": PUBLISHED_ROOT / "TABLE_PULSE_SCENARIO_REPLAY.generated.json",
}

MATERIALIZERS = [
    ["python3", "scripts/verify_live_public_web_recrawl.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/verify_rules_authority_minimum_coverage.py"],
    ["python3", "scripts/verify_provider_proof_discoverability.py"],
    ["python3", "scripts/verify_black_ledger_live_media_proof.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/verify_table_pulse_scenario_replay.py", "--base-url", DEFAULT_BASE_URL],
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def generated_at_is_fresh(value: str, max_age_hours: int) -> bool:
    if not value:
        return False
    try:
        generated_at = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return False
    return generated_at >= datetime.now(UTC) - timedelta(hours=max_age_hours)


def run_materializers() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in MATERIALIZERS:
        completed = subprocess.run(
            command,
            cwd=RUN_SERVICES_ROOT,
            capture_output=True,
            text=True,
        )
        results.append(
            {
                "command": " ".join(command),
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )
    return results


def build_payload(command_results: list[dict[str, Any]]) -> dict[str, Any]:
    required_gates: dict[str, Any] = {}
    failures: list[str] = []
    for name, path in REQUIRED_RECEIPTS.items():
        payload = load_json(path)
        generated_at = str(payload.get("generated_at_utc") or payload.get("generatedAt") or "")
        is_fresh = generated_at_is_fresh(generated_at, RECRAWL_MAX_AGE_HOURS) if name == "live_public_web_recrawl" else True
        passed = path.is_file() and payload.get("status") == "pass" and is_fresh
        if not passed:
            reason = f"{name} missing" if not path.is_file() else f"{name} failed"
            if path.is_file() and name == "live_public_web_recrawl" and not is_fresh:
                reason = f"{name} stale"
            failures.append(reason)
        required_gates[name] = {
            "path": str(path),
            "exists": path.is_file(),
            "status": payload.get("status", "missing"),
            "generated_at_utc": generated_at,
            "fresh_within_hours": RECRAWL_MAX_AGE_HOURS if name == "live_public_web_recrawl" else None,
            "pass": passed,
        }

    for result in command_results:
        if result["returncode"] != 0:
            failures.append(f"materializer failed: {result['command']}")

    return {
        "contract_name": "chummer.final_gold_janitor",
        "generated_at_utc": now_iso(),
        "scope": "full_estate_v20",
        "artifact_root": f"_completion/{ARTIFACT_ROOT_NAME}",
        "durable_artifacts_required": True,
        "live_backed_required": True,
        "live_recrawl_required": True,
        "recrawl_max_age_hours": RECRAWL_MAX_AGE_HOURS,
        "status": "pass" if not failures else "fail",
        "verdict": "GOLD_READY" if not failures else "NOT_GOLD",
        "required_gates": required_gates,
        "materializers": command_results,
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the final gold verdict from committed, fresh, fail-closed receipts.")
    parser.add_argument("--skip-materializers", action="store_true", help="Read receipts without regenerating them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command_results = [] if args.skip_materializers else run_materializers()
    payload = build_payload(command_results)
    write_json(PUBLISHED_ROOT / "FINAL_GOLD_JANITOR.generated.json", payload)
    write_json(ARTIFACT_ROOT / "FINAL_GOLD_JANITOR.generated.json", payload)
    write_text(PUBLISHED_ROOT / "FINAL_GOLD_VERDICT.md", payload["verdict"])
    write_text(ARTIFACT_ROOT / "FINAL_GOLD_VERDICT.md", payload["verdict"])
    if payload["status"] != "pass":
        raise SystemExit("final gold janitor failed")
    print("final_gold_janitor:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
