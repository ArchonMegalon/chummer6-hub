#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text
from verify_public_copy_leak_gate import visible_text


DESIGN_FILES = [
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml",
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_FEATURE_REGISTRY.yaml",
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_RELEASE_EXPERIENCE.yaml",
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_DOWNLOADS_POLICY.md",
    RUN_SERVICES_ROOT / "docs" / "PUBLIC_LANDING_SURFACE.md",
]
EXCLUDED_PUBLIC_VIEWS = {"Home.cshtml", "ReleaseUpload.cshtml"}
HTML_ROUTES = [
    "/",
    "/downloads",
    "/now",
    "/packages",
    "/mobile",
    "/play",
    "/feedback",
    "/feedback/operations",
    "/feedback/operations/lookup",
    "/ledger",
    "/black-ledger",
    "/roadmap",
    "/changelog",
    "/help",
    "/contact",
    "/participate",
    "/partizipate",
    "/karma-forge",
    "/participate/karma-forge",
    "/participate/karma-forge/submitted/sample-submission-id",
    "/contact/submitted/sample-case-id",
]
ALLOWED_EXTERNAL_REDIRECT_ROUTES = {
    "/participate",
    "/feedback",
    "/help/feedback",
}
FORBIDDEN_PATTERN = re.compile(
    r"\b(ProductLift|ICanpreneur|Icanpreneur|Emailit|Deftform|MetaSurvey|Lunacal|Signitic|Teable|ApproveThis|NextStep|FacePop|ClickRank|Katteb)\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan public copy and rendered HTML for forbidden provider or LTD names.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def public_source_files() -> list[Path]:
    paths = list(DESIGN_FILES)
    public_views_root = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding"
    for path in sorted(public_views_root.glob("*.cshtml")):
        if path.name not in EXCLUDED_PUBLIC_VIEWS:
            paths.append(path)
    paths.append(RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_PublicSignalOperationsPacket.cshtml")
    return paths


def relative_label(path: Path) -> str:
    try:
        return str(path.relative_to(RUN_SERVICES_ROOT))
    except ValueError:
        return str(path)


def scan_text(surface: str, path_label: str, text: str) -> list[dict]:
    hits = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if FORBIDDEN_PATTERN.search(line):
            hits.append(
                {
                    "surface": surface,
                    "path": path_label,
                    "line": line_number,
                    "text": line.strip(),
                }
            )
    return hits


def scan_files() -> list[dict]:
    hits: list[dict] = []
    for path in public_source_files():
        hits.extend(scan_text("file", relative_label(path), path.read_text(encoding="utf-8")))
    return hits


def scan_html(base_url: str) -> list[dict]:
    hits: list[dict] = []
    session = requests.Session()
    base_host = urlparse(base_url).netloc.lower()
    for route in HTML_ROUTES:
        url = f"{base_url}{route}"
        response = session.get(url, timeout=30, allow_redirects=False)
        response.raise_for_status()
        if 300 <= response.status_code < 400:
            redirect_location = response.headers.get("Location", "").strip()
            redirect_url = urljoin(url, redirect_location) if redirect_location else ""
            redirect_host = urlparse(redirect_url).netloc.lower()
            if redirect_host and redirect_host != base_host and route in ALLOWED_EXTERNAL_REDIRECT_ROUTES:
                continue
            if redirect_url and (not redirect_host or redirect_host == base_host):
                response = session.get(redirect_url, timeout=30, allow_redirects=False)
                response.raise_for_status()
        hits.extend(scan_text("html", route, visible_text(response.text)))
    return hits


def run(base_url: str) -> int:
    hits = scan_files() + scan_html(base_url)
    payload = {
        "contract_name": "chummer.public_forbidden_string_scan",
        "status": "pass" if not hits else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "scanned_source_file_count": len(public_source_files()),
        "scanned_html_route_count": len(HTML_ROUTES),
        "hit_count": len(hits),
        "hits": hits,
    }
    write_json(completion_path("PUBLIC_FORBIDDEN_STRING_SCAN.generated.json"), payload)

    lines = [
        "# Public copy scrub report",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Status: `{payload['status']}`",
        f"- Source files scanned: {payload['scanned_source_file_count']}",
        f"- HTML routes scanned: {payload['scanned_html_route_count']}",
        f"- Hit count: {payload['hit_count']}",
    ]
    if hits:
        lines.extend(["", "## Hits", ""])
        lines.extend(f"- `{hit['surface']} {hit['path']}:{hit['line']}` - {hit['text']}" for hit in hits[:50])
    else:
        lines.extend(["", "No forbidden provider or LTD strings were found on the audited public sources or HTML routes."])

    write_text(completion_path("PUBLIC_COPY_SCRUB_REPORT.md"), "\n".join(lines))
    return 0 if not hits else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
