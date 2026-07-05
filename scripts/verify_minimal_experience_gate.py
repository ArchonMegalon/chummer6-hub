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
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "source" and values.get("src"):
            self.sources.append(values["src"])
        if tag.lower() == "video" and values.get("poster"):
            self.video_posters.append(values["poster"])
        if tag.lower() == "img" and values.get("src"):
            self.images.append(values["src"])
        if tag.lower() == "a" and values.get("href"):
            self.links.append(values["href"])


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._hidden_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        class_tokens = {token.strip().lower() for token in values.get("class", "").split() if token.strip()}
        parent_hidden = self._hidden_stack[-1] if self._hidden_stack else False
        current_hidden = (
            tag.lower() in {"script", "style", "svg", "template"}
            or "hidden" in values
            or values.get("aria-hidden", "").lower() == "true"
            or "sr-only" in class_tokens
        )
        self._hidden_stack.append(parent_hidden or current_hidden)

    def handle_endtag(self, tag: str) -> None:
        if self._hidden_stack:
            self._hidden_stack.pop()

    def handle_data(self, data: str) -> None:
        hidden = self._hidden_stack[-1] if self._hidden_stack else False
        if not hidden and data.strip():
            self.parts.append(" ".join(data.split()))

    @property
    def text(self) -> str:
        return " ".join(self.parts)


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


def count_class_token(text: str, token: str) -> int:
    pattern = rf'class=["\'][^"\']*(?<![\w-]){re.escape(token)}(?![\w-])[^"\']*["\']'
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def count_dated_update_mentions(text: str) -> int:
    return len(re.findall(r"\bUpdated\s+\d{4}-\d{2}-\d{2}\b", text, flags=re.IGNORECASE))


def find_release_noise(text: str) -> list[str]:
    patterns = [
        r"\brun-\d{8}-\d{6}\b",
        r"\bReleased\b",
        r"\bChecks passed\b",
        r"\bstale proof\b",
        r"\bnot gold-ready\b",
    ]
    findings: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            findings.append(pattern)
    return findings


def visible_text(html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(html)
    return parser.text


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
    downloads_text = visible_text(downloads_html)
    status_text = visible_text(status_html)

    parser = SourceParser()
    parser.feed(home_html)
    product_video_sources = [
        source
        for source in parser.sources
        if "/media/promo/every-wonder-horizon-promo" in source
    ]
    product_video_links = [
        link
        for link in parser.links
        if "/media/promo/every-wonder-horizon-promo" in link
    ]
    poster_sources = [*parser.video_posters, *parser.images]
    image_urls = [urljoin(f"{normalized_base_url}/", image) for image in parser.images]

    nav_panel_open = "nav-panel-open" in home_html
    hero_image_loaded = bool(image_urls) and all(asset_checker(url) for url in image_urls)
    video_sources_load = all(asset_checker(urljoin(f"{normalized_base_url}/", source)) for source in product_video_sources)
    promo_video_link_load = all(asset_checker(urljoin(f"{normalized_base_url}/", link)) for link in product_video_links)
    stable_visible = (
        'id="stable"' in downloads_html
        and "Stable" in downloads_text
        and "Stable release" in downloads_text
    )
    nightly_visible = 'id="nightly"' in downloads_html and "Nightly" in downloads_text
    decision_card_count = count_class_token(status_html, "minimal-status-pill")
    next_action_count = count_occurrences(status_html, 'data-analytics-event="status_next_action"')
    status_updated_count = count_dated_update_mentions(status_text)
    downloads_updated_count = count_dated_update_mentions(downloads_text)
    status_release_noise = find_release_noise(status_text)
    downloads_release_noise = find_release_noise(downloads_text)

    if nav_panel_open:
        failures.append("home navigation panel is open by default")
    if not hero_image_loaded:
        failures.append("home hero image is missing or unreachable")
    if not product_video_sources and not product_video_links:
        failures.append("home promo video entry is missing")
    if product_video_sources and not video_sources_load:
        failures.append("home product video sources are unreachable")
    if product_video_links and not promo_video_link_load:
        failures.append("home promo video link is unreachable")
    if not stable_visible:
        failures.append("downloads stable lane is not visible")
    if not nightly_visible:
        failures.append("downloads nightly lane is not visible")
    if decision_card_count != 1:
        failures.append("status page should expose exactly one decision card")
    if next_action_count != 2:
        failures.append("status page should expose exactly two next actions")
    if status_updated_count > 1:
        failures.append("status page repeats the update date")
    if downloads_updated_count > 1:
        failures.append("downloads page repeats the update date")
    if status_release_noise:
        failures.append(f"status page exposes internal release noise: {', '.join(status_release_noise)}")
    if downloads_release_noise:
        failures.append(f"downloads page exposes internal release noise: {', '.join(downloads_release_noise)}")

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
                "product_video_links": product_video_links,
                "product_video_links_load": promo_video_link_load,
            },
            {
                "surface": "downloads",
                "stable_visible": stable_visible,
                "nightly_visible": nightly_visible,
                "updated_label_count": downloads_updated_count,
                "release_noise": downloads_release_noise,
            },
            {
                "surface": "status",
                "decision_card_count": decision_card_count,
                "next_action_count": next_action_count,
                "updated_label_count": status_updated_count,
                "release_noise": status_release_noise,
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
                "- Checks: navigation closed by default, homepage hero image plus promo-video entry reachable, downloads exposes Stable and Nightly, status exposes one release decision plus two next actions.",
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
