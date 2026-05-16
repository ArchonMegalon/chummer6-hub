#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


FACTIONS = [
    "glass-tower-compact",
    "rust-market-syndicate",
    "ashline-circle",
    "neon-docks-union",
    "ghostline-network",
    "barrens-free-wardens",
]
OUT_DIR = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="advertisemind")
    parser.add_argument("--fallback", default="storyboard")
    parser.add_argument("--base-url", default="https://chummer.run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = args.base_url.rstrip("/")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    receipts = []
    overall = "pass"
    for faction in FACTIONS:
        r = requests.get(f"{base}/ledger/factions/{faction}/promo.json", timeout=30)
        payload = r.json() if r.ok else {}
        status = "pass" if r.status_code == 200 and payload.get("render_mode") == "fallback_static_storyboard" else "fail"
        if status != "pass":
            overall = "fail"
        receipt = {
            "generated_at_utc": now_iso(),
            "faction": faction,
            "provider": args.provider,
            "fallback": args.fallback,
            "status": status,
            "route": f"/ledger/factions/{faction}/promo.json",
            "provider_status": payload.get("provider_status"),
            "render_mode": payload.get("render_mode"),
            "formats": payload.get("formats"),
        }
        receipts.append(receipt)
        out = OUT_DIR / f"{faction.replace('-', '_').upper()}_VIDEO_RECEIPT.generated.json"
        out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    summary = OUT_DIR / "FACTION_VIDEO_BRIEFS.generated.json"
    summary.write_text(json.dumps({"generated_at_utc": now_iso(), "status": overall, "receipts": receipts}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": overall, "count": len(receipts)}))
    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
