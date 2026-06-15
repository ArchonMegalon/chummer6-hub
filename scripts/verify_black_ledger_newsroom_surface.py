from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import re
import sys
from types import SimpleNamespace
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


REPO_ROOT = Path(
    os.environ.get(
        "CHUMMER_BLACK_LEDGER_NEWSROOM_ROOT",
        Path(__file__).resolve().parents[1],
    )
)

REQUIRED_SOURCE_MARKERS: dict[str, tuple[str, ...]] = {
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": (
        '[HttpGet("/ledger/newsroom")]',
        '[HttpGet("/ledger/newsroom/{episodeId}")]',
        '[HttpGet("/ledger/newsroom/{episodeId}/transcript")]',
        '[HttpGet("/ledger/newsroom/{episodeId}/receipts")]',
        "TryParseNewsroomEpisodeTurn",
    ),
    "Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml": (
        "Black Ledger Newsroom",
        "Open watch route",
        "Transcript",
        "Source receipts",
        "Feedback",
        "Published:",
    ),
    "Chummer.Run.Api/Services/Community/BlackLedgerWorldTickBriefingService.cs": (
        'string watchHref = $"{ledgerBasePath.TrimEnd(\'/\')}/newsroom/{slug}";',
        "City bulletin only.",
        "Some shots replay city movement.",
    ),
    "Chummer.Run.Api/ViewModels/SiteViewModels.cs": (
        "TranscriptHref",
        "ReceiptsHref",
        "PublishedLabel",
        "EpisodeTypeLabel",
        "PublicSafetyNote",
        "ReconstructionNote",
        "FeedbackHref",
    ),
}

RECEIPTS_JSON_EXPECTATIONS: dict[str, tuple[str, ...]] = {
    "summary": (
        "validation packet",
        "newsreel lane",
    ),
    "checks": (
        "Public-safe effects carried",
        "Notification route: /account/ledger/notifications",
    ),
}

NEGATIVE_PATH_EXPECTATIONS: tuple[str, ...] = (
    "/ledger/newsroom/turn-999-newsreel",
    "/ledger/newsroom/turn-999-newsreel/transcript",
    "/ledger/newsroom/turn-999-newsreel/receipts",
)

WATCH_ROUTE_ASSET_PATTERNS: dict[str, tuple[str, str]] = {
    "poster": (r'poster="([^"]+turn-\d+-newsreel-poster\.png[^"]*)"', "image/png"),
    "mp4": (r'<source src="([^"]+turn-\d+-newsreel\.mp4[^"]*)"\s+type="video/mp4"', "video/mp4"),
    "webm": (r'<source src="([^"]+turn-\d+-newsreel\.webm[^"]*)"\s+type="video/webm"', "video/webm"),
    "vtt": (r'<track kind="captions" src="([^"]+turn-\d+-newsreel\.vtt[^"]*)"', "text/vtt"),
}

WATCH_ROUTE_TEXT_MARKERS: tuple[str, ...] = (
    "Black Ledger Newsroom",
    "Transcript",
    "Source receipts",
    "Feedback",
    "Published:",
)

NO_STORE_HEADER_MARKERS: tuple[str, ...] = (
    "no-store",
    "max-age=0",
)


@dataclass
class HttpResponse:
    url: str
    status_code: int
    headers: object
    body: bytes

    @property
    def text(self) -> str:
        charset = None
        if hasattr(self.headers, "get_content_charset"):
            charset = self.headers.get_content_charset()
        return self.body.decode(charset or "utf-8", errors="replace")

    def json(self) -> object:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code} for {self.url}")


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


NO_REDIRECT_OPENER = build_opener(NoRedirectHandler)
HTTP_HEADERS = {
    "User-Agent": "chummer-black-ledger-newsroom-verifier/1.0",
}


class _RequestsCompat:
    @staticmethod
    def get(url: str, timeout: int, allow_redirects: bool = True) -> HttpResponse:
        request = Request(url, headers=HTTP_HEADERS)
        try:
            if allow_redirects:
                with urlopen(request, timeout=timeout) as response:
                    return read_http_response(response)
            with NO_REDIRECT_OPENER.open(request, timeout=timeout) as response:
                return read_http_response(response)
        except HTTPError as exc:
            return HttpResponse(
                url=exc.geturl(),
                status_code=exc.code,
                headers=exc.headers,
                body=exc.read(),
            )


requests = SimpleNamespace(get=_RequestsCompat.get)


def read_http_response(response: object) -> HttpResponse:
    body = response.read()
    status_code = getattr(response, "status", None)
    if status_code is None:
        status_code = response.getcode()
    return HttpResponse(
        url=response.geturl(),
        status_code=status_code,
        headers=response.headers,
        body=body,
    )


def http_get(url: str, timeout: int, allow_redirects: bool = True) -> HttpResponse:
    return requests.get(url, timeout=timeout, allow_redirects=allow_redirects)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Black Ledger newsroom source contracts and optionally live public routes.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Optional running Hub base URL. When provided, verify live newsroom routes too.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing: list[str] = []

    for relative_path, markers in REQUIRED_SOURCE_MARKERS.items():
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
        newsroom_home = http_get(f"{base_url}/ledger/newsroom", timeout=30, allow_redirects=False)
        if newsroom_home.status_code not in {301, 302, 303, 307, 308}:
            missing.append("live route /ledger/newsroom missing redirect status")
            current_watch_route = "/ledger/newsroom/turn-1-newsreel"
        else:
            current_watch_route = newsroom_home.headers.get("Location", "")
            if "/ledger/newsroom/turn-" not in current_watch_route and "/ledger/turns/" not in current_watch_route:
                missing.append("live route /ledger/newsroom redirect missing turn newsroom target")
            if not current_watch_route.startswith("/"):
                current_watch_route = f"/{current_watch_route.lstrip('/')}"
        cache_control = newsroom_home.headers.get("Cache-Control", "")
        for marker in NO_STORE_HEADER_MARKERS:
            if marker not in cache_control:
                missing.append(f"live route /ledger/newsroom missing cache-control marker: {marker}")

        watch_response = http_get(f"{base_url}{current_watch_route}", timeout=30)
        watch_response.raise_for_status()
        watch_body = watch_response.text
        cache_control = watch_response.headers.get("Cache-Control", "")
        for marker in NO_STORE_HEADER_MARKERS:
            if marker not in cache_control:
                missing.append(f"live route {current_watch_route} missing cache-control marker: {marker}")
        for marker in WATCH_ROUTE_TEXT_MARKERS:
            if marker not in watch_body:
                missing.append(f"live route {current_watch_route} missing marker: {marker}")
        for asset_label, (pattern, expected_type) in WATCH_ROUTE_ASSET_PATTERNS.items():
            match = re.search(pattern, watch_body)
            if match is None:
                missing.append(f"live route {current_watch_route} missing {asset_label} asset reference")
                continue
            asset_url = urljoin(f"{base_url}{current_watch_route}", match.group(1))
            asset_response = http_get(asset_url, timeout=30)
            asset_response.raise_for_status()
            content_type = asset_response.headers.get("Content-Type", "")
            if expected_type not in content_type:
                missing.append(
                    f"asset {asset_label} for {current_watch_route} expected content type {expected_type}, got {content_type}"
                )

        transcript_match = re.search(r'href="([^"]+/transcript)"[^>]*>Transcript', watch_body)
        receipts_match = re.search(r'href="([^"]+/receipts)"[^>]*>Source receipts', watch_body)
        transcript_route = transcript_match.group(1) if transcript_match else f"{current_watch_route}/transcript"
        receipts_route = receipts_match.group(1) if receipts_match else f"{current_watch_route}/receipts"

        transcript_response = http_get(
            f"{base_url}{transcript_route}",
            timeout=30,
            allow_redirects=False,
        )
        if transcript_response.status_code not in {301, 302, 303, 307, 308}:
            missing.append(f"live route {transcript_route} missing redirect status")
        else:
            location = transcript_response.headers.get("Location", "")
            if ".vtt" not in location:
                missing.append(f"live route {transcript_route} redirect missing marker: .vtt")
        cache_control = transcript_response.headers.get("Cache-Control", "")
        for marker in NO_STORE_HEADER_MARKERS:
            if marker not in cache_control:
                missing.append(f"live route {transcript_route} missing cache-control marker: {marker}")

        receipts_response = http_get(
            f"{base_url}{receipts_route}",
            timeout=30,
        )
        receipts_response.raise_for_status()
        cache_control = receipts_response.headers.get("Cache-Control", "")
        for marker in NO_STORE_HEADER_MARKERS:
            if marker not in cache_control:
                missing.append(f"live route {receipts_route} missing cache-control marker: {marker}")
        try:
            receipts_payload = receipts_response.json()
        except json.JSONDecodeError as exc:
            missing.append(f"live route {receipts_route} did not return JSON: {exc}")
        else:
            summary_value = str(receipts_payload.get("summary") or "")
            checks_values = receipts_payload.get("checks") or []
            if not isinstance(checks_values, list):
                checks_values = []
            checks_text = "\n".join(str(item) for item in checks_values)
            for marker in RECEIPTS_JSON_EXPECTATIONS["summary"]:
                if marker not in summary_value:
                    missing.append(
                        f"live route {current_watch_route}/receipts summary missing marker: "
                        f"{marker}"
                    )
            for marker in RECEIPTS_JSON_EXPECTATIONS["checks"]:
                if marker not in checks_text:
                    missing.append(
                        f"live route {current_watch_route}/receipts checks missing marker: "
                        f"{marker}"
                    )

        for route in NEGATIVE_PATH_EXPECTATIONS:
            response = http_get(f"{base_url}{route}", timeout=30, allow_redirects=False)
            if response.status_code != 404:
                missing.append(
                    f"live route {route} expected status 404, got {response.status_code}"
                )

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("black_ledger_newsroom_surface:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
