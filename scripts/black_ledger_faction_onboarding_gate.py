#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from urllib.parse import urlparse

import requests

from absolute_completion_common import (
    LocalHubApp,
    TokenIdentityStub,
    extract_antiforgery_token,
)


OUT = "/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_ONBOARDING.generated.json"
ACCESS_TOKEN = "ledger-onboarding-proof-token"


def main() -> int:
    steps = ["welcome", "allegiance", "factions", "choose-path", "confirm", "builder", "welcome-kit"]
    with TokenIdentityStub(access_token=ACCESS_TOKEN, subject_id="subject.ledger.onboarding", display_name="Ledger Onboarding Proof", email="ledger-onboarding@chummer.run") as identity:
        with LocalHubApp(identity_base_url=identity.base_url) as app:
            session = requests.Session()
            session.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

            step_results: list[dict[str, object]] = []
            for step in steps:
                response = session.get(f"{app.base_url}/account/ledger/onboarding?step={step}", timeout=30, allow_redirects=True)
                response.raise_for_status()
                step_results.append(
                    {
                        "step": step,
                        "status_code": response.status_code,
                        "final_path": urlparse(response.url).path,
                    }
                )

            factions_page = session.get(f"{app.base_url}/account/ledger/onboarding?step=factions", timeout=30)
            factions_page.raise_for_status()
            anti_forgery = extract_antiforgery_token(factions_page.text)

            join = session.post(
                f"{app.base_url}/account/ledger/onboarding/join",
                data={
                    "__RequestVerificationToken": anti_forgery,
                    "factionId": "ashline-circle",
                },
                timeout=30,
                allow_redirects=False,
            )
            join_ok = join.status_code == 302 and "/account/ledger/factions/ashline-circle" in (join.headers.get("Location") or "")

            allegiance = session.get(f"{app.base_url}/api/v1/account/ledger/allegiance", timeout=30)
            allegiance.raise_for_status()
            allegiance_payload = allegiance.json()

            payload = {
                "status": "pass" if all(item["status_code"] == 200 for item in step_results) and join_ok and allegiance_payload.get("activeFactionId") == "ashline_circle" else "fail",
                "kind": "authenticated_http_e2e",
                "base_url": app.base_url,
                "identity_stub_base_url": identity.base_url,
                "steps": step_results,
                "join_status_code": join.status_code,
                "join_location": join.headers.get("Location"),
                "allegiance": {
                    "activeFactionId": allegiance_payload.get("activeFactionId"),
                    "appliesToAllCurrentRunners": allegiance_payload.get("appliesToAllCurrentRunners"),
                    "appliesToAllFutureRunners": allegiance_payload.get("appliesToAllFutureRunners"),
                    "switchCount": allegiance_payload.get("switchCount"),
                },
            }

            with open(OUT, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(json.dumps(payload))
            return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
