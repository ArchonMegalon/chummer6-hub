#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests


STORE_CONTAINER = "chummer6-hub-chummer-portal-1"
STORE_PATH = "/app/state/community-store.json"
RECIPIENT_USER_ID = "usr-ea8af6d123c0"
OUTPUT = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/BLACK_LEDGER_INBOX_AND_MAIL_ROLLOUT.generated.json")
INDIVIDUAL = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/BLACK_LEDGER_INDIVIDUAL_LEADER_DIGESTS.generated.json")
BUNDLE = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/BLACK_LEDGER_LEADER_DIGEST_BUNDLE.generated.json")
TURN1 = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/TIBOR_EXIT_GATE_EMAIL.generated.json")
EMAILIT_API_KEY = "secret_FiT7mnEllFcHlSSdOTDwBLjy78UmutFU"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_store() -> dict:
    text = subprocess.check_output(
        ["docker", "exec", STORE_CONTAINER, "/bin/sh", "-lc", f"cat {STORE_PATH}"],
        text=True,
    )
    return json.loads(text)


def lookup_provider_statuses(delivery_map: dict[str, str]) -> dict[str, dict]:
    matched: dict[str, dict] = {}
    page = 1
    while page <= 8 and len(matched) < len(delivery_map):
        response = requests.get(
            "https://api.emailit.com/v2/emails",
            headers={
                "Authorization": f"Bearer {EMAILIT_API_KEY}",
                "Accept": "application/json",
            },
            params={"page": page, "limit": 100},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json().get("data") or []
        if not payload:
            break
        for item in payload:
            meta = item.get("meta") or {}
            delivery_id = meta.get("delivery_id")
            if delivery_id in delivery_map:
                matched[delivery_id] = {
                    "label": delivery_map[delivery_id],
                    "email_id": item.get("id"),
                    "status": item.get("status"),
                    "to": item.get("to"),
                    "subject": item.get("subject"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                }
        page += 1
    return matched


def main() -> int:
    store = load_store()
    receipts = store.get("blackLedgerNewsDeliveryReceipts") or []
    inbox_entries = store.get("blackLedgerInboxEntries") or []
    user_receipts = [
        item for item in receipts
        if item.get("recipientUserId") == RECIPIENT_USER_ID
        and item.get("worldId") == "emerald-sprawl-prelude"
        and item.get("status") == "sent"
    ]
    user_entries = [
        item for item in inbox_entries
        if item.get("recipientUserId") == RECIPIENT_USER_ID
        and item.get("worldId") == "emerald-sprawl-prelude"
    ]

    bundle = load_json(BUNDLE)
    individual = load_json(INDIVIDUAL)
    turn1 = load_json(TURN1)
    delivery_map = {
        "delivery_0a6566bc027b0bc6": "turn1_newsreel",
        "delivery_5a40df341bb00eb9": "exit_gate_email",
        "delivery_5eed80f183a0aad7": "leader_bundle",
        "delivery_226f6b686b9a1947": "ashline-circle",
        "delivery_893d8cdd3dc90da8": "barrens-free-wardens",
        "delivery_eb102dea63692373": "ghostline-network",
        "delivery_f239553c74038806": "glass-tower-compact",
        "delivery_7764d446d65b9f11": "neon-docks-union",
        "delivery_90fa9cdfbd5d4a47": "rust-market-syndicate",
    }
    provider_statuses = lookup_provider_statuses(delivery_map)

    payload = {
        "contract_name": "black_ledger_inbox_and_mail_rollout",
        "generated_at_utc": now_iso(),
        "status": "pass",
        "live_store": {
            "receipt_count": len(receipts),
            "user_sent_receipt_count": len(user_receipts),
            "inbox_entry_count": len(inbox_entries),
            "user_inbox_entry_count": len(user_entries),
            "latest_user_receipt_event_keys": [item.get("eventKey") for item in user_receipts[:3]],
            "latest_user_inbox_kinds": [item.get("kind") for item in user_entries[:14]],
        },
        "turn1_newsreel_email": {
            "status": turn1.get("status"),
            "delivery_id": (((turn1.get("delivery") or {}).get("response") or {}).get("output_json") or {}).get("delivery_id")
                or ((turn1.get("delivery") or {}).get("response") or {}).get("target_ref")
                or (turn1.get("delivery") or {}).get("delivery_id"),
        },
        "leader_digest_bundle": {
            "status": bundle.get("status"),
            "delivery_id": (bundle.get("delivery") or {}).get("delivery_id"),
            "faction_count": ((bundle.get("content") or {}).get("faction_count")),
        },
        "individual_leader_digests": {
            "status": individual.get("status"),
            "delivery_count": individual.get("delivery_count"),
            "deliveries": [
                {
                    "faction_id": item.get("faction_id"),
                    "delivery_id": item.get("delivery_id"),
                }
                for item in (individual.get("deliveries") or [])
            ],
        },
        "provider_delivery_statuses": provider_statuses,
    }

    expected_kinds = {"newsreel", "validation", "promo", "leader_digest"}
    if not user_receipts:
        payload["status"] = "fail"
        payload["failure_reason"] = "missing_user_sent_receipt"
    elif len(user_entries) < 14 or not expected_kinds.issubset({item.get("kind") for item in user_entries}):
        payload["status"] = "fail"
        payload["failure_reason"] = "missing_expected_inbox_entries"
    elif individual.get("delivery_count") != 6:
        payload["status"] = "fail"
        payload["failure_reason"] = "missing_individual_deliveries"
    elif len(provider_statuses) != len(delivery_map) or any(item.get("status") != "delivered" for item in provider_statuses.values()):
        payload["status"] = "fail"
        payload["failure_reason"] = "provider_delivery_status_incomplete"

    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "user_inbox_entry_count": len(user_entries), "delivery_count": individual.get("delivery_count")}))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
