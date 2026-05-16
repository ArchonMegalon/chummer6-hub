#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect")


def main() -> int:
    receipts = sorted(ROOT.glob("*_VIDEO_RECEIPT.generated.json"))
    payload = {
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z"),
        "contract_name": "faction_video_public_safety",
        "status": "pass",
        "receipts": [],
    }
    for receipt_path in receipts:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        payload["receipts"].append(receipt)
        if receipt.get("status") != "pass":
            payload["status"] = "fail"
    out = ROOT / "FACTION_VIDEO_PUBLIC_SAFETY.generated.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
