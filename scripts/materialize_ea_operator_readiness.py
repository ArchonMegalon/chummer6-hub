#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ea_operator_readiness_contract as readiness_contract
from ea_live_ops_receipt_hygiene import (
    contains_secretish_key,
    json_from_text,
    public_href,
    public_source_ref,
    stderr_summary,
)

DEFAULT_OUTPUT_PATH = REPO_ROOT / ".codex-studio" / "published" / "EA_OPERATOR_READINESS.generated.json"
BRIDGE_SCRIPT = SCRIPT_DIR / "ea_live_ops.py"
CONTRACT_NAME = "chummer.ea_operator_readiness.v1"
REQUIRED_COMPONENT_KEYS = readiness_contract.REQUIRED_COMPONENT_KEYS
SOURCE_ID = "script:ea_live_ops.py"
SOURCE_RUNTIME = "ea_live_ops.bridge"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_probe(timeout_seconds: float) -> tuple[int, dict[str, Any], str, str]:
    completed = subprocess.run(
        [sys.executable, str(BRIDGE_SCRIPT), "probe-operator-readiness", "--timeout-seconds", str(timeout_seconds)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    payload = json_from_text(completed.stdout)
    return completed.returncode, payload, completed.stdout, completed.stderr


def _public_reason(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("pushbullet_token_missing:"):
        return "pushbullet_token_missing"
    return text


def _public_component(component: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key in (
        "key",
        "label",
        "observed_at",
        "probe_ok",
        "ready",
        "status",
        "reason",
        "source",
        "next_action",
        "next_action_href",
        "next_action_label",
        "next_action_method",
    ):
        if key in component:
            if key == "reason":
                public[key] = _public_reason(component[key])
            elif key == "next_action_href":
                public[key] = public_href(component[key])
            elif key == "source":
                public[key] = public_source_ref(component[key])
            else:
                public[key] = component[key]
    return public


def _public_next_actions(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    public_actions: list[dict[str, str]] = []
    for item in actions:
        public_actions.append(
            {
                "component_key": str(item.get("component_key") or "").strip(),
                "component_label": str(item.get("component_label") or "").strip(),
                "action": str(item.get("action") or "").strip(),
                "reason": _public_reason(item.get("reason")),
                "href": public_href(item.get("href")),
                "label": str(item.get("label") or "").strip(),
                "method": str(item.get("method") or "").strip(),
            }
        )
    return public_actions


def _normalized_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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
                "reason": str(component.get("reason") or "").strip(),
                "href": str(component.get("next_action_href") or "").strip(),
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


def _stdout_summary(
    *,
    returncode: int,
    payload: dict[str, Any],
    component_count: int,
    attention_required_count: int,
    blocked_count: int,
    probe_failed_count: int,
    runtime_status: str,
    runtime_ready: bool,
) -> str:
    parts = [
        f"returncode={returncode}",
        f"observed_at={str(payload.get('observed_at') or '').strip() or 'missing'}",
        f"probe_ok={str(bool(payload.get('probe_ok'))).lower()}",
        f"status={str(payload.get('status') or '').strip() or 'missing'}",
        f"ready={str(bool(payload.get('ready'))).lower()}",
        f"runtime_status={runtime_status or 'missing'}",
        f"runtime_ready={str(bool(runtime_ready)).lower()}",
        f"component_count={component_count}",
        f"attention_required_count={attention_required_count}",
        f"blocked_count={blocked_count}",
        f"probe_failed_count={probe_failed_count}",
        f"source={public_source_ref(payload.get('source')) or 'missing'}",
    ]
    return " ".join(parts)


def build_receipt(*, timeout_seconds: float) -> dict[str, Any]:
    receipt_updated_at = now_iso()
    returncode, payload, stdout, stderr = _run_probe(timeout_seconds)
    components = payload.get("components") if isinstance(payload.get("components"), list) else []
    normalized_components = [component for component in components if isinstance(component, dict)]
    public_components = [_public_component(component) for component in normalized_components]
    effective_components = [
        component for component in readiness_contract.effective_components(normalized_components) if isinstance(component, dict)
    ]
    computed_next_actions = readiness_contract.next_actions(normalized_components)
    computed_advisory_actions = readiness_contract.advisory_actions(normalized_components)
    public_advisory_actions = _public_next_actions(computed_advisory_actions)
    component_keys = readiness_contract.component_keys(normalized_components)
    effective_component_keys = readiness_contract.component_keys(effective_components)
    ready_component_keys = readiness_contract.ready_component_keys(normalized_components)
    steering_component_keys = _normalized_string_list(payload.get("steering_component_keys"))
    steering_components = (
        _select_components(effective_components, steering_component_keys) if steering_component_keys else list(effective_components)
    )
    if not steering_component_keys:
        steering_component_keys = readiness_contract.component_keys(steering_components)
    attention_component_keys = (
        _normalized_string_list(payload.get("attention_component_keys"))
        if "attention_component_keys" in payload
        else _subset_attention_component_keys(steering_components)
    )
    blocked_component_keys = (
        _normalized_string_list(payload.get("blocked_component_keys"))
        if "blocked_component_keys" in payload
        else _subset_blocked_component_keys(steering_components)
    )
    probe_failed_component_keys = (
        _normalized_string_list(payload.get("probe_failed_component_keys"))
        if "probe_failed_component_keys" in payload
        else _subset_probe_failed_component_keys(steering_components)
    )
    raw_next_actions = (
        [dict(item) for item in payload.get("next_actions") if isinstance(item, dict)]
        if isinstance(payload.get("next_actions"), list)
        else _subset_next_actions(steering_components, all_components=normalized_components)
    )
    public_next_actions = _public_next_actions(raw_next_actions)
    steering_key_set = set(steering_component_keys)
    supplemental_components = [
        component
        for component in effective_components
        if readiness_contract.component_key(component)
        and readiness_contract.component_key(component) not in steering_key_set
    ]
    supplemental_attention_component_keys = (
        _normalized_string_list(payload.get("supplemental_attention_component_keys"))
        if "supplemental_attention_component_keys" in payload
        else _subset_attention_component_keys(supplemental_components)
    )
    supplemental_blocked_component_keys = (
        _normalized_string_list(payload.get("supplemental_blocked_component_keys"))
        if "supplemental_blocked_component_keys" in payload
        else _subset_blocked_component_keys(supplemental_components)
    )
    supplemental_probe_failed_component_keys = (
        _normalized_string_list(payload.get("supplemental_probe_failed_component_keys"))
        if "supplemental_probe_failed_component_keys" in payload
        else _subset_probe_failed_component_keys(supplemental_components)
    )
    raw_supplemental_next_actions = (
        [dict(item) for item in payload.get("supplemental_next_actions") if isinstance(item, dict)]
        if isinstance(payload.get("supplemental_next_actions"), list)
        else _subset_next_actions(supplemental_components, all_components=normalized_components)
    )
    public_supplemental_next_actions = _public_next_actions(raw_supplemental_next_actions)
    runtime_blocking_findings = _subset_blocking_findings(steering_components)
    runtime_advisory_findings = _subset_advisory_findings(steering_components)
    runtime_status = (
        "blocked"
        if probe_failed_component_keys or blocked_component_keys
        else "degraded"
        if attention_component_keys
        else "ready"
    )
    runtime_ready = runtime_status == "ready"
    missing_component_keys = [key for key in REQUIRED_COMPONENT_KEYS if key not in component_keys]
    probe_ok = bool(payload.get("probe_ok")) and returncode == 0
    secret_leak_detected = contains_secretish_key(payload)

    structural_status = "pass" if probe_ok and not missing_component_keys and not secret_leak_detected else "fail"
    operator_status = str(payload.get("status") or "").strip()
    effective_status = operator_status or structural_status
    return {
        "contract_name": CONTRACT_NAME,
        "generated_at_utc": receipt_updated_at,
        "updated_at": receipt_updated_at,
        "status": structural_status,
        "structural_status": structural_status,
        "effective_status": effective_status,
        "source": SOURCE_ID,
        "source_runtime": SOURCE_RUNTIME,
        "observed_at": payload.get("observed_at"),
        "probe_ok": probe_ok,
        "operator_ready": bool(payload.get("ready")),
        "operator_status": operator_status,
        "runtime_ready": runtime_ready,
        "runtime_status": runtime_status,
        "attention_required_count": len(attention_component_keys),
        "blocked_count": len(blocked_component_keys),
        "probe_failed_count": len(probe_failed_component_keys),
        "blocking_count": len(runtime_blocking_findings),
        "advisory_count": len(runtime_advisory_findings),
        "component_count": len(normalized_components),
        "component_keys": component_keys,
        "effective_component_keys": effective_component_keys,
        "steering_component_keys": steering_component_keys,
        "ready_component_keys": ready_component_keys,
        "attention_component_keys": attention_component_keys,
        "blocked_component_keys": blocked_component_keys,
        "probe_failed_component_keys": probe_failed_component_keys,
        "blocking_findings": runtime_blocking_findings,
        "advisory_findings": runtime_advisory_findings,
        "supplemental_attention_count": len(supplemental_attention_component_keys),
        "supplemental_blocked_count": len(supplemental_blocked_component_keys),
        "supplemental_probe_failed_count": len(supplemental_probe_failed_component_keys),
        "supplemental_attention_component_keys": supplemental_attention_component_keys,
        "supplemental_blocked_component_keys": supplemental_blocked_component_keys,
        "supplemental_probe_failed_component_keys": supplemental_probe_failed_component_keys,
        "missing_component_keys": missing_component_keys,
        "next_action_component_keys": [
            str(item.get("component_key") or "").strip()
            for item in public_next_actions
            if isinstance(item, dict) and str(item.get("component_key") or "").strip()
        ],
        "next_actions": public_next_actions,
        "supplemental_next_action_component_keys": [
            str(item.get("component_key") or "").strip()
            for item in public_supplemental_next_actions
            if isinstance(item, dict) and str(item.get("component_key") or "").strip()
        ],
        "supplemental_next_actions": public_supplemental_next_actions,
        "advisory_action_component_keys": [
            str(item.get("component_key") or "").strip()
            for item in public_advisory_actions
            if isinstance(item, dict) and str(item.get("component_key") or "").strip()
        ],
        "advisory_actions": public_advisory_actions,
        "secret_leak_detected": secret_leak_detected,
        "components": public_components,
        "stdout_tail": _stdout_summary(
            returncode=returncode,
            payload=payload,
            component_count=len(normalized_components),
            attention_required_count=len(attention_component_keys),
            blocked_count=len(blocked_component_keys),
            probe_failed_count=len(probe_failed_component_keys),
            runtime_status=runtime_status,
            runtime_ready=runtime_ready,
        ),
        "stderr_tail": stderr_summary(stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize a secret-safe EA operator readiness receipt from the live runtime.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    payload = build_receipt(timeout_seconds=float(args.timeout_seconds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
