#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPLETION_ROOT = Path("/docker/chummercomplete/_completion/chummer_run_redesign_closure")
DEFAULT_BASE_URL = "https://chummer.run"


class SourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []
        self.video_posters: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "source" and values.get("src"):
            self.sources.append(values["src"])
        if tag.lower() == "video" and values.get("poster"):
            self.video_posters.append(values["poster"])
        if tag.lower() == "img" and values.get("src"):
            self.images.append(values["src"])


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fetch_text(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_head_ok(url: str) -> bool:
    response = requests.get(url, timeout=30, stream=True)
    response.raise_for_status()
    response.close()
    return True


def count_occurrences(text: str, needle: str) -> int:
    return len(re.findall(re.escape(needle), text, flags=re.IGNORECASE))


def build_payload(
    base_url: str,
    *,
    html_fetcher: Callable[[str], str] = fetch_text,
    asset_checker: Callable[[str], bool] = fetch_head_ok,
) -> dict:
    normalized_base_url = base_url.rstrip("/")
    failures: list[str] = []

    home_html = html_fetcher(f"{normalized_base_url}/")
    downloads_html = html_fetcher(f"{normalized_base_url}/downloads")
    status_html = html_fetcher(f"{normalized_base_url}/status")

    parser = SourceParser()
    parser.feed(home_html)
    product_video_sources = [
        source
        for source in parser.sources
        if "/media/promo/chummer6-flagship-promo" in source
    ]
    poster_sources = [*parser.video_posters, *parser.images]
    poster_urls = [
        urljoin(f"{normalized_base_url}/", poster)
        for poster in poster_sources
        if "/media/promo/chummer6-flagship-promo" in poster
    ]

    nav_panel_open = "nav-panel-open" in home_html
    hero_image_loaded = bool(poster_urls) and all(asset_checker(url) for url in poster_urls)
    video_sources_load = all(asset_checker(urljoin(f"{normalized_base_url}/", source)) for source in product_video_sources)
    product_video_retired = not product_video_sources and bool(poster_urls)
    stable_visible = 'id="stable"' in downloads_html and "Current stable build" in downloads_html
    nightly_visible = 'id="nightly"' in downloads_html and "Nightly" in downloads_html
    decision_card_count = count_occurrences(status_html, 'class="minimal-status-pill"')
    next_action_count = count_occurrences(status_html, 'data-analytics-event="status_next_action"')

    if nav_panel_open:
        failures.append("home navigation panel is open by default")
    if not hero_image_loaded:
        failures.append("home product video poster image is missing or unreachable")
    if product_video_sources and not video_sources_load:
        failures.append("home product video sources are unreachable")
    if not product_video_sources and not product_video_retired:
        failures.append("home product promo fallback image is missing or unreachable")
    if not stable_visible:
        failures.append("downloads stable lane is not visible")
    if not nightly_visible:
        failures.append("downloads nightly lane is not visible")
    if decision_card_count != 1:
        failures.append("status page should expose exactly one decision card")
    if next_action_count < 3:
        failures.append("status page should expose at least three next actions")

    payload = {
        "generated_at_utc": now_iso(),
        "base_url": normalized_base_url,
        "status": "pass" if not failures else "fail",
        "verdict": "READY" if not failures else "NOT_READY",
        "failures": failures,
        "results": [
            {
                "surface": "home",
                "nav_panel_open": nav_panel_open,
                "hero_image_loaded": hero_image_loaded,
                "product_video_sources": product_video_sources,
                "product_video_sources_load": video_sources_load,
                "product_video_retired": product_video_retired,
            },
            {
                "surface": "downloads",
                "stable_visible": stable_visible,
                "nightly_visible": nightly_visible,
            },
            {
                "surface": "status",
                "decision_card_count": decision_card_count,
                "next_action_count": next_action_count,
            },
        ],
    }
    return payload


def write_outputs(payload: dict, completion_root: Path) -> None:
    completion_root.mkdir(parents=True, exist_ok=True)
    json_path = completion_root / "MINIMAL_EXPERIENCE_GATE.generated.json"
    report_path = completion_root / "MINIMAL_EXPERIENCE_GATE.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(
        "\n".join(
            [
                "# Minimal Experience Gate",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                f"- Base URL: {payload['base_url']}",
                "- Checks: navigation closed by default, homepage product video/poster reachable, downloads exposes Stable and Nightly, status exposes one release decision plus next actions.",
                "",
                *[f"- {failure}" for failure in payload["failures"]],
                *[f"- {result['surface']} checked" for result in payload["results"]],
                "",
            ]
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the minimal public experience against a live or local Chummer base URL.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--completion-dir", default=str(DEFAULT_COMPLETION_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload(args.base_url)
    write_outputs(payload, Path(args.completion_dir))
    print(f"minimal_experience_gate:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
