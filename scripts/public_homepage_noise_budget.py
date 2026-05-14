#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape

import requests


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

    section_count = len(re.findall(r'data-homepage-section="[^"]+"', html_text))
    section_ids = re.findall(r'data-homepage-section="([^"]+)"', html_text)
    button_like_count = len(re.findall(r'class="[^"]*\bbutton-like\b', html_text))
    link_count = len(re.findall(r"<a\b", main_html, flags=re.I))
    proof_mentions = len(re.findall(r"\bproof\b", main_text, flags=re.I))
    artifact_mentions = len(re.findall(r"\bartifact[s]?\b", main_text, flags=re.I))
    word_count = len(main_text.split())

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
        "summary": "Homepage stays within the simplified front-door noise budget.",
    }

    failures: list[str] = []
    if section_count != 6:
        failures.append(f"expected exactly 6 homepage sections, found {section_count}")
    if word_count > 900:
        failures.append(f"homepage main content is too long ({word_count} words)")
    if proof_mentions > 10:
        failures.append(f"homepage mentions proof too often ({proof_mentions})")
    if artifact_mentions > 1:
        failures.append(f"homepage mentions artifacts too often ({artifact_mentions})")
    if link_count > 40:
        failures.append(f"homepage contains too many links ({link_count})")

    if failures:
        result["status"] = "fail"
        result["summary"] = "Homepage exceeds the front-door noise budget."
        result["failures"] = failures
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
