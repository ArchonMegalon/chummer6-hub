#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import tempfile
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_participate_iframe_shell  # noqa: E402
import verify_mobile_pwa_service_worker_boundary  # noqa: E402


EXPECTED_PLAYTIME_TOOLS = {
    "inventory",
    "health",
    "ammo",
    "modifiers",
    "quick_rolls",
    "living_world",
}
EXPECTED_LEDGER_OPT_IN_KEYS = {
    "black_ledger_heat",
    "followed_world_updates",
    "session_continuity",
}
EXPECTED_READY_ROLES = {"player", "gm", "organizer"}
EXPECTED_MOBILE_ROUTES = {
    "/mobile": ('data-blazor-shell="interactive-server"', 'data-role="Player"', "manifest.player.webmanifest"),
    "/mobile/player": ('data-blazor-shell="interactive-server"', 'data-role="Player"', "manifest.player.webmanifest"),
    "/mobile/gm": ('data-blazor-shell="interactive-server"', 'data-role="GameMaster"', "manifest.gm.webmanifest"),
    "/mobile/observer": ('data-blazor-shell="interactive-server"', 'data-role="Observer"', "manifest.webmanifest"),
    "/play": ("Player entry",),
    "/play/continuity": ("NEXUS-PAN continuity",),
}
EXPECTED_ASSETS = [
    "/pwa-icon.svg",
    "/pwa-maskable.svg",
    "/pwa-screenshot-mobile.svg",
    "/pwa-screenshot-wide.svg",
    "/apple-touch-icon.png",
    "/favicon.ico",
    "/favicon.svg",
]
EXPECTED_MANIFESTS = {
    "/manifest.json": "/mobile",
    "/manifest.webmanifest": "/mobile",
    "/site.webmanifest": "/mobile",
    "/manifest.player.webmanifest": "/mobile/player",
    "/manifest.gm.webmanifest": "/mobile/gm",
}
PLAYWRIGHT_REQUIREMENTS = {
    "downloadsStatus": {
        "spec": "tests/public/downloads-status.spec.ts",
        "artifact": "DOWNLOADS_STATUS_E2E.generated.json",
    },
    "mobilePwaViewport": {
        "spec": "tests/public/mobile-pwa-viewport-smoke.spec.ts",
        "artifact": "MOBILE_PWA_VIEWPORT_SMOKE.generated.json",
    },
    "frontdoorNavigation": {
        "spec": "tests/public/frontdoor-mobile-launch.spec.ts",
        "artifact": "FRONTDOOR_MOBILE_LAUNCH.generated.json",
    },
}
ANSI_CONTROL_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
EXPECTED_FLAGSHIP_HORIZONS = {
    "near_term_stabilization": {
        "title": "Near-term stabilization",
        "requiredReceipts": [
            "downloads",
            "navigation",
            "pwaStatic",
            "readyMobileHandoff",
            "mobilePwaServiceWorkerBoundary",
            "participateIframeShell",
            "portalRuntimeImage",
        ],
    },
    "mid_term_pwa_session_utility": {
        "title": "Mid-term PWA/session utility",
        "requiredReceipts": [
            "pwaStatic",
            "readyMobileHandoff",
            "browserPlaywright",
        ],
        "requiredRoutes": [
            "/mobile",
            "/mobile/player",
            "/mobile/gm",
            "/mobile/observer",
            "/play/continuity",
        ],
        "requiredTools": sorted(EXPECTED_PLAYTIME_TOOLS - {"living_world"}),
    },
    "long_term_living_world_expansion": {
        "title": "Long-term living-world expansion",
        "requiredReceipts": [
            "readyMobileHandoff",
            "mobileLedger",
            "mobilePwaServiceWorkerBoundary",
        ],
        "requiredTools": ["living_world"],
        "requiredLedgerStatus": "opt_in_required",
    },
}
DEFAULT_PORTAL_CONTAINER = "chummer6-hub-chummer-portal-1"
DEFAULT_PORTAL_IMAGE_TAG = "chummer-run-api:local"


@dataclass(frozen=True)
class FetchResult:
    path: str
    status_code: int
    headers: dict[str, str]
    body: str
    final_url: str

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def clean_process_text(value: Any) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value or "")
    return ANSI_CONTROL_RE.sub("", text)


def tail_lines(value: Any, max_lines: int = 80) -> str:
    lines = []
    skip_next_trace_hint = False
    for line in clean_process_text(value).splitlines():
        if "Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set." in line:
            skip_next_trace_hint = True
            continue
        if skip_next_trace_hint and line.startswith("(Use `node --trace-warnings"):
            skip_next_trace_hint = False
            continue
        skip_next_trace_hint = False
        lines.append(line)
    return "\n".join(lines[-max_lines:])


def normalize_token(value: Any) -> str:
    return str(value or "").strip().casefold()


def resolve_playwright_package_spec() -> str:
    override = str(os.environ.get("CHUMMER_PLAYWRIGHT_PACKAGE_SPEC") or "").strip()
    if override:
        return override

    package_lock_path = ROOT / "package-lock.json"
    if package_lock_path.is_file():
        try:
            package_lock = json.loads(package_lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            package_lock = {}
        packages = package_lock.get("packages")
        if isinstance(packages, dict):
            playwright_package = packages.get("node_modules/playwright")
            if isinstance(playwright_package, dict):
                version = str(playwright_package.get("version") or "").strip()
                if version:
                    return f"playwright@{version}"

    package_json_path = ROOT / "package.json"
    if package_json_path.is_file():
        try:
            package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            package_json = {}
        for field in ("dependencies", "devDependencies"):
            dependencies = package_json.get(field)
            if not isinstance(dependencies, dict):
                continue
            version_spec = str(dependencies.get("playwright") or "").strip()
            if version_spec:
                return f"playwright@{version_spec}"

    return "playwright"


def resolve_playwright_node_modules_root() -> Path | None:
    override_root = str(os.environ.get("CHUMMER_PLAYWRIGHT_NODE_MODULES_ROOT") or "").strip()
    candidates = []
    if override_root:
        candidates.append(Path(override_root).expanduser())
    candidates.extend(
        [
            ROOT / "node_modules",
            ROOT.parent / "chummer.run-services" / "node_modules",
            Path("/docker/chummercomplete/chummer.run-services/node_modules"),
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if (candidate / ".bin" / "playwright").is_file():
            return candidate
    return None


def resolve_playwright_command() -> list[str]:
    override_bin = str(os.environ.get("CHUMMER_PLAYWRIGHT_BIN") or "").strip()
    if override_bin:
        return [override_bin]

    node_modules_root = resolve_playwright_node_modules_root()
    if node_modules_root is not None:
        return [str(node_modules_root / ".bin" / "playwright")]

    return ["npx", "--yes", resolve_playwright_package_spec()]


def expected_release_posture(expected_release_channel: str) -> dict[str, str]:
    normalized = normalize_token(expected_release_channel) or "public_stable"
    if normalized in {"preview", "nightly", "promoted_preview"}:
        return {
            "channel": "preview",
            "rollout": "promoted_preview",
            "supportability": "preview_supported",
        }
    return {
        "channel": "public_stable",
        "rollout": "public_stable",
        "supportability": "gold_supported",
    }


def fetch(base_url: str, path: str, timeout_seconds: float) -> FetchResult:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "ChummerPublicEdgePostdeployGate/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return FetchResult(path, response.status, headers, body, response.geturl())
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in error.headers.items()}
        return FetchResult(path, error.code, headers, body, error.geturl())
    except URLError as error:
        raise RuntimeError(f"{url}: {error}") from error


def parse_json(result: FetchResult, failures: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(result.body)
    except json.JSONDecodeError as error:
        failures.append(f"{result.path} returned invalid JSON: {error}")
        return {}
    return value if isinstance(value, dict) else {}


def normalize_manifest_asset_src(src: Any) -> str:
    value = str(src or "").strip().replace("\\", "/")
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return ""

    path = parsed.path.strip()
    if not path:
        return ""

    normalized_path = posixpath.normpath(path if path.startswith("/") else f"/{path}")
    if normalized_path == "/.":
        return ""
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if parsed.query:
        return f"{normalized_path}?{parsed.query}"
    return normalized_path


def manifest_asset_paths(payload: dict[str, Any]) -> list[str]:
    paths: set[str] = set()

    def collect_icon_sources(rows: Any) -> None:
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            path = normalize_manifest_asset_src(item.get("src"))
            if path:
                paths.add(path)

    collect_icon_sources(payload.get("icons"))
    collect_icon_sources(payload.get("screenshots"))
    shortcuts = payload.get("shortcuts") if isinstance(payload.get("shortcuts"), list) else []
    for shortcut in shortcuts:
        if isinstance(shortcut, dict):
            collect_icon_sources(shortcut.get("icons"))

    return sorted(paths)


def extract_quoted_values(text: str, pattern: str) -> set[str]:
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def service_worker_declared_fetchable_paths(service_worker: dict[str, Any]) -> list[str]:
    raw_paths: list[Any] = []
    for key in ("precache_urls", "shell_assets"):
        values = service_worker.get(key)
        if isinstance(values, list):
            raw_paths.extend(values)

    non_cacheable_paths: set[str] = set()
    for value in service_worker.get("non_cacheable_paths", []):
        normalized_path = normalize_manifest_asset_src(value)
        if normalized_path:
            non_cacheable_paths.add(normalized_path)
    non_cacheable_bases = {path.split("?", 1)[0] for path in non_cacheable_paths}

    paths: set[str] = set()
    for raw_path in raw_paths:
        path = normalize_manifest_asset_src(raw_path)
        if not path:
            continue
        if path in non_cacheable_paths or path.split("?", 1)[0] in non_cacheable_bases:
            continue
        paths.add(path)
    return sorted(paths)


def inspect_service_worker(body: str, failures: list[str]) -> dict[str, Any]:
    cache_name_match = re.search(r'const CACHE_NAME = "([^"]+)";', body)
    cache_version_match = re.search(r'const CACHE_VERSION = "([^"]+)";', body)
    precache_urls = extract_quoted_values(body, r"const PRECACHE_URLS = \[(.*?)\];")
    shell_assets = extract_quoted_values(body, r"const SHELL_ASSETS = \[(.*?)\];")
    non_cacheable_paths = extract_quoted_values(body, r"const NON_CACHEABLE_PATHS = new Set\(\[(.*?)\]\);")
    worker_kind = "play" if cache_version_match and "SHELL_ASSETS" in body else "portal"

    if worker_kind == "play":
        for listener in ['"install"', '"activate"', '"fetch"']:
            require(f"self.addEventListener({listener}" in body, failures, f"service worker missing {listener} listener")
        for path in [
            "/mobile",
            "/mobile/player",
            "/mobile/player?role=Player",
            "/mobile/gm",
            "/mobile/gm?role=GameMaster",
            "/mobile/observer",
            "/_framework/blazor.web.js",
            "/mobile.css",
            "/mobile-turn-companion.js",
            "/manifest.webmanifest",
            "/manifest.player.webmanifest",
            "/manifest.gm.webmanifest",
        ]:
            require(path in shell_assets, failures, f"service worker missing play shell asset {path}")
        require("/mobile/pwa/ledger.json" in non_cacheable_paths, failures, "service worker must keep mobile ledger stream non-cacheable")
        require("/mobile/pwa/ledger.json" not in shell_assets, failures, "service worker must not precache mobile ledger stream")
        require('url.pathname.startsWith("/api/play/")' in body, failures, "service worker must keep private play API network-only")
        require("play_public_route_network_unavailable" in body, failures, "service worker missing typed non-cacheable route offline failure")
    else:
        require(cache_name_match and cache_name_match.group(1) == "chummer-public-v4", failures, "service worker cache name is not chummer-public-v4")
        for required_path in ["/mobile/player", "/mobile/gm", "/mobile/observer", "/ready/handoff/mobile.json"]:
            require(required_path in body, failures, f"service worker missing {required_path}")
        require('"/mobile/pwa/ledger.json"' in body and "NON_CACHEABLE_PATHS" in body, failures, "service worker does not mark mobile ledger stream non-cacheable")

    return {
        "worker_kind": worker_kind,
        "cache_name": cache_name_match.group(1) if cache_name_match else "",
        "cache_version": cache_version_match.group(1) if cache_version_match else "",
        "precache_urls": sorted(precache_urls),
        "shell_assets": sorted(shell_assets),
        "non_cacheable_paths": sorted(non_cacheable_paths),
        "ledger_stream_non_cacheable": "/mobile/pwa/ledger.json" in non_cacheable_paths,
        "ledger_stream_precached": "/mobile/pwa/ledger.json" in (shell_assets if worker_kind == "play" else precache_urls),
        "play_shell_asset_count": len(shell_assets),
    }


def extract_downloads_version_marker(html: str) -> str:
    match = re.search(r"<[^>]+data-downloads-release-version[^>]*>\s*(Version\s+[^<\s]+)", html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def verify_downloads(base_url: str, timeout_seconds: float, expected_release_channel: str = "public_stable") -> dict[str, Any]:
    failures: list[str] = []
    expected_posture = expected_release_posture(expected_release_channel)
    downloads = fetch(base_url, "/downloads", timeout_seconds)
    status = fetch(base_url, "/status", timeout_seconds)
    release = fetch(base_url, "/downloads/RELEASE_CHANNEL.generated.json", timeout_seconds)
    compatibility = fetch(base_url, "/downloads/releases.json", timeout_seconds)
    release_payload = parse_json(release, failures) if release.status_code == 200 else {}
    compatibility_payload = parse_json(compatibility, failures) if compatibility.status_code == 200 else {}

    downloads_version = extract_downloads_version_marker(downloads.body)
    status_version = extract_downloads_version_marker(status.body)
    release_version = str(release_payload.get("releaseVersion") or release_payload.get("version") or "")
    release_status = str(release_payload.get("status") or "")
    release_channel = str(release_payload.get("channel") or release_payload.get("channelId") or "")
    release_rollout = str(release_payload.get("rolloutState") or "")
    release_supportability = str(release_payload.get("supportabilityState") or "")
    compatibility_version = str(compatibility_payload.get("releaseVersion") or compatibility_payload.get("version") or "")
    compatibility_status = str(compatibility_payload.get("status") or "")
    compatibility_channel = str(compatibility_payload.get("channel") or compatibility_payload.get("channelId") or "")
    compatibility_rollout = str(compatibility_payload.get("rolloutState") or "")
    compatibility_supportability = str(compatibility_payload.get("supportabilityState") or "")
    compatibility_download_count = len(compatibility_payload.get("downloads") or [])
    release_guarded_preview = (
        expected_posture["channel"] == "preview"
        and normalize_token(release_supportability) == "review_required"
        and normalize_token(release_rollout) in {"coverage_incomplete", "desktop_polish_needed", "readiness_review_required"}
    )
    compatibility_guarded_preview = (
        expected_posture["channel"] == "preview"
        and normalize_token(compatibility_supportability) == "review_required"
        and normalize_token(compatibility_rollout) in {"desktop_polish_needed", "readiness_review_required"}
    )

    require(downloads.status_code == 200, failures, f"/downloads expected 200, got {downloads.status_code}")
    require(status.status_code == 200, failures, f"/status expected 200, got {status.status_code}")
    require(release.status_code == 200, failures, f"/downloads/RELEASE_CHANNEL.generated.json expected 200, got {release.status_code}")
    require(compatibility.status_code == 200, failures, f"/downloads/releases.json expected 200, got {compatibility.status_code}")
    require(bool(downloads_version), failures, "/downloads missing data-downloads-release-version marker")
    require(bool(status_version), failures, "/status missing data-downloads-release-version marker")
    if release_version:
        require(downloads_version.endswith(release_version), failures, "/downloads version marker does not match release channel version")
        require(status_version.endswith(release_version), failures, "/status version marker does not match release channel version")
        require(compatibility_version == release_version, failures, "/downloads/releases.json version does not match release channel version")
    require(release_status == "published", failures, f"release status expected published, got {release_status or '<empty>'}")
    require(compatibility_status == "published", failures, f"compatibility manifest status expected published, got {compatibility_status or '<empty>'}")
    require(compatibility_download_count > 0, failures, "compatibility manifest exposes no downloads")
    require(
        normalize_token(release_channel) == expected_posture["channel"],
        failures,
        f"release channel expected {expected_posture['channel']}, got {release_channel or '<empty>'}",
    )
    require(
        normalize_token(compatibility_channel) == expected_posture["channel"],
        failures,
        f"compatibility manifest channel expected {expected_posture['channel']}, got {compatibility_channel or '<empty>'}",
    )
    if not release_guarded_preview:
        require(
            normalize_token(release_rollout) == expected_posture["rollout"],
            failures,
            f"release rollout expected {expected_posture['rollout']}, got {release_rollout or '<empty>'}",
        )
        require(
            normalize_token(release_supportability) == expected_posture["supportability"],
            failures,
            f"release supportability expected {expected_posture['supportability']}, got {release_supportability or '<empty>'}",
        )
    if not compatibility_guarded_preview:
        require(
            normalize_token(compatibility_rollout) == expected_posture["rollout"],
            failures,
            f"compatibility manifest rollout expected {expected_posture['rollout']}, got {compatibility_rollout or '<empty>'}",
        )
        require(
            normalize_token(compatibility_supportability) == expected_posture["supportability"],
            failures,
            f"compatibility manifest supportability expected {expected_posture['supportability']}, got {compatibility_supportability or '<empty>'}",
        )

    return {
        "contractName": "chummer.downloads_version_marker.v1",
        "status": "pass" if not failures else "fail",
        "downloads_status": downloads.status_code,
        "status_status": status.status_code,
        "release_manifest_status": release.status_code,
        "compatibility_manifest_status": compatibility.status_code,
        "visible_version": downloads_version,
        "status_redirect_version": status_version,
        "release_version": release_version,
        "compatibility_manifest_version": compatibility_version,
        "release_channel": release_channel,
        "compatibility_manifest_channel": compatibility_channel,
        "expected_release_channel": expected_posture["channel"],
        "expected_release_rollout_state": expected_posture["rollout"],
        "expected_release_supportability_state": expected_posture["supportability"],
        "release_rollout_state": release_rollout,
        "release_status": release_status,
        "release_supportability_state": release_supportability,
        "release_manifest_guarded_preview": release_guarded_preview,
        "compatibility_manifest_rollout_state": compatibility_rollout,
        "compatibility_manifest_supportability_state": compatibility_supportability,
        "compatibility_manifest_download_count": compatibility_download_count,
        "compatibility_manifest_guarded_preview": compatibility_guarded_preview,
        "failures": failures,
    }


def verify_navigation(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    home = fetch(base_url, "/", timeout_seconds)
    require(home.status_code == 200, failures, f"/ expected 200, got {home.status_code}")
    require("site-open-chummer-menu" in home.body, failures, "homepage missing Open Chummer dropdown")
    require('href="/mobile/player"' in home.body, failures, "homepage Open Chummer menu missing public Play link")
    require('data-analytics-label="Build">Build</button>' in home.body or ">Build</button>" in home.body, failures, "homepage Build action is not gated as a disabled button")
    require('href="/build"' not in home.body, failures, "homepage leaks public Build link before sign-in")
    return {
        "contractName": "chummer.public_navigation_open_chummer.v1",
        "status": "pass" if not failures else "fail",
        "status_code": home.status_code,
        "sha256": home.sha256,
        "failures": failures,
    }


def verify_pwa_static(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    route_results: list[dict[str, Any]] = []
    for path, expected_terms in EXPECTED_MOBILE_ROUTES.items():
        result = fetch(base_url, path, timeout_seconds)
        has_expected = all(term in result.body for term in expected_terms)
        require(result.status_code == 200, failures, f"{path} expected 200, got {result.status_code}")
        require(has_expected, failures, f"{path} missing expected mobile shell text")
        route_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "sha256": result.sha256,
                "expected_text_found": has_expected,
            }
        )

    manifest_results: list[dict[str, Any]] = []
    manifest_declared_asset_paths: list[str] = []
    for path, expected_start_prefix in EXPECTED_MANIFESTS.items():
        result = fetch(base_url, path, timeout_seconds)
        manifest_failures: list[str] = []
        payload = parse_json(result, manifest_failures) if result.status_code == 200 else {}
        start_url = str(payload.get("start_url") or "")
        display = str(payload.get("display") or "")
        icons = payload.get("icons") if isinstance(payload.get("icons"), list) else []
        declared_asset_paths = manifest_asset_paths(payload)
        manifest_declared_asset_paths.extend(declared_asset_paths)
        require(result.status_code == 200, failures, f"{path} expected 200, got {result.status_code}")
        require(start_url.startswith(expected_start_prefix), failures, f"{path} start_url expected {expected_start_prefix}, got {start_url or '<empty>'}")
        require(display == "standalone", failures, f"{path} display expected standalone, got {display or '<empty>'}")
        require(len(icons) >= 2, failures, f"{path} expected at least two icons")
        failures.extend(f"{path}: {item}" for item in manifest_failures)
        manifest_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "start_url": start_url,
                "display": display,
                "icon_count": len(icons),
                "manifest_declared_asset_count": len(declared_asset_paths),
                "manifest_declared_assets": declared_asset_paths,
                "sha256": result.sha256,
            }
        )

    asset_results: list[dict[str, Any]] = []
    for path in EXPECTED_ASSETS:
        result = fetch(base_url, path, timeout_seconds)
        require(result.status_code == 200, failures, f"{path} expected 200, got {result.status_code}")
        require(len(result.body) > 0, failures, f"{path} returned an empty body")
        asset_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "bytes": len(result.body.encode("utf-8")),
                "sha256": result.sha256,
            }
        )

    manifest_declared_asset_results: list[dict[str, Any]] = []
    for path in sorted(set(manifest_declared_asset_paths)):
        result = fetch(base_url, path, timeout_seconds)
        require(result.status_code == 200, failures, f"manifest-declared asset {path} expected 200, got {result.status_code}")
        require(len(result.body) > 0, failures, f"manifest-declared asset {path} returned an empty body")
        manifest_declared_asset_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "bytes": len(result.body.encode("utf-8")),
                "sha256": result.sha256,
            }
        )

    service_worker = fetch(base_url, "/service-worker.js", timeout_seconds)
    require(service_worker.status_code == 200, failures, f"/service-worker.js expected 200, got {service_worker.status_code}")
    service_worker_result = inspect_service_worker(service_worker.body, failures)
    service_worker_declared_paths = service_worker_declared_fetchable_paths(service_worker_result)
    service_worker_declared_path_results: list[dict[str, Any]] = []
    for path in service_worker_declared_paths:
        result = fetch(base_url, path, timeout_seconds)
        require(result.status_code == 200, failures, f"service-worker declared path {path} expected 200, got {result.status_code}")
        require(len(result.body) > 0, failures, f"service-worker declared path {path} returned an empty body")
        service_worker_declared_path_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "bytes": len(result.body.encode("utf-8")),
                "sha256": result.sha256,
            }
        )

    return {
        "contractName": "chummer.public_pwa_static_assets.v1",
        "status": "pass" if not failures else "fail",
        "route_count": len(route_results),
        "manifest_count": len(manifest_results),
        "asset_count": len(asset_results),
        "manifest_declared_asset_count": len(manifest_declared_asset_results),
        "service_worker_declared_path_count": len(service_worker_declared_path_results),
        "routes": route_results,
        "manifests": manifest_results,
        "assets": asset_results,
        "manifest_declared_assets": manifest_declared_asset_results,
        "service_worker_declared_paths": service_worker_declared_path_results,
        "service_worker": {
            "status_code": service_worker.status_code,
            "content_type": service_worker.content_type,
            **service_worker_result,
            "sha256": service_worker.sha256,
        },
        "failures": failures,
    }


def verify_ready_mobile_handoff(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    result = fetch(base_url, "/ready/handoff/mobile.json", timeout_seconds)
    payload = parse_json(result, failures) if result.status_code == 200 else {}
    tools = payload.get("playtime_tools") if isinstance(payload.get("playtime_tools"), list) else []
    tool_ids = {str(item.get("id") or "") for item in tools if isinstance(item, dict)}
    living_world_tool = next(
        (item for item in tools if isinstance(item, dict) and str(item.get("id") or "") == "living_world"),
        {},
    )
    living_world_summary = str(living_world_tool.get("summary") or "").lower() if isinstance(living_world_tool, dict) else ""
    packet_routes = payload.get("packet_routes") if isinstance(payload.get("packet_routes"), list) else []
    roles = {str(item.get("roleId") or "") for item in packet_routes if isinstance(item, dict)}
    boundaries = payload.get("boundaries") if isinstance(payload.get("boundaries"), list) else []
    boundary_text = " ".join(str(item) for item in boundaries).lower()
    packet_route_results: list[dict[str, Any]] = []

    require(result.status_code == 200, failures, f"/ready/handoff/mobile.json expected 200, got {result.status_code}")
    require(payload.get("status") == "ready", failures, "mobile handoff status is not ready")
    require(payload.get("pwa_route") == "/mobile", failures, "mobile handoff pwa_route is not /mobile")
    require(payload.get("continuity_route") == "/play/continuity", failures, "mobile handoff continuity_route is not /play/continuity")
    require(EXPECTED_PLAYTIME_TOOLS.issubset(tool_ids), failures, f"mobile handoff missing playtime tools: {sorted(EXPECTED_PLAYTIME_TOOLS - tool_ids)}")
    require(EXPECTED_READY_ROLES.issubset(roles), failures, f"mobile handoff missing packet roles: {sorted(EXPECTED_READY_ROLES - roles)}")
    require("character building" in boundary_text and "before or after" in boundary_text, failures, "mobile handoff missing character-building boundary")
    require("opt-in" in boundary_text or "opt in" in boundary_text, failures, "mobile handoff missing living-world opt-in boundary")
    require("gm remains final authority" in boundary_text, failures, "mobile handoff missing GM authority boundary")
    require("black ledger" in living_world_summary, failures, "living-world tool summary is not bound to Black Ledger")
    require("heat" in living_world_summary, failures, "living-world tool summary is not bound to heat tracking")
    require("followed-world" in living_world_summary or "followed world" in living_world_summary, failures, "living-world tool summary is not bound to followed-world selection")
    require("opt-in" in living_world_summary or "opt in" in living_world_summary, failures, "living-world tool summary is not bound to account opt-in")

    for packet_route in packet_routes:
        if not isinstance(packet_route, dict):
            failures.append("mobile handoff packet route row is not an object")
            continue

        role_id = str(packet_route.get("roleId") or "").strip()
        markdown_path = str(packet_route.get("markdown") or "").strip()
        json_path = str(packet_route.get("json") or "").strip()
        require(bool(role_id), failures, "mobile handoff packet route is missing roleId")
        require(markdown_path.startswith("/ready/packet/"), failures, f"mobile handoff packet route for {role_id or '<empty>'} has invalid markdown path")
        require(json_path.startswith("/ready/packet/"), failures, f"mobile handoff packet route for {role_id or '<empty>'} has invalid json path")

        markdown_result = fetch(base_url, markdown_path, timeout_seconds) if markdown_path.startswith("/") else None
        json_result = fetch(base_url, json_path, timeout_seconds) if json_path.startswith("/") else None
        packet_failures: list[str] = []
        packet_payload = parse_json(json_result, packet_failures) if json_result is not None and json_result.status_code == 200 else {}
        verdict = packet_payload.get("verdict") if isinstance(packet_payload.get("verdict"), dict) else {}
        packet = packet_payload.get("packet") if isinstance(packet_payload.get("packet"), dict) else {}
        verdict_role_id = str(verdict.get("roleId") or "")
        packet_role_id = str(packet.get("roleId") or "")

        if markdown_result is None:
            require(False, failures, f"{role_id or '<empty>'} markdown packet route was not fetched")
        else:
            require(markdown_result.status_code == 200, failures, f"{markdown_path} expected 200, got {markdown_result.status_code}")
            require(len(markdown_result.body.strip()) > 0, failures, f"{markdown_path} returned an empty body")
            require("markdown" in markdown_result.content_type.lower() or "text/plain" in markdown_result.content_type.lower(), failures, f"{markdown_path} is not markdown/text")
            require(f"# {role_id}".lower() in markdown_result.body.lower(), failures, f"{markdown_path} does not identify role {role_id}")

        if json_result is None:
            require(False, failures, f"{role_id or '<empty>'} json packet route was not fetched")
        else:
            require(json_result.status_code == 200, failures, f"{json_path} expected 200, got {json_result.status_code}")
            require("json" in json_result.content_type.lower(), failures, f"{json_path} is not JSON")
            require(len(json_result.body.strip()) > 0, failures, f"{json_path} returned an empty body")
            require(verdict_role_id == role_id, failures, f"{json_path} verdict roleId expected {role_id}, got {verdict_role_id or '<empty>'}")
            require(packet_role_id == role_id, failures, f"{json_path} packet roleId expected {role_id}, got {packet_role_id or '<empty>'}")
            failures.extend(f"{json_path}: {item}" for item in packet_failures)

        packet_route_results.append(
            {
                "roleId": role_id,
                "markdown": markdown_path,
                "markdown_status": markdown_result.status_code if markdown_result else 0,
                "markdown_content_type": markdown_result.content_type if markdown_result else "",
                "markdown_bytes": len(markdown_result.body.encode("utf-8")) if markdown_result else 0,
                "json": json_path,
                "json_status": json_result.status_code if json_result else 0,
                "json_content_type": json_result.content_type if json_result else "",
                "json_bytes": len(json_result.body.encode("utf-8")) if json_result else 0,
                "json_verdict_role_id": verdict_role_id,
                "json_packet_role_id": packet_role_id,
            }
        )

    return {
        "contractName": "chummer.ready_mobile_handoff_contract.v1",
        "status": "pass" if not failures else "fail",
        "status_code": result.status_code,
        "pwa_route": payload.get("pwa_route"),
        "continuity_route": payload.get("continuity_route"),
        "tool_ids": sorted(tool_ids),
        "living_world_summary": living_world_summary,
        "packet_roles": sorted(roles),
        "packet_route_count": len(packet_route_results),
        "packet_routes": packet_route_results,
        "failures": failures,
    }


def verify_mobile_ledger(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    result = fetch(base_url, "/mobile/pwa/ledger.json", timeout_seconds)
    payload = parse_json(result, failures) if result.status_code == 200 else {}
    cache_control = result.headers.get("cache-control", "")
    vary = result.headers.get("vary", "")
    pragma = result.headers.get("pragma", "")
    summary = str(payload.get("summary") or "").lower()
    legal_posture = str(payload.get("legal_posture") or "").lower()
    opt_in_required_for = {
        str(item or "").strip()
        for item in (payload.get("opt_in_required_for") if isinstance(payload.get("opt_in_required_for"), list) else [])
        if str(item or "").strip()
    }
    black_ledger_bound = "black ledger" in summary
    heat_bound = "heat" in summary and payload.get("heat_visibility") == "hidden_until_opt_in"
    followed_world_bound = (
        ("followed-world" in summary or "followed world" in summary)
        and payload.get("world_gate") == "account_opt_in_and_followed_world_selection"
    )
    session_continuity_bound = (
        ("session continuity" in summary or "continuity" in summary)
        and payload.get("session_visibility") == "hidden_until_opt_in"
    )
    private_table_state_hidden = (
        "aggregate only" in legal_posture
        and "no private run table state" in legal_posture
        and "world heat" in legal_posture
        and "session continuity" in legal_posture
    )

    require(result.status_code == 200, failures, f"/mobile/pwa/ledger.json expected 200, got {result.status_code}")
    require(payload.get("mode") == "mobile_pwa_living_world", failures, "mobile ledger payload mode is wrong")
    require(payload.get("status") == "opt_in_required", failures, "mobile ledger should require opt-in for anonymous access")
    require(payload.get("opt_in_route") == "/account", failures, "mobile ledger opt_in_route is not /account")
    require(black_ledger_bound, failures, "mobile ledger opt-in boundary is not bound to Black Ledger")
    require(heat_bound, failures, "mobile ledger opt-in boundary is not bound to hidden heat tracking")
    require(followed_world_bound, failures, "mobile ledger opt-in boundary is not bound to followed-world selection")
    require(session_continuity_bound, failures, "mobile ledger opt-in boundary is not bound to hidden session continuity")
    require(EXPECTED_LEDGER_OPT_IN_KEYS.issubset(opt_in_required_for), failures, f"mobile ledger missing opt-in-required keys: {sorted(EXPECTED_LEDGER_OPT_IN_KEYS - opt_in_required_for)}")
    require(private_table_state_hidden, failures, "mobile ledger legal posture does not hide private table state, world heat, and session continuity")
    require(payload.get("updates_route") == "/mobile/pwa/ledger.json", failures, "mobile ledger updates_route is wrong")
    require("private" in cache_control.lower(), failures, "mobile ledger response is not private")
    require("no-store" in cache_control.lower(), failures, "mobile ledger response is not no-store")
    require("no-cache" in cache_control.lower(), failures, "mobile ledger response is not no-cache")
    require("cookie" in vary.lower() and "authorization" in vary.lower(), failures, "mobile ledger response does not vary on Cookie and Authorization")
    require("no-cache" in pragma.lower(), failures, "mobile ledger response missing Pragma no-cache")

    return {
        "contractName": "chummer.mobile_pwa_ledger_boundary.v1",
        "status": "pass" if not failures else "fail",
        "status_code": result.status_code,
        "payload_status": payload.get("status"),
        "opt_in_route": payload.get("opt_in_route"),
        "world_gate": payload.get("world_gate"),
        "heat_visibility": payload.get("heat_visibility"),
        "session_visibility": payload.get("session_visibility"),
        "opt_in_required_for": sorted(opt_in_required_for),
        "black_ledger_bound": black_ledger_bound,
        "heat_bound": heat_bound,
        "followed_world_bound": followed_world_bound,
        "session_continuity_bound": session_continuity_bound,
        "private_table_state_hidden": private_table_state_hidden,
        "cache_control": cache_control,
        "vary": vary,
        "pragma": pragma,
        "failures": failures,
    }


def receipt_is_pass(receipt: dict[str, Any] | None) -> bool:
    return isinstance(receipt, dict) and str(receipt.get("status") or "") == "pass"


def verify_flagship_horizons(child_receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    horizon_rows: list[dict[str, Any]] = []

    route_rows = child_receipts.get("pwaStatic", {}).get("routes")
    route_statuses = {
        str(row.get("path") or ""): str(row.get("status_code") or "")
        for row in route_rows
        if isinstance(row, dict)
    } if isinstance(route_rows, list) else {}
    tool_ids = set(child_receipts.get("readyMobileHandoff", {}).get("tool_ids") or [])
    packet_roles = set(child_receipts.get("readyMobileHandoff", {}).get("packet_roles") or [])
    packet_route_count = int(child_receipts.get("readyMobileHandoff", {}).get("packet_route_count") or 0)
    browser_receipt = child_receipts.get("browserPlaywright", {})
    browser_required_proofs = set(browser_receipt.get("requiredProofs") or [])
    browser_skipped = bool(browser_receipt.get("skipped"))
    browser_status = str(browser_receipt.get("status") or "")
    required_browser_proofs = set(PLAYWRIGHT_REQUIREMENTS)
    browser_proof_coverage = (
        "full"
        if browser_status == "pass" and required_browser_proofs.issubset(browser_required_proofs)
        else "skipped"
        if browser_skipped
        else "partial"
    )

    for horizon_id, config in EXPECTED_FLAGSHIP_HORIZONS.items():
        row_failures: list[str] = []
        required_receipts = list(config.get("requiredReceipts") or [])
        for receipt_name in required_receipts:
            if not receipt_is_pass(child_receipts.get(receipt_name)):
                row_failures.append(f"{receipt_name} receipt is not pass")

        required_routes = set(config.get("requiredRoutes") or [])
        missing_routes = sorted(path for path in required_routes if route_statuses.get(path) != "200")
        if missing_routes:
            row_failures.append(f"missing deployed routes: {', '.join(missing_routes)}")

        required_tools = set(config.get("requiredTools") or [])
        missing_tools = sorted(required_tools - tool_ids)
        if missing_tools:
            row_failures.append(f"missing playtime tools: {', '.join(missing_tools)}")

        if horizon_id == "mid_term_pwa_session_utility":
            if not {"player", "gm", "organizer"}.issubset(packet_roles):
                row_failures.append("ready handoff is missing player/gm/organizer packet roles")
            if packet_route_count < len(EXPECTED_READY_ROLES):
                row_failures.append("ready handoff packet routes are not fully verified")
            if browser_status not in {"pass", ""}:
                row_failures.append("browser proof receipt is not pass")

        if horizon_id == "long_term_living_world_expansion":
            mobile_ledger = child_receipts.get("mobileLedger", {})
            cache_control = str(mobile_ledger.get("cache_control") or "").lower()
            service_worker_mode = (
                child_receipts.get("mobilePwaServiceWorkerBoundary", {})
                .get("mobileRuntime", {})
                .get("serviceWorkerBoundaryMode", "")
            )
            if mobile_ledger.get("payload_status") != config.get("requiredLedgerStatus"):
                row_failures.append("mobile ledger does not enforce opt-in-required status")
            for key, label in [
                ("black_ledger_bound", "Black Ledger heat"),
                ("heat_bound", "hidden heat tracking"),
                ("followed_world_bound", "followed-world selection"),
                ("session_continuity_bound", "session continuity"),
                ("private_table_state_hidden", "private table state"),
            ]:
                if not bool(mobile_ledger.get(key)):
                    row_failures.append(f"mobile ledger does not bind {label}")
            if "private" not in cache_control or "no-store" not in cache_control:
                row_failures.append("mobile ledger is not private/no-store")
            if service_worker_mode != "shared_portal_root_worker":
                row_failures.append("mobile service-worker boundary is not shared_portal_root_worker")

        horizon_rows.append(
            {
                "id": horizon_id,
                "title": config.get("title", horizon_id),
                "status": "pass" if not row_failures else "fail",
                "requiredReceipts": required_receipts,
                "requiredRoutes": sorted(required_routes),
                "requiredTools": sorted(required_tools),
                "failures": row_failures,
            }
        )
        failures.extend(f"{horizon_id}: {failure}" for failure in row_failures)

    return {
        "contractName": "chummer.flagship_horizons_gate.v1",
        "status": "pass" if not failures else "fail",
        "horizonCount": len(horizon_rows),
        "horizons": horizon_rows,
        "browserProofCoverage": browser_proof_coverage,
        "browserProofsRequiredForReleaseClaims": sorted(required_browser_proofs),
        "browserProofsPresent": sorted(browser_required_proofs),
        "toolIds": sorted(tool_ids),
        "packetRoles": sorted(packet_roles),
        "packetRouteCount": packet_route_count,
        "routeStatuses": route_statuses,
        "failures": failures,
    }


def verify_preflight(skip_preflight: bool) -> dict[str, Any]:
    if skip_preflight:
        return {
            "contractName": "chummer.public_edge_deploy_preflight.v1",
            "status": "pass",
            "skipped": True,
            "activePortalBuildProcesses": [],
            "failures": [],
        }

    completed = subprocess.run(
        ["pgrep", "-af", r"docker (compose .*build chummer-portal|build.*chummer-run-api:local)"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    failures: list[str] = []
    if lines:
        failures.append("portal image build/deploy process is active")
    return {
        "contractName": "chummer.public_edge_deploy_preflight.v1",
        "status": "pass" if not failures else "fail",
        "skipped": False,
        "activePortalBuildProcesses": lines,
        "failures": failures,
    }


def normalize_image_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if re.fullmatch(r"[0-9a-fA-F]{64}", normalized):
        return f"sha256:{normalized.lower()}"
    if normalized.startswith("sha256:"):
        prefix, digest = normalized.split(":", 1)
        return f"{prefix}:{digest.lower()}"
    return normalized


def run_docker_inspect(args: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def verify_portal_runtime_image(
    expected_image_id: str,
    portal_container: str,
    portal_image_tag: str,
) -> dict[str, Any]:
    expected = normalize_image_id(expected_image_id)
    if not expected:
        return {
            "contractName": "chummer.public_edge_portal_runtime_image.v1",
            "status": "pass",
            "skipped": True,
            "portalContainer": portal_container,
            "portalImageTag": portal_image_tag,
            "expectedImageId": "",
            "failures": [],
        }

    failures: list[str] = []
    container_code, container_stdout, container_stderr = run_docker_inspect(
        ["inspect", "--format", "{{.Image}} {{.Config.Image}}", portal_container]
    )
    image_code, image_stdout, image_stderr = run_docker_inspect(
        ["image", "inspect", "--format", "{{.Id}}", portal_image_tag]
    )

    actual_container_image = ""
    configured_image = ""
    actual_tag_image = ""
    if container_code != 0:
        failures.append(f"docker inspect {portal_container} failed")
    else:
        parts = container_stdout.split(maxsplit=1)
        actual_container_image = normalize_image_id(parts[0] if parts else "")
        configured_image = parts[1] if len(parts) > 1 else ""
        if actual_container_image != expected:
            failures.append(
                f"portal container image {actual_container_image or '<empty>'} does not match expected {expected}"
            )

    if image_code != 0:
        failures.append(f"docker image inspect {portal_image_tag} failed")
    else:
        actual_tag_image = normalize_image_id(image_stdout)
        if actual_tag_image != expected:
            failures.append(
                f"portal image tag {portal_image_tag} points at {actual_tag_image or '<empty>'}, expected {expected}"
            )

    return {
        "contractName": "chummer.public_edge_portal_runtime_image.v1",
        "status": "pass" if not failures else "fail",
        "skipped": False,
        "portalContainer": portal_container,
        "portalImageTag": portal_image_tag,
        "expectedImageId": expected,
        "containerImageId": actual_container_image,
        "configuredImage": configured_image,
        "tagImageId": actual_tag_image,
        "containerInspectExitCode": container_code,
        "imageInspectExitCode": image_code,
        "containerInspectStderr": container_stderr,
        "imageInspectStderr": image_stderr,
        "failures": failures,
    }


def summarize_child(name: str, child: dict[str, Any], failures: list[str]) -> str:
    status = str(child.get("status") or "fail")
    if status != "pass":
        failures.append(f"{name} proof is not pass")
    return status


def run_playwright_browser_proofs(
    base_url: str,
    required_proofs: list[str],
    timeout_seconds: float,
    artifact_dir: Path | None,
) -> dict[str, Any]:
    if not required_proofs:
        return {
            "contractName": "chummer.public_edge_browser_playwright.v1",
            "status": "pass",
            "skipped": True,
            "requiredProofs": [],
            "artifacts": {},
            "failures": [],
        }

    failures: list[str] = []
    unknown = [item for item in required_proofs if item not in PLAYWRIGHT_REQUIREMENTS]
    if unknown:
        failures.append(f"unknown Playwright proof requirements: {', '.join(sorted(unknown))}")

    proof_specs = [PLAYWRIGHT_REQUIREMENTS[item]["spec"] for item in required_proofs if item in PLAYWRIGHT_REQUIREMENTS]
    if not proof_specs:
        return {
            "contractName": "chummer.public_edge_browser_playwright.v1",
            "status": "fail",
            "skipped": False,
            "requiredProofs": required_proofs,
            "specs": [],
            "artifacts": {},
            "failures": failures or ["no Playwright specs were selected"],
        }

    completion_dir = artifact_dir or Path(tempfile.mkdtemp(prefix="chummer-public-edge-browser-proof-"))
    completion_dir.mkdir(parents=True, exist_ok=True)

    for proof_id in required_proofs:
        if proof_id not in PLAYWRIGHT_REQUIREMENTS:
            continue
        artifact_name = str(PLAYWRIGHT_REQUIREMENTS[proof_id]["artifact"])
        artifact_path = completion_dir / artifact_name
        if artifact_path.exists():
            artifact_path.unlink()

    playwright_command = resolve_playwright_command()
    playwright_env = {**os.environ}
    playwright_env.pop("FORCE_COLOR", None)
    playwright_env.pop("NO_COLOR", None)
    playwright_env["BASE_URL"] = base_url
    playwright_env["CHUMMER_COMPLETION_DIR"] = str(completion_dir)
    npm_cache_dir = completion_dir / ".npm-cache"
    npm_cache_dir.mkdir(parents=True, exist_ok=True)
    playwright_env.setdefault("npm_config_cache", str(npm_cache_dir))
    playwright_node_modules_root = resolve_playwright_node_modules_root()
    if playwright_node_modules_root is not None:
        existing_node_path = str(playwright_env.get("NODE_PATH") or "").strip()
        playwright_env["NODE_PATH"] = (
            f"{playwright_node_modules_root}{os.pathsep}{existing_node_path}"
            if existing_node_path
            else str(playwright_node_modules_root)
        )
    started = datetime.now(UTC)
    runs: dict[str, Any] = {}
    for proof_id in required_proofs:
        if proof_id not in PLAYWRIGHT_REQUIREMENTS:
            continue
        spec = str(PLAYWRIGHT_REQUIREMENTS[proof_id]["spec"])
        command = [
            *playwright_command,
            "test",
            spec,
            "--workers=1",
            "--reporter=line",
        ]
        proof_started = datetime.now(UTC)
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=playwright_env,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            proof_run = {
                "spec": spec,
                "startedAtUtc": proof_started.isoformat(),
                "completedAtUtc": datetime.now(UTC).isoformat(),
                "returnCode": completed.returncode,
                "stdoutTail": tail_lines(completed.stdout),
                "stderrTail": tail_lines(completed.stderr),
            }
            if completed.returncode != 0:
                failures.append(f"{proof_id} Playwright proof exited {completed.returncode}")
        except subprocess.TimeoutExpired as error:
            proof_run = {
                "spec": spec,
                "startedAtUtc": proof_started.isoformat(),
                "completedAtUtc": datetime.now(UTC).isoformat(),
                "returnCode": None,
                "stdoutTail": tail_lines(error.stdout),
                "stderrTail": tail_lines(error.stderr),
            }
            failures.append(f"{proof_id} Playwright proof timed out after {timeout_seconds:.0f}s")
        runs[proof_id] = proof_run

    artifacts: dict[str, Any] = {}
    for proof_id in required_proofs:
        if proof_id not in PLAYWRIGHT_REQUIREMENTS:
            continue
        artifact_name = str(PLAYWRIGHT_REQUIREMENTS[proof_id]["artifact"])
        path = completion_dir / artifact_name
        if not path.is_file():
            failures.append(f"{proof_id} did not write {artifact_name}")
            artifacts[proof_id] = {
                "path": str(path),
                "exists": False,
                "status": "missing",
            }
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            failures.append(f"{proof_id} wrote invalid JSON: {error}")
            artifacts[proof_id] = {
                "path": str(path),
                "exists": True,
                "status": "invalid_json",
            }
            continue
        status = str(payload.get("status") or "pass")
        if status != "pass":
            failures.append(f"{proof_id} artifact status is {status}")
        artifacts[proof_id] = {
            "path": str(path),
            "exists": True,
            "status": status,
            "contractName": payload.get("contractName"),
            "base_url": payload.get("base_url"),
        }

    return {
        "contractName": "chummer.public_edge_browser_playwright.v1",
        "status": "pass" if not failures else "fail",
        "skipped": False,
        "requiredProofs": required_proofs,
        "specs": proof_specs,
        "artifactDir": str(completion_dir),
        "startedAtUtc": started.isoformat(),
        "completedAtUtc": datetime.now(UTC).isoformat(),
        "runs": runs,
        "artifacts": artifacts,
        "failures": failures,
    }


def verify(
    base_url: str,
    timeout_seconds: float,
    skip_preflight: bool,
    expected_release_channel: str = "public_stable",
    playwright_requirements: list[str] | None = None,
    playwright_timeout_seconds: float = 420.0,
    playwright_artifact_dir: Path | None = None,
    expected_portal_image_id: str = "",
    portal_container: str = DEFAULT_PORTAL_CONTAINER,
    portal_image_tag: str = DEFAULT_PORTAL_IMAGE_TAG,
) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    child_receipts = {
        "downloads": verify_downloads(normalized_base_url, timeout_seconds, expected_release_channel),
        "navigation": verify_navigation(normalized_base_url, timeout_seconds),
        "pwaStatic": verify_pwa_static(normalized_base_url, timeout_seconds),
        "readyMobileHandoff": verify_ready_mobile_handoff(normalized_base_url, timeout_seconds),
        "mobileLedger": verify_mobile_ledger(normalized_base_url, timeout_seconds),
        "mobilePwaServiceWorkerBoundary": verify_mobile_pwa_service_worker_boundary.verify(normalized_base_url, timeout_seconds),
        "participateIframeShell": verify_participate_iframe_shell.verify(normalized_base_url, timeout_seconds),
        "preflight": verify_preflight(skip_preflight),
        "portalRuntimeImage": verify_portal_runtime_image(
            expected_portal_image_id,
            portal_container,
            portal_image_tag,
        ),
        "browserPlaywright": run_playwright_browser_proofs(
            normalized_base_url,
            playwright_requirements or [],
            playwright_timeout_seconds,
            playwright_artifact_dir,
        ),
    }
    child_receipts["flagshipHorizons"] = verify_flagship_horizons(child_receipts)

    failures: list[str] = []
    statuses = {name: summarize_child(name, child, failures) for name, child in child_receipts.items()}

    return {
        "contractName": "chummer.public_edge_postdeploy_gate.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "baseUrl": normalized_base_url,
        "status": "pass" if not failures else "fail",
        "childStatuses": statuses,
        "downloadsStatus": statuses["downloads"],
        "navigationStatus": statuses["navigation"],
        "pwaStaticStatus": statuses["pwaStatic"],
        "readyMobileHandoffStatus": statuses["readyMobileHandoff"],
        "mobileLedgerStatus": statuses["mobileLedger"],
        "mobilePwaServiceWorkerBoundaryStatus": statuses["mobilePwaServiceWorkerBoundary"],
        "participateIframeShellStatus": statuses["participateIframeShell"],
        "preflightStatus": statuses["preflight"],
        "portalRuntimeImageStatus": statuses["portalRuntimeImage"],
        "browserPlaywrightStatus": statuses["browserPlaywright"],
        "flagshipHorizonsStatus": statuses["flagshipHorizons"],
        "readyMobileHandoffToolIds": child_receipts["readyMobileHandoff"].get("tool_ids", []),
        "readyMobileHandoffPacketRoles": child_receipts["readyMobileHandoff"].get("packet_roles", []),
        "mobileLedgerPayloadStatus": child_receipts["mobileLedger"].get("payload_status", ""),
        "mobileLedgerCacheControl": child_receipts["mobileLedger"].get("cache_control", ""),
        "mobilePwaServiceWorkerBoundaryMode": child_receipts["mobilePwaServiceWorkerBoundary"].get("mobileRuntime", {}).get("serviceWorkerBoundaryMode", ""),
        "browserPlaywrightRequiredProofs": child_receipts["browserPlaywright"].get("requiredProofs", []),
        "flagshipHorizonIds": [row.get("id") for row in child_receipts["flagshipHorizons"].get("horizons", [])],
        "flagshipHorizonsBrowserProofCoverage": child_receipts["flagshipHorizons"].get("browserProofCoverage", ""),
        "portalRuntimeImageExpectedImageId": child_receipts["portalRuntimeImage"].get("expectedImageId", ""),
        "portalRuntimeImageContainerImageId": child_receipts["portalRuntimeImage"].get("containerImageId", ""),
        "participateIframeRouteCount": child_receipts["participateIframeShell"].get("iframe_route_count", 0),
        "visibleVersion": child_receipts["downloads"].get("visible_version", ""),
        "releaseManifestVersion": child_receipts["downloads"].get("release_version", ""),
        "childReceipts": child_receipts,
        "failures": failures,
    }


def self_contained_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify public-edge deployment after Chummer portal publish.")
    parser.add_argument("--base-url", default="https://chummer.run")
    parser.add_argument("--timeout-seconds", type=float, default=25.0)
    parser.add_argument("--skip-preflight", action="store_true", help="Skip active-build process checks for post-fact live verification.")
    parser.add_argument(
        "--expected-release-channel",
        default="public_stable",
        choices=["public_stable", "stable", "preview", "nightly"],
        help="Expected published release posture. Stable remains the default; nightly handoff verification must opt into preview.",
    )
    parser.add_argument("--require-downloads-status-playwright", action="store_true", help="Run the downloads/status public browser proof and include its receipt.")
    parser.add_argument("--require-mobile-pwa-viewport-playwright", action="store_true", help="Run the mobile PWA viewport browser proof and include its receipt.")
    parser.add_argument("--require-frontdoor-navigation-playwright", action="store_true", help="Run the frontdoor Open Chummer mobile browser proof and include its receipt.")
    parser.add_argument("--playwright-timeout-seconds", type=float, default=420.0)
    parser.add_argument("--playwright-artifact-dir")
    parser.add_argument("--expected-portal-image-id", default="", help="Optional Docker image id required for the live portal container and mutable local image tag.")
    parser.add_argument("--portal-container", default=DEFAULT_PORTAL_CONTAINER)
    parser.add_argument("--portal-image-tag", default=DEFAULT_PORTAL_IMAGE_TAG)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    playwright_requirements: list[str] = []
    if args.require_downloads_status_playwright:
        playwright_requirements.append("downloadsStatus")
    if args.require_mobile_pwa_viewport_playwright:
        playwright_requirements.append("mobilePwaViewport")
    if args.require_frontdoor_navigation_playwright:
        playwright_requirements.append("frontdoorNavigation")

    result = verify(
        args.base_url,
        args.timeout_seconds,
        args.skip_preflight,
        args.expected_release_channel,
        playwright_requirements,
        args.playwright_timeout_seconds,
        Path(args.playwright_artifact_dir) if args.playwright_artifact_dir else None,
        args.expected_portal_image_id,
        args.portal_container,
        args.portal_image_tag,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1


# Orchestrated flagship verification retained from the integration branch.
RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE_CHANNEL_RECEIPT = WORKSPACE_ROOT / "chummer-hub-registry" / ".codex-studio" / "published" / "RELEASE_CHANNEL.generated.json"
DEFAULT_PUBLIC_EDGE_OVERLAY_ROOT = RUN_SERVICES_ROOT / ".state" / "public-edge-portal-overlay" / "app"
CORE_CHILD_CONTRACTS = {
    "preflight": "chummer.public_edge_deploy_preflight.v1",
    "downloads": "chummer.downloads_version_marker.v1",
    "pwaStatic": "chummer.public_pwa_static_assets.v1",
    "mobileLedger": "chummer.mobile_pwa_ledger_boundary.v1",
    "readyMobileHandoff": "chummer.ready_mobile_handoff_contract.v1",
    "participateIframeShell": "chummer.participate_iframe_shell.v1",
}
OPTIONAL_PLAYWRIGHT_CONTRACTS = {
    "downloadsStatusBrowser": "chummer.downloads_status_e2e.v1",
    "mobilePwaViewport": "chummer.mobile_pwa_viewport_smoke.v1",
    "pwaOfflineCache": "chummer.pwa_offline_cache.v1",
    "frontdoorNavigationMobile": "chummer.frontdoor_mobile_launch.v1",
    "frontdoorNavigationLedger": "chummer.black_ledger_globe_frontdoor.v1",
    "frontdoorNavigationAnchor": "chummer.frontdoor_mobile_anchor_redirect.v1",
}
DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS = float(
    os.environ.get("CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS", "24")
)
REQUIRED_READY_MOBILE_TOOLS = {"inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world"}
REQUIRED_READY_MOBILE_PACKET_ROLES = {"player", "gm", "organizer"}
REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE = "/mobile/player"
REQUIRED_READY_MOBILE_ROLE_ROUTES = {
    "Player": {
        "mode": "player",
        "route": "/mobile/player",
        "manifest_path": "/manifest.player.webmanifest",
        "manifest_id": "/mobile/player",
        "manifest_start_url": "/mobile/player?role=Player",
        "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
        "frontdoor_default": True,
    },
    "GameMaster": {
        "mode": "gm",
        "route": "/mobile/gm",
        "manifest_path": "/manifest.gm.webmanifest",
        "manifest_id": "/mobile/gm",
        "manifest_start_url": "/mobile/gm?role=GameMaster",
        "session_handoff_route_template": "/mobile/gm?sessionId={sessionId}&role=GameMaster",
        "frontdoor_default": False,
    },
}
REQUIRED_LEDGER_CACHE_CONTROL_TOKENS = {"private", "no-store", "no-cache", "max-age=0"}
REQUIRED_LEDGER_VARY_TOKENS = {"cookie", "authorization"}
REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES = {
    "/mobile",
    "/mobile/player",
    "/mobile/gm",
    "/mobile/observer",
    "/play",
    "/play/continuity",
}
REQUIRED_PWA_MANIFEST_COUNT = 3
MINIMUM_PWA_ASSET_COUNT = 1
MINIMUM_PARTICIPATE_IFRAME_ROUTES = 2
MINIMUM_MOBILE_PWA_VIEWPORTS = 3
REQUIRED_ROLE_PWA_MANIFESTS = {
    "Player": ("/manifest.player.webmanifest", "/mobile/player", "/mobile/player?role=Player"),
    "GameMaster": ("/manifest.gm.webmanifest", "/mobile/gm", "/mobile/gm?role=GameMaster"),
}
ROLE_ALIAS_EXPECTED_FINAL_ROUTES = {
    "/player": "/mobile/player",
    "/gm": "/mobile/gm",
    "/observer": "/mobile/observer",
}
RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE = "gold_supported"
RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE = "preview_supported"
RELEASE_CHANNEL_STABLE_CHANNELS = {"public_stable", "stable", "docker"}
RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES = {
    "coverage_incomplete",
    "release_review_required",
    "desktop_polish_needed",
    "revoked",
}
FRONTDOOR_ANCHOR_CANONICAL_SUFFIX = "/#turn-runsite-card"
FRONTDOOR_ANCHOR_LEGACY_SUFFIX = "/#turn-runsite-card?"


def frontdoor_anchor_entry_url_matches_contract(entry_url: str) -> bool:
    normalized = str(entry_url or "").strip()
    return normalized.endswith(FRONTDOOR_ANCHOR_CANONICAL_SUFFIX) or normalized.endswith(FRONTDOOR_ANCHOR_LEGACY_SUFFIX)


def supportability_state_supported_for_channel(channel: str, supportability_state: str) -> bool:
    normalized_channel = (channel or "").lower()
    normalized_state = (supportability_state or "").lower()
    if normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS:
        return normalized_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
    if normalized_channel == "preview":
        return normalized_state in {
            RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE,
            RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE,
        }
    return bool(normalized_state)


def is_published_stable_release(
    expected_release_status: str,
    expected_release_channel: str,
    expected_supportability_state: str,
    expected_rollout_state: str,
) -> bool:
    normalized_status = str(expected_release_status or "").strip().lower()
    normalized_channel = str(expected_release_channel or "").strip().lower()
    normalized_supportability_state = str(expected_supportability_state or "").strip().lower()
    normalized_rollout_state = str(expected_rollout_state or "").strip().lower()
    stable_lane_published = (
        normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS
        or normalized_rollout_state == "public_stable"
    )
    return (
        stable_lane_published
        and normalized_supportability_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
        and normalized_status == "published"
    )


def expected_visible_version_candidates(
    expected_release_version: str,
    expected_release_status: str = "",
    expected_release_channel: str = "",
    expected_supportability_state: str = "",
    expected_rollout_state: str = "",
) -> list[str]:
    normalized = str(expected_release_version or "").strip()
    if not normalized:
        return []

    posture_known = any(
        (
            str(expected_release_status or "").strip(),
            str(expected_release_channel or "").strip(),
            str(expected_supportability_state or "").strip(),
            str(expected_rollout_state or "").strip(),
        )
    )
    stable_release = is_published_stable_release(
        expected_release_status,
        expected_release_channel,
        expected_supportability_state,
        expected_rollout_state,
    )
    candidates: list[str] = [f"Version {normalized}"]
    if normalized.lower().startswith("run-") and len(normalized) >= 12:
        stamp = normalized[4:12]
        if stamp.isdigit():
            stable_label = f"Version {stamp[0:4]}.{stamp[4:6]}.{stamp[6:8]}"
            preview_label = f"{stable_label} (Preview)"
            candidates.insert(0, stable_label if stable_release else preview_label)
            if not posture_known:
                candidates.insert(1, preview_label)
                candidates.insert(2, stable_label)
        else:
            candidates.insert(0, "Version" if stable_release else "Version Preview")
            if not posture_known:
                candidates.insert(1, "Version")
                candidates.insert(2, "Version Preview")

    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def expected_homepage_lane_text(
    expected_release_status: str,
    expected_release_version: str,
    expected_release_channel: str,
    expected_supportability_state: str,
    expected_rollout_state: str,
) -> str | None:
    normalized_status = (expected_release_status or "").strip().lower()
    normalized_version = (expected_release_version or "").strip()
    normalized_channel = (expected_release_channel or "").strip().lower()
    normalized_supportability_state = (expected_supportability_state or "").strip().lower()
    normalized_rollout_state = (expected_rollout_state or "").strip().lower()

    if not any(
        (
            normalized_status,
            normalized_version,
            normalized_channel,
            normalized_supportability_state,
            normalized_rollout_state,
        )
    ):
        return None

    if normalized_status and normalized_status != "published":
        return "Current public lane: Downloads paused."

    is_published_stable_release = (
        normalized_status == "published"
        and normalized_supportability_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
        and (
            normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS
            or normalized_rollout_state == "public_stable"
        )
    )
    if is_published_stable_release:
        return "Current public lane: Stable."

    if (
        normalized_channel == "preview"
        or normalized_rollout_state == "promoted_preview"
        or normalized_supportability_state == RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE
        or normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS
        or normalized_rollout_state == "public_stable"
        or normalized_supportability_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
        or normalized_version
    ):
        return "Current public lane: Preview. Review required."

    return None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return load_json(path)
    except json.JSONDecodeError:
        return {}


def resolve_public_edge_overlay_root(configured_root: str = "") -> Path:
    configured = (configured_root or os.environ.get("CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR") or "").strip()
    return Path(configured).resolve() if configured else DEFAULT_PUBLIC_EDGE_OVERLAY_ROOT.resolve()


def receipt_contract(payload: dict[str, Any]) -> str:
    return str(payload.get("contractName") or payload.get("contract_name") or "").strip()


def list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def contains_tokens(value: Any, required_tokens: set[str]) -> bool:
    normalized = str(value or "").lower()
    return all(token in normalized for token in required_tokens)


def mobile_pwa_viewport_route_set(artifact: dict[str, Any]) -> set[str]:
    routes = string_set(artifact.get("routes"))
    results = artifact.get("results") if isinstance(artifact.get("results"), list) else []
    for result in results:
        if not isinstance(result, dict):
            continue
        route = str(result.get("route") or "").strip()
        if route:
            routes.add(route)
    return routes


def route_from_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme and not parsed.netloc:
        return text
    route = parsed.path or "/"
    return route + (f"?{parsed.query}" if parsed.query else "")


def role_alias_route_results(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    results = value.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


def probe_role_alias_routes(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    normalized_base_url = base_url.rstrip("/") + "/"
    timeout = max(1.0, timeout_seconds)
    for alias_path, expected_final_route in ROLE_ALIAS_EXPECTED_FINAL_ROUTES.items():
        requested_url = urljoin(normalized_base_url, alias_path.lstrip("/"))
        final_url = ""
        final_route = ""
        http_status = 0
        error = ""
        try:
            request = Request(
                requested_url,
                headers={"User-Agent": "chummer-public-edge-postdeploy-gate/1.0"},
                method="GET",
            )
            with urlopen(request, timeout=timeout) as response:
                final_url = response.geturl()
                http_status = int(getattr(response, "status", 0) or 0)
        except HTTPError as exc:
            final_url = exc.geturl()
            http_status = int(exc.code or 0)
            error = str(exc)
        except (TimeoutError, URLError, OSError, ValueError) as exc:
            error = str(exc)
        final_route = route_from_url(final_url)
        result = {
            "aliasPath": alias_path,
            "requestedUrl": requested_url,
            "httpStatus": http_status,
            "finalUrl": final_url,
            "finalRoute": final_route,
            "expectedFinalRoute": expected_final_route,
            "pass": http_status == 200 and final_route == expected_final_route and not error,
            "error": error,
        }
        results.append(result)
    drift = [result for result in results if result.get("pass") is not True]
    return {
        "contractName": "chummer.public_role_alias_routes.v1",
        "status": "pass" if not drift and len(results) == len(ROLE_ALIAS_EXPECTED_FINAL_ROUTES) else "fail",
        "baseUrl": base_url.rstrip("/"),
        "results": results,
        "drift": drift,
    }


def coerce_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_playwright_command(command: list[str], env: dict[str, str], timeout_seconds: int) -> tuple[int, str, str, bool]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=RUN_SERVICES_ROOT,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, coerce_output(exc.output), coerce_output(exc.stderr), True
    return completed.returncode, coerce_output(completed.stdout), coerce_output(completed.stderr), False


def normalize_base_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def artifact_base_url_matches(artifact: dict[str, Any], base_url: str) -> bool:
    artifact_base_url = normalize_base_url(artifact.get("base_url") or artifact.get("baseUrl"))
    requested_base_url = normalize_base_url(base_url)
    return not artifact_base_url or artifact_base_url == requested_base_url


def artifact_generated_at_text(artifact: dict[str, Any]) -> str:
    return str(
        artifact.get("generated_at_utc")
        or artifact.get("generatedAtUtc")
        or artifact.get("generated_at")
        or artifact.get("generatedAt")
        or ""
    ).strip()


def artifact_age_hours(artifact: dict[str, Any]) -> float | None:
    generated_at = artifact_generated_at_text(artifact)
    if not generated_at:
        return None

    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)

    age_hours = (datetime.now(UTC) - parsed).total_seconds() / 3600.0
    return max(age_hours, 0.0)


def frontdoor_anchor_artifact_matches_current_contract(anchor_artifact: dict[str, Any]) -> bool:
    entry_url = str(anchor_artifact.get("entry_url") or "").strip()
    final_path = str(anchor_artifact.get("final_pathname") or "").strip()
    final_hash = str(anchor_artifact.get("final_hash") or "").strip()
    manifest_path = str(anchor_artifact.get("pwa_manifest_path") or "").strip()
    role = str(anchor_artifact.get("pwa_role") or "").strip()
    blazor_shell = str(anchor_artifact.get("blazor_shell") or "").strip()
    return (
        frontdoor_anchor_entry_url_matches_contract(entry_url)
        and final_path == "/mobile/player"
        and final_hash == "#turn-runsite-card"
        and manifest_path == "/manifest.player.webmanifest"
        and role == "Player"
        and blazor_shell == "interactive-server"
        and anchor_artifact.get("session_id_present") is True
        and anchor_artifact.get("device_id_present") is True
    )


def maybe_reuse_playwright_artifact(
    *,
    artifact_path: Path,
    expected_contract: str,
    base_url: str,
    timeout_seconds: int,
    reuse_artifact_max_age_hours: float | None,
) -> dict[str, Any] | None:
    if not artifact_path.is_file():
        return None

    artifact = load_json(artifact_path)
    artifact_contract = receipt_contract(artifact)
    artifact_status = str(artifact.get("status") or "").strip().lower()
    base_url_matches = artifact_base_url_matches(artifact, base_url)
    generated_at = artifact_generated_at_text(artifact)
    age_hours = artifact_age_hours(artifact)
    artifact_fresh = (
        True
        if reuse_artifact_max_age_hours is None
        else age_hours is not None and age_hours <= reuse_artifact_max_age_hours
    )
    artifact_pass = (
        artifact_status == "pass"
        and artifact_contract == expected_contract
        and base_url_matches
        and artifact_fresh
    )
    if not artifact_pass:
        return None

    return {
        "status": "pass",
        "exitCode": 0,
        "timedOut": False,
        "timeoutSeconds": timeout_seconds,
        "artifactPath": str(artifact_path),
        "artifactContract": artifact_contract,
        "expectedArtifactContract": expected_contract,
        "artifactBaseUrlMatchesRequested": base_url_matches,
        "artifactGeneratedAtUtc": generated_at or None,
        "artifactAgeHours": age_hours,
        "artifactFresh": artifact_fresh,
        "artifactMaxAgeHours": reuse_artifact_max_age_hours,
        "artifact": artifact,
        "artifactReused": True,
        "playwrightExecuted": False,
        "stdoutTail": "",
        "stderrTail": "",
    }


def run_child(command: list[str], output_path: Path, allow_failure: bool = False) -> dict[str, Any]:
    resolved_command = list(command)
    if len(resolved_command) >= 2 and resolved_command[1].startswith("scripts/"):
        resolved_command[1] = str(RUN_SERVICES_ROOT / resolved_command[1])
    completed = subprocess.run(
        resolved_command + ["--output", str(output_path)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=RUN_SERVICES_ROOT,
    )
    if completed.returncode != 0 and not allow_failure:
        raise RuntimeError(f"{' '.join(resolved_command)} failed with exit code {completed.returncode}")
    if not output_path.is_file():
        synthetic = {
            "status": "fail",
            "failures": [f"child verifier did not write output: {output_path.name}"],
            "childCommand": " ".join(resolved_command),
            "childExitCode": completed.returncode,
            "childStdoutTail": completed.stdout[-4000:],
            "childStderrTail": completed.stderr[-4000:],
        }
        if not allow_failure:
            raise RuntimeError(
                f"{' '.join(resolved_command)} did not write expected output {output_path}"
            )
        return synthetic
    try:
        return load_json(output_path)
    except json.JSONDecodeError:
        synthetic = {
            "status": "fail",
            "failures": [f"child verifier wrote invalid JSON: {output_path.name}"],
            "childCommand": " ".join(resolved_command),
            "childExitCode": completed.returncode,
            "childStdoutTail": completed.stdout[-4000:],
            "childStderrTail": completed.stderr[-4000:],
        }
        if not allow_failure:
            raise
        return synthetic


def compose_status(
    preflight: dict[str, Any],
    downloads: dict[str, Any],
    pwa_static: dict[str, Any],
    mobile_ledger: dict[str, Any],
    ready_mobile_handoff: dict[str, Any],
    participate_iframe_shell: dict[str, Any],
    downloads_status_browser: dict[str, Any] | None = None,
    mobile_pwa_viewport: dict[str, Any] | None = None,
    frontdoor_navigation: dict[str, Any] | None = None,
    pwa_offline_cache: dict[str, Any] | None = None,
    expected_release_version: str | None = None,
    role_alias_routes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    core_child_receipts = {
        "preflight": preflight,
        "downloads": downloads,
        "pwaStatic": pwa_static,
        "mobileLedger": mobile_ledger,
        "readyMobileHandoff": ready_mobile_handoff,
        "participateIframeShell": participate_iframe_shell,
    }
    for name, expected_contract in CORE_CHILD_CONTRACTS.items():
        child = core_child_receipts[name]
        actual_contract = str(child.get("contractName") or child.get("contract_name") or "").strip()
        if actual_contract != expected_contract:
            failures.append(f"{name} child receipt contract is not {expected_contract}")
    if preflight.get("status") != "pass":
        failures.append("public-edge deploy preflight is not pass")
    if downloads.get("status") != "pass":
        failures.append("downloads version marker proof is not pass")
    if pwa_static.get("status") != "pass":
        failures.append("public PWA static asset proof is not pass")
    if mobile_ledger.get("status") != "pass":
        failures.append("mobile PWA ledger boundary proof is not pass")
    if ready_mobile_handoff.get("status") != "pass":
        failures.append("Ready mobile handoff proof is not pass")
    if participate_iframe_shell.get("status") != "pass":
        failures.append("Participate iframe shell proof is not pass")

    service_worker = pwa_static.get("service_worker") if isinstance(pwa_static.get("service_worker"), dict) else {}
    if downloads.get("downloads_has_marker") is not True:
        failures.append("downloads receipt does not prove /downloads version marker")
    if downloads.get("status_redirect_has_marker") is not True:
        failures.append("downloads receipt does not prove /status version marker")
    visible_version = str(downloads.get("visible_version") or "").strip()
    status_redirect_version = str(downloads.get("status_redirect_version") or "").strip()
    downloads_version_marker_value = str(downloads.get("downloads_version_marker_value") or "").strip()
    status_redirect_version_marker_value = str(downloads.get("status_redirect_version_marker_value") or "").strip()
    downloads_version_marker_matches_release_channel = downloads.get("downloads_version_marker_matches_release_channel")
    status_redirect_version_marker_matches_release_channel = downloads.get("status_redirect_version_marker_matches_release_channel")
    status_redirect_heading = str(downloads.get("status_redirect_heading") or "").strip()
    status_redirect_heading_recognized = downloads.get("status_redirect_heading_recognized")
    status_redirect_heading_expected = str(downloads.get("status_redirect_heading_expected") or "").strip()
    status_redirect_heading_matches_release_channel = downloads.get("status_redirect_heading_matches_release_channel")
    status_redirect_heading_uses_generic_updated_copy = downloads.get("status_redirect_heading_uses_generic_updated_copy")
    if not visible_version.startswith("Version "):
        failures.append("downloads receipt missing visible Version text")
    if not status_redirect_version.startswith("Version "):
        failures.append("downloads receipt missing /status visible Version text")
    if not downloads_version_marker_value.startswith("Version "):
        failures.append("downloads receipt missing /downloads version marker value")
    if not status_redirect_version_marker_value.startswith("Version "):
        failures.append("downloads receipt missing /status version marker value")
    if not status_redirect_heading:
        failures.append("downloads receipt missing /status decision heading")
    if status_redirect_heading_recognized is not True:
        failures.append("downloads receipt does not prove a recognized /status decision heading")
    if status_redirect_heading_uses_generic_updated_copy is True:
        failures.append("downloads receipt still proves the stale generic Updated /status heading")
    if status_redirect_heading_expected and status_redirect_heading_matches_release_channel is not True:
        failures.append("downloads receipt does not prove the /status heading matches release posture")
    expected_release_status = str(downloads.get("expected_release_status") or "").strip()
    expected_release_channel = str(downloads.get("expected_release_channel") or "").strip()
    expected_release_supportability_state = str(downloads.get("expected_release_supportability_state") or "").strip()
    expected_release_rollout_state = str(downloads.get("expected_release_rollout_state") or "").strip()
    expected_release_version = str(expected_release_version or "").strip()
    require_release_channel_parity = bool(expected_release_version)
    expected_visible_versions = expected_visible_version_candidates(
        expected_release_version,
        expected_release_status,
        expected_release_channel,
        expected_release_supportability_state,
        expected_release_rollout_state,
    )
    visible_version_matches_release_channel = (
        downloads.get("visible_version_matches_release_channel")
        if isinstance(downloads.get("visible_version_matches_release_channel"), bool)
        else visible_version in expected_visible_versions
        if expected_release_version
        else None
    )
    status_redirect_version_matches_release_channel = (
        downloads.get("status_redirect_version_matches_release_channel")
        if isinstance(downloads.get("status_redirect_version_matches_release_channel"), bool)
        else status_redirect_version in expected_visible_versions
        if expected_release_version
        else None
    )
    if expected_release_version and downloads_version_marker_matches_release_channel is not True:
        failures.append("downloads version marker data does not match release channel")
    if expected_release_version and status_redirect_version_marker_matches_release_channel is not True:
        failures.append("status redirect version marker data does not match release channel")
    if expected_release_version and not visible_version_matches_release_channel:
        failures.append("downloads visible Version text does not match release channel")
    if expected_release_version and not status_redirect_version_matches_release_channel:
        failures.append("status redirect visible Version text does not match release channel")
    release_manifest_http_status = downloads.get("release_manifest_http_status")
    release_manifest_status_matches_release_channel = downloads.get("release_manifest_status_matches_release_channel")
    release_manifest_channel_matches_release_channel = downloads.get("release_manifest_channel_matches_release_channel")
    release_manifest_version_matches_release_channel = downloads.get("release_manifest_version_matches_release_channel")
    release_manifest_supportability_matches_release_channel = downloads.get("release_manifest_supportability_matches_release_channel")
    release_manifest_rollout_matches_release_channel = downloads.get("release_manifest_rollout_matches_release_channel")
    public_release_copy_safe = downloads.get("public_release_copy_safe")
    release_manifest_copy_safe = downloads.get("release_manifest_copy_safe")
    if require_release_channel_parity:
        if not expected_release_status:
            failures.append("downloads receipt missing expected release status")
        elif expected_release_status.lower() != "published":
            failures.append("downloads receipt expected release status is not published")
        if not expected_release_channel:
            failures.append("downloads receipt missing expected release channel")
        if not expected_release_supportability_state:
            failures.append("downloads receipt missing expected release supportability state")
        elif not supportability_state_supported_for_channel(expected_release_channel, expected_release_supportability_state):
            failures.append("downloads receipt expected release supportability is not launch-supported")
        if not expected_release_rollout_state:
            failures.append("downloads receipt missing expected release rollout state")
        elif expected_release_rollout_state.lower() in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
            failures.append(f"downloads receipt expected release rollout is blocking: {expected_release_rollout_state.lower()}")
        if release_manifest_http_status != 200:
            failures.append("downloads receipt does not prove live release manifest HTTP 200")
        if release_manifest_status_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest status does not match release channel")
        if release_manifest_channel_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest channel does not match release channel")
        if release_manifest_version_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest version does not match release channel")
        if release_manifest_supportability_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest supportability does not match release channel")
        if release_manifest_rollout_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest rollout does not match release channel")
        if public_release_copy_safe is not True:
            failures.append("downloads receipt static public release manifest copy is not safe")
        if release_manifest_copy_safe is not True:
            failures.append("downloads receipt live release manifest copy is not safe")

    pwa_manifest_count = list_count(pwa_static.get("manifests"))
    role_manifests = pwa_static.get("role_manifests") if isinstance(pwa_static.get("role_manifests"), list) else []
    role_manifest_count = len(role_manifests)
    role_manifests_by_role = {
        str(entry.get("role") or "").strip(): entry
        for entry in role_manifests
        if isinstance(entry, dict)
    }
    pwa_asset_count = list_count(pwa_static.get("assets"))
    if pwa_manifest_count < REQUIRED_PWA_MANIFEST_COUNT:
        failures.append("public PWA static proof does not include all manifests")
    for role, (path, expected_id, expected_start_url) in REQUIRED_ROLE_PWA_MANIFESTS.items():
        manifest = role_manifests_by_role.get(role)
        if not manifest:
            failures.append(f"public PWA static proof does not include the {role} role manifest")
            continue
        if str(manifest.get("path") or "").strip() != path:
            failures.append(f"public PWA static proof {role} manifest path is not {path}")
        if str(manifest.get("id") or "").strip() != expected_id:
            failures.append(f"public PWA static proof {role} manifest id is not {expected_id}")
        if str(manifest.get("start_url") or "").strip() != expected_start_url:
            failures.append(f"public PWA static proof {role} manifest start_url is not {expected_start_url}")
        if str(manifest.get("display") or "").strip() != "standalone":
            failures.append(f"public PWA static proof {role} manifest display is not standalone")
    if pwa_asset_count < MINIMUM_PWA_ASSET_COUNT:
        failures.append("public PWA static proof does not include required assets")
    if service_worker.get("ledger_stream_non_cacheable") is not True:
        failures.append("public PWA static proof does not keep ledger stream non-cacheable")
    if service_worker.get("ledger_stream_precached") is not False:
        failures.append("public PWA static proof precaches personalized ledger stream")
    if service_worker.get("worker_kind") != "play":
        failures.append("public PWA static proof does not use the Play root service worker")

    if mobile_ledger.get("payload_status") != "opt_in_required":
        failures.append("mobile ledger receipt payload is not opt_in_required")
    if not contains_tokens(mobile_ledger.get("cache_control"), REQUIRED_LEDGER_CACHE_CONTROL_TOKENS):
        failures.append("mobile ledger cache-control is missing private/no-store/no-cache/max-age=0")
    if not contains_tokens(mobile_ledger.get("vary"), REQUIRED_LEDGER_VARY_TOKENS):
        failures.append("mobile ledger vary is missing Cookie and Authorization")

    tool_ids = string_set(ready_mobile_handoff.get("tool_ids"))
    missing_tools = sorted(REQUIRED_READY_MOBILE_TOOLS - tool_ids)
    if missing_tools:
        failures.append("Ready mobile handoff is missing required tools: " + ", ".join(missing_tools))
    packet_roles = string_set(ready_mobile_handoff.get("packet_roles"))
    missing_roles = sorted(REQUIRED_READY_MOBILE_PACKET_ROLES - packet_roles)
    if missing_roles:
        failures.append("Ready mobile handoff is missing required packet roles: " + ", ".join(missing_roles))
    frontdoor_launch_route = str(ready_mobile_handoff.get("frontdoor_launch_route") or "").strip()
    if frontdoor_launch_route != REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE:
        failures.append(
            "Ready mobile handoff frontdoor launch route is not " + REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE
        )
    role_routes = ready_mobile_handoff.get("role_routes") if isinstance(ready_mobile_handoff.get("role_routes"), list) else []
    role_routes_by_role = {
        str(item.get("role") or "").strip(): item
        for item in role_routes
        if isinstance(item, dict)
    }
    for role_name, expected in REQUIRED_READY_MOBILE_ROLE_ROUTES.items():
        route = role_routes_by_role.get(role_name)
        if not route:
            failures.append(f"Ready mobile handoff is missing the {role_name} role route")
            continue
        if str(route.get("mode") or "").strip() != expected["mode"]:
            failures.append(f"Ready mobile handoff {role_name} mode is not {expected['mode']}")
        if str(route.get("route") or "").strip() != expected["route"]:
            failures.append(f"Ready mobile handoff {role_name} route is not {expected['route']}")
        if str(route.get("manifest_path") or "").strip() != expected["manifest_path"]:
            failures.append(f"Ready mobile handoff {role_name} manifest path is not {expected['manifest_path']}")
        if str(route.get("manifest_id") or "").strip() != expected["manifest_id"]:
            failures.append(f"Ready mobile handoff {role_name} manifest id is not {expected['manifest_id']}")
        if str(route.get("manifest_start_url") or "").strip() != expected["manifest_start_url"]:
            failures.append(
                f"Ready mobile handoff {role_name} manifest start_url is not {expected['manifest_start_url']}"
            )
        if (
            str(route.get("session_handoff_route_template") or "").strip()
            != expected["session_handoff_route_template"]
        ):
            failures.append(
                "Ready mobile handoff "
                f"{role_name} session handoff route template is not {expected['session_handoff_route_template']}"
            )
        if route.get("frontdoor_default") is not expected["frontdoor_default"]:
            failures.append(
                "Ready mobile handoff "
                f"{role_name} frontdoor_default is not {str(expected['frontdoor_default']).lower()}"
            )

    participate_route_count = int_value(participate_iframe_shell.get("route_count"))
    participate_iframe_count = int_value(participate_iframe_shell.get("iframe_route_count"))
    participate_offline_count = int_value(participate_iframe_shell.get("offline_fallback_route_count"))
    if participate_route_count < MINIMUM_PARTICIPATE_IFRAME_ROUTES:
        failures.append("Participate iframe shell route count is below required public routes")
    if participate_iframe_count < MINIMUM_PARTICIPATE_IFRAME_ROUTES:
        failures.append("Participate iframe shell does not prove both iframe routes")
    if participate_offline_count != 0:
        failures.append("Participate iframe shell is using offline fallback routes")

    if downloads_status_browser and downloads_status_browser.get("status") != "pass":
        failures.append("downloads-status Playwright proof is not pass")
    if mobile_pwa_viewport and mobile_pwa_viewport.get("status") != "pass":
        failures.append("mobile PWA viewport Playwright proof is not pass")
    if frontdoor_navigation and frontdoor_navigation.get("status") != "pass":
        failures.append("front-door navigation Playwright proof is not pass")
    if pwa_offline_cache and pwa_offline_cache.get("status") != "pass":
        failures.append("PWA offline cache Playwright proof is not pass")
    role_alias_route_result_rows = role_alias_route_results(role_alias_routes)
    role_alias_route_results_by_alias = {
        str(result.get("aliasPath") or "").strip(): result
        for result in role_alias_route_result_rows
    }
    role_alias_route_drift: list[dict[str, Any]] = []
    if role_alias_routes is not None:
        if role_alias_routes.get("status") != "pass":
            failures.append("role alias route redirects drifted")
        for alias_path, expected_final_route in ROLE_ALIAS_EXPECTED_FINAL_ROUTES.items():
            route_result = role_alias_route_results_by_alias.get(alias_path)
            if not route_result:
                failures.append(f"{alias_path} alias route proof is missing")
                role_alias_route_drift.append(
                    {
                        "aliasPath": alias_path,
                        "finalRoute": "",
                        "expectedFinalRoute": expected_final_route,
                        "pass": False,
                        "error": "missing result",
                    }
                )
                continue
            final_route = str(route_result.get("finalRoute") or route_from_url(route_result.get("finalUrl"))).strip()
            if final_route != expected_final_route or route_result.get("pass") is not True:
                drift_result = dict(route_result)
                role_alias_route_drift.append(drift_result)
                failures.append(f"{alias_path} resolved to {final_route or '<missing>'} instead of {expected_final_route}")
    if downloads_status_browser:
        artifact = downloads_status_browser.get("artifact") if isinstance(downloads_status_browser.get("artifact"), dict) else {}
        artifact_contract = receipt_contract(artifact)
        if artifact_contract != OPTIONAL_PLAYWRIGHT_CONTRACTS["downloadsStatusBrowser"]:
            failures.append(
                "downloads-status Playwright artifact contract is not "
                + OPTIONAL_PLAYWRIGHT_CONTRACTS["downloadsStatusBrowser"]
            )
        else:
            browser_status_heading = str(artifact.get("status_redirect_heading") or "").strip()
            browser_status_heading_expected = str(artifact.get("status_redirect_heading_expected") or "").strip()
            browser_status_heading_recognized = artifact.get("status_redirect_heading_recognized")
            browser_status_heading_matches_release_channel = artifact.get("status_redirect_heading_matches_release_channel")
            browser_status_heading_uses_generic_updated_copy = artifact.get("status_redirect_heading_uses_generic_updated_copy")
            if not browser_status_heading:
                failures.append("downloads-status Playwright proof does not record a /status heading")
            if browser_status_heading_recognized is not True:
                failures.append("downloads-status Playwright proof does not prove a recognized /status decision heading")
            if not browser_status_heading_expected:
                failures.append("downloads-status Playwright proof does not record the expected /status heading")
            if browser_status_heading_uses_generic_updated_copy is True:
                failures.append("downloads-status Playwright proof still uses stale generic Updated heading")
            if browser_status_heading_expected and browser_status_heading_matches_release_channel is not True:
                failures.append("downloads-status Playwright proof does not prove the /status heading matches release posture")
    if mobile_pwa_viewport:
        artifact = mobile_pwa_viewport.get("artifact") if isinstance(mobile_pwa_viewport.get("artifact"), dict) else {}
        if receipt_contract(artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["mobilePwaViewport"]:
            failures.append(
                "mobile PWA viewport Playwright artifact contract is not "
                + OPTIONAL_PLAYWRIGHT_CONTRACTS["mobilePwaViewport"]
            )
        mobile_pwa_viewport_routes = mobile_pwa_viewport_route_set(artifact)
        missing_mobile_pwa_viewport_routes = sorted(REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES - mobile_pwa_viewport_routes)
        if int_value(artifact.get("route_count")) < len(REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES):
            failures.append("mobile PWA viewport Playwright route count is below required mobile routes")
        if int_value(artifact.get("viewport_count")) < MINIMUM_MOBILE_PWA_VIEWPORTS:
            failures.append("mobile PWA viewport Playwright viewport count is below required viewports")
        if missing_mobile_pwa_viewport_routes:
            failures.append("mobile PWA viewport Playwright proof is missing required routes: " + ", ".join(missing_mobile_pwa_viewport_routes))
    else:
        mobile_pwa_viewport_routes = set()
        missing_mobile_pwa_viewport_routes = sorted(REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES)
    if pwa_offline_cache:
        artifact = pwa_offline_cache.get("artifact") if isinstance(pwa_offline_cache.get("artifact"), dict) else {}
        if receipt_contract(artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["pwaOfflineCache"]:
            failures.append(
                "PWA offline cache Playwright artifact contract is not "
                + OPTIONAL_PLAYWRIGHT_CONTRACTS["pwaOfflineCache"]
            )
        cached_paths = string_set(artifact.get("cached_paths"))
        for expected_path in ["/manifest.player.webmanifest", "/manifest.gm.webmanifest", "/mobile.css", "/mobile-turn-companion.js", "/mobile/player", "/mobile/gm"]:
            if expected_path not in cached_paths:
                failures.append(f"PWA offline cache proof did not cache {expected_path}")
        if artifact.get("personalized_ledger_cached") is True:
            failures.append("PWA offline cache proof cached the personalized ledger stream")
        role_results = artifact.get("offline_role_routes") if isinstance(artifact.get("offline_role_routes"), list) else []
        role_results_by_name = {
            str(item.get("name") or "").strip(): item
            for item in role_results
            if isinstance(item, dict)
        }
        expected_role_results = {
            "player": ("Player", "/mobile/player", "/manifest.player.webmanifest"),
            "gm": ("GameMaster", "/mobile/gm", "/manifest.gm.webmanifest"),
        }
        for name, (role, cached_path, manifest) in expected_role_results.items():
            result = role_results_by_name.get(name)
            if not result:
                failures.append(f"PWA offline cache proof is missing {name} offline role route")
                continue
            if result.get("offline_reload") != "pass":
                failures.append(f"PWA offline cache proof did not reload {name} offline")
            if result.get("role") != role:
                failures.append(f"PWA offline cache proof {name} role is not {role}")
            if result.get("cached_path") != cached_path:
                failures.append(f"PWA offline cache proof {name} cached path is not {cached_path}")
            if result.get("manifest") != manifest:
                failures.append(f"PWA offline cache proof {name} manifest is not {manifest}")
    if frontdoor_navigation:
        mobile_artifact = frontdoor_navigation.get("mobileArtifact") if isinstance(frontdoor_navigation.get("mobileArtifact"), dict) else {}
        ledger_artifact = frontdoor_navigation.get("ledgerArtifact") if isinstance(frontdoor_navigation.get("ledgerArtifact"), dict) else {}
        anchor_artifact = frontdoor_navigation.get("anchorArtifact") if isinstance(frontdoor_navigation.get("anchorArtifact"), dict) else {}
        frontdoor_navigation_stderr_tail = str(frontdoor_navigation.get("stderrTail") or "").strip()
        frontdoor_navigation_artifacts_missing = not mobile_artifact and not ledger_artifact and not anchor_artifact
        frontdoor_gated_targets = string_set(mobile_artifact.get("gated_targets"))
        frontdoor_public_targets = string_set(mobile_artifact.get("public_targets"))
        frontdoor_homepage_lane_text = str(mobile_artifact.get("homepage_lane_text") or "").strip()
        frontdoor_play_route = str(mobile_artifact.get("play_route") or "").strip()
        frontdoor_play_sign_in_route = str(mobile_artifact.get("play_sign_in_route") or "").strip()
        frontdoor_direct_player_route = str(mobile_artifact.get("direct_player_route") or "").strip()
        frontdoor_final_path = ""
        frontdoor_final_url = str(mobile_artifact.get("final_url") or "").strip()
        if frontdoor_final_url:
            try:
                from urllib.parse import urlparse

                frontdoor_final_path = urlparse(frontdoor_final_url).path
            except ValueError:
                frontdoor_final_path = ""
        frontdoor_http_status = int_value(mobile_artifact.get("direct_player_http_status"))
        frontdoor_pwa_manifest_path = str(mobile_artifact.get("pwa_manifest_path") or "").strip()
        frontdoor_pwa_role = str(mobile_artifact.get("pwa_role") or "").strip()
        frontdoor_blazor_shell = str(mobile_artifact.get("blazor_shell") or "").strip()
        frontdoor_rybbit_tag = str(mobile_artifact.get("rybbit_tag") or "").strip()
        frontdoor_rybbit_route = str(mobile_artifact.get("rybbit_route") or "").strip()
        frontdoor_rybbit_mode = str(mobile_artifact.get("rybbit_mode") or "").strip()
        frontdoor_rybbit_role = str(mobile_artifact.get("rybbit_role") or "").strip()
        player_handoff_url = str(mobile_artifact.get("player_session_handoff_url") or "").strip()
        player_handoff_status = str(mobile_artifact.get("player_session_handoff_status") or "").strip()
        player_handoff_link_text = str(mobile_artifact.get("player_session_handoff_link_text") or "").strip()
        frontdoor_gm_route = str(mobile_artifact.get("gm_route") or "").strip()
        frontdoor_gm_final_path = ""
        frontdoor_gm_final_url = str(mobile_artifact.get("gm_final_url") or "").strip()
        if frontdoor_gm_final_url:
            try:
                from urllib.parse import urlparse

                frontdoor_gm_final_path = urlparse(frontdoor_gm_final_url).path
            except ValueError:
                frontdoor_gm_final_path = ""
        frontdoor_gm_http_status = int_value(mobile_artifact.get("gm_http_status"))
        frontdoor_gm_pwa_manifest_path = str(mobile_artifact.get("gm_pwa_manifest_path") or "").strip()
        frontdoor_gm_pwa_role = str(mobile_artifact.get("gm_pwa_role") or "").strip()
        frontdoor_gm_blazor_shell = str(mobile_artifact.get("gm_blazor_shell") or "").strip()
        frontdoor_gm_rybbit_tag = str(mobile_artifact.get("gm_rybbit_tag") or "").strip()
        frontdoor_gm_rybbit_route = str(mobile_artifact.get("gm_rybbit_route") or "").strip()
        frontdoor_gm_rybbit_mode = str(mobile_artifact.get("gm_rybbit_mode") or "").strip()
        frontdoor_gm_rybbit_role = str(mobile_artifact.get("gm_rybbit_role") or "").strip()
        gm_handoff_url = str(mobile_artifact.get("gm_session_handoff_url") or "").strip()
        gm_handoff_status = str(mobile_artifact.get("gm_session_handoff_status") or "").strip()
        gm_handoff_link_text = str(mobile_artifact.get("gm_session_handoff_link_text") or "").strip()
        frontdoor_anchor_entry_url = str(anchor_artifact.get("entry_url") or "").strip()
        frontdoor_anchor_final_url = str(anchor_artifact.get("final_url") or "").strip()
        frontdoor_anchor_final_path = str(anchor_artifact.get("final_pathname") or "").strip()
        frontdoor_anchor_final_hash = str(anchor_artifact.get("final_hash") or "").strip()
        frontdoor_anchor_pwa_manifest_path = str(anchor_artifact.get("pwa_manifest_path") or "").strip()
        frontdoor_anchor_pwa_role = str(anchor_artifact.get("pwa_role") or "").strip()
        frontdoor_anchor_blazor_shell = str(anchor_artifact.get("blazor_shell") or "").strip()
        frontdoor_anchor_failure = str(anchor_artifact.get("failure") or "").strip()
        frontdoor_anchor_current_contract_satisfied = frontdoor_navigation.get("anchorArtifactCurrentContractSatisfied")
        if frontdoor_anchor_current_contract_satisfied is None:
            frontdoor_anchor_current_contract_satisfied = frontdoor_anchor_artifact_matches_current_contract(anchor_artifact)
        expected_frontdoor_homepage_lane_text = expected_homepage_lane_text(
            expected_release_status,
            expected_release_version,
            expected_release_channel,
            expected_release_supportability_state,
            expected_release_rollout_state,
        )
        frontdoor_homepage_lane_matches_release_channel = (
            frontdoor_homepage_lane_text == expected_frontdoor_homepage_lane_text
            if expected_frontdoor_homepage_lane_text
            else None
        )
        if frontdoor_navigation_artifacts_missing:
            if frontdoor_navigation_stderr_tail:
                normalized_stderr_tail = (
                    frontdoor_navigation_stderr_tail.replace("\\r\\n", "\n")
                    .replace("\\n", "\n")
                    .replace("\\r", "\n")
                )
                first_line = normalized_stderr_tail.splitlines()[0].strip()
                if first_line:
                    failures.append("front-door navigation Playwright proof failed before artifacts were written: " + first_line)
        else:
            if receipt_contract(mobile_artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationMobile"]:
                failures.append(
                    "front-door navigation mobile artifact contract is not "
                    + OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationMobile"]
                )
            if receipt_contract(ledger_artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationLedger"]:
                failures.append(
                    "front-door navigation ledger artifact contract is not "
                    + OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationLedger"]
                )
            if receipt_contract(anchor_artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationAnchor"]:
                failures.append(
                    "front-door navigation anchor artifact contract is not "
                    + OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationAnchor"]
                )
            if "Build" not in frontdoor_gated_targets:
                failures.append("front-door navigation does not gate Build")
            if "Build" in frontdoor_public_targets:
                failures.append("front-door navigation exposes Build as public")
            if "Play" not in frontdoor_gated_targets:
                failures.append("front-door navigation does not gate Play")
            if "Play" in frontdoor_public_targets:
                failures.append("front-door navigation exposes Play as public")
            if not frontdoor_homepage_lane_text:
                failures.append("front-door navigation homepage does not disclose current public lane")
            if expected_frontdoor_homepage_lane_text and frontdoor_homepage_lane_matches_release_channel is not True:
                failures.append("front-door navigation homepage current public lane copy does not match release posture")
            if frontdoor_play_route != "/mobile/player":
                failures.append("front-door navigation Play route is not /mobile/player")
            if frontdoor_play_sign_in_route != "/login?next=%2Fmobile%2Fplayer":
                failures.append("front-door navigation Play sign-in route is not /login?next=%2Fmobile%2Fplayer")
            if frontdoor_direct_player_route != "/mobile/player":
                failures.append("front-door navigation direct player route is not /mobile/player")
            if frontdoor_http_status != 200:
                failures.append("front-door navigation Play launch did not return HTTP 200")
            if frontdoor_final_path != "/mobile/player":
                failures.append("front-door navigation Play launch did not land on /mobile/player")
            if mobile_artifact.get("live_turn_companion_shell") is not True:
                failures.append("front-door navigation Play launch did not prove the live turn companion shell")
            if frontdoor_pwa_manifest_path != "/manifest.player.webmanifest":
                failures.append("front-door navigation Play launch did not activate the player PWA manifest")
            if frontdoor_pwa_role != "Player":
                failures.append("front-door navigation Play launch did not prove the Player role")
            if frontdoor_blazor_shell != "interactive-server":
                failures.append("front-door navigation Play launch did not prove the interactive Blazor shell")
            if mobile_artifact.get("rybbit_configured") is not True or frontdoor_rybbit_tag != "mobile_play_shell":
                failures.append("front-door navigation Play launch did not prove the Rybbit mobile shell config")
            if frontdoor_rybbit_route != "/mobile/player" or frontdoor_rybbit_mode != "player" or frontdoor_rybbit_role != "Player":
                failures.append("front-door navigation Play launch did not prove the Player Rybbit role config")
            if mobile_artifact.get("rybbit_site_id_present") is not True or mobile_artifact.get("rybbit_script_url_allowed") is not True:
                failures.append("front-door navigation Play launch did not prove the Rybbit provider config")
            if mobile_artifact.get("rybbit_skip_mobile_paths") is not True:
                failures.append("front-door navigation Play launch did not prove Rybbit skips mobile paths")
            if mobile_artifact.get("rybbit_mask_mobile_paths") is not True:
                failures.append("front-door navigation Play launch did not prove Rybbit masks mobile paths")
            if mobile_artifact.get("rybbit_masks_private_play_routes") is not True:
                failures.append("front-door navigation Play launch did not prove Rybbit masks private play routes")
            if mobile_artifact.get("rybbit_replay_blocks_turn_root") is not True:
                failures.append("front-door navigation Play launch did not prove Rybbit replay blocks turn content")
            if "/mobile/player?" not in player_handoff_url:
                failures.append("front-door navigation Player session handoff URL is not a player mobile route")
            if player_handoff_status != "Session handoff is ready in the link above.":
                failures.append("front-door navigation Player session handoff did not expose ready status")
            if player_handoff_link_text != "Open session handoff link":
                failures.append("front-door navigation Player session handoff did not relabel the visible route")
            if mobile_artifact.get("player_session_handoff_preserves_session") is not True:
                failures.append("front-door navigation Player session handoff did not preserve session id")
            if mobile_artifact.get("player_session_handoff_preserves_role") is not True:
                failures.append("front-door navigation Player session handoff did not preserve role")
            if mobile_artifact.get("player_session_handoff_strips_device") is not True:
                failures.append("front-door navigation Player session handoff leaked sender device id")
            if mobile_artifact.get("player_session_handoff_sender_device_id_present") is not True:
                failures.append("front-door navigation Player session handoff did not prove a sender device id was stripped")
            if not frontdoor_gm_route.startswith("/mobile/gm"):
                failures.append("front-door navigation GM switch route is not /mobile/gm")
            if frontdoor_gm_http_status != 200:
                failures.append("front-door navigation GM switch did not return HTTP 200")
            if frontdoor_gm_final_path != "/mobile/gm":
                failures.append("front-door navigation GM switch did not land on /mobile/gm")
            if mobile_artifact.get("gm_live_turn_companion_shell") is not True:
                failures.append("front-door navigation GM switch did not prove the live turn companion shell")
            if frontdoor_gm_pwa_manifest_path != "/manifest.gm.webmanifest":
                failures.append("front-door navigation GM switch did not activate the GM PWA manifest")
            if frontdoor_gm_pwa_role != "GameMaster":
                failures.append("front-door navigation GM switch did not prove the GameMaster role")
            if frontdoor_gm_blazor_shell != "interactive-server":
                failures.append("front-door navigation GM switch did not prove the interactive Blazor shell")
            if mobile_artifact.get("gm_rybbit_configured") is not True or frontdoor_gm_rybbit_tag != "mobile_play_shell":
                failures.append("front-door navigation GM switch did not prove the Rybbit mobile shell config")
            if frontdoor_gm_rybbit_route != "/mobile/gm" or frontdoor_gm_rybbit_mode != "gm" or frontdoor_gm_rybbit_role != "GameMaster":
                failures.append("front-door navigation GM switch did not prove the GM Rybbit role config")
            if mobile_artifact.get("gm_rybbit_site_id_present") is not True or mobile_artifact.get("gm_rybbit_script_url_allowed") is not True:
                failures.append("front-door navigation GM switch did not prove the Rybbit provider config")
            if mobile_artifact.get("gm_rybbit_skip_mobile_paths") is not True:
                failures.append("front-door navigation GM switch did not prove Rybbit skips mobile paths")
            if mobile_artifact.get("gm_rybbit_mask_mobile_paths") is not True:
                failures.append("front-door navigation GM switch did not prove Rybbit masks mobile paths")
            if mobile_artifact.get("gm_rybbit_masks_private_play_routes") is not True:
                failures.append("front-door navigation GM switch did not prove Rybbit masks private play routes")
            if mobile_artifact.get("gm_rybbit_replay_blocks_turn_root") is not True:
                failures.append("front-door navigation GM switch did not prove Rybbit replay blocks turn content")
            if "/mobile/gm?" not in gm_handoff_url:
                failures.append("front-door navigation GM session handoff URL is not a GM mobile route")
            if gm_handoff_status != "Session handoff is ready in the link above.":
                failures.append("front-door navigation GM session handoff did not expose ready status")
            if gm_handoff_link_text != "Open session handoff link":
                failures.append("front-door navigation GM session handoff did not relabel the visible route")
            if mobile_artifact.get("gm_session_handoff_preserves_session") is not True:
                failures.append("front-door navigation GM session handoff did not preserve session id")
            if mobile_artifact.get("gm_session_handoff_preserves_role") is not True:
                failures.append("front-door navigation GM session handoff did not preserve role")
            if mobile_artifact.get("gm_session_handoff_strips_device") is not True:
                failures.append("front-door navigation GM session handoff leaked sender device id")
            if mobile_artifact.get("gm_session_handoff_sender_device_id_present") is not True:
                failures.append("front-door navigation GM session handoff did not prove a sender device id was stripped")
            if not frontdoor_anchor_entry_url_matches_contract(frontdoor_anchor_entry_url):
                failures.append("front-door navigation homepage anchor proof did not start from /#turn-runsite-card")
            if frontdoor_anchor_final_path != "/mobile/player":
                failures.append("front-door navigation homepage anchor proof did not land on /mobile/player")
            if frontdoor_anchor_final_hash != "#turn-runsite-card":
                failures.append("front-door navigation homepage anchor proof did not preserve #turn-runsite-card")
            if frontdoor_anchor_pwa_manifest_path != "/manifest.player.webmanifest":
                failures.append("front-door navigation homepage anchor proof did not activate the player PWA manifest")
            if frontdoor_anchor_pwa_role != "Player":
                failures.append("front-door navigation homepage anchor proof did not prove the Player role")
            if frontdoor_anchor_blazor_shell != "interactive-server":
                failures.append("front-door navigation homepage anchor proof did not prove the interactive Blazor shell")
            if anchor_artifact.get("session_id_present") is not True:
                failures.append("front-door navigation homepage anchor proof did not reach a session-backed player route")
            if anchor_artifact.get("device_id_present") is not True:
                failures.append("front-door navigation homepage anchor proof did not reach a device-backed player route")
            if frontdoor_anchor_failure:
                failures.append("front-door navigation homepage anchor proof failed: " + frontdoor_anchor_failure)

    preflight_findings = preflight.get("findings") if isinstance(preflight.get("findings"), list) else []
    preflight_overlay_fingerprint = (
        preflight.get("overlayBuildInfoSourceFingerprint")
        if isinstance(preflight.get("overlayBuildInfoSourceFingerprint"), dict)
        else {}
    )
    preflight_overlay_fingerprint_missing_keys = string_list(preflight_overlay_fingerprint.get("missingKeys"))
    preflight_overlay_fingerprint_mismatched_keys = string_list(preflight_overlay_fingerprint.get("mismatchedKeys"))
    preflight_overlay_fingerprint_aggregate_matches = (
        preflight_overlay_fingerprint.get("aggregateMatchesCurrentSource")
        if isinstance(preflight_overlay_fingerprint.get("aggregateMatchesCurrentSource"), bool)
        else None
    )
    if preflight_overlay_fingerprint_missing_keys:
        failures.append(
            "public-edge preflight overlay build info is missing source fingerprint fields: "
            + ", ".join(preflight_overlay_fingerprint_missing_keys)
        )
    if preflight_overlay_fingerprint_mismatched_keys:
        failures.append(
            "public-edge preflight overlay build info source fingerprint does not match current source: "
            + ", ".join(preflight_overlay_fingerprint_mismatched_keys)
        )
    result = {
        "contractName": "chummer.public_edge_postdeploy_gate.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if not failures else "fail",
        "baseUrl": downloads.get("base_url") or pwa_static.get("base_url") or "",
        "preflightStatus": preflight.get("status"),
        "preflightActiveLockCount": preflight.get("activeLockCount"),
        "preflightBlockingLockCount": sum(1 for finding in preflight_findings if isinstance(finding, dict) and finding.get("id") == "active_build_lane"),
        "preflightForeignLockCount": preflight.get("foreignLockCount"),
        "preflightIgnoredForeignLockCount": preflight.get("ignoredForeignLockCount"),
        "preflightFindingCount": len(preflight_findings),
        "preflightForeignLocksIgnored": preflight.get("foreignLocksIgnored"),
        "preflightAllowForeignBuildLocks": preflight.get("allowForeignBuildLocks"),
        "preflightStaleLookingLockCount": preflight.get("staleLookingLockCount"),
        "preflightStaleForeignLockCount": preflight.get("staleForeignLockCount"),
        "preflightStaleForeignLocksIgnored": preflight.get("staleForeignLocksIgnored"),
        "preflightAllowStaleForeignBuildLocks": preflight.get("allowStaleForeignBuildLocks"),
        "preflightOverlayRoot": preflight.get("overlayRoot"),
        "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource": preflight_overlay_fingerprint_aggregate_matches,
        "preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256": preflight_overlay_fingerprint.get("recordedAggregateSha256"),
        "preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256": preflight_overlay_fingerprint.get("expectedAggregateSha256"),
        "preflightOverlayBuildInfoSourceFingerprintMissingKeys": preflight_overlay_fingerprint_missing_keys,
        "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys": preflight_overlay_fingerprint_mismatched_keys,
        "downloadsStatus": downloads.get("status"),
        "downloadsHasMarker": downloads.get("downloads_has_marker"),
        "statusRedirectHasMarker": downloads.get("status_redirect_has_marker"),
        "visibleVersion": downloads.get("visible_version"),
        "statusRedirectVersion": downloads.get("status_redirect_version"),
        "downloadsVersionMarkerValue": downloads.get("downloads_version_marker_value"),
        "statusRedirectVersionMarkerValue": downloads.get("status_redirect_version_marker_value"),
        "downloadsVersionMarkerMatchesReleaseChannel": downloads_version_marker_matches_release_channel,
        "statusRedirectVersionMarkerMatchesReleaseChannel": status_redirect_version_marker_matches_release_channel,
        "statusRedirectHeading": status_redirect_heading,
        "statusRedirectHeadingRecognized": status_redirect_heading_recognized,
        "statusRedirectHeadingExpected": status_redirect_heading_expected,
        "statusRedirectHeadingMatchesReleaseChannel": status_redirect_heading_matches_release_channel,
        "statusRedirectHeadingUsesGenericUpdatedCopy": status_redirect_heading_uses_generic_updated_copy,
        "expectedReleaseVersion": expected_release_version,
        "visibleVersionMatchesReleaseChannel": visible_version_matches_release_channel,
        "statusRedirectVersionMatchesReleaseChannel": status_redirect_version_matches_release_channel,
        "expectedReleaseStatus": expected_release_status,
        "expectedReleaseChannel": expected_release_channel,
        "expectedReleaseSupportabilityState": expected_release_supportability_state,
        "expectedReleaseRolloutState": expected_release_rollout_state,
        "releaseManifestHttpStatus": release_manifest_http_status,
        "releaseManifestStatus": downloads.get("release_manifest_status"),
        "releaseManifestStatusMatchesReleaseChannel": release_manifest_status_matches_release_channel,
        "releaseManifestChannel": downloads.get("release_manifest_channel"),
        "releaseManifestChannelMatchesReleaseChannel": release_manifest_channel_matches_release_channel,
        "releaseManifestVersion": downloads.get("release_manifest_version"),
        "releaseManifestVersionMatchesReleaseChannel": release_manifest_version_matches_release_channel,
        "releaseManifestSupportabilityState": downloads.get("release_manifest_supportability_state"),
        "releaseManifestSupportabilityMatchesReleaseChannel": release_manifest_supportability_matches_release_channel,
        "releaseManifestRolloutState": downloads.get("release_manifest_rollout_state"),
        "releaseManifestRolloutMatchesReleaseChannel": release_manifest_rollout_matches_release_channel,
        "publicReleaseManifestCopySafe": public_release_copy_safe,
        "publicReleaseManifestUnsafeCopyMarkers": downloads.get("public_release_unsafe_copy_markers"),
        "publicReleaseManifestHasPreviewOrReviewCaveat": downloads.get("public_release_has_preview_or_review_caveat"),
        "releaseManifestCopySafe": release_manifest_copy_safe,
        "releaseManifestUnsafeCopyMarkers": downloads.get("release_manifest_unsafe_copy_markers"),
        "releaseManifestHasPreviewOrReviewCaveat": downloads.get("release_manifest_has_preview_or_review_caveat"),
        "releaseManifestParseError": downloads.get("release_manifest_parse_error"),
        "pwaStaticStatus": pwa_static.get("status"),
        "pwaManifestCount": pwa_manifest_count,
        "rolePwaManifestCount": role_manifest_count,
        "rolePwaManifests": role_manifests,
        "pwaAssetCount": pwa_asset_count,
        "ledgerStreamNonCacheable": service_worker.get("ledger_stream_non_cacheable"),
        "ledgerStreamPrecached": service_worker.get("ledger_stream_precached"),
        "pwaRootWorkerKind": service_worker.get("worker_kind"),
        "pwaRootWorkerCacheVersion": service_worker.get("cache_version"),
        "mobileLedgerStatus": mobile_ledger.get("status"),
        "mobileLedgerPayloadStatus": mobile_ledger.get("payload_status"),
        "mobileLedgerCacheControl": mobile_ledger.get("cache_control"),
        "mobileLedgerVary": mobile_ledger.get("vary"),
        "readyMobileHandoffStatus": ready_mobile_handoff.get("status"),
        "readyMobileHandoffToolIds": ready_mobile_handoff.get("tool_ids"),
        "readyMobileHandoffPacketRoles": ready_mobile_handoff.get("packet_roles"),
        "readyMobileHandoffFrontdoorLaunchRoute": ready_mobile_handoff.get("frontdoor_launch_route"),
        "readyMobileHandoffRoleRoutes": ready_mobile_handoff.get("role_routes"),
        "participateIframeShellStatus": participate_iframe_shell.get("status"),
        "participateIframeRouteCount": participate_route_count,
        "participateIframeRouteIframeCount": participate_iframe_count,
        "participateIframeRouteOfflineFallbackCount": participate_offline_count,
        "coreChildContracts": {
            name: str(child.get("contractName") or child.get("contract_name") or "").strip()
            for name, child in core_child_receipts.items()
        },
        "failures": failures,
        "childReceipts": {
            "preflight": preflight,
            "downloads": downloads,
            "pwaStatic": pwa_static,
            "mobileLedger": mobile_ledger,
            "readyMobileHandoff": ready_mobile_handoff,
            "participateIframeShell": participate_iframe_shell,
        },
    }
    if role_alias_routes is not None:
        result["roleAliasRouteStatus"] = role_alias_routes.get("status")
        result["roleAliasRouteContract"] = receipt_contract(role_alias_routes)
        result["roleAliasRouteResults"] = role_alias_route_result_rows
        result["roleAliasRouteDrift"] = role_alias_route_drift
    if downloads_status_browser:
        artifact = downloads_status_browser.get("artifact") if isinstance(downloads_status_browser.get("artifact"), dict) else {}
        result["downloadsStatusBrowserStatus"] = downloads_status_browser.get("status")
        result["downloadsStatusBrowserExitCode"] = downloads_status_browser.get("exitCode")
        result["downloadsStatusBrowserArtifactDir"] = downloads_status_browser.get("artifactDir")
        result["downloadsStatusBrowserArtifactContract"] = receipt_contract(artifact)
        result["downloadsStatusBrowserStatusRedirectHeading"] = artifact.get("status_redirect_heading")
        result["downloadsStatusBrowserStatusRedirectHeadingRecognized"] = artifact.get("status_redirect_heading_recognized")
        result["downloadsStatusBrowserStatusRedirectHeadingExpected"] = artifact.get("status_redirect_heading_expected")
        result["downloadsStatusBrowserStatusRedirectHeadingMatchesReleaseChannel"] = artifact.get("status_redirect_heading_matches_release_channel")
        result["downloadsStatusBrowserStatusRedirectHeadingUsesGenericUpdatedCopy"] = artifact.get("status_redirect_heading_uses_generic_updated_copy")
        result["childReceipts"]["downloadsStatusBrowser"] = downloads_status_browser
    if mobile_pwa_viewport:
        artifact = mobile_pwa_viewport.get("artifact") if isinstance(mobile_pwa_viewport.get("artifact"), dict) else {}
        result["mobilePwaViewportStatus"] = mobile_pwa_viewport.get("status")
        result["mobilePwaViewportExitCode"] = mobile_pwa_viewport.get("exitCode")
        result["mobilePwaViewportArtifactDir"] = mobile_pwa_viewport.get("artifactDir")
        result["mobilePwaViewportArtifactContract"] = receipt_contract(artifact)
        result["mobilePwaViewportRouteCount"] = artifact.get("route_count")
        result["mobilePwaViewportViewportCount"] = artifact.get("viewport_count")
        result["mobilePwaViewportRoutes"] = sorted(mobile_pwa_viewport_routes)
        result["mobilePwaViewportMissingRoutes"] = missing_mobile_pwa_viewport_routes
        result["childReceipts"]["mobilePwaViewport"] = mobile_pwa_viewport
    if frontdoor_navigation:
        mobile_artifact = frontdoor_navigation.get("mobileArtifact") if isinstance(frontdoor_navigation.get("mobileArtifact"), dict) else {}
        ledger_artifact = frontdoor_navigation.get("ledgerArtifact") if isinstance(frontdoor_navigation.get("ledgerArtifact"), dict) else {}
        anchor_artifact = frontdoor_navigation.get("anchorArtifact") if isinstance(frontdoor_navigation.get("anchorArtifact"), dict) else {}
        result["frontdoorNavigationStatus"] = frontdoor_navigation.get("status")
        result["frontdoorNavigationExitCode"] = frontdoor_navigation.get("exitCode")
        result["frontdoorNavigationArtifactDir"] = frontdoor_navigation.get("artifactDir")
        result["frontdoorNavigationMobileArtifactContract"] = receipt_contract(mobile_artifact)
        result["frontdoorNavigationLedgerArtifactContract"] = receipt_contract(ledger_artifact)
        result["frontdoorNavigationAnchorArtifactContract"] = receipt_contract(anchor_artifact)
        result["frontdoorNavigationGatedTargets"] = mobile_artifact.get("gated_targets")
        result["frontdoorNavigationPublicTargets"] = mobile_artifact.get("public_targets")
        result["frontdoorNavigationHomepageLaneText"] = mobile_artifact.get("homepage_lane_text")
        result["frontdoorNavigationHomepageLaneExpected"] = expected_frontdoor_homepage_lane_text
        result["frontdoorNavigationHomepageLaneMatchesReleaseChannel"] = frontdoor_homepage_lane_matches_release_channel
        result["frontdoorNavigationPlayRoute"] = mobile_artifact.get("play_route")
        result["frontdoorNavigationPlaySignInRoute"] = mobile_artifact.get("play_sign_in_route")
        result["frontdoorNavigationDirectPlayerRoute"] = mobile_artifact.get("direct_player_route")
        result["frontdoorNavigationDirectPlayerHttpStatus"] = mobile_artifact.get("direct_player_http_status")
        result["frontdoorNavigationFinalUrl"] = mobile_artifact.get("final_url")
        result["frontdoorNavigationLiveTurnCompanionShell"] = mobile_artifact.get("live_turn_companion_shell")
        result["frontdoorNavigationPwaManifestPath"] = mobile_artifact.get("pwa_manifest_path")
        result["frontdoorNavigationPwaRole"] = mobile_artifact.get("pwa_role")
        result["frontdoorNavigationBlazorShell"] = mobile_artifact.get("blazor_shell")
        result["frontdoorNavigationRybbitConfigured"] = mobile_artifact.get("rybbit_configured")
        result["frontdoorNavigationRybbitTag"] = mobile_artifact.get("rybbit_tag")
        result["frontdoorNavigationRybbitRoute"] = mobile_artifact.get("rybbit_route")
        result["frontdoorNavigationRybbitMode"] = mobile_artifact.get("rybbit_mode")
        result["frontdoorNavigationRybbitRole"] = mobile_artifact.get("rybbit_role")
        result["frontdoorNavigationRybbitSiteIdPresent"] = mobile_artifact.get("rybbit_site_id_present")
        result["frontdoorNavigationRybbitScriptUrlPresent"] = mobile_artifact.get("rybbit_script_url_present")
        result["frontdoorNavigationRybbitScriptUrlAllowed"] = mobile_artifact.get("rybbit_script_url_allowed")
        result["frontdoorNavigationRybbitSkipPatterns"] = mobile_artifact.get("rybbit_skip_patterns")
        result["frontdoorNavigationRybbitMaskPatterns"] = mobile_artifact.get("rybbit_mask_patterns")
        result["frontdoorNavigationRybbitSkipMobilePaths"] = mobile_artifact.get("rybbit_skip_mobile_paths")
        result["frontdoorNavigationRybbitMaskMobilePaths"] = mobile_artifact.get("rybbit_mask_mobile_paths")
        result["frontdoorNavigationRybbitMasksPrivatePlayRoutes"] = mobile_artifact.get("rybbit_masks_private_play_routes")
        result["frontdoorNavigationRybbitReplayBlockSelector"] = mobile_artifact.get("rybbit_replay_block_selector")
        result["frontdoorNavigationRybbitReplayBlocksTurnRoot"] = mobile_artifact.get("rybbit_replay_blocks_turn_root")
        result["frontdoorNavigationPlayerSessionHandoffUrl"] = mobile_artifact.get("player_session_handoff_url")
        result["frontdoorNavigationPlayerSessionHandoffStatus"] = mobile_artifact.get("player_session_handoff_status")
        result["frontdoorNavigationPlayerSessionHandoffLinkText"] = mobile_artifact.get("player_session_handoff_link_text")
        result["frontdoorNavigationPlayerSessionHandoffPreservesSession"] = mobile_artifact.get("player_session_handoff_preserves_session")
        result["frontdoorNavigationPlayerSessionHandoffPreservesRole"] = mobile_artifact.get("player_session_handoff_preserves_role")
        result["frontdoorNavigationPlayerSessionHandoffStripsDevice"] = mobile_artifact.get("player_session_handoff_strips_device")
        result["frontdoorNavigationPlayerSessionHandoffSenderDeviceIdPresent"] = mobile_artifact.get("player_session_handoff_sender_device_id_present")
        result["frontdoorNavigationGmRoute"] = mobile_artifact.get("gm_route")
        result["frontdoorNavigationGmHttpStatus"] = mobile_artifact.get("gm_http_status")
        result["frontdoorNavigationGmFinalUrl"] = mobile_artifact.get("gm_final_url")
        result["frontdoorNavigationGmLiveTurnCompanionShell"] = mobile_artifact.get("gm_live_turn_companion_shell")
        result["frontdoorNavigationGmPwaManifestPath"] = mobile_artifact.get("gm_pwa_manifest_path")
        result["frontdoorNavigationGmPwaRole"] = mobile_artifact.get("gm_pwa_role")
        result["frontdoorNavigationGmBlazorShell"] = mobile_artifact.get("gm_blazor_shell")
        result["frontdoorNavigationGmRybbitConfigured"] = mobile_artifact.get("gm_rybbit_configured")
        result["frontdoorNavigationGmRybbitTag"] = mobile_artifact.get("gm_rybbit_tag")
        result["frontdoorNavigationGmRybbitRoute"] = mobile_artifact.get("gm_rybbit_route")
        result["frontdoorNavigationGmRybbitMode"] = mobile_artifact.get("gm_rybbit_mode")
        result["frontdoorNavigationGmRybbitRole"] = mobile_artifact.get("gm_rybbit_role")
        result["frontdoorNavigationGmRybbitSiteIdPresent"] = mobile_artifact.get("gm_rybbit_site_id_present")
        result["frontdoorNavigationGmRybbitScriptUrlPresent"] = mobile_artifact.get("gm_rybbit_script_url_present")
        result["frontdoorNavigationGmRybbitScriptUrlAllowed"] = mobile_artifact.get("gm_rybbit_script_url_allowed")
        result["frontdoorNavigationGmRybbitSkipPatterns"] = mobile_artifact.get("gm_rybbit_skip_patterns")
        result["frontdoorNavigationGmRybbitMaskPatterns"] = mobile_artifact.get("gm_rybbit_mask_patterns")
        result["frontdoorNavigationGmRybbitSkipMobilePaths"] = mobile_artifact.get("gm_rybbit_skip_mobile_paths")
        result["frontdoorNavigationGmRybbitMaskMobilePaths"] = mobile_artifact.get("gm_rybbit_mask_mobile_paths")
        result["frontdoorNavigationGmRybbitMasksPrivatePlayRoutes"] = mobile_artifact.get("gm_rybbit_masks_private_play_routes")
        result["frontdoorNavigationGmRybbitReplayBlockSelector"] = mobile_artifact.get("gm_rybbit_replay_block_selector")
        result["frontdoorNavigationGmRybbitReplayBlocksTurnRoot"] = mobile_artifact.get("gm_rybbit_replay_blocks_turn_root")
        result["frontdoorNavigationGmSessionHandoffUrl"] = mobile_artifact.get("gm_session_handoff_url")
        result["frontdoorNavigationGmSessionHandoffStatus"] = mobile_artifact.get("gm_session_handoff_status")
        result["frontdoorNavigationGmSessionHandoffLinkText"] = mobile_artifact.get("gm_session_handoff_link_text")
        result["frontdoorNavigationGmSessionHandoffPreservesSession"] = mobile_artifact.get("gm_session_handoff_preserves_session")
        result["frontdoorNavigationGmSessionHandoffPreservesRole"] = mobile_artifact.get("gm_session_handoff_preserves_role")
        result["frontdoorNavigationGmSessionHandoffStripsDevice"] = mobile_artifact.get("gm_session_handoff_strips_device")
        result["frontdoorNavigationGmSessionHandoffSenderDeviceIdPresent"] = mobile_artifact.get("gm_session_handoff_sender_device_id_present")
        result["frontdoorNavigationLedgerPrimary"] = ledger_artifact.get("ledger_primary")
        result["frontdoorNavigationAnchorEntryUrl"] = anchor_artifact.get("entry_url")
        result["frontdoorNavigationAnchorFinalUrl"] = anchor_artifact.get("final_url")
        result["frontdoorNavigationAnchorFinalPath"] = anchor_artifact.get("final_pathname")
        result["frontdoorNavigationAnchorFinalHash"] = anchor_artifact.get("final_hash")
        result["frontdoorNavigationAnchorPwaManifestPath"] = anchor_artifact.get("pwa_manifest_path")
        result["frontdoorNavigationAnchorPwaRole"] = anchor_artifact.get("pwa_role")
        result["frontdoorNavigationAnchorBlazorShell"] = anchor_artifact.get("blazor_shell")
        result["frontdoorNavigationAnchorSessionIdPresent"] = anchor_artifact.get("session_id_present")
        result["frontdoorNavigationAnchorDeviceIdPresent"] = anchor_artifact.get("device_id_present")
        result["frontdoorNavigationAnchorFailure"] = anchor_artifact.get("failure")
        result["frontdoorNavigationAnchorArtifactCurrentContractSatisfied"] = frontdoor_anchor_current_contract_satisfied
        result["childReceipts"]["frontdoorNavigation"] = frontdoor_navigation
    if pwa_offline_cache:
        artifact = pwa_offline_cache.get("artifact") if isinstance(pwa_offline_cache.get("artifact"), dict) else {}
        result["pwaOfflineCacheStatus"] = pwa_offline_cache.get("status")
        result["pwaOfflineCacheExitCode"] = pwa_offline_cache.get("exitCode")
        result["pwaOfflineCacheArtifactDir"] = pwa_offline_cache.get("artifactDir")
        result["pwaOfflineCacheArtifactContract"] = receipt_contract(artifact)
        result["pwaOfflineCacheOfflineReload"] = artifact.get("offline_reload")
        result["pwaOfflineCacheCachedPaths"] = artifact.get("cached_paths")
        result["pwaOfflineCacheOfflineRoleRoutes"] = artifact.get("offline_role_routes")
        result["pwaOfflineCachePersonalizedLedgerCached"] = artifact.get("personalized_ledger_cached")
        result["childReceipts"]["pwaOfflineCache"] = pwa_offline_cache
    return result


def run_downloads_status_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "DOWNLOADS_STATUS_E2E.generated.json"
    expected_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["downloadsStatusBrowser"]
    playwright_timeout_seconds = max(120, int(timeout_seconds) + 60)
    if reuse_existing_artifact:
        reused = maybe_reuse_playwright_artifact(
            artifact_path=artifact_path,
            expected_contract=expected_contract,
            base_url=base_url,
            timeout_seconds=playwright_timeout_seconds,
            reuse_artifact_max_age_hours=reuse_artifact_max_age_hours,
        )
        if reused is not None:
            reused["artifactDir"] = str(artifact_dir)
            return reused

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    command = [
        "npx",
        "playwright",
        "test",
        "tests/public/downloads-status.spec.ts",
        "--workers=1",
        "--reporter=line",
    ]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    artifact: dict[str, Any] = {}
    if artifact_path.exists():
        artifact = load_json(artifact_path)
    artifact_contract = receipt_contract(artifact)
    artifact_pass = artifact.get("status") == "pass" and artifact_contract == expected_contract
    return {
        "status": "pass" if exit_code == 0 and artifact_pass else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "artifactPath": str(artifact_path),
        "artifactContract": artifact_contract,
        "expectedArtifactContract": expected_contract,
        "artifact": artifact,
        "artifactBaseUrlMatchesRequested": artifact_base_url_matches(artifact, base_url),
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def run_mobile_pwa_viewport_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "MOBILE_PWA_VIEWPORT_SMOKE.generated.json"
    expected_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["mobilePwaViewport"]
    playwright_timeout_seconds = max(300, int(timeout_seconds) + 180)
    if reuse_existing_artifact:
        reused = maybe_reuse_playwright_artifact(
            artifact_path=artifact_path,
            expected_contract=expected_contract,
            base_url=base_url,
            timeout_seconds=playwright_timeout_seconds,
            reuse_artifact_max_age_hours=reuse_artifact_max_age_hours,
        )
        if reused is not None:
            reused["artifactDir"] = str(artifact_dir)
            return reused

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    command = [
        "npx",
        "playwright",
        "test",
        "tests/public/mobile-pwa-viewport-smoke.spec.ts",
        "--workers=1",
        "--reporter=line",
    ]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    artifact: dict[str, Any] = {}
    if artifact_path.exists():
        artifact = load_json(artifact_path)
    artifact_contract = receipt_contract(artifact)
    artifact_pass = artifact.get("status") == "pass" and artifact_contract == expected_contract
    return {
        "status": "pass" if exit_code == 0 and artifact_pass else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "artifactPath": str(artifact_path),
        "artifactContract": artifact_contract,
        "expectedArtifactContract": expected_contract,
        "artifact": artifact,
        "artifactBaseUrlMatchesRequested": artifact_base_url_matches(artifact, base_url),
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def run_pwa_offline_cache_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "PWA_OFFLINE_CACHE.generated.json"
    expected_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["pwaOfflineCache"]
    playwright_timeout_seconds = max(180, int(timeout_seconds) + 120)
    if reuse_existing_artifact:
        reused = maybe_reuse_playwright_artifact(
            artifact_path=artifact_path,
            expected_contract=expected_contract,
            base_url=base_url,
            timeout_seconds=playwright_timeout_seconds,
            reuse_artifact_max_age_hours=reuse_artifact_max_age_hours,
        )
        if reused is not None:
            reused["artifactDir"] = str(artifact_dir)
            return reused

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    command = [
        "npx",
        "playwright",
        "test",
        "tests/public/pwa-offline-cache.spec.ts",
        "--workers=1",
        "--reporter=line",
    ]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    artifact: dict[str, Any] = {}
    if artifact_path.exists():
        artifact = load_json(artifact_path)
    contract = receipt_contract(artifact)
    contract_ok = contract == expected_contract
    return {
        "status": "pass" if exit_code == 0 and artifact.get("status") == "pass" and contract_ok else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "artifactPath": str(artifact_path),
        "artifactContract": contract,
        "expectedArtifactContract": expected_contract,
        "artifact": artifact,
        "artifactBaseUrlMatchesRequested": artifact_base_url_matches(artifact, base_url),
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def run_frontdoor_navigation_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    mobile_artifact_path = artifact_dir / "FRONTDOOR_MOBILE_LAUNCH.generated.json"
    ledger_artifact_path = artifact_dir / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json"
    anchor_artifact_path = artifact_dir / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json"
    expected_mobile_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationMobile"]
    expected_ledger_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationLedger"]
    expected_anchor_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationAnchor"]
    playwright_timeout_seconds = max(180, int(timeout_seconds) + 120)
    if reuse_existing_artifact and mobile_artifact_path.is_file() and ledger_artifact_path.is_file() and anchor_artifact_path.is_file():
        mobile_artifact = load_json(mobile_artifact_path)
        ledger_artifact = load_json(ledger_artifact_path)
        anchor_artifact = load_json(anchor_artifact_path)
        mobile_contract = receipt_contract(mobile_artifact)
        ledger_contract = receipt_contract(ledger_artifact)
        anchor_contract = receipt_contract(anchor_artifact)
        mobile_generated_at = artifact_generated_at_text(mobile_artifact)
        ledger_generated_at = artifact_generated_at_text(ledger_artifact)
        anchor_generated_at = artifact_generated_at_text(anchor_artifact)
        mobile_age_hours = artifact_age_hours(mobile_artifact)
        ledger_age_hours = artifact_age_hours(ledger_artifact)
        anchor_age_hours = artifact_age_hours(anchor_artifact)
        anchor_current_contract = frontdoor_anchor_artifact_matches_current_contract(anchor_artifact)
        mobile_fresh = (
            True
            if reuse_artifact_max_age_hours is None
            else mobile_age_hours is not None and mobile_age_hours <= reuse_artifact_max_age_hours
        )
        ledger_fresh = (
            True
            if reuse_artifact_max_age_hours is None
            else ledger_age_hours is not None and ledger_age_hours <= reuse_artifact_max_age_hours
        )
        anchor_fresh = (
            True
            if reuse_artifact_max_age_hours is None
            else anchor_age_hours is not None and anchor_age_hours <= reuse_artifact_max_age_hours
        )
        mobile_pass = (
            str(mobile_artifact.get("status") or "").strip().lower() == "pass"
            and mobile_contract == expected_mobile_contract
            and artifact_base_url_matches(mobile_artifact, base_url)
            and mobile_fresh
        )
        ledger_pass = (
            str(ledger_artifact.get("status") or "").strip().lower() == "pass"
            and ledger_contract == expected_ledger_contract
            and artifact_base_url_matches(ledger_artifact, base_url)
            and ledger_fresh
        )
        anchor_pass = (
            str(anchor_artifact.get("status") or "").strip().lower() == "pass"
            and anchor_contract == expected_anchor_contract
            and artifact_base_url_matches(anchor_artifact, base_url)
            and anchor_fresh
            and anchor_current_contract
        )
        if mobile_pass and ledger_pass and anchor_pass:
            return {
                "status": "pass",
                "exitCode": 0,
                "timedOut": False,
                "timeoutSeconds": playwright_timeout_seconds,
                "artifactDir": str(artifact_dir),
                "mobileArtifactPath": str(mobile_artifact_path),
                "ledgerArtifactPath": str(ledger_artifact_path),
                "anchorArtifactPath": str(anchor_artifact_path),
                "mobileArtifactContract": mobile_contract,
                "expectedMobileArtifactContract": expected_mobile_contract,
                "ledgerArtifactContract": ledger_contract,
                "expectedLedgerArtifactContract": expected_ledger_contract,
                "anchorArtifactContract": anchor_contract,
                "expectedAnchorArtifactContract": expected_anchor_contract,
                "mobileArtifact": mobile_artifact,
                "ledgerArtifact": ledger_artifact,
                "anchorArtifact": anchor_artifact,
                "mobileArtifactBaseUrlMatchesRequested": artifact_base_url_matches(mobile_artifact, base_url),
                "ledgerArtifactBaseUrlMatchesRequested": artifact_base_url_matches(ledger_artifact, base_url),
                "anchorArtifactBaseUrlMatchesRequested": artifact_base_url_matches(anchor_artifact, base_url),
                "mobileArtifactGeneratedAtUtc": mobile_generated_at or None,
                "ledgerArtifactGeneratedAtUtc": ledger_generated_at or None,
                "anchorArtifactGeneratedAtUtc": anchor_generated_at or None,
                "mobileArtifactAgeHours": mobile_age_hours,
                "ledgerArtifactAgeHours": ledger_age_hours,
                "anchorArtifactAgeHours": anchor_age_hours,
                "mobileArtifactFresh": mobile_fresh,
                "ledgerArtifactFresh": ledger_fresh,
                "anchorArtifactFresh": anchor_fresh,
                "anchorArtifactCurrentContractSatisfied": anchor_current_contract,
                "artifactMaxAgeHours": reuse_artifact_max_age_hours,
                "artifactReused": True,
                "playwrightExecuted": False,
                "stdoutTail": "",
                "stderrTail": "",
            }

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    for artifact_path in (mobile_artifact_path, ledger_artifact_path, anchor_artifact_path):
        try:
            artifact_path.unlink()
        except FileNotFoundError:
            pass
    probe_path = artifact_dir / "frontdoor-navigation-proof.cjs"
    probe_path.write_text(
        r"""const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(path.join(process.cwd(), 'node_modules', 'playwright'));

const baseUrl = (process.env.BASE_URL || 'https://chummer.run').replace(/\/+$/, '');
const artifactDir = process.env.CHUMMER_COMPLETION_DIR || process.cwd();
const mobileViewport = { width: 390, height: 844 };
const proofTimeoutMs = """
        + str(int(playwright_timeout_seconds * 1000))
        + r""";
const ignoredConsoleErrorFragments = [
  'Failed to load resource: net::ERR_NETWORK_CHANGED',
  'Failed to load resource: the server responded with a status of 401',
  'Failed to send tracking data: TypeError: Failed to fetch',
  'WebSocket closed with status code: 1006',
];

function writeJson(fileName, payload) {
  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(path.join(artifactDir, fileName), `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function assertProof(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function firstAttributeOrNull(locator, name) {
  try {
    return await locator.first().getAttribute(name);
  } catch {
    return null;
  }
}

async function assertContains(locator, text, label) {
  const content = (await locator.textContent()) || '';
  assertProof(content.includes(text), `${label} does not contain ${text}`);
}

function jsonStringArray(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  const raw = String(value || '').trim();
  if (!raw) {
    return [];
  }
  try {
    const decoded = JSON.parse(raw);
    if (Array.isArray(decoded)) {
      return decoded.map((item) => String(item).trim()).filter(Boolean);
    }
  } catch {
  }
  return [raw];
}

function analyticsProof(config, spec) {
  const skipPatterns = new Set(jsonStringArray(config.skipPatterns));
  const maskPatterns = new Set(jsonStringArray(config.maskPatterns));
  const scriptUrl = String(config.scriptUrl || '').trim();
  const siteId = String(config.siteId || '').trim();
  const proof = {
    enabled: config.enabled === true,
    script_url_present: Boolean(scriptUrl),
    script_url_allowed: scriptUrl.startsWith('https://') || scriptUrl.startsWith('/'),
    site_id_present: Boolean(siteId),
    tag: config.tag || '',
    route: config.route || '',
    mode: config.mode || '',
    role: config.role || '',
    skip_patterns: Array.from(skipPatterns).sort(),
    mask_patterns: Array.from(maskPatterns).sort(),
    replay_block_selector: config.replayBlockSelector || '',
    skip_mobile_paths: skipPatterns.has('/mobile/**'),
    mask_mobile_paths: maskPatterns.has('/mobile/**'),
    masks_private_play_routes: maskPatterns.has('/api/play/**'),
    replay_blocks_turn_root: config.replayBlockSelector === '[data-turn-root]',
  };
  proof.pass = proof.enabled
    && proof.script_url_present
    && proof.script_url_allowed
    && proof.site_id_present
    && proof.tag === 'mobile_play_shell'
    && proof.route === spec.route
    && proof.mode === spec.mode
    && proof.role === spec.role
    && proof.skip_mobile_paths
    && proof.mask_mobile_paths
    && proof.masks_private_play_routes
    && proof.replay_blocks_turn_root;
  return proof;
}

async function main() {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: mobileViewport });
    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    page.on('console', (message) => {
      if (message.type() !== 'error') {
        return;
      }
      const text = message.text();
      if (!ignoredConsoleErrorFragments.some((fragment) => text.includes(fragment))) {
        pageErrors.push(text);
      }
    });

    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const homepageMetrics = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      overflowX: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth,
    }));

    const hero = page.locator('[data-homepage-section="hero"]');
    await assertContains(hero, 'Download Chummer', 'hero');
    const heroText = ((await hero.innerText()) || '').replace(/\s+/g, ' ').trim();
    const homepageLaneMatch = heroText.match(/Current public lane:\s*(Stable\.|Preview\. Review required\.|Downloads paused\.)/);
    const homepageLaneText = homepageLaneMatch ? `Current public lane: ${homepageLaneMatch[1]}` : '';
    const legacyHomepageLaneMatch = heroText.match(/Current release:\s*(Stable\.|Preview build\.|Downloads paused\.)/);
    const legacyHomepageLaneText = legacyHomepageLaneMatch ? `Current release: ${legacyHomepageLaneMatch[1]}` : '';
    assertProof(
      Boolean(homepageLaneText),
      legacyHomepageLaneText
        ? `Homepage still serves legacy release posture copy: ${legacyHomepageLaneText}`
        : 'Homepage does not disclose current public lane'
    );
    const openMenu = hero.locator('.minimal-open-chummer');
    await assertContains(openMenu.locator('summary'), 'Open Chummer', 'open menu summary');
    await openMenu.locator('summary').click();

    const buildButton = openMenu.locator('button.site-open-chummer-menu__button[data-disabled-target="/build"]', { hasText: 'Build' }).first();
    assertProof(await buildButton.count() === 1, 'Build button is missing');
    assertProof(await buildButton.isDisabled(), 'Build button is not gated');
    const playButton = openMenu.locator('button.site-open-chummer-menu__button[data-disabled-target="/mobile/player"]', { hasText: 'Play' }).first();
    assertProof(await playButton.count() === 1, 'Play button is missing');
    assertProof(await playButton.isDisabled(), 'Play button is not gated');
    const accountLink = openMenu.getByRole('link', { name: 'Sign in first' }).first();
    assertProof(await accountLink.count() === 1, 'Sign-in link is missing');
    assertProof(await openMenu.locator('.site-open-chummer-menu__button[href="/build"]').count() === 0, 'Build is exposed as a public link');
    assertProof(await openMenu.locator('.site-open-chummer-menu__button[href="/mobile/player"]').count() === 0, 'Play is exposed as a public link');
    assertProof(await openMenu.locator('.site-open-chummer-menu__button[href="/play"]').count() === 0, 'Legacy /play link is exposed');

    const accountRoute = await accountLink.getAttribute('href');
    const playRoute = await playButton.getAttribute('data-disabled-target');
    const playSignInRoute = await playButton.getAttribute('data-sign-in-href');
    const directPlayerRoute = playRoute;
    assertProof(playRoute === '/mobile/player', 'Play route is not /mobile/player');
    assertProof(playSignInRoute === '/login?next=%2Fmobile%2Fplayer', 'Play sign-in route is not /login?next=%2Fmobile%2Fplayer');
    assertProof(directPlayerRoute === '/mobile/player', 'Play direct route is not /mobile/player');
    const directPlayerResponse = await page.request.get(new URL(directPlayerRoute || '/mobile/player', baseUrl).toString());
    await page.goto(new URL(directPlayerRoute || '/mobile/player', baseUrl).toString(), { waitUntil: 'domcontentloaded' });
    const playerShell = page.locator('[data-blazor-shell="interactive-server"][data-role="Player"]').first();
    assertProof(await playerShell.count() === 1, 'Play did not open the interactive Player shell');
    const pwaManifestPath = await page.locator('link[rel="manifest"]').first().getAttribute('href');
    const directPlayerTitle = await page.title();
    const pwaRole = await playerShell.getAttribute('data-role');
    const blazorShell = await playerShell.getAttribute('data-blazor-shell');
    const analyticsConfig = await page.locator('#chummer-play-analytics-config').first().textContent();
    const analytics = analyticsConfig ? JSON.parse(analyticsConfig) : {};
    const playerAnalyticsProof = analyticsProof(analytics, { route: '/mobile/player', mode: 'player', role: 'Player' });
    const finalUrl = page.url();
    const playerFinalUrl = new URL(finalUrl);
    const playerSessionId = playerFinalUrl.searchParams.get('sessionId') || '';
    const playerDeviceId = playerFinalUrl.searchParams.get('deviceId') || '';
    assertProof(pageErrors.length === 0, `Unexpected page errors: ${pageErrors.join('; ')}`);
    assertProof(directPlayerResponse && directPlayerResponse.status() === 200, 'Play did not return HTTP 200');
    assertProof(new URL(finalUrl).pathname === '/mobile/player', 'Play did not land on /mobile/player');
    assertProof(pwaManifestPath === '/manifest.player.webmanifest', 'Player PWA manifest is not active');
    assertProof(pwaRole === 'Player', 'Player shell role marker is missing');
    assertProof(blazorShell === 'interactive-server', 'Blazor interactive shell marker is missing');
    assertProof(playerAnalyticsProof.pass, 'Rybbit Player mobile shell privacy config is missing');
    await page.evaluate(() => {
      try {
        Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
      } catch {
      }
    });
    await page.locator('#turn-share-owner-route-button').click();
    await page.waitForFunction(() => {
      const link = document.getElementById('turn-owner-route-link');
      const status = document.getElementById('turn-owner-route-share-status')?.textContent || '';
      return status.trim() === 'Session handoff is ready in the link above.'
        && Boolean(link?.getAttribute('href'));
    }, null, { timeout: 30000 });
    const playerHandoff = await page.evaluate(() => {
      const link = document.getElementById('turn-owner-route-link');
      return {
        href: link ? new URL(link.getAttribute('href') || '', window.location.origin).toString() : '',
        text: link ? (link.textContent || '').trim() : '',
        status: (document.getElementById('turn-owner-route-share-status')?.textContent || '').trim(),
      };
    });
    assertProof(Boolean(playerHandoff.href), 'Player session handoff did not expose a URL');
    const playerHandoffUrl = new URL(playerHandoff.href);
    assertProof(playerHandoffUrl.pathname === '/mobile/player', 'Player session handoff did not stay on /mobile/player');
    assertProof(playerHandoffUrl.searchParams.get('sessionId') === playerSessionId, 'Player session handoff did not preserve session id');
    assertProof(playerHandoffUrl.searchParams.get('role') === 'Player', 'Player session handoff did not preserve role');
    assertProof(!playerHandoffUrl.searchParams.has('deviceId'), 'Player session handoff leaked sender device id');
    assertProof(playerHandoff.text === 'Open session handoff link', 'Player session handoff did not expose the handoff link label');
    const gmLink = page.locator('a.role-button[href^="/mobile/gm"]').first();
    assertProof(await gmLink.count() === 1, 'GM role switch is missing from the Player shell');
    const gmRoute = await gmLink.getAttribute('href');
    const gmRouteResponse = await page.request.get(new URL(gmRoute || '/mobile/gm', baseUrl).toString());
    await Promise.all([
      page.waitForURL('**/mobile/gm**', { timeout: proofTimeoutMs }),
      gmLink.click({ noWaitAfter: true }),
    ]);
    const gmShell = page.locator('[data-blazor-shell="interactive-server"][data-role="GameMaster"]').first();
    assertProof(await gmShell.count() === 1, 'GM switch did not open the interactive GM shell');
    const gmPwaManifestPath = await page.locator('link[rel="manifest"]').first().getAttribute('href');
    const gmRole = await gmShell.getAttribute('data-role');
    const gmBlazorShell = await gmShell.getAttribute('data-blazor-shell');
    const gmAnalyticsConfig = await page.locator('#chummer-play-analytics-config').first().textContent();
    const gmAnalytics = gmAnalyticsConfig ? JSON.parse(gmAnalyticsConfig) : {};
    const gmAnalyticsProof = analyticsProof(gmAnalytics, { route: '/mobile/gm', mode: 'gm', role: 'GameMaster' });
    const gmFinalUrl = page.url();
    const gmFinalUrlParsed = new URL(gmFinalUrl);
    const gmSessionId = gmFinalUrlParsed.searchParams.get('sessionId') || '';
    const gmDeviceId = gmFinalUrlParsed.searchParams.get('deviceId') || '';
    assertProof(gmRouteResponse.status() === 200, 'GM switch did not return HTTP 200');
    assertProof(new URL(gmFinalUrl).pathname === '/mobile/gm', 'GM switch did not land on /mobile/gm');
    assertProof(gmPwaManifestPath === '/manifest.gm.webmanifest', 'GM PWA manifest is not active');
    assertProof(gmRole === 'GameMaster', 'GM shell role marker is missing');
    assertProof(gmBlazorShell === 'interactive-server', 'GM Blazor interactive shell marker is missing');
    assertProof(gmAnalyticsProof.pass, 'Rybbit GM mobile shell privacy config is missing');
    await page.locator('#turn-share-owner-route-button').click();
    await page.waitForFunction(() => {
      const link = document.getElementById('turn-owner-route-link');
      const status = document.getElementById('turn-owner-route-share-status')?.textContent || '';
      return status.trim() === 'Session handoff is ready in the link above.'
        && Boolean(link?.getAttribute('href'));
    }, null, { timeout: 30000 });
    const gmHandoff = await page.evaluate(() => {
      const link = document.getElementById('turn-owner-route-link');
      return {
        href: link ? new URL(link.getAttribute('href') || '', window.location.origin).toString() : '',
        text: link ? (link.textContent || '').trim() : '',
        status: (document.getElementById('turn-owner-route-share-status')?.textContent || '').trim(),
      };
    });
    assertProof(Boolean(gmHandoff.href), 'GM session handoff did not expose a URL');
    const gmHandoffUrl = new URL(gmHandoff.href);
    assertProof(gmHandoffUrl.pathname === '/mobile/gm', 'GM session handoff did not stay on /mobile/gm');
    assertProof(gmHandoffUrl.searchParams.get('sessionId') === gmSessionId, 'GM session handoff did not preserve session id');
    assertProof(gmHandoffUrl.searchParams.get('role') === 'GameMaster', 'GM session handoff did not preserve role');
    assertProof(!gmHandoffUrl.searchParams.has('deviceId'), 'GM session handoff leaked sender device id');
    assertProof(gmHandoff.text === 'Open session handoff link', 'GM session handoff did not expose the handoff link label');

    writeJson('FRONTDOOR_MOBILE_LAUNCH.generated.json', {
      contractName: 'chummer.frontdoor_mobile_launch.v1',
      generated_at_utc: new Date().toISOString(),
      status: 'pass',
      base_url: baseUrl,
      viewport: mobileViewport,
      homepage_overflow_x: homepageMetrics.overflowX,
      homepage_lane_text: homepageLaneText,
      account_route: accountRoute,
      play_route: playRoute,
      play_sign_in_route: playSignInRoute,
      direct_player_route: directPlayerRoute,
      direct_player_http_status: directPlayerResponse ? directPlayerResponse.status() : 0,
      direct_player_title: directPlayerTitle,
      final_url: finalUrl,
      pwa_role: pwaRole,
      blazor_shell: blazorShell,
      live_turn_companion_shell: true,
      pwa_manifest: pwaManifestPath,
      pwa_manifest_path: pwaManifestPath,
      rybbit_configured: playerAnalyticsProof.pass,
      rybbit_tag: playerAnalyticsProof.tag || '',
      rybbit_route: playerAnalyticsProof.route || '',
      rybbit_mode: playerAnalyticsProof.mode || '',
      rybbit_role: playerAnalyticsProof.role || '',
      rybbit_site_id_present: playerAnalyticsProof.site_id_present,
      rybbit_script_url_present: playerAnalyticsProof.script_url_present,
      rybbit_script_url_allowed: playerAnalyticsProof.script_url_allowed,
      rybbit_skip_patterns: playerAnalyticsProof.skip_patterns,
      rybbit_mask_patterns: playerAnalyticsProof.mask_patterns,
      rybbit_skip_mobile_paths: playerAnalyticsProof.skip_mobile_paths,
      rybbit_mask_mobile_paths: playerAnalyticsProof.mask_mobile_paths,
      rybbit_masks_private_play_routes: playerAnalyticsProof.masks_private_play_routes,
      rybbit_replay_block_selector: playerAnalyticsProof.replay_block_selector,
      rybbit_replay_blocks_turn_root: playerAnalyticsProof.replay_blocks_turn_root,
      player_session_handoff_url: playerHandoffUrl.toString(),
      player_session_handoff_status: playerHandoff.status,
      player_session_handoff_link_text: playerHandoff.text,
      player_session_handoff_preserves_session: playerHandoffUrl.searchParams.get('sessionId') === playerSessionId,
      player_session_handoff_preserves_role: playerHandoffUrl.searchParams.get('role') === 'Player',
      player_session_handoff_strips_device: !playerHandoffUrl.searchParams.has('deviceId'),
      player_session_handoff_sender_device_id_present: Boolean(playerDeviceId),
      gm_route: gmRoute,
      gm_http_status: gmRouteResponse.status(),
      gm_final_url: gmFinalUrl,
      gm_live_turn_companion_shell: true,
      gm_pwa_manifest_path: gmPwaManifestPath,
      gm_pwa_role: gmRole,
      gm_blazor_shell: gmBlazorShell,
      gm_rybbit_configured: gmAnalyticsProof.pass,
      gm_rybbit_tag: gmAnalyticsProof.tag || '',
      gm_rybbit_route: gmAnalyticsProof.route || '',
      gm_rybbit_mode: gmAnalyticsProof.mode || '',
      gm_rybbit_role: gmAnalyticsProof.role || '',
      gm_rybbit_site_id_present: gmAnalyticsProof.site_id_present,
      gm_rybbit_script_url_present: gmAnalyticsProof.script_url_present,
      gm_rybbit_script_url_allowed: gmAnalyticsProof.script_url_allowed,
      gm_rybbit_skip_patterns: gmAnalyticsProof.skip_patterns,
      gm_rybbit_mask_patterns: gmAnalyticsProof.mask_patterns,
      gm_rybbit_skip_mobile_paths: gmAnalyticsProof.skip_mobile_paths,
      gm_rybbit_mask_mobile_paths: gmAnalyticsProof.mask_mobile_paths,
      gm_rybbit_masks_private_play_routes: gmAnalyticsProof.masks_private_play_routes,
      gm_rybbit_replay_block_selector: gmAnalyticsProof.replay_block_selector,
      gm_rybbit_replay_blocks_turn_root: gmAnalyticsProof.replay_blocks_turn_root,
      gm_session_handoff_url: gmHandoffUrl.toString(),
      gm_session_handoff_status: gmHandoff.status,
      gm_session_handoff_link_text: gmHandoff.text,
      gm_session_handoff_preserves_session: gmHandoffUrl.searchParams.get('sessionId') === gmSessionId,
      gm_session_handoff_preserves_role: gmHandoffUrl.searchParams.get('role') === 'GameMaster',
      gm_session_handoff_strips_device: !gmHandoffUrl.searchParams.has('deviceId'),
      gm_session_handoff_sender_device_id_present: Boolean(gmDeviceId),
      gated_targets: ['Build', 'Play'],
      public_targets: [],
      page_errors: pageErrors,
    });

    await page.close({ runBeforeUnload: false }).catch(() => undefined);

    const anchorPage = await browser.newPage({ viewport: mobileViewport });
    const anchorPageErrors = [];
    anchorPage.on('pageerror', (error) => anchorPageErrors.push(error.message));
    anchorPage.on('console', (message) => {
      if (message.type() !== 'error') {
        return;
      }
      const text = message.text();
      if (!ignoredConsoleErrorFragments.some((fragment) => text.includes(fragment))) {
        anchorPageErrors.push(text);
      }
    });

    const anchorEntryUrl = new URL('/#turn-runsite-card', baseUrl).toString();
    let anchorStatus = 'fail';
    let anchorFailure = '';
    let anchorFinalUrlText = anchorEntryUrl;
    let anchorFinalPath = '';
    let anchorFinalHash = '';
    let anchorManifestPath = null;
    let anchorRole = null;
    let anchorBlazorShell = null;
    let anchorSessionIdPresent = false;
    let anchorDeviceIdPresent = false;
    try {
      await anchorPage.goto(anchorEntryUrl, { waitUntil: 'domcontentloaded' });
      await anchorPage.waitForFunction(() => {
        const currentUrl = new URL(window.location.href);
        return currentUrl.pathname === '/mobile/player'
          && currentUrl.hash === '#turn-runsite-card';
      }, null, { timeout: proofTimeoutMs });
      const anchorFinalUrl = new URL(anchorPage.url());
      anchorFinalUrlText = anchorPage.url();
      anchorFinalPath = anchorFinalUrl.pathname;
      anchorFinalHash = anchorFinalUrl.hash;
      const anchorPlayerShell = anchorPage.locator('[data-blazor-shell="interactive-server"][data-role="Player"]').first();
      assertProof(await anchorPlayerShell.count() === 1, 'Homepage anchor redirect did not open the interactive Player shell');
      anchorManifestPath = await firstAttributeOrNull(anchorPage.locator('link[rel="manifest"]'), 'href');
      anchorRole = await anchorPlayerShell.getAttribute('data-role');
      anchorBlazorShell = await anchorPlayerShell.getAttribute('data-blazor-shell');
      const anchorSessionId = anchorFinalUrl.searchParams.get('sessionId') || '';
      const anchorDeviceId = anchorFinalUrl.searchParams.get('deviceId') || '';
      anchorSessionIdPresent = Boolean(anchorSessionId);
      anchorDeviceIdPresent = Boolean(anchorDeviceId);
      assertProof(anchorFinalPath === '/mobile/player', 'Homepage anchor redirect did not land on /mobile/player');
      assertProof(anchorFinalHash === '#turn-runsite-card', 'Homepage anchor redirect did not preserve #turn-runsite-card');
      assertProof(anchorManifestPath === '/manifest.player.webmanifest', 'Homepage anchor redirect did not activate the player PWA manifest');
      assertProof(anchorRole === 'Player', 'Homepage anchor redirect did not prove the Player role');
      assertProof(anchorBlazorShell === 'interactive-server', 'Homepage anchor redirect did not prove the interactive Blazor shell');
      anchorStatus = 'pass';
    } catch (error) {
      anchorFailure = error && error.message ? error.message : String(error);
      anchorFinalUrlText = anchorPage.url();
      try {
        const anchorObservedUrl = new URL(anchorFinalUrlText);
        anchorFinalPath = anchorObservedUrl.pathname;
        anchorFinalHash = anchorObservedUrl.hash;
        anchorSessionIdPresent = Boolean(anchorObservedUrl.searchParams.get('sessionId'));
        anchorDeviceIdPresent = Boolean(anchorObservedUrl.searchParams.get('deviceId'));
      } catch {
      }
      anchorManifestPath = await firstAttributeOrNull(anchorPage.locator('link[rel="manifest"]'), 'href');
      const anchorPlayerShell = anchorPage.locator('[data-blazor-shell="interactive-server"][data-role="Player"]').first();
      if (await anchorPlayerShell.count() === 1) {
        anchorRole = await anchorPlayerShell.getAttribute('data-role');
        anchorBlazorShell = await anchorPlayerShell.getAttribute('data-blazor-shell');
      }
    }

    writeJson('FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json', {
      contractName: 'chummer.frontdoor_mobile_anchor_redirect.v1',
      generated_at_utc: new Date().toISOString(),
      status: anchorStatus,
      base_url: baseUrl,
      entry_url: anchorEntryUrl,
      final_url: anchorFinalUrlText,
      final_pathname: anchorFinalPath,
      final_hash: anchorFinalHash,
      pwa_manifest_path: anchorManifestPath,
      pwa_role: anchorRole,
      blazor_shell: anchorBlazorShell,
      session_id_present: anchorSessionIdPresent,
      device_id_present: anchorDeviceIdPresent,
      failure: anchorFailure,
      page_errors: anchorPageErrors,
    });
    await anchorPage.close({ runBeforeUnload: false }).catch(() => undefined);

    const ledgerPage = await browser.newPage();
    await ledgerPage.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const ledgerHero = ledgerPage.locator('[data-homepage-section="hero"]');
    await assertContains(ledgerHero, 'Chummer', 'ledger hero');
    await assertContains(ledgerHero, 'A Shadowrun character manager', 'ledger hero');
    assertProof(await ledgerHero.locator('[data-black-ledger-geoscape-root]').count() === 0, 'Black Ledger geoscape is on the primary homepage');
    assertProof(await ledgerPage.getByText('Black Ledger').count() === 0, 'Black Ledger copy is on the primary homepage');
    const heroActionLinks = ledgerHero.locator('.minimal-actions a.button-like');
    assertProof(await heroActionLinks.count() > 0, 'Primary hero action links are missing');
    await ledgerHero.locator('.minimal-open-chummer summary').click();
    const ledgerOpenMenu = ledgerHero.locator('.minimal-open-chummer');
    const ledgerBuildButton = ledgerOpenMenu.locator('button.site-open-chummer-menu__button', { hasText: 'Build' }).first();
    const ledgerPlayButton = ledgerOpenMenu.locator('button.site-open-chummer-menu__button[data-disabled-target="/mobile/player"]', { hasText: 'Play' }).first();
    assertProof(await ledgerBuildButton.count() === 1 && await ledgerBuildButton.isDisabled(), 'Build is not gated on ledger frontdoor check');
    assertProof(await ledgerPlayButton.count() === 1 && await ledgerPlayButton.isDisabled(), 'Play is not gated on ledger frontdoor check');
    assertProof(await ledgerOpenMenu.locator('.site-open-chummer-menu__button[href="/build"]').count() === 0, 'Build public link leaked on ledger frontdoor check');
    assertProof(await ledgerOpenMenu.locator('.site-open-chummer-menu__button[href="/mobile/player"]').count() === 0, 'Play public link leaked on ledger frontdoor check');
    assertProof(await ledgerOpenMenu.locator('.site-open-chummer-menu__button[href="/play"]').count() === 0, 'Legacy /play link leaked on ledger frontdoor check');
    const ctaLabels = await heroActionLinks.evaluateAll((items) => items.map((item) => item.textContent ? item.textContent.trim() : ''));
    writeJson('BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json', {
      contractName: 'chummer.black_ledger_globe_frontdoor.v1',
      generated_at_utc: new Date().toISOString(),
      status: 'pass',
      base_url: baseUrl,
      route: '/',
      cta_labels: ctaLabels,
      open_menu_targets: ['/login?next=%2Fbuild', '/login?next=%2Fmobile%2Fplayer', '/login?next=%2Faccount%2Faccess'],
      gated_targets: ['Build', 'Play'],
      public_targets: [],
      ledger_primary: false,
    });
    await ledgerPage.close({ runBeforeUnload: false }).catch(() => undefined);
    if (anchorFailure) {
      throw new Error(anchorFailure);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
""",
        encoding="utf-8",
    )
    command = ["node", str(probe_path)]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    mobile_artifact: dict[str, Any] = {}
    ledger_artifact: dict[str, Any] = {}
    if mobile_artifact_path.exists():
        mobile_artifact = load_json(mobile_artifact_path)
    if ledger_artifact_path.exists():
        ledger_artifact = load_json(ledger_artifact_path)
    anchor_artifact: dict[str, Any] = {}
    if anchor_artifact_path.exists():
        anchor_artifact = load_json(anchor_artifact_path)
    mobile_contract = receipt_contract(mobile_artifact)
    ledger_contract = receipt_contract(ledger_artifact)
    anchor_contract = receipt_contract(anchor_artifact)
    mobile_contract_ok = mobile_contract == expected_mobile_contract
    ledger_contract_ok = ledger_contract == expected_ledger_contract
    anchor_contract_ok = anchor_contract == expected_anchor_contract
    anchor_current_contract = frontdoor_anchor_artifact_matches_current_contract(anchor_artifact)
    return {
        "status": "pass" if exit_code == 0 and mobile_artifact.get("status") == "pass" and ledger_artifact.get("status") == "pass" and anchor_artifact.get("status") == "pass" and mobile_contract_ok and ledger_contract_ok and anchor_contract_ok and anchor_current_contract else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "mobileArtifactPath": str(mobile_artifact_path),
        "ledgerArtifactPath": str(ledger_artifact_path),
        "anchorArtifactPath": str(anchor_artifact_path),
        "mobileArtifactContract": mobile_contract,
        "expectedMobileArtifactContract": expected_mobile_contract,
        "ledgerArtifactContract": ledger_contract,
        "expectedLedgerArtifactContract": expected_ledger_contract,
        "anchorArtifactContract": anchor_contract,
        "expectedAnchorArtifactContract": expected_anchor_contract,
        "mobileArtifact": mobile_artifact,
        "ledgerArtifact": ledger_artifact,
        "anchorArtifact": anchor_artifact,
        "mobileArtifactBaseUrlMatchesRequested": artifact_base_url_matches(mobile_artifact, base_url),
        "ledgerArtifactBaseUrlMatchesRequested": artifact_base_url_matches(ledger_artifact, base_url),
        "anchorArtifactBaseUrlMatchesRequested": artifact_base_url_matches(anchor_artifact, base_url),
        "anchorArtifactCurrentContractSatisfied": anchor_current_contract,
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def orchestrated_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the non-mutating public-edge postdeploy gate.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--skip-preflight", action="store_true", help="Use only for post-fact canonical checks where local build lanes are irrelevant.")
    parser.add_argument("--require-downloads-status-playwright", action="store_true", help="Require the focused browser proof for /downloads and /status.")
    parser.add_argument("--playwright-artifact-dir", help="Artifact directory for the downloads-status Playwright proof.")
    parser.add_argument("--require-mobile-pwa-viewport-playwright", action="store_true", help="Require the focused browser proof for core mobile PWA route viewports.")
    parser.add_argument("--mobile-pwa-viewport-artifact-dir", help="Artifact directory for the mobile PWA viewport Playwright proof.")
    parser.add_argument("--require-pwa-offline-cache-playwright", action="store_true", help="Require the focused browser proof for offline Player and GM mobile PWA routes.")
    parser.add_argument("--pwa-offline-cache-artifact-dir", help="Artifact directory for the PWA offline cache Playwright proof.")
    parser.add_argument("--require-frontdoor-navigation-playwright", action="store_true", help="Require the focused browser proof for front-door Build/Play navigation and Black Ledger de-emphasis.")
    parser.add_argument("--frontdoor-navigation-artifact-dir", help="Artifact directory for the front-door navigation Playwright proof.")
    parser.add_argument("--reuse-existing-playwright-artifacts", action="store_true", help="Reuse existing Playwright-generated receipts from the supplied artifact directories instead of rerunning browser proofs.")
    parser.add_argument("--reuse-artifact-max-age-hours", type=float, default=DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS, help="Maximum age for reused Playwright receipts before the browser proof must rerun.")
    parser.add_argument("--release-channel-receipt", default=str(DEFAULT_RELEASE_CHANNEL_RECEIPT), help="Release-channel receipt used to require visible downloads version parity.")
    parser.add_argument("--skip-release-version-match", action="store_true", help="Do not require public visible Version text to match the release-channel version.")
    parser.add_argument("--overlay-root", default="", help="Mounted /app overlay root that public-edge preflight must validate.")
    args = parser.parse_args(argv)
    release_channel = {} if args.skip_release_version_match else load_optional_json(Path(args.release_channel_receipt))
    expected_release_version = "" if args.skip_release_version_match else str(release_channel.get("version") or "").strip()
    overlay_root = resolve_public_edge_overlay_root(args.overlay_root)

    with tempfile.TemporaryDirectory(prefix="chummer-public-edge-postdeploy-") as temp_dir:
        temp = Path(temp_dir)
        if args.skip_preflight:
            preflight = {
                "contractName": "chummer.public_edge_deploy_preflight.v1",
                "status": "pass",
                "activeLockCount": 0,
                "staleForeignLockCount": 0,
                "staleLookingLockCount": 0,
                "staleForeignLocksIgnored": False,
                "allowStaleForeignBuildLocks": False,
                "skipped": True,
                "findings": [],
            }
        else:
            preflight = run_child(
                [
                    sys.executable,
                    "scripts/check_public_edge_deploy_preflight.py",
                    "--allow-foreign-build-locks",
                    "--allow-stale-foreign-build-locks",
                    "--overlay-root",
                    str(overlay_root),
                ],
                temp / "preflight.json",
                allow_failure=True,
            )

        downloads_command = [
            sys.executable,
            "scripts/verify_downloads_version_marker.py",
            "--base-url",
            args.base_url,
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--release-channel-receipt",
            args.release_channel_receipt,
        ]
        if args.skip_release_version_match:
            downloads_command.append("--skip-release-version-match")
        downloads = run_child(
            downloads_command,
            temp / "downloads.json",
            allow_failure=True,
        )
        pwa_static = run_child(
            [
                sys.executable,
                "scripts/verify_public_pwa_static_assets.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            temp / "pwa-static.json",
            allow_failure=True,
        )
        mobile_ledger = run_child(
            [
                sys.executable,
                "scripts/verify_mobile_pwa_ledger_boundary.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            temp / "mobile-ledger.json",
            allow_failure=True,
        )
        ready_mobile_handoff = run_child(
            [
                sys.executable,
                "scripts/verify_ready_mobile_handoff_contract.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            temp / "ready-mobile-handoff.json",
            allow_failure=True,
        )
        participate_iframe_shell = run_child(
            [
                sys.executable,
                "scripts/verify_participate_iframe_shell.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            temp / "participate-iframe-shell.json",
            allow_failure=True,
        )

    downloads_status_browser = None
    if args.require_downloads_status_playwright:
        artifact_dir = Path(args.playwright_artifact_dir) if args.playwright_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-downloads-status-browser-"))
        downloads_status_browser = run_downloads_status_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
        )
    mobile_pwa_viewport = None
    if args.require_mobile_pwa_viewport_playwright:
        artifact_dir = Path(args.mobile_pwa_viewport_artifact_dir) if args.mobile_pwa_viewport_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-mobile-pwa-viewport-"))
        mobile_pwa_viewport = run_mobile_pwa_viewport_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
        )
    pwa_offline_cache = None
    if args.require_pwa_offline_cache_playwright:
        artifact_dir = Path(args.pwa_offline_cache_artifact_dir) if args.pwa_offline_cache_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-pwa-offline-cache-"))
        pwa_offline_cache = run_pwa_offline_cache_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
        )
    frontdoor_navigation = None
    if args.require_frontdoor_navigation_playwright:
        artifact_dir = Path(args.frontdoor_navigation_artifact_dir) if args.frontdoor_navigation_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-frontdoor-navigation-"))
        frontdoor_navigation = run_frontdoor_navigation_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
        )
    role_alias_routes = probe_role_alias_routes(args.base_url.rstrip("/"), args.timeout_seconds)

    result = compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        downloads_status_browser,
        mobile_pwa_viewport,
        frontdoor_navigation,
        pwa_offline_cache,
        expected_release_version,
        role_alias_routes,
    )
    if not args.skip_release_version_match and not expected_release_version:
        result["expectedReleaseVersion"] = ""
        result["visibleVersionMatchesReleaseChannel"] = False
        result["statusRedirectVersionMatchesReleaseChannel"] = False
        result["failures"].append("release channel version is missing")
        result["status"] = "fail"
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1

def main(argv: list[str] | None = None) -> int:
    """Run the orchestrated flagship gate, with the upstream direct verifier available explicitly."""
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-contained-direct" in effective_argv:
        direct_argv = [value for value in effective_argv if value != "--self-contained-direct"]
        return self_contained_main(direct_argv)
    return orchestrated_main(effective_argv)


if __name__ == "__main__":
    raise SystemExit(main())
