#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_WORLD_ID = "emerald-sprawl-prelude"
DEFAULT_FACTIONS = [
    ("ashline-circle", "Ashline Circle", "Ashline Circle enters the city through visible pressure, clean public signals, and one promise the board can verify next turn.", "This ad lane can dramatize posture, but it cannot outrun the actual world tick, dispatch receipts, or faction file."),
    ("barrens-free-wardens", "Barrens Free Wardens", "The Wardens sell order where nobody else can hold it, and every promise is framed as protection under pressure.", "This lane can spotlight stability and grit, but it stays subordinate to the same public-safe world turn receipts."),
    ("ghostline-network", "Ghostline Network", "Ghostline trades in movement, secrecy, and timing, but only through signals the board can actually verify.", "This promo can dramatize stealth and routing, but it cannot invent private intel or outrun the ledger."),
    ("glass-tower-compact", "Glass Tower Compact", "The Compact projects executive calm while every pressure move remains measurable from the outside.", "This lane can sell control and prestige, but it must stay anchored to the public turn packet."),
    ("neon-docks-union", "Neon Docks Union", "The Union frames leverage through throughput, labor, and visible chokepoints the city can feel next turn.", "This ad lane can dramatize momentum, but it cannot overclaim beyond the verified world tick."),
    ("rust-market-syndicate", "Rust Market Syndicate", "The Syndicate enters through salvage, barter, and pressure that climbs in plain sight rather than hidden lore.", "This lane can lean into grit and hustle, but it remains bounded by the public-safe dispatch history."),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill durable Black Ledger inbox entries from existing sent receipts.")
    parser.add_argument("store_path", help="Path to community-store.json")
    parser.add_argument("--recipient-user-id", default="usr-ea8af6d123c0")
    parser.add_argument("--world-id", default=DEFAULT_WORLD_ID)
    return parser.parse_args()


def build_entries(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    recipient_user_id = receipt["recipientUserId"]
    world_id = receipt["worldId"]
    turn = int(receipt["toTurn"])
    tick_receipt_id = receipt["tickReceiptId"]
    created_at = receipt["createdAtUtc"]
    entries: list[dict[str, Any]] = [
        {
            "entryId": f"blinbox_news_{recipient_user_id}_{tick_receipt_id}",
            "recipientUserId": recipient_user_id,
            "worldId": world_id,
            "turn": turn,
            "kind": "newsreel",
            "eyebrow": "World turn",
            "heading": "Turn 0 -> Turn 1 world brief is live",
            "summary": "Receipt-backed world-turn newsreel is ready for review and replay.",
            "href": f"/ledger/turns/{turn}",
            "ctaLabel": "Open newsreel",
            "statusLabel": "Delivered",
            "sourceReceiptId": receipt["receiptId"],
            "createdAtUtc": created_at,
        },
        {
            "entryId": f"blinbox_validation_{recipient_user_id}_{tick_receipt_id}",
            "recipientUserId": recipient_user_id,
            "worldId": world_id,
            "turn": turn,
            "kind": "validation",
            "eyebrow": "Validation",
            "heading": "World-tick validation packet",
            "summary": "Validate the inbox-safe turn packet against the same receipt-backed world-turn truth.",
            "href": "/account/ledger/worldtick/validation",
            "ctaLabel": "Open validation",
            "statusLabel": "Ready",
            "sourceReceiptId": receipt["receiptId"],
            "createdAtUtc": created_at,
        },
    ]
    for faction_id, public_name, hook, promise in DEFAULT_FACTIONS:
        entries.append(
            {
                "entryId": f"blinbox_promo_{recipient_user_id}_{tick_receipt_id}_{faction_id}",
                "recipientUserId": recipient_user_id,
                "worldId": world_id,
                "turn": turn,
                "kind": "promo",
                "eyebrow": "Faction promo",
                "heading": f"{public_name} storyboard rail",
                "summary": f"{hook} {promise}",
                "href": f"/ledger/factions/{faction_id}/promo",
                "ctaLabel": "Open promo rail",
                "statusLabel": "Public-safe",
                "sourceReceiptId": receipt["receiptId"],
                "createdAtUtc": created_at,
            }
        )
        entries.append(
            {
                "entryId": f"blinbox_leader_{recipient_user_id}_{tick_receipt_id}_{faction_id}",
                "recipientUserId": recipient_user_id,
                "worldId": world_id,
                "turn": turn,
                "kind": "leader_digest",
                "eyebrow": "Leader brief",
                "heading": f"{public_name} leader validation",
                "summary": "Personalized faction-leader readout and validation handoff for the current world turn.",
                "href": f"/account/ledger/factions/{faction_id}/leader-briefing",
                "ctaLabel": "Open leader brief",
                "statusLabel": "Personalized",
                "sourceReceiptId": receipt["receiptId"],
                "createdAtUtc": created_at,
            }
        )
    return entries


def main() -> int:
    args = parse_args()
    store_path = Path(args.store_path)
    data = json.loads(store_path.read_text(encoding="utf-8"))
    receipts = data.get("blackLedgerNewsDeliveryReceipts") or []
    inbox_entries = data.get("blackLedgerInboxEntries") or []

    if any(
        entry.get("recipientUserId") == args.recipient_user_id and entry.get("worldId") == args.world_id
        for entry in inbox_entries
    ):
        print(json.dumps({"status": "noop", "reason": "entries_already_present", "inbox_entry_count": len(inbox_entries)}))
        return 0

    matching_receipts = [
        receipt for receipt in receipts
        if receipt.get("recipientUserId") == args.recipient_user_id
        and receipt.get("worldId") == args.world_id
        and receipt.get("status") == "sent"
    ]
    added = 0
    existing_ids = {entry.get("entryId") for entry in inbox_entries}
    for receipt in matching_receipts:
        for entry in build_entries(receipt):
            if entry["entryId"] in existing_ids:
                continue
            inbox_entries.append(entry)
            existing_ids.add(entry["entryId"])
            added += 1

    inbox_entries.sort(key=lambda item: item.get("createdAtUtc", ""), reverse=True)
    data["blackLedgerInboxEntries"] = inbox_entries
    store_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "receipts_used": len(matching_receipts), "entries_added": added, "inbox_entry_count": len(inbox_entries)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
