#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from html import unescape
from pathlib import Path

import requests


COMPLETION_DIR = Path(
    os.environ.get(
        "CHUMMER_COMPLETION_DIR",
        "/docker/chummercomplete/_completion/pregold_ux_pwa_black_ledger",
    )
)


def strip_tags(html_text: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html_text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    response = requests.get(args.base_url.rstrip("/") + "/", timeout=30)
    response.raise_for_status()
    html_text = response.text

    main_match = re.search(r"<main\b[^>]*>(.*?)</main>", html_text, flags=re.I | re.S)
    main_html = main_match.group(1) if main_match else html_text
    main_text = strip_tags(main_html)
    hero_match = re.search(r'<section\b[^>]*data-homepage-section="hero"[^>]*>(.*?)</section>', html_text, flags=re.I | re.S)
    hero_html = hero_match.group(1) if hero_match else ""

    section_count = len(re.findall(r'data-homepage-section="[^"]+"', html_text))
    section_ids = re.findall(r'data-homepage-section="([^"]+)"', html_text)
    button_like_count = len(re.findall(r'class="[^"]*\bbutton-like\b', html_text))
    link_count = len(re.findall(r"<a\b", main_html, flags=re.I))
    proof_mentions = len(re.findall(r"\bproof\b", main_text, flags=re.I))
    artifact_mentions = len(re.findall(r"\bartifact[s]?\b", main_text, flags=re.I))
    word_count = len(main_text.split())
    hero_status_chip_count = len(re.findall(r'class="[^"]*(?:^|\s)proof-chip(?:\s|")', hero_html))
    proof_card_count = len(re.findall(r'class="[^"]*\bflagship-coverage__card\b', main_html))
    repeated_download_ctas = len(re.findall(r'href="/downloads"', main_html))

    result = {
        "status": "pass",
        "base_url": args.base_url,
        "section_count": section_count,
        "sections": section_ids,
        "button_like_count": button_like_count,
        "link_count": link_count,
        "proof_mentions": proof_mentions,
        "artifact_mentions": artifact_mentions,
        "word_count": word_count,
        "hero_status_chip_count": hero_status_chip_count,
        "proof_card_count": proof_card_count,
        "downloads_cta_count": repeated_download_ctas,
        "summary": "Homepage stays within the simplified front-door noise budget.",
    }

    failures: list[str] = []
    if section_count > 5:
        failures.append(f"expected at most 5 homepage sections, found {section_count}")
    if word_count > 900:
        failures.append(f"homepage main content is too long ({word_count} words)")
    if proof_mentions > 4:
        failures.append(f"homepage mentions proof too often ({proof_mentions})")
    if artifact_mentions > 0:
        failures.append(f"homepage mentions artifacts too often ({artifact_mentions})")
    if link_count > 40:
        failures.append(f"homepage contains too many links ({link_count})")
    if hero_status_chip_count > 4:
        failures.append(f"homepage exposes too many hero status chips ({hero_status_chip_count})")
    if proof_card_count > 3:
        failures.append(f"homepage exposes too many proof cards ({proof_card_count})")
    if repeated_download_ctas > 3:
        failures.append(f"homepage repeats the downloads destination too often ({repeated_download_ctas})")

    COMPLETION_DIR.mkdir(parents=True, exist_ok=True)
    report_path = COMPLETION_DIR / "NOISE_BUDGET_REPORT.md"
    if failures:
        result["status"] = "fail"
        result["summary"] = "Homepage exceeds the front-door noise budget."
        result["failures"] = failures
    report_lines = [
        "# Noise Budget Report",
        "",
        f"- Base URL: {args.base_url}",
        f"- Status: `{result['status']}`",
        f"- Homepage sections: `{section_count}`",
        f"- Hero status chips: `{hero_status_chip_count}`",
        f"- Proof cards: `{proof_card_count}`",
        f"- Link count: `{link_count}`",
        f"- Proof mentions: `{proof_mentions}`",
        f"- Artifact mentions: `{artifact_mentions}`",
        f"- Downloads CTA count: `{repeated_download_ctas}`",
        f"- Word count: `{word_count}`",
    ]
    if failures:
        report_lines.extend(["", "## Failures", ""])
        report_lines.extend(f"- {failure}" for failure in failures)
    else:
        report_lines.extend(["", "Homepage stays within the current front-door noise budget."])
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
