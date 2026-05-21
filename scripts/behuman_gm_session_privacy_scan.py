#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path("/docker/chummercomplete/chummer.run-services")
SERVICE = ROOT / "Chummer.Run.Api" / "Services" / "Community" / "GmSessionVenueService.cs"
ADAPTER = ROOT / "Chummer.Run.Api" / "Services" / "Community" / "IGmSessionVenueAdapter.cs"
CONTRACTS = ROOT / "Chummer.Campaign.Contracts" / "GmSessionVenueContracts.cs"
CONTROLLER = ROOT / "Chummer.Run.Api" / "Controllers" / "GmSessionVenueController.cs"
PUBLIC_CONTROLLER = ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
VENUE_VIEW = ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "GmSessionVenue.cshtml"

FORBIDDEN_MARKERS = [
    "runner character sheets",
    "GM secrets",
    "sourcebook",
    "combat state",
]

SECRET_MARKERS = [
    "BEHUMAN_API_KEY",
    "BEHUMAN_WEBHOOK_SECRET",
]


def main() -> int:
    missing = [path for path in (SERVICE, ADAPTER, CONTRACTS, CONTROLLER, PUBLIC_CONTROLLER, VENUE_VIEW) if not path.is_file()]
    if missing:
        for path in missing:
            print(f"missing:{path}")
        print("NOT_READY")
        return 1

    service_text = SERVICE.read_text(encoding="utf-8")
    adapter_text = ADAPTER.read_text(encoding="utf-8")
    contracts_text = CONTRACTS.read_text(encoding="utf-8")
    controller_text = CONTROLLER.read_text(encoding="utf-8")
    public_controller_text = PUBLIC_CONTROLLER.read_text(encoding="utf-8")
    venue_view_text = VENUE_VIEW.read_text(encoding="utf-8")

    required_service_markers = [
        'Provider = "behuman"',
    ]
    required_adapter_markers = [
        "venue_url host is not an allowed BeHuman domain.",
        "Create BeHuman venue is unavailable until a verified adapter transport base URL exists.",
        "venue_url may not include suspicious query payloads.",
    ]
    required_contract_markers = [
        "PublicSafeSessionTitle",
        "ConsentToShareAttendeeEmails",
        "SessionVenueCloseoutReceiptProjection",
    ]
    required_controller_markers = [
        '[HttpPost("manual-link")]',
        '[HttpPost("behuman")]',
        '[HttpPost("closeout")]',
    ]
    required_public_markers = [
        '[HttpGet("/community/runs/{runId}/venue")]',
        "Live room integration unavailable. Paste your external room link manually or use another provider.",
    ]
    required_view_markers = [
        "Join live room",
        "Copy invite link",
        "No public room disclosure",
        "Create BeHuman room unavailable",
    ]

    for marker in required_service_markers:
        if marker not in service_text:
            print(f"service_missing:{marker}")
            print("NOT_READY")
            return 1

    for marker in required_adapter_markers:
        if marker not in adapter_text:
            print(f"adapter_missing:{marker}")
            print("NOT_READY")
            return 1

    for marker in required_contract_markers:
        if marker not in contracts_text:
            print(f"contracts_missing:{marker}")
            print("NOT_READY")
            return 1

    for marker in required_controller_markers:
        if marker not in controller_text:
            print(f"controller_missing:{marker}")
            print("NOT_READY")
            return 1

    for marker in required_public_markers:
        if marker not in public_controller_text:
            print(f"public_missing:{marker}")
            print("NOT_READY")
            return 1

    for marker in required_view_markers:
        if marker not in venue_view_text:
            print(f"view_missing:{marker}")
            print("NOT_READY")
            return 1

    for marker in FORBIDDEN_MARKERS:
        if marker in contracts_text:
            print(f"forbidden_payload_leak:{marker}")
            print("NOT_READY")
            return 1

    public_haystack = public_controller_text + "\n" + venue_view_text
    for marker in SECRET_MARKERS:
        if marker in public_haystack:
            print(f"public_secret_leak:{marker}")
            print("NOT_READY")
            return 1

    print("BEHUMAN_GM_SESSION_PRIVACY_SCAN_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
