#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = REPO_ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "LIVE_SURFACE_PARITY.generated.json"
DEFAULT_BASE_URL = "https://chummer.run"

def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_billing_surface(require_brilliant_directories_checkout: bool) -> dict[str, Any]:
    return {
        "path": "/account/billing",
        "required_final_url_prefix": "/login",
        "required_texts": [
            "Open Chummer",
            "Email first. Google if you prefer.",
            "Continue with email",
            "Continue with Google",
        ],
        "forbidden_texts": [
            "Account settings",
            "Supporter is not open right now.",
            "Billing is unavailable",
            "Membership",
        ],
    }


def build_surfaces(require_brilliant_directories_checkout: bool) -> list[dict[str, Any]]:
    return [
        {
            "path": "/",
            "required_texts": [
                "A Shadowrun character manager for clean sheets and faster tables.",
                "Download Chummer",
                "Current public installer",
                "Help",
                "Watch 90 sec",
            ],
            "forbidden_texts": [
                "Next move",
                "Need help?",
                "One compact rail for downloads, play, and public status.",
                "Reel details",
                "Keep it simple",
                "Get started",
                "Worlds",
                "Flagship routes",
                "Signals and horizons",
                "Trust and support",
                "Account and quick actions",
            ],
        },
        {
            "path": "/downloads",
            "required_texts": [
                "Downloads",
                "Main build for this browser",
                "Nightly",
                "Stable",
                "Build from source",
                "Download script",
            ],
            "forbidden_texts": [
                "Advanced download options",
                "Release notes",
                "Build run",
                "Need account return?",
                "Current notes.",
                "Install questions?",
                "Account return later?",
                "account-assisted install paths",
                "Link this copy from the first launch",
                "guided installer",
                "Current stable build",
                "Latest published build",
                "Use this when you want the newest Windows or Linux release.",
                "Get started",
                "Flagship routes",
                "Signals and horizons",
                "Trust and support",
                "Account and quick actions",
            ],
        },
        {
            "path": "/status",
            "required_texts": [
                "Status",
                "Updated",
                "Downloads",
                "Help",
            ],
            "forbidden_texts": [
                "Current release",
                "The build, platforms, and current state in one place.",
                "Open downloads",
                "Open help",
                "Platforms",
                "Release and next step.",
                "Release, caution, next click.",
                "Known issues and install help stay nearby.",
                "provider",
                "operator",
                "fleet",
                "proof",
                "receipt",
                "Build",
                "Released",
                "Current caution.",
                "Preview posture on Public release",
                "Review is still required before this release can be treated as supportable.",
                "Fallback",
                "Revoked",
                "usage snapshot",
                "At a glance",
                "Signed-in return",
                "Status poster",
                "Get started",
                "Flagship routes",
                "Signals and horizons",
                "Trust and support",
                "Account and quick actions",
            ],
        },
        build_billing_surface(require_brilliant_directories_checkout),
        {
            "path": "/participate",
            "required_texts": [
                "What should Chummer do next?",
                "Public requests, clear bugs, useful ideas.",
                "Requests",
                "Board is live.",
            ],
            "forbidden_texts": [
                "ProductLift",
                "Log in",
                "Sign up",
                "Authorize Codex access.",
                "OpenAI account in ChatGPT",
                "Requests, votes, and shipped work.",
                "Something went wrong",
                "Could not load posts",
                "Network error while loading tab configuration",
            ],
            "forbidden_html_texts": [
                "chummer6.productlift.dev",
                "data-chummer-board-skin",
            ],
        },
        {
            "path": "/participate/board",
            "required_texts": [
                "What should Chummer do next?",
                "Public requests, clear bugs, useful ideas.",
                "Requests",
                "Board is live.",
            ],
            "required_final_url_prefix": "/participate",
            "required_html_texts": [
                "<title>Participate · Chummer</title>",
            ],
            "forbidden_texts": [
                "ProductLift",
                "productlift.dev",
                "Log in",
                "Sign up",
                "Search",
                "Ctrl K",
                "×",
                "Something went wrong",
                "Could not load posts",
                "Network error while loading tab configuration",
                "/auth/google/start?next=",
                "accounts.google.com",
            ],
            "forbidden_html_texts": [
                "data-chummer-board-skin",
            ],
        },
        {
            "path": "/roadmap",
            "required_texts": [
                "Roadmap",
                "Now and next.",
                "Planned work is here. Shipped work stays in Changelog.",
            ],
            "required_any_texts": [
                "Current work opens below.",
                "Current requests live in Participate.",
            ],
            "forbidden_texts": [
                "ProductLift",
                "Open live board",
                "Something went wrong",
                "Could not load posts",
                "Network error while loading tab configuration",
            ],
        },
        {
            "path": "/roadmap/board",
            "required_texts": [
                "Roadmap",
                "Now and next.",
                "Planned work is here. Shipped work stays in Changelog.",
            ],
            "required_any_texts": [
                "Current work opens below.",
                "Current requests live in Participate.",
            ],
            "required_final_url_prefix": "/roadmap",
            "forbidden_texts": [
                "ProductLift",
                "Open live board",
                "Something went wrong",
                "Could not load posts",
                "Network error while loading tab configuration",
            ],
        },
        {
            "path": "/ledger",
            "required_texts": [
                "Black Ledger command map",
                "Command map",
            ],
            "required_final_url_prefix": "/ledger/map",
            "forbidden_texts": [
                "Internal Error",
                "Board signal:",
                "Turn source:",
                "Production notes",
                "City note:",
                "City pulse:",
                "Built from",
                "deterministic board",
                "Linked through",
                "Turn record:",
                "Scene notes",
                "<p class=\"editorial-copy\"></p>",
            ],
        },
        {
            "path": "/ledger/newsroom",
            "required_texts": [
                "Black Ledger Newsroom",
                "Transcript",
                "Published:",
            ],
            "forbidden_texts": [
                "Internal Error",
            ],
        },
    ]


SURFACES = build_surfaces(False)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "template"} and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        text = data.strip()
        if text:
            self.parts.append(text)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _same_origin(left: str, right: str) -> bool:
    left_parts = urllib.parse.urlparse(left)
    right_parts = urllib.parse.urlparse(right)
    return (
        left_parts.scheme.lower(),
        left_parts.netloc.lower(),
    ) == (
        right_parts.scheme.lower(),
        right_parts.netloc.lower(),
    )


def fetch(url: str, base_url: str) -> tuple[int | None, str, str, str | None, list[str]]:
    opener = urllib.request.build_opener(NoRedirectHandler())
    redirect_chain: list[str] = []
    current_url = url

    for _ in range(5):
        request = urllib.request.Request(
            current_url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 chummer-live-surface-parity/1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with opener.open(request, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
                location = response.headers.get("Location")
                if location and 300 <= int(response.status) < 400:
                    target = urllib.parse.urljoin(current_url, location)
                    redirect_chain.append(target)
                    if not _same_origin(target, base_url):
                        return int(response.status), body, current_url, location, redirect_chain

                    current_url = target
                    continue

                return int(response.status), body, response.geturl(), location, redirect_chain
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            location = exc.headers.get("Location")
            if location and 300 <= int(exc.code) < 400:
                target = urllib.parse.urljoin(current_url, location)
                redirect_chain.append(target)
                if not _same_origin(target, base_url):
                    return int(exc.code), body, current_url, location, redirect_chain

                current_url = target
                continue

            return int(exc.code), body, exc.geturl(), location, redirect_chain
        except Exception as exc:  # pragma: no cover
            return None, str(exc), current_url, None, redirect_chain

    return None, "redirect loop exceeded", current_url, None, redirect_chain


def flatten_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return " ".join(parser.parts)


def verify(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    base_origin = urllib.parse.urlparse(base)
    require_brilliant_directories_checkout = truthy_env("CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT")
    surfaces = build_surfaces(require_brilliant_directories_checkout)
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for surface in surfaces:
        path = str(surface["path"])
        url = urllib.parse.urljoin(f"{base}/", path.lstrip("/"))
        status_code, body, final_url, redirect_location, redirect_chain = fetch(url, base)
        flattened = flatten_text(body) if status_code == 200 else body
        missing = [token for token in surface.get("required_texts", []) if token not in flattened]
        required_any = list(surface.get("required_any_texts", []))
        missing_any = required_any if required_any and not any(token in flattened for token in required_any) else []
        missing_html = [token for token in surface.get("required_html_texts", []) if token not in body]
        forbidden = [token for token in surface.get("forbidden_texts", []) if token in flattened]
        forbidden_html = [token for token in surface.get("forbidden_html_texts", []) if token in body]
        final_url_prefix = str(surface.get("required_final_url_prefix") or "")
        final_url_matches = True
        cross_origin_redirect = False
        redirect_target_url = None

        if redirect_location:
            redirect_target_url = urllib.parse.urljoin(url, redirect_location)
            redirect_origin = urllib.parse.urlparse(redirect_target_url)
            cross_origin_redirect = (
                bool(redirect_origin.scheme)
                and bool(redirect_origin.netloc)
                and (
                    redirect_origin.scheme.lower() != base_origin.scheme.lower()
                    or redirect_origin.netloc.lower() != base_origin.netloc.lower()
                )
            )

        if final_url_prefix:
            final_path = urllib.parse.urlparse(final_url).path or "/"
            final_url_matches = final_path.startswith(final_url_prefix)
            if not final_url_matches:
                failures.append(f"{path}: final URL {final_path} did not start with {final_url_prefix}")

        if status_code != 200:
            failures.append(f"{path}: expected 200, got {status_code}")
        if redirect_location:
            failures.append(f"{path}: redirected to {redirect_target_url or redirect_location}")
        if cross_origin_redirect:
            failures.append(f"{path}: redirected off-origin to {redirect_target_url}")
        if missing:
            failures.append(f"{path}: missing required text: {', '.join(missing)}")
        if missing_any:
            failures.append(f"{path}: missing any-of required text: {', '.join(missing_any)}")
        if missing_html:
            failures.append(f"{path}: missing required html text: {', '.join(missing_html)}")
        if forbidden:
            failures.append(f"{path}: contains forbidden text: {', '.join(forbidden)}")
        if forbidden_html:
            failures.append(f"{path}: contains forbidden html text: {', '.join(forbidden_html)}")

        results.append(
            {
                "path": path,
                "url": url,
                "final_url": final_url,
                "redirect_location": redirect_location,
                "redirect_target_url": redirect_target_url,
                "cross_origin_redirect": cross_origin_redirect,
                "status_code": status_code,
                "redirect_chain": redirect_chain,
                "required_texts": surface.get("required_texts", []),
                "required_any_texts": required_any,
                "required_html_texts": surface.get("required_html_texts", []),
                "missing_required_texts": missing,
                "missing_required_any_texts": missing_any,
                "missing_required_html_texts": missing_html,
                "forbidden_texts": surface.get("forbidden_texts", []),
                "forbidden_html_texts": surface.get("forbidden_html_texts", []),
                "forbidden_hits": forbidden,
                "forbidden_html_hits": forbidden_html,
                "required_final_url_prefix": final_url_prefix or None,
                "final_url_matches": final_url_matches,
                "status": "pass" if status_code == 200 and not missing and not missing_any and not missing_html and not forbidden and not forbidden_html and final_url_matches else "fail",
            }
        )

    payload = {
        "contract_name": "chummer.live_surface_parity",
        "generated_at_utc": now_iso(),
        "base_url": base,
        "require_brilliant_directories_checkout": require_brilliant_directories_checkout,
        "status": "pass" if not failures else "fail",
        "verdict": "LIVE_SURFACE_PARITY_READY" if not failures else "LIVE_SURFACE_PARITY_NOT_READY",
        "results": results,
        "failures": failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that the deployed public surfaces match the reviewed public product copy and route behavior.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public base URL to verify.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = verify(args.base_url)
    if payload["status"] != "pass":
        raise SystemExit("live surface parity failed")
    print("live_surface_parity:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
