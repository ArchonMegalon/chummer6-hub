#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_ACTIONS.generated.json")

controller = (ROOT / "Chummer.Run.Api/Controllers/LedgerController.cs").read_text()
workspace = (ROOT / "Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml").read_text()
service = (ROOT / "Chummer.Run.Api/Services/Community/BlackLedgerFactionOnboardingService.cs").read_text()

actions = [
    "Scout",
    "Recruit",
    "Secure District",
    "Sponsor Package",
    "Publish Dispatch",
    "Reduce Heat",
    "Challenge Faction",
    "Fortify Safehouse",
    "Gather Receipts",
]

required_receipt_tokens = [
    "RemainingActionPoints",
    "Effects",
    "Turn:",
]

required_reducer_tokens = [
    "Faction action points are exhausted for the current turn.",
    "ReduceActionLocked(",
    "ActionPointsSpent",
    "RivalsChallenged",
    "DistrictPressure",
]

payload = {
    "status": "pass" if all(action in service for action in actions)
    and all(token in service for token in required_receipt_tokens + required_reducer_tokens)
    and "/api/v1/account/ledger/factions/{factionId}/actions" in controller
    and "Spend action point" in workspace
    else "fail",
    "actions": actions,
    "api_route": "/api/v1/account/ledger/factions/{factionId}/actions",
    "receipt_link_present": "View receipt" in workspace,
    "receipt_fields_present": all(token in service for token in required_receipt_tokens),
    "reducer_enforcement_present": all(token in service for token in required_reducer_tokens),
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, indent=2))
print(json.dumps(payload))
