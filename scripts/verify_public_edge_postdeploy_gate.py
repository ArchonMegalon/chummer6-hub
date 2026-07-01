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


def verify_downloads(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    downloads = fetch(base_url, "/downloads", timeout_seconds)
    status = fetch(base_url, "/status", timeout_seconds)
    release = fetch(base_url, "/downloads/RELEASE_CHANNEL.generated.json", timeout_seconds)
    release_payload = parse_json(release, failures) if release.status_code == 200 else {}

    downloads_version = extract_downloads_version_marker(downloads.body)
    status_version = extract_downloads_version_marker(status.body)
    release_version = str(release_payload.get("releaseVersion") or release_payload.get("version") or "")
    release_status = str(release_payload.get("status") or "")
    release_rollout = str(release_payload.get("rolloutState") or "")
    release_supportability = str(release_payload.get("supportabilityState") or "")

    require(downloads.status_code == 200, failures, f"/downloads expected 200, got {downloads.status_code}")
    require(status.status_code == 200, failures, f"/status expected 200, got {status.status_code}")
    require(release.status_code == 200, failures, f"/downloads/RELEASE_CHANNEL.generated.json expected 200, got {release.status_code}")
    require(bool(downloads_version), failures, "/downloads missing data-downloads-release-version marker")
    require(bool(status_version), failures, "/status missing data-downloads-release-version marker")
    if release_version:
        require(downloads_version.endswith(release_version), failures, "/downloads version marker does not match release channel version")
        require(status_version.endswith(release_version), failures, "/status version marker does not match release channel version")
    require(release_status == "published", failures, f"release status expected published, got {release_status or '<empty>'}")
    require(release_rollout == "public_stable", failures, f"release rollout expected public_stable, got {release_rollout or '<empty>'}")
    require(release_supportability == "gold_supported", failures, f"release supportability expected gold_supported, got {release_supportability or '<empty>'}")

    return {
        "contractName": "chummer.downloads_version_marker.v1",
        "status": "pass" if not failures else "fail",
        "downloads_status": downloads.status_code,
        "status_status": status.status_code,
        "release_manifest_status": release.status_code,
        "visible_version": downloads_version,
        "status_redirect_version": status_version,
        "release_version": release_version,
        "release_channel": release_payload.get("channel") or release_payload.get("channelId"),
        "release_rollout_state": release_rollout,
        "release_status": release_status,
        "release_supportability_state": release_supportability,
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

    playwright_bin = ROOT / "node_modules" / ".bin" / "playwright"
    playwright_command = [str(playwright_bin)] if playwright_bin.is_file() else ["npx", "--no-install", "playwright"]
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
                env={
                    **os.environ,
                    "BASE_URL": base_url,
                    "CHUMMER_COMPLETION_DIR": str(completion_dir),
                },
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
                "stdoutTail": "\n".join(completed.stdout.splitlines()[-80:]),
                "stderrTail": "\n".join(completed.stderr.splitlines()[-80:]),
            }
            if completed.returncode != 0:
                failures.append(f"{proof_id} Playwright proof exited {completed.returncode}")
        except subprocess.TimeoutExpired as error:
            proof_run = {
                "spec": spec,
                "startedAtUtc": proof_started.isoformat(),
                "completedAtUtc": datetime.now(UTC).isoformat(),
                "returnCode": None,
                "stdoutTail": "\n".join((error.stdout or "").splitlines()[-80:]) if isinstance(error.stdout, str) else "",
                "stderrTail": "\n".join((error.stderr or "").splitlines()[-80:]) if isinstance(error.stderr, str) else "",
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
    playwright_requirements: list[str] | None = None,
    playwright_timeout_seconds: float = 420.0,
    playwright_artifact_dir: Path | None = None,
    expected_portal_image_id: str = "",
    portal_container: str = DEFAULT_PORTAL_CONTAINER,
    portal_image_tag: str = DEFAULT_PORTAL_IMAGE_TAG,
) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    child_receipts = {
        "downloads": verify_downloads(normalized_base_url, timeout_seconds),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify public-edge deployment after Chummer portal publish.")
    parser.add_argument("--base-url", default="https://chummer.run")
    parser.add_argument("--timeout-seconds", type=float, default=25.0)
    parser.add_argument("--skip-preflight", action="store_true", help="Skip active-build process checks for post-fact live verification.")
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


if __name__ == "__main__":
    raise SystemExit(main())
