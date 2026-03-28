#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BANNED_COPY = re.compile(r"\b(Read the linked detail|Read more|Learn more)\b", re.IGNORECASE)


@dataclass
class AuditRoute:
    path: str
    expected_text: str | None = None
    required_texts: tuple[str, ...] = ()
    forbidden_texts: tuple[str, ...] = ()
    expected_status: int = 200
    expects_header_count: int | None = None
    allows_redirect: bool = False


class HeaderCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "header":
            return
        attrs_map = dict(attrs)
        if "data-site-header" in attrs_map:
            self.count += 1


def fetch(base_url: str, path: str) -> tuple[int, str, dict[str, str], str]:
    url = urljoin(base_url, path)
    request = Request(url, headers={"User-Agent": "chummer-hub-live-audit"})
    with urlopen(request, timeout=20) as response:
        status = response.status
        body = response.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in response.headers.items()}
        final_url = response.geturl()
    return status, body, headers, final_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the public Chummer Hub surface.")
    parser.add_argument("--base-url", default="https://chummer.run", help="Base URL to audit.")
    parser.add_argument("--poll-seconds", type=int, default=0, help="Sleep before starting the audit.")
    args = parser.parse_args()

    if args.poll_seconds > 0:
        time.sleep(args.poll_seconds)

    routes = [
        AuditRoute("/", "Create account to get preview", required_texts=("Final pool 9",), expects_header_count=1),
        AuditRoute("/what-is-chummer", "One product for rules truth, living dossiers, and session return.", expects_header_count=1),
        AuditRoute(
            "/now",
            "Current preview, visible proof, and known posture",
            required_texts=("What you can verify now", "Build, explain, and run with visible evidence", "Status guide"),
            expects_header_count=1),
        AuditRoute(
            "/downloads",
            "Install the current preview",
            required_texts=("Create account to get preview", "Already have an account? Sign in", "Advanced download options", "Release notes, known issues, and requirements"),
            forbidden_texts=("Package details",),
            expects_header_count=1),
        AuditRoute("/horizons", "What Chummer is building toward", required_texts=("Preparing next", "Designing in public", "Research track", "Status guide"), forbidden_texts=("Research tracks",), expects_header_count=1),
        AuditRoute("/artifacts", "Current proof surfaces", required_texts=("Preview in progress", "Status guide"), expects_header_count=1),
        AuditRoute("/artifacts/current-preview-build", "Current preview build", expects_header_count=1),
        AuditRoute("/roadmap/nexus-pan", "NEXUS-PAN", expects_header_count=1),
        AuditRoute("/participate", "Choose how to participate", expects_header_count=1),
        AuditRoute("/help", "Get help without guessing", required_texts=("Fallback:",), expects_header_count=1),
        AuditRoute("/faq", "Plain answers before you spend more time", expects_header_count=1),
        AuditRoute("/contact", "Open the right support case", expects_header_count=1),
        AuditRoute("/privacy", "What Chummer stores, and what it does not", expects_header_count=1),
        AuditRoute("/terms", "Preview terms in plain language", expects_header_count=1),
        AuditRoute("/robots.txt", "Disallow: /"),
    ]

    for route in routes:
        status, body, headers, final_url = fetch(args.base_url, route.path)
        if status != route.expected_status:
            raise AssertionError(f"{route.path} returned {status}, expected {route.expected_status}")
        if route.expected_text and route.expected_text not in body:
            raise AssertionError(f"{route.path} missing expected text: {route.expected_text}")
        for snippet in route.required_texts:
            if snippet not in body:
                raise AssertionError(f"{route.path} missing required text: {snippet}")
        for snippet in route.forbidden_texts:
            if snippet in body:
                raise AssertionError(f"{route.path} rendered forbidden text: {snippet}")
        if route.path != "/robots.txt":
            robots = headers.get("x-robots-tag", "")
            if "noindex" not in robots.lower():
                raise AssertionError(f"{route.path} missing X-Robots-Tag noindex header")
            if BANNED_COPY.search(body):
                raise AssertionError(f"{route.path} rendered banned generic CTA copy")
            if route.path == "/" and body.count("Final pool 9") != 1:
                raise AssertionError("/ rendered the proof teaser more than once")
            if route.expects_header_count is not None:
                parser_ = HeaderCounter()
                parser_.feed(body)
                if parser_.count != route.expects_header_count:
                    raise AssertionError(f"{route.path} rendered {parser_.count} site headers, expected {route.expects_header_count}")
        print(f"ok {route.path} -> {final_url}")

    status, _, _, final_url = fetch(args.base_url, "/status")
    if status != 200 or not final_url.rstrip("/").endswith("/now"):
        raise AssertionError("/status did not resolve to /now")
    print(f"ok /status -> {final_url}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - operational script
        print(f"hub live audit failed: {exc}", file=sys.stderr)
        raise
