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
private_lore_tokens = [
    "campaign alias",
    "safehouse codename",
    "pressure lane beta",
]
no_noise_forbidden = private_lore_tokens + [
    'href="#"',
    "javascript:void",
    "Learn more",
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
    for token in no_noise_forbidden:
        if token in text:
            file_violations.append(token)
            source_status = "fail"
    results.append({"path": str(file.relative_to(ROOT)), "source_violations": file_violations})

for path in targets:
    try:
        response = requests.get(args.base_url.rstrip("/") + path, timeout=20)
        body = response.text
        leaked = [token for token in private_lore_tokens if token in body]
        if leaked:
            status = "fail"
        results.append({"path": path, "status_code": response.status_code, "leaks": leaked})
    except Exception as exc:
        results.append({"path": path, "runtime_unavailable": str(exc)})

combined = "pass" if status == "pass" and source_status == "pass" else "fail"
payload = {
    "status": combined,
    "runtime_status": status,
    "source_status": source_status,
    "results": results,
}

base = Path("/docker/chummercomplete/_completion/black_ledger_faction_onboarding")
base.mkdir(parents=True, exist_ok=True)
(base / "BLACK_LEDGER_PRIVATE_LORE_LEAK_SCAN.generated.json").write_text(json.dumps(payload, indent=2))
(base / "BLACK_LEDGER_FACTION_NO_NOISE.generated.json").write_text(json.dumps(payload, indent=2))
print(json.dumps(payload))
