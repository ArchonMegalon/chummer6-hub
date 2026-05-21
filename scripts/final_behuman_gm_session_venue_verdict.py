#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path("/docker/chummercomplete")
DESIGN = ROOT / "chummer-design" / "products" / "chummer"
RUN = ROOT / "chummer.run-services"

REQUIRED_FILES = [
    DESIGN / "BEHUMAN_GM_SESSION_VENUE_SPEC.md",
    DESIGN / "GM_SESSION_VENUE_DATA_BOUNDARY.md",
    DESIGN / "GM_SESSION_VENUE_RECEIPT_MODEL.yaml",
    RUN / "Chummer.Campaign.Contracts" / "GmSessionVenueContracts.cs",
    RUN / "Chummer.Run.Api" / "Services" / "Community" / "GmSessionVenueService.cs",
    RUN / "Chummer.Run.Api" / "Services" / "Community" / "IGmSessionVenueAdapter.cs",
    RUN / "Chummer.Run.Api" / "Services" / "Community" / "GmSessionVenueStore.cs",
    RUN / "Chummer.Run.Api" / "Controllers" / "GmSessionVenueController.cs",
    RUN / "Chummer.Run.Api" / "Views" / "PublicLanding" / "GmSessionVenue.cshtml",
    RUN / "Chummer.Tests" / "GmSessionVenueServiceTests.cs",
    RUN / "tests" / "account" / "gm-session-venue.spec.ts",
    RUN / "scripts" / "behuman_gm_session_privacy_scan.py",
]


def main() -> int:
    missing = [path for path in REQUIRED_FILES if not path.is_file()]
    if missing:
        for path in missing:
            print(f"missing:{path}")
        print("NOT_READY")
        return 1

    controller = (RUN / "Chummer.Run.Api" / "Controllers" / "GmSessionVenueController.cs").read_text(encoding="utf-8")
    public_controller = (RUN / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")
    service = (RUN / "Chummer.Run.Api" / "Services" / "Community" / "GmSessionVenueService.cs").read_text(encoding="utf-8")
    adapter = (RUN / "Chummer.Run.Api" / "Services" / "Community" / "IGmSessionVenueAdapter.cs").read_text(encoding="utf-8")
    contracts = (RUN / "Chummer.Campaign.Contracts" / "GmSessionVenueContracts.cs").read_text(encoding="utf-8")
    view = (RUN / "Chummer.Run.Api" / "Views" / "PublicLanding" / "GmSessionVenue.cshtml").read_text(encoding="utf-8")

    required_markers = [
        '[HttpPost("manual-link")]',
        '[HttpPost("behuman")]',
        '[HttpPost("closeout")]',
        '[HttpGet("/community/runs/{runId}/venue")]',
        '[HttpGet("/account/campaigns/{campaignId}/sessions/{sessionId}/venue")]',
        "Create BeHuman venue is unavailable until a verified adapter transport base URL exists.",
        "CreateSessionVenueAsync",
        "SessionVenueCloseoutReceiptProjection",
        "manual_link_mode",
        "adapter_create_mode",
        "Create BeHuman room unavailable",
        "Provider create available",
        "No public room disclosure",
    ]
    for marker in required_markers:
        haystack = controller + "\n" + public_controller + "\n" + service + "\n" + adapter + "\n" + contracts + "\n" + view
        if marker not in haystack:
            print(f"missing_marker:{marker}")
            print("NOT_READY")
            return 1

    print("BEHUMAN_GM_SESSION_VENUE_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
