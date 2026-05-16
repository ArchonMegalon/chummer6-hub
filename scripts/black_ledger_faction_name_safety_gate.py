#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "Chummer.Run.Api/Services/Community/BlackLedgerFactionOnboardingService.cs").read_text()
TESTS = (ROOT / "Chummer.Tests/BlackLedgerFactionOnboardingTests.cs").read_text()
OUT = Path("/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_NAME_SAFETY.generated.json")

checks = {
    "moderation_terms_present": "ForbiddenFactionNameTerms" in SERVICE,
    "name_length_guard_present": "Faction name must stay between 4 and 48 characters." in SERVICE,
    "safety_exception_present": "Faction name failed public-safety moderation." in SERVICE,
    "duplicate_name_guard_present": "Faction name is already taken." in SERVICE,
    "test_coverage_present": "FactionCharterBuilder_rejects_unsafe_public_names" in TESTS,
}

payload = {
    "status": "pass" if all(checks.values()) else "fail",
    **checks,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, indent=2))
print(json.dumps(payload))
