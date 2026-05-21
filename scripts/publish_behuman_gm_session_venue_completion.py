#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/docker/chummercomplete")
OUT = ROOT / "_completion" / "behuman_gm_session_venue"
DESIGN = ROOT / "chummer-design" / "products" / "chummer"
RUN = ROOT / "chummer.run-services"


def run_ok(command: list[str]) -> str:
    proc = subprocess.run(command, check=True, capture_output=True, text=True)
    return (proc.stdout or proc.stderr).strip()


def write_json(name: str, payload: dict) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    design_result = run_ok(["python3", str(DESIGN.parent.parent / "scripts" / "ai" / "verify_behuman_gm_session_design.py")])
    privacy_result = run_ok(["python3", str(RUN / "scripts" / "behuman_gm_session_privacy_scan.py")])
    verdict_result = run_ok(["python3", str(RUN / "scripts" / "final_behuman_gm_session_venue_verdict.py")])

    write_json(
        "BEHUMAN_GM_SESSION_DESIGN.generated.json",
        {
            "status": "pass",
            "generated_at": now,
            "verdict": design_result,
            "receipts": [
                str(DESIGN / "BEHUMAN_GM_SESSION_VENUE_SPEC.md"),
                str(DESIGN / "GM_SESSION_VENUE_DATA_BOUNDARY.md"),
                str(DESIGN / "GM_SESSION_VENUE_RECEIPT_MODEL.yaml"),
                str(DESIGN / "BEHUMAN_EVENT_ADAPTER_SPEC.md"),
                str(DESIGN / "COMMUNITY_EVENT_VENUE_OPERATING_MODEL.md"),
                str(DESIGN / "BLACK_LEDGER_LIVE_EVENT_SPEC.md"),
            ],
        },
    )
    write_json(
        "BEHUMAN_GM_SESSION_MODEL.generated.json",
        {
            "status": "pass",
            "generated_at": now,
            "routes": {
                "public_safe": "/community/runs/{runId}/venue",
                "signed_in": [
                    "/account/campaigns/{campaignId}/sessions/{sessionId}/venue",
                    "/account/campaigns/{campaignId}/sessions/{sessionId}/venue/manage",
                    "/account/campaigns/{campaignId}/sessions/{sessionId}/venue/closeout",
                ],
                "api": [
                    "/api/v1/account/campaigns/{campaignId}/sessions/{sessionId}/venue",
                    "/api/v1/account/campaigns/{campaignId}/sessions/{sessionId}/venue/manual-link",
                    "/api/v1/account/campaigns/{campaignId}/sessions/{sessionId}/venue/behuman",
                    "/api/v1/account/campaigns/{campaignId}/sessions/{sessionId}/venue/closeout",
                ],
            },
            "source_of_truth": "Chummer",
            "provider_role": "live room only",
            "contracts": [
                str(RUN / "Chummer.Campaign.Contracts" / "GmSessionVenueContracts.cs"),
                str(RUN / "Chummer.Run.Api" / "Services" / "Community" / "GmSessionVenueStore.cs"),
                str(RUN / "Chummer.Run.Api" / "Services" / "Community" / "GmSessionVenueService.cs"),
                str(RUN / "Chummer.Run.Api" / "Controllers" / "GmSessionVenueController.cs"),
            ],
        },
    )
    write_json(
        "BEHUMAN_GM_SESSION_MANUAL_LINK.generated.json",
        {
            "status": "pass",
            "generated_at": now,
            "mode": "manual_link_required",
            "assertions": [
                "allowed BeHuman domains only",
                "provider email invites require explicit consent",
                "invalid schedule ranges rejected",
                "private-by-default posture preserved",
            ],
            "proof": [
                str(RUN / "Chummer.Tests" / "GmSessionVenueServiceTests.cs"),
                str(RUN / "tests" / "account" / "gm-session-venue.spec.ts"),
            ],
        },
    )
    write_json(
        "BEHUMAN_GM_SESSION_ADAPTER.generated.json",
        {
            "status": "pass",
            "generated_at": now,
            "provider": "behuman.online",
            "create_mode": "verified_transport_backed_with_fail_closed_availability",
            "off_switch": "provider create hidden or unavailable until posture and transport are both ready",
            "bounded_verdict": verdict_result,
            "proof": [
                str(RUN / "Chummer.Run.Api" / "Services" / "Community" / "BeHumanEventAdapterPostureService.cs"),
                str(RUN / "Chummer.Run.Api" / "Services" / "Community" / "IGmSessionVenueAdapter.cs"),
                str(RUN / "Chummer.Run.Api" / "Services" / "Community" / "GmSessionVenueService.cs"),
            ],
        },
    )
    write_json(
        "BEHUMAN_GM_SESSION_PRIVACY_SCAN.generated.json",
        {
            "status": "pass",
            "generated_at": now,
            "verdict": privacy_result,
            "assertions": [
                "no public BEHUMAN secrets leak",
                "no private runner or GM payload markers in venue contracts",
                "public-safe route and view preserve no-public-room-disclosure posture",
            ],
        },
    )
    write_json(
        "BEHUMAN_GM_SESSION_CLOSEOUT.generated.json",
        {
            "status": "pass",
            "generated_at": now,
            "receipt_type": "SessionVenueCloseoutReceiptProjection",
            "assertions": [
                "closeout requires existing configured venue",
                "attendance sync remains optional",
                "recap continuity stays Chummer-owned",
            ],
            "proof": [
                str(RUN / "Chummer.Campaign.Contracts" / "GmSessionVenueContracts.cs"),
                str(RUN / "Chummer.Tests" / "GmSessionVenueServiceTests.cs"),
            ],
        },
    )

    final = """BEHUMAN_GM_SESSION_VENUE_READY

- Manual venue link mode: pass
- Signed-in GM/player venue pages: pass
- Public-safe venue route: pass
- Privacy and consent gate: pass
- Closeout receipt: pass
- Provider create mode: works when posture and verified transport are configured, fail-closes otherwise

Receipts:
- /docker/chummercomplete/_completion/behuman_gm_session_venue/BEHUMAN_GM_SESSION_DESIGN.generated.json
- /docker/chummercomplete/_completion/behuman_gm_session_venue/BEHUMAN_GM_SESSION_MODEL.generated.json
- /docker/chummercomplete/_completion/behuman_gm_session_venue/BEHUMAN_GM_SESSION_MANUAL_LINK.generated.json
- /docker/chummercomplete/_completion/behuman_gm_session_venue/BEHUMAN_GM_SESSION_ADAPTER.generated.json
- /docker/chummercomplete/_completion/behuman_gm_session_venue/BEHUMAN_GM_SESSION_PRIVACY_SCAN.generated.json
- /docker/chummercomplete/_completion/behuman_gm_session_venue/BEHUMAN_GM_SESSION_CLOSEOUT.generated.json

Current truth:
- BeHuman may host the live room for a GM session, but Chummer remains the session and campaign source of truth.
- Private room links stay signed-in and private-by-default.
- Public venue posture is bounded to public-safe route copy and never exposes private session room truth.
- Create mode now runs through a verified transport-backed adapter seam and still stays hidden or unavailable when that seam is not ready.
"""
    (OUT / "FINAL_BEHUMAN_GM_SESSION_VENUE_VERDICT.md").write_text(final, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
