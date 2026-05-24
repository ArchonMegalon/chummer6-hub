from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(
    os.environ.get(
        "CHUMMER_TABLE_PULSE_CONNECTED_LANE_ROOT",
        Path(__file__).resolve().parents[1],
    )
)

REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": (
        "Runner Passport connected lane",
        "Connected faction command lane",
        "Table Pulse Live turns the signed-in inbox into a command packet",
        "GM cockpit keeps remote-reaction aftermath on one command rail",
        "Table Pulse Live inbox",
    ),
    "Chummer.Run.Api/Views/Accounts/Account.cshtml": (
        "<strong>Table Pulse Live command-to-fallout lane</strong>",
        "Open campaign memory",
        "<strong>Table Pulse Aftermath return lane</strong>",
        "Open aftermath rail",
    ),
    "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml": (
        "the artifact shelf keeps your live Table Pulse Aftermath return cues, aftermath, replay, and linked creator-publication record together",
        "Table Pulse Aftermath return artifacts that stay on this signed-in shelf",
    ),
    "Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml": (
        "Connected command lane",
        "@Model.ConnectedLanePacket.BoundaryLine",
    ),
    "Chummer.Run.Api/Views/PublicLanding/MediaArtifactHorizon.cshtml": (
        "<p class=\"eyebrow\">Connected lane</p>",
        "@Model.ConnectedLanePacket.BoundaryLine",
    ),
}


def main() -> int:
    missing: list[str] = []

    for relative_path, markers in REQUIRED_MARKERS.items():
        path = REPO_ROOT / relative_path
        if not path.is_file():
            missing.append(f"missing file: {relative_path}")
            continue

        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path} missing marker: {marker}")

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("table_pulse_connected_lane_surface:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
