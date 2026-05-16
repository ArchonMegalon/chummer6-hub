#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml


SOURCE = Path("/docker/chummercomplete/_completion/all_horizons_missed_potential/HORIZON_STATUS_MATRIX.generated.yaml")
OUT = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/HORIZON_PORTFOLIO_VERIFICATION.generated.json")
ALLOWED = {"shipped_mvp", "route_visible_preview_with_proof", "honestly_parked", "parked", "deleted_no_claim", "deleted/no longer claimed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    payload = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    rows = payload.get("horizons", [])
    invalid = [row for row in rows if row.get("state") not in ALLOWED]
    out = {
        "generated_at_utc": now_iso(),
        "contract_name": "chummer.horizon_portfolio_verdicts",
        "status": "pass" if not invalid and len(rows) > 0 else "fail",
        "source": str(SOURCE),
        "horizon_count": len(rows),
        "invalid_rows": invalid,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out))
    return 0 if out["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
