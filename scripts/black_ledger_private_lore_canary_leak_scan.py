#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid

import requests

from absolute_completion_common import LocalHubApp, TokenIdentityStub


OUT = "/docker/chummercomplete/_completion/black_ledger_faction_onboarding/BLACK_LEDGER_PRIVATE_LORE_LEAK_SCAN.generated.json"
ACCESS_TOKEN = "ledger-private-lore-proof-token"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    canary = f"canary-{uuid.uuid4().hex}"
    canary_labels = {
        "safehouse_alpha": f"{canary}-safehouse",
        "district_beta": f"{canary}-district",
    }
    note = f"{canary}-note"

    with TokenIdentityStub(access_token=ACCESS_TOKEN, subject_id="subject.ledger.private-lore", display_name="Ledger Private Lore Proof", email="ledger-private-lore@chummer.run") as identity:
        with LocalHubApp(identity_base_url=identity.base_url) as app:
            base_url = args.base_url.rstrip("/") if args.base_url else app.base_url
            session = requests.Session()
            session.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

            created = session.post(
                f"{app.base_url}/api/v1/account/ledger/factions",
                json={
                    "publicName": f"Private Lore {uuid.uuid4().hex[:10]}",
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
            route_faction_id = faction_id.replace("_", "-")

            approve = session.post(
                f"{app.base_url}/api/v1/account/ledger/factions/{faction_id}/moderation/approve",
                timeout=30,
            )
            approve.raise_for_status()

            overlay = session.post(
                f"{app.base_url}/api/v1/account/campaigns/cmp-proof/ledger/private-lore-overlay",
                json={
                    "worldId": "emerald-sprawl-prelude",
                    "factionId": faction_id,
                    "labelMap": canary_labels,
                    "notes": [note],
                },
                timeout=30,
            )
            overlay.raise_for_status()
            overlay_payload = overlay.json()

            private_page = session.get(
                f"{app.base_url}/account/ledger/factions/{route_faction_id}/private-lore?campaignId=cmp-proof",
                timeout=30,
            )
            private_page.raise_for_status()
            private_visible = all(value in private_page.text for value in list(canary_labels.values()) + [note])

            routes = [
                "/",
                "/feedback",
                "/ledger",
                "/ledger/factions",
                f"/ledger/factions/{route_faction_id}",
                f"/ledger/factions/{route_faction_id}/packages",
                "/ledger/map",
                "/api/v1/ledger/factions",
                f"/api/v1/ledger/factions/{faction_id}",
                "/api/v1/ledger/worlds/emerald-sprawl-prelude",
            ]

            route_results = []
            runtime_status = "pass"
            needles = list(canary_labels.values()) + [note]
            for route in routes:
                response = requests.get(f"{base_url}{route}", timeout=30)
                leaks = [needle for needle in needles if needle in response.text]
                if leaks:
                    runtime_status = "fail"
                route_results.append(
                    {
                        "route": route,
                        "status_code": response.status_code,
                        "leaks": leaks,
                    }
                )

            payload = {
                "status": "pass" if private_visible and runtime_status == "pass" else "fail",
                "kind": "authenticated_http_e2e_plus_scan",
                "base_url": base_url,
                "identity_stub_base_url": identity.base_url,
                "strict": args.strict,
                "private_page_contains_canary": private_visible,
                "overlay_id": overlay_payload.get("overlayId"),
                "routes": route_results,
                "canary_values": needles,
            }

            with open(OUT, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(json.dumps(payload))
            return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
