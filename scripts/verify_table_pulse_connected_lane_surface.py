from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib import error, request


REPO_ROOT = Path(
    os.environ.get(
        "CHUMMER_TABLE_PULSE_CONNECTED_LANE_ROOT",
        Path(__file__).resolve().parents[1],
    )
)

REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": (
        "LeaderBriefingHrefTemplate = \"/account/ledger/factions/{factionId}/leader-briefing\"",
        "Runner Passport keeps public-safe trust posture connected to the first-party Table Pulse live inbox, leader command, and aftermath return path.",
        "Table Pulse Live turns the account inbox into a command packet",
        "GM cockpit keeps remote-reaction aftermath on one command path",
        "Table Pulse Live inbox",
    ),
    "Chummer.Run.Api/Views/Accounts/Account.cshtml": (
        "Table Pulse Live command to fallout",
        "Table Pulse Live is armed on this workspace",
        "Open campaign memory",
        "Open aftermath",
    ),
    "Chummer.Run.Api/Views/PublicLanding/Home.cshtml": (
        "Table Pulse aftermath: account reaction fallout stays on the same reviewed workspace",
        "Open aftermath and return",
    ),
    "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml": (
        "Same return view",
        "the detail view keeps your live Table Pulse Aftermath return cues, aftermath, replay, and linked creator-publication history together",
        "Table Pulse Aftermath return items that stay in this account view",
    ),
    "Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml": (
        "Connected workspace section",
        "Model.ConnectedLanePacket.BoundaryLine",
    ),
    "Chummer.Run.Api/Views/PublicLanding/MediaArtifactHorizon.cshtml": (
        "<p class=\"eyebrow\">Connected page</p>",
        "@PublicFacingCopyHumanizer.Clean(Model.ConnectedLanePacket.BoundaryLine)",
    ),
}

LIVE_ROUTE_MARKERS: dict[str, tuple[str, ...]] = {
    "/living-world": (
        "Connected page",
        "Table Pulse Live inbox",
    ),
    "/signal-deck": (
        "Connected page",
        "Table Pulse Live inbox",
    ),
    "/passport": (
        "Connected page",
        "Table Pulse Live inbox",
    ),
}

LIVE_REQUEST_ATTEMPTS = 3


class HttpResponse:
    def __init__(self, url: str, status_code: int, text: str) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code} for {self.url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the connected Table Pulse lane in source and optionally on live public routes.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Optional running Hub base URL. When provided, verify live public horizon pages too.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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

    if args.base_url:
        base_url = args.base_url.rstrip("/")
        for route, markers in LIVE_ROUTE_MARKERS.items():
            body = fetch_live_route(f"{base_url}{route}", missing)
            if not body:
                continue
            for marker in markers:
                if marker not in body:
                    missing.append(f"live route {route} missing marker: {marker}")

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("table_pulse_connected_lane_surface:ok")
    return 0


def fetch_live_route(url: str, missing: list[str]) -> str:
    last_error = ""
    for attempt in range(1, LIVE_REQUEST_ATTEMPTS + 1):
        try:
            response = http_get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == LIVE_REQUEST_ATTEMPTS:
                break

    missing.append(f"live route {url} could not be fetched after {LIVE_REQUEST_ATTEMPTS} attempts: {last_error}")
    return ""


def http_get(url: str, timeout: int) -> HttpResponse:
    http_request = request.Request(
        url,
        headers={"User-Agent": "Chummer Table Pulse Connected Lane Verifier/1.0"},
    )
    try:
        with request.urlopen(http_request, timeout=timeout) as response:
            raw_body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return HttpResponse(
                url=url,
                status_code=response.getcode(),
                text=raw_body.decode(charset, errors="replace"),
            )
    except error.HTTPError as exc:
        raw_body = exc.read()
        charset = exc.headers.get_content_charset() if exc.headers is not None else None
        return HttpResponse(
            url=url,
            status_code=exc.code,
            text=raw_body.decode(charset or "utf-8", errors="replace"),
        )
    except error.URLError as exc:
        raise RuntimeError(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
