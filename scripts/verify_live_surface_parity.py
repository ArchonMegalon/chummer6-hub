#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = REPO_ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "LIVE_SURFACE_PARITY.generated.json"
DEFAULT_BASE_URL = "https://chummer.run"

SURFACES = [
    {
        "path": "/",
        "required_texts": [
            "A Shadowrun character manager for building, updating, and bringing clean sheets to the table.",
            "Download Chummer",
            "Windows and Linux.",
            "What it does",
        ],
        "forbidden_texts": [
            "Next move",
            "Need help?",
            "One compact rail for downloads, play, and public status.",
            "Reel details",
            "Keep it simple",
            "Get started",
            "Worlds",
            "Flagship routes",
            "Signals and horizons",
            "Trust and support",
            "Account and quick actions",
        ],
    },
    {
        "path": "/downloads",
        "required_texts": [
            "Install Chummer",
            "Choose the latest build for Windows or Linux.",
            "Nightly",
            "Stable",
        ],
        "forbidden_texts": [
            "Need account return?",
            "Current notes.",
            "Install questions?",
            "Account return later?",
            "account-assisted install paths",
            "Link this copy from the first launch",
            "guided installer",
            "Get started",
            "Flagship routes",
            "Signals and horizons",
            "Trust and support",
            "Account and quick actions",
        ],
    },
    {
        "path": "/status",
        "required_texts": [
            "Release status",
            "The build currently available from Chummer.",
            "Release",
            "Open downloads",
            "Open support",
        ],
        "forbidden_texts": [
            "Release and next step.",
            "Release, caution, next click.",
            "Known issues and install help stay nearby.",
            "Current caution.",
            "Preview posture on Public release",
            "Review is still required before this release can be treated as supportable.",
            "Fallback",
            "Revoked",
            "usage snapshot",
            "At a glance",
            "Signed-in return",
            "Status poster",
            "Get started",
            "Flagship routes",
            "Signals and horizons",
            "Trust and support",
            "Account and quick actions",
        ],
    },
    {
        "path": "/ledger",
        "required_texts": [
            "Black Ledger command map",
            "Command map",
        ],
        "required_final_url_prefix": "/ledger/map",
        "forbidden_texts": [
            "Internal Error",
            "Board signal:",
            "Turn source:",
            "Production notes",
            "City note:",
            "City pulse:",
            "Built from",
            "deterministic board",
            "Linked through",
            "Turn record:",
            "Scene notes",
            "<p class=\"editorial-copy\"></p>",
        ],
    },
    {
        "path": "/ledger/newsroom",
        "required_texts": [
            "Black Ledger Newsroom",
            "Transcript",
            "Published:",
        ],
        "forbidden_texts": [
            "Internal Error",
        ],
    },
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "template"} and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        text = data.strip()
        if text:
            self.parts.append(text)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch(url: str) -> tuple[int | None, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "chummer-live-surface-parity/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(response.status), body, response.geturl()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body, exc.geturl()
    except Exception as exc:  # pragma: no cover
        return None, str(exc), url


def flatten_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return " ".join(parser.parts)


def verify(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for surface in SURFACES:
        path = str(surface["path"])
        url = urllib.parse.urljoin(f"{base}/", path.lstrip("/"))
        status_code, body, final_url = fetch(url)
        flattened = flatten_text(body) if status_code == 200 else body
        missing = [token for token in surface.get("required_texts", []) if token not in flattened]
        forbidden = [token for token in surface.get("forbidden_texts", []) if token in flattened]
        final_url_prefix = str(surface.get("required_final_url_prefix") or "")
        final_url_matches = True
        if final_url_prefix:
            final_path = urllib.parse.urlparse(final_url).path or "/"
            final_url_matches = final_path.startswith(final_url_prefix)
            if not final_url_matches:
                failures.append(f"{path}: final URL {final_path} did not start with {final_url_prefix}")

        if status_code != 200:
            failures.append(f"{path}: expected 200, got {status_code}")
        if missing:
            failures.append(f"{path}: missing required text: {', '.join(missing)}")
        if forbidden:
            failures.append(f"{path}: contains forbidden text: {', '.join(forbidden)}")

        results.append(
            {
                "path": path,
                "url": url,
                "final_url": final_url,
                "status_code": status_code,
                "required_texts": surface.get("required_texts", []),
                "missing_required_texts": missing,
                "forbidden_texts": surface.get("forbidden_texts", []),
                "forbidden_hits": forbidden,
                "required_final_url_prefix": final_url_prefix or None,
                "final_url_matches": final_url_matches,
                "status": "pass" if status_code == 200 and not missing and not forbidden and final_url_matches else "fail",
            }
        )

    payload = {
        "contract_name": "chummer.live_surface_parity",
        "generated_at_utc": now_iso(),
        "base_url": base,
        "status": "pass" if not failures else "fail",
        "verdict": "LIVE_SURFACE_PARITY_READY" if not failures else "LIVE_SURFACE_PARITY_NOT_READY",
        "results": results,
        "failures": failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that the deployed public surfaces match the reviewed public product copy and route behavior.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public base URL to verify.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = verify(args.base_url)
    if payload["status"] != "pass":
        raise SystemExit("live surface parity failed")
    print("live_surface_parity:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
