#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


PORTAL_CACHE_NAME = "chummer-public-v4"
LEDGER_ROUTE = "/mobile/pwa/ledger.json"
MOBILE_ROUTES = (
    "/mobile",
    "/mobile/player",
    "/mobile/gm",
    "/mobile/observer",
    "/play",
    "/play/continuity",
)
MANIFEST_ROUTES = (
    "/manifest.webmanifest",
    "/site.webmanifest",
    "/manifest.json",
    "/manifest.player.webmanifest",
    "/manifest.gm.webmanifest",
)
ROOT_REGISTRATION_RE = re.compile(
    r'navigator\.serviceWorker\.register\(\s*"(?P<script>[^"]+)"(?:\s*,\s*\{[^}]*scope:\s*"(?P<scope>[^"]+)"[^}]*\})?',
    re.DOTALL,
)


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
    request = Request(url, headers={"User-Agent": "ChummerMobilePwaServiceWorkerBoundary/1.0"})
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


def classify_worker(body: str) -> str:
    if "play-shell-v" in body or "play_public_route_network_unavailable" in body:
        return "play_root_worker"
    if f'CACHE_NAME = "{PORTAL_CACHE_NAME}"' in body and "handlePush" in body:
        return "portal_public_root_worker"
    return "unknown"


def extract_service_worker_registrations(body: str) -> list[dict[str, str]]:
    registrations: list[dict[str, str]] = []
    for match in ROOT_REGISTRATION_RE.finditer(body):
        registrations.append(
            {
                "script": match.group("script") or "",
                "scope": match.group("scope") or "",
            }
        )
    return registrations


def classify_registration_boundary(registrations: list[dict[str, str]], root_worker_kind: str) -> str:
    for registration in registrations:
        script = registration.get("script", "")
        scope = registration.get("scope", "")
        if script == "/service-worker.js" and scope == "/" and root_worker_kind == "portal_public_root_worker":
            return "shared_portal_root_worker"
        if script in {"/mobile-sw.js", "/mobile/service-worker.js"} and scope.startswith("/mobile"):
            return "scoped_mobile_worker"
    return "unknown"


def verify(base_url: str, timeout_seconds: float = 25.0) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    failures: list[str] = []

    service_worker = fetch(normalized_base_url, "/service-worker.js", timeout_seconds)
    worker_kind = classify_worker(service_worker.body)
    require(service_worker.status_code == 200, failures, f"/service-worker.js expected 200, got {service_worker.status_code}")
    require(worker_kind == "portal_public_root_worker", failures, f"root service worker must stay portal-owned, got {worker_kind}")
    require(f'CACHE_NAME = "{PORTAL_CACHE_NAME}"' in service_worker.body, failures, f"root service worker missing {PORTAL_CACHE_NAME}")
    require('self.addEventListener("push"' in service_worker.body, failures, "root service worker missing push handler")
    require('self.addEventListener("notificationclick"' in service_worker.body, failures, "root service worker missing notification click handler")
    require("play_public_route_network_unavailable" not in service_worker.body, failures, "root service worker appears to be the play shell worker")
    for route in MOBILE_ROUTES:
        require(route in service_worker.body, failures, f"root service worker missing mobile route {route}")
    for route in MANIFEST_ROUTES:
        require(route in service_worker.body, failures, f"root service worker missing manifest route {route}")
    require("NON_CACHEABLE_PATHS" in service_worker.body, failures, "root service worker missing non-cacheable path set")
    require(f'"{LEDGER_ROUTE}"' in service_worker.body, failures, "root service worker missing mobile ledger no-cache route")
    require('"/api"' in service_worker.body, failures, "root service worker must keep API paths non-cacheable")
    require('"/account"' in service_worker.body, failures, "root service worker must keep account paths non-cacheable")

    mobile_runtime = fetch(normalized_base_url, "/mobile-turn-companion.js", timeout_seconds)
    registrations = extract_service_worker_registrations(mobile_runtime.body)
    boundary_mode = classify_registration_boundary(registrations, worker_kind)
    require(mobile_runtime.status_code == 200, failures, f"/mobile-turn-companion.js expected 200, got {mobile_runtime.status_code}")
    require(bool(registrations), failures, "mobile runtime does not register a service worker")
    require(boundary_mode != "unknown", failures, "mobile runtime service-worker registration boundary is not recognized")

    ledger = fetch(normalized_base_url, LEDGER_ROUTE, timeout_seconds)
    ledger_payload = parse_json(ledger, failures) if ledger.status_code == 200 else {}
    cache_control = ledger.headers.get("cache-control", "")
    vary = ledger.headers.get("vary", "")
    pragma = ledger.headers.get("pragma", "")
    require(ledger.status_code == 200, failures, f"{LEDGER_ROUTE} expected 200, got {ledger.status_code}")
    require(ledger_payload.get("status") == "opt_in_required", failures, "mobile ledger must require opt-in without a signed-in session")
    require("private" in cache_control.lower(), failures, "mobile ledger response is not private")
    require("no-store" in cache_control.lower(), failures, "mobile ledger response is not no-store")
    require("no-cache" in cache_control.lower(), failures, "mobile ledger response is not no-cache")
    require("cookie" in vary.lower() and "authorization" in vary.lower(), failures, "mobile ledger response must vary on Cookie and Authorization")
    require("no-cache" in pragma.lower(), failures, "mobile ledger response missing Pragma no-cache")

    return {
        "contractName": "chummer.mobile_pwa_service_worker_boundary.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "baseUrl": normalized_base_url,
        "status": "pass" if not failures else "fail",
        "rootWorker": {
            "path": "/service-worker.js",
            "status_code": service_worker.status_code,
            "content_type": service_worker.content_type,
            "kind": worker_kind,
            "sha256": service_worker.sha256,
        },
        "mobileRuntime": {
            "path": "/mobile-turn-companion.js",
            "status_code": mobile_runtime.status_code,
            "content_type": mobile_runtime.content_type,
            "serviceWorkerBoundaryMode": boundary_mode,
            "registrations": registrations,
            "sha256": mobile_runtime.sha256,
        },
        "ledgerBoundary": {
            "path": LEDGER_ROUTE,
            "status_code": ledger.status_code,
            "payload_status": ledger_payload.get("status"),
            "cache_control": cache_control,
            "pragma": pragma,
            "vary": vary,
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify mobile PWA service-worker and ledger non-interference boundaries.")
    parser.add_argument("--base-url", default="https://chummer.run")
    parser.add_argument("--timeout-seconds", type=float, default=25.0)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    result = verify(args.base_url, args.timeout_seconds)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        from pathlib import Path

        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
