#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import uuid

import requests

from absolute_completion_common import LocalHubApp, TokenIdentityStub


OUT = "/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_ACTIONS.generated.json"
ACCESS_TOKEN = "ledger-actions-proof-token"


def main() -> int:
    public_name = f"Action Proof {uuid.uuid4().hex[:10]}"
    with TokenIdentityStub(access_token=ACCESS_TOKEN, subject_id="subject.ledger.actions", display_name="Ledger Action Proof", email="ledger-actions@chummer.run") as identity:
        with LocalHubApp(identity_base_url=identity.base_url) as app:
            session = requests.Session()
            session.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

            created = session.post(
                f"{app.base_url}/api/v1/account/ledger/factions",
                json={
                    "publicName": public_name,
                    "charterType": "challenger",
                    "archetypeId": "matrix_cell",
                    "perkIds": ["underdog_momentum", "dispatch_desk"],
                    "flawIds": ["overexposed", "thin_resources", "rival_target"],
                    "rivalFactionId": "ashline_circle",
                    "warningAccepted": True,
                },
                timeout=30,
            )
            created.raise_for_status()
            faction_id = created.json()["factionId"]

            approve = session.post(f"{app.base_url}/api/v1/account/ledger/factions/{faction_id}/moderation/approve", timeout=30)
            approve.raise_for_status()

            actions = session.get(f"{app.base_url}/api/v1/ledger/factions/{faction_id}/actions", timeout=30)
            actions.raise_for_status()
            action_payload = actions.json()

            first = session.post(
                f"{app.base_url}/api/v1/account/ledger/factions/{faction_id}/actions",
                json={
                    "actionId": "challenge-faction",
                    "targetDistrictId": "emerald-core",
                    "targetFactionId": "ashline_circle",
                    "stake": "pressure",
                },
                timeout=30,
            )
            first.raise_for_status()
            first_payload = first.json()

            second = session.post(
                f"{app.base_url}/api/v1/account/ledger/factions/{faction_id}/actions",
                json={
                    "actionId": "recruit",
                    "targetDistrictId": "emerald-core",
                    "stake": "trust",
                },
                timeout=30,
            )

            public_detail = session.get(f"{app.base_url}/api/v1/ledger/factions/{faction_id}", timeout=30)
            public_detail.raise_for_status()
            detail_payload = public_detail.json()

            payload = {
                "status": "pass"
                if actions.status_code == 200
                and len(action_payload) > 0
                and first_payload.get("remainingActionPoints") == 0
                and second.status_code == 400
                and any("AP 0/2" in signal for signal in detail_payload.get("publicSignals", []))
                else "fail",
                "kind": "authenticated_http_e2e",
                "base_url": app.base_url,
                "identity_stub_base_url": identity.base_url,
                "action_definition_count": len(action_payload),
                "first_receipt": {
                    "status_code": first.status_code,
                    "receiptId": first_payload.get("receiptId"),
                    "remainingActionPoints": first_payload.get("remainingActionPoints"),
                    "effects": first_payload.get("effects"),
                },
                "second_action": {
                    "status_code": second.status_code,
                    "body": second.text[-1000:],
                },
                "public_signals": detail_payload.get("publicSignals", []),
            }

            with open(OUT, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(json.dumps(payload))
            return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
