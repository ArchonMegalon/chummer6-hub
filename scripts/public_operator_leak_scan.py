#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import requests

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


EXCLUDED_PUBLIC_VIEWS = {"Home.cshtml", "ReleaseUpload.cshtml", "LedgerFactionWorkspace.cshtml"}
HTML_ROUTES = [
    "/feedback",
    "/feedback/operations",
    "/feedback/operations/lookup",
    "/ledger",
    "/black-ledger",
    "/packages",
    "/karma-forge",
    "/participate/karma-forge",
    "/participate/karma-forge/submitted/sample-submission-id",
    "/contact/submitted/sample-case-id",
]
LEAK_PATTERNS = {
    "operator_term": re.compile(r"\boperator(s)?\b", re.IGNORECASE),
    "webhook_term": re.compile(r"\bwebhook(s)?\b", re.IGNORECASE),
    "product_governor": re.compile(r"\bProduct Governor\b", re.IGNORECASE),
    "provider_message_id": re.compile(r"\bprovider message id\b", re.IGNORECASE),
    "provider_callback": re.compile(r"\bprovider callback(s)?\b", re.IGNORECASE),
    "provider_identity": re.compile(r"\bprovider identity\b", re.IGNORECASE),
    "provider_state": re.compile(r"\bprovider state\b", re.IGNORECASE),
    "provider_payload": re.compile(r"\braw provider payload(s)?\b", re.IGNORECASE),
    "env_var": re.compile(r"\bCHUMMER_[A-Z0-9_]+\b"),
    "webhook_secret": re.compile(r"\bX-[A-Za-z0-9-]*Webhook-Secret\b"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan public HTML and customer-facing view sources for operator or provider leak strings.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def public_source_files() -> list[Path]:
    files = [
        RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_PublicSignalOperationsPacket.cshtml",
    ]
    public_views_root = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding"
    for path in sorted(public_views_root.glob("*.cshtml")):
        if path.name not in EXCLUDED_PUBLIC_VIEWS:
            files.append(path)
    return files


def relative_label(path: Path) -> str:
    try:
        return str(path.relative_to(RUN_SERVICES_ROOT))
    except ValueError:
        return str(path)


def find_leaks(surface: str, path_label: str, text: str) -> list[dict]:
    hits = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for leak_id, pattern in LEAK_PATTERNS.items():
            if pattern.search(line):
                hits.append(
                    {
                        "surface": surface,
                        "path": path_label,
                        "line": line_number,
                        "leak_id": leak_id,
                        "text": line.strip(),
                    }
                )
    return hits


def scan_sources() -> list[dict]:
    hits: list[dict] = []
    for path in public_source_files():
        hits.extend(find_leaks("file", relative_label(path), path.read_text(encoding="utf-8")))
    return hits


def scan_html(base_url: str) -> tuple[list[dict], list[dict]]:
    all_hits: list[dict] = []
    route_statuses: list[dict] = []
    session = requests.Session()
    for route in HTML_ROUTES:
        response = session.get(f"{base_url}{route}", timeout=30)
        response.raise_for_status()
        route_hits = find_leaks("html", route, response.text)
        all_hits.extend(route_hits)
        route_statuses.append(
            {
                "route": route,
                "status_code": response.status_code,
                "hit_count": len(route_hits),
            }
        )
    return all_hits, route_statuses


def run(base_url: str) -> int:
    source_hits = scan_sources()
    html_hits, route_statuses = scan_html(base_url)
    hits = source_hits + html_hits
    passed = not hits

    payload = {
        "contract_name": "chummer.public_provider_leak_scan",
        "status": "pass" if passed else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "source_file_count": len(public_source_files()),
        "html_route_count": len(HTML_ROUTES),
        "source_hit_count": len(source_hits),
        "html_hit_count": len(html_hits),
        "route_statuses": route_statuses,
        "hits": hits,
    }
    write_json(completion_path("PUBLIC_PROVIDER_LEAK_SCAN.generated.json"), payload)
    write_json(completion_path("PUBLIC_OPERATOR_LEAK_SCAN.generated.json"), payload)

    lines = [
        "# Janitor deployed HTML report",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Status: `{payload['status']}`",
        f"- Source files scanned: {payload['source_file_count']}",
        f"- HTML routes scanned: {payload['html_route_count']}",
        f"- Source hits: {payload['source_hit_count']}",
        f"- HTML hits: {payload['html_hit_count']}",
        "",
        "## Route scan",
        "",
    ]
    for status in route_statuses:
        lines.append(
            f"- `{status['route']}`: status=`{status['status_code']}` hits=`{status['hit_count']}`"
        )
    if hits:
        lines.extend(["", "## Hits", ""])
        lines.extend(
            f"- `{hit['surface']} {hit['path']}:{hit['line']}` `{hit['leak_id']}` - {hit['text']}"
            for hit in hits[:50]
        )

    report = "\n".join(lines)
    write_text(completion_path("JANITOR_DEPLOYED_HTML_REPORT.md"), report)
    write_text(completion_path("PUBLIC_OPERATOR_LEAK_SCAN.md"), report)
    return 0 if passed else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
