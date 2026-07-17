#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import socket
import time
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
DEFAULT_RELEASE_CHANNEL_RECEIPT = REPO_ROOT.parent / "chummer-hub-registry" / ".codex-studio" / "published" / "RELEASE_CHANNEL.generated.json"
DEFAULT_FETCH_TIMEOUT_SECONDS = float(os.environ.get("CHUMMER_LIVE_SURFACE_PARITY_FETCH_TIMEOUT_SECONDS", "60"))
DEFAULT_FETCH_ATTEMPTS = max(1, int(os.environ.get("CHUMMER_LIVE_SURFACE_PARITY_FETCH_ATTEMPTS", "3")))
RETRYABLE_FETCH_REASONS = (
    TimeoutError,
    socket.timeout,
    ConnectionAbortedError,
    ConnectionResetError,
    ConnectionRefusedError,
)

def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_public_chummer_run_base(parsed_base_url: urllib.parse.ParseResult) -> bool:
    host = (parsed_base_url.hostname or "").lower()
    return parsed_base_url.scheme.lower() == "https" and (host == "chummer.run" or host.endswith(".chummer.run"))


def build_billing_surface(require_brilliant_directories_checkout: bool) -> dict[str, Any]:
    return {
        "path": "/account/billing",
        "required_final_url_prefix": "/login",
        "required_texts": [
            "Supporter",
            "After this step, Chummer returns to billing.",
            "Continue with Google",
        ],
        "required_any_texts": [
            "Email first. Billing stays attached after this step.",
            "Google first. Billing stays attached after that step.",
            "Email first. Supporter attaches after that step.",
            "Google first. Supporter attaches after that step.",
        ],
        "forbidden_texts": [
            "Account settings",
            "Supporter is not open right now.",
            "Billing is unavailable",
        ],
    }


def build_downloads_surface(
    *,
    release_review_required: bool,
    downloads_paused: bool = False,
) -> dict[str, Any]:
    required_texts = [
        "Downloads",
        "Chummer selects the best installer when it can.",
    ]
    forbidden_texts = [
        "Advanced download options",
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
    ]
    if downloads_paused:
        required_texts.extend(
            [
                "Current public installer",
                "No build is available right now",
                "Help",
            ]
        )
        forbidden_texts.extend(
            [
                "Stable release.",
                "No Stable build on this shelf.",
                "Preview build. Review required.",
                "Build from source",
                "Download script",
            ]
        )
    else:
        required_texts.extend(["Nightly", "Stable", "Build from source", "Download script"])
    if not downloads_paused and release_review_required:
        required_texts.extend(["No Stable build on this shelf.", "Preview build. Review required."])
        forbidden_texts.append("Stable release.")
    elif not downloads_paused:
        required_texts.append("Stable release.")
        forbidden_texts.extend(["No Stable build on this shelf.", "Preview build. Review required."])

    return {
        "path": "/downloads",
        "required_texts": required_texts,
        "required_html_texts": [
            '<a class="inline-link" href="/now">Release notes and known issues</a>',
        ],
        "forbidden_texts": forbidden_texts,
    }


def build_status_surface(
    *,
    release_review_required: bool,
    downloads_paused: bool = False,
) -> dict[str, Any]:
    status_heading = (
        "Downloads paused"
        if downloads_paused
        else "Preview downloads"
        if release_review_required
        else "Stable downloads"
    )
    return {
        "path": "/status",
        "required_texts": [
            "Now",
            status_heading,
            "Downloads",
            "Help",
        ],
        "required_any_texts": [
            "Windows and Linux downloads are live.",
            "Windows download is live.",
            "Linux download is live.",
            "Downloads are paused.",
            "No public installer right now.",
        ],
        "required_html_texts": [
            "<title>Status · Chummer</title>",
            "minimal-page-hero minimal-status-pill",
            "data-analytics-surface=\"status_decision\"",
        ],
        "forbidden_texts": [
            "Chummer selects the best installer when it can.",
            "Nightly",
            "Stable release.",
            "Build from source",
            "Download script",
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
        ],
    }


def build_surfaces(
    require_brilliant_directories_checkout: bool,
    *,
    release_review_required: bool = True,
    downloads_paused: bool = False,
) -> list[dict[str, Any]]:
    landing_required_texts = [
        "A Shadowrun character manager for clean sheets and faster tables.",
        "Download Chummer",
        "No public installer right now."
        if downloads_paused
        else "Current public installer",
        "Help",
    ]
    if downloads_paused:
        landing_required_texts.append("Current public lane: Downloads paused.")
    return [
        {
            "path": "/",
            "required_texts": landing_required_texts,
            "required_html_texts": [
                "data-disabled-target=\"/build\"",
                "data-sign-in-href=\"/login?next=%2Fbuild\"",
                "data-disabled-target=\"/mobile/player\"",
                "data-sign-in-href=\"/login?next=%2Fmobile%2Fplayer\"",
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
                "Chummer selects the best installer when it can.",
                "Stable release",
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
            "required_final_url_prefix": "/status",
            "required_texts": [
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
        build_downloads_surface(
            release_review_required=release_review_required,
            downloads_paused=downloads_paused,
        ),
        build_status_surface(
            release_review_required=release_review_required,
            downloads_paused=downloads_paused,
        ),
        build_billing_surface(require_brilliant_directories_checkout),
        {
            "path": "/participate",
            "required_texts": [
                "Participate",
            ],
            "required_html_texts": [
                "<title>Participate · Chummer</title>",
                "data-chummer-participate-frame",
                "productlift.dev",
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
                "data-chummer-board-skin",
                "participate-preview-card",
            ],
        },
        {
            "path": "/participate/board",
            "required_texts": [
                "Participate",
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
            ],
            "required_html_texts": [
                "<title>Roadmap · Chummer</title>",
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
                "Participate",
            ],
            "required_final_url_prefix": "/participate",
            "required_html_texts": [
                "<title>Participate · Chummer</title>",
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
            "path": "/mobile",
            "required_texts": [
                "Live-session turn companion",
                "Device posture",
                "Claimed player actor",
                "Player",
                "GM",
                "Observer",
            ],
            "required_html_texts": [
                "<title>Chummer Mobile Turn Companion</title>",
                "data-turn-root",
                "data-role=\"Player\"",
                "mobile-turn-companion.js",
            ],
            "forbidden_texts": [
                "Internal Error",
                "Authorize Codex access.",
                "OpenAI account in ChatGPT",
            ],
        },
        {
            "path": "/mobile/player",
            "required_texts": [
                "Live-session turn companion",
                "Claimed player actor",
                "Player",
                "GM",
                "Observer",
            ],
            "required_html_texts": [
                "<title>Chummer Mobile Turn Companion</title>",
                "data-turn-root",
                "data-role=\"Player\"",
                "mobile-turn-companion.js",
            ],
            "forbidden_texts": [
                "Internal Error",
                "Authorize Codex access.",
                "OpenAI account in ChatGPT",
            ],
        },
        {
            "path": "/mobile/gm",
            "required_texts": [
                "Live-session turn companion",
                "GM focus actor",
                "Player",
                "GM",
                "Observer",
            ],
            "required_html_texts": [
                "<title>Chummer Mobile Turn Companion</title>",
                "data-turn-root",
                "data-role=\"GameMaster\"",
                "mobile-turn-companion.js",
            ],
            "forbidden_texts": [
                "Internal Error",
                "Authorize Codex access.",
                "OpenAI account in ChatGPT",
            ],
        },
        {
            "path": "/mobile/observer",
            "required_texts": [
                "Live-session turn companion",
                "Observer mirror",
                "Player",
                "GM",
                "Observer",
            ],
            "required_html_texts": [
                "<title>Chummer Mobile Turn Companion</title>",
                "data-turn-root",
                "data-role=\"Observer\"",
                "mobile-turn-companion.js",
            ],
            "forbidden_texts": [
                "Internal Error",
                "Authorize Codex access.",
                "OpenAI account in ChatGPT",
            ],
        },
        {
            "path": "/play",
            "required_texts": [
                "Player entry",
                "Open Chummer",
                "Install this app",
                "Player, GM, and observer entry points meet in one shell.",
            ],
            "required_html_texts": [
                "data-pwa-ledger-status",
                "data-pwa-ledger-summary",
            ],
            "forbidden_texts": [
                "Internal Error",
                "Authorize Codex access.",
                "OpenAI account in ChatGPT",
            ],
        },
        {
            "path": "/play/continuity",
            "required_texts": [
                "NEXUS-PAN continuity",
                "Continuity stays cross-device",
                "Open continuity history",
            ],
            "forbidden_texts": [
                "Internal Error",
                "Authorize Codex access.",
                "OpenAI account in ChatGPT",
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


def is_retryable_fetch_exception(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return False
    if isinstance(exc, RETRYABLE_FETCH_REASONS):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, RETRYABLE_FETCH_REASONS)
    return False


def remaining_fetch_budget_seconds(deadline_monotonic: float | None) -> float:
    if deadline_monotonic is None:
        return DEFAULT_FETCH_TIMEOUT_SECONDS
    remaining = deadline_monotonic - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("global live-surface parity deadline exceeded")
    return min(DEFAULT_FETCH_TIMEOUT_SECONDS, max(0.001, remaining))


def fetch(
    url: str,
    base_url: str,
    deadline_monotonic: float | None = None,
) -> tuple[int | None, str, str, str | None, list[str], str | None]:
    for attempt in range(DEFAULT_FETCH_ATTEMPTS):
        opener = urllib.request.build_opener(NoRedirectHandler())
        redirect_chain: list[str] = []
        current_url = url
        try:
            for _ in range(5):
                request = urllib.request.Request(
                    current_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 chummer-live-surface-parity/1",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                try:
                    with opener.open(
                        request,
                        timeout=remaining_fetch_budget_seconds(deadline_monotonic),
                    ) as response:
                        body = response.read().decode("utf-8", errors="replace")
                        location = response.headers.get("Location")
                        if location and 300 <= int(response.status) < 400:
                            target = urllib.parse.urljoin(current_url, location)
                            redirect_chain.append(target)
                            if not _same_origin(target, base_url):
                                return int(response.status), body, current_url, location, redirect_chain, None

                            current_url = target
                            continue

                        return int(response.status), body, response.geturl(), location, redirect_chain, None
                except urllib.error.HTTPError as exc:
                    body = exc.read().decode("utf-8", errors="replace")
                    location = exc.headers.get("Location")
                    if location and 300 <= int(exc.code) < 400:
                        target = urllib.parse.urljoin(current_url, location)
                        redirect_chain.append(target)
                        if not _same_origin(target, base_url):
                            return int(exc.code), body, current_url, location, redirect_chain, None

                        current_url = target
                        continue

                    return int(exc.code), body, exc.geturl(), location, redirect_chain, None

            return None, "redirect loop exceeded", current_url, None, redirect_chain, "redirect loop exceeded"
        except Exception as exc:  # pragma: no cover
            fetch_error = f"{exc.__class__.__name__}: {exc}"
            if attempt + 1 >= DEFAULT_FETCH_ATTEMPTS or not is_retryable_fetch_exception(exc):
                return None, fetch_error, current_url, None, redirect_chain, fetch_error
            retry_delay = min(0.5 * (attempt + 1), 1.5)
            if deadline_monotonic is not None:
                retry_delay = min(
                    retry_delay,
                    remaining_fetch_budget_seconds(deadline_monotonic),
                )
            time.sleep(retry_delay)

    return None, "exhausted fetch retries", url, None, [], "exhausted fetch retries"


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def load_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def release_review_required(payload: dict[str, Any]) -> bool:
    channel = normalize_token(payload.get("channel") or payload.get("channelId") or payload.get("channel_id"))
    supportability_state = normalize_token(payload.get("supportabilityState"))
    rollout_state = normalize_token(payload.get("rolloutState"))
    status = normalize_token(payload.get("status"))
    stable_lane_published = channel in {"public_stable", "stable", "docker"} or rollout_state == "public_stable"

    if status and status != "published":
        return True
    if supportability_state != "gold_supported":
        return True
    if rollout_state in {"coverage_incomplete", "release_review_required", "public_release_review_required", "desktop_polish_needed", "revoked"}:
        return True
    if not stable_lane_published:
        return True
    return False


def public_installer_available(payload: dict[str, Any]) -> bool:
    trust_metrics = payload.get("publicTrustMetrics")
    trust_metrics = trust_metrics if isinstance(trust_metrics, dict) else {}
    adoption_health = trust_metrics.get("adoptionHealth")
    adoption_health = adoption_health if isinstance(adoption_health, dict) else {}
    if "publicInstallCount" in adoption_health:
        try:
            return int(adoption_health.get("publicInstallCount") or 0) > 0
        except (TypeError, ValueError):
            return False

    coverage = payload.get("registryBoundaryCoverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    entitlement = coverage.get("entitlement")
    entitlement = entitlement if isinstance(entitlement, dict) else {}
    if "openPublicSurfaceCount" in entitlement:
        try:
            return int(entitlement.get("openPublicSurfaceCount") or 0) > 0
        except (TypeError, ValueError):
            return False

    downloads = payload.get("downloads")
    if isinstance(downloads, list):
        return bool(downloads)

    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            kind = normalize_token(artifact.get("kind") or artifact.get("artifactKind"))
            if "installer" not in kind:
                continue
            access = normalize_token(
                artifact.get("installAccessClass")
                or artifact.get("accessClass")
                or artifact.get("access")
            )
            if access and access not in {"open_public", "public", "guest"}:
                continue
            if first_text(artifact, "downloadUrl", "url", "installUrl"):
                return True
        return False

    # Older manifest contracts did not expose availability counters. Preserve their
    # established surface expectations until an explicit availability signal exists.
    return True


def release_posture_expected_failures(payload: dict[str, Any], expected: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if not expected:
        return {}, []

    live_status = first_text(payload, "status")
    live_version = first_text(payload, "version")
    live_channel = first_text(payload, "channel", "channelId", "channel_id")
    live_supportability = first_text(payload, "supportabilityState", "supportability_state")
    live_rollout = first_text(payload, "rolloutState", "rollout_state")
    expected_status = first_text(expected, "status")
    expected_version = first_text(expected, "version")
    expected_channel = first_text(expected, "channel", "channelId", "channel_id")
    expected_supportability = first_text(expected, "supportabilityState", "supportability_state")
    expected_rollout = first_text(expected, "rolloutState", "rollout_state")

    fields = {
        "expected_status": expected_status,
        "expected_version": expected_version,
        "expected_channel": expected_channel,
        "expected_supportability_state": expected_supportability,
        "expected_rollout_state": expected_rollout,
        "status_matches_expected": live_status == expected_status if expected_status else None,
        "version_matches_expected": live_version == expected_version if expected_version else None,
        "channel_matches_expected": live_channel == expected_channel if expected_channel else None,
        "supportability_matches_expected": live_supportability == expected_supportability if expected_supportability else None,
        "rollout_matches_expected": live_rollout == expected_rollout if expected_rollout else None,
    }
    failures: list[str] = []
    for key, label in (
        ("expected_status", "status"),
        ("expected_version", "version"),
        ("expected_channel", "channel"),
        ("expected_supportability_state", "supportabilityState"),
        ("expected_rollout_state", "rolloutState"),
    ):
        if not fields[key]:
            failures.append(f"expected release channel {label} is missing")
    for key, label in (
        ("status_matches_expected", "status"),
        ("version_matches_expected", "version"),
        ("channel_matches_expected", "channel"),
        ("supportability_matches_expected", "supportabilityState"),
        ("rollout_matches_expected", "rolloutState"),
    ):
        if fields[key] is False:
            failures.append(f"live release manifest {label} does not match expected release channel")
    return fields, failures


def load_release_posture(
    base_url: str,
    expected_release_channel: dict[str, Any] | None = None,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    manifest_url = urllib.parse.urljoin(f"{base_url.rstrip('/')}/", "downloads/RELEASE_CHANNEL.generated.json")
    if deadline_monotonic is None:
        status_code, body, final_url, redirect_location, redirect_chain, fetch_error = fetch(
            manifest_url,
            base_url,
        )
    else:
        status_code, body, final_url, redirect_location, redirect_chain, fetch_error = fetch(
            manifest_url,
            base_url,
            deadline_monotonic,
        )
    payload: dict[str, Any] = {}
    parse_error: str | None = None
    if status_code == 200 and not fetch_error:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                parse_error = "release manifest root is not an object"
        except json.JSONDecodeError as exc:
            parse_error = f"JSONDecodeError: {exc}"

    review_required = True
    installer_available = False
    if payload and parse_error is None:
        review_required = release_review_required(payload)
        installer_available = public_installer_available(payload)
    expected_fields, expected_failures = release_posture_expected_failures(payload, expected_release_channel or {})

    return {
        "url": manifest_url,
        "final_url": final_url,
        "status_code": status_code,
        "redirect_location": redirect_location,
        "redirect_chain": redirect_chain,
        "fetch_error": fetch_error,
        "parse_error": parse_error,
        "status": payload.get("status"),
        "version": payload.get("version"),
        "channel": payload.get("channel"),
        "supportability_state": payload.get("supportabilityState"),
        "rollout_state": payload.get("rolloutState"),
        "review_required": review_required,
        "public_installer_available": installer_available,
        "downloads_paused": not installer_available,
        **expected_fields,
        "expected_failures": expected_failures,
    }


def flatten_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return " ".join(parser.parts)


def verify(
    base_url: str,
    output_path: Path | None = None,
    release_channel_receipt: Path | None = None,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    output_path = output_path or OUTPUT_PATH
    base = base_url.rstrip("/")
    base_origin = urllib.parse.urlparse(base)
    require_brilliant_directories_checkout = truthy_env("CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT") or is_public_chummer_run_base(base_origin)
    expected_release_channel = load_optional_json(release_channel_receipt)
    if deadline_monotonic is None:
        release_posture = load_release_posture(base, expected_release_channel)
    else:
        release_posture = load_release_posture(
            base,
            expected_release_channel,
            deadline_monotonic,
        )
    surfaces = build_surfaces(
        require_brilliant_directories_checkout,
        release_review_required=bool(release_posture["review_required"]),
        downloads_paused=bool(release_posture["downloads_paused"]),
    )
    results: list[dict[str, Any]] = []
    failures: list[str] = list(release_posture.get("expected_failures") or [])

    for surface in surfaces:
        path = str(surface["path"])
        url = urllib.parse.urljoin(f"{base}/", path.lstrip("/"))
        if deadline_monotonic is None:
            status_code, body, final_url, redirect_location, redirect_chain, fetch_error = fetch(
                url,
                base,
            )
        else:
            status_code, body, final_url, redirect_location, redirect_chain, fetch_error = fetch(
                url,
                base,
                deadline_monotonic,
            )
        decoded_body = html_lib.unescape(body)
        flattened = flatten_text(decoded_body) if status_code == 200 else decoded_body
        missing = [token for token in surface.get("required_texts", []) if token not in flattened]
        required_any = list(surface.get("required_any_texts", []))
        missing_any = required_any if required_any and not any(token in flattened for token in required_any) else []
        missing_html = [token for token in surface.get("required_html_texts", []) if token not in decoded_body]
        forbidden = [token for token in surface.get("forbidden_texts", []) if token in flattened]
        forbidden_html = [
            token
            for token in surface.get("forbidden_html_texts", [])
            if token in body or token in decoded_body
        ]
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
            failure = f"{path}: expected 200, got {status_code}"
            if fetch_error:
                failure += f" ({fetch_error})"
            failures.append(failure)
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
                "fetch_error": fetch_error,
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
        "release_posture": release_posture,
        "status": "pass" if not failures else "fail",
        "verdict": "LIVE_SURFACE_PARITY_READY" if not failures else "LIVE_SURFACE_PARITY_NOT_READY",
        "results": results,
        "failures": failures,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that the deployed public surfaces match the reviewed public product copy and route behavior.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public base URL to verify.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Path to write the generated live-surface parity receipt.")
    parser.add_argument("--release-channel-receipt", type=Path, default=DEFAULT_RELEASE_CHANNEL_RECEIPT, help="Expected release-channel receipt used to compare the live downloads release manifest.")
    parser.add_argument("--skip-release-channel-match", action="store_true", help="Skip comparing the live downloads release manifest with the local release-channel receipt.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    release_channel_receipt = None if args.skip_release_channel_match else args.release_channel_receipt
    payload = verify(args.base_url, args.output, release_channel_receipt)
    if payload["status"] != "pass":
        raise SystemExit("live surface parity failed")
    print("live_surface_parity:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
