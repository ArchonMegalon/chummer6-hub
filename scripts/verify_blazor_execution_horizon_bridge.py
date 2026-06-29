#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
PUBLISHED = RUN_SERVICES_ROOT / ".codex-studio" / "published"
PRESENTATION_PUBLISHED = Path(
    os.environ.get(
        "CHUMMER_PRESENTATION_PUBLISHED_ROOT",
        WORKSPACE_ROOT / "chummer-presentation" / ".codex-studio" / "published",
    )
)
OUTPUT_PATH = Path(
    os.environ.get(
        "CHUMMER_BLAZOR_EXECUTION_HORIZON_BRIDGE_PATH",
        PUBLISHED / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json",
    )
)

MOBILE_PWA_PROOF = PUBLISHED / "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"
BLAZOR_PWA_PROOF = PRESENTATION_PUBLISHED / "BLAZOR_PWA_PUBLIC_EDGE_PROOF.generated.json"
BLAZOR_EXECUTION_HORIZON = PRESENTATION_PUBLISHED / "BLAZOR_PUBLIC_EDGE_EXECUTION_HORIZON.generated.json"
EXPECTED_CONTRACT = "chummer.blazor_execution_horizon_bridge"


def load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, f"missing JSON proof: {path}"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON proof {path}: {exc}"
    if not isinstance(loaded, dict):
        return {}, f"proof root must be an object: {path}"
    return loaded, None


def normalize_status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "").strip().lower()


def horizon_by_id(horizon_payload: dict[str, Any], horizon_id: str) -> dict[str, Any]:
    for row in horizon_payload.get("horizons") or []:
        if isinstance(row, dict) and str(row.get("id") or "").strip() == horizon_id:
            return row
    return {}


def main() -> int:
    failures: list[str] = []
    mobile, mobile_error = load_json(MOBILE_PWA_PROOF)
    blazor_pwa, blazor_pwa_error = load_json(BLAZOR_PWA_PROOF)
    horizon, horizon_error = load_json(BLAZOR_EXECUTION_HORIZON)

    for error in [mobile_error, blazor_pwa_error, horizon_error]:
        if error:
            failures.append(error)

    mobile_pass = normalize_status(mobile) in {"pass", "passed", "ready"}
    blazor_pwa_pass = normalize_status(blazor_pwa) in {"pass", "passed", "ready"}
    horizon_pass = normalize_status(horizon) in {"pass", "passed", "ready"}
    near_term = horizon_by_id(horizon, "near_term_hosted_smoke_execution")
    mid_term = horizon_by_id(horizon, "mid_term_full_live_public_edge_execution_matrix")
    boundary = horizon.get("boundary") if isinstance(horizon.get("boundary"), dict) else {}
    near_term_proven = str(near_term.get("status") or "").strip() == "proven"
    mid_term_status = str(mid_term.get("status") or "").strip() or "missing"
    no_smoke_to_full = boundary.get("does_not_upgrade_smoke_to_full") is True
    full_requires_full_receipt = boundary.get("full_scope_requires_current_passing_full_receipt") is True

    if not mobile_pass:
        failures.append("Hub mobile/PWA public projection proof is not passing.")
    if not blazor_pwa_pass:
        failures.append("Blazor hosted PWA public-edge proof is not passing.")
    if not horizon_pass:
        failures.append("Blazor hosted execution horizon receipt is not passing.")
    if not near_term_proven:
        failures.append("Blazor near-term smoke execution horizon is not proven.")
    if not no_smoke_to_full:
        failures.append("Blazor execution horizon does not explicitly block smoke-to-full promotion.")
    if not full_requires_full_receipt:
        failures.append("Blazor execution horizon does not require a current passing full-scope receipt for full-matrix promotion.")

    verdict = (
        "mobile_pwa_and_blazor_smoke_integrated_full_matrix_not_proven"
        if mid_term_status != "proven"
        else "mobile_pwa_and_blazor_full_matrix_integrated"
    )
    payload = {
        "contract_name": EXPECTED_CONTRACT,
        "status": "fail" if failures else "pass",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "verdict": verdict,
        "proofs": {
            "hub_mobile_pwa_public_projection": {
                "path": str(MOBILE_PWA_PROOF),
                "status": normalize_status(mobile) or "missing",
                "contract_name": str(mobile.get("contract_name") or "").strip(),
                "pass": mobile_pass,
            },
            "blazor_hosted_pwa_public_edge": {
                "path": str(BLAZOR_PWA_PROOF),
                "status": normalize_status(blazor_pwa) or "missing",
                "contract_name": str(blazor_pwa.get("contract_name") or "").strip(),
                "route_lane": str(blazor_pwa.get("route_lane") or "").strip(),
                "pass": blazor_pwa_pass,
            },
            "blazor_hosted_execution_horizon": {
                "path": str(BLAZOR_EXECUTION_HORIZON),
                "status": normalize_status(horizon) or "missing",
                "contract_name": str(horizon.get("contract_name") or "").strip(),
                "near_term_smoke_status": str(near_term.get("status") or "").strip() or "missing",
                "mid_term_full_matrix_status": mid_term_status,
                "mid_term_full_required_workflow_family_count": mid_term.get("required_workflow_family_count", 0),
                "mid_term_full_covered_workflow_family_count": mid_term.get("covered_workflow_family_count", 0),
                "pass": horizon_pass and near_term_proven and no_smoke_to_full and full_requires_full_receipt,
            },
        },
        "boundaries": {
            "does_not_upgrade_smoke_to_full": no_smoke_to_full,
            "full_matrix_requires_current_passing_full_scope_receipt": full_requires_full_receipt,
            "hub_mobile_pwa_projection_is_not_blazor_full_execution": True,
        },
        "failures": failures,
        "notes": [
            "This Hub bridge keeps mobile/PWA readiness, Blazor PWA installability, and Blazor hosted execution horizons visible together.",
            "A passing bridge does not mean the full live Blazor public-edge execution matrix is proven unless mid_term_full_matrix_status is proven.",
            "Living-world opt-in and Black Ledger mobile projection remain Hub-owned; Blazor hosted execution breadth remains presentation-owned.",
        ],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if failures:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    print(f"blazor_execution_horizon_bridge:ok {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
