#!/usr/bin/env python3
import json
from pathlib import Path

base = Path("/docker/chummercomplete/_completion/black_ledger_faction_onboarding")
required = [
    "BLACK_LEDGER_FACTION_ONBOARDING.generated.json",
    "BLACK_LEDGER_FACTION_ALLEGIANCE.generated.json",
    "BLACK_LEDGER_FACTION_CHARTER_BUILDER.generated.json",
    "BLACK_LEDGER_FACTION_PAGES.generated.json",
    "BLACK_LEDGER_FACTION_ACTIONS.generated.json",
    "BLACK_LEDGER_FACTION_NO_NOISE.generated.json",
]

status = "BLACK_LEDGER_FACTION_ONBOARDING_READY"
for path in required:
    file = base / path
    if not file.exists():
        status = "NOT_READY"
        break
    try:
        data = json.loads(file.read_text())
        if data.get("status") != "pass":
            status = "NOT_READY"
            break
    except Exception:
        status = "NOT_READY"
        break

verdict = base / "FINAL_BLACK_LEDGER_FACTION_ONBOARDING_VERDICT.md"
verdict.write_text(status + "\n")
print(status)
