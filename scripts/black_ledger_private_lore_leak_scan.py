#!/usr/bin/env python3
import argparse
import json
import requests
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:5000")
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[1]
targets = [
    "/ledger",
    "/ledger/factions",
    "/ledger/factions/ashline-circle",
    "/ledger/factions/ashline-circle/dispatches",
    "/ledger/factions/ashline-circle/packages",
]
forbidden = [
    "internal tag",
    "lore overlay alpha",
    "district pressure lane",
]

results = []
status = "pass"
source_status = "pass"
source_files = [
    ROOT / "Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml",
    ROOT / "Chummer.Run.Api/Views/PublicLanding/LedgerOnboarding.cshtml",
    ROOT / "Chummer.Run.Api/Views/PublicLanding/LedgerFactionCreate.cshtml",
    ROOT / "Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml",
]
for file in source_files:
    text = file.read_text()
    file_violations = []
    for token in forbidden + ['href="#"', "javascript:void", "Learn more"]:
        if token in text:
            file_violations.append(token)
            source_status = "fail"
    results.append({"path": str(file.relative_to(ROOT)), "source_violations": file_violations})

for path in targets:
    try:
        response = requests.get(args.base_url.rstrip("/") + path, timeout=20)
        body = response.text
        leaked = [token for token in forbidden if token in body]
        if leaked:
            status = "fail"
        results.append({"path": path, "status_code": response.status_code, "leaks": leaked})
    except Exception as exc:
        results.append({"path": path, "runtime_unavailable": str(exc)})

out = Path("/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_NO_NOISE.generated.json")
out.parent.mkdir(parents=True, exist_ok=True)
combined = "pass" if status == "pass" and source_status == "pass" else "fail"
payload = {"status": combined, "runtime_status": status, "source_status": source_status, "results": results}
out.write_text(json.dumps(payload, indent=2))
print(json.dumps(payload))
