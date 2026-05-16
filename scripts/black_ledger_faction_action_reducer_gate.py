#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "Chummer.Run.Api/Services/Community/BlackLedgerFactionOnboardingService.cs").read_text()
TESTS = (ROOT / "Chummer.Tests/BlackLedgerFactionOnboardingTests.cs").read_text()
OUT = Path("/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_ACTION_REDUCER.generated.json")

checks = {
    "operational_state_present": "BlackLedgerFactionOperationalState" in SERVICE,
    "action_point_guard_present": "Faction action points are exhausted for the current turn." in SERVICE,
    "reducer_function_present": "ReduceActionLocked(" in SERVICE,
    "receipt_effects_present": "Effects:" in SERVICE and "RemainingActionPoints:" in SERVICE,
    "district_pressure_present": "DistrictPressure" in SERVICE,
    "rival_tracking_present": "RivalsChallenged" in SERVICE,
    "test_coverage_present": "FactionActionReducer_enforces_action_points_and_persists_receipts" in TESTS,
}

payload = {
    "status": "pass" if all(checks.values()) else "fail",
    **checks,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, indent=2))
print(json.dumps(payload))
