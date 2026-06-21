#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8091"
DEFAULT_MESSAGE = (
    "Mei, da bin ich jetzt aber froh, das ist nur ein WhatsApp-Test. "
    "Ich tipp langsam, aber es kommt an. Liebe Gruesse!"
)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def mask_phone(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return "[phone-redacted]" if len(digits) < 4 else f"[phone-redacted:*{digits[-4:]}]"


def run_readiness(recipient: str, include_ea_db: bool) -> tuple[int, dict[str, Any]]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "check_heyy_whatsapp_live_readiness.py"),
        "--recipient",
        recipient,
    ]
    if include_ea_db:
        cmd.append("--include-ea-db")
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "status": "blocked",
            "blockers": ["readiness_output_invalid"],
            "stdout": proc.stdout[-1000:],
            "stderr": proc.stderr[-1000:],
        }
    return proc.returncode, payload


def post_json(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http_{exc.code}:{response_body[:1000]}") from exc
    return json.loads(response_body)


def scrub_response(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "conversationId",
        "mode",
        "manualApprovalRequired",
        "autoSendAllowed",
        "personaId",
        "status",
        "failureReason",
        "approvalId",
        "draftId",
        "deliveryMode",
        "dryRun",
        "manualApprovalConfirmed",
        "operatorId",
        "recipientMasked",
        "deliveryRef",
        "createdAtUtc",
        "attemptedAtUtc",
    }
    return {key: value for key, value in payload.items() if key in allowed}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a single Heyy old-lady WhatsApp test message after live-readiness checks pass."
    )
    parser.add_argument("--recipient", required=True, help="Consenting WhatsApp test recipient.")
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--conversation-id", default="")
    parser.add_argument("--operator-id", default="operator")
    parser.add_argument("--dry-run", action="store_true", help="Exercise approval flow without requiring provider readiness.")
    parser.add_argument("--include-ea-db", action="store_true")
    args = parser.parse_args()

    env = load_env_file(Path(args.env_file))
    token = env.get("CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN") or env.get("FLEET_INTERNAL_API_TOKEN") or ""
    if not token.strip():
        print(json.dumps({"status": "blocked", "blockers": ["internal_token_missing"]}, indent=2))
        return 2

    readiness_code, readiness = run_readiness(args.recipient, include_ea_db=args.include_ea_db)
    if readiness.get("status") != "ready" and not args.dry_run:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "stage": "readiness",
                    "recipientMasked": mask_phone(args.recipient),
                    "readiness": readiness,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return readiness_code if readiness_code else 2

    conversation_id = args.conversation_id.strip() or f"heyy-wa-live-test-{int(time.time())}"
    base_url = args.api_base_url.rstrip("/")
    ingest = post_json(
        f"{base_url}/api/internal/heyy/scam-chat/messages",
        token,
        {
            "channel": "heyy",
            "conversationId": conversation_id,
            "counterpartyHandle": "consenting-test-fixture",
            "messageText": "Create one short old-lady WhatsApp integration test message. No links, no banking data.",
        },
    )
    approval = post_json(
        f"{base_url}/api/internal/heyy/scam-chat/conversations/{conversation_id}/approve",
        token,
        {
            "operatorId": args.operator_id,
            "deliveryMode": "whatsapp_approved",
            "recipient": args.recipient,
            "approvedText": args.message,
            "confirmManualApproval": True,
            "dryRun": bool(args.dry_run),
        },
    )

    print(
        json.dumps(
            {
                "status": approval.get("status"),
                "recipientMasked": approval.get("recipientMasked") or mask_phone(args.recipient),
                "dryRun": approval.get("dryRun"),
                "deliveryRef": approval.get("deliveryRef"),
                "failureReason": approval.get("failureReason"),
                "conversation": scrub_response(ingest),
                "approval": scrub_response(approval),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if str(approval.get("status", "")).startswith(("sent_", "dry_run_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
