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

import mymedia_public_surface_contract as contract
from ea_live_ops_receipt_hygiene import public_href, public_source_ref

DEFAULT_RECEIPT_PATH = REPO_ROOT / ".codex-studio" / "published" / "MYMEDIA_PUBLIC_SURFACE.generated.json"
CONTRACT_NAME = "chummer.ea_mymedia_public_surface.v1"
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


def verify(path: Path, *, require_pass: bool = False) -> tuple[bool, dict[str, Any]]:
    if not path.is_file():
        result = {
            "contract_name": CONTRACT_NAME,
            "path": str(path),
            "status": "fail",
            "issues": ["missing_receipt"],
            "require_pass": require_pass,
            "structural_status": "missing",
            "effective_status": "missing",
            "runtime_status": "",
            "runtime_ready": False,
            "surface_ready": False,
            "surface_status": "",
            "surface_url": "",
            "surface_scope": "",
            "blocking_count": 0,
            "advisory_count": 0,
            "http_status_code": 0,
            "cloudflare_blocked": False,
            "mymedia_status": "",
        }
        return False, result

    try:
        payload = load_json(path)
    except json.JSONDecodeError:
        result = {
            "contract_name": CONTRACT_NAME,
            "path": str(path),
            "status": "fail",
            "issues": ["malformed_receipt"],
            "require_pass": require_pass,
            "structural_status": "invalid",
            "effective_status": "invalid",
            "runtime_status": "",
            "runtime_ready": False,
            "surface_ready": False,
            "surface_status": "",
            "surface_url": "",
            "surface_scope": "",
            "blocking_count": 0,
            "advisory_count": 0,
            "http_status_code": 0,
            "cloudflare_blocked": False,
            "mymedia_status": "",
        }
        return False, result

    issues: list[str] = []
    structural_status = str(payload.get("structural_status") or "").strip()
    effective_status = str(payload.get("effective_status") or "").strip()

    if str(payload.get("contract_name") or "").strip() != CONTRACT_NAME:
        issues.append("contract_name_mismatch")
    if str(payload.get("source") or "").strip() != EXPECTED_SOURCE:
        issues.append("source_mismatch")
    if structural_status != str(payload.get("status") or "").strip():
        issues.append("structural_status_mismatch")
    if payload.get("secret_leak_detected") is not False:
        issues.append("secret_leak_detected")
    if not str(payload.get("generated_at_utc") or "").strip():
        issues.append("generated_at_missing")
    if not str(payload.get("updated_at") or "").strip():
        issues.append("updated_at_missing")
    if not str(payload.get("observed_at") or "").strip():
        issues.append("observed_at_missing")
    if str(payload.get("source_runtime") or "").strip() != EXPECTED_SOURCE_RUNTIME:
        issues.append("source_runtime_mismatch")
    if payload.get("probe_payload_present") is not True:
        issues.append("probe_payload_missing")

    public_surface_status = str(payload.get("public_surface_status") or "").strip()
    public_surface_ready = payload.get("public_surface_ready") is True
    public_surface_access_protected = payload.get("public_surface_access_protected") is True
    public_surface_cloudflare_blocked = payload.get("public_surface_cloudflare_blocked") is True
    public_surface_scope = str(payload.get("public_surface_scope") or "").strip()
    public_surface_http_status_code = int(payload.get("public_surface_http_status_code") or 0)
    public_surface_url = str(payload.get("public_surface_url") or "").strip()
    next_action_href = str(payload.get("next_action_href") or "").strip()
    next_action = str(payload.get("next_action") or "").strip()
    expected_runtime_blocking_findings = contract.blocking_findings(
        public_surface_configured=payload.get("public_surface_configured") is True,
        public_surface_scope=public_surface_scope,
        public_surface_ready=public_surface_ready,
        public_surface_status=public_surface_status,
        public_surface_reason=str(payload.get("public_surface_reason") or "").strip(),
        public_surface_cloudflare_blocked=public_surface_cloudflare_blocked,
    )
    expected_runtime_advisory_findings = contract.advisory_findings()
    expected_runtime_status = contract.runtime_status(expected_runtime_blocking_findings, expected_runtime_advisory_findings)
    expected_runtime_ready = contract.runtime_ready(expected_runtime_blocking_findings, expected_runtime_advisory_findings)
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

    if effective_status != (public_surface_status or str(payload.get("status") or "").strip()):
        issues.append("effective_status_mismatch")
    if runtime_status != expected_runtime_status:
        issues.append("runtime_status_mismatch")
    if runtime_ready != expected_runtime_ready:
        issues.append("runtime_ready_mismatch")
    if reported_blocking_count != len(expected_runtime_blocking_findings):
        issues.append("blocking_count_mismatch")
    if reported_advisory_count != len(expected_runtime_advisory_findings):
        issues.append("advisory_count_mismatch")
    if runtime_blocking_findings != expected_runtime_blocking_findings:
        issues.append("blocking_findings_mismatch")
    if runtime_advisory_findings != expected_runtime_advisory_findings:
        issues.append("advisory_findings_mismatch")

    if public_surface_ready and public_surface_status not in contract.PASS_SURFACE_STATUSES:
        issues.append("public_surface_ready_status_mismatch")
    if public_surface_access_protected and public_surface_status != "access_protected":
        issues.append("public_surface_access_protected_status_mismatch")
    if public_surface_cloudflare_blocked and public_surface_ready:
        issues.append("public_surface_cloudflare_blocked_while_ready")
    if public_surface_url and public_surface_scope != "public":
        issues.append("public_surface_url_scope_mismatch")
    if public_surface_url and public_surface_url != public_href(public_surface_url):
        issues.append("public_surface_url_not_sanitized")
    if next_action_href and next_action_href != public_href(next_action_href):
        issues.append("next_action_href_not_sanitized")
    if public_surface_http_status_code < 0:
        issues.append("public_surface_http_status_code_invalid")
    stdout_source = stdout_tail_source(payload.get("stdout_tail"))
    if stdout_source and stdout_source != public_source_ref(stdout_source):
        issues.append("stdout_tail_source_not_sanitized")

    if require_pass:
        if str(payload.get("status") or "").strip() != "pass":
            issues.append("receipt_status_not_pass")
        if payload.get("probe_ok") is not True:
            issues.append("probe_not_ok")
        if payload.get("public_surface_configured") is not True:
            issues.append("public_surface_not_configured")
        if public_surface_scope != "public":
            issues.append("public_surface_scope_not_public")
        if not public_surface_ready:
            issues.append("public_surface_not_ready")
        if public_surface_status not in contract.PASS_SURFACE_STATUSES:
            issues.append("public_surface_status_not_allowed")
        if public_surface_cloudflare_blocked:
            issues.append("public_surface_blocked_by_cloudflare")
        if not public_surface_url:
            issues.append("public_surface_url_missing")
        if next_action:
            issues.append("next_action_still_present")

    result = {
        "contract_name": CONTRACT_NAME,
        "path": str(path),
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "require_pass": require_pass,
        "structural_status": structural_status,
        "effective_status": effective_status,
        "runtime_status": runtime_status,
        "runtime_ready": runtime_ready,
        "surface_ready": public_surface_ready,
        "surface_status": public_surface_status,
        "surface_url": public_surface_url,
        "surface_scope": public_surface_scope,
        "blocking_count": reported_blocking_count,
        "advisory_count": reported_advisory_count,
        "http_status_code": public_surface_http_status_code,
        "cloudflare_blocked": public_surface_cloudflare_blocked,
        "mymedia_status": str(payload.get("mymedia_status") or "").strip(),
    }
    return not issues, result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the My Media public surface receipt.")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()

    passed, result = verify(args.receipt, require_pass=bool(args.require_pass))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
