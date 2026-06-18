#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

import requests


OUT = "/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_LIVE_ROOT_PROOF.generated.json"


def main() -> int:
    base_url = "https://chummer.run"
    response = requests.get(base_url, timeout=30)
    response.raise_for_status()
    body = response.text

    homepage_tokens_present = all(token in body for token in ["Build the runner. Run the night.", "Download Chummer"])
    black_ledger_hidden = "Open Black Ledger" not in body and "Enter Black Ledger" not in body

    payload = {
        "status": "pass" if homepage_tokens_present and black_ledger_hidden else "fail",
        "base_url": base_url,
        "route": "/",
        "status_code": response.status_code,
        "checks": {
            "builder_first_headline": "Build the runner. Run the night." in body,
            "black_ledger_not_promoted": black_ledger_hidden,
            "download_chummer_cta": "Download Chummer" in body,
        },
    }

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(json.dumps(payload))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
