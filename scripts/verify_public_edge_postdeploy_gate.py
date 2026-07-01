#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
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


def extract_quoted_values(text: str, pattern: str) -> set[str]:
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r'"([^"]+)"', match.group(1)))


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
    for path, expected_start_prefix in EXPECTED_MANIFESTS.items():
        result = fetch(base_url, path, timeout_seconds)
        manifest_failures: list[str] = []
        payload = parse_json(result, manifest_failures) if result.status_code == 200 else {}
        start_url = str(payload.get("start_url") or "")
        display = str(payload.get("display") or "")
        icons = payload.get("icons") if isinstance(payload.get("icons"), list) else []
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

    service_worker = fetch(base_url, "/service-worker.js", timeout_seconds)
    require(service_worker.status_code == 200, failures, f"/service-worker.js expected 200, got {service_worker.status_code}")
    service_worker_result = inspect_service_worker(service_worker.body, failures)

    return {
        "contractName": "chummer.public_pwa_static_assets.v1",
        "status": "pass" if not failures else "fail",
        "route_count": len(route_results),
        "manifest_count": len(manifest_results),
        "asset_count": len(asset_results),
        "routes": route_results,
        "manifests": manifest_results,
        "assets": asset_results,
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
    packet_routes = payload.get("packet_routes") if isinstance(payload.get("packet_routes"), list) else []
    roles = {str(item.get("roleId") or "") for item in packet_routes if isinstance(item, dict)}
    boundaries = payload.get("boundaries") if isinstance(payload.get("boundaries"), list) else []
    boundary_text = " ".join(str(item) for item in boundaries).lower()

    require(result.status_code == 200, failures, f"/ready/handoff/mobile.json expected 200, got {result.status_code}")
    require(payload.get("status") == "ready", failures, "mobile handoff status is not ready")
    require(payload.get("pwa_route") == "/mobile", failures, "mobile handoff pwa_route is not /mobile")
    require(payload.get("continuity_route") == "/play/continuity", failures, "mobile handoff continuity_route is not /play/continuity")
    require(EXPECTED_PLAYTIME_TOOLS.issubset(tool_ids), failures, f"mobile handoff missing playtime tools: {sorted(EXPECTED_PLAYTIME_TOOLS - tool_ids)}")
    require(EXPECTED_READY_ROLES.issubset(roles), failures, f"mobile handoff missing packet roles: {sorted(EXPECTED_READY_ROLES - roles)}")
    require("character building" in boundary_text and "before or after" in boundary_text, failures, "mobile handoff missing character-building boundary")
    require("opt-in" in boundary_text or "opt in" in boundary_text, failures, "mobile handoff missing living-world opt-in boundary")
    require("gm remains final authority" in boundary_text, failures, "mobile handoff missing GM authority boundary")

    return {
        "contractName": "chummer.ready_mobile_handoff_contract.v1",
        "status": "pass" if not failures else "fail",
        "status_code": result.status_code,
        "pwa_route": payload.get("pwa_route"),
        "continuity_route": payload.get("continuity_route"),
        "tool_ids": sorted(tool_ids),
        "packet_roles": sorted(roles),
        "failures": failures,
    }


def verify_mobile_ledger(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    result = fetch(base_url, "/mobile/pwa/ledger.json", timeout_seconds)
    payload = parse_json(result, failures) if result.status_code == 200 else {}
    cache_control = result.headers.get("cache-control", "")
    vary = result.headers.get("vary", "")
    pragma = result.headers.get("pragma", "")

    require(result.status_code == 200, failures, f"/mobile/pwa/ledger.json expected 200, got {result.status_code}")
    require(payload.get("mode") == "mobile_pwa_living_world", failures, "mobile ledger payload mode is wrong")
    require(payload.get("status") == "opt_in_required", failures, "mobile ledger should require opt-in for anonymous access")
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
        "cache_control": cache_control,
        "vary": vary,
        "pragma": pragma,
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


def summarize_child(name: str, child: dict[str, Any], failures: list[str]) -> str:
    status = str(child.get("status") or "fail")
    if status != "pass":
        failures.append(f"{name} proof is not pass")
    return status


def verify(base_url: str, timeout_seconds: float, skip_preflight: bool) -> dict[str, Any]:
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
    }

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
        "readyMobileHandoffToolIds": child_receipts["readyMobileHandoff"].get("tool_ids", []),
        "readyMobileHandoffPacketRoles": child_receipts["readyMobileHandoff"].get("packet_roles", []),
        "mobileLedgerPayloadStatus": child_receipts["mobileLedger"].get("payload_status", ""),
        "mobileLedgerCacheControl": child_receipts["mobileLedger"].get("cache_control", ""),
        "mobilePwaServiceWorkerBoundaryMode": child_receipts["mobilePwaServiceWorkerBoundary"].get("mobileRuntime", {}).get("serviceWorkerBoundaryMode", ""),
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
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    result = verify(args.base_url, args.timeout_seconds, args.skip_preflight)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
