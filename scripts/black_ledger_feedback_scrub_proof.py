#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys

import requests


OUT = "/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FEEDBACK_SCRUB_PROOF.generated.json"
ROUTES = ["/feedback", "/feedback/operations", "/feedback/operations/lookup"]
PATTERNS = {
    "operator_term": re.compile(r"\boperator(s)?\b", re.IGNORECASE),
    "provider_message_id": re.compile(r"\bprovider message id\b", re.IGNORECASE),
    "provider_callback": re.compile(r"\bprovider callback(s)?\b", re.IGNORECASE),
    "provider_identity": re.compile(r"\bprovider identity\b", re.IGNORECASE),
    "provider_state": re.compile(r"\bprovider state\b", re.IGNORECASE),
    "provider_payload": re.compile(r"\braw provider payload(s)?\b", re.IGNORECASE),
    "env_var": re.compile(r"\bCHUMMER_[A-Z0-9_]+\b"),
}


def main() -> int:
    base_url = "https://chummer.run"
    route_results = []
    failures = []

    for route in ROUTES:
        response = requests.get(f"{base_url}{route}", timeout=30)
        response.raise_for_status()
        hits = []
        for line_number, line in enumerate(response.text.splitlines(), start=1):
            for leak_id, pattern in PATTERNS.items():
                if pattern.search(line):
                    hits.append({"line": line_number, "leak_id": leak_id, "text": line.strip()})
        route_results.append({"route": route, "status_code": response.status_code, "hits": hits})
        if hits:
            failures.append(route)

    payload = {
        "status": "pass" if not failures else "fail",
        "base_url": base_url,
        "routes": route_results,
        "failure_count": len(failures),
    }

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(json.dumps(payload))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
