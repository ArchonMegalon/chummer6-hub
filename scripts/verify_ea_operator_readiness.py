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

import ea_operator_readiness_contract as readiness_contract
from ea_live_ops_receipt_hygiene import public_href, public_source_ref

DEFAULT_RECEIPT_PATH = REPO_ROOT / ".codex-studio" / "published" / "EA_OPERATOR_READINESS.generated.json"
CONTRACT_NAME = "chummer.ea_operator_readiness.v1"
REQUIRED_COMPONENT_KEYS = set(readiness_contract.REQUIRED_COMPONENT_KEYS)
EXPECTED_SOURCE = "script:ea_live_ops.py"
EXPECTED_SOURCE_RUNTIME = "ea_live_ops.bridge"


def stdout_tail_source(stdout_tail: str) -> str:
    for token in str(stdout_tail or "").split():
        if token.startswith("source="):
            return token.split("=", 1)[1].strip()
    return ""


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _normalized_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _public_reason(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("pushbullet_token_missing:"):
        return "pushbullet_token_missing"
    return text


def _select_components(components: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    if not keys:
        return []
    key_set = set(keys)
    return [
        component
        for component in components
        if readiness_contract.component_key(component) and readiness_contract.component_key(component) in key_set
    ]


def _subset_attention_component_keys(components: list[dict[str, Any]]) -> list[str]:
    return [
        readiness_contract.component_key(component)
        for component in components
        if readiness_contract.component_key(component) and readiness_contract.component_requires_attention(component)
    ]


def _subset_blocked_component_keys(components: list[dict[str, Any]]) -> list[str]:
    return [
        readiness_contract.component_key(component)
        for component in components
        if readiness_contract.component_key(component) and readiness_contract.component_counts_as_blocked(component)
    ]


def _subset_probe_failed_component_keys(components: list[dict[str, Any]]) -> list[str]:
    return [
        readiness_contract.component_key(component)
        for component in components
        if readiness_contract.component_key(component) and not bool(component.get("probe_ok"))
    ]


def _subset_next_actions(
    components: list[dict[str, Any]],
    *,
    all_components: list[dict[str, Any]],
) -> list[dict[str, str]]:
    has_pairing_qr_action = readiness_contract.pairing_qr_recovery_present(all_components)
    actions: list[dict[str, str]] = []
    for component in components:
        if not readiness_contract.component_requires_attention(component):
            continue
        component_key = readiness_contract.component_key(component)
        action = str(component.get("next_action") or "").strip()
        if not component_key or not action:
            continue
        if has_pairing_qr_action and component_key == "whatsapp" and action == "scan_whatsapp_web_qr":
            continue
        actions.append(
            {
                "component_key": component_key,
                "component_label": str(component.get("label") or "").strip(),
                "action": action,
                "reason": _public_reason(component.get("reason")),
                "href": public_href(component.get("next_action_href")),
                "label": str(component.get("next_action_label") or "").strip(),
                "method": str(component.get("next_action_method") or "").strip(),
            }
        )
    return actions


def _subset_blocking_findings(components: list[dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for component in components:
        component_key = readiness_contract.component_key(component)
        if not component_key:
            continue
        status = str(component.get("status") or "").strip() or "unknown"
        if not bool(component.get("probe_ok")):
            findings.append(f"probe_failed:{component_key}:{status}")
            continue
        if readiness_contract.component_counts_as_blocked(component):
            findings.append(f"blocked:{component_key}:{status}")
    return findings


def _subset_advisory_findings(components: list[dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for component in components:
        component_key = readiness_contract.component_key(component)
        if not component_key or not readiness_contract.component_requires_attention(component):
            continue
        if not bool(component.get("probe_ok")) or readiness_contract.component_counts_as_blocked(component):
            continue
        status = str(component.get("status") or "").strip() or "unknown"
        findings.append(f"attention:{component_key}:{status}")
    return findings


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
            "operator_ready": False,
            "operator_status": "",
            "blocking_count": 0,
            "advisory_count": 0,
            "attention_required_count": 0,
            "blocked_count": 0,
            "probe_failed_count": 0,
            "component_keys": [],
            "effective_component_keys": [],
            "attention_component_keys": [],
            "blocked_component_keys": [],
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
            "operator_ready": False,
            "operator_status": "",
            "blocking_count": 0,
            "advisory_count": 0,
            "attention_required_count": 0,
            "blocked_count": 0,
            "probe_failed_count": 0,
            "component_keys": [],
            "effective_component_keys": [],
            "attention_component_keys": [],
            "blocked_component_keys": [],
            "next_action_count": 0,
            "advisory_action_count": 0,
        }
        return verified, False

    failures: list[str] = []

    structural_status = str(payload.get("structural_status") or "").strip()
    effective_status = str(payload.get("effective_status") or "").strip()
    operator_status = str(payload.get("operator_status") or "").strip()

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
    if effective_status != (operator_status or str(payload.get("status") or "")):
        failures.append("effective_status_mismatch")
    if payload.get("probe_ok") is not True:
        failures.append("probe_not_ok")
    if payload.get("secret_leak_detected") is not False:
        failures.append("secret_leak_detected")

    components = [item for item in payload.get("components") or [] if isinstance(item, dict)]
    component_keys = set(payload.get("component_keys") or [])
    missing = sorted(REQUIRED_COMPONENT_KEYS - component_keys)
    if missing:
        failures.append(f"missing_components:{','.join(missing)}")

    effective_components = [
        component for component in readiness_contract.effective_components(components) if isinstance(component, dict)
    ]
    expected_component_keys = readiness_contract.component_keys(components)
    expected_effective_component_keys = readiness_contract.component_keys(effective_components)
    expected_ready_component_keys = readiness_contract.ready_component_keys(components)
    steering_component_keys = _normalized_string_list(payload.get("steering_component_keys"))
    steering_components = (
        _select_components(effective_components, steering_component_keys) if steering_component_keys else list(effective_components)
    )
    if not steering_component_keys:
        steering_component_keys = readiness_contract.component_keys(steering_components)
    steering_key_set = set(steering_component_keys)
    supplemental_components = [
        component
        for component in effective_components
        if readiness_contract.component_key(component)
        and readiness_contract.component_key(component) not in steering_key_set
    ]
    expected_attention_component_keys = _subset_attention_component_keys(steering_components)
    expected_blocked_component_keys = _subset_blocked_component_keys(steering_components)
    expected_probe_failed_component_keys = _subset_probe_failed_component_keys(steering_components)
    expected_runtime_blocking_findings = _subset_blocking_findings(steering_components)
    expected_runtime_advisory_findings = _subset_advisory_findings(steering_components)
    expected_runtime_status = (
        "blocked"
        if expected_probe_failed_component_keys or expected_blocked_component_keys
        else "degraded"
        if expected_attention_component_keys
        else "ready"
    )
    expected_runtime_ready = expected_runtime_status == "ready"
    expected_next_actions = _subset_next_actions(steering_components, all_components=components)
    expected_advisory_actions = readiness_contract.advisory_actions(components)
    expected_next_action_component_keys = [item["component_key"] for item in expected_next_actions]
    expected_advisory_action_component_keys = [item["component_key"] for item in expected_advisory_actions]
    expected_supplemental_attention_component_keys = _subset_attention_component_keys(supplemental_components)
    expected_supplemental_blocked_component_keys = _subset_blocked_component_keys(supplemental_components)
    expected_supplemental_probe_failed_component_keys = _subset_probe_failed_component_keys(supplemental_components)
    expected_supplemental_next_actions = _subset_next_actions(supplemental_components, all_components=components)
    expected_supplemental_next_action_component_keys = [item["component_key"] for item in expected_supplemental_next_actions]

    runtime_status = str(payload.get("runtime_status") or "").strip() or expected_runtime_status
    runtime_ready = bool(payload.get("runtime_ready")) if "runtime_ready" in payload else expected_runtime_ready
    runtime_blocking_findings = (
        [str(item).strip() for item in payload.get("blocking_findings") or [] if str(item).strip()]
        if "blocking_findings" in payload
        else expected_runtime_blocking_findings
    )
    runtime_advisory_findings = (
        [str(item).strip() for item in payload.get("advisory_findings") or [] if str(item).strip()]
        if "advisory_findings" in payload
        else expected_runtime_advisory_findings
    )
    reported_blocking_count = (
        int(payload.get("blocking_count") or 0) if "blocking_count" in payload else len(expected_runtime_blocking_findings)
    )
    reported_advisory_count = (
        int(payload.get("advisory_count") or 0) if "advisory_count" in payload else len(expected_runtime_advisory_findings)
    )

    if runtime_status != expected_runtime_status:
        failures.append("runtime_status_mismatch")
    if runtime_ready != expected_runtime_ready:
        failures.append("runtime_ready_mismatch")

    if components:
        for component in components:
            component_key = str(component.get("key") or "").strip() or "unknown"
            href = str(component.get("next_action_href") or "").strip()
            if href and href != public_href(href):
                failures.append(f"unsafe_component_next_action_href:{component_key}")
            source = str(component.get("source") or "").strip()
            if source and source != public_source_ref(source):
                failures.append(f"unsafe_component_source:{component_key}")
        if list(payload.get("component_keys") or []) != expected_component_keys:
            failures.append("component_keys_mismatch")
        if list(payload.get("effective_component_keys") or []) != expected_effective_component_keys:
            failures.append("effective_component_keys_mismatch")
        if "steering_component_keys" in payload and list(payload.get("steering_component_keys") or []) != steering_component_keys:
            failures.append("steering_component_keys_mismatch")
        if list(payload.get("ready_component_keys") or []) != expected_ready_component_keys:
            failures.append("ready_component_keys_mismatch")
        if list(payload.get("attention_component_keys") or []) != expected_attention_component_keys:
            failures.append("attention_component_keys_mismatch")
        if list(payload.get("blocked_component_keys") or []) != expected_blocked_component_keys:
            failures.append("blocked_component_keys_mismatch")
        if list(payload.get("probe_failed_component_keys") or []) != expected_probe_failed_component_keys:
            failures.append("probe_failed_component_keys_mismatch")
        if "supplemental_attention_component_keys" in payload and list(payload.get("supplemental_attention_component_keys") or []) != expected_supplemental_attention_component_keys:
            failures.append("supplemental_attention_component_keys_mismatch")
        if "supplemental_blocked_component_keys" in payload and list(payload.get("supplemental_blocked_component_keys") or []) != expected_supplemental_blocked_component_keys:
            failures.append("supplemental_blocked_component_keys_mismatch")
        if "supplemental_probe_failed_component_keys" in payload and list(payload.get("supplemental_probe_failed_component_keys") or []) != expected_supplemental_probe_failed_component_keys:
            failures.append("supplemental_probe_failed_component_keys_mismatch")
        if int(payload.get("attention_required_count") or 0) != len(expected_attention_component_keys):
            failures.append("attention_required_count_mismatch")
        if int(payload.get("blocked_count") or 0) != len(expected_blocked_component_keys):
            failures.append("blocked_count_mismatch")
        if int(payload.get("probe_failed_count") or 0) != len(expected_probe_failed_component_keys):
            failures.append("probe_failed_count_mismatch")
        if "supplemental_attention_count" in payload and int(payload.get("supplemental_attention_count") or 0) != len(expected_supplemental_attention_component_keys):
            failures.append("supplemental_attention_count_mismatch")
        if "supplemental_blocked_count" in payload and int(payload.get("supplemental_blocked_count") or 0) != len(expected_supplemental_blocked_component_keys):
            failures.append("supplemental_blocked_count_mismatch")
        if "supplemental_probe_failed_count" in payload and int(payload.get("supplemental_probe_failed_count") or 0) != len(expected_supplemental_probe_failed_component_keys):
            failures.append("supplemental_probe_failed_count_mismatch")
        if reported_blocking_count != len(expected_runtime_blocking_findings):
            failures.append("blocking_count_mismatch")
        if reported_advisory_count != len(expected_runtime_advisory_findings):
            failures.append("advisory_count_mismatch")
        if runtime_blocking_findings != expected_runtime_blocking_findings:
            failures.append("blocking_findings_mismatch")
        if runtime_advisory_findings != expected_runtime_advisory_findings:
            failures.append("advisory_findings_mismatch")
        if list(payload.get("next_action_component_keys") or []) != expected_next_action_component_keys:
            failures.append("next_action_component_keys_mismatch")
        if list(payload.get("next_actions") or []) != expected_next_actions:
            failures.append("next_actions_mismatch")
        if "supplemental_next_action_component_keys" in payload and list(payload.get("supplemental_next_action_component_keys") or []) != expected_supplemental_next_action_component_keys:
            failures.append("supplemental_next_action_component_keys_mismatch")
        if "supplemental_next_actions" in payload and list(payload.get("supplemental_next_actions") or []) != expected_supplemental_next_actions:
            failures.append("supplemental_next_actions_mismatch")
        if list(payload.get("advisory_action_component_keys") or []) != expected_advisory_action_component_keys:
            failures.append("advisory_action_component_keys_mismatch")
        if list(payload.get("advisory_actions") or []) != expected_advisory_actions:
            failures.append("advisory_actions_mismatch")
        for item in payload.get("next_actions") or []:
            if not isinstance(item, dict):
                continue
            component_key = str(item.get("component_key") or "").strip() or "unknown"
            href = str(item.get("href") or "").strip()
            if href and href != public_href(href):
                failures.append(f"unsafe_next_action_href:{component_key}")
        for item in payload.get("supplemental_next_actions") or []:
            if not isinstance(item, dict):
                continue
            component_key = str(item.get("component_key") or "").strip() or "unknown"
            href = str(item.get("href") or "").strip()
            if href and href != public_href(href):
                failures.append(f"unsafe_supplemental_next_action_href:{component_key}")
        for item in payload.get("advisory_actions") or []:
            if not isinstance(item, dict):
                continue
            component_key = str(item.get("component_key") or "").strip() or "unknown"
            href = str(item.get("href") or "").strip()
            if href and href != public_href(href):
                failures.append(f"unsafe_advisory_action_href:{component_key}")
    stdout_source = stdout_tail_source(payload.get("stdout_tail"))
    if stdout_source and stdout_source != public_source_ref(stdout_source):
        failures.append("unsafe_stdout_tail_source")

    verified = {
        "contract_name": CONTRACT_NAME,
        "path": str(path),
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "structural_status": structural_status,
        "effective_status": effective_status,
        "runtime_ready": runtime_ready,
        "runtime_status": runtime_status,
        "operator_ready": bool(payload.get("operator_ready")),
        "operator_status": operator_status,
        "blocking_count": reported_blocking_count,
        "advisory_count": reported_advisory_count,
        "attention_required_count": int(payload.get("attention_required_count") or 0),
        "blocked_count": int(payload.get("blocked_count") or 0),
        "probe_failed_count": int(payload.get("probe_failed_count") or 0),
        "component_keys": sorted(component_keys),
        "effective_component_keys": expected_effective_component_keys,
        "steering_component_keys": steering_component_keys,
        "attention_component_keys": expected_attention_component_keys,
        "blocked_component_keys": expected_blocked_component_keys,
        "next_action_count": len(payload.get("next_actions") or []),
        "supplemental_next_action_count": len(payload.get("supplemental_next_actions") or []),
        "advisory_action_count": len(payload.get("advisory_actions") or []),
    }
    return verified, not failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the local EA operator readiness receipt.")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    args = parser.parse_args()

    verified, passed = verify_receipt(args.receipt)
    print(json.dumps(verified, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
