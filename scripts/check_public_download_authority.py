#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import requests

from absolute_completion_common import CHUMMER6_ROOT, LocalHubApp, completion_path, now_iso, write_json


DOWNLOAD_DOC = CHUMMER6_ROOT / "DOWNLOAD.md"
ALLOWED_LINE_PATTERNS = [
    re.compile(r"not the normal public download path", re.IGNORECASE),
    re.compile(r"do not need github", re.IGNORECASE),
    re.compile(r"use github only when you want source", re.IGNORECASE),
    re.compile(r"development and audit evidence surface", re.IGNORECASE),
]
FORBIDDEN_LINK_PATTERN = re.compile(r"github\.com/.*/releases", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check that public download guidance keeps chummer.run as the acquisition authority.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def scan_download_doc() -> list[dict]:
    hits: list[dict] = []
    for line_number, line in enumerate(DOWNLOAD_DOC.read_text(encoding="utf-8").splitlines(), start=1):
        lowered = line.lower()
        if "github" not in lowered:
            continue
        if any(pattern.search(line) for pattern in ALLOWED_LINE_PATTERNS):
            continue
        hits.append({"path": str(DOWNLOAD_DOC), "line": line_number, "text": line.strip()})
    return hits


def scan_download_html(base_url: str) -> list[dict]:
    response = requests.get(f"{base_url}/downloads", timeout=30)
    response.raise_for_status()
    hits: list[dict] = []
    for line_number, line in enumerate(response.text.splitlines(), start=1):
        if FORBIDDEN_LINK_PATTERN.search(line):
            hits.append({"path": "/downloads", "line": line_number, "text": line.strip()})
    return hits


def run(base_url: str) -> int:
    hits = scan_download_doc() + scan_download_html(base_url)
    payload = {
        "contract_name": "chummer.public_download_authority",
        "status": "pass" if not hits else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "hit_count": len(hits),
        "hits": hits,
    }
    write_json(completion_path("PUBLIC_DOWNLOAD_AUTHORITY.generated.json"), payload)
    return 0 if not hits else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url)

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
