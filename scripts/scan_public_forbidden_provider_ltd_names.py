#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import requests

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json


FILE_TARGETS = [
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml",
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_FEATURE_REGISTRY.yaml",
    RUN_SERVICES_ROOT / "docs" / "PUBLIC_LANDING_SURFACE.md",
]
FILE_TARGETS.append(RUN_SERVICES_ROOT.parent / "Chummer6" / "DOWNLOAD.md")

HTML_ROUTES = ["/", "/packages", "/mobile", "/play", "/feedback", "/roadmap", "/changelog", "/help", "/contact"]
FORBIDDEN_PATTERN = re.compile(
    r"\b(ProductLift|ICanpreneur|Icanpreneur|Emailit|Deftform|MetaSurvey|Lunacal|Signitic|Teable|ApproveThis|NextStep|FacePop|ClickRank|Katteb)\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan public-surface files and rendered HTML for forbidden provider or LTD names.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def scan_files() -> list[dict]:
    hits: list[dict] = []
    for path in FILE_TARGETS:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_PATTERN.search(line):
                hits.append(
                    {
                        "surface": "file",
                        "path": str(path.relative_to(RUN_SERVICES_ROOT)) if path.is_relative_to(RUN_SERVICES_ROOT) else str(path),
                        "line": line_number,
                        "text": line.strip(),
                    }
                )
    return hits


def scan_html(base_url: str) -> list[dict]:
    hits: list[dict] = []
    session = requests.Session()
    for route in HTML_ROUTES:
        response = session.get(f"{base_url}{route}", timeout=30)
        response.raise_for_status()
        for line_number, line in enumerate(response.text.splitlines(), start=1):
            if FORBIDDEN_PATTERN.search(line):
                hits.append(
                    {
                        "surface": "html",
                        "path": route,
                        "line": line_number,
                        "text": line.strip(),
                    }
                )
    return hits


def run(base_url: str) -> int:
    hits = scan_files() + scan_html(base_url)
    payload = {
        "contract_name": "chummer.public_forbidden_string_scan",
        "status": "pass" if not hits else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "scanned_file_count": len(FILE_TARGETS),
        "scanned_html_route_count": len(HTML_ROUTES),
        "hit_count": len(hits),
        "hits": hits,
    }
    write_json(completion_path("PUBLIC_FORBIDDEN_STRING_SCAN.generated.json"), payload)
    return 0 if not hits else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url)

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
