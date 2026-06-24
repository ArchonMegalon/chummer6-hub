#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from requests import exceptions as requests_exceptions


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT = REPO_ROOT / ".codex-studio" / "published" / "PUBLIC_SHELL_CLICKABILITY_GATE.generated.json"
DEFAULT_PAGES = ["/", "/status", "/downloads", "/feedback", "/partizipate", "/what-is-chummer"]
FORBIDDEN_TEXT_PATTERNS = [
    r"chummer-api",
    r"127\.0\.0\.1",
    r"host\.docker\.internal",
    r"localhost",
    r"Load Demo Runner",
    r"Open Demo",
]
ACCEPTABLE_STATUSES = {200, 301, 302, 303, 307, 308}
DEFAULT_REQUEST_TIMEOUT_SECONDS = 8
DEFAULT_RUNTIME_BUDGET_SECONDS = 90


class AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value.strip())
                return


@dataclass
class LinkResult:
    page: str
    href: str
    resolved_url: str
    success: bool
    status_code: int | None
    final_url: str | None
    detail: str | None = None


@dataclass
class PageResult:
    page: str
    success: bool
    status_code: int | None
    forbidden_text_hits: list[str]
    link_count: int
    failed_link_count: int
    detail: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify public shell pages stay clickable and free of internal-host/debug copy leaks.")
    parser.add_argument("--base-url", default="https://chummer.run", help="Base public URL to verify")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to write the machine-readable proof packet")
    return parser.parse_args(argv)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def find_forbidden_text_hits(html: str) -> list[str]:
    hits: list[str] = []
    for pattern in FORBIDDEN_TEXT_PATTERNS:
        if re.search(pattern, html, re.IGNORECASE):
            hits.append(pattern)
    return hits


def extract_same_origin_links(page_url: str, html: str, base_origin: str) -> list[str]:
    parser = AnchorExtractor()
    parser.feed(html)
    seen: list[str] = []
    for href in parser.hrefs:
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        resolved = urljoin(page_url, href)
        if not resolved.startswith(base_origin):
            continue
        if resolved not in seen:
            seen.append(resolved)
    return seen


def walk_link(session: requests.Session, resolved_url: str, base_origin: str) -> LinkResult:
    current_url = resolved_url
    for _ in range(8):
        last_exception: Exception | None = None
        response = None
        for attempt in range(2):
            try:
                response = session.get(current_url, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS, allow_redirects=False)
                last_exception = None
                break
            except (requests_exceptions.ReadTimeout, requests_exceptions.ConnectTimeout) as exc:
                last_exception = exc
                if attempt == 0:
                    continue
            except Exception as exc:  # pragma: no cover - exercised via failure handling
                last_exception = exc
                break

        if response is None:
            return LinkResult(
                page="",
                href="",
                resolved_url=resolved_url,
                success=False,
                status_code=None,
                final_url=current_url,
                detail=str(last_exception) if last_exception else "request failed without response",
            )

        status_code = response.status_code
        if status_code not in ACCEPTABLE_STATUSES:
            return LinkResult(
                page="",
                href="",
                resolved_url=resolved_url,
                success=False,
                status_code=status_code,
                final_url=current_url,
                detail=f"unexpected status {status_code}",
            )

        if status_code < 300 or status_code >= 400:
            return LinkResult(
                page="",
                href="",
                resolved_url=resolved_url,
                success=True,
                status_code=status_code,
                final_url=current_url,
            )

        location = response.headers.get("Location") or ""
        if not location:
            return LinkResult(
                page="",
                href="",
                resolved_url=resolved_url,
                success=False,
                status_code=status_code,
                final_url=current_url,
                detail="redirect missing Location header",
            )

        next_url = urljoin(current_url, location)
        if not next_url.startswith(base_origin):
            return LinkResult(
                page="",
                href="",
                resolved_url=resolved_url,
                success=True,
                status_code=status_code,
                final_url=next_url,
            )
        current_url = next_url

    return LinkResult(
        page="",
        href="",
        resolved_url=resolved_url,
        success=False,
        status_code=None,
        final_url=current_url,
        detail="redirect loop exceeded maximum hop count",
    )


def verify_page(session: requests.Session, base_origin: str, page: str, link_cache: dict[str, LinkResult]) -> tuple[PageResult, list[LinkResult]]:
    page_url = urljoin(f"{base_origin}/", page.lstrip("/"))
    try:
        response = session.get(page_url, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS)
    except Exception as exc:
        return (
            PageResult(page=page, success=False, status_code=None, forbidden_text_hits=[], link_count=0, failed_link_count=0, detail=str(exc)),
            [],
        )

    forbidden_hits = find_forbidden_text_hits(response.text)
    links = extract_same_origin_links(page_url, response.text, base_origin)
    link_results: list[LinkResult] = []
    failed_link_count = 0
    for link in links:
        cached = link_cache.get(link)
        if cached is None:
            cached = walk_link(session, link, base_origin)
            cached.href = link
            link_cache[link] = cached
        result = LinkResult(
            page=page,
            href=link,
            resolved_url=cached.resolved_url,
            success=cached.success,
            status_code=cached.status_code,
            final_url=cached.final_url,
            detail=cached.detail,
        )
        link_results.append(result)
        if not result.success:
            failed_link_count += 1

    success = response.status_code == 200 and not forbidden_hits and failed_link_count == 0
    detail = None
    if response.status_code != 200:
        detail = f"page returned {response.status_code}"
    elif forbidden_hits:
        detail = "forbidden internal-host or debug/demo copy found"
    elif failed_link_count:
        detail = "one or more same-origin links were not clickable"

    return (
        PageResult(
            page=page,
            success=success,
            status_code=response.status_code,
            forbidden_text_hits=forbidden_hits,
            link_count=len(links),
            failed_link_count=failed_link_count,
            detail=detail,
        ),
        link_results,
    )


def build_payload(base_url: str, page_results: Iterable[PageResult], link_results: Iterable[LinkResult]) -> dict:
    page_results_list = list(page_results)
    link_results_list = list(link_results)
    failed_pages = [result.page for result in page_results_list if not result.success]
    failed_links = [result.resolved_url for result in link_results_list if not result.success]
    status = "pass" if not failed_pages and not failed_links else "fail"
    return {
        "status": status,
        "base_url": base_url,
        "generated_at": now_iso(),
        "summary": {
            "page_count": len(page_results_list),
            "link_count": len(link_results_list),
            "failed_page_count": len(failed_pages),
            "failed_link_count": len(failed_links),
            "failed_pages": failed_pages,
            "failed_links": failed_links,
        },
        "pages": [asdict(result) for result in page_results_list],
        "links": [asdict(result) for result in link_results_list],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base_url = normalize_base_url(args.base_url)
    base_origin = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    session = requests.Session()
    session.headers.update({"User-Agent": "chummer-public-shell-clickability-gate/1.0"})
    deadline = time.monotonic() + DEFAULT_RUNTIME_BUDGET_SECONDS

    page_results: list[PageResult] = []
    link_results: list[LinkResult] = []
    link_cache: dict[str, LinkResult] = {}
    for page in DEFAULT_PAGES:
        if time.monotonic() >= deadline:
            page_results.append(
                PageResult(
                    page=page,
                    success=False,
                    status_code=None,
                    forbidden_text_hits=[],
                    link_count=0,
                    failed_link_count=0,
                    detail="runtime budget exceeded before this page could be verified",
                )
            )
            continue
        page_result, page_link_results = verify_page(session, base_origin, page, link_cache)
        page_results.append(page_result)
        link_results.extend(page_link_results)

    payload = build_payload(base_url, page_results, link_results)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if payload["status"] != "pass":
        json.dump(payload, sys.stderr, indent=2)
        sys.stderr.write("\n")
        return 1

    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
