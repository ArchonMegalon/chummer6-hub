#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import host_workload_runtime_health_contract as contract
from ea_live_ops_receipt_hygiene import public_href


DEFAULT_RECEIPT_PATH = REPO_ROOT / ".codex-studio" / "published" / "HOST_WORKLOAD_RUNTIME_HEALTH.generated.json"
CONTRACT_NAME = "chummer.host_workload_runtime_health.v1"
EXPECTED_SOURCE = "script:materialize_host_workload_runtime_health.py"
EXPECTED_SOURCE_RUNTIME = "host_workload.runtime_health"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def verify_receipt(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.is_file():
        verified = {
            "contract_name": CONTRACT_NAME,
            "path": str(path),
            "status": "fail",
            "failures": ["missing_receipt"],
            "structural_status": "missing",
            "effective_status": "missing",
            "runtime_ready": False,
            "runtime_status": "",
            "blocking_count": 0,
            "advisory_count": 0,
            "next_action_count": 0,
            "advisory_action_count": 0,
        }
        return verified, False

    try:
        payload = load_json(path)
    except json.JSONDecodeError:
        verified = {
            "contract_name": CONTRACT_NAME,
            "path": str(path),
            "status": "fail",
            "failures": ["malformed_receipt"],
            "structural_status": "invalid",
            "effective_status": "invalid",
            "runtime_ready": False,
            "runtime_status": "",
            "blocking_count": 0,
            "advisory_count": 0,
            "next_action_count": 0,
            "advisory_action_count": 0,
        }
        return verified, False

    failures: list[str] = []

    structural_status = str(payload.get("structural_status") or "").strip()
    effective_status = str(payload.get("effective_status") or "").strip()
    runtime_status = str(payload.get("runtime_status") or "").strip()
    blocking_findings = [str(item).strip() for item in payload.get("blocking_findings") or [] if str(item).strip()]
    advisory_findings = [str(item).strip() for item in payload.get("advisory_findings") or [] if str(item).strip()]
    expected_runtime_status = contract.runtime_status(blocking_findings, advisory_findings)
    expected_runtime_ready = contract.runtime_ready(blocking_findings, advisory_findings)
    expected_next_actions = contract.next_actions(blocking_findings)
    expected_advisory_actions = contract.advisory_actions(advisory_findings)
    expected_next_action_component_keys = [item["component_key"] for item in expected_next_actions]
    expected_advisory_action_component_keys = [item["component_key"] for item in expected_advisory_actions]

    if str(payload.get("contract_name") or "") != CONTRACT_NAME:
        failures.append("contract_name_mismatch")
    if str(payload.get("status") or "") != "pass":
        failures.append("status_not_pass")
    if str(payload.get("source") or "").strip() != EXPECTED_SOURCE:
        failures.append("source_mismatch")
    if str(payload.get("source_runtime") or "").strip() != EXPECTED_SOURCE_RUNTIME:
        failures.append("source_runtime_mismatch")
    if not str(payload.get("generated_at_utc") or "").strip():
        failures.append("generated_at_missing")
    if not str(payload.get("updated_at") or "").strip():
        failures.append("updated_at_missing")
    if not str(payload.get("observed_at") or "").strip():
        failures.append("observed_at_missing")
    if structural_status != str(payload.get("status") or ""):
        failures.append("structural_status_mismatch")
    if runtime_status != expected_runtime_status:
        failures.append("runtime_status_mismatch")
    if effective_status != runtime_status:
        failures.append("effective_status_mismatch")
    if bool(payload.get("runtime_ready")) != expected_runtime_ready:
        failures.append("runtime_ready_mismatch")
    if int(payload.get("blocking_count") or 0) != len(blocking_findings):
        failures.append("blocking_count_mismatch")
    if int(payload.get("advisory_count") or 0) != len(advisory_findings):
        failures.append("advisory_count_mismatch")
    if list(payload.get("next_action_component_keys") or []) != expected_next_action_component_keys:
        failures.append("next_action_component_keys_mismatch")
    if list(payload.get("advisory_action_component_keys") or []) != expected_advisory_action_component_keys:
        failures.append("advisory_action_component_keys_mismatch")
    if list(payload.get("next_actions") or []) != expected_next_actions:
        failures.append("next_actions_mismatch")
    if list(payload.get("advisory_actions") or []) != expected_advisory_actions:
        failures.append("advisory_actions_mismatch")
    if payload.get("secret_leak_detected") is not False:
        failures.append("secret_leak_detected")
    runtime_observation = payload.get("runtime_observation")
    if not isinstance(runtime_observation, dict):
        failures.append("runtime_observation_missing")
    elif not isinstance(runtime_observation.get("plex_internxt_mirror"), dict):
        failures.append("plex_internxt_mirror_observation_missing")
    if not isinstance(payload.get("failures"), list):
        failures.append("structural_failures_missing")

    for item in payload.get("next_actions") or []:
        if not isinstance(item, dict):
            continue
        component_key = str(item.get("component_key") or "").strip() or "unknown"
        href = str(item.get("href") or "").strip()
        if href and href != public_href(href):
            failures.append(f"unsafe_next_action_href:{component_key}")
    for item in payload.get("advisory_actions") or []:
        if not isinstance(item, dict):
            continue
        component_key = str(item.get("component_key") or "").strip() or "unknown"
        href = str(item.get("href") or "").strip()
        if href and href != public_href(href):
            failures.append(f"unsafe_advisory_action_href:{component_key}")

    verified = {
        "contract_name": CONTRACT_NAME,
        "path": str(path),
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "structural_status": structural_status,
        "effective_status": effective_status,
        "runtime_ready": bool(payload.get("runtime_ready")),
        "runtime_status": runtime_status,
        "blocking_count": int(payload.get("blocking_count") or 0),
        "advisory_count": int(payload.get("advisory_count") or 0),
        "next_action_count": len(payload.get("next_actions") or []),
        "advisory_action_count": len(payload.get("advisory_actions") or []),
    }
    return verified, not failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the host workload runtime-health receipt.")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    args = parser.parse_args()

    verified, passed = verify_receipt(args.receipt)
    print(json.dumps(verified, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
