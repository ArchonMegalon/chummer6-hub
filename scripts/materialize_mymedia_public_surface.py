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

import mymedia_public_surface_contract as contract
from ea_live_ops_receipt_hygiene import (
    contains_secretish_key,
    json_from_text,
    public_href,
    public_source_ref,
    stderr_summary,
)

BRIDGE_SCRIPT = SCRIPT_DIR / "ea_live_ops.py"
DEFAULT_OUTPUT_PATH = REPO_ROOT / ".codex-studio" / "published" / "MYMEDIA_PUBLIC_SURFACE.generated.json"
CONTRACT_NAME = "chummer.ea_mymedia_public_surface.v1"
SOURCE_ID = "script:ea_live_ops.py"
SOURCE_RUNTIME = "ea_live_ops.bridge"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_probe(timeout_seconds: float) -> tuple[int, dict[str, Any], str, str]:
    completed = subprocess.run(
        [sys.executable, str(BRIDGE_SCRIPT), "probe-mymedia-alexa", "--format", "json", "--timeout-seconds", str(timeout_seconds)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    payload = json_from_text(completed.stdout)
    return completed.returncode, payload, completed.stdout, completed.stderr


def _stdout_summary(*, returncode: int, payload: dict[str, Any], runtime_status: str, runtime_ready: bool) -> str:
    parts = [
        f"returncode={returncode}",
        f"observed_at={str(payload.get('observed_at') or '').strip() or 'missing'}",
        f"probe_ok={str(bool(payload.get('probe_ok'))).lower()}",
        f"status={str(payload.get('status') or '').strip() or 'missing'}",
        f"ready={str(bool(payload.get('ready'))).lower()}",
        f"runtime_status={runtime_status or 'missing'}",
        f"runtime_ready={str(bool(runtime_ready)).lower()}",
        f"public_surface_status={str(payload.get('public_surface_status') or '').strip() or 'missing'}",
        f"public_surface_ready={str(bool(payload.get('public_surface_ready'))).lower()}",
        f"public_surface_scope={str(payload.get('public_surface_scope') or '').strip() or 'missing'}",
        f"source={public_source_ref(payload.get('source')) or 'missing'}",
    ]
    return " ".join(parts)


def build_receipt(*, timeout_seconds: float) -> dict[str, Any]:
    receipt_updated_at = now_iso()
    returncode, payload, stdout, stderr = _run_probe(timeout_seconds)
    public_surface_status = str(payload.get("public_surface_status") or "").strip()
    public_surface_reason = str(payload.get("public_surface_reason") or "").strip()
    public_surface_url = public_href(payload.get("public_surface_next_action_href"))
    public_surface_scope = str(payload.get("public_surface_scope") or "").strip()
    public_surface_ready = bool(payload.get("public_surface_ready"))
    public_surface_configured = bool(payload.get("public_surface_configured"))
    public_surface_http_status_code = int(payload.get("public_surface_http_status_code") or 0)
    public_surface_access_protected = bool(payload.get("public_surface_access_protected"))
    public_surface_cloudflare_blocked = bool(payload.get("public_surface_cloudflare_blocked"))
    secret_leak_detected = contains_secretish_key(payload)
    probe_payload_present = bool(payload)
    runtime_blocking_findings = contract.blocking_findings(
        public_surface_configured=public_surface_configured,
        public_surface_scope=public_surface_scope,
        public_surface_ready=public_surface_ready,
        public_surface_status=public_surface_status,
        public_surface_reason=public_surface_reason,
        public_surface_cloudflare_blocked=public_surface_cloudflare_blocked,
    )
    runtime_advisory_findings = contract.advisory_findings()
    runtime_status = contract.runtime_status(runtime_blocking_findings, runtime_advisory_findings)
    runtime_ready = contract.runtime_ready(runtime_blocking_findings, runtime_advisory_findings)
    pass_ready = (
        probe_payload_present
        and public_surface_configured
        and public_surface_scope == "public"
        and public_surface_ready
        and public_surface_status in contract.PASS_SURFACE_STATUSES
        and not public_surface_cloudflare_blocked
        and not secret_leak_detected
    )
    next_action = str(payload.get("public_surface_next_action") or "").strip()
    next_action_href = public_href(payload.get("public_surface_next_action_href"))
    next_action_label = str(payload.get("public_surface_next_action_label") or "").strip()
    next_action_method = str(payload.get("public_surface_next_action_method") or "").strip()
    next_actions: list[str] = []
    if next_action:
        pieces = [next_action]
        if next_action_label:
            pieces.append(f"label={next_action_label}")
        if next_action_href:
            pieces.append(f"href={next_action_href}")
        next_actions.append(" ".join(pieces))
    failures: list[str] = []
    if secret_leak_detected:
        failures.append("secret_leak_detected")
    if not probe_payload_present:
        failures.append("mymedia_public_surface_probe_payload_missing")
    failures.extend(runtime_blocking_findings)

    structural_status = "pass" if pass_ready else "fail"
    effective_status = public_surface_status or structural_status

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
        "probe_exit_code": int(returncode),
        "probe_payload_present": probe_payload_present,
        "probe_ok": bool(payload.get("probe_ok")),
        "secret_leak_detected": secret_leak_detected,
        "runtime_status": runtime_status,
        "runtime_ready": runtime_ready,
        "blocking_count": len(runtime_blocking_findings),
        "advisory_count": len(runtime_advisory_findings),
        "blocking_findings": runtime_blocking_findings,
        "advisory_findings": runtime_advisory_findings,
        "public_surface_configured": public_surface_configured,
        "public_surface_ready": public_surface_ready,
        "public_surface_status": public_surface_status,
        "public_surface_reason": public_surface_reason,
        "public_surface_url": public_surface_url,
        "public_surface_scope": public_surface_scope,
        "public_surface_http_status_code": public_surface_http_status_code,
        "public_surface_access_protected": public_surface_access_protected,
        "public_surface_cloudflare_blocked": public_surface_cloudflare_blocked,
        "public_surface_redirect_host": str(payload.get("public_surface_redirect_host") or "").strip(),
        "next_action": next_action,
        "next_action_href": next_action_href,
        "next_action_label": next_action_label,
        "next_action_method": next_action_method,
        "nextActions": next_actions,
        "mymedia_status": str(payload.get("status") or "").strip(),
        "mymedia_reason": str(payload.get("reason") or "").strip(),
        "connection_status": str(payload.get("connection_status") or "").strip(),
        "container_running": bool(payload.get("container_running")),
        "library_scan_pending": bool(payload.get("library_scan_pending")),
        "watch_folder_states": [
            str(item).strip()
            for item in payload.get("watch_folder_states") or []
            if str(item).strip()
        ],
        "tracks": int(payload.get("tracks") or 0),
        "failures": failures,
        "stdout_tail": _stdout_summary(
            returncode=returncode,
            payload=payload,
            runtime_status=runtime_status,
            runtime_ready=runtime_ready,
        ),
        "stderr_tail": stderr_summary(stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize a secret-safe receipt for the live My Media public surface."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    payload = build_receipt(timeout_seconds=float(args.timeout_seconds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    print(f"mymedia_public_surface:{payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
