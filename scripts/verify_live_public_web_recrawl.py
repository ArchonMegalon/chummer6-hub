#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = REPO_ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "LIVE_PUBLIC_WEB_RECRAWL.generated.json"
DEFAULT_BASE_URL = "https://chummer.run"
RECRAWL_MAX_AGE_HOURS = 24
REQUIRED_PATHS = [
    "/",
    "/status",
    "/downloads",
    "/ledger",
    "/ledger/map",
    "/ledger/factions",
    "/ledger/newsroom",
]
FORBIDDEN_COPY = [
    "load demo runner",
    "open demo",
    "chummer-api",
    "127.0.0.1",
    "host.docker.internal",
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_excerpt(html: str, max_words: int = 40) -> str:
    parser = TextExtractor()
    parser.feed(html)
    words = " ".join(parser.parts).split()
    return " ".join(words[:max_words])


def fetch(url: str) -> tuple[int | None, str, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "chummer-live-recrawl/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return int(response.status), body, headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return int(exc.code), body, headers
    except Exception as exc:  # pragma: no cover - network failure path
        return None, str(exc), {}


def recrawl(base_url: str) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    forbidden_hits: list[dict[str, str]] = []

    for path in REQUIRED_PATHS:
        url = urllib.parse.urljoin(f"{base_url}/", path.lstrip("/"))
        status, body, headers = fetch(url)
        excerpt = extract_excerpt(body) if status == 200 else body[:200].strip()
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest() if status == 200 else None
        x_robots_tag = headers.get("x-robots-tag", "")
        lower_body = body.lower()
        page_hits = [token for token in FORBIDDEN_COPY if token in lower_body]
        for token in page_hits:
            forbidden_hits.append({"path": path, "token": token})
        if status != 200:
            failures.append(f"{path}: expected 200, got {status}")

        results.append(
            {
                "path": path,
                "url": url,
                "status_code": status,
                "sha256": sha,
                "excerpt": excerpt,
                "x_robots_tag": x_robots_tag,
                "forbidden_hits": page_hits,
            }
        )

    status = "pass" if not failures and not forbidden_hits else "fail"
    payload = {
        "contract_name": "chummer.live_public_web_recrawl",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "required_paths": REQUIRED_PATHS,
        "recrawl_max_age_hours": RECRAWL_MAX_AGE_HOURS,
        "status": status,
        "failures": failures,
        "forbidden_hits": forbidden_hits,
        "results": results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recrawl the live public Chummer pages and persist fresh proof excerpts.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public base URL to recrawl.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    payload = recrawl(base_url)
    if payload["status"] != "pass":
        raise SystemExit("live public web recrawl failed")
    print("live_public_web_recrawl:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
