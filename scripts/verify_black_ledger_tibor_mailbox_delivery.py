#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


RECIPIENT = "tibor.girschele@gmail.com"
OUTPUT = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/BLACK_LEDGER_TIBOR_MAILBOX_DELIVERY.generated.json")
EXPECTED_SUBJECTS = {
    "[Chummer] Black Ledger Turn 1 newsreel + faction promo rail": "newsreel_and_promo",
    "[Chummer] Black Ledger leader digest bundle": "leader_digest_bundle",
    "[Chummer] Ashline Circle leader digest": "ashline_circle",
    "[Chummer] Barrens Free Wardens leader digest": "barrens_free_wardens",
    "[Chummer] Ghostline Network leader digest": "ghostline_network",
    "[Chummer] Glass Tower Compact leader digest": "glass_tower_compact",
    "[Chummer] Neon Docks Union leader digest": "neon_docks_union",
    "[Chummer] Rust Market Syndicate leader digest": "rust_market_syndicate",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def emailit_api_key() -> str:
    value = os.environ.get("IDENTITY_EMAILIT_API_KEY", "").strip()
    if value:
        return value

    env_path = Path("/docker/chummercomplete/chummer.run-services/.env")
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("IDENTITY_EMAILIT_API_KEY="):
                _, _, raw = line.partition("=")
                token = raw.strip()
                if token:
                    return token

    raise RuntimeError("IDENTITY_EMAILIT_API_KEY is missing")


def fetch_latest_subject_statuses() -> dict[str, dict]:
    matched: dict[str, dict] = {}
    response = requests.get(
        "https://api.emailit.com/v2/emails",
        headers={
            "Authorization": f"Bearer {emailit_api_key()}",
            "Accept": "application/json",
        },
        params={"page": 1, "limit": 100},
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("data") or []
    for item in items:
        if item.get("to") != RECIPIENT:
            continue
        subject = item.get("subject")
        if subject not in EXPECTED_SUBJECTS:
            continue
        existing = matched.get(subject)
        candidate = {
            "label": EXPECTED_SUBJECTS[subject],
            "subject": subject,
            "status": item.get("status"),
            "delivery_id": (item.get("meta") or {}).get("delivery_id"),
            "email_id": item.get("id"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        if existing is None or str(candidate["created_at"]) > str(existing["created_at"]):
            matched[subject] = candidate
    return matched


def main() -> int:
    matched = fetch_latest_subject_statuses()
    payload = {
        "contract_name": "black_ledger_tibor_mailbox_delivery",
        "generated_at_utc": now_iso(),
        "recipient": RECIPIENT,
        "status": "pass",
        "expected_count": len(EXPECTED_SUBJECTS),
        "matched_count": len(matched),
        "deliveries": list(matched.values()),
    }
    if len(matched) != len(EXPECTED_SUBJECTS) or any(item.get("status") != "delivered" for item in matched.values()):
        payload["status"] = "fail"
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "matched_count": len(matched)}))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
