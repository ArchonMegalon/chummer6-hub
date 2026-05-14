#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


DEFAULT_POLICY = "subscribed_or_only_user_preview_fallback"
LOCAL_INTERNAL_TOKEN = "black-ledger-local-token"
REMOTE_INTERNAL_TOKEN_ENV_KEYS = (
    "CHUMMER_BLACK_LEDGER_INTERNAL_API_TOKEN",
    "FLEET_INTERNAL_API_TOKEN",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run or send Black Ledger tick-news email delivery.")
    parser.add_argument("--world", default="emerald-sprawl-prelude")
    parser.add_argument("--turn", type=int, default=1)
    parser.add_argument("--policy", default=DEFAULT_POLICY)
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--send", action="store_true")
    return parser.parse_args()


def resolve_internal_token(base_url: str) -> str:
    if not base_url:
        return LOCAL_INTERNAL_TOKEN
    for key in REMOTE_INTERNAL_TOKEN_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    joined = ", ".join(REMOTE_INTERNAL_TOKEN_ENV_KEYS)
    raise RuntimeError(f"missing internal API token for remote tick-news send; set one of: {joined}")


def invoke(base_url: str, world: str, turn: int, policy: str, dry_run: bool, token: str) -> tuple[int, dict]:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/v1/ledger/worlds/{world}/tick-news/send",
        params={
            "turn": turn,
            "dryRun": "true" if dry_run else "false",
            "policy": policy,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    payload = response.json() if response.content else {}
    return response.status_code, payload


def seed_preview_store(path: Path) -> None:
    payload = {
        "users": [
            {
                "userId": "preview-ledger-user",
                "subjectId": "subject.preview.ledger",
                "displayName": "Preview Ledger User",
                "handle": "preview-ledger-user",
                "visibility": "private",
                "timezone": "UTC",
                "countryCode": "AT",
                "linkedPrincipals": [],
                "groupIds": [],
                "createdAtUtc": "2026-05-14T00:00:00Z",
                "updatedAtUtc": "2026-05-14T00:00:00Z",
                "email": "preview-ledger-user@example.com",
            }
        ],
        "groups": [],
        "joinCodes": [],
        "campaigns": [],
        "boostCodes": [],
        "sponsorSessions": [],
        "linkedIdentities": [],
        "channelLinks": [],
        "receipts": [],
        "ledgerEntries": [],
        "rewardEntries": [],
        "entitlementEntries": [],
        "badges": [],
        "userExperience": [],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def emit_receipts(status_code: int, payload: dict, world: str, turn: int, dry_run: bool, base_url: str) -> int:
    ok = status_code == 200 and payload.get("Status", payload.get("status")) not in {"failed_delivery", "suppressed_privacy_failed"}
    normalized = {
        "contract_name": "chummer.black_ledger_tick_news_send",
        "status": "pass" if ok else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "world_id": world,
        "turn": turn,
        "dry_run": dry_run,
        "http_status": status_code,
        "payload": payload,
    }
    write_json(completion_path("BLACK_LEDGER_TICK_NEWS_SEND.generated.json"), normalized)
    lines = [
        "# Black Ledger tick-news send",
        "",
        f"- Generated: {normalized['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- World: `{world}`",
        f"- Turn: `{turn}`",
        f"- Dry run: `{dry_run}`",
        f"- HTTP status: `{status_code}`",
        f"- Result: `{payload.get('Status', payload.get('status', 'unknown'))}`",
        f"- Recipients: `{payload.get('RecipientCount', payload.get('recipientCount', 0))}`",
    ]
    if payload.get("FailureReason") or payload.get("failureReason"):
        lines.append(f"- Failure reason: `{payload.get('FailureReason', payload.get('failureReason'))}`")
    write_text(completion_path("BLACK_LEDGER_TICK_NEWS_SEND.md"), "\n".join(lines))
    return 0 if ok else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        token = resolve_internal_token(args.base_url)
        status_code, payload = invoke(args.base_url, args.world, args.turn, args.policy, args.dry_run, token)
        return emit_receipts(status_code, payload, args.world, args.turn, args.dry_run, args.base_url.rstrip("/"))

    previous = os.environ.get("FLEET_INTERNAL_API_TOKEN")
    previous_store = os.environ.get("CHUMMER_COMMUNITY_STORE_PATH")
    os.environ["FLEET_INTERNAL_API_TOKEN"] = LOCAL_INTERNAL_TOKEN
    try:
        with tempfile.TemporaryDirectory(prefix="black-ledger-send-") as temp_root:
            store_path = Path(temp_root) / "community-store.json"
            seed_preview_store(store_path)
            os.environ["CHUMMER_COMMUNITY_STORE_PATH"] = str(store_path)
            try:
                with LocalHubApp() as app:
                    status_code, payload = invoke(app.base_url, args.world, args.turn, args.policy, args.dry_run, LOCAL_INTERNAL_TOKEN)
                    return emit_receipts(status_code, payload, args.world, args.turn, args.dry_run, app.base_url)
            finally:
                if previous_store is None:
                    os.environ.pop("CHUMMER_COMMUNITY_STORE_PATH", None)
                else:
                    os.environ["CHUMMER_COMMUNITY_STORE_PATH"] = previous_store
    finally:
        if previous is None:
            os.environ.pop("FLEET_INTERNAL_API_TOKEN", None)
        else:
            os.environ["FLEET_INTERNAL_API_TOKEN"] = previous


if __name__ == "__main__":
    raise SystemExit(main())
