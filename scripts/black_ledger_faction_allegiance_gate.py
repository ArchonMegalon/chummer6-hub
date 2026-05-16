#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

import requests

from absolute_completion_common import LocalHubApp, TokenIdentityStub


OUT = "/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_ALLEGIANCE.generated.json"
ACCESS_TOKEN = "ledger-allegiance-proof-token"


def main() -> int:
    with TokenIdentityStub(access_token=ACCESS_TOKEN, subject_id="subject.ledger.allegiance", display_name="Ledger Allegiance Proof", email="ledger-allegiance@chummer.run") as identity:
        with LocalHubApp(identity_base_url=identity.base_url) as app:
            session = requests.Session()
            session.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

            join_first = session.post(
                f"{app.base_url}/api/v1/account/ledger/allegiance/join",
                json={"factionId": "ashline-circle"},
                timeout=30,
            )
            join_first.raise_for_status()
            join_first_payload = join_first.json()

            get_allegiance = session.get(f"{app.base_url}/api/v1/account/ledger/allegiance", timeout=30)
            get_allegiance.raise_for_status()
            allegiance_payload = get_allegiance.json()

            join_second = session.post(
                f"{app.base_url}/api/v1/account/ledger/allegiance/join",
                json={"factionId": "glass-tower-compact"},
                timeout=30,
            )

            payload = {
                "status": "pass"
                if join_first.status_code == 200
                and allegiance_payload.get("activeFactionId") == "ashline_circle"
                and allegiance_payload.get("appliesToAllCurrentRunners") is True
                and allegiance_payload.get("appliesToAllFutureRunners") is True
                and join_second.status_code == 400
                else "fail",
                "kind": "authenticated_http_e2e",
                "base_url": app.base_url,
                "identity_stub_base_url": identity.base_url,
                "join_receipt": {
                    "status_code": join_first.status_code,
                    "runnerCount": join_first_payload.get("runnerCount"),
                    "futureRunnersInherit": join_first_payload.get("futureRunnersInherit"),
                },
                "allegiance": {
                    "activeFactionId": allegiance_payload.get("activeFactionId"),
                    "appliesToAllCurrentRunners": allegiance_payload.get("appliesToAllCurrentRunners"),
                    "appliesToAllFutureRunners": allegiance_payload.get("appliesToAllFutureRunners"),
                },
                "cooldown_rejection": {
                    "status_code": join_second.status_code,
                    "body": join_second.text[-1000:],
                },
            }

            with open(OUT, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(json.dumps(payload))
            return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
