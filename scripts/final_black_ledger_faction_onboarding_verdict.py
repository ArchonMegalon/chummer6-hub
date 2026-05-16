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
    "BLACK_LEDGER_NO_NOISE_LINK_AUDIT.generated.json",
    "BLACK_LEDGER_PRIVATE_LORE_LEAK_SCAN.generated.json",
    "BLACK_LEDGER_FACTION_NAME_SAFETY.generated.json",
    "BLACK_LEDGER_FACTION_ACTION_REDUCER.generated.json",
    "BLACK_LEDGER_COMMAND_MAP_MOTION.generated.json",
    "BLACK_LEDGER_LIVE_ROOT_PROOF.generated.json",
    "BLACK_LEDGER_FEEDBACK_SCRUB_PROOF.generated.json",
]

status = "BLACK_LEDGER_FACTION_ONBOARDING_READY"
failures = []
for path in required:
    file = base / path
    if not file.exists():
        status = "NOT_READY"
        failures.append(f"missing:{path}")
        break
    try:
        data = json.loads(file.read_text())
        if data.get("status") != "pass":
            status = "NOT_READY"
            failures.append(f"failed:{path}")
            break
    except Exception:
        status = "NOT_READY"
        failures.append(f"invalid:{path}")
        break

verdict = base / "FINAL_BLACK_LEDGER_FACTION_ONBOARDING_VERDICT.md"
body = status if not failures else status + "\n" + "\n".join(failures) + "\n"
verdict.write_text(body)
print(status)
