#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import uuid

import requests

from absolute_completion_common import LocalHubApp, TokenIdentityStub


OUT = "/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_FACTION_CHARTER_BUILDER.generated.json"
ACCESS_TOKEN = "ledger-builder-proof-token"


def main() -> int:
    public_name = f"Proof Charter {uuid.uuid4().hex[:10]}"
    with TokenIdentityStub(access_token=ACCESS_TOKEN, subject_id="subject.ledger.builder", display_name="Ledger Builder Proof", email="ledger-builder@chummer.run") as identity:
        with LocalHubApp(identity_base_url=identity.base_url) as app:
            session = requests.Session()
            session.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

            invalid = session.post(
                f"{app.base_url}/api/v1/account/ledger/factions",
                json={
                    "publicName": "Quiet Undertow",
                    "charterType": "challenger",
                    "archetypeId": "matrix_cell",
                    "perkIds": ["underdog_momentum", "dispatch_desk"],
                    "flawIds": ["overexposed", "thin_resources", "rival_target"],
                    "rivalFactionId": "ashline_circle",
                    "warningAccepted": False,
                },
                timeout=30,
            )

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
            charter = created.json()
            faction_id = charter["factionId"]

            before_public = session.get(f"{app.base_url}/api/v1/ledger/factions/{faction_id}", timeout=30)
            approve = session.post(f"{app.base_url}/api/v1/account/ledger/factions/{faction_id}/moderation/approve", timeout=30)
            approve.raise_for_status()
            after_public = session.get(f"{app.base_url}/api/v1/ledger/factions/{faction_id}", timeout=30)
            suppress = session.post(
                f"{app.base_url}/api/v1/account/ledger/factions/{faction_id}/moderation/suppress",
                json={"reason": "proof suppression check"},
                timeout=30,
            )
            suppress.raise_for_status()
            after_suppress = session.get(f"{app.base_url}/api/v1/ledger/factions/{faction_id}", timeout=30)

            payload = {
                "status": "pass"
                if invalid.status_code == 400
                and charter.get("status") == "pending_review"
                and before_public.status_code == 404
                and approve.status_code == 200
                and after_public.status_code == 200
                and suppress.status_code == 200
                and after_suppress.status_code == 404
                else "fail",
                "kind": "authenticated_http_e2e",
                "base_url": app.base_url,
                "identity_stub_base_url": identity.base_url,
                "invalid_create": {
                    "status_code": invalid.status_code,
                    "body": invalid.text[-1000:],
                },
                "created_charter": {
                    "factionId": faction_id,
                    "status": charter.get("status"),
                    "charterType": charter.get("charterType"),
                    "charterPointsSpent": charter.get("charterPointsSpent"),
                },
                "public_projection": {
                    "before_approve_status_code": before_public.status_code,
                    "approve_status_code": approve.status_code,
                    "after_approve_status_code": after_public.status_code,
                    "suppress_status_code": suppress.status_code,
                    "after_suppress_status_code": after_suppress.status_code,
                },
            }

            with open(OUT, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(json.dumps(payload))
            return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
