#!/usr/bin/env python3
"""Materialize source-bound prerequisites for the auxiliary Rafter/Pixefy gates."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path("/docker/chummercomplete")
COMPLETION_ROOT = WORKSPACE_ROOT / "_completion"
BOUNDARY_SOURCE = (
    WORKSPACE_ROOT
    / "chummer-design"
    / "products"
    / "chummer"
    / "RAFTER_PIXEFY_RELEASE_QA_BOUNDARY.md"
)
LTD_SOURCE = Path("/docker/EA/LTDs.md")
BOUNDARY_OUTPUT = (
    COMPLETION_ROOT
    / "rafter_pixefy_design"
    / "RAFTER_PIXEFY_DESIGN_BOUNDARY.generated.json"
)
LTD_OUTPUT_ROOT = COMPLETION_ROOT / "ltd_inventory"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def source_identity(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError:
        return {"path": str(path), "exists": False, "sha256": "", "size_bytes": 0}
    return {
        "path": str(path),
        "exists": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def boundary_payload() -> dict[str, Any]:
    text = BOUNDARY_SOURCE.read_text(encoding="utf-8") if BOUNDARY_SOURCE.is_file() else ""
    required_claims = {
        "auxiliary_not_authority": "auxiliary release-proof systems, not product authorities",
        "rafter_no_publish": "It may not publish changes, deploy, own release truth",
        "pixefy_no_private_data": "inspect private campaign data",
        "combined_requires_both": "both provider verifications are verified, both gates pass",
        "ready_token": "RAFTER_PIXEFY_QA_STACK_READY",
    }
    checks = {key: value in text for key, value in required_claims.items()}
    failures = [f"missing_boundary_claim:{key}" for key, passed in checks.items() if not passed]
    return {
        "contract_name": "chummer.rafter_pixefy_design_boundary.v1",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "source": source_identity(BOUNDARY_SOURCE),
        "checks": checks,
        "failures": failures,
        "authority": "auxiliary_qa_only",
        "may_publish_changes": False,
        "may_own_product_or_release_truth": False,
    }


def ltd_payload(provider: str) -> dict[str, Any]:
    text = LTD_SOURCE.read_text(encoding="utf-8") if LTD_SOURCE.is_file() else ""
    provider_row_present = f"| `{provider}` |" in text
    tier_present = provider_row_present and "License Tier 3 / highest AppSumo tier" in text
    auxiliary_boundary_present = (
        "auxiliary QA gate" in text
        if provider == "Pixefy"
        else "auxiliary security evidence only" in text
    )
    checks = {
        "provider_row_present": provider_row_present,
        "tier_present": tier_present,
        "auxiliary_boundary_present": auxiliary_boundary_present,
    }
    failures = [f"missing_ltd_contract:{key}" for key, passed in checks.items() if not passed]
    return {
        "contract_name": "ea.ltd_inventory.provider_entry.v1",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "provider": provider,
        "license_tier": "License Tier 3 / highest AppSumo tier",
        "source": source_identity(LTD_SOURCE),
        "checks": checks,
        "failures": failures,
        "runtime_authority": False,
    }


def main() -> int:
    receipts = {
        BOUNDARY_OUTPUT: boundary_payload(),
        LTD_OUTPUT_ROOT / "RAFTER_TIER3_LTDS_ENTRY.generated.json": ltd_payload("Rafter"),
        LTD_OUTPUT_ROOT / "PIXEFY_TIER3_LTDS_ENTRY.generated.json": ltd_payload("Pixefy"),
    }
    for path, payload in receipts.items():
        write_json(path, payload)
    passed = all(payload["status"] == "pass" for payload in receipts.values())
    print(f"rafter_pixefy_prerequisites:{'pass' if passed else 'fail'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
